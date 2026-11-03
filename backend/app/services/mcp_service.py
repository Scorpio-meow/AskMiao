import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx
from app import __version__
from app.core.error_response import format_client_error, log_and_get_error_id
from app.core.ssrf_protection import DnsPool, SSRFSafeTransport, same_origin, send_following_redirects
from app.services.mcp_tools import (
    McpToolDefinitionError,
    encode_header_value,
    function_parameters,
    header_parameters,
    param_headers,
    prompt_messages,
    resource_contents,
    tool_result,
)
from app.services.openapi_parser import fit_tool_name
logger = logging.getLogger(__name__)
MCP_PROTOCOL_VERSION = "2026-07-28"
MCP_LEGACY_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
MCP_LEGACY_PROTOCOL_VERSION = MCP_LEGACY_PROTOCOL_VERSIONS[0]
MCP_META_PREFIX = "io.modelcontextprotocol/"
MCP_CLIENT_INFO = {"name": "AskMiao-MCP-Client", "version": __version__}
HEADER_MISMATCH_ERROR = -32020
MISSING_CLIENT_CAPABILITY_ERROR = -32021
UNSUPPORTED_PROTOCOL_VERSION_ERROR = -32022
METHOD_NOT_FOUND_ERROR = -32601
MODERN_NEGOTIATION_ERRORS = (HEADER_MISMATCH_ERROR, MISSING_CLIENT_CAPABILITY_ERROR, UNSUPPORTED_PROTOCOL_VERSION_ERROR)
MODERN_HTTP_ERRORS = MODERN_NEGOTIATION_ERRORS + (METHOD_NOT_FOUND_ERROR,)
MCP_NAME_PARAMS = {"tools/call": "name", "resources/read": "uri", "prompts/get": "name"}
MCP_DISCOVER_PROBE_TIMEOUT_SECONDS = 5.0
MCP_TIME_TOOLS_CACHE_TTL_MS = 3_600_000
MAX_MCP_ERROR_BODY_BYTES = 64 * 1024
MAX_MCP_TOOL_PAGES = 50
MAX_MCP_CATALOG_ITEMS = 200
MAX_MCP_URI_CHARS = 2048
MAX_MCP_CATALOG_DESCRIPTION_CHARS = 500
MCP_HTTP_ACCEPT = "application/json, text/event-stream"
LEGACY_SSE_FALLBACK_STATUS = (400, 404, 405)
AUTH_FAILURE_STATUS = (401, 403)
# 同時存在的 stdio MCP 子行程數上限（每次探索或工具呼叫都會啟動一個）；等待空位的時間不超過該伺服器的逾時設定
MAX_CONCURRENT_STDIO_PROCESSES = 4
_stdio_process_slots = asyncio.Semaphore(MAX_CONCURRENT_STDIO_PROCESSES)
# HTTP/SSE MCP 伺服器的單次回應上限：對端不受信任，超過即中止讀取
MAX_MCP_HTTP_RESPONSE_BYTES = 4 * 1024 * 1024
# stdio 的單行 JSON-RPC 訊息上限（asyncio 預設 64 KiB，較大的工具結果會讀取失敗），與 HTTP 回應上限一致
MAX_MCP_STDIO_LINE_BYTES = MAX_MCP_HTTP_RESPONSE_BYTES
# stdio 子行程的 stderr 持續讀出，只保留最後這麼多位元組供日誌診斷
MCP_STDERR_TAIL_BYTES = 2048
# HTTP MCP 伺服器的轉址次數上限；只跟隨同一來源的轉址
MAX_MCP_HTTP_REDIRECTS = 5
# MCP 規格建議的工具名稱字元；名稱會出現在 API 路徑與函式名稱中，其他名稱的工具一律略過
MCP_TOOL_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,128}")
def mcp_function_name(server_name: str, tool_name: str) -> str:
    clean_server = re.sub(r'[^a-zA-Z0-9_]', '_', server_name).lower()
    clean_tool = re.sub(r'[^a-zA-Z0-9_]', '_', tool_name).lower()
    return fit_tool_name(f"mcp_{clean_server}_{clean_tool}")


class McpRpcError(RuntimeError):
    def __init__(self, error: Any):
        super().__init__(f"MCP JSON-RPC 錯誤: {error}")
        self.code = error.get("code") if isinstance(error, dict) else None
        self.data = error.get("data") if isinstance(error, dict) else None


class McpInputRequiredError(RuntimeError):
    pass


class McpLegacyServerError(RuntimeError):
    pass


class McpHttpStatusError(RuntimeError):
    def __init__(self, status_code: int, rpc_error: Optional[Dict[str, Any]] = None, www_authenticate: str = ""):
        super().__init__(f"HTTP MCP 伺服器返回狀態碼 {status_code}")
        self.status_code = status_code
        self.rpc_error = rpc_error
        self.www_authenticate = www_authenticate


class McpInsufficientScopeError(RuntimeError):
    def __init__(self, scopes: List[str]):
        super().__init__(f"MCP 伺服器要求額外的 OAuth scope: {' '.join(scopes)}")
        self.scopes = scopes


def _is_response_to(message: Any, req_id: int) -> bool:
    return isinstance(message, dict) and message.get("id") == req_id and "method" not in message


def _rpc_result(message: Dict[str, Any]) -> Dict[str, Any]:
    if "error" in message:
        raise McpRpcError(message["error"])
    result = message.get("result", {})
    if not isinstance(result, dict):
        raise RuntimeError("MCP 伺服器回應的 result 不是物件")
    result_type = result.get("resultType", "complete")
    if result_type == "input_required":
        raise McpInputRequiredError("MCP 伺服器要求額外輸入（elicitation、sampling 或 roots），AskMiao 不提供這類互動")
    if result_type != "complete":
        raise RuntimeError(f"MCP 伺服器回應的 resultType 無法辨識: {result_type!r}")
    return result


