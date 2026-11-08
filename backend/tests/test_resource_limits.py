import asyncio
import base64
import json
import threading
import time
import zipfile
from dataclasses import replace
import pymupdf as fitz
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.api import chat as chat_api
from app.api.documents import split_faq
from app.core import body_limit
from app.core.body_limit import RequestBodyLimitMiddleware
from app.core.config import settings
from app.core.jwt_auth import create_token_pair
from app.core.limits import (
    ADMIN_UPLOAD_EXTRACTION_LIMITS,
    CHAT_ATTACHMENT_EXTRACTION_LIMITS,
    MAX_CHAT_ATTACHMENT_BYTES,
    MAX_CHAT_ATTACHMENTS,
    MAX_CHAT_MESSAGE_CHARS,
    MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS,
    MAX_REQUEST_BODY_BYTES,
    MAX_TOOL_RESULT_CHARS,
    MIB,
)
from app.models import Conversation, FileAttachment, LlmConnection, Message, MessageCreate
from app.models.database import Base
from app.rag import agent as agent_module
from app.rag.research_session import ResearchSession
from app.rag.tools import ResearchToolRegistry, extract_html_text
from app.services import conversation_files as conversation_files_module
from app.services import pdf_service
from app.services.chat_service import AttachmentQuotaExceeded, ChatService
from app.services.document_processor import DocumentLimitExceeded, DocumentProcessor, DocumentRejected
from test_agent_guardrails import research
from app.services.structured_data import (
    _extract_declared_json,
    _replace_svg_blocks,
    count_rendered_records,
    merge_record_parts,
)
from app.services.pdf_service import PDFService
def data_url(size, mime="text/plain"):
    return f"data:{mime};base64," + base64.b64encode(b"x" * size).decode()
def body_limit_client():
    app = FastAPI()
    @app.post("/api/chat/send")
    async def echo(request: Request):
        return {"size": len(await request.body())}
    @app.post("/api/documents/upload")
    async def upload(request: Request):
        return {"size": len(await request.body())}
    app.add_middleware(RequestBodyLimitMiddleware)
    return TestClient(app)
