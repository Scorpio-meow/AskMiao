import asyncio
import base64
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models import (
    CustomApiTool,
    CustomApiToolCreate,
    CustomApiToolUpdate,
    OpenApiParseRequest,
    OpenApiImportRequest,
    OAUTH2_CLIENT_CREDENTIALS,
    ToolTestRequest,
)
from app.core.jwt_auth import get_current_admin_user
from app.core.limits import MAX_TOOL_NAME_CHARS
from app.core.ssrf_protection import DnsPool, SSRFProtectionError, SSRFSafeTransport, same_origin, send_following_redirects
from app.services.oauth_client import OAuthError, client_credentials_token, invalidate_client_credentials_token
from app.services.openapi_parser import OpenApiParser
from app.services.api_tool_request import (
    RequestParts,
    build_query,
    encode_body,
    scalar_text,
    serialize_cookie,
    serialize_header,
    serialize_path,
    serialize_query,
    serialize_querystring,
)
from app.rag.tool_approval import SAFE_HTTP_METHODS, default_requires_approval
from app.core.error_response import SafeClientError, log_and_get_error_id, format_client_error, format_ssrf_rejection
from app.core.tool_secrets import (
    NON_SECRET_HEADER_NAMES,
    decrypt_for_display,
    decrypt_json,
    encrypt_json,
    is_secret_auth_key,
    is_secret_header,
    mask,
    merge_masked,
)
logger = logging.getLogger(__name__)
router = APIRouter()
def _serialize_tool_model(tool: CustomApiTool) -> Dict[str, Any]:
    headers = decrypt_json(tool.headers)
    auth_config = decrypt_json(tool.auth_config)
    return _tool_fields(tool, headers, auth_config)
def _tool_response(tool: CustomApiTool) -> Dict[str, Any]:
    headers, headers_unreadable = decrypt_for_display(tool.headers)
    auth_config, auth_unreadable = decrypt_for_display(tool.auth_config)
    fields = _tool_fields(tool, mask(headers, is_secret_header), mask(auth_config, is_secret_auth_key))
    fields["credentials_unreadable"] = headers_unreadable or auth_unreadable
    return fields
def _tool_fields(tool: CustomApiTool, headers: Optional[Dict[str, Any]], auth_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    parameters_schema = None
    if tool.parameters_schema:
        try:
            parameters_schema = json.loads(tool.parameters_schema)
        except Exception:
            parameters_schema = {"type": "object", "properties": {}}
    request_body_schema = None
    if tool.request_body_schema:
        try:
            request_body_schema = json.loads(tool.request_body_schema)
        except Exception:
            request_body_schema = None
    param_locations = None
    if tool.param_locations:
        try:
            param_locations = json.loads(tool.param_locations)
        except Exception:
            param_locations = {}
    param_styles = None
    if tool.param_styles:
        try:
            param_styles = json.loads(tool.param_styles)
        except Exception:
            param_styles = None
    workflow_definition = None
    if tool.workflow_definition:
        try:
            workflow_definition = json.loads(tool.workflow_definition)
        except Exception:
            workflow_definition = None
    return {
        "id": tool.id,
        "name": tool.name,
        "display_name": tool.display_name,
        "description": tool.description,
        "category": tool.category or "custom_api",
        "method": (tool.method or "GET").upper(),
        "url": tool.url,
        "base_url": tool.base_url,
        "path": tool.path,
        "headers": headers,
        "auth_type": tool.auth_type or "none",
        "auth_config": auth_config,
        "parameters_schema": parameters_schema,
        "request_body_schema": request_body_schema,
        "param_locations": param_locations,
        "param_styles": param_styles,
        "workflow_definition": workflow_definition,
        "body_content_type": tool.body_content_type or JSON_CONTENT_TYPE,
        "response_mapping": tool.response_mapping,
        "is_enabled": bool(tool.is_enabled),
        "requires_approval": bool(tool.requires_approval),
        "timeout": tool.timeout or 15,
        "spec_version": tool.spec_version or "manual",
        "created_at": tool.created_at,
        "updated_at": tool.updated_at,
    }
MAX_API_TOOL_RESPONSE_BYTES = 1024 * 1024
MAX_API_TOOL_TEXT_CHARS = 4000
MAX_API_TOOL_REDIRECTS = 5
REDACTED = "[已遮蔽]"
MIN_SECRET_LENGTH = 4
JSON_CONTENT_TYPE = "application/json"
BODYLESS_METHODS = ("GET", "HEAD", "OPTIONS", "TRACE")
RESERVED_HEADER_NAMES = ("authorization", "content-type", "accept", "cookie", "host", "content-length")
class ApiToolResponseTooLarge(ValueError):
    pass
def _collect_secrets(headers: Dict[str, str], auth_type: str, auth_config: Dict[str, Any]) -> Set[str]:
    secrets: Set[str] = set()
    for name, value in headers.items():
        if name.lower() not in NON_SECRET_HEADER_NAMES and value:
            secrets.add(str(value))
    if auth_type == "bearer" and auth_config.get("token"):
        secrets.add(str(auth_config["token"]))
    elif auth_type == "api_key" and auth_config.get("key_value"):
        secrets.add(str(auth_config["key_value"]))
    elif auth_type == "basic" and auth_config.get("username"):
        username = str(auth_config.get("username", ""))
        password = str(auth_config.get("password", ""))
        secrets.add(password)
        secrets.add(base64.b64encode(f"{username}:{password}".encode()).decode())
    elif auth_type == OAUTH2_CLIENT_CREDENTIALS and auth_config.get("client_secret"):
        secrets.add(str(auth_config["client_secret"]))
    return {s for s in secrets if len(s) >= MIN_SECRET_LENGTH}
def _redact(value: Any, secrets: Set[str]) -> Any:
    if not secrets:
        return value
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, dict):
        return {_redact(k, secrets): _redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, secrets) for v in value]
    return value
