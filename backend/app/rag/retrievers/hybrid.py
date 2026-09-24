from dataclasses import dataclass
from typing import Callable, Iterable, List, Tuple, Dict, Optional, Sequence
import re
import time
import logging
import numpy as np
from ..types import Document
from ..indices.vector_store import VectorStoreManager
from ..indices.bm25_store import BM25StoreManager

logger = logging.getLogger(__name__)

CrossEncoder = None

URL_MATCH_SCORE = 1.0
POST_ID_MATCH_SCORE = 0.98
DATE_MATCH_SCORE = 0.98
USER_MATCH_SCORE = 0.90
# 精確比對分數達此值者（網址、貼文 ID、日期）排在最前面，且不受相關性門檻限制
PINNED_MATCH_SCORE = 0.95


@dataclass(frozen=True)
class RetrievedChunk:
    document: Document
    # 排序用的混合分數：RERANK_WEIGHT × 重排機率 + (1 − RERANK_WEIGHT) × 候選原分數
    score: float
    # 重排模型判定的相關機率，相關性門檻只看這個值
    relevance: float
    # 精確比對到網址、貼文 ID 或日期
    pinned: bool


def matches_target_document(doc: Document, target_document: str) -> bool:
    target = target_document.strip().lower()
    return (
        target in (doc.metadata.get("source", "")).lower()
        or target in (doc.metadata.get("original_filename", "")).lower()
    )


def reciprocal_rank_fusion(
    ranked_lists: Sequence[List[Tuple[Document, float]]], rrf_k: int
) -> List[Tuple[Document, float]]:
    """依各軌名次融合：分數 = Σ 1 / (rrf_k + 名次)，名次從 1 起算，以 chunk_id 辨識同一片段"""
    fused: Dict[int, List] = {}
    for ranked in ranked_lists:
        for rank, (doc, _) in enumerate(ranked, start=1):
            entry = fused.setdefault(doc.metadata["chunk_id"], [doc, 0.0])
            entry[1] += 1.0 / (rrf_k + rank)
    return sorted(((doc, score) for doc, score in fused.values()), key=lambda x: x[1], reverse=True)


