import json
from pathlib import Path
import pytest
from app.rag.answer_evaluator import (
    AnswerCase,
    chunk_lookup,
    grade,
    judge_messages,
    load_answer_cases,
    missing_facts,
    missing_passages,
    normalize,
    parse_judgement,
    summarize,
)
from app.rag.types import Document
GOLDEN = Path(__file__).resolve().parent.parent / "eval" / "answer_golden.jsonl"
CORPUS_GOLDEN = Path(__file__).resolve().parent.parent / "eval" / "corpus_golden.jsonl"
def case(**overrides):
    fields = {
        "query": "日本出差住宿上限",
        "relevant_sources": ["差旅.md"],
        "relevant_passages": ["日本 | 新臺幣 5,500 元"],
        "facts": [["5500"]],
        "kind": "lookup",
        "note": "",
    }
    fields.update(overrides)
    return AnswerCase(**fields)
LOOKUP = chunk_lookup([
    Document(page_content="| 日本 | 新臺幣 5,500 元 |", metadata={"source": "差旅.md", "chunk_index": 2}),
    Document(page_content="國內出差每日 600 元", metadata={"source": "差旅.md", "chunk_index": 3}),
    Document(page_content="[記錄 1] 忘記密碼", metadata={"source": "faq.jsonl", "chunk_index": 0}),
    Document(page_content="[記錄 2] 筆電遺失", metadata={"source": "faq.jsonl", "chunk_index": 0}),
])
def run(answer, details, tools=("search_knowledge_base",), error=None):
    return {"answer": answer, "sources_detail": details, "steps": [{"tool": t} for t in tools], "error": error}
def test_normalize_ignores_spacing_digit_groups_citations_and_variant_characters():
    assert normalize("新台幣 5,500 元[1][2]") == "新臺幣5500元"
    assert normalize("ＭＦＡ 用 Microsoft Authenticator") == "mfa用microsoftauthenticator"
    assert missing_facts("每晚上限新臺幣 5,500 元 [3]", [["5500"], ["經理", "主管"]]) == [["經理", "主管"]]
def test_numbers_only_match_whole_numbers():
    assert missing_facts("日本每晚 5,500 元", [["500"]]) == [["500"]]
    assert missing_facts("2025 年版已廢止", [["25"]]) == [["25"]]
    assert missing_facts("請於 13 日內提出", [["3日"]]) == [["3日"]]
    assert missing_facts("FortiClient 7.25", [["7.2"]]) == [["7.2"]]
    assert missing_facts("每月 500 元，年資 2.5 個月", [["500"], ["2.5個月"], ["5個月"]]) == [["5個月"]]
def test_positive_passes_only_with_facts_relevant_citation_and_search():
    cited = [{"source": "差旅.md", "chunk": 2}]
    good = grade(case(), run("上限 5,500 元[1]", cited), LOOKUP, None)
    assert good["passed"] and good["cite_passage"] is True
    assert grade(case(), run("上限 5,000 元[1]", cited), LOOKUP, None)["failure"] == "missing_facts"
    assert grade(case(), run("上限 5,500 元", []), LOOKUP, None)["failure"] == "no_relevant_citation"
    assert grade(case(), run("上限 5,500 元", cited, tools=()), LOOKUP, None)["failure"] == "no_search"
    wrong_chunk = grade(case(), run("上限 5,500 元[1]", [{"source": "差旅.md", "chunk": 3}]), LOOKUP, None)
    assert wrong_chunk["passed"] and wrong_chunk["cite_passage"] is False
    record = case(relevant_sources=["faq.jsonl"], relevant_passages=["筆電遺失"], facts=[["通報"]])
    assert grade(record, run("請通報[1]", [{"source": "faq.jsonl", "chunk": 0}]), LOOKUP, None)["cite_passage"] is True
    assert missing_passages(record, LOOKUP) == []
