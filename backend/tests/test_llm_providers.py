import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import httpx
import pytest
from app.core import llm_client
from app.core.config import settings
from app.core.llm_client import LlmEndpoint
from app.core.ssrf_protection import SSRFProtectionError, SSRFSafeHttpx2Transport, SSRFSafeTransport
from app import prompts
from app.rag import agent as agent_module
from app.rag.agent import ResearchAgent
from app.rag.retrievers.hybrid import RetrievedChunk
from app.rag.tools import ResearchToolRegistry
from app.rag.types import Document
KB_TOOL = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": "檢索內部知識庫",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
}
CLAUDE = LlmEndpoint("anthropic", "https://api.anthropic.com", "test-key", 16000, False)
LOCAL_OLLAMA = LlmEndpoint("ollama", "http://localhost:11434", None, None, False)
class StaticRetriever:
    def smart_search(self, query, target_document=None):
        doc = Document(page_content="特休依年資計算", metadata={"source": "leave.txt", "chunk_index": 0, "chunk_id": 7})
        return [RetrievedChunk(document=doc, score=0.9, relevance=0.9, pinned=False)]
    def adjacent_texts(self, documents):
        return [("", "") for _ in documents]
class FakeStream:
    def __init__(self, chunks, final_message):
        self.chunks = chunks
        self.final_message = final_message
    async def __aenter__(self):
        async def text_stream():
            for chunk in self.chunks:
                yield chunk
        self.text_stream = text_stream()
        return self
    async def __aexit__(self, *exc_info):
        return False
    async def get_final_message(self):
        return self.final_message
class FakeAnthropicMessages:
    def __init__(self, responses, stream_chunks=()):
        self.responses = list(responses)
        self.stream_chunks = list(stream_chunks)
        self.chat_calls = []
        self.answer_stream_calls = []
    def stream(self, **kwargs):
        if kwargs.get("tool_choice") == {"type": "none"}:
            self.answer_stream_calls.append(kwargs)
            return FakeStream(self.stream_chunks, SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[]))
        self.chat_calls.append(kwargs)
        return FakeStream([], self.responses.pop(0))
class FakeAnthropicModels:
    def __init__(self, output_limits):
        self.output_limits = output_limits
        self.retrieve_calls = []
    async def retrieve(self, model):
        self.retrieve_calls.append(model)
        return SimpleNamespace(id=model, max_tokens=self.output_limits[model])
class FakeAnthropicClient:
    def __init__(self, messages, models):
        self.messages = messages
        self.models = models
    def with_options(self, **kwargs):
        return self
@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setattr(llm_client, "_anthropic_output_limits", {})
    def install(responses, stream_chunks=(), output_limits=None):
        fake_messages = FakeAnthropicMessages(responses, stream_chunks)
        fake_messages.models = FakeAnthropicModels(output_limits or {"claude-opus-5": 128000, "claude-opus-5-5": 128000})
        client = FakeAnthropicClient(fake_messages, fake_messages.models)
        monkeypatch.setattr(llm_client, "_anthropic_client", lambda endpoint: client)
        return fake_messages
    return install
def test_default_claude_model_ids_use_family_version_format():
    assert "claude-opus-5" in llm_client.DEFAULT_CLAUDE_MODELS
    assert all(re.fullmatch(r"claude-(opus|sonnet|haiku|fable)-\d+(-\d+)?", model) for model in llm_client.DEFAULT_CLAUDE_MODELS)
def test_anthropic_request_merges_tool_results_and_converts_images():
    messages = [
        {"role": "system", "content": "系統提示"},
        {"role": "user", "content": [
            {"type": "text", "text": "看這張圖"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
        ]},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_a", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"}},
            {"id": "call_b", "type": "function", "function": {"name": "web_search", "arguments": "{\"query\": \"勞基法\"}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_a", "name": "search_knowledge_base", "content": "{\"documents\": []}"},
        {"role": "tool", "tool_call_id": "call_b", "name": "web_search", "content": "{\"results\": []}"},
    ]
    request = llm_client._anthropic_request(messages, [KB_TOOL])
    assert request["system"] == [{"type": "text", "text": "系統提示", "cache_control": {"type": "ephemeral"}}]
    assert request["messages"] == [
        {"role": "user", "content": [
            {"type": "text", "text": "看這張圖"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"}},
        ]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "call_a", "name": "search_knowledge_base", "input": {"query": "特休"}},
            {"type": "tool_use", "id": "call_b", "name": "web_search", "input": {"query": "勞基法"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "call_a", "content": "{\"documents\": []}"},
            {"type": "tool_result", "tool_use_id": "call_b", "content": "{\"results\": []}", "cache_control": {"type": "ephemeral"}},
        ]},
    ]
    assert request["tools"] == [{
        "name": "search_knowledge_base",
        "description": "檢索內部知識庫",
        "input_schema": KB_TOOL["function"]["parameters"],
        "cache_control": {"type": "ephemeral"},
    }]
def test_anthropic_request_marks_failed_tool_results():
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_a", "type": "function", "function": {"name": "web_search", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_a", "name": "web_search", "content": "{\"error\": \"x\"}", "_is_error": True},
    ]
    request = llm_client._anthropic_request(messages, None)
    assert request["messages"][1]["content"] == [
        {"type": "tool_result", "tool_use_id": "call_a", "content": "{\"error\": \"x\"}", "is_error": True, "cache_control": {"type": "ephemeral"}},
    ]
def test_anthropic_request_marks_last_user_message_as_cache_breakpoint():
    messages = [
        {"role": "user", "content": "第一問"},
        {"role": "assistant", "content": "第一答"},
        {"role": "user", "content": "第二問"},
    ]
    request = llm_client._anthropic_request(messages, None)
    assert request["messages"][0] == {"role": "user", "content": "第一問"}
    assert request["messages"][1] == {"role": "assistant", "content": [{"type": "text", "text": "第一答"}]}
    assert request["messages"][2] == {
        "role": "user",
        "content": [{"type": "text", "text": "第二問", "cache_control": {"type": "ephemeral"}}],
    }
