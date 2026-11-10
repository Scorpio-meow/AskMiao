import asyncio
import base64
import io
import json
import docx
import openpyxl
import pptx
import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.api import chat as chat_api
from app.core.user_context import get_current_user_id
from app.models import Conversation, ConversationFile, FileAttachment, LlmConnection, Message, MessageCreate
from app.models.database import Base, get_db
from app.rag import file_tools
from app.rag.agent import ResearchAgent
from app.rag.tools import ResearchToolRegistry
from app.services import conversation_files as files
from app.services import file_builders
from app.services.chat_service import ChatService
from test_agent_guardrails import ScriptedLLM, answer, collect, research, tool_call
MARKDOWN = "# 出差規定\n\n住宿上限每晚 **5,500 元**。\n\n- 出發前申請\n- 檢附收據\n\n| 項目 | 上限 |\n|---|---|\n| 住宿 | 5,500 元 |"
@pytest.fixture
def session_factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(file_tools, "SessionLocal", factory)
    with factory() as db:
        for user_id in (1, 2):
            db.add(Conversation(id=user_id * 10, user_id=user_id, title="對話"))
        db.commit()
    yield factory
    engine.dispose()
def add(factory, filename, data, conversation_id=10, user_id=1, parent=None):
    with factory() as db:
        return files.add_file(db, conversation_id=conversation_id, user_id=user_id, filename=filename, data=data,
                              origin="assistant", parent=parent, enforce_limits=True)
def run_tool(name, arguments, user_id=1, conversation_id=10):
    import asyncio
    return asyncio.run(ResearchToolRegistry().execute_tool(name, arguments, user_id=user_id, conversation_id=conversation_id))
def test_every_creatable_format_round_trips():
    document = docx.Document(io.BytesIO(file_builders.build_file(".docx", {"content": MARKDOWN})))
    assert [(p.style.name, p.text) for p in document.paragraphs][:4] == [
        ("Heading 1", "出差規定"), ("Normal", "住宿上限每晚 5,500 元。"), ("List Bullet", "出發前申請"), ("List Bullet", "檢附收據"),
    ]
    assert document.tables[0].cell(1, 1).text == "5,500 元"
    pdf_bytes = file_builders.build_file(".pdf", {"content": MARKDOWN})
    assert len(pdf_bytes) < 200_000
    pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    assert "住宿上限每晚 5,500 元" in pdf[0].get_text()
    slides = pptx.Presentation(io.BytesIO(file_builders.build_file(".pptx", {"slides": [{"title": "重點", "bullets": ["一", "二"], "notes": "備忘"}]})))
    assert slides.slides[0].shapes.title.text == "重點"
    assert slides.slides[0].notes_slide.notes_text_frame.text == "備忘"
    assert file_builders.build_file(".md", {"content": "# 標題"}) == "# 標題".encode()
    with pytest.raises(files.ConversationFileError, match="JSON"):
        file_builders.build_file(".json", {"content": "{壞掉"})
    with pytest.raises(files.ConversationFileError, match="只能建立"):
        file_builders.build_file(".exe", {"content": "x"})
def test_spreadsheet_strings_never_become_formulas():
    sheets = {"sheets": [{"name": "統計", "rows": [["名稱", "數量"], ["=HYPERLINK(\"http://evil\")", -3], ["@cmd", 1.5]]}]}
    worksheet = openpyxl.load_workbook(io.BytesIO(file_builders.build_file(".xlsx", sheets)))["統計"]
    assert worksheet["A2"].data_type == "s" and worksheet["A2"].value.startswith("=HYPERLINK")
    assert worksheet["B2"].value == -3 and worksheet["A1"].font.bold and worksheet.freeze_panes == "A2"
    assert file_builders.build_file(".csv", sheets).decode("utf-8-sig").splitlines()[1:] == ["\"'=HYPERLINK(\"\"http://evil\"\")\",-3", "'@cmd,1.5"]