def _query_dates(query: str) -> List[str]:
    target_dates = []
    for m in re.finditer(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', query):
        y, mth, d = m.group(1), int(m.group(2)), int(m.group(3))
        target_dates.extend([f"{y}-{mth:02d}-{d:02d}", f"{y}年{mth}月{d}日", f"{y}年{mth:02d}月{d:02d}日"])
    for m in re.finditer(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', query):
        y, mth, d = m.group(1), int(m.group(2)), int(m.group(3))
        target_dates.extend([f"{y}-{mth:02d}-{d:02d}", f"{y}年{mth}月{d}日", f"{y}年{mth:02d}月{d:02d}日"])
    return list(set(target_dates))


def find_exact_matches(query: str, documents: Iterable[Document]) -> List[Tuple[Document, float]]:
    """查詢中的網址、貼文 ID、日期與 @帳號，以原文比對片段內容；查詢沒有這些目標時不掃描片段"""
    url_match = re.search(r'https?://[^\s"\'<>]+', query)
    id_match = re.search(r'/post/([A-Za-z0-9_-]+)', query)
    user_match = re.search(r'@[A-Za-z0-9_.-]+', query)
    target_dates = _query_dates(query)
    target_url = url_match.group(0).rstrip('/>"\'') if url_match else None
    target_id = id_match.group(1) if id_match else None
    target_user = user_match.group(0) if user_match else None
    if not (target_url or target_id or target_user or target_dates):
        return []

    matches: List[Tuple[Document, float]] = []
    for doc in documents:
        c = doc.page_content
        c_lower = c.lower()
        if target_url and target_url.lower() in c_lower:
            matches.append((doc, URL_MATCH_SCORE))
        elif target_id and target_id in c:
            matches.append((doc, POST_ID_MATCH_SCORE))
        elif target_dates and any(td in c for td in target_dates):
            matches.append((doc, DATE_MATCH_SCORE))
        elif target_user and target_user.lower() in c_lower:
            matches.append((doc, USER_MATCH_SCORE))
    return matches


class HybridRetriever:
    def __init__(
        self,
        vector_store: VectorStoreManager,
        bm25_store: BM25StoreManager,
        *,
        reranker_model: str,
        top_k: int,
        rrf_k: int,
        rerank_top_k: int,
        final_k: int,
        rerank_weight: float,
        relevance_threshold: float,
        use_fp16: bool,
    ):
        self.vector_store = vector_store
        self.bm25_store = bm25_store
        self.top_k = top_k
        self.rrf_k = rrf_k
        self.rerank_top_k = rerank_top_k
        self.final_k = final_k
        self.rerank_weight = rerank_weight
        self.relevance_threshold = relevance_threshold

        global CrossEncoder
        try:
            if CrossEncoder is None:
                from sentence_transformers import CrossEncoder as _CE
                CrossEncoder = _CE
            self.cross_encoder = CrossEncoder(reranker_model, device=self.vector_store.device)
        except Exception as e:
            raise RuntimeError(
                f"無法載入重排模型 ({reranker_model})：{e}。重排模型是必要元件，請檢查 RERANKER_MODEL 設定、模型快取或網路連線"
            ) from e

        if use_fp16 and self.vector_store.device == "cuda":
            try:
                self.cross_encoder.model = self.cross_encoder.model.half()
                logger.info("Cross-Encoder 已量化為 FP16")
            except Exception as e:
                logger.warning(f"Cross-Encoder FP16 量化失敗: {e}")

        import torch
        activation_fn = getattr(self.cross_encoder, "activation_fn", None)
        if activation_fn is None:
            activation_fn = getattr(self.cross_encoder, "default_activation_function", None)
        self.reranker_outputs_probability = isinstance(activation_fn, torch.nn.Sigmoid)
        logger.info(f"Cross-Encoder 已載入至 {self.vector_store.device.upper()}: {reranker_model} (精度: {'FP16' if use_fp16 else 'FP32'})")

    def hybrid_search(
        self, query: str, allowed: Optional[Callable[[Document], bool]] = None
    ) -> List[Tuple[Document, float]]:
        """兩軌必跑：向量與 BM25 各取 TOP_K 筆，以 RRF 融合後取前 RERANK_TOP_K 筆（呼叫端須持有 vector_store.lock）"""
        vector_results = self.vector_store.search(query, self.top_k, apply_threshold=False)
        bm25_results = self.bm25_store.search(query, self.vector_store.chunks, self.top_k)
        fused = reciprocal_rank_fusion([vector_results, bm25_results], self.rrf_k)
        if allowed is not None:
            fused = [(doc, score) for doc, score in fused if allowed(doc)]
        return fused[: self.rerank_top_k]

    def _relevance(self, query: str, documents: List[Document]) -> List[float]:
        scores = np.asarray(self.cross_encoder.predict([(query, doc.page_content) for doc in documents]), dtype=float)
        if not self.reranker_outputs_probability:
            scores = 1.0 / (1.0 + np.exp(-np.clip(scores, -20.0, 20.0)))
        return scores.tolist()

    def rank(self, query: str, target_document: Optional[str] = None) -> List[RetrievedChunk]:
        """融合並重排後的全部候選，未套用相關性門檻、未截斷；重排失敗時直接拋出例外"""
        with self.vector_store.lock:
            allowed = (lambda doc: matches_target_document(doc, target_document)) if target_document else None
            exact = find_exact_matches(
                query, (doc for doc in self.vector_store.chunks.values() if allowed is None or allowed(doc))
            )
            fused = self.hybrid_search(query, allowed)

            exact_ids = {doc.metadata["chunk_id"] for doc, _ in exact}
            fused = [(doc, score) for doc, score in fused if doc.metadata["chunk_id"] not in exact_ids]
            max_fused = max((score for _, score in fused), default=0.0)
            # 精確比對以其比對分數、融合結果以 RRF 分數 / 最高分作為候選原分數，兩者同在 0~1
            candidates = [(doc, score, score >= PINNED_MATCH_SCORE) for doc, score in exact]
            candidates += [(doc, score / max_fused, False) for doc, score in fused]
            if not candidates:
                return []

            started = time.time()
            relevances = self._relevance(query, [doc for doc, _, _ in candidates])
            w = min(max(self.rerank_weight, 0.0), 1.0)
            ranked = [
                RetrievedChunk(document=doc, score=float(w * rel + (1 - w) * base), relevance=float(rel), pinned=pinned)
                for (doc, base, pinned), rel in zip(candidates, relevances)
            ]
            ranked.sort(key=lambda r: (r.pinned, r.score), reverse=True)
            logger.info(
                f"Retrieval query='{query}' exact={len(exact)} fused={len(fused)} "
                f"reranked={len(ranked)} in {time.time() - started:.2f}s"
            )
            return ranked

    def select(self, ranked: List[RetrievedChunk], relevance_threshold: float) -> List[RetrievedChunk]:
        """套用相關性門檻（精確比對到網址、貼文 ID、日期者不受限制），取前 FINAL_K 筆"""
        return [r for r in ranked if r.pinned or r.relevance >= relevance_threshold][: self.final_k]

    def smart_search(self, query: str, target_document: Optional[str] = None) -> List[RetrievedChunk]:
        return self.select(self.rank(query, target_document), self.relevance_threshold)
