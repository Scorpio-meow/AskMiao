"""
有副作用的工具需要發問者在對話內核准
驗證：
1. 預設政策：會改變狀態的 HTTP 方法與所有 MCP 伺服器需要核准，建立與更新時套用
2. Agent 遇到需核准的工具先送出 approval_required 並暫停；核准才執行，拒絕、逾時或無人可核准都不執行
3. 只有發問的使用者能處理自己的核准項目
4. 既有資料庫升級時補上欄位並依 HTTP 方法回填
"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.api import api_tools, chat as chat_api, mcp
from app.core.jwt_auth import get_current_user_from_token
from app.models import CustomApiTool, McpServer
from app.models.database import Base, SessionLocal, engine, upgrade_schema
from app.rag import tool_approval
from app.rag.tool_approval import ToolApprovalBroker, approval_broker, default_requires_approval
from test_agent_guardrails import ScriptedLLM, answer, collect, make_agent, tool_call

ADMIN_USER = {"user_id": 1, "username": "admin", "email": "admin@example.com", "role": "admin", "is_admin": True}


def test_default_policy_by_http_method():
    assert not default_requires_approval("GET")
    assert not default_requires_approval("head")
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert default_requires_approval(method)


@pytest.mark.anyio
async def test_only_the_requesting_user_can_resolve():
    broker = ToolApprovalBroker()
    approval_id, future = broker.create(user_id=7)
    assert broker.resolve(approval_id, user_id=8, approved=True) is False
    assert not future.done()
    assert broker.resolve(approval_id, user_id=7, approved=True) is True
    assert await broker.wait(approval_id, future) is True
    assert broker.resolve(approval_id, user_id=7, approved=True) is False


@pytest.mark.anyio
async def test_unanswered_approval_times_out_as_denied(monkeypatch):
    monkeypatch.setattr(tool_approval, "APPROVAL_TIMEOUT_SECONDS", 0.05)
    broker = ToolApprovalBroker()
    approval_id, future = broker.create(user_id=1)
    assert await broker.wait(approval_id, future) is False
    assert broker.resolve(approval_id, user_id=1, approved=True) is False


def approval_agent(monkeypatch):
    agent, registry = make_agent(monkeypatch)
    executed = []

    async def fake_execute(name, arguments):
        executed.append((name, dict(arguments)))
        return {"ok": True}

    monkeypatch.setattr(registry, "approval_requirement", lambda name: {"kind": "custom_api", "display_name": "建立訂單"} if name == "create_order" else None)
    monkeypatch.setattr(registry, "execute_tool", fake_execute)
    ScriptedLLM([tool_call("create_order", {"item": "A", "qty": 1}), answer("完成")]).install(monkeypatch)
    return agent, executed


async def run_with_decision(agent, decision, user_id=5):
    events = []
    async for event in agent.stream_research("幫我下單", max_turns=3, approval_user_id=user_id):
        events.append(event)
        if event["event"] == "approval_required" and decision is not None:
            assert approval_broker.resolve(event["data"]["approval_id"], user_id, decision)
    return events


@pytest.mark.anyio
@pytest.mark.parametrize("decision", [True, False])
async def test_agent_waits_for_the_users_decision(monkeypatch, decision):
    agent, executed = approval_agent(monkeypatch)
    events = await run_with_decision(agent, decision)
    names = [e["event"] for e in events]
    assert names.index("step_start") < names.index("approval_required") < names.index("approval_resolved") < names.index("step_end")
    required = next(e for e in events if e["event"] == "approval_required")["data"]
    assert required["tool"] == "create_order" and required["arguments"] == {"item": "A", "qty": 1}
    assert executed == ([("create_order", {"item": "A", "qty": 1})] if decision else [])


@pytest.mark.anyio
async def test_agent_without_an_approver_never_runs_the_tool(monkeypatch):
    agent, executed = approval_agent(monkeypatch)
    events = await collect(agent.stream_research("幫我下單", max_turns=3))
    assert executed == []
    assert not any(e["event"] == "approval_required" for e in events)


@pytest.mark.anyio
async def test_disconnect_while_waiting_discards_the_approval(monkeypatch):
    agent, executed = approval_agent(monkeypatch)
    stream = agent.stream_research("幫我下單", max_turns=3, approval_user_id=5)
    approval_id = None
    async for event in stream:
        if event["event"] == "approval_required":
            approval_id = event["data"]["approval_id"]
            break
    waiting = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0.01)
    waiting.cancel()
    with pytest.raises((asyncio.CancelledError, StopAsyncIteration)):
        await waiting
    await stream.aclose()
    assert approval_broker.resolve(approval_id, 5, True) is False
    assert executed == []


def admin_client():
    app = FastAPI()
    app.include_router(api_tools.router, prefix="/api/api-tools")
    app.include_router(mcp.router, prefix="/api/mcp")
    app.include_router(chat_api.router, prefix="/api/chat")
    app.dependency_overrides[get_current_user_from_token] = lambda: ADMIN_USER
    return TestClient(app)


@pytest.fixture
def clean_tools():
    Base.metadata.create_all(bind=engine)
    names = ("approval_get_tool", "approval_post_tool")

    def remove():
        with SessionLocal() as db:
            db.query(CustomApiTool).filter(CustomApiTool.name.in_(names)).delete(synchronize_session=False)
            db.commit()

    remove()
    yield names
    remove()


def test_api_tool_creation_applies_policy_and_update_never_loosens_silently(clean_tools):
    client = admin_client()
    created = {}
    for name, method in zip(clean_tools, ("GET", "POST")):
        response = client.post("/api/api-tools", json={
            "name": name, "display_name": name, "description": "d", "method": method, "url": "https://api.example.com/x",
        })
        assert response.status_code == 200
        created[method] = response.json()["tool"]
    assert created["GET"]["requires_approval"] is False
    assert created["POST"]["requires_approval"] is True

    changed = client.put(f"/api/api-tools/{created['GET']['id']}", json={"method": "DELETE"}).json()["tool"]
    assert changed["requires_approval"] is True
    relaxed = client.put(f"/api/api-tools/{created['POST']['id']}", json={"requires_approval": False}).json()["tool"]
    assert relaxed["requires_approval"] is False


def test_approval_endpoint_rejects_other_users():
    client = admin_client()
    loop = asyncio.new_event_loop()
    try:
        approval_id, _ = loop.run_until_complete(_create_pending(user_id=999))
    finally:
        loop.close()
    response = client.post(f"/api/chat/approvals/{approval_id}", json={"approved": True})
    assert response.status_code == 404
    approval_broker.discard(approval_id)


async def _create_pending(user_id):
    return approval_broker.create(user_id)


def test_existing_database_gets_the_column_with_backfill(tmp_path):
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE custom_api_tools (id INTEGER PRIMARY KEY, name VARCHAR, method VARCHAR)"))
        conn.execute(text("CREATE TABLE mcp_servers (id INTEGER PRIMARY KEY, name VARCHAR)"))
        conn.execute(text("INSERT INTO custom_api_tools (name, method) VALUES ('r', 'GET'), ('w', 'post'), ('n', NULL)"))
        conn.execute(text("INSERT INTO mcp_servers (name) VALUES ('m')"))
    upgrade_schema(old)
    upgrade_schema(old)
    with old.connect() as conn:
        tools = dict(conn.execute(text("SELECT name, requires_approval FROM custom_api_tools")).all())
        servers = conn.execute(text("SELECT requires_approval FROM mcp_servers")).scalar()
    assert tools == {"r": 0, "w": 1, "n": 0}
    assert servers == 1
    old.dispose()
