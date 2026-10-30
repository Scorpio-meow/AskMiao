import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_response import SafeClientError
from app.core.llm_client import (
    DEFAULT_CLAUDE_MODELS,
    DEFAULT_GEMINI_MODELS,
    DEFAULT_OPENAI_MODELS,
    FOUNDRY_ANTHROPIC_HOST_SUFFIX,
    OLLAMA_CLOUD_HOST,
    LlmEndpoint,
)
from app.core.ssrf_protection import DnsPool, SSRFProtectionError, validate_url_ssrf
from app.core.tool_secrets import decrypt_json, encrypt_json
from app.models import LlmConnection, User

logger = logging.getLogger(__name__)

PROVIDERS_REQUIRING_API_KEY = ("anthropic", "gemini", "foundry")
PRIVATE_ADDRESS_MESSAGE = "API 位址無法使用：個人連線只能連到可從網際網路解析的公開位址，內部網路的服務請管理員設為共用連線"
CONNECTION_TEST_PROMPT = [{"role": "user", "content": "請只回覆「OK」。"}]
CONNECTION_TEST_REPLY_CHARS = 200


def provider_presets() -> List[Dict[str, Any]]:
    return [
        {"provider": "openai", "label": "OpenAI 或相容的 API", "api_base": settings.OPENAI_API_BASE,
         "models": DEFAULT_OPENAI_MODELS, "requires_api_key": False, "uses_max_output_tokens": False},
        {"provider": "anthropic", "label": "Anthropic Claude", "api_base": settings.ANTHROPIC_API_BASE,
         "models": DEFAULT_CLAUDE_MODELS, "requires_api_key": True, "uses_max_output_tokens": True},
        {"provider": "gemini", "label": "Google Gemini", "api_base": settings.GEMINI_API_BASE,
         "models": DEFAULT_GEMINI_MODELS, "requires_api_key": True, "uses_max_output_tokens": False},
        {"provider": "foundry", "label": "Microsoft Foundry／Azure OpenAI", "api_base": "",
         "models": [], "requires_api_key": True, "uses_max_output_tokens": True},
        {"provider": "ollama", "label": "Ollama", "api_base": f"https://{OLLAMA_CLOUD_HOST}",
         "models": [], "requires_api_key": False, "uses_max_output_tokens": False},
    ]


def _user_ids(stored: Optional[str]) -> Optional[List[int]]:
    if stored is None:
        return None
    try:
        ids = json.loads(stored)
    except json.JSONDecodeError:
        return []
    return ids if isinstance(ids, list) else []


def models_of(connection: LlmConnection) -> List[str]:
    return json.loads(connection.models)


def visible_to(connection: LlmConnection, user_id: int) -> bool:
    if connection.owner_id is not None:
        return connection.owner_id == user_id
    allowed = _user_ids(connection.allowed_user_ids)
    return allowed is None or user_id in allowed


def connections_for_user(db: Session, user_id: int) -> List[LlmConnection]:
    rows = (
        db.query(LlmConnection)
        .filter((LlmConnection.owner_id == user_id) | LlmConnection.owner_id.is_(None))
        .order_by(LlmConnection.owner_id.is_(None), LlmConnection.id)
        .all()
    )
    return [connection for connection in rows if visible_to(connection, user_id)]


def requires_public_address(db: Session, connection: LlmConnection) -> bool:
    if connection.owner_id is None:
        return False
    owner = db.get(User, connection.owner_id)
    return not (owner and owner.is_admin)


def endpoint_of(db: Session, connection: LlmConnection) -> LlmEndpoint:
    secrets = decrypt_json(connection.api_key) or {}
    return LlmEndpoint(
        provider=connection.provider,
        api_base=connection.api_base,
        api_key=secrets.get("api_key"),
        max_output_tokens=connection.max_output_tokens,
        public_only=requires_public_address(db, connection),
    )


def resolve_chat_endpoint(db: Session, user_id: int, connection_id: int, model_name: str) -> LlmEndpoint:
    connection = db.get(LlmConnection, connection_id)
    if connection is None or not visible_to(connection, user_id):
        raise SafeClientError("找不到這個 API 連線，或你沒有使用權限")
    if model_name not in models_of(connection):
        raise SafeClientError("這個 API 連線沒有提供此模型")
    return endpoint_of(db, connection)


def _is_claude_connection(provider: str, models: List[str]) -> bool:
    return provider == "anthropic" or (provider == "foundry" and any(m.startswith("claude-") for m in models))