def test_unauthenticated_large_body_is_rejected_before_parsing():
    client = body_limit_client()
    oversized = b"x" * (MAX_REQUEST_BODY_BYTES + 1)
    assert client.post("/api/chat/send", content=oversized).status_code == 413
    def chunks():
        for _ in range(3):
            yield b"x" * (MAX_REQUEST_BODY_BYTES // 2)
    assert client.post("/api/chat/send", content=chunks()).status_code == 413
    assert client.post("/api/chat/send", content=b"x" * 100).json() == {"size": 100}
def test_valid_access_token_raises_limit_for_large_body_routes(monkeypatch):
    claims = {b"Bearer member": {"is_admin": False}, b"Bearer admin": {"is_admin": True}}
    monkeypatch.setattr(body_limit, "_access_token_claims", lambda headers: claims.get(headers.get(b"authorization")))
    client = body_limit_client()
    payload = b"x" * (2 * MIB)
    assert client.post("/api/chat/send", content=payload, headers={"Authorization": "Bearer bad"}).status_code == 413
    assert client.post("/api/chat/send", content=payload, headers={"Authorization": "Bearer member"}).json() == {"size": 2 * MIB}
    assert client.post("/api/documents/upload", content=payload, headers={"Authorization": "Bearer member"}).status_code == 413
    assert client.post("/api/documents/upload", content=payload, headers={"Authorization": "Bearer admin"}).json() == {"size": 2 * MIB}
def test_access_token_check_requires_signed_access_token():
    token = create_token_pair({"user_id": 1, "username": "u", "is_admin": True})
    claims = body_limit._access_token_claims({b"authorization": f"Bearer {token['access_token']}".encode()})
    assert claims["sub"] == "1" and claims["is_admin"] is True
    assert body_limit._access_token_claims({b"authorization": f"Bearer {token['refresh_token']}".encode()}) is None
    assert body_limit._access_token_claims({b"authorization": b"Bearer not-a-token"}) is None
@pytest.mark.parametrize("url", [
    "https://attacker.example/pixel.png",
    "http://169.254.169.254/latest/meta-data/",
    "data:image/png,rawbytes",
    "data:image/png;base64,not base64!",
])
def test_attachment_must_be_base64_data_url(url):
    with pytest.raises(ValidationError):
        FileAttachment(filename="a.png", file_type="image/png", data_url=url)
def test_attachment_count_size_and_message_length_are_bounded():
    FileAttachment(filename="ok.txt", file_type="text/plain", data_url=data_url(1024))
    with pytest.raises(ValidationError):
        FileAttachment(filename="big.txt", file_type="text/plain", data_url=data_url(MAX_CHAT_ATTACHMENT_BYTES + 3))
    small = {"filename": "a.txt", "file_type": "text/plain", "data_url": data_url(10)}
    with pytest.raises(ValidationError):
        MessageCreate(content="hi", connection_id=1, model_name="m", attachments=[small] * (MAX_CHAT_ATTACHMENTS + 1))
    near_max = {"filename": "a.txt", "file_type": "text/plain", "data_url": data_url(MAX_CHAT_ATTACHMENT_BYTES - 3)}
    with pytest.raises(ValidationError):
        MessageCreate(content="hi", connection_id=1, model_name="m", attachments=[near_max, near_max])
    with pytest.raises(ValidationError):
        MessageCreate(content="x" * (MAX_CHAT_MESSAGE_CHARS + 1), connection_id=1, model_name="m")
@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()
def add_connection(db, owner_id, models=("model-a",)):
    connection = LlmConnection(name="測試連線", provider="ollama", api_base="http://127.0.0.1:9",
                               models=json.dumps(list(models)), owner_id=owner_id)
    db.add(connection)
    db.commit()
    return connection
@pytest.mark.anyio
async def test_connections_and_models_the_user_cannot_use_are_rejected(db):
    own = add_connection(db, owner_id=1)
    others = add_connection(db, owner_id=2)
    for connection_id, model in ((others.id, "model-a"), (own.id, "expensive-model"), (own.id + 100, "model-a")):
        with pytest.raises(HTTPException) as exc_info:
            await chat_api.send_message(MessageCreate(content="hi", connection_id=connection_id, model_name=model), db=db, user_id=1)
        assert exc_info.value.status_code == 400
    assert db.query(Message).count() == 0
@pytest.mark.anyio
async def test_concurrent_stream_limit_per_user(monkeypatch, db):
    connection = add_connection(db, owner_id=7)
    monkeypatch.setattr(chat_api, "_active_streams", {7: chat_api.MAX_CONCURRENT_CHAT_STREAMS_PER_USER})
    with pytest.raises(HTTPException) as exc_info:
        await chat_api.send_message(MessageCreate(content="hi", connection_id=connection.id, model_name="model-a"), db=db, user_id=7)
    assert exc_info.value.status_code == 429
@pytest.mark.anyio
async def test_stream_slot_is_released_when_rag_fails(monkeypatch, db):
    connection = add_connection(db, owner_id=7)
    monkeypatch.setattr(chat_api, "_active_streams", {})
    class FailingRag:
        async def generate_response_stream(self, *args, **kwargs):
            raise RuntimeError("模型連線失敗")
            yield
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: FailingRag())
    response = await chat_api.send_message(MessageCreate(content="hi", connection_id=connection.id, model_name="model-a"), db=db, user_id=7)
    body = "".join([chunk async for chunk in response.body_iterator])
    assert "event: error" in body
    assert chat_api._active_streams == {}
