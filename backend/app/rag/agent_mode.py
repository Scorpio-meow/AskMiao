from typing import Any, Dict, List, Optional, Tuple
from app import prompts
from app.core.limits import MAX_PLAN_STEP_CHARS, MAX_PLAN_STEPS
UPDATE_PLAN_TOOL_NAME = "update_plan"
PLAN_STATUSES = ("pending", "in_progress", "completed")
UPDATE_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": UPDATE_PLAN_TOOL_NAME,
        "description": prompts.UPDATE_PLAN,
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": prompts.PLAN_ITEMS.format(max_steps=MAX_PLAN_STEPS),
                    "maxItems": MAX_PLAN_STEPS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string", "description": prompts.PLAN_STEP.format(max_chars=MAX_PLAN_STEP_CHARS)},
                            "status": {"type": "string", "enum": list(PLAN_STATUSES), "description": prompts.PLAN_STATUS},
                        },
                        "required": ["step", "status"],
                    },
                },
            },
            "required": ["items"],
        },
    },
}
def parse_plan(arguments: Dict[str, Any]) -> Tuple[Optional[List[Dict[str, str]]], Optional[str]]:
    items = arguments.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_PLAN_STEPS:
        return None, prompts.PLAN_INVALID.format(reason="步驟數量不符", max_steps=MAX_PLAN_STEPS, max_chars=MAX_PLAN_STEP_CHARS)
    plan = []
    for item in items:
        step = item.get("step") if isinstance(item, dict) else None
        status = item.get("status") if isinstance(item, dict) else None
        if not isinstance(step, str) or not step.strip() or len(step.strip()) > MAX_PLAN_STEP_CHARS:
            return None, prompts.PLAN_INVALID.format(reason="步驟內容空白或過長", max_steps=MAX_PLAN_STEPS, max_chars=MAX_PLAN_STEP_CHARS)
        if status not in PLAN_STATUSES:
            return None, prompts.PLAN_INVALID.format(reason="狀態不是 pending、in_progress 或 completed", max_steps=MAX_PLAN_STEPS, max_chars=MAX_PLAN_STEP_CHARS)
        plan.append({"step": step.strip(), "status": status})
    return plan, None
def clear_old_tool_results(messages: List[Dict[str, Any]], budget: int) -> None:
    results = [m for m in messages if m.get("role") == "tool"]
    total = sum(len(m.get("content") or "") for m in results)
    for message in results[:-1]:
        if total <= budget:
            return
        size = len(message.get("content") or "")
        if size > len(prompts.TOOL_RESULT_CLEARED):
            total -= size - len(prompts.TOOL_RESULT_CLEARED)
            message["content"] = prompts.TOOL_RESULT_CLEARED