def _modern_params(params: Dict[str, Any], version: str) -> Dict[str, Any]:
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    return {
        **params,
        "_meta": {
            **meta,
            f"{MCP_META_PREFIX}protocolVersion": version,
            f"{MCP_META_PREFIX}clientInfo": MCP_CLIENT_INFO,
            f"{MCP_META_PREFIX}clientCapabilities": {},
        },
    }


def _select_version(supported: Any) -> Optional[str]:
    if not isinstance(supported, list):
        return None
    if MCP_PROTOCOL_VERSION in supported:
        return MCP_PROTOCOL_VERSION
    return next((version for version in MCP_LEGACY_PROTOCOL_VERSIONS if version in supported), None)


def _incompatible_versions(supported: Any) -> RuntimeError:
    return RuntimeError(f"MCP 伺服器支援的協定版本 {supported!r} 都與 AskMiao 不相容")


def _discover_info(result: Dict[str, Any], version: str) -> Dict[str, Any]:
    meta = result.get("_meta") if isinstance(result.get("_meta"), dict) else {}
    server_info = meta.get(f"{MCP_META_PREFIX}serverInfo")
    return {
        "protocolVersion": version,
        "capabilities": result.get("capabilities") if isinstance(result.get("capabilities"), dict) else {},
        "serverInfo": server_info if isinstance(server_info, dict) else {},
        "supportedVersions": result.get("supportedVersions") if isinstance(result.get("supportedVersions"), list) else [],
    }


async def _list_all(request, method: str, key: str) -> List[Any]:
    items: List[Any] = []
    params: Dict[str, Any] = {}
    for _ in range(MAX_MCP_TOOL_PAGES):
        result = await request(method, params)
        page = result.get(key, [])
        if isinstance(page, list):
            items.extend(page)
        cursor = result.get("nextCursor")
        if not cursor:
            return items
        params = {"cursor": cursor}
    raise RuntimeError(f"MCP 清單 {method} 超過 {MAX_MCP_TOOL_PAGES} 頁")


def _text(value: Any, limit: int) -> Optional[str]:
    return value[:limit] if isinstance(value, str) else None


def _usable_resources(items: List[Any]) -> List[Dict[str, Any]]:
    resources = []
    for item in items[:MAX_MCP_CATALOG_ITEMS]:
        if isinstance(item, dict) and isinstance(item.get("uri"), str) and len(item["uri"]) <= MAX_MCP_URI_CHARS:
            resources.append({
                "uri": item["uri"],
                "name": _text(item.get("name"), 200) or item["uri"],
                "description": _text(item.get("description"), MAX_MCP_CATALOG_DESCRIPTION_CHARS),
                "mimeType": _text(item.get("mimeType"), 100),
            })
    return resources


def _usable_prompts(items: List[Any]) -> List[Dict[str, Any]]:
    prompts = []
    for item in items[:MAX_MCP_CATALOG_ITEMS]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not MCP_TOOL_NAME_PATTERN.fullmatch(item["name"]):
            continue
        arguments = [
            {
                "name": arg["name"],
                "description": _text(arg.get("description"), MAX_MCP_CATALOG_DESCRIPTION_CHARS),
                "required": bool(arg.get("required")),
            }
            for arg in item.get("arguments") or []
            if isinstance(arg, dict) and isinstance(arg.get("name"), str) and MCP_TOOL_NAME_PATTERN.fullmatch(arg["name"])
        ]
        prompts.append({
            "name": item["name"],
            "description": _text(item.get("description"), MAX_MCP_CATALOG_DESCRIPTION_CHARS),
            "arguments": arguments,
        })
    return prompts


def _sse_events(buffer: bytes) -> Tuple[List[Tuple[str, str]], bytes]:
    events = []
    normalized = buffer.replace(b"\r\n", b"\n")
    *raw_events, rest = normalized.split(b"\n\n")
    for raw in raw_events:
        name = "message"
        data_lines = []
        for line in raw.decode("utf-8", errors="replace").split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                value = line[5:]
                data_lines.append(value[1:] if value.startswith(" ") else value)
        if data_lines:
            events.append((name, "\n".join(data_lines)))
    return events, rest


def _sse_messages(buffer: bytes) -> Tuple[List[Any], bytes]:
    events, rest = _sse_events(buffer)
    messages = []
    for name, data in events:
        if name != "message":
            continue
        try:
            messages.append(json.loads(data))
        except json.JSONDecodeError:
            logger.debug("略過無法解析的 MCP SSE 事件")
    return messages, rest


def _usable_tools(tools: List[Dict[str, Any]], transport_type: str) -> List[Dict[str, Any]]:
    usable = []
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if not isinstance(name, str) or not MCP_TOOL_NAME_PATTERN.fullmatch(name):
            logger.warning("略過名稱不合規則的 MCP 工具: %r", name)
            continue
        try:
            function_parameters(tool.get("inputSchema"))
            if transport_type != "stdio":
                header_parameters(tool.get("inputSchema"))
        except McpToolDefinitionError as e:
            logger.warning("略過定義不合規則的 MCP 工具 %s: %s", name, e)
            continue
        usable.append(tool)
    return usable


def _tool_input_schema(tools: Any, name: str) -> Any:
    for tool in tools if isinstance(tools, list) else []:
        if isinstance(tool, dict) and tool.get("name") == name:
            return tool.get("inputSchema")
    return None


async def _error_body(resp: httpx.Response) -> Optional[Dict[str, Any]]:
    data = b""
    async for chunk in resp.aiter_bytes():
        data += chunk
        if len(data) > MAX_MCP_ERROR_BODY_BYTES:
            return None
    try:
        message = json.loads(data)
    except ValueError:
        return None
    error = message.get("error") if isinstance(message, dict) else None
    return error if isinstance(error, dict) else None
