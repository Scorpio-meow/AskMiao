"""
工具外送請求的安全邊界
驗證：
1. SSRF 檢查後連線固定到核可的 IP（DNS rebinding），DNS 解析有逾時
2. 自訂 API 工具：路徑參數編碼、跨來源轉址不轉送憑證、回應與網址中的憑證遮蔽、回應大小上限；
   只接受工具宣告的參數，工具網址中固定的查詢參數不可被覆寫
3. web_fetch 與 SSRF 拒絕訊息不帶出伺服器端 DNS 解析結果
4. HTTP MCP 回應大小上限
5. MCP 範本不含網頁擷取、檔案系統範本不與資料目錄重疊且釘選版本
6. 轉址回應的本文不讀取；HTTP MCP 不跟隨跨來源轉址；整個呼叫有總時限；工具網址中的固定查詢值不回傳
7. MCP 工具失敗只回傳錯誤代碼；stdio 子行程在空的暫存目錄執行，stderr 持續讀出，可讀取超過 64 KiB 的訊息行
"""
import asyncio
import ipaddress
import os
import sys
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.api.api_tools import MAX_API_TOOL_RESPONSE_BYTES, execute_http_api_tool
from app.core import ssrf_protection
from app.core.config import settings
from app.core.ssrf_protection import safe_fetch_text
from app.rag.tools import ResearchToolRegistry
from app.services import mcp_service
from app.services.mcp_service import McpHttpClient, McpManager

PUBLIC_IP = ipaddress.ip_address("93.184.216.34")
OTHER_PUBLIC_IP = ipaddress.ip_address("93.184.216.35")


@pytest.fixture
def public_dns():
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = [PUBLIC_IP]
        yield mock_dns


@pytest.fixture
def upstream(monkeypatch):
    """以函式決定上游回應，並記錄實際送到傳輸層的請求"""
    state = {"sent": [], "handler": None}

    async def fake_send(self, request):
        state["sent"].append(request)
        return state["handler"](request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_send)
    return state


@pytest.mark.anyio
async def test_connection_is_pinned_to_validated_ip(upstream):
    # 第一次解析得到公開 IP，之後改解析到內網（DNS rebinding）；連線必須用檢查時核可的 IP
    answers = [[PUBLIC_IP], [ipaddress.ip_address("10.0.0.5")]]
    upstream["handler"] = lambda request: httpx.Response(200, text="ok", request=request)
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.side_effect = lambda *args, **kwargs: answers.pop(0)
        async with httpx.AsyncClient(transport=ssrf_protection.SSRFSafeTransport(ssrf_protection.DnsPool.CONFIGURED_ENDPOINT)) as client:
            response = await client.get("https://rebind.example.com/page")
    assert response.text == "ok"
    request = upstream["sent"][0]
    assert request.url.host == str(PUBLIC_IP)
    assert request.headers["host"] == "rebind.example.com"
    assert request.extensions["sni_hostname"] == "rebind.example.com"


@pytest.mark.anyio
async def test_safe_fetch_text_never_connects_to_rebound_address(upstream):
    answers = [[PUBLIC_IP], [ipaddress.ip_address("10.0.0.5")]]
    upstream["handler"] = lambda request: httpx.Response(200, text="ok", request=request)
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.side_effect = lambda *args, **kwargs: answers.pop(0) if answers else [ipaddress.ip_address("10.0.0.5")]
        with pytest.raises(ssrf_protection.SSRFProtectionError):
            await safe_fetch_text("https://rebind.example.com/page", ssrf_protection.DnsPool.USER_URL)
    assert upstream["sent"] == []


