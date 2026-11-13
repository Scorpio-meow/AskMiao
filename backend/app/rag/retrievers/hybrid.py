from dataclasses import dataclass
from typing import Iterable, List, Tuple, Dict, Optional, Sequence
import hashlib
import os
import re
import threading
import time
import logging
import numpy as np
from ..types import Document
from ..indices.vector_store import VectorStoreManager
from ..indices.bm25_store import BM25StoreManager
logger = logging.getLogger(__name__)
CrossEncoder = None
AutoTokenizer = None
URL_MATCH_SCORE = 1.0
POST_ID_MATCH_SCORE = 0.98
DATE_MATCH_SCORE = 0.98
USER_MATCH_SCORE = 0.90
PINNED_MATCH_SCORE = 0.95
@dataclass(frozen=True)
class RetrievedChunk:
    document: Document
    score: float
    relevance: float
    pinned: bool
def is_text_chunk(doc: Document) -> bool:
    metadata = doc.metadata
    return (
        isinstance(metadata.get("document_id"), int)
        and isinstance(metadata.get("chunk_index"), int)
        and not metadata.get("preserve_whole")
        and "record_index" not in metadata
        and "qa_index" not in metadata
    )
def overlap_length(head: str, tail: str) -> int:
    for size in range(min(len(head), len(tail)), 0, -1):
        if head.endswith(tail[:size]):
            return size
    return 0
def matches_target_document(doc: Document, target_document: str) -> bool:
    target = target_document.strip().lower()
    return (
        target in (doc.metadata.get("source", "")).lower()
        or target in (doc.metadata.get("original_filename", "")).lower()
    )
