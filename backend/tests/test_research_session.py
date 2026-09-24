from app.rag.research_session import ResearchSession, strip_citations


def kb_output(*chunks):
    return {"documents": [
        {"chunk_id": chunk_id, "source": source, "chunk_index": 0, "score": 0.9, "content": f"{source} 內容"}
        for chunk_id, source in chunks
    ]}


def test_same_chunk_keeps_its_citation_number_across_tool_calls():
    session = ResearchSession(["特休怎麼算"])
    first = kb_output((10, "leave.pdf"), (11, "overtime.pdf"))
    second = kb_output((11, "overtime.pdf"), (12, "handbook.pdf"))

    session.record_tool_output("search_knowledge_base", first)
    session.record_tool_output("search_knowledge_base", second)

    assert [doc["citation"] for doc in first["documents"]] == [1, 2]
    assert [doc["citation"] for doc in second["documents"]] == [2, 3]


def test_web_search_and_fetch_share_the_number_of_the_same_url():
    session = ResearchSession(["勞基法修正"])
    search = {"query": "勞基法", "results": [{"title": "新聞", "url": "https://news.example.com/a", "content": "摘要"}]}
    fetch = {"url": "https://news.example.com/a", "title": "新聞全文", "content": "全文"}

    session.record_tool_output("web_search", search)
    session.record_tool_output("web_fetch", fetch)

    assert search["results"][0]["citation"] == fetch["citation"] == 1


def test_cited_sources_follow_first_citation_order_and_ignore_unknown_numbers():
    session = ResearchSession(["問題"])
    session.record_tool_output("search_knowledge_base", kb_output((1, "a.pdf"), (2, "b.pdf"), (3, "c.pdf")))

    cited = session.cited_sources("甲[2]。乙[1,2]。丙[3][1]。丁[9]。戊[1，3]、[2、3]")

    assert [detail["citation"] for detail in cited] == [2, 1, 3]
    assert [detail["source"] for detail in cited] == ["b.pdf", "a.pdf", "c.pdf"]


def test_error_outputs_get_no_citations():
    session = ResearchSession(["問題"])
    output = {"error": "檢索知識庫時發生錯誤（錯誤代碼：abc）", "documents": []}

    session.record_tool_output("search_knowledge_base", output)

    assert session.cited_sources("[1]") == []
    assert not session.kb_content_returned


def test_strip_citations_removes_markers_only():
    assert strip_citations("依年資計算 [1][2]，另見 [3, 4]。第 [a] 項") == "依年資計算 ，另見 。第 [a] 項"
