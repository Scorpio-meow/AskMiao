import json
import re
import statistics
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from app import prompts
from .research_session import strip_citations
from .tools import KNOWLEDGE_TOOL_NAMES
from .types import Document
JUDGE_VERDICTS = ("correct", "partial", "wrong", "refused")
JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.S)
DIGIT_GROUP_PATTERN = re.compile(r"(?<=\d)[,，](?=\d{3})")
WHITESPACE_PATTERN = re.compile(r"\s+")
CITATION_MARK_PATTERN = re.compile(r"\[\d+(?:\]\s*\[\d+)*\]")
@dataclass
class AnswerCase:
    query: str
    relevant_sources: List[str]
    relevant_passages: List[str]
    facts: List[List[str]]
    kind: str
    note: str
    @property
    def negative(self) -> bool:
        return not self.relevant_sources
def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)
def load_answer_cases(path: str) -> List[AnswerCase]:
    cases: List[AnswerCase] = []
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            where = f"{path} 第 {line_number} 行"
            query = record.get("query")
            sources = record.get("relevant_sources")
            passages = record.get("relevant_passages", [])
            facts = record.get("facts", [])
            kind = record.get("kind")
            note = record.get("note", "")
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f"{where}缺少 query")
            if not isinstance(sources, list) or not all(isinstance(s, str) and s for s in sources):
                raise ValueError(f"{where}的 relevant_sources 必須是檔名陣列（應查無資料的題目填 []）")
            if not _string_list(passages):
                raise ValueError(f"{where}的 relevant_passages 必須是原文片段陣列")
            if not isinstance(facts, list) or not all(_string_list(group) and group for group in facts):
                raise ValueError(f"{where}的 facts 必須是陣列，每個元素是可接受寫法的字串陣列")
            if not isinstance(kind, str) or not kind.strip():
                raise ValueError(f"{where}缺少 kind")
            if not isinstance(note, str):
                raise ValueError(f"{where}的 note 必須是字串")
            if sources and not facts:
                raise ValueError(f"{where}是正例，必須列出 facts")
            if not sources and (facts or passages):
                raise ValueError(f"{where}是反例，不能有 facts 或 relevant_passages")
            cases.append(AnswerCase(query.strip(), sources, passages, facts, kind.strip(), note))
    if not cases:
        raise ValueError(f"{path} 沒有任何評估案例")
    return cases
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("台", "臺")
    text = CITATION_MARK_PATTERN.sub("", text)
    text = DIGIT_GROUP_PATTERN.sub("", text)
    return WHITESPACE_PATTERN.sub("", text)
def mentions(normalized_answer: str, variant: str) -> bool:
    target = normalize(variant)
    pattern = re.escape(target)
    if target[:1].isdigit():
        pattern = r"(?<![\d.])" + pattern
    if target[-1:].isdigit():
        pattern += r"(?!\.?\d)"
    return re.search(pattern, normalized_answer) is not None
def missing_facts(answer: str, facts: Sequence[Sequence[str]]) -> List[List[str]]:
    normalized = normalize(answer)
    return [list(group) for group in facts if not any(mentions(normalized, variant) for variant in group)]
ChunkLookup = Dict[Tuple[str, int], List[str]]
def chunk_lookup(chunks: Iterable[Document]) -> ChunkLookup:
    lookup: ChunkLookup = {}
    for doc in chunks:
        lookup.setdefault((doc.metadata.get("source"), doc.metadata.get("chunk_index")), []).append(doc.page_content)
    return lookup
def missing_passages(case: AnswerCase, lookup: ChunkLookup) -> List[str]:
    return [p for p in case.relevant_passages if not any(p in content for contents in lookup.values() for content in contents)]
def reference_texts(case: AnswerCase, lookup: ChunkLookup) -> List[str]:
    texts: List[str] = []
    for contents in lookup.values():
        for content in contents:
            if content not in texts and any(p in content for p in case.relevant_passages):
                texts.append(content)
    return texts
def cited_texts(details: Sequence[Dict[str, Any]], lookup: ChunkLookup, exclude: Sequence[str]) -> List[str]:
    texts: List[str] = []
    for detail in details:
        source, index = detail.get("source"), detail.get("chunk")
        if isinstance(index, int):
            contents = [c for step in (0, -1, 1) for c in lookup.get((source, index + step), [])]
        else:
            snippet = detail.get("snippet") or ""
            contents = [c for (s, _), group in lookup.items() if s == source for c in group if snippet and c.startswith(snippet)]
        for content in contents:
            if content not in texts and content not in exclude:
                texts.append(content)
    return texts
def judge_messages(case: AnswerCase, answer: str, details: Sequence[Dict[str, Any]], lookup: ChunkLookup) -> List[Dict[str, str]]:
    references = reference_texts(case, lookup)
    if case.negative:
        reference = prompts.ANSWER_JUDGE_NEGATIVE
    else:
        facts = "\n".join(f"- {' / '.join(group)}" for group in case.facts)
        reference = prompts.ANSWER_JUDGE_POSITIVE.format(facts=facts, passages="\n\n".join(references) or "（未標註）")
    if case.note:
        reference += prompts.ANSWER_JUDGE_NOTE.format(note=case.note)
    cited = cited_texts(details, lookup, references)
    if cited:
        reference += prompts.ANSWER_JUDGE_CITED.format(cited="\n\n".join(cited))
    return [
        {"role": "system", "content": prompts.ANSWER_JUDGE_SYSTEM},
        {"role": "user", "content": prompts.ANSWER_JUDGE_CASE.format(query=case.query, reference=reference, answer=strip_citations(answer))},
    ]
