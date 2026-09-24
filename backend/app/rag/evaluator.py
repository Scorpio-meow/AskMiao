import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Sequence

from .retrievers.hybrid import HybridRetriever


@dataclass
class RetrievalCase:
    query: str
    relevant_sources: List[str]


def load_golden_set(path: str) -> List[RetrievalCase]:
    """讀取 JSONL 標準問答集：每行 {"query": "...", "relevant_sources": ["檔名", ...]}"""
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
            if not isinstance(sources, list) or not sources or not all(isinstance(s, str) and s for s in sources):
                raise ValueError(f"{path} 第 {line_number} 行的 relevant_sources 必須是非空的檔名陣列")
            cases.append(RetrievalCase(query=query.strip(), relevant_sources=sources))
    if not cases:
        raise ValueError(f"{path} 沒有任何評估案例")
    return cases


def ranked_sources(doc_score_pairs) -> List[str]:
    """依排名取出不重複的來源檔名（同一文件的多個片段只算一次）"""
    sources: List[str] = []
    for doc, _ in doc_score_pairs:
        source = doc.metadata.get("source")
        if source and source not in sources:
            sources.append(source)
    return sources


class RAGEvaluator:
    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever

    def evaluate(self, cases: Sequence[RetrievalCase], k_values: Sequence[int]) -> Dict[str, Any]:
        """以線上實際使用的 smart_search 計算文件層級的 hit@k、recall@k 與 MRR"""
        per_query = []
        for case in cases:
            ranking = ranked_sources(self.retriever.smart_search(case.query))
            relevant = set(case.relevant_sources)
            first_hit_rank = next((rank for rank, source in enumerate(ranking, start=1) if source in relevant), None)
            per_query.append({
                "query": case.query,
                "relevant_sources": case.relevant_sources,
                "retrieved_sources": ranking,
                "first_hit_rank": first_hit_rank,
                "hit": {k: bool(relevant & set(ranking[:k])) for k in k_values},
                "recall": {k: len(relevant & set(ranking[:k])) / len(relevant) for k in k_values},
                "reciprocal_rank": 1.0 / first_hit_rank if first_hit_rank else 0.0,
            })

        total = len(per_query)
        return {
            "num_queries": total,
            "hit_rate": {k: sum(q["hit"][k] for q in per_query) / total for k in k_values},
            "recall": {k: sum(q["recall"][k] for q in per_query) / total for k in k_values},
            "mrr": sum(q["reciprocal_rank"] for q in per_query) / total,
            "per_query": per_query,
            "evaluation_timestamp": datetime.now().isoformat(),
        }

    def auto_tune_alpha(
        self,
        cases: Sequence[RetrievalCase],
        k_values: Sequence[int],
        alphas: Sequence[float]
    ) -> Dict[str, Any]:
        """逐一嘗試 hybrid_alpha 並回傳 MRR 最高者；結束後還原原本的 alpha，是否套用由呼叫端決定"""
        original_alpha = self.retriever.hybrid_alpha
        best: Dict[str, Any] = {}
        try:
            for alpha in alphas:
                self.retriever.hybrid_alpha = alpha
                report = self.evaluate(cases, k_values)
                if not best or report["mrr"] > best["mrr"]:
                    best = {"alpha": alpha, "mrr": report["mrr"], "report": report}
        finally:
            self.retriever.hybrid_alpha = original_alpha
        return best