def test_anthropic_request_skips_cache_breakpoint_for_empty_or_assistant_tail():
    assert llm_client._anthropic_request([{"role": "user", "content": ""}], None)["messages"] == [{"role": "user", "content": ""}]
    tail_assistant = llm_client._anthropic_request([{"role": "user", "content": "問"}, {"role": "assistant", "content": "答"}], None)
    assert "cache_control" not in str(tail_assistant["messages"])
def test_anthropic_effort_options_map_reasoning_effort():
    assert llm_client._anthropic_effort_options("high", "claude-sonnet-5", "anthropic") == {"extra_body": {"output_config": {"effort": "high"}}}
    assert llm_client._anthropic_effort_options("minimal", "claude-sonnet-5", "anthropic") == {"extra_body": {"output_config": {"effort": "low"}}}
    assert llm_client._anthropic_effort_options("none", "claude-sonnet-5", "anthropic") == {"extra_body": {"output_config": {"effort": "low"}}}
    assert llm_client._anthropic_effort_options(None, "claude-sonnet-5", "anthropic") == {}
def test_anthropic_effort_options_skip_effort_on_haiku_4_5():
    assert llm_client._anthropic_effort_options("high", "claude-haiku-4-5", "anthropic") == {}
def test_anthropic_effort_options_enable_adaptive_thinking_on_opt_in_models():
    assert llm_client._anthropic_effort_options("high", "claude-opus-4-8", "anthropic") == {
        "thinking": {"type": "adaptive"},
        "extra_body": {"output_config": {"effort": "high"}},
    }
    assert "thinking" not in llm_client._anthropic_effort_options("none", "claude-opus-4-8", "anthropic")
    assert "thinking" not in llm_client._anthropic_effort_options("high", "claude-opus-5-5", "anthropic")
def test_anthropic_effort_options_request_server_side_fallback():
    options = llm_client._anthropic_effort_options("low", "claude-opus-5-5", "anthropic")
    assert options["extra_body"] == {"output_config": {"effort": "low"}, "fallbacks": "default"}
    assert options["extra_headers"] == {"anthropic-beta": "server-side-fallback-2026-07-01"}
    assert "fallbacks" not in llm_client._anthropic_effort_options("low", "claude-haiku-5-5", "anthropic").get("extra_body", {})
def test_anthropic_effort_options_skip_fallback_on_foundry():
    options = llm_client._anthropic_effort_options("low", "claude-opus-5-5", "foundry")
    assert "extra_headers" not in options
    assert "fallbacks" not in options["extra_body"]
CLAUDE_TOOL_USE_CONTENT = [
    SimpleNamespace(type="thinking", thinking="", signature="sig-1"),
    SimpleNamespace(type="tool_use", id="toolu_1", name="search_knowledge_base", input={"query": "特休"}),
]
FIXED_NOW = datetime(2026, 11, 8, 23, 7, tzinfo=timezone(timedelta(hours=8)))
def claude_agent(monkeypatch):
    registry = ResearchToolRegistry(retriever=StaticRetriever())
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None, conversation_id=None, requested_skill=None: [KB_TOOL])
    monkeypatch.setattr(agent_module, "local_now", lambda: FIXED_NOW)
    return ResearchAgent(tool_registry=registry)
async def final_result(events):
    return [event async for event in events if event["event"] == "done"][-1]["data"]
@pytest.mark.asyncio
async def test_agent_tool_round_trip_with_claude_preserves_raw_content(claude, monkeypatch):
    fake_messages = claude(responses=[
        SimpleNamespace(stop_reason="tool_use", stop_details=None, content=CLAUDE_TOOL_USE_CONTENT),
        SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[SimpleNamespace(type="text", text="特休依年資計算 [1]")]),
    ])
    result = await final_result(claude_agent(monkeypatch).stream_research("特休怎麼算？", endpoint=CLAUDE, model_name="claude-opus-5", allow_web=True))
    first_call, second_call = fake_messages.chat_calls
    assert first_call["model"] == "claude-opus-5"
    assert first_call["system"] == [{"type": "text", "text": prompts.SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    assert first_call["messages"] == [{"role": "user", "content": [{"type": "text", "text": agent_module.with_current_time("特休怎麼算？", FIXED_NOW), "cache_control": {"type": "ephemeral"}}]}]
    assert second_call["messages"][1] == {"role": "assistant", "content": CLAUDE_TOOL_USE_CONTENT}
    assert [block["tool_use_id"] for block in second_call["messages"][2]["content"]] == ["toolu_1"]
    assert fake_messages.answer_stream_calls == []
    assert all("temperature" not in call for call in fake_messages.chat_calls)
    assert result["answer"] == "特休依年資計算 [1]"
    assert result["sources"] == ["leave.txt"]
@pytest.mark.asyncio
async def test_claude_streams_final_answer_when_answer_is_empty(claude, monkeypatch):
    fake_messages = claude(
        responses=[
            SimpleNamespace(stop_reason="tool_use", stop_details=None, content=CLAUDE_TOOL_USE_CONTENT),
            SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[]),
        ],
        stream_chunks=["特休", "依年資計算"],
    )
    result = await final_result(claude_agent(monkeypatch).stream_research("特休怎麼算？", endpoint=CLAUDE, model_name="claude-opus-5", allow_web=True))
    first_call, _ = fake_messages.chat_calls
    (stream_call,) = fake_messages.answer_stream_calls
    assert stream_call["tool_choice"] == {"type": "none"}
    assert stream_call["tools"] == first_call["tools"]
    assert all("temperature" not in call for call in fake_messages.chat_calls + fake_messages.answer_stream_calls)
    assert result["answer"] == "特休依年資計算"
@pytest.mark.asyncio
async def test_call_llm_returns_text_blocks_after_thinking(claude):
    claude(responses=[SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[
        SimpleNamespace(type="thinking", thinking="", signature="sig"),
        SimpleNamespace(type="text", text="文件摘要"),
    ])])
    answer = await llm_client.call_llm([{"role": "user", "content": "摘要"}], endpoint=CLAUDE, model_name="claude-opus-5")
    assert answer == "文件摘要"