# 檔案系統範本的專屬根目錄：與 DATA_DIR（含 Whoosh 以 pickle 載入的 BM25 索引）完全分開
MCP_FILESYSTEM_SANDBOX_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "mcp_filesystem_sandbox",
)
# 範本中的登錄庫套件一律釘選確切版本，避免每次執行時解析到管理員未審閱的新版
MCP_FILESYSTEM_PACKAGE = "@modelcontextprotocol/server-filesystem@2026.8.31"
# stdio 子行程只繼承執行所需的系統變數（與 MCP 官方 SDK 的預設清單相同），
# 後端的 JWT 金鑰、資料庫連線與模型 API 金鑰不會外流給第三方 MCP 伺服器；
# 伺服器需要的其他變數要寫在該伺服器的 env_vars
INHERITED_ENV_VARS = (
    (
        "APPDATA",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "USERNAME",
        "USERPROFILE",
    )
    if sys.platform == "win32"
    else ("HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
)
def build_stdio_env(env_vars: Dict[str, str]) -> Dict[str, str]:
    """組出 stdio 子行程的環境變數：系統必要變數加上伺服器設定的 env_vars"""
    env: Dict[str, str] = {}
    for key in INHERITED_ENV_VARS:
        value = os.environ.get(key)
        # 以 "()" 開頭的是 shell 匯出的函式定義，不交給子行程
        if value is None or value.startswith("()"):
            continue
        env[key] = value
    env.update(env_vars)
    return env
async def kill_process_tree(process: asyncio.subprocess.Process) -> None:
    if sys.platform == "win32":
        # taskkill /T 會終止整棵子行程樹
        killer = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(process.pid), "/T", "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(killer.wait(), timeout=5.0)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            await asyncio.wait_for(process.wait(), timeout=3.0)
        except (ProcessLookupError, asyncio.TimeoutError):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


PROCESS_GROUP_KWARGS: Dict[str, Any] = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {"start_new_session": True}
)


