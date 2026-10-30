import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_response import SafeClientError
from app.core.jwt_auth import get_current_active_user, get_current_admin_user
from app.core.llm_client import LlmEndpoint, call_llm, list_models
from app.core.security_logging import log_security_event
from app.core.tool_secrets import decrypt_json
from app.models import (
    LlmConnection,
    LlmConnectionCreate,
    LlmConnectionTestRequest,
    LlmConnectionUpdate,
    LlmModelDiscoveryRequest,
    SharedLlmConnectionCreate,
    SharedLlmConnectionUpdate,
)
from app.models.database import get_db
from app.services.llm_connections import (
    CONNECTION_TEST_PROMPT,
    CONNECTION_TEST_REPLY_CHARS,
    chat_option,
    connection_response,
    connections_for_user,
    describe_connection_error,
    encrypt_api_key,
    endpoint_of,
    models_of,
    provider_presets,
    validate_connection,
    validated_user_ids,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/llm-connections", tags=["llm_connections"])
admin_router = APIRouter(prefix="/api/admin/llm-connections", tags=["admin"])


def _get_personal(db: Session, connection_id: int, user_id: int) -> LlmConnection:
    connection = db.get(LlmConnection, connection_id)
    if connection is None or connection.owner_id != user_id:
        raise HTTPException(status_code=404, detail="找不到這個 API 連線")
    return connection


def _get_shared(db: Session, connection_id: int) -> LlmConnection:
    connection = db.get(LlmConnection, connection_id)
    if connection is None or connection.owner_id is not None:
        raise HTTPException(status_code=404, detail="找不到這個共用 API 連線")
    return connection


async def _validate(connection: LlmConnection, public_only: bool) -> None:
    try:
        await validate_connection(
            connection.provider,
            connection.api_base,
            connection.api_key is not None,
            models_of(connection),
            connection.max_output_tokens,
            public_only,
        )
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _apply_update(connection: LlmConnection, changes: Dict[str, Any]) -> None:
    cleared = [field for field in ("name", "provider", "api_base", "models") if field in changes and changes[field] is None]
    if cleared:
        raise HTTPException(status_code=400, detail=f"這些欄位不可設為空值：{', '.join(cleared)}")
    endpoint_changed = any(field in changes and changes[field] != getattr(connection, field) for field in ("provider", "api_base"))
    for field in ("name", "provider", "api_base", "max_output_tokens"):
        if field in changes:
            setattr(connection, field, changes[field])
    if "models" in changes:
        connection.models = json.dumps(changes["models"], ensure_ascii=False)
    if changes.get("api_key"):
        connection.api_key = encrypt_api_key(changes["api_key"])
    elif endpoint_changed:
        connection.api_key = None


def _new_connection(data: LlmConnectionCreate, owner_id) -> LlmConnection:
    return LlmConnection(
        name=data.name,
        provider=data.provider,
        api_base=data.api_base,
        api_key=encrypt_api_key(data.api_key),
        models=json.dumps(data.models, ensure_ascii=False),
        max_output_tokens=data.max_output_tokens,
        owner_id=owner_id,
    )


@router.get("/providers")
async def get_providers(current_user: dict = Depends(get_current_active_user)):
    return {"providers": provider_presets()}


@router.get("")
def list_my_connections(db: Session = Depends(get_db), current_user: dict = Depends(get_current_active_user)):
    connections = connections_for_user(db, current_user["user_id"])
    return {
        "personal": [connection_response(c, include_access=False) for c in connections if c.owner_id is not None],
        "shared": [chat_option(c) for c in connections if c.owner_id is None],
    }


@router.post("", status_code=201)
async def create_my_connection(
    data: LlmConnectionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    connection = _new_connection(data, current_user["user_id"])
    await _validate(connection, public_only=not current_user["is_admin"])
    db.add(connection)
    db.commit()
    db.refresh(connection)
    log_security_event("LLM_CONNECTION_CREATED", request=request, user_id=current_user["user_id"], details={
        "connection_id": connection.id, "provider": connection.provider, "api_base": connection.api_base
    })
    return connection_response(connection, include_access=False)


@router.put("/{connection_id}")
async def update_my_connection(
    connection_id: int,
    data: LlmConnectionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    connection = _get_personal(db, connection_id, current_user["user_id"])
    _apply_update(connection, data.model_dump(exclude_unset=True))
    try:
        await _validate(connection, public_only=not current_user["is_admin"])
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    db.refresh(connection)
    log_security_event("LLM_CONNECTION_UPDATED", request=request, user_id=current_user["user_id"], details={
        "connection_id": connection.id, "provider": connection.provider, "api_base": connection.api_base
    })
    return connection_response(connection, include_access=False)


@router.delete("/{connection_id}")
def delete_my_connection(
    connection_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    connection = _get_personal(db, connection_id, current_user["user_id"])
    db.delete(connection)
    db.commit()
    log_security_event("LLM_CONNECTION_DELETED", request=request, user_id=current_user["user_id"], details={
        "connection_id": connection_id
    })
    return {"message": "已刪除 API 連線"}


@router.post("/discover-models")
async def discover_models(
    data: LlmModelDiscoveryRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    api_key = data.api_key
    if api_key is None and data.connection_id is not None:
        connection = db.get(LlmConnection, data.connection_id)
        allowed = connection is not None and (
            connection.owner_id == current_user["user_id"] or (connection.owner_id is None and current_user["is_admin"])
        )
        if not allowed:
            raise HTTPException(status_code=404, detail="找不到這個 API 連線")
        if data.provider == connection.provider and data.api_base == connection.api_base:
            try:
                api_key = (decrypt_json(connection.api_key) or {}).get("api_key")
            except SafeClientError as e:
                raise HTTPException(status_code=400, detail=str(e))
    db.close()
    endpoint = LlmEndpoint(data.provider, data.api_base, api_key, None, not current_user["is_admin"])
    try:
        models = await list_models(endpoint)
    except Exception as e:
        logger.info("取得 %s 的模型清單失敗", data.provider, exc_info=True)
        raise HTTPException(status_code=400, detail=describe_connection_error(e))
    return {"models": models}


@router.post("/{connection_id}/test")
async def test_connection(
    connection_id: int,
    data: LlmConnectionTestRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    connection = db.get(LlmConnection, connection_id)
    allowed = connection is not None and (
        connection.owner_id == current_user["user_id"] or (connection.owner_id is None and current_user["is_admin"])
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="找不到這個 API 連線")
    if data.model_name not in models_of(connection):
        raise HTTPException(status_code=400, detail="這個 API 連線沒有提供此模型")
    try:
        endpoint = endpoint_of(db, connection)
        db.close()
        reply = await call_llm(
            CONNECTION_TEST_PROMPT,
            endpoint=endpoint,
            model_name=data.model_name,
            timeout=settings.LLM_TIMEOUT,
            reasoning_effort="none",
        )
    except Exception as e:
        logger.info("API 連線 %s 測試失敗", connection_id, exc_info=True)
        return {"ok": False, "error": describe_connection_error(e)}
    return {"ok": True, "reply": reply[:CONNECTION_TEST_REPLY_CHARS]}


@admin_router.get("")
def list_shared_connections(db: Session = Depends(get_db), current_user: dict = Depends(get_current_admin_user)):
    connections = db.query(LlmConnection).filter(LlmConnection.owner_id.is_(None)).order_by(LlmConnection.id).all()
    return {"connections": [connection_response(c, include_access=True) for c in connections]}


@admin_router.post("", status_code=201)
async def create_shared_connection(
    data: SharedLlmConnectionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user),
):
    connection = _new_connection(data, None)
    try:
        connection.allowed_user_ids = validated_user_ids(db, data.allowed_user_ids)
    except SafeClientError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _validate(connection, public_only=False)
    db.add(connection)
    db.commit()
    db.refresh(connection)
    log_security_event("ADMIN_LLM_CONNECTION_CREATED", request=request, user_id=current_user["user_id"], details={
        "connection_id": connection.id, "provider": connection.provider,
        "allowed_user_ids": json.loads(connection.allowed_user_ids) if connection.allowed_user_ids else None
    })
    return connection_response(connection, include_access=True)


@admin_router.put("/{connection_id}")
async def update_shared_connection(
    connection_id: int,
    data: SharedLlmConnectionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user),
):
    connection = _get_shared(db, connection_id)
    changes = data.model_dump(exclude_unset=True)
    _apply_update(connection, changes)
    try:
        if changes.get("allowed_user_ids") is not None:
            connection.allowed_user_ids = validated_user_ids(db, changes["allowed_user_ids"])
        await _validate(connection, public_only=False)
    except SafeClientError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    db.refresh(connection)
    log_security_event("ADMIN_LLM_CONNECTION_UPDATED", request=request, user_id=current_user["user_id"], details={
        "connection_id": connection.id, "provider": connection.provider,
        "allowed_user_ids": json.loads(connection.allowed_user_ids) if connection.allowed_user_ids else None
    })
    return connection_response(connection, include_access=True)


@admin_router.delete("/{connection_id}")
def delete_shared_connection(
    connection_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user),
):
    connection = _get_shared(db, connection_id)
    db.delete(connection)
    db.commit()
    log_security_event("ADMIN_LLM_CONNECTION_DELETED", request=request, user_id=current_user["user_id"], details={
        "connection_id": connection_id
    })
    return {"message": "已刪除共用 API 連線"}
