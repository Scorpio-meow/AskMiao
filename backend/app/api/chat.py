from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models import MessageCreate, ConversationResponse
from app.services.chat_service import AttachmentQuotaExceeded, ChatService
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
from app.core.limits import MAX_CONCURRENT_CHAT_STREAMS_PER_USER
from app.rag.tool_approval import approval_broker
from app.services.llm_connections import chat_option, connections_for_user, resolve_chat_endpoint
from pydantic import BaseModel
router = APIRouter()
chat_service = ChatService()
_active_streams: Dict[int, int] = {}
_attachment_quota_lock = asyncio.Lock()
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
    user_context = None
    if message_data.attachments:
        user_context = json.dumps({
            "attachments": [att.dict() for att in message_data.attachments]
        }, ensure_ascii=False)
    async with (_attachment_quota_lock if user_context else contextlib.nullcontext()):
        if user_context:
            try:
                await asyncio.to_thread(chat_service.ensure_attachment_quota, db, user_id, len(user_context))
            except AttachmentQuotaExceeded:
                raise HTTPException(status_code=413, detail="附件儲存空間已達上限，請刪除部分含附件的對話後再試")
        user_message = await asyncio.to_thread(
            chat_service.save_message,
            db,
            user_id,
            message_data.content,
            True,
            message_data.conversation_id,
            context_used=user_context,
            model_name=message_data.model_name,
        )
    conv_id = user_message.conversation_id
    user_message_id = user_message.id
    conversation_history = await asyncio.to_thread(
        chat_service.get_recent_history,
        db,
        conv_id,
        before_message_id=user_message_id,
        limit=settings.CONVERSATION_HISTORY_MESSAGES
    )
    await asyncio.to_thread(db.close)
    async def sse_generator():
        if not _acquire_stream_slot(user_id):
            err = {"detail": f"每位使用者最多同時進行 {MAX_CONCURRENT_CHAT_STREAMS_PER_USER} 個對話回應，請等待目前的回應完成"}
            yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"
            return
        try:
            yield f"event: start\ndata: {json.dumps({'conversation_id': conv_id, 'user_message_id': user_message_id}, ensure_ascii=False)}\n\n"
            rag_system = get_rag_system()
            collected_tokens = ""
            collected_sources = []
            collected_sources_detail = []
            collected_research_trace = []
            try:
                async for event_item in rag_system.generate_response_stream(
                    message_data.content,
                    conversation_history=conversation_history,
                    endpoint=endpoint,
                    model_name=message_data.model_name,
                    reasoning_effort=message_data.reasoning_effort,
                    attachments=message_data.attachments,
                    approval_user_id=user_id
                ):
                    ev = event_item.get("event")
                    data = event_item.get("data", {})
                    if ev in ("approval_required", "approval_resolved"):
                        yield f"event: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif ev == "attachments_extracted":
                        await asyncio.to_thread(chat_service.save_attachment_texts, db, user_message_id, data["contents"])
                    elif ev == "step_start":
                        yield f"event: step_start\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif ev == "step_end":
                        collected_research_trace.append(data)
                        yield f"event: step_end\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
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
                context_payload = json.dumps({
                    "sources": collected_sources,
                    "sources_detail": collected_sources_detail,
                    "research_trace": collected_research_trace
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
                    "research_trace": collected_research_trace
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
@router.post("/approvals/{approval_id}")
async def resolve_tool_approval(
    approval_id: str,
    decision: ToolApprovalDecision,
    user_id: int = Depends(get_current_user_id)
):
    if not approval_broker.resolve(approval_id, user_id, decision.approved):
        raise HTTPException(status_code=404, detail="找不到待核准的工具呼叫，可能已逾時或已處理")
    return {"approval_id": approval_id, "approved": decision.approved}
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