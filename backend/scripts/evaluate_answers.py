import argparse
import asyncio
import gc
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(Path(__file__).resolve().parent))
PROVIDERS = ("vllm", "openai", "ollama", "gemini", "anthropic", "foundry")
MODES = ("research", "agent")
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
ANSWER_PREVIEW_CHARS = 300
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="以真實模型跑完整的研究迴圈，評估知識庫問答的最終答案")
    parser.add_argument("--golden", required=True, help="答案層級的 JSONL 題組")
    parser.add_argument("--corpus", required=True, help="在暫存環境中建立知識庫的文件目錄")
    parser.add_argument("--provider", required=True, choices=PROVIDERS)
    parser.add_argument("--api-base", required=True, help="模型 API 位址，例如 http://host:8000/v1")
    parser.add_argument("--api-key-env", help="存放 API 金鑰的環境變數名稱；不需要金鑰時省略")
    parser.add_argument("--model", required=True)
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--reasoning-effort", required=True, choices=EFFORTS)
    parser.add_argument("--runs", required=True, type=int, help="每題重跑次數")
    parser.add_argument("--concurrency", required=True, type=int, help="同時進行的提問數")
    parser.add_argument("--judge-model", required=True, help="評分用的模型（同一個 API 位址）；反例要靠它判定有沒有照實說查不到")
    parser.add_argument("--judge-reasoning-effort", required=True, choices=EFFORTS)
    parser.add_argument("--only", nargs="+", help="只跑問題包含這些字的題目")
    parser.add_argument("--output", help="把完整結果寫成 JSON 檔")
    parser.add_argument("--min-pass-rate", type=float, help="整體通過率低於此值時以結束碼 1 結束")
    args = parser.parse_args()
    if args.runs < 1 or args.concurrency < 1:
        parser.error("--runs 與 --concurrency 必須是正整數")
    if args.api_key_env and not os.environ.get(args.api_key_env):
        parser.error(f"環境變數 {args.api_key_env} 沒有設定")
    return args
async def ask(agent, case, args, endpoint) -> dict:
    steps = []
    started = time.monotonic()
    try:
        async for event in agent.stream_research(
            query=case.query,
            endpoint=endpoint,
            model_name=args.model,
            conversation_history=[],
            reasoning_effort=args.reasoning_effort,
            attachments=None,
            approval_user_id=None,
            conversation_id=None,
            mode=args.mode,
            instructions="",
            allow_web=False,
        ):
            if event["event"] == "step_end":
                data = event["data"]
                steps.append({"tool": data["tool"], "arguments": data.get("arguments"), "status": data.get("status")})
            elif event["event"] == "done":
                data = event["data"]
                return {
                    "answer": data["answer"],
                    "sources_detail": data["sources_detail"],
                    "steps": steps,
                    "turns_used": data["turns_used"],
                    "total_time": round(time.monotonic() - started, 2),
                    "error": None,
                }
        return {"answer": "", "sources_detail": [], "steps": steps, "turns_used": None, "total_time": None, "error": "研究迴圈沒有送出 done 事件"}
    except Exception as e:
        return {"answer": "", "sources_detail": [], "steps": steps, "turns_used": None, "total_time": None, "error": f"{type(e).__name__}: {e}"}
async def judge(case, run, lookup, args, endpoint) -> dict:
    from app.core.llm_client import chat_completion
    from app.rag.answer_evaluator import judge_messages, parse_judgement
    reply = await chat_completion(
        judge_messages(case, run["answer"], run["sources_detail"], lookup), endpoint=endpoint, model_name=args.judge_model, reasoning_effort=args.judge_reasoning_effort
    )
    return parse_judgement(reply.get("content") or "")
async def evaluate(cases, agent, lookup, args, endpoint) -> list:
    from app.rag.answer_evaluator import grade
    gate = asyncio.Semaphore(args.concurrency)
    results = [[None] * args.runs for _ in cases]
    done = 0
    async def one(index, run_index):
        nonlocal done
        case = cases[index]
        async with gate:
            run = await ask(agent, case, args, endpoint)
            judgement = None
            if not run["error"]:
                try:
                    judgement = await judge(case, run, lookup, args, endpoint)
                except Exception as e:
                    run["error"] = f"評分失敗 {type(e).__name__}: {e}"
        run["grade"] = grade(case, run, lookup, judgement)
        results[index][run_index] = run
        done += 1
        mark = "通過" if run["grade"]["passed"] else f"失敗（{run['grade']['failure']}）"
        print(f"[{done}/{len(cases) * args.runs}] {case.query}：{mark}", flush=True)
    await asyncio.gather(*(one(i, r) for r in range(args.runs) for i in range(len(cases))))
    return results
def rate(value) -> str:
    return "—" if value is None else f"{value:.3f}"