@pytest.mark.asyncio
async def test_claude_refusal_raises(claude):
    claude(responses=[SimpleNamespace(
        stop_reason="refusal",
        stop_details=SimpleNamespace(category="cyber"),
        content=[],
    )])
    with pytest.raises(RuntimeError, match="refusal"):
        await llm_client.chat_completion([{"role": "user", "content": "…"}], endpoint=CLAUDE, model_name="claude-opus-5")
@pytest.mark.asyncio
async def test_claude_max_tokens_capped_by_model_output_limit(claude):
    endpoint = LlmEndpoint("anthropic", "https://api.anthropic.com", "test-key", 128000, False)
    end_turn = SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[SimpleNamespace(type="text", text="OK")])
    fake_messages = claude(responses=[end_turn, end_turn, end_turn], output_limits={"claude-haiku-4-5": 64000, "claude-opus-5-5": 128000})
    await llm_client.chat_completion([{"role": "user", "content": "你好"}], endpoint=endpoint, model_name="claude-haiku-4-5")
    await llm_client.chat_completion([{"role": "user", "content": "你好"}], endpoint=endpoint, model_name="claude-haiku-4-5")
    await llm_client.chat_completion([{"role": "user", "content": "你好"}], endpoint=endpoint, model_name="claude-opus-5-5")
    assert [call["max_tokens"] for call in fake_messages.chat_calls] == [64000, 64000, 128000]
    assert fake_messages.models.retrieve_calls == ["claude-haiku-4-5", "claude-opus-5-5"]
@pytest.mark.asyncio
async def test_slow_model_lookup_does_not_block_other_endpoints(monkeypatch):
    monkeypatch.setattr(llm_client, "_anthropic_output_limits", {})
    slow = LlmEndpoint("anthropic", "https://slow.example.com", "test-key", 128000, False)
    fast = LlmEndpoint("anthropic", "https://api.anthropic.com", "test-key", 128000, False)
    release_slow = asyncio.Event()
    class Models:
        def __init__(self, endpoint):
            self.endpoint = endpoint
        async def retrieve(self, model):
            if self.endpoint is slow:
                await release_slow.wait()
            return SimpleNamespace(id=model, max_tokens=64000)
    monkeypatch.setattr(llm_client, "_anthropic_client", lambda endpoint: SimpleNamespace(models=Models(endpoint)))
    slow_lookup = asyncio.create_task(llm_client._anthropic_max_tokens(slow, "claude-haiku-4-5"))
    await asyncio.sleep(0)
    assert await asyncio.wait_for(llm_client._anthropic_max_tokens(fast, "claude-haiku-4-5"), timeout=1) == 64000
    release_slow.set()
    assert await slow_lookup == 64000
@pytest.mark.asyncio
async def test_claude_max_tokens_on_foundry_uses_connection_limit():
    endpoint = LlmEndpoint("foundry", "https://example.services.ai.azure.com", "foundry-key", 32000, False)
    assert await llm_client._anthropic_max_tokens(endpoint, "claude-opus-5-5") == 32000
@pytest.mark.asyncio
async def test_claude_without_output_limit_uses_the_model_limit(claude):
    end_turn = SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[SimpleNamespace(type="text", text="OK")])
    fake_messages = claude(responses=[end_turn], output_limits={"claude-haiku-4-5": 64000})
    endpoint = LlmEndpoint("anthropic", "https://api.anthropic.com", "test-key", None, False)
    await llm_client.chat_completion([{"role": "user", "content": "你好"}], endpoint=endpoint, model_name="claude-haiku-4-5")
    assert fake_messages.chat_calls[0]["max_tokens"] == 64000
@pytest.mark.asyncio
async def test_claude_on_foundry_requires_max_output_tokens():
    endpoint = LlmEndpoint("foundry", "https://example.services.ai.azure.com", "foundry-key", None, False)
    with pytest.raises(ValueError, match="輸出 token 上限"):
        await llm_client._anthropic_max_tokens(endpoint, "claude-opus-5-5")
def test_ollama_conversion_and_response_normalization():
    converted = llm_client._ollama_messages([
        {"role": "user", "content": [
            {"type": "text", "text": "看圖"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
        ]},
        {"role": "assistant", "content": "", "_anthropic_content": ["ignored"], "tool_calls": [
            {"id": "call_a", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_a", "name": "search_knowledge_base", "content": "{}"},
    ])
    assert converted == [
        {"role": "user", "content": "看圖", "images": ["QUJD"]},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "search_knowledge_base", "arguments": {"query": "特休"}}},
        ]},
        {"role": "tool", "content": "{}", "tool_name": "search_knowledge_base"},
    ]
    normalized = llm_client._normalize_ollama_message({"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "search_knowledge_base", "arguments": {"query": "特休"}}},
        {"function": {"name": "web_search", "arguments": {"query": "勞基法"}}},
    ]})
    assert len({call["id"] for call in normalized["tool_calls"]}) == 2
    assert json.loads(normalized["tool_calls"][0]["function"]["arguments"]) == {"query": "特休"}
@pytest.mark.parametrize("effort, expected", [("none", False), ("low", "low"), ("high", "high")])
def test_ollama_payload_maps_reasoning_effort_to_think(effort, expected):
    payload = llm_client._ollama_payload([{"role": "user", "content": "hi"}], "qwen3:8b", None, reasoning_effort=effort)
    assert payload["think"] is expected if isinstance(expected, bool) else payload["think"] == expected
def test_ollama_payload_omits_think_without_reasoning_effort():
    payload = llm_client._ollama_payload([{"role": "user", "content": "hi"}], "qwen3:8b", None, reasoning_effort=None)
    assert "think" not in payload
def test_openai_compatible_payload_strips_private_fields():
    messages = [{"role": "assistant", "content": "hi", "_anthropic_content": ["raw"]}]
    payload = llm_client._openai_payload("gemini", messages, "gemini-3.8-flash", None, None, max_output_tokens=None)
    assert payload["messages"] == [{"role": "assistant", "content": "hi"}]
    assert "reasoning_effort" not in payload
    assert "tools" not in payload
