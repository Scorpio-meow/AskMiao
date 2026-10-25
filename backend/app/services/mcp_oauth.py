import asyncio
import base64
import hashlib
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

from app.core.ssrf_protection import DnsPool, SSRFSafeTransport
from app.services.oauth_client import OAuthError, oauth_request, token_from_response

AUTHORIZATION_STATE_TTL_SECONDS = 600
MAX_PENDING_AUTHORIZATIONS = 1000
TOKEN_REFRESH_MARGIN_SECONDS = 60
PROBE_TIMEOUT_SECONDS = 15.0
RESOURCE_METADATA_PATTERN = re.compile(r'resource_metadata="([^"]+)"')

_pending: Dict[str, Dict[str, Any]] = {}


class OAuthClientRequired(OAuthError):
    pass
_refresh_locks: Dict[int, asyncio.Lock] = {}


def _origin(url: httpx.URL) -> str:
    return f"{url.scheme}://{url.netloc.decode('ascii')}"


def _require_web_url(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise OAuthError(f"OAuth 中繼資料缺少 {label}")
    try:
        parsed = httpx.URL(value)
    except Exception as e:
        raise OAuthError(f"OAuth 中繼資料的 {label} 不是有效網址") from e
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise OAuthError(f"OAuth 中繼資料的 {label} 必須是 http(s) 網址")
    return value


async def _probe_resource_metadata_url(server_url: str, headers: Dict[str, str]) -> Optional[str]:
    async with httpx.AsyncClient(
        timeout=PROBE_TIMEOUT_SECONDS,
        follow_redirects=False,
        transport=SSRFSafeTransport(DnsPool.CONFIGURED_ENDPOINT),
    ) as client:
        request = client.build_request(
            "POST", server_url,
            headers={**headers, "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 0, "method": "ping"},
        )
        response = await asyncio.wait_for(client.send(request, stream=True), timeout=PROBE_TIMEOUT_SECONDS)
        await response.aclose()
    match = RESOURCE_METADATA_PATTERN.search(response.headers.get("www-authenticate", ""))
    return match.group(1) if match else None


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


async def _first_metadata(urls: List[str]) -> Dict[str, Any]:
    for url in urls:
        try:
            status, data = await oauth_request("GET", url)
        except (OAuthError, httpx.HTTPError):
            continue
        if status == 200 and data:
            return data
    raise OAuthError("找不到 OAuth 授權伺服器的中繼資料")


async def discover(server_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    server = httpx.URL(server_url)
    metadata_url = await _probe_resource_metadata_url(server_url, headers)
    candidates = [metadata_url] if metadata_url else []
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
    metadata = await _first_metadata(_authorization_server_metadata_urls(_require_web_url(issuer, "authorization_servers")))
    methods = metadata.get("code_challenge_methods_supported")
    if isinstance(methods, list) and "S256" not in methods:
        raise OAuthError("OAuth 授權伺服器不支援 PKCE S256")
    return {
        "authorization_endpoint": _require_web_url(metadata.get("authorization_endpoint"), "authorization_endpoint"),
        "token_endpoint": _require_web_url(metadata.get("token_endpoint"), "token_endpoint"),
        "registration_endpoint": metadata.get("registration_endpoint"),
        "token_endpoint_auth_methods": metadata.get("token_endpoint_auth_methods_supported") or [],
        "resource": resource_id,
        "scopes_supported": scopes if isinstance(scopes, list) else [],
    }


async def register_client(registration_endpoint: str, redirect_uri: str) -> Dict[str, Any]:
    status, data = await oauth_request("POST", _require_web_url(registration_endpoint, "registration_endpoint"), json_body={
        "client_name": "AskMiao",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    })
    if status >= 400 or not isinstance(data.get("client_id"), str):
        raise OAuthError(f"OAuth 動態註冊失敗（狀態碼 {status}）")
    return {"client_id": data["client_id"], "client_secret": data.get("client_secret") or "", "redirect_uri": redirect_uri}


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
    _pending[state] = {
        "server_id": server_id,
        "user_id": user_id,
        "verifier": verifier,
        "redirect_uri": redirect_uri,
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
    scope = config.get("scope") or " ".join(config.get("scopes_supported") or [])
    if scope:
        params["scope"] = scope
    separator = "&" if "?" in config["authorization_endpoint"] else "?"
    return f"{config['authorization_endpoint']}{separator}{urlencode(params)}"


def take_pending(state: str) -> Optional[Dict[str, Any]]:
    entry = _pending.pop(state or "", None)
    if entry is None or entry["expires_at"] < time.time():
        return None
    return entry


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
