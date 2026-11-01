import ipaddress
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.api.api_tools import execute_http_api_tool
from app.services.api_tool_request import serialize_cookie, serialize_header, serialize_path, serialize_query
from app.services import oauth_client

PUBLIC_IP = ipaddress.ip_address("93.184.216.34")


@pytest.fixture
def upstream(monkeypatch):
    state = {"sent": [], "handler": lambda request: httpx.Response(200, json={"ok": True}, request=request)}

    async def fake_send(self, request):
        await request.aread()
        state["sent"].append(request)
        return state["handler"](request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_send)
    oauth_client._token_cache.clear()
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = [PUBLIC_IP]
        yield state


@pytest.mark.parametrize("value, style, explode, expected", [
    ("blue", "simple", False, "blue"),
    (["blue", "black"], "simple", False, "blue,black"),
    ({"R": 100, "G": 200}, "simple", False, "R,100,G,200"),
    ({"R": 100, "G": 200}, "simple", True, "R=100,G=200"),
    ("blue", "label", False, ".blue"),
    (["blue", "black"], "label", True, ".blue.black"),
    ("blue", "matrix", False, ";color=blue"),
    (["blue", "black"], "matrix", True, ";color=blue;color=black"),
    ({"R": 100, "G": 200}, "matrix", False, ";color=R,100,G,200"),
    (True, "simple", False, "true"),
    ("a/b?c", "simple", False, "a%2Fb%3Fc"),
])
def test_path_styles_follow_the_openapi_examples(value, style, explode, expected):
    assert serialize_path("color", value, style, explode) == expected


@pytest.mark.parametrize("value", [".", "..", ["ok", ".."]])
def test_path_values_cannot_be_dot_segments(value):
    with pytest.raises(ValueError):
        serialize_path("id", value, "simple", False)
    with pytest.raises(ValueError):
        serialize_path("id", "." if value == "" else value, "label", False)


@pytest.mark.parametrize("value, spec, expected", [
    (["blue", "black"], {"style": "form", "explode": True}, [("color", "blue"), ("color", "black")]),
    (["blue", "black"], {"style": "form", "explode": False}, [("color", "blue,black")]),
    (["blue", "black"], {"style": "spaceDelimited", "explode": False}, [("color", "blue%20black")]),
    (["blue", "black"], {"style": "pipeDelimited", "explode": False}, [("color", "blue%7Cblack")]),
    ({"R": 100, "G": 200}, {"style": "form", "explode": True}, [("R", "100"), ("G", "200")]),
    ({"R": 100, "G": 200}, {"style": "form", "explode": False}, [("color", "R,100,G,200")]),
    ({"R": 100, "G": 200}, {"style": "deepObject", "explode": True}, [("color[R]", "100"), ("color[G]", "200")]),
    ("a/b c", {"style": "form", "allow_reserved": True}, [("color", "a/b%20c")]),
    ("a/b c", {"style": "form"}, [("color", "a%2Fb%20c")]),
    ({"lat": 1.5}, {"content_type": "application/json"}, [("color", "%7B%22lat%22%3A1.5%7D")]),
    (None, {}, []),
])
def test_query_styles_follow_the_openapi_examples(value, spec, expected):
    assert serialize_query("color", value, spec) == expected


def test_header_and_cookie_styles():
    assert serialize_header(["a", "b"], {}) == "a,b"
    assert serialize_header({"x": 1, "y": True}, {"explode": True}) == "x=1,y=true"
    assert serialize_header(False, {}) == "false"
    assert serialize_cookie("prefs", ["a b", "c"], {"explode": False}) == ["prefs=a%20b,c"]
    assert serialize_cookie("prefs", "a b", {"style": "cookie"}) == ["prefs=a b"]


def styled_tool(**overrides):
    tool = {
        "name": "pets",
        "method": "GET",
        "url": "https://api.example.com/pets/{petId}?fixed=1",
        "auth_type": "api_key",
        "auth_config": {"key_name": "session", "key_in": "cookie", "key_value": "secret-session"},
        "headers": {"Cookie": "region=tw"},
        "parameters_schema": {"type": "object", "properties": {
            "petId": {}, "filter": {}, "fields": {}, "lang": {}, "X-Trace": {}, "petId_query": {},
        }},
        "param_locations": {"petId": "path", "filter": "query", "fields": "query", "lang": "cookie", "X-Trace": "header"},
        "param_styles": {
            "petId": {"name": "petId", "in": "path", "style": "label", "explode": False},
            "filter": {"name": "filter", "in": "query", "style": "deepObject", "explode": True},
            "fields": {"name": "fields", "in": "query", "style": "form", "explode": False},
            "lang": {"name": "lang", "in": "cookie", "style": "form", "explode": True},
            "X-Trace": {"name": "X-Trace", "in": "header", "style": "simple", "explode": False},
            "petId_query": {"name": "petId", "in": "query", "style": "form", "explode": True},
        },
    }
    tool.update(overrides)
    return tool


