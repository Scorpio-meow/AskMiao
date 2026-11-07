import contextvars
import re
import uuid
from dataclasses import dataclass
from typing import Optional
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{7,63}")
REQUEST_ID_HEX_CHARS = 16
NO_REQUEST_ID = "-"
@dataclass
class RequestContext:
    request_id: str
    user_id: Optional[int] = None
_current_request: contextvars.ContextVar[Optional[RequestContext]] = contextvars.ContextVar("current_request", default=None)
def resolve_request_id(header_value: Optional[str]) -> str:
    if header_value and REQUEST_ID_PATTERN.fullmatch(header_value):
        return header_value
    return uuid.uuid4().hex[:REQUEST_ID_HEX_CHARS]
def begin_request(request_id: str) -> contextvars.Token:
    return _current_request.set(RequestContext(request_id))
def end_request(token: contextvars.Token) -> None:
    _current_request.reset(token)
def current_request() -> Optional[RequestContext]:
    return _current_request.get()
def current_request_id() -> str:
    context = _current_request.get()
    return context.request_id if context else NO_REQUEST_ID
def bind_request_user(user_id: int) -> None:
    context = _current_request.get()
    if context is not None:
        context.user_id = user_id