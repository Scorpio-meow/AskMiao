import time
from collections import OrderedDict, deque
from typing import Deque
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from app.core.limits import MAX_TRACKED_ADDRESSES
logger = logging.getLogger(__name__)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if "Server" in response.headers:
            del response.headers["Server"]
        return response
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, calls: int, period: int):
        super().__init__(app)
        self.calls = calls
        self.period = period
        # 以位址分組的請求時間；追蹤的位址數有上限，最久未活動的先淘汰，大量來源位址不會讓記憶體持續成長
        self.clients: "OrderedDict[str, Deque[float]]" = OrderedDict()
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        current_time = time.time()
        timestamps = self.clients.get(client_ip)
        if timestamps is None:
            timestamps = deque()
            self.clients[client_ip] = timestamps
            while len(self.clients) > MAX_TRACKED_ADDRESSES:
                self.clients.popitem(last=False)
        else:
            self.clients.move_to_end(client_ip)
        while timestamps and current_time - timestamps[0] >= self.period:
            timestamps.popleft()
        if len(timestamps) >= self.calls:
            logger.warning(f"速率限制: {client_ip} 超過限制 ({len(timestamps)} requests)")
            return Response(
                content="Rate limit exceeded. Please try again later.",
                status_code=429,
                headers={"Retry-After": str(self.period)}
            )
        timestamps.append(current_time)
        response = await call_next(request)
        return response
