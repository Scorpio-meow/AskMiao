from datetime import datetime
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import prompts
from app.api import admin as admin_api
from app.api import chat as chat_api
from app.core.jwt_auth import get_current_admin_user
from app.core.limits import MAX_AGENT_INSTRUCTIONS_CHARS
from app.core.user_context import get_current_user_id
from app.models import AgentInstruction, User
from app.models.database import Base, get_db
from app.services.agent_instructions import instructions_prompt
from test_agent_guardrails import ScriptedLLM, answer, collect, make_agent, research
@pytest.fixture
def api(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        for user_id in (1, 2):
            db.add(User(id=user_id, username=f"u{user_id}", email=f"u{user_id}@example.com", hashed_password="x", tokens_valid_after=datetime.utcnow()))
        db.commit()
    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    current = {"user_id": 1}
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/api/chat")
    app.include_router(admin_api.router, prefix="/api/admin")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_id] = lambda: current["user_id"]
    app.dependency_overrides[get_current_admin_user] = lambda: {"user_id": 99, "username": "root", "is_admin": True}
    monkeypatch.setattr(admin_api, "log_security_event", lambda *args, **kwargs: None)
    yield TestClient(app), current, Session
    engine.dispose()
def test_personal_and_organization_instructions_are_kept_apart(api):
    http, current, Session = api
    assert http.put("/api/admin/agent-instructions", json={"content": "  附上負責單位  "}).json() == {"content": "附上負責單位"}
    assert http.put("/api/chat/instructions", json={"content": "先列重點"}).json() == {"content": "先列重點"}
    current["user_id"] = 2
    assert http.get("/api/chat/instructions").json() == {"content": ""}
    assert http.put("/api/chat/instructions", json={"content": "x" * (MAX_AGENT_INSTRUCTIONS_CHARS + 1)}).status_code == 422
    assert http.get("/api/admin/agent-instructions").json() == {"content": "附上負責單位"}
    with Session() as db:
        assert instructions_prompt(db, 1) == prompts.ORGANIZATION_INSTRUCTIONS.format(content="附上負責單位") + prompts.PERSONAL_INSTRUCTIONS.format(content="先列重點")
        assert instructions_prompt(db, 2) == prompts.ORGANIZATION_INSTRUCTIONS.format(content="附上負責單位")
    current["user_id"] = 1
    assert http.put("/api/chat/instructions", json={"content": "   "}).json() == {"content": ""}
    with Session() as db:
        assert db.query(AgentInstruction).count() == 1
def test_duplicate_organization_rows_collapse_into_the_oldest(api):
    http, _, Session = api
    with Session() as db:
        db.add_all([AgentInstruction(user_id=None, content="第一筆"), AgentInstruction(user_id=None, content="同時寫入的第二筆")])
        db.commit()
    assert http.get("/api/admin/agent-instructions").json() == {"content": "第一筆"}
    assert http.put("/api/admin/agent-instructions", json={"content": "新的指示"}).json() == {"content": "新的指示"}
    assert http.get("/api/admin/agent-instructions").json() == {"content": "新的指示"}
    with Session() as db:
        assert [(row.user_id, row.content) for row in db.query(AgentInstruction).all()] == [(None, "新的指示")]
def test_deleting_a_user_removes_their_instructions(api):
    http, _, Session = api
    http.put("/api/chat/instructions", json={"content": "先列重點"})
    http.put("/api/admin/agent-instructions", json={"content": "附上負責單位"})
    assert http.delete("/api/admin/users/1").status_code == 200
    with Session() as db:
        assert [(row.user_id, row.content) for row in db.query(AgentInstruction).all()] == [(None, "附上負責單位")]
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["research", "agent"])
async def test_instructions_follow_the_system_prompt_in_both_modes(monkeypatch, mode):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([answer("好")]).install(monkeypatch)
    block = prompts.PERSONAL_INSTRUCTIONS.format(content="先列重點")
    await collect(research(agent, "你好", mode=mode, instructions=block))
    system = llm.chat_messages[0][0]["content"]
    base = prompts.AGENT_SYSTEM_PROMPT if mode == "agent" else prompts.SYSTEM_PROMPT
    assert system == base + block