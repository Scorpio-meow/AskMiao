import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import html
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models import (
    McpServer,
    McpServerCreate,
    McpServerUpdate,
    McpToolTestRequest,
)
from app.core.jwt_auth import get_current_admin_user
from app.core.ssrf_protection import SSRFProtectionError
from app.services import mcp_oauth
from app.services.mcp_service import McpHttpStatusError, McpManager
from app.core.security_logging import log_security_event
from app.core.error_response import SafeClientError, log_and_get_error_id, format_client_error
from app.core.tool_secrets import decrypt_for_display, decrypt_json, encrypt_json, is_any_key, is_secret_header, mask, merge_masked
logger = logging.getLogger(__name__)
# MCP 伺服器是所有使用者的 Agent 共用的全域設定：stdio 模式會在主機上執行指定的指令，
# 回應中也含環境變數與標頭等憑證，因此整個模組（含查詢）只開放管理員
router = APIRouter()
oauth_callback_router = APIRouter()
OAUTH_CLIENT_KEYS = ("client_id", "client_secret", "scope")
def _serialize_mcp_server(server: McpServer) -> Dict[str, Any]:
    """序列化 McpServer 模型為 Dict（含解密後的環境變數與標頭，只供連線與執行使用，不可直接回傳給用戶端）"""
    fields = _server_fields(server, decrypt_json(server.env_vars), decrypt_json(server.headers))
    fields["oauth_authorized"] = bool(server.oauth_tokens)
    return fields
def _oauth_client_display(server: McpServer) -> Tuple[Optional[Dict[str, Any]], bool]:
    config, unreadable = decrypt_for_display(server.oauth_config)
    if not config or config.get("client_source") != "admin":
        return None, unreadable
    return mask({key: config.get(key, "") for key in OAUTH_CLIENT_KEYS}, lambda key: key == "client_secret"), unreadable
def _apply_oauth_client(server: McpServer, incoming: Dict[str, str]) -> None:
    existing = decrypt_for_display(server.oauth_config)[0] or {}
    admin_existing = existing if existing.get("client_source") == "admin" else {}
    client = merge_masked({key: str(incoming.get(key) or "") for key in OAUTH_CLIENT_KEYS}, admin_existing)
    if not client.get("client_id"):
        if admin_existing:
            server.oauth_config = None
            server.oauth_tokens = None
        return
    if all(client.get(key, "") == admin_existing.get(key, "") for key in OAUTH_CLIENT_KEYS):
        return
    server.oauth_config = encrypt_json({**client, "client_source": "admin"})
    server.oauth_tokens = None
def _server_response(server: McpServer) -> Dict[str, Any]:
    """管理 API 回應用：環境變數與標頭中的憑證以遮蔽字樣取代；更新時送回遮蔽字樣的欄位沿用原值"""
    env_vars, env_unreadable = decrypt_for_display(server.env_vars)
    headers, headers_unreadable = decrypt_for_display(server.headers)
    fields = _server_fields(server, mask(env_vars, is_any_key), mask(headers, is_secret_header))
    oauth_client, oauth_unreadable = _oauth_client_display(server)
    fields["oauth_client"] = oauth_client
    fields["oauth_authorized"] = bool(server.oauth_tokens)
    fields["credentials_unreadable"] = env_unreadable or headers_unreadable or oauth_unreadable
    return fields
