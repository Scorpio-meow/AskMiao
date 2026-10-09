from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import re
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any
from app.core.limits import (
    MAX_ATTACHMENT_TEXT_CHARS,
    MAX_CHAT_ATTACHMENT_BYTES,
    MAX_CHAT_ATTACHMENTS,
    MAX_CHAT_ATTACHMENTS_TOTAL_BYTES,
    MAX_CHAT_MESSAGE_CHARS,
)
from .database import Base
class User(Base):
    __tablename__ = "users"
    # SQLite 預設會把已刪除的最大 id 配給下一位使用者；AUTOINCREMENT 保證 id 不重用
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    role = Column(String, default="user")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    # 簽發時間早於此時刻的權杖一律無效：建立帳號時等於 created_at（防 id 重用），變更密碼時更新為當下（撤銷所有工作階段）
    tokens_valid_after = Column(DateTime, nullable=False)
    
    conversations = relationship("Conversation", back_populates="user")
class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String, default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    content = Column(Text)
    is_user = Column(Boolean)
    created_at = Column(DateTime, default=datetime.utcnow)
    context_used = Column(Text)
    model_name = Column(String, nullable=True)
    
    conversation = relationship("Conversation", back_populates="messages")
class Document(Base):
    __tablename__ = "documents"
    # 與 users 相同：避免刪除後的文件 id 被新文件重用，舊片段因此誤掛到新文件
    __table_args__ = {"sqlite_autoincrement": True}
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    content = Column(Text)
    file_type = Column(String)
    description = Column(Text, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_processed = Column(Boolean, default=False)
class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    chunk_metadata = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
class CustomApiTool(Base):
    __tablename__ = "custom_api_tools"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    display_name = Column(String)
    description = Column(Text)
    category = Column(String, default="custom_api")
    method = Column(String, default="GET")
    url = Column(String)
    base_url = Column(String, nullable=True)
    path = Column(String, nullable=True)
    headers = Column(Text, nullable=True)
    auth_type = Column(String, default="none")
    auth_config = Column(Text, nullable=True)
    parameters_schema = Column(Text, nullable=True)
    request_body_schema = Column(Text, nullable=True)
    param_locations = Column(Text, nullable=True)
    response_mapping = Column(Text, nullable=True)
    is_enabled = Column(Boolean, default=True)
    # Agent 呼叫前是否需要發問的使用者在對話內核准；建立時依 HTTP 方法決定（見 tool_approval.default_requires_approval）
    requires_approval = Column(Boolean, nullable=False)
    timeout = Column(Integer, default=15)
    spec_version = Column(String, nullable=True)
    raw_spec = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
class McpServer(Base):
    __tablename__ = "mcp_servers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    display_name = Column(String)
    description = Column(Text, nullable=True)
    transport_type = Column(String, default="stdio")
    command = Column(String, nullable=True)
    args = Column(Text, nullable=True)
    env_vars = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    headers = Column(Text, nullable=True)
    is_enabled = Column(Boolean, default=True)
    # MCP 工具的行為無法事先得知，建立時一律需要核准，管理員可逐台關閉
    requires_approval = Column(Boolean, nullable=False)
    status = Column(String, default="disconnected")
    last_error = Column(Text, nullable=True)
    discovered_tools = Column(Text, nullable=True)
    timeout = Column(Integer, default=30)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
class UserCreate(BaseModel):
    username: str
    email: str
    password: str
class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: datetime
# 附件內容只接受內嵌的 base64 data URL；遠端網址會讓模型供應商代為擷取任意位址
DATA_URL_HEADER_PATTERN = re.compile(r"^data:[\w.+-]+/[\w.+-]+(;[\w.+-]+=[\w.+-]+)*;base64$", re.IGNORECASE)
BASE64_BODY_PATTERN = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


def decoded_data_url_size(data_url: str) -> int:
    """不解碼即可算出 base64 data URL 的原始位元組數"""
    body = data_url.split(",", 1)[1]
    return (len(body) * 3) // 4 - body[-2:].count("=")


class FileAttachment(BaseModel):
    filename: str = Field(max_length=255)
    file_type: str = Field(max_length=255)
    file_size: Optional[int] = None
    data_url: Optional[str] = None
    content: Optional[str] = Field(default=None, max_length=MAX_ATTACHMENT_TEXT_CHARS)

    @field_validator("data_url")
    @classmethod
    def validate_data_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        header, separator, body = value.partition(",")
        if not separator or not DATA_URL_HEADER_PATTERN.match(header):
            raise ValueError("附件必須是 base64 編碼的 data: URL")
        if len(body) % 4 != 0 or not BASE64_BODY_PATTERN.match(body):
            raise ValueError("附件的 base64 內容格式無效")
        if decoded_data_url_size(value) > MAX_CHAT_ATTACHMENT_BYTES:
            raise ValueError(f"單一附件不可超過 {MAX_CHAT_ATTACHMENT_BYTES // (1024 * 1024)} MiB")
        return value


class MessageCreate(BaseModel):
    content: str = Field(max_length=MAX_CHAT_MESSAGE_CHARS)
    conversation_id: Optional[int] = None
    model_name: Optional[str] = Field(default=None, max_length=200)
    reasoning_effort: Optional[str] = "medium"
    attachments: Optional[List[FileAttachment]] = Field(default=[], max_length=MAX_CHAT_ATTACHMENTS)

    @model_validator(mode="after")
    def validate_attachment_total(self) -> "MessageCreate":
        total = sum(decoded_data_url_size(att.data_url) for att in self.attachments or [] if att.data_url)
        if total > MAX_CHAT_ATTACHMENTS_TOTAL_BYTES:
            raise ValueError(f"單則訊息的附件總量不可超過 {MAX_CHAT_ATTACHMENTS_TOTAL_BYTES // (1024 * 1024)} MiB")
        return self
class MessageResponse(BaseModel):
    id: int
    content: str
    is_user: bool
    created_at: datetime
    context_used: Optional[str] = None
    model_name: Optional[str] = None
    reasoning_effort: Optional[str] = None
    attachments: Optional[List[FileAttachment]] = None
    sources: Optional[List[str]] = None
    sources_detail: Optional[List[Dict[str, Any]]] = None
    research_trace: Optional[List[Dict[str, Any]]] = None
class ConversationResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []
class ChatResponse(BaseModel):
    message: MessageResponse
    conversation_id: int
class CustomApiToolCreate(BaseModel):
    name: str
    display_name: str
    description: str
    category: Optional[str] = "custom_api"
    method: Optional[str] = "GET"
    url: str
    base_url: Optional[str] = None
    path: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    auth_type: Optional[str] = "none"
    auth_config: Optional[Dict[str, Any]] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    request_body_schema: Optional[Dict[str, Any]] = None
    param_locations: Optional[Dict[str, str]] = None
    response_mapping: Optional[str] = None
    is_enabled: Optional[bool] = True
    requires_approval: Optional[bool] = None
    timeout: Optional[int] = 15
    spec_version: Optional[str] = "manual"
    raw_spec: Optional[str] = None
class CustomApiToolUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    method: Optional[str] = None
    url: Optional[str] = None
    base_url: Optional[str] = None
    path: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    auth_type: Optional[str] = None
    auth_config: Optional[Dict[str, Any]] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    request_body_schema: Optional[Dict[str, Any]] = None
    param_locations: Optional[Dict[str, str]] = None
    response_mapping: Optional[str] = None
    is_enabled: Optional[bool] = None
    requires_approval: Optional[bool] = None
    timeout: Optional[int] = None
class CustomApiToolResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: str
    category: str
    method: str
    url: str
    base_url: Optional[str] = None
    path: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    auth_type: str
    auth_config: Optional[Dict[str, Any]] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    request_body_schema: Optional[Dict[str, Any]] = None
    param_locations: Optional[Dict[str, str]] = None
    response_mapping: Optional[str] = None
    is_enabled: bool
    requires_approval: bool
    timeout: int
    spec_version: Optional[str] = None
    created_at: datetime
    updated_at: datetime
class OpenApiParseRequest(BaseModel):
    spec_content_or_url: str
    default_base_url: Optional[str] = None
class OpenApiImportItem(BaseModel):
    name: str
    display_name: str
    description: str
    method: str
    path: str
    base_url: Optional[str] = None
    full_url: str
    headers: Optional[Dict[str, str]] = None
    auth_type: Optional[str] = "none"
    auth_config: Optional[Dict[str, Any]] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    request_body_schema: Optional[Dict[str, Any]] = None
    param_locations: Optional[Dict[str, str]] = None
    spec_version: Optional[str] = None
class OpenApiImportRequest(BaseModel):
    tools: List[OpenApiImportItem]
    global_base_url: Optional[str] = None
    global_headers: Optional[Dict[str, str]] = None
    global_auth_type: Optional[str] = "none"
    global_auth_config: Optional[Dict[str, Any]] = None
class ToolTestRequest(BaseModel):
    arguments: Optional[Dict[str, Any]] = {}
class McpServerCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    transport_type: Optional[str] = "stdio"
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env_vars: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    is_enabled: Optional[bool] = True
    requires_approval: Optional[bool] = None
    timeout: Optional[int] = 30
class McpServerUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    transport_type: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env_vars: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    is_enabled: Optional[bool] = None
    requires_approval: Optional[bool] = None
    timeout: Optional[int] = None
class McpServerResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    transport_type: str
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env_vars: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    is_enabled: bool
    requires_approval: bool
    status: str
    last_error: Optional[str] = None
    discovered_tools: Optional[List[Dict[str, Any]]] = None
    timeout: int
    created_at: datetime
    updated_at: datetime
class McpToolTestRequest(BaseModel):
    arguments: Optional[Dict[str, Any]] = {}
