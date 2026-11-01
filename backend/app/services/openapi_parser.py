import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from app.core.error_response import SafeClientError
from app.core.limits import MAX_TOOL_NAME_CHARS
from app.models import OAUTH2_CLIENT_CREDENTIALS
from app.services.openapi_documents import (
    SpecDocuments,
    build_documents,
    document_base,
    is_remote_uri,
    join_uri,
    load_source,
    load_yaml_without_aliases,
)
from app.services.openapi_overlay import apply_overlay, is_overlay
from app.services.openapi_schema import SchemaNormalizer

TOOL_NAME_HASH_CHARS = 8
SWAGGER_METHODS = ("get", "put", "post", "delete", "options", "head", "patch")
OAS3_METHODS = SWAGGER_METHODS + ("trace",)
OAS32_METHODS = OAS3_METHODS + ("query",)
HTTP_TOKEN_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
OPENAPI_VERSION_PATTERN = re.compile(r"^3\.(?P<minor>[0-2])(\.\d+)?(-[0-9A-Za-z.-]+)?$")
JSON_MEDIA_PATTERN = re.compile(r"^application/(json|[\w.+-]+\+json)$|^text/json$")
FORM_MEDIA = "application/x-www-form-urlencoded"
MULTIPART_MEDIA = "multipart/form-data"
COLLECTION_FORMAT_STYLES = {
    "csv": ("form", False),
    "ssv": ("spaceDelimited", False),
    "tsv": ("tabDelimited", False),
    "pipes": ("pipeDelimited", False),
    "multi": ("form", True),
}
SWAGGER_SCHEMA_KEYS = (
    "type", "format", "items", "enum", "default", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems", "multipleOf",
)
INTERACTIVE_OAUTH_FLOWS = ("authorizationCode", "implicit", "password", "deviceAuthorization", "accessCode")
IGNORED_HEADER_PARAMETERS = ("accept", "content-type", "authorization")

__all__ = ["OpenApiParser", "fit_tool_name", "load_yaml_without_aliases", "media_family"]


def fit_tool_name(name: str) -> str:
    if len(name) <= MAX_TOOL_NAME_CHARS:
        return name
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:TOOL_NAME_HASH_CHARS]
    return f"{name[:MAX_TOOL_NAME_CHARS - TOOL_NAME_HASH_CHARS - 1]}_{digest}"


def media_family(media_type: str) -> str:
    base = media_type.split(";", 1)[0].strip().lower()
    if base in ("*/*", "application/*") or JSON_MEDIA_PATTERN.match(base):
        return "json"
    if base == FORM_MEDIA:
        return "form"
    if base == MULTIPART_MEDIA or base.startswith("multipart/"):
        return "multipart"
    if base in ("application/xml", "text/xml") or base.endswith("+xml"):
        return "xml"
    if base.startswith("text/"):
        return "text"
    return "binary"


def _media_rank(media_type: str) -> int:
    return ["json", "form", "multipart", "text", "xml", "binary"].index(media_family(media_type))


def _concrete_media(media_type: str) -> str:
    base = media_type.split(";", 1)[0].strip()
    return "application/json" if base in ("*/*", "application/*") else base


def detect_spec_version(spec: Dict[str, Any]) -> Tuple[str, str]:
    if "swaggerVersion" in spec and "swagger" not in spec:
        raise SafeClientError(f"不支援 Swagger {spec.get('swaggerVersion')}，請先轉換成 OpenAPI 2.0 以上的版本")
    if "swagger" in spec:
        version = str(spec.get("swagger", "")).strip()
        if version != "2.0":
            raise SafeClientError(f"不支援 Swagger {version or '（未標示版本）'}，目前支援 2.0 與 OpenAPI 3.0、3.1、3.2")
        return "swagger_2.0", version
    if "openapi" in spec:
        version = str(spec.get("openapi", "")).strip()
        match = OPENAPI_VERSION_PATTERN.match(version)
        if not match:
            raise SafeClientError(f"不支援 OpenAPI {version or '（未標示版本）'}，目前支援 Swagger 2.0 與 OpenAPI 3.0、3.1、3.2")
        return f"openapi_3.{match.group('minor')}", version
    raise SafeClientError("無法識別規格版本：請確認文件包含 openapi、swagger、arazzo 或 overlay 版本欄位")


