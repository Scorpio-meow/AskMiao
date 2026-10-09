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
from app.core.ssrf_protection import DnsPool, SSRFSafeTransport, send_following_redirects
logger = logging.getLogger(__name__)
MCP_PROTOCOL_VERSION = "2024-11-05"
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
def _usable_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    usable = []
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if isinstance(name, str) and MCP_TOOL_NAME_PATTERN.fullmatch(name):
            usable.append(tool)
        else:
            logger.warning("略過名稱不合規則的 MCP 工具: %r", name)
    return usable
# 檔案系統範本的專屬根目錄：與 DATA_DIR（含以 pickle 載入的索引中繼資料）完全分開
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
class McpStdioClient:
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
        group_kwargs: Dict[str, Any] = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if sys.platform == "win32"
            else {"start_new_session": True}
        )
        try:
            self.process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self._workdir.name,
                limit=MAX_MCP_STDIO_LINE_BYTES,
                **group_kwargs
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
    async def _kill_process_tree(self, process: asyncio.subprocess.Process):
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
                await self._kill_process_tree(process)
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
    async def _send_rpc_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """發送單次 JSON-RPC 2.0 請求並讀取回應"""
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError("MCP 子行程尚未啟動或通訊管線已中斷")
        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {}
        }
        msg_line = json.dumps(payload, ensure_ascii=False) + "\n"
        self.process.stdin.write(msg_line.encode("utf-8"))
        await self.process.stdin.drain()
        start_t = time.time()
        while True:
            if time.time() - start_t > self.timeout:
                raise TimeoutError(f"等待 MCP 伺服器回應逾時 ({self.timeout}s)")
            try:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=self.timeout)
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
                if isinstance(data, dict) and data.get("id") == req_id:
                    if "error" in data:
                        raise RuntimeError(f"MCP JSON-RPC 錯誤: {data['error']}")
                    return data.get("result", {})
            except json.JSONDecodeError:
 
                logger.debug(f"[MCP Stdio Log] {line_str}")
                continue
    async def initialize(self) -> Dict[str, Any]:
        """執行 MCP Initialize 交握"""
        result = await self._send_rpc_request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "AskMiao-MCP-Client",
                    "version": __version__
                }
            }
        )
        if self.process and self.process.stdin:
            notif = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            self.process.stdin.write((json.dumps(notif) + "\n").encode("utf-8"))
            await self.process.stdin.drain()
        return result
    async def list_tools(self) -> List[Dict[str, Any]]:
        """向 MCP 伺服器查詢所有可用工具"""
        result = await self._send_rpc_request("tools/list", {})
        return _usable_tools(result.get("tools", []))
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """向 MCP 伺服器發送 tools/call 工具執行請求"""
        result = await self._send_rpc_request("tools/call", {
            "name": name,
            "arguments": arguments or {}
        })
        return result
