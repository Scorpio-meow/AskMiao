import json
import threading

import pytest

from app.core.config import settings
from app.core.domain_profile import domain_profile
from app.rag import tokenizers
from app.rag.indices.bm25_store import BM25StoreManager, SIGNATURE_FILENAME
from app.rag.retrievers.hybrid import HybridRetriever
from app.rag.tokenizers import configure_tokenizer, get_chinese_analyzer
from app.rag.types import Document


class ListVectorStore:
    """依固定順序回傳結果的向量庫替身"""
    device = "cpu"

    def __init__(self, documents):
        self.chunks = {doc.metadata["chunk_id"]: doc for doc in documents}
        self.lock = threading.RLock()

    @property
    def documents(self):
        return list(self.chunks.values())

    def search(self, query, top_k, apply_threshold):
        return [(doc, 1.0) for doc in self.documents[:top_k]]


class EmptyBM25:
    def search(self, query, chunks, top_k):
        return []


QUERY = "特休怎麼計算"
RELEVANT = Document(page_content="特休假依年資計算，滿半年享三天，滿一年享七天特休。", metadata={"chunk_id": 1, "source": "leave.txt"})
IRRELEVANT = Document(page_content="今天天氣晴朗，適合出門散步。", metadata={"chunk_id": 2, "source": "weather.txt"})


@pytest.fixture(scope="module")
def reranker():
    # 無關片段排在融合結果第一名：舊版門檻套在混合分數上，第一名一定拿到 0.15 而過門檻
    return HybridRetriever(
        vector_store=ListVectorStore([IRRELEVANT, RELEVANT]),
        bm25_store=EmptyBM25(),
        reranker_model=settings.RERANKER_MODEL,
        top_k=10,
        rrf_k=60,
        rerank_top_k=10,
        final_k=10,
        rerank_weight=0.85,
        relevance_threshold=0.15,
        use_fp16=False,
    )


@pytest.fixture
def profile_tokenizer():
    configure_tokenizer(None, domain_profile.domain_words)


def test_relevance_is_reranker_probability_without_second_sigmoid(reranker):
    probabilities = reranker.cross_encoder.predict(
        [(QUERY, RELEVANT.page_content), (QUERY, IRRELEVANT.page_content)]
    )

    relevance = {r.document.metadata["chunk_id"]: r.relevance for r in reranker.rank(QUERY)}

    assert relevance[1] == pytest.approx(float(probabilities[0]))
    assert relevance[2] == pytest.approx(float(probabilities[1]))
    assert relevance[2] < 0.15


def test_top_fused_candidate_is_dropped_when_reranker_judges_it_irrelevant(reranker):
    results = reranker.smart_search(QUERY)

    assert [r.document.metadata["chunk_id"] for r in results] == [1]


def test_off_topic_query_keeps_no_chunk(reranker):
    assert reranker.smart_search("推薦台北好吃的拉麵店") == []


def test_jieba_analyzer_drops_punctuation_tokens(profile_tokenizer):
    tokens = [token.text for token in get_chinese_analyzer()("特休怎麼申請？（含主管核准）")]

    assert tokens
    assert not {"？", "（", "）"} & set(tokens)


def test_jieba_analyzer_lowercases_tokens(profile_tokenizer):
    tokens = [token.text for token in get_chinese_analyzer()("MES 系統與 PAKKA 設定")]

    assert {"mes", "pakka"} <= set(tokens)
    assert not {"MES", "PAKKA"} & set(tokens)


def test_bm25_matches_natural_language_question(tmp_path, profile_tokenizer):
    store = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(tmp_path / "bm25"))
    chunks = {
        1: Document(page_content="特休假的申請需於系統填寫假單，經主管核准。", metadata={"source": "leave.txt"}),
        2: Document(page_content="加班費依勞動基準法計算。", metadata={"source": "overtime.txt"}),
    }
    store.add_documents(chunks)

    hits = store.search("特休怎麼申請？", chunks, top_k=5)

    assert [doc.metadata["source"] for doc, _ in hits] == ["leave.txt"]


def test_bm25_matching_ignores_case(tmp_path, profile_tokenizer):
    store = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(tmp_path / "bm25"))
    chunks = {
        1: Document(page_content="MES 系統的工時填寫說明", metadata={"source": "mes.txt"}),
        2: Document(page_content="加班費依勞動基準法計算。", metadata={"source": "overtime.txt"}),
    }
    store.add_documents(chunks)

    hits = store.search("mes", chunks, top_k=5)

    assert [doc.metadata["source"] for doc, _ in hits] == ["mes.txt"]


def test_bm25_rebuilds_when_tokenizer_signature_changes(tmp_path):
    index_dir = tmp_path / "bm25"
    chunks = {1: Document(page_content="MES 系統的工時填寫說明", metadata={"source": "mes.txt"})}
    configure_tokenizer(None, ["年資"])
    store = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(index_dir))
    store.add_documents(chunks)
    store.bm25_searcher.close()

    configure_tokenizer(None, ["年資", "工時填寫"])
    reopened = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(index_dir))
    assert not reopened.tokenizer_matches()

    reopened.ensure_aligned(chunks)

    assert reopened.tokenizer_matches()
    assert json.loads((index_dir / SIGNATURE_FILENAME).read_text(encoding="utf-8")) == tokenizers.tokenizer_signature()
    assert [doc.metadata["source"] for doc, _ in reopened.search("工時填寫", chunks, top_k=5)] == ["mes.txt"]


def test_bm25_index_without_signature_is_treated_as_stale(tmp_path, profile_tokenizer):
    index_dir = tmp_path / "bm25"
    chunks = {1: Document(page_content="MES 系統的工時填寫說明", metadata={"source": "mes.txt"})}
    store = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(index_dir))
    store.add_documents(chunks)
    store.bm25_searcher.close()
    (index_dir / SIGNATURE_FILENAME).unlink()

    reopened = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(index_dir))

    assert not reopened.tokenizer_matches()
