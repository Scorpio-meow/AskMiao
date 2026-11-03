import asyncio
import base64
import hashlib
import ipaddress
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

from app.core.ssrf_protection import DnsPool, SSRFSafeTransport
from app.services.mcp_service import MCP_HTTP_ACCEPT, MCP_PROTOCOL_VERSION, _modern_params
from app.services.oauth_client import OAuthError, oauth_request, token_from_response

AUTHORIZATION_STATE_TTL_SECONDS = 600
MAX_PENDING_AUTHORIZATIONS = 1000
TOKEN_REFRESH_MARGIN_SECONDS = 60
PROBE_TIMEOUT_SECONDS = 15.0
CHALLENGE_PARAM_PATTERN = re.compile(r'([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^\s,"]+))')
LOOPBACK_HOSTNAMES = ("localhost",)
CLIENT_NAME = "AskMiao"
CLIENT_GRANT_TYPES = ["authorization_code", "refresh_token"]

_pending: Dict[str, Dict[str, Any]] = {}


class OAuthClientRequired(OAuthError):
    pass


class OAuthIssuerChanged(OAuthError):
    pass
_refresh_locks: Dict[int, asyncio.Lock] = {}


def _origin(url: httpx.URL) -> str:
    return f"{url.scheme}://{url.netloc.decode('ascii')}"


