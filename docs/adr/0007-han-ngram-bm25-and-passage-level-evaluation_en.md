# ADR-0007: Han Unigram and Bigram Fields in BM25, Evaluated with a Chunk-Level Benchmark

[繁體中文](0007-han-ngram-bm25-and-passage-level-evaluation.md) | [English](0007-han-ngram-bm25-and-passage-level-evaluation_en.md)

## Status

Accepted - 2026-11-01

Extends the BM25 tokenization and retrieval evaluation in [ADR-0003](./0003-rrf-relevance-citations-and-tool-trust_en.md).

---

## Context and Problem Statement

1. **Evaluation was document-level only**: the evaluation tool computed only document-level hit@k and MRR. In a knowledge base where one file holds thousands of records (a social media post export, for example), every chunk belongs to the same file, so document-level metrics are always perfect and say nothing about ranking quality. The project also had no built-in reference corpus, so retrieval settings could not be compared.
2. **BM25 missed entirely when jieba mis-segmented Traditional Chinese**: jieba's built-in dictionary is mostly Simplified Chinese and often mis-segments Traditional text, for example 「大眾捷運系統」 into 「大眾捷／運系統」, 「新臺幣」 into 「新／臺／幣」, and 「喪亡者」 into 「喪／亡者」. When the query is segmented differently from the document, no term matches at all: BM25 retrieved only 79% of the relevant chunks on the enterprise document corpus and 65% on the social post corpus.
3. **Common tweaks were never measured on this project's data**: the BGE query instruction, RRF parameters, convex combination fusion, rerank weight, and relative cutoffs each have support in the literature, but none had been checked against this project's data.

---

## Decision

### 1. Separate Han unigram and bigram fields in BM25

- Besides the jieba word field, the BM25 index now has `han_unigrams` (each Han character) and `han_bigrams` (each pair of adjacent Han characters). Both take only runs of Han characters (U+3400–U+4DBF, U+4E00–U+9FFF, U+F900–U+FAFF) and never span punctuation, Latin letters, digits, or kana.
- Each of the three fields produces its own query terms; all of them are combined with OR and scored together by Whoosh BM25F, with equal weights (lowering the character fields to 0.5 or 0.3 was no better in the experiments).
- Rationale: Chinese information retrieval research shows that indexing words together with single characters or bigrams is more robust than segmentation alone, because character-level matches recover what segmentation errors lose (Nie et al., 2000; He et al., 2002). The unigram field restores recall, and the bigram field ranks chunks with the characters in sequence (「海邊」) above chunks where they are scattered (「上海…旁邊」). Both fields together did best on the social post corpus and matched the unigram field alone on the enterprise benchmark.
- `TOKENIZER_RULES_VERSION` goes from 2 to 3. Existing BM25 indexes therefore fail the tokenizer signature check, and the backend rebuilds BM25 from the database chunks on its first start; vectors are not recomputed.

### 2. Chunk-level evaluation and a built-in benchmark

