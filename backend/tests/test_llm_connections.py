import ipaddress
import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import admin as admin_api
from app.api import chat as chat_api
from app.api import llm_connections as connections_api
from app.core import ssrf_protection
from app.core.error_response import SafeClientError
from app.core.jwt_auth import get_current_active_user
from app.core.ssrf_protection import SSRFProtectionError
from app.models import LlmConnection, User
from app.models.database import Base, get_db
from app.services import llm_connections as connections_service

RESOLVED = {
    "api.example.com": "93.184.216.34",
    "intranet.example.com": "10.0.0.5",
}


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    now = datetime.utcnow()
    with Session() as session:
        for username, is_admin in (("root", True), ("alice", False), ("bob", False)):
            session.add(User(username=username, email=f"{username}@example.com", hashed_password="x", is_active=True,
                             is_admin=is_admin, role="admin" if is_admin else "user", created_at=now, tokens_valid_after=now))
        session.commit()
        ids = {user.username: user.id for user in session.query(User).all()}

    async def fake_resolve(hostname, port, dns_pool):
        return [ipaddress.ip_address(RESOLVED[hostname])] if hostname in RESOLVED else []

    monkeypatch.setattr(ssrf_protection, "resolve_hostname", fake_resolve)
    monkeypatch.setattr(admin_api, "log_security_event", lambda *args, **kwargs: None)
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
    app.include_router(chat_api.router, prefix="/api/chat")
    app.include_router(admin_api.router, prefix="/api/admin")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_active_user] = lambda: dict(current)
    client = TestClient(app)

    def login(username):
        current.clear()
        current.update({"user_id": ids[username], "username": username, "is_admin": username == "root"})
        return client

    yield login, Session, ids
    engine.dispose()


def personal(**overrides):
    payload = {
        "name": "我的 OpenAI",
        "provider": "openai",
        "api_base": "https://api.example.com/v1",
        "api_key": "sk-alice",
        "models": ["gpt-6-sol", " gpt-6-sol ", "gpt-6-luna"],
    }
    return {**payload, **overrides}


def test_personal_connections_are_private_and_keys_are_never_returned(env):
    login, Session, ids = env
    created = login("alice").post("/api/llm-connections", json=personal())
    assert created.status_code == 201
    body = created.json()
    assert body["models"] == ["gpt-6-sol", "gpt-6-luna"]
    assert body["has_api_key"] is True and body["scope"] == "personal"
    assert "sk-alice" not in created.text
    with Session() as session:
        stored = session.get(LlmConnection, body["id"])
        assert stored.owner_id == ids["alice"]
        assert stored.api_key.startswith("fernet:") and "sk-alice" not in stored.api_key

    updated = login("alice").put(f"/api/llm-connections/{body['id']}", json={"name": "改名"})
    assert updated.json()["name"] == "改名"
    with Session() as session:
        assert connections_service.endpoint_of(session, session.get(LlmConnection, body["id"])).api_key == "sk-alice"

    bob = login("bob")
    assert bob.get("/api/llm-connections").json() == {"personal": [], "shared": []}
    assert bob.put(f"/api/llm-connections/{body['id']}", json={"name": "搶走"}).status_code == 404
    assert bob.delete(f"/api/llm-connections/{body['id']}").status_code == 404
    assert bob.get("/api/chat/models").json() == {"connections": []}

    alice = login("alice")
    assert [c["name"] for c in alice.get("/api/llm-connections").json()["personal"]] == ["改名"]
    assert alice.delete(f"/api/llm-connections/{body['id']}").status_code == 200
    assert alice.get("/api/llm-connections").json()["personal"] == []


def test_members_cannot_point_personal_connections_at_internal_networks(env):
    login, _, _ = env
    alice = login("alice")
    for api_base in ("http://127.0.0.1:11434", "http://10.1.2.3", "https://intranet.example.com", "https://unknown.example.com"):
        response = alice.post("/api/llm-connections", json=personal(provider="ollama", api_base=api_base, api_key=None))
        assert response.status_code == 400
        assert response.json()["detail"] == connections_service.PRIVATE_ADDRESS_MESSAGE
        assert "10.0.0.5" not in response.text

    created = alice.post("/api/llm-connections", json=personal()).json()
    moved = alice.put(f"/api/llm-connections/{created['id']}", json={"api_base": "https://intranet.example.com"})
    assert moved.status_code == 400
    assert alice.get("/api/llm-connections").json()["personal"][0]["api_base"] == "https://api.example.com/v1"

    root = login("root")
    assert root.post("/api/llm-connections", json=personal(provider="ollama", api_base="http://localhost:11434", api_key=None)).status_code == 201