def test_edits_need_a_unique_match_and_keep_other_formats():
    data = file_builders.build_file(".docx", {"content": MARKDOWN})
    edited = docx.Document(io.BytesIO(file_builders.edit_file("a.docx", data, {"edits": [{"find": "5,500 元。", "replace": "6,000 元。"}]})))
    assert edited.paragraphs[1].text == "住宿上限每晚 6,000 元。"
    assert edited.paragraphs[0].style.name == "Heading 1"
    with pytest.raises(files.ConversationFileError, match="出現 2 次"):
        file_builders.edit_file("a.docx", data, {"edits": [{"find": "5,500 元", "replace": "x"}]})
    workbook = file_builders.build_file(".xlsx", {"sheets": [{"name": "表", "rows": [["a", 1]]}]})
    assert openpyxl.load_workbook(io.BytesIO(file_builders.edit_file("a.xlsx", workbook, {"cells": [{"sheet": "表", "cell": "b1", "value": 2}]})))["表"]["B1"].value == 2
    with pytest.raises(files.ConversationFileError, match="找不到工作表"):
        file_builders.edit_file("a.xlsx", workbook, {"cells": [{"sheet": "沒有", "cell": "A1", "value": 1}]})
    assert file_builders.edit_file("a.txt", "甲乙丙".encode("big5"), {"edits": [{"find": "乙", "replace": "二"}]}).decode() == "甲二丙"
    with pytest.raises(files.ConversationFileError, match="不能部分修改"):
        file_builders.edit_file("a.pdf", b"%PDF", {"edits": [{"find": "a", "replace": "b"}]})
    with pytest.raises(files.ConversationFileError, match="無法整份重寫"):
        file_builders.edit_file("a.doc", b"x", {"content": "新內容"})
def test_word_edits_keep_the_formatting_of_runs_they_do_not_touch():
    data = file_builders.build_file(".docx", {"content": "住宿上限每晚 **5,500 元**，膳雜費每日 80 美元。"})
    edited = docx.Document(io.BytesIO(file_builders.edit_file("a.docx", data, {"edits": [{"find": "5,500 元，膳雜費", "replace": "6,000 元，膳雜費"}]})))
    assert [(run.text, bool(run.bold)) for run in edited.paragraphs[0].runs] == [("住宿上限每晚 ", False), ("6,000 元，膳雜費", True), ("每日 80 美元。", False)]
def test_edits_ignore_unused_fields_sent_as_null():
    payload = {"edits": [{"find": "乙", "replace": "二"}], "content": None, "sheets": None, "slides": None}
    assert file_builders.edit_file("a.txt", "甲乙丙".encode(), payload).decode() == "甲二丙"
def test_filenames_without_an_extension_are_kept(session_factory):
    assert files.clean_filename("C:\\docs\\LICENSE") == "LICENSE"
    with pytest.raises(files.ConversationFileError, match="不可空白"):
        files.clean_filename("../..")
    attachment = FileAttachment(filename="LICENSE", file_type="application/octet-stream", data_url="data:application/octet-stream;base64," + base64.b64encode(b"MIT").decode())
    with session_factory() as db:
        ChatService().save_user_message(db, 1, "看授權", 10, [attachment], "m")
        assert [(f.filename, f.media_type) for f in files.list_files(db, 10, 1)] == [("LICENSE", "application/octet-stream")]
    assert "只能建立這些格式" in run_tool("create_conversation_file", {"filename": "README", "content": "x"})["error"]
@pytest.mark.asyncio
async def test_reading_files_waits_for_a_parse_slot_and_reuses_the_text(session_factory, monkeypatch):
    created = add(session_factory, "長.txt", "一二三".encode())
    file_tools._file_text.cache_clear()
    calls = []
    real_file_text = file_builders.file_text
    monkeypatch.setattr(file_builders, "file_text", lambda name, data: calls.append(name) or real_file_text(name, data))
    monkeypatch.setattr(file_builders, "extraction_slots", asyncio.Semaphore(0))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(file_tools.execute_file_tool("read_conversation_file", {"file_id": created.id}, 1, 10), 0.2)
    monkeypatch.setattr(file_builders, "extraction_slots", asyncio.Semaphore(1))
    for _ in range(2):
        assert (await file_tools.execute_file_tool("read_conversation_file", {"file_id": created.id}, 1, 10))["content"] == "一二三"
    assert calls == ["長.txt"]