@pytest.mark.parametrize("effort, expected", [
    ("none", "minimal"),
    ("minimal", "minimal"),
    ("low", "low"),
    ("medium", "medium"),
    ("high", "high"),
    ("xhigh", "high"),
    ("max", "high"),
])
def test_gemini_payload_maps_reasoning_effort_to_supported_levels(effort, expected):
    payload = llm_client._openai_payload("gemini", [{"role": "user", "content": "hi"}], "gemini-3.8-flash", None, effort, max_output_tokens=None)
    assert payload["reasoning_effort"] == expected
@pytest.mark.asyncio
async def test_llm_requests_keep_the_pool_acquire_timeout(monkeypatch):
    pool_timeouts = []
    def handler(request):
        pool_timeouts.append(request.extensions["timeout"]["pool"])
        if json.loads(request.content)["stream"]:
            return httpx.Response(200, text='{"message": {"content": "好"}}\n')
        return httpx.Response(200, json={"message": {"content": "好"}})
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(settings.LLM_TIMEOUT, pool=llm_client.LLM_POOL_ACQUIRE_TIMEOUT_SECONDS),
    )
    monkeypatch.setattr(llm_client, "_http_client", client)
    messages = [{"role": "user", "content": "你好"}]
    await llm_client.chat_completion(messages, endpoint=LOCAL_OLLAMA, model_name="local-model", timeout=18.0)
    assert [chunk async for chunk in llm_client.stream_completion(messages, endpoint=LOCAL_OLLAMA, model_name="local-model")] == ["好"]
    assert pool_timeouts == [llm_client.LLM_POOL_ACQUIRE_TIMEOUT_SECONDS] * 2
    await client.aclose()
def test_gpt6_models_use_responses_api_only_on_openai():
    assert llm_client.uses_responses_api("openai", "gpt-6.1-sol")
    assert llm_client.uses_responses_api("openai", "gpt-6-luna")
    assert not llm_client.uses_responses_api("openai", "gpt-5.6-sol")
    assert llm_client.uses_responses_api("foundry", "gpt-5.6-sol")
    assert llm_client.uses_responses_api("foundry", "o3")
    assert not llm_client.uses_responses_api("foundry", "gpt-oss-120b")
    assert not llm_client.uses_responses_api("foundry", "o3-mini")
    assert not llm_client.uses_responses_api("foundry", "o1")
    assert not llm_client.uses_responses_api("foundry", "Kimi-K2.6")
    assert not llm_client.uses_responses_api("foundry", "grok-4.7")
    assert not llm_client.uses_responses_api("foundry", "my-deployment")
    assert not llm_client.uses_responses_api("gemini", "gemini-3.8-flash")
def test_responses_payload_converts_messages_tools_and_effort():
    messages = [
        {"role": "system", "content": "系統提示"},
        {"role": "user", "content": [
            {"type": "text", "text": "看這張圖"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
        ]},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_a", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_a", "name": "search_knowledge_base", "content": "{\"documents\": []}", "_is_error": False},
    ]
    payload = llm_client._responses_payload(messages, "gpt-6.1-sol", [KB_TOOL], "none", allow_tool_calls=True)
    assert payload["input"] == [
        {"role": "system", "content": "系統提示"},
        {"role": "user", "content": [
            {"type": "input_text", "text": "看這張圖"},
            {"type": "input_image", "image_url": "data:image/png;base64,QUJD"},
        ]},
        {"type": "function_call", "call_id": "call_a", "name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"},
        {"type": "function_call_output", "call_id": "call_a", "output": "{\"documents\": []}"},
    ]
    assert payload["tools"] == [{
        "type": "function",
        "name": "search_knowledge_base",
        "description": "檢索內部知識庫",
        "parameters": KB_TOOL["function"]["parameters"],
        "strict": False,
    }]
    assert payload["reasoning"] == {"effort": "low"}
def test_responses_effort_allows_none_only_on_luna():
    assert llm_client._responses_effort("gpt-6-luna", "none") == "none"
    assert llm_client._responses_effort("gpt-6-astra", "none") == "low"
    assert llm_client._responses_effort("gpt-6-astra", "max") == "max"
    assert llm_client._responses_effort("gpt-6-astra", None) is None
def test_responses_message_keeps_raw_output_for_next_round():
    output = [
        {"type": "reasoning", "id": "rs_1", "summary": []},
        {"type": "function_call", "id": "fc_1", "call_id": "call_a", "name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"},
    ]
    message = llm_client._responses_message({"status": "completed", "output": output})
    assert message["tool_calls"] == [
        {"id": "call_a", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"}},
    ]
    assert llm_client._responses_input([message]) == output
def test_responses_message_collects_text_and_rejects_incomplete_or_refusal():
    text = llm_client._responses_message({
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "特休依年資計算"}]}],
    })
    assert text["content"] == "特休依年資計算"
    assert "tool_calls" not in text
    with pytest.raises(RuntimeError, match="不完整"):
        llm_client._responses_message({"status": "incomplete", "incomplete_details": {"reason": "content_filter"}})
    with pytest.raises(RuntimeError, match="拒絕"):
        llm_client._responses_message({
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "不行"}]}],
        })
def test_responses_endpoint_per_provider():
    openai = LlmEndpoint("openai", "https://api.openai.com/v1", "openai-key", None, False)
    foundry = LlmEndpoint("foundry", "https://res.openai.azure.com/", "foundry-key", None, False)
    openai_url, openai_headers = llm_client._responses_endpoint(openai)
    foundry_url, foundry_headers = llm_client._responses_endpoint(foundry)
    assert openai_url == "https://api.openai.com/v1/responses"
    assert openai_headers["Authorization"] == "Bearer openai-key"
    assert foundry_url == "https://res.openai.azure.com/openai/v1/responses"
    assert foundry_headers["api-key"] == "foundry-key"
