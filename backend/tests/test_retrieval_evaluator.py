import json
import threading
from pathlib import Path

import pytest

from app.core.config import settings
from app.rag.evaluator import RAGEvaluator, RetrievalCase, load_golden_set, passage_relevant_chunk_ids
from app.rag.retrievers.hybrid import HybridRetriever, RetrievedChunk
from app.rag.types import Document

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


class ChunkStoreStub:
    def __init__(self, chunks):
        self.chunks = chunks
        self.lock = threading.RLock()


class RankingRetriever:
    """rank() 依題目回傳預設的（來源, 重排機率）排名，select() 沿用正式的門檻邏輯"""
    final_k = 10

    def __init__(self, rankings, relevance_threshold, chunks=None):
        self.rankings = rankings
        self.relevance_threshold = relevance_threshold
        self.rank_calls = 0
        self.vector_store = ChunkStoreStub(chunks or {})

    def rank(self, query):
        self.rank_calls += 1
        return [
            RetrievedChunk(document=self._document(item), score=relevance, relevance=relevance, pinned=False)
            for item, relevance in self.rankings[query]
        ]

    def _document(self, item):
        if isinstance(item, int):
            return self.vector_store.chunks[item]
        return Document(page_content=f"{item} 片段", metadata={"source": item})

    def select(self, ranked, relevance_threshold):
        return HybridRetriever.select(self, ranked, relevance_threshold)


def chunk(chunk_id, content, source):
    return Document(page_content=content, metadata={"chunk_id": chunk_id, "source": source})


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
    assert report["passage"] is None


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


def test_passage_metrics_score_chunks_that_contain_the_labelled_text():
    chunks = {
        1: chunk(1, "滿 1 年未滿 2 年：7 日", "handbook.md"),
        2: chunk(2, "加班需事前申請", "attendance.md"),
        3: chunk(3, "滿 2 年未滿 3 年：10 日", "handbook.md"),
        4: chunk(4, "重疊段落：滿 2 年未滿 3 年：10 日", "handbook.md"),
    }
    case = RetrievalCase("年資兩年半的特休", ["handbook.md"], ["滿 2 年未滿 3 年：10 日"])
    retriever = RankingRetriever({case.query: [(2, 0.9), (3, 0.8), (1, 0.3), (4, 0.1)]}, relevance_threshold=0.2, chunks=chunks)

    passage = RAGEvaluator(retriever).evaluate([case], k_values=[1, 3])["passage"]

    assert passage["num_cases"] == 1
    assert passage["precision"] == pytest.approx({1: 0.0, 3: 1 / 3})
    assert passage["recall"] == pytest.approx({1: 0.0, 3: 1.0})
    assert passage["mrr"] == pytest.approx(1 / 2)
    ideal = 1 + 1 / 1.584962500721156
    assert passage["ndcg"][3] == pytest.approx((1 / 1.584962500721156) / ideal)
    assert passage["candidate_recall"] == pytest.approx(1.0)


def test_candidate_recall_counts_chunks_cut_by_the_threshold():
    chunks = {1: chunk(1, "補休應於 6 個月內休畢", "attendance.md"), 2: chunk(2, "其他內容", "attendance.md")}
    case = RetrievalCase("補休期限", ["attendance.md"], ["補休應於 6 個月內休畢"])
    retriever = RankingRetriever({case.query: [(2, 0.9), (1, 0.05)]}, relevance_threshold=0.5, chunks=chunks)

    passage = RAGEvaluator(retriever).evaluate([case], k_values=[3])["passage"]

    assert passage["recall"][3] == 0.0
    assert passage["candidate_recall"] == 1.0


def test_passage_missing_from_knowledge_base_is_reported():
    chunks = {1: chunk(1, "特休依年資計算", "handbook.md")}

    with pytest.raises(ValueError, match="找不到：不存在的條文"):
        passage_relevant_chunk_ids(RetrievalCase("q", ["handbook.md"], ["不存在的條文"]), chunks)


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


@pytest.mark.parametrize("record, message", [
    ({"query": "q", "relevant_sources": ["a.md"], "relevant_passages": "片段"}, "relevant_passages 必須是原文片段陣列"),
    ({"query": "q", "relevant_sources": ["a.md"], "relevant_passages": ["  "]}, "relevant_passages 必須是原文片段陣列"),
    ({"query": "q", "relevant_sources": [], "relevant_passages": ["片段"]}, "沒有 relevant_sources"),
])
def test_load_golden_set_validates_relevant_passages(tmp_path, record, message):
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_golden_set(str(golden))


def test_example_golden_set_is_valid():
    cases = load_golden_set(str(EVAL_DIR / "retrieval_golden.example.jsonl"))

    assert len(cases) == 4
    assert sum(1 for case in cases if not case.relevant_sources) == 1


def test_builtin_corpus_golden_set_matches_chunks_from_the_upload_pipeline():
    from app.api.documents import process_document_for_rag
    from app.core.limits import ADMIN_UPLOAD_EXTRACTION_LIMITS
    from app.rag.pipeline import RAGPipeline
    from app.services.document_processor import DocumentProcessor

    pipeline = RAGPipeline(retriever=None, chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP)
    chunks = {}
    for document_id, path in enumerate(sorted((EVAL_DIR / "corpus").iterdir()), start=1):
        extraction = DocumentProcessor.extract_document(str(path), "", ADMIN_UPLOAD_EXTRACTION_LIMITS, None)
        documents, _, _ = process_document_for_rag(extraction, {"source": path.name, "document_id": document_id}, pipeline)
        for piece in pipeline.split_documents(documents):
            chunks[len(chunks) + 1] = piece
    sources = {doc.metadata["source"] for doc in chunks.values()}

    cases = load_golden_set(str(EVAL_DIR / "corpus_golden.jsonl"))

    assert sum(1 for case in cases if case.relevant_passages) >= 100
    assert sum(1 for case in cases if not case.relevant_sources) >= 15
    for case in cases:
        assert set(case.relevant_sources) <= sources
        if case.relevant_passages:
            relevant = passage_relevant_chunk_ids(case, chunks)
            assert {chunks[chunk_id].metadata["source"] for chunk_id in relevant} == set(case.relevant_sources), case.query