@pytest.mark.anyio
async def test_dns_resolution_times_out(monkeypatch):
    monkeypatch.setattr(ssrf_protection, "DNS_RESOLVE_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(ssrf_protection, "_resolve_hostname_sync", lambda host, port: time.sleep(1) or [PUBLIC_IP])
    started = time.monotonic()
    assert await ssrf_protection.resolve_hostname("slow.example.com", 443, ssrf_protection.DnsPool.USER_URL) == []
    assert time.monotonic() - started < 0.9


@pytest.mark.anyio
async def test_path_parameters_cannot_change_request_target(public_dns, upstream):
    upstream["handler"] = lambda request: httpx.Response(200, json={}, request=request)
    tool = {
        "name": "pets",
        "method": "GET",
        "url": "https://api.example.com/v1/pets/{petId}",
        "parameters_schema": {"type": "object", "properties": {"petId": {"type": "string"}}},
        "param_locations": {"petId": "path"},
    }
    await execute_http_api_tool(tool, {"petId": "../../admin/users?all=1#x"})
    assert upstream["sent"][0].url.raw_path == b"/v1/pets/..%2F..%2Fadmin%2Fusers%3Fall%3D1%23x"

    result = await execute_http_api_tool(tool, {"petId": ".."})
    assert result["status_code"] == 400
    assert len(upstream["sent"]) == 1


@pytest.mark.anyio
async def test_undeclared_arguments_are_rejected_before_sending(public_dns, upstream):
    upstream["handler"] = lambda request: httpx.Response(200, json={}, request=request)
    tool = {
        "name": "records",
        "method": "POST",
        "url": "https://api.example.com/records",
        "parameters_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
        "param_locations": {"title": "body"},
    }
    result = await execute_http_api_tool(tool, {"title": "t", "assignee": "admin", "_method": "DELETE"})
    assert result["status_code"] == 400
    assert "assignee" in result["error"] and "_method" in result["error"]
    # 沒有宣告 request_body 時，不能以它整包替換本文
    result = await execute_http_api_tool(tool, {"title": "t", "request_body": {"is_admin": True}})
    assert result["status_code"] == 400
    assert upstream["sent"] == []

    await execute_http_api_tool(tool, {"title": "t"})
    assert await upstream["sent"][0].aread() == b'{"title":"t"}'


@pytest.mark.anyio
async def test_request_body_fields_follow_the_declared_body_schema(public_dns, upstream):
    upstream["handler"] = lambda request: httpx.Response(200, json={}, request=request)
    declared_body = {
        "name": "tickets",
        "method": "POST",
        "url": "https://api.example.com/tickets",
        "parameters_schema": {"type": "object", "properties": {"request_body": {"type": "object"}}},
        "request_body_schema": {"type": "object", "properties": {"subject": {"type": "string"}}},
        "param_locations": {"request_body": "body"},
    }
    result = await execute_http_api_tool(declared_body, {"request_body": {"subject": "s", "priority": "urgent"}})
    assert result["status_code"] == 400 and "request_body.priority" in result["error"]
    await execute_http_api_tool(declared_body, {"request_body": {"subject": "s"}})
    # 規格沒有描述本文欄位時，宣告的 request_body 照原樣送出
    opaque = dict(declared_body, request_body_schema=None)
    await execute_http_api_tool(opaque, {"request_body": {"anything": 1}})
    assert [await request.aread() for request in upstream["sent"]] == [b'{"subject":"s"}', b'{"anything":1}']


@pytest.mark.anyio
async def test_fixed_query_parameters_cannot_be_overridden(public_dns, upstream):
    upstream["handler"] = lambda request: httpx.Response(200, json={}, request=request)
    tool = {
        "name": "scoped",
        "method": "GET",
        "url": "https://api.example.com/records?project=public-docs&readonly=true",
        "parameters_schema": {"type": "object", "properties": {
            "q": {"type": "string"}, "project": {"type": "string"}, "tags": {"type": "array"},
        }},
        "param_locations": {"q": "query", "project": "query", "tags": "query"},
        "auth_type": "api_key",
        "auth_config": {"key_name": "key", "key_value": "query-secret-123", "key_in": "query"},
    }
    result = await execute_http_api_tool(tool, {"q": "x", "project": "hr-salaries"})
    assert result["status_code"] == 400 and "project" in result["error"]
    assert upstream["sent"] == []

    await execute_http_api_tool(tool, {"q": "x", "tags": ["a", "b"]})
    assert upstream["sent"][0].url.params.multi_items() == [
        ("project", "public-docs"), ("readonly", "true"), ("q", "x"), ("tags", "a"), ("tags", "b"), ("key", "query-secret-123"),
    ]


@pytest.mark.anyio
async def test_cross_origin_redirect_drops_credentials(public_dns, upstream):
    def handler(request):
        if request.headers["host"] == "api.example.com":
            return httpx.Response(302, headers={"Location": "https://collector.example.net/steal"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    upstream["handler"] = handler
    tool = {
        "name": "redirecting",
        "method": "GET",
        "url": "https://api.example.com/data",
        "headers": {"X-Tenant-Secret": "tenant-secret-value"},
        "auth_type": "api_key",
        "auth_config": {"key_name": "X-API-Key", "key_value": "admin-api-key-value", "key_in": "header"},
    }
    result = await execute_http_api_tool(tool, {})
    assert result["is_success"] is True
    first, second = upstream["sent"]
    assert first.headers["x-api-key"] == "admin-api-key-value"
    assert first.headers["x-tenant-secret"] == "tenant-secret-value"
    assert second.headers["host"] == "collector.example.net"
    assert "x-api-key" not in second.headers
    assert "x-tenant-secret" not in second.headers


@pytest.mark.anyio
async def test_credentials_are_redacted_from_result(public_dns, upstream):
    def echo(request):
        return httpx.Response(
            200,
            json={"echo_url": str(request.url), "echo_auth": request.headers.get("authorization"), "api_key": request.url.params.get("key")},
            request=request,
        )

    upstream["handler"] = echo
    query_tool = {
        "name": "query_key",
        "method": "GET",
        "url": "https://api.example.com/search",
        "parameters_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        "auth_type": "api_key",
        "auth_config": {"key_name": "key", "key_value": "query-secret-123", "key_in": "query"},
    }
    result = await execute_http_api_tool(query_tool, {"q": "cats"})
    assert "query-secret-123" not in str(result)
    assert "key=" in result["url"]
    assert upstream["sent"][0].url.params["key"] == "query-secret-123"

    bearer_tool = {
        "name": "bearer",
        "method": "GET",
        "url": "https://api.example.com/me",
        "auth_type": "bearer",
        "auth_config": {"token": "bearer-secret-456"},
    }
    result = await execute_http_api_tool(bearer_tool, {})
    assert "bearer-secret-456" not in str(result)


@pytest.mark.anyio
async def test_oversized_response_is_not_buffered(public_dns, upstream):
    upstream["handler"] = lambda request: httpx.Response(
        200, content=b"x" * (MAX_API_TOOL_RESPONSE_BYTES + 1), headers={"content-type": "text/plain"}, request=request
    )
    result = await execute_http_api_tool({"name": "big", "method": "GET", "url": "https://api.example.com/big"}, {})
    assert result["is_success"] is False
    assert result["status_code"] == 502
    assert "data" not in result


@pytest.mark.anyio
async def test_mcp_http_response_size_is_bounded(public_dns, upstream, monkeypatch):
    monkeypatch.setattr(mcp_service, "MAX_MCP_HTTP_RESPONSE_BYTES", 1024)
    upstream["handler"] = lambda request: httpx.Response(200, content=b"{" + b" " * 2048 + b"}", request=request)
    with pytest.raises(RuntimeError, match="上限"):
        await McpHttpClient(url="https://mcp.example.com/rpc").list_tools()


@pytest.mark.anyio
async def test_web_fetch_rejection_hides_resolved_address(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", None)
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = [ipaddress.ip_address("10.20.30.40")]
        result = await ResearchToolRegistry().web_fetch("https://internal-alias.example.com/")
    assert "SSRF" in result["error"]
    assert "10.20.30.40" not in str(result)


def test_mcp_presets_are_constrained():
    presets = {preset["name"]: preset for preset in McpManager.get_preset_servers()}
    assert "mcp_fetch" not in presets
    filesystem_args = presets["mcp_filesystem"]["args"]
    package = next(arg for arg in filesystem_args if "server-filesystem" in arg)
    assert package.rsplit("@", 1)[1][0].isdigit()
    root = os.path.realpath(filesystem_args[-1])
    data_dir = os.path.realpath(settings.DATA_DIR)
    assert os.path.isabs(filesystem_args[-1])
    assert not root.startswith(data_dir + os.sep) and root != data_dir
    assert not data_dir.startswith(root + os.sep)



class UnreadStream(httpx.AsyncByteStream):
    """記錄本文是否被讀取的串流"""

    def __init__(self):
        self.read = False

    async def __aiter__(self):
        self.read = True
        yield b"x" * 1024

    async def aclose(self):
        pass


@pytest.mark.anyio
async def test_redirect_bodies_are_never_read(public_dns, upstream):
    redirect_bodies = []

    def handler(request):
        if request.url.path == "/start":
            body = UnreadStream()
            redirect_bodies.append(body)
            return httpx.Response(302, headers={"Location": "/final"}, stream=body, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    upstream["handler"] = handler
    result = await execute_http_api_tool({"name": "hop", "method": "GET", "url": "https://api.example.com/start"}, {})
    assert result["is_success"] is True
    assert result["url"] == "https://api.example.com/final"
    assert len(redirect_bodies) == 1 and redirect_bodies[0].read is False


@pytest.mark.anyio
async def test_mcp_http_refuses_cross_origin_redirects(public_dns, upstream):
    def handler(request):
        if request.headers["host"] == "mcp.example.com":
            return httpx.Response(307, headers={"Location": "https://collector.example.net/rpc"}, request=request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}}, request=request)

    upstream["handler"] = handler
    server = {"transport_type": "http", "url": "https://mcp.example.com/rpc", "headers": {"X-API-Key": "mcp-secret"}, "timeout": 5}
    result = await McpManager.execute_mcp_tool(server, "lookup", {"query": "使用者資料"})
    assert result["is_success"] is False
    assert [request.headers["host"] for request in upstream["sent"]] == ["mcp.example.com"]


@pytest.mark.anyio
async def test_mcp_failures_return_only_an_error_code(public_dns, upstream):
    upstream["handler"] = lambda request: httpx.Response(
        200, json={"jsonrpc": "2.0", "id": 1, "error": {"message": "postgresql://admin:pw@10.0.0.5/db"}}, request=request
    )
    server = {"transport_type": "http", "url": "https://mcp.example.com/rpc", "timeout": 5}
    result = await McpManager.execute_mcp_tool(server, "lookup", {})
    assert result["is_success"] is False
    assert result["error_id"] in result["error"]
    assert "postgresql" not in str(result) and "10.0.0.5" not in str(result)


@pytest.mark.anyio
async def test_fixed_query_values_are_not_returned(public_dns, upstream):
    upstream["handler"] = lambda request: httpx.Response(200, json={}, request=request)
    tool = {"name": "weather", "method": "GET", "url": "https://api.example.com/weather?appid=url-embedded-secret&units=metric"}
    result = await execute_http_api_tool(tool, {})
    assert upstream["sent"][0].url.params["appid"] == "url-embedded-secret"
    assert "url-embedded-secret" not in str(result)


@pytest.mark.anyio
async def test_tool_call_has_a_total_deadline(public_dns, monkeypatch):
    async def slow_send(self, request):
        await asyncio.sleep(5)
        return httpx.Response(200, json={}, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", slow_send)
    started = time.monotonic()
    result = await execute_http_api_tool({"name": "slow", "method": "GET", "url": "https://api.example.com/slow", "timeout": 1}, {})
    assert result["status_code"] == 504
    assert time.monotonic() - started < 3


STDIO_SERVER = r"""
import json, os, sys
sys.stderr.write("x" * 200000); sys.stderr.flush()
for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    if request["method"] == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "cwd": os.getcwd(), "files": os.listdir(".")}
    else:
        result = {"tools": [{"name": "big", "description": "y" * 200000, "inputSchema": {"type": "object"}}]}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}) + "\n")
    sys.stdout.flush()
"""


@pytest.mark.anyio
async def test_stdio_server_runs_in_an_empty_workdir_and_large_output_does_not_hang():
    server = {"transport_type": "stdio", "command": sys.executable, "args": ["-c", STDIO_SERVER], "timeout": 10}
    tools, init_info = await McpManager.discover_server_tools(server)
    assert len(tools[0]["description"]) == 200000
    assert init_info["files"] == []
    assert os.path.realpath(init_info["cwd"]) != os.path.realpath(os.getcwd())
    assert not os.path.exists(init_info["cwd"])


@pytest.mark.anyio
async def test_stdio_slot_wait_is_bounded(monkeypatch):
    monkeypatch.setattr(mcp_service, "_stdio_process_slots", asyncio.Semaphore(0))
    server = {"transport_type": "stdio", "command": sys.executable, "args": ["-c", "pass"], "timeout": 0.2}
    with pytest.raises(TimeoutError, match="上限"):
        await McpManager.discover_server_tools(server)


@pytest.mark.anyio
async def test_user_urls_and_configured_endpoints_use_separate_dns_pools(monkeypatch, upstream):
    executors = ssrf_protection._dns_executors
    assert executors[ssrf_protection.DnsPool.USER_URL] is not executors[ssrf_protection.DnsPool.CONFIGURED_ENDPOINT]
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", None)
    upstream["handler"] = lambda request: httpx.Response(200, text="<p>ok</p>", request=request)
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = [PUBLIC_IP]
        await ResearchToolRegistry().web_fetch("https://news.example.com/a")
        assert {call.args[2] for call in mock_dns.call_args_list} == {ssrf_protection.DnsPool.USER_URL}
        mock_dns.reset_mock()
        await execute_http_api_tool({"name": "t", "method": "GET", "url": "https://api.example.com/x"}, {})
        assert {call.args[2] for call in mock_dns.call_args_list} == {ssrf_protection.DnsPool.CONFIGURED_ENDPOINT}


def test_mcp_tools_with_unsafe_names_are_dropped():
    tools = [{"name": "read_file"}, {"name": "../../documents/rebuild-index?"}, {"name": ""}, {"description": "no name"}, {"name": "a" * 129}]
    assert [tool["name"] for tool in mcp_service._usable_tools(tools)] == ["read_file"]
