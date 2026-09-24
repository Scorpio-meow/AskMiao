import json
import uuid
import logging
import asyncio
import httpx
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from app.core.config import settings
logger = logging.getLogger(__name__)
_http_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()
_anthropic_client = None
REASONING_EFFORT_VALUES = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
OPENAI_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4")
# Claude 的工具呼叫回合需原樣送回 response.content（含 thinking 區塊），以此鍵附在標準化後的 assistant 訊息上
ANTHROPIC_CONTENT_KEY = "_anthropic_content"
OLLAMA_HEADERS = {
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true"
}
async def get_llm_http_client() -> httpx.AsyncClient:
    global _http_client
    async with _client_lock:
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.LLM_TIMEOUT),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
        return _http_client
async def close_llm_http_client():
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
DEFAULT_OPENAI_MODELS = ["gpt-6-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.4", "gpt-5.4-mini"]
DEFAULT_CLAUDE_MODELS = ["claude-opus-5-5", "claude-fable-5-1", "claude-sonnet-5", "claude-opus-5", "claude-fable-5", "claude-opus-4-8", "claude-haiku-4-5"]
DEFAULT_GEMINI_MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3-pro"]
def is_azure_openai_enabled() -> bool:
    return bool(settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT)
def get_available_models() -> List[str]:
    available = (settings.AVAILABLE_MODELS or "").strip()
    if available:
        return [m.strip() for m in available.split(",") if m.strip()]

    models: List[str] = []

    if is_azure_openai_enabled():
        if settings.AZURE_OPENAI_DEPLOYMENT:
            deployments = [d.strip() for d in settings.AZURE_OPENAI_DEPLOYMENT.split(",") if d.strip()]
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
def _azure_deployments() -> List[str]:
    return [d.strip() for d in (settings.AZURE_OPENAI_DEPLOYMENT or "").split(",") if d.strip()]
def resolve_model_name(model_name: Optional[str]) -> str:
    target = model_name or settings.MODEL_NAME
    if target:
        return target
    available = get_available_models()
    if not available:
        raise ValueError("未指定模型，且未設定 MODEL_NAME、AVAILABLE_MODELS 或任何供應商金鑰")
    return available[0]
def resolve_provider(model_name: str) -> str:
    """依模型名稱決定供應商：azure、anthropic、gemini、openai 或 ollama"""
    if is_azure_openai_enabled() and model_name in _azure_deployments():
        return "azure"
    if model_name.startswith("claude-") and settings.ANTHROPIC_API_KEY:
        return "anthropic"
    if model_name.startswith("gemini-") and settings.GEMINI_API_KEY:
        return "gemini"
    if model_name.startswith(OPENAI_MODEL_PREFIXES):
        if settings.OPENAI_API_KEY:
            return "openai"
        if is_azure_openai_enabled():
            return "azure"
    return "ollama"
def _public_message(message: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in message.items() if not key.startswith("_")}
def _parse_image_url(url: str) -> Tuple[Optional[str], str]:
    """data URL 回傳 (media_type, base64 內容)；其他網址回傳 (None, 原字串)"""
    if url.startswith("data:") and "," in url:
        header, data = url.split(",", 1)
        return header[5:].split(";")[0], data
    return None, url
