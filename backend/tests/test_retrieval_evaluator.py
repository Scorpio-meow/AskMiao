import json
from pathlib import Path

import pytest

from app.rag.evaluator import RAGEvaluator, RetrievalCase, load_golden_set
from app.rag.retrievers.hybrid import HybridRetriever, RetrievedChunk
from app.rag.types import Document


class RankingRetriever:
    """rank() 依題目回傳預設的（來源, 重排機率）排名，select() 沿用正式的門檻邏輯"""
    final_k = 10

    def __init__(self, rankings, relevance_threshold):
        self.rankings = rankings
        self.relevance_threshold = relevance_threshold
        self.rank_calls = 0

    def rank(self, query):
        self.rank_calls += 1
        return [
            RetrievedChunk(
                document=Document(page_content=f"{source} 片段", metadata={"source": source}),
                score=relevance, relevance=relevance, pinned=False,
            )
            for source, relevance in self.rankings[query]
        ]

    def select(self, ranked, relevance_threshold):
        return HybridRetriever.select(self, ranked, relevance_threshold)


CASES = [
    RetrievalCase("q1", ["a.pdf"]),
    RetrievalCase("q2", ["b.pdf", "c.pdf"]),
    RetrievalCase("q3", ["z.pdf"]),
]


def test_evaluate_computes_document_level_metrics():
    retriever = RankingRetriever({
        "q1": [("a.pdf", 0.9), ("a.pdf", 0.8), ("b.pdf", 0.7)],
        "q2": [("x.pdf", 0.9), ("c.pdf", 0.8), ("b.pdf", 0.7)],
        "q3": [("x.pdf", 0.9)],
    }, relevance_threshold=0.5)

    report = RAGEvaluator(retriever).evaluate(CASES, k_values=[1, 3])

    assert report["num_queries"] == 3
    assert report["mrr"] == pytest.approx((1 + 1 / 2 + 0) / 3)
    assert report["hit_rate"] == pytest.approx({1: 1 / 3, 3: 2 / 3})
    assert report["recall"] == pytest.approx({1: 1 / 3, 3: 2 / 3})
    assert report["per_query"][0]["retrieved_sources"] == ["a.pdf", "b.pdf"]
    assert report["negative_rejection_rate"] is None


def test_negative_cases_report_rejection_rate_separately():
    cases = [RetrievalCase("q1", ["a.pdf"]), RetrievalCase("n1", []), RetrievalCase("n2", [])]
    retriever = RankingRetriever({
        "q1": [("a.pdf", 0.9)],
        "n1": [("a.pdf", 0.2)],
        "n2": [("b.pdf", 0.7)],
    }, relevance_threshold=0.5)

    report = RAGEvaluator(retriever).evaluate(cases, k_values=[1])

    assert (report["num_positive"], report["num_negative"]) == (1, 2)
    assert report["mrr"] == pytest.approx(1.0)
    assert report["negative_rejection_rate"] == pytest.approx(0.5)
    assert [q["rejected"] for q in report["per_query"][1:]] == [True, False]


def test_threshold_sweep_reranks_each_query_once():
    cases = [RetrievalCase("q1", ["a.pdf"]), RetrievalCase("n1", [])]
    retriever = RankingRetriever({
        "q1": [("x.pdf", 0.8), ("a.pdf", 0.4)],
        "n1": [("b.pdf", 0.3)],
    }, relevance_threshold=0.5)

    low, high = RAGEvaluator(retriever).sweep_relevance_thresholds(cases, k_values=[1, 3], thresholds=[0.2, 0.6])

    assert retriever.rank_calls == len(cases)
    assert (low["relevance_threshold"], high["relevance_threshold"]) == (0.2, 0.6)
    assert low["mrr"] == pytest.approx(1 / 2)
    assert low["negative_rejection_rate"] == 0.0
    assert high["mrr"] == 0.0
    assert high["negative_rejection_rate"] == 1.0


def test_load_golden_set_accepts_negative_cases_and_reports_invalid_line(tmp_path):
    golden = tmp_path / "golden.jsonl"
    golden.write_text(
        json.dumps({"query": "特休怎麼算？", "relevant_sources": ["員工手冊.pdf"]}, ensure_ascii=False) + "\n"
        + json.dumps({"query": "公司附近有什麼好吃的？", "relevant_sources": []}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    assert [case.relevant_sources for case in load_golden_set(str(golden))] == [["員工手冊.pdf"], []]

    with golden.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"query": "加班要誰核准？", "relevant_sources": "差勤管理辦法.docx"}, ensure_ascii=False) + "\n")

    with pytest.raises(ValueError, match="第 3 行"):
        load_golden_set(str(golden))


def test_example_golden_set_is_valid():
    example = Path(__file__).resolve().parent.parent / "eval" / "retrieval_golden.example.jsonl"

    cases = load_golden_set(str(example))

    assert len(cases) == 4
    assert sum(1 for case in cases if not case.relevant_sources) == 1
