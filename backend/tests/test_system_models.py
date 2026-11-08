import asyncio
import threading
from datetime import datetime
import pymupdf as fitz
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.api import llm_connections as connections_api
from app.core.jwt_auth import get_current_active_user
from app.core.llm_client import LlmEndpoint
from app.models import SystemModel, User
from app.models.database import Base, get_db, upgrade_schema
from app import prompts
from app.services import system_models
from app.services.pdf_service import PDFService
OLLAMA = {"name": "公司 Ollama", "provider": "ollama", "api_base": "http://localhost:11434", "models": ["qwen3:8b", "gemma3:12b"]}
OPENAI = {
    "name": "公司 OpenAI", "provider": "openai", "api_base": "https://api.openai.com/v1",
    "api_key": "sk-company", "models": ["gpt-6-sol"],
}
@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    now = datetime.utcnow()
    with Session() as session:
        for username, is_admin in (("root", True), ("alice", False)):
            session.add(User(username=username, email=f"{username}@example.com", hashed_password="x", is_active=True,
                             is_admin=is_admin, role="admin" if is_admin else "user", created_at=now, tokens_valid_after=now))
        session.commit()
        ids = {user.username: user.id for user in session.query(User).all()}
    monkeypatch.setattr(connections_api, "log_security_event", lambda *args, **kwargs: None)
    current = {}
    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()
    app = FastAPI()
    app.include_router(connections_api.router)
    app.include_router(connections_api.admin_router)
    app.include_router(connections_api.system_models_router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_active_user] = lambda: dict(current)
    client = TestClient(app)
    def login(username):
        current.clear()
        current.update({"user_id": ids[username], "username": username, "is_admin": username == "root"})
        return client
    yield login, Session
    engine.dispose()
def shared(root, payload):
    response = root.post("/api/admin/llm-connections", json={**payload, "allowed_user_ids": []})
    assert response.status_code == 201
    return response.json()["id"]
def assign(summary, ocr):
    return {"document_summary": summary, "pdf_ocr": ocr}
def test_admin_assigns_shared_connections_and_the_target_carries_the_stored_key(env):
    login, Session = env
    root = login("root")
    ollama_id = shared(root, OLLAMA)
    openai_id = shared(root, OPENAI)
    assert root.get("/api/admin/system-models").json() == assign(None, None)
    body = assign(
        {"connection_id": ollama_id, "model_name": "qwen3:8b", "reasoning_effort": "none"},
        {"connection_id": openai_id, "model_name": "gpt-6-sol", "reasoning_effort": "high"},
    )
    response = root.put("/api/admin/system-models", json=body)
    assert response.status_code == 200
    assert response.json() == body
    assert root.get("/api/admin/system-models").json() == body
    with Session() as session:
        target = system_models.system_model_target(session, "pdf_ocr")
        assert (target.endpoint.provider, target.endpoint.api_key, target.model_name) == ("openai", "sk-company", "gpt-6-sol")
        assert target.reasoning_effort == "high"
        assert target.endpoint.public_only is False
    cleared = root.put("/api/admin/system-models", json=assign(None, body["pdf_ocr"]))
    assert cleared.json() == assign(None, body["pdf_ocr"])
    with Session() as session:
        assert system_models.system_model_target(session, "document_summary") is None
def test_only_admins_can_assign_and_only_shared_connections_with_that_model(env):
    login, _ = env
    root = login("root")
    ollama_id = shared(root, OLLAMA)
    personal = login("alice").post("/api/llm-connections", json={**OPENAI, "name": "我的 OpenAI"})
    assert personal.status_code == 201
    alice = login("alice")
    assert alice.get("/api/admin/system-models").status_code == 403
    assert alice.put("/api/admin/system-models", json=assign(None, None)).status_code == 403
    root = login("root")
    unknown_model = root.put(
        "/api/admin/system-models", json=assign({"connection_id": ollama_id, "model_name": "llama9", "reasoning_effort": "none"}, None)
    )
    assert unknown_model.status_code == 400
    assert "llama9" in unknown_model.json()["detail"]
    personal_connection = root.put(
        "/api/admin/system-models",
        json=assign({"connection_id": personal.json()["id"], "model_name": "gpt-6-sol", "reasoning_effort": "low"}, None),
    )
    assert personal_connection.status_code == 400
    missing = {"connection_id": 999, "model_name": "x", "reasoning_effort": "low"}
    assert root.put("/api/admin/system-models", json=assign(missing, None)).status_code == 400
    assert root.put("/api/admin/system-models", json={"document_summary": None}).status_code == 422
    without_effort = {"connection_id": ollama_id, "model_name": "qwen3:8b"}
    assert root.put("/api/admin/system-models", json=assign(without_effort, None)).status_code == 422
    unknown_effort = {**without_effort, "reasoning_effort": "extreme"}
    assert root.put("/api/admin/system-models", json=assign(unknown_effort, None)).status_code == 422
    assert root.get("/api/admin/system-models").json() == assign(None, None)