def parse_judgement(text: str) -> Dict[str, str]:
    match = JSON_OBJECT_PATTERN.search(text or "")
    if not match:
        raise ValueError(f"評分模型沒有回傳 JSON：{(text or '')[:200]}")
    data = json.loads(match.group(0))
    verdict = data.get("verdict")
    if verdict not in JUDGE_VERDICTS:
        raise ValueError(f"評分模型回傳未知的 verdict：{verdict}")
    return {"verdict": verdict, "reason": str(data.get("reason", ""))}
def grade(
    case: AnswerCase,
    run: Dict[str, Any],
    lookup: ChunkLookup,
    judgement: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    answer = run.get("answer") or ""
    details = run.get("sources_detail") or []
    cited_sources = sorted({d.get("source") for d in details if d.get("source")})
    searched = any(step["tool"] in KNOWLEDGE_TOOL_NAMES for step in run.get("steps") or [])
    result: Dict[str, Any] = {"searched": searched, "cited_sources": cited_sources, "judge": judgement}
    if run.get("error"):
        result.update({"passed": False, "failure": "error"})
        return result
    if case.negative:
        refused = judgement is not None and judgement["verdict"] == "refused"
        result.update({"refused": refused, "passed": refused, "failure": None if refused else "not_refused"})
        return result
    missing = missing_facts(answer, case.facts)
    relevant = set(case.relevant_sources)
    cite_source = bool(relevant & set(cited_sources))
    cite_passage = any(
        any(p in content for content in lookup.get((d.get("source"), d.get("chunk")), []) for p in case.relevant_passages)
        for d in details
    ) if case.relevant_passages else None
    judged_correct = judgement is None or judgement["verdict"] == "correct"
    if not searched:
        failure = "no_search"
    elif missing:
        failure = "missing_facts"
    elif not cite_source:
        failure = "no_relevant_citation"
    elif not judged_correct:
        failure = f"judge_{judgement['verdict']}"
    else:
        failure = None
    result.update({
        "missing_facts": missing,
        "facts_ok": not missing,
        "cite_source": cite_source,
        "cite_passage": cite_passage,
        "passed": failure is None,
        "failure": failure,
    })
    return result
def _rate(values: List[bool]) -> Optional[float]:
    return sum(values) / len(values) if values else None
def summarize(cases: Sequence[AnswerCase], results: Sequence[List[Dict[str, Any]]]) -> Dict[str, Any]:
    flat = [(case, r) for case, runs in zip(cases, results) for r in runs]
    positives = [r for case, r in flat if not case.negative]
    negatives = [r for case, r in flat if case.negative]
    judged = [r for r in positives if r["grade"]["judge"] is not None]
    by_kind: Dict[str, Dict[str, Any]] = {}
    for case, r in flat:
        bucket = by_kind.setdefault(case.kind, {"runs": 0, "passed": 0})
        bucket["runs"] += 1
        bucket["passed"] += int(r["grade"]["passed"])
    failures: Dict[str, int] = {}
    for _, r in flat:
        if r["grade"]["failure"]:
            failures[r["grade"]["failure"]] = failures.get(r["grade"]["failure"], 0) + 1
    stability = [sum(r["grade"]["passed"] for r in runs) for runs in results]
    runs_per_case = max((len(runs) for runs in results), default=0)
    times = [r["total_time"] for _, r in flat if r.get("total_time") is not None]
    turns = [r["turns_used"] for _, r in flat if r.get("turns_used") is not None]
    return {
        "num_cases": len(cases),
        "num_positive": sum(not c.negative for c in cases),
        "num_negative": sum(c.negative for c in cases),
        "runs_per_case": runs_per_case,
        "pass_rate": _rate([r["grade"]["passed"] for _, r in flat]),
        "positive_pass_rate": _rate([r["grade"]["passed"] for r in positives]),
        "facts_rate": _rate([bool(r["grade"].get("facts_ok")) for r in positives]),
        "cite_source_rate": _rate([bool(r["grade"].get("cite_source")) for r in positives]),
        "cite_passage_rate": _rate([bool(r["grade"]["cite_passage"]) for r in positives if r["grade"].get("cite_passage") is not None]),
        "search_rate": _rate([r["grade"]["searched"] for _, r in flat]),
        "judge_correct_rate": _rate([r["grade"]["judge"]["verdict"] == "correct" for r in judged]),
        "refusal_rate": _rate([bool(r["grade"].get("refused")) for r in negatives]),
        "error_rate": _rate([bool(r.get("error")) for _, r in flat]),
        "by_kind": {kind: {**v, "pass_rate": v["passed"] / v["runs"]} for kind, v in sorted(by_kind.items())},
        "failures": dict(sorted(failures.items(), key=lambda item: -item[1])),
        "always_pass": sum(1 for s in stability if s == runs_per_case),
        "flaky": sum(1 for s in stability if 0 < s < runs_per_case),
        "always_fail": sum(1 for s in stability if s == 0),
        "median_seconds": statistics.median(times) if times else None,
        "median_turns": statistics.median(turns) if turns else None,
    }