# ADR-0003: RRF Fusion, Relevance Threshold, Citations, and Tool-Output Trust Boundary

[繁體中文](0003-rrf-relevance-citations-and-tool-trust.md) | [English](0003-rrf-relevance-citations-and-tool-trust_en.md)

## Status

Accepted - 2026-09-24

Supersedes the "score normalization fusion" decision in [ADR-0001](./0001-hybrid-rag-and-security_en.md).

---

## Context and Problem Statement

1. **Dual-track retrieval existed in name only**: queries were first routed by hard-coded rules (pure English to BM25 only, long Chinese sentences to vectors only, hybrid only when FAQ keywords matched), and hybrid mode weighted normalized scores with `HYBRID_ALPHA = 0.75`. A chunk found only by BM25 landed behind the top 30 vector results even when it ranked first, so it never reached the reranker's short list.
2. **The threshold always passed something**: the threshold applied to "0.85 × rerank score + 0.15 × original score", and the top candidate's normalized original score is always 1. Even a chunk the reranker judged irrelevant scored exactly 0.15 and passed, so at least one chunk always reached the model; a reranking failure returned unfiltered chunks outright.
3. **Source badges were unrelated to the answer**: the badges listed every retrieved chunk (the first 6), not what the answer actually used.
4. **No trust boundary for tool output**: tool results went into the conversation verbatim, so documents or pages could carry prompt injection, and the model could put internal data from the knowledge base or the conversation into a `web_fetch` URL.
5. **Latency**: questions that used tools discarded the answer the model had already produced, generated it again in full, and sent it as fake streaming with a 15 ms pause every 4 characters.
6. **Tokenization and domain data**: BM25 was case-sensitive (`mes` did not match `MES`), and domain words, record date fields, and summary fallback rules were hard-coded.
7. **Accidental deletion**: the uploads watcher deleted index and database records when an uploaded file went missing, while relative path settings resolved against the working directory, so starting the backend from another directory marked every document as missing.

---

## Decision

### 1. Standard RRF with both tracks always running

- Every query takes `TOP_K` results from both vector search and BM25 and merges them by rank with Reciprocal Rank Fusion: score = Σ 1 / (`RRF_K` + rank); the top `RERANK_TOP_K` go to the reranker.
- Fusion is **unweighted** standard RRF; `HYBRID_ALPHA`, `NORMALIZATION`, and `auto_tune_alpha` are removed. A weighted RRF that kept alpha was considered, but keeping 0.75 would reproduce problem 1 (the BM25 top result ranked behind the top 30 vector results), and there is no golden set yet to calibrate a weight.
- Exact matches on URLs, post IDs, dates, and @accounts are added as candidates and ranked first.

### 2. Relevance threshold on the reranker probability

- `RERANK_RELEVANCE_THRESHOLD` (replacing `FINAL_THRESHOLD`) applies directly to the reranker's probability; the mixed score is used only for ordering.
- Exact URL, post ID, and date matches are exempt, because a query that is just a URL naturally gets a low rerank score.
- The reranker is a required component: the backend refuses to start if it cannot load, and a reranking failure at query time returns an error code instead of unfiltered chunks.
- When no chunk passes, `search_knowledge_base` explicitly returns "知識庫中查無相關資料" (no relevant data in the knowledge base); a `target_document` restricts candidates before reranking and never falls back to the whole library.
- The golden set accepts negatives (`"relevant_sources": []`), and the evaluation CLI compares several thresholds over a single rerank pass with `--relevance-thresholds` (positive hit@k and MRR, negative rejection rate).

### 3. Citations mapped to sources

- Each question builds a citation table keyed by chunk_id for knowledge-base chunks and by URL for web pages; a number is assigned on first appearance, written into the tool result, and reused when the same item appears again.
- The system prompt requires `[n]` citations using only numbers from tool results; after the answer completes, `[n]` markers (including `[1,2]` and `[1][2]`) are parsed and only the cited entries are listed, deduplicated in order of first citation. An answer without citations shows no source badges.

### 4. Tool-output trust boundary