def is_loopback_host(host: str) -> bool:
    if host.lower() in LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _require_secure_url(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise OAuthError(f"OAuth 中繼資料缺少 {label}")
    try:
        parsed = httpx.URL(value)
    except Exception as e:
        raise OAuthError(f"OAuth 中繼資料的 {label} 不是有效網址") from e
    if not parsed.host or parsed.scheme not in ("http", "https"):
        raise OAuthError(f"OAuth 中繼資料的 {label} 必須是 http(s) 網址")
    if parsed.scheme != "https" and not is_loopback_host(parsed.host):
        raise OAuthError(f"OAuth 中繼資料的 {label} 必須使用 HTTPS")
    return value


def bearer_challenge(header: str) -> Dict[str, str]:
    return {
        key.lower(): bare or quoted.replace('\\"', '"')
        for key, quoted, bare in CHALLENGE_PARAM_PATTERN.findall(header or "")
    }


async def _probe_challenge(server_url: str, headers: Dict[str, str]) -> Dict[str, str]:
    async with httpx.AsyncClient(
        timeout=PROBE_TIMEOUT_SECONDS,
        follow_redirects=False,
        transport=SSRFSafeTransport(DnsPool.CONFIGURED_ENDPOINT),
    ) as client:
        request = client.build_request(
            "POST", server_url,
            headers={**headers, "Accept": MCP_HTTP_ACCEPT, "MCP-Protocol-Version": MCP_PROTOCOL_VERSION, "Mcp-Method": "server/discover"},
            json={"jsonrpc": "2.0", "id": 0, "method": "server/discover", "params": _modern_params({}, MCP_PROTOCOL_VERSION)},
        )
        response = await asyncio.wait_for(client.send(request, stream=True), timeout=PROBE_TIMEOUT_SECONDS)
        await response.aclose()
    return bearer_challenge(response.headers.get("www-authenticate", ""))


def _authorization_server_metadata_urls(issuer: str) -> List[str]:
    url = httpx.URL(issuer)
    origin = _origin(url)
    path = url.path.rstrip("/")
    if not path:
        return [f"{origin}/.well-known/oauth-authorization-server", f"{origin}/.well-known/openid-configuration"]
    return [
        f"{origin}/.well-known/oauth-authorization-server{path}",
        f"{origin}/.well-known/openid-configuration{path}",
        f"{origin}{path}/.well-known/openid-configuration",
    ]


async def _first_metadata(urls: List[str], issuer: Optional[str] = None) -> Dict[str, Any]:
    for url in urls:
        try:
            status, data = await oauth_request("GET", url)
        except (OAuthError, httpx.HTTPError):
            continue
        if status == 200 and data and (issuer is None or data.get("issuer") == issuer):
            return data
    raise OAuthError("找不到 OAuth 授權伺服器的中繼資料" if issuer is None else "找不到 issuer 相符的 OAuth 授權伺服器中繼資料")


async def discover(server_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    server = httpx.URL(server_url)
    challenge = await _probe_challenge(server_url, headers)
    candidates = [challenge["resource_metadata"]] if challenge.get("resource_metadata") else []
    candidates += [f"{_origin(server)}/.well-known/oauth-protected-resource{server.path.rstrip('/')}",
                   f"{_origin(server)}/.well-known/oauth-protected-resource"]
    try:
        resource = await _first_metadata(candidates)
        issuers = resource.get("authorization_servers")
        issuer = issuers[0] if isinstance(issuers, list) and issuers else _origin(server)
        resource_id = resource.get("resource") if isinstance(resource.get("resource"), str) else server_url
        scopes = resource.get("scopes_supported")
    except OAuthError:
        issuer, resource_id, scopes = _origin(server), server_url, None
    issuer = _require_secure_url(issuer, "authorization_servers")
    metadata = await _first_metadata(_authorization_server_metadata_urls(issuer), issuer)
    methods = metadata.get("code_challenge_methods_supported")
    if not isinstance(methods, list) or "S256" not in methods:
        raise OAuthError("OAuth 授權伺服器沒有宣告支援 PKCE S256")
    registration_endpoint = metadata.get("registration_endpoint")
    return {
        "issuer": issuer,
        "authorization_endpoint": _require_secure_url(metadata.get("authorization_endpoint"), "authorization_endpoint"),
        "token_endpoint": _require_secure_url(metadata.get("token_endpoint"), "token_endpoint"),
        "registration_endpoint": _require_secure_url(registration_endpoint, "registration_endpoint") if registration_endpoint else None,
        "token_endpoint_auth_methods": metadata.get("token_endpoint_auth_methods_supported") or [],
        "iss_parameter_supported": metadata.get("authorization_response_iss_parameter_supported") is True,
        "client_id_metadata_document_supported": metadata.get("client_id_metadata_document_supported") is True,
        "resource": resource_id,
        "scopes_supported": scopes if isinstance(scopes, list) else [],
        "challenged_scopes": challenge.get("scope", "").split(),
    }


def application_type(redirect_uri: str) -> str:
    return "native" if is_loopback_host(httpx.URL(redirect_uri).host) else "web"


def client_metadata_document(client_id: str, redirect_uri: str) -> Dict[str, Any]:
    return {
        "client_id": client_id,
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": CLIENT_GRANT_TYPES,
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": application_type(redirect_uri),
    }


def can_use_metadata_document(config: Dict[str, Any], client_id: str) -> bool:
    return bool(config.get("client_id_metadata_document_supported")) and httpx.URL(client_id).scheme == "https"


async def register_client(registration_endpoint: str, redirect_uri: str) -> Dict[str, Any]:
    status, data = await oauth_request("POST", _require_secure_url(registration_endpoint, "registration_endpoint"), json_body={
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": CLIENT_GRANT_TYPES,
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": application_type(redirect_uri),
    })
    if status >= 400 or not isinstance(data.get("client_id"), str):
        raise OAuthError(f"OAuth 動態註冊失敗（狀態碼 {status}）")
    return {"client_id": data["client_id"], "client_secret": data.get("client_secret") or "", "redirect_uri": redirect_uri}


def prepare_client(stored: Dict[str, Any], discovered: Dict[str, Any], redirect_uri: str, metadata_client_id: str) -> Tuple[Dict[str, Any], bool]:
    config = {**stored, **discovered, "redirect_uri": redirect_uri}
    issuer = discovered["issuer"]
    source = stored.get("client_source")
    if source == "admin":
        if stored.get("client_issuer") not in (None, issuer):
            raise OAuthIssuerChanged("MCP 伺服器的授權伺服器已變更，請在 MCP 伺服器設定中更新 OAuth client_id")
        return {**config, "client_issuer": issuer}, False
    if can_use_metadata_document(discovered, metadata_client_id):
        return {**config, "client_id": metadata_client_id, "client_secret": "", "client_source": "metadata_document", "client_issuer": issuer}, False
    reusable = (
        source == "registered" and stored.get("client_id")
        and stored.get("client_issuer") == issuer and stored.get("redirect_uri") == redirect_uri
    )
    if reusable:
        return config, False
    if not discovered.get("registration_endpoint"):
        raise OAuthClientRequired()
    return config, True


def requested_scope(config: Dict[str, Any]) -> str:
    if config.get("scope"):
        base = config["scope"].split()
    elif config.get("granted_scope"):
        base = config["granted_scope"].split()
    else:
        base = config.get("challenged_scopes") or config.get("scopes_supported") or []
    scopes = list(dict.fromkeys(base + list(config.get("step_up_scopes") or [])))
    return " ".join(scopes)


def _pkce_pair() -> Tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _prune_pending() -> None:
    now = time.time()
    for state in [s for s, entry in _pending.items() if entry["expires_at"] < now]:
        _pending.pop(state, None)
    while len(_pending) >= MAX_PENDING_AUTHORIZATIONS:
        _pending.pop(next(iter(_pending)))


def authorization_url(server_id: int, user_id: int, config: Dict[str, Any], redirect_uri: str) -> str:
    _prune_pending()
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    scope = requested_scope(config)
    _pending[state] = {
        "server_id": server_id,
        "user_id": user_id,
        "verifier": verifier,
        "redirect_uri": redirect_uri,
        "issuer": config["issuer"],
        "iss_parameter_supported": bool(config.get("iss_parameter_supported")),
        "scope": scope,
        "expires_at": time.time() + AUTHORIZATION_STATE_TTL_SECONDS,
    }
    params = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": config["resource"],
    }
    if scope:
        params["scope"] = scope
    separator = "&" if "?" in config["authorization_endpoint"] else "?"
    return f"{config['authorization_endpoint']}{separator}{urlencode(params)}"


def take_pending(state: str) -> Optional[Dict[str, Any]]:
    entry = _pending.pop(state or "", None)
    if entry is None or entry["expires_at"] < time.time():
        return None
    return entry


def issuer_matches(pending: Dict[str, Any], iss: Optional[str]) -> bool:
    if iss is None:
        return not pending["iss_parameter_supported"]
    return iss == pending["issuer"]


def _client_auth(config: Dict[str, Any], form: Dict[str, str]) -> Optional[Tuple[str, str]]:
    form["client_id"] = config["client_id"]
    secret = config.get("client_secret")
    if not secret:
        return None
    methods = config.get("token_endpoint_auth_methods") or []
    if "client_secret_post" in methods and "client_secret_basic" not in methods:
        form["client_secret"] = secret
        return None
    return config["client_id"], secret


def _tokens(data: Dict[str, Any], previous_refresh: Optional[str] = None) -> Dict[str, Any]:
    expires_in = data.get("expires_in")
    lifetime = float(expires_in) if isinstance(expires_in, (int, float)) and expires_in > 0 else None
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or previous_refresh,
        "expires_at": time.time() + lifetime if lifetime else None,
    }


