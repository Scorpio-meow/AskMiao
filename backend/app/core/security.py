import os
import secrets
import hmac
import time
from collections import OrderedDict, deque
from typing import Deque, Optional
from fastapi import Header, HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from app.core.config import settings
from app.core.limits import MAX_TRACKED_ADDRESSES
from app.core.security_logging import log_unauthorized_access, log_security_event, SecurityEvent
logger = logging.getLogger(__name__)
security = HTTPBearer()
ADMIN_API_KEY = settings.ADMIN_API_KEY
if not ADMIN_API_KEY or ADMIN_API_KEY == "CHANGE_THIS_TO_A_SECURE_RANDOM_STRING":
    ADMIN_API_KEY = secrets.token_urlsafe(32)
    logger.warning("=" * 80)
    logger.warning("WARNING: ADMIN_API_KEY not set in environment!")
    logger.warning("Using temporary API key for development; set ADMIN_API_KEY in your environment.")
    logger.warning("Please set ADMIN_API_KEY in your .env file!")
    logger.warning("=" * 80)
async def verify_admin_api_key(x_api_key: Optional[str] = Header(None, description="Admin API Key")) -> bool:
    if not x_api_key:
        logger.warning("Admin API access attempt without API key")
        raise HTTPException(
            status_code=401,
            detail="Missing API Key. Please provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    if not hmac.compare_digest(x_api_key, ADMIN_API_KEY):
        logger.warning("Admin API access attempt with invalid API key")
        raise HTTPException(
            status_code=403,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    logger.info("Admin API access granted")
    return True
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
        try:
            from app.core.intrusion_detection import get_intrusion_detector
            detector = get_intrusion_detector()
        except Exception as e:
            logger.debug(f"入侵檢測系統不可用: {e}")
            detector = None
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
            if detector:
                detector.record_event(
                    'api_request',
                    client_ip,
                    details={'rate_limit_exceeded': True}
                )
            return Response(
                content="Rate limit exceeded. Please try again later.",
                status_code=429,
                headers={"Retry-After": str(self.period)}
            )
        timestamps.append(current_time)
        if detector and len(timestamps) % 10 == 0:
            detector.record_event('api_request', client_ip)
        response = await call_next(request)
        return response
def validate_api_endpoint(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if settings.ENVIRONMENT == "production" and "ngrok" in parsed.netloc:
        raise ValueError(
            "Ngrok URLs are not allowed in production environment. "
            "Please use a proper domain name."
        )
    if settings.ENVIRONMENT == "production" and parsed.scheme != "https":
        logger.warning(f"Using non-HTTPS URL in production: {url}")
    return url