def reciprocal_rank_fusion(
    ranked_lists: Sequence[List[Tuple[Document, float]]], rrf_k: int
) -> List[Tuple[Document, float]]:
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
        openvino_device: Optional[str],
        openvino_max_length: Optional[int],
    ):
        self.vector_store = vector_store
        self.bm25_store = bm25_store
        self.top_k = top_k
        self.rrf_k = rrf_k
        self.rerank_top_k = rerank_top_k
        self._rerank_lock = threading.Lock()
        self.final_k = final_k
        self.rerank_weight = rerank_weight
        self.relevance_threshold = relevance_threshold
        self.cross_encoder = None
        self.openvino_reranker = None
        if openvino_device:
            if openvino_max_length is None:
                raise RuntimeError("設定 RERANKER_OPENVINO_DEVICE 時必須同時設定 RERANKER_OPENVINO_MAX_LENGTH")
            self.reranker_tokenizer = self._load_reranker_tokenizer(reranker_model)
            if openvino_max_length > self.reranker_tokenizer.model_max_length:
                raise RuntimeError(
                    f"RERANKER_OPENVINO_MAX_LENGTH ({openvino_max_length}) 超過重排模型 {reranker_model} "
                    f"可接受的最大長度 {self.reranker_tokenizer.model_max_length}"
                )
            self.openvino_batch_size = rerank_top_k
            self.openvino_max_length = openvino_max_length
            started = time.time()
            self.openvino_reranker = self._compile_openvino_reranker(reranker_model, openvino_device)
            logger.info(
                f"Cross-Encoder 已以 OpenVINO 編譯至 {openvino_device}: 批次 1~{self.openvino_batch_size}、"
                f"長度 {self.openvino_max_length}，耗時 {time.time() - started:.1f}s"
            )
        else:
            self._load_cross_encoder(reranker_model, use_fp16)
    def _load_cross_encoder(self, reranker_model: str, use_fp16: bool) -> None:
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
    def _load_reranker_tokenizer(self, reranker_model: str):
        global AutoTokenizer
        try:
            if AutoTokenizer is None:
                from transformers import AutoTokenizer as _AT
                AutoTokenizer = _AT
            return AutoTokenizer.from_pretrained(reranker_model)
        except Exception as e:
            raise RuntimeError(
                f"無法載入重排模型 ({reranker_model}) 的 tokenizer：{e}。重排模型是必要元件，請檢查 RERANKER_MODEL 設定、模型快取或網路連線"
            ) from e
    @staticmethod
    def _reranker_fingerprint(reranker_model: str) -> str:
        from transformers.utils import cached_file
        model_dir = os.path.dirname(cached_file(reranker_model, "config.json"))
        files = sorted(
            (entry.name, entry.stat().st_size, entry.stat().st_mtime_ns)
            for entry in os.scandir(model_dir) if entry.is_file()
        )
        return hashlib.sha256(repr(files).encode()).hexdigest()[:16]
    def _compile_openvino_reranker(self, reranker_model: str, device: str):
        import openvino as ov
        cache_dir = os.path.join(self.vector_store.data_dir, "openvino_cache")
        os.makedirs(cache_dir, exist_ok=True)
        model_path = os.path.join(
            cache_dir, f"{re.sub(r'[^\w.-]', '_', reranker_model)}_{self._reranker_fingerprint(reranker_model)}.xml"
        )
        if not os.path.exists(model_path):
            self._convert_openvino_reranker(reranker_model, model_path)
        core = ov.Core()
        core.set_property({"CACHE_DIR": cache_dir})
        model = core.read_model(model_path)
        shape = ov.PartialShape([ov.Dimension(1, self.openvino_batch_size), self.openvino_max_length])
        model.reshape({model_input.get_any_name(): shape for model_input in model.inputs})
        return core.compile_model(model, device)
    def _convert_openvino_reranker(self, reranker_model: str, model_path: str) -> None:
        import openvino as ov
        from transformers import AutoModelForSequenceClassification
        model = AutoModelForSequenceClassification.from_pretrained(reranker_model)
        example = self._tokenize([("", "")] * 2, "pt")
        converted = ov.convert_model(model, example_input=dict(example))
        stem = os.path.splitext(model_path)[0]
        temp_stem = f"{stem}.{os.getpid()}.tmp"
        ov.save_model(converted, f"{temp_stem}.xml")
        os.replace(f"{temp_stem}.bin", f"{stem}.bin")
        os.replace(f"{temp_stem}.xml", model_path)
    def _tokenize(self, pairs: Sequence[Tuple[str, str]], tensor_type: str):
        return self.reranker_tokenizer(
            [query for query, _ in pairs],
            [text for _, text in pairs],
            padding="max_length",
            truncation=True,
            max_length=self.openvino_max_length,
            return_tensors=tensor_type,
        )
    def _openvino_logits(self, pairs: List[Tuple[str, str]]) -> List[float]:
        logits: List[float] = []
        for start in range(0, len(pairs), self.openvino_batch_size):
            encoded = self._tokenize(pairs[start:start + self.openvino_batch_size], "np")
            output = self.openvino_reranker(dict(encoded))[0]
            logits.extend(np.asarray(output, dtype=float).reshape(-1).tolist())
        return logits
    def hybrid_search(
        self, query: str, query_embedding: np.ndarray, chunk_ids: Optional[List[int]] = None
    ) -> List[Tuple[Document, float]]:
        vector_results = self.vector_store.search(query_embedding, self.top_k, apply_threshold=False, chunk_ids=chunk_ids)
        bm25_results = self.bm25_store.search(query, self.vector_store.chunks, self.top_k, chunk_ids=chunk_ids)
        fused = reciprocal_rank_fusion([vector_results, bm25_results], self.rrf_k)
        return fused[: self.rerank_top_k]
    def _relevance(self, query: str, documents: List[Document]) -> List[float]:
        pairs = [(query, doc.page_content) for doc in documents]
        with self._rerank_lock:
            if self.openvino_reranker is None:
                predicted = self.cross_encoder.predict(pairs)
            else:
                predicted = self._openvino_logits(pairs)
        scores = np.asarray(predicted, dtype=float)
        if self.openvino_reranker is not None or not self.reranker_outputs_probability:
            scores = 1.0 / (1.0 + np.exp(-np.clip(scores, -20.0, 20.0)))
        return scores.tolist()
    def rank(self, query: str, target_document: Optional[str] = None) -> List[RetrievedChunk]:
        query_embedding = self.vector_store.embed_query(query)
        with self.vector_store.lock:
            chunk_ids = None
            if target_document:
                chunk_ids = [
                    chunk_id for chunk_id, doc in self.vector_store.chunks.items()
                    if matches_target_document(doc, target_document)
                ]
            exact = find_exact_matches(
                query,
                self.vector_store.chunks.values() if chunk_ids is None
                else (self.vector_store.chunks[chunk_id] for chunk_id in chunk_ids)
            )
            exact = sorted(exact, key=lambda item: item[1], reverse=True)[: self.rerank_top_k]
            fused = self.hybrid_search(query, query_embedding, chunk_ids)
            exact_ids = {doc.metadata["chunk_id"] for doc, _ in exact}
            fused = [(doc, score) for doc, score in fused if doc.metadata["chunk_id"] not in exact_ids]
            max_fused = max((score for _, score in fused), default=0.0)
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
            f"Retrieval query_chars={len(query)} exact={len(exact)} fused={len(fused)} "
            f"reranked={len(ranked)} in {time.time() - started:.2f}s"
        )
        return ranked
    def select(self, ranked: List[RetrievedChunk], relevance_threshold: float) -> List[RetrievedChunk]:
        return [r for r in ranked if r.pinned or r.relevance >= relevance_threshold][: self.final_k]
    def smart_search(self, query: str, target_document: Optional[str] = None) -> List[RetrievedChunk]:
        return self.select(self.rank(query, target_document), self.relevance_threshold)
    def adjacent_texts(self, documents: Sequence[Document]) -> List[Tuple[str, str]]:
        wanted = {
            (doc.metadata.get("document_id"), doc.metadata.get("chunk_index") + step)
            for doc in documents if is_text_chunk(doc)
            for step in (-1, 1)
        }
        found: Dict[Tuple[int, int], str] = {}
        with self.vector_store.lock:
            for chunk in self.vector_store.chunks.values():
                key = (chunk.metadata.get("document_id"), chunk.metadata.get("chunk_index"))
                if key in wanted and is_text_chunk(chunk):
                    found[key] = chunk.page_content
        texts: List[Tuple[str, str]] = []
        for doc in documents:
            if not is_text_chunk(doc):
                texts.append(("", ""))
                continue
            document_id, index = doc.metadata["document_id"], doc.metadata["chunk_index"]
            before = found.get((document_id, index - 1), "")
            after = found.get((document_id, index + 1), "")
            texts.append((before[:len(before) - overlap_length(before, doc.page_content)], after[overlap_length(doc.page_content, after):]))
        return texts