async def exchange_code(config: Dict[str, Any], code: str, verifier: str, redirect_uri: str) -> Dict[str, Any]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
        "resource": config["resource"],
    }
    auth = _client_auth(config, form)
    return _tokens(token_from_response(*await oauth_request("POST", config["token_endpoint"], form=form, auth=auth)))


async def refresh(config: Dict[str, Any], tokens: Dict[str, Any]) -> Dict[str, Any]:
    if not tokens.get("refresh_token"):
        raise OAuthError("OAuth 存取權杖已過期且沒有 refresh token，請重新授權")
    form = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "resource": config["resource"]}
    auth = _client_auth(config, form)
    data = token_from_response(*await oauth_request("POST", config["token_endpoint"], form=form, auth=auth))
    return _tokens(data, tokens["refresh_token"])


def _load_tokens(server_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    from app.core.tool_secrets import decrypt_json
    from app.models import McpServer
    from app.models.database import SessionLocal

    db = SessionLocal()
    try:
        server = db.query(McpServer).filter(McpServer.id == server_id).first()
        if server is None:
            return None, None
        return decrypt_json(server.oauth_config), decrypt_json(server.oauth_tokens)
    finally:
        db.close()


def save_tokens(server_id: int, tokens: Optional[Dict[str, Any]]) -> None:
    from app.core.tool_secrets import encrypt_json
    from app.models import McpServer
    from app.models.database import SessionLocal

    db = SessionLocal()
    try:
        server = db.query(McpServer).filter(McpServer.id == server_id).first()
        if server is not None:
            server.oauth_tokens = encrypt_json(tokens)
            db.commit()
    finally:
        db.close()


def save_scope_challenge(server_id: int, scopes: List[str]) -> None:
    from app.core.tool_secrets import decrypt_json, encrypt_json
    from app.models import McpServer
    from app.models.database import SessionLocal

    db = SessionLocal()
    try:
        server = db.query(McpServer).filter(McpServer.id == server_id).first()
        config = decrypt_json(server.oauth_config) if server is not None else None
        if config:
            config["step_up_scopes"] = list(dict.fromkeys(list(config.get("step_up_scopes") or []) + scopes))
            server.oauth_config = encrypt_json(config)
            db.commit()
    finally:
        db.close()


async def access_token(server_id: int, force_refresh: bool = False) -> Optional[str]:
    lock = _refresh_locks.setdefault(server_id, asyncio.Lock())
    async with lock:
        config, tokens = await asyncio.to_thread(_load_tokens, server_id)
        if not config or not tokens or not tokens.get("access_token"):
            return None
        expires_at = tokens.get("expires_at")
        expired = isinstance(expires_at, (int, float)) and expires_at - TOKEN_REFRESH_MARGIN_SECONDS < time.time()
        if not force_refresh and not expired:
            return tokens["access_token"]
        new_tokens = await refresh(config, tokens)
        await asyncio.to_thread(save_tokens, server_id, new_tokens)
        return new_tokens["access_token"]
