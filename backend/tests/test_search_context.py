import threading
from types import SimpleNamespace
import pytest
from app import prompts
from app.core.limits import MAX_RESEARCH_KNOWLEDGE_SEARCHES
from app.rag.research_session import ResearchSession
from app.rag.retrievers.hybrid import HybridRetriever, RetrievedChunk, is_text_chunk, overlap_length
from app.rag.tools import ResearchToolRegistry
from app.rag.types import Document
from test_agent_guardrails import ScriptedLLM, answer, collect, make_agent, research, tool_call
LAW = [
    "第 50 條\n有下列情形之一者，處新臺幣一千五百元以上七千五百元以下罰鍰：\n一、攀登車輛。",
    "一、攀登車輛。\n二、跨越黃色警戒線。",
    "二、跨越黃色警戒線。\n第 51 條\n其他規定。",
]
def chunk(text, chunk_id, **metadata):
    return Document(page_content=text, metadata={"chunk_id": chunk_id, "source": "law.txt", **metadata})
def store(*docs):
    return SimpleNamespace(vector_store=SimpleNamespace(lock=threading.RLock(), chunks={d.metadata["chunk_id"]: d for d in docs}))
def test_overlap_between_neighbouring_chunks_is_removed():
    assert overlap_length(LAW[0], LAW[1]) == len("一、攀登車輛。")
    assert overlap_length("甲乙", "丙丁") == 0
def test_neighbours_come_only_from_the_same_text_document():
    docs = [chunk(text, i, document_id=1, chunk_index=i) for i, text in enumerate(LAW)]
    other = chunk("別份文件", 9, document_id=2, chunk_index=0)
    record = chunk("[記錄 1]", 10, document_id=1, chunk_index=3, record_index=1, preserve_whole=True)
    retriever = store(*docs, other, record)
    [(before, after)] = HybridRetriever.adjacent_texts(retriever, [docs[1]])
    assert before == "第 50 條\n有下列情形之一者，處新臺幣一千五百元以上七千五百元以下罰鍰：\n"
    assert after == "\n第 51 條\n其他規定。"
    assert HybridRetriever.adjacent_texts(retriever, [record, docs[2]]) == [("", ""), (docs[1].page_content[:-len("二、跨越黃色警戒線。")], "")]
    assert not is_text_chunk(record) and not is_text_chunk(chunk("Q：A", 11, document_id=3, chunk_index=0, qa_index=0))
class LawRetriever:
    def __init__(self):
        self.docs = [chunk(text, i, document_id=1, chunk_index=i) for i, text in enumerate(LAW)]
    def smart_search(self, query, target_document=None):
        return [RetrievedChunk(document=self.docs[1], score=0.9, relevance=0.9, pinned=False)]
    def adjacent_texts(self, documents):
        return HybridRetriever.adjacent_texts(store(*self.docs), documents)
@pytest.mark.asyncio
async def test_search_results_carry_the_text_around_each_chunk():
    result = await ResearchToolRegistry(retriever=LawRetriever()).search_knowledge_base("黃線")
    [doc] = result["documents"]
    assert list(doc)[-3:] == ["context_before", "content", "context_after"]
    assert "罰鍰" in doc["context_before"] and doc["content"].endswith("跨越黃色警戒線。")
    assert doc["context_after"].startswith("第 51 條")
    assert await ResearchToolRegistry(retriever=LawRetriever()).execute_tool("search_knowledge_base", {"query": " "}) == {"error": prompts.SEARCH_QUERY_REQUIRED}
