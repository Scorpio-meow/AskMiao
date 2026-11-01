import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .retrievers.hybrid import HybridRetriever, RetrievedChunk
from .types import Document


@dataclass
class RetrievalCase:
    query: str
    # 空陣列表示這題應查無資料（反例）
    relevant_sources: List[str]
    relevant_passages: List[str] = field(default_factory=list)


def load_golden_set(path: str) -> List[RetrievalCase]:
    """讀取 JSONL 標準問答集：每行 {"query": "...", "relevant_sources": ["檔名", ...], "relevant_passages": ["原文片段", ...]}；
    relevant_passages 可省略，應查無資料的題目 relevant_sources 填 []"""
    cases: List[RetrievalCase] = []
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            query = record.get("query")
            sources = record.get("relevant_sources")
            passages = record.get("relevant_passages", [])
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f"{path} 第 {line_number} 行缺少 query")
            if not isinstance(sources, list) or not all(isinstance(s, str) and s for s in sources):
                raise ValueError(f"{path} 第 {line_number} 行的 relevant_sources 必須是檔名陣列（應查無資料的題目填 []）")
            if not isinstance(passages, list) or not all(isinstance(p, str) and p.strip() for p in passages):
                raise ValueError(f"{path} 第 {line_number} 行的 relevant_passages 必須是原文片段陣列")
            if passages and not sources:
                raise ValueError(f"{path} 第 {line_number} 行有 relevant_passages 卻沒有 relevant_sources")
            cases.append(RetrievalCase(query=query.strip(), relevant_sources=sources, relevant_passages=passages))
    if not cases:
        raise ValueError(f"{path} 沒有任何評估案例")
    return cases


def ranked_sources(results: Sequence[RetrievedChunk]) -> List[str]:
    """依排名取出不重複的來源檔名（同一文件的多個片段只算一次）"""
    sources: List[str] = []
    for result in results:
        source = result.document.metadata.get("source")
        if source and source not in sources:
            sources.append(source)
    return sources


def _dcg(flags: Sequence[bool]) -> float:
    return sum(1.0 / math.log2(rank + 1) for rank, flag in enumerate(flags, start=1) if flag)


def _covered(passages: Sequence[str], results: Iterable[RetrievedChunk]) -> Set[str]:
    contents = [result.document.page_content for result in results]
    return {passage for passage in passages if any(passage in content for content in contents)}


def passage_relevant_chunk_ids(case: RetrievalCase, chunks: Dict[int, Document]) -> Set[int]:
    missing = [p for p in case.relevant_passages if not any(p in doc.page_content for doc in chunks.values())]
    if missing:
        raise ValueError(f"「{case.query}」的 relevant_passages 在知識庫片段中找不到：{'、'.join(missing)}")
    return {
        chunk_id for chunk_id, doc in chunks.items()
        if any(passage in doc.page_content for passage in case.relevant_passages)
    }