class _Context:
    def __init__(self, docs: SpecDocuments, label: str, base_url: str, default_base_url: Optional[str]):
        self.docs = docs
        self.label = label
        self.base_url = base_url
        self.default_base_url = default_base_url
        self.json_schema_2020 = label in ("openapi_3.1", "openapi_3.2")
        self.swagger = label == "swagger_2.0"

    def deref(self, node: Any, base: str, depth: int = 0) -> Tuple[Any, str, Dict[str, Any]]:
        overrides: Dict[str, Any] = {}
        while isinstance(node, dict) and isinstance(node.get("$ref"), str) and depth < 32:
            if not self.swagger and self.label != "openapi_3.0":
                overrides.update({k: v for k, v in node.items() if k in ("summary", "description")})
            try:
                node, base = self.docs.resolve(node["$ref"], base)
            except (KeyError, IndexError, ValueError, TypeError):
                return None, base, overrides
            depth += 1
        return node, base, overrides

    def schema(self, schema: Any, base: str, for_request: bool, warnings: List[str]) -> Dict[str, Any]:
        normalizer = SchemaNormalizer(self.docs, self.json_schema_2020, for_request)
        result = normalizer.normalize(schema, base)
        warnings.extend(w for w in normalizer.warnings if w not in warnings)
        return result


