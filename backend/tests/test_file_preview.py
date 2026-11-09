import asyncio
from datetime import datetime
import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import chat as chat_api
from app.api import documents as documents_api
from app.core.jwt_auth import get_current_user_from_token
from app.core.limits import CHAT_ATTACHMENT_EXTRACTION_LIMITS, FILE_PREVIEW_PAGE_MAX_PIXELS
from app.core.security import SecurityHeadersMiddleware
from app.core.user_context import get_current_user_id
from app.models import Document as DbDocument
from app.models import User
from app.models.database import get_db
from app.services import conversation_files as files
from app.services import file_builders, file_preview
from test_conversation_files import add, session_factory
MARKDOWN = "# 出差規定\n\n住宿上限每晚 **5,500 元**。\n\n- 出發前申請\n\n| 項目 | 上限 |\n|---|---|\n| 住宿 | 5,500 元 |"
def preview(filename, data, allow_html=True):
    return file_preview.build_preview(filename, data, CHAT_ATTACHMENT_EXTRACTION_LIMITS, allow_html)
def test_office_files_become_structured_previews():
    document = preview("a.docx", file_builders.build_file(".docx", {"content": MARKDOWN}))
    assert [block["type"] for block in document["blocks"]] == ["heading", "paragraph", "list_item", "table"]
    assert document["blocks"][1]["runs"][1] == {"text": "5,500 元", "bold": True, "italic": False}
    assert document["blocks"][3]["rows"] == [["項目", "上限"], ["住宿", "5,500 元"]]
    sheets = preview("a.xlsx", file_builders.build_file(".xlsx", {"sheets": [{"name": "表", "rows": [["項目", 1.0, None], ["=SUM(A1)", 2.5]]}]}))
    assert sheets["sheets"] == [{"name": "表", "rows": [["項目", "1"], ["=SUM(A1)", "2.5"]], "truncated": False}]
    slides = preview("a.pptx", file_builders.build_file(".pptx", {"slides": [{"title": "重點", "bullets": ["一", "二"], "notes": "備忘"}]}))
    assert slides["slides"][0] == {"number": 1, "title": "重點", "notes": "備忘", "items": [{"type": "text", "level": 0, "text": "一"}, {"type": "text", "level": 0, "text": "二"}], "images": 0}
def test_large_tables_are_cut_and_marked(monkeypatch):
    monkeypatch.setattr(file_preview, "FILE_PREVIEW_SHEET_ROWS", 2)
    monkeypatch.setattr(file_preview, "FILE_PREVIEW_SHEET_COLUMNS", 2)
    sheets = preview("a.csv", "a,b,c\n1,2\n3,4\n5,6".encode())
    assert sheets["sheets"][0] == {"name": "a.csv", "rows": [["a", "b"], ["1", "2"]], "truncated": True}
def test_text_markdown_html_and_binary_files():
    assert preview("a.md", MARKDOWN.encode())["type"] == "markdown"
    assert preview("LICENSE", b"MIT License") == {"type": "text", "text": "MIT License", "truncated": False}
    assert preview("a.html", b"<h1>x</h1>") == {"type": "html"}
    assert preview("a.html", b"<h1>x</h1>", allow_html=False)["text"] == "<h1>x</h1>"
    assert preview("a.bin", bytes(range(256)))["type"] == "unsupported"
    assert preview("a.pdf", b"not a pdf") == {"type": "unsupported", "reason": "PDF 檔案損毀，無法預覽"}
def test_pdf_pages_render_as_bounded_images():
    data = file_builders.build_file(".pdf", {"content": MARKDOWN})
    assert preview("a.pdf", data) == {"type": "pages", "page_count": 1}
    assert file_preview.render_pdf_page(data, 1).startswith(b"\x89PNG")
    with pytest.raises(files.ConversationFileError, match="頁碼超出範圍"):
        file_preview.render_pdf_page(data, 2)
    with pymupdf.open() as huge:
        huge.new_page(width=10_000, height=4_000)
        big = huge.tobytes()
    with pymupdf.open(stream=file_preview.render_pdf_page(big, 1), filetype="png") as image:
        assert max(image[0].rect.width, image[0].rect.height) <= FILE_PREVIEW_PAGE_MAX_PIXELS
@pytest.fixture
def client(session_factory):
    with session_factory() as db:
        for user_id in (1, 2):
            db.add(User(id=user_id, username=f"u{user_id}", email=f"u{user_id}@example.com", hashed_password="x", tokens_valid_after=datetime.utcnow()))
        db.commit()
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
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
def test_preview_and_pages_are_limited_to_the_owner(client, session_factory):
    http, current = client
    pdf = add(session_factory, "報告.pdf", file_builders.build_file(".pdf", {"content": MARKDOWN}))
    assert http.get(f"/api/chat/files/{pdf.id}/preview").json() == {"type": "pages", "page_count": 1}
    page = http.get(f"/api/chat/files/{pdf.id}/pages/1")
    assert page.status_code == 200 and page.headers["content-type"] == "image/png"
    assert http.get(f"/api/chat/files/{pdf.id}/pages/2").status_code == 404
    current["user_id"] = 2
    assert http.get(f"/api/chat/files/{pdf.id}/preview").status_code == 404
    assert http.get(f"/api/chat/files/{pdf.id}/pages/1").status_code == 404
def test_recent_files_keep_only_the_newest_entries():
    loads = []
    cache = file_preview.RecentFiles(2)
    def loader(value):
        return lambda: loads.append(value) or value
    assert [cache.get(key, loader(key.encode())) for key in ("a", "b", "a", "c", "b")] == [b"a", b"b", b"a", b"c", b"b"]
    assert loads == [b"a", b"b", b"c", b"b"]
