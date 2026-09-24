import asyncio
import contextlib
import time

import pytest

from app.core.config import settings
from app.rag import agent as agent_module
from app.rag.pipeline import RAGPipeline
from app.rag.tools import ResearchToolRegistry
from app.rag.types import Document


class StaticRetriever:
    def smart_search(self, query):
        doc = Document(page_content="特休依年資計算", metadata={"source": "leave.txt", "chunk_index": 0})
        return [(doc, 0.9)]


async def collect(events):
    return [event async for event in events]


@pytest.mark.asyncio
async def test_pipeline_stream_stops_after_configured_max_turns(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MAX_TURNS", 3)
    pipeline = RAGPipeline(retriever=StaticRetriever())
    monkeypatch.setattr(pipeline.tool_registry, "get_tool_definitions", lambda: [])
    calls = {"tool_rounds": 0, "final_answers": 0}

    async def always_call_tool(messages, model_name=None, tools=None, reasoning_effort=None):
        calls["tool_rounds"] += 1
        await asyncio.sleep(0)
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "search_knowledge_base", "arguments": {"query": "特休"}}}],
        }

    async def final_answer(messages, model_name=None, tools=None, reasoning_effort=None):
        calls["final_answers"] += 1
        yield "依年資計算"

    monkeypatch.setattr(agent_module, "chat_completion", always_call_tool)
    monkeypatch.setattr(agent_module, "stream_completion", final_answer)

    events = await asyncio.wait_for(
        collect(pipeline.generate_response_stream("特休怎麼算", conversation_history=[])), timeout=5
    )

    assert calls == {"tool_rounds": 3, "final_answers": 1}
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["answer"] == "依年資計算"


@pytest.mark.asyncio
async def test_web_tools_hidden_and_blocked_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_WEB_SEARCH", False)
    registry = ResearchToolRegistry(retriever=StaticRetriever())

    async def must_not_fetch(url):
        raise AssertionError("web_fetch must not run when ENABLE_WEB_SEARCH is false")

    monkeypatch.setattr(registry, "web_fetch", must_not_fetch)

    names = [tool["function"]["name"] for tool in registry.get_tool_definitions()]
    result = await registry.execute_tool("web_fetch", {"url": "https://example.com"})

    assert "search_knowledge_base" in names
    assert "web_search" not in names
    assert "web_fetch" not in names
    assert "error" in result


@pytest.mark.asyncio
async def test_search_knowledge_base_does_not_block_event_loop():
    class SlowRetriever:
        def smart_search(self, query):
            time.sleep(0.5)
            return []

    registry = ResearchToolRegistry(retriever=SlowRetriever())
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker_task = asyncio.create_task(ticker())
    await registry.search_knowledge_base("特休")
    ticker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await ticker_task

    assert ticks >= 10
