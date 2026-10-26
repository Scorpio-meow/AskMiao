import json
import re
from types import SimpleNamespace

import httpx
import pytest

from app.core import llm_client
from app.core.config import settings
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


class StaticRetriever:
    def smart_search(self, query, target_document=None):
        doc = Document(page_content="特休依年資計算", metadata={"source": "leave.txt", "chunk_index": 0, "chunk_id": 7})
        return [RetrievedChunk(document=doc, score=0.9, relevance=0.9, pinned=False)]


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
        self.create_calls = []
        self.stream_calls = []

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.responses.pop(0)

    def stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        return FakeStream(self.stream_chunks, SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[]))


class FakeAnthropicClient:
    def __init__(self, messages):
        self.messages = messages

    def with_options(self, **kwargs):
        return self


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ANTHROPIC_MAX_TOKENS", 16000)

    def install(responses, stream_chunks=()):
        fake_messages = FakeAnthropicMessages(responses, stream_chunks)
        monkeypatch.setattr(llm_client, "_anthropic_client_instance", lambda: FakeAnthropicClient(fake_messages))
        return fake_messages

    return install


def test_default_claude_model_ids_use_family_version_format(monkeypatch):
    monkeypatch.setattr(settings, "AVAILABLE_MODELS", "")
    monkeypatch.setattr(settings, "FOUNDRY_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "anthropic-key")

    claude_models = [model for model in llm_client.get_available_models() if model.startswith("claude-")]

    assert "claude-opus-5" in claude_models
    assert all(re.fullmatch(r"claude-(opus|sonnet|haiku|fable)-\d+(-\d+)?", model) for model in claude_models)


@pytest.mark.parametrize("model, expected", [
    ("foundry-gpt", "foundry"),
    ("claude-opus-5-5", "anthropic"),
    ("gemini-3-pro", "gemini"),
    ("gpt-5.6-sol", "openai"),
    ("qwen3:8b", "ollama"),
])
def test_resolve_provider(monkeypatch, model, expected):
    monkeypatch.setattr(settings, "FOUNDRY_API_KEY", "foundry-key")
    monkeypatch.setattr(settings, "FOUNDRY_ENDPOINT", "https://foundry.example.com")
    monkeypatch.setattr(settings, "FOUNDRY_DEPLOYMENT", "foundry-gpt")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "openai-key")

    assert llm_client.resolve_provider(model) == expected


def test_gpt_model_routes_to_foundry_when_only_foundry_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "FOUNDRY_API_KEY", "foundry-key")
    monkeypatch.setattr(settings, "FOUNDRY_ENDPOINT", "https://foundry.example.com")
    monkeypatch.setattr(settings, "FOUNDRY_DEPLOYMENT", "foundry-gpt")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    assert llm_client.resolve_provider("gpt-6-sol") == "foundry"


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
            {"type": "tool_result", "tool_use_id": "call_b", "content": "{\"results\": []}"},
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
        {"type": "tool_result", "tool_use_id": "call_a", "content": "{\"error\": \"x\"}", "is_error": True},
    ]


def test_anthropic_effort_options_map_reasoning_effort():
    assert llm_client._anthropic_effort_options("high") == {"extra_body": {"output_config": {"effort": "high"}}}
    assert llm_client._anthropic_effort_options("minimal") == {"extra_body": {"output_config": {"effort": "low"}}}
    assert llm_client._anthropic_effort_options("none") == {}
    assert llm_client._anthropic_effort_options(None) == {}


CLAUDE_TOOL_USE_CONTENT = [
    SimpleNamespace(type="thinking", thinking="", signature="sig-1"),
    SimpleNamespace(type="tool_use", id="toolu_1", name="search_knowledge_base", input={"query": "特休"}),
]


def claude_agent(monkeypatch):
    registry = ResearchToolRegistry(retriever=StaticRetriever())
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None: [KB_TOOL])
    return ResearchAgent(tool_registry=registry)


async def final_result(events):
    """stream_research 最後的 done 事件內容"""
    return [event async for event in events if event["event"] == "done"][-1]["data"]