class McpSession:
    protocol_version: Optional[str] = None
    modern = False

    async def _send_rpc_request(
        self, method: str, params: Dict[str, Any], extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        raise NotImplementedError

    async def request(
        self, method: str, params: Optional[Dict[str, Any]] = None, extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        body = dict(params or {})
        if self.modern:
            body = _modern_params(body, self.protocol_version)
        return await self._send_rpc_request(method, body, extra_headers)

    async def list_tools(self) -> List[Dict[str, Any]]:
        return await _list_all(self.request, "tools/list", "tools")

    async def call_tool(self, name: str, arguments: Dict[str, Any], input_schema: Any = None) -> Dict[str, Any]:
        return await self.request("tools/call", {"name": name, "arguments": arguments or {}})

    def _use_modern(self, version: str) -> None:
        self.modern = True
        self.protocol_version = version

    def _use_legacy(self, result: Dict[str, Any], requested: str) -> Dict[str, Any]:
        self.modern = False
        negotiated = result.get("protocolVersion")
        self.protocol_version = negotiated if isinstance(negotiated, str) else requested
        return result


class McpStdioClient(McpSession):
    """
    基於 Stdio (標準輸入/輸出子進程) 的 MCP 用戶端通訊器
    透過 JSON-RPC 2.0 協議與本地 MCP 伺服器交握並調用工具
    """
    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ):
        self.command = command
        self.args = args or []
        self.env_vars = env_vars or {}
        self.timeout = timeout
        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._holds_slot = False
        self._workdir: Optional[tempfile.TemporaryDirectory] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._stderr_tail = bytearray()
    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id
    async def start(self):
        """啟動子進程（自成一個程序群組，關閉時可連同 npx／uvx 啟動的孫行程一起終止）。

        工作目錄是每次新建的空暫存目錄：後端目錄下的 .env、keys/ 不在子行程的相對路徑範圍內，
        會自動載入工作目錄 .env 的套件也讀不到後端設定。子行程仍以後端的系統帳號執行，
        能讀取該帳號可讀的檔案，第三方 MCP 伺服器應只在受信任時啟用。
        錯誤訊息只帶指令名稱，參數（可能含連線字串等秘密）不寫入訊息"""
        env = build_stdio_env(self.env_vars)
        full_cmd = [self.command] + self.args
        try:
            await asyncio.wait_for(_stdio_process_slots.acquire(), timeout=self.timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"同時執行的 MCP 子行程已達上限 ({MAX_CONCURRENT_STDIO_PROCESSES})，請稍後再試")
        self._holds_slot = True
        self._workdir = tempfile.TemporaryDirectory(prefix="askmiao-mcp-")
        try:
            self.process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self._workdir.name,
                limit=MAX_MCP_STDIO_LINE_BYTES,
                **PROCESS_GROUP_KWARGS
            )
        except Exception as e:
            self._release_slot()
            self._remove_workdir()
            raise RuntimeError(f"無法啟動 MCP 子行程 ({self.command}): {e.__class__.__name__}")
        self._stderr_task = asyncio.create_task(self._drain_stderr(self.process.stderr))
    async def _drain_stderr(self, stream: asyncio.StreamReader):
        """持續讀取 stderr，只保留最後一段：不讀取時子行程寫滿管線就會卡住直到逾時"""
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                return
            self._stderr_tail.extend(chunk)
            del self._stderr_tail[:-MCP_STDERR_TAIL_BYTES]
    def _release_slot(self):
        if self._holds_slot:
            self._holds_slot = False
            _stdio_process_slots.release()
    def _remove_workdir(self):
        if self._workdir is not None:
            self._workdir.cleanup()
            self._workdir = None
    async def close(self):
        """關閉子進程：先關閉管線，再終止整個程序群組（含孫行程）"""
        process = self.process
        self.process = None
        if process is None:
            self._release_slot()
            return
        try:
            if process.stdin and not process.stdin.is_closing():
                process.stdin.close()
            if process.returncode is None:
                await kill_process_tree(process)
            try:
                await asyncio.wait_for(process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                process.kill()
        except Exception as e:
            logger.warning(f"關閉 MCP 子行程時發生錯誤: {e}")
            try:
                process.kill()
            except Exception:
                pass
        finally:
            if self._stderr_task is not None and not self._stderr_task.done():
                self._stderr_task.cancel()
            self._release_slot()
            self._remove_workdir()
    async def _write(self, message: Dict[str, Any]) -> None:
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError("MCP 子行程尚未啟動或通訊管線已中斷")
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.process.stdin.drain()
    async def _send_rpc_request(
        self, method: str, params: Dict[str, Any], extra_headers: Optional[Dict[str, str]] = None, timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """發送單次 JSON-RPC 2.0 請求並讀取回應"""
        limit = timeout or self.timeout
        req_id = self._next_id()
        await self._write({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        start_t = time.time()
        while True:
            if time.time() - start_t > limit:
                raise TimeoutError(f"等待 MCP 伺服器回應逾時 ({limit}s)")
            try:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=limit)
            except asyncio.TimeoutError:
                raise TimeoutError(f"讀取 MCP 伺服器輸出逾時")
            if not line_bytes:
                # 子行程結束時讓 stderr 讀完；內容只寫入伺服器日誌，不回傳給使用者
                if self._stderr_task is not None:
                    try:
                        await asyncio.wait_for(asyncio.shield(self._stderr_task), timeout=0.5)
                    except Exception:
                        pass
                raise RuntimeError(f"MCP 伺服器已異常結束: {bytes(self._stderr_tail).decode('utf-8', errors='ignore')}")
            line_str = line_bytes.decode("utf-8", errors="ignore").strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                if _is_response_to(data, req_id):
                    return _rpc_result(data)
            except json.JSONDecodeError:

                logger.debug(f"[MCP Stdio Log] {line_str}")
                continue
    async def connect(self, hint: Optional[str]) -> Dict[str, Any]:
        if hint in MCP_LEGACY_PROTOCOL_VERSIONS:
            try:
                return await self.initialize(hint)
            except McpRpcError:
                pass
        return await self._negotiate()
    async def _negotiate(self) -> Dict[str, Any]:
        try:
            result = await self._send_rpc_request(
                "server/discover",
                _modern_params({}, MCP_PROTOCOL_VERSION),
                timeout=min(self.timeout, MCP_DISCOVER_PROBE_TIMEOUT_SECONDS),
            )
        except McpRpcError as e:
            if e.code == UNSUPPORTED_PROTOCOL_VERSION_ERROR:
                supported = e.data.get("supported") if isinstance(e.data, dict) else None
                version = _select_version(supported)
                if version is None or version == MCP_PROTOCOL_VERSION:
                    raise _incompatible_versions(supported)
                return await self.initialize(version)
            if e.code in MODERN_NEGOTIATION_ERRORS:
                raise
            return await self.initialize(MCP_LEGACY_PROTOCOL_VERSION)
        except (TimeoutError, McpInputRequiredError):
            return await self.initialize(MCP_LEGACY_PROTOCOL_VERSION)
        if not isinstance(result.get("supportedVersions"), list):
            return await self.initialize(MCP_LEGACY_PROTOCOL_VERSION)
        version = _select_version(result.get("supportedVersions"))
        if version is None:
            raise _incompatible_versions(result.get("supportedVersions"))
        if version != MCP_PROTOCOL_VERSION:
            return await self.initialize(version)
        self._use_modern(version)
        return _discover_info(result, version)
    async def initialize(self, version: str) -> Dict[str, Any]:
        """執行 MCP Initialize 交握（2025-11-25 以前的協定版本）"""
        result = await self._send_rpc_request(
            "initialize",
            {"protocolVersion": version, "capabilities": {}, "clientInfo": MCP_CLIENT_INFO},
        )
        await self._write({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self._use_legacy(result, version)
class McpHttpClient(McpSession):
    """
    基於 Streamable HTTP 的 MCP 用戶端通訊器
    """
    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self._request_id = 0
        self._session_id: Optional[str] = None
    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id
    def _request_headers(self, payload: Dict[str, Any], extra_headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        headers = {**self.headers, "Accept": MCP_HTTP_ACCEPT}
        if self.modern:
            headers["MCP-Protocol-Version"] = self.protocol_version
            headers["Mcp-Method"] = payload["method"]
            name_key = MCP_NAME_PARAMS.get(payload["method"])
            name = payload.get("params", {}).get(name_key) if name_key else None
            if isinstance(name, str):
                headers["Mcp-Name"] = encode_header_value(name)
            headers.update(extra_headers or {})
            return headers
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers
    async def _send_rpc_request(
        self, method: str, params: Dict[str, Any], extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        if self.modern:
            return await self._send_once(method, params, extra_headers)
        try:
            return await self._send_once(method, params, extra_headers)
        except McpHttpStatusError as e:
            if e.status_code != 404 or not self._session_id or method == "initialize":
                raise
        self._session_id = None
        await self.initialize(self.protocol_version)
        return await self._send_once(method, params, extra_headers)
    async def _send_once(self, method: str, params: Dict[str, Any], extra_headers: Optional[Dict[str, str]]) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}
        try:
            # httpx 的逾時是逐次讀寫計算；整個請求（含轉址與慢速逐段回應）另以伺服器的逾時設定為總時限
            return await asyncio.wait_for(self._post(payload, extra_headers), timeout=self.timeout)
        except McpHttpStatusError as e:
            if not self.modern or e.status_code not in LEGACY_SSE_FALLBACK_STATUS:
                raise
            if e.rpc_error is not None and e.rpc_error.get("code") in MODERN_HTTP_ERRORS:
                raise McpRpcError(e.rpc_error) from e
            raise McpLegacyServerError(str(e)) from e
    async def close(self) -> None:
        if not self._session_id:
            return
        headers = self._request_headers({}, None)
        self._session_id = None
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                transport=SSRFSafeTransport(DnsPool.CONFIGURED_ENDPOINT),
            ) as client:
                await asyncio.wait_for(client.delete(self.url, headers=headers), timeout=self.timeout)
        except Exception as e:
            logger.debug("關閉 MCP session 失敗: %s", e)
    async def _send_notification(self, method: str) -> None:
        await asyncio.wait_for(self._post({"jsonrpc": "2.0", "method": method}, None), timeout=self.timeout)
    async def _post(self, payload: Dict[str, Any], extra_headers: Optional[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        # 與自訂 API 工具相同：第一跳與每次轉址都要通過 SSRF 檢查，並固定連線到核可的 IP。
        # 只跟隨同一來源的轉址：307／308 會把管理員設定的標頭與 JSON-RPC 本文（含使用者資料）原樣送往轉址目標；
        # 轉址回應的本文不讀取，最終回應才套用大小上限
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=False,
            transport=SSRFSafeTransport(DnsPool.CONFIGURED_ENDPOINT),
        ) as client:
            request = client.build_request("POST", self.url, headers=self._request_headers(payload, extra_headers), json=payload)
            resp = await send_following_redirects(client, request, MAX_MCP_HTTP_REDIRECTS, allow_cross_origin=False)
            try:
                if "id" not in payload:
                    if resp.status_code not in (200, 202):
                        raise McpHttpStatusError(resp.status_code)
                    return None
                if resp.status_code != 200:
                    raise McpHttpStatusError(
                        resp.status_code,
                        rpc_error=await _error_body(resp),
                        www_authenticate=resp.headers.get("www-authenticate", ""),
                    )
                session_id = resp.headers.get("mcp-session-id")
                if session_id and not self.modern:
                    self._session_id = session_id
                content_length = resp.headers.get("content-length")
                if content_length and content_length.isdigit() and int(content_length) > MAX_MCP_HTTP_RESPONSE_BYTES:
                    raise RuntimeError(f"HTTP MCP 伺服器回應超過 {MAX_MCP_HTTP_RESPONSE_BYTES} 位元組上限")
                is_sse = resp.headers.get("content-type", "").split(";")[0].strip().lower() == "text/event-stream"
                chunks = []
                buffer = b""
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_MCP_HTTP_RESPONSE_BYTES:
                        raise RuntimeError(f"HTTP MCP 伺服器回應超過 {MAX_MCP_HTTP_RESPONSE_BYTES} 位元組上限")
                    if not is_sse:
                        chunks.append(chunk)
                        continue
                    messages, buffer = _sse_messages(buffer + chunk)
                    for message in messages:
                        if _is_response_to(message, payload["id"]):
                            return _rpc_result(message)
            finally:
                await resp.aclose()
            if is_sse:
                messages, _ = _sse_messages(buffer + b"\n\n")
                for message in messages:
                    if _is_response_to(message, payload["id"]):
                        return _rpc_result(message)
                raise RuntimeError("HTTP MCP 伺服器的 SSE 串流結束前沒有回應")
            data = json.loads(b"".join(chunks))
            if not _is_response_to(data, payload["id"]):
                raise RuntimeError("HTTP MCP 伺服器的回應與請求不符")
            return _rpc_result(data)
    async def connect(self, hint: Optional[str]) -> Dict[str, Any]:
        if hint == MCP_PROTOCOL_VERSION:
            self._use_modern(hint)
            return {"protocolVersion": hint, "capabilities": {}, "serverInfo": {}}
        if hint in MCP_LEGACY_PROTOCOL_VERSIONS:
            try:
                return await self.initialize(hint)
            except McpRpcError:
                pass
            except McpHttpStatusError as e:
                if e.status_code in AUTH_FAILURE_STATUS:
                    raise
        return await self._negotiate()
    async def _negotiate(self) -> Dict[str, Any]:
        self._use_modern(MCP_PROTOCOL_VERSION)
        try:
            result = await self.request("server/discover")
        except McpRpcError as e:
            self.modern = False
            if e.code == UNSUPPORTED_PROTOCOL_VERSION_ERROR:
                supported = e.data.get("supported") if isinstance(e.data, dict) else None
                version = _select_version(supported)
                if version is None or version == MCP_PROTOCOL_VERSION:
                    raise _incompatible_versions(supported)
                return await self.initialize(version)
            if e.code in MODERN_NEGOTIATION_ERRORS:
                raise
            return await self.initialize(MCP_LEGACY_PROTOCOL_VERSION)
        except McpLegacyServerError:
            self.modern = False
            return await self.initialize(MCP_LEGACY_PROTOCOL_VERSION)
        except McpHttpStatusError as e:
            self.modern = False
            if e.status_code in AUTH_FAILURE_STATUS:
                raise
            return await self.initialize(MCP_LEGACY_PROTOCOL_VERSION)
        except McpInputRequiredError:
            self.modern = False
            return await self.initialize(MCP_LEGACY_PROTOCOL_VERSION)
        if not isinstance(result.get("supportedVersions"), list):
            return await self.initialize(MCP_LEGACY_PROTOCOL_VERSION)
        version = _select_version(result.get("supportedVersions"))
        if version is None:
            raise _incompatible_versions(result.get("supportedVersions"))
        if version != MCP_PROTOCOL_VERSION:
            self.modern = False
            return await self.initialize(version)
        return _discover_info(result, version)
    async def initialize(self, version: str) -> Dict[str, Any]:
        self.modern = False
        self.protocol_version = None
        result = await self._send_rpc_request("initialize", {
            "protocolVersion": version,
            "capabilities": {},
            "clientInfo": MCP_CLIENT_INFO,
        })
        self._use_legacy(result, version)
        try:
            await self._send_notification("notifications/initialized")
        except McpHttpStatusError as e:
            raise RuntimeError(str(e)) from e
        return result
    async def call_tool(self, name: str, arguments: Dict[str, Any], input_schema: Any = None) -> Dict[str, Any]:
        params = {"name": name, "arguments": arguments or {}}
        if not self.modern:
            return await self.request("tools/call", params)
        try:
            return await self.request("tools/call", params, param_headers(header_parameters(input_schema), arguments or {}))
        except McpRpcError as e:
            if e.code != HEADER_MISMATCH_ERROR:
                raise
        refreshed = _tool_input_schema(await self.list_tools(), name)
        return await self.request("tools/call", params, param_headers(header_parameters(refreshed), arguments or {}))
class McpLegacySseClient(McpSession):
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 30.0):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self._request_id = 0
        self._client: Optional[httpx.AsyncClient] = None
        self._stream: Optional[httpx.Response] = None
        self._reader: Optional[asyncio.Task] = None
        self._endpoint: Optional[asyncio.Future] = None
        self._post_url: Optional[httpx.URL] = None
        self._pending: Dict[int, asyncio.Future] = {}
    async def start(self) -> None:
        self._endpoint = asyncio.get_running_loop().create_future()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, read=None),
            follow_redirects=False,
            transport=SSRFSafeTransport(DnsPool.CONFIGURED_ENDPOINT),
        )
        request = self._client.build_request("GET", self.url, headers={**self.headers, "Accept": "text/event-stream"})
        self._stream = await asyncio.wait_for(
            send_following_redirects(self._client, request, MAX_MCP_HTTP_REDIRECTS, allow_cross_origin=False),
            timeout=self.timeout,
        )
        if self._stream.status_code != 200:
            raise McpHttpStatusError(self._stream.status_code)
        self._reader = asyncio.create_task(self._read_stream())
        endpoint = await asyncio.wait_for(asyncio.shield(self._endpoint), timeout=self.timeout)
        target = self._stream.url.join(endpoint)
        if not same_origin(target, self._stream.url):
            raise RuntimeError("MCP SSE 伺服器指定的 endpoint 屬於其他來源，已拒絕")
        self._post_url = target
    async def _read_stream(self) -> None:
        buffer = b""
        total = 0
        try:
            async for chunk in self._stream.aiter_bytes():
                total += len(chunk)
                if total > MAX_MCP_HTTP_RESPONSE_BYTES:
                    raise RuntimeError(f"HTTP MCP 伺服器回應超過 {MAX_MCP_HTTP_RESPONSE_BYTES} 位元組上限")
                events, buffer = _sse_events(buffer + chunk)
                for name, data in events:
                    if name == "endpoint":
                        if not self._endpoint.done():
                            self._endpoint.set_result(data.strip())
                        continue
                    if name != "message":
                        continue
                    try:
                        message = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(message, dict) and "method" not in message:
                        future = self._pending.pop(message.get("id"), None)
                        if future is not None and not future.done():
                            future.set_result(message)
            raise RuntimeError("MCP SSE 串流已結束")
        except Exception as e:
            for future in [self._endpoint, *self._pending.values()]:
                if future is not None and not future.done():
                    future.set_exception(e)
            self._pending.clear()
    async def _post_message(self, payload: Dict[str, Any]) -> None:
        request = self._client.build_request("POST", self._post_url, headers=self.headers, json=payload)
        response = await self._client.send(request, stream=True)
        await response.aclose()
        if response.status_code not in (200, 202):
            raise McpHttpStatusError(response.status_code)
    async def _send_rpc_request(
        self, method: str, params: Dict[str, Any], extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        self._request_id += 1
        req_id = self._request_id
        future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        try:
            payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            await asyncio.wait_for(self._post_message(payload), timeout=self.timeout)
            message = await asyncio.wait_for(future, timeout=self.timeout)
        finally:
            self._pending.pop(req_id, None)
        return _rpc_result(message)
    async def initialize(self, version: str) -> Dict[str, Any]:
        result = await self._send_rpc_request("initialize", {
            "protocolVersion": version,
            "capabilities": {},
            "clientInfo": MCP_CLIENT_INFO,
        })
        await asyncio.wait_for(self._post_message({"jsonrpc": "2.0", "method": "notifications/initialized"}), timeout=self.timeout)
        return self._use_legacy(result, version)
    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except BaseException:
                pass
        if self._endpoint is not None and self._endpoint.done() and not self._endpoint.cancelled():
            self._endpoint.exception()
        if self._stream is not None:
            await self._stream.aclose()
        if self._client is not None:
            await self._client.aclose()


async def open_http_mcp_client(url: str, headers: Dict[str, str], timeout: float, hint: Optional[str]):
    client = McpHttpClient(url=url, headers=headers, timeout=timeout)
    try:
        return client, await client.connect(hint)
    except McpHttpStatusError as e:
        if e.status_code not in LEGACY_SSE_FALLBACK_STATUS:
            raise
    legacy = McpLegacySseClient(url=url, headers=headers, timeout=timeout)
    try:
        await legacy.start()
        return legacy, await legacy.initialize(MCP_LEGACY_PROTOCOL_VERSION)
    except BaseException:
        await legacy.close()
        raise


TIME_SERVER_SCRIPT = """import sys, json, datetime, zoneinfo
META = 'io.modelcontextprotocol/'
SERVER_INFO = {'name': 'mcp-time-server', 'version': '1.1'}
SUPPORTED_VERSIONS = [PROTOCOL_VERSION] + LEGACY_VERSIONS
TOOLS = [{
    'name': 'get_current_time',
    'title': '查詢目前時間',
    'description': '查詢指定時區或城市的當前精確時間',
    'inputSchema': {
        'type': 'object',
        'properties': {
            'timezone': {'type': 'string', 'description': '時區名稱 (例如 Asia/Taipei, UTC, America/New_York)', 'default': 'Asia/Taipei'}
        },
        'additionalProperties': False
    },
    'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}
}]
def send(message):
    sys.stdout.write(json.dumps(message) + '\\n')
    sys.stdout.flush()
def error(mid, code, message, data=None):
    body = {'code': code, 'message': message}
    if data is not None:
        body['data'] = data
    send({'jsonrpc': '2.0', 'id': mid, 'error': body})
def reply(mid, body, modern):
    if modern:
        body = dict(body, resultType='complete', _meta={META + 'serverInfo': SERVER_INFO})
    send({'jsonrpc': '2.0', 'id': mid, 'result': body})
def current_time(tz_name):
    try:
        return datetime.datetime.now(zoneinfo.ZoneInfo(tz_name)).strftime('%Y-%m-%d %H:%M:%S %Z')
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
def handle(mid, method, params):
    version = (params.get('_meta') or {}).get(META + 'protocolVersion')
    modern = version is not None
    if method == 'initialize':
        requested = params.get('protocolVersion')
        negotiated = requested if requested in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
        reply(mid, {'protocolVersion': negotiated, 'capabilities': {'tools': {}}, 'serverInfo': SERVER_INFO}, False)
    elif modern and version != PROTOCOL_VERSION:
        error(mid, -32022, 'Unsupported protocol version', {'supported': SUPPORTED_VERSIONS, 'requested': version})
    elif method == 'server/discover' and modern:
        reply(mid, {'supportedVersions': SUPPORTED_VERSIONS, 'capabilities': {'tools': {}}, 'ttlMs': CACHE_TTL_MS, 'cacheScope': 'public'}, True)
    elif method == 'tools/list':
        body = {'tools': TOOLS, 'ttlMs': CACHE_TTL_MS, 'cacheScope': 'public'} if modern else {'tools': TOOLS}
        reply(mid, body, modern)
    elif method == 'tools/call':
        if params.get('name') != 'get_current_time':
            error(mid, -32602, 'Unknown tool: ' + str(params.get('name')))
            return
        tz_name = (params.get('arguments') or {}).get('timezone', 'Asia/Taipei')
        reply(mid, {'content': [{'type': 'text', 'text': '當前時間: ' + current_time(tz_name)}], 'isError': False}, modern)
    else:
        error(mid, -32601, 'Method not found')
def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
        except ValueError:
            continue
        if isinstance(req, dict) and 'id' in req:
            handle(req['id'], req.get('method'), req.get('params') or {})
if __name__ == '__main__':
    main()
"""


class McpManager:
    """
    MCP 伺服器與工具調度管理器
    """
    _negotiated_versions: Dict[Any, str] = {}
    @classmethod
    def get_preset_servers(cls) -> List[Dict[str, Any]]:
        """常見官方與社群 MCP 伺服器快速範本

        不提供網頁擷取類範本：stdio 子行程的出站連線不受 web_fetch 的 SSRF、
        網域白名單與網址來源防護約束。
        """
        os.makedirs(MCP_FILESYSTEM_SANDBOX_DIR, exist_ok=True)
        script_constants = (
            f"PROTOCOL_VERSION = {MCP_PROTOCOL_VERSION!r}\n"
            f"LEGACY_VERSIONS = {list(MCP_LEGACY_PROTOCOL_VERSIONS)!r}\n"
            f"CACHE_TTL_MS = {MCP_TIME_TOOLS_CACHE_TTL_MS!r}\n"
        )
        return [
            {
                "name": "mcp_time",
                "display_name": "即時時間與時區轉換 (Time)",
                "description": "提供全球各大城市當前精確時間查詢、時區換算與時間差計算工具。",
                "transport_type": "stdio",
                "command": "python",
                "args": ["-c", script_constants + TIME_SERVER_SCRIPT],
                "env_vars": {}
            },
            {
                "name": "mcp_filesystem",
                "display_name": "檔案系統安全讀取 (Filesystem)",
                "description": "提供專屬沙箱目錄下的檔案瀏覽、搜尋與檔案讀取工具（不含後端資料目錄）。",
                "transport_type": "stdio",
                "command": "npx",
                "args": ["-y", MCP_FILESYSTEM_PACKAGE, MCP_FILESYSTEM_SANDBOX_DIR],
                "env_vars": {}
            },
        ]
    @staticmethod
    def _json_value(value: Any, fallback: Any) -> Any:
        if not isinstance(value, str):
            return value if value is not None else fallback
        try:
            return json.loads(value)
        except Exception:
            return fallback
    @classmethod
    async def _http_headers(cls, server_dict: Dict[str, Any], force_refresh: bool = False) -> Dict[str, str]:
        headers = dict(cls._json_value(server_dict.get("headers"), {}) or {})
        if server_dict.get("oauth_authorized") and server_dict.get("id") is not None:
            from app.services import mcp_oauth
            token = await mcp_oauth.access_token(server_dict["id"], force_refresh=force_refresh)
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers
    @classmethod
    async def _open_http(cls, server_dict: Dict[str, Any], hint: Optional[str]):
        url = server_dict.get("url")
        if not url:
            raise ValueError("SSE/HTTP 傳輸模式必須指定 url 連線網址")
        timeout = float(server_dict.get("timeout", 30))
        try:
            return await open_http_mcp_client(url, await cls._http_headers(server_dict), timeout, hint)
        except McpHttpStatusError as e:
            if e.status_code != 401 or not server_dict.get("oauth_authorized"):
                raise
        return await open_http_mcp_client(url, await cls._http_headers(server_dict, force_refresh=True), timeout, hint)
    @classmethod
    async def _connect_and_run(cls, server_dict: Dict[str, Any], action, hint: Optional[str]) -> Any:
        transport_type = server_dict.get("transport_type", "stdio")
        timeout = float(server_dict.get("timeout", 30))
        if transport_type == "stdio":
            cmd = server_dict.get("command")
            if not cmd:
                raise ValueError("Stdio 傳輸模式必須指定 command 執行指令")
            raw_args = cls._json_value(server_dict.get("args"), [server_dict.get("args")]) or []
            raw_env = cls._json_value(server_dict.get("env_vars"), {}) or {}
            client = McpStdioClient(command=cmd, args=raw_args, env_vars=raw_env, timeout=timeout)
            try:
                await client.start()
                init_res = await client.connect(hint)
                cls._remember_version(server_dict, client)
                return await action(client, init_res)
            finally:
                await client.close()
        if transport_type in ("sse", "http"):
            client, init_res = await cls._open_http(server_dict, hint)
            cls._remember_version(server_dict, client)
            try:
                return await action(client, init_res)
            finally:
                await client.close()
        raise ValueError(f"不支援的傳輸模式: {transport_type}")
    @classmethod
    def _remember_version(cls, server_dict: Dict[str, Any], client: McpSession) -> None:
        if server_dict.get("id") is not None and client.protocol_version:
            cls._negotiated_versions[server_dict["id"]] = client.protocol_version
    @classmethod
    async def _run(cls, server_dict: Dict[str, Any], action, use_hint: bool = True) -> Any:
        hint = (cls._negotiated_versions.get(server_dict.get("id")) or server_dict.get("protocol_version")) if use_hint else None
        try:
            return await cls._connect_and_run(server_dict, action, hint)
        except (McpLegacyServerError, McpRpcError) as e:
            stale = isinstance(e, McpLegacyServerError) or e.code == UNSUPPORTED_PROTOCOL_VERSION_ERROR
            if hint is None or not stale:
                raise
        except McpHttpStatusError as e:
            if e.status_code == 403:
                cls._record_scope_challenge(server_dict, e)
            raise
        cls._negotiated_versions.pop(server_dict.get("id"), None)
        return await cls._connect_and_run(server_dict, action, None)
    @staticmethod
    def _record_scope_challenge(server_dict: Dict[str, Any], error: McpHttpStatusError) -> None:
        from app.services import mcp_oauth
        challenge = mcp_oauth.bearer_challenge(error.www_authenticate)
        if challenge.get("error") != "insufficient_scope":
            return
        scopes = challenge.get("scope", "").split()
        if server_dict.get("id") is not None and scopes:
            mcp_oauth.save_scope_challenge(server_dict["id"], scopes)
        raise McpInsufficientScopeError(scopes) from error
    @classmethod
    async def discover_server_tools(cls, server_dict: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
        """
        向指定 MCP 伺服器判斷協定世代（server/discover 或 initialize）並探索工具、resources 與 prompts
        回傳: (tools_list, server_info, {"resources": [...], "prompts": [...]})
        """
        transport_type = server_dict.get("transport_type", "stdio")
        async def discover(client, init_res):
            tools = _usable_tools(await client.list_tools(), transport_type)
            capabilities = init_res.get("capabilities") or {}
            catalog = {"resources": [], "prompts": []}
            for kind, method in (("resources", "resources/list"), ("prompts", "prompts/list")):
                if kind not in capabilities:
                    continue
                try:
                    items = await _list_all(client.request, method, kind)
                except Exception as e:
                    log_and_get_error_id(logger, f"探索 MCP {kind} 失敗", e, logging.WARNING)
                    continue
                catalog[kind] = _usable_resources(items) if kind == "resources" else _usable_prompts(items)
            return tools, {**init_res, "protocolVersion": client.protocol_version}, catalog
        return await cls._run(server_dict, discover, use_hint=False)
    @classmethod
    async def _execute(cls, server_dict: Dict[str, Any], label: str, action, shape) -> Dict[str, Any]:
        start_t = time.time()
        try:
            res = await cls._run(server_dict, lambda client, _init: action(client))
            return {"duration_seconds": round(time.time() - start_t, 3), **shape(res)}
        except Exception as e:
            duration = round(time.time() - start_t, 3)
            # 例外內容（stderr、JSON-RPC 錯誤、SSRF 拒絕原因）只寫入日誌；結果會交給模型、顯示給使用者並存進研究軌跡
            error_id = log_and_get_error_id(logger, f"調用 {label} 失敗", e)
            return {
                "is_success": False,
                "duration_seconds": duration,
                "error": format_client_error(error_id),
                "error_id": error_id
            }
    @classmethod
    async def execute_mcp_tool(cls, server_dict: Dict[str, Any], tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """調用指定 MCP 伺服器之特定工具 (tools/call)"""
        input_schema = _tool_input_schema(cls._json_value(server_dict.get("discovered_tools"), []), tool_name)
        return await cls._execute(
            server_dict,
            f"MCP 工具 {tool_name}",
            lambda client: client.call_tool(tool_name, arguments, input_schema),
            tool_result,
        )
    @classmethod
    async def read_mcp_resource(cls, server_dict: Dict[str, Any], uri: str) -> Dict[str, Any]:
        return await cls._execute(
            server_dict,
            f"MCP resource {uri}",
            lambda client: client.request("resources/read", {"uri": uri}),
            lambda res: {
                "is_success": True,
                "contents": [resource_contents(item) for item in res.get("contents", []) if isinstance(item, dict)],
            },
        )
    @classmethod
    async def get_mcp_prompt(cls, server_dict: Dict[str, Any], name: str, arguments: Dict[str, str]) -> Dict[str, Any]:
        return await cls._execute(
            server_dict,
            f"MCP prompt {name}",
            lambda client: client.request("prompts/get", {"name": name, "arguments": arguments}),
            lambda res: {"is_success": True, "description": res.get("description"), "messages": prompt_messages(res.get("messages"))},
        )
    @classmethod
    def convert_mcp_tool_to_function_def(
        cls,
        server_name: str,
        server_display_name: str,
        mcp_tool: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        將 MCP tool 規格轉換為 OpenAI Function Calling 相容之 Tool Definition；inputSchema 無法轉換時回傳 None
        """
        t_name = mcp_tool.get("name", "")
        try:
            parameters = function_parameters(mcp_tool.get("inputSchema"))
        except McpToolDefinitionError as e:
            logger.warning("略過定義不合規則的 MCP 工具 %s: %s", t_name, e)
            return None
        title = mcp_tool.get("title") if isinstance(mcp_tool.get("title"), str) else t_name
        desc = mcp_tool.get("description") or f"由 MCP 伺服器 [{server_display_name}] 提供的工具: {title}"
        return {
            "type": "function",
            "function": {
                "name": mcp_function_name(server_name, t_name),
                "description": f"[MCP 協定工具]{server_display_name} -> {title}：{desc}",
                "parameters": parameters
            }
        }
