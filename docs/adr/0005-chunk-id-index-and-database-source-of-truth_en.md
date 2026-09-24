# ADR-0005: Chunk Index Keyed by Database chunk_id

[繁體中文](0005-chunk-id-index-and-database-source-of-truth.md) | [English](0005-chunk-id-index-and-database-source-of-truth_en.md)

## Status

Accepted - 2026-09-24

Extends [ADR-0001](./0001-hybrid-rag-and-security_en.md): hybrid retrieval with FAISS and BM25 stays, while where chunks are stored and how indexes refer to them changes. This record was written at the 3.0.0 release (2026-09-25) from the implementation of that date.

---

## Context

In 2.x, chunks lived in three places, matched to each other by "the n-th item in the list":

- `documents.pkl`: the chunk list, pickled.
- FAISS `IndexFlatIP`: a vector's id was its insertion order.
- Whoosh BM25: `doc_id` was the chunk's position in the list.

This design caused four problems:

1. **Misalignment**: any failed write or load (for example `documents.pkl` failing to load and being cleared), a document deletion, or two uploads writing at once broke the shared order. After that, searches returned the wrong chunks without any error.
2. **Deletion cost**: `IndexFlatIP` cannot remove vectors by id, so deleting one document re-embedded every remaining chunk and rebuilt BM25.
3. **No way to reconcile**: chunks existed only in files, so they could not be checked against the `documents` table, and there was no way to tell whether the indexes matched the data; the only remedy was a daily full rebuild (`ENABLE_AUTO_REINDEX_TASK`, `REINDEX_HOURS`).
4. **Blocking**: searches, writes, and the scheduled rebuild ran synchronously on the event loop, so every other request stalled while a large document was embedded or the index was rebuilt.

---

## Decision

### 1. The database is the single source of truth for chunks

- A new `rag_chunks` table (`id`, `document_id`, `chunk_index`, `content`, `chunk_metadata`), where `id` is the chunk_id.
- `documents.pkl` and the `DOCUMENTS_PATH` setting are removed.

### 2. Indexes are keyed by chunk_id

- FAISS uses `IndexIDMap2(IndexFlatIP)` and adds or removes vectors by chunk_id with `add_with_ids` and `remove_ids`; BM25 stores the chunk_id in `doc_id`.
- Deleting a document removes only its chunks, vectors, and BM25 entries and leaves every other chunk alone.

### 3. A fixed write order

- New chunks are written under one lock, in order: embed → insert into `rag_chunks` and obtain ids (not yet committed) → add to FAISS under those ids → commit (on failure, remove the just-added vectors) → add to BM25 → write the index files back through temporary files that replace the originals.
- Searches hold the same lock; searches and writes run in worker threads and no longer block the event loop.

### 4. Reconcile against the database at startup instead of rebuilding on a schedule

- Every startup treats `rag_chunks` as authoritative: it deletes chunks whose document no longer exists, removes surplus ids from FAISS, and embeds missing vectors; when the BM25 chunk_id set differs from the database, BM25 is rebuilt from it.
- The daily rebuild task and the `ENABLE_AUTO_REINDEX`, `ENABLE_AUTO_REINDEX_TASK`, and `REINDEX_HOURS` settings are removed.

### 5. Legacy indexes are not converted

- A FAISS index in the old format (anything other than `IndexIDMap2`) is renamed to `*.legacy.bak` and kept, without conversion: the old index may already be misaligned, and converting it would carry that misalignment into the new structure. After upgrading, `POST /api/documents/rebuild-index` re-chunks and re-embeds from the `documents` table.
- When a new embedding model changes the vector dimension, the old index is renamed to `*.mismatch.bak` and vectors are recomputed from the database chunks.

---

## Consequences

### Benefits

- **Search results always map to the right chunks**: a lost or corrupted index is restored from the database on the next startup.
- **Deletion cost scales with the document**: deleting one document no longer re-embeds the whole knowledge base.
- **Citations have a stable key**: the citation numbers of [ADR-0003](./0003-rrf-relevance-citations-and-tool-trust_en.md) are keyed by chunk_id, so a chunk keeps one number throughout a question.
- **No scheduled rebuilds**, and searches and writes no longer block other requests.

### Trade-offs & Risks

- **Chunk text is stored twice**: both the database and the BM25 index keep the full text, using more space.
- **Upgrading requires one full rebuild**: old indexes cannot be reused, and the rebuild asks the LLM for a new summary of every document, so it takes longer with more documents.
- **Startup time**: reconciliation reads every chunk, and when many vectors are missing the first start embeds them before serving.
- **The lock only covers one process**: it is an in-process `threading.RLock`. Several workers or hosts writing the same index files overwrite each other's changes, so only one backend process may write the index.
- **SQLite foreign keys**: SQLite does not enforce foreign keys by default, so deleting a document row does not cascade to its chunks. The normal flow deletes chunks before the document, and the orphan cleanup at startup covers the exceptions.

### Upgrade & Rollback

- **Upgrade**: follow the [upgrade guide](../upgrading_en.md). After the first start renames the old index to `faiss_index.bin.legacy.bak`, run one full rebuild; once answers look right, delete `faiss_index.bin.legacy.bak` and `documents.pkl`.
- **Rollback**: restore `backend/data/` from the pre-upgrade backup. The `rag_chunks` table can stay; older versions do not read it.