@pytest.mark.anyio
async def test_stream_slot_is_released_when_client_disconnects(monkeypatch, db):
    connection = add_connection(db, owner_id=7)
    monkeypatch.setattr(chat_api, "_active_streams", {})
    class EndlessRag:
        async def generate_response_stream(self, *args, **kwargs):
            yield {"event": "token", "data": {"content": "半"}}
            await asyncio.Event().wait()
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: EndlessRag())
    response = await chat_api.send_message(MessageCreate(content="hi", connection_id=connection.id, model_name="model-a"), db=db, user_id=7)
    stream = response.body_iterator
    assert "event: start" in await stream.__anext__()
    assert "event: token" in await stream.__anext__()
    assert chat_api._active_streams == {7: 1}
    await stream.aclose()
    assert chat_api._active_streams == {}
def test_attachment_storage_quota(monkeypatch, db):
    monkeypatch.setattr(conversation_files_module, "MAX_USER_ATTACHMENT_STORAGE_BYTES", 1000)
    service = ChatService()
    service.save_message(db, 1, "q", True, context_used="x" * 900)
    service.ensure_attachment_quota(db, 1, 100)
    with pytest.raises(AttachmentQuotaExceeded):
        service.ensure_attachment_quota(db, 1, 101)
    service.ensure_attachment_quota(db, 2, 1000)
def test_attachment_text_is_stored_only_within_the_quota(monkeypatch, db):
    service = ChatService()
    context = json.dumps({"attachments": [{"filename": "a.txt"}]})
    message = service.save_message(db, 1, "q", True, context_used=context)
    monkeypatch.setattr(conversation_files_module, "MAX_USER_ATTACHMENT_STORAGE_BYTES", len(context) + 50)
    service.save_attachment_texts(db, message.id, ["x" * 100])
    db.refresh(message)
    assert message.context_used == context
    service.save_attachment_texts(db, message.id, ["x" * 10])
    db.refresh(message)
    assert json.loads(message.context_used)["attachments"][0]["content"] == "x" * 10
@pytest.mark.anyio
async def test_concurrent_attachment_messages_cannot_exceed_the_quota(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'quota.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    attachment = FileAttachment(filename="a.txt", file_type="text/plain", data_url="data:text/plain;base64,QUFBQQ==")
    one_message = len(json.dumps({"attachments": [attachment.dict(exclude={"data_url"})]}, ensure_ascii=False)) + len(b"AAAA")
    monkeypatch.setattr(conversation_files_module, "MAX_USER_ATTACHMENT_STORAGE_BYTES", one_message * 3 // 2)
    real_check = chat_api.chat_service.ensure_attachment_quota
    def slow_check(db, user_id, new_bytes):
        real_check(db, user_id, new_bytes)
        time.sleep(0.05)
    monkeypatch.setattr(chat_api.chat_service, "ensure_attachment_quota", slow_check)
    with Session() as session:
        connection_id = add_connection(session, owner_id=1).id
    async def send():
        try:
            message = MessageCreate(content="看附件", connection_id=connection_id, model_name="model-a", attachments=[attachment])
            await chat_api.send_message(message, db=Session(), user_id=1)
            return 200
        except HTTPException as exc:
            return exc.status_code
    statuses = await asyncio.gather(*(send() for _ in range(5)))
    assert sorted(statuses) == [200, 413, 413, 413, 413]
    with Session() as session:
        assert session.query(Message).filter(Message.context_used.isnot(None)).count() == 1
    engine.dispose()
def test_conversation_list_and_detail_carry_no_messages(db):
    service = ChatService()
    conversation = Conversation(user_id=1, title="t")
    db.add(conversation)
    db.commit()
    context = '{"attachments": [{"filename": "a.png", "file_type": "image/png", "data_url": "data:image/png;base64,AAAA"}]}'
    for index in range(12):
        db.add(Message(conversation_id=conversation.id, content=f"m{index}", is_user=True, context_used=context))
    db.commit()
    listed = service.get_user_conversations(db, 1)
    assert [(c.id, c.title, c.messages) for c in listed] == [(conversation.id, "t", [])]
    assert service.get_conversation_with_messages(db, conversation.id, 1).messages == []
    messages = service.get_conversation_messages(db, conversation.id, 1, limit=5)
    assert [m.content for m in messages] == [f"m{i}" for i in range(7, 12)]
    assert all(m.context_used is None for m in messages)
    assert messages[0].attachments[0].data_url == "data:image/png;base64,AAAA"
@pytest.mark.anyio
async def test_attachment_parsing_runs_off_the_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    seen = {}
    def fake_extract(fname, ftype, url, ocr):
        seen["thread"] = threading.get_ident()
        return "附件內容" * 100000
    monkeypatch.setattr(agent_module, "_extract_attachment_text", fake_extract)
    monkeypatch.setattr(agent_module, "_attachment_ocr", lambda: None)
    async def fake_chat_completion(messages, **kwargs):
        seen["user_content"] = messages[-1]["content"]
        return {"role": "assistant", "content": "好"}
    monkeypatch.setattr(agent_module, "chat_completion", fake_chat_completion)
    registry = ResearchToolRegistry()
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None, conversation_id=None: [])
    agent = agent_module.ResearchAgent(tool_registry=registry)
    attachment = FileAttachment(filename="a.txt", file_type="text/plain", data_url=data_url(10))
    [event async for event in research(agent, "摘要", attachments=[attachment])]
    assert seen["thread"] != loop_thread
    assert len(seen["user_content"]) < agent_module.MAX_ATTACHMENT_TEXT_CHARS + 1000
def blank_pdf(tmp_path, pages, size=(595, 842)):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=size[0], height=size[1])
    path = tmp_path / "scan.pdf"
    doc.save(path)
    doc.close()
    return str(path)
