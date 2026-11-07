import copy
import re
from typing import Any, Dict, List
from app.core.error_response import SafeClientError
from app.services import jsonpath
OVERLAY_VERSION_PATTERN = re.compile(r"^1\.[0-2](\.\d+)?$")
MAX_OVERLAY_ACTIONS = 500
def is_overlay(document: Any) -> bool:
    return isinstance(document, dict) and "overlay" in document
def overlay_version(document: Dict[str, Any]) -> str:
    version = str(document.get("overlay", "")).strip()
    if not OVERLAY_VERSION_PATTERN.match(version):
        raise SafeClientError(f"不支援 Overlay {version or '（未標示版本）'}，目前支援 1.0、1.1、1.2")
    return version
def _actions(overlay: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions = overlay.get("actions")
    if not isinstance(actions, list) or not actions:
        raise SafeClientError("Overlay 必須包含至少一個 actions 項目")
    if len(actions) > MAX_OVERLAY_ACTIONS:
        raise SafeClientError(f"Overlay 的 actions 超過 {MAX_OVERLAY_ACTIONS} 個")
    reusable = (overlay.get("components") or {}).get("actions") or {}
    resolved = []
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict):
            raise SafeClientError(f"Overlay 第 {index} 個 action 不是物件")
        if "$ref" in action:
            ref = action["$ref"]
            name = ref.rsplit("/", 1)[-1] if isinstance(ref, str) and ref.startswith("#/components/actions/") else None
            if name is None or not isinstance(reusable.get(name), dict):
                raise SafeClientError(f"Overlay 第 {index} 個 action 參照的 {ref} 不存在")
            action = {**reusable[name], **{k: v for k, v in action.items() if k != "$ref"}}
        if not isinstance(action.get("target"), str):
            raise SafeClientError(f"Overlay 第 {index} 個 action 缺少 target")
        resolved.append(action)
    return resolved
def _kind(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "primitive"
def _merge(target: Any, update: Any, where: str) -> Any:
    if isinstance(target, dict):
        if not isinstance(update, dict):
            raise SafeClientError(f"Overlay 不能把非物件的值合併到物件 {where}")
        for key, value in update.items():
            if key in target:
                existing_kind, update_kind = _kind(target[key]), _kind(value)
                if existing_kind != update_kind:
                    raise SafeClientError(f"Overlay 合併 {where}.{key} 時型別不同（{existing_kind} 與 {update_kind}）")
                target[key] = _merge(target[key], value, f"{where}.{key}")
            else:
                target[key] = copy.deepcopy(value)
        return target
    if isinstance(target, list):
        if isinstance(update, list):
            target.extend(copy.deepcopy(update))
        else:
            target.append(copy.deepcopy(update))
        return target
    if isinstance(update, (dict, list)):
        raise SafeClientError(f"Overlay 不能把物件或陣列寫入純量 {where}")
    return copy.deepcopy(update)
def _parent(document: Any, location: jsonpath.Location) -> Any:
    parent = document
    for key in location[:-1]:
        parent = parent[key]
    return parent
def _write(document: Dict[str, Any], node: jsonpath.Node, value: Any) -> Dict[str, Any]:
    if not node.location:
        return value
    _parent(document, node.location)[node.location[-1]] = value
    return document
def _remove(document: Dict[str, Any], nodes: List[jsonpath.Node]) -> None:
    if any(not node.location for node in nodes):
        raise SafeClientError("Overlay 不能移除整份文件")
    for node in sorted(nodes, key=lambda n: (len(n.location), n.location[-1] if isinstance(n.location[-1], int) else -1), reverse=True):
        parent = _parent(document, node.location)
        key = node.location[-1]
        if isinstance(parent, list):
            if isinstance(key, int) and key < len(parent):
                del parent[key]
        elif isinstance(parent, dict):
            parent.pop(key, None)
def apply_overlay(document: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    overlay_version(overlay)
    result = copy.deepcopy(document)
    for index, action in enumerate(_actions(overlay), start=1):
        nodes = jsonpath.query(result, action["target"])
        if not nodes:
            continue
        if action.get("remove") is True:
            _remove(result, nodes)
            continue
        if "update" in action:
            source = action["update"]
        elif isinstance(action.get("copy"), str):
            sources = jsonpath.query(result, action["copy"])
            if len(sources) != 1:
                raise SafeClientError(f"Overlay 第 {index} 個 action 的 copy 必須剛好選到一個節點（選到 {len(sources)} 個）")
            source = copy.deepcopy(sources[0].value)
        else:
            continue
        kinds = {_kind(node.value) for node in nodes}
        if len(kinds) > 1:
            raise SafeClientError(f"Overlay 第 {index} 個 action 選到的節點型別不一致")
        for node in nodes:
            where = "$" + "".join(f"[{k!r}]" for k in node.location)
            merged = _merge(node.value, source, where)
            if _kind(node.value) == "primitive":
                result = _write(result, node, merged)
    return result