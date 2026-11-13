# ADR-0008: Answer-level evaluation, a knowledge-base search limit in research mode, and neighbouring text

[繁體中文](0008-answer-level-evaluation-and-search-guards.md) | [English](0008-answer-level-evaluation-and-search-guards_en.md)

## Status

Accepted - 2026-11-13

Supplements the research loop in [ADR-0003](./0003-rrf-relevance-citations-and-tool-trust_en.md) and the evaluation in [ADR-0007](./0007-han-ngram-bm25-and-passage-level-evaluation_en.md).

---

## Context and problem statement

1. **Only retrieval was measured**: ADR-0007 stops at chunk-level metrics, but users read the answer the model writes. A good ranking can still produce an answer that misses a fact, cites the wrong number, or presents general knowledge as the organization's rule. Without answer-level measurements there was no way to compare prompt or research-loop changes.
2. **Questions with no answer kept searching**: running the bundled set with Gemma-4-26B-A4B (vLLM, `reasoning_effort=medium`), 92% of the questions the knowledge base can answer needed one search and none needed more than 4; questions it cannot answer averaged 7.8 searches and reached 31, ending with single characters such as 「認」, 「車」, and 「元」, and one question took 302 seconds. Research mode has no turn limit; only the prompt's "stop searching once you have enough" held it back.
3. **Chunking cut articles apart**: Article 50 of the Mass Rapid Transit Act states the fine at the start and lists "crossing the yellow warning line" as item 14, and chunking put them in different chunks. The model got only the second one and answered all three times that the article states no fine. Articles 48 and 48-1 had the same problem.
4. **Answers attached their own source lists**: 15 of 408 answers ended with a self-made list of file names and numbers, duplicating the sources the system attaches from the `[n]` marks.

---

## Decision

### 1. Answer-level evaluation

- `scripts/evaluate_answers.py` builds a knowledge base from the `--corpus` files on a temporary SQLite database, runs the full research loop (without the web) with the given real model, and repeats each question `--runs` times; `app/rag/answer_evaluator.py` grades and summarizes. Every argument must be given explicitly; there are no defaults.
- **Rule checks**:
  - Answer facts: each group in `facts` must appear in at least one accepted form. Both sides are normalized first, and a number must not run into other digits, so "500" does not match "5,500" and "25" does not match "2025".
  - Citations: the cited sources must include a correct document; whether a cited chunk contains the correct passage is reported as well.
  - Searched: at least one knowledge-base tool call.
- **Judge model** (required, because only the judge can grade negative questions): it gets the expected facts, the full text of the passages that hold them, and the text of the chunks the answer actually cites (with their neighbouring chunks, matching the `context_before` and `context_after` the model saw), and returns `correct`, `partial`, `wrong`, or `refused`. Details found in the cited chunks are fine. For negative questions, saying plainly that nothing was found is `refused`, and adding related rules from the knowledge base that are not the item asked about does not count against the answer.
- **Report**: pass rates are not decided by majority vote. The report lists per-question stability (always passes, sometimes passes, never passes), and pass rates and failure reasons by question kind.
- **The set**, `backend/eval/answer_golden.jsonl`, has 136 questions:
  - The 118 questions of `corpus_golden.jsonl`, each labelled with its answer facts.
  - 18 more: calculations (three nights in Japan, the halved allowance for same-day trips, the birth allowance for twins), a comparison (application deadlines in the 2025 and 2026 versions), multi-document questions (when a new hire may work remotely, when annual leave starts), false premises ("the auditorium seats 200", "the 2026 version bans taxi claims"), counting (account questions in the IT FAQ), abbreviations, and negative questions that invite answers from general knowledge (the overtime pay multiplier, a 2027 travel policy).
- **The judge itself had to be checked**: the first version got a single line of reference text. It marked correct details from other paragraphs as made up, and failed negative answers that added related rules. On the same answers it reported a negative refusal rate of 0.889 although every answer was correct on manual review. Giving it the full passages and the cited chunks, and relaxing the negative rule, brought the rate to 1.000, matching the manual review.

### 2. A knowledge-base search limit in research mode