def test_ocr_rendering_is_single_threaded_pixel_bounded_and_page_capped(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf_service, "MAX_OCR_PIXELS", 40_000)
    main_thread = threading.get_ident()
    rendered = []
    original_render = PDFService._render_page_png.__func__
    def recording_render(cls, page):
        png = original_render(cls, page)
        pix = fitz.Pixmap(png)
        rendered.append((threading.get_ident(), pix.width * pix.height))
        return png
    ocr_calls = []
    monkeypatch.setattr(PDFService, "_render_page_png", classmethod(recording_render))
    monkeypatch.setattr(PDFService, "_ocr_page_sync", classmethod(lambda cls, ocr, img, page_num: ocr_calls.append(page_num) or f"第{page_num}頁文字"))
    text = PDFService.extract_text_robust(blank_pdf(tmp_path, 5, size=(14400, 14400)), max_ocr_pages=2, ocr=lambda png: "")
    assert sorted(ocr_calls) == [1, 2]
    assert [thread for thread, _ in rendered] == [main_thread, main_thread]
    assert all(pixels <= 40_000 * 1.05 for _, pixels in rendered)
    assert "超過每份文件的 OCR 頁數上限" in text
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="png" ContentType="image/png"/>'
    '<Override PartName="/word/body.bin" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>'
)
def write_zip(path, members):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return str(path)
def test_ooxml_decompression_bomb_is_rejected(tmp_path):
    path = write_zip(tmp_path / "bomb.docx", {"[Content_Types].xml": "<Types/>", "word/document.xml": b"\0" * (64 * MIB)})
    with pytest.raises(DocumentLimitExceeded, match="壓縮"):
        DocumentProcessor.extract_text_from_file(path, DOCX_TYPE, ADMIN_UPLOAD_EXTRACTION_LIMITS, None)
def test_ooxml_ratio_is_checked_across_small_members(tmp_path):
    members = {"[Content_Types].xml": "<Types/>"}
    members.update({f"word/part{index}.xml": b"\0" * MIB for index in range(11)})
    path = write_zip(tmp_path / "split.docx", members)
    for limits in (ADMIN_UPLOAD_EXTRACTION_LIMITS, CHAT_ATTACHMENT_EXTRACTION_LIMITS):
        with pytest.raises(DocumentLimitExceeded, match="壓縮"):
            DocumentProcessor.extract_text_from_file(path, DOCX_TYPE, limits, None)