def test_changing_provider_or_address_drops_the_stored_key(env):
    login, Session, _ = env
    alice = login("alice")
    connection_id = alice.post("/api/llm-connections", json=personal()).json()["id"]
    renamed = alice.put(f"/api/llm-connections/{connection_id}", json={"name": "改名", "provider": "openai", "api_base": "https://api.example.com/v1"})
    assert renamed.json()["has_api_key"] is True

    keyed = alice.put(f"/api/llm-connections/{connection_id}", json={"provider": "anthropic", "max_output_tokens": 8000})
    assert keyed.status_code == 400 and "重新輸入" in keyed.json()["detail"]
    with Session() as session:
        assert connections_service.endpoint_of(session, session.get(LlmConnection, connection_id)).api_key == "sk-alice"

    moved = alice.put(f"/api/llm-connections/{connection_id}", json={"api_base": "https://api.example.com/other"})
    assert moved.status_code == 200 and moved.json()["has_api_key"] is False
    with Session() as session:
        assert session.get(LlmConnection, connection_id).api_key is None


def test_explicit_nulls_cannot_clear_required_fields(env):
    login, Session, _ = env
    alice = login("alice")
    connection_id = alice.post("/api/llm-connections", json=personal()).json()["id"]
    for field in ("name", "provider", "api_base", "models"):
        response = alice.put(f"/api/llm-connections/{connection_id}", json={field: None})
        assert response.status_code == 400 and field in response.json()["detail"]
    with Session() as session:
        stored = session.get(LlmConnection, connection_id)
        assert (stored.name, stored.provider, stored.api_base, json.loads(stored.models)) == (
            "我的 OpenAI", "openai", "https://api.example.com/v1", ["gpt-6-sol", "gpt-6-luna"]
        )

    assert alice.put(f"/api/llm-connections/{connection_id}", json={"max_output_tokens": 8000}).json()["max_output_tokens"] == 8000
    assert alice.put(f"/api/llm-connections/{connection_id}", json={"max_output_tokens": None}).json()["max_output_tokens"] is None

    root = login("root")
    shared_id = root.post("/api/admin/llm-connections", json={**personal(name="共用"), "allowed_user_ids": []}).json()["id"]
    assert root.put(f"/api/admin/llm-connections/{shared_id}", json={"models": None}).status_code == 400
    assert root.get("/api/admin/llm-connections").json()["connections"][0]["models"] == ["gpt-6-sol", "gpt-6-luna"]


@pytest.mark.parametrize("overrides, message", [
    ({"provider": "anthropic", "api_key": None, "max_output_tokens": 8000}, "金鑰"),
    ({"provider": "anthropic", "models": ["claude-opus-5-5"]}, "輸出 token 上限"),
    ({"provider": "foundry", "api_base": "https://api.example.com", "models": ["claude-sonnet-5-5"], "max_output_tokens": 8000}, "services.ai.azure.com"),
    ({"models": [" ", ""]}, "模型"),
    ({"api_base": "ftp://api.example.com"}, "http"),
    ({"provider": "deepseek"}, "pattern"),
])
def test_invalid_connections_are_rejected(env, overrides, message):
    login, _, _ = env
    response = login("alice").post("/api/llm-connections", json=personal(**overrides))
    assert response.status_code in (400, 422)
    assert message in response.text


def test_shared_connections_reach_only_the_accounts_the_admin_chose(env):
    login, _, ids = env
    root = login("root")
    shared = root.post("/api/admin/llm-connections", json={
        **personal(name="公司 Ollama", provider="ollama", api_base="http://localhost:11434", api_key=None, models=["qwen3:8b"]),
        "allowed_user_ids": [ids["alice"]],
    })
    assert shared.status_code == 201
    shared_id = shared.json()["id"]
    assert shared.json()["allowed_user_ids"] == [ids["alice"]]

    alice_models = login("alice").get("/api/chat/models").json()["connections"]
    assert alice_models == [{"id": shared_id, "name": "公司 Ollama", "provider": "ollama", "scope": "shared", "models": ["qwen3:8b"]}]
    assert "localhost" not in login("alice").get("/api/llm-connections").text
    assert login("bob").get("/api/chat/models").json()["connections"] == []
    assert login("bob").get("/api/admin/llm-connections").status_code == 403
    assert login("bob").put(f"/api/llm-connections/{shared_id}", json={"name": "x"}).status_code == 404

    opened = login("root").put(f"/api/admin/llm-connections/{shared_id}", json={"allowed_user_ids": []})
    assert opened.json()["allowed_user_ids"] is None
    assert [c["id"] for c in login("bob").get("/api/chat/models").json()["connections"]] == [shared_id]

    unknown = login("root").put(f"/api/admin/llm-connections/{shared_id}", json={"allowed_user_ids": [999]})
    assert unknown.status_code == 400
    assert login("root").get("/api/admin/llm-connections").json()["connections"][0]["allowed_user_ids"] is None


