import asyncio
import copy
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.core.error_response import SafeClientError
from app.core.limits import (
    MAX_ARAZZO_NESTED_WORKFLOWS,
    MAX_ARAZZO_RETRY_AFTER_SECONDS,
    MAX_ARAZZO_STEP_RUNS,
    MAX_ARAZZO_WORKFLOW_SECONDS,
)
from app.rag.tool_approval import SAFE_HTTP_METHODS
from app.services import jsonpath
from app.services.api_tool_request import scalar_text
from app.services.openapi_documents import SpecDocuments, decode_pointer, document_base, is_remote_uri, join_uri, load_source, walk_pointer

ARAZZO_VERSION_PATTERN = re.compile(r"^1\.[01](\.\d+)?$")
EXPRESSION_PATTERN = re.compile(r"^\$(url|method|statusCode|self|request|response|inputs|outputs|steps|workflows|sourceDescriptions|components)\b")
EMBEDDED_PATTERN = re.compile(r"\{(\$[^{}]+)\}")
MAX_REGEX_CONTEXT_CHARS = 20_000


def _tool_name(workflow_id: str) -> str:
    from app.services.openapi_parser import OpenApiParser
    return OpenApiParser._generate_tool_name("WORKFLOW", "", f"workflow_{workflow_id}")


def _operation_view(endpoint: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "method", "full_url", "path", "base_url", "param_locations", "param_styles", "body_content_type",
        "auth_type", "auth_config", "headers", "operation_id", "parameters_schema",
    )
    return {key: copy.deepcopy(endpoint.get(key)) for key in keys}


async def _load_sources(root: Dict[str, Any], base: str, default_base_url: Optional[str], warnings: List[str]):
    from app.services.openapi_parser import OpenApiParser
    sources: Dict[str, Dict[str, Any]] = {}
    for source in root.get("sourceDescriptions") or []:
        if not isinstance(source, dict) or not isinstance(source.get("name"), str) or not isinstance(source.get("url"), str):
            warnings.append("sourceDescriptions 有缺少 name 或 url 的項目，已略過")
            continue
        name, kind = source["name"], source.get("type", "openapi")
        url = join_uri(base, source["url"])
        entry = {"name": name, "type": kind, "url": url, "endpoints": [], "by_id": {}, "by_path": {}}
        sources[name] = entry
        if kind != "openapi":
            warnings.append(f"來源 {name} 的類型 {kind} 不支援（只支援 openapi），引用它的步驟會失敗")
            continue
        if not is_remote_uri(url):
            warnings.append(f"來源 {name} 的位址 {source['url']} 是相對位址，請改以 Arazzo 文件的網址匯入")
            continue
        try:
            document, fetched_url, size = await load_source(url, f"Arazzo 來源 {name}")
            parsed = await OpenApiParser.parse_document(document, fetched_url, size, default_base_url)
        except SafeClientError as e:
            warnings.append(f"來源 {name} 無法載入：{e}")
            continue
        warnings.extend(f"來源 {name}：{w}" for w in parsed["warnings"])
        for endpoint in parsed["endpoints"]:
            entry["endpoints"].append(endpoint)
            if endpoint.get("operation_id"):
                entry["by_id"][endpoint["operation_id"]] = endpoint
            entry["by_path"][(endpoint["path"], endpoint["method"].lower())] = endpoint
    return sources