class McpHttpClient:
    """
    基於 HTTP / SSE 網路連線的 MCP 用戶端通訊器
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
    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id
    async def _send_rpc_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {}
        }
        # httpx 的逾時是逐次讀寫計算；整個請求（含轉址與慢速逐段回應）另以伺服器的逾時設定為總時限
        return await asyncio.wait_for(self._post(payload), timeout=self.timeout)
    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 與自訂 API 工具相同：第一跳與每次轉址都要通過 SSRF 檢查，並固定連線到核可的 IP。
        # 只跟隨同一來源的轉址：307／308 會把管理員設定的標頭與 JSON-RPC 本文（含使用者資料）原樣送往轉址目標；
        # 轉址回應的本文不讀取，最終回應才套用大小上限
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=False,
            transport=SSRFSafeTransport(DnsPool.CONFIGURED_ENDPOINT),
        ) as client:
            request = client.build_request("POST", self.url, headers=self.headers, json=payload)
            resp = await send_following_redirects(client, request, MAX_MCP_HTTP_REDIRECTS, allow_cross_origin=False)
            try:
                content_length = resp.headers.get("content-length")
                if content_length and content_length.isdigit() and int(content_length) > MAX_MCP_HTTP_RESPONSE_BYTES:
                    raise RuntimeError(f"HTTP MCP 伺服器回應超過 {MAX_MCP_HTTP_RESPONSE_BYTES} 位元組上限")
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_MCP_HTTP_RESPONSE_BYTES:
                        raise RuntimeError(f"HTTP MCP 伺服器回應超過 {MAX_MCP_HTTP_RESPONSE_BYTES} 位元組上限")
                    chunks.append(chunk)
            finally:
                await resp.aclose()
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP MCP 伺服器返回狀態碼 {resp.status_code}")
            data = json.loads(b"".join(chunks))
            if "error" in data:
                raise RuntimeError(f"MCP JSON-RPC 錯誤: {data['error']}")
            return data.get("result", {})
    async def initialize(self) -> Dict[str, Any]:
        return await self._send_rpc_request("initialize", {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": "AskMiao-MCP-Client",
                "version": __version__
            }
        })
    async def list_tools(self) -> List[Dict[str, Any]]:
        result = await self._send_rpc_request("tools/list", {})
        return _usable_tools(result.get("tools", []))
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._send_rpc_request("tools/call", {
            "name": name,
            "arguments": arguments or {}
        })
class McpManager:
    """
    MCP 伺服器與工具調度管理器
    """
    @classmethod
    def get_preset_servers(cls) -> List[Dict[str, Any]]:
        """常見官方與社群 MCP 伺服器快速範本

        不提供網頁擷取類範本：stdio 子行程的出站連線不受 web_fetch 的 SSRF、
        網域白名單與網址來源防護約束。
        """
        os.makedirs(MCP_FILESYSTEM_SANDBOX_DIR, exist_ok=True)
        return [
            {
                "name": "mcp_time",
                "display_name": "即時時間與時區轉換 (Time)",
                "description": "提供全球各大城市當前精確時間查詢、時區換算與時間差計算工具。",
                "transport_type": "stdio",
                "command": "python",
                "args": ["-c", """import sys, json, datetime, zoneinfo
def main():
    while True:
        line = sys.stdin.readline()
        if not line: break
        try:
            req = json.loads(line)
            mid = req.get('id')
            method = req.get('method')
            if method == 'initialize':
                res = {'jsonrpc': '2.0', 'id': mid, 'result': {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'mcp-time-server', 'version': '1.0'}}}
                sys.stdout.write(json.dumps(res) + '\\n'); sys.stdout.flush()
            elif method == 'tools/list':
                tools = [{
                    'name': 'get_current_time',
                    'description': '查詢指定時區或城市的當前精確時間',
                    'inputSchema': {
                        'type': 'object',
                        'properties': {
                            'timezone': {'type': 'string', 'description': '時區名稱 (例如 Asia/Taipei, UTC, America/New_York)', 'default': 'Asia/Taipei'}
                        }
                    }
                }]
                res = {'jsonrpc': '2.0', 'id': mid, 'result': {'tools': tools}}
                sys.stdout.write(json.dumps(res) + '\\n'); sys.stdout.flush()
            elif method == 'tools/call':
                params = req.get('params', {})
                tz_name = params.get('arguments', {}).get('timezone', 'Asia/Taipei')
                try:
                    tz = zoneinfo.ZoneInfo(tz_name)
                    now_str = datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')
                except Exception:
                    now_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
                content = [{'type': 'text', 'text': f'當前時間: {now_str}'}]
                res = {'jsonrpc': '2.0', 'id': mid, 'result': {'content': content, 'isError': False}}
                sys.stdout.write(json.dumps(res) + '\\n'); sys.stdout.flush()
        except Exception:
            pass
if __name__ == '__main__':
    main()