- In research mode, `ResearchSession` blocks two kinds of knowledge-base calls (`search_knowledge_base`, `filter_and_count_records`) in code rather than through the prompt:
  - a call with the same arguments as an earlier one (ignoring leading and trailing spaces in strings) is not run again and returns `KNOWLEDGE_SEARCH_REPEATED`, but still counts toward the budget, so a model that keeps resending the same search also runs out;
  - the seventh call returns `KNOWLEDGE_SEARCH_LIMIT`, and the loop then appends `ANSWER_NOW` and has the model answer from what it has without calling more tools, so a model that ignores the refusal cannot keep retrying;
  - a search that fails to run (for example on a reranker error) does not count as done and may be retried with the same arguments, though it still counts toward the budget.
- Blocked calls run no retrieval or reranking and show as failed steps in the research trace.
- The limit, `MAX_RESEARCH_KNOWLEDGE_SEARCHES`, is 6: in the baseline, answerable questions needed at most 4 searches, which leaves 2 to spare.
- Agent mode has no limit. It replaces older tool results with `TOOL_RESULT_CLEARED` and may need to fetch them again, and its subagents search on their own, so blocking repeated searches would cut it off from data.

### 3. Neighbouring text in knowledge-base results

- Chunks of text documents returned by `search_knowledge_base` also carry `context_before` and `context_after`: the chunks right before and after them in the same document, minus the text they share with this chunk (`HybridRetriever.adjacent_texts`).
- Structured records and Q&A chunks kept whole get neither, because they are self-contained units already.
- The neighbouring text is assembled at query time from the chunks in memory, so the index does not change and needs no rebuild.
- Retrieval and reranking still score the original chunk, and citation numbers and sources still point at it. The neighbouring text only helps the model read the context.

### 4. Prompts

- When nothing is found, search again once or twice with wording the documents may use (full names, formal terms, Chinese), then say plainly that nothing was found instead of re-querying with single characters or generic words. The rule is in both the system prompt and the tool description, and its examples deliberately avoid words from the question set so the scores are not inflated.
- When the knowledge base has nothing on the item asked about, say so first; related rules may be added with their `[n]` but must not be presented as that item.
- Do not end the answer with a separate list of sources or file names.
- The keyword description of `filter_and_count_records` reminds the model to write the full "field: value" when counting by a field. With just 「帳號」, records where another field happens to contain 「帳號」 are counted too, which is how the model answered 4 instead of 3.

### 5. Measurements

Same question set, same model (Gemma-4-26B-A4B-NVFP4, `reasoning_effort=medium`), three runs per question, graded by the same version of the judge (the same model at `low`). While the "before" answers were generated, about 13 requests from other users were running on the model server; during the "after" run, only the evaluation's own requests were.

| Metric | Before | After |
|---|---|---|
| Overall pass rate | 0.975 | 0.990 |
| Positive pass rate | 0.972 | 0.989 |
| Negative refusal rate | 1.000 | 1.000 |
| Answer facts found | 0.989 | 0.989 |
| Judged correct | 0.972 | 0.989 |
| Per-question stability (always / sometimes / never passes) | 130 / 5 / 1 | 134 / 1 / 1 |
| Answers ending with a self-made source list | 15 / 408 | 1 / 408 |
| Knowledge-base searches on negatives (mean / max) | 7.8 / 31 | 5.1 / 7 |
| Time on negatives (median / mean / max) | 74 / 91 / 302 s | 60 / 59 / 100 s |
| Time on positives (median / mean) | 12.5 / 14.4 s | 12.8 / 13.7 s |

- Questions that went from wrong to right:
  - "Is crossing the yellow line on the platform fined?" 0/3 → 3/3.
  - The counting question 1/3 → 3/3.
  - "How many years for damaging MRT facilities?" 2/3 → 3/3.
  - "WFH policy" 1/3 → 3/3; it used to tag facts from other paragraphs with [1].
