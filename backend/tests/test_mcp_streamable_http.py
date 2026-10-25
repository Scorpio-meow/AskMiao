import ipaddress
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import mcp_service
from app.services.mcp_service import MCP_HTTP_ACCEPT, McpHttpClient, McpManager

PUBLIC_IP = ipaddress.ip_address("93.184.216.34")
URL = "https://mcp.example.com/mcp"


@pytest.fixture
def upstream(monkeypatch):
    state = {"sent": [], "handler": None}

    async def fake_send(self, request):
        await request.aread()
        state["sent"].append(request)
        return state["handler"](request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_send)
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = [PUBLIC_IP]
        yield state


def sse(*messages):
    body = "".join(f"event: message\r\ndata: {json.dumps(m)}\r\n\r\n" for m in messages)
    return {"content": body.encode(), "headers": {"content-type": "text/event-stream"}}


def streamable_server(pages):
    def handler(request):
        if request.method == "DELETE":
            return httpx.Response(200, request=request)
        body = json.loads(request.content)
        method = body.get("method")
        if method == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "s"}}
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": body["id"], "result": result},
                headers={"mcp-session-id": "session-abc"}, request=request,
            )
        if method == "notifications/initialized":
            return httpx.Response(202, request=request)
        if method == "tools/list":
            page = int(body["params"].get("cursor", "0"))
            result = {"tools": [{"name": f"tool_{page}"}]}
            if page + 1 < pages:
                result["nextCursor"] = str(page + 1)
            return httpx.Response(200, request=request, **sse(
                {"jsonrpc": "2.0", "method": "notifications/message", "params": {"level": "info"}},
                {"jsonrpc": "2.0", "id": body["id"], "method": "roots/list"},
                {"jsonrpc": "2.0", "id": body["id"], "result": result},
            ))
        if method == "tools/call":
            return httpx.Response(200, request=request, **sse(
                {"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": "ok"}]}},
            ))
        return httpx.Response(400, request=request)
    return handler


@pytest.mark.anyio
async def test_streamable_http_handshake_session_and_paginated_sse(upstream):
    upstream["handler"] = streamable_server(pages=3)
    tools, init, _ = await McpManager.discover_server_tools({"transport_type": "http", "url": URL, "timeout": 5})

    assert [t["name"] for t in tools] == ["tool_0", "tool_1", "tool_2"]
    assert init["protocolVersion"] == "2025-06-18"
    assert upstream["sent"][-1].method == "DELETE"
    methods = [json.loads(r.content).get("method") for r in upstream["sent"][:-1]]
    assert methods == ["initialize", "notifications/initialized", "tools/list", "tools/list", "tools/list"]
    assert all(r.headers["accept"] == MCP_HTTP_ACCEPT for r in upstream["sent"])
    assert "mcp-session-id" not in upstream["sent"][0].headers
    for request in upstream["sent"][1:]:
        assert request.headers["mcp-session-id"] == "session-abc"
        assert request.headers["mcp-protocol-version"] == "2025-06-18"
    assert json.loads(upstream["sent"][2].content)["params"] == {}
    assert json.loads(upstream["sent"][3].content)["params"] == {"cursor": "1"}


@pytest.mark.anyio
async def test_streamable_http_tool_call_reads_sse_result(upstream):
    upstream["handler"] = streamable_server(pages=1)
    result = await McpManager.execute_mcp_tool({"transport_type": "http", "url": URL, "timeout": 5}, "tool_0", {})
    assert result["is_success"] is True
    assert result["content"] == [{"type": "text", "text": "ok"}]


@pytest.mark.anyio
async def test_sse_stream_without_response_fails(upstream):
    upstream["handler"] = lambda request: httpx.Response(200, request=request, **sse(
        {"jsonrpc": "2.0", "method": "notifications/progress", "params": {}},
    ))
    with pytest.raises(RuntimeError, match="SSE"):
        await McpHttpClient(url=URL).list_tools()


