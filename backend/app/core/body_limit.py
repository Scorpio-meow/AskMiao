"""請求本文大小上限（純 ASGI 中介層）。

FastAPI 會在執行驗證相依之前讀完並解析整個請求本文，因此本文上限必須在更外層處理：
- 一般請求（含所有未帶有效存取權杖的請求）最多 MAX_REQUEST_BODY_BYTES；
- 聊天送出需要較大的本文，只有帶著簽章有效的存取權杖時才放寬；
- 文件上傳只限管理員，另外要求權杖中的 is_admin 聲明。這裡只用來決定本文上限
  （降權後最多到權杖到期前仍可送出大本文），路由本身仍以資料庫判定是否為管理員。
Content-Length 超過上限時直接回 413；分塊傳輸則邊讀邊計數，超過即中止。
"""
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import HTTPException

from app.core.config import settings
from app.core.limits import (
    MAX_CHAT_REQUEST_BODY_BYTES,
    MAX_FILES_PER_UPLOAD,
    MAX_REQUEST_BODY_BYTES,
    MIB,
)


@dataclass(frozen=True)
class LargeBodyRoute:
    limit: int
    admin_only: bool


LARGE_BODY_ROUTES: Dict[str, LargeBodyRoute] = {
    "/api/chat/send": LargeBodyRoute(limit=MAX_CHAT_REQUEST_BODY_BYTES, admin_only=False),
    "/api/documents/upload": LargeBodyRoute(
        limit=MAX_FILES_PER_UPLOAD * settings.MAX_FILE_SIZE_MB * MIB + 1 * MIB, admin_only=True
    ),
}
TOO_LARGE_DETAIL = "請求內容超過大小上限"


def _access_token_claims(headers: Dict[bytes, bytes]) -> Optional[Dict[str, Any]]:
    """簽章有效且未撤銷的存取權杖回傳其聲明，否則回傳 None"""
    authorization = headers.get(b"authorization", b"").decode("latin-1")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    from app.core.jwt_auth import TokenManager

    try:
        payload = TokenManager.decode_token(token)
    except HTTPException:
        return None
    return payload if TokenManager.verify_token_type(payload, "access") else None


def body_limit_for(path: str, headers: Dict[bytes, bytes]) -> int:
    route = LARGE_BODY_ROUTES.get(path.rstrip("/"))
    if route is None:
        return MAX_REQUEST_BODY_BYTES
    claims = _access_token_claims(headers)
    if claims is None or (route.admin_only and claims.get("is_admin") is not True):
        return MAX_REQUEST_BODY_BYTES
    return route.limit


class RequestBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive: Callable[[], Awaitable[dict]], send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        limit = body_limit_for(scope.get("path", ""), headers)
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = -1
            if declared < 0 or declared > limit:
                await _send_413(send)
                return

        received = 0
        response_started = False

        async def limited_receive() -> dict:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail=TOO_LARGE_DETAIL)
            return message

        async def tracking_send(message: dict) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except HTTPException as exc:
            if exc.status_code != 413 or response_started:
                raise
            await _send_413(send)


async def _send_413(send) -> None:
    body = json.dumps({"detail": TOO_LARGE_DETAIL}, ensure_ascii=False).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"connection", b"close"),
        ],
    })
    await send({"type": "http.response.body", "body": body})