class OpenApiParser:
    """解析 Swagger 2.0、OpenAPI 3.0、3.1、3.2（可先套用 Overlay 1.0～1.2），以及 Arazzo 1.0、1.1 工作流程文件"""

    @classmethod
    async def parse(
        cls,
        spec_content_or_url: str,
        default_base_url: Optional[str],
        overlays: List[str],
    ) -> Dict[str, Any]:
        root, url, size = await load_source(spec_content_or_url, "規格")
        overlay_docs: List[Dict[str, Any]] = []
        if is_overlay(root):
            extends = root.get("extends")
            if not isinstance(extends, str) or not extends:
                raise SafeClientError("這是 Overlay 文件但沒有 extends，請把要修改的規格放在規格欄位、Overlay 放在 Overlay 欄位")
            target = join_uri(document_base(root, url), extends)
            if not is_remote_uri(target):
                raise SafeClientError("Overlay 的 extends 是相對位址，請改以 Overlay 網址匯入，或把規格貼在規格欄位")
            overlay_docs.append(root)
            root, url, size = await load_source(target, "Overlay 指向的規格")
        for overlay_input in overlays:
            overlay_doc, _, _ = await load_source(overlay_input, "Overlay")
            if not is_overlay(overlay_doc):
                raise SafeClientError("Overlay 欄位的內容不是 Overlay 文件（缺少 overlay 版本欄位）")
            overlay_docs.append(overlay_doc)
        for overlay_doc in overlay_docs:
            root = apply_overlay(root, overlay_doc)
        if "arazzo" in root:
            from app.services.arazzo import parse_arazzo
            return await parse_arazzo(root, url, size, default_base_url)
        return await cls.parse_document(root, url, size, default_base_url)

    @classmethod
    async def parse_document(
        cls, root: Dict[str, Any], url: Optional[str], size: int, default_base_url: Optional[str]
    ) -> Dict[str, Any]:
        label, version = detect_spec_version(root)
        docs = await build_documents(root, url, size)
        base_url = default_base_url or cls._root_base_url(root, label, docs)
        ctx = _Context(docs, label, base_url, default_base_url)
        warnings = list(docs.warnings)
        endpoints = cls._endpoints(ctx, warnings)
        if isinstance(root.get("webhooks"), dict) and root["webhooks"]:
            warnings.append(f"webhooks（{len(root['webhooks'])} 個）是 API 主動呼叫外部的回呼，不會匯入成工具")
        if base_url and not is_remote_uri(base_url):
            warnings.append(f"伺服器位址 {base_url} 是相對位址，請以規格網址匯入或填寫預設 Base URL")
        info = root.get("info") if isinstance(root.get("info"), dict) else {}
        description = info.get("description") or info.get("summary") or ""
        return {
            "kind": "openapi",
            "version": label,
            "spec_version": version,
            "title": info.get("title", "未命名 API"),
            "description": description,
            "base_url": base_url,
            "endpoints_count": len(endpoints),
            "endpoints": endpoints,
            "warnings": warnings,
        }

    @classmethod
    def _server_url(cls, servers: Any, docs: SpecDocuments) -> Optional[str]:
        if not isinstance(servers, list) or not servers:
            return None
        first = servers[0]
        if isinstance(first, str):
            url = first
        elif isinstance(first, dict) and isinstance(first.get("url"), str):
            url = first["url"]
            for name, variable in (first.get("variables") or {}).items():
                if isinstance(variable, dict) and "default" in variable:
                    url = url.replace(f"{{{name}}}", str(variable["default"]))
        else:
            return None
        if not is_remote_uri(url):
            base = docs.root_uri if is_remote_uri(docs.root_uri) else docs.retrieval_url
            if base:
                url = urljoin(base, url)
        return url.rstrip("/")

    @classmethod
    def _root_base_url(cls, spec: Dict[str, Any], label: str, docs: SpecDocuments) -> str:
        retrieval = urlparse(docs.retrieval_url) if docs.retrieval_url else None
        if label == "swagger_2.0":
            host = str(spec.get("host") or (retrieval.netloc if retrieval else "")).strip()
            base_path = str(spec.get("basePath") or "").strip()
            if base_path and not base_path.startswith("/"):
                base_path = "/" + base_path
            schemes = [s for s in spec.get("schemes") or [] if s in ("https", "http")]
            scheme = "https" if "https" in schemes else (schemes[0] if schemes else (retrieval.scheme if retrieval else "https"))
            return f"{scheme}://{host}{base_path}".rstrip("/") if host else base_path.rstrip("/")
        url = cls._server_url(spec.get("servers"), docs)
        if url is not None:
            return url
        if docs.retrieval_url:
            return f"{retrieval.scheme}://{retrieval.netloc}"
        return ""

    @classmethod
    def _endpoints(cls, ctx: _Context, warnings: List[str]) -> List[Dict[str, Any]]:
        paths = ctx.docs.root.get("paths")
        if not isinstance(paths, dict):
            return []
        endpoints: List[Dict[str, Any]] = []
        used_names: Dict[str, int] = {}
        methods = SWAGGER_METHODS if ctx.swagger else (OAS32_METHODS if ctx.label == "openapi_3.2" else OAS3_METHODS)
        for path, raw_item in paths.items():
            if not isinstance(path, str) or not path.startswith("/"):
                continue
            item, item_base = cls._path_item(ctx, raw_item, ctx.docs.root_uri, warnings, path)
            if item is None:
                continue
            operations: List[Tuple[str, Any]] = [(m.upper(), item[m]) for m in methods if isinstance(item.get(m), dict)]
            extra = item.get("additionalOperations") if ctx.label == "openapi_3.2" else None
            if isinstance(extra, dict):
                for method, op in extra.items():
                    if isinstance(method, str) and HTTP_TOKEN_PATTERN.match(method) and method.lower() not in OAS32_METHODS and isinstance(op, dict):
                        operations.append((method, op))
            for method, raw_op in operations:
                op, op_base, _ = ctx.deref(raw_op, item_base)
                if not isinstance(op, dict):
                    continue
                endpoint = cls._operation(ctx, path, method, op, op_base, item, item_base)
                name = endpoint["name"]
                if name in used_names:
                    used_names[name] += 1
                    endpoint["name"] = fit_tool_name(f"{name}_{used_names[name]}")
                    endpoint["function_definition"]["function"]["name"] = endpoint["name"]
                used_names.setdefault(endpoint["name"], 1)
                endpoints.append(endpoint)
        return endpoints

    @classmethod
    def _path_item(cls, ctx: _Context, raw: Any, base: str, warnings: List[str], path: str) -> Tuple[Optional[Dict[str, Any]], str]:
        if not isinstance(raw, dict):
            return None, base
        if not isinstance(raw.get("$ref"), str):
            return raw, base
        target, target_base, _ = ctx.deref({"$ref": raw["$ref"]}, base)
        if not isinstance(target, dict):
            warnings.append(f"路徑 {path} 參照的 {raw['$ref']} 無法解析，已略過")
            return None, base
        merged = {**target, **{k: v for k, v in raw.items() if k != "$ref"}}
        return merged, target_base

    @staticmethod
    def _generate_tool_name(method: str, path: str, operation_id: Optional[str]) -> str:
        """生成符合 Function Calling 規範的唯一合法工具名稱 (英文字母、數字與底線)"""
        if operation_id:
            clean_op = re.sub(r"[^a-zA-Z0-9_]", "_", operation_id.strip())
            clean_op = re.sub(r"_+", "_", clean_op).strip("_")
            if clean_op and re.match(r"^[a-zA-Z]", clean_op):
                return fit_tool_name(clean_op.lower())
        path_clean = re.sub(r"[\{\}\/]", "_", path)
        combined = f"{method.lower()}_{path_clean}"
        clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", combined)
        clean_name = re.sub(r"_+", "_", clean_name).strip("_")
        if not re.match(r"^[a-zA-Z]", clean_name):
            clean_name = f"api_{clean_name}"
        return clean_name[:MAX_TOOL_NAME_CHARS]

    @classmethod
    def _operation_base_url(cls, ctx: _Context, op: Dict[str, Any], item: Dict[str, Any]) -> str:
        if not ctx.swagger:
            for servers in (op.get("servers"), item.get("servers")):
                url = cls._server_url(servers, ctx.docs)
                if url is not None:
                    return url
        return ctx.base_url

    @classmethod
    def _parameters(cls, ctx: _Context, raw_lists: List[Tuple[Any, str]], warnings: List[str]) -> List[Tuple[Dict[str, Any], str, Dict[str, Any]]]:
        merged: Dict[Tuple[str, str], Tuple[Dict[str, Any], str, Dict[str, Any]]] = {}
        for raw_list, base in raw_lists:
            if not isinstance(raw_list, list):
                continue
            for raw in raw_list:
                param, param_base, overrides = ctx.deref(raw, base)
                if not isinstance(param, dict):
                    if isinstance(raw, dict) and "$ref" in raw:
                        warnings.append(f"參數參照 {raw['$ref']} 無法解析，已略過")
                    continue
                name, location = param.get("name"), param.get("in", "query")
                if not isinstance(name, str) or not name:
                    continue
                merged[(name, location)] = (param, param_base, overrides)
        return list(merged.values())

    @classmethod
    def _arg_name(cls, wanted: str, location: str, used: Dict[str, Any]) -> str:
        if wanted not in used:
            return wanted
        candidate = f"{wanted}_{location}"
        suffix = 2
        while candidate in used:
            candidate = f"{wanted}_{location}_{suffix}"
            suffix += 1
        return candidate

    @classmethod
    def _operation(
        cls, ctx: _Context, path: str, method: str, op: Dict[str, Any], op_base: str,
        item: Dict[str, Any], item_base: str,
    ) -> Dict[str, Any]:
        warnings: List[str] = []
        summary = op.get("summary") or item.get("summary") or op.get("description") or f"{method} {path}"
        description = op.get("description") or item.get("description") or op.get("summary") or summary
        if op.get("deprecated") is True:
            summary = f"（已棄用）{summary}"
        operation_id = op.get("operationId")
        tool_name = cls._generate_tool_name(method, path, operation_id if isinstance(operation_id, str) else None)
        properties: Dict[str, Any] = {}
        required: List[str] = []
        styles: Dict[str, Dict[str, Any]] = {}
        locations: Dict[str, str] = {}
        has_body = False
        body_media = "application/json"
        form_params: List[Tuple[Dict[str, Any], str]] = []
        params = cls._parameters(ctx, [(item.get("parameters"), item_base), (op.get("parameters"), op_base)], warnings)
        for param, param_base, overrides in params:
            location = param.get("in", "query")
            if ctx.swagger and location == "body":
                has_body = True
                body_media = cls._swagger_body_media(ctx, op, form=False)
                schema = ctx.schema(param.get("schema", {}), param_base, True, warnings)
                cls._add_body(schema, bool(param.get("required")), body_media, param.get("description"), properties, required, styles, locations, {})
                continue
            if ctx.swagger and location == "formData":
                form_params.append((param, param_base))
                continue
            if location not in ("query", "header", "path", "cookie", "querystring"):
                warnings.append(f"參數 {param.get('name')} 的位置 {location} 不支援，已略過")
                continue
            if location == "header" and str(param["name"]).lower() in IGNORED_HEADER_PARAMETERS:
                continue
            name = param["name"]
            arg = cls._arg_name(name, location, properties)
            spec: Dict[str, Any] = {"name": name, "in": location}
            if ctx.swagger:
                schema_source = {k: v for k, v in param.items() if k in SWAGGER_SCHEMA_KEYS}
                schema = ctx.schema(schema_source, param_base, True, warnings)
                if schema.get("type") == "array":
                    style, explode = COLLECTION_FORMAT_STYLES.get(param.get("collectionFormat", "csv"), ("form", False))
                    if location in ("path", "header"):
                        style = "simple"
                    spec.update({"style": style, "explode": explode})
            elif isinstance(param.get("content"), dict) and param["content"]:
                media_type = sorted(param["content"], key=_media_rank)[0]
                media, media_base, _ = ctx.deref(param["content"][media_type], param_base)
                schema = ctx.schema((media or {}).get("schema", {}), media_base, True, warnings)
                spec["content_type"] = _concrete_media(media_type)
            else:
                schema = ctx.schema(param.get("schema", {}), param_base, True, warnings)
                default_style = "form" if location in ("query", "cookie") else "simple"
                style = param.get("style") or default_style
                spec.update({
                    "style": style,
                    "explode": bool(param.get("explode", style in ("form", "cookie"))),
                    "allow_reserved": bool(param.get("allowReserved", False)),
                })
            notes = [overrides.get("description") or param.get("description") or ""]
            if param.get("deprecated") is True:
                notes.append("已棄用")
            if location in ("header", "cookie", "querystring"):
                notes.append({"header": "HTTP 標頭", "cookie": "Cookie", "querystring": "整段查詢字串"}[location])
            note = "；".join(n for n in notes if n)
            if note:
                schema = {**schema, "description": "；".join(filter(None, [note, schema.get("description")])) if schema.get("description") != note else note}
            properties[arg] = schema
            locations[arg] = location
            styles[arg] = spec
            if param.get("required") is True or location == "path":
                required.append(arg)
        if form_params:
            has_body = True
            body_media = cls._swagger_body_media(ctx, op, form=True, has_file=any(p.get("type") == "file" for p, _ in form_params))
            for param, param_base in form_params:
                name = param["name"]
                arg = cls._arg_name(name, "body", properties)
                schema = ctx.schema({k: v for k, v in param.items() if k in SWAGGER_SCHEMA_KEYS}, param_base, True, warnings)
                if param.get("description"):
                    schema = {**schema, "description": param["description"]}
                properties[arg] = schema
                locations[arg] = "body"
                styles[arg] = {"name": name, "in": "body"}
                if schema.get("type") == "array":
                    style, explode = COLLECTION_FORMAT_STYLES.get(param.get("collectionFormat", "csv"), ("form", False))
                    styles[arg].update({"style": style, "explode": explode})
                if param.get("required") is True:
                    required.append(arg)
        if not ctx.swagger and "requestBody" in op:
            body, body_base, overrides = ctx.deref(op["requestBody"], op_base)
            content = body.get("content") if isinstance(body, dict) else None
            if isinstance(content, dict) and content:
                has_body = True
                media_type = sorted(content, key=_media_rank)[0]
                media, media_base, _ = ctx.deref(content[media_type], body_base)
                media = media if isinstance(media, dict) else {}
                body_media = _concrete_media(media_type)
                raw_schema = media.get("schema")
                if raw_schema is None and "itemSchema" in media:
                    raw_schema = {"type": "array", "items": media["itemSchema"]}
                schema = ctx.schema(raw_schema or {}, media_base, True, warnings)
                encoding = media.get("encoding") if isinstance(media.get("encoding"), dict) else {}
                cls._add_body(
                    schema, bool(body.get("required")), body_media,
                    overrides.get("description") or body.get("description"), properties, required, styles, locations, encoding,
                )
                if media_family(body_media) == "xml":
                    styles["$body"] = {"xml_root": cls._xml_root(raw_schema, media_base, ctx)}
                if media_family(body_media) == "binary":
                    warnings.append(f"請求本文是 {body_media}，只能以文字內容送出")
        auth_type, auth_config, extra_headers, auth_warnings = cls._security(ctx, op)
        warnings.extend(auth_warnings)
        base_url = cls._operation_base_url(ctx, op, item)
        full_url = f"{base_url.rstrip('/')}/{path.lstrip('/')}" if base_url else path
        required = list(dict.fromkeys(required))
        parameters_schema = {"type": "object", "properties": properties, "required": required}
        function_description = f"{summary}\n\n詳細說明: {description}".strip() if description != summary else summary
        return {
            "name": tool_name,
            "display_name": summary.split("\n")[0][:60],
            "description": summary,
            "long_description": description,
            "method": method,
            "path": path,
            "base_url": base_url,
            "full_url": full_url,
            "has_body": has_body,
            "body_content_type": body_media,
            "auth_type": auth_type,
            "auth_config": auth_config,
            "headers": extra_headers,
            "param_locations": locations,
            "param_styles": styles,
            "parameters_schema": parameters_schema,
            "function_definition": {
                "type": "function",
                "function": {"name": tool_name, "description": function_description, "parameters": parameters_schema},
            },
            "operation_id": operation_id if isinstance(operation_id, str) else None,
            "tags": op.get("tags", []),
            "deprecated": op.get("deprecated") is True,
            "spec_version": ctx.label,
            "warnings": warnings,
        }

    @staticmethod
    def _xml_root(raw_schema: Any, base: str, ctx: _Context) -> str:
        schema, _, _ = ctx.deref(raw_schema, base) if isinstance(raw_schema, dict) else (None, base, {})
        if isinstance(schema, dict) and isinstance(schema.get("xml"), dict) and schema["xml"].get("name"):
            return str(schema["xml"]["name"])
        if isinstance(raw_schema, dict) and isinstance(raw_schema.get("$ref"), str):
            return raw_schema["$ref"].rsplit("/", 1)[-1]
        return "root"

    @staticmethod
    def _swagger_body_media(ctx: _Context, op: Dict[str, Any], form: bool, has_file: bool = False) -> str:
        consumes = op.get("consumes", ctx.docs.root.get("consumes"))
        consumes = [c for c in consumes if isinstance(c, str)] if isinstance(consumes, list) else []
        if form:
            if has_file or MULTIPART_MEDIA in consumes and FORM_MEDIA not in consumes:
                return MULTIPART_MEDIA
            return FORM_MEDIA
        candidates = [c for c in consumes if media_family(c) not in ("form", "multipart")]
        return _concrete_media(sorted(candidates, key=_media_rank)[0]) if candidates else "application/json"

    @classmethod
    def _add_body(
        cls, schema: Dict[str, Any], body_required: bool, media_type: str, description: Optional[str],
        properties: Dict[str, Any], required: List[str], styles: Dict[str, Dict[str, Any]],
        locations: Dict[str, str], encoding: Dict[str, Any],
    ) -> None:
        family = media_family(media_type)
        flatten = family in ("json", "form", "multipart", "xml") and schema.get("type") == "object" and schema.get("properties")
        if flatten:
            for prop, prop_schema in schema["properties"].items():
                arg = cls._arg_name(prop, "body", properties)
                properties[arg] = prop_schema
                locations[arg] = "body"
                spec: Dict[str, Any] = {"name": prop, "in": "body"}
                hint = encoding.get(prop) if isinstance(encoding.get(prop), dict) else {}
                if hint.get("contentType"):
                    spec["content_type"] = str(hint["contentType"]).split(",")[0].strip()
                if "style" in hint or "explode" in hint:
                    style = hint.get("style", "form")
                    spec.update({"style": style, "explode": bool(hint.get("explode", style == "form"))})
                styles[arg] = spec
                if body_required and prop in (schema.get("required") or []):
                    required.append(arg)
            return
        whole = {**schema, "description": description or schema.get("description") or "請求本文資料"}
        if family in ("text", "binary") and whole.get("type") not in ("string",):
            whole = {"type": "string", "description": whole["description"]}
        properties["request_body"] = whole
        locations["request_body"] = "body"
        styles["request_body"] = {"name": "request_body", "in": "body", "whole": True}
        if body_required:
            required.append("request_body")

    @classmethod
    def _security_schemes(cls, ctx: _Context) -> Dict[str, Tuple[Dict[str, Any], str]]:
        root = ctx.docs.root
        schemes = root.get("securityDefinitions") if ctx.swagger else (root.get("components") or {}).get("securitySchemes")
        if not isinstance(schemes, dict):
            return {}
        resolved = {}
        for name, scheme in schemes.items():
            target, base, _ = ctx.deref(scheme, ctx.docs.root_uri)
            if isinstance(target, dict):
                resolved[name] = (target, base)
        return resolved

    @staticmethod
    def _scheme(scheme: Dict[str, Any], scopes: List[str]) -> Tuple[Optional[str], Dict[str, Any], List[str]]:
        kind = str(scheme.get("type", "")).lower()
        if kind == "apikey":
            location = scheme.get("in")
            if location in ("header", "query", "cookie") and scheme.get("name"):
                return "api_key", {"key_name": scheme["name"], "key_in": location, "key_value": ""}, []
            return None, {}, [f"API Key 的位置 {location} 不支援"]
        http_scheme = str(scheme.get("scheme", "")).lower()
        if kind == "basic" or (kind == "http" and http_scheme == "basic"):
            return "basic", {"username": "", "password": ""}, []
        if kind == "http" and http_scheme == "bearer":
            return "bearer", {"token": ""}, []
        if kind == "http":
            return None, {}, [f"HTTP {http_scheme} 驗證不支援"]
        if kind == "oauth2":
            flows = scheme.get("flows") if isinstance(scheme.get("flows"), dict) else {}
            token_url = None
            if isinstance(flows.get("clientCredentials"), dict):
                token_url = flows["clientCredentials"].get("tokenUrl")
            elif scheme.get("flow") == "application":
                token_url = scheme.get("tokenUrl")
            if token_url:
                return OAUTH2_CLIENT_CREDENTIALS, {
                    "token_url": token_url, "scope": " ".join(scopes), "client_id": "", "client_secret": "", "client_auth": "basic",
                }, []
            flow_names = [f for f in INTERACTIVE_OAUTH_FLOWS if f in flows] or [str(scheme.get("flow", "")) or "未知流程"]
            return "bearer", {"token": ""}, [f"OAuth2 {'、'.join(flow_names)} 需要使用者授權，AskMiao 不代為執行；請自行取得存取權杖後填入 Bearer token"]
        if kind == "openidconnect":
            return "bearer", {"token": ""}, ["OpenID Connect 需要使用者登入，AskMiao 不代為執行；請自行取得存取權杖後填入 Bearer token"]
        if kind == "mutualtls":
            return None, {}, ["mutualTLS（用戶端憑證）不支援"]
        return None, {}, [f"安全機制 {kind or '（未標示）'} 不支援"]

    @classmethod
    def _requirement(cls, requirement: Dict[str, Any], schemes: Dict[str, Tuple[Dict[str, Any], str]]):
        primary: Optional[Tuple[str, Dict[str, Any]]] = None
        extra_headers: Dict[str, str] = {}
        notes: List[str] = []
        usable = True
        for name, scopes in requirement.items():
            scheme = schemes.get(name)
            if scheme is None:
                usable = False
                notes.append(f"安全機制 {name} 未定義")
                continue
            auth_type, config, scheme_notes = cls._scheme(scheme[0], [str(s) for s in scopes] if isinstance(scopes, list) else [])
            notes.extend(scheme_notes)
            if auth_type is None:
                usable = False
            elif primary is None:
                primary = (auth_type, config)
            elif auth_type == "api_key" and config["key_in"] == "header":
                extra_headers[config["key_name"]] = ""
                notes.append(f"另需 API Key 標頭 {config['key_name']}，請在工具的標頭填入")
            elif auth_type == "api_key" and config["key_in"] == "cookie":
                extra_headers["Cookie"] = f"{config['key_name']}="
                notes.append(f"另需 Cookie {config['key_name']}，請在工具的 Cookie 標頭填入")
            else:
                usable = False
                notes.append(f"同時需要多種驗證（{', '.join(requirement)}），只能套用其中一種")
        return primary, extra_headers, notes, usable

    @classmethod
    def _security(cls, ctx: _Context, op: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Dict[str, str], List[str]]:
        requirements = op.get("security", ctx.docs.root.get("security"))
        if not isinstance(requirements, list) or not requirements:
            return "none", {}, {}, []
        schemes = cls._security_schemes(ctx)
        fallback = None
        manual = None
        notes: List[str] = []
        anonymous = False
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            if not requirement:
                anonymous = True
                continue
            primary, extra_headers, local_notes, usable = cls._requirement(requirement, schemes)
            if usable and primary is not None and not local_notes:
                return primary[0], primary[1], extra_headers, []
            if usable and primary is not None:
                manual = manual or (primary[0], primary[1], extra_headers, local_notes)
                continue
            notes.extend(n for n in local_notes if n not in notes)
            if fallback is None and primary is not None:
                fallback = (primary[0], primary[1], extra_headers)
        if manual is not None:
            return manual
        if anonymous:
            return "none", {}, {}, []
        if fallback is not None:
            return fallback[0], fallback[1], fallback[2], notes
        return "none", {}, {}, notes
