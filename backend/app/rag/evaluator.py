import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Sequence

from .retrievers.hybrid import HybridRetriever, RetrievedChunk


@dataclass
class RetrievalCase:
    query: str
    # 空陣列表示這題應查無資料（反例）
    relevant_sources: List[str]


def load_golden_set(path: str) -> List[RetrievalCase]:
    """讀取 JSONL 標準問答集：每行 {"query": "...", "relevant_sources": ["檔名", ...]}；應查無資料的題目填 []"""
    cases: List[RetrievalCase] = []
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            query = record.get("query")
            sources = record.get("relevant_sources")
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f"{path} 第 {line_number} 行缺少 query")
            if not isinstance(sources, list) or not all(isinstance(s, str) and s for s in sources):
                raise ValueError(f"{path} 第 {line_number} 行的 relevant_sources 必須是檔名陣列（應查無資料的題目填 []）")
            cases.append(RetrievalCase(query=query.strip(), relevant_sources=sources))
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
        rankings = [self.retriever.rank(case.query) for case in cases]
        return [
            self._report(cases, [self.retriever.select(ranked, threshold) for ranked in rankings], k_values, threshold)
            for threshold in thresholds
        ]

    @staticmethod
    def _report(
        cases: Sequence[RetrievalCase],
        results_per_case: Sequence[List[RetrievedChunk]],
        k_values: Sequence[int],
        threshold: float
    ) -> Dict[str, Any]:
        """正例計算文件層級的 hit@k、recall@k 與 MRR；反例計算拒絕率（沒有回傳任何片段）"""
        per_query = []
        for case, results in zip(cases, results_per_case):
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
            per_query.append(entry)

        positives = [q for q in per_query if q["relevant_sources"]]
        negatives = [q for q in per_query if not q["relevant_sources"]]
        return {
            "relevance_threshold": threshold,
            "num_queries": len(per_query),
            "num_positive": len(positives),
            "num_negative": len(negatives),
            "hit_rate": {k: sum(q["hit"][k] for q in positives) / len(positives) for k in k_values} if positives else None,
            "recall": {k: sum(q["recall"][k] for q in positives) / len(positives) for k in k_values} if positives else None,
            "mrr": sum(q["reciprocal_rank"] for q in positives) / len(positives) if positives else None,
            "negative_rejection_rate": sum(q["rejected"] for q in negatives) / len(negatives) if negatives else None,
            "per_query": per_query,
            "evaluation_timestamp": datetime.now().isoformat(),
        }
