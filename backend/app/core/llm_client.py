import json
import time
import uuid
import logging
import asyncio
from dataclasses import dataclass
import httpx
from urllib.parse import urlparse
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union
from app.core.config import settings
from app.core.limits import MAX_DISCOVERED_MODELS, VLLM_MODEL_LENGTH_CACHE_SECONDS
from app.core.security_logging import log_fields
from app.core.ssrf_protection import DnsPool, SSRFSafeHttpx2Transport, SSRFSafeTransport
logger = logging.getLogger(__name__)
_http_client: Optional[httpx.AsyncClient] = None
_public_http_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()
_anthropic_http_clients: Dict[bool, Any] = {}
_anthropic_output_limits: Dict[Tuple[str, str], Optional[int]] = {}
_vllm_model_lengths: Dict[Tuple[str, str], Tuple[float, Optional[int]]] = {}
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
ANTHROPIC_CONTENT_KEY = "_anthropic_content"
OLLAMA_HEADERS = {
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true"
}
LLM_POOL_ACQUIRE_TIMEOUT_SECONDS = 15.0
OLLAMA_CLOUD_HOST = "ollama.com"
OLLAMA_THINKING_KEY = "_ollama_thinking"
OLLAMA_THINK_BY_REASONING = {"minimal": "low", "low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}
VLLM_AUTO_TOOL_CHOICE_FLAG = "--enable-auto-tool-choice"
VLLM_TOOLS_DISABLED_MESSAGE = "vLLM 伺服器沒有開啟工具呼叫：啟動 vLLM 時請加上 --enable-auto-tool-choice 與符合模型的 --tool-call-parser"
STREAM_USAGE_PROVIDERS = ("vllm", "openai")
STREAMED_TEXT_FIELDS = ("content", "reasoning", "reasoning_content", "refusal", "arguments")
RESPONSES_FINAL_EVENTS = ("response.completed", "response.failed", "response.incomplete")
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
GPT5_MODEL_MARKER = "gpt-5"
GPT5_NONE_EFFORT_MARKER = "gpt-5."
ORIGINAL_GPT5_EFFORT_BY_REASONING = {"none": "minimal", "xhigh": "high", "max": "high"}
OPENAI_OUTPUT_KEY = "_openai_output"
DEFAULT_OPENAI_MODELS = ["gpt-6.1-sol", "gpt-6-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.4", "gpt-5.4-mini"]
DEFAULT_CLAUDE_MODELS = ["claude-opus-5-5", "claude-fable-5-1", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-sonnet-5", "claude-opus-5", "claude-fable-5", "claude-opus-4-8", "claude-haiku-4-5"]
ANTHROPIC_CACHE_CONTROL = {"type": "ephemeral"}
ANTHROPIC_EFFORT_BY_REASONING = {"none": "low", "minimal": "low", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "max"}
ANTHROPIC_MODELS_WITHOUT_EFFORT = ("claude-haiku-4-5",)
ANTHROPIC_MODELS_WITH_OPT_IN_THINKING = ("claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6")
ANTHROPIC_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"
ANTHROPIC_INCOMPLETE_STOP_REASONS = {
    "pause_turn": "Claude 回合被暫停（pause_turn），回應不完整",
    "model_context_window_exceeded": "對話超出 Claude 的 context window，請縮短內容"
}
DEFAULT_GEMINI_MODELS = ["gemini-4-argon", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
GEMINI_EFFORT_BY_REASONING = {"none": "minimal", "minimal": "minimal", "low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}
OLLAMA_DURATION_FIELDS = (
    ("load_duration", "load_ms"),
    ("prompt_eval_duration", "prompt_eval_ms"),
    ("eval_duration", "eval_ms"),
    ("total_duration", "total_ms"),
)
NANOSECONDS_PER_MILLISECOND = 1_000_000
@dataclass(frozen=True)
class LlmStreamStats:
    fields: Dict[str, Any]
def _int_fields(**fields: Any) -> Dict[str, int]:
    return {key: value for key, value in fields.items() if isinstance(value, int) and not isinstance(value, bool)}
def _chat_completions_stats(data: Dict[str, Any]) -> Dict[str, Any]:
    usage = data.get("usage") or {}
    return _int_fields(
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
    )
def _responses_stats(data: Dict[str, Any]) -> Dict[str, Any]:
    usage = data.get("usage") or {}
    stats: Dict[str, Any] = _int_fields(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cached_tokens=(usage.get("input_tokens_details") or {}).get("cached_tokens"),
        reasoning_tokens=(usage.get("output_tokens_details") or {}).get("reasoning_tokens"),
    )
    if data.get("status"):
        stats["stop_reason"] = data["status"]
    return stats
def _ollama_stats(data: Dict[str, Any]) -> Dict[str, Any]:
    stats: Dict[str, Any] = _int_fields(input_tokens=data.get("prompt_eval_count"), output_tokens=data.get("eval_count"))
    for source, name in OLLAMA_DURATION_FIELDS:
        if isinstance(data.get(source), int):
            stats[name] = data[source] // NANOSECONDS_PER_MILLISECOND
    if data.get("done_reason"):
        stats["stop_reason"] = data["done_reason"]
    return stats
def _anthropic_stats(response, model: str) -> Dict[str, Any]:
    usage = getattr(response, "usage", None)
    stats: Dict[str, Any] = _int_fields(
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", None),
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", None),
    )
    if getattr(response, "stop_reason", None):
        stats["stop_reason"] = response.stop_reason
    served_model = getattr(response, "model", None)
    if served_model and served_model != model:
        stats["served_model"] = served_model
    return stats
def _prompt_size(messages: List[Dict[str, Any]]) -> Tuple[int, int]:
    chars = 0
    images = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            chars += len(content)
            continue
        for part in content or []:
            if part.get("type") == "text":
                chars += len(part.get("text") or "")
            elif part.get("type") == "image_url":
                images += 1
    return chars, images
class _LlmCallLog:
    def __init__(
        self,
        mode: str,
        endpoint: LlmEndpoint,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        reasoning_effort: Optional[str],
        timeout: float
    ):
        self.fields: Dict[str, Any] = {"mode": mode, "provider": endpoint.provider, "model": model}
        self.timeout = timeout
        self.streaming = mode == "stream"
        self.first_chunk_ms: Optional[int] = None
        self.chunks = 0
        self.output_chars = 0
        self.stats: Dict[str, Any] = {}
        prompt_chars, images = _prompt_size(messages)
        logger.info("LLM 呼叫開始 %s", log_fields(
            **self.fields,
            host=urlparse(endpoint.api_base).hostname,
            messages=len(messages),
            prompt_chars=prompt_chars,
            images=images,
            tools=len(tools or []),
            reasoning=reasoning_effort,
            timeout_s=timeout
        ))
        self.started = time.perf_counter()
    def _elapsed_ms(self) -> int:
        return round((time.perf_counter() - self.started) * 1000)
    def chunk(self, text: str) -> None:
        if self.first_chunk_ms is None:
            self.first_chunk_ms = self._elapsed_ms()
        self.chunks += 1
        self.output_chars += len(text)
    def _stream_fields(self) -> Dict[str, Any]:
        if not self.streaming:
            return {}
        return {"first_chunk_ms": self.first_chunk_ms, "chunks": self.chunks, "output_chars": self.output_chars}
    def _log(self, level: int, event: str, status: str, **fields: Any) -> None:
        logger.log(level, "%s %s", event, log_fields(**{
            **self.fields, "status": status, "duration_ms": self._elapsed_ms(), **self._stream_fields(), **fields
        }))
    def finished(self, **fields: Any) -> None:
        self._log(logging.INFO, "LLM 呼叫完成", "ok", **{**fields, **self.stats})
    def failed(self, exc: BaseException) -> None:
        self._log(logging.WARNING, "LLM 呼叫失敗", "error", timeout_s=self.timeout, error=type(exc).__name__, detail=str(exc) or None)
    def cancelled(self) -> None:
        self._log(logging.INFO, "LLM 呼叫中止", "cancelled")
def _public_message(message: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in message.items() if not key.startswith("_")}
def _parse_image_url(url: str) -> Tuple[str, str]:
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
def _chat_completions_effort(model: str, tools: Optional[List[Dict[str, Any]]], reasoning_effort: Optional[str]) -> Optional[str]:
    name = model.lower()
    if GPT5_MODEL_MARKER not in name:
        return reasoning_effort
    accepts_none = GPT5_NONE_EFFORT_MARKER in name
    if tools and accepts_none:
        return "none"
    if not accepts_none:
        return ORIGINAL_GPT5_EFFORT_BY_REASONING.get(reasoning_effort, reasoning_effort)
    return reasoning_effort
def _openai_error(provider: str, kind: str, status_code: int, body: str) -> str:
    if provider == "vllm" and VLLM_AUTO_TOOL_CHOICE_FLAG in body:
        return VLLM_TOOLS_DISABLED_MESSAGE
    return f"{provider} {kind} ({status_code}): {body[:500]}"
def _openai_payload(
    provider: str,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    max_output_tokens: Optional[int]
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [_public_message(m) for m in messages],
        "stream": True
    }
    if provider in STREAM_USAGE_PROVIDERS:
        payload["stream_options"] = {"include_usage": True}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if provider == "openai" or (provider == "foundry" and model.startswith(OPENAI_MODEL_PREFIXES)):
        effort = _chat_completions_effort(model, tools, reasoning_effort)
        if effort in REASONING_EFFORT_VALUES:
            payload["reasoning_effort"] = effort
    if provider == "gemini" and reasoning_effort in GEMINI_EFFORT_BY_REASONING:
        payload["reasoning_effort"] = GEMINI_EFFORT_BY_REASONING[reasoning_effort]
    if provider == "vllm":
        if reasoning_effort in REASONING_EFFORT_VALUES:
            payload["reasoning_effort"] = reasoning_effort
        if max_output_tokens is not None:
            payload["max_completion_tokens"] = max_output_tokens
    return payload
async def _vllm_model_length(endpoint: LlmEndpoint, model: str) -> Optional[int]:
    key = (endpoint.api_base, model)
    cached = _vllm_model_lengths.get(key)
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]
    _, headers = _openai_endpoint(endpoint)
    try:
        entries = await _http_models(endpoint, f"{endpoint.api_base.rstrip('/')}/models", headers)
        length = next((entry.get("max_model_len") for entry in entries if entry.get("id") == model), None)
    except (httpx.HTTPError, RuntimeError, ValueError):
        logger.warning("讀取 vLLM 模型 %s 的上下文長度失敗，沿用連線設定的輸出 token 上限", model, exc_info=True)
        length = None
    length = length if isinstance(length, int) else None
    _vllm_model_lengths[key] = (time.monotonic() + VLLM_MODEL_LENGTH_CACHE_SECONDS, length)
    return length
async def _vllm_output_tokens(endpoint: LlmEndpoint, model: str) -> Optional[int]:
    limit = endpoint.max_output_tokens
    if limit is None:
        return None
    length = await _vllm_model_length(endpoint, model)
    return None if length is not None and limit >= length else limit
def _drop_rejected_limit(payload: Dict[str, Any], status_code: int) -> bool:
    if status_code != 400 or "max_completion_tokens" not in payload:
        return False
    logger.warning("vLLM 拒絕帶有輸出 token 上限 %s 的請求，拿掉上限後重送", payload.pop("max_completion_tokens"))
    return True
async def _openai_events(endpoint: LlmEndpoint, payload: Dict[str, Any], timeout: float) -> AsyncIterator[Dict[str, Any]]:
    provider = endpoint.provider
    url, headers = _openai_endpoint(endpoint)
    client = await get_llm_http_client(endpoint.public_only)
    request_timeout = httpx.Timeout(timeout, pool=LLM_POOL_ACQUIRE_TIMEOUT_SECONDS)
    while True:
        async with client.stream("POST", url, json=payload, headers=headers, timeout=request_timeout) as response:
            if response.status_code != 200:
                body = await response.aread()
                if _drop_rejected_limit(payload, response.status_code):
                    continue
                raise RuntimeError(_openai_error(provider, "API 錯誤", response.status_code, body.decode("utf-8", "replace")))
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("error"):
                    raise RuntimeError(f"{provider} 串流中斷: {json.dumps(event['error'], ensure_ascii=False)[:500]}")
                yield event
            return
def _first_choice(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    choices = event.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return choices[0]
    return None
def _merge_delta(target: Dict[str, Any], delta: Dict[str, Any]) -> None:
    for key, value in delta.items():
        if value is None or value == "":
            continue
        if key == "tool_calls":
            _merge_tool_call_deltas(target.setdefault("tool_calls", []), value)
        elif isinstance(value, dict):
            _merge_delta(target.setdefault(key, {}), value)
        elif key in STREAMED_TEXT_FIELDS and isinstance(value, str):
            target[key] = (target.get(key) or "") + value
        else:
            target[key] = value
def _merge_tool_call_deltas(calls: List[Dict[str, Any]], deltas: List[Dict[str, Any]]) -> None:
    for delta in deltas:
        index = delta.get("index")
        continues = isinstance(index, int) and index < len(calls) and (not delta.get("id") or delta["id"] == calls[index].get("id"))
        if not continues:
            calls.append({})
        _merge_delta(calls[index] if continues else calls[-1], {key: value for key, value in delta.items() if key != "index"})
async def _openai_chat(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    timeout: float
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    provider = endpoint.provider
    max_output_tokens = await _vllm_output_tokens(endpoint, model) if provider == "vllm" else None
    payload = _openai_payload(provider, messages, model, tools, reasoning_effort, max_output_tokens)
    message: Dict[str, Any] = {"role": "assistant", "content": None}
    stats: Dict[str, Any] = {}
    answered = False
    async for event in _openai_events(endpoint, payload, timeout):
        if event.get("usage"):
            stats.update(_chat_completions_stats(event))
        choice = _first_choice(event)
        if choice is None:
            continue
        answered = True
        _merge_delta(message, choice.get("delta") or {})
        if choice.get("finish_reason"):
            stats["stop_reason"] = choice["finish_reason"]
    if not answered:
        raise RuntimeError(f"{provider} API 回傳空的 choices")
    return message, stats
async def _openai_stream(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    reasoning_effort: Optional[str]
) -> AsyncIterator[Union[str, LlmStreamStats]]:
    provider = endpoint.provider
    max_output_tokens = await _vllm_output_tokens(endpoint, model) if provider == "vllm" else None
    payload = _openai_payload(provider, messages, model, None, reasoning_effort, max_output_tokens)
    async for event in _openai_events(endpoint, payload, settings.LLM_TIMEOUT):
        if event.get("usage"):
            yield LlmStreamStats(_chat_completions_stats(event))
        choice = _first_choice(event)
        if choice is None:
            continue
        if choice.get("finish_reason"):
            yield LlmStreamStats({"stop_reason": choice["finish_reason"]})
        content = (choice.get("delta") or {}).get("content")
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
    allow_tool_calls: bool
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"model": model, "input": _responses_input(messages), "stream": True}
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
        payload["tool_choice"] = "auto" if allow_tool_calls else "none"
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
async def _responses_events(endpoint: LlmEndpoint, payload: Dict[str, Any], timeout: float) -> AsyncIterator[Dict[str, Any]]:
    provider = endpoint.provider
    url, headers = _responses_endpoint(endpoint)
    client = await get_llm_http_client(endpoint.public_only)
    request_timeout = httpx.Timeout(timeout, pool=LLM_POOL_ACQUIRE_TIMEOUT_SECONDS)
    async with client.stream("POST", url, json=payload, headers=headers, timeout=request_timeout) as response:
        if response.status_code != 200:
            body = await response.aread()
            raise RuntimeError(f"{provider} Responses API 錯誤 ({response.status_code}): {body.decode('utf-8', 'replace')[:500]}")
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except ValueError:
                continue
            if isinstance(event, dict):
                yield event
def _responses_interrupted(event: Dict[str, Any]) -> RuntimeError:
    return RuntimeError(f"openai Responses 串流中斷: {json.dumps(event, ensure_ascii=False)[:500]}")
async def _responses_chat(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    timeout: float
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    payload = _responses_payload(messages, model, tools, reasoning_effort, allow_tool_calls=True)
    final: Optional[Dict[str, Any]] = None
    async for event in _responses_events(endpoint, payload, timeout):
        kind = event.get("type")
        if kind in RESPONSES_FINAL_EVENTS:
            final = event.get("response") or {}
        elif kind == "error":
            raise _responses_interrupted(event)
    if final is None:
        raise RuntimeError(f"{endpoint.provider} Responses 串流在回應完成前就結束")
    return _responses_message(final), _responses_stats(final)
async def _responses_stream(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str]
) -> AsyncIterator[Union[str, LlmStreamStats]]:
    payload = _responses_payload(messages, model, tools, reasoning_effort, allow_tool_calls=False)
    async for event in _responses_events(endpoint, payload, settings.LLM_TIMEOUT):
        kind = event.get("type")
        if kind == "response.output_text.delta":
            if event.get("delta"):
                yield event["delta"]
        elif kind == "response.completed":
            yield LlmStreamStats(_responses_stats(event.get("response") or {}))
        elif kind in RESPONSES_FINAL_EVENTS or kind == "error":
            raise _responses_interrupted(event)
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
    reasoning_effort: Optional[str]
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"model": model, "messages": _ollama_messages(messages), "stream": True}
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
async def _ollama_chunks(endpoint: LlmEndpoint, payload: Dict[str, Any], timeout: float) -> AsyncIterator[Dict[str, Any]]:
    client = await get_llm_http_client(endpoint.public_only)
    async with client.stream(
        "POST",
        f"{endpoint.api_base.rstrip('/')}/api/chat",
        json=payload,
        headers=_ollama_request_headers(endpoint),
        timeout=httpx.Timeout(timeout, pool=LLM_POOL_ACQUIRE_TIMEOUT_SECONDS),
    ) as response:
        if response.status_code != 200:
            body = await response.aread()
            raise RuntimeError(f"Ollama API 錯誤 ({response.status_code}): {body.decode('utf-8', 'replace')[:500]}")
        async for line in response.aiter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except ValueError:
                continue
            if not isinstance(chunk, dict):
                continue
            if chunk.get("error"):
                raise RuntimeError(f"Ollama 串流中斷: {str(chunk['error'])[:500]}")
            yield chunk
async def _ollama_chat(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str],
    timeout: float
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    content: List[str] = []
    thinking: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {}
    async for chunk in _ollama_chunks(endpoint, _ollama_payload(messages, model, tools, reasoning_effort), timeout):
        message = chunk.get("message") or {}
        content.append(message.get("content") or "")
        thinking.append(message.get("thinking") or "")
        tool_calls.extend(message.get("tool_calls") or [])
        if chunk.get("done"):
            stats = _ollama_stats(chunk)
    return _normalize_ollama_message({"content": "".join(content), "thinking": "".join(thinking), "tool_calls": tool_calls}), stats
async def _ollama_stream(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    reasoning_effort: Optional[str]
) -> AsyncIterator[Union[str, LlmStreamStats]]:
    async for chunk in _ollama_chunks(endpoint, _ollama_payload(messages, model, None, reasoning_effort), settings.LLM_TIMEOUT):
        content = (chunk.get("message") or {}).get("content")
        if content:
            yield content
        if chunk.get("done"):
            yield LlmStreamStats(_ollama_stats(chunk))
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
    if endpoint.provider == "foundry":
        return None
    key = (endpoint.api_base, model)
    if key not in _anthropic_output_limits:
        info = await _anthropic_client(endpoint).models.retrieve(model)
        _anthropic_output_limits[key] = info.max_tokens
    return _anthropic_output_limits[key]
async def _anthropic_max_tokens(endpoint: LlmEndpoint, model: str) -> int:
    limits = [value for value in (endpoint.max_output_tokens, await _anthropic_model_output_limit(endpoint, model)) if value is not None]
    if not limits:
        raise ValueError("查不到這個 Claude 模型的輸出上限：請在 API 連線填寫「輸出 token 上限」，系統模型則設定在所指定的共用連線")
    return min(limits)
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
def _anthropic_request(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]]
) -> Dict[str, Any]:
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
        raise RuntimeError("Claude 的工具呼叫參數被輸出 token 上限截斷：請調高 API 連線的「輸出 token 上限」（系統模型請調整所指定的共用連線）；已是模型的上限時，請要求分段產生或縮短內容")
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
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    client = _anthropic_client(endpoint).with_options(timeout=timeout)
    async with client.messages.stream(
        model=model,
        max_tokens=await _anthropic_max_tokens(endpoint, model),
        **_anthropic_request(messages, tools),
        **_anthropic_effort_options(reasoning_effort, model, endpoint.provider)
    ) as stream:
        response = await stream.get_final_message()
    return _anthropic_message(response), _anthropic_stats(response, model)
async def _anthropic_stream(
    endpoint: LlmEndpoint,
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]],
    reasoning_effort: Optional[str]
) -> AsyncIterator[Union[str, LlmStreamStats]]:
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
    yield LlmStreamStats(_anthropic_stats(final_message, model))
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
    provider = endpoint.provider
    request_timeout = timeout if timeout is not None else settings.LLM_TIMEOUT
    call_log = _LlmCallLog("chat", endpoint, model_name, messages, tools, reasoning_effort, request_timeout)
    try:
        if _uses_anthropic_api(endpoint, model_name):
            message, stats = await _anthropic_chat(endpoint, messages, model_name, tools, reasoning_effort, request_timeout)
        elif uses_responses_api(provider, model_name):
            message, stats = await _responses_chat(endpoint, messages, model_name, tools, reasoning_effort, request_timeout)
        elif provider == "ollama":
            message, stats = await _ollama_chat(endpoint, messages, model_name, tools, reasoning_effort, request_timeout)
        else:
            message, stats = await _openai_chat(endpoint, messages, model_name, tools, reasoning_effort, request_timeout)
    except asyncio.CancelledError:
        call_log.cancelled()
        raise
    except Exception as exc:
        call_log.failed(exc)
        raise
    call_log.stats.update(stats)
    call_log.finished(output_chars=len(message.get("content") or ""), tool_calls=len(message.get("tool_calls") or []))
    return message