def test_judge_verdict_decides_positive_and_negative_cases():
    cited = [{"source": "差旅.md", "chunk": 2}]
    partial = grade(case(), run("5,500 元[1]", cited), LOOKUP, {"verdict": "partial", "reason": "漏了經理級"})
    assert partial["failure"] == "judge_partial"
    negative = case(relevant_sources=[], relevant_passages=[], facts=[], kind="negative")
    assert grade(negative, run("查不到", []), LOOKUP, {"verdict": "refused", "reason": ""})["passed"]
    made_up = grade(negative, run("宿舍每月 3,000 元", []), LOOKUP, {"verdict": "wrong", "reason": "編造"})
    assert made_up["failure"] == "not_refused"
    assert grade(case(), run("", [], error="ReadTimeout"), LOOKUP, None)["failure"] == "error"
def test_judge_prompt_carries_reference_and_strips_citations():
    messages = judge_messages(case(note="2025 年版已廢止"), "上限 5,500 元[1]", [{"source": "差旅.md", "chunk": 2}], LOOKUP)
    assert "5500" in messages[1]["content"] and "2025 年版已廢止" in messages[1]["content"]
    content = messages[1]["content"]
    assert content.count("| 日本 | 新臺幣 5,500 元 |") == 1
    assert content.index("回答引用的片段原文") < content.index("國內出差每日 600 元")
    record = judge_messages(case(), "請通報[1]", [{"source": "faq.jsonl", "chunk": 0}], LOOKUP)[1]["content"]
    assert "[記錄 1] 忘記密碼" in record and "[記錄 2] 筆電遺失" in record
    counted = judge_messages(case(), "共 1 題[1]", [{"source": "faq.jsonl", "snippet": "[記錄 2]"}], LOOKUP)[1]["content"]
    assert "[記錄 2] 筆電遺失" in counted and "[記錄 1] 忘記密碼" not in counted
    assert "[1]" not in messages[1]["content"]
    assert parse_judgement('好的\n```json\n{"verdict": "correct", "reason": "一致"}\n```') == {"verdict": "correct", "reason": "一致"}
    with pytest.raises(ValueError):
        parse_judgement('{"verdict": "maybe"}')
    with pytest.raises(ValueError):
        parse_judgement("看起來正確")
def test_summary_counts_stability_and_kinds():
    negative = case(query="宿舍", relevant_sources=[], relevant_passages=[], facts=[], kind="negative")
    results = [
        [{"grade": {"passed": True, "failure": None, "facts_ok": True, "cite_source": True, "cite_passage": True, "searched": True, "judge": None}, "total_time": 4.0, "turns_used": 2}] * 2,
        [
            {"grade": {"passed": True, "failure": None, "refused": True, "searched": True, "judge": None}, "total_time": 2.0, "turns_used": 2},
            {"grade": {"passed": False, "failure": "not_refused", "refused": False, "searched": False, "judge": None}, "total_time": 6.0, "turns_used": 1},
        ],
    ]
    summary = summarize([case(), negative], results)
    assert summary["pass_rate"] == 0.75 and summary["refusal_rate"] == 0.5
    assert (summary["always_pass"], summary["flaky"], summary["always_fail"]) == (1, 1, 0)
    assert summary["by_kind"]["negative"]["pass_rate"] == 0.5
    assert summary["failures"] == {"not_refused": 1}
def test_loader_rejects_incomplete_cases(tmp_path):
    path = tmp_path / "golden.jsonl"
    path.write_text(json.dumps({"query": "q", "relevant_sources": ["a.md"], "kind": "lookup"}), encoding="utf-8")
    with pytest.raises(ValueError, match="facts"):
        load_answer_cases(str(path))
    path.write_text(json.dumps({"query": "q", "relevant_sources": [], "facts": [["x"]], "kind": "negative"}), encoding="utf-8")
    with pytest.raises(ValueError, match="反例"):
        load_answer_cases(str(path))
def test_bundled_answer_set_covers_every_retrieval_question():
    cases = load_answer_cases(str(GOLDEN))
    queries = {c.query for c in cases}
    retrieval = [json.loads(line)["query"] for line in CORPUS_GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert set(retrieval) <= queries
    assert len(queries) == len(cases)
    assert {c.kind for c in cases} >= {"lookup", "negative", "calc", "multi_doc", "false_premise", "compare", "count"}