- Every tool result is wrapped in an `<untrusted_tool_result>` marker whose id changes per question; the system prompt says to treat it as data only, never to follow instructions inside it, and never to put conversation or knowledge-base content into URLs or search strings.
- `web_fetch` may only read URLs that appear verbatim in the user's messages or in the data fields of this question's built-in tool results. Query arguments echoed by a tool are not a source, so the model cannot first smuggle data into a query and then fetch it as a URL that "appeared".
- `WEB_FETCH_ALLOWED_DOMAINS` is a domain allowlist (subdomains included) where only an explicit `*` means unrestricted; with `BLOCK_WEB_TOOLS_AFTER_KB` enabled, once a knowledge-base tool returns content in a question, later web tool calls are refused.

### 5. Related decisions

- When the model stops calling tools, that response is the final answer and is not regenerated; fake streaming is removed, and real streaming is used only when the turn limit is reached or the model returns empty content.
- Tokens are always lowercased; `JIEBA_DICTIONARY` can replace the main dictionary; the BM25 index directory records a tokenizer signature (rules version, main-dictionary hash, domain-words hash), BM25 is rebuilt automatically on a mismatch, and read-only evaluation refuses to run.
- Domain words, record date fields, and summary fallback rules move to the profile at `DOMAIN_PROFILE_PATH` (`backend/config/domain_profile.json`), validated at startup.
- Relative path settings are always resolved against `backend/`; the uploads watcher only logs one warning when a file goes missing and deletes neither index nor database records (document content already lives in the database, and index rebuilds fall back to it).

---

## Consequences

### Benefits

- Chunks found by only one track reach the reranker, so queries for proper nouns and identifiers are no longer drowned out by weighting.
- Off-topic questions get an explicit "no data" instead of always receiving irrelevant chunks, and a reranking failure never hands unfiltered content to the model.
- Source badges map one-to-one to the answer, so users can check each claim against its source.
- Prompt injection in tool results cannot rewrite the rules, and the model cannot assemble internal data into a URL to send it out.
- Questions that use tools save one full LLM call and the fake-streaming delay.

### Trade-offs & Risks

- **Rerank latency**: measured on CPU at about 0.2 s per pair for 300-character chunks and 0.4 s for 800-character chunks, so with `RERANK_TOP_K = 20` each knowledge-base search takes about 4 to 8 seconds. Exact-match candidates keep the previous behaviour and are not capped by `RERANK_TOP_K`, so dates or @accounts matching many chunks add more cost.
- **Recall risk of the threshold**: on a small corpus, the reranker scored paraphrases (for example "ChatGPT" against "generative AI services") and single-keyword queries low, and positives and negatives overlapped between 0.3 and 0.42. `0.2` is a provisional value that must be calibrated with `--relevance-thresholds` on a real golden set.
- **Streaming experience**: answers after tool use appear in one piece instead of token by token, although sooner than before.
- **Stricter startup**: the backend refuses to start if the reranker cache is missing and cannot be downloaded, or if the new required settings are missing from `.env`.
- **Web restrictions**: with `BLOCK_WEB_TOOLS_AFTER_KB` on, a question that has read the knowledge base cannot go online afterwards; URL provenance requires a verbatim match, so a rewritten URL (for example with an added trailing slash) is refused; the domain allowlist checks only the initial URL, not redirect targets.
- **Known risk**: results from custom API and MCP tools are wrapped as untrusted but feed neither URL provenance nor citations, and their outbound requests are outside the limits of this decision.

### Upgrade and rollback

- **Upgrade**: add `RRF_K`, `RERANK_RELEVANCE_THRESHOLD`, `WEB_FETCH_ALLOWED_DOMAINS`, `BLOCK_WEB_TOOLS_AFTER_KB`, and `DOMAIN_PROFILE_PATH` to `.env` before starting. The old `HYBRID_ALPHA`, `NORMALIZATION`, and `FINAL_THRESHOLD` are ignored. On the first start the existing BM25 index has no tokenizer signature, so BM25 is rebuilt from the database chunks automatically without recomputing vectors.
- **Rollback**: delete the `BM25_INDEX_DIR` directory before reverting to the old code, and the old version rebuilds BM25 from the database at startup. Otherwise the old version matches non-lowercased queries against the lowercased index, and terms with capital letters (such as `MES`) no longer match.
