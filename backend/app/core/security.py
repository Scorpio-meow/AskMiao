import asyncio
import time
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from app.core.limits import MAX_RATE_LIMIT_LOGGED_PATHS, MAX_TRACKED_ADDRESSES
from app.core.security_logging import log_fields, truncate_log_value
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
@dataclass
class _BlockedWindow:
    started: float
    blocked: int = 0
    paths: Counter = field(default_factory=Counter)
    def record(self, path: str) -> None:
        self.blocked += 1
        path = truncate_log_value(path)
        if path in self.paths or len(self.paths) < MAX_RATE_LIMIT_LOGGED_PATHS:
            self.paths[path] += 1
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, calls: int, period: int):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.clients: "OrderedDict[str, Deque[float]]" = OrderedDict()
        self.blocked_windows: Dict[str, _BlockedWindow] = {}
    def _record_block(self, client_ip: str, path: str, current_time: float) -> None:
        window = self.blocked_windows.get(client_ip)
        if window is not None and current_time - window.started >= self.period:
            self.close_blocked_window(client_ip)
            window = None
        if window is None:
            window = self.blocked_windows[client_ip] = _BlockedWindow(current_time)
            logger.warning("速率限制開始擋下請求 %s", log_fields(
                ip=client_ip, path=path, limit=self.calls, period_s=self.period
            ))
            asyncio.get_running_loop().call_later(self.period, self._expire_blocked_window, client_ip, window)
        window.record(path)
    def _expire_blocked_window(self, client_ip: str, window: _BlockedWindow) -> None:
        if self.blocked_windows.get(client_ip) is window:
            self.close_blocked_window(client_ip)
    def close_blocked_window(self, client_ip: str) -> None:
        window = self.blocked_windows.pop(client_ip, None)
        if window is None:
            return
        logger.warning("速率限制視窗結束 %s", log_fields(
            ip=client_ip,
            blocked=window.blocked,
            period_s=self.period,
            paths=",".join(f"{path}×{count}" for path, count in window.paths.most_common()),
        ))
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
            self._record_block(client_ip, request.url.path, current_time)
            return Response(
                content="Rate limit exceeded. Please try again later.",
                status_code=429,
                headers={"Retry-After": str(self.period)}
            )
        timestamps.append(current_time)
        response = await call_next(request)
        return response