def test_research_session_stops_repeated_and_excess_knowledge_searches():
    session = ResearchSession(["q"])
    assert session.refuse_tool_call("search_knowledge_base", {"query": "特休"}) is None
    assert session.refuse_tool_call("search_knowledge_base", {"query": "特休"}) is None
    session.limit_knowledge_searches(4)
    assert session.refuse_tool_call("search_knowledge_base", {"query": "特休"}) is None
    assert session.refuse_tool_call("search_knowledge_base", {"query": " 特休 "}) == {"error": prompts.KNOWLEDGE_SEARCH_REPEATED}
    session.forget_knowledge_call("search_knowledge_base", {"query": "特休"})
    assert session.refuse_tool_call("search_knowledge_base", {"query": "特休"}) is None
    assert session.refuse_tool_call("filter_and_count_records", {"keyword": "特休"}) is None
    assert not session.knowledge_searches_exhausted
    assert session.refuse_tool_call("search_knowledge_base", {"query": "年假"}) == {"error": prompts.KNOWLEDGE_SEARCH_LIMIT.format(limit=4)}
    assert session.knowledge_searches_exhausted
    assert session.refuse_tool_call("web_search", {"query": "年假"}) is None
@pytest.mark.asyncio
async def test_research_mode_answers_once_the_search_budget_is_spent(monkeypatch):
    calls = [tool_call("search_knowledge_base", {"query": f"關鍵字{i}"}, f"c{i}") for i in range(MAX_RESEARCH_KNOWLEDGE_SEARCHES + 1)]
    llm = ScriptedLLM([*calls, tool_call("search_knowledge_base", {"query": "再查一次"}, "extra")]).install(monkeypatch)
    agent, registry = make_agent(monkeypatch)
    events = await collect(research(agent, "員工宿舍"))
    steps = [e["data"] for e in events if e["event"] == "step_end"]
    assert [s["status"] for s in steps] == ["success"] * MAX_RESEARCH_KNOWLEDGE_SEARCHES + ["error"]
    assert len(llm.responses) == 1 and llm.stream_calls == 1
    final = llm.stream_messages[-1]
    assert final[-1]["content"] == prompts.ANSWER_NOW
    assert prompts.KNOWLEDGE_SEARCH_LIMIT.format(limit=MAX_RESEARCH_KNOWLEDGE_SEARCHES) in final[-2]["content"]
    llm = ScriptedLLM([*calls, answer("查不到")]).install(monkeypatch)
    agent, registry = make_agent(monkeypatch)
    events = await collect(research(agent, "員工宿舍", mode="agent"))
    assert all(e["data"]["status"] == "success" for e in events if e["event"] == "step_end")
@pytest.mark.asyncio
async def test_repeating_the_same_search_still_ends_the_loop(monkeypatch):
    same = [tool_call("search_knowledge_base", {"query": "特休"}, f"c{i}") for i in range(MAX_RESEARCH_KNOWLEDGE_SEARCHES + 2)]
    llm = ScriptedLLM(same).install(monkeypatch)
    agent, registry = make_agent(monkeypatch)
    events = await collect(research(agent, "特休幾天"))
    steps = [e["data"] for e in events if e["event"] == "step_end"]
    assert [s["status"] for s in steps] == ["success"] + ["error"] * MAX_RESEARCH_KNOWLEDGE_SEARCHES
    assert len(llm.responses) == 1 and llm.stream_calls == 1
    assert llm.stream_messages[-1][-1]["content"] == prompts.ANSWER_NOW
class FlakyRetriever(LawRetriever):
    def __init__(self):
        super().__init__()
        self.calls = 0
    def smart_search(self, query, target_document=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("重排模型暫時失敗")
        return super().smart_search(query, target_document)
@pytest.mark.asyncio
async def test_a_failed_search_can_be_retried_with_the_same_query(monkeypatch):
    same = {"query": "黃線"}
    ScriptedLLM([tool_call("search_knowledge_base", same, "a"), tool_call("search_knowledge_base", same, "b"), answer("罰鍰 [1]")]).install(monkeypatch)
    agent, registry = make_agent(monkeypatch, retriever=FlakyRetriever())
    events = await collect(research(agent, "跨越黃線會被罰嗎"))
    assert [e["data"]["status"] for e in events if e["event"] == "step_end"] == ["error", "success"]