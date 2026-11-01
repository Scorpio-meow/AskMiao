import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, quote_plus
from xml.sax.saxutils import escape

from app.services.openapi_parser import media_family

QUERY_RESERVED_SAFE = ":/?@!$'()*,;[]"


def scalar_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _object_pairs(value: Dict[str, Any]) -> List[Tuple[str, str]]:
    return [(str(k), scalar_text(v)) for k, v in value.items() if v is not None]


def _enc(text: str) -> str:
    return quote(text, safe="")


@dataclass
class RequestParts:
    path_values: Dict[str, str] = field(default_factory=dict)
    query: List[Tuple[str, str]] = field(default_factory=list)
    querystring: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: List[str] = field(default_factory=list)
    body: Dict[str, Any] = field(default_factory=dict)
    whole_body: Any = None
    has_whole_body: bool = False
    body_specs: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def serialize_path(name: str, value: Any, style: str, explode: bool) -> str:
    def element(item: Any) -> str:
        text = scalar_text(item)
        if text in (".", ".."):
            raise ValueError("路徑參數不可為 . 或 ..")
        return _enc(text)

    if isinstance(value, list):
        items = [element(v) for v in value]
        if style == "label":
            result = "." + ("." if explode else ",").join(items)
        elif style == "matrix":
            result = "".join(f";{name}={v}" for v in items) if explode else f";{name}=" + ",".join(items)
        else:
            result = ",".join(items)
    elif isinstance(value, dict):
        pairs = [(_enc(k), element(v)) for k, v in _object_pairs(value)]
        if style == "label":
            result = "." + (".".join(f"{k}={v}" for k, v in pairs) if explode else ",".join(f"{k},{v}" for k, v in pairs))
        elif style == "matrix":
            result = "".join(f";{k}={v}" for k, v in pairs) if explode else f";{name}=" + ",".join(f"{k},{v}" for k, v in pairs)
        else:
            result = ",".join(f"{k}={v}" if explode else f"{k},{v}" for k, v in pairs)
    else:
        text = element(value)
        if style == "label":
            result = f".{text}"
        elif style == "matrix":
            result = f";{name}={text}" if text else f";{name}"
        else:
            result = text
    if result in (".", ".."):
        raise ValueError("路徑參數不可為 . 或 ..")
    return result


def serialize_query(name: str, value: Any, spec: Dict[str, Any]) -> List[Tuple[str, str]]:
    safe = QUERY_RESERVED_SAFE if spec.get("allow_reserved") else ""

    def enc(text: str) -> str:
        return quote(text, safe=safe)

    key = _enc(name)
    if spec.get("content_type"):
        return [(key, enc(json.dumps(value, ensure_ascii=False, separators=(",", ":")) if media_family(spec["content_type"]) == "json" else scalar_text(value)))]
    style = spec.get("style", "form")
    explode = spec.get("explode", style == "form")
    delimiter = {"spaceDelimited": "%20", "pipeDelimited": "%7C", "tabDelimited": "%09"}.get(style)
    if isinstance(value, list):
        items = [enc(scalar_text(v)) for v in value if v is not None]
        if delimiter:
            return [(key, delimiter.join(items))]
        if explode:
            return [(key, item) for item in items]
        return [(key, ",".join(items))]
    if isinstance(value, dict):
        pairs = [(k, enc(v)) for k, v in _object_pairs(value)]
        if style == "deepObject":
            return [(f"{key}[{_enc(k)}]", v) for k, v in pairs]
        if delimiter:
            return [(key, delimiter.join(f"{_enc(k)}{delimiter}{v}" for k, v in pairs))]
        if explode:
            return [(_enc(k), v) for k, v in pairs]
        return [(key, ",".join(f"{_enc(k)},{v}" for k, v in pairs))]
    if value is None:
        return []
    return [(key, enc(scalar_text(value)))]


def serialize_header(value: Any, spec: Dict[str, Any]) -> str:
    if spec.get("content_type"):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if media_family(spec["content_type"]) == "json" else scalar_text(value)
    if isinstance(value, list):
        return ",".join(scalar_text(v) for v in value)
    if isinstance(value, dict):
        explode = spec.get("explode", False)
        return ",".join(f"{k}={v}" if explode else f"{k},{v}" for k, v in _object_pairs(value))
    return scalar_text(value)


