"""
外部工具憑證的靜態加密與回應遮蔽
驗證：
1. 自訂 API 工具的 headers、auth_config 與 MCP 伺服器的 env_vars、headers 以加密內容存入資料庫
2. 管理 API 的回應以遮蔽字樣取代秘密值，非秘密的標頭與設定照常顯示
3. 更新時送回遮蔽字樣的欄位沿用原值，新值會取代；沒有原值卻送回遮蔽字樣時拒絕
4. 執行工具時取得解密後的實際值；啟動時把舊版明文資料改為加密
5. TOOL_SECRETS_KEY 必須是 Fernet 金鑰
6. 以其他金鑰加密的憑證：回應標示 credentials_unreadable，測試與探索端點回傳 400 說明需重新輸入
"""
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app.api import api_tools, mcp
from app.core.config import Settings
from app.core.jwt_auth import get_current_user_from_token
from app.core.tool_secrets import SECRET_MASK, decrypt_json, is_encrypted
from app.models import CustomApiTool, McpServer
from app.models.database import Base, SessionLocal, engine, upgrade_schema

ADMIN_USER = {"user_id": 1, "username": "admin", "email": "admin@example.com", "role": "admin", "is_admin": True}
TOOL_NAME = "secrets_test_tool"
SERVER_NAME = "secrets_test_server"


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)

    def remove():
        with SessionLocal() as db:
            db.query(CustomApiTool).filter(CustomApiTool.name == TOOL_NAME).delete(synchronize_session=False)
            db.query(McpServer).filter(McpServer.name == SERVER_NAME).delete(synchronize_session=False)
            db.commit()

    remove()
    app = FastAPI()
    app.include_router(api_tools.router, prefix="/api/api-tools")
    app.include_router(mcp.router, prefix="/api/mcp")
    app.dependency_overrides[get_current_user_from_token] = lambda: ADMIN_USER
    yield TestClient(app)
    remove()


def stored_tool():
    with SessionLocal() as db:
        return db.query(CustomApiTool).filter(CustomApiTool.name == TOOL_NAME).first()


def test_api_tool_credentials_are_encrypted_masked_and_merged(client):
    created = client.post("/api/api-tools", json={
        "name": TOOL_NAME, "display_name": "d", "description": "d", "method": "GET", "url": "https://api.example.com/x",
        "headers": {"X-Tenant-Secret": "tenant-secret", "Accept": "application/json"},
        "auth_type": "api_key",
        "auth_config": {"key_name": "X-API-Key", "key_value": "api-key-secret", "key_in": "header"},
    })
    assert created.status_code == 200
    tool = created.json()["tool"]
    assert tool["headers"] == {"X-Tenant-Secret": SECRET_MASK, "Accept": "application/json"}
    assert tool["auth_config"] == {"key_name": "X-API-Key", "key_value": SECRET_MASK, "key_in": "header"}
    for listed in (client.get("/api/api-tools").json()["tools"], [client.get(f"/api/api-tools/{tool['id']}").json()["tool"]]):
        assert "tenant-secret" not in str(listed) and "api-key-secret" not in str(listed)

    row = stored_tool()
    assert is_encrypted(row.headers) and is_encrypted(row.auth_config)
    assert "tenant-secret" not in row.headers and "api-key-secret" not in row.auth_config

    # 送回遮蔽字樣沿用原值，新值取代，沒有送回的鍵移除
    updated = client.put(f"/api/api-tools/{tool['id']}", json={
        "headers": {"X-Tenant-Secret": SECRET_MASK, "X-Region": "tw"},
        "auth_config": {"key_name": "X-API-Key", "key_value": "rotated-key", "key_in": "header"},
    })
    assert updated.status_code == 200
    row = stored_tool()
    assert decrypt_json(row.headers) == {"X-Tenant-Secret": "tenant-secret", "X-Region": "tw"}
    assert decrypt_json(row.auth_config)["key_value"] == "rotated-key"

    rejected = client.put(f"/api/api-tools/{tool['id']}", json={"headers": {"X-Unknown": SECRET_MASK}})
    assert rejected.status_code == 400
    assert decrypt_json(stored_tool().headers)["X-Tenant-Secret"] == "tenant-secret"


