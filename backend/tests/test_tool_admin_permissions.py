"""
MCP 伺服器與自訂 API 工具的權限與出站防護
驗證：
1. 兩個模組的每個端點都拒絕非管理員，且不會啟動子行程或送出外部請求
2. 管理員可以正常管理；MCP HTTP 網址被 SSRF 防護拒絕時註明遭拒並附錯誤代碼，不帶出伺服器端的解析結果
3. stdio 子行程不繼承後端的機密環境變數
4. 自訂 API 工具與 MCP HTTP 傳輸的每一跳（含轉址）都經過 SSRF 檢查
"""
import ipaddress
import os
import re
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api import api_tools, mcp
from app.api.api_tools import execute_http_api_tool
from app.core.jwt_auth import get_current_user_from_token
from app.core.ssrf_protection import SSRFProtectionError
from app.models import McpServer
from app.models.database import Base, SessionLocal, engine
from app.services import mcp_service
from app.services.mcp_service import INHERITED_ENV_VARS, McpHttpClient, McpManager, build_stdio_env

NORMAL_USER = {"user_id": 2, "username": "member", "email": "member@example.com", "role": "user", "is_admin": False}
ADMIN_USER = {"user_id": 1, "username": "admin", "email": "admin@example.com", "role": "admin", "is_admin": True}
ROUTERS = ((mcp.router, "/api/mcp"), (api_tools.router, "/api/api-tools"))
TEST_SERVER_NAMES = ("permission_test_stdio", "permission_test_http")


def build_client(user):
    app = FastAPI()
    for router, prefix in ROUTERS:
        app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_current_user_from_token] = lambda: user
    return TestClient(app)


def all_endpoints():
    for router, prefix in ROUTERS:
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            # 權限檢查應在讀取資料前擋下，路徑參數代入任意值即可
            path = re.sub(r"\{[^}]+\}", "1", prefix + route.path)
            for method in sorted(route.methods):
                yield method, path


@pytest.fixture
def no_side_effects(monkeypatch):
    """記錄測試期間是否啟動子行程或送出外部 HTTP 請求"""
    calls = {"spawned": [], "sent": []}

    async def fake_spawn(*args, **kwargs):
        calls["spawned"].append(args)
        raise AssertionError("不應啟動子行程")

    async def fake_send(self, request):
        calls["sent"].append(str(request.url))
        raise AssertionError("不應送出外部請求")

    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_send)
    return calls


@pytest.fixture
def clean_test_servers():
    Base.metadata.create_all(bind=engine)

    def remove():
        db = SessionLocal()
        try:
            db.query(McpServer).filter(McpServer.name.in_(TEST_SERVER_NAMES)).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    remove()
    yield
    remove()


def test_every_tool_endpoint_rejects_non_admin(no_side_effects):
    client = build_client(NORMAL_USER)
    endpoints = list(all_endpoints())
    assert len(endpoints) >= 18
    stdio_payload = {
        "name": "permission_test_stdio",
        "display_name": "權限測試",
        "transport_type": "stdio",
        "command": "python",
        "args": ["-c", "print('should not run')"],
    }
    for method, path in endpoints:
        response = client.request(method, path, json=stdio_payload)
        assert response.status_code == 403, f"{method} {path} 回傳 {response.status_code}"
        assert response.json()["detail"] == "需要管理員權限"
    assert no_side_effects["spawned"] == []
    assert no_side_effects["sent"] == []


def test_admin_can_create_and_delete_mcp_server(monkeypatch, clean_test_servers):
    monkeypatch.setattr(
        McpManager,
        "discover_server_tools",
        AsyncMock(return_value=([], {"protocolVersion": mcp_service.MCP_PROTOCOL_VERSION})),
    )
    client = build_client(ADMIN_USER)
    created = client.post(
        "/api/mcp/servers",
        json={"name": "permission_test_stdio", "display_name": "權限測試", "transport_type": "stdio", "command": "python"},
    )
    assert created.status_code == 200
    server = created.json()["server"]
    assert server["status"] == "connected"
    assert client.get("/api/mcp/servers").status_code == 200
    assert client.get("/api/api-tools").status_code == 200
    assert client.delete(f"/api/mcp/servers/{server['id']}").status_code == 200


def test_mcp_http_server_on_private_address_is_rejected(no_side_effects, clean_test_servers):
    client = build_client(ADMIN_USER)
    created = client.post(
        "/api/mcp/servers",
        json={"name": "permission_test_http", "display_name": "內網測試", "transport_type": "http", "url": "http://localhost:8080/mcp"},
    )
    assert created.status_code == 200
    server = created.json()["server"]
    assert server["status"] == "error"
    assert "SSRF" in server["last_error"]
    discovered = client.post(f"/api/mcp/servers/{server['id']}/discover")
    assert discovered.status_code == 400
    assert "SSRF" in discovered.json()["detail"]
    assert no_side_effects["sent"] == []


def test_mcp_ssrf_rejection_hides_resolved_address(no_side_effects, clean_test_servers):
    """拒絕原因含伺服器端 DNS 解析出的內網 IP，只寫入日誌；回應只說明遭 SSRF 防護拒絕並附錯誤代碼"""
    client = build_client(ADMIN_USER)
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = [ipaddress.ip_address("10.20.30.40")]
        created = client.post(
            "/api/mcp/servers",
            json={"name": "permission_test_http", "display_name": "解析到內網", "transport_type": "http", "url": "https://mcp.example.com/mcp"},
        )
        server = created.json()["server"]
        discovered = client.post(f"/api/mcp/servers/{server['id']}/discover")
        stored = client.get(f"/api/mcp/servers/{server['id']}").json()["server"]
    assert server["status"] == "error"
    assert discovered.status_code == 400
    for message in (server["last_error"], discovered.json()["detail"], stored["last_error"]):
        assert "SSRF" in message
        assert "10.20.30.40" not in message
        assert re.search(r"錯誤代碼：[0-9a-f]{12}", message)
    assert no_side_effects["sent"] == []


def test_stdio_env_excludes_backend_secrets(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "backend-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db/app")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-backend")
    env = build_stdio_env({"MCP_TOKEN": "server-token"})
    assert "JWT_SECRET_KEY" not in env
    assert "DATABASE_URL" not in env
    assert "OPENAI_API_KEY" not in env
    assert env["MCP_TOKEN"] == "server-token"
    assert env["PATH"] == os.environ["PATH"]


def test_stdio_env_skips_exported_shell_functions(monkeypatch):
    key = INHERITED_ENV_VARS[-1]
    monkeypatch.setenv(key, "() { echo injected; }")
    assert key not in build_stdio_env({})


@pytest.mark.anyio
async def test_api_tool_redirect_to_metadata_ip_is_blocked(monkeypatch):
    sent = []

    async def redirect_to_metadata(self, request):
        sent.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"}, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", redirect_to_metadata)
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = [ipaddress.ip_address("93.184.216.34")]
        result = await execute_http_api_tool(
            {"name": "redirect_probe", "method": "GET", "url": "https://api.example.com/status"},
            {},
        )
    assert result["status_code"] == 403
    assert result["is_success"] is False
    assert "SSRF" in result["error"]
    assert sent == ["https://api.example.com/status"]


@pytest.mark.anyio
async def test_mcp_http_client_rejects_private_address(no_side_effects):
    client = McpHttpClient(url="http://127.0.0.1:8080/mcp")
    with pytest.raises(SSRFProtectionError):
        await client.initialize()
    assert no_side_effects["sent"] == []
