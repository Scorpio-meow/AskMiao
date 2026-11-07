import json
import threading
import pytest
from app.core.config import settings
from app.core.domain_profile import domain_profile
from app.rag import tokenizers
from app.rag.indices import bm25_store as bm25_store_module
from app.rag.indices.bm25_store import BM25StoreManager, SIGNATURE_FILENAME
from app.rag.retrievers.hybrid import HybridRetriever
from app.rag.tokenizers import configure_tokenizer, get_chinese_analyzer, get_han_ngram_analyzer
from app.rag.types import Document
class ListVectorStore:
    device = "cpu"
    def __init__(self, documents):
        self.chunks = {doc.metadata["chunk_id"]: doc for doc in documents}
        self.lock = threading.RLock()
    @property
    def documents(self):
        return list(self.chunks.values())
    def embed_query(self, query):
        return query
    def search(self, query_embedding, top_k, apply_threshold, chunk_ids=None):
        return [(doc, 1.0) for doc in self.documents[:top_k]]
class EmptyBM25:
    def search(self, query, chunks, top_k, chunk_ids=None):
        return []
QUERY = "特休怎麼計算"
RELEVANT = Document(page_content="特休假依年資計算，滿半年享三天，滿一年享七天特休。", metadata={"chunk_id": 1, "source": "leave.txt"})
IRRELEVANT = Document(page_content="今天天氣晴朗，適合出門散步。", metadata={"chunk_id": 2, "source": "weather.txt"})
@pytest.fixture(scope="module")
def reranker():
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
        openvino_device=None,
        openvino_max_length=None,
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
@pytest.mark.parametrize("size, expected", [
    (1, ["系", "統", "設", "定", "字"]),
    (2, ["系統", "設定"]),
])
def test_han_ngram_analyzer_emits_ngrams_within_runs_of_han_characters(size, expected):
    tokens = [token.text for token in get_han_ngram_analyzer(size)("MES 系統（v2）設定，OK！A字B")]
    assert tokens == expected
def test_bm25_matches_traditional_text_that_jieba_segments_differently(tmp_path, profile_tokenizer):
    content = "於大眾捷運系統禁止飲食區內飲食"
    query = "捷運上可以吃東西嗎"
    words = get_chinese_analyzer()
    assert not {t.text for t in words(query, mode="query")} & {t.text for t in words(content)}
    store = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(tmp_path / "bm25"))
    chunks = {
        1: Document(page_content=content, metadata={"source": "mrt.txt"}),
        2: Document(page_content="加班費依勞動基準法計算。", metadata={"source": "overtime.txt"}),
    }
    store.add_documents(chunks)
    hits = store.search(query, chunks, top_k=5)
    assert [doc.metadata["source"] for doc, _ in hits] == ["mrt.txt"]
def test_bm25_ranks_adjacent_characters_above_scattered_ones(tmp_path, profile_tokenizer):
    store = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(tmp_path / "bm25"))
    chunks = {
        1: Document(page_content="上海車站旁邊新開的店", metadata={"source": "scattered.txt"}),
        2: Document(page_content="週末去海邊散步", metadata={"source": "adjacent.txt"}),
    }
    store.add_documents(chunks)
    hits = store.search("海邊", chunks, top_k=5)
    assert [doc.metadata["source"] for doc, _ in hits] == ["adjacent.txt", "scattered.txt"]
def test_bm25_index_built_with_previous_rules_version_is_stale(tmp_path, profile_tokenizer):
    index_dir = tmp_path / "bm25"
    chunks = {1: Document(page_content="MES 系統的工時填寫說明", metadata={"source": "mes.txt"})}
    store = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(index_dir))
    store.add_documents(chunks)
    store.bm25_searcher.close()
    previous = {**tokenizers.tokenizer_signature(), "rules_version": tokenizers.TOKENIZER_RULES_VERSION - 1}
    (index_dir / SIGNATURE_FILENAME).write_text(json.dumps(previous), encoding="utf-8")
    reopened = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(index_dir))
    assert not reopened.tokenizer_matches()
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
def test_bm25_search_is_limited_to_given_chunk_ids(tmp_path, profile_tokenizer):
    store = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(tmp_path / "bm25"))
    chunks = {
        1: Document(page_content="MES 系統的 MES 工時填寫說明", metadata={"source": "mes.txt"}),
        2: Document(page_content="MES 報表匯出", metadata={"source": "report.txt"}),
    }
    store.add_documents(chunks)
    assert [doc.metadata["source"] for doc, _ in store.search("mes", chunks, top_k=1, chunk_ids=[2])] == ["report.txt"]
    assert store.search("mes", chunks, top_k=5, chunk_ids=[]) == []
def test_bm25_write_failure_is_raised_after_retries(tmp_path, profile_tokenizer, monkeypatch):
    store = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(tmp_path / "bm25"))
    chunks = {1: Document(page_content="MES 系統的工時填寫說明", metadata={"source": "mes.txt"})}
    store.add_documents(chunks)
    attempts = []
    def locked_writer(index):
        attempts.append(index)
        raise OSError("index is locked")
    monkeypatch.setattr(bm25_store_module, "AsyncWriter", locked_writer)
    monkeypatch.setattr(bm25_store_module.time, "sleep", lambda seconds: None)
    with pytest.raises(OSError, match="index is locked"):
        store.delete_ids([1])
    assert len(attempts) == bm25_store_module.WRITE_ATTEMPTS
    assert [doc.metadata["source"] for doc, _ in store.search("mes", chunks, top_k=5)] == ["mes.txt"]