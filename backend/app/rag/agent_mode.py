import re
from typing import Any, Dict, List, Optional, Tuple
from app import prompts
from app.core.limits import (
    MAX_PLAN_STEP_CHARS,
    MAX_PLAN_STEPS,
    MAX_QUESTION_CHARS,
    MAX_QUESTION_OPTION_CHARS,
    MAX_QUESTION_OPTIONS,
    MAX_STEP_NOTE_CHARS,
)
from app.rag.research_session import strip_citations, strip_tool_result_blocks
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)
ASK_USER_TOOL_NAME = "ask_user"
ASK_USER_TOOL = {
    "type": "function",
    "function": {
        "name": ASK_USER_TOOL_NAME,
        "description": prompts.ASK_USER,
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": prompts.QUESTION_TEXT.format(max_chars=MAX_QUESTION_CHARS)},
                "options": {
                    "type": "array",
                    "maxItems": MAX_QUESTION_OPTIONS,
                    "items": {"type": "string"},
                    "description": prompts.QUESTION_OPTIONS.format(max_options=MAX_QUESTION_OPTIONS, max_chars=MAX_QUESTION_OPTION_CHARS),
                },
            },
            "required": ["question"],
        },
    },
}
def _question_error(reason: str) -> str:
    return prompts.QUESTION_INVALID.format(
        reason=reason, max_chars=MAX_QUESTION_CHARS, max_options=MAX_QUESTION_OPTIONS, max_option_chars=MAX_QUESTION_OPTION_CHARS
    )
def parse_question(arguments: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    question = arguments.get("question")
    if not isinstance(question, str) or not question.strip() or len(question.strip()) > MAX_QUESTION_CHARS:
        return None, _question_error("問題空白或過長")
    options = arguments.get("options") or []
    if not isinstance(options, list) or len(options) > MAX_QUESTION_OPTIONS:
        return None, _question_error("選項數量不符")
    cleaned = []
    for option in options:
        if not isinstance(option, str) or not option.strip() or len(option.strip()) > MAX_QUESTION_OPTION_CHARS:
            return None, _question_error("選項空白或過長")
        cleaned.append(option.strip())
    return {"question": question.strip(), "options": list(dict.fromkeys(cleaned))}, None
def turn_note(content: Optional[str]) -> Optional[str]:
    visible = THINK_BLOCK.sub("", content or "").split("<think>", 1)[0]
    note = strip_citations(strip_tool_result_blocks(visible)).strip()
    if not note:
        return None
    return note if len(note) <= MAX_STEP_NOTE_CHARS else note[:MAX_STEP_NOTE_CHARS - 1] + "…"
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