def test_files_are_not_saved_into_a_deleted_conversation(session_factory):
    with session_factory() as db:
        ChatService().delete_conversation(db, 10, 1)
    assert "已被刪除" in run_tool("create_conversation_file", {"filename": "報告.md", "content": "# 報告"})["error"]
    assert "已被刪除" in run_tool("create_conversation_file", {"filename": "報告.md", "content": "# 報告"}, conversation_id=20)["error"]
    with session_factory() as db:
        assert db.query(ConversationFile).count() == 0
        assert files.storage_used(db, 1) == 0
def test_versions_keep_the_original_and_number_the_lineage(session_factory):
    original = add(session_factory, "報告.md", b"v1")
    second = add(session_factory, "報告.md", b"v2", parent=original)
    third = add(session_factory, "報告.md", b"v3", parent=original)
    fourth = add(session_factory, second.filename, b"v4", parent=second)
    assert [f.filename for f in (original, second, third, fourth)] == ["報告.md", "報告 v2.md", "報告 v3.md", "報告 v4.md"]
    assert (fourth.parent_id, fourth.root_id) == (second.id, original.id)
    user_named = add(session_factory, "計畫 v3.md", b"x")
    assert add(session_factory, user_named.filename, b"y", parent=user_named).filename == "計畫 v3 v2.md"
    with session_factory() as db:
        assert files.get_file(db, original.id, 1, 10, with_data=True).data == b"v1"
def test_files_are_scoped_to_their_owner_and_conversation(session_factory):
    mine = add(session_factory, "a.txt", b"x")
    with session_factory() as db:
        for user_id, conversation_id in ((2, None), (1, 20), (2, 20)):
            with pytest.raises(files.ConversationFileError):
                files.get_file(db, mine.id, user_id, conversation_id, with_data=False)
    assert "error" in run_tool("read_conversation_file", {"file_id": mine.id}, user_id=2, conversation_id=20)
    assert "error" in run_tool("delete_conversation_file", {"file_id": mine.id}, user_id=1, conversation_id=20)
    assert run_tool("list_conversation_files", {}, user_id=2, conversation_id=20) == {"files": []}
def test_quota_and_capacity_cover_conversation_files(session_factory, monkeypatch):
    monkeypatch.setattr(files, "MAX_USER_ATTACHMENT_STORAGE_BYTES", 10)
    add(session_factory, "a.txt", b"x" * 8)
    with pytest.raises(files.AttachmentQuotaExceeded):
        add(session_factory, "b.txt", b"x" * 3)
    assert run_tool("create_conversation_file", {"filename": "c.md", "content": "123"}) == {"error": file_tools.prompts.FILE_QUOTA_EXCEEDED}
    monkeypatch.setattr(files, "MAX_USER_ATTACHMENT_STORAGE_BYTES", 10_000)
    monkeypatch.setattr(files, "MAX_CONVERSATION_FILES", 1)
    with pytest.raises(files.ConversationFileError, match="最多 1 個檔案"):
        add(session_factory, "d.txt", b"x")
