# ADR-0001: Contextual Hybrid RAG & Dual-Token Security Architecture

[繁體中文](0001-hybrid-rag-and-security.md) | [English](0001-hybrid-rag-and-security_en.md)

## Status

Accepted - 2026-08-01

---

## Context & Problem Statement

As an intelligent conversational and multi-Agent collaboration system, AskMiao faced two core technical challenges regarding retrieval precision and authentication security:

1. **Limitations of Single Retrieval Approaches**:
   - Pure dense vector search excels at semantic similarity but misses exact technical terms, proper names, or model codes, occasionally introducing hallucinations.
   - Pure sparse keyword search (e.g. BM25) excels at exact matching but lacks semantic understanding and synonym expansion.
2. **Authentication Security & Credential Leakage Prevention**:
   - Long-lived single JWT tokens pose security risks if intercepted, whereas pure session-based auth scales poorly in async microservices.
   - System logs risk inadvertently printing user passwords or API secrets, triggering CodeQL security alerts.

---

## Decision Outcome

After evaluation, the engineering team adopted the following architectural solution:

### 1. Contextual Hybrid RAG Pipeline

- Combines **FAISS dense vector retrieval** (powered by `BAAI/bge-small-zh-v1.5`) and **Whoosh BM25 keyword search** (with `Jieba` segmentation).
- ~~Merges candidate passages via score normalization fusion~~ (**superseded**: since 2026-09-24 both tracks always run and are merged with standard RRF, see [ADR-0003](./0003-rrf-relevance-citations-and-tool-trust_en.md)) and re-ranks Top-K contexts using a **Cross-Encoder model (`bge-reranker-base`)**.

### 2. RSA-2048 Dual-Token Auth & Redis Revocation Blacklist

- **Access Token**: Signed with RSA-2048 private key, 30-minute expiration, transmitted via Authorization header.
- **Refresh Token**: HttpOnly / Secure / SameSite Cookie, 7-day expiration.
- **Instant Revocation**: Blacklists Access Token JTI in Redis upon logout.

### 3. Two-Layer Sensitive Data Redaction (`security_logging.py`)

- Object-level recursive key masking via `sanitize_sensitive_data`.
- Secondary string-level regex filter applied prior to JSON logging, turning sensitive fields into `[REDACTED]`.

---

## Consequences & Trade-offs

### Positive Consequences

- **Significant Accuracy Boost**: Hybrid RAG with re-ranking drastically reduces hallucinations and improves exact domain-keyword retrieval.
- **Enhanced Security Profile**: Silent refresh balances UX with short-lived tokens, while two-layer log masking eliminates credential leakage risks and satisfies CodeQL audits.

### Negative Consequences & Risks

- **Increased System Complexity**: Backend must manage both FAISS vector indices and Whoosh text index files.
- **Computation Latency**: Cross-Encoder re-ranking adds dozens of milliseconds per query, mitigated by caching frequent queries in Redis.

---

## Amendments

- **2026-08-24 | Token revocation list moved in-process**: the architecture lightening pass dropped the Redis dependency; `TokenBlacklist` in `app/core/redis_client.py` now keeps the revocation list in process memory and prunes expired entries automatically. Trade-off: no external service is required, but the list resets on backend restart (unexpired tokens become valid again), and a multi-process deployment would need shared storage again.
- **2026-08-24 | Multi-agent collaboration board removed**: the project focuses on knowledge base Q&A and agentic research; the discussion board and workflow module were retired.
- **2026-09-01 | Outbound request safety**: the security design for external calls is now governed by [ADR-0002](./0002-external-tools-and-outbound-safety_en.md).
- **2026-09-24 | Score normalization fusion superseded**: fusion now runs both tracks every time and merges them with standard RRF, the relevance threshold applies to the reranker probability, and the reranker is a required component; see [ADR-0003](./0003-rrf-relevance-citations-and-tool-trust_en.md). Measured CPU reranking takes about 0.2 to 0.4 s per pair, far above the tens of milliseconds estimated above.
- **2026-09-24 | Chunks keyed by database chunk_id**: chunks live in the `rag_chunks` table, FAISS moves to `IndexIDMap2` and is keyed by chunk_id together with BM25, and startup reconciles both against the database, replacing the position-aligned `documents.pkl`; see [ADR-0005](./0005-chunk-id-index-and-database-source-of-truth_en.md).