def test_responses_streaming_payload_declares_tools_but_forbids_calling_them():
    messages = [{"role": "system", "content": [{"type": "text", "text": "系統"}, {"type": "text", "text": "提示"}]}]
    payload = llm_client._responses_payload(messages, "gpt-6-astra", [KB_TOOL], "high", allow_tool_calls=False)
    assert payload["tool_choice"] == "none"
    assert payload["tools"][0]["name"] == "search_knowledge_base"
    assert payload["input"] == [{"role": "system", "content": "系統\n提示"}]
def test_foundry_claude_deployment_uses_the_anthropic_api_and_other_deployments_do_not():
    endpoint = LlmEndpoint("foundry", "https://res.services.ai.azure.com", "foundry-key", 32000, False)
    assert llm_client._uses_anthropic_api(endpoint, "claude-sonnet-4-6")
    assert not llm_client._uses_anthropic_api(endpoint, "my-gpt")
def test_foundry_claude_client_uses_anthropic_endpoint_and_api_key():
    endpoint = LlmEndpoint("foundry", "https://res.services.ai.azure.com/", "foundry-key", 32000, False)
    client = llm_client._anthropic_client(endpoint)
    assert str(client.base_url).rstrip("/") == "https://res.services.ai.azure.com/anthropic"
    assert client.api_key == "foundry-key"
def test_foundry_claude_rejects_azure_openai_resource_endpoint():
    endpoint = LlmEndpoint("foundry", "https://res.openai.azure.com", "foundry-key", 32000, False)
    with pytest.raises(ValueError, match="services.ai.azure.com"):
        llm_client._anthropic_client(endpoint)
def test_foundry_chat_completions_skips_reasoning_effort_for_non_openai_models():
    messages = [{"role": "user", "content": "hi"}]
    kimi = llm_client._openai_payload("foundry", messages, "Kimi-K2.6", None, "high", max_output_tokens=None)
    gpt = llm_client._openai_payload("foundry", messages, "gpt-oss-120b", None, "high", max_output_tokens=None)
    assert "reasoning_effort" not in kimi
    assert gpt["reasoning_effort"] == "high"
@pytest.mark.parametrize("model, tools, effort, expected", [
    ("gpt-5.4", [KB_TOOL], "high", "none"),
    ("gpt-5.4-mini", None, "none", "none"),
    ("gpt-5.4", None, "medium", "medium"),
    ("gpt-5", [KB_TOOL], "high", "high"),
    ("gpt-5-mini", [KB_TOOL], "none", "minimal"),
    ("gpt-5-nano", None, "none", "minimal"),
    ("gpt-5-nano", None, "low", "low"),
    ("gpt-5", [KB_TOOL], "xhigh", "high"),
    ("gpt-5-mini", None, "max", "high"),
])
def test_chat_completions_sends_none_effort_only_to_gpt5_point_releases(model, tools, effort, expected):
    payload = llm_client._openai_payload("openai", [{"role": "user", "content": "hi"}], model, tools, effort, max_output_tokens=None)
    assert payload["reasoning_effort"] == expected
@pytest.mark.parametrize("effort, expected", [
    ("none", False),
    ("minimal", "low"),
    ("low", "low"),
    ("medium", "medium"),
    ("high", "high"),
    ("xhigh", "high"),
    ("max", "high"),
])
def test_ollama_payload_maps_reasoning_effort_to_think_values(effort, expected):
    payload = llm_client._ollama_payload([{"role": "user", "content": "hi"}], "gpt-oss:20b", None, reasoning_effort=effort)
    assert payload["think"] == expected
def test_ollama_options_include_num_ctx_only_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_TEMPERATURE", None)
    monkeypatch.setattr(settings, "OLLAMA_NUM_PREDICT", None)
    monkeypatch.setattr(settings, "OLLAMA_NUM_CTX", None)
    assert llm_client._ollama_options() == {}
    monkeypatch.setattr(settings, "OLLAMA_NUM_CTX", 16384)
    assert llm_client._ollama_options() == {"num_ctx": 16384}
def test_connection_api_key_is_sent_to_its_own_ollama_endpoint():
    endpoint = LlmEndpoint("ollama", "https://my-ollama.example.com", "user-key", None, True)
    assert llm_client._ollama_request_headers(endpoint)["Authorization"] == "Bearer user-key"
    assert "Authorization" not in llm_client._ollama_request_headers(LOCAL_OLLAMA)
@pytest.mark.asyncio
async def test_public_only_endpoints_cannot_reach_private_addresses(monkeypatch):
    monkeypatch.setattr(llm_client, "_public_http_client", None)
    endpoint = LlmEndpoint("ollama", "http://127.0.0.1:11434", None, None, True)
    try:
        assert isinstance((await llm_client.get_llm_http_client(True))._transport, SSRFSafeTransport)
        with pytest.raises(SSRFProtectionError):
            await llm_client.chat_completion([{"role": "user", "content": "hi"}], endpoint=endpoint, model_name="qwen3:8b")
    finally:
        await llm_client._public_http_client.aclose()
def test_public_only_claude_endpoints_use_the_ssrf_safe_httpx2_transport(monkeypatch):
    monkeypatch.setattr(llm_client, "_anthropic_http_clients", {})
    public = LlmEndpoint("anthropic", "https://claude-proxy.example.com", "k", 1000, True)
    assert isinstance(llm_client._anthropic_client(public)._client._transport, SSRFSafeHttpx2Transport)
    assert not isinstance(llm_client._anthropic_client(CLAUDE)._client._transport, SSRFSafeHttpx2Transport)
@pytest.mark.asyncio
async def test_ollama_stream_raises_on_error_line(monkeypatch):
    def handler(request):
        return httpx.Response(200, content=b'{"message":{"content":"ab"}}\n{"error":"model crashed"}\n')
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    received = []
    with pytest.raises(RuntimeError, match="model crashed"):
        async for chunk in llm_client._ollama_stream(LOCAL_OLLAMA, [{"role": "user", "content": "hi"}], "qwen3:8b", None):
            received.append(chunk)
    assert received == ["ab"]
