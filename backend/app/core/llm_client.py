import json
import uuid
import logging
import asyncio
from dataclasses import dataclass
import httpx
from urllib.parse import urlparse
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from app.core.config import settings
from app.core.ssrf_protection import DnsPool, SSRFSafeHttpx2Transport, SSRFSafeTransport
logger = logging.getLogger(__name__)
_http_client: Optional[httpx.AsyncClient] = None
_public_http_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()
_anthropic_http_clients: Dict[bool, Any] = {}
_anthropic_output_limits: Dict[Tuple[str, str], int] = {}
_anthropic_output_limits_lock = asyncio.Lock()
@dataclass(frozen=True)
class LlmEndpoint:
    provider: str
    api_base: str
    api_key: Optional[str]
    max_output_tokens: Optional[int]
    public_only: bool
FOUNDRY_ANTHROPIC_HOST_SUFFIX = ".services.ai.azure.com"
REASONING_EFFORT_VALUES = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
OPENAI_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4")
# Claude 的工具呼叫回合需原樣送回 response.content（含 thinking 區塊），以此鍵附在標準化後的 assistant 訊息上
ANTHROPIC_CONTENT_KEY = "_anthropic_content"
OLLAMA_HEADERS = {
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true"
}
# 等待連線池名額的上限與單次請求逾時分開：池被占滿時很快失敗，而不是排隊到 LLM_TIMEOUT
LLM_POOL_ACQUIRE_TIMEOUT_SECONDS = 15.0
OLLAMA_CLOUD_HOST = "ollama.com"
OLLAMA_THINKING_KEY = "_ollama_thinking"
OLLAMA_THINK_BY_REASONING = {"minimal": "low", "low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}
def _new_llm_http_client(transport: Optional[httpx.AsyncBaseTransport]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.LLM_TIMEOUT, pool=LLM_POOL_ACQUIRE_TIMEOUT_SECONDS),
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        transport=transport
    )
async def get_llm_http_client(public_only: bool) -> httpx.AsyncClient:
    global _http_client, _public_http_client
    async with _client_lock:
        if public_only:
            if _public_http_client is None or _public_http_client.is_closed:
                _public_http_client = _new_llm_http_client(SSRFSafeTransport(DnsPool.USER_URL))
            return _public_http_client
        if _http_client is None or _http_client.is_closed:
            _http_client = _new_llm_http_client(None)
        return _http_client
async def close_llm_http_client():
    global _http_client, _public_http_client
    for client in (_http_client, _public_http_client, *_anthropic_http_clients.values()):
        if client is not None and not client.is_closed:
            await client.aclose()
    _http_client = None
    _public_http_client = None
    _anthropic_http_clients.clear()