def _server_fields(server: McpServer, env_vars: Optional[Dict[str, Any]], headers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    args = []
    if server.args:
        try:
            args = json.loads(server.args)
        except Exception:
            args = [server.args]
    discovered_tools = _json_list(server.discovered_tools)
    return {
        "id": server.id,
        "name": server.name,
        "display_name": server.display_name,
        "description": server.description,
        "transport_type": server.transport_type,
        "command": server.command,
        "args": args,
        "env_vars": env_vars,
        "url": server.url,
        "headers": headers,
        "is_enabled": bool(server.is_enabled),
        "requires_approval": bool(server.requires_approval),
        "status": server.status,
        "last_error": server.last_error,
        "discovered_tools": discovered_tools,
        "discovered_resources": _json_list(server.discovered_resources),
        "discovered_prompts": _json_list(server.discovered_prompts),
        "timeout": server.timeout or 30,
        "created_at": server.created_at,
        "updated_at": server.updated_at,
    }
def _json_list(value: Optional[str]) -> List[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []
def _store_discovery(server: McpServer, tools: List[Dict[str, Any]], catalog: Dict[str, List[Dict[str, Any]]]) -> None:
    server.discovered_tools = json.dumps(tools, ensure_ascii=False)
    server.discovered_resources = json.dumps(catalog["resources"], ensure_ascii=False)
    server.discovered_prompts = json.dumps(catalog["prompts"], ensure_ascii=False)
OAUTH_REQUIRED_MESSAGE = "MCP 伺服器要求 OAuth 授權，請按「OAuth 授權」完成登入後再重新探索"
def _discovery_error_message(e: Exception, error_id: str) -> str:
    if isinstance(e, McpHttpStatusError) and e.status_code == 401:
        return f"{OAUTH_REQUIRED_MESSAGE}（錯誤代碼：{error_id}）"
    return format_client_error(error_id)
def _format_ssrf_rejection(error_id: str) -> str:
    """SSRF 拒絕原因可能含伺服器端 DNS 解析出的內網 IP 或轉址目標，只寫入日誌；對外只說明遭拒並附錯誤代碼"""
    return (
        "SSRF 防護拒絕連線：網址或其轉址目標未通過安全檢查，完整原因記錄於伺服器日誌；"
        f"本機的 MCP 伺服器請改用 stdio 傳輸（錯誤代碼：{error_id}）"
    )
@router.get("/presets")
async def get_preset_servers(current_user: dict = Depends(get_current_admin_user)):
    """獲取常用官方與社群 MCP 伺服器範本"""
    return {
        "status": "success",
        "presets": McpManager.get_preset_servers()
    }
@router.get("/servers")
async def get_all_servers(
    is_enabled: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """獲取所有已配置的 MCP 伺服器清單"""
    query = db.query(McpServer)
    if is_enabled is not None:
        query = query.filter(McpServer.is_enabled == is_enabled)
    servers = query.order_by(McpServer.id.desc()).all()
    return {
        "status": "success",
        "total": len(servers),
        "servers": [_server_response(s) for s in servers]
    }
@router.post("/servers")
async def create_server(
    server_data: McpServerCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """新增 MCP 伺服器配置"""
    clean_name = server_data.name.strip().lower()
    existing = db.query(McpServer).filter(McpServer.name == clean_name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"已存在同名 MCP 伺服器: {clean_name}")
    new_server = McpServer(
        name=clean_name,
        display_name=server_data.display_name,
        description=server_data.description,
        transport_type=server_data.transport_type or "stdio",
        command=server_data.command,
        args=json.dumps(server_data.args, ensure_ascii=False) if server_data.args else None,
        env_vars=encrypt_json(server_data.env_vars),
        url=server_data.url,
        headers=encrypt_json(server_data.headers),
        is_enabled=server_data.is_enabled if server_data.is_enabled is not None else True,
        requires_approval=server_data.requires_approval if server_data.requires_approval is not None else True,
        timeout=server_data.timeout or 30,
        status="disconnected",
        created_by=current_user["user_id"]
    )
    if server_data.oauth_client:
        _apply_oauth_client(new_server, server_data.oauth_client)
    db.add(new_server)
    db.commit()
    db.refresh(new_server)
    try:
        server_dict = _serialize_mcp_server(new_server)
        tools, init_info, catalog = await McpManager.discover_server_tools(server_dict)
        _store_discovery(new_server, tools, catalog)
        new_server.status = "connected"
        new_server.last_error = None
        db.commit()
        db.refresh(new_server)
    except SSRFProtectionError as e:
        error_id = log_and_get_error_id(logger, "MCP 伺服器網址被 SSRF 防護拒絕", e, logging.WARNING)
        new_server.status = "error"
        new_server.last_error = _format_ssrf_rejection(error_id)
        db.commit()
        db.refresh(new_server)
    except Exception as e:
        error_id = log_and_get_error_id(logger, "初次探索 MCP 工具失敗", e, logging.WARNING)
        new_server.status = "error"
        new_server.last_error = _discovery_error_message(e, error_id)
        db.commit()
        db.refresh(new_server)
    return {
        "status": "success",
        "message": "MCP 伺服器建立成功",
        "server": _server_response(new_server)
    }
@router.get("/servers/{server_id}")
async def get_server_detail(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """獲取單一 MCP 伺服器詳情"""
    server = db.query(McpServer).filter(McpServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="找不到該 MCP 伺服器")
    return {
        "status": "success",
        "server": _server_response(server)
    }
@router.put("/servers/{server_id}")
async def update_server(
    server_id: int,
    server_data: McpServerUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """更新 MCP 伺服器配置"""
    server = db.query(McpServer).filter(McpServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="找不到該 MCP 伺服器")
    if server_data.display_name is not None:
        server.display_name = server_data.display_name
    if server_data.description is not None:
        server.description = server_data.description
    if server_data.transport_type is not None:
        server.transport_type = server_data.transport_type
    if server_data.command is not None:
        server.command = server_data.command
    if server_data.args is not None:
        server.args = json.dumps(server_data.args, ensure_ascii=False)
    try:
        if server_data.env_vars is not None:
            server.env_vars = encrypt_json(merge_masked(server_data.env_vars, decrypt_for_display(server.env_vars)[0]))
        if server_data.headers is not None:
            server.headers = encrypt_json(merge_masked(server_data.headers, decrypt_for_display(server.headers)[0]))
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if server_data.url is not None and server_data.url != server.url:
        server.url = server_data.url
        server.oauth_tokens = None
        if (decrypt_for_display(server.oauth_config)[0] or {}).get("client_source") != "admin":
            server.oauth_config = None
    try:
        if server_data.oauth_client is not None:
            _apply_oauth_client(server, server_data.oauth_client)
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if server_data.is_enabled is not None:
        server.is_enabled = server_data.is_enabled
    if server_data.requires_approval is not None:
        server.requires_approval = server_data.requires_approval
    if server_data.timeout is not None:
        server.timeout = server_data.timeout
    db.commit()
    db.refresh(server)
    return {
        "status": "success",
        "message": "MCP 伺服器配置更新成功",
        "server": _server_response(server)
    }
@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """刪除 MCP 伺服器配置"""
    server = db.query(McpServer).filter(McpServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="找不到該 MCP 伺服器")
    db.delete(server)
    db.commit()
    return {
        "status": "success",
        "message": "MCP 伺服器已成功刪除"
    }
def _oauth_page(title: str, message: str, status_code: int) -> HTMLResponse:
    body = (
        "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title></head><body><h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(message)}</p></body></html>"
    )
    return HTMLResponse(body, status_code=status_code)
@router.post("/servers/{server_id}/oauth/start")
async def start_oauth(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """以授權碼流程（PKCE）向遠端 MCP 伺服器的授權伺服器取得權杖；回傳讓管理員在瀏覽器開啟的授權網址"""
    server = db.query(McpServer).filter(McpServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="找不到該 MCP 伺服器")
    if server.transport_type not in ("http", "sse") or not server.url:
        raise HTTPException(status_code=400, detail="只有 HTTP / SSE 傳輸的 MCP 伺服器可以使用 OAuth 授權")
    redirect_uri = str(request.url_for("mcp_oauth_callback"))
    try:
        config = decrypt_json(server.oauth_config) or {}
        discovered = await mcp_oauth.discover(server.url, decrypt_json(server.headers) or {})
        config = {**config, **discovered}
        if config.get("client_source") == "admin":
            config["redirect_uri"] = redirect_uri
        elif config.get("redirect_uri") != redirect_uri or not config.get("client_id"):
            if not discovered.get("registration_endpoint"):
                raise mcp_oauth.OAuthClientRequired()
            config.update(await mcp_oauth.register_client(discovered["registration_endpoint"], redirect_uri))
            config["client_source"] = "registered"
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except mcp_oauth.OAuthClientRequired:
        raise HTTPException(status_code=400, detail="授權伺服器不支援動態註冊，請在 MCP 伺服器設定中填入 OAuth client_id")
    except SSRFProtectionError as e:
        error_id = log_and_get_error_id(logger, "MCP OAuth 網址被 SSRF 防護拒絕", e, logging.WARNING)
        raise HTTPException(status_code=400, detail=_format_ssrf_rejection(error_id))
    except Exception as e:
        error_id = log_and_get_error_id(logger, "MCP OAuth 探索失敗", e, logging.WARNING)
        raise HTTPException(status_code=400, detail=f"無法取得 MCP 伺服器的 OAuth 設定（錯誤代碼：{error_id}）")
    server.oauth_config = encrypt_json(config)
    db.commit()
    return {
        "status": "success",
        "authorization_url": mcp_oauth.authorization_url(server.id, current_user["user_id"], config, redirect_uri),
    }
@router.delete("/servers/{server_id}/oauth")
async def revoke_oauth(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """清除已保存的 OAuth 權杖"""
    server = db.query(McpServer).filter(McpServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="找不到該 MCP 伺服器")
    server.oauth_tokens = None
    db.commit()
    return {"status": "success", "message": "已清除 OAuth 授權", "server": _server_response(server)}
@oauth_callback_router.get("/oauth/callback", name="mcp_oauth_callback", response_class=HTMLResponse)
async def oauth_callback(
    request: Request,
    state: str = Query(""),
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """授權伺服器導回的位址：不需登入，以一次性的 state 對應發起授權的管理員與伺服器"""
    pending = mcp_oauth.take_pending(state)
    if pending is None:
        return _oauth_page("授權失敗", "授權連結無效或已過期，請回到 AskMiao 重新按「OAuth 授權」。", 400)
    if error or not code:
        return _oauth_page("授權未完成", "授權伺服器沒有核發授權碼，請回到 AskMiao 重新授權。", 400)
    server = db.query(McpServer).filter(McpServer.id == pending["server_id"]).first()
    if server is None:
        return _oauth_page("授權失敗", "找不到該 MCP 伺服器。", 404)
    try:
        config = decrypt_json(server.oauth_config) or {}
        tokens = await mcp_oauth.exchange_code(config, code, pending["verifier"], pending["redirect_uri"])
    except Exception as e:
        error_id = log_and_get_error_id(logger, "MCP OAuth 換取權杖失敗", e, logging.WARNING)
        return _oauth_page("授權失敗", f"無法換取存取權杖（錯誤代碼：{error_id}）。", 400)
    server.oauth_tokens = encrypt_json(tokens)
    db.commit()
    log_security_event(
        "ADMIN_MCP_OAUTH_AUTHORIZED", request=request, user_id=pending["user_id"], details={"server": server.name}
    )
    return _oauth_page("授權完成", f"已完成「{server.display_name}」的 OAuth 授權，可以關閉這個視窗，回到 AskMiao 重新探索工具。", 200)
@router.post("/servers/{server_id}/discover")
async def discover_server_tools(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """即時連線並探索 MCP 伺服器提供的所有工具 (tools/list)"""
    server = db.query(McpServer).filter(McpServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="找不到該 MCP 伺服器")
    try:
        server_dict = _serialize_mcp_server(server)
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        tools, init_info, catalog = await McpManager.discover_server_tools(server_dict)
        _store_discovery(server, tools, catalog)
        server.status = "connected"
        server.last_error = None
        db.commit()
        db.refresh(server)
        return {
            "status": "success",
            "message": f"成功連線並探索到 {len(tools)} 項 MCP 工具、{len(catalog['resources'])} 項 resource、{len(catalog['prompts'])} 項 prompt",
            "tools_count": len(tools),
            "tools": tools,
            "resources": catalog["resources"],
            "prompts": catalog["prompts"],
            "init_info": init_info,
            "server": _server_response(server)
        }
    except SSRFProtectionError as e:
        error_id = log_and_get_error_id(logger, "MCP 伺服器網址被 SSRF 防護拒絕", e, logging.WARNING)
        server.status = "error"
        server.last_error = _format_ssrf_rejection(error_id)
        db.commit()
        raise HTTPException(status_code=400, detail=_format_ssrf_rejection(error_id))
    except Exception as e:
        error_id = log_and_get_error_id(logger, "探索 MCP 伺服器工具失敗", e)
        server.status = "error"
        server.last_error = _discovery_error_message(e, error_id)
        db.commit()
        db.refresh(server)
        raise HTTPException(status_code=400, detail=format_client_error(error_id))
@router.patch("/servers/{server_id}/toggle")
async def toggle_server(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """切換 MCP 伺服器啟用狀態"""
    server = db.query(McpServer).filter(McpServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="找不到該 MCP 伺服器")
    server.is_enabled = not server.is_enabled
    db.commit()
    db.refresh(server)
    return {
        "status": "success",
        "is_enabled": server.is_enabled,
        "message": f"MCP 伺服器已{'啟用' if server.is_enabled else '停用'}"
    }
@router.post("/servers/{server_id}/tools/{tool_name}/test")
async def test_mcp_tool(
    server_id: int,
    tool_name: str,
    test_data: McpToolTestRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """即時線上測試特定 MCP 工具調用 (tools/call)"""
    server = db.query(McpServer).filter(McpServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="找不到該 MCP 伺服器")
    try:
        server_dict = _serialize_mcp_server(server)
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = await McpManager.execute_mcp_tool(server_dict, tool_name, test_data.arguments or {})
    return {
        "status": "success",
        "server_name": server.name,
        "tool_name": tool_name,
        "result": result
    }