def test_ollama_tool_round_trip_returns_thinking_with_the_tool_calls():
    reply = {"role": "assistant", "content": "", "thinking": "先查知識庫", "tool_calls": [
        {"function": {"name": "search_knowledge_base", "arguments": {"query": "特休"}}},
    ]}
    assistant = llm_client._normalize_ollama_message(reply)
    converted = llm_client._ollama_messages([assistant])
    assert converted[0]["thinking"] == "先查知識庫"
    assert converted[0]["tool_calls"] == [{"function": {"name": "search_knowledge_base", "arguments": {"query": "特休"}}}]
    assert "_ollama_thinking" not in converted[0]
def test_openai_compatible_payload_keeps_provider_extra_fields_on_tool_calls():
    assistant = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{}"},
         "extra_content": {"google": {"thought_signature": "sig-abc"}}},
    ]}
    payload = llm_client._openai_payload("gemini", [assistant], "gemini-3.8-flash", [KB_TOOL], "high", max_output_tokens=None)
    assert payload["messages"][0]["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "sig-abc"}}
@pytest.mark.asyncio
async def test_list_models_reads_each_providers_model_endpoint(monkeypatch):
    seen = []
    def handler(request):
        seen.append((request.url.path, request.headers.get("Authorization")))
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}, {"name": "gemma4:e2b"}]})
        if request.url.path == "/v1beta/openai/models":
            return httpx.Response(200, json={"data": [{"id": "models/gemini-3.8-flash"}]})
        return httpx.Response(200, json={"data": [{"id": "gpt-6-sol"}, {"id": "gpt-6-luna"}, {"id": "gpt-6-sol"}]})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm_client, "_http_client", client)
    assert await llm_client.list_models(LlmEndpoint("openai", "https://api.example.com/v1/", "k1", None, False)) == ["gpt-6-luna", "gpt-6-sol"]
    assert await llm_client.list_models(LlmEndpoint("gemini", "https://g.example.com", "k2", None, False)) == ["gemini-3.8-flash"]
    assert await llm_client.list_models(LOCAL_OLLAMA) == ["gemma4:e2b", "qwen3:8b"]
    assert seen == [("/v1/models", "Bearer k1"), ("/v1beta/openai/models", "Bearer k2"), ("/api/tags", None)]
    with pytest.raises(ValueError, match="手動填寫"):
        await llm_client.list_models(LlmEndpoint("foundry", "https://x.services.ai.azure.com", "k", None, False))
    await client.aclose()
LOCAL_VLLM = LlmEndpoint("vllm", "http://localhost:8000/v1", None, None, False)
def sse(events):
    return "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events) + "data: [DONE]\n\n"
def completion_stream(message, finish_reason="stop", usage=None):
    calls = [{"index": index, **call} for index, call in enumerate(message.get("tool_calls") or [])]
    delta = {**message, "tool_calls": calls} if calls else message
    events = [{"choices": [{"delta": delta, "finish_reason": finish_reason}]}] + ([{"choices": [], "usage": usage}] if usage else [])
    return httpx.Response(200, text=sse(events))
@pytest.mark.parametrize("effort", llm_client.REASONING_EFFORT_VALUES)
def test_vllm_payload_passes_every_reasoning_effort_and_the_output_limit(effort):
    payload = llm_client._openai_payload("vllm", [{"role": "user", "content": "hi"}], "Qwen/Qwen3-32B", [KB_TOOL], effort, max_output_tokens=4096)
    assert payload["reasoning_effort"] == effort
    assert payload["max_completion_tokens"] == 4096
    assert payload["tool_choice"] == "auto"
def test_vllm_payload_omits_unset_options_and_asks_for_stream_usage():
    payload = llm_client._openai_payload("vllm", [{"role": "user", "content": "hi"}], "Qwen/Qwen3-32B", None, None, max_output_tokens=None)
    assert payload["stream_options"] == {"include_usage": True}
    assert "reasoning_effort" not in payload
    assert "max_completion_tokens" not in payload
def test_openai_payload_ignores_the_output_limit_for_other_providers():
    payload = llm_client._openai_payload("openai", [{"role": "user", "content": "hi"}], "gpt-5.4", None, None, max_output_tokens=4096)
    assert "max_completion_tokens" not in payload
    assert payload["stream_options"] == {"include_usage": True}
    assert "stream_options" not in llm_client._openai_payload("gemini", [{"role": "user", "content": "hi"}], "gemini-3.8-flash", None, None, max_output_tokens=None)
@pytest.fixture(autouse=True)
def fresh_vllm_model_lengths(monkeypatch):
    monkeypatch.setattr(llm_client, "_vllm_model_lengths", {})
VLLM_MODELS = (200, {"object": "list", "data": [{"id": "Qwen/Qwen3-32B", "object": "model", "max_model_len": 65536}]})
@pytest.mark.asyncio
@pytest.mark.parametrize("limit, models_reply, expected, lookup_count", [
    (131072, VLLM_MODELS, None, 1),
    (65536, VLLM_MODELS, None, 1),
    (8192, VLLM_MODELS, 8192, 1),
    (8192, (200, {"object": "list", "data": [{"id": "Qwen/Qwen3-32B", "object": "model"}]}), 8192, 1),
    (8192, (404, {"detail": "Not Found"}), 8192, 1),
    (None, VLLM_MODELS, None, 0),
])
async def test_vllm_output_limit_gives_way_to_the_model_context_length(monkeypatch, limit, models_reply, expected, lookup_count):
    lookups, payloads = [], []
    def handler(request):
        if request.method == "GET":
            lookups.append(request.url.path)
            return httpx.Response(models_reply[0], json=models_reply[1])
        payloads.append(json.loads(request.content))
        return completion_stream({"role": "assistant", "content": "好"})
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    endpoint = LlmEndpoint("vllm", "http://localhost:8000/v1", None, limit, False)
    for _ in range(2):
        await llm_client.chat_completion([{"role": "user", "content": "hi"}], endpoint=endpoint, model_name="Qwen/Qwen3-32B")
    assert [payload.get("max_completion_tokens") for payload in payloads] == [expected, expected]
    assert lookups == ["/v1/models"] * lookup_count
