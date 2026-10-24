import datetime
import math
from typing import Any, Iterable, Optional

from app.core.limits import MAX_RECORD_LABEL_CHARS

from .noise import clean_noise

BINARY_PLACEHOLDER = "[BINARY_OMITTED]"
LINK_PREFIXES = ("http://", "https://")


def is_scalar(value: Any) -> bool:
    return not isinstance(value, (dict, list, tuple, set, frozenset))


def render_scalar(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None and value.time() == datetime.time(0, 0):
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return BINARY_PLACEHOLDER
    text = clean_noise(str(value).strip())
    return text or None


def is_link(text: str) -> bool:
    return text.lower().startswith(LINK_PREFIXES)


def make_label(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    collapsed = " ".join(text.split())
    if not collapsed:
        return None
    if len(collapsed) > MAX_RECORD_LABEL_CHARS:
        return collapsed[:MAX_RECORD_LABEL_CHARS] + "…"
    return collapsed


def unique_links(links: Iterable[str]) -> tuple:
    return tuple(dict.fromkeys(links))