async def validate_connection(
    provider: str,
    api_base: str,
    has_api_key: bool,
    models: List[str],
    max_output_tokens: Optional[int],
    public_only: bool,
) -> None:
    if provider in PROVIDERS_REQUIRING_API_KEY and not has_api_key:
        raise SafeClientError("這個供應商需要 API 金鑰")
    if _is_claude_connection(provider, models):
        if max_output_tokens is None:
            raise SafeClientError("Claude 模型需要設定輸出 token 上限")
        if provider == "foundry" and not (urlparse(api_base).hostname or "").endswith(FOUNDRY_ANTHROPIC_HOST_SUFFIX):
            raise SafeClientError(f"Foundry 上的 Claude 部署需要 Foundry 資源端點（*{FOUNDRY_ANTHROPIC_HOST_SUFFIX}）")
    if public_only:
        is_valid, reason, _ = await validate_url_ssrf(api_base, DnsPool.USER_URL)
        if not is_valid:
            logger.info("拒絕個人 API 連線位址 %s: %s", api_base, reason)
            raise SafeClientError(PRIVATE_ADDRESS_MESSAGE)


def encrypt_api_key(api_key: Optional[str]) -> Optional[str]:
    return encrypt_json({"api_key": api_key}) if api_key else None


def connection_response(connection: LlmConnection, include_access: bool) -> Dict[str, Any]:
    response = {
        "id": connection.id,
        "name": connection.name,
        "provider": connection.provider,
        "api_base": connection.api_base,
        "models": models_of(connection),
        "max_output_tokens": connection.max_output_tokens,
        "has_api_key": connection.api_key is not None,
        "scope": "shared" if connection.owner_id is None else "personal",
        "created_at": connection.created_at,
        "updated_at": connection.updated_at,
    }
    if include_access:
        response["allowed_user_ids"] = _user_ids(connection.allowed_user_ids)
    return response


def chat_option(connection: LlmConnection) -> Dict[str, Any]:
    return {
        "id": connection.id,
        "name": connection.name,
        "provider": connection.provider,
        "scope": "shared" if connection.owner_id is None else "personal",
        "models": models_of(connection),
    }


def validated_user_ids(db: Session, user_ids: List[int]) -> Optional[str]:
    unique_ids = sorted(set(user_ids))
    existing = {row.id for row in db.query(User.id).filter(User.id.in_(unique_ids)).all()} if unique_ids else set()
    missing = [user_id for user_id in unique_ids if user_id not in existing]
    if missing:
        raise SafeClientError(f"找不到使用者：{', '.join(map(str, missing))}")
    return json.dumps(unique_ids) if unique_ids else None


def user_connection_access(db: Session, user_id: int) -> Dict[str, Any]:
    connections = db.query(LlmConnection).filter(
        (LlmConnection.owner_id == user_id) | LlmConnection.owner_id.is_(None)
    ).order_by(LlmConnection.id).all()
    return {
        "personal": [chat_option(c) for c in connections if c.owner_id is not None],
        "shared": [
            {**chat_option(c), "all_users": c.allowed_user_ids is None, "allowed": visible_to(c, user_id)}
            for c in connections if c.owner_id is None
        ],
    }


def set_user_shared_access(db: Session, user_id: int, connection_ids: List[int]) -> None:
    shared = db.query(LlmConnection).filter(LlmConnection.owner_id.is_(None)).all()
    unknown = sorted(set(connection_ids) - {c.id for c in shared})
    if unknown:
        raise SafeClientError(f"找不到共用 API 連線：{', '.join(map(str, unknown))}")
    wanted = set(connection_ids)
    for connection in shared:
        if connection.allowed_user_ids is None:
            continue
        ids = [uid for uid in _user_ids(connection.allowed_user_ids) if uid != user_id]
        if connection.id in wanted:
            ids.append(user_id)
        connection.allowed_user_ids = json.dumps(sorted(ids))


def remove_user_connections(db: Session, user_id: int) -> None:
    db.query(LlmConnection).filter(LlmConnection.owner_id == user_id).delete(synchronize_session=False)
    for connection in db.query(LlmConnection).filter(LlmConnection.allowed_user_ids.isnot(None)).all():
        remaining = [uid for uid in _user_ids(connection.allowed_user_ids) if uid != user_id]
        connection.allowed_user_ids = json.dumps(remaining)


def describe_connection_error(error: BaseException) -> str:
    cause: Optional[BaseException] = error
    while cause is not None:
        if isinstance(cause, SSRFProtectionError):
            return PRIVATE_ADDRESS_MESSAGE
        cause = cause.__cause__ or cause.__context__
    import anthropic
    if isinstance(error, (httpx.TimeoutException, anthropic.APITimeoutError)):
        return "連線逾時，請確認 API 位址可以連線"
    if isinstance(error, (httpx.HTTPError, anthropic.APIConnectionError)):
        return "無法連線到 API 位址"
    if isinstance(error, anthropic.APIStatusError):
        return f"API 回應錯誤 ({error.status_code}): {error.message[:500]}"
    if isinstance(error, (RuntimeError, ValueError)):
        return str(error)[:500]
    return "連線測試失敗"