@pytest.mark.asyncio
async def test_agent_tool_round_trip_with_claude_preserves_raw_content(claude, monkeypatch):
    fake_messages = claude(responses=[
        SimpleNamespace(stop_reason="tool_use", stop_details=None, content=CLAUDE_TOOL_USE_CONTENT),
        SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[SimpleNamespace(type="text", text="特休依年資計算 [1]")]),
    ])

    result = await final_result(claude_agent(monkeypatch).stream_research("特休怎麼算？", model_name="claude-opus-5"))

    first_call, second_call = fake_messages.create_calls
    assert first_call["model"] == "claude-opus-5"
    assert first_call["system"] == [{"type": "text", "text": agent_module.SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    assert first_call["messages"] == [{"role": "user", "content": "特休怎麼算？"}]
    assert second_call["messages"][1] == {"role": "assistant", "content": CLAUDE_TOOL_USE_CONTENT}
    assert [block["tool_use_id"] for block in second_call["messages"][2]["content"]] == ["toolu_1"]
    assert fake_messages.stream_calls == []
    assert all("temperature" not in call for call in fake_messages.create_calls)
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

    result = await final_result(claude_agent(monkeypatch).stream_research("特休怎麼算？", model_name="claude-opus-5"))

    first_call, _ = fake_messages.create_calls
    (stream_call,) = fake_messages.stream_calls
    assert stream_call["tool_choice"] == {"type": "none"}
    assert stream_call["tools"] == first_call["tools"]
    assert all("temperature" not in call for call in fake_messages.create_calls + fake_messages.stream_calls)
    assert result["answer"] == "特休依年資計算"


@pytest.mark.asyncio
async def test_call_llm_returns_text_blocks_after_thinking(claude):
    claude(responses=[SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[
        SimpleNamespace(type="thinking", thinking="", signature="sig"),
        SimpleNamespace(type="text", text="文件摘要"),
    ])])

    answer = await llm_client.call_llm([{"role": "user", "content": "摘要"}], model_name="claude-opus-5")

    assert answer == "文件摘要"


@pytest.mark.asyncio
async def test_claude_refusal_raises(claude):
    claude(responses=[SimpleNamespace(
        stop_reason="refusal",
        stop_details=SimpleNamespace(category="cyber"),
        content=[],
    )])

    with pytest.raises(RuntimeError, match="refusal"):
        await llm_client.chat_completion([{"role": "user", "content": "…"}], model_name="claude-opus-5")


@pytest.mark.asyncio
async def test_claude_requires_max_tokens_setting(claude, monkeypatch):
    claude(responses=[])
    monkeypatch.setattr(settings, "ANTHROPIC_MAX_TOKENS", None)

    with pytest.raises(ValueError, match="ANTHROPIC_MAX_TOKENS"):
        await llm_client.chat_completion([{"role": "user", "content": "你好"}], model_name="claude-opus-5")


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
    payload = llm_client._ollama_payload([{"role": "user", "content": "hi"}], "qwen3:8b", None, stream=False, reasoning_effort=effort)

    assert payload["think"] is expected if isinstance(expected, bool) else payload["think"] == expected


def test_ollama_payload_omits_think_without_reasoning_effort():
    payload = llm_client._ollama_payload([{"role": "user", "content": "hi"}], "qwen3:8b", None, stream=False, reasoning_effort=None)

    assert "think" not in payload


def test_openai_compatible_payload_strips_private_fields():
    messages = [{"role": "assistant", "content": "hi", "_anthropic_content": ["raw"]}]

    payload = llm_client._openai_payload("gemini", messages, "gemini-3.8-flash", None, None, stream=True)

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
    payload = llm_client._openai_payload("gemini", [{"role": "user", "content": "hi"}], "gemini-3.8-flash", None, effort, stream=False)

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

    await llm_client.chat_completion(messages, model_name="local-model", timeout=18.0)
    assert [chunk async for chunk in llm_client.stream_completion(messages, model_name="local-model")] == ["好"]

    # 每次請求自帶的逾時不能把等待連線池名額的上限一起拉長到整個請求的逾時
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

    payload = llm_client._responses_payload(messages, "gpt-6.1-sol", [KB_TOOL], "none", stream=False)

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


def test_responses_endpoint_per_provider(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "openai-key")
    monkeypatch.setattr(settings, "OPENAI_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "FOUNDRY_API_KEY", "foundry-key")
    monkeypatch.setattr(settings, "FOUNDRY_ENDPOINT", "https://res.openai.azure.com/")

    openai_url, openai_headers = llm_client._responses_endpoint("openai")
    foundry_url, foundry_headers = llm_client._responses_endpoint("foundry")

    assert openai_url == "https://api.openai.com/v1/responses"
    assert openai_headers["Authorization"] == "Bearer openai-key"
    assert foundry_url == "https://res.openai.azure.com/openai/v1/responses"
    assert foundry_headers["api-key"] == "foundry-key"


def test_foundry_settings_still_read_legacy_azure_openai_names(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://legacy.openai.azure.com")
    monkeypatch.setenv("FOUNDRY_DEPLOYMENT", "new-deployment")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "legacy-deployment")

    loaded = type(settings)()

    assert loaded.FOUNDRY_API_KEY == "legacy-key"
    assert loaded.FOUNDRY_ENDPOINT == "https://legacy.openai.azure.com"
    assert loaded.FOUNDRY_DEPLOYMENT == "new-deployment"


def test_responses_streaming_payload_declares_tools_but_forbids_calling_them():
    messages = [{"role": "system", "content": [{"type": "text", "text": "系統"}, {"type": "text", "text": "提示"}]}]

    payload = llm_client._responses_payload(messages, "gpt-6-astra", [KB_TOOL], "high", stream=True)

    assert payload["tool_choice"] == "none"
    assert payload["tools"][0]["name"] == "search_knowledge_base"
    assert payload["input"] == [{"role": "system", "content": "系統\n提示"}]


def configure_foundry(monkeypatch, endpoint):
    monkeypatch.setattr(settings, "FOUNDRY_API_KEY", "foundry-key")
    monkeypatch.setattr(settings, "FOUNDRY_ENDPOINT", endpoint)
    monkeypatch.setattr(settings, "FOUNDRY_DEPLOYMENT", "claude-sonnet-4-6,my-gpt")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(llm_client, "_foundry_anthropic_client", None)


def test_foundry_claude_deployment_routes_to_anthropic_and_other_deployments_stay_on_foundry(monkeypatch):
    configure_foundry(monkeypatch, "https://res.services.ai.azure.com")

    assert llm_client.resolve_provider("claude-sonnet-4-6") == "anthropic"
    assert llm_client.resolve_provider("my-gpt") == "foundry"
    assert llm_client.is_foundry_claude("claude-sonnet-4-6")
    assert not llm_client.is_foundry_claude("my-gpt")


def test_foundry_claude_client_uses_anthropic_endpoint_and_api_key(monkeypatch):
    configure_foundry(monkeypatch, "https://res.services.ai.azure.com/")

    client = llm_client._anthropic_client_for("claude-sonnet-4-6")

    assert str(client.base_url).rstrip("/") == "https://res.services.ai.azure.com/anthropic"
    assert client.api_key == "foundry-key"
    assert llm_client._anthropic_client_for("claude-sonnet-4-6") is client


def test_foundry_claude_rejects_azure_openai_resource_endpoint(monkeypatch):
    configure_foundry(monkeypatch, "https://res.openai.azure.com")

    with pytest.raises(ValueError, match="services.ai.azure.com"):
        llm_client._anthropic_client_for("claude-sonnet-4-6")


def test_direct_claude_uses_the_anthropic_client_even_when_foundry_is_enabled(monkeypatch):
    configure_foundry(monkeypatch, "https://res.services.ai.azure.com")
    sentinel = object()
    monkeypatch.setattr(llm_client, "_anthropic_client_instance", lambda: sentinel)

    assert llm_client._anthropic_client_for("claude-opus-5-5") is sentinel


def test_foundry_chat_completions_skips_reasoning_effort_for_non_openai_models():
    messages = [{"role": "user", "content": "hi"}]

    kimi = llm_client._openai_payload("foundry", messages, "Kimi-K2.6", None, "high", stream=False)
    gpt = llm_client._openai_payload("foundry", messages, "gpt-oss-120b", None, "high", stream=False)

    assert "reasoning_effort" not in kimi
    assert gpt["reasoning_effort"] == "high"


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
    payload = llm_client._ollama_payload([{"role": "user", "content": "hi"}], "gpt-oss:20b", None, stream=False, reasoning_effort=effort)

    assert payload["think"] == expected


def test_ollama_options_include_num_ctx_only_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_TEMPERATURE", None)
    monkeypatch.setattr(settings, "OLLAMA_NUM_PREDICT", None)
    monkeypatch.setattr(settings, "OLLAMA_NUM_CTX", None)
    assert llm_client._ollama_options() == {}

    monkeypatch.setattr(settings, "OLLAMA_NUM_CTX", 16384)
    assert llm_client._ollama_options() == {"num_ctx": 16384}


def test_ollama_cloud_requests_carry_bearer_key_only_for_ollama_com(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "ollama-key")

    assert llm_client.ollama_auth_headers("https://ollama.com/api/chat") == {"Authorization": "Bearer ollama-key"}
    assert llm_client.ollama_auth_headers("http://localhost:11434/api/chat") == {}
    assert llm_client.ollama_auth_headers("https://abc.ngrok-free.app/api/chat") == {}
    assert llm_client.ollama_auth_headers("https://ollama.com.evil.example/api/chat") == {}


@pytest.mark.asyncio
async def test_ollama_stream_raises_on_error_line(monkeypatch):
    def handler(request):
        return httpx.Response(200, content=b'{"message":{"content":"ab"}}\n{"error":"model crashed"}\n')

    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    received = []

    with pytest.raises(RuntimeError, match="model crashed"):
        async for chunk in llm_client._ollama_stream([{"role": "user", "content": "hi"}], "qwen3:8b", None):
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

    payload = llm_client._openai_payload("gemini", [assistant], "gemini-3.8-flash", [KB_TOOL], "high", stream=False)

    assert payload["messages"][0]["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "sig-abc"}}