def test_mcp_server_credentials_are_encrypted_and_masked(client):
    with patch("app.services.mcp_service.McpManager.discover_server_tools", new_callable=AsyncMock) as discover:
        discover.return_value = ([], {})
        created = client.post("/api/mcp/servers", json={
            "name": SERVER_NAME, "display_name": "d", "transport_type": "stdio", "command": "mcp-server",
            "env_vars": {"DATABASE_URL": "postgresql://u:pw@db/x"}, "headers": {},
        })
        # 探索時拿到的是解密後的實際值
        assert discover.call_args.args[0]["env_vars"] == {"DATABASE_URL": "postgresql://u:pw@db/x"}
    server = created.json()["server"]
    assert server["env_vars"] == {"DATABASE_URL": SECRET_MASK}
    assert "pw@db" not in str(client.get("/api/mcp/servers").json())
    with SessionLocal() as db:
        row = db.query(McpServer).filter(McpServer.name == SERVER_NAME).first()
        assert is_encrypted(row.env_vars) and "pw@db" not in row.env_vars
    client.put(f"/api/mcp/servers/{server['id']}", json={"env_vars": {"DATABASE_URL": SECRET_MASK, "LOG_LEVEL": "debug"}})
    with SessionLocal() as db:
        row = db.query(McpServer).filter(McpServer.name == SERVER_NAME).first()
        assert decrypt_json(row.env_vars) == {"DATABASE_URL": "postgresql://u:pw@db/x", "LOG_LEVEL": "debug"}


def test_existing_plaintext_credentials_are_encrypted_at_startup(tmp_path):
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE custom_api_tools (id INTEGER PRIMARY KEY, name VARCHAR, method VARCHAR, "
                          "headers TEXT, auth_config TEXT, requires_approval BOOLEAN)"))
        conn.execute(text("CREATE TABLE mcp_servers (id INTEGER PRIMARY KEY, name VARCHAR, env_vars TEXT, headers TEXT, "
                          "requires_approval BOOLEAN)"))
        conn.execute(text("INSERT INTO custom_api_tools (name, method, headers, auth_config, requires_approval) "
                          "VALUES ('t', 'GET', '{\"X-Key\": \"legacy-secret\"}', 'not json', 0)"))
        conn.execute(text("INSERT INTO mcp_servers (name, env_vars, headers, requires_approval) "
                          "VALUES ('m', '{\"TOKEN\": \"legacy-token\"}', NULL, 1)"))
    upgrade_schema(old)
    upgrade_schema(old)
    with old.connect() as conn:
        headers, auth_config = conn.execute(text("SELECT headers, auth_config FROM custom_api_tools")).one()
        env_vars = conn.execute(text("SELECT env_vars FROM mcp_servers")).scalar()
    assert decrypt_json(headers) == {"X-Key": "legacy-secret"}
    assert auth_config is None
    assert decrypt_json(env_vars) == {"TOKEN": "legacy-token"}
    old.dispose()


def test_credentials_from_another_key_are_reported_instead_of_failing(client):
    foreign = "fernet:" + Fernet(Fernet.generate_key()).encrypt(b'{"X-Key": "old-secret"}').decode("ascii")
    with SessionLocal() as db:
        tool = CustomApiTool(name=TOOL_NAME, display_name="d", description="d", method="GET",
                             url="https://api.example.com/x", headers=foreign, requires_approval=False)
        server = McpServer(name=SERVER_NAME, display_name="d", transport_type="stdio", command="mcp-server",
                           env_vars=foreign, requires_approval=True)
        db.add_all([tool, server])
        db.commit()
        tool_id, server_id = tool.id, server.id

    shown = client.get(f"/api/api-tools/{tool_id}").json()["tool"]
    assert shown["credentials_unreadable"] is True and shown["headers"] is None
    assert client.get("/api/mcp/servers").json()["servers"][0]["credentials_unreadable"] is True

    for response in (
        client.post(f"/api/api-tools/{tool_id}/test", json={"arguments": {}}),
        client.post(f"/api/mcp/servers/{server_id}/discover"),
        client.post(f"/api/mcp/servers/{server_id}/tools/echo/test", json={"arguments": {}}),
    ):
        assert response.status_code == 400
        assert "TOOL_SECRETS_KEY" in response.json()["detail"]


@pytest.mark.parametrize("key", ["", "not-a-fernet-key", "a" * 44])
def test_tool_secrets_key_must_be_a_fernet_key(key):
    with pytest.raises(ValidationError, match="TOOL_SECRETS_KEY"):
        Settings(TOOL_SECRETS_KEY=key)