def _without_query(url: str) -> str:
    return url.split("#", 1)[0].split("?", 1)[0]
def _declared_properties(schema: Any) -> Optional[Dict[str, Any]]:
    if isinstance(schema, dict) and isinstance(schema.get("properties"), dict):
        return schema["properties"]
    return None
def _undeclared_arguments(tool_dict: Dict[str, Any], arguments: Dict[str, Any]) -> List[str]:
    properties = _declared_properties(tool_dict.get("parameters_schema"))
    declared = set(properties) if properties is not None else set()
    undeclared = [name for name in arguments if name not in declared]
    body = arguments.get("request_body")
    body_schema = tool_dict.get("request_body_schema")
    body_properties = _declared_properties(body_schema)
    if isinstance(body, dict) and body_properties is not None and body_schema.get("additionalProperties") is not True:
        undeclared += [f"request_body.{name}" for name in body if name not in body_properties]
    return undeclared
async def execute_api_tool(tool_dict: Dict[str, Any], arguments: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    if tool_dict.get("workflow_definition"):
        from app.services.arazzo import run_workflow
        return await run_workflow(tool_dict, arguments, tool_name)
    return await execute_http_api_tool(tool_dict, arguments, tool_name)
async def execute_http_api_tool(tool_dict: Dict[str, Any], arguments: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    return await execute_http_request(tool_dict, arguments, tool_name, keep_exchange=False)
async def execute_http_request(
    tool_dict: Dict[str, Any], arguments: Dict[str, Any], tool_name: str, keep_exchange: bool
) -> Dict[str, Any]:
    start_time = time.time()
    arguments = dict(arguments or {})
    method = (tool_dict.get("method") or "GET").upper()
    base_url = (tool_dict.get("base_url") or "").rstrip("/")
    path = tool_dict.get("path") or ""
    url = tool_dict.get("url") or ""
    if not url and base_url and path:
        url = f"{base_url}/{path.lstrip('/')}"
    elif not url:
        url = path
    undeclared = _undeclared_arguments(tool_dict, arguments)
    if undeclared:
        return {
            "status_code": 400,
            "is_success": False,
            "duration_seconds": round(time.time() - start_time, 3),
            "url": _without_query(url),
            "error": f"工具參數無效：未宣告的參數 {', '.join(undeclared)}",
        }
    param_locations = tool_dict.get("param_locations") or {}
    configured_headers = dict(tool_dict.get("headers") or {})
    headers = dict(configured_headers)
    timeout = int(tool_dict.get("timeout") or 15)
    auth_type = tool_dict.get("auth_type", "none")
    auth_config = tool_dict.get("auth_config") or {}
    credential_query_key: Optional[str] = None
    auth_cookie: Optional[str] = None
    credential_header_names: Set[str] = {name.lower() for name in configured_headers}
    if auth_type == "bearer" and auth_config.get("token"):
        headers["Authorization"] = f"Bearer {auth_config['token']}"
        credential_header_names.add("authorization")
    elif auth_type == "api_key":
        key_name = auth_config.get("key_name", "X-API-Key")
        key_value = auth_config.get("key_value", "")
        key_in = auth_config.get("key_in", "header")
        if key_in == "header" and key_name and key_value:
            headers[key_name] = key_value
            credential_header_names.add(key_name.lower())
        elif key_in == "query" and key_name and key_value:
            arguments[key_name] = key_value
            credential_query_key = key_name
        elif key_in == "cookie" and key_name and key_value:
            auth_cookie = f"{key_name}={key_value}"
            credential_header_names.add("cookie")
    elif auth_type == "basic" and auth_config.get("username"):
        u = auth_config.get("username", "")
        p = auth_config.get("password", "")
        b64_auth = base64.b64encode(f"{u}:{p}".encode()).decode()
        headers["Authorization"] = f"Basic {b64_auth}"
        credential_header_names.add("authorization")
    elif auth_type == OAUTH2_CLIENT_CREDENTIALS:
        try:
            headers["Authorization"] = f"Bearer {await client_credentials_token(auth_config)}"
        except (OAuthError, SSRFProtectionError, httpx.HTTPError, asyncio.TimeoutError) as e:
            error_id = log_and_get_error_id(logger, f"自訂 API 工具 {tool_name} 取得 OAuth2 權杖失敗", e, logging.WARNING)
            return {
                "status_code": 502,
                "is_success": False,
                "duration_seconds": round(time.time() - start_time, 3),
                "url": _without_query(url),
                "error": f"無法取得 OAuth2 存取權杖，請檢查工具的 OAuth2 設定（錯誤代碼：{error_id}）",
                "error_id": error_id,
            }
        credential_header_names.add("authorization")
    secrets = _collect_secrets(headers, auth_type, auth_config)
    if auth_type == OAUTH2_CLIENT_CREDENTIALS:
        secrets.add(headers["Authorization"].split(" ", 1)[1])
    styles = tool_dict.get("param_styles") or {}
    parts = RequestParts()
    query_names: Set[str] = set()
    path_replaced_url = url
    whole_body: Any = None
    has_whole_body = False
    try:
        for k, v in arguments.items():
            spec = styles.get(k) if isinstance(styles.get(k), dict) else {}
            loc = spec.get("in") or param_locations.get(k)
            name = spec.get("name") or k
            if k == credential_query_key:
                parts.query.append((quote(k, safe=""), quote(scalar_text(v), safe="")))
            elif loc == "path" or (loc is None and f"{{{name}}}" in path_replaced_url):
                path_replaced_url = path_replaced_url.replace(
                    f"{{{name}}}", serialize_path(name, v, spec.get("style", "simple"), spec.get("explode", False))
                )
            elif loc == "header":
                if name.lower() in credential_header_names or name.lower() in RESERVED_HEADER_NAMES:
                    raise ValueError(f"不可由參數設定標頭 {name}")
                headers[name] = serialize_header(v, spec)
            elif loc == "cookie":
                parts.cookies.extend(serialize_cookie(name, v, spec))
            elif loc == "querystring":
                parts.querystring = serialize_querystring(v, spec)
            elif loc == "query":
                query_names.add(name)
                parts.query.extend(serialize_query(name, v, spec))
            elif loc == "body":
                if spec.get("whole") or (k == "request_body" and not spec):
                    whole_body, has_whole_body = v, True
                else:
                    parts.body[name] = v
                    parts.body_specs[name] = spec
            elif method in ("POST", "PUT", "PATCH"):
                parts.body[k] = v
            else:
                query_names.add(k)
                parts.query.extend(serialize_query(k, v, {}))
    except ValueError as e:
        return {
            "status_code": 400,
            "is_success": False,
            "duration_seconds": round(time.time() - start_time, 3),
            "url": _without_query(url),
            "error": f"工具參數無效：{e}",
        }
    body_data: Any = parts.body
    if has_whole_body:
        body_data = whole_body
    elif "request_body" in arguments and isinstance(arguments["request_body"], dict) and "request_body" not in styles:
        body_data = arguments["request_body"]
    cookie_items = [value for header_name, value in list(headers.items()) if header_name.lower() == "cookie" and value]
    for header_name in [n for n in headers if n.lower() == "cookie"]:
        del headers[header_name]
    if auth_cookie:
        cookie_items.append(auth_cookie)
    cookie_items.extend(parts.cookies)
    if cookie_items:
        headers["Cookie"] = "; ".join(cookie_items)
    hidden_query_names: Set[str] = {credential_query_key} if credential_query_key else set()
    def display_url(target: httpx.URL) -> str:
        for name in hidden_query_names & set(target.params.keys()):
            target = target.copy_set_param(name, REDACTED)
        return _redact(str(target), secrets)
    try:
        original_url = httpx.URL(path_replaced_url)
        template_url = httpx.URL(url.replace("{", "").replace("}", ""))
        if not same_origin(original_url, template_url):
            raise SafeClientError("代入參數後的網址與工具設定的主機不符")
        fixed_params = original_url.params
        hidden_query_names.update(fixed_params.keys())
        overridden = sorted(name for name in query_names if name in fixed_params and name != credential_query_key)
        if overridden:
            raise SafeClientError(f"工具參數無效：不可覆寫工具網址中固定的查詢參數 {', '.join(overridden)}")
        if parts.querystring and fixed_params:
            raise SafeClientError("工具參數無效：工具網址已有固定的查詢參數，不能再送整段查詢字串")
        raw_query = build_query([(name, value) for name, value in fixed_params.multi_items() if name != credential_query_key], parts)
        async def strip_credentials_cross_origin(request: httpx.Request) -> None:
            if not same_origin(request.url, original_url):
                for name in list(request.headers.keys()):
                    if name.lower() in credential_header_names:
                        del request.headers[name]
        req_kwargs: Dict[str, Any] = {
            "method": method,
            "url": original_url.copy_with(query=raw_query.encode("ascii") if raw_query else None),
            "headers": headers,
        }
        if method not in BODYLESS_METHODS and (has_whole_body or body_data != {}):
            try:
                encoded = encode_body(
                    tool_dict.get("body_content_type") or JSON_CONTENT_TYPE, body_data, parts.body_specs,
                    (styles.get("$body") or {}).get("xml_root"),
                )
            except ValueError as e:
                raise SafeClientError(f"工具參數無效：{e}") from e
            req_kwargs["headers"] = {**headers, **encoded.pop("headers", {})}
            req_kwargs.update(encoded)
        async def perform() -> Dict[str, Any]:
            async with httpx.AsyncClient(
                timeout=float(timeout),
                follow_redirects=False,
                transport=SSRFSafeTransport(DnsPool.CONFIGURED_ENDPOINT),
                event_hooks={"request": [strip_credentials_cross_origin]},
            ) as client:
                try:
                    response = await send_following_redirects(
                        client, client.build_request(**req_kwargs), MAX_API_TOOL_REDIRECTS, allow_cross_origin=method in SAFE_HTTP_METHODS
                    )
                except SSRFProtectionError:
                    raise
                except ValueError as e:
                    raise SafeClientError(f"上游轉址未跟隨：{e}") from e
                try:
                    content_length = response.headers.get("content-length")
                    if content_length and content_length.isdigit() and int(content_length) > MAX_API_TOOL_RESPONSE_BYTES:
                        raise ApiToolResponseTooLarge()
                    chunks = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_API_TOOL_RESPONSE_BYTES:
                            raise ApiToolResponseTooLarge()
                        chunks.append(chunk)
                finally:
                    await response.aclose()
                raw = b"".join(chunks)
                encoding = response.encoding or "utf-8"
                try:
                    text = raw.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    text = raw.decode("utf-8", errors="replace")
                content_type = response.headers.get("content-type", "").lower()
                res_body: Any
                if "application/json" in content_type:
                    try:
                        res_body = json.loads(text)
                    except Exception:
                        res_body = text[:MAX_API_TOOL_TEXT_CHARS]
                else:
                    res_body = text[:MAX_API_TOOL_TEXT_CHARS]
                result = {
                    "status_code": response.status_code,
                    "is_success": response.is_success,
                    "duration_seconds": round(time.time() - start_time, 3),
                    "url": display_url(response.url),
                    "data": _redact(res_body, secrets)
                }
                if keep_exchange:
                    result["exchange"] = {
                        "method": method,
                        "response_headers": {k.lower(): _redact(v, secrets) for k, v in response.headers.items()},
                        "request_headers": {k.lower(): _redact(v, secrets) for k, v in req_kwargs["headers"].items()},
                        "request_query": {k: _redact(v, secrets) for k, v in httpx.URL(str(req_kwargs["url"])).params.items()},
                        "request_path": {
                            (styles.get(k) or {}).get("name", k): v for k, v in arguments.items()
                            if (styles.get(k) or {}).get("in", param_locations.get(k)) == "path"
                        },
                        "request_body": body_data if (has_whole_body or body_data != {}) else None,
                    }
                return result
        result = await asyncio.wait_for(perform(), timeout=float(timeout))
        if auth_type == OAUTH2_CLIENT_CREDENTIALS and result.get("status_code") == 401:
            invalidate_client_credentials_token(auth_config)
            token = await client_credentials_token(auth_config)
            headers["Authorization"] = f"Bearer {token}"
            secrets.add(token)
            result = await asyncio.wait_for(perform(), timeout=float(timeout))
        return result
    except asyncio.TimeoutError:
        return {
            "status_code": 504,
            "is_success": False,
            "duration_seconds": round(time.time() - start_time, 3),
            "url": display_url(httpx.URL(path_replaced_url)),
            "error": f"上游在 {timeout} 秒內沒有完成回應",
        }
    except ApiToolResponseTooLarge:
        return {
            "status_code": 502,
            "is_success": False,
            "duration_seconds": round(time.time() - start_time, 3),
            "url": display_url(httpx.URL(path_replaced_url)),
            "error": f"上游回應超過 {MAX_API_TOOL_RESPONSE_BYTES} 位元組上限，已中止讀取",
        }
    except SafeClientError as e:
        return {
            "status_code": 400,
            "is_success": False,
            "duration_seconds": round(time.time() - start_time, 3),
            "url": _without_query(url),
            "error": str(e),
        }
    except SSRFProtectionError as e:
        duration = round(time.time() - start_time, 3)
        error_id = log_and_get_error_id(
            logger, f"自訂 API 工具 {tool_name} 被 SSRF 防護拒絕", e, logging.WARNING
        )
        return {
            "status_code": 403,
            "is_success": False,
            "duration_seconds": duration,
            "url": display_url(httpx.URL(path_replaced_url)),
            "error": format_ssrf_rejection(error_id),
            "error_id": error_id
        }
    except Exception as e:
        duration = round(time.time() - start_time, 3)
        error_id = log_and_get_error_id(
            logger, f"執行自訂 API 工具 {tool_name} 失敗", e
        )
        return {
            "status_code": 500,
            "is_success": False,
            "duration_seconds": duration,
            "url": _redact(_without_query(path_replaced_url), secrets),
            "error": format_client_error(error_id),
            "error_id": error_id
        }
@router.post("/parse-spec")
async def parse_openapi_spec(
    request_data: OpenApiParseRequest,
    current_user: dict = Depends(get_current_admin_user)
):
    try:
        parsed_result = await OpenApiParser.parse(
            spec_content_or_url=request_data.spec_content_or_url,
            default_base_url=request_data.default_base_url,
            overlays=request_data.overlays,
        )
        return {
            "status": "success",
            "data": parsed_result
        }
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=f"OpenAPI 規格解析失敗: {str(e)}")
    except Exception as e:
        error_id = log_and_get_error_id(logger, "OpenAPI 規格解析失敗", e)
        raise HTTPException(status_code=500, detail=format_client_error(error_id))
def _import_auth(item, global_auth_type: str, global_auth_config: Dict[str, Any]) -> tuple:
    if not item.auth_type or item.auth_type == "none":
        return global_auth_type, global_auth_config
    config = dict(item.auth_config or {})
    if item.auth_type == global_auth_type:
        config.update({key: value for key, value in global_auth_config.items() if value not in (None, "")})
    return item.auth_type, config
def _reimport_auth(existing: CustomApiTool, auth_type: str, auth_config: Dict[str, Any]) -> tuple:
    stored = decrypt_for_display(existing.auth_config)[0] or {}
    provided = {key: value for key, value in auth_config.items() if value not in (None, "")}
    if auth_type == existing.auth_type:
        return auth_type, {**stored, **provided}
    if existing.auth_type in (None, "none") or any(is_secret_auth_key(key) for key in provided):
        return auth_type, auth_config
    return existing.auth_type, stored
def _import_requires_approval(item) -> bool:
    if item.workflow_definition and item.requires_approval is not None:
        return item.requires_approval
    return default_requires_approval(item.method)
@router.post("/import")
async def import_openapi_tools(
    import_data: OpenApiImportRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    imported_count = 0
    updated_count = 0
    global_base_url = import_data.global_base_url
    global_headers = import_data.global_headers or {}
    global_auth_type = import_data.global_auth_type or "none"
    global_auth_config = import_data.global_auth_config or {}
    too_long = [item.name for item in import_data.tools if len(item.name) > MAX_TOOL_NAME_CHARS]
    if too_long:
        raise HTTPException(status_code=400, detail=f"工具名稱最多 {MAX_TOOL_NAME_CHARS} 個字元：{', '.join(too_long)}")
    for item in import_data.tools:
        effective_base = item.base_url or global_base_url or ""
        effective_url = item.full_url
        if effective_base and item.path:
            effective_url = f"{effective_base.rstrip('/')}/{item.path.lstrip('/')}"
        merged_headers = dict(global_headers)
        if item.headers:
            merged_headers.update(item.headers)
        effective_auth_type, effective_auth_config = _import_auth(item, global_auth_type, global_auth_config)
        existing = db.query(CustomApiTool).filter(CustomApiTool.name == item.name).first()
        if existing:
            existing.display_name = item.display_name
            existing.description = item.description
            existing.method = item.method.upper()
            existing.url = effective_url
            existing.base_url = effective_base
            existing.path = item.path
            stored_headers = decrypt_for_display(existing.headers)[0] or {}
            existing.headers = encrypt_json({**stored_headers, **{name: value for name, value in merged_headers.items() if value}})
            existing.auth_type, reimported_auth_config = _reimport_auth(existing, effective_auth_type, effective_auth_config)
            existing.auth_config = encrypt_json(reimported_auth_config)
            existing.parameters_schema = json.dumps(item.parameters_schema, ensure_ascii=False) if item.parameters_schema else None
            existing.request_body_schema = json.dumps(item.request_body_schema, ensure_ascii=False) if item.request_body_schema else None
            existing.param_locations = json.dumps(item.param_locations, ensure_ascii=False) if item.param_locations else None
            existing.param_styles = json.dumps(item.param_styles, ensure_ascii=False) if item.param_styles else None
            existing.workflow_definition = json.dumps(item.workflow_definition, ensure_ascii=False) if item.workflow_definition else None
            existing.body_content_type = item.body_content_type
            existing.spec_version = item.spec_version
            existing.requires_approval = bool(existing.requires_approval) or _import_requires_approval(item)
            updated_count += 1
        else:
            new_tool = CustomApiTool(
                name=item.name,
                display_name=item.display_name,
                description=item.description,
                method=item.method.upper(),
                url=effective_url,
                base_url=effective_base,
                path=item.path,
                headers=encrypt_json(merged_headers),
                auth_type=effective_auth_type,
                auth_config=encrypt_json(effective_auth_config),
                parameters_schema=json.dumps(item.parameters_schema, ensure_ascii=False) if item.parameters_schema else None,
                request_body_schema=json.dumps(item.request_body_schema, ensure_ascii=False) if item.request_body_schema else None,
                param_locations=json.dumps(item.param_locations, ensure_ascii=False) if item.param_locations else None,
                param_styles=json.dumps(item.param_styles, ensure_ascii=False) if item.param_styles else None,
                workflow_definition=json.dumps(item.workflow_definition, ensure_ascii=False) if item.workflow_definition else None,
                body_content_type=item.body_content_type,
                spec_version=item.spec_version,
                is_enabled=True,
                requires_approval=_import_requires_approval(item),
                created_by=current_user["user_id"]
            )
            db.add(new_tool)
            imported_count += 1
    db.commit()
    return {
        "status": "success",
        "message": f"成功匯入 {imported_count} 個新工具，更新 {updated_count} 個既有工具。",
        "imported": imported_count,
        "updated": updated_count
    }
@router.get("")
async def get_all_api_tools(
    category: Optional[str] = Query(None),
    is_enabled: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    query = db.query(CustomApiTool)
    if category:
        query = query.filter(CustomApiTool.category == category)
    if is_enabled is not None:
        query = query.filter(CustomApiTool.is_enabled == is_enabled)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            (CustomApiTool.name.ilike(s)) |
            (CustomApiTool.display_name.ilike(s)) |
            (CustomApiTool.description.ilike(s)) |
            (CustomApiTool.url.ilike(s))
        )
    tools = query.order_by(CustomApiTool.id.desc()).all()
    return {
        "status": "success",
        "total": len(tools),
        "tools": [_tool_response(t) for t in tools]
    }
@router.post("")
async def create_api_tool(
    tool_data: CustomApiToolCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    if len(tool_data.name.strip()) > MAX_TOOL_NAME_CHARS:
        raise HTTPException(status_code=400, detail=f"工具名稱最多 {MAX_TOOL_NAME_CHARS} 個字元")
    clean_name = OpenApiParser._generate_tool_name(tool_data.method, tool_data.path or tool_data.url, tool_data.name)
    existing = db.query(CustomApiTool).filter(CustomApiTool.name == clean_name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"已存在同名工具: {clean_name}")
    new_tool = CustomApiTool(
        name=clean_name,
        display_name=tool_data.display_name,
        description=tool_data.description,
        category=tool_data.category or "custom_api",
        method=tool_data.method.upper(),
        url=tool_data.url,
        base_url=tool_data.base_url,
        path=tool_data.path,
        headers=encrypt_json(tool_data.headers),
        auth_type=tool_data.auth_type or "none",
        auth_config=encrypt_json(tool_data.auth_config),
        parameters_schema=json.dumps(tool_data.parameters_schema, ensure_ascii=False) if tool_data.parameters_schema else None,
        request_body_schema=json.dumps(tool_data.request_body_schema, ensure_ascii=False) if tool_data.request_body_schema else None,
        param_locations=json.dumps(tool_data.param_locations, ensure_ascii=False) if tool_data.param_locations else None,
        param_styles=json.dumps(tool_data.param_styles, ensure_ascii=False) if tool_data.param_styles else None,
        body_content_type=tool_data.body_content_type,
        response_mapping=tool_data.response_mapping,
        is_enabled=tool_data.is_enabled if tool_data.is_enabled is not None else True,
        requires_approval=(
            tool_data.requires_approval
            if tool_data.requires_approval is not None
            else default_requires_approval(tool_data.method)
        ),
        timeout=tool_data.timeout or 15,
        spec_version=tool_data.spec_version or "manual",
        created_by=current_user["user_id"]
    )
    db.add(new_tool)
    db.commit()
    db.refresh(new_tool)
    return {
        "status": "success",
        "message": "自訂 API 工具建立成功",
        "tool": _tool_response(new_tool)
    }
@router.get("/{tool_id}")
async def get_api_tool_detail(
    tool_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    tool = db.query(CustomApiTool).filter(CustomApiTool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="找不到該自訂 API 工具")
    return {
        "status": "success",
        "tool": _tool_response(tool)
    }
@router.put("/{tool_id}")
async def update_api_tool(
    tool_id: int,
    tool_data: CustomApiToolUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    tool = db.query(CustomApiTool).filter(CustomApiTool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="找不到該自訂 API 工具")
    if tool_data.display_name is not None:
        tool.display_name = tool_data.display_name
    if tool_data.description is not None:
        tool.description = tool_data.description
    if tool_data.category is not None:
        tool.category = tool_data.category
    if tool_data.method is not None:
        tool.method = tool_data.method.upper()
    if tool_data.url is not None:
        tool.url = tool_data.url
    if tool_data.base_url is not None:
        tool.base_url = tool_data.base_url
    if tool_data.path is not None:
        tool.path = tool_data.path
    try:
        if tool_data.headers is not None:
            tool.headers = encrypt_json(merge_masked(tool_data.headers, decrypt_for_display(tool.headers)[0]))
        if tool_data.auth_config is not None:
            tool.auth_config = encrypt_json(merge_masked(tool_data.auth_config, decrypt_for_display(tool.auth_config)[0]))
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if tool_data.auth_type is not None:
        tool.auth_type = tool_data.auth_type
    if tool_data.parameters_schema is not None:
        tool.parameters_schema = json.dumps(tool_data.parameters_schema, ensure_ascii=False) if tool_data.parameters_schema else None
    if tool_data.request_body_schema is not None:
        tool.request_body_schema = json.dumps(tool_data.request_body_schema, ensure_ascii=False) if tool_data.request_body_schema else None
    if tool_data.param_locations is not None:
        tool.param_locations = json.dumps(tool_data.param_locations, ensure_ascii=False) if tool_data.param_locations else None
    if tool_data.param_styles is not None:
        tool.param_styles = json.dumps(tool_data.param_styles, ensure_ascii=False) if tool_data.param_styles else None
    if tool_data.body_content_type is not None:
        tool.body_content_type = tool_data.body_content_type
    if tool_data.is_enabled is not None:
        tool.is_enabled = tool_data.is_enabled
    if tool_data.requires_approval is not None:
        tool.requires_approval = tool_data.requires_approval
    elif tool_data.method is not None and default_requires_approval(tool_data.method):
        tool.requires_approval = True
    if tool_data.timeout is not None:
        tool.timeout = tool_data.timeout
    db.commit()
    db.refresh(tool)
    return {
        "status": "success",
        "message": "自訂 API 工具更新成功",
        "tool": _tool_response(tool)
    }
@router.patch("/{tool_id}/toggle")
async def toggle_api_tool(
    tool_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    tool = db.query(CustomApiTool).filter(CustomApiTool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="找不到該自訂 API 工具")
    tool.is_enabled = not tool.is_enabled
    db.commit()
    db.refresh(tool)
    return {
        "status": "success",
        "is_enabled": tool.is_enabled,
        "message": f"工具已{'啟用' if tool.is_enabled else '停用'}"
    }
@router.delete("/{tool_id}")
async def delete_api_tool(
    tool_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    tool = db.query(CustomApiTool).filter(CustomApiTool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="找不到該自訂 API 工具")
    db.delete(tool)
    db.commit()
    return {
        "status": "success",
        "message": "自訂 API 工具已成功刪除"
    }
@router.post("/{tool_id}/test")
async def test_api_tool(
    tool_id: int,
    test_data: ToolTestRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    tool = db.query(CustomApiTool).filter(CustomApiTool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="找不到該自訂 API 工具")
    try:
        tool_dict = _serialize_tool_model(tool)
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = await execute_api_tool(tool_dict, test_data.arguments or {}, tool.name)
    return {
        "status": "success",
        "tool_name": tool.name,
        "result": result
    }