@pytest.mark.asyncio
async def test_vllm_resends_without_a_rejected_output_limit(monkeypatch):
    sent = []
    def handler(request):
        if request.method == "GET":
            return httpx.Response(VLLM_MODELS[0], json=VLLM_MODELS[1])
        payload = json.loads(request.content)
        sent.append(payload.get("max_completion_tokens"))
        if "max_completion_tokens" in payload:
            return httpx.Response(400, json={"error": {
                "message": "This model's maximum context length is 65536 tokens. However, you requested 32768 output tokens and your prompt contains at least 40000 input tokens",
                "type": "BadRequestError",
                "code": 400,
            }})
        if payload["stream"]:
            return httpx.Response(200, text='data: {"choices": [{"delta": {"content": "好"}}]}\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "好"}}]})
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    endpoint = LlmEndpoint("vllm", "http://localhost:8000/v1", None, 32768, False)
    reply = await llm_client.chat_completion([{"role": "user", "content": "hi"}], endpoint=endpoint, model_name="Qwen/Qwen3-32B")
    chunks = [chunk async for chunk in llm_client.stream_completion([{"role": "user", "content": "hi"}], endpoint=endpoint, model_name="Qwen/Qwen3-32B", reasoning_effort="none")]
    assert reply["content"] == "好" and chunks == ["好"]
    assert sent == [32768, None, 32768, None]
@pytest.mark.asyncio
async def test_vllm_context_length_is_read_again_after_the_cache_expires(monkeypatch):
    lengths = iter([131072, 65536])
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "Qwen/Qwen3-32B", "max_model_len": next(lengths)}]})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "好"}}]})
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    endpoint = LlmEndpoint("vllm", "http://localhost:8000/v1", None, 100000, False)
    assert await llm_client._vllm_output_tokens(endpoint, "Qwen/Qwen3-32B") == 100000
    key = (endpoint.api_base, "Qwen/Qwen3-32B")
    llm_client._vllm_model_lengths[key] = (0.0, llm_client._vllm_model_lengths[key][1])
    assert await llm_client._vllm_output_tokens(endpoint, "Qwen/Qwen3-32B") is None
@pytest.mark.asyncio
async def test_vllm_chat_explains_a_server_without_tool_calling(monkeypatch):
    def handler(request):
        return httpx.Response(400, json={"error": {
            "message": '"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set',
            "type": "BadRequestError",
            "code": 400,
        }})
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(RuntimeError) as raised:
        await llm_client.chat_completion([{"role": "user", "content": "hi"}], endpoint=LOCAL_VLLM, model_name="Qwen/Qwen3-32B", tools=[KB_TOOL])
    assert str(raised.value) == llm_client.VLLM_TOOLS_DISABLED_MESSAGE
@pytest.mark.asyncio
async def test_vllm_tool_round_trip_keeps_reasoning_for_the_next_request(monkeypatch):
    sent = []
    replies = [
        completion_stream({
            "role": "assistant", "content": None, "reasoning": "先查知識庫",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"}}],
        }, "tool_calls", {"prompt_tokens": 20, "completion_tokens": 8}),
        completion_stream({"role": "assistant", "content": "特休依年資計算"}),
    ]
    def handler(request):
        sent.append((request.url.path, json.loads(request.content)))
        return replies[len(sent) - 1]
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    messages = [{"role": "user", "content": "特休怎麼算"}]
    first = await llm_client.chat_completion(messages, endpoint=LOCAL_VLLM, model_name="Qwen/Qwen3-32B", tools=[KB_TOOL], reasoning_effort="high")
    assert first["tool_calls"][0]["function"]["name"] == "search_knowledge_base"
    messages += [first, {"role": "tool", "tool_call_id": "call_1", "name": "search_knowledge_base", "content": "特休依年資計算"}]
    second = await llm_client.chat_completion(messages, endpoint=LOCAL_VLLM, model_name="Qwen/Qwen3-32B", tools=[KB_TOOL], reasoning_effort="high")
    assert second["content"] == "特休依年資計算"
    assert [path for path, _ in sent] == ["/v1/chat/completions"] * 2
    assert sent[1][1]["messages"][1]["reasoning"] == "先查知識庫"
@pytest.mark.asyncio
async def test_vllm_stream_yields_only_answer_text(monkeypatch):
    events = [
        {"choices": [{"delta": {"reasoning": "想一下"}}]},
        {"choices": [{"delta": {"content": "特休"}}]},
        {"choices": [{"delta": {"content": "依年資計算"}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 6}},
    ]
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        body = "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events) + "data: [DONE]\n\n"
        return httpx.Response(200, text=body)
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    chunks = [chunk async for chunk in llm_client.stream_completion([{"role": "user", "content": "hi"}], endpoint=LOCAL_VLLM, model_name="Qwen/Qwen3-32B", reasoning_effort="none")]
    assert chunks == ["特休", "依年資計算"]
    assert payloads[0]["stream_options"] == {"include_usage": True}
    assert payloads[0]["reasoning_effort"] == "none"
@pytest.mark.asyncio
async def test_vllm_lists_models_from_its_openai_models_endpoint(monkeypatch):
    paths = []
    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"object": "list", "data": [{"id": "Qwen/Qwen3-32B", "object": "model"}]})
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await llm_client.list_models(LOCAL_VLLM) == ["Qwen/Qwen3-32B"]
    assert paths == ["/v1/models"]