def test_attachment_xml_budget_follows_content_types(tmp_path):
    limits = replace(CHAT_ATTACHMENT_EXTRACTION_LIMITS, max_ooxml_xml_bytes=4096)
    xml_body = ("<w:p>" + "段落文字" * 1000 + "</w:p>").encode()
    renamed = write_zip(tmp_path / "renamed.docx", {"[Content_Types].xml": CONTENT_TYPES_XML, "word/body.bin": xml_body})
    with pytest.raises(DocumentLimitExceeded, match="XML"):
        DocumentProcessor.extract_text_from_file(renamed, DOCX_TYPE, limits, None)
    media = write_zip(tmp_path / "media.docx", {"[Content_Types].xml": CONTENT_TYPES_XML, "word/media/image1.png": xml_body})
    DocumentProcessor._check_ooxml_archive(media, limits, builds_dom=True)
    DocumentProcessor._check_ooxml_archive(renamed, limits, builds_dom=False)
    rels = write_zip(tmp_path / "rels.docx", {"[Content_Types].xml": "<Types/>", "word/_rels/body.bin.rels": xml_body})
    with pytest.raises(DocumentLimitExceeded, match="XML"):
        DocumentProcessor._check_ooxml_archive(rels, limits, builds_dom=True)
def test_ooxml_member_count_is_bounded(tmp_path):
    limits = replace(ADMIN_UPLOAD_EXTRACTION_LIMITS, max_ooxml_members=3)
    members = {"[Content_Types].xml": CONTENT_TYPES_XML}
    members.update({f"ppt/slides/slide{index}.xml": "<p/>" for index in range(3)})
    path = write_zip(tmp_path / "many.pptx", members)
    with pytest.raises(DocumentLimitExceeded, match="檔案數"):
        DocumentProcessor.extract_text_from_file(path, "application/vnd.openxmlformats-officedocument.presentationml.presentation", limits, None)
def test_structured_parse_budget_skips_json_loads(tmp_path):
    path = tmp_path / "posts.json"
    path.write_text('[{"author": "喵", "content": "第一則"}]', encoding="utf-8")
    structured = DocumentProcessor.extract_text_from_file(str(path), "application/json", ADMIN_UPLOAD_EXTRACTION_LIMITS, None)
    assert structured.startswith("[記錄 1]")
    raw = DocumentProcessor.extract_text_from_file(
        str(path), "application/json", replace(CHAT_ATTACHMENT_EXTRACTION_LIMITS, max_structured_parse_chars=10), None
    )
    assert raw.startswith("[{")
def test_attachment_over_budget_is_reported_instead_of_parsed(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "CHAT_ATTACHMENT_EXTRACTION_LIMITS", replace(CHAT_ATTACHMENT_EXTRACTION_LIMITS, max_ooxml_members=1))
    path = write_zip(tmp_path / "a.docx", {"[Content_Types].xml": CONTENT_TYPES_XML, "word/body.bin": "<w:p/>"})
    with open(path, "rb") as handle:
        url = f"data:{DOCX_TYPE};base64," + base64.b64encode(handle.read()).decode()
    text = agent_module._extract_attachment_text("a.docx", DOCX_TYPE, url, None)
    assert text.startswith("[附件超過解析上限") and "檔案數" in text
def test_rejected_attachment_is_reported_to_the_model(monkeypatch):
    def reject(*_):
        raise DocumentRejected("PDF 文件中沒有可擷取的文字")
    monkeypatch.setattr(DocumentProcessor, "extract_text_from_file", reject)
    url = "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.7").decode()
    assert agent_module._extract_attachment_text("scan.pdf", "application/pdf", url, None) == "[附件未讀取內容：PDF 文件中沒有可擷取的文字]"
