import asyncio
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, undefer
from app.core.limits import (
    MAX_CONVERSATION_FILE_BYTES,
    MAX_CONVERSATION_FILES,
    MAX_FILENAME_BYTES,
    MAX_USER_ATTACHMENT_STORAGE_BYTES,
    MIB,
)
from app.models import Conversation, ConversationFile, Message
storage_lock = asyncio.Lock()
MEDIA_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".json": "application/json",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
    ".ppt": "application/vnd.ms-powerpoint",
    ".html": "text/plain; charset=utf-8",
    ".htm": "text/plain; charset=utf-8",
    ".css": "text/plain; charset=utf-8",
    ".js": "text/plain; charset=utf-8",
    ".ts": "text/plain; charset=utf-8",
    ".py": "text/plain; charset=utf-8",
}
OCTET_STREAM = "application/octet-stream"
FORBIDDEN_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
class ConversationFileError(Exception):
    pass
class AttachmentQuotaExceeded(Exception):
    pass
def extension_of(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
def media_type_for(filename: str) -> str:
    return MEDIA_TYPES.get(extension_of(filename), OCTET_STREAM)
def clean_filename(filename: str) -> str:
    name = FORBIDDEN_FILENAME_CHARS.sub("", filename.replace("\\", "/").rsplit("/", 1)[-1]).strip().strip(".")
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
    suffix = dot + extension
    if not stem.strip():
        raise ConversationFileError(f"檔名不可空白：{filename[:100]}")
    while len((stem + suffix).encode("utf-8")) > MAX_FILENAME_BYTES:
        stem = stem[:-1]
    return stem.strip() + suffix
def content_disposition(filename: str) -> str:
    quoted = quote(filename)
    return f'attachment; filename="{filename}"' if quoted == filename else f"attachment; filename*=UTF-8''{quoted}"
def versioned_filename(parent: ConversationFile, version: int) -> str:
    stem, _, extension = parent.filename.rpartition(".")
    own_suffix = f" v{parent.version}"
    if parent.version > 1 and stem.endswith(own_suffix):
        stem = stem[:-len(own_suffix)]
    return clean_filename(f"{stem} v{version}.{extension}")
def summary(file: ConversationFile) -> Dict[str, Any]:
    return {
        "id": file.id,
        "filename": file.filename,
        "media_type": file.media_type,
        "size_bytes": file.size_bytes,
        "origin": file.origin,
        "version": file.version,
        "parent_id": file.parent_id,
        "created_at": file.created_at.isoformat() if file.created_at else None,
    }
def storage_used(db: Session, user_id: int) -> int:
    messages = db.query(func.coalesce(func.sum(func.length(Message.context_used)), 0)).join(
        Conversation, Conversation.id == Message.conversation_id
    ).filter(Conversation.user_id == user_id, Message.is_user.is_(True)).scalar()
    files = db.query(func.coalesce(func.sum(ConversationFile.size_bytes), 0)).filter(ConversationFile.user_id == user_id).scalar()
    return int(messages) + int(files)
def ensure_storage_quota(db: Session, user_id: int, new_bytes: int) -> None:
    if storage_used(db, user_id) + new_bytes > MAX_USER_ATTACHMENT_STORAGE_BYTES:
        raise AttachmentQuotaExceeded()
def ensure_file_capacity(db: Session, conversation_id: Optional[int], new_files: int) -> None:
    existing = 0 if conversation_id is None else db.query(func.count(ConversationFile.id)).filter(
        ConversationFile.conversation_id == conversation_id
    ).scalar()
    if existing + new_files > MAX_CONVERSATION_FILES:
        raise ConversationFileError(f"每個對話最多 {MAX_CONVERSATION_FILES} 個檔案，請先刪除不需要的檔案")
def ensure_file_size(size: int) -> None:
    if size > MAX_CONVERSATION_FILE_BYTES:
        raise ConversationFileError(f"檔案不可超過 {MAX_CONVERSATION_FILE_BYTES // MIB} MiB")
def list_files(db: Session, conversation_id: int, user_id: int) -> List[ConversationFile]:
    return db.query(ConversationFile).filter(
        ConversationFile.conversation_id == conversation_id,
        ConversationFile.user_id == user_id,
    ).order_by(ConversationFile.id).all()
def get_file(db: Session, file_id: int, user_id: int, conversation_id: Optional[int], with_data: bool) -> ConversationFile:
    query = db.query(ConversationFile).filter(ConversationFile.id == file_id, ConversationFile.user_id == user_id)
    if conversation_id is not None:
        query = query.filter(ConversationFile.conversation_id == conversation_id)
    if with_data:
        query = query.options(undefer(ConversationFile.data))
    file = query.first()
    if file is None:
        raise ConversationFileError(f"這個對話沒有編號 #{file_id} 的檔案")
    return file
def next_version(db: Session, parent: ConversationFile) -> int:
    root_id = parent.root_id or parent.id
    latest = db.query(func.max(ConversationFile.version)).filter(
        or_(ConversationFile.id == root_id, ConversationFile.root_id == root_id)
    ).scalar()
    return max(int(latest or 0), parent.version) + 1
def add_file(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
    filename: str,
    data: bytes,
    origin: str,
    parent: Optional[ConversationFile],
    enforce_limits: bool,
) -> ConversationFile:
    ensure_file_size(len(data))
    if not db.query(Conversation.id).filter(Conversation.id == conversation_id, Conversation.user_id == user_id).first():
        raise ConversationFileError("這個對話已被刪除，檔案沒有儲存")
    if enforce_limits:
        ensure_file_capacity(db, conversation_id, 1)
        ensure_storage_quota(db, user_id, len(data))
    if parent is None:
        name, version, root_id = clean_filename(filename), 1, None
    else:
        version = next_version(db, parent)
        name, root_id = versioned_filename(parent, version), parent.root_id or parent.id
    file = ConversationFile(
        conversation_id=conversation_id,
        user_id=user_id,
        filename=name,
        media_type=media_type_for(name),
        size_bytes=len(data),
        data=data,
        origin=origin,
        parent_id=parent.id if parent else None,
        root_id=root_id,
        version=version,
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file
def delete_file(db: Session, file_id: int, user_id: int, conversation_id: Optional[int]) -> Dict[str, Any]:
    file = get_file(db, file_id, user_id, conversation_id, with_data=False)
    removed = summary(file)
    db.delete(file)
    db.commit()
    return removed
def delete_files_for_conversations(db: Session, conversation_ids: Iterable[int]) -> None:
    ids = list(conversation_ids)
    if ids:
        db.query(ConversationFile).filter(ConversationFile.conversation_id.in_(ids)).delete(synchronize_session=False)