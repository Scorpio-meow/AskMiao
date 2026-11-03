import base64
import ipaddress
import json
import sys
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import mcp_service
from app.services.mcp_service import MCP_LEGACY_PROTOCOL_VERSION, MCP_PROTOCOL_VERSION, McpManager
from app.services.mcp_tools import (
    McpToolDefinitionError,
    encode_header_value,
    function_parameters,
    header_parameters,
    param_headers,
    tool_result,
)

PUBLIC_IP = ipaddress.ip_address("93.184.216.34")
URL = "https://mcp.example.com/mcp"
META = "io.modelcontextprotocol/"
HEADER_TOOL = {
    "name": "execute_sql",
    "inputSchema": {
        "type": "object",
        "properties": {
            "region": {"type": "string", "x-mcp-header": "Region"},
            "options": {"type": "object", "properties": {"dry_run": {"type": "boolean", "x-mcp-header": "Dry-Run"}}},
            "query": {"type": "string"},
        },
        "required": ["region", "query"],
    },
}


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


def body_of(request):
    return json.loads(request.content)


def modern_server(tools=None, call_result=None, supported=None, mismatches=0):
    state = {"mismatches": mismatches}

    def respond(body, result):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"resultType": "complete", **result}})

    def handler(request):
        assert request.method == "POST"
        body = body_of(request)
        meta = body["params"]["_meta"]
        version = meta[f"{META}protocolVersion"]
        assert request.headers["mcp-protocol-version"] == version
        assert request.headers["mcp-method"] == body["method"]
        assert meta[f"{META}clientInfo"]["name"] == "AskMiao-MCP-Client"
        assert meta[f"{META}clientCapabilities"] == {}
        assert "mcp-session-id" not in request.headers
        if version not in (supported or [MCP_PROTOCOL_VERSION]):
            error = {"code": -32022, "message": "Unsupported protocol version", "data": {"supported": supported, "requested": version}}
            return httpx.Response(400, json={"jsonrpc": "2.0", "id": body["id"], "error": error})
        method = body["method"]
        if method == "server/discover":
            return respond(body, {
                "supportedVersions": [MCP_PROTOCOL_VERSION],
                "capabilities": {"tools": {}, "resources": {}},
                "_meta": {f"{META}serverInfo": {"name": "modern", "version": "1"}},
                "ttlMs": 1000,
                "cacheScope": "public",
            })
        if method == "tools/list":
            return respond(body, {"tools": tools or [{"name": "echo"}], "ttlMs": 1000, "cacheScope": "public"})
        if method == "resources/list":
            return respond(body, {"resources": [], "ttlMs": 1000, "cacheScope": "public"})
        if method == "resources/read":
            return respond(body, {"contents": [{"uri": body["params"]["uri"], "blob": "AAAA"}], "ttlMs": 1000, "cacheScope": "private"})
        if method == "tools/call":
            if state["mismatches"]:
                state["mismatches"] -= 1
                return httpx.Response(400, json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32020, "message": "Header mismatch"}})
            return respond(body, call_result or {"content": [{"type": "text", "text": "ok"}], "isError": False})
        return httpx.Response(404, json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32601, "message": "Method not found"}})

    return handler


