"""
檢索品質評估：以線上實際使用的檢索流程（重排後套用相關性門檻），對標準問答集計算文件層級的 hit@k、recall@k 與 MRR。

標準問答集為 JSONL，每行一個案例：
    {"query": "特休假怎麼計算？", "relevant_sources": ["員工手冊.pdf"]}
relevant_sources 填知識庫中文件的檔名（與上傳後的 source 相同），同一題可列多份相關文件。
應該查無資料的題目填 "relevant_sources": []（反例），用來計算反例拒絕率。
格式範例見 backend/eval/retrieval_golden.example.jsonl。

評估在索引檔的暫存副本上以唯讀模式執行，不會修改資料庫或正式索引，可與後端同時執行。

用法（在 backend/ 目錄執行）：
    ../.venv/Scripts/python.exe scripts/evaluate_retrieval.py --golden eval/retrieval_golden.jsonl --k 1 3 5
加上 --min-mrr 0.6 可在 MRR 未達標時以結束碼 1 結束（適合放進 CI）；--output report.json 會輸出完整結果。
加上 --relevance-thresholds 0.1 0.2 0.3 可校準 RERANK_RELEVANCE_THRESHOLD：每題只重排一次，
對同一份結果套用各個門檻，列出正例的 hit@k、MRR 與反例的拒絕率。
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.models.database import SessionLocal
from app.rag.contextual_rag import HybridContextualRAG
from app.rag.evaluator import load_golden_set


def snapshot_index_files(snapshot_dir: Path) -> None:
    """把正式索引檔複製到暫存目錄，並讓本程序的設定改指向副本"""
    for setting_name in ("FAISS_INDEX_PATH", "METADATA_PATH"):
        source = Path(getattr(settings, setting_name))
        target = snapshot_dir / source.name
        if source.exists():
            shutil.copy2(source, target)
        setattr(settings, setting_name, str(target))

    bm25_source = Path(settings.BM25_INDEX_DIR)
    bm25_target = snapshot_dir / bm25_source.name
    if bm25_source.is_dir():
        shutil.copytree(bm25_source, bm25_target)
    settings.BM25_INDEX_DIR = str(bm25_target)
    settings.DATA_DIR = str(snapshot_dir)


def format_metric(value) -> str:
    return "—" if value is None else f"{value:.3f}"


def print_report(report: dict, k_values: list) -> None:
    print(f"評估案例數：{report['num_queries']}（正例 {report['num_positive']}、反例 {report['num_negative']}）")
    print(f"相關性門檻：{report['relevance_threshold']}")
    if report["mrr"] is not None:
        print(f"MRR：{report['mrr']:.3f}")
        for k in k_values:
            print(f"hit@{k}：{report['hit_rate'][k]:.3f}　recall@{k}：{report['recall'][k]:.3f}")
    if report["negative_rejection_rate"] is not None:
        print(f"反例拒絕率：{report['negative_rejection_rate']:.3f}")

    positives = [q for q in report["per_query"] if q["relevant_sources"]]
    misses = [q for q in positives if q["first_hit_rank"] is None or q["first_hit_rank"] > max(k_values)]
    if misses:
        print(f"\n前 {max(k_values)} 名內未找到相關文件的問題（{len(misses)} 題）：")
        for q in misses:
            retrieved = "、".join(q["retrieved_sources"][:max(k_values)]) or "（無結果）"
            print(f"- {q['query']}\n  預期：{'、'.join(q['relevant_sources'])}\n  實際：{retrieved}")

    accepted = [q for q in report["per_query"] if not q["relevant_sources"] and not q["rejected"]]
    if accepted:
        print(f"\n應查無資料卻回傳片段的問題（{len(accepted)} 題）：")
        for q in accepted:
            print(f"- {q['query']}\n  實際：{'、'.join(q['retrieved_sources']) or '（片段缺少來源）'}")


def print_threshold_sweep(reports: list, k_values: list) -> None:
    print("\n相關性門檻比較（同一次重排結果）：")
    for report in reports:
        hits = "　".join(
            f"hit@{k} {format_metric(report['hit_rate'][k] if report['hit_rate'] else None)}" for k in k_values
        )
        print(
            f"門檻 {report['relevance_threshold']}：MRR {format_metric(report['mrr'])}　{hits}"
            f"　反例拒絕率 {format_metric(report['negative_rejection_rate'])}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="以標準問答集評估 RAG 檢索品質")
    parser.add_argument("--golden", required=True, help="JSONL 標準問答集路徑")
    parser.add_argument("--k", required=True, type=int, nargs="+", help="要計算的 k 值，例如 1 3 5")
    parser.add_argument("--min-mrr", type=float, help="MRR 低於此值時以結束碼 1 結束")
    parser.add_argument("--output", help="將完整評估結果寫成 JSON 檔")
    parser.add_argument(
        "--relevance-thresholds", type=float, nargs="+",
        help="要比較的相關性門檻，例如 0.1 0.2 0.3（對同一次重排結果套用）"
    )
    args = parser.parse_args()

    cases = load_golden_set(args.golden)
    snapshot_dir = Path(tempfile.mkdtemp(prefix="askmiao_eval_"))
    rag = None
    try:
        snapshot_index_files(snapshot_dir)
        rag = HybridContextualRAG(session_factory=SessionLocal, read_only=True)
        thresholds = [rag.relevance_threshold] + (args.relevance_thresholds or [])
        report, *sweep = rag.evaluator.sweep_relevance_thresholds(cases, args.k, thresholds)
    finally:
        if rag is not None and rag.bm25_store.bm25_searcher is not None:
            rag.bm25_store.bm25_searcher.close()
        shutil.rmtree(snapshot_dir, ignore_errors=True)

    print_report(report, args.k)
    if sweep:
        print_threshold_sweep(sweep, args.k)
        report["threshold_sweep"] = sweep
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.min_mrr is not None:
        if report["mrr"] is None:
            print("\n問答集沒有正例，無法檢查 MRR 門檻")
            return 1
        if report["mrr"] < args.min_mrr:
            print(f"\nMRR {report['mrr']:.3f} 低於門檻 {args.min_mrr}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
