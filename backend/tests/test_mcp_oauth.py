import ipaddress
import json
import time
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import mcp
from app.core.jwt_auth import get_current_user_from_token
from app.core.tool_secrets import decrypt_json, encrypt_json
from app.models import McpServer
from app.models.database import Base, SessionLocal, engine

PUBLIC_IP = ipaddress.ip_address("93.184.216.34")
ADMIN_USER = {"user_id": 1, "username": "admin", "email": "admin@example.com", "role": "admin", "is_admin": True}
SERVER_NAME = "oauth_test_server"
MCP_URL = "https://mcp.example.com/mcp"


class FakeServers:
    def __init__(self, registration=True):
        self.registration = registration
        self.token_requests = []
        self.mcp_auth = []
        self.issued = 0

    def handle(self, request):
        host = request.headers["host"]
        path = request.url.path
        if host == "mcp.example.com" and path == "/mcp":
            auth = request.headers.get("authorization")
            self.mcp_auth.append(auth)
            if auth not in {f"Bearer access-{i}" for i in range(1, self.issued + 1)} or auth == "Bearer access-1" and self.issued > 1:
                return httpx.Response(401, headers={
                    "www-authenticate": 'Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource/mcp"'
                }, request=request)
            body = json.loads(request.content)
            if "id" not in body:
                return httpx.Response(202, request=request)
            result = {"capabilities": {"tools": {}}} if body["method"] == "initialize" else {"tools": [{"name": "secure_tool"}]}
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result}, request=request)
        if host == "mcp.example.com" and path == "/.well-known/oauth-protected-resource/mcp":
            return httpx.Response(200, json={"resource": MCP_URL, "authorization_servers": ["https://auth.example.com"], "scopes_supported": ["mcp"]}, request=request)
        if host == "auth.example.com" and path == "/.well-known/oauth-authorization-server":
            metadata = {
                "issuer": "https://auth.example.com",
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
                "code_challenge_methods_supported": ["S256"],
            }
            if self.registration:
                metadata["registration_endpoint"] = "https://auth.example.com/register"
            return httpx.Response(200, json=metadata, request=request)
        if host == "auth.example.com" and path == "/register":
            return httpx.Response(201, json={"client_id": "registered-client"}, request=request)
        if host == "auth.example.com" and path == "/token":
            form = parse_qs(request.content.decode())
            self.token_requests.append(form)
            self.issued += 1
            return httpx.Response(200, json={"access_token": f"access-{self.issued}", "refresh_token": f"refresh-{self.issued}", "expires_in": 3600}, request=request)
        return httpx.Response(404, request=request)


@pytest.fixture
def fake(monkeypatch):
    servers = FakeServers()

    async def fake_send(self, request):
        await request.aread()
        return servers.handle(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_send)
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = [PUBLIC_IP]
        yield servers


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.query(McpServer).filter(McpServer.name == SERVER_NAME).delete()
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(mcp.router, prefix="/api/mcp")
    app.include_router(mcp.oauth_callback_router, prefix="/api/mcp")
    app.dependency_overrides[get_current_user_from_token] = lambda: ADMIN_USER
    yield TestClient(app)
    db = SessionLocal()
    db.query(McpServer).filter(McpServer.name == SERVER_NAME).delete()
    db.commit()
    db.close()


def create_server(client, **extra):
    response = client.post("/api/mcp/servers", json={
        "name": SERVER_NAME, "display_name": "OAuth 測試", "transport_type": "http", "url": MCP_URL, **extra,
    })
    assert response.status_code == 200, response.text
    return response.json()["server"]


def authorize(client):
    server = create_server(client)
    assert server["status"] == "error"
    assert "OAuth" in server["last_error"]
    start = client.post(f"/api/mcp/servers/{server['id']}/oauth/start")
    assert start.status_code == 200, start.text
    url = urlparse(start.json()["authorization_url"])
    params = {k: v[0] for k, v in parse_qs(url.query).items()}
    return server, url, params


