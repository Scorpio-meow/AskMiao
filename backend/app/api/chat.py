from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models import AgentInstructionsUpdate, Conversation, MessageCreate, ConversationResponse, User
from app.services.chat_service import AttachmentQuotaExceeded, ChatService
from app.services.conversation_files import (
    ConversationFileError,
    content_disposition,
    delete_file,
    extension_of,
    get_file,
    list_files,
    storage_lock,
    summary,
    view_token,
    view_token_owner,
)
from app.core.rag_manager import get_rag_system
from app.core.user_context import get_current_user_id
from app.core.error_response import SafeClientError, build_error_payload
from typing import Dict, List
import asyncio
import contextlib
import logging
logger = logging.getLogger(__name__)
import json
from app.core.config import settings
from app.core.limits import CHAT_ATTACHMENT_EXTRACTION_LIMITS, FILE_VIEW_TOKEN_SECONDS, MAX_CONCURRENT_CHAT_STREAMS_PER_USER, MAX_QUESTION_ANSWER_CHARS
from app.services.file_builders import extraction_slots
from app.services.file_preview import HTML_EXTENSIONS, build_preview, recent_pdfs, render_pdf_page
from app.rag.tool_approval import approval_broker
from app.services.llm_connections import chat_option, connections_for_user, resolve_chat_endpoint
from app.services.agent_instructions import get_instructions, instructions_prompt, set_instructions
from pydantic import BaseModel, Field
router = APIRouter()
chat_service = ChatService()
_active_streams: Dict[int, int] = {}
def _has_stream_slot(user_id: int) -> bool:
    return _active_streams.get(user_id, 0) < MAX_CONCURRENT_CHAT_STREAMS_PER_USER
def _acquire_stream_slot(user_id: int) -> bool:
    if not _has_stream_slot(user_id):
        return False
    _active_streams[user_id] = _active_streams.get(user_id, 0) + 1
    return True
def _release_stream_slot(user_id: int) -> None:
    remaining = _active_streams.get(user_id, 0) - 1
    if remaining > 0:
        _active_streams[user_id] = remaining
    else:
        _active_streams.pop(user_id, None)