def _as_arguments_dict(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if not arguments:
        return {}
    return json.loads(arguments)
def _openai_endpoint(provider: str) -> Tuple[str, Dict[str, str]]:
    headers = {"Content-Type": "application/json"}
    if provider == "azure":
        headers["api-key"] = settings.AZURE_OPENAI_API_KEY
        headers["Authorization"] = f"Bearer {settings.AZURE_OPENAI_API_KEY}"
        return f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/v1/chat/completions", headers
    if provider == "gemini":
        headers["Authorization"] = f"Bearer {settings.GEMINI_API_KEY}"
        return f"{settings.GEMINI_API_BASE.rstrip('/')}/v1beta/openai/chat/completions", headers
    headers["Authorization"] = f"Bearer {settings.OPENAI_API_KEY}"
    return f"{settings.OPENAI_API_BASE.rstrip('/')}/chat/completions", headers
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
    if provider in ("openai", "azure"):
        effort = "none" if tools and "gpt-5" in model.lower() else reasoning_effort
        if effort in REASONING_EFFORT_VALUES:
            payload["reasoning_effort"] = effort
    return payload
async def _openai_chat(
    provider: str,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    timeout: float
) -> Dict[str, Any]:
    url, headers = _openai_endpoint(provider)
    client = await get_llm_http_client()
    response = await client.post(
        url,
        json=_openai_payload(provider, messages, model, tools, reasoning_effort, stream=False),
        headers=headers,
        timeout=httpx.Timeout(timeout)
    )
    if response.status_code != 200:
        raise RuntimeError(f"{provider} API 錯誤 ({response.status_code}): {response.text[:500]}")
    choices = response.json().get("choices") or []
    if not choices:
        raise RuntimeError(f"{provider} API 回傳空的 choices")
    return choices[0]["message"]
async def _openai_stream(
    provider: str,
    messages: List[Dict[str, Any]],
    model: str,
    reasoning_effort: Optional[str]
) -> AsyncIterator[str]:
    url, headers = _openai_endpoint(provider)
    client = await get_llm_http_client()
    payload = _openai_payload(provider, messages, model, None, reasoning_effort, stream=True)
    async with client.stream("POST", url, json=payload, headers=headers, timeout=httpx.Timeout(settings.LLM_TIMEOUT)) as response:
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
def _ollama_options() -> Dict[str, Any]:
    options: Dict[str, Any] = {}
    if settings.OLLAMA_TEMPERATURE is not None:
        options["temperature"] = settings.OLLAMA_TEMPERATURE
    if settings.OLLAMA_NUM_PREDICT is not None:
        options["num_predict"] = settings.OLLAMA_NUM_PREDICT
    return options
def _ollama_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    converted = []
    for message in messages:
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
        elif role == "tool":
            message = {"role": "tool", "content": content, "tool_name": message.get("name")}
        converted.append(message)
    return converted
def _ollama_payload(
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    stream: bool
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"model": model, "messages": _ollama_messages(messages), "stream": stream}
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
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    timeout: float
) -> Dict[str, Any]:
    client = await get_llm_http_client()
    response = await client.post(
        f"{settings.LLM_API_BASE.rstrip('/')}/api/chat",
        json=_ollama_payload(messages, model, tools, stream=False),
        headers=OLLAMA_HEADERS,
        timeout=httpx.Timeout(timeout)
    )
    if response.status_code != 200:
        raise RuntimeError(f"Ollama API 錯誤 ({response.status_code}): {response.text[:500]}")
    return _normalize_ollama_message(response.json().get("message", {}))
async def _ollama_stream(messages: List[Dict[str, Any]], model: str) -> AsyncIterator[str]:
    client = await get_llm_http_client()
    payload = _ollama_payload(messages, model, None, stream=True)
    async with client.stream(
        "POST",
        f"{settings.LLM_API_BASE.rstrip('/')}/api/chat",
        json=payload,
        headers=OLLAMA_HEADERS,
        timeout=httpx.Timeout(settings.LLM_TIMEOUT)
    ) as response:
        if response.status_code != 200:
            body = await response.aread()
            raise RuntimeError(f"Ollama 串流錯誤 ({response.status_code}): {body.decode('utf-8', 'replace')[:500]}")
        async for line in response.aiter_lines():
            if not line:
                continue
            try:
                content = json.loads(line).get("message", {}).get("content", "")
            except ValueError:
                continue
            if content:
                yield content
def _anthropic_client_instance():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            base_url=settings.ANTHROPIC_API_BASE,
            timeout=settings.LLM_TIMEOUT
        )
    return _anthropic_client