class RAGEvaluator:
    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever

    def evaluate(self, cases: Sequence[RetrievalCase], k_values: Sequence[int]) -> Dict[str, Any]:
        """以線上檢索流程（重排後套用設定的相關性門檻，與 smart_search 相同）計算指標"""
        return self.sweep_relevance_thresholds(cases, k_values, [self.retriever.relevance_threshold])[0]

    def sweep_relevance_thresholds(
        self,
        cases: Sequence[RetrievalCase],
        k_values: Sequence[int],
        thresholds: Sequence[float]
    ) -> List[Dict[str, Any]]:
        """每題只重排一次，對同一份重排結果套用多個相關性門檻，依門檻順序回傳各自的報告"""
        relevant_ids = self._passage_relevant_ids(cases)
        rankings = [self.retriever.rank(case.query) for case in cases]
        return [
            self._report(
                cases, rankings, [self.retriever.select(ranked, threshold) for ranked in rankings],
                relevant_ids, k_values, threshold,
            )
            for threshold in thresholds
        ]

    def _passage_relevant_ids(self, cases: Sequence[RetrievalCase]) -> List[Optional[Set[int]]]:
        if not any(case.relevant_passages for case in cases):
            return [None] * len(cases)
        with self.retriever.vector_store.lock:
            chunks = dict(self.retriever.vector_store.chunks)
        return [passage_relevant_chunk_ids(case, chunks) if case.relevant_passages else None for case in cases]

    @staticmethod
    def _report(
        cases: Sequence[RetrievalCase],
        rankings: Sequence[List[RetrievedChunk]],
        results_per_case: Sequence[List[RetrievedChunk]],
        relevant_ids: Sequence[Optional[Set[int]]],
        k_values: Sequence[int],
        threshold: float
    ) -> Dict[str, Any]:
        """正例計算文件層級的 hit@k、recall@k 與 MRR；有 relevant_passages 的正例另計片段層級的 precision@k、nDCG@k、
        原文片段 recall@k、MRR 與候選召回（重排前候選涵蓋的原文片段比例）；反例計算拒絕率（沒有回傳任何片段）"""
        per_query = []
        for case, ranked, results, relevant_chunks in zip(cases, rankings, results_per_case, relevant_ids):
            ranking = ranked_sources(results)
            entry: Dict[str, Any] = {
                "query": case.query,
                "relevant_sources": case.relevant_sources,
                "retrieved_sources": ranking,
            }
            if case.relevant_sources:
                relevant = set(case.relevant_sources)
                first_hit_rank = next((rank for rank, source in enumerate(ranking, start=1) if source in relevant), None)
                entry.update({
                    "first_hit_rank": first_hit_rank,
                    "hit": {k: bool(relevant & set(ranking[:k])) for k in k_values},
                    "recall": {k: len(relevant & set(ranking[:k])) / len(relevant) for k in k_values},
                    "reciprocal_rank": 1.0 / first_hit_rank if first_hit_rank else 0.0,
                })
            else:
                entry["rejected"] = not results
            if relevant_chunks is not None:
                flags = [result.document.metadata["chunk_id"] in relevant_chunks for result in results]
                first_relevant = next((rank for rank, flag in enumerate(flags, start=1) if flag), None)
                passages = case.relevant_passages
                entry["passage"] = {
                    "first_relevant_rank": first_relevant,
                    "precision": {k: sum(flags[:k]) / k for k in k_values},
                    "ndcg": {k: _dcg(flags[:k]) / _dcg([True] * min(k, len(relevant_chunks))) for k in k_values},
                    "recall": {k: len(_covered(passages, results[:k])) / len(passages) for k in k_values},
                    "reciprocal_rank": 1.0 / first_relevant if first_relevant else 0.0,
                    "candidate_recall": len(_covered(passages, ranked)) / len(passages),
                }
            per_query.append(entry)

        positives = [q for q in per_query if q["relevant_sources"]]
        negatives = [q for q in per_query if not q["relevant_sources"]]
        with_passages = [q["passage"] for q in per_query if "passage" in q]
        return {
            "relevance_threshold": threshold,
            "num_queries": len(per_query),
            "num_positive": len(positives),
            "num_negative": len(negatives),
            "hit_rate": {k: sum(q["hit"][k] for q in positives) / len(positives) for k in k_values} if positives else None,
            "recall": {k: sum(q["recall"][k] for q in positives) / len(positives) for k in k_values} if positives else None,
            "mrr": sum(q["reciprocal_rank"] for q in positives) / len(positives) if positives else None,
            "negative_rejection_rate": sum(q["rejected"] for q in negatives) / len(negatives) if negatives else None,
            "passage": {
                "num_cases": len(with_passages),
                "precision": {k: sum(p["precision"][k] for p in with_passages) / len(with_passages) for k in k_values},
                "ndcg": {k: sum(p["ndcg"][k] for p in with_passages) / len(with_passages) for k in k_values},
                "recall": {k: sum(p["recall"][k] for p in with_passages) / len(with_passages) for k in k_values},
                "mrr": sum(p["reciprocal_rank"] for p in with_passages) / len(with_passages),
                "candidate_recall": sum(p["candidate_recall"] for p in with_passages) / len(with_passages),
            } if with_passages else None,
            "per_query": per_query,
            "evaluation_timestamp": datetime.now().isoformat(),
        }
