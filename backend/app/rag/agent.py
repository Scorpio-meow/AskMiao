import asyncio
import base64
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
from app.core.limits import (
    AGENT_TOOL_RESULT_BUDGET_CHARS,
    CHAT_ATTACHMENT_EXTRACTION_LIMITS,
    MAX_AGENT_TURNS,
    MAX_ATTACHMENT_TEXT_CHARS,
)
from app.models import AGENT_MODE, RESEARCH_MODE
from app.rag.agent_mode import (
    ASK_USER_TOOL,
    ASK_USER_TOOL_NAME,
    UPDATE_PLAN_TOOL,
    UPDATE_PLAN_TOOL_NAME,
    clear_old_tool_results,
    parse_plan,
    parse_question,
    turn_note,
)
from app import prompts
from app.core.llm_client import LlmEndpoint, chat_completion, stream_completion
from app.rag.file_tools import FILE_TOOL_NAMES
from app.services.file_builders import extraction_slots
from app.rag.tools import ResearchToolRegistry
from app.services.agent_skills import SKILL_NAME_PATTERN
from app.rag.research_session import ResearchSession, ToolResultFilter, strip_citations, strip_tool_result_blocks
from app.rag.tool_approval import approval_broker
from app.core.error_response import log_and_get_error_id
from app.core.security_logging import log_fields
logger = logging.getLogger(__name__)
EXPLICIT_SKILL_PATTERN = re.compile(rf"^/({SKILL_NAME_PATTERN.pattern})(?:\s+|$)")
MODEL_IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")
TEXT_IMAGE_TYPES = ("image/svg+xml",)
def _attachment_ocr() -> Optional[Callable[[bytes], str]]:
    from app.models.database import SessionLocal
    from app.services.system_models import page_ocr, system_model_target
    with SessionLocal() as db:
        return page_ocr(system_model_target(db, "pdf_ocr"))
def _extract_attachment_text(fname: str, ftype: str, data_url: str, ocr: Optional[Callable[[bytes], str]]) -> Optional[str]:
    from app.services.document_processor import DocumentLimitExceeded, DocumentProcessor, DocumentRejected
    _, b64_data = data_url.split(",", 1)
    file_bytes = base64.b64decode(b64_data)
    suffix = os.path.splitext(fname)[1] or ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        return DocumentProcessor.extract_text_from_file(tmp_path, ftype, CHAT_ATTACHMENT_EXTRACTION_LIMITS, ocr)
    except DocumentLimitExceeded as e:
        logger.warning(f"附件 {fname} 超過解析上限: {e}")
        return prompts.ATTACHMENT_OVER_LIMIT.format(reason=e.reason)
    except DocumentRejected as e:
        logger.warning(f"附件 {fname} 無法讀取: {e}")
        return prompts.ATTACHMENT_REJECTED.format(reason=e.reason)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
def attachment_context(filename: str, text: str, file_id: Optional[int]) -> str:
    if file_id is None:
        return prompts.ATTACHMENT.format(filename=filename, text=text)
    return prompts.ATTACHMENT_FILE.format(file_id=file_id, filename=filename, text=text)
def local_now() -> datetime:
    return datetime.now().astimezone()
def with_current_time(query: str, now: datetime) -> str:
    offset = now.strftime("%z")
    return prompts.CURRENT_TIME.format(
        date=now.strftime("%Y-%m-%d"),
        weekday=prompts.WEEKDAYS[now.weekday()],
        time=now.strftime("%H:%M"),
        offset=f"{offset[:3]}:{offset[3:]}",
        query=query,
    )
def query_with_attachments(query: str, doc_contexts: List[str]) -> str:
    if not doc_contexts:
        return query
    return "\n\n".join([*doc_contexts, prompts.ATTACHMENT_QUESTION.format(query=query)])
