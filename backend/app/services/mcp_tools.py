import base64
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from app.services.openapi_documents import SpecDocuments
from app.services.openapi_schema import SchemaNormalizer
MCP_TOOL_SCHEMA_URI = "urn:askmiao:mcp-tool-input"
LEGACY_SCHEMA_DIALECT_MARKERS = ("draft-04", "draft-06", "draft-07")
UNRESOLVED_REF_WARNING = "無法解析之參照"
HEADER_TOKEN_PATTERN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
HEADER_PARAM_TYPES = ("string", "integer", "boolean")
BASE64_SENTINEL_PREFIX = "=?base64?"
BASE64_SENTINEL_SUFFIX = "?="
BINARY_CONTENT_TYPES = ("image", "audio")
OMITTED_BINARY_NOTE = "二進位內容不提供給模型"
RESOURCE_LINK_FIELDS = ("type", "uri", "name", "title", "description", "mimeType")
RESOURCE_TEXT_FIELDS = ("uri", "mimeType", "text")
HeaderParameter = Tuple[Tuple[str, ...], str]
class McpToolDefinitionError(ValueError):
    pass
def _uses_json_schema_2020(schema: Dict[str, Any]) -> bool:
    dialect = schema.get("$schema")
    return not (isinstance(dialect, str) and any(marker in dialect for marker in LEGACY_SCHEMA_DIALECT_MARKERS))
def function_parameters(input_schema: Any) -> Dict[str, Any]:
    if input_schema is None:
        return {"type": "object", "properties": {}}
    if not isinstance(input_schema, dict):
        raise McpToolDefinitionError("inputSchema 必須是 JSON Schema 物件")
    docs = SpecDocuments(root=input_schema, root_uri=MCP_TOOL_SCHEMA_URI, retrieval_url=None)
    docs.register(MCP_TOOL_SCHEMA_URI, input_schema)
    normalizer = SchemaNormalizer(docs, _uses_json_schema_2020(input_schema), for_request=True)
    parameters = normalizer.normalize(input_schema, MCP_TOOL_SCHEMA_URI)
    if any(warning.startswith(UNRESOLVED_REF_WARNING) for warning in normalizer.warnings):
        raise McpToolDefinitionError("inputSchema 含無法在工具定義內解析的 $ref")
    if parameters.get("type") != "object":
        return {"type": "object", "properties": {}}
    return {"properties": {}, **parameters}
def header_parameters(input_schema: Any) -> List[HeaderParameter]:
    found: List[HeaderParameter] = []
    seen = set()
    stack: List[Tuple[Any, Tuple[str, ...], bool]] = [(input_schema, (), True)]
    while stack:
        node, path, reachable = stack.pop()
        if isinstance(node, list):
            stack.extend((item, path, False) for item in node)
            continue
        if not isinstance(node, dict):
            continue
        if "x-mcp-header" in node:
            name = node["x-mcp-header"]
            if not reachable or not path:
                raise McpToolDefinitionError("x-mcp-header 只能放在從根結構只經 properties 到達的參數上")
            if not isinstance(name, str) or not HEADER_TOKEN_PATTERN.fullmatch(name):
                raise McpToolDefinitionError("x-mcp-header 的值必須是 HTTP 欄位名稱")
            if node.get("type") not in HEADER_PARAM_TYPES:
                raise McpToolDefinitionError("x-mcp-header 只能用在 string、integer 或 boolean 參數")
            if name.lower() in seen:
                raise McpToolDefinitionError("x-mcp-header 的值不可重複")
            seen.add(name.lower())
            found.append((path, name))
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                stack.extend((child, path + (prop,), reachable) for prop, child in value.items())
            elif isinstance(value, (dict, list)):
                stack.append((value, path, False))
    return found
def _is_plain_header_value(value: str) -> bool:
    return (
        value == value.strip(" \t")
        and all(char == "\t" or " " <= char <= "~" for char in value)
        and not (value.startswith(BASE64_SENTINEL_PREFIX) and value.endswith(BASE64_SENTINEL_SUFFIX))
    )
def encode_header_value(value: str) -> str:
    if _is_plain_header_value(value):
        return value
    return f"{BASE64_SENTINEL_PREFIX}{base64.b64encode(value.encode('utf-8')).decode('ascii')}{BASE64_SENTINEL_SUFFIX}"
def _header_text(value: Any) -> Optional[str]:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str):
        return value
    return None
def param_headers(parameters: List[HeaderParameter], arguments: Dict[str, Any]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for path, name in parameters:
        value: Any = arguments
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        text = _header_text(value)
        if text is not None:
            headers[f"Mcp-Param-{name}"] = encode_header_value(text)
    return headers
def _content_item(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    kind = item.get("type")
    if kind == "text":
        return {"type": "text", "text": item["text"] if isinstance(item.get("text"), str) else ""}
    if kind in BINARY_CONTENT_TYPES:
        return {"type": kind, "mimeType": item.get("mimeType"), "omitted": OMITTED_BINARY_NOTE}
    if kind == "resource_link":
        return {key: item[key] for key in RESOURCE_LINK_FIELDS if key in item}
    if kind == "resource" and isinstance(item.get("resource"), dict):
        return {"type": "resource", "resource": resource_contents(item["resource"])}
    return None
def resource_contents(resource: Dict[str, Any]) -> Dict[str, Any]:
    shaped = {key: resource[key] for key in RESOURCE_TEXT_FIELDS if key in resource}
    if "blob" in resource:
        shaped["omitted"] = OMITTED_BINARY_NOTE
    return shaped
def model_content(items: Any) -> List[Dict[str, Any]]:
    shaped = [_content_item(item) for item in items] if isinstance(items, list) else []
    return [item for item in shaped if item is not None]
def _same_json(text: str, value: Any) -> bool:
    try:
        return json.loads(text) == value
    except (TypeError, ValueError):
        return False
def tool_result(result: Dict[str, Any]) -> Dict[str, Any]:
    content = model_content(result.get("content"))
    shaped: Dict[str, Any] = {"is_success": not result.get("isError", False), "content": content}
    if "structuredContent" in result:
        structured = result["structuredContent"]
        shaped["content"] = [item for item in content if not (item["type"] == "text" and _same_json(item["text"], structured))]
        shaped["structuredContent"] = structured
    return shaped
def prompt_messages(messages: Any) -> List[Dict[str, Any]]:
    shaped = []
    for message in messages if isinstance(messages, list) else []:
        if isinstance(message, dict):
            content = _content_item(message.get("content"))
            if content is not None:
                shaped.append({"role": message.get("role"), "content": content})
    return shaped