import os
import threading
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from app.rag.retrievers import hybrid as hybrid_module
from app.rag.retrievers.hybrid import HybridRetriever, reciprocal_rank_fusion
from app.rag.tools import ResearchToolRegistry
from app.rag.types import Document


def chunk(chunk_id, content, source="handbook.txt"):
    return Document(page_content=content, metadata={"chunk_id": chunk_id, "source": source, "chunk_index": 0})


class FakeCrossEncoder:
    """依片段內容回傳指定機率的重排模型替身"""
    activation_fn = torch.nn.Sigmoid()

    def __init__(self, relevance_by_content, default_relevance):
        self.relevance_by_content = relevance_by_content
        self.default_relevance = default_relevance
        self.predicted_pairs = 0

    def predict(self, pairs):
        self.predicted_pairs += len(pairs)
        return [self.relevance_by_content.get(text, self.default_relevance) for _, text in pairs]


class FailingCrossEncoder(FakeCrossEncoder):
    def predict(self, pairs):
        raise RuntimeError("reranker crashed")


class RankedVectorStore:
    device = "cpu"

    def __init__(self, documents, vector_ranking):
        self.chunks = {doc.metadata["chunk_id"]: doc for doc in documents}
        self.vector_ranking = vector_ranking
        self.lock = threading.RLock()

    @property
    def documents(self):
        return list(self.chunks.values())

    def embed_query(self, query):
        return query

    def search(self, query_embedding, top_k, apply_threshold, chunk_ids=None):
        ranking = [doc for doc in self.vector_ranking if chunk_ids is None or doc.metadata["chunk_id"] in chunk_ids]
        return [(doc, 1.0 / rank) for rank, doc in enumerate(ranking[:top_k], start=1)]


class RankedBM25:
    def __init__(self, bm25_ranking):
        self.bm25_ranking = bm25_ranking

    def search(self, query, chunks, top_k, chunk_ids=None):
        ranking = [doc for doc in self.bm25_ranking if chunk_ids is None or doc.metadata["chunk_id"] in chunk_ids]
        return [(doc, 10.0 / rank) for rank, doc in enumerate(ranking[:top_k], start=1)]


def make_retriever(monkeypatch, documents, vector_ranking, bm25_ranking, encoder, **overrides):
    monkeypatch.setattr(hybrid_module, "CrossEncoder", lambda model_name, device=None: encoder)
    options = dict(
        top_k=30, rrf_k=60, rerank_top_k=20, final_k=8, rerank_weight=0.85, relevance_threshold=0.5, use_fp16=False,
        openvino_device=None, openvino_max_length=None,
    )
    options.update(overrides)
    return HybridRetriever(
        vector_store=RankedVectorStore(documents, vector_ranking),
        bm25_store=RankedBM25(bm25_ranking),
        reranker_model="fake-reranker",
        **options,
    )


def test_rrf_scores_by_rank_across_both_tracks():
    a, b, c = chunk(1, "a"), chunk(2, "b"), chunk(3, "c")

    fused = reciprocal_rank_fusion([[(a, 0.9), (b, 0.8)], [(b, 12.0), (c, 3.0)]], rrf_k=60)

    assert [doc.metadata["chunk_id"] for doc, _ in fused] == [2, 1, 3]
    assert fused[0][1] == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1][1] == pytest.approx(1 / 61)


def test_chunk_found_only_by_bm25_reaches_rerank_candidates(monkeypatch):
    vector_only = [chunk(i, f"向量片段 {i}") for i in range(1, 31)]
    bm25_only = chunk(99, "只有關鍵字找得到的 MES 片段")
    retriever = make_retriever(
        monkeypatch, vector_only + [bm25_only], vector_only, [bm25_only],
        FakeCrossEncoder({bm25_only.page_content: 0.95}, default_relevance=0.1),
    )

    candidates = [doc.metadata["chunk_id"] for doc, _ in retriever.hybrid_search("MES", "MES")]
    results = retriever.smart_search("MES")

    assert 99 in candidates
    assert [r.document.metadata["chunk_id"] for r in results] == [99]