@pytest.mark.anyio
async def test_executor_serializes_every_location_by_its_style(upstream):
    result = await execute_http_api_tool(styled_tool(), {
        "petId": 7, "filter": {"color": "red"}, "fields": ["name", "kind"], "lang": "zh-TW",
        "X-Trace": ["a", "b"], "petId_query": 8,
    }, "pets")
    assert result["is_success"] is True
    request = upstream["sent"][0]
    assert request.url.path == "/pets/.7"
    assert request.url.query.decode() == "fixed=1&filter[color]=red&fields=name,kind&petId=8"
    assert request.headers["x-trace"] == "a,b"
    assert request.headers["cookie"] == "region=tw; session=secret-session; lang=zh-TW"
    assert "secret-session" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.anyio
async def test_header_parameters_cannot_override_credentials(upstream):
    tool = styled_tool(
        auth_type="bearer", auth_config={"token": "t-123456"},
        param_locations={"Authorization": "header"},
        param_styles={"Authorization": {"name": "Authorization", "in": "header"}},
        parameters_schema={"type": "object", "properties": {"Authorization": {}}},
        url="https://api.example.com/pets",
    )
    result = await execute_http_api_tool(tool, {"Authorization": "Bearer stolen"}, "pets")
    assert result["status_code"] == 400 and "Authorization" in result["error"]
    assert upstream["sent"] == []


@pytest.mark.anyio
async def test_querystring_parameter_becomes_the_whole_query(upstream):
    tool = {
        "name": "search", "method": "GET", "url": "https://api.example.com/search",
        "parameters_schema": {"type": "object", "properties": {"params": {}}},
        "param_styles": {"params": {"name": "params", "in": "querystring", "content_type": "application/x-www-form-urlencoded"}},
    }
    await execute_http_api_tool(tool, {"params": {"q": "貓 咪", "page": 2, "tags": ["a", "b"]}}, "search")
    assert upstream["sent"][0].url.query.decode() == "q=%E8%B2%93%20%E5%92%AA&page=2&tags=a&tags=b"


@pytest.mark.anyio
@pytest.mark.parametrize("content_type, body, expected_body", [
    ("application/merge-patch+json", {"name": "Rex"}, b'{"name":"Rex"}'),
    ("application/xml", {"name": "Rex", "tags": ["a", "b"]}, b"<Pet><name>Rex</name><tags>a</tags><tags>b</tags></Pet>"),
    ("text/plain", "hello", b"hello"),
])
async def test_bodies_use_the_declared_media_type(upstream, content_type, body, expected_body):
    tool = {
        "name": "put", "method": "PUT", "url": "https://api.example.com/pets/1", "body_content_type": content_type,
        "parameters_schema": {"type": "object", "properties": {"request_body": {}}},
        "param_styles": {"request_body": {"name": "request_body", "in": "body", "whole": True}, "$body": {"xml_root": "Pet"}},
    }
    await execute_http_api_tool(tool, {"request_body": body}, "put")
    request = upstream["sent"][0]
    assert request.headers["content-type"] == content_type
    assert request.content == expected_body


@pytest.mark.anyio
async def test_custom_methods_from_oas32_can_send_bodies(upstream):
    tool = {
        "name": "q", "method": "QUERY", "url": "https://api.example.com/search",
        "parameters_schema": {"type": "object", "properties": {"q": {}}},
        "param_styles": {"q": {"name": "q", "in": "body"}},
    }
    await execute_http_api_tool(tool, {"q": "cats"}, "q")
    request = upstream["sent"][0]
    assert request.method == "QUERY" and request.content == b'{"q":"cats"}'


@pytest.mark.anyio
async def test_tools_without_styles_keep_working_and_objects_are_not_python_repr(upstream):
    tool = {
        "name": "legacy", "method": "GET", "url": "https://api.example.com/items",
        "parameters_schema": {"type": "object", "properties": {"tags": {}, "filter": {}, "active": {}}},
        "param_locations": {"tags": "query", "filter": "query", "active": "query"},
    }
    await execute_http_api_tool(tool, {"tags": ["a", "b"], "filter": {"color": "red"}, "active": True}, "legacy")
    assert upstream["sent"][0].url.query.decode() == "tags=a&tags=b&color=red&active=true"