- Golden sets gain an optional `relevant_passages` field: short verbatim snippets that identify the answer, where any knowledge base chunk containing one of them counts as relevant. Matching on text instead of recording chunk_ids keeps the labels valid after chunking changes or index rebuilds; a snippet that cannot be found in the knowledge base fails the evaluation instead of silently scoring zero.
- Cases with snippets also get chunk-level precision@k, nDCG@k, snippet recall@k, MRR, and **candidate recall** (whether the candidates before reranking already contain the answer). Low candidate recall is a recall problem (tune BM25, vectors, or `TOP_K`); high candidate recall with poor ranks is a reranking problem.
- `scripts/evaluate_retrieval.py --corpus <dir>` chunks the files the same way uploads do and builds the knowledge base on a temporary SQLite database and temporary indexes, without connecting to the production database; `--min-passage-ndcg` fails CI on regressions.
- Built-in benchmark: `backend/eval/corpus/` (12 fictional "Miao Technology" company documents plus the full text of Taiwan's Mass Rapid Transit Act as statute-style text and distractors, 119 chunks) and `backend/eval/corpus_golden.jsonl` (103 positive and 15 negative cases). The questions deliberately include colloquial rewording (「外婆過世」 for 「祖父母喪亡」), Simplified Chinese, typos, English abbreviations, cross-document answers, and old-versus-new distractors (the 2025 and 2026 travel policies): questions without a year count both versions as relevant, questions with a year count only that version, and every negative is a near-domain question the corpus really does not answer. A test checks that every snippet falls entirely within a chunk produced by the upload pipeline.

### 3. Measurements

Measured with the production code and the same parameters as `.env` (`TOP_K=30`, `RRF_K=60`, `RERANK_TOP_K=50`, `RERANK_WEIGHT=0.85`, `RERANK_RELEVANCE_THRESHOLD=0.02`, reranking with OpenVINO on an Intel iGPU at length 256); before and after differ only in the BM25 fields.

| Metric (chunk level) | Enterprise benchmark: before | After | Social posts (2,437): before | After |
|---|---|---|---|---|
| Candidate recall | 0.971 | **1.000** | 0.924 | **0.937** |
| precision@1 | 0.835 | 0.825 | 0.964 | 0.964 |
| nDCG@3 | 0.892 | **0.897** | 0.927 | **0.932** |
| nDCG@5 | 0.898 | **0.907** | 0.893 | **0.901** |
| Snippet recall@5 | 0.937 | **0.956** | 0.417 | **0.421** |
| MRR | 0.888 | 0.889 | 0.982 | 0.982 |
| Negative rejection rate | 0.133 | 0.133 | 0.667 | 0.667 |

- The social post corpus is not in the repository (it is data the user uploaded). Its questions are 56 topic queries and 15 negatives verified to be absent from the corpus, with relevance decided by whether a post contains one of a set of synonyms.
- On the enterprise benchmark, questions with no relevant chunk in the top 5 dropped from 6 to 4. All 4 remaining have a candidate recall of 1.0, so they are reranker misjudgments (the typo 「特修」, the English 「WFH policy」, 「統編」, and so on). precision@1 lost one question: individual ranks move as the RRF ranks change (3 questions moved down on the enterprise benchmark, while 2 went from not found to first and third), and nDCG rose overall.
- After OpenVINO reranking switched to feeding the actual number of candidates on 2026-11-02, the same benchmark was re-run: enterprise chunk-level MRR 0.892, nDCG@3 0.903, nDCG@5 0.909, and snippet recall@3 0.947, with the other metrics unchanged from the table (rerank scores differ by at most 0.007, which nudges a few ranks).
- Cost: for the 2,437 posts the BM25 index grew from 4.4 MB to 7.4 MB and the median query time from 1.0 ms to 2.6 ms, negligible next to the roughly 2.7 s of reranking per search; index build time did not change.

### 4. Approaches tried and rejected

Each was compared on both corpora, and only changes that improved both were adopted. The figures below come from the experiment harness (the same models, parameters, and chunks as production), where precision@k divides by min(k, number of relevant chunks).

| Approach | Result | Why it was rejected |
|---|---|---|
| BGE query instruction (「为这个句子生成表示以用于检索相关文章：」) | Enterprise unchanged, candidate recall 0.966 → 0.956; social posts precision@5 +0.008 | The two corpora disagree, and the BGE v1.5 model card says the instruction is optional |
| `RRF_K` of 20 or 100, weighted RRF, convex combination fusion | All within ±0.005 | No consistent gain. Convex combination beats RRF in the literature (Bruch et al., 2023), but reranking erases the difference; unweighted RRF stays |
| `RERANK_WEIGHT` of 0.7 or 1.0 | Worse on both corpora | 0.85 stays |
| Relative cutoff (drop chunks whose rerank probability is below r × the top one, a simple form of ranked list truncation) | Enterprise unchanged for r ≤ 0.2; social posts precision@5 −0.058 at r = 0.2 | Rerank probabilities of short posts vary widely, so a relative cutoff drops relevant chunks |
| Rerank input length 512 (currently 256) | Enterprise identical | A 300-character chunk plus the query stays under 256 tokens |
| Strip the field boilerplate of structured records from the rerank input | Enterprise nDCG@5 −0.015, and an earlier social post experiment was also worse | Field names help the reranker |
| `RERANK_TOP_K` of 20 | Candidate recall 0.966 → 0.950 | 50 stays |
| Raise the threshold to 0.05 or 0.1 | Higher negative rejection, but social post precision@5 falls from 0.871 to 0.781 or 0.646 | Positive short posts get low rerank probabilities; see "Negative rejection" below |

Not evaluated: Contextual Retrieval (Anthropic, 2024) has an LLM write a short context prefix for every chunk before the vector and BM25 indexes are built. It needs one model call per chunk, which raises ingestion cost and quality concerns with small local models; it is left for a later evaluation on this benchmark.

### 5. Reranker comparison: keep `bge-reranker-base`

On 2026-11-02 `BAAI/bge-reranker-base` and `BAAI/bge-reranker-v2-m3` were compared with the same pipeline (both on OpenVINO on an Intel iGPU at length 256, with this ADR's Han fields already in BM25), sweeping thresholds with `--relevance-thresholds`:

| Corpus and threshold | base precision@1 | base nDCG@5 | base negative rejection | v2-m3 precision@1 | v2-m3 nDCG@5 | v2-m3 negative rejection |
|---|---|---|---|---|---|---|
| Enterprise, threshold 0.01 | 0.835 | 0.922 | 0.067 | 0.874 | 0.907 | 0.667 |
| Enterprise, threshold 0.02 | 0.825 | 0.907 | 0.133 | 0.854 | 0.893 | 0.867 |
| Social posts, threshold 0.01 | 0.964 | 0.912 | 0.533 | 0.839 | 0.840 | 0.800 |
| Social posts, threshold 0.02 | 0.964 | 0.901 | 0.667 | 0.821 | 0.739 | 0.933 |
| Time per rerank (median / p95) | 2.75 / 3.67 s | | | 8.61 / 11.19 s | | |

- **Document knowledge bases**: v2-m3 separates its probabilities well. At threshold 0.01 its nDCG@5 matches base at 0.02 (0.907) while negative rejection rises from 0.133 to 0.667; base needs a threshold of 0.3 for 0.733 rejection, which drops nDCG@5 to 0.836.
- **Short posts**: v2-m3 gives short posts even lower probabilities, and its precision@1 and nDCG@5 trail base at every threshold; it wins only slightly at equal negative rejection (0.8), with nDCG@5 0.840 against 0.819.
- **Latency**: the model has about twice the parameters of base and reranks about 3 times slower on the Intel iGPU; the agent often searches two or three times per question, adding more than ten seconds.
- **Note (2026-11-02, after OpenVINO switched to a variable batch)**: the latencies in the table were measured with a fixed batch padded to 50 pairs on every call. After switching to sending only the actual candidates, base was rerun on the enterprise benchmark at threshold 0.02: precision@1 and negative rejection are unchanged, passage MRR went from 0.889 to 0.892, and nDCG@5 from 0.907 to 0.909. The benchmark's 118 reranks (30–50 candidates each) were recorded and replayed interleaved in one process: the fixed batch had a median of 2.73 s and p95 of 3.39 s, the variable batch 2.46 s and 3.26 s. A separate interleaved measurement on 352 sample pairs took 10 pairs from 2.83 to 0.51 s. The first time a new number of candidates appears, compilation adds about 0.3 s, so a benchmark run right after a restart is somewhat slower than the steady state. Measurements hours apart are also affected by the machine's temperature and should not be compared directly with the table. v2-m3 was not remeasured.
- **Decision**: the default stays `bge-reranker-base`. Deployments that are mostly documents, care about correct "nothing found" answers, and can accept the latency can set `RERANKER_MODEL=BAAI/bge-reranker-v2-m3` with `RERANK_RELEVANCE_THRESHOLD` around 0.01, then calibrate on their own golden set; after the switch OpenVINO converts the model again into `DATA_DIR/openvino_cache` (about 1.1 GB, plus about 1.1 GB of compiled cache).

---

## Consequences and Trade-offs

### Benefits

- BM25 still retrieves chunks when jieba mis-segments words; candidate recall rose on both corpora and reached 1.0 on the enterprise benchmark. Simplified Chinese queries can also hit some chunks through characters shared by both scripts (the 「海」 in 「海边」).
- Retrieval tuning now has a reproducible chunk-level benchmark, the report separates recall problems from ranking problems, and CI can block regressions with `--min-passage-ndcg`.

### Trade-offs & Risks

- **Character-level noise**: unigram matches bring in chunks that merely share characters, which RRF ranks and the reranker have to filter out; individual questions change rank.
- **Larger index**: every Han character and every pair of adjacent Han characters is a term, so the BM25 index is about 70% larger.
- **Negative rejection remains weak and is not solved here**: `bge-reranker-base` scores near-domain negatives high (on the enterprise benchmark the negatives' top rerank probabilities have a median of 0.12 and a maximum of 0.74), while positive short posts score low (median 0.37), so no single threshold suits both corpora. `RERANK_RELEVANCE_THRESHOLD` must still be calibrated on real data with `--relevance-thresholds`; see section 5 above for the trade-offs of switching to `bge-reranker-v2-m3`.
- **Benchmark limits**: the same person wrote the enterprise documents and questions; despite deliberate rewording, the questions may lean toward literal overlap, and 119 chunks is smaller than a real deployment. Compare settings against your own golden set as well.

### Upgrade and Rollback

- **Upgrade**: no new settings. On the first start the backend logs that the BM25 tokenizer signature differs and rebuilds BM25 from the database chunks (about 6 seconds for 2,437 chunks); vectors are not recomputed. Read-only evaluation refuses to run until the backend has started once and finished the rebuild.
- **Rollback**: older code cannot load the analyzer classes stored in the new index, so it fails to load it and rebuilds BM25 from the database chunks; there is no need to delete the index by hand.

---

## References

- Jian-Yun Nie, Jianfeng Gao, Jian Zhang, Ming Zhou. [On the Use of Words and N-grams for Chinese Information Retrieval](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/words_ngrams_chinese_learning.pdf). IRAL 2000.
- Hongzhao He, Jianfeng Gao, Pilian He, Changning Huang. [Finding the Better Indexing Units for Chinese Information Retrieval](https://aclanthology.org/W02-1804/). First SIGHAN Workshop on Chinese Language Processing, 2002.
- Sebastian Bruch, Siyu Gai, Amir Ingber. [An Analysis of Fusion Functions for Hybrid Retrieval](https://arxiv.org/abs/2210.11934). ACM TOIS, 2023.
- Gordon V. Cormack, Charles L. A. Clarke, Stefan Büttcher. Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods. SIGIR 2009.
- Dara Bahri, Yi Tay, Che Zheng, Donald Metzler, Andrew Tomkins. [Choppy: Cut Transformer for Ranked List Truncation](https://arxiv.org/abs/2004.13012). SIGIR 2020.
- Anthropic. [Introducing Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval). 2024.
- BAAI. [bge-small-zh-v1.5 model card](https://huggingface.co/BAAI/bge-small-zh-v1.5) (query instruction and v1.5 notes).