@router.get("/models")
def get_available_models(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    return {"connections": [chat_option(c) for c in connections_for_user(db, user_id)]}
@router.get("/tools")
def get_available_tools(user_id: int = Depends(get_current_user_id)):
    try:
        tool_defs = get_rag_system().pipeline.tool_registry.get_tool_definitions(user_id)
        return {
            "status": "success",
            "tools": tool_defs
        }
    except Exception as e:
        error_payload = build_error_payload(logger, "取得可用工具清單失敗", e)
        from app.rag.tools import ResearchToolRegistry
        tool_defs = ResearchToolRegistry().get_tool_definitions(user_id)
        return {
            "status": "partial",
            "tools": tool_defs,
            "error": error_payload["detail"],
            "error_id": error_payload["error_id"],
            "request_id": error_payload["request_id"]
        }
@router.post("/send")
async def send_message(
    message_data: MessageCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    try:
        endpoint = await asyncio.to_thread(
            resolve_chat_endpoint, db, user_id, message_data.connection_id, message_data.model_name
        )
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not _has_stream_slot(user_id):
        raise HTTPException(
            status_code=429,
            detail=f"每位使用者最多同時進行 {MAX_CONCURRENT_CHAT_STREAMS_PER_USER} 個對話回應，請等待目前的回應完成",
        )
    attachments = message_data.attachments or []
    async with (storage_lock if attachments else contextlib.nullcontext()):
        try:
            user_message = await asyncio.to_thread(
                chat_service.save_user_message,
                db,
                user_id,
                message_data.content,
                message_data.conversation_id,
                attachments,
                message_data.model_name,
            )
        except AttachmentQuotaExceeded:
            raise HTTPException(status_code=413, detail="附件儲存空間已達上限，請刪除部分含附件的對話或對話檔案後再試")
        except ConversationFileError as e:
            raise HTTPException(status_code=400, detail=str(e))
    conv_id = user_message.conversation_id
    user_message_id = user_message.id
    conversation_history = await asyncio.to_thread(
        chat_service.get_recent_history,
        db,
        conv_id,
        before_message_id=user_message_id,
        limit=settings.CONVERSATION_HISTORY_MESSAGES
    )
    instructions = await asyncio.to_thread(instructions_prompt, db, user_id)
    await asyncio.to_thread(db.close)
    async def sse_generator():
        if not _acquire_stream_slot(user_id):
            err = {"detail": f"每位使用者最多同時進行 {MAX_CONCURRENT_CHAT_STREAMS_PER_USER} 個對話回應，請等待目前的回應完成"}
            yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"
            return
        try:
            start_payload = {
                "conversation_id": conv_id,
                "user_message_id": user_message_id,
                "attachment_file_ids": [att.file_id for att in attachments],
            }
            yield f"event: start\ndata: {json.dumps(start_payload, ensure_ascii=False)}\n\n"
            rag_system = get_rag_system()
            collected_tokens = ""
            collected_sources = []
            collected_sources_detail = []
            collected_research_trace = []
            collected_plan = None
            collected_files = []
            try:
                async for event_item in rag_system.generate_response_stream(
                    message_data.content,
                    conversation_history=conversation_history,
                    endpoint=endpoint,
                    model_name=message_data.model_name,
                    reasoning_effort=message_data.reasoning_effort,
                    attachments=message_data.attachments,
                    approval_user_id=user_id,
                    conversation_id=conv_id,
                    mode=message_data.mode,
                    instructions=instructions
                ):
                    ev = event_item.get("event")
                    data = event_item.get("data", {})
                    if ev in ("approval_required", "approval_resolved", "question", "question_resolved"):
                        yield f"event: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif ev == "attachments_extracted":
                        await asyncio.to_thread(chat_service.save_attachment_texts, db, user_message_id, data["contents"])
                    elif ev == "step_start":
                        yield f"event: step_start\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif ev == "step_end":
                        collected_research_trace.append(data)
                        yield f"event: step_end\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif ev == "plan":
                        collected_plan = data.get("items")
                        yield f"event: plan\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif ev == "file":
                        collected_files.append(data)
                        yield f"event: file\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif ev == "token":
                        collected_tokens += data.get("content", "")
                        yield f"event: token\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif ev == "sources":
                        collected_sources = data.get("sources", [])
                        collected_sources_detail = data.get("sources_detail", [])
                        yield f"event: sources\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif ev == "done":
                        collected_tokens = data.get("answer") or collected_tokens
                        if not collected_sources:
                            collected_sources = data.get("sources", [])
                            collected_sources_detail = data.get("sources_detail", [])
                        if not collected_research_trace:
                            collected_research_trace = data.get("research_trace", [])
                        if collected_plan is None:
                            collected_plan = data.get("plan")
                context_payload = json.dumps({
                    "sources": collected_sources,
                    "sources_detail": collected_sources_detail,
                    "research_trace": collected_research_trace,
                    "plan": collected_plan,
                    "files": collected_files
                }, ensure_ascii=False)
                bot_message = await asyncio.to_thread(
                    chat_service.save_message,
                    db,
                    user_id,
                    collected_tokens,
                    False,
                    conv_id,
                    context_payload,
                    model_name=message_data.model_name,
                )
                done_payload = {
                    "message_id": bot_message.id if bot_message else None,
                    "conversation_id": conv_id,
                    "answer": collected_tokens,
                    "sources": collected_sources,
                    "sources_detail": collected_sources_detail,
                    "research_trace": collected_research_trace,
                    "plan": collected_plan,
                    "files": collected_files
                }
                yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
            except Exception as e:
                err_payload = build_error_payload(logger, "處理訊息串流時發生錯誤", e)
                yield f"event: error\ndata: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
        finally:
            _release_stream_slot(user_id)
            await asyncio.to_thread(db.close)
    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
class ToolApprovalDecision(BaseModel):
    approved: bool
    remember: bool = False
@router.post("/approvals/{approval_id}")
async def resolve_tool_approval(
    approval_id: str,
    decision: ToolApprovalDecision,
    user_id: int = Depends(get_current_user_id)
):
    if not approval_broker.resolve(approval_id, user_id, decision.approved, decision.remember):
        raise HTTPException(status_code=404, detail="找不到待核准的工具呼叫，可能已逾時或已處理")
    return {"approval_id": approval_id, "approved": decision.approved, "remember": decision.approved and decision.remember}
@router.get("/instructions")
def get_personal_instructions(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return {"content": get_instructions(db, user_id)}
@router.put("/instructions")
def update_personal_instructions(
    update: AgentInstructionsUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    return {"content": set_instructions(db, user_id, update.content)}
class QuestionAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=MAX_QUESTION_ANSWER_CHARS)
@router.post("/questions/{question_id}")
async def answer_agent_question(
    question_id: str,
    reply: QuestionAnswer,
    user_id: int = Depends(get_current_user_id)
):
    answer = reply.answer.strip()
    if not answer:
        raise HTTPException(status_code=422, detail="回答不可空白")
    if not approval_broker.answer(question_id, user_id, answer):
        raise HTTPException(status_code=404, detail="找不到等待回答的問題，可能已逾時或已回答")
    return {"question_id": question_id, "answered": True}
@router.get("/conversations", response_model=List[ConversationResponse])
def get_conversations(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    conversations = chat_service.get_user_conversations(db, user_id)
    return conversations
@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    conversation = chat_service.get_conversation_with_messages(db, conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="找不到該對話")
    
    return conversation
@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages_endpoint(
    conversation_id: int,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    messages = chat_service.get_conversation_messages(db, conversation_id, user_id, limit=limit, offset=offset)
    return messages
@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    conversation = chat_service.create_conversation(db, user_id)
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[]
    )
@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    success = chat_service.delete_conversation(db, conversation_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="找不到該對話")
    
    return {"message": "對話已刪除"}
@router.get("/conversations/{conversation_id}/files")
def list_conversation_files(
    conversation_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    owned = db.query(Conversation.id).filter(Conversation.id == conversation_id, Conversation.user_id == user_id).first()
    if not owned:
        raise HTTPException(status_code=404, detail="找不到該對話")
    return {"files": [summary(file) for file in list_files(db, conversation_id, user_id)]}
def _owned_file(db: Session, file_id: int, user_id: int, with_data: bool):
    try:
        return get_file(db, file_id, user_id, None, with_data=with_data)
    except ConversationFileError:
        raise HTTPException(status_code=404, detail="找不到這個檔案")
def _preview_bytes(file) -> bytes:
    if extension_of(file.filename) == ".pdf":
        return recent_pdfs.get((file.id, str(file.created_at)), lambda: file.data)
    return file.data
def html_view_policy() -> str:
    ancestors = " ".join(["'self'", *settings.allowed_origins_list])
    return (
        "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        f"img-src data: blob:; font-src data:; media-src data: blob:; base-uri 'none'; form-action 'none'; frame-ancestors {ancestors}"
    )
@router.get("/files/{file_id}")
def download_conversation_file(
    file_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    file = _owned_file(db, file_id, user_id, with_data=True)
    return Response(
        content=file.data,
        media_type=file.media_type,
        headers={
            "Content-Disposition": content_disposition(file.filename),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
@router.get("/files/{file_id}/preview")
async def preview_conversation_file(
    file_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    file = await asyncio.to_thread(_owned_file, db, file_id, user_id, False)
    async with extraction_slots:
        data = await asyncio.to_thread(_preview_bytes, file)
        return await asyncio.to_thread(build_preview, file.filename, data, CHAT_ATTACHMENT_EXTRACTION_LIMITS, True)
@router.get("/files/{file_id}/pages/{page}")
async def conversation_file_page(
    file_id: int,
    page: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    file = await asyncio.to_thread(_owned_file, db, file_id, user_id, False)
    async with extraction_slots:
        data = await asyncio.to_thread(_preview_bytes, file)
        try:
            image = await asyncio.to_thread(render_pdf_page, data, page)
        except ConversationFileError:
            raise HTTPException(status_code=404, detail="找不到這一頁")
    return Response(content=image, media_type="image/png", headers={"Cache-Control": "private, no-store"})
@router.post("/files/{file_id}/view-token")
def create_conversation_file_view_token(
    file_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    file = _owned_file(db, file_id, user_id, with_data=False)
    if extension_of(file.filename) not in HTML_EXTENSIONS:
        raise HTTPException(status_code=400, detail="只有網頁檔（.html）可以預覽成網頁")
    return {"token": view_token(user_id, file.id), "expires_in": FILE_VIEW_TOKEN_SECONDS}
@router.get("/files/{file_id}/view")
def view_conversation_file(file_id: int, token: str, db: Session = Depends(get_db)):
    owner = view_token_owner(token, file_id)
    if owner is None or not db.query(User.id).filter(User.id == owner, User.is_active.is_(True)).first():
        raise HTTPException(status_code=403, detail="預覽連結無效或已過期，請重新開啟預覽")
    file = _owned_file(db, file_id, owner, with_data=True)
    if extension_of(file.filename) not in HTML_EXTENSIONS:
        raise HTTPException(status_code=404, detail="找不到這個檔案")
    return Response(
        content=file.data,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": html_view_policy(),
            "Cache-Control": "private, no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )
@router.delete("/files/{file_id}")
def delete_conversation_file(
    file_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    try:
        removed = delete_file(db, file_id, user_id, None)
    except ConversationFileError:
        raise HTTPException(status_code=404, detail="找不到這個檔案")
    return {"file": removed}