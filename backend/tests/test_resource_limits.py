"""
單一後端行程的資源上限與付費用量
驗證：
1. 請求本文上限在驗證相依之前生效，只有帶有效存取權杖的聊天／上傳請求才放寬
2. 聊天附件只接受 base64 data: URL，並限制數量、單檔與總量；訊息長度有上限
3. 模型名稱必須在可用清單內；每位使用者的並行串流與附件儲存量有上限
4. 對話清單只帶最近幾則訊息、不含附件本體與原始 context_used
5. 附件在執行緒中解析；PDF 點陣化有像素上限、在單一執行緒進行、OCR 頁數有上限；OOXML 擋壓縮炸彈
6. 會超線性回溯的清洗與切分邏輯改為線性；工具結果與篩選參數有上限；遠端模型清單有快取
"""
import asyncio
import base64
import io
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
from app.api import tags as tags_api
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
from app.models import Conversation, FileAttachment, Message, MessageCreate
from app.models.database import Base
from app.rag import agent as agent_module
from app.rag.research_session import ResearchSession
from app.rag.tools import ResearchToolRegistry, extract_html_text
from app.services import chat_service as chat_service_module
from app.services import pdf_service
from app.services.chat_service import AttachmentQuotaExceeded, ChatService
from app.services.document_processor import (
    DocumentLimitExceeded,
    DocumentProcessor,
    _extract_declared_json,
    _replace_svg_blocks,
)
from app.services.pdf_service import PDFService


def data_url(size, mime="text/plain"):
    return f"data:{mime};base64," + base64.b64encode(b"x" * size).decode()


# ---------- 1. 請求本文上限 ----------

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
    # 文件上傳只限管理員：一般使用者的有效權杖不會放寬本文上限
    assert client.post("/api/documents/upload", content=payload, headers={"Authorization": "Bearer member"}).status_code == 413
    assert client.post("/api/documents/upload", content=payload, headers={"Authorization": "Bearer admin"}).json() == {"size": 2 * MIB}


def test_access_token_check_requires_signed_access_token():
    token = create_token_pair({"user_id": 1, "username": "u", "is_admin": True})
    claims = body_limit._access_token_claims({b"authorization": f"Bearer {token['access_token']}".encode()})
    assert claims["sub"] == "1" and claims["is_admin"] is True
    assert body_limit._access_token_claims({b"authorization": f"Bearer {token['refresh_token']}".encode()}) is None
    assert body_limit._access_token_claims({b"authorization": b"Bearer not-a-token"}) is None


# ---------- 2. 聊天附件與訊息驗證 ----------

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
        MessageCreate(content="hi", attachments=[small] * (MAX_CHAT_ATTACHMENTS + 1))
    near_max = {"filename": "a.txt", "file_type": "text/plain", "data_url": data_url(MAX_CHAT_ATTACHMENT_BYTES - 3)}
    with pytest.raises(ValidationError):
        MessageCreate(content="hi", attachments=[near_max, near_max])
    with pytest.raises(ValidationError):
        MessageCreate(content="x" * (MAX_CHAT_MESSAGE_CHARS + 1))


# ---------- 3. 模型、並行與配額 ----------

@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.mark.anyio
async def test_unlisted_model_is_rejected(monkeypatch, db):
    monkeypatch.setattr(settings, "AVAILABLE_MODELS", "model-a,model-b")
    monkeypatch.setattr(settings, "MODEL_NAME", None)
    with pytest.raises(HTTPException) as exc_info:
        await chat_api.send_message(MessageCreate(content="hi", model_name="expensive-model"), db=db, user_id=1)
    assert exc_info.value.status_code == 400
    assert db.query(Message).count() == 0
    await chat_api._ensure_model_allowed("model-b")


@pytest.mark.anyio
async def test_concurrent_stream_limit_per_user(monkeypatch, db):
    monkeypatch.setattr(settings, "AVAILABLE_MODELS", "model-a")
    monkeypatch.setattr(chat_api, "_active_streams", {7: chat_api.MAX_CONCURRENT_CHAT_STREAMS_PER_USER})
    with pytest.raises(HTTPException) as exc_info:
        await chat_api.send_message(MessageCreate(content="hi"), db=db, user_id=7)
    assert exc_info.value.status_code == 429


def test_attachment_storage_quota(monkeypatch, db):
    monkeypatch.setattr(chat_service_module, "MAX_USER_ATTACHMENT_STORAGE_BYTES", 1000)
    service = ChatService()
    service.save_message(db, 1, "q", True, context_used="x" * 900)
    service.ensure_attachment_quota(db, 1, 100)
    with pytest.raises(AttachmentQuotaExceeded):
        service.ensure_attachment_quota(db, 1, 101)
    # 其他使用者不受影響
    service.ensure_attachment_quota(db, 2, 1000)


