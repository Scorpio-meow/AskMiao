import pytest

from app.core.config import settings
from app.rag.indices.bm25_store import BM25StoreManager
from app.rag.retrievers.hybrid import HybridRetriever
from app.rag.tokenizers import get_chinese_analyzer, init_domain_dictionary
from app.rag.types import Document


class CpuVectorStore:
    device = "cpu"


QUERY = "特休怎麼計算"
RELEVANT = Document(page_content="特休假依年資計算，滿半年享三天，滿一年享七天特休。", metadata={})
IRRELEVANT = Document(page_content="今天天氣晴朗，適合出門散步。", metadata={})


@pytest.fixture(scope="module")
def reranker():
    retriever = HybridRetriever(
        vector_store=CpuVectorStore(),
        bm25_store=None,
        reranker_model=settings.RERANKER_MODEL,
        rerank_weight=1.0,
        final_threshold=0.0,
        final_k=10,
    )
    assert retriever.has_reranker
    return retriever


def test_rerank_does_not_apply_a_second_sigmoid(reranker):
    probabilities = reranker.cross_encoder.predict(
        [(QUERY, RELEVANT.page_content), (QUERY, IRRELEVANT.page_content)]
    )

    ranked = reranker.rerank_with_cross_encoder(QUERY, [(RELEVANT, 0.5), (IRRELEVANT, 0.5)])
    scores = {doc.page_content: score for doc, score in ranked}

    assert scores[RELEVANT.page_content] == pytest.approx(float(probabilities[0]))
    assert scores[IRRELEVANT.page_content] == pytest.approx(float(probabilities[1]))
    assert scores[IRRELEVANT.page_content] < 0.5


def test_final_threshold_filters_irrelevant_chunk(reranker, monkeypatch):
    monkeypatch.setattr(reranker, "rerank_weight", 0.85)
    monkeypatch.setattr(reranker, "final_threshold", 0.15)

    ranked = reranker.rerank_with_cross_encoder(QUERY, [(RELEVANT, 0.9), (IRRELEVANT, 0.2)])

    assert [doc.page_content for doc, _ in ranked] == [RELEVANT.page_content]


def test_jieba_analyzer_drops_punctuation_tokens():
    tokens = [token.text for token in get_chinese_analyzer()("特休怎麼申請？（含主管核准）")]

    assert tokens
    assert not {"？", "（", "）"} & set(tokens)


def test_bm25_matches_natural_language_question(tmp_path):
    init_domain_dictionary(str(tmp_path))
    store = BM25StoreManager(data_dir=str(tmp_path), bm25_index_dir=str(tmp_path / "bm25"))
    chunks = {
        1: Document(page_content="特休假的申請需於系統填寫假單，經主管核准。", metadata={"source": "leave.txt"}),
        2: Document(page_content="加班費依勞動基準法計算。", metadata={"source": "overtime.txt"}),
    }
    store.add_documents(chunks)

    hits = store.search("特休怎麼申請？", chunks, top_k=5)

    assert [doc.metadata["source"] for doc, _ in hits] == ["leave.txt"]