async def stream_completion(
    messages: List[Dict[str, Any]],
    *,
    endpoint: LlmEndpoint,
    model_name: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None
) -> AsyncIterator[str]:
    provider = endpoint.provider
    call_log = _LlmCallLog("stream", endpoint, model_name, messages, tools, reasoning_effort, settings.LLM_TIMEOUT)
    if _uses_anthropic_api(endpoint, model_name):
        stream = _anthropic_stream(endpoint, messages, model_name, tools, reasoning_effort)
    elif uses_responses_api(provider, model_name):
        stream = _responses_stream(endpoint, messages, model_name, tools, reasoning_effort)
    elif provider == "ollama":
        stream = _ollama_stream(endpoint, messages, model_name, reasoning_effort)
    else:
        stream = _openai_stream(endpoint, messages, model_name, reasoning_effort)
    try:
        async for chunk in stream:
            if isinstance(chunk, LlmStreamStats):
                call_log.stats.update(chunk.fields)
                continue
            call_log.chunk(chunk)
            yield chunk
    except (asyncio.CancelledError, GeneratorExit):
        call_log.cancelled()
        raise
    except Exception as exc:
        call_log.failed(exc)
        raise
    call_log.finished()
async def _http_models(endpoint: LlmEndpoint, url: str, headers: Dict[str, str]) -> List[Dict[str, Any]]:
    client = await get_llm_http_client(endpoint.public_only)
    response = await client.get(url, headers=headers, timeout=httpx.Timeout(settings.LLM_TAGS_TIMEOUT, pool=LLM_POOL_ACQUIRE_TIMEOUT_SECONDS))
    if response.status_code != 200:
        raise RuntimeError(f"{endpoint.provider} 模型清單錯誤 ({response.status_code}): {response.text[:500]}")
    payload = response.json()
    items = payload.get("models" if endpoint.provider == "ollama" else "data") if isinstance(payload, dict) else None
    return [item for item in items or [] if isinstance(item, dict)]