# ---------- 4. 對話清單 ----------

def test_conversation_list_is_bounded_and_omits_attachment_bodies(db):
    service = ChatService()
    conversation = Conversation(user_id=1, title="t")
    db.add(conversation)
    db.commit()
    context = '{"attachments": [{"filename": "a.png", "file_type": "image/png", "data_url": "data:image/png;base64,AAAA"}]}'
    for index in range(12):
        db.add(Message(conversation_id=conversation.id, content=f"m{index}", is_user=True, context_used=context))
    db.commit()

    listed = service.get_user_conversations(db, 1)
    messages = listed[0].messages
    assert [m.content for m in messages] == [f"m{i}" for i in range(7, 12)]
    assert all(m.context_used is None for m in messages)
    assert messages[0].attachments[0].data_url is None
    assert messages[0].attachments[0].filename == "a.png"

    full = service.get_conversation_with_messages(db, conversation.id, 1)
    assert full.messages[0].attachments[0].data_url == "data:image/png;base64,AAAA"


# ---------- 5. 附件解析 ----------

@pytest.mark.anyio
async def test_attachment_parsing_runs_off_the_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    seen = {}

    def fake_extract(fname, ftype, url):
        seen["thread"] = threading.get_ident()
        return "附件內容" * 100000

    monkeypatch.setattr(agent_module, "_extract_attachment_text", fake_extract)

    async def fake_chat_completion(messages, **kwargs):
        seen["user_content"] = messages[-1]["content"]
        return {"role": "assistant", "content": "好"}

    monkeypatch.setattr(agent_module, "chat_completion", fake_chat_completion)
    registry = ResearchToolRegistry()
    monkeypatch.setattr(registry, "get_tool_definitions", lambda: [])
    agent = agent_module.ResearchAgent(tool_registry=registry)
    attachment = FileAttachment(filename="a.txt", file_type="text/plain", data_url=data_url(10))
    [event async for event in agent.stream_research("摘要", attachments=[attachment], max_turns=1)]

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
    monkeypatch.setattr(PDFService, "_is_vision_available", classmethod(lambda cls: True))
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
    monkeypatch.setattr(PDFService, "_ocr_page_sync", classmethod(lambda cls, img, page_num: ocr_calls.append(page_num) or f"第{page_num}頁文字"))

    text = PDFService.extract_text_robust(blank_pdf(tmp_path, 5, size=(14400, 14400)), max_ocr_pages=2)

    assert sorted(ocr_calls) == [1, 2]
    assert [thread for thread, _ in rendered] == [main_thread, main_thread]
    assert all(pixels <= 40_000 * 1.05 for _, pixels in rendered)
    assert "超過每份文件的 OCR 頁數上限" in text


DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# 主文件部件刻意不用 .xml 副檔名：是否建成 DOM 由內容類型決定
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
        DocumentProcessor.extract_text_from_file(path, DOCX_TYPE, ADMIN_UPLOAD_EXTRACTION_LIMITS)


def test_ooxml_ratio_is_checked_across_small_members(tmp_path):
    # 每個成員都小於逐一檢查的門檻，但整個檔案的壓縮比異常
    members = {"[Content_Types].xml": "<Types/>"}
    members.update({f"word/part{index}.xml": b"\0" * MIB for index in range(11)})
    path = write_zip(tmp_path / "split.docx", members)
    for limits in (ADMIN_UPLOAD_EXTRACTION_LIMITS, CHAT_ATTACHMENT_EXTRACTION_LIMITS):
        with pytest.raises(DocumentLimitExceeded, match="壓縮"):
            DocumentProcessor.extract_text_from_file(path, DOCX_TYPE, limits)


def test_attachment_xml_budget_follows_content_types(tmp_path):
    limits = replace(CHAT_ATTACHMENT_EXTRACTION_LIMITS, max_ooxml_xml_bytes=4096)
    xml_body = ("<w:p>" + "段落文字" * 1000 + "</w:p>").encode()
    renamed = write_zip(tmp_path / "renamed.docx", {"[Content_Types].xml": CONTENT_TYPES_XML, "word/body.bin": xml_body})
    with pytest.raises(DocumentLimitExceeded, match="XML"):
        DocumentProcessor.extract_text_from_file(renamed, DOCX_TYPE, limits)
    # 圖片等非 XML 部件只占記憶體一次，不計入 DOM 預算；串流讀取的 xlsx 也不套用
    media = write_zip(tmp_path / "media.docx", {"[Content_Types].xml": CONTENT_TYPES_XML, "word/media/image1.png": xml_body})
    DocumentProcessor._check_ooxml_archive(media, limits, builds_dom=True)
    DocumentProcessor._check_ooxml_archive(renamed, limits, builds_dom=False)
    # .rels 一律會被解析
    rels = write_zip(tmp_path / "rels.docx", {"[Content_Types].xml": "<Types/>", "word/_rels/body.bin.rels": xml_body})
    with pytest.raises(DocumentLimitExceeded, match="XML"):
        DocumentProcessor._check_ooxml_archive(rels, limits, builds_dom=True)