@pytest.mark.anyio
async def test_endless_pagination_is_bounded(upstream, monkeypatch):
    monkeypatch.setattr(mcp_service, "MAX_MCP_TOOL_PAGES", 3)

    def handler(request):
        body = json.loads(request.content)
        result = {"tools": [{"name": "t"}], "nextCursor": "again"}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result}, request=request)

    upstream["handler"] = handler
    with pytest.raises(RuntimeError, match="3 頁"):
        await McpHttpClient(url=URL).list_tools()
    assert len(upstream["sent"]) == 3


@pytest.mark.anyio
async def test_rejected_initialized_notification_fails(upstream):
    def handler(request):
        body = json.loads(request.content)
        if body.get("method") == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}}, request=request)
        return httpx.Response(400, request=request)

    upstream["handler"] = handler
    with pytest.raises(RuntimeError, match="400"):
        await McpHttpClient(url=URL).initialize()


@pytest.mark.anyio
async def test_expired_session_is_reinitialized_once(upstream):
    state = {"sessions": 0, "expired": True}

    def handler(request):
        body = json.loads(request.content)
        if body.get("method") == "initialize":
            state["sessions"] += 1
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}},
                                  headers={"mcp-session-id": f"s{state['sessions']}"}, request=request)
        if "id" not in body:
            return httpx.Response(202, request=request)
        if request.headers.get("mcp-session-id") == "s1" and state["expired"]:
            return httpx.Response(404, request=request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "t"}]}}, request=request)

    upstream["handler"] = handler
    client = McpHttpClient(url=URL)
    await client.initialize()
    tools = await client.list_tools()
    assert [t["name"] for t in tools] == ["t"]
    assert state["sessions"] == 2


class LegacyStream(httpx.AsyncByteStream):
    def __init__(self, posts):
        self.posts = posts

    async def __aiter__(self):
        yield b"event: endpoint\ndata: /messages?session=1\n\n"
        while True:
            payload = await self.posts.get()
            if payload is None:
                return
            yield f"event: message\ndata: {json.dumps(payload)}\n\n".encode()

    async def aclose(self):
        self.posts.put_nowait(None)


@pytest.mark.anyio
async def test_falls_back_to_legacy_sse_transport(upstream):
    import asyncio
    posts = asyncio.Queue()

    def handler(request):
        if request.method == "GET":
            assert request.headers["accept"] == "text/event-stream"
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=LegacyStream(posts), request=request)
        if request.url.path == "/mcp":
            return httpx.Response(405, request=request)
        body = json.loads(request.content)
        if "id" in body:
            result = {"tools": [{"name": "legacy_tool"}]} if body["method"] == "tools/list" else {"protocolVersion": "2024-11-05"}
            posts.put_nowait({"jsonrpc": "2.0", "id": body["id"], "result": result})
        return httpx.Response(202, request=request)

    upstream["handler"] = handler
    tools, init, _ = await McpManager.discover_server_tools({"transport_type": "sse", "url": URL, "timeout": 5})
    assert [t["name"] for t in tools] == ["legacy_tool"]
    assert init["protocolVersion"] == "2024-11-05"
    posted = [json.loads(r.content)["method"] for r in upstream["sent"] if r.method == "POST" and r.url.path == "/messages"]
    assert posted == ["initialize", "notifications/initialized", "tools/list"]


@pytest.mark.anyio
async def test_legacy_endpoint_on_other_origin_is_rejected(upstream):
    class OtherOrigin(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"event: endpoint\ndata: https://evil.example.net/messages\n\n"

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=OtherOrigin(), request=request)
        return httpx.Response(404, request=request)

    upstream["handler"] = handler
    with pytest.raises(RuntimeError, match="其他來源"):
        await McpManager.discover_server_tools({"transport_type": "sse", "url": URL, "timeout": 5})