"""],
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
    @classmethod
    async def discover_server_tools(cls, server_dict: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        向指定 MCP 伺服器進行 Initialize 交握並探索工具清單 (tools/list)
        回傳: (tools_list, server_info)
        """
        transport_type = server_dict.get("transport_type", "stdio")
        timeout = float(server_dict.get("timeout", 20))
        if transport_type == "stdio":
            cmd = server_dict.get("command")
            if not cmd:
                raise ValueError("Stdio 傳輸模式必須指定 command 執行指令")
            raw_args = server_dict.get("args") or []
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except Exception:
                    raw_args = [raw_args]
            raw_env = server_dict.get("env_vars") or {}
            if isinstance(raw_env, str):
                try:
                    raw_env = json.loads(raw_env)
                except Exception:
                    raw_env = {}
            client = McpStdioClient(
                command=cmd,
                args=raw_args,
                env_vars=raw_env,
                timeout=timeout
            )
            try:
                await client.start()
                init_res = await client.initialize()
                tools = await client.list_tools()
                return tools, init_res
            finally:
                await client.close()
        elif transport_type in ["sse", "http"]:
            url = server_dict.get("url")
            if not url:
                raise ValueError("SSE/HTTP 傳輸模式必須指定 url 連線網址")
            raw_headers = server_dict.get("headers") or {}
            if isinstance(raw_headers, str):
                try:
                    raw_headers = json.loads(raw_headers)
                except Exception:
                    raw_headers = {}
            client = McpHttpClient(
                url=url,
                headers=raw_headers,
                timeout=timeout
            )
            init_res = await client.initialize()
            tools = await client.list_tools()
            return tools, init_res
        else:
            raise ValueError(f"不支援的傳輸模式: {transport_type}")
    @classmethod
    async def execute_mcp_tool(
        cls,
        server_dict: Dict[str, Any],
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        調用指定 MCP 伺服器之特定工具 (tools/call)
        """
        start_t = time.time()
        transport_type = server_dict.get("transport_type", "stdio")
        timeout = float(server_dict.get("timeout", 30))
        try:
            if transport_type == "stdio":
                cmd = server_dict.get("command")
                raw_args = server_dict.get("args") or []
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except Exception:
                        raw_args = [raw_args]
                raw_env = server_dict.get("env_vars") or {}
                if isinstance(raw_env, str):
                    try:
                        raw_env = json.loads(raw_env)
                    except Exception:
                        raw_env = {}
                client = McpStdioClient(
                    command=cmd,
                    args=raw_args,
                    env_vars=raw_env,
                    timeout=timeout
                )
                try:
                    await client.start()
                    await client.initialize()
                    res = await client.call_tool(tool_name, arguments)
                    duration = round(time.time() - start_t, 3)
                    return {
                        "is_success": not res.get("isError", False),
                        "duration_seconds": duration,
                        "content": res.get("content", []),
                        "raw_result": res
                    }
                finally:
                    await client.close()
            elif transport_type in ["sse", "http"]:
                url = server_dict.get("url")
                raw_headers = server_dict.get("headers") or {}
                if isinstance(raw_headers, str):
                    try:
                        raw_headers = json.loads(raw_headers)
                    except Exception:
                        raw_headers = {}
                client = McpHttpClient(
                    url=url,
                    headers=raw_headers,
                    timeout=timeout
                )
                await client.initialize()
                res = await client.call_tool(tool_name, arguments)
                duration = round(time.time() - start_t, 3)
                return {
                    "is_success": not res.get("isError", False),
                    "duration_seconds": duration,
                    "content": res.get("content", []),
                    "raw_result": res
                }
            else:
                raise ValueError(f"不支援的傳輸模式: {transport_type}")
        except Exception as e:
            duration = round(time.time() - start_t, 3)
            # 例外內容（stderr、JSON-RPC 錯誤、SSRF 拒絕原因）只寫入日誌；結果會交給模型、顯示給使用者並存進研究軌跡
            error_id = log_and_get_error_id(logger, f"調用 MCP 工具 {tool_name} 失敗", e)
            return {
                "is_success": False,
                "duration_seconds": duration,
                "error": format_client_error(error_id),
                "error_id": error_id
            }
    @classmethod
    def convert_mcp_tool_to_function_def(
        cls,
        server_name: str,
        server_display_name: str,
        mcp_tool: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        將 MCP tool 規格轉換為 OpenAI Function Calling 相容之 Tool Definition
        """
        t_name = mcp_tool.get("name", "")
        clean_server = re.sub(r'[^a-zA-Z0-9_]', '_', server_name).lower()
        clean_tool = re.sub(r'[^a-zA-Z0-9_]', '_', t_name).lower()
        fn_name = f"mcp_{clean_server}_{clean_tool}"
        desc = mcp_tool.get("description") or f"由 MCP 伺服器 [{server_display_name}] 提供的工具: {t_name}"
        input_schema = mcp_tool.get("inputSchema") or {"type": "object", "properties": {}}
        return {
            "type": "function",
            "function": {
                "name": fn_name,
                "description": f"【MCP 協定工具】{server_display_name} -> {t_name}：{desc}",
                "parameters": input_schema
            }
        }
