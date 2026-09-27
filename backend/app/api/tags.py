import asyncio
import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi import status
import os
import logging
from collections.abc import Iterable, Mapping, Sequence
from typing import Optional
import requests
from app.core.config import settings
from app.core.llm_client import get_available_models
logger = logging.getLogger(__name__)
router = APIRouter()
# 遠端模型清單的快取：此路由不需登入，每次請求都外連會讓匿名請求占滿執行緒並放大對外流量
REMOTE_MODELS_CACHE_SECONDS = 30.0
_remote_models_lock = asyncio.Lock()
_remote_models_cache: Optional[tuple[float, tuple[list[str], Optional[str]], Optional[Exception]]] = None


async def fetch_remote_models_cached() -> tuple[list[str], Optional[str]]:
    """在執行緒中查詢遠端模型清單，結果（含失敗）快取 REMOTE_MODELS_CACHE_SECONDS 秒，同時只有一個查詢在進行"""
    global _remote_models_cache
    async with _remote_models_lock:
        now = time.monotonic()
        if _remote_models_cache is None or now - _remote_models_cache[0] >= REMOTE_MODELS_CACHE_SECONDS:
            try:
                result = await asyncio.to_thread(_fetch_remote_models)
                _remote_models_cache = (now, result, None)
            except Exception as exc:
                _remote_models_cache = (now, ([], None), exc)
        _, result, error = _remote_models_cache
    if error is not None:
        raise error
    return result
@router.get("/tags")
async def get_tags():
    configured_models = get_available_models()
    if configured_models:
        azure_dep = settings.AZURE_OPENAI_DEPLOYMENT.split(',')[0].strip() if settings.AZURE_OPENAI_DEPLOYMENT else None
        default_model = settings.MODEL_NAME or azure_dep or configured_models[0]
        if default_model not in configured_models:
            default_model = configured_models[0]
        return {"tags": configured_models, "default": default_model}
    fallback_models = _load_fallback_models()
    configured_default = settings.MODEL_NAME
    default_model: Optional[str] = configured_default
    models: list[str] = []
    try:
        remote_models, remote_default = await fetch_remote_models_cached()
        if remote_models:
            models = remote_models
            if remote_default:
                default_model = remote_default
        else:
            models = []
    except Exception as exc:
        logger.exception("Failed to load models from LLM_API_BASE")
    if not models:
        models = fallback_models
        if not default_model:
            default_model = fallback_models[0] if fallback_models else None
    if default_model and default_model not in models and models:
        default_model = models[0]
    return {"tags": models, "default": default_model}
def _load_fallback_models() -> list[str]:
    available = settings.AVAILABLE_MODELS or ""
    models = [m.strip() for m in available.split(",") if m.strip()]
    return models
def _fetch_remote_models() -> tuple[list[str], Optional[str]]:
    custom_url = (settings.EXTERNAL_TAGS_URL or "").strip()
    base = (settings.LLM_API_BASE or "").strip()
    if custom_url:
        url = custom_url
    else:
        if not base:
            raise RuntimeError(
                "Configuration LLM_API_BASE is required to query remote models (or set EXTERNAL_TAGS_URL)."
            )
        url = f"{base.rstrip('/')}/api/tags"
    timeout = float(settings.LLM_TAGS_TIMEOUT)
    headers: dict[str, str] = {}
    if "ngrok-free.app" in url or settings.ADD_NGROK_HEADER:
        headers["ngrok-skip-browser-warning"] = "true"
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    models, default_model = _parse_model_payload(payload)
    return models, default_model
def _parse_model_payload(payload: object) -> tuple[list[str], Optional[str]]:
    models: list[str] = []
    default_model: Optional[str] = None
    if isinstance(payload, list):
        models = _normalize_model_list(payload)
    elif isinstance(payload, dict):
        candidate_arrays = [
            payload.get("models"),
            payload.get("tags"),
            payload.get("data"),
            payload.get("items"),
        ]
        for candidate in candidate_arrays:
            items = _coerce_to_iterable(candidate)
            if items:
                models = _normalize_model_list(items)
                if models:
                    break
        default_keys = ["default", "default_model", "defaultModel", "defaultTag"]
        for key in default_keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                default_model = value.strip()
                break
        if not models and "data" in payload and isinstance(payload["data"], Mapping):
            inner = _coerce_to_iterable(payload["data"].get("items"))
            if inner:
                models = _normalize_model_list(inner)
    return models, default_model
def _normalize_model_list(items: Iterable[object]) -> list[str]:
    normalized: list[str] = []
    for item in items:
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, dict):
            value = _first_present(item, ["name", "value", "model", "tag", "id", "label"])
        else:
            continue
        if not value:
            continue
        if value not in normalized:
            normalized.append(value)
    return normalized
def _first_present(source: dict, keys: list[str]) -> Optional[str]:
    for key in keys:
        candidate = source.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    nested = source.get("attributes")
    if isinstance(nested, dict):
        return _first_present(nested, keys)
    return None
def _coerce_to_iterable(candidate: object) -> Iterable[object] | None:
    if candidate is None:
        return None
    if isinstance(candidate, (list, tuple, set)):
        return candidate
    if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
        return candidate
    if isinstance(candidate, Mapping):
        for key in ("items", "models", "tags", "data", "values"):
            if key in candidate:
                nested = _coerce_to_iterable(candidate[key])
                if nested:
                    return nested
    return None
@router.get("/external-tags")
def get_external_tags():
    configured_models = get_available_models()
    if configured_models:
        azure_dep = settings.AZURE_OPENAI_DEPLOYMENT.split(',')[0].strip() if settings.AZURE_OPENAI_DEPLOYMENT else None
        default_model = settings.MODEL_NAME or azure_dep or configured_models[0]
        if default_model not in configured_models:
            default_model = configured_models[0]
        return JSONResponse(content={"tags": configured_models, "default": default_model})
    custom_url = (settings.EXTERNAL_TAGS_URL or "").strip()
    base = (settings.LLM_API_BASE or "").strip()
    if custom_url:
        url = custom_url
    else:
        if not base:
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={
                "error": "No external tags URL configured (set EXTERNAL_TAGS_URL or LLM_API_BASE)."
            })
        url = f"{base.rstrip('/')}/api/tags"
    timeout = float(settings.LLM_TAGS_TIMEOUT)
    headers: dict[str, str] = {}
    if "ngrok-free.app" in url or settings.ADD_NGROK_HEADER:
        headers["ngrok-skip-browser-warning"] = "true"
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return JSONResponse(content=resp.json())
    except Exception as exc:
        logger.exception("Failed to fetch external tags from %s", url)
        fallback = _load_fallback_models()
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "Failed to fetch external tags", "models": fallback},
        )