def test_full_authorization_code_flow(fake, client):
    server, url, params = authorize(client)
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://auth.example.com/authorize"
    assert params["client_id"] == "registered-client"
    assert params["code_challenge_method"] == "S256" and len(params["code_challenge"]) == 43
    assert params["resource"] == MCP_URL
    assert params["scope"] == "mcp"
    assert params["redirect_uri"] == "http://testserver/api/mcp/oauth/callback"

    page = client.get("/api/mcp/oauth/callback", params={"state": params["state"], "code": "the-code"})
    assert page.status_code == 200 and "授權完成" in page.text
    exchange = fake.token_requests[0]
    assert exchange["grant_type"] == ["authorization_code"] and exchange["code"] == ["the-code"]
    assert len(exchange["code_verifier"][0]) >= 43 and exchange["resource"] == [MCP_URL]

    replay = client.get("/api/mcp/oauth/callback", params={"state": params["state"], "code": "the-code"})
    assert replay.status_code == 400

    listed = client.get("/api/mcp/servers").json()["servers"]
    stored = next(s for s in listed if s["name"] == SERVER_NAME)
    assert stored["oauth_authorized"] is True
    assert "access-1" not in json.dumps(listed)

    discovered = client.post(f"/api/mcp/servers/{server['id']}/discover")
    assert discovered.status_code == 200, discovered.text
    assert [t["name"] for t in discovered.json()["tools"]] == ["secure_tool"]
    assert fake.mcp_auth[-1] == "Bearer access-1"


def test_expired_token_is_refreshed_before_use(fake, client):
    server, _, params = authorize(client)
    client.get("/api/mcp/oauth/callback", params={"state": params["state"], "code": "c"})
    with SessionLocal() as db:
        row = db.get(McpServer, server["id"])
        tokens = decrypt_json(row.oauth_tokens)
        tokens["expires_at"] = time.time() - 10
        row.oauth_tokens = encrypt_json(tokens)
        db.commit()
    discovered = client.post(f"/api/mcp/servers/{server['id']}/discover")
    assert discovered.status_code == 200, discovered.text
    assert fake.token_requests[-1]["grant_type"] == ["refresh_token"]
    assert fake.token_requests[-1]["refresh_token"] == ["refresh-1"]
    assert fake.mcp_auth[-1] == "Bearer access-2"


def test_rejected_or_unknown_callback_does_not_store_tokens(fake, client):
    server, _, params = authorize(client)
    denied = client.get("/api/mcp/oauth/callback", params={"state": params["state"], "error": "access_denied"})
    assert denied.status_code == 400
    assert client.get("/api/mcp/oauth/callback", params={"state": "forged", "code": "x"}).status_code == 400
    assert fake.token_requests == []
    with SessionLocal() as db:
        assert db.get(McpServer, server["id"]).oauth_tokens is None


def test_admin_client_is_used_without_registration(fake, client):
    fake.registration = False
    server = create_server(client, oauth_client={"client_id": "admin-client", "client_secret": "admin-secret", "scope": "read"})
    assert server["oauth_client"] == {"client_id": "admin-client", "client_secret": "••••••••", "scope": "read"}
    params = {k: v[0] for k, v in parse_qs(urlparse(client.post(f"/api/mcp/servers/{server['id']}/oauth/start").json()["authorization_url"]).query).items()}
    assert params["client_id"] == "admin-client" and params["scope"] == "read"
    client.get("/api/mcp/oauth/callback", params={"state": params["state"], "code": "c"})
    assert fake.token_requests[0]["code"] == ["c"]

    edited = client.put(f"/api/mcp/servers/{server['id']}", json={
        "display_name": "改名", "oauth_client": {"client_id": "admin-client", "client_secret": "••••••••", "scope": "read"},
    })
    assert edited.json()["server"]["oauth_authorized"] is True
    changed = client.put(f"/api/mcp/servers/{server['id']}", json={
        "oauth_client": {"client_id": "other-client", "client_secret": "••••••••", "scope": "read"},
    })
    assert changed.json()["server"]["oauth_authorized"] is False

    revoked = client.delete(f"/api/mcp/servers/{server['id']}/oauth")
    assert revoked.json()["server"]["oauth_authorized"] is False


def test_missing_client_without_registration_is_reported(fake, client):
    fake.registration = False
    server = create_server(client)
    response = client.post(f"/api/mcp/servers/{server['id']}/oauth/start")
    assert response.status_code == 400
    assert "client_id" in response.json()["detail"]
