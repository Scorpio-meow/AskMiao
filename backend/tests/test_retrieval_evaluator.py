import json
from pathlib import Path

import pytest

from app.rag.evaluator import RAGEvaluator, RetrievalCase, load_golden_set
from app.rag.types import Document


class RankingRetriever:
    def __init__(self, rankings_by_alpha, hybrid_alpha):
        self.rankings_by_alpha = rankings_by_alpha
        self.hybrid_alpha = hybrid_alpha

    def smart_search(self, query):
        sources = self.rankings_by_alpha[self.hybrid_alpha][query]
        return [(Document(page_content=f"{source} 片段", metadata={"source": source}), 1.0) for source in sources]


CASES = [
    RetrievalCase("q1", ["a.pdf"]),
    RetrievalCase("q2", ["b.pdf", "c.pdf"]),
    RetrievalCase("q3", ["z.pdf"]),
]


def test_evaluate_computes_document_level_metrics():
    retriever = RankingRetriever({0.5: {
        "q1": ["a.pdf", "a.pdf", "b.pdf"],
        "q2": ["x.pdf", "c.pdf", "b.pdf"],
        "q3": ["x.pdf"],
    }}, hybrid_alpha=0.5)

    report = RAGEvaluator(retriever).evaluate(CASES, k_values=[1, 3])

    assert report["num_queries"] == 3
    assert report["mrr"] == pytest.approx((1 + 1 / 2 + 0) / 3)
    assert report["hit_rate"] == pytest.approx({1: 1 / 3, 3: 2 / 3})
    assert report["recall"] == pytest.approx({1: 1 / 3, 3: 2 / 3})
    assert report["per_query"][0]["retrieved_sources"] == ["a.pdf", "b.pdf"]


def test_auto_tune_alpha_returns_best_alpha_and_restores_original():
    retriever = RankingRetriever({
        0.3: {"q1": ["x.pdf", "a.pdf"], "q2": ["b.pdf"], "q3": ["z.pdf"]},
        0.7: {"q1": ["a.pdf"], "q2": ["b.pdf"], "q3": ["z.pdf"]},
    }, hybrid_alpha=0.3)

    best = RAGEvaluator(retriever).auto_tune_alpha(CASES, k_values=[1], alphas=[0.3, 0.7])

    assert best["alpha"] == 0.7
    assert best["mrr"] == pytest.approx(1.0)
    assert retriever.hybrid_alpha == 0.3


def test_load_golden_set_reports_invalid_line(tmp_path):
    golden = tmp_path / "golden.jsonl"
    golden.write_text(
        json.dumps({"query": "特休怎麼算？", "relevant_sources": ["員工手冊.pdf"]}, ensure_ascii=False) + "\n\n"
        + json.dumps({"query": "加班要誰核准？", "relevant_sources": []}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="第 3 行"):
        load_golden_set(str(golden))


def test_example_golden_set_is_valid():
    example = Path(__file__).resolve().parent.parent / "eval" / "retrieval_golden.example.jsonl"

    cases = load_golden_set(str(example))

    assert len(cases) == 3
    assert all(case.relevant_sources for case in cases)
