import json

import pytest

from app.api import llm_connections as connections_api
from app.core.jwt_auth import PasswordManager
from app.models import LlmConnection, User
from test_llm_connections import env, personal


def test_admin_creates_accounts_with_the_registration_rules(env):
    login, Session, ids = env
    root = login("root")
    created = root.post("/api/admin/users", json={"username": "carol", "email": "carol@example.com", "password": "Secret123", "is_admin": False})
    assert created.status_code == 201
    assert created.json()["role"] == "user" and "hashed_password" not in created.text
    for payload, message in (
        ({"username": "carol", "email": "other@example.com", "password": "Secret123"}, "使用者名稱已被使用"),
        ({"username": "dave", "email": "carol@example.com", "password": "Secret123"}, "電子郵件已被使用"),
        ({"username": "bad name", "email": "bad@example.com", "password": "Secret123"}, "使用者名稱只能包含"),
        ({"username": "weak", "email": "weak@example.com", "password": "alllowercase1"}, "大寫"),
    ):
        response = root.post("/api/admin/users", json={**payload, "is_admin": False})
        assert response.status_code == 400
        assert message in response.json()["detail"]
    assert login("alice").post("/api/admin/users", json={"username": "eve", "email": "eve@example.com", "password": "Secret123", "is_admin": True}).status_code == 403


def test_admin_resets_passwords_and_revokes_sessions(env):
    login, Session, ids = env
    with Session() as session:
        before = session.get(User, ids["alice"]).tokens_valid_after
    root = login("root")
    assert root.put(f"/api/admin/users/{ids['alice']}/password", json={"new_password": "weak"}).status_code == 400
    assert root.put(f"/api/admin/users/{ids['root']}/password", json={"new_password": "Secret123"}).status_code == 400
    assert root.put("/api/admin/users/999/password", json={"new_password": "Secret123"}).status_code == 404
    assert root.put(f"/api/admin/users/{ids['alice']}/password", json={"new_password": "NewSecret456"}).status_code == 200
    with Session() as session:
        alice = session.get(User, ids["alice"])
        assert PasswordManager.verify_password("NewSecret456", alice.hashed_password)
        assert alice.tokens_valid_after > before


def test_admins_cannot_lock_themselves_out(env):
    login, Session, ids = env
    root = login("root")
    for changes in ({"is_active": False}, {"is_admin": False}):
        response = root.put(f"/api/admin/users/{ids['root']}", json=changes)
        assert response.status_code == 400
    assert root.delete(f"/api/admin/users/{ids['root']}").status_code == 400
    assert root.put(f"/api/admin/users/{ids['root']}", json={"email": "root2@example.com"}).status_code == 200

    promoted = root.put(f"/api/admin/users/{ids['alice']}", json={"is_admin": True}).json()["user"]
    assert (promoted["is_admin"], promoted["role"]) == (True, "admin")
    demoted = root.put(f"/api/admin/users/{ids['alice']}", json={"is_admin": False}).json()["user"]
    assert (demoted["is_admin"], demoted["role"]) == (False, "user")


@pytest.mark.parametrize("changes", [{"username": "a b"}, {"username": "ab"}, {"email": "not-an-email"}])
def test_admin_user_updates_are_validated(env, changes):
    login, _, ids = env
    assert login("root").put(f"/api/admin/users/{ids['alice']}", json=changes).status_code == 422


def test_admin_sets_which_shared_connections_an_account_may_use(env):
    login, Session, ids = env
    root = login("root")
    restricted = root.post("/api/admin/llm-connections", json={**personal(name="限定"), "allowed_user_ids": [ids["bob"]]}).json()["id"]
    everyone = root.post("/api/admin/llm-connections", json={**personal(name="全部"), "allowed_user_ids": []}).json()["id"]
    login("alice").post("/api/llm-connections", json=personal(name="我的"))

    access = login("root").get(f"/api/admin/users/{ids['alice']}/llm-connections").json()
    assert [c["name"] for c in access["personal"]] == ["我的"]
    assert {c["id"]: (c["all_users"], c["allowed"]) for c in access["shared"]} == {restricted: (False, False), everyone: (True, True)}

    updated = login("root").put(f"/api/admin/users/{ids['alice']}/llm-connections", json={"shared_connection_ids": [restricted]})
    assert {c["id"]: c["allowed"] for c in updated.json()["shared"]} == {restricted: True, everyone: True}
    assert {c["id"] for c in login("alice").get("/api/chat/models").json()["connections"]} >= {restricted, everyone}

    login("root").put(f"/api/admin/users/{ids['alice']}/llm-connections", json={"shared_connection_ids": []})
    with Session() as session:
        assert json.loads(session.get(LlmConnection, restricted).allowed_user_ids) == [ids["bob"]]
        assert session.get(LlmConnection, everyone).allowed_user_ids is None

    assert login("root").put(f"/api/admin/users/{ids['alice']}/llm-connections", json={"shared_connection_ids": [999]}).status_code == 400
    assert login("alice").get(f"/api/admin/users/{ids['alice']}/llm-connections").status_code == 403


def test_model_discovery_uses_the_stored_key_and_network_scope(env, monkeypatch):
    login, _, ids = env
    calls = []

    async def fake_list_models(endpoint):
        calls.append((endpoint.provider, endpoint.api_base, endpoint.api_key, endpoint.public_only))
        return ["gpt-6-luna", "gpt-6-sol"]

    monkeypatch.setattr(connections_api, "list_models", fake_list_models)
    alice = login("alice")
    connection_id = alice.post("/api/llm-connections", json=personal()).json()["id"]
    body = {"provider": "openai", "api_base": "https://api.example.com/v1", "connection_id": connection_id}
    assert alice.post("/api/llm-connections/discover-models", json=body).json() == {"models": ["gpt-6-luna", "gpt-6-sol"]}
    assert alice.post("/api/llm-connections/discover-models", json={**body, "api_key": "sk-draft"}).status_code == 200
    assert login("bob").post("/api/llm-connections/discover-models", json=body).status_code == 404
    login("root").post("/api/llm-connections/discover-models", json={"provider": "ollama", "api_base": "http://localhost:11434"})
    assert calls == [
        ("openai", "https://api.example.com/v1", "sk-alice", True),
        ("openai", "https://api.example.com/v1", "sk-draft", True),
        ("ollama", "http://localhost:11434", None, False),
    ]

    async def failing(endpoint):
        raise ValueError("Foundry 無法從 API 列出部署，請手動填寫部署名稱")

    monkeypatch.setattr(connections_api, "list_models", failing)
    failed = login("root").post("/api/llm-connections/discover-models", json={"provider": "foundry", "api_base": "https://x.services.ai.azure.com", "api_key": "k"})
    assert failed.status_code == 400 and "手動填寫" in failed.json()["detail"]