def legacy_server(requests):
    def handler(request):
        if request.method == "DELETE":
            return httpx.Response(200)
        body = body_of(request)
        requests.append(body.get("method"))
        if body.get("method") == "initialize":
            result = {"protocolVersion": body["params"]["protocolVersion"], "capabilities": {"tools": {}}, "serverInfo": {"name": "legacy"}}
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result}, headers={"mcp-session-id": "s1"})
        if "id" not in body:
            return httpx.Response(202)
        if request.headers.get("mcp-session-id") != "s1":
            return httpx.Response(400, json={"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "No valid session ID"}})
        if body.get("method") == "tools/call":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": "legacy ok"}]}})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "echo"}]}})

    return handler


def test_function_parameters_resolve_local_refs_and_drop_header_hints():
    schema = {
        "type": "object",
        "$defs": {"region": {"type": "string", "enum": ["us", "eu"]}},
        "properties": {"region": {"$ref": "#/$defs/region", "x-mcp-header": "Region"}},
        "required": ["region"],
    }
    parameters = function_parameters(schema)
    assert parameters["type"] == "object"
    assert parameters["properties"]["region"]["enum"] == ["us", "eu"]
    assert "x-mcp-header" not in json.dumps(parameters)
    assert function_parameters(None) == {"type": "object", "properties": {}}


@pytest.mark.parametrize("ref", ["https://schemas.example.com/user.json", "other.json#/defs/a"])
def test_function_parameters_reject_refs_outside_the_tool(ref):
    with pytest.raises(McpToolDefinitionError):
        function_parameters({"type": "object", "properties": {"user": {"$ref": ref}}})


def test_header_parameters_follow_static_property_paths():
    assert sorted(header_parameters(HEADER_TOOL["inputSchema"])) == [(("options", "dry_run"), "Dry-Run"), (("region",), "Region")]


@pytest.mark.parametrize("schema", [
    {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string", "x-mcp-header": "Id"}}}},
    {"type": "object", "properties": {"ratio": {"type": "number", "x-mcp-header": "Ratio"}}},
    {"type": "object", "properties": {"a": {"type": "string", "x-mcp-header": "Tenant"}, "b": {"type": "string", "x-mcp-header": "tenant"}}},
    {"type": "object", "properties": {"a": {"type": "string", "x-mcp-header": "Bad Name"}}},
    {"type": "object", "oneOf": [{"properties": {"a": {"type": "string", "x-mcp-header": "A"}}}]},
])
def test_invalid_header_hints_are_rejected(schema):
    with pytest.raises(McpToolDefinitionError):
        header_parameters(schema)


@pytest.mark.parametrize("value, encoded", [
    ("us-west1", "us-west1"),
    ("Hello, 世界", "=?base64?SGVsbG8sIOS4lueVjA==?="),
    (" padded ", "=?base64?IHBhZGRlZCA=?="),
    ("line1\nline2", "=?base64?bGluZTEKbGluZTI=?="),
    ("=?base64?literal?=", "=?base64?PT9iYXNlNjQ/bGl0ZXJhbD89?="),
])
def test_header_values_use_the_base64_sentinel_when_needed(value, encoded):
    assert encode_header_value(value) == encoded


def test_param_headers_convert_primitives_and_skip_missing_values():
    parameters = header_parameters(HEADER_TOOL["inputSchema"])
    assert param_headers(parameters, {"region": "us-west1", "options": {"dry_run": True}}) == {
        "Mcp-Param-Region": "us-west1", "Mcp-Param-Dry-Run": "true",
    }
    assert param_headers(parameters, {"region": None}) == {}


def test_tool_results_hide_binary_data_and_deduplicate_structured_json():
    structured = {"temperature": 22.5}
    shaped = tool_result({
        "content": [
            {"type": "text", "text": json.dumps(structured)},
            {"type": "text", "text": "晴時多雲"},
            {"type": "image", "data": "iVBORw0KGgo=", "mimeType": "image/png"},
            {"type": "resource_link", "uri": "file:///a.txt", "name": "a.txt", "extra": "x"},
            {"type": "resource", "resource": {"uri": "file:///b.bin", "blob": "AAAA"}},
        ],
        "structuredContent": structured,
        "isError": False,
    })
    assert shaped["structuredContent"] == structured
    assert [item["type"] for item in shaped["content"]] == ["text", "image", "resource_link", "resource"]
    assert "iVBORw0KGgo=" not in json.dumps(shaped) and "AAAA" not in json.dumps(shaped)
    assert shaped["content"][2] == {"type": "resource_link", "uri": "file:///a.txt", "name": "a.txt"}
    assert tool_result({"content": [], "isError": True})["is_success"] is False


def test_invalid_header_tools_are_dropped_only_on_http():
    tools = [HEADER_TOOL, {"name": "bad", "inputSchema": {"type": "object", "properties": {"n": {"type": "number", "x-mcp-header": "N"}}}}]
    assert [t["name"] for t in mcp_service._usable_tools(tools, "http")] == ["execute_sql"]
    assert [t["name"] for t in mcp_service._usable_tools(tools, "stdio")] == ["execute_sql", "bad"]


@pytest.mark.anyio
async def test_modern_http_discovery_is_stateless(upstream):
    upstream["handler"] = modern_server()
    tools, init, catalog = await McpManager.discover_server_tools({"transport_type": "http", "url": URL, "timeout": 5})
    assert [t["name"] for t in tools] == ["echo"]
    assert init["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert init["serverInfo"] == {"name": "modern", "version": "1"}
    assert [body_of(r)["method"] for r in upstream["sent"]] == ["server/discover", "tools/list", "resources/list"]
    assert catalog == {"resources": [], "prompts": []}


@pytest.mark.anyio
async def test_modern_tool_call_mirrors_name_and_parameter_headers(upstream):
    upstream["handler"] = modern_server(tools=[HEADER_TOOL])
    server = {"transport_type": "http", "url": URL, "timeout": 5, "protocol_version": MCP_PROTOCOL_VERSION, "discovered_tools": [HEADER_TOOL]}
    result = await McpManager.execute_mcp_tool(server, "execute_sql", {"region": "台北", "query": "SELECT 1"})
    assert result["is_success"] is True
    [request] = upstream["sent"]
    assert request.headers["mcp-name"] == "execute_sql"
    assert request.headers["mcp-param-region"] == "=?base64?" + base64.b64encode("台北".encode()).decode() + "?="
    assert "mcp-param-dry-run" not in request.headers


@pytest.mark.anyio
async def test_resource_uri_is_mirrored_and_binary_contents_are_hidden(upstream):
    upstream["handler"] = modern_server()
    server = {"transport_type": "http", "url": URL, "timeout": 5, "protocol_version": MCP_PROTOCOL_VERSION}
    result = await McpManager.read_mcp_resource(server, "file:///文件.pdf")
    assert result["contents"] == [{"uri": "file:///文件.pdf", "omitted": "二進位內容不提供給模型"}]
    assert upstream["sent"][0].headers["mcp-name"].startswith("=?base64?")


@pytest.mark.anyio
async def test_header_mismatch_relists_tools_and_retries_once(upstream):
    upstream["handler"] = modern_server(tools=[HEADER_TOOL], mismatches=1)
    server = {"transport_type": "http", "url": URL, "timeout": 5, "protocol_version": MCP_PROTOCOL_VERSION, "discovered_tools": [HEADER_TOOL]}
    result = await McpManager.execute_mcp_tool(server, "execute_sql", {"region": "us", "query": "q"})
    assert result["is_success"] is True
    assert [body_of(r)["method"] for r in upstream["sent"]] == ["tools/call", "tools/list", "tools/call"]


@pytest.mark.anyio
async def test_input_required_results_are_reported_as_failures(upstream):
    upstream["handler"] = modern_server(call_result={"resultType": "input_required", "inputRequests": {"x": {"method": "elicitation/create"}}})
    server = {"transport_type": "http", "url": URL, "timeout": 5, "protocol_version": MCP_PROTOCOL_VERSION}
    result = await McpManager.execute_mcp_tool(server, "echo", {})
    assert result["is_success"] is False and "error_id" in result


@pytest.mark.anyio
async def test_unsupported_version_error_falls_back_to_an_advertised_legacy_version(upstream):
    modern = modern_server(supported=[MCP_LEGACY_PROTOCOL_VERSION])
    requests = []
    legacy = legacy_server(requests)

    def handler(request):
        body = body_of(request) if request.method == "POST" else {}
        if "_meta" in body.get("params", {}):
            return modern(request)
        return legacy(request)

    upstream["handler"] = handler
    tools, init, _ = await McpManager.discover_server_tools({"transport_type": "http", "url": URL, "timeout": 5})
    assert init["protocolVersion"] == MCP_LEGACY_PROTOCOL_VERSION
    assert requests[0] == "initialize"
    assert [t["name"] for t in tools] == ["echo"]


@pytest.mark.anyio
async def test_stale_modern_hint_renegotiates_with_a_legacy_server(upstream):
    requests = []
    upstream["handler"] = legacy_server(requests)
    server = {"id": 987654, "transport_type": "http", "url": URL, "timeout": 5, "protocol_version": MCP_PROTOCOL_VERSION}
    result = await McpManager.execute_mcp_tool(server, "echo", {})
    assert result["is_success"] is True and result["content"] == [{"type": "text", "text": "legacy ok"}]
    methods = [body_of(r).get("method") for r in upstream["sent"] if r.method == "POST"]
    assert methods[0] == "tools/call" and methods[1] == "server/discover" and "initialize" in methods
    assert McpManager._negotiated_versions.pop(987654) == MCP_LEGACY_PROTOCOL_VERSION


SILENT_LEGACY_STDIO = r"""
import json, sys
initialized = False
for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    if request["method"] == "initialize":
        initialized = True
        result = {"protocolVersion": request["params"]["protocolVersion"], "capabilities": {"tools": {}}}
    elif not initialized:
        continue
    else:
        result = {"tools": [{"name": "quiet"}]}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}) + "\n")
    sys.stdout.flush()
"""


@pytest.mark.anyio
async def test_stdio_probe_times_out_and_falls_back_to_initialize(monkeypatch):
    monkeypatch.setattr(mcp_service, "MCP_DISCOVER_PROBE_TIMEOUT_SECONDS", 0.5)
    server = {"transport_type": "stdio", "command": sys.executable, "args": ["-c", SILENT_LEGACY_STDIO], "timeout": 10}
    tools, init, _ = await McpManager.discover_server_tools(server)
    assert [t["name"] for t in tools] == ["quiet"]
    assert init["protocolVersion"] == MCP_LEGACY_PROTOCOL_VERSION


@pytest.mark.anyio
async def test_time_preset_answers_both_protocol_eras():
    preset = next(p for p in McpManager.get_preset_servers() if p["name"] == "mcp_time")
    modern = await McpManager.execute_mcp_tool({**preset, "timeout": 10}, "get_current_time", {"timezone": "UTC"})
    legacy = await McpManager.execute_mcp_tool({**preset, "timeout": 10, "protocol_version": MCP_LEGACY_PROTOCOL_VERSION}, "get_current_time", {"timezone": "UTC"})
    assert modern["is_success"] is True and legacy["is_success"] is True
    assert "UTC" in modern["content"][0]["text"] and "UTC" in legacy["content"][0]["text"]
