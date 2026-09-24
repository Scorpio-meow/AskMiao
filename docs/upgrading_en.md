# Upgrade Guide

[繁體中文](upgrading.md) | [English](upgrading_en.md)

> How to upgrade an existing deployment to a new release, with rollback steps and troubleshooting. See the [CHANGELOG](../CHANGELOG_en.md) for the full list of changes in each version.

- [Upgrading from 2.x to 3.0.0](#upgrading-from-2x-to-300)
  - [Overview](#overview)
  - [Step 0: stop and back up](#step-0-stop-and-back-up)
  - [Step 1: update code and dependencies](#step-1-update-code-and-dependencies)
  - [Step 2: update `.env`](#step-2-update-env)
  - [Step 3: start the backend and rebuild the index](#step-3-start-the-backend-and-rebuild-the-index)
  - [Step 4: check admins and tool settings](#step-4-check-admins-and-tool-settings)
  - [Step 5: verify the upgrade](#step-5-verify-the-upgrade)
  - [Rolling back to 2.2.x](#rolling-back-to-22x)
  - [Troubleshooting](#troubleshooting)

---

## Upgrading from 2.x to 3.0.0

3.0.0 is a major release with incompatible changes to the index format, the required settings, and tool management permissions. The hands-on work takes about 15 minutes, plus one index rebuild: the rebuild re-extracts text, asks the LLM for a new summary, and embeds every document, so its duration grows with the size of your library.

### Overview

| Area | 2.2.x | 3.0.0 | Action |
|---|---|---|---|
| Chunks and indexes | FAISS, `documents.pkl`, and BM25 aligned by list position | The `rag_chunks` table is the source of truth; FAISS and BM25 are keyed by chunk_id | Rebuild the index once after upgrading |
| Retrieval fusion | Weighted normalized scores (`HYBRID_ALPHA`) | Standard RRF (`RRF_K`) plus a reranker probability threshold | Add the new settings |
| Required settings | 3 | 11 | Add 8 |
| Reranker | Skipped when it failed to load | Required; the backend refuses to start without it | Make sure the model cache or network is available |
| Tool management | Any signed-in user | Admins only | Make sure at least one admin exists |
| MCP `stdio` environment | Inherited the whole backend environment | Inherits essential system variables only | Put the variables a server needs in its `env_vars` |
| MCP HTTP URLs | Not validated | SSRF-validated on every request and redirect | Switch loopback or intranet servers to `stdio` |
| Hugging Face cache | Defaulted to `./data/hf_home` | `~/.cache/huggingface` when unset | Set `HF_HOME` explicitly to keep the old cache |
| Built-in model lists | GPT-4o, o-series, and others | GPT-6 / GPT-5.6, Claude 5 family, Gemini 3.x | List older models in `AVAILABLE_MODELS` |

### Step 0: stop and back up

The upgrade rewrites index files, so stop the backend first and back up:

- **Database**: copy the `.db` file for SQLite; use `pg_dump` for PostgreSQL.
- **`backend/data/`**: the vector index `faiss_index.bin`, `documents.pkl`, `index_metadata.pkl`, `bm25_index/`, the uploads in `uploads/`, and the model cache `hf_home/` if present.
- **`backend/.env`**.

### Step 1: update code and dependencies

```bash
# after checking out the 3.0.0 code
cd backend
pip install -r requirements.txt   # 3.0.0 adds the official anthropic SDK

cd ../frontend
bun install
```

### Step 2: update `.env`

#### New required settings

These 8 settings have no defaults, and the backend refuses to start if any is missing. The recommended values match `backend/.env.example`:

| Setting | Recommended | Description |
|---|---|---|
| `ENABLE_WEB_SEARCH` | `true` | Offer the `web_search` and `web_fetch` web tools |
| `AGENT_MAX_TURNS` | `5` | Maximum tool-calling turns per question (≥ 1) |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | Prior messages loaded from the database as context (0 disables) |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | Domains `web_fetch` may read (subdomains included, comma-separated); only an explicit `*` means unrestricted |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | Refuse web tools once knowledge-base content has been read in the same question |
| `RRF_K` | `60` | RRF fusion constant |
| `RERANK_RELEVANCE_THRESHOLD` | `0.2` | Chunks whose reranker probability falls below this are irrelevant (provisional value; see [calibrating the threshold](configuration_en.md#calibrating-the-relevance-threshold)) |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | Domain profile path (relative paths resolve against `backend/`) |

Ready to paste into `.env`:

```dotenv
ENABLE_WEB_SEARCH=true
AGENT_MAX_TURNS=5
CONVERSATION_HISTORY_MESSAGES=6
WEB_FETCH_ALLOWED_DOMAINS=*
BLOCK_WEB_TOOLS_AFTER_KB=true
RRF_K=60
RERANK_RELEVANCE_THRESHOLD=0.2
DOMAIN_PROFILE_PATH=config/domain_profile.json
```

> [!IMPORTANT]
> Claude models also need `ANTHROPIC_MAX_TOKENS` (for example `16000`); without it every Claude call fails with a message asking you to set it in `.env`.

#### Settings you can delete

These settings were removed and are ignored if left in `.env`:

`HYBRID_ALPHA`, `NORMALIZATION`, `FINAL_THRESHOLD`, `DOCUMENTS_PATH`, `ENABLE_AUTO_REINDEX`, `ENABLE_AUTO_REINDEX_TASK`, `REINDEX_HOURS`, `TRANSFORMERS_CACHE`, `HUGGINGFACE_HUB_CACHE`.

#### Behavior changes to review

- **Hugging Face cache**: 2.2.x stored models in `./data/hf_home` by default; 3.0.0 uses `~/.cache/huggingface` when `HF_HOME` is unset. To reuse the existing cache and avoid downloading the embedding and reranker models again (about 1.2 GB), set `HF_HOME=./data/hf_home`; `HUGGINGFACE_HUB_CACHE` is now `HF_HUB_CACHE`.
- **Default models**: `OPENAI_VISION_MODEL` now defaults to `gpt-6-sol` and `GEMINI_VISION_MODEL` to `gemini-3.5-flash` (both are used for OCR of scanned PDF pages), and the built-in lists no longer include `gpt-4o`, `o1`, `o3`, `gemini-2.5-flash`, and other older models. To keep using them, name them in `AVAILABLE_MODELS` and in those two settings.
- **Relative paths**: relative values of `DATA_DIR`, `UPLOAD_DIR`, the index paths, `HF_*`, `DOMAIN_PROFILE_PATH`, and `JIEBA_DICTIONARY` always resolve against `backend/`, no longer against the startup directory.
- **`RERANK_TOP_K`**: the code default is 50 and `.env.example` suggests 20. Reranking costs about 0.2 to 0.4 seconds per pair on CPU, so more candidates make every search slower.

The [configuration reference](configuration_en.md) documents every setting.

### Step 3: start the backend and rebuild the index

```bash
cd backend
python main.py
```

On the first start you will see, in order:

1. **Settings validation**: missing required settings stop startup with a `Field required` error that names each missing field.
2. **Model loading**: the embedding and reranker models; if the reranker cannot load, startup ends with a "cannot load the reranker model" error (logged in Chinese as 無法載入重排模型).
3. **Legacy index detected**: the log reports the old position-aligned FAISS format, and the file is renamed to `faiss_index.bin.legacy.bak`.
4. **An empty knowledge base for now**: the new `rag_chunks` table has no chunks yet, so existing documents are not searchable until you rebuild.

Rebuild the index in one of these ways:

| Method | How | Best for |
|---|---|---|
| Frontend | Sign in as an admin → Knowledge base (知識庫) → Rebuild index (重建索引) | Small libraries, seeing the result on screen |
| API | `POST /api/documents/rebuild-index` with an admin access token | Automated deployments |
| Offline script | **With the backend stopped**, run `python scripts/reprocess_existing_docs.py` in `backend/` | Large libraries, keeping the live service free |

```bash
# API method
curl -X POST http://localhost:8001/api/documents/rebuild-index \
  -H "Authorization: Bearer <admin access_token>"
```

For every document in the database the rebuild re-extracts text from `UPLOAD_DIR` (falling back to the stored content when the file is gone), regenerates the AI summary, chunks it with the current `CHUNK_SIZE` / `CHUNK_OVERLAP`, and writes `rag_chunks`, FAISS, and BM25. Once answers look right, you can delete `faiss_index.bin.legacy.bak` and `documents.pkl` from `backend/data/`.

> [!NOTE]
> You will not need manual rebuilds after this: every startup reconciles FAISS and BM25 against `rag_chunks`, and switching to an embedding model with a different vector dimension renames the old index to `*.mismatch.bak` and re-embeds automatically.

### Step 4: check admins and tool settings

- **At least one admin**: the AI tools, knowledge base, and admin dashboard pages are admin-only. If you have no admin yet, follow [README: create the first admin](../README_en.md#4-create-the-first-admin).
- **MCP `stdio` servers**: subprocesses inherit only essential system variables (`PATH`, `SYSTEMROOT`, `USERPROFILE`, and a few more on Windows; `HOME`, `PATH`, `SHELL`, and a few more elsewhere). Servers that relied on backend variables (such as `HTTP_PROXY`, `HTTPS_PROXY`, `NODE_EXTRA_CA_CERTS`, or access tokens) need those variables in their `env_vars`; then run discovery again.
- **MCP HTTP servers**: servers on `localhost` or intranet addresses fail discovery, and `last_error` shows the SSRF rejection reason. Use the `stdio` transport for local MCP servers.
- **Custom API tools**: every redirect of an outbound request is SSRF-validated again, so APIs that redirect into the intranet are rejected (the test result reports `status_code` `403`).

### Step 5: verify the upgrade

- [ ] `GET http://localhost:8001/health` returns `{"status": "healthy"}`.
- [ ] `http://localhost:8001/docs` is titled "AskMiao API" with version `3.0.0`.
- [ ] As an admin, `GET /api/admin/vector-store/info` reports `index_type` `FAISS IndexIDMap2(IndexFlatIP) + Whoosh BM25` and `total_vectors` above 0.
- [ ] A question the knowledge base covers gets `[n]` citations, and the source badges open the cited chunks.
- [ ] A question the knowledge base does not cover gets an honest "nothing relevant" answer instead of a made-up one.
- [ ] (Recommended) Run `python scripts/evaluate_retrieval.py --golden <golden set> --k 1 3 5 --relevance-thresholds 0.1 0.2 0.3` on a real golden set to calibrate `RERANK_RELEVANCE_THRESHOLD`.

### Rolling back to 2.2.x

1. Stop the backend and check out the 2.2.x code.
2. Restore `backend/data/` and `.env` from the Step 0 backup. The FAISS index written by 3.0.0 is keyed by chunk_id, which 2.2.x cannot use correctly.
3. For the database, pick one:
   - **Restore the backup**: the cleanest option, but conversations and documents added after the upgrade are lost.
   - **Keep the current database**: 2.2.x ignores the `rag_chunks` table. Documents added after the upgrade are missing from the restored index, so call `POST /api/documents/rebuild-index` on 2.2.x to rebuild it.

### Troubleshooting

<details>
<summary><b>Startup fails with <code>Field required</code></b></summary>

A required setting is missing from `.env`. The error names each missing field; add them as described in [Step 2](#step-2-update-env).

</details>

<details>
<summary><b>Startup fails because the reranker cannot load</b></summary>

The reranker is required in 3.0.0. Check that:

- `RERANKER_MODEL` is correct (default `BAAI/bge-reranker-base`).
- The first start can reach Hugging Face and `HF_HUB_OFFLINE` is not `true`.
- `HF_HOME` points at the old cache directory if you want to reuse it.

</details>

<details>
<summary><b>Every question reports that the knowledge base has nothing relevant</b></summary>

First confirm the index was rebuilt (`total_vectors` above 0 in `GET /api/admin/vector-store/info`). If the index is fine, the relevance threshold may be too high: `0.2` is a provisional value from a small corpus, so calibrate it with `scripts/evaluate_retrieval.py --relevance-thresholds` on a real golden set.

</details>

<details>
<summary><b>Regular users cannot see the AI tools page</b></summary>

This is expected in 3.0.0. Tools are shared by every user's agent and `stdio` servers run commands on the host, so only admins manage them; regular users can still let the agent use enabled tools in chat. See [ADR-0004](adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md).

</details>

<details>
<summary><b>An MCP server shows the <code>error</code> status</b></summary>

Check the server's `last_error`:

- It mentions SSRF or an intranet address: the server is local or on the intranet; switch it to the `stdio` transport.
- It shows an error code: most likely the `stdio` subprocess is missing a variable it used to inherit from the backend. Add it to `env_vars` and run discovery again; the error code maps to the full exception in the server log.

</details>
