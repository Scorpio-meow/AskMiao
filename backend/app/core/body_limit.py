"""請求本文大小上限（純 ASGI 中介層）。

FastAPI 會在執行驗證相依之前讀完並解析整個請求本文，因此本文上限必須在更外層處理：
- 一般請求（含所有未帶有效存取權杖的請求）最多 MAX_REQUEST_BODY_BYTES；
- 聊天送出與文件上傳需要較大的本文，只有帶著簽章有效的存取權杖時才放寬。
Content-Length 超過上限時直接回 413；分塊傳輸則邊讀邊計數，超過即中止。
"""
import json
from typing import Awaitable, Callable, Dict

from fastapi import HTTPException

from app.core.config import settings
from app.core.limits import (
    MAX_CHAT_REQUEST_BODY_BYTES,
    MAX_FILES_PER_UPLOAD,
    MAX_REQUEST_BODY_BYTES,
    MIB,
)

LARGE_BODY_ROUTES: Dict[str, int] = {
    "/api/chat/send": MAX_CHAT_REQUEST_BODY_BYTES,
    "/api/documents/upload": MAX_FILES_PER_UPLOAD * settings.MAX_FILE_SIZE_MB * MIB + 1 * MIB,
}
TOO_LARGE_DETAIL = "請求內容超過大小上限"


def _has_valid_access_token(headers: Dict[bytes, bytes]) -> bool:
    authorization = headers.get(b"authorization", b"").decode("latin-1")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    from app.core.jwt_auth import TokenManager

    try:
        payload = TokenManager.decode_token(token)
    except HTTPException:
        return False
    return TokenManager.verify_token_type(payload, "access")


def body_limit_for(path: str, headers: Dict[bytes, bytes]) -> int:
    route_limit = LARGE_BODY_ROUTES.get(path.rstrip("/"))
    if route_limit is not None and _has_valid_access_token(headers):
        return route_limit
    return MAX_REQUEST_BODY_BYTES


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