def print_report(cases, results, summary) -> None:
    print(f"\n題數：{summary['num_cases']}（正例 {summary['num_positive']}、反例 {summary['num_negative']}），每題 {summary['runs_per_case']} 次")
    print(f"整體通過率：{rate(summary['pass_rate'])}　正例通過率：{rate(summary['positive_pass_rate'])}　反例拒答率：{rate(summary['refusal_rate'])}")
    print(f"答案事實命中：{rate(summary['facts_rate'])}　引用相關文件：{rate(summary['cite_source_rate'])}　引用正解片段：{rate(summary['cite_passage_rate'])}")
    print(f"有查知識庫：{rate(summary['search_rate'])}　評分判定正確：{rate(summary['judge_correct_rate'])}　錯誤率：{rate(summary['error_rate'])}")
    print(f"每題穩定度：全過 {summary['always_pass']}、時過時不過 {summary['flaky']}、全不過 {summary['always_fail']}")
    print(f"中位數耗時 {summary['median_seconds']} 秒，中位數輪數 {summary['median_turns']}")
    print("\n各題型通過率：")
    for kind, value in summary["by_kind"].items():
        print(f"- {kind}：{value['pass_rate']:.3f}（{value['passed']}/{value['runs']}）")
    if summary["failures"]:
        print("\n失敗原因：" + "、".join(f"{k} {v}" for k, v in summary["failures"].items()))
    print("\n沒有每次都通過的題目：")
    for case, runs in zip(cases, results):
        passed = sum(r["grade"]["passed"] for r in runs)
        if passed == len(runs):
            continue
        print(f"\n■ {case.query}（{passed}/{len(runs)}，{case.kind}）")
        for index, r in enumerate(runs, start=1):
            g = r["grade"]
            if g["passed"]:
                continue
            tools = "、".join(f"{s['tool']}({json.dumps(s['arguments'], ensure_ascii=False)})" for s in r["steps"]) or "（沒有呼叫工具）"
            extra = ""
            if g.get("missing_facts"):
                extra += f" 缺少：{'；'.join('/'.join(group) for group in g['missing_facts'])}"
            if g.get("judge"):
                extra += f" 評分：{g['judge']['verdict']}（{g['judge']['reason']}）"
            if r.get("error"):
                extra += f" 錯誤：{r['error']}"
            print(f"  第 {index} 次 {g['failure']}{extra}")
            print(f"    工具：{tools}")
            print(f"    引用：{'、'.join(g['cited_sources']) or '（無）'}")
            print(f"    回答：{r['answer'][:ANSWER_PREVIEW_CHARS].replace(chr(10), ' ')}")
def main() -> int:
    args = parse_args()
    work_dir = Path(tempfile.mkdtemp(prefix="askmiao_answer_eval_"))
    os.environ["DATABASE_URL"] = f"sqlite:///{(work_dir / 'corpus.db').as_posix()}"
    os.environ["LOG_DIR"] = str(work_dir / "logs")
    from app.core.config import settings
    from app.core.llm_client import LlmEndpoint
    from app.models.database import engine
    from app.rag.answer_evaluator import chunk_lookup, load_answer_cases, missing_passages, summarize
    from evaluate_retrieval import build_corpus_knowledge_base
    settings.ENABLE_WEB_SEARCH = False
    cases = load_answer_cases(args.golden)
    if args.only:
        cases = [case for case in cases if any(word in case.query for word in args.only)]
        if not cases:
            print("沒有符合 --only 的題目")
            return 1
    endpoint = LlmEndpoint(
        provider=args.provider,
        api_base=args.api_base,
        api_key=os.environ[args.api_key_env] if args.api_key_env else None,
        max_output_tokens=None,
        public_only=False,
    )
    rag = None
    try:
        rag = build_corpus_knowledge_base(Path(args.corpus), work_dir)
        with rag.vector_store.lock:
            lookup = chunk_lookup(rag.vector_store.chunks.values())
        for case in cases:
            missing = missing_passages(case, lookup)
            if missing:
                raise ValueError(f"「{case.query}」的 relevant_passages 在知識庫片段中找不到：{'、'.join(missing)}")
        started = time.monotonic()
        results = asyncio.run(evaluate(cases, rag.pipeline.agent, lookup, args, endpoint))
        elapsed = round(time.monotonic() - started, 1)
    finally:
        if rag is not None and rag.bm25_store.bm25_searcher is not None:
            rag.bm25_store.bm25_searcher.close()
        rag = None
        gc.collect()
        engine.dispose()
        shutil.rmtree(work_dir, ignore_errors=True)
    summary = summarize(cases, results)
    print_report(cases, results, summary)
    print(f"\n總耗時 {elapsed} 秒")
    if args.output:
        report = {
            "config": {k: v for k, v in vars(args).items() if k not in ("output", "api_key_env")},
            "summary": summary,
            "cases": [{"query": c.query, "kind": c.kind, "runs": runs} for c, runs in zip(cases, results)],
        }
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.min_pass_rate is not None and summary["pass_rate"] < args.min_pass_rate:
        print(f"\n整體通過率 {summary['pass_rate']:.3f} 低於門檻 {args.min_pass_rate}")
        return 1
    return 0
if __name__ == "__main__":
    sys.exit(main())