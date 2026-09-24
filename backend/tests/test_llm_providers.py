import json
import re
from types import SimpleNamespace

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
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "anthropic-key")

    claude_models = [model for model in llm_client.get_available_models() if model.startswith("claude-")]

    assert "claude-opus-5" in claude_models
    assert all(re.fullmatch(r"claude-(opus|sonnet|haiku|fable)-\d+(-\d+)?", model) for model in claude_models)


@pytest.mark.parametrize("model, expected", [
    ("azure-gpt", "azure"),
    ("claude-opus-5", "anthropic"),
    ("gemini-3-pro", "gemini"),
    ("gpt-5.5", "openai"),
    ("qwen3:8b", "ollama"),
])
def test_resolve_provider(monkeypatch, model, expected):
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "https://azure.example.com")
    monkeypatch.setattr(settings, "AZURE_OPENAI_DEPLOYMENT", "azure-gpt")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "openai-key")

    assert llm_client.resolve_provider(model) == expected


def test_gpt_model_routes_to_azure_when_only_azure_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "https://azure.example.com")
    monkeypatch.setattr(settings, "AZURE_OPENAI_DEPLOYMENT", "azure-gpt")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    assert llm_client.resolve_provider("gpt-4o") == "azure"


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

    assert request["system"] == "系統提示"
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
    }]


CLAUDE_TOOL_USE_CONTENT = [
    SimpleNamespace(type="thinking", thinking="", signature="sig-1"),
    SimpleNamespace(type="tool_use", id="toolu_1", name="search_knowledge_base", input={"query": "特休"}),
]


def claude_agent(monkeypatch):
    registry = ResearchToolRegistry(retriever=StaticRetriever())
    monkeypatch.setattr(registry, "get_tool_definitions", lambda: [KB_TOOL])
    return ResearchAgent(tool_registry=registry)


@pytest.mark.asyncio
async def test_agent_tool_round_trip_with_claude_preserves_raw_content(claude, monkeypatch):
    fake_messages = claude(responses=[
        SimpleNamespace(stop_reason="tool_use", stop_details=None, content=CLAUDE_TOOL_USE_CONTENT),
        SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[SimpleNamespace(type="text", text="特休依年資計算 [1]")]),
    ])

    result = await claude_agent(monkeypatch).run_research("特休怎麼算？", model_name="claude-opus-5", max_turns=3)

    first_call, second_call = fake_messages.create_calls
    assert first_call["model"] == "claude-opus-5"
    assert first_call["system"] == agent_module.SYSTEM_PROMPT
    assert first_call["messages"] == [{"role": "user", "content": "特休怎麼算？"}]
    assert second_call["messages"][1] == {"role": "assistant", "content": CLAUDE_TOOL_USE_CONTENT}
    assert [block["tool_use_id"] for block in second_call["messages"][2]["content"]] == ["toolu_1"]
    assert fake_messages.stream_calls == []
    assert all("temperature" not in call for call in fake_messages.create_calls)
    assert result["answer"] == "特休依年資計算 [1]"
    assert result["sources"] == ["leave.txt"]


@pytest.mark.asyncio
async def test_claude_streams_final_answer_when_turn_limit_is_reached(claude, monkeypatch):
    fake_messages = claude(
        responses=[SimpleNamespace(stop_reason="tool_use", stop_details=None, content=CLAUDE_TOOL_USE_CONTENT)],
        stream_chunks=["特休", "依年資計算"],
    )

    result = await claude_agent(monkeypatch).run_research("特休怎麼算？", model_name="claude-opus-5", max_turns=1)

    (first_call,) = fake_messages.create_calls
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


def test_openai_compatible_payload_strips_private_fields():
    messages = [{"role": "assistant", "content": "hi", "_anthropic_content": ["raw"]}]

    payload = llm_client._openai_payload("gemini", messages, "gemini-3-pro", None, "high", stream=True)

    assert payload["messages"] == [{"role": "assistant", "content": "hi"}]
    assert "reasoning_effort" not in payload
    assert "tools" not in payload