def test_previews_read_files_only_while_holding_a_parse_slot(client, session_factory, tmp_path, monkeypatch):
    http, _ = client
    held = []
    slots = asyncio.Semaphore(1)
    monkeypatch.setattr(chat_api, "extraction_slots", slots)
    monkeypatch.setattr(documents_api, "extraction_slots", slots)
    real_preview_bytes = chat_api._preview_bytes
    real_read_file = documents_api._read_file
    monkeypatch.setattr(chat_api, "_preview_bytes", lambda file: held.append(slots.locked()) or real_preview_bytes(file))
    monkeypatch.setattr(documents_api, "_read_file", lambda path: held.append(slots.locked()) or real_read_file(path))
    pdf_data = file_builders.build_file(".pdf", {"content": MARKDOWN})
    pdf = add(session_factory, "報告.pdf", pdf_data)
    assert http.get(f"/api/chat/files/{pdf.id}/preview").status_code == 200
    assert http.get(f"/api/chat/files/{pdf.id}/pages/1").status_code == 200
    monkeypatch.setattr(documents_api, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "規章.pdf").write_bytes(pdf_data)
    with session_factory() as db:
        db.add(DbDocument(id=1, filename="規章.pdf", content="規章"))
        db.commit()
    app = FastAPI()
    app.include_router(documents_api.router, prefix="/api/documents")
    app.dependency_overrides[get_db] = lambda: session_factory()
    app.dependency_overrides[get_current_user_from_token] = lambda: {"user_id": 1, "is_admin": True}
    admin = TestClient(app)
    assert admin.get("/api/documents/1/preview").status_code == 200
    assert admin.get("/api/documents/1/pages/1").status_code == 200
    assert held == [True, True, True, True]
def test_web_pages_open_only_through_a_short_lived_sandboxed_link(client, session_factory, monkeypatch):
    http, current = client
    page = add(session_factory, "首頁.html", "<h1>首頁</h1><script>1</script>".encode())
    notes = add(session_factory, "筆記.md", b"# x")
    assert http.post(f"/api/chat/files/{notes.id}/view-token").status_code == 400
    token = http.post(f"/api/chat/files/{page.id}/view-token").json()["token"]
    view = http.get(f"/api/chat/files/{page.id}/view", params={"token": token})
    assert view.status_code == 200 and view.text == "<h1>首頁</h1><script>1</script>"
    policy = view.headers["content-security-policy"]
    assert policy.startswith("sandbox allow-scripts; default-src 'none'") and "frame-ancestors 'self'" in policy
    assert "x-frame-options" not in view.headers
    assert http.get(f"/api/chat/files/{page.id}").headers["x-frame-options"] == "DENY"
    assert http.get(f"/api/chat/files/{notes.id}/view", params={"token": token}).status_code == 403
    assert http.get(f"/api/chat/files/{page.id}/view", params={"token": "forged"}).status_code == 403
    assert http.get(f"/api/chat/files/{page.id}/view", params={"token": files.view_token(2, page.id)}).status_code == 404
    monkeypatch.setattr(files, "FILE_VIEW_TOKEN_SECONDS", -1)
    assert http.get(f"/api/chat/files/{page.id}/view", params={"token": token}).status_code == 403
def test_knowledge_base_preview_is_admin_only_and_falls_back_to_stored_text(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(documents_api, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "規章.pdf").write_bytes(file_builders.build_file(".pdf", {"content": MARKDOWN}))
    with session_factory() as db:
        db.add_all([DbDocument(id=1, filename="規章.pdf", content="規章"), DbDocument(id=2, filename="遺失.docx", content="擷取出的文字")])
        db.commit()
    app = FastAPI()
    app.include_router(documents_api.router, prefix="/api/documents")
    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()
    user = {"user_id": 1, "username": "admin", "is_admin": True}
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_from_token] = lambda: user
    http = TestClient(app)
    assert http.get("/api/documents/1/preview").json() == {"type": "pages", "page_count": 1}
    assert http.get("/api/documents/1/pages/1").headers["content-type"] == "image/png"
    assert http.get("/api/documents/2/preview").json() == {"type": "text", "text": "擷取出的文字", "truncated": False, "notice": "伺服器上找不到原始檔，以下是擷取出的文字"}
    assert http.get("/api/documents/2/pages/1").status_code == 404
    user["is_admin"] = False
    assert http.get("/api/documents/1/preview").status_code == 403
def test_assistant_can_create_web_pages():
    assert ".html" in file_builders.CREATABLE_EXTENSIONS
    assert file_builders.build_file(".html", {"content": "<p>hi</p>"}) == b"<p>hi</p>"
def test_created_files_report_their_structure_for_checking():
    check = lambda filename, data: file_preview.structure_check(filename, data, CHAT_ATTACHMENT_EXTRACTION_LIMITS)
    assert check("a.docx", file_builders.build_file(".docx", {"content": MARKDOWN})) == {"headings": ["出差規定"], "paragraphs": 2, "tables": 1}
    assert check("a.xlsx", file_builders.build_file(".xlsx", {"sheets": [{"name": "表", "rows": [["項目", "上限"], ["住宿", 5500], ["膳雜", 80]]}]})) == {
        "sheets": [{"name": "表", "rows": 3, "columns": 2, "truncated": False}]
    }
    assert check("a.pptx", file_builders.build_file(".pptx", {"slides": [{"title": "重點"}, {"title": "結論"}]})) == {"slides": 2, "titles": ["重點", "結論"]}
    assert check("a.pdf", file_builders.build_file(".pdf", {"content": MARKDOWN})) == {"pages": 1}
    assert check("a.md", "第一行\n第二行".encode()) == {"characters": 7, "lines": 2}
    assert check("a.docx", b"not a docx")["problem"]