class ResearchAgent:
    def __init__(self, tool_registry: ResearchToolRegistry):
        self.tools = tool_registry
    async def stream_research(
        self,
        query: str,
        *,
        endpoint: LlmEndpoint,
        model_name: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        reasoning_effort: Optional[str] = "medium",
        attachments: Optional[List[Any]] = None,
        approval_user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
        mode: str = RESEARCH_MODE
    ) -> AsyncGenerator[Dict[str, Any], None]:
        start_time = time.time()
        agent_mode = mode == AGENT_MODE
        tools_def = await asyncio.to_thread(self.tools.get_tool_definitions, approval_user_id, conversation_id)
        skill_names = next(
            (t["function"]["parameters"]["properties"]["name"]["enum"] for t in tools_def if t["function"]["name"] == "activate_skill"),
            [],
        )
        if agent_mode:
            tools_def = [*tools_def, UPDATE_PLAN_TOOL, ASK_USER_TOOL]
        base_prompt = prompts.AGENT_SYSTEM_PROMPT if agent_mode else prompts.SYSTEM_PROMPT
        system_prompt = base_prompt + prompts.SKILL_RULES if skill_names else base_prompt
        plan: Optional[List[Dict[str, str]]] = None
        research_trace: List[Dict[str, Any]] = []
        explicit_skill = None
        explicit_match = EXPLICIT_SKILL_PATTERN.match(query)
        if explicit_match and explicit_match.group(1) in skill_names:
            explicit_skill = explicit_match.group(1)
            query = query[explicit_match.end():].strip() or query
            yield {"event": "step_start", "data": {"step": 1, "tool": "activate_skill", "arguments": {"name": explicit_skill}}}
            skill_start = time.time()
            skill_output = await self.tools.activate_skill(explicit_skill, approval_user_id)
            if "error" not in skill_output:
                system_prompt += prompts.EXPLICIT_SKILL.format(content=skill_output["content"])
            step_info = {
                "step": 1,
                "tool": "activate_skill",
                "arguments": {"name": explicit_skill},
                "output_preview": skill_output.get("error") or f"已載入技能 {explicit_skill}",
                "duration_seconds": round(time.time() - skill_start, 2),
                "status": "error" if "error" in skill_output else "success",
            }
            research_trace.append(step_info)
            yield {"event": "step_end", "data": step_info}
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        history = conversation_history or []
        for turn_msg in history:
            if turn_msg.get("role") == "assistant" and isinstance(turn_msg.get("content"), str):
                turn_msg = {**turn_msg, "content": strip_citations(turn_msg["content"])}
            messages.append(turn_msg)
        doc_contexts = []
        image_data_urls = []
        attachment_texts: List[Optional[str]] = []
        if attachments:
            attachment_ocr = _attachment_ocr()
            for att in attachments:
                fname = getattr(att, "filename", None) or (att.get("filename") if isinstance(att, dict) else "未知檔案")
                ftype = getattr(att, "file_type", None) or (att.get("file_type") if isinstance(att, dict) else "")
                data_url = getattr(att, "data_url", None) or (att.get("data_url") if isinstance(att, dict) else None)
                content = getattr(att, "content", None) or (att.get("content") if isinstance(att, dict) else None)
                file_id = getattr(att, "file_id", None) if not isinstance(att, dict) else att.get("file_id")
                stored_text = None
                if data_url and not data_url.startswith("data:"):
                    logger.warning(f"略過非 data: URL 的附件 {fname}")
                    data_url = None
                if ftype in MODEL_IMAGE_TYPES:
                    if data_url:
                        image_data_urls.append(data_url)
                elif ftype.startswith("image/") and ftype not in TEXT_IMAGE_TYPES:
                    doc_contexts.append(attachment_context(fname, prompts.ATTACHMENT_UNSUPPORTED_IMAGE.format(file_type=ftype), file_id))
                else:
                    extracted_text = content
                    if not extracted_text and data_url and "," in data_url:
                        try:
                            async with extraction_slots:
                                extracted_text = await asyncio.to_thread(
                                    _extract_attachment_text, fname, ftype, data_url, attachment_ocr
                                )
                        except Exception as e:
                            logger.warning(f"即時解析附件 {fname} 失敗: {e}")
                    if extracted_text and extracted_text.strip():
                        text = extracted_text.strip()
                        stored_text = text[:MAX_ATTACHMENT_TEXT_CHARS]
                        if len(text) > MAX_ATTACHMENT_TEXT_CHARS:
                            text = stored_text + prompts.ATTACHMENT_TRUNCATED
                        doc_contexts.append(attachment_context(fname, text, file_id))
                    elif file_id is not None:
                        doc_contexts.append(attachment_context(fname, prompts.ATTACHMENT_NO_TEXT, file_id))
                attachment_texts.append(stored_text)
        if any(attachment_texts):
            yield {"event": "attachments_extracted", "data": {"contents": attachment_texts}}
        effective_query = query_with_attachments(query, doc_contexts)
        timed_query = with_current_time(effective_query, local_now())
        if image_data_urls:
            user_content = [{"type": "text", "text": timed_query}]
            for img_url in image_data_urls:
                user_content.append({"type": "image_url", "image_url": {"url": img_url}})
            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": timed_query})
        session = ResearchSession(
            [effective_query]
            + [m["content"] for m in history if m.get("role") == "user" and isinstance(m.get("content"), str)]
        )
        if explicit_skill and research_trace[0]["status"] == "success":
            session.record_tool_output("activate_skill", skill_output)
        final_answer = ""
        turns_used = 0
        while True:
            if agent_mode:
                if turns_used >= MAX_AGENT_TURNS:
                    messages.append({"role": "user", "content": prompts.AGENT_TURN_LIMIT.format(limit=MAX_AGENT_TURNS)})
                    break
                clear_old_tool_results(messages, AGENT_TOOL_RESULT_BUDGET_CHARS)
            turns_used += 1
            try:
                assistant_msg = await chat_completion(
                    messages, endpoint=endpoint, model_name=model_name, tools=tools_def, reasoning_effort=reasoning_effort
                )
            except Exception as e:
                error_id = log_and_get_error_id(logger, f"模型呼叫失敗 (第 {turns_used} 輪)", e)
                if not research_trace:
                    err_msg = f"在執行自主研究時遇到連線異常（錯誤代碼：{error_id}）"
                    yield {"event": "token", "data": {"content": err_msg}}
                    final_answer = err_msg
                break
            tool_calls = assistant_msg.get("tool_calls")
            if not tool_calls:
                content = session.drop_unknown_citations(strip_tool_result_blocks(assistant_msg.get("content") or ""))
                if content.strip():
                    final_answer = content
                    yield {"event": "token", "data": {"content": content}}
                break
            messages.append(assistant_msg)
            note = turn_note(assistant_msg.get("content"))
            for tc in tool_calls:
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                raw_args = fn.get("arguments", {})
                
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except Exception:
                        args = {"query": raw_args}
                else:
                    args = raw_args or {}
                if not isinstance(args, dict):
                    args = {}
                if agent_mode and fn_name == UPDATE_PLAN_TOOL_NAME:
                    new_plan, plan_error = parse_plan(args)
                    if new_plan is None:
                        plan_output: Dict[str, Any] = {"error": plan_error}
                    else:
                        plan = new_plan
                        plan_output = {"message": prompts.PLAN_UPDATED}
                        yield {"event": "plan", "data": {"items": plan}}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id") or f"call_plan_{turns_used}",
                        "name": fn_name,
                        "_is_error": new_plan is None,
                        "content": session.tool_message_content(fn_name, plan_output)
                    })
                    continue
                step_num = len(research_trace) + 1
                step_note, note = note, None
                noted = {"note": step_note} if step_note else {}
                logger.info("🔍 [Agent Step %s] 呼叫工具 %s", step_num, log_fields(tool=fn_name, arg_keys=",".join(map(str, args)) or None))
 
                yield {
                    "event": "step_start",
                    "data": {
                        "step": step_num,
                        "tool": fn_name,
                        "arguments": args,
                        **noted
                    }
                }
                tool_start = time.time()
                tool_output = session.refuse_tool_call(fn_name, args)
                skipped_status = "refused" if tool_output is not None else None
                user_answer: Optional[str] = None
                if tool_output is None and agent_mode and fn_name == ASK_USER_TOOL_NAME:
                    question, question_error = parse_question(args)
                    if question is None:
                        tool_output = {"error": question_error}
                    elif approval_user_id is None:
                        tool_output = {"error": prompts.ASK_USER_UNAVAILABLE}
                    else:
                        question_id, pending = approval_broker.create_question(approval_user_id)
                        yield {"event": "question", "data": {"question_id": question_id, "step": step_num, **question}}
                        user_answer = await approval_broker.wait_answer(question_id, pending)
                        yield {"event": "question_resolved", "data": {"question_id": question_id, "answered": user_answer is not None}}
                        if user_answer is None:
                            tool_output = {"error": prompts.ASK_USER_NO_ANSWER}
                        else:
                            tool_output = {"answer": user_answer}
                            session.add_user_text(user_answer)
                if tool_output is None:
                    approval = await asyncio.to_thread(self.tools.approval_requirement, fn_name, args, approval_user_id, conversation_id)
                    if session.is_preapproved(fn_name, args):
                        approval = None
                    if approval is not None:
                        if approval_user_id is None:
                            tool_output = {"error": "此工具需要使用者在對話中核准後才能執行，本次無法取得核准，請改以已取得的資料回答"}
                            skipped_status = "approval_unavailable"
                        else:
                            approval_id, decision = approval_broker.create(approval_user_id)
                            yield {
                                "event": "approval_required",
                                "data": {
                                    "approval_id": approval_id,
                                    "step": step_num,
                                    "tool": fn_name,
                                    "kind": approval["kind"],
                                    "tool_display_name": approval["display_name"],
                                    "target": approval["target"],
                                    "arguments": args,
                                },
                            }
                            approved = await approval_broker.wait(approval_id, decision)
                            yield {"event": "approval_resolved", "data": {"approval_id": approval_id, "approved": approved}}
                            if not approved:
                                tool_output = {"error": "使用者未核准執行此工具，請改以已取得的資料回答，不要再次呼叫同一工具"}
                                skipped_status = "not_approved"
                if tool_output is None:
                    try:
                        tool_output = await self.tools.execute_tool(fn_name, args, user_id=approval_user_id, conversation_id=conversation_id)
                    except Exception as e:
                        error_id = log_and_get_error_id(logger, f"工具 {fn_name} 執行失敗", e)
                        tool_output = {"error": f"工具執行失敗，請檢查參數格式後再試（錯誤代碼：{error_id}）"}
                    session.record_tool_output(fn_name, tool_output)
                tool_duration = round(time.time() - tool_start, 2)
                if skipped_status:
                    logger.info("工具呼叫未執行 %s", log_fields(tool=fn_name, status=skipped_status, duration_ms=round(tool_duration * 1000)))
                output_preview = json.dumps(tool_output, ensure_ascii=False)
                if len(output_preview) > 300:
                    output_preview = output_preview[:300] + "..."
                step_info = {
                    "step": step_num,
                    "tool": fn_name,
                    "arguments": args,
                    "output_preview": output_preview,
                    "duration_seconds": tool_duration,
                    "status": "error" if "error" in tool_output else "success",
                    **noted
                }
                research_trace.append(step_info)
 
                yield {
                    "event": "step_end",
                    "data": step_info
                }
                if fn_name in FILE_TOOL_NAMES and "action" in tool_output:
                    yield {"event": "file", "data": {"action": tool_output["action"], "file": tool_output["file"]}}
                tool_call_id = tc.get("id") or f"call_{step_num}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": fn_name,
                    "_is_error": "error" in tool_output,
                    "content": prompts.ASK_USER_ANSWER.format(answer=user_answer) if user_answer is not None
                    else session.tool_message_content(fn_name, tool_output)
                })
        if not final_answer:
            if agent_mode:
                clear_old_tool_results(messages, AGENT_TOOL_RESULT_BUDGET_CHARS)
            tool_result_filter = ToolResultFilter()
            try:
                async for chunk in stream_completion(
                    messages, endpoint=endpoint, model_name=model_name, tools=tools_def, reasoning_effort=reasoning_effort
                ):
                    text = tool_result_filter.feed(chunk)
                    if text:
                        final_answer += text
                        yield {"event": "token", "data": {"content": text}}
            except Exception as e:
                error_id = log_and_get_error_id(logger, "串流生成最終答案失敗", e)
                err_msg = f"\n[回答生成中斷（錯誤代碼：{error_id}）]"
            else:
                err_msg = ""
            tail = tool_result_filter.flush() + err_msg
            if tail:
                final_answer += tail
                yield {"event": "token", "data": {"content": tail}}
        total_time = round(time.time() - start_time, 2)
        final_answer = session.drop_unknown_citations(final_answer)
        sources_detail = session.cited_sources(final_answer)
        sources = list(dict.fromkeys(detail["source"] for detail in sources_detail))
        yield {
            "event": "sources",
            "data": {
                "sources": sources,
                "sources_detail": sources_detail
            }
        }
        yield {
            "event": "done",
            "data": {
                "answer": final_answer,
                "sources": sources,
                "sources_detail": sources_detail,
                "research_trace": research_trace,
                "plan": plan,
                "turns_used": turns_used,
                "total_time": total_time,
                "retrieval_strategy": "agentic_react"
            }
        }