OPENAI_RESPONSES_MODEL_PREFIXES = ("gpt-6",)
FOUNDRY_RESPONSES_MODEL_PREFIXES = ("gpt-", "o3", "o4")
CHAT_COMPLETIONS_ONLY_PREFIXES = ("gpt-oss", "o3-mini")
OPENAI_RESPONSES_NONE_EFFORT_MARKER = "luna"
OPENAI_OUTPUT_KEY = "_openai_output"
DEFAULT_OPENAI_MODELS = ["gpt-6.1-sol", "gpt-6-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.4", "gpt-5.4-mini"]
DEFAULT_CLAUDE_MODELS = ["claude-opus-5-5", "claude-fable-5-1", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-sonnet-5", "claude-opus-5", "claude-fable-5", "claude-opus-4-8", "claude-haiku-4-5"]
ANTHROPIC_CACHE_CONTROL = {"type": "ephemeral"}
ANTHROPIC_EFFORT_BY_REASONING = {"none": "low", "minimal": "low", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "max"}
ANTHROPIC_MODELS_WITHOUT_EFFORT = ("claude-haiku-4-5",)
# 這些模型未送 thinking 時完全不思考，需明確啟用 adaptive；較新的模型未送 thinking 即為 adaptive
ANTHROPIC_MODELS_WITH_OPT_IN_THINKING = ("claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6")
ANTHROPIC_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"
ANTHROPIC_INCOMPLETE_STOP_REASONS = {
    "pause_turn": "Claude 回合被暫停（pause_turn），回應不完整",
    "model_context_window_exceeded": "對話超出 Claude 的 context window，請縮短內容"
}
DEFAULT_GEMINI_MODELS = ["gemini-4-argon", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
GEMINI_EFFORT_BY_REASONING = {"none": "minimal", "minimal": "minimal", "low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}
def is_foundry_enabled() -> bool:
    return bool(settings.FOUNDRY_API_KEY and settings.FOUNDRY_ENDPOINT)
def get_available_models() -> List[str]:
    available = (settings.AVAILABLE_MODELS or "").strip()
    if available:
        return [m.strip() for m in available.split(",") if m.strip()]

    models: List[str] = []

    if is_foundry_enabled():
        if settings.FOUNDRY_DEPLOYMENT:
            deployments = [d.strip() for d in settings.FOUNDRY_DEPLOYMENT.split(",") if d.strip()]
            for dep in deployments:
                if dep not in models:
                    models.append(dep)
        else:
            models.append("gpt-6-sol")

    if settings.OPENAI_API_KEY:
        for m in DEFAULT_OPENAI_MODELS:
            if m not in models:
                models.append(m)

    if settings.ANTHROPIC_API_KEY:
        for m in DEFAULT_CLAUDE_MODELS:
            if m not in models:
                models.append(m)

    if settings.GEMINI_API_KEY:
        for m in DEFAULT_GEMINI_MODELS:
            if m not in models:
                models.append(m)

    return models
def _foundry_deployments() -> List[str]:
    return [d.strip() for d in (settings.FOUNDRY_DEPLOYMENT or "").split(",") if d.strip()]
def resolve_model_name(model_name: Optional[str]) -> str:
    target = model_name or settings.MODEL_NAME
    if target:
        return target
    available = get_available_models()
    if not available:
        raise ValueError("未指定模型，且未設定 MODEL_NAME、AVAILABLE_MODELS 或任何供應商金鑰")
    return available[0]
def resolve_provider(model_name: str) -> str:
    """依模型名稱決定供應商：foundry、anthropic、gemini、openai 或 ollama"""
    if is_foundry_enabled() and model_name in _foundry_deployments():
        return "anthropic" if model_name.startswith("claude-") else "foundry"
    if model_name.startswith("claude-") and settings.ANTHROPIC_API_KEY:
        return "anthropic"
    if model_name.startswith("gemini-") and settings.GEMINI_API_KEY:
        return "gemini"
    if model_name.startswith(OPENAI_MODEL_PREFIXES):
        if settings.OPENAI_API_KEY:
            return "openai"
        if is_foundry_enabled():
            return "foundry"
    return "ollama"
def system_endpoint(model_name: str) -> LlmEndpoint:
    provider = resolve_provider(model_name)
    if provider == "foundry" or is_foundry_claude(model_name):
        return LlmEndpoint("foundry", settings.FOUNDRY_ENDPOINT, settings.FOUNDRY_API_KEY, settings.ANTHROPIC_MAX_TOKENS, False)
    if provider == "anthropic":
        return LlmEndpoint("anthropic", settings.ANTHROPIC_API_BASE, settings.ANTHROPIC_API_KEY, settings.ANTHROPIC_MAX_TOKENS, False)
    if provider == "gemini":
        return LlmEndpoint("gemini", settings.GEMINI_API_BASE, settings.GEMINI_API_KEY, None, False)
    if provider == "openai":
        return LlmEndpoint("openai", settings.OPENAI_API_BASE, settings.OPENAI_API_KEY, None, False)
    ollama_key = settings.OLLAMA_API_KEY if urlparse(settings.LLM_API_BASE).hostname == OLLAMA_CLOUD_HOST else None
    return LlmEndpoint("ollama", settings.LLM_API_BASE, ollama_key, None, False)
def _public_message(message: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in message.items() if not key.startswith("_")}
def _parse_image_url(url: str) -> Tuple[str, str]:
    """data URL 回傳 (media_type, base64 內容)。
    只接受內嵌影像：遠端網址會讓模型供應商代為擷取使用者指定的任意位址"""
    if url.startswith("data:") and "," in url:
        header, data = url.split(",", 1)
        return header[5:].split(";")[0], data
    raise ValueError("影像只接受 base64 data: URL")
def _as_arguments_dict(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if not arguments:
        return {}
    return json.loads(arguments)
def _openai_endpoint(endpoint: LlmEndpoint) -> Tuple[str, Dict[str, str]]:
    headers = {"Content-Type": "application/json"}
    base = endpoint.api_base.rstrip("/")
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    if endpoint.provider == "foundry":
        headers["api-key"] = endpoint.api_key
        return f"{base}/openai/v1/chat/completions", headers
    if endpoint.provider == "gemini":
        return f"{base}/v1beta/openai/chat/completions", headers
    return f"{base}/chat/completions", headers
def _openai_payload(
    provider: str,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    stream: bool
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [_public_message(m) for m in messages],
        "stream": stream
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if provider == "openai" or (provider == "foundry" and model.startswith(OPENAI_MODEL_PREFIXES)):
        effort = "none" if tools and "gpt-5" in model.lower() else reasoning_effort
        if effort in REASONING_EFFORT_VALUES:
            payload["reasoning_effort"] = effort
    if provider == "gemini" and reasoning_effort in GEMINI_EFFORT_BY_REASONING:
        payload["reasoning_effort"] = GEMINI_EFFORT_BY_REASONING[reasoning_effort]
    return payload
async def _openai_chat(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    timeout: float
) -> Dict[str, Any]:
    provider = endpoint.provider
    url, headers = _openai_endpoint(endpoint)
    client = await get_llm_http_client(endpoint.public_only)
    response = await client.post(
        url,
        json=_openai_payload(provider, messages, model, tools, reasoning_effort, stream=False),
        headers=headers,
        timeout=httpx.Timeout(timeout, pool=LLM_POOL_ACQUIRE_TIMEOUT_SECONDS)
    )
    if response.status_code != 200:
        raise RuntimeError(f"{provider} API 錯誤 ({response.status_code}): {response.text[:500]}")
    choices = response.json().get("choices") or []
    if not choices:
        raise RuntimeError(f"{provider} API 回傳空的 choices")
    return choices[0]["message"]
async def _openai_stream(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    reasoning_effort: Optional[str]
) -> AsyncIterator[str]:
    provider = endpoint.provider
    url, headers = _openai_endpoint(endpoint)
    client = await get_llm_http_client(endpoint.public_only)
    payload = _openai_payload(provider, messages, model, None, reasoning_effort, stream=True)
    # 不另給 timeout：沿用連線池的設定，排隊等連線超過 LLM_POOL_ACQUIRE_TIMEOUT_SECONDS 即失敗
    async with client.stream("POST", url, json=payload, headers=headers) as response:
        if response.status_code != 200:
            body = await response.aread()
            raise RuntimeError(f"{provider} 串流錯誤 ({response.status_code}): {body.decode('utf-8', 'replace')[:500]}")
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                content = json.loads(data)["choices"][0].get("delta", {}).get("content")
            except (ValueError, KeyError, IndexError):
                continue
            if content:
                yield content
def uses_responses_api(provider: str, model: str) -> bool:
    if provider == "foundry":
        return model.startswith(FOUNDRY_RESPONSES_MODEL_PREFIXES) and not model.startswith(CHAT_COMPLETIONS_ONLY_PREFIXES)
    return provider == "openai" and model.startswith(OPENAI_RESPONSES_MODEL_PREFIXES)
def _responses_user_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    parts: List[Dict[str, Any]] = []
    for part in content:
        if part.get("type") == "text" and part.get("text"):
            parts.append({"type": "input_text", "text": part["text"]})
        elif part.get("type") == "image_url":
            media_type, data = _parse_image_url(part["image_url"]["url"])
            parts.append({"type": "input_image", "image_url": f"data:{media_type};base64,{data}"})
    return parts
def _responses_input(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "tool":
            items.append({
                "type": "function_call_output",
                "call_id": message["tool_call_id"],
                "output": message.get("content") or ""
            })
        elif role == "assistant":
            raw_output = message.get(OPENAI_OUTPUT_KEY)
            if raw_output is not None:
                items.extend(raw_output)
                continue
            if message.get("content"):
                items.append({"role": "assistant", "content": message["content"]})
            for call in message.get("tool_calls") or []:
                items.append({
                    "type": "function_call",
                    "call_id": call["id"],
                    "name": call["function"]["name"],
                    "arguments": json.dumps(_as_arguments_dict(call["function"]["arguments"]), ensure_ascii=False)
                })
        elif role == "user":
            items.append({"role": "user", "content": _responses_user_content(message.get("content") or "")})
        else:
            items.append({"role": role, "content": _anthropic_system_text(message.get("content") or "")})
    return items
def _responses_effort(model: str, reasoning_effort: Optional[str]) -> Optional[str]:
    if reasoning_effort == "none":
        return "none" if OPENAI_RESPONSES_NONE_EFFORT_MARKER in model else "low"
    if reasoning_effort == "minimal":
        return "low"
    return reasoning_effort if reasoning_effort in REASONING_EFFORT_VALUES else None
def _responses_payload(
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    stream: bool
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"model": model, "input": _responses_input(messages), "stream": stream}
    if tools:
        payload["tools"] = [
            {
                "type": "function",
                "name": tool["function"]["name"],
                "description": tool["function"].get("description", ""),
                "parameters": tool["function"].get("parameters") or {"type": "object", "properties": {}},
                "strict": False
            }
            for tool in tools
        ]
        payload["tool_choice"] = "none" if stream else "auto"
    effort = _responses_effort(model, reasoning_effort)
    if effort:
        payload["reasoning"] = {"effort": effort}
    return payload
def _responses_endpoint(endpoint: LlmEndpoint) -> Tuple[str, Dict[str, str]]:
    url, headers = _openai_endpoint(endpoint)
    return url.rsplit("/chat/completions", 1)[0] + "/responses", headers
def _responses_message(data: Dict[str, Any]) -> Dict[str, Any]:
    status = data.get("status")
    if status == "failed":
        raise RuntimeError(f"openai Responses 失敗: {((data.get('error') or {}).get('message') or '')[:500]}")
    if status == "incomplete":
        raise RuntimeError(f"openai Responses 回應不完整（{(data.get('incomplete_details') or {}).get('reason')}）")
    output = data.get("output") or []
    texts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    for item in output:
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if part.get("type") == "refusal":
                    raise RuntimeError(f"openai 拒絕回應此請求：{(part.get('refusal') or '')[:200]}")
                if part.get("type") == "output_text":
                    texts.append(part.get("text") or "")
        elif item.get("type") == "function_call":
            tool_calls.append({
                "id": item["call_id"],
                "type": "function",
                "function": {"name": item["name"], "arguments": item.get("arguments") or "{}"}
            })
    message: Dict[str, Any] = {"role": "assistant", "content": "".join(texts), OPENAI_OUTPUT_KEY: output}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message
async def _responses_chat(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    timeout: float
) -> Dict[str, Any]:
    provider = endpoint.provider
    url, headers = _responses_endpoint(endpoint)
    client = await get_llm_http_client(endpoint.public_only)
    response = await client.post(
        url,
        json=_responses_payload(messages, model, tools, reasoning_effort, stream=False),
        headers=headers,
        timeout=httpx.Timeout(timeout, pool=LLM_POOL_ACQUIRE_TIMEOUT_SECONDS)
    )
    if response.status_code != 200:
        raise RuntimeError(f"{provider} Responses API 錯誤 ({response.status_code}): {response.text[:500]}")
    return _responses_message(response.json())
async def _responses_stream(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str]
) -> AsyncIterator[str]:
    provider = endpoint.provider
    url, headers = _responses_endpoint(endpoint)
    client = await get_llm_http_client(endpoint.public_only)
    payload = _responses_payload(messages, model, tools, reasoning_effort, stream=True)
    async with client.stream("POST", url, json=payload, headers=headers) as response:
        if response.status_code != 200:
            body = await response.aread()
            raise RuntimeError(f"{provider} Responses 串流錯誤 ({response.status_code}): {body.decode('utf-8', 'replace')[:500]}")
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except ValueError:
                continue
            kind = event.get("type")
            if kind == "response.output_text.delta":
                if event.get("delta"):
                    yield event["delta"]
            elif kind in ("response.failed", "response.incomplete", "error"):
                raise RuntimeError(f"openai Responses 串流中斷: {json.dumps(event, ensure_ascii=False)[:500]}")
def ollama_auth_headers(url: str) -> Dict[str, str]:
    if settings.OLLAMA_API_KEY and urlparse(url).hostname == OLLAMA_CLOUD_HOST:
        return {"Authorization": f"Bearer {settings.OLLAMA_API_KEY}"}
    return {}
def _ollama_request_headers(endpoint: LlmEndpoint) -> Dict[str, str]:
    if endpoint.api_key:
        return {**OLLAMA_HEADERS, "Authorization": f"Bearer {endpoint.api_key}"}
    return dict(OLLAMA_HEADERS)
def _ollama_options() -> Dict[str, Any]:
    options: Dict[str, Any] = {}
    if settings.OLLAMA_TEMPERATURE is not None:
        options["temperature"] = settings.OLLAMA_TEMPERATURE
    if settings.OLLAMA_NUM_PREDICT is not None:
        options["num_predict"] = settings.OLLAMA_NUM_PREDICT
    if settings.OLLAMA_NUM_CTX is not None:
        options["num_ctx"] = settings.OLLAMA_NUM_CTX
    return options
def _ollama_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    converted = []
    for message in messages:
        thinking = message.get(OLLAMA_THINKING_KEY)
        message = _public_message(message)
        role = message.get("role")
        content = message.get("content")
        if role == "user" and isinstance(content, list):
            message = {
                "role": "user",
                "content": "\n".join(part["text"] for part in content if part.get("type") == "text"),
                "images": [_parse_image_url(part["image_url"]["url"])[1] for part in content if part.get("type") == "image_url"]
            }
        elif role == "assistant" and message.get("tool_calls"):
            message = {
                "role": "assistant",
                "content": content or "",
                "tool_calls": [
                    {"function": {"name": call["function"]["name"], "arguments": _as_arguments_dict(call["function"]["arguments"])}}
                    for call in message["tool_calls"]
                ]
            }
            if thinking:
                message["thinking"] = thinking
        elif role == "tool":
            message = {"role": "tool", "content": content, "tool_name": message.get("name")}
        converted.append(message)
    return converted
def _ollama_payload(
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    stream: bool,
    reasoning_effort: Optional[str]
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"model": model, "messages": _ollama_messages(messages), "stream": stream}
    if reasoning_effort == "none":
        payload["think"] = False
    elif reasoning_effort in OLLAMA_THINK_BY_REASONING:
        payload["think"] = OLLAMA_THINK_BY_REASONING[reasoning_effort]
    options = _ollama_options()
    if options:
        payload["options"] = options
    if tools:
        payload["tools"] = tools
    return payload
def _normalize_ollama_message(message: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {"role": "assistant", "content": message.get("content") or ""}
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        if message.get("thinking"):
            normalized[OLLAMA_THINKING_KEY] = message["thinking"]
        normalized["tool_calls"] = [
            {
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": call.get("function", {}).get("name", ""),
                    "arguments": json.dumps(call.get("function", {}).get("arguments") or {}, ensure_ascii=False)
                }
            }
            for call in tool_calls
        ]
    return normalized
async def _ollama_chat(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    timeout: float
) -> Dict[str, Any]:
    client = await get_llm_http_client(endpoint.public_only)
    response = await client.post(
        f"{endpoint.api_base.rstrip('/')}/api/chat",
        json=_ollama_payload(messages, model, tools, stream=False, reasoning_effort=reasoning_effort),
        headers=_ollama_request_headers(endpoint),
        timeout=httpx.Timeout(timeout, pool=LLM_POOL_ACQUIRE_TIMEOUT_SECONDS)
    )
    if response.status_code != 200:
        raise RuntimeError(f"Ollama API 錯誤 ({response.status_code}): {response.text[:500]}")
    return _normalize_ollama_message(response.json().get("message", {}))
async def _ollama_stream(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    reasoning_effort: Optional[str]
) -> AsyncIterator[str]:
    client = await get_llm_http_client(endpoint.public_only)
    payload = _ollama_payload(messages, model, None, stream=True, reasoning_effort=reasoning_effort)
    async with client.stream(
        "POST",
        f"{endpoint.api_base.rstrip('/')}/api/chat",
        json=payload,
        headers=_ollama_request_headers(endpoint),
    ) as response:
        if response.status_code != 200:
            body = await response.aread()
            raise RuntimeError(f"Ollama 串流錯誤 ({response.status_code}): {body.decode('utf-8', 'replace')[:500]}")
        async for line in response.aiter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except ValueError:
                continue
            if chunk.get("error"):
                raise RuntimeError(f"Ollama 串流中斷: {str(chunk['error'])[:500]}")
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content
def is_foundry_claude(model: str) -> bool:
    return is_foundry_enabled() and model in _foundry_deployments() and model.startswith("claude-")
def _uses_anthropic_api(endpoint: LlmEndpoint, model: str) -> bool:
    return endpoint.provider == "anthropic" or (endpoint.provider == "foundry" and model.startswith("claude-"))
def _anthropic_http_client(public_only: bool):
    client = _anthropic_http_clients.get(public_only)
    if client is None or client.is_closed:
        import anthropic
        transport = SSRFSafeHttpx2Transport(DnsPool.USER_URL) if public_only else None
        client = anthropic.DefaultAsyncHttpxClient(transport=transport) if transport else anthropic.DefaultAsyncHttpxClient()
        _anthropic_http_clients[public_only] = client
    return client
def _anthropic_base_url(endpoint: LlmEndpoint) -> str:
    if endpoint.provider != "foundry":
        return endpoint.api_base
    host = urlparse(endpoint.api_base).hostname or ""
    if not host.endswith(FOUNDRY_ANTHROPIC_HOST_SUFFIX):
        raise ValueError(
            f"Foundry 上的 Claude 需要 Foundry 資源端點（*{FOUNDRY_ANTHROPIC_HOST_SUFFIX}），"
            "目前的端點不是；Azure OpenAI 資源只提供 /openai/v1 端點"
        )
    return f"{endpoint.api_base.rstrip('/')}/anthropic"
def _anthropic_client(endpoint: LlmEndpoint):
    import anthropic
    return anthropic.AsyncAnthropic(
        api_key=endpoint.api_key,
        base_url=_anthropic_base_url(endpoint),
        timeout=settings.LLM_TIMEOUT,
        http_client=_anthropic_http_client(endpoint.public_only)
    )
async def _anthropic_model_output_limit(endpoint: LlmEndpoint, model: str) -> Optional[int]:
    """以 Models API 查詢模型的輸出 token 上限並快取；Foundry 不提供 Models API，回傳 None"""
    if endpoint.provider == "foundry":
        return None
    key = (endpoint.api_base, model)
    if key in _anthropic_output_limits:
        return _anthropic_output_limits[key]
    async with _anthropic_output_limits_lock:
        if key not in _anthropic_output_limits:
            info = await _anthropic_client(endpoint).models.retrieve(model)
            _anthropic_output_limits[key] = info.max_tokens
    return _anthropic_output_limits[key]
async def _anthropic_max_tokens(endpoint: LlmEndpoint, model: str) -> int:
    """連線設定的輸出 token 上限與模型輸出上限取較小值，避免輸出上限較低的模型回傳 400"""
    if endpoint.max_output_tokens is None:
        raise ValueError("使用 Claude 模型前需設定輸出 token 上限：API 連線的「輸出 token 上限」，系統模型則為 .env 的 ANTHROPIC_MAX_TOKENS")
    limit = await _anthropic_model_output_limit(endpoint, model)
    if limit is None:
        return endpoint.max_output_tokens
    return min(endpoint.max_output_tokens, limit)
def _anthropic_system_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
def _anthropic_user_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    blocks: List[Dict[str, Any]] = []
    for part in content:
        if part.get("type") == "text" and part.get("text"):
            blocks.append({"type": "text", "text": part["text"]})
        elif part.get("type") == "image_url":
            media_type, data = _parse_image_url(part["image_url"]["url"])
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
    return blocks
def _mark_history_cache_breakpoint(converted: List[Dict[str, Any]]) -> None:
    """在最後一則使用者訊息的最後一個區塊加上快取標記，system、工具與先前的對話歷史都會成為可快取的前綴"""
    if not converted or converted[-1].get("role") != "user":
        return
    last = converted[-1]
    content = last["content"]
    if isinstance(content, str):
        if content:
            last["content"] = [{"type": "text", "text": content, "cache_control": ANTHROPIC_CACHE_CONTROL}]
        return
    if content and isinstance(content[-1], dict):
        last["content"] = [*content[:-1], {**content[-1], "cache_control": ANTHROPIC_CACHE_CONTROL}]
def _log_anthropic_usage(response) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    logger.info(
        "Claude usage: model=%s, input=%s, cache_read=%s, cache_creation=%s, output=%s",
        getattr(response, "model", None),
        getattr(usage, "input_tokens", None),
        getattr(usage, "cache_read_input_tokens", None),
        getattr(usage, "cache_creation_input_tokens", None),
        getattr(usage, "output_tokens", None)
    )
def _anthropic_request(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """將 OpenAI 格式訊息轉為 Messages API 參數：system 抽出、連續的 tool 訊息併成一則 tool_result 使用者訊息"""
    system_parts: List[str] = []
    converted: List[Dict[str, Any]] = []
    tool_results: List[Dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            system_parts.append(_anthropic_system_text(message.get("content") or ""))
            continue
        if role == "tool":
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": message["tool_call_id"],
                "content": message.get("content") or "",
                **({"is_error": True} if message.get("_is_error") else {})
            })
            continue
        if tool_results:
            converted.append({"role": "user", "content": tool_results})
            tool_results = []
        if role == "assistant":
            content = message.get(ANTHROPIC_CONTENT_KEY)
            if content is None:
                content = []
                if message.get("content"):
                    content.append({"type": "text", "text": message["content"]})
                for call in message.get("tool_calls") or []:
                    content.append({
                        "type": "tool_use",
                        "id": call["id"],
                        "name": call["function"]["name"],
                        "input": _as_arguments_dict(call["function"]["arguments"])
                    })
            converted.append({"role": "assistant", "content": content})
        else:
            converted.append({"role": "user", "content": _anthropic_user_content(message.get("content") or "")})
    if tool_results:
        converted.append({"role": "user", "content": tool_results})
    _mark_history_cache_breakpoint(converted)

    request: Dict[str, Any] = {"messages": converted}
    if system_parts:
        request["system"] = [{"type": "text", "text": "\n\n".join(system_parts), "cache_control": ANTHROPIC_CACHE_CONTROL}]
    if tools:
        request["tools"] = [
            {
                "name": tool["function"]["name"],
                "description": tool["function"].get("description", ""),
                "input_schema": tool["function"].get("parameters") or {"type": "object", "properties": {}}
            }
            for tool in tools
        ]
        request["tools"][-1]["cache_control"] = ANTHROPIC_CACHE_CONTROL
    return request
def _anthropic_effort_options(reasoning_effort: Optional[str], model: str, provider: str) -> Dict[str, Any]:
    """依模型組出 thinking、effort 與拒答備援參數；拒答備援只在直連 Claude API 時由伺服器端處理"""
    options: Dict[str, Any] = {}
    extra_body: Dict[str, Any] = {}
    effort = ANTHROPIC_EFFORT_BY_REASONING.get(reasoning_effort or "")
    if effort is not None and model not in ANTHROPIC_MODELS_WITHOUT_EFFORT:
        extra_body["output_config"] = {"effort": effort}
    if model in ANTHROPIC_MODELS_WITH_OPT_IN_THINKING and reasoning_effort != "none":
        options["thinking"] = {"type": "adaptive"}
    if model in ANTHROPIC_FALLBACK_MODELS and provider == "anthropic":
        extra_body["fallbacks"] = "default"
        options["extra_headers"] = {"anthropic-beta": ANTHROPIC_FALLBACK_BETA}
    if extra_body:
        options["extra_body"] = extra_body
    return options
def _raise_if_refused(response) -> None:
    if response.stop_reason == "refusal":
        stop_details = getattr(response, "stop_details", None)
        category = getattr(stop_details, "category", None)
        raise RuntimeError(f"Claude 拒絕回應此請求（refusal，類別：{category}）")
    incomplete = ANTHROPIC_INCOMPLETE_STOP_REASONS.get(response.stop_reason)
    if incomplete:
        raise RuntimeError(incomplete)
def _anthropic_message(response) -> Dict[str, Any]:
    _raise_if_refused(response)
    tool_uses = [block for block in response.content if block.type == "tool_use"]
    if tool_uses and response.stop_reason == "max_tokens":
        raise RuntimeError("Claude 的工具呼叫參數被輸出 token 上限截斷，請調高 API 連線的輸出 token 上限（系統模型為 .env 的 ANTHROPIC_MAX_TOKENS）")
    message: Dict[str, Any] = {
        "role": "assistant",
        "content": "".join(block.text for block in response.content if block.type == "text"),
        ANTHROPIC_CONTENT_KEY: response.content
    }
    if tool_uses:
        message["tool_calls"] = [
            {
                "id": block.id,
                "type": "function",
                "function": {"name": block.name, "arguments": json.dumps(block.input, ensure_ascii=False)}
            }
            for block in tool_uses
        ]
    return message
async def _anthropic_chat(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    timeout: float
) -> Dict[str, Any]:
    client = _anthropic_client(endpoint).with_options(timeout=timeout)
    async with client.messages.stream(
        model=model,
        max_tokens=await _anthropic_max_tokens(endpoint, model),
        **_anthropic_request(messages, tools),
        **_anthropic_effort_options(reasoning_effort, model, endpoint.provider)
    ) as stream:
        response = await stream.get_final_message()
    _log_anthropic_usage(response)
    return _anthropic_message(response)
async def _anthropic_stream(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str]
) -> AsyncIterator[str]:
    request = _anthropic_request(messages, tools)
    if tools:
        request["tool_choice"] = {"type": "none"}
    async with _anthropic_client(endpoint).messages.stream(
        model=model,
        max_tokens=await _anthropic_max_tokens(endpoint, model),
        **request,
        **_anthropic_effort_options(reasoning_effort, model, endpoint.provider)
    ) as stream:
        async for text in stream.text_stream:
            yield text
        final_message = await stream.get_final_message()
    _log_anthropic_usage(final_message)
    _raise_if_refused(final_message)
async def chat_completion(
    messages: List[Dict[str, Any]],
    *,
    endpoint: LlmEndpoint,
    model_name: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None,
    timeout: Optional[float] = None
) -> Dict[str, Any]:
    """單次呼叫 endpoint 指定的供應商，回傳 OpenAI 格式的 assistant 訊息（content、tool_calls）"""
    provider = endpoint.provider
    request_timeout = timeout if timeout is not None else settings.LLM_TIMEOUT
    logger.info(f"Calling LLM: provider={provider}, model={model_name}, messages={len(messages)}, tools={len(tools or [])}")
    if _uses_anthropic_api(endpoint, model_name):
        return await _anthropic_chat(endpoint, messages, model_name, tools, reasoning_effort, request_timeout)
    if uses_responses_api(provider, model_name):
        return await _responses_chat(endpoint, messages, model_name, tools, reasoning_effort, request_timeout)
    if provider == "ollama":
        return await _ollama_chat(endpoint, messages, model_name, tools, reasoning_effort, request_timeout)
    return await _openai_chat(endpoint, messages, model_name, tools, reasoning_effort, request_timeout)
async def stream_completion(
    messages: List[Dict[str, Any]],
    *,
    endpoint: LlmEndpoint,
    model_name: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None
) -> AsyncIterator[str]:
    """串流產生最終答案；tools 只在歷史含工具呼叫時提供給需要宣告工具的供應商，不會再觸發工具"""
    provider = endpoint.provider
    logger.info(f"Streaming LLM: provider={provider}, model={model_name}, messages={len(messages)}")
    if _uses_anthropic_api(endpoint, model_name):
        stream = _anthropic_stream(endpoint, messages, model_name, tools, reasoning_effort)
    elif uses_responses_api(provider, model_name):
        stream = _responses_stream(endpoint, messages, model_name, tools, reasoning_effort)
    elif provider == "ollama":
        stream = _ollama_stream(endpoint, messages, model_name, reasoning_effort)
    else:
        stream = _openai_stream(endpoint, messages, model_name, reasoning_effort)
    async for chunk in stream:
        yield chunk
async def call_llm(
    messages: List[Dict[str, str]],
    *,
    endpoint: LlmEndpoint,
    model_name: str,
    timeout: Optional[float] = None,
    reasoning_effort: Optional[str] = None
) -> str:
    message = await chat_completion(
        messages,
        endpoint=endpoint,
        model_name=model_name,
        reasoning_effort=reasoning_effort,
        timeout=timeout
    )
    return (message.get("content") or "").strip()
