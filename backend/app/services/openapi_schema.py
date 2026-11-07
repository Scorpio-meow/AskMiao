from typing import Any, Dict, List, Optional, Set, Tuple
from app.core.limits import MAX_OPENAPI_SCHEMA_DEPTH, MAX_OPENAPI_SCHEMA_REFS
from app.services.openapi_documents import SpecDocuments, join_uri
JSON_TYPES = ("string", "number", "integer", "boolean", "array", "object")
KEPT_KEYWORDS = (
    "format", "minimum", "maximum", "minLength", "maxLength", "pattern", "minItems", "maxItems",
    "uniqueItems", "multipleOf", "minProperties", "maxProperties",
)
class SchemaNormalizer:
    def __init__(self, docs: SpecDocuments, json_schema_2020: bool, for_request: bool):
        self.docs = docs
        self.json_schema_2020 = json_schema_2020
        self.for_request = for_request
        self.resolved_refs = 0
        self.warnings: List[str] = []
    def normalize(self, schema: Any, base: str) -> Dict[str, Any]:
        return self._normalize(schema, base, frozenset(), 0)
    def _deref(self, schema: Dict[str, Any], base: str, stack: frozenset) -> Tuple[Optional[Dict[str, Any]], str, frozenset, Optional[str]]:
        ref = schema.get("$ref") if "$ref" in schema else schema.get("$dynamicRef")
        target_uri = join_uri(base, ref) if isinstance(ref, str) else None
        if target_uri is None or target_uri in stack:
            return None, base, stack, f"遞迴結構：{ref}"
        if self.resolved_refs >= MAX_OPENAPI_SCHEMA_REFS:
            return None, base, stack, f"參照目標: {ref}"
        self.resolved_refs += 1
        try:
            target, target_base = self.docs.resolve(ref, base)
        except (KeyError, IndexError, ValueError, TypeError):
            self.warnings.append(f"無法解析之參照: {ref}")
            return None, base, stack, f"無法解析之參照: {ref}"
        if target is True:
            target = {}
        if not isinstance(target, dict):
            return None, base, stack, f"無法解析之參照: {ref}"
        return target, target_base, stack | {target_uri}, None
    def _normalize(self, schema: Any, base: str, stack: frozenset, depth: int) -> Dict[str, Any]:
        if schema is True or schema is None:
            return {}
        if not isinstance(schema, dict):
            return {"type": "string"}
        if depth > MAX_OPENAPI_SCHEMA_DEPTH:
            return {"type": "object", "description": "結構層數過深，已省略內部欄位"}
        if isinstance(schema.get("$id"), str):
            base = join_uri(base, schema["$id"]).split("#", 1)[0]
        if "$ref" in schema or "$dynamicRef" in schema:
            target, target_base, next_stack, failure = self._deref(schema, base, stack)
            if target is None:
                return {"type": "object", "description": failure}
            resolved = self._normalize(target, target_base, next_stack, depth + 1)
            siblings = {k: v for k, v in schema.items() if k not in ("$ref", "$dynamicRef")}
            if not siblings:
                return resolved
            if not self.json_schema_2020:
                if "description" in siblings and "description" not in resolved:
                    resolved = {**resolved, "description": siblings["description"]}
                return resolved
            return self._merge_all([resolved, self._normalize(siblings, base, stack, depth + 1)])
        parts: List[Dict[str, Any]] = []
        own = self._own(schema, base, stack, depth)
        if "allOf" in schema and isinstance(schema["allOf"], list):
            parts.extend(self._normalize(item, base, stack, depth + 1) for item in schema["allOf"])
        for key in ("oneOf", "anyOf"):
            if isinstance(schema.get(key), list) and schema[key]:
                parts.append(self._choice(schema[key], schema.get("discriminator"), base, stack, depth))
        if not parts:
            return own
        return self._merge_all(parts + ([own] if self._meaningful(own) else []))
    @staticmethod
    def _meaningful(schema: Dict[str, Any]) -> bool:
        return any(key != "type" for key in schema) or schema.get("type") not in (None, "string")
    def _type_of(self, schema: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
        raw = schema.get("type")
        if isinstance(raw, list):
            types = [t for t in raw if t in JSON_TYPES]
            return (types[0] if types else None), types[1:]
        if raw in JSON_TYPES:
            return raw, []
        if raw == "file":
            return "string", []
        if "properties" in schema or "additionalProperties" in schema:
            return "object", []
        if "items" in schema or "prefixItems" in schema:
            return "array", []
        if "const" in schema:
            const = schema["const"]
            return {bool: "boolean", int: "integer", float: "number", str: "string"}.get(type(const)), []
        return None, []
    def _own(self, schema: Dict[str, Any], base: str, stack: frozenset, depth: int) -> Dict[str, Any]:
        cleaned: Dict[str, Any] = {}
        primary, others = self._type_of(schema)
        cleaned["type"] = primary or "string"
        notes: List[str] = []
        if schema.get("description"):
            notes.append(str(schema["description"]))
        elif schema.get("title"):
            notes.append(str(schema["title"]))
        if others:
            notes.append(f"也可以是 {', '.join(others)}")
        if schema.get("deprecated") is True:
            notes.append("已棄用")
        if schema.get("type") == "file" or schema.get("format") == "binary" or schema.get("contentEncoding") or schema.get("contentMediaType"):
            notes.append("檔案或二進位內容，請以文字提供")
        if isinstance(schema.get("enum"), list):
            cleaned["enum"] = [v for v in schema["enum"] if v is not None] or schema["enum"]
        elif "const" in schema:
            cleaned["enum"] = [schema["const"]]
        if "default" in schema:
            cleaned["default"] = schema["default"]
        for key in KEPT_KEYWORDS:
            if key in schema and not isinstance(schema[key], (dict, list)):
                cleaned[key] = schema[key]
        for key in ("exclusiveMinimum", "exclusiveMaximum"):
            value = schema.get(key)
            if isinstance(value, bool):
                if value:
                    notes.append(f"{'大於' if key == 'exclusiveMinimum' else '小於'}邊界值（不含）")
            elif isinstance(value, (int, float)):
                cleaned[key] = value
        if cleaned["type"] == "object" or "properties" in schema:
            props = schema.get("properties")
            if isinstance(props, dict):
                kept = {}
                for name, prop in props.items():
                    if self.for_request and isinstance(prop, dict) and prop.get("readOnly") is True:
                        continue
                    kept[name] = self._normalize(prop, base, stack, depth + 1)
                cleaned["properties"] = kept
                required = [str(r) for r in schema.get("required") or [] if isinstance(r, str) and r in kept]
                if required:
                    cleaned["required"] = required
            extra = schema.get("additionalProperties")
            if isinstance(extra, bool):
                cleaned["additionalProperties"] = extra
            elif isinstance(extra, dict):
                cleaned["additionalProperties"] = self._normalize(extra, base, stack, depth + 1)
        if cleaned["type"] == "array":
            items = schema.get("items")
            prefix = schema.get("prefixItems")
            if isinstance(items, dict):
                cleaned["items"] = self._normalize(items, base, stack, depth + 1)
            elif isinstance(prefix, list) and prefix:
                normalized = [self._normalize(item, base, stack, depth + 1) for item in prefix]
                cleaned["items"] = normalized[0] if all(n.get("type") == normalized[0].get("type") for n in normalized) else {}
                notes.append(f"依序為 {len(normalized)} 個元素：{', '.join(n.get('type', 'any') for n in normalized)}")
            else:
                cleaned["items"] = {}
        if notes:
            cleaned["description"] = "；".join(notes)
        return cleaned
    def _choice(self, options: List[Any], discriminator: Any, base: str, stack: frozenset, depth: int) -> Dict[str, Any]:
        variants = [self._normalize(option, base, stack, depth + 1) for option in options]
        labels = []
        for option, variant in zip(options, variants):
            if isinstance(option, dict) and isinstance(option.get("$ref"), str):
                labels.append(option["$ref"].rsplit("/", 1)[-1])
            else:
                labels.append(variant.get("description", "").split("；")[0] or variant.get("type", "物件"))
        if all(v.get("type") == "object" for v in variants):
            properties: Dict[str, Any] = {}
            for variant in variants:
                for name, prop in (variant.get("properties") or {}).items():
                    properties.setdefault(name, prop)
            required_sets = [set(v.get("required") or []) for v in variants]
            common = set.intersection(*required_sets) if required_sets else set()
            merged: Dict[str, Any] = {"type": "object", "properties": properties}
            if common:
                merged["required"] = sorted(common)
            if isinstance(discriminator, dict) and isinstance(discriminator.get("propertyName"), str):
                prop_name = discriminator["propertyName"]
                mapping = discriminator.get("mapping")
                values = list(mapping.keys()) if isinstance(mapping, dict) and mapping else labels
                properties[prop_name] = {**properties.get(prop_name, {"type": "string"}), "enum": values}
                merged["required"] = sorted(set(merged.get("required", [])) | {prop_name})
            merged["description"] = f"以下格式擇一：{'、'.join(labels)}"
            return merged
        non_null = [v for v in variants if v]
        first = dict(non_null[0]) if non_null else {"type": "string"}
        enums = [v.get("enum") for v in variants]
        if all(isinstance(e, list) for e in enums):
            first["enum"] = [value for e in enums for value in e]
        types = list(dict.fromkeys(v.get("type", "string") for v in variants))
        if len(types) > 1:
            first["description"] = "；".join(filter(None, [first.get("description"), f"可以是 {', '.join(types)}"]))
        return first
    def _merge_all(self, parts: List[Dict[str, Any]]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        descriptions: List[str] = []
        required: Set[str] = set()
        for part in parts:
            for key, value in part.items():
                if key == "description":
                    if value and value not in descriptions:
                        descriptions.append(value)
                elif key == "required":
                    required.update(value)
                elif key == "properties":
                    props = merged.setdefault("properties", {})
                    for name, prop in value.items():
                        props[name] = self._merge_all([props[name], prop]) if name in props else prop
                elif key == "type":
                    if merged.get("type") in (None, "string"):
                        merged["type"] = value
                elif key not in merged:
                    merged[key] = value
        if "properties" in merged:
            merged["type"] = "object"
        merged.setdefault("type", "string")
        if required and "properties" in merged:
            merged["required"] = sorted(r for r in required if r in merged["properties"])
        if descriptions:
            merged["description"] = "；".join(descriptions)
        return merged