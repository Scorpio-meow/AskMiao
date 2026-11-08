import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import Callable, Dict, Optional
from sqlalchemy.orm import Session
from app import prompts
from app.core.error_response import SafeClientError
from app.core.llm_client import LlmEndpoint, call_llm
from app.models import SYSTEM_MODEL_PURPOSES, LlmConnection, SystemModel, SystemModelAssignment
from app.services.llm_connections import endpoint_of, models_of
logger = logging.getLogger(__name__)
@dataclass(frozen=True)
class SystemModelTarget:
    endpoint: LlmEndpoint
    model_name: str
    reasoning_effort: str
def system_model_target(db: Session, purpose: str) -> Optional[SystemModelTarget]:
    row = db.get(SystemModel, purpose)
    if row is None:
        return None
    connection = db.get(LlmConnection, row.connection_id)
    if connection is None or connection.owner_id is not None or row.model_name not in models_of(connection):
        logger.warning("系統模型 %s 指定的連線或模型已不存在，視為未指定", purpose)
        return None
    try:
        endpoint = endpoint_of(db, connection)
    except SafeClientError as e:
        logger.warning("系統模型 %s 的連線金鑰無法解密，視為未指定: %s", purpose, e)
        return None
    return SystemModelTarget(endpoint=endpoint, model_name=row.model_name, reasoning_effort=row.reasoning_effort)
def system_models_response(db: Session) -> Dict[str, Optional[Dict[str, object]]]:
    rows = {row.purpose: row for row in db.query(SystemModel).all()}
    return {
        purpose: {
            "connection_id": rows[purpose].connection_id,
            "model_name": rows[purpose].model_name,
            "reasoning_effort": rows[purpose].reasoning_effort,
        }
        if purpose in rows else None
        for purpose in SYSTEM_MODEL_PURPOSES
    }
def set_system_models(db: Session, assignments: Dict[str, Optional[SystemModelAssignment]]) -> None:
    for purpose in SYSTEM_MODEL_PURPOSES:
        assignment = assignments[purpose]
        row = db.get(SystemModel, purpose)
        if assignment is None:
            if row is not None:
                db.delete(row)
            continue
        connection = db.get(LlmConnection, assignment.connection_id)
        if connection is None or connection.owner_id is not None:
            raise SafeClientError("系統模型只能指定共用 API 連線")
        if assignment.model_name not in models_of(connection):
            raise SafeClientError(f"共用連線「{connection.name}」沒有提供模型 {assignment.model_name}")
        if row is None:
            db.add(SystemModel(
                purpose=purpose,
                connection_id=connection.id,
                model_name=assignment.model_name,
                reasoning_effort=assignment.reasoning_effort,
            ))
        else:
            row.connection_id = connection.id
            row.model_name = assignment.model_name
            row.reasoning_effort = assignment.reasoning_effort
def release_system_models(db: Session, connection: LlmConnection, deleted: bool) -> None:
    available = set() if deleted else set(models_of(connection))
    for row in db.query(SystemModel).filter(SystemModel.connection_id == connection.id).all():
        if row.model_name not in available:
            logger.warning("共用連線 %s 不再提供系統模型 %s 使用的 %s，已取消指定", connection.id, row.purpose, row.model_name)
            db.delete(row)
def page_ocr(target: Optional[SystemModelTarget]) -> Optional[Callable[[bytes], str]]:
    if target is None:
        return None
    loop = asyncio.get_running_loop()
    def recognize(png: bytes) -> str:
        image_url = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompts.PDF_OCR},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }]
        request = call_llm(
            messages, endpoint=target.endpoint, model_name=target.model_name, reasoning_effort=target.reasoning_effort
        )
        return asyncio.run_coroutine_threadsafe(request, loop).result()
    return recognize