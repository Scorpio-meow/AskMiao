import logging
import time
from urllib.parse import parse_qsl
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from app.core.request_context import REQUEST_ID_HEADER, begin_request, current_request, end_request, resolve_request_id
from app.core.security_logging import log_fields
ACCESS_LOG_PATH_PREFIX = "/api"
SERVER_ERROR_STATUS = 500
NO_REQUEST_VALUE = "-"
access_logger = logging.getLogger("app.access")
def _query_keys(query_string: bytes) -> str:
    keys = dict.fromkeys(key for key, _ in parse_qsl(query_string.decode("latin-1"), keep_blank_values=True))
    return ",".join(keys)
class AccessLogMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        token = begin_request(request_id)
        context = current_request()
        started = time.perf_counter()
        status_code = None
        response_bytes = 0
        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_bytes
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            elif message["type"] == "http.response.body":
                response_bytes += len(message.get("body", b""))
            await send(message)
        error = None
        try:
            await self.app(scope, receive, send_with_request_id)
        except BaseException as exc:
            error = type(exc).__name__
            raise
        finally:
            if scope["path"].startswith(ACCESS_LOG_PATH_PREFIX):
                status = status_code if status_code is not None else SERVER_ERROR_STATUS
                client = scope.get("client")
                access_logger.log(
                    logging.WARNING if status >= SERVER_ERROR_STATUS or error else logging.INFO,
                    "%s",
                    log_fields(
                        method=scope["method"],
                        path=scope["path"],
                        query_keys=_query_keys(scope["query_string"]) or None,
                        status=status,
                        duration_ms=round((time.perf_counter() - started) * 1000),
                        bytes=response_bytes,
                        ip=client[0] if client else NO_REQUEST_VALUE,
                        user=context.user_id if context.user_id is not None else NO_REQUEST_VALUE,
                        error=error,
                    ),
                )
            end_request(token)