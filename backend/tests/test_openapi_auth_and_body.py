import ipaddress
import json
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs

import httpx
import pytest

from app.api.api_tools import _import_auth, execute_http_api_tool
from app.models import OpenApiImportItem
from app.services import oauth_client
from app.services.openapi_parser import OpenApiParser

PUBLIC_IP = ipaddress.ip_address("93.184.216.34")


@pytest.fixture
def upstream(monkeypatch):
    state = {"sent": [], "handler": None}

    async def fake_send(self, request):
        await request.aread()
        state["sent"].append(request)
        return state["handler"](request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_send)
    oauth_client._token_cache.clear()
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = [PUBLIC_IP]
        yield state


def post_tool(content_type):
    return {
        "name": "form_tool",
        "method": "POST",
        "url": "https://api.example.com/submit",
        "body_content_type": content_type,
        "param_locations": {"title": "body", "tags": "body"},
        "parameters_schema": {"type": "object", "properties": {"title": {"type": "string"}, "tags": {"type": "array"}}},
    }


@pytest.mark.anyio
@pytest.mark.parametrize("content_type, expected_header", [
    ("application/json", "application/json"),
    ("application/x-www-form-urlencoded", "application/x-www-form-urlencoded"),
    ("multipart/form-data", "multipart/form-data"),
])
async def test_body_is_encoded_by_declared_content_type(upstream, content_type, expected_header):
    upstream["handler"] = lambda request: httpx.Response(200, json={"ok": True}, request=request)
    result = await execute_http_api_tool(post_tool(content_type), {"title": "嗨", "tags": ["a", "b"]}, "test_tool")
    assert result["is_success"] is True
    request = upstream["sent"][0]
    assert request.headers["content-type"].startswith(expected_header)
    body = request.content.decode("utf-8")
    if content_type == "application/json":
        assert json.loads(body) == {"title": "嗨", "tags": ["a", "b"]}
    elif content_type == "application/x-www-form-urlencoded":
        assert parse_qs(body) == {"title": ["嗨"], "tags": ['["a", "b"]']}
    else:
        assert 'name="title"' in body and "嗨" in body and '["a", "b"]' in body


SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "t", "version": "1"},
    "servers": [{"url": "https://api.example.com"}],
    "security": [{"apiKeyAuth": []}],
    "components": {"securitySchemes": {
        "apiKeyAuth": {"type": "apiKey", "in": "query", "name": "api_key"},
        "bearerAuth": {"type": "http", "scheme": "bearer"},
        "cc": {"type": "oauth2", "flows": {"clientCredentials": {"tokenUrl": "https://auth.example.com/token", "scopes": {"read": "r"}}}},
        "cookie": {"type": "apiKey", "in": "cookie", "name": "sid"},
    }},
    "paths": {
        "/a": {"get": {"operationId": "a"}},
        "/b": {"get": {"operationId": "b", "security": [{"bearerAuth": []}]}},
        "/c": {"post": {"operationId": "c", "security": [{"cc": ["read"]}],
                        "requestBody": {"content": {"application/x-www-form-urlencoded": {"schema": {"type": "object", "properties": {"q": {"type": "string"}}}}}}}},
        "/d": {"get": {"operationId": "d", "security": [{"cookie": []}]}},
        "/e": {"get": {"operationId": "e", "security": []}},
        "/f": {"post": {"operationId": "f", "requestBody": {"content": {"application/xml": {"schema": {"type": "object"}}}}}},
    },
}


