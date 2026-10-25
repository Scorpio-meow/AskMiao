import asyncio
import base64
import hashlib
import json
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote_plus

import httpx

from app.core.ssrf_protection import DnsPool, SSRFSafeTransport, send_following_redirects

MAX_OAUTH_RESPONSE_BYTES = 256 * 1024
OAUTH_TIMEOUT_SECONDS = 15.0
OAUTH_MAX_REDIRECTS = 3
TOKEN_EXPIRY_MARGIN_SECONDS = 30
MAX_CACHED_TOKENS = 1000

_token_cache: Dict[str, Tuple[str, float]] = {}
_token_locks: Dict[str, asyncio.Lock] = {}


class OAuthError(RuntimeError):
    pass


async def _read_json(response: httpx.Response) -> Dict[str, Any]:
    chunks = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_OAUTH_RESPONSE_BYTES:
            raise OAuthError("OAuth 端點的回應超過大小上限")
        chunks.append(chunk)
    try:
        data = json.loads(b"".join(chunks) or b"{}")
    except json.JSONDecodeError as e:
        raise OAuthError(f"OAuth 端點回傳的不是 JSON（狀態碼 {response.status_code}）") from e
    if not isinstance(data, dict):
        raise OAuthError("OAuth 端點回傳的 JSON 不是物件")
    return data


async def oauth_request(
    method: str,
    url: str,
    *,
    form: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    auth: Optional[Tuple[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, Dict[str, Any]]:
    async def perform() -> Tuple[int, Dict[str, Any]]:
        async with httpx.AsyncClient(
            timeout=OAUTH_TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=SSRFSafeTransport(DnsPool.CONFIGURED_ENDPOINT),
        ) as client:
            request_headers = {"Accept": "application/json", **(headers or {})}
            if auth is not None:
                credentials = f"{quote_plus(auth[0])}:{quote_plus(auth[1])}".encode("utf-8")
                request_headers["Authorization"] = f"Basic {base64.b64encode(credentials).decode('ascii')}"
            request = client.build_request(method, url, data=form, json=json_body, headers=request_headers)
            response = await send_following_redirects(client, request, OAUTH_MAX_REDIRECTS, allow_cross_origin=False)
            try:
                return response.status_code, await _read_json(response)
            finally:
                await response.aclose()

    return await asyncio.wait_for(perform(), timeout=OAUTH_TIMEOUT_SECONDS)


def token_from_response(status: int, data: Dict[str, Any]) -> Dict[str, Any]:
    if status >= 400 or "error" in data:
        raise OAuthError(f"OAuth 權杖端點拒絕請求：{data.get('error', status)}")
    if not isinstance(data.get("access_token"), str) or not data["access_token"]:
        raise OAuthError("OAuth 權杖端點沒有回傳 access_token")
    return data


def _cache_key(config: Dict[str, Any]) -> str:
    raw = json.dumps(
        [config.get("token_url"), config.get("client_id"), config.get("client_secret"), config.get("scope"), config.get("client_auth")],
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def invalidate_client_credentials_token(config: Dict[str, Any]) -> None:
    _token_cache.pop(_cache_key(config), None)


async def client_credentials_token(config: Dict[str, Any]) -> str:
    token_url = str(config.get("token_url") or "")
    client_id = str(config.get("client_id") or "")
    client_secret = str(config.get("client_secret") or "")
    if not token_url or not client_id or not client_secret:
        raise OAuthError("OAuth2 client credentials 需要 token_url、client_id 與 client_secret")
    key = _cache_key(config)
    cached = _token_cache.get(key)
    if cached and cached[1] > time.time():
        return cached[0]
    lock = _token_locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _token_cache.get(key)
        if cached and cached[1] > time.time():
            return cached[0]
        form = {"grant_type": "client_credentials"}
        if config.get("scope"):
            form["scope"] = str(config["scope"])
        auth = None
        if config.get("client_auth") == "post":
            form.update({"client_id": client_id, "client_secret": client_secret})
        else:
            auth = (client_id, client_secret)
        data = token_from_response(*await oauth_request("POST", token_url, form=form, auth=auth))
        expires_in = data.get("expires_in")
        lifetime = float(expires_in) if isinstance(expires_in, (int, float)) and expires_in > 0 else 300.0
        if len(_token_cache) >= MAX_CACHED_TOKENS:
            _token_cache.clear()
        _token_cache[key] = (data["access_token"], time.time() + max(lifetime - TOKEN_EXPIRY_MARGIN_SECONDS, 1.0))
        return data["access_token"]