async def _http_model_ids(endpoint: LlmEndpoint, url: str, headers: Dict[str, str]) -> List[str]:
    key = "name" if endpoint.provider == "ollama" else "id"
    return [item[key] for item in await _http_models(endpoint, url, headers) if item.get(key)]
async def list_models(endpoint: LlmEndpoint) -> List[str]:
    base = endpoint.api_base.rstrip("/")
    if endpoint.provider == "foundry":
        raise ValueError("Foundry 無法從 API 列出部署，請手動填寫部署名稱")
    if endpoint.provider == "anthropic":
        client = _anthropic_client(endpoint).with_options(timeout=settings.LLM_TAGS_TIMEOUT)
        models = [model.id async for model in client.models.list(limit=MAX_DISCOVERED_MODELS)]
    elif endpoint.provider == "ollama":
        models = await _http_model_ids(endpoint, f"{base}/api/tags", _ollama_request_headers(endpoint))
    elif endpoint.provider == "gemini":
        _, headers = _openai_endpoint(endpoint)
        ids = await _http_model_ids(endpoint, f"{base}/v1beta/openai/models", headers)
        models = [model_id.removeprefix("models/") for model_id in ids]
    else:
        _, headers = _openai_endpoint(endpoint)
        models = await _http_model_ids(endpoint, f"{base}/models", headers)
    return sorted(dict.fromkeys(models))[:MAX_DISCOVERED_MODELS]
async def call_llm(
    messages: List[Dict[str, str]],
    *,
    endpoint: LlmEndpoint,
    model_name: str,
    timeout: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None
) -> str:
    message = await chat_completion(
        messages,
        endpoint=endpoint,
        model_name=model_name,
        tools=tools,
        reasoning_effort=reasoning_effort,
        timeout=timeout
    )
    return (message.get("content") or "").strip()