def test_editing_or_deleting_the_shared_connection_releases_its_assignments(env):
    login, Session = env
    root = login("root")
    ollama_id = shared(root, OLLAMA)
    ocr = {"connection_id": ollama_id, "model_name": "gemma3:12b", "reasoning_effort": "medium"}
    root.put("/api/admin/system-models", json=assign(
        {"connection_id": ollama_id, "model_name": "qwen3:8b", "reasoning_effort": "none"}, ocr
    ))
    assert root.put(f"/api/admin/llm-connections/{ollama_id}", json={"models": ["gemma3:12b"]}).status_code == 200
    assert root.get("/api/admin/system-models").json() == assign(None, ocr)
    assert root.delete(f"/api/admin/llm-connections/{ollama_id}").status_code == 200
    assert root.get("/api/admin/system-models").json() == assign(None, None)
    with Session() as session:
        assert session.query(SystemModel).count() == 0
def test_existing_system_models_table_gets_reasoning_effort_without_changing_behavior(tmp_path):
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE system_models (purpose VARCHAR PRIMARY KEY, connection_id INTEGER, model_name VARCHAR)"))
        conn.execute(text("INSERT INTO system_models VALUES ('document_summary', 1, 'qwen3:8b')"))
    upgrade_schema(old)
    upgrade_schema(old)
    with old.connect() as conn:
        assert conn.execute(text("SELECT reasoning_effort FROM system_models")).scalar() == "none"
    old.dispose()
def test_stale_assignment_is_ignored_instead_of_used(env):
    login, Session = env
    root = login("root")
    ollama_id = shared(root, OLLAMA)
    with Session() as session:
        session.add(SystemModel(purpose="document_summary", connection_id=ollama_id, model_name="removed-model", reasoning_effort="none"))
        session.commit()
        assert system_models.system_model_target(session, "document_summary") is None
@pytest.mark.asyncio
async def test_page_ocr_sends_the_image_to_the_system_model_through_the_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    seen = {}
    async def fake_call_llm(messages, *, endpoint, model_name, timeout=None, reasoning_effort=None):
        seen["thread"] = threading.get_ident()
        seen["model_name"] = model_name
        seen["reasoning_effort"] = reasoning_effort
        seen["content"] = messages[0]["content"]
        return " 第一頁文字 "
    monkeypatch.setattr(system_models, "call_llm", fake_call_llm)
    target = system_models.SystemModelTarget(LlmEndpoint("gemini", "https://g.example", "k", None, False), "vision", "low")
    recognize = system_models.page_ocr(target)
    text = await asyncio.to_thread(recognize, b"\x89PNG")
    assert text == " 第一頁文字 "
    assert seen["thread"] == loop_thread
    assert seen["model_name"] == "vision"
    assert seen["reasoning_effort"] == "low"
    assert seen["content"][0] == {"type": "text", "text": prompts.PDF_OCR}
    assert seen["content"][1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw=="}}
    assert system_models.page_ocr(None) is None
def scanned_pdf(tmp_path, pages):
    path = tmp_path / "scan.pdf"
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=200, height=200)
    doc.save(str(path))
    doc.close()
    return str(path)
def test_pdf_ocr_uses_the_given_model_and_skips_scanned_pages_without_one(tmp_path):
    pdf = scanned_pdf(tmp_path, 2)
    calls = []
    text = PDFService.extract_text_robust(pdf, max_ocr_pages=None, ocr=lambda png: calls.append(png[:4]) or "辨識出的文字")
    assert calls == [b"\x89PNG", b"\x89PNG"]
    assert "第 1 頁 (OCR 辨識)" in text and "辨識出的文字" in text
    with pytest.raises(ValueError, match="OCR 未設定或辨識失敗"):
        PDFService.extract_text_robust(pdf, max_ocr_pages=None, ocr=None)