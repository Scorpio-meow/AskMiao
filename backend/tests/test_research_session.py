from app.rag.research_session import ResearchSession, strip_citations, strip_tool_result_blocks


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


def test_strip_citations_keeps_code():
    text = "取第一筆用 `items[0]` [1]\n```python\nprint(items[1])\n```\n~~~\nrow[2]\n~~~\n結果 [2]"

    assert strip_citations(text) == "取第一筆用 `items[0]` \n```python\nprint(items[1])\n```\n~~~\nrow[2]\n~~~\n結果 "


def fetch_allowed(session, url):
    arguments = {"url": url}
    return session.refuse_tool_call("web_fetch", arguments) is None, arguments["url"]


def test_web_fetch_url_must_match_a_whole_url_that_appeared():
    session = ResearchSession(["請摘要 https://news.example.com/labor-law?id=42。謝謝"])

    assert fetch_allowed(session, "https://news.example.com/labor-law?id=42") == (True, "https://news.example.com/labor-law?id=42")
    # 截斷、延伸與改寫編碼都不是出現過的網址
    for crafted in (
        "https://news.example.com/labor",
        "https://news.example.com/labor-law?id=4",
        "https://news.example.com/labor-law?id=42&leak=secret",
        "https://news.example.com/labor-law?id=%34%32",
        "https://news.example.com/labor-law%3Fid=42",
    ):
        assert fetch_allowed(session, crafted)[0] is False, crafted


def test_web_fetch_does_not_match_decoded_substrings():
    session = ResearchSession(["參考 https://a.example/r?to=https%3A%2F%2Fattacker.example%2Fleak"])

    assert fetch_allowed(session, "https://attacker.example/leak")[0] is False
    assert fetch_allowed(session, "https://a.example/r?to=https%3A%2F%2Fattacker.example%2Fleak")[0] is True


def test_web_fetch_accepts_the_same_url_with_non_ascii_encoded():
    session = ResearchSession(["看這篇 https://wiki.example.org/wiki/特休 說明"])

    allowed, sent = fetch_allowed(session, "https://wiki.example.org/wiki/%E7%89%B9%E4%BC%91")
    assert allowed is True
    assert sent == "https://wiki.example.org/wiki/%E7%89%B9%E4%BC%91"


def test_strip_tool_result_blocks_removes_blocks_and_stray_tags():
    text = '前言<untrusted_tool_result id="ab12">{"a": 1}\n[1] 內容</untrusted_tool_result id="ab12">中段<untrusted_tool_result>x</untrusted_tool_result>結尾</untrusted_tool_result>'

    assert strip_tool_result_blocks(text) == "前言中段結尾"


def test_tool_result_filter_matches_full_strip_at_every_chunk_boundary():
    from app.rag.research_session import ToolResultFilter

    text = '答案 [1]<untrusted_tool_result id="ab">{"links": ["https://x.example"]}</untrusted_tool_result id="ab">，以及 <b>粗體</b> 結論'
    expected = strip_tool_result_blocks(text)
    for size in range(1, len(text) + 1):
        stream_filter = ToolResultFilter()
        out = "".join(stream_filter.feed(text[i:i + size]) for i in range(0, len(text), size)) + stream_filter.flush()
        assert out == expected == "答案 [1]，以及 <b>粗體</b> 結論"


def test_tool_result_filter_keeps_content_of_an_unclosed_block():
    from app.rag.research_session import ToolResultFilter

    stream_filter = ToolResultFilter()

    assert stream_filter.feed("結論<untrusted_tool_result>沒有結尾") == "結論"
    assert stream_filter.flush() == "沒有結尾"