def test_chat_endpoint_resolution_checks_access_models_and_network_scope(env):
    login, Session, ids = env
    alice_conn = login("alice").post("/api/llm-connections", json=personal()).json()["id"]
    root_conn = login("root").post("/api/llm-connections", json=personal(provider="ollama", api_base="http://localhost:11434", api_key=None)).json()["id"]
    shared_conn = login("root").post("/api/admin/llm-connections", json={
        **personal(name="共用", api_key="sk-company"), "allowed_user_ids": [ids["alice"]],
    }).json()["id"]

    with Session() as session:
        endpoint = connections_service.resolve_chat_endpoint(session, ids["alice"], alice_conn, "gpt-6-luna")
        assert (endpoint.provider, endpoint.api_key, endpoint.public_only) == ("openai", "sk-alice", True)
        assert connections_service.resolve_chat_endpoint(session, ids["alice"], shared_conn, "gpt-6-sol").public_only is False
        assert connections_service.resolve_chat_endpoint(session, ids["root"], root_conn, "gpt-6-sol").public_only is False
        for user, connection_id, model in (
            ("bob", alice_conn, "gpt-6-sol"),
            ("bob", shared_conn, "gpt-6-sol"),
            ("alice", root_conn, "gpt-6-sol"),
            ("alice", alice_conn, "claude-opus-5-5"),
        ):
            with pytest.raises(SafeClientError):
                connections_service.resolve_chat_endpoint(session, ids[user], connection_id, model)


def test_connection_test_reports_errors_without_internal_addresses(env, monkeypatch):
    login, _, ids = env
    alice = login("alice")
    connection_id = alice.post("/api/llm-connections", json=personal()).json()["id"]
    calls = []

    async def fake_call_llm(messages, *, endpoint, model_name, timeout=None, reasoning_effort=None):
        calls.append((endpoint.api_key, model_name))
        return "OK"

    monkeypatch.setattr(connections_api, "call_llm", fake_call_llm)
    assert alice.post(f"/api/llm-connections/{connection_id}/test", json={"model_name": "gpt-6-sol"}).json() == {"ok": True, "reply": "OK"}
    assert calls == [("sk-alice", "gpt-6-sol")]
    assert alice.post(f"/api/llm-connections/{connection_id}/test", json={"model_name": "other"}).status_code == 400

    async def blocked(*args, **kwargs):
        try:
            raise SSRFProtectionError("SSRF 防護拒絕連線: 主機解析至受保護或私有 IP 位址 (10.0.0.5)")
        except SSRFProtectionError as e:
            raise RuntimeError("Connection error.") from e

    monkeypatch.setattr(connections_api, "call_llm", blocked)
    result = alice.post(f"/api/llm-connections/{connection_id}/test", json={"model_name": "gpt-6-sol"}).json()
    assert result == {"ok": False, "error": connections_service.PRIVATE_ADDRESS_MESSAGE}

    shared_id = login("root").post("/api/admin/llm-connections", json={**personal(name="共用"), "allowed_user_ids": []}).json()["id"]
    assert login("alice").post(f"/api/llm-connections/{shared_id}/test", json={"model_name": "gpt-6-sol"}).status_code == 404


def test_deleting_an_account_removes_its_connections_and_access(env):
    login, Session, ids = env
    login("alice").post("/api/llm-connections", json=personal())
    shared_id = login("root").post("/api/admin/llm-connections", json={
        **personal(name="共用"), "allowed_user_ids": [ids["alice"], ids["bob"]],
    }).json()["id"]

    assert login("root").delete(f"/api/admin/users/{ids['alice']}").status_code == 200

    with Session() as session:
        assert session.query(LlmConnection).filter(LlmConnection.owner_id == ids["alice"]).count() == 0
        assert json.loads(session.get(LlmConnection, shared_id).allowed_user_ids) == [ids["bob"]]