def _find_operation(step: Dict[str, Any], sources: Dict[str, Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if isinstance(step.get("operationId"), str):
        ref = step["operationId"]
        match = re.match(r"^\$sourceDescriptions\.([^.]+)\.(.+)$", ref)
        candidates = [sources[match.group(1)]] if match and match.group(1) in sources else list(sources.values())
        operation_id = match.group(2) if match else ref
        found = [s["by_id"][operation_id] for s in candidates if operation_id in s["by_id"]]
        if len(found) == 1:
            return found[0], None
        return None, f"找不到 operationId {ref}" if not found else f"operationId {ref} 在多個來源中重複，請加上 $sourceDescriptions 前綴"
    if isinstance(step.get("operationPath"), str):
        ref = step["operationPath"]
        match = re.match(r"^\{\$sourceDescriptions\.([^.}]+)\.url\}#(.+)$", ref)
        if not match or match.group(1) not in sources:
            return None, f"operationPath {ref} 的格式不支援"
        parts = decode_pointer(match.group(2))
        if len(parts) != 3 or parts[0] != "paths":
            return None, f"operationPath {ref} 必須指向 /paths/<路徑>/<方法>"
        endpoint = sources[match.group(1)]["by_path"].get((parts[1], parts[2].lower()))
        return (endpoint, None) if endpoint else (None, f"找不到 operationPath {ref}")
    return None, "步驟沒有 operationId、operationPath 或 workflowId"


def _compile_workflows(root: Dict[str, Any], sources: Dict[str, Dict[str, Any]], warnings: List[str]) -> Dict[str, Dict[str, Any]]:
    workflows: Dict[str, Dict[str, Any]] = {}
    ids = {wf.get("workflowId") for wf in root.get("workflows") or [] if isinstance(wf, dict)}
    for wf in root.get("workflows") or []:
        if not isinstance(wf, dict) or not isinstance(wf.get("workflowId"), str):
            warnings.append("workflows 有缺少 workflowId 的項目，已略過")
            continue
        steps = []
        for step in wf.get("steps") or []:
            if not isinstance(step, dict) or not isinstance(step.get("stepId"), str):
                warnings.append(f"工作流程 {wf['workflowId']} 有缺少 stepId 的步驟，已略過")
                continue
            compiled = {k: copy.deepcopy(step.get(k)) for k in ("stepId", "description", "parameters", "requestBody", "successCriteria", "onSuccess", "onFailure", "outputs", "timeout")}
            if isinstance(step.get("workflowId"), str):
                target = step["workflowId"]
                if target not in ids:
                    warnings.append(f"步驟 {wf['workflowId']}.{step['stepId']} 引用的工作流程 {target} 不在本文件中，執行時會失敗")
                compiled["workflowId"] = target
            elif step.get("channelPath") or step.get("action"):
                warnings.append(f"步驟 {wf['workflowId']}.{step['stepId']} 是 AsyncAPI 訊息步驟，不支援")
                compiled["error"] = "AsyncAPI 步驟不支援"
            else:
                endpoint, error = _find_operation(step, sources)
                if error:
                    warnings.append(f"步驟 {wf['workflowId']}.{step['stepId']}：{error}")
                    compiled["error"] = error
                else:
                    compiled["operation"] = _operation_view(endpoint)
            for criterion in step.get("successCriteria") or []:
                kind = criterion.get("type") if isinstance(criterion, dict) else None
                kind = kind.get("type") if isinstance(kind, dict) else kind
                if kind == "xpath":
                    warnings.append(f"步驟 {wf['workflowId']}.{step['stepId']} 使用 XPath 條件，不支援，該條件一律視為失敗")
            steps.append(compiled)
        workflows[wf["workflowId"]] = {
            "workflowId": wf["workflowId"],
            "summary": wf.get("summary"),
            "description": wf.get("description"),
            "inputs": copy.deepcopy(wf.get("inputs") or {"type": "object", "properties": {}}),
            "dependsOn": [d for d in wf.get("dependsOn") or [] if isinstance(d, str)],
            "parameters": copy.deepcopy(wf.get("parameters") or []),
            "successActions": copy.deepcopy(wf.get("successActions") or []),
            "failureActions": copy.deepcopy(wf.get("failureActions") or []),
            "outputs": copy.deepcopy(wf.get("outputs") or {}),
            "steps": steps,
        }
    return workflows


def _step_targets(workflows: Dict[str, Dict[str, Any]], workflow_id: str, seen: Optional[set] = None) -> List[str]:
    seen = seen or set()
    if workflow_id in seen or workflow_id not in workflows:
        return []
    seen.add(workflow_id)
    wf = workflows[workflow_id]
    targets: List[str] = []
    for dependency in wf["dependsOn"]:
        targets.extend(_step_targets(workflows, dependency, seen))
    for step in wf["steps"]:
        if step.get("operation"):
            op = step["operation"]
            targets.append(f"{op['method']} {urlparse(op['full_url']).hostname or op['full_url']}")
        elif step.get("workflowId"):
            targets.extend(_step_targets(workflows, step["workflowId"], seen))
    return list(dict.fromkeys(targets))


async def parse_arazzo(root: Dict[str, Any], url: Optional[str], size: int, default_base_url: Optional[str]) -> Dict[str, Any]:
    from app.services.openapi_schema import SchemaNormalizer
    version = str(root.get("arazzo", "")).strip()
    if not ARAZZO_VERSION_PATTERN.match(version):
        raise SafeClientError(f"不支援 Arazzo {version or '（未標示版本）'}，目前支援 1.0、1.1")
    base = document_base(root, url)
    warnings: List[str] = []
    sources = await _load_sources(root, base, default_base_url, warnings)
    workflows = _compile_workflows(root, sources, warnings)
    docs = SpecDocuments(root=root, root_uri=base, retrieval_url=url)
    docs.register(base, root)
    label = f"arazzo_{'.'.join(version.split('.')[:2])}"
    endpoints = []
    for workflow_id, wf in workflows.items():
        normalizer = SchemaNormalizer(docs, True, True)
        inputs_schema = normalizer.normalize(wf["inputs"], base)
        if inputs_schema.get("type") != "object":
            inputs_schema = {"type": "object", "properties": {}}
        inputs_schema.setdefault("properties", {})
        inputs_schema.setdefault("required", [])
        operations = [s["operation"] for s in wf["steps"] if s.get("operation")]
        auth_types = {(op["auth_type"], json.dumps(op["auth_config"], sort_keys=True)) for op in operations}
        wf_warnings = [w for w in warnings if f"{workflow_id}." in w]
        if len(auth_types) > 1:
            wf_warnings.append("步驟使用不同的驗證方式，工作流程只能套用一組憑證（第一個步驟的驗證方式）")
        first = operations[0] if operations else None
        targets = _step_targets(workflows, workflow_id)
        summary = wf.get("summary") or workflow_id
        description = f"{wf.get('description') or summary}（Arazzo 工作流程，{len(wf['steps'])} 個步驟）"
        name = _tool_name(workflow_id)
        methods = {t.split(" ", 1)[0] for t in targets}
        definition = {
            "arazzo_version": version,
            "self": base,
            "workflow_id": workflow_id,
            "workflows": workflows,
            "components": copy.deepcopy(root.get("components") or {}),
            "source_urls": {n: s["url"] for n, s in sources.items()},
            "step_targets": targets,
        }
        endpoints.append({
            "kind": "workflow",
            "name": name,
            "display_name": str(summary).split("\n")[0][:60],
            "description": description,
            "long_description": description,
            "method": "WORKFLOW",
            "path": "",
            "base_url": "",
            "full_url": first["full_url"] if first else (url or ""),
            "has_body": False,
            "body_content_type": "application/json",
            "auth_type": first["auth_type"] if first else "none",
            "auth_config": first["auth_config"] if first else {},
            "headers": first["headers"] if first else {},
            "param_locations": {},
            "param_styles": {},
            "parameters_schema": inputs_schema,
            "function_definition": {"type": "function", "function": {"name": name, "description": description, "parameters": inputs_schema}},
            "workflow_definition": definition,
            "requires_approval": any(m not in SAFE_HTTP_METHODS for m in methods) or not methods,
            "steps_count": len(wf["steps"]),
            "step_targets": targets,
            "tags": [],
            "deprecated": False,
            "spec_version": label,
            "warnings": wf_warnings,
        }
        )
    info = root.get("info") if isinstance(root.get("info"), dict) else {}
    return {
        "kind": "arazzo",
        "version": label,
        "spec_version": version,
        "title": info.get("title", "未命名工作流程"),
        "description": info.get("description") or info.get("summary") or "",
        "base_url": "",
        "endpoints_count": len(endpoints),
        "endpoints": endpoints,
        "warnings": [w for w in warnings if not any(f"{wid}." in w for wid in workflows)],
    }


class WorkflowError(Exception):
    pass


class _Tokens:
    PATTERN = re.compile(
        r"\s*(?:(?P<expr>\$[A-Za-z][\w.\-]*(?:#[^\s()\[\]=!<>&|]*)?)|(?P<num>-?\d+(?:\.\d+)?)|(?P<str>'(?:[^']|'')*')"
        r"|(?P<op>==|!=|<=|>=|&&|\|\||[<>!()\[\].])|(?P<word>[A-Za-z_][\w-]*))"
    )

    def __init__(self, text: str):
        self.items: List[Tuple[str, str]] = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            m = self.PATTERN.match(text, pos)
            if not m or m.end() == pos:
                raise WorkflowError(f"條件語法錯誤：{text}")
            kind = m.lastgroup
            self.items.append((kind, m.group(kind)))
            pos = m.end()
        self.i = 0

    def peek(self) -> Tuple[str, str]:
        return self.items[self.i] if self.i < len(self.items) else ("end", "")

    def take(self) -> Tuple[str, str]:
        tok = self.peek()
        self.i += 1
        return tok


class _Run:
    def __init__(self, tool_dict: Dict[str, Any], tool_name: str):
        self.tool = tool_dict
        self.tool_name = tool_name
        self.definition = tool_dict["workflow_definition"]
        self.workflows = self.definition.get("workflows") or {}
        self.components = self.definition.get("components") or {}
        self.deadline = time.monotonic() + MAX_ARAZZO_WORKFLOW_SECONDS
        self.step_runs = 0
        self.trace: List[Dict[str, Any]] = []
        self.results: Dict[str, Dict[str, Any]] = {}

    def check_budget(self) -> None:
        self.step_runs += 1
        if self.step_runs > MAX_ARAZZO_STEP_RUNS:
            raise WorkflowError(f"執行步驟數超過 {MAX_ARAZZO_STEP_RUNS} 次上限，可能是 goto 或 retry 形成迴圈")
        if time.monotonic() > self.deadline:
            raise WorkflowError(f"工作流程超過 {int(MAX_ARAZZO_WORKFLOW_SECONDS)} 秒上限")

    def expression(self, expr: str, scope: Dict[str, Any]) -> Any:
        head, _, pointer = expr.partition("#")
        parts = head[1:].split(".")
        exchange = scope.get("exchange") or {}
        root = parts[0]
        if root == "url":
            value = exchange.get("url")
        elif root == "method":
            value = exchange.get("method")
        elif root == "statusCode":
            value = exchange.get("status_code")
        elif root == "self":
            value = self.definition.get("self")
        elif root in ("request", "response") and len(parts) >= 2:
            side = exchange.get(root) or {}
            if parts[1] == "header" and len(parts) >= 3:
                value = (side.get("header") or {}).get(".".join(parts[2:]).lower())
            elif parts[1] in ("query", "path") and len(parts) >= 3:
                value = (side.get(parts[1]) or {}).get(".".join(parts[2:]))
            elif parts[1] in ("body", "payload"):
                value = side.get("body")
            else:
                value = None
        elif root == "inputs" and len(parts) >= 2:
            value = (scope.get("inputs") or {}).get(".".join(parts[1:]))
        elif root == "outputs" and len(parts) >= 2:
            value = (scope.get("outputs") or {}).get(".".join(parts[1:]))
        elif root == "steps" and len(parts) >= 4 and parts[2] == "outputs":
            value = ((scope.get("steps") or {}).get(parts[1]) or {}).get(".".join(parts[3:]))
        elif root == "workflows" and len(parts) >= 4 and parts[2] in ("inputs", "outputs"):
            value = (self.results.get(parts[1]) or {}).get(parts[2], {}).get(".".join(parts[3:]))
        elif root == "sourceDescriptions" and len(parts) >= 3:
            value = (self.definition.get("source_urls") or {}).get(parts[1]) if parts[2] == "url" else None
        elif root == "components" and len(parts) >= 3:
            value = (self.components.get(parts[1]) or {}).get(".".join(parts[2:]))
        else:
            raise WorkflowError(f"不支援的執行期運算式 {expr}")
        if pointer:
            if isinstance(value, str) and root in ("request", "response"):
                try:
                    value = json.loads(value)
                except ValueError:
                    return None
            try:
                value = walk_pointer(value, pointer)
            except (KeyError, IndexError, ValueError, TypeError):
                return None
        return value

    def value(self, raw: Any, scope: Dict[str, Any]) -> Any:
        if isinstance(raw, str):
            if raw.startswith("$") and EXPRESSION_PATTERN.match(raw) and " " not in raw.strip():
                return self.expression(raw.strip(), scope)
            return EMBEDDED_PATTERN.sub(lambda m: scalar_text(self.expression(m.group(1).strip(), scope)), raw)
        if isinstance(raw, dict):
            if set(raw) >= {"context", "selector"}:
                return self.select(raw, scope)
            return {k: self.value(v, scope) for k, v in raw.items()}
        if isinstance(raw, list):
            return [self.value(v, scope) for v in raw]
        return raw

    def select(self, selector: Dict[str, Any], scope: Dict[str, Any]) -> Any:
        context = self.value(selector["context"], scope)
        kind = selector.get("type", "jsonpath")
        kind = kind.get("type") if isinstance(kind, dict) else kind
        expression = str(selector["selector"])
        if kind == "jsonpointer":
            try:
                return walk_pointer(context, expression.lstrip("#"))
            except (KeyError, IndexError, ValueError, TypeError):
                return None
        if kind == "jsonpath":
            found = jsonpath.values(context, expression)
            return found[0] if len(found) == 1 else (found or None)
        raise WorkflowError(f"不支援 {kind} 選擇器")

    def criterion(self, criterion: Any, scope: Dict[str, Any]) -> bool:
        if not isinstance(criterion, dict) or not isinstance(criterion.get("condition"), str):
            return False
        kind = criterion.get("type", "simple")
        kind = kind.get("type") if isinstance(kind, dict) else kind
        condition = criterion["condition"]
        try:
            if kind == "simple":
                return self.simple(condition, scope)
            context = self.value(criterion.get("context"), scope) if criterion.get("context") else None
            if context is None:
                return False
            condition = EMBEDDED_PATTERN.sub(lambda m: scalar_text(self.expression(m.group(1).strip(), scope)), condition)
            if kind == "regex":
                text = scalar_text(context)[:MAX_REGEX_CONTEXT_CHARS]
                return re.search(condition, text) is not None
            if kind == "jsonpath":
                if isinstance(context, str):
                    context = json.loads(context)
                return len(jsonpath.query(context, condition)) > 0
            return False
        except (WorkflowError, SafeClientError, ValueError, re.error):
            return False

    def simple(self, condition: str, scope: Dict[str, Any]) -> bool:
        tokens = _Tokens(condition)
        result = self._or(tokens, scope)
        if tokens.peek()[0] != "end":
            raise WorkflowError(f"條件語法錯誤：{condition}")
        return result is True

    def _or(self, t: _Tokens, scope) -> Any:
        left = self._and(t, scope)
        while t.peek() == ("op", "||"):
            t.take()
            right = self._and(t, scope)
            left = left is True or right is True
        return left

    def _and(self, t: _Tokens, scope) -> Any:
        left = self._not(t, scope)
        while t.peek() == ("op", "&&"):
            t.take()
            right = self._not(t, scope)
            left = left is True and right is True
        return left

    def _not(self, t: _Tokens, scope) -> Any:
        if t.peek() == ("op", "!"):
            t.take()
            return not (self._not(t, scope) is True)
        return self._compare(t, scope)

    def _compare(self, t: _Tokens, scope) -> Any:
        left = self._operand(t, scope)
        kind, text = t.peek()
        if kind == "op" and text in ("==", "!=", "<", "<=", ">", ">="):
            t.take()
            right = self._operand(t, scope)
            return self._apply(text, left, right)
        return left

    @staticmethod
    def _apply(op: str, a: Any, b: Any) -> bool:
        if isinstance(a, str) and isinstance(b, (int, float)) and not isinstance(b, bool):
            try:
                a = float(a)
            except ValueError:
                return op == "!="
        if isinstance(b, str) and isinstance(a, (int, float)) and not isinstance(a, bool):
            try:
                b = float(b)
            except ValueError:
                return op == "!="
        if isinstance(a, str) and isinstance(b, str):
            a, b = a.lower(), b.lower()
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if a is None or b is None or type(a) is bool or type(b) is bool:
            return False
        try:
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
        except TypeError:
            return False

    def _operand(self, t: _Tokens, scope) -> Any:
        kind, text = t.take()
        if kind == "op" and text == "(":
            value = self._or(t, scope)
            if t.take() != ("op", ")"):
                raise WorkflowError("條件缺少右括號")
        elif kind == "expr":
            value = self.expression(text, scope)
        elif kind == "num":
            value = float(text) if "." in text else int(text)
        elif kind == "str":
            value = text[1:-1].replace("''", "'")
        elif kind == "word" and text in ("true", "false", "null"):
            value = {"true": True, "false": False, "null": None}[text]
        else:
            raise WorkflowError(f"條件語法錯誤，無法辨識 {text}")
        while t.peek() in (("op", "["), ("op", ".")):
            _, accessor = t.take()
            if accessor == "[":
                index_kind, index_text = t.take()
                if t.take() != ("op", "]"):
                    raise WorkflowError("條件的索引缺少右中括號")
                key: Any = int(index_text) if index_kind == "num" else index_text.strip("'")
            else:
                key = t.take()[1]
            try:
                value = value[key] if isinstance(value, (list, dict)) else None
            except (KeyError, IndexError, TypeError):
                value = None
        return value

    def parameters(self, workflow: Dict[str, Any], step: Dict[str, Any]) -> List[Dict[str, Any]]:
        merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for raw in list(workflow.get("parameters") or []) + list(step.get("parameters") or []):
            param = self.reusable(raw, "parameters")
            if isinstance(param, dict) and isinstance(param.get("name"), str):
                merged[(param["name"], param.get("in", ""))] = param
        return list(merged.values())

    def reusable(self, raw: Any, kind: str) -> Any:
        if isinstance(raw, dict) and isinstance(raw.get("reference"), str):
            match = re.match(rf"^\$components\.{kind}\.(.+)$", raw["reference"])
            target = (self.components.get(kind) or {}).get(match.group(1)) if match else None
            if not isinstance(target, dict):
                raise WorkflowError(f"找不到可重用物件 {raw['reference']}")
            merged = copy.deepcopy(target)
            if "value" in raw:
                merged["value"] = raw["value"]
            return merged
        return raw

    def actions(self, workflow: Dict[str, Any], step: Dict[str, Any], success: bool) -> List[Dict[str, Any]]:
        step_actions = [self.reusable(a, "successActions" if success else "failureActions") for a in step.get("onSuccess" if success else "onFailure") or []]
        names = {a.get("name") for a in step_actions if isinstance(a, dict)}
        workflow_actions = [
            self.reusable(a, "successActions" if success else "failureActions")
            for a in workflow.get("successActions" if success else "failureActions") or []
        ]
        return [a for a in step_actions if isinstance(a, dict)] + [a for a in workflow_actions if isinstance(a, dict) and a.get("name") not in names]

    async def http_step(self, step: Dict[str, Any], workflow: Dict[str, Any], scope: Dict[str, Any]) -> Dict[str, Any]:
        from app.api.api_tools import execute_http_request
        op = step["operation"]
        styles = copy.deepcopy(op.get("param_styles") or {})
        locations = copy.deepcopy(op.get("param_locations") or {})
        arguments: Dict[str, Any] = {}
        by_name = {(spec.get("name"), spec.get("in")): arg for arg, spec in styles.items() if isinstance(spec, dict)}
        for param in self.parameters(workflow, step):
            location = param.get("in")
            value = self.value(param.get("value"), scope)
            arg = by_name.get((param["name"], location))
            if arg is None:
                arg = f"{location}:{param['name']}"
                styles[arg] = {"name": param["name"], "in": location}
                locations[arg] = location
            arguments[arg] = value
        content_type = op.get("body_content_type") or "application/json"
        body = step.get("requestBody")
        if isinstance(body, dict) and "payload" in body:
            payload = self.value(copy.deepcopy(body["payload"]), scope)
            for replacement in body.get("replacements") or []:
                if isinstance(replacement, dict) and isinstance(replacement.get("target"), str):
                    payload = self.replace(payload, replacement, scope)
            content_type = body.get("contentType") or content_type
            for arg in [a for a, spec in styles.items() if isinstance(spec, dict) and spec.get("in") == "body"]:
                styles.pop(arg)
                locations.pop(arg, None)
            styles["request_body"] = {"name": "request_body", "in": "body", "whole": True}
            locations["request_body"] = "body"
            arguments["request_body"] = payload
        timeout = self.tool.get("timeout") or 15
        if isinstance(step.get("timeout"), (int, float)) and step["timeout"] > 0:
            timeout = max(1, int(step["timeout"] / 1000))
        step_tool = {
            **{k: self.tool.get(k) for k in ("headers", "auth_type", "auth_config")},
            "name": f"{self.tool_name}.{step['stepId']}",
            "method": op["method"],
            "url": op["full_url"],
            "base_url": "",
            "path": "",
            "param_locations": locations,
            "param_styles": styles,
            "body_content_type": content_type,
            "parameters_schema": {"type": "object", "properties": {arg: {} for arg in arguments}},
            "timeout": timeout,
        }
        result = await execute_http_request(step_tool, arguments, step_tool["name"], keep_exchange=True)
        exchange = result.get("exchange") or {}
        return {
            "status_code": result.get("status_code"),
            "is_success": result.get("is_success"),
            "url": result.get("url"),
            "method": op["method"],
            "error": result.get("error"),
            "request": {
                "header": exchange.get("request_headers") or {},
                "query": exchange.get("request_query") or {},
                "path": exchange.get("request_path") or {},
                "body": exchange.get("request_body"),
            },
            "response": {"header": exchange.get("response_headers") or {}, "body": result.get("data")},
        }

    def replace(self, payload: Any, replacement: Dict[str, Any], scope: Dict[str, Any]) -> Any:
        target = replacement["target"]
        value = self.value(replacement.get("value"), scope)
        selector_type = replacement.get("targetSelectorType")
        selector_type = selector_type.get("type") if isinstance(selector_type, dict) else selector_type
        if selector_type == "jsonpath" or (selector_type is None and target.startswith("$")):
            nodes = jsonpath.query(payload, target)
            for node in nodes:
                if not node.location:
                    payload = value
                    continue
                parent = payload
                for key in node.location[:-1]:
                    parent = parent[key]
                parent[node.location[-1]] = copy.deepcopy(value)
            return payload
        parts = decode_pointer(target.lstrip("#"))
        if not parts:
            return value
        parent = payload
        for key in parts[:-1]:
            parent = parent[int(key)] if isinstance(parent, list) else parent.setdefault(key, {})
        if isinstance(parent, list):
            parent[int(parts[-1])] = value
        elif isinstance(parent, dict):
            parent[parts[-1]] = value
        return payload

    async def run_workflow(self, workflow_id: str, inputs: Dict[str, Any], depth: int) -> Dict[str, Any]:
        if depth > MAX_ARAZZO_NESTED_WORKFLOWS:
            raise WorkflowError(f"巢狀工作流程超過 {MAX_ARAZZO_NESTED_WORKFLOWS} 層")
        workflow = self.workflows.get(workflow_id)
        if workflow is None:
            raise WorkflowError(f"找不到工作流程 {workflow_id}")
        for dependency in workflow.get("dependsOn") or []:
            if dependency not in self.results:
                await self.run_workflow(dependency, {}, depth + 1)
        scope: Dict[str, Any] = {"inputs": inputs, "steps": {}, "outputs": {}}
        steps = workflow.get("steps") or []
        index_of = {s["stepId"]: i for i, s in enumerate(steps)}
        retries: Dict[str, int] = {}
        index = 0
        succeeded = True
        failure: Optional[str] = None
        while index < len(steps):
            step = steps[index]
            exchange, success, step_scope = await self.run_step(step, workflow, workflow_id, scope, depth)
            chosen = None
            for action in self.actions(workflow, step, success):
                if not all(self.criterion(c, step_scope) for c in action.get("criteria") or []):
                    continue
                if action.get("type") == "retry":
                    limit = action.get("retryLimit", 1)
                    if retries.get(step["stepId"], 0) >= (limit if isinstance(limit, int) else 1):
                        continue
                chosen = action
                break
            if success:
                if chosen and chosen.get("type") == "end":
                    break
                if chosen and chosen.get("type") == "goto":
                    index = await self.goto(chosen, index_of, scope, depth)
                    if index < 0:
                        break
                    continue
                index += 1
                continue
            if chosen is None or chosen.get("type") == "end":
                succeeded = False
                failure = f"步驟 {step['stepId']} 失敗（狀態碼 {exchange.get('status_code')}）"
                break
            if chosen.get("type") == "retry":
                retries[step["stepId"]] = retries.get(step["stepId"], 0) + 1
                wait = chosen.get("retryAfter", 0)
                header = (exchange.get("response") or {}).get("header", {}).get("retry-after")
                if isinstance(header, str) and header.strip().isdigit():
                    wait = int(header.strip())
                wait = min(max(float(wait or 0), 0.0), MAX_ARAZZO_RETRY_AFTER_SECONDS, max(self.deadline - time.monotonic(), 0.0))
                if wait:
                    await asyncio.sleep(wait)
                if chosen.get("stepId"):
                    if chosen["stepId"] not in index_of:
                        raise WorkflowError(f"retry 的步驟 {chosen['stepId']} 不存在")
                    await self.run_step(steps[index_of[chosen["stepId"]]], workflow, workflow_id, scope, depth)
                elif chosen.get("workflowId"):
                    await self.goto(chosen, index_of, scope, depth)
                continue
            index = await self.goto(chosen, index_of, scope, depth)
            if index < 0:
                break
        outputs = {}
        if succeeded:
            outputs = {name: self.value(expr, scope) for name, expr in (workflow.get("outputs") or {}).items()}
        self.results[workflow_id] = {"inputs": inputs, "outputs": outputs, "success": succeeded}
        return {"success": succeeded, "outputs": outputs, "error": failure}

    async def run_step(self, step: Dict[str, Any], workflow: Dict[str, Any], workflow_id: str, scope: Dict[str, Any], depth: int):
        self.check_budget()
        if step.get("error"):
            raise WorkflowError(f"步驟 {step['stepId']} 無法執行：{step['error']}")
        if step.get("workflowId"):
            sub_inputs = {p["name"]: self.value(p.get("value"), scope) for p in self.parameters({}, step) if isinstance(p, dict) and p.get("name")}
            sub = await self.run_workflow(step["workflowId"], sub_inputs, depth + 1)
            exchange = {"status_code": None, "response": {"body": sub.get("outputs")}, "request": {}, "is_success": sub["success"]}
        else:
            exchange = await self.http_step(step, workflow, scope)
        step_scope = {**scope, "exchange": exchange}
        criteria = step.get("successCriteria")
        success = all(self.criterion(c, step_scope) for c in criteria) if criteria else bool(exchange.get("is_success"))
        self.trace.append({
            "workflow": workflow_id, "step": step["stepId"], "status_code": exchange.get("status_code"),
            "success": success, "url": exchange.get("url"), "error": exchange.get("error"),
        })
        if success:
            scope["steps"][step["stepId"]] = {name: self.value(expr, step_scope) for name, expr in (step.get("outputs") or {}).items()}
        return exchange, success, step_scope

    async def goto(self, action: Dict[str, Any], index_of: Dict[str, int], scope: Dict[str, Any], depth: int) -> int:
        if action.get("stepId"):
            if action["stepId"] not in index_of:
                raise WorkflowError(f"goto 的步驟 {action['stepId']} 不存在")
            return index_of[action["stepId"]]
        if action.get("workflowId"):
            sub_inputs = {p["name"]: self.value(p.get("value"), scope) for p in action.get("parameters") or [] if isinstance(p, dict) and p.get("name")}
            await self.run_workflow(action["workflowId"], sub_inputs, depth + 1)
            return -1
        raise WorkflowError("goto 動作缺少 stepId 或 workflowId")


async def run_workflow(tool_dict: Dict[str, Any], arguments: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    started = time.time()
    declared = set(((tool_dict.get("parameters_schema") or {}).get("properties") or {}).keys())
    undeclared = [name for name in arguments or {} if name not in declared]
    if undeclared:
        return {"status_code": 400, "is_success": False, "duration_seconds": 0.0, "error": f"工具參數無效：未宣告的參數 {', '.join(undeclared)}"}
    run = _Run(tool_dict, tool_name)
    workflow_id = run.definition.get("workflow_id")
    try:
        result = await asyncio.wait_for(run.run_workflow(workflow_id, dict(arguments or {}), 0), timeout=MAX_ARAZZO_WORKFLOW_SECONDS + 5)
    except asyncio.TimeoutError:
        result = {"success": False, "outputs": {}, "error": f"工作流程超過 {int(MAX_ARAZZO_WORKFLOW_SECONDS)} 秒上限"}
    except WorkflowError as e:
        result = {"success": False, "outputs": {}, "error": str(e)}
    response: Dict[str, Any] = {
        "status_code": 200 if result["success"] else 502,
        "is_success": result["success"],
        "duration_seconds": round(time.time() - started, 3),
        "workflow": workflow_id,
        "outputs": result["outputs"],
        "steps": run.trace,
    }
    if result.get("error"):
        response["error"] = result["error"]
    return response
