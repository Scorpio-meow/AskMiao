import json
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models import Conversation, Message, MessageResponse, ConversationResponse
from app.core.config import settings
from app.core.limits import MAX_ATTACHMENT_TEXT_CHARS, MAX_USER_ATTACHMENT_STORAGE_BYTES
from app.rag.agent import attachment_context, query_with_attachments
DEFAULT_CONVERSATION_TITLE = settings.DEFAULT_CONVERSATION_TITLE
MAX_TITLE_PREVIEW_LENGTH = 50
# 讀取路徑的上限：對話清單只列最近的對話；單段對話只回最近的訊息
MAX_LISTED_CONVERSATIONS = 200
MAX_CONVERSATION_MESSAGES = 500
MAX_HISTORY_ATTACHMENT_CHARS = MAX_ATTACHMENT_TEXT_CHARS


class AttachmentQuotaExceeded(Exception):
    pass


def _build_message_response(msg: Message) -> MessageResponse:
    sources = []
    sources_detail = []
    research_trace = []
    attachments = []
    if msg.context_used:
        try:
            parsed = json.loads(msg.context_used)
            if isinstance(parsed, dict):
                sources = parsed.get("sources", [])
                sources_detail = parsed.get("sources_detail", [])
                research_trace = parsed.get("research_trace", [])
                attachments = parsed.get("attachments", [])
            elif isinstance(parsed, list):
                sources = parsed
        except Exception:
            pass
    # 解析後的欄位已完整回傳，原始 context_used（含附件 base64）不再重複輸出
    return MessageResponse(
        id=msg.id,
        content=msg.content,
        is_user=msg.is_user,
        created_at=msg.created_at,
        context_used=None,
        model_name=getattr(msg, "model_name", None),
        attachments=attachments,
        sources=sources,
        sources_detail=sources_detail,
        research_trace=research_trace
    )


def _stored_attachments(msg: Message) -> List[Dict]:
    try:
        parsed = json.loads(msg.context_used)
    except ValueError:
        return []
    return parsed.get("attachments", []) if isinstance(parsed, dict) else []


class ChatService:
    def get_recent_history(
        self,
        db: Session,
        conversation_id: int,
        before_message_id: int,
        limit: int
    ) -> List[Dict[str, str]]:
        """讀取指定訊息之前的最近 limit 則訊息作為 Agent 前文（確保以使用者訊息開頭）"""
        if limit <= 0:
            return []
        rows = db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.id < before_message_id
        ).order_by(Message.id.desc()).limit(limit).all()
        attachment_budget = MAX_HISTORY_ATTACHMENT_CHARS
        history = []
        for msg in rows:
            content = msg.content
            if msg.is_user and msg.context_used and attachment_budget > 0:
                doc_contexts = []
                for att in _stored_attachments(msg):
                    text = (att.get("content") or "")[:attachment_budget]
                    if text:
                        doc_contexts.append(attachment_context(att["filename"], text))
                        attachment_budget -= len(text)
                content = query_with_attachments(content, doc_contexts)
            if content:
                history.append({"role": "user" if msg.is_user else "assistant", "content": content})
        history.reverse()
        while history and history[0]["role"] != "user":
            history.pop(0)
        return history
    def ensure_attachment_quota(self, db: Session, user_id: int, new_bytes: int) -> None:
        """使用者訊息的附件（存在 context_used）總量不可超過每位使用者的配額"""
        used = db.query(func.coalesce(func.sum(func.length(Message.context_used)), 0)).join(
            Conversation, Conversation.id == Message.conversation_id
        ).filter(
            Conversation.user_id == user_id,
            Message.is_user.is_(True),
        ).scalar()
        if int(used) + new_bytes > MAX_USER_ATTACHMENT_STORAGE_BYTES:
            raise AttachmentQuotaExceeded()
    def create_conversation(self, db: Session, user_id: int, title: Optional[str] = None):
        conversation = Conversation(
            user_id=user_id,
            title=title or DEFAULT_CONVERSATION_TITLE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation
    def save_message(
        self,
        db: Session,
        user_id: int,
        content: str,
        is_user: bool,
        conversation_id: Optional[int] = None,
        context_used: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        conversation = None
        if conversation_id is not None:
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id
            ).first()
        if not conversation:
            if not is_user:
                return None
            conversation = self.create_conversation(db, user_id)
        message = Message(
            conversation_id=conversation.id,
            content=content,
            is_user=is_user,
            created_at=datetime.utcnow(),
            context_used=context_used,
            model_name=model_name
        )
        db.add(message)
        conversation.updated_at = datetime.utcnow()
        if is_user and len(content) > 0:
            if conversation.title == DEFAULT_CONVERSATION_TITLE:
                conversation.title = content[:MAX_TITLE_PREVIEW_LENGTH] + "..." if len(content) > MAX_TITLE_PREVIEW_LENGTH else content
        db.commit()
        db.refresh(message)
        return message
    def save_attachment_texts(self, db: Session, message_id: int, contents: List[Optional[str]]) -> None:
        message = db.query(Message).filter(Message.id == message_id).first()
        if not message or not message.context_used:
            return
        context = json.loads(message.context_used)
        for attachment, content in zip(context["attachments"], contents):
            if content:
                attachment["content"] = content
        updated = json.dumps(context, ensure_ascii=False)
        user_id = db.query(Conversation.user_id).filter(Conversation.id == message.conversation_id).scalar()
        try:
            self.ensure_attachment_quota(db, user_id, len(updated) - len(message.context_used))
        except AttachmentQuotaExceeded:
            return
        message.context_used = updated
        db.commit()
    def get_user_conversations(self, db: Session, user_id: int) -> List[ConversationResponse]:
        conversations = db.query(Conversation).filter(
            Conversation.user_id == user_id
        ).order_by(Conversation.updated_at.desc()).limit(MAX_LISTED_CONVERSATIONS).all()
        return [
            ConversationResponse(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                messages=[]
            )
            for conv in conversations
        ]
    def get_conversation_with_messages(
        self, 
        db: Session, 
        conversation_id: int, 
        user_id: int
    ) -> Optional[ConversationResponse]:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id
        ).first()
        if not conversation:
            return None
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[]
        )
    def delete_conversation(self, db: Session, conversation_id: int, user_id: int) -> bool:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id
        ).first()
        if not conversation:
            return False
        db.query(Message).filter(Message.conversation_id == conversation_id).delete()
        db.delete(conversation)
        db.commit()
        return True
    def get_conversation_messages(
        self, 
        db: Session, 
        conversation_id: int, 
        user_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> List[MessageResponse]:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id
        ).first()
        if not conversation:
            return []
        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.desc(), Message.id.desc()).offset(max(0, offset)).limit(max(0, min(limit, MAX_CONVERSATION_MESSAGES))).all()
        return [_build_message_response(msg) for msg in reversed(messages)]