@pytest.mark.anyio
async def test_attachment_extractions_are_bounded_process_wide(monkeypatch):
    assert agent_module.extraction_slots._value == MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS
    monkeypatch.setattr(agent_module, "extraction_slots", asyncio.Semaphore(MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS))
    lock = threading.Lock()
    running = {"now": 0, "peak": 0}
    def slow_extract(fname, ftype, url, ocr):
        with lock:
            running["now"] += 1
            running["peak"] = max(running["peak"], running["now"])
        time.sleep(0.05)
        with lock:
            running["now"] -= 1
        return "內容"
    async def fake_chat_completion(messages, **kwargs):
        return {"role": "assistant", "content": "好"}
    monkeypatch.setattr(agent_module, "_extract_attachment_text", slow_extract)
    monkeypatch.setattr(agent_module, "_attachment_ocr", lambda: None)
    monkeypatch.setattr(agent_module, "chat_completion", fake_chat_completion)
    registry = ResearchToolRegistry()
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None, conversation_id=None: [])
    attachments = [FileAttachment(filename=f"{i}.txt", file_type="text/plain", data_url=data_url(10)) for i in range(2)]
    async def ask():
        agent = agent_module.ResearchAgent(tool_registry=registry)
        return [event async for event in research(agent, "摘要", attachments=attachments)]
    await asyncio.gather(*(ask() for _ in range(MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS + 2)))
    assert running["peak"] == MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS
def assert_fast(func, *args, limit=2.0):
    started = time.monotonic()
    result = func(*args)
    assert time.monotonic() - started < limit
    return result
def test_text_cleanup_is_linear():
    assert _replace_svg_blocks("a<svg x>1</svg>b<svg>2</svg>c") == "a[SVG_ICON_OMITTED]b[SVG_ICON_OMITTED]c"
    assert _replace_svg_blocks("a<svg unclosed") == "a<svg unclosed"
    assert_fast(_replace_svg_blocks, "<svg " * 200_000)
    assert _extract_declared_json('const posts = [{"a": 1}];') == '[{"a": 1}]'
    assert_fast(_extract_declared_json, "const x = [{" + "}" * 200_000)
    title, text = extract_html_text("<html><title>T</title><script>bad()</script><p>Hi <b>there</b></p></html>")
    assert title == "T" and "bad" not in text and "Hi there" in text
    assert_fast(extract_html_text, "<script" * 100_000)
    assert_fast(extract_html_text, "<" * 300_000)
def test_split_faq_is_linear_and_keeps_semantics():
    text = "Q：特休幾天？\nA：依年資。\n補充說明\nＱ: 病假？\nＡ: 一年三十天"
    assert split_faq(text) == [("特休幾天？", "依年資。\n補充說明"), ("病假？", "一年三十天")]
    assert assert_fast(split_faq, "Q: x\n" * 100_000) == []
def test_rendered_record_scans_are_linear():
    assert count_rendered_records("[記錄 1]a\nauthor: a\n\n---\n\n[data 記錄 2]b\nauthor: b") == 2
    assert_fast(count_rendered_records, "[" + "a " * 200_000)
    assert_fast(count_rendered_records, "[記錄 1]---" + "\n" * 200_000 + "x")
    assert_fast(merge_record_parts, ["[記錄 1]（1/2）" + "（" * 200_000, "[記錄 1]（2/2）\nx"])
def test_fallback_summary_toc_cleanup_is_linear():
    line = "1. 章節" + " " * 50_000 + "x"
    assert_fast(DocumentProcessor._generate_fallback_summary, "doc.txt", "\n".join([line] * 20))
def test_tool_results_are_truncated_before_reaching_the_model():
    wrapped = ResearchSession(["q"]).wrap_tool_output({"data": "x" * (MAX_TOOL_RESULT_CHARS * 3)})
    assert len(wrapped) < MAX_TOOL_RESULT_CHARS + 500
@pytest.mark.anyio
async def test_filter_records_bounds_date_range_and_limit():
    class Store:
        documents = [type("D", (), {"page_content": f"發布時間: 2026-08-{d:02d} 內容", "metadata": {"chunk_id": d}})() for d in range(1, 29)]
    registry = ResearchToolRegistry(retriever=type("R", (), {"vector_store": Store()})())
    result = await registry.filter_and_count_records(date_range="2026-08", limit=10_000)
    assert result["returned_count"] <= 50
    too_long = await registry.filter_and_count_records(date_range="2026-08-01 " * 100)
    assert "error" in too_long