def test_ooxml_member_count_is_bounded(tmp_path):
    limits = replace(ADMIN_UPLOAD_EXTRACTION_LIMITS, max_ooxml_members=3)
    members = {"[Content_Types].xml": CONTENT_TYPES_XML}
    members.update({f"ppt/slides/slide{index}.xml": "<p/>" for index in range(3)})
    path = write_zip(tmp_path / "many.pptx", members)
    with pytest.raises(DocumentLimitExceeded, match="檔案數"):
        DocumentProcessor.extract_text_from_file(path, "application/vnd.openxmlformats-officedocument.presentationml.presentation", limits)


def test_structured_parse_budget_skips_json_loads(tmp_path):
    path = tmp_path / "posts.json"
    path.write_text('[{"author": "喵", "content": "第一則"}]', encoding="utf-8")
    structured = DocumentProcessor.extract_text_from_file(str(path), "application/json", ADMIN_UPLOAD_EXTRACTION_LIMITS)
    assert structured.startswith("【記錄 1】")
    raw = DocumentProcessor.extract_text_from_file(
        str(path), "application/json", replace(CHAT_ATTACHMENT_EXTRACTION_LIMITS, max_structured_parse_chars=10)
    )
    assert raw.startswith("[{")


def test_attachment_over_budget_is_reported_instead_of_parsed(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "CHAT_ATTACHMENT_EXTRACTION_LIMITS", replace(CHAT_ATTACHMENT_EXTRACTION_LIMITS, max_ooxml_members=1))
    path = write_zip(tmp_path / "a.docx", {"[Content_Types].xml": CONTENT_TYPES_XML, "word/body.bin": "<w:p/>"})
    with open(path, "rb") as handle:
        url = f"data:{DOCX_TYPE};base64," + base64.b64encode(handle.read()).decode()
    text = agent_module._extract_attachment_text("a.docx", DOCX_TYPE, url)
    assert text.startswith("[附件超過解析上限") and "檔案數" in text


@pytest.mark.anyio
async def test_attachment_extractions_are_bounded_process_wide(monkeypatch):
    assert agent_module._attachment_extraction_slots._value == MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS
    # 號誌綁定第一個等待它的事件迴圈；測試各自建立事件迴圈，因此換成同樣大小的新號誌
    monkeypatch.setattr(agent_module, "_attachment_extraction_slots", asyncio.Semaphore(MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS))
    lock = threading.Lock()
    running = {"now": 0, "peak": 0}

    def slow_extract(fname, ftype, url):
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
    monkeypatch.setattr(agent_module, "chat_completion", fake_chat_completion)
    registry = ResearchToolRegistry()
    monkeypatch.setattr(registry, "get_tool_definitions", lambda: [])
    attachments = [FileAttachment(filename=f"{i}.txt", file_type="text/plain", data_url=data_url(10)) for i in range(2)]

    async def ask():
        agent = agent_module.ResearchAgent(tool_registry=registry)
        return [event async for event in agent.stream_research("摘要", attachments=attachments, max_turns=1)]

    await asyncio.gather(*(ask() for _ in range(MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS + 2)))
    assert running["peak"] == MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS


# ---------- 6. 線性時間的清洗與切分、工具結果上限 ----------

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


def test_structured_record_split_is_linear():
    records = DocumentProcessor.split_structured_records("【記錄 1】\n作者: a\n\n---\n\n【記錄 2】\n作者: b")
    assert [meta["author"] for _, meta in records] == ["a", "b"]
    assert_fast(DocumentProcessor.split_structured_records, "【記錄 1】---" + "\n" * 200_000 + "x")


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


@pytest.mark.anyio
async def test_remote_model_list_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(tags_api, "_remote_models_cache", None)
    monkeypatch.setattr(tags_api, "_fetch_remote_models", lambda: calls.append(1) or (["m1"], "m1"))
    results = await asyncio.gather(*[tags_api.fetch_remote_models_cached() for _ in range(10)])
    assert all(result == (["m1"], "m1") for result in results)
    assert len(calls) == 1