- Repeating the yellow-line question ten times passed only 5/10; failing answers had the fine from the previous chunk but followed paragraph 2 (removal from the station without a refund). The neighbouring text moved this question from never answerable to mostly answerable, but it is not yet stable.
- A run made after the first round of changes overlapped with other users' requests and measured a 17.3-second median for positives. On an idle server it measured 12.8 seconds, close to the 12.5 seconds before the changes, so the longer prompts from neighbouring text add little time.
- Two questions still fail:
  - "Who is the competent authority for the MRT?" 0/3: the model rewrites the question as 「捷運主管機關」, and Article 4, which names the authorities, drops to twelfth place, outside the top 3.
  - "How do I clock in when visiting a client?" 2/3: 「拜訪客戶」 does not match 「公務外出、外勤」 in the document.

### 6. Evaluated but not adopted, or left open

| Approach | Result | Decision |
|---|---|---|
| Limiting searches through the prompt only | With "search again once or twice, then stop", 23 of 51 negative runs still used all 6 searches and were stopped by the limit, while the rest stopped on their own; none of the 357 positive runs was blocked | Keep the prompt, enforce the count in code |
| Lowering the limit to 4 | Negatives would be faster, but answerable questions such as 「加班費怎麼算」 and 「大禮堂要怎麼借」 already used 4 in the baseline, and the counting question used more | Keep 6 |
| Searching with both the original question and the model's rewrite (multi-query) | Recomputed over the 354 first searches in the baseline: the model's own queries put a correct passage in the top 3 for 0.952, the original questions for 0.946, and their union for 0.972. Rewrites handle typos and abbreviations (特修 → 特別休假, WFH → 遠端工作); original questions handle legal text (for 「捷運的主管機關是誰」 Article 4 ranks third, but the rewrite 「捷運主管機關」 drops it to twelfth) | Doubles the reranking time of every search while the positive pass rate is already above 0.97; not now |
| A synonym or abbreviation table in the domain profile | The model already rewrites: 「統編」 becomes 「統一編號」, 「WFH」 becomes 「遠端工作」; what remains, such as 「拜訪客戶」 versus 「公務外出、外勤」, is semantic paraphrase that a fixed table cannot cover | Not adopted |
| Refusing through a higher relevance threshold | ADR-0007 records that the reranker scores near-domain negatives high; answer-level refusal is already 1.000 with the model deciding | Not adopted |

---

## Consequences

### Benefits

- Changes to prompts, the research loop, or the model can be measured on the final answers, including which questions are unstable.
- Questions with no answer no longer take minutes: at most 6 knowledge-base searches, and repeated ones skip reranking.
- The model can read articles and tables that chunking cut apart, and answers no longer attach their own source lists.

### Trade-offs and risks

- **Longer tool results**: each text chunk carries two neighbouring chunks, which adds prompt tokens; with a large `top_k` and a large `CHUNK_SIZE`, results may hit `MAX_TOOL_RESULT_CHARS` (20,000 characters) and be truncated.
- **The cited excerpt may not contain the sentence**: the model may tag a fact from the neighbouring text with that chunk's `[n]`, while the source panel shows the excerpt of the matched chunk itself. The document is right, but the excerpt may not show the sentence.
- **The limit may cut off questions that need many searches**: research mode cannot search after the sixth call; heavy lookups belong in agent mode.
- **The judge is the model under test**: a model grading itself may favour its own phrasing. Grading relies mainly on the rule checks (facts, citations, searched) with the judge as a second opinion; numbers from a different judge are not comparable with this table.
- **Limits of the set**: one person wrote both the documents and the questions, and it is small (13 documents, 136 questions). When comparing settings, also measure with your own organization's documents and questions.

### Upgrade and rollback

- **Upgrade**: no `.env` changes and no index rebuild; the neighbouring text is assembled from existing chunks at query time.
- **Rollback**: switch back to the older code. The evaluation script and question set do not affect production behaviour.

---

## References

- Shahul Es, Jithin James, Luis Espinosa-Anke, Steven Schockaert. [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://arxiv.org/abs/2309.15217). EACL 2024 demo track.
- Lianmin Zheng et al. [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685). NeurIPS 2023 Datasets and Benchmarks (biases of judge models, including self-preference).
- Zackary Rackauckas. [RAG-Fusion: a New Take on Retrieval-Augmented Generation](https://arxiv.org/abs/2402.03367). 2024 (multi-query retrieval and fusion).