@pytest.mark.asyncio
async def test_off_topic_query_reports_no_data_even_for_top_candidate(monkeypatch):
    docs = [chunk(1, "特休依年資計算"), chunk(2, "加班需主管核准")]
    # 第一名的混合分數 0.85 × 0.05 + 0.15 × 1.0 = 0.19，舊版門檻 0.15 會放行
    retriever = make_retriever(
        monkeypatch, docs, docs, docs, FakeCrossEncoder({}, default_relevance=0.05), relevance_threshold=0.15,
    )

    result = await ResearchToolRegistry(retriever=retriever).search_knowledge_base("推薦拉麵店")

    assert result["documents"] == []
    assert result["message"] == "知識庫中查無相關資料"


def test_exact_url_match_is_exempt_from_relevance_threshold(monkeypatch):
    url = "https://www.threads.net/@example_user/post/ABC123"
    post = chunk(5, f"作者: @example_user\n連結: {url}\n內容: 週末活動心得", source="posts.json")
    other = chunk(6, "特休依年資計算")
    retriever = make_retriever(monkeypatch, [post, other], [other], [other], FakeCrossEncoder({}, default_relevance=0.01))

    results = retriever.smart_search(url)

    assert [r.document.metadata["chunk_id"] for r in results] == [5]
    assert results[0].pinned


@pytest.mark.asyncio
async def test_target_document_is_filtered_before_ranking_without_falling_back(monkeypatch):
    a1, a2 = chunk(1, "特休規定一", source="a.txt"), chunk(2, "特休規定二", source="a.txt")
    b1 = chunk(3, "特休規定三", source="b.txt")
    retriever = make_retriever(
        monkeypatch, [a1, a2, b1], [a1, a2, b1], [], FakeCrossEncoder({}, default_relevance=0.9), final_k=1,
    )
    registry = ResearchToolRegistry(retriever=retriever)

    in_document = await registry.search_knowledge_base("特休", target_document="b.txt")
    missing_document = await registry.search_knowledge_base("特休", target_document="c.txt")

    assert [d["chunk_id"] for d in in_document["documents"]] == [3]
    assert missing_document["documents"] == []
    assert missing_document["message"] == "指定文件《c.txt》中查無相關資料"


@pytest.mark.asyncio
async def test_rerank_failure_returns_error_code_instead_of_unfiltered_chunks(monkeypatch):
    docs = [chunk(1, "特休依年資計算")]
    retriever = make_retriever(monkeypatch, docs, docs, docs, FailingCrossEncoder({}, default_relevance=0.9))

    result = await ResearchToolRegistry(retriever=retriever).search_knowledge_base("特休")

    assert result["documents"] == []
    assert "錯誤代碼" in result["error"]


def test_reranker_load_failure_stops_startup(monkeypatch):
    def unavailable(model_name, device=None):
        raise OSError("model files not found")

    monkeypatch.setattr(hybrid_module, "CrossEncoder", unavailable)

    with pytest.raises(RuntimeError, match="重排模型"):
        HybridRetriever(
            vector_store=RankedVectorStore([], []), bm25_store=RankedBM25([]), reranker_model="missing-reranker",
            top_k=30, rrf_k=60, rerank_top_k=20, final_k=8, rerank_weight=0.85, relevance_threshold=0.5, use_fp16=False,
            openvino_device=None, openvino_max_length=None,
        )


def test_exact_match_candidates_are_capped_and_reranked_outside_the_index_lock(monkeypatch):
    posts = [chunk(i, f"日期: 2026-08-01 第 {i} 則貼文", source="posts.json") for i in range(1, 201)]

    class LockCheckingEncoder(FakeCrossEncoder):
        def predict(self, pairs):
            # 重排時不應持有索引鎖：另一個執行緒要能立即取得
            acquired = []

            def try_lock():
                lock = retriever.vector_store.lock
                got = lock.acquire(timeout=1)
                acquired.append(got)
                if got:
                    lock.release()

            worker = threading.Thread(target=try_lock)
            worker.start()
            worker.join()
            self.lock_free = acquired[0]
            return super().predict(pairs)

    encoder = LockCheckingEncoder({}, default_relevance=0.9)
    retriever = make_retriever(monkeypatch, posts, [], [], encoder, rerank_top_k=20)

    retriever.rank("2026-08-01 有哪些貼文")

    assert encoder.predicted_pairs == 20
    assert encoder.lock_free is True


class FakeTokenizer:
    model_max_length = 16

    def __call__(self, queries, documents, padding, truncation, max_length, return_tensors):
        assert (padding, truncation) == ("max_length", True)
        ids = np.array([[ord(d[0]) if d else 0] * max_length for d in documents])
        return {"input_ids": ids, "attention_mask": np.ones_like(ids)}