def _anthropic_max_tokens() -> int:
    if settings.ANTHROPIC_MAX_TOKENS is None:
        raise ValueError("使用 Claude 模型前需在 .env 設定 ANTHROPIC_MAX_TOKENS")
    return settings.ANTHROPIC_MAX_TOKENS
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
            if media_type:
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
            else:
                blocks.append({"type": "image", "source": {"type": "url", "url": data}})
    return blocks
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
                "content": message.get("content") or ""
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

    request: Dict[str, Any] = {"messages": converted}
    if system_parts:
        request["system"] = "\n\n".join(system_parts)
    if tools:
        request["tools"] = [
            {
                "name": tool["function"]["name"],
                "description": tool["function"].get("description", ""),
                "input_schema": tool["function"].get("parameters") or {"type": "object", "properties": {}}
            }
            for tool in tools
        ]
    return request
def _raise_if_refused(response) -> None:
    if response.stop_reason == "refusal":
        stop_details = getattr(response, "stop_details", None)
        category = getattr(stop_details, "category", None)
        raise RuntimeError(f"Claude 拒絕回應此請求（refusal，類別：{category}）")
def _anthropic_message(response) -> Dict[str, Any]:
    _raise_if_refused(response)
    tool_uses = [block for block in response.content if block.type == "tool_use"]
    if tool_uses and response.stop_reason == "max_tokens":
        raise RuntimeError("Claude 的工具呼叫參數被 ANTHROPIC_MAX_TOKENS 截斷，請調高該設定")
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
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    timeout: float
) -> Dict[str, Any]:
    client = _anthropic_client_instance().with_options(timeout=timeout)
    response = await client.messages.create(
        model=model,
        max_tokens=_anthropic_max_tokens(),
        **_anthropic_request(messages, tools)
    )
    return _anthropic_message(response)
async def _anthropic_stream(
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]]
) -> AsyncIterator[str]:
    request = _anthropic_request(messages, tools)
    if tools:
        request["tool_choice"] = {"type": "none"}
    async with _anthropic_client_instance().messages.stream(
        model=model,
        max_tokens=_anthropic_max_tokens(),
        **request
    ) as stream:
        async for text in stream.text_stream:
            yield text
        final_message = await stream.get_final_message()
    _raise_if_refused(final_message)
async def chat_completion(
    messages: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None,
    timeout: Optional[float] = None
) -> Dict[str, Any]:
    """單次呼叫任一供應商，回傳 OpenAI 格式的 assistant 訊息（content、tool_calls）"""
    model = resolve_model_name(model_name)
    provider = resolve_provider(model)
    request_timeout = timeout if timeout is not None else settings.LLM_TIMEOUT
    logger.info(f"Calling LLM: provider={provider}, model={model}, messages={len(messages)}, tools={len(tools or [])}")
    if provider == "anthropic":
        return await _anthropic_chat(messages, model, tools, request_timeout)
    if provider == "ollama":
        return await _ollama_chat(messages, model, tools, request_timeout)
    return await _openai_chat(provider, messages, model, tools, reasoning_effort, request_timeout)
async def stream_completion(
    messages: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None
) -> AsyncIterator[str]:
    """串流產生最終答案；tools 只在歷史含工具呼叫時提供給需要宣告工具的供應商，不會再觸發工具"""
    model = resolve_model_name(model_name)
    provider = resolve_provider(model)
    logger.info(f"Streaming LLM: provider={provider}, model={model}, messages={len(messages)}")
    if provider == "anthropic":
        stream = _anthropic_stream(messages, model, tools)
    elif provider == "ollama":
        stream = _ollama_stream(messages, model)
    else:
        stream = _openai_stream(provider, messages, model, reasoning_effort)
    async for chunk in stream:
        yield chunk
async def call_llm(
    messages: List[Dict[str, str]],
    model_name: Optional[str] = None,
    timeout: Optional[float] = None,
    reasoning_effort: Optional[str] = None
) -> str:
    message = await chat_completion(
        messages,
        model_name=model_name,
        reasoning_effort=reasoning_effort,
        timeout=timeout
    )
    return (message.get("content") or "").strip()