def install_http(monkeypatch, body):
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, text=body)
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return payloads
@pytest.mark.asyncio
async def test_chat_is_streamed_and_rebuilds_tool_calls_from_deltas(monkeypatch):
    payloads = install_http(monkeypatch, sse([
        {"choices": [{"delta": {"role": "assistant", "reasoning": "先查"}}]},
        {"choices": [{"delta": {"reasoning": "知識庫"}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{\"query\""}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ": \"特休\"}"}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 1, "id": "call_2", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 8}},
    ]))
    message = await llm_client.chat_completion([{"role": "user", "content": "特休怎麼算"}], endpoint=LOCAL_VLLM, model_name="Qwen/Qwen3-32B", tools=[KB_TOOL])
    assert payloads[0]["stream"] is True
    assert message == {"role": "assistant", "content": None, "reasoning": "先查知識庫", "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"}},
        {"id": "call_2", "type": "function", "function": {"name": "web_search", "arguments": "{}"}},
    ]}
def test_streamed_tool_calls_without_a_matching_index_stay_apart_and_keep_extra_fields():
    message = {}
    for delta in (
        {"tool_calls": [{"id": "a", "type": "function", "function": {"name": "x", "arguments": "{}"}, "extra_content": {"google": {"thought_signature": "sig"}}}]},
        {"tool_calls": [{"id": "b", "type": "function", "function": {"name": "y", "arguments": "{}"}}]},
        {"tool_calls": [{"index": 0, "id": "c", "type": "function", "function": {"name": "z", "arguments": "{}"}}]},
    ):
        llm_client._merge_delta(message, delta)
    assert [(call["id"], call["function"]["name"]) for call in message["tool_calls"]] == [("a", "x"), ("b", "y"), ("c", "z")]
    assert message["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "sig"}}
def test_blank_fields_in_later_tool_call_chunks_continue_the_same_call():
    message = {}
    for delta in (
        {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{\"query\""}}]},
        {"tool_calls": [{"index": 0, "id": "", "type": "", "function": {"name": "", "arguments": ": \"特休\"}"}}]},
    ):
        llm_client._merge_delta(message, delta)
    assert message["tool_calls"] == [
        {"id": "call_1", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"}},
    ]
@pytest.mark.asyncio
async def test_error_inside_a_chat_stream_is_raised(monkeypatch):
    install_http(monkeypatch, sse([{"choices": [{"delta": {"content": "特"}}]}, {"error": {"message": "engine died"}}]))
    with pytest.raises(RuntimeError, match="engine died"):
        await llm_client.chat_completion([{"role": "user", "content": "hi"}], endpoint=LOCAL_VLLM, model_name="Qwen/Qwen3-32B")
OPENAI_RESPONSES = LlmEndpoint("openai", "https://api.openai.com/v1", "openai-key", None, False)
@pytest.mark.asyncio
async def test_responses_chat_reads_the_completed_response_from_the_stream(monkeypatch):
    output = [{"type": "function_call", "id": "fc_1", "call_id": "call_a", "name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"}]
    payloads = install_http(monkeypatch, sse([
        {"type": "response.output_item.added", "item": output[0]},
        {"type": "response.completed", "response": {"status": "completed", "output": output}},
    ]))
    message = await llm_client.chat_completion([{"role": "user", "content": "特休怎麼算"}], endpoint=OPENAI_RESPONSES, model_name="gpt-6.1-sol", tools=[KB_TOOL])
    assert (payloads[0]["stream"], payloads[0]["tool_choice"]) == (True, "auto")
    assert message["tool_calls"] == [{"id": "call_a", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{\"query\": \"特休\"}"}}]
@pytest.mark.asyncio
async def test_responses_chat_explains_an_incomplete_stream(monkeypatch):
    install_http(monkeypatch, sse([{"type": "response.incomplete", "response": {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}}]))
    with pytest.raises(RuntimeError, match="max_output_tokens"):
        await llm_client.chat_completion([{"role": "user", "content": "hi"}], endpoint=OPENAI_RESPONSES, model_name="gpt-6.1-sol")
@pytest.mark.asyncio
async def test_ollama_chat_is_streamed_and_keeps_thinking_with_the_tool_calls(monkeypatch):
    lines = [
        {"message": {"role": "assistant", "content": "", "thinking": "先查"}, "done": False},
        {"message": {"role": "assistant", "content": "", "thinking": "知識庫"}, "done": False},
        {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "search_knowledge_base", "arguments": {"query": "特休"}}}]}, "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"},
    ]
    payloads = install_http(monkeypatch, "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines))
    message = await llm_client.chat_completion([{"role": "user", "content": "特休怎麼算"}], endpoint=LOCAL_OLLAMA, model_name="qwen3:8b", tools=[KB_TOOL])
    assert payloads[0]["stream"] is True
    assert message[llm_client.OLLAMA_THINKING_KEY] == "先查知識庫"
    assert [json.loads(call["function"]["arguments"]) for call in message["tool_calls"]] == [{"query": "特休"}]
@pytest.mark.asyncio
async def test_streamed_chat_reads_to_the_end_so_the_connection_is_reused(monkeypatch):
    bodies = {
        "/v1/chat/completions": sse([{"choices": [{"delta": {"content": "好"}, "finish_reason": "stop"}]}]),
        "/v1/responses": sse([{"type": "response.completed", "response": {"status": "completed", "output": []}}]),
    }
    connections = []
    async def serve(reader, writer):
        connections.append(writer)
        try:
            while True:
                head = await reader.readuntil(b"\r\n\r\n")
                await reader.readexactly(int(re.search(rb"(?i)content-length: (\d+)", head).group(1)))
                body = bodies[head.split(b" ")[1].decode()].encode()
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n%x\r\n%s\r\n0\r\n\r\n" % (len(body), body))
                await writer.drain()
        except asyncio.IncompleteReadError:
            writer.close()
    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    base = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/v1"
    client = httpx.AsyncClient()
    monkeypatch.setattr(llm_client, "_http_client", client)
    for endpoint, model in ((LlmEndpoint("vllm", base, None, None, False), "Qwen/Qwen3-32B"), (LlmEndpoint("openai", base, "k", None, False), "gpt-6.1-sol")):
        for _ in range(2):
            await llm_client.chat_completion([{"role": "user", "content": "hi"}], endpoint=endpoint, model_name=model)
    await client.aclose()
    server.close()
    assert len(connections) == 1