def make_openvino_retriever(monkeypatch, documents, compiled, *, rerank_top_k, openvino_max_length):
    def pytorch_reranker(model_name, device=None):
        raise AssertionError("OpenVINO 模式不應載入 PyTorch 重排模型")

    monkeypatch.setattr(hybrid_module, "CrossEncoder", pytorch_reranker)
    monkeypatch.setattr(hybrid_module, "AutoTokenizer", SimpleNamespace(from_pretrained=lambda model_name: FakeTokenizer()))
    monkeypatch.setattr(HybridRetriever, "_compile_openvino_reranker", lambda self, model, device: compiled)
    return HybridRetriever(
        vector_store=RankedVectorStore(documents, documents), bm25_store=RankedBM25([]), reranker_model="fake-reranker",
        top_k=30, rrf_k=60, rerank_top_k=rerank_top_k, final_k=8, rerank_weight=0.85, relevance_threshold=0.5,
        use_fp16=False, openvino_device="GPU", openvino_max_length=openvino_max_length,
    )


def test_openvino_reranker_sends_only_real_pairs_and_applies_sigmoid(monkeypatch):
    texts = {"a": 2.0, "b": -2.0, "c": 0.0}
    seen_shapes = []

    def fake_compiled(feed):
        seen_shapes.append(feed["input_ids"].shape)
        return [np.array([[texts[chr(row[0])]] for row in feed["input_ids"]])]

    docs = [chunk(1, "a"), chunk(2, "b"), chunk(3, "c")]
    retriever = make_openvino_retriever(monkeypatch, docs, fake_compiled, rerank_top_k=2, openvino_max_length=8)

    scores = retriever._relevance("q", docs)

    assert seen_shapes == [(2, 8), (1, 8)]
    assert scores == pytest.approx([1 / (1 + np.exp(-2.0)), 1 / (1 + np.exp(2.0)), 0.5])
    assert retriever.cross_encoder is None


def test_openvino_reranker_requires_max_length(monkeypatch):
    with pytest.raises(RuntimeError, match="RERANKER_OPENVINO_MAX_LENGTH"):
        make_retriever(monkeypatch, [], [], [], FakeCrossEncoder({}, 0.0), openvino_device="GPU", openvino_max_length=None)


def test_openvino_max_length_cannot_exceed_model_limit(monkeypatch):
    with pytest.raises(RuntimeError, match="RERANKER_OPENVINO_MAX_LENGTH \\(17\\)"):
        make_openvino_retriever(monkeypatch, [], None, rerank_top_k=2, openvino_max_length=FakeTokenizer.model_max_length + 1)


def test_openvino_ir_name_follows_model_files(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    weights = tmp_path / "model.safetensors"
    weights.write_bytes(b"v1")
    before = HybridRetriever._reranker_fingerprint(str(tmp_path))

    weights.write_bytes(b"v2 weights")

    assert HybridRetriever._reranker_fingerprint(str(tmp_path)) != before


def test_interrupted_openvino_conversion_leaves_no_ir(monkeypatch, tmp_path):
    import openvino
    import transformers

    retriever = make_openvino_retriever(monkeypatch, [], None, rerank_top_k=2, openvino_max_length=8)
    monkeypatch.setattr(transformers.AutoModelForSequenceClassification, "from_pretrained", lambda model_name: object())
    monkeypatch.setattr(openvino, "convert_model", lambda model, example_input: "converted")
    model_path = tmp_path / "reranker.xml"

    def interrupted_save(model, path):
        (tmp_path / os.path.basename(path)).write_text("<partial", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr(openvino, "save_model", interrupted_save)
    with pytest.raises(OSError, match="disk full"):
        retriever._convert_openvino_reranker("fake-reranker", str(model_path))
    assert not model_path.exists()

    def complete_save(model, path):
        stem = os.path.splitext(path)[0]
        open(f"{stem}.xml", "w", encoding="utf-8").write("<net/>")
        open(f"{stem}.bin", "wb").write(b"weights")

    monkeypatch.setattr(openvino, "save_model", complete_save)
    retriever._convert_openvino_reranker("fake-reranker", str(model_path))
    assert model_path.read_text(encoding="utf-8") == "<net/>"
    assert (tmp_path / "reranker.bin").read_bytes() == b"weights"