def test_file_tools_create_read_edit_and_delete(session_factory):
    created = run_tool("create_conversation_file", {"filename": "../旅費.docx", "content": MARKDOWN})
    assert created["action"] == "created" and created["file"]["filename"] == "旅費.docx"
    first = run_tool("read_conversation_file", {"file_id": created["file"]["id"], "offset": 0})
    assert "住宿上限每晚 5,500 元" in first["content"] and first["next_offset"] is None
    edited = run_tool("edit_conversation_file", {"file_id": created["file"]["id"], "edits": [{"find": "5,500 元。", "replace": "6,000 元。"}]})
    assert (edited["action"], edited["file"]["filename"], edited["source_file_id"]) == ("updated", "旅費 v2.docx", created["file"]["id"])
    assert created["check"] == edited["check"] == {"headings": ["出差規定"], "paragraphs": 3, "tables": 1}
    listed = run_tool("list_conversation_files", {})
    assert [f["filename"] for f in listed["files"]] == ["旅費.docx", "旅費 v2.docx"]
    requirement = ResearchToolRegistry().approval_requirement("delete_conversation_file", {"file_id": edited["file"]["id"]}, 1, 10)
    assert requirement == {"kind": "file", "display_name": "刪除對話檔案", "target": f"#{edited['file']['id']}「旅費 v2.docx」"}
    deleted = run_tool("delete_conversation_file", {"file_id": edited["file"]["id"]})
    assert deleted["action"] == "deleted"
    assert [f["filename"] for f in run_tool("list_conversation_files", {})["files"]] == ["旅費.docx"]
    assert run_tool("list_conversation_files", {}, conversation_id=None) == {"error": file_tools.prompts.FILE_TOOLS_UNAVAILABLE}
def test_reading_pages_through_long_files(session_factory, monkeypatch):
    monkeypatch.setattr(file_builders, "FILE_READ_PAGE_CHARS", 4)
    created = add(session_factory, "長.txt", "一二三四五六七八九".encode())
    first = run_tool("read_conversation_file", {"file_id": created.id, "offset": 0})
    second = run_tool("read_conversation_file", {"file_id": created.id, "offset": first["next_offset"]})
    assert (first["content"], first["next_offset"], second["content"], second["next_offset"]) == ("一二三四", 4, "五六七八", 8)
def test_only_delete_needs_approval(session_factory):
    registry = ResearchToolRegistry()
    for name in file_tools.FILE_TOOL_NAMES[:-1]:
        assert registry.approval_requirement(name, {}, 1, 10) is None
    assert [t["function"]["name"] for t in registry.get_tool_definitions(1, 10) if t["function"]["name"] in file_tools.FILE_TOOL_NAMES] == list(file_tools.FILE_TOOL_NAMES)
    assert not [t for t in registry.get_tool_definitions(1) if t["function"]["name"] in file_tools.FILE_TOOL_NAMES]
@pytest.mark.asyncio
async def test_agent_reports_file_events_and_waits_for_delete_approval(session_factory, monkeypatch):
    registry = ResearchToolRegistry()
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None, conversation_id=None, requested_skill=None: [])
    ScriptedLLM([
        tool_call("create_conversation_file", {"filename": "摘要.md", "content": "# 摘要"}, "c1"),
        tool_call("delete_conversation_file", {"file_id": 1}, "c2"),
        answer("完成"),
    ]).install(monkeypatch)
    events = []
    async for event in research(ResearchAgent(tool_registry=registry), "做一份摘要再刪掉", approval_user_id=1, conversation_id=10):
        events.append(event)
        if event["event"] == "approval_required":
            assert (event["data"]["kind"], event["data"]["target"]) == ("file", "#1「摘要.md」")
            from app.rag.tool_approval import approval_broker
            approval_broker.resolve(event["data"]["approval_id"], 1, False, False)
    file_events = [event["data"] for event in events if event["event"] == "file"]
    assert [(e["action"], e["file"]["filename"]) for e in file_events] == [("created", "摘要.md")]
    with session_factory() as db:
        assert [f.filename for f in files.list_files(db, 10, 1)] == ["摘要.md"]
@pytest.fixture
def api(session_factory):
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/api/chat")
    current = {"user_id": 1}
    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_id] = lambda: current["user_id"]
    return TestClient(app), current