def serialize_cookie(name: str, value: Any, spec: Dict[str, Any]) -> List[str]:
    raw = spec.get("style") == "cookie"

    def enc(text: str) -> str:
        return text if raw else quote(text, safe="")

    if spec.get("content_type"):
        return [f"{name}={enc(serialize_header(value, spec))}"]
    explode = spec.get("explode", True)
    if isinstance(value, list):
        items = [enc(scalar_text(v)) for v in value]
        return [f"{name}={v}" for v in items] if explode else [f"{name}=" + ",".join(items)]
    if isinstance(value, dict):
        pairs = [(k, enc(v)) for k, v in _object_pairs(value)]
        return [f"{k}={v}" for k, v in pairs] if explode else [f"{name}=" + ",".join(f"{k},{v}" for k, v in pairs)]
    return [f"{name}={enc(scalar_text(value))}"]


def serialize_querystring(value: Any, spec: Dict[str, Any]) -> str:
    content_type = spec.get("content_type") or "application/x-www-form-urlencoded"
    family = media_family(content_type)
    if family == "form":
        if not isinstance(value, dict):
            raise ValueError("整段查詢字串的參數必須是物件")
        pairs: List[Tuple[str, str]] = []
        for k, v in value.items():
            pairs.extend(serialize_query(str(k), v, {"style": "form", "explode": True}))
        return "&".join(f"{k}={v}" for k, v in pairs)
    if family == "json":
        return _enc(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return _enc(scalar_text(value))


def build_query(fixed: List[Tuple[str, str]], parts: RequestParts) -> str:
    pairs = [f"{_enc(k)}={_enc(v)}" for k, v in fixed] + [f"{k}={v}" for k, v in parts.query]
    if parts.querystring:
        pairs.append(parts.querystring)
    return "&".join(pairs)


def _form_pairs(body: Dict[str, Any], specs: Dict[str, Dict[str, Any]]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for name, value in body.items():
        spec = specs.get(name, {})
        if value is None:
            continue
        if spec.get("content_type"):
            pairs.append((name, json.dumps(value, ensure_ascii=False) if media_family(spec["content_type"]) == "json" else scalar_text(value)))
            continue
        style = spec.get("style", "form")
        explode = spec.get("explode", style == "form")
        if isinstance(value, list):
            if explode and style == "form":
                pairs.extend((name, scalar_text(v)) for v in value)
            else:
                delimiter = {"spaceDelimited": " ", "pipeDelimited": "|", "tabDelimited": "\t"}.get(style, ",")
                pairs.append((name, delimiter.join(scalar_text(v) for v in value)))
        elif isinstance(value, dict):
            if style == "deepObject":
                pairs.extend((f"{name}[{k}]", v) for k, v in _object_pairs(value))
            elif explode:
                pairs.extend(_object_pairs(value))
            else:
                pairs.append((name, ",".join(f"{k},{v}" for k, v in _object_pairs(value))))
        else:
            pairs.append((name, scalar_text(value)))
    return pairs


def _xml(name: str, value: Any) -> str:
    tag = "".join(ch if ch.isalnum() or ch in "_-." else "_" for ch in str(name)) or "item"
    if isinstance(value, dict):
        return f"<{tag}>" + "".join(_xml(k, v) for k, v in value.items()) + f"</{tag}>"
    if isinstance(value, list):
        return "".join(_xml(tag, v) for v in value)
    return f"<{tag}>{escape(scalar_text(value))}</{tag}>"


def encode_body(content_type: str, body: Any, specs: Dict[str, Dict[str, Any]], xml_root: Optional[str]) -> Dict[str, Any]:
    family = media_family(content_type)
    if family == "json":
        return {"content": json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), "headers": {"Content-Type": content_type}}
    if family in ("form", "multipart") and not isinstance(body, dict):
        raise ValueError(f"{content_type} 的請求主體必須是物件")
    if family == "form":
        encoded = "&".join(f"{quote_plus(k)}={quote_plus(v)}" for k, v in _form_pairs(body, specs))
        return {"content": encoded.encode("ascii"), "headers": {"Content-Type": content_type}}
    if family == "multipart":
        files: List[Tuple[str, Tuple]] = []
        for name, value in body.items():
            spec = specs.get(name, {})
            part_type = spec.get("content_type")
            if value is None:
                continue
            if isinstance(value, list) and not part_type:
                files.extend((name, (None, scalar_text(v))) for v in value)
            elif isinstance(value, (dict, list)):
                files.append((name, (None, json.dumps(value, ensure_ascii=False), part_type or "application/json")))
            elif part_type:
                files.append((name, (None, scalar_text(value), part_type)))
            else:
                files.append((name, (None, scalar_text(value))))
        return {"files": files}
    if family == "xml":
        text = body if isinstance(body, str) else _xml(xml_root or "root", body)
        return {"content": text.encode("utf-8"), "headers": {"Content-Type": content_type}}
    text = body if isinstance(body, str) else scalar_text(body)
    return {"content": text.encode("utf-8"), "headers": {"Content-Type": content_type}}