@pytest.mark.anyio
async def test_parser_maps_security_schemes_and_body_types():
    endpoints = {e["name"]: e for e in (await OpenApiParser.parse(json.dumps(SPEC)))["endpoints"]}
    assert endpoints["a"]["auth_type"] == "api_key"
    assert endpoints["a"]["auth_config"] == {"key_name": "api_key", "key_in": "query", "key_value": ""}
    assert endpoints["b"]["auth_type"] == "bearer"
    assert endpoints["c"]["auth_type"] == "oauth2_client_credentials"
    assert endpoints["c"]["auth_config"]["token_url"] == "https://auth.example.com/token"
    assert endpoints["c"]["auth_config"]["scope"] == "read"
    assert endpoints["c"]["body_content_type"] == "application/x-www-form-urlencoded"
    assert endpoints["d"]["auth_type"] == "none"
    assert endpoints["e"]["auth_type"] == "none"
    assert endpoints["f"]["body_content_type"] == "application/json"


def test_import_merges_global_credentials_only_for_matching_type():
    item = OpenApiImportItem(name="b", display_name="b", description="b", method="GET", path="/b", full_url="https://x/b",
                             auth_type="bearer", auth_config={"token": ""})
    assert _import_auth(item, "bearer", {"token": "secret"}) == ("bearer", {"token": "secret"})
    assert _import_auth(item, "none", {}) == ("bearer", {"token": ""})
    plain = OpenApiImportItem(name="a", display_name="a", description="a", method="GET", path="/a", full_url="https://x/a")
    assert _import_auth(plain, "bearer", {"token": "secret"}) == ("bearer", {"token": "secret"})


def test_unknown_options_are_rejected():
    with pytest.raises(ValueError):
        OpenApiImportItem(name="a", display_name="a", description="a", method="GET", path="/a", full_url="https://x/a",
                          body_content_type="application/xml")
    with pytest.raises(ValueError):
        OpenApiImportItem(name="a", display_name="a", description="a", method="GET", path="/a", full_url="https://x/a",
                          auth_type="digest")


OAUTH_TOOL = {
    "name": "oauth_tool",
    "method": "GET",
    "url": "https://api.example.com/data",
    "auth_type": "oauth2_client_credentials",
    "auth_config": {"token_url": "https://auth.example.com/token", "client_id": "cid", "client_secret": "csecret-123", "scope": "read"},
}


@pytest.mark.anyio
async def test_client_credentials_token_is_cached_and_refreshed_on_401(upstream):
    issued = []
    rejected = {"token-1"}

    def handler(request):
        if request.headers["host"] == "auth.example.com":
            token = f"token-{len(issued) + 1}"
            issued.append(token)
            return httpx.Response(200, json={"access_token": token, "expires_in": 3600}, request=request)
        token = request.headers["authorization"].split(" ", 1)[1]
        if token in rejected:
            return httpx.Response(401, json={"error": "expired"}, request=request)
        return httpx.Response(200, json={"echo": f"{token} csecret-123"}, request=request)

    upstream["handler"] = handler
    first = await execute_http_api_tool(OAUTH_TOOL, {}, "test_tool")
    assert first["is_success"] is True
    assert issued == ["token-1", "token-2"]
    assert "token-2" not in json.dumps(first) and "csecret-123" not in json.dumps(first)
    token_request = next(r for r in upstream["sent"] if r.headers["host"] == "auth.example.com")
    assert parse_qs(token_request.content.decode()) == {"grant_type": ["client_credentials"], "scope": ["read"]}
    assert token_request.headers["authorization"].startswith("Basic ")

    second = await execute_http_api_tool(OAUTH_TOOL, {}, "test_tool")
    assert second["is_success"] is True
    assert issued == ["token-1", "token-2"]


@pytest.mark.anyio
async def test_token_endpoint_failure_is_reported_without_details(upstream):
    upstream["handler"] = lambda request: httpx.Response(400, json={"error": "invalid_client", "secret": "x"}, request=request)
    result = await execute_http_api_tool(OAUTH_TOOL, {}, "test_tool")
    assert result["is_success"] is False
    assert "錯誤代碼" in result["error"]
    assert "invalid_client" not in result["error"]
    assert all(r.headers["host"] == "auth.example.com" for r in upstream["sent"])