def test_download_list_and_delete_endpoints(api, session_factory):
    client, current = api
    created = add(session_factory, "會議 紀錄.html", b"<script>alert(1)</script>")
    response = client.get(f"/api/chat/files/{created.id}")
    assert response.content == b"<script>alert(1)</script>"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-disposition"] == "attachment; filename*=UTF-8''%E6%9C%83%E8%AD%B0%20%E7%B4%80%E9%8C%84.html"
    assert response.headers["cache-control"] == "private, no-store" and response.headers["x-content-type-options"] == "nosniff"
    assert [f["id"] for f in client.get("/api/chat/conversations/10/files").json()["files"]] == [created.id]
    current["user_id"] = 2
    assert client.get(f"/api/chat/files/{created.id}").status_code == 404
    assert client.delete(f"/api/chat/files/{created.id}").status_code == 404
    assert client.get("/api/chat/conversations/10/files").status_code == 404
    current["user_id"] = 1
    assert client.delete(f"/api/chat/files/{created.id}").json()["file"]["id"] == created.id
    assert client.get(f"/api/chat/files/{created.id}").status_code == 404
def test_deleting_a_conversation_removes_its_files(session_factory):
    add(session_factory, "a.txt", b"x")
    with session_factory() as db:
        assert ChatService().delete_conversation(db, 10, 1)
        assert db.query(ConversationFile).count() == 0
@pytest.mark.asyncio
async def test_document_attachments_are_stored_as_files(session_factory, monkeypatch):
    with session_factory() as db:
        db.add(LlmConnection(name="本機", provider="ollama", api_base="http://127.0.0.1:9", models=json.dumps(["m"]), owner_id=1))
        db.commit()
    captured = {}
    class FakeRag:
        async def generate_response_stream(self, query, conversation_history, **kwargs):
            captured.update(kwargs)
            yield {"event": "attachments_extracted", "data": {"contents": ["第三條", None]}}
            yield {"event": "file", "data": {"action": "created", "file": {"id": 99, "filename": "產出.md"}}}
            yield {"event": "token", "data": {"content": "好"}}
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: FakeRag())
    document = FileAttachment(filename="合約.txt", file_type="text/plain", data_url="data:text/plain;base64," + base64.b64encode("第三條".encode()).decode())
    image = FileAttachment(filename="圖.png", file_type="image/png", data_url="data:image/png;base64,iVBORw0KGgo=", file_id=12345)
    response = await chat_api.send_message(MessageCreate(content="改合約", connection_id=1, model_name="m", attachments=[document, image]), db=session_factory(), user_id=1)
    body = "".join([chunk async for chunk in response.body_iterator])
    start = json.loads(body.split("event: start\ndata: ", 1)[1].split("\n", 1)[0])
    assert start["attachment_file_ids"][1] is None and start["attachment_file_ids"][0] is not None
    assert captured["conversation_id"] == start["conversation_id"] and "event: file" in body
    with session_factory() as db:
        stored = files.get_file(db, start["attachment_file_ids"][0], 1, start["conversation_id"], with_data=True)
        assert (stored.filename, stored.data, stored.origin) == ("合約.txt", "第三條".encode(), "user")
        user_message, bot_message = db.query(Message).order_by(Message.id).all()
        context = json.loads(user_message.context_used)
        assert "data_url" not in context["attachments"][0] and context["attachments"][0]["file_id"] == stored.id
        assert context["attachments"][1]["data_url"].startswith("data:image/png") and context["attachments"][1]["file_id"] is None
        assert json.loads(bot_message.context_used)["files"] == [{"action": "created", "file": {"id": 99, "filename": "產出.md"}}]
        history = ChatService().get_recent_history(db, start["conversation_id"], before_message_id=bot_message.id + 1, limit=4)
        assert history[0]["content"].startswith(f"[附件 #{stored.id}：合約.txt]\n第三條")
        user_message.context_used = json.dumps({"attachments": [{**context["attachments"][0], "content": None}]}, ensure_ascii=False)
        db.commit()
        history = ChatService().get_recent_history(db, start["conversation_id"], before_message_id=bot_message.id + 1, limit=4)
        assert history[0]["content"].startswith(f"[附件 #{stored.id}：合約.txt]\n（沒有擷取到文字內容）")