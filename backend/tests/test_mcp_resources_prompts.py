import ipaddress
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models import McpServer
from app.models.database import Base, SessionLocal, engine
from app.rag.tools import ResearchToolRegistry
from app.services.mcp_service import McpManager

PUBLIC_IP = ipaddress.ip_address("93.184.216.34")
URL = "https://mcp.example.com/mcp"
SERVER_NAME = "catalog_test_server"


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


def server_handler(request):
    if request.method == "DELETE":
        return httpx.Response(200, request=request)
    body = json.loads(request.content)
    method = body.get("method")
    results = {
        "initialize": {"capabilities": {"tools": {}, "resources": {}, "prompts": {}}},
        "tools/list": {"tools": []},
        "resources/list": {"resources": [
            {"uri": "file:///docs/readme.md", "name": "readme", "description": "專案說明", "mimeType": "text/markdown"},
            {"name": "no uri"},
        ]},
        "prompts/list": {"prompts": [
            {"name": "summarize", "description": "摘要", "arguments": [{"name": "topic", "required": True}, {"name": "bad name!"}]},
            {"name": "bad prompt!"},
        ]},
        "resources/read": {"contents": [{"uri": "file:///docs/readme.md", "text": "內容"}]},
        "prompts/get": {"description": "摘要", "messages": [{"role": "user", "content": {"type": "text", "text": "請摘要 AI"}}]},
    }
    if "id" not in body:
        return httpx.Response(202, request=request)
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": results[method]}, request=request)


@pytest.fixture
def stored_server():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.query(McpServer).filter(McpServer.name == SERVER_NAME).delete()
    server = McpServer(
        name=SERVER_NAME, display_name="目錄測試", transport_type="http", url=URL, is_enabled=True,
        requires_approval=True, status="connected", discovered_tools="[]",
        discovered_resources=json.dumps([{"uri": "file:///docs/readme.md", "name": "readme", "description": "專案說明"}]),
        discovered_prompts=json.dumps([{"name": "summarize", "description": "摘要", "arguments": [{"name": "topic", "required": True}]}]),
        timeout=5,
    )
    db.add(server)
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(McpServer).filter(McpServer.name == SERVER_NAME).delete()
    db.commit()
    db.close()


@pytest.mark.anyio
async def test_discovery_collects_valid_resources_and_prompts(upstream):
    upstream["handler"] = server_handler
    _, _, catalog = await McpManager.discover_server_tools({"transport_type": "http", "url": URL, "timeout": 5})
    assert [r["uri"] for r in catalog["resources"]] == ["file:///docs/readme.md"]
    assert [p["name"] for p in catalog["prompts"]] == ["summarize"]
    assert catalog["prompts"][0]["arguments"] == [{"name": "topic", "description": None, "required": True}]


@pytest.mark.anyio
async def test_discovery_skips_lists_the_server_does_not_offer(upstream):
    def handler(request):
        if request.method == "DELETE":
            return httpx.Response(200, request=request)
        body = json.loads(request.content)
        if "id" not in body:
            return httpx.Response(202, request=request)
        result = {"capabilities": {"tools": {}}} if body["method"] == "initialize" else {"tools": []}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result}, request=request)

    upstream["handler"] = handler
    _, _, catalog = await McpManager.discover_server_tools({"transport_type": "http", "url": URL, "timeout": 5})
    assert catalog == {"resources": [], "prompts": []}
    methods = [json.loads(r.content).get("method") for r in upstream["sent"] if r.method == "POST"]
    assert "resources/list" not in methods and "prompts/list" not in methods


def tool(definitions, name):
    return next((t for t in definitions if t["function"]["name"] == name), None)


@pytest.mark.anyio
async def test_agent_tools_read_only_listed_items(upstream, stored_server):
    upstream["handler"] = server_handler
    registry = ResearchToolRegistry()
    definitions = registry.get_tool_definitions()
    read = tool(definitions, "read_mcp_resource")
    prompt = tool(definitions, "get_mcp_prompt")
    assert SERVER_NAME in read["function"]["parameters"]["properties"]["server"]["enum"]
    assert "file:///docs/readme.md" in read["function"]["description"]
    assert "summarize" in prompt["function"]["description"] and "topic*" in prompt["function"]["description"]

    result = await registry.execute_tool("read_mcp_resource", {"server": SERVER_NAME, "uri": "file:///docs/readme.md"})
    assert result["contents"][0]["text"] == "內容"
    result = await registry.execute_tool("get_mcp_prompt", {"server": SERVER_NAME, "name": "summarize", "arguments": {"topic": "AI"}})
    assert result["messages"][0]["content"]["text"] == "請摘要 AI"
    get_request = next(json.loads(r.content) for r in upstream["sent"] if r.method == "POST" and json.loads(r.content).get("method") == "prompts/get")
    assert get_request["params"] == {"name": "summarize", "arguments": {"topic": "AI"}}

    sent_before = len(upstream["sent"])
    refused = await registry.execute_tool("read_mcp_resource", {"server": SERVER_NAME, "uri": "file:///etc/passwd"})
    assert "error" in refused
    assert len(upstream["sent"]) == sent_before


def test_catalog_tools_follow_server_approval(stored_server):
    registry = ResearchToolRegistry()
    requirement = registry.approval_requirement("read_mcp_resource", {"server": SERVER_NAME, "uri": "file:///docs/readme.md"})
    assert requirement["kind"] == "mcp"
    assert requirement["target"] == "HTTP mcp.example.com"
    assert registry.approval_requirement("read_mcp_resource", {"server": SERVER_NAME, "uri": "file:///other"}) is None
