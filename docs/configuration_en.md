# AskMiao Configuration Reference

[繁體中文](configuration.md) | [English](configuration_en.md)

> Every setting in the backend `backend/.env` and the frontend `frontend/.env`, with its default and what it actually does, as of **3.0.0**. The source of truth is `Settings` in `backend/app/core/config.py`; the template is [`backend/.env.example`](../backend/.env.example).

- [How settings are read](#how-settings-are-read)
- [Required settings](#required-settings)
- [LLM providers and models](#llm-providers-and-models)
- [Agent and web tools](#agent-and-web-tools)
- [Retrieval, reranking, and chunking](#retrieval-reranking-and-chunking)
- [Compute devices](#compute-devices)
- [Hugging Face model cache](#hugging-face-model-cache)
- [Storage paths and uploads](#storage-paths-and-uploads)
- [Database](#database)
- [Authentication and tokens](#authentication-and-tokens)
- [Network access control](#network-access-control)
- [Server and runtime](#server-and-runtime)
- [Reserved settings](#reserved-settings)
- [Removed settings](#removed-settings)
- [Domain profile](#domain-profile)
- [Calibrating the relevance threshold](#calibrating-the-relevance-threshold)
- [Frontend environment variables](#frontend-environment-variables)

---

## How settings are read

- **Source**: the backend reads `backend/.env` regardless of the startup directory, and process environment variables take precedence over `.env`. Unknown keys are ignored, so removed settings left in `.env` cause no errors.
- **Required settings have no defaults**: if any is missing, the backend stops at startup with a `Field required` error that names the missing fields.
- **Value ranges**: `AGENT_MAX_TURNS ≥ 1`, `CONVERSATION_HISTORY_MESSAGES ≥ 0`, `RRF_K ≥ 1`, `0 ≤ RERANK_RELEVANCE_THRESHOLD ≤ 1`, and `ANTHROPIC_MAX_TOKENS ≥ 1`; out-of-range values also stop startup.
- **Booleans**: `true` / `false`, `1` / `0`, and `yes` / `no` all work.
- **Relative paths**: relative values of `DATA_DIR`, `UPLOAD_DIR`, `FAISS_INDEX_PATH`, `BM25_INDEX_DIR`, `METADATA_PATH`, `HF_HOME`, `HF_HUB_CACHE`, `SENTENCE_TRANSFORMERS_HOME`, `DOMAIN_PROFILE_PATH`, and `JIEBA_DICTIONARY` always resolve against `backend/`. `DATABASE_URL` is not one of them: a relative SQLite path depends on the startup directory.
- **Code default versus template value**: in the tables below, "Code default" applies when `.env` does not set the key, and "Template" is the value suggested by `backend/.env.example`; your `.env` wins whenever they differ.

## Required settings

| Variable | Template | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@localhost:5432/chatbot` | Database connection string; see [Database](#database) |
| `JWT_SECRET_KEY` | `your_jwt_secret_key_here` | HS256 signing key used when the RSA keys are unavailable; replace with a random string |
| `ADMIN_API_KEY` | `your_admin_api_key_here` | Admin API key (required by settings validation, currently unused by any route); replace with a random string |
| `ENABLE_WEB_SEARCH` | `true` | Offer the web tools |
| `AGENT_MAX_TURNS` | `5` | Tool-calling turn limit per question |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | Prior messages loaded as context |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | `web_fetch` domain allowlist |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | Disable web tools after knowledge-base content was read |
| `RRF_K` | `60` | RRF fusion constant |
| `RERANK_RELEVANCE_THRESHOLD` | `0.2` | Reranker probability threshold |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | Domain profile path |

Claude models also require `ANTHROPIC_MAX_TOKENS` (without it Claude calls fail, but startup is unaffected).

## LLM providers and models

| Variable | Code default | Template | Description |
|---|---|---|---|
| `LLM_API_BASE` | `http://localhost:5000` | `http://localhost:11434` | Ollama base URL, used to call Ollama models (`/api/chat`) and to query remote model lists (`/api/tags`) |
| `LLM_TIMEOUT` | `120` | `120` | LLM call timeout in seconds, also used for the vision model calls of PDF OCR |
| `MODEL_NAME` | empty | — | Default model; when unset, the "default model" rule below applies |
| `AVAILABLE_MODELS` | empty | commented example | Models offered to the frontend (comma-separated); when set, it fully replaces the generated list |
| `OLLAMA_TEMPERATURE` | empty | `0.3` | Ollama `temperature`; model default when unset |
| `OLLAMA_NUM_PREDICT` | empty | `2048` | Ollama `num_predict`; model default when unset |
| `AZURE_OPENAI_API_KEY` | empty | commented example | Azure OpenAI is enabled only when this and `AZURE_OPENAI_ENDPOINT` are both set |
| `AZURE_OPENAI_ENDPOINT` | empty | commented example | For example `https://<resource>.openai.azure.com`; calls `/openai/v1/chat/completions` |
| `AZURE_OPENAI_DEPLOYMENT` | empty | commented example | Deployment names, comma-separated, the first being the default; with Azure enabled but no deployment, the list shows `gpt-6-sol` |
| `OPENAI_API_KEY` | empty | commented example | OpenAI key |
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | commented example | Base URL of OpenAI or a compatible service |
| `OPENAI_VISION_MODEL` | `gpt-6-sol` | — | OpenAI model for OCR of scanned PDF pages; also used as the Azure deployment name when no deployment is set |
| `ANTHROPIC_API_KEY` | empty | commented example | Anthropic key |
| `ANTHROPIC_API_BASE` | `https://api.anthropic.com` | commented example | Anthropic API URL |
| `ANTHROPIC_MAX_TOKENS` | empty | commented example `16000` | Output token cap per Claude response (required for Claude); a truncated tool call is reported as an error, so raise it if that happens |
| `GEMINI_API_KEY` | empty | commented example | Google Gemini key |
| `GEMINI_API_BASE` | `https://generativelanguage.googleapis.com` | commented example | Calls the OpenAI-compatible endpoint `/v1beta/openai/chat/completions` |
| `GEMINI_VISION_MODEL` | `gemini-3.5-flash` | — | Gemini model for OCR of scanned PDF pages |
| `EXTERNAL_TAGS_URL` | empty | — | URL of a remote model list, queried when no cloud model is configured; defaults to `{LLM_API_BASE}/api/tags` |
| `LLM_TAGS_TIMEOUT` | `10` | — | Timeout in seconds for the remote model list |
| `ADD_NGROK_HEADER` | `false` | — | Adds the `ngrok-skip-browser-warning` header to remote model list requests (added automatically for `ngrok-free.app` URLs) |

### Model list

`GET /api/chat/models` and `GET /api/tags` build the model list in this order:

1. `AVAILABLE_MODELS` is set: use it as is.
2. Otherwise merge, in order: the Azure deployments (`gpt-6-sol` when none is set), the built-in OpenAI list if `OPENAI_API_KEY` is set, the built-in Claude list if `ANTHROPIC_API_KEY` is set, and the built-in Gemini list if `GEMINI_API_KEY` is set.
3. Still empty: query the remote list at `EXTERNAL_TAGS_URL` (or `{LLM_API_BASE}/api/tags`), such as the models pulled into a local Ollama.

| Provider | Built-in list (3.0.0) |
|---|---|
| OpenAI | `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.4`, `gpt-5.4-mini` |
| Anthropic | `claude-opus-5-5`, `claude-fable-5-1`, `claude-sonnet-5`, `claude-opus-5`, `claude-fable-5`, `claude-opus-4-8`, `claude-haiku-4-5` |
| Gemini | `gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-3-pro` |

**Default model**: `MODEL_NAME` → the first Azure deployment → the first model in the list; a choice that is not in the list falls back to the first model in the list.

### Provider routing

Each call picks a provider from the model name; the first matching rule wins:

| Condition | Provider | Endpoint |
|---|---|---|
| Azure is enabled and the model is one of `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI | `{AZURE_OPENAI_ENDPOINT}/openai/v1/chat/completions` |
| The name starts with `claude-` and `ANTHROPIC_API_KEY` is set | Anthropic | Official `anthropic` SDK (Messages API) |
| The name starts with `gemini-` and `GEMINI_API_KEY` is set | Google Gemini | `{GEMINI_API_BASE}/v1beta/openai/chat/completions` |
| The name starts with `gpt-`, `o1`, `o3`, or `o4` | OpenAI when `OPENAI_API_KEY` is set; otherwise Azure when enabled | `{OPENAI_API_BASE}/chat/completions` |
| None of the above | Ollama | `{LLM_API_BASE}/api/chat` |

> [!NOTE]
> `reasoning_effort` is sent only to OpenAI and Azure OpenAI; models whose name contains `gpt-5` always get `none` when tools are attached, to respect the compatibility limits between reasoning and tool calling.

## Agent and web tools

| Variable | Code default | Template | Description |
|---|---|---|---|
| `ENABLE_WEB_SEARCH` | — (required) | `true` | Controls both `web_search` and `web_fetch`; with `false` both are left out of the tool list and calls to them are refused |
| `AGENT_MAX_TURNS` | — (required, ≥ 1) | `5` | Maximum model rounds per question (each round may call several tools); when they run out without an answer, the final answer is streamed from a fresh call |
| `CONVERSATION_HISTORY_MESSAGES` | — (required, ≥ 0) | `6` | Prior messages loaded from the database as context (user and assistant messages combined; history always starts with a user message); `0` disables history |
| `WEB_FETCH_ALLOWED_DOMAINS` | — (required) | `*` | Domains `web_fetch` may read, including subdomains, comma-separated; only an explicit `*` means unrestricted |
| `BLOCK_WEB_TOOLS_AFTER_KB` | — (required) | `true` | Within one question, refuse `web_search` and `web_fetch` once a knowledge-base tool has returned content |
| `OLLAMA_API_KEY` | empty | commented example | Key for the Ollama Web Search / Web Fetch APIs. When set, the web tools try the Ollama APIs first and fall back to DuckDuckGo or a direct fetch; unrelated to LLM calls |
| `OLLAMA_SEARCH_ENDPOINT` | `https://ollama.com/api/web_search` | — | Ollama Web Search endpoint |
| `OLLAMA_FETCH_ENDPOINT` | `https://ollama.com/api/web_fetch` | — | Ollama Web Fetch endpoint |
| `DUCKDUCKGO_SEARCH_ENDPOINT` | `https://html.duckduckgo.com/html/` | — | Fallback search endpoint for `web_search` |
| `DEFAULT_CONVERSATION_TITLE` | `新對話` | — | Placeholder title of a new conversation; replaced by the first 50 characters of the first user message |

Format rules for `WEB_FETCH_ALLOWED_DOMAINS`:

- It cannot be empty; write `*` explicitly for no restriction, and `*` cannot be combined with other domains.
- List bare domains only (lowercase letters, digits, hyphens, and dots) without `https://` or paths, for example `gov.tw,example.com`.
- Whatever the allowlist says, `web_fetch` only reads URLs that appear verbatim in the user's message or in this question's tool results, and every fetch passes SSRF validation.

## Retrieval, reranking, and chunking

Each search runs: `TOP_K` candidates from vector search and from BM25 → RRF fusion keeps the top `RERANK_TOP_K` (plus exact matches on URLs, post IDs, dates, and @accounts) → Cross-Encoder reranking → `RERANK_RELEVANCE_THRESHOLD` → the top `FINAL_K`.

| Variable | Code default | Template | Description |
|---|---|---|---|
| `EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | same | Embedding model; when a new model changes the vector dimension, the old index is renamed to `*.mismatch.bak` and vectors are recomputed from the database chunks |
| `RERANKER_MODEL` | `BAAI/bge-reranker-base` | same | Cross-Encoder reranker, a required component: the backend refuses to start if it cannot load |
| `TOP_K` | `30` | `30` | Candidates fetched by vector search and by BM25 each |
| `RRF_K` | — (required, ≥ 1) | `60` | RRF score = Σ 1 / (`RRF_K` + rank), ranks starting at 1 |
| `RERANK_TOP_K` | `50` | `20` | Fused candidates sent to the reranker; on CPU each pair costs about 0.2 s (300 characters) to 0.4 s (800 characters) |
| `RERANK_WEIGHT` | `0.85` | `0.85` | Sort score = `RERANK_WEIGHT` × reranker probability + (1 − `RERANK_WEIGHT`) × candidate base score; it does not affect the threshold |
| `RERANK_RELEVANCE_THRESHOLD` | — (required, 0 to 1) | `0.2` | Chunks whose reranker probability falls below this are irrelevant; exact URL, post ID, and date matches are exempt; when everything is filtered out the tool reports that the knowledge base has nothing relevant |
| `FINAL_K` | `8` | `8` | Maximum chunks kept after the threshold |
| `SIMILARITY_THRESHOLD` | `0.30` | `0.30` | Used only by standalone vector search (`vector_search`); the main RRF hybrid path does not apply it |
| `CHUNK_SIZE` | `800` | `300` | Chunk length in characters; rebuild the index to apply a change to existing documents |
| `CHUNK_OVERLAP` | `150` | `100` | Characters shared by neighboring chunks |
| `DOMAIN_PROFILE_PATH` | — (required) | `config/domain_profile.json` | Domain profile; see [Domain profile](#domain-profile) |
| `JIEBA_DICTIONARY` | empty | commented example | Replacement jieba main dictionary, such as the Traditional-Chinese-friendly [`dict.txt.big`](https://raw.githubusercontent.com/fxsjy/jieba/master/extra_dict/dict.txt.big); a missing file stops startup, and changing it rebuilds BM25 automatically |

> [!TIP]
> Q&A documents (`Q：…` / `A：…`) become one chunk per question-answer pair, and structured records and JSON data become one chunk per record; neither case is limited by `CHUNK_SIZE`.

## Compute devices

| Variable | Code default | Template | Description |
|---|---|---|---|
| `FORCE_CPU` | `true` | `true` | Use the CPU even when CUDA is available; in CPU mode PyTorch uses min(16, CPU cores) threads |
| `USE_FP16_QUANTIZATION` | `false` | `false` | CUDA only: run the embedding and reranker models in FP16 |
| `GPU_BATCH_SIZE` | `128` | `128` | Embedding batch size on GPU |
| `CPU_BATCH_SIZE` | `64` | `32` | Embedding batch size on CPU |
| `USE_FAISS_GPU` | `false` | `false` | Run FAISS on GPU (requires `faiss-gpu`; falls back to CPU if initialization fails) |
| `FAISS_GPU_DEVICE` | `0` | `0` | GPU index for FAISS |
| `FAISS_GPU_TEMP_MEMORY` | `2147483648` | same | FAISS GPU scratch memory in bytes (2 GiB by default) |

## Hugging Face model cache

These settings are exported to the environment before any model loads (booleans as `1` / `0`); unset keys are not exported.

| Variable | Code default | Template | Description |
|---|---|---|---|
| `HF_HOME` | empty (library default `~/.cache/huggingface`) | `./data/hf_home` | Root of the model cache |
| `HF_HUB_CACHE` | empty (follows `HF_HOME`) | commented example | Set only to keep the Hub cache elsewhere |
| `SENTENCE_TRANSFORMERS_HOME` | empty (follows `HF_HOME`) | commented example | sentence-transformers cache location |
| `HF_HUB_OFFLINE` | empty | `false` | With `true`, models load from the cache only and startup makes no network checks; keep `false` until the models have been downloaded once |
| `HF_HUB_DISABLE_SYMLINKS_WARNING` | empty | `true` | Hides the warning when Windows cannot create symlinks; the cache then stores copies, so the reranker downloads about 1.1 GB but occupies about 2.2 GB |

## Storage paths and uploads

| Variable | Code default | Template | Description |
|---|---|---|---|
| `DATA_DIR` | `data` | `data` | Root directory for indexes and runtime data |
| `UPLOAD_DIR` | `data/uploads` | `data/uploads` | Original uploaded files; index rebuilds re-extract text from here first |
| `FAISS_INDEX_PATH` | `data/faiss_index.bin` | same | FAISS vector index (`IndexIDMap2`, ids are chunk_ids) |
| `BM25_INDEX_DIR` | `data/bm25_index` | same | Whoosh BM25 index directory (including `tokenizer_signature.json`) |
| `METADATA_PATH` | `data/index_metadata.pkl` | same | Index metadata such as the last rebuild time |
| `MAX_FILE_SIZE_MB` | `50` | `10` | Per-file upload limit for the knowledge base (MB) |
| `UPLOADS_WATCHER_INTERVAL` | `30` | `30` | Seconds between checks for missing uploads; a missing file is logged once and nothing is deleted |

## Database

| Variable | Code default | Template | Description |
|---|---|---|---|
| `DATABASE_URL` | — (required) | PostgreSQL example | SQLAlchemy connection string |
| `DB_POOL_SIZE` | `20` | `20` | Connection pool size (PostgreSQL and other non-SQLite databases; fixed at 5 for SQLite) |
| `DB_MAX_OVERFLOW` | `40` | `40` | Pool overflow limit (fixed at 10 for SQLite) |
| `DB_POOL_RECYCLE` | `3600` | — | Seconds before a connection is recycled |
| `DB_POOL_PRE_PING` | `true` | — | Check connections before use (non-SQLite only) |
| `SQLALCHEMY_ECHO` | `false` | — | Log SQL statements |

Common `DATABASE_URL` values:

| Scenario | Connection string |
|---|---|
| SQLite (zero dependencies) | `sqlite:///./chatbot.db` (relative to the startup directory, so starting in `backend/` gives `backend/chatbot.db`) |
| PostgreSQL 17 from `backend/docker-compose.yml` | `postgresql+psycopg2://postgres:postgres@localhost:7690/chatbot` (the container publishes port 7690) |
| Your own PostgreSQL | `postgresql+psycopg2://<user>:<password>@<host>:5432/<database>` |

Tables are created automatically when the backend starts. `init_db.py` is a compatibility script that adds columns and indexes to older PostgreSQL databases; SQLite does not need it (SQLite does not support its `ADD COLUMN IF NOT EXISTS` statement).

## Authentication and tokens

| Variable | Code default | Template | Description |
|---|---|---|---|
| `JWT_SECRET_KEY` | — (required) | placeholder | Tokens are normally signed RS256 with the RSA keys; when those cannot load (non-`production` only), this key signs HS256 instead |
| `JWT_ALGORITHM` | `RS256` | `RS256` | Currently not used by the code: RS256 whenever the RSA keys are available, otherwise HS256 |
| `ADMIN_API_KEY` | — (required) | placeholder | Required by settings validation; no route currently checks `X-API-Key`, and admin endpoints rely on the `is_admin` claim of the access token |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | `30` | Access token lifetime in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | `7` | Refresh token lifetime in days, also the cookie `max-age` |
| `COOKIE_SECURE` | empty (`true` when `ENVIRONMENT=production`) | — | `Secure` attribute of the refresh token cookie |
| `COOKIE_SAMESITE` | `lax` | — | `SameSite` attribute of the refresh token cookie |

The RSA key pair lives in `backend/keys/jwt_private.pem` and `jwt_public.pem` and is generated on first start if missing (2048-bit, ignored by git). When several backends serve the same users, give them the same key pair.

## Network access control

| Variable | Code default | Template | Description |
|---|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:3001,https://localhost:3001,http://127.0.0.1:3001,https://127.0.0.1:3001` | `http://localhost:3001,https://localhost:3001` | Allowed CORS origins (comma-separated, credentials allowed) |
| `DEVTUNNEL_URL` | empty | empty | One extra origin added to the CORS allowlist, such as a Dev Tunnels URL |
| `RATE_LIMIT_ENABLED` | `true` | `true` | Enable rate limiting |
| `RATE_LIMIT_PER_MINUTE` | `60` | `60` | Requests allowed per client IP in 60 seconds; beyond that the backend returns `429` with `Retry-After` |

> [!NOTE]
> Rate limiting counts requests per connecting IP. Behind the Vite dev proxy or a reverse proxy, every user shares the proxy's IP and therefore one quota.

## Server and runtime

| Variable | Code default | Template | Description |
|---|---|---|---|
| `ENVIRONMENT` | `development` | `development` | With `production`, cookies get `Secure` by default and the backend refuses to start without usable RSA keys |
| `HOST` | `0.0.0.0` | `0.0.0.0` | Default bind address of `python main.py` (override with `--host`) |
| `PORT` | `8001` | `8001` | Default port (override with `--port`) |
| `RELOAD` | `true` | `true` | Reload on code changes (disable with `--no-reload`) |
| `LOG_LEVEL` | `INFO` | `INFO` | Log level; application logs go to `backend/logs/app.log` |
| `BASE_URL` | `http://backend:8001` | `http://localhost:8001` | Used only by `healthcheck.py`, which reads the process environment and not `.env` |

## Reserved settings

These settings can appear in `.env`, but no code path uses them in 3.0.0:

| Variable | Code default | Description |
|---|---|---|
| `ENABLE_BATCH_ACCUMULATION` | `false` | Switch for the embedding batch accumulator, which is not wired into the upload flow |
| `BATCH_ACCUMULATOR_SIZE` | `32` | Same as above |

## Removed settings

Ignored if left in `.env`; safe to delete:

| Variable | Removed in | Replacement |
|---|---|---|
| `HYBRID_ALPHA`, `NORMALIZATION` | 3.0.0 | Standard RRF fusion with `RRF_K` |
| `FINAL_THRESHOLD` | 3.0.0 | `RERANK_RELEVANCE_THRESHOLD` |
| `DOCUMENTS_PATH` | 3.0.0 | Chunks live in the `rag_chunks` table |
| `ENABLE_AUTO_REINDEX`, `ENABLE_AUTO_REINDEX_TASK`, `REINDEX_HOURS` | 3.0.0 | Indexes are reconciled against the database at startup, so scheduled rebuilds are unnecessary |
| `TRANSFORMERS_CACHE`, `HUGGINGFACE_HUB_CACHE` | 3.0.0 | `HF_HOME` or `HF_HUB_CACHE` |
| `AZURE_OPENAI_API_VERSION` | 2.0.0 | The Azure OpenAI v1 endpoint |

## Domain profile

The JSON file at `DOMAIN_PROFILE_PATH` (default `backend/config/domain_profile.json`) holds deployment-specific domain data and is validated strictly at startup: a missing field, an unknown field, or an empty string stops the backend.

```json
{
  "domain_words": ["補休", "育嬰留停", "免刷卡"],
  "record_date_fields": ["timestamp", "timestampTitle"],
  "summary_fallback": {
    "chat_member_noise_words": ["All", "收到", "好的"],
    "chat_topic_keywords": ["Agent", "部署", "會議"],
    "boilerplate_line_prefixes": ["copyright", "all rights reserved", "www."]
  }
}
```

| Field | Purpose |
|---|---|
| `domain_words` | Domain terms added to the jieba dictionary so BM25 keeps them whole; changing them rebuilds BM25 automatically |
| `record_date_fields` | Field names that hold the publish date in structured records (content formatted as "field: date"); `filter_and_count_records` matches dates only in these fields, falling back to the full text for records without them |
| `summary_fallback.chat_member_noise_words` | When the LLM summary fails and rule-based summaries take over, words in chat logs that are not member names |
| `summary_fallback.chat_topic_keywords` | Keywords the rule-based summary uses to detect chat log topics |
| `summary_fallback.boilerplate_line_prefixes` | Lines starting with these prefixes (case-insensitive) are treated as footer or copyright noise |

## Calibrating the relevance threshold

`RERANK_RELEVANCE_THRESHOLD=0.2` is a provisional value from a small Traditional Chinese corpus: full-question positives usually score above 0.9, but single-keyword queries and in-domain negatives overlap between 0.3 and 0.42 (see [ADR-0003](adr/0003-rrf-relevance-citations-and-tool-trust_en.md)). Once your real documents are uploaded, calibrate with your own golden set:

1. **Prepare a golden set**: JSONL with one question per line; `relevant_sources` lists the file names that should be found, and questions the knowledge base cannot answer use an empty list as negatives. See [`backend/eval/retrieval_golden.example.jsonl`](../backend/eval/retrieval_golden.example.jsonl) for the format.

   ```json
   {"query": "特休假的天數如何依年資計算？", "relevant_sources": ["員工手冊.pdf"]}
   {"query": "公司附近有推薦的午餐餐廳嗎？", "relevant_sources": []}
   ```

2. **Compare thresholds**: run the command below in `backend/`. The evaluation runs read-only on a copy of the index and can run alongside the backend; it refuses to run when the index disagrees with the database or the tokenizer signature differs, so start the backend once to reconcile first.

   ```bash
   python scripts/evaluate_retrieval.py --golden eval/retrieval_golden.jsonl --k 1 3 5 --relevance-thresholds 0.1 0.2 0.3 0.4
   ```

3. **Read the report**: it lists MRR, hit@k, recall@k, and the negative rejection rate for the current threshold, then compares every candidate threshold over the same rerank pass. Higher thresholds reject more negatives but may miss positives; pick the value that balances the two.
4. **Apply it**: set the chosen value as `RERANK_RELEVANCE_THRESHOLD` in `.env` and restart the backend.

Other options: `--min-mrr 0.6` exits with code 1 when MRR falls short, which suits CI; `--output report.json` writes the full results.

## Frontend environment variables

The frontend works without a `.env`: the API base defaults to the relative path `/api`, which the Vite dev server (port 3000) proxies to `http://127.0.0.1:8001`, so the browser never goes cross-origin and the backend needs no CORS setup.

| Variable | When unset | Description |
|---|---|---|
| `VITE_API_BASE` | `/api` | API base. With an absolute URL (such as `http://localhost:8001`) the browser calls the backend directly, so the backend's `ALLOWED_ORIGINS` must include the frontend origin; the value is also the target of the Vite `/api` proxy. `/api` is appended to the path automatically |
| `VITE_API_URL` | — | Used only when `VITE_API_BASE` is unset; same format |
| `PORT` | `3000` | Vite dev server port (`bun run preview` always uses 3000) |
| `GENERATE_SOURCEMAP` | emitted | Emit source maps in builds; only `false` turns them off |

`frontend/.env.example` uses the direct mode: `VITE_API_BASE=http://localhost:8001` with `PORT=3001`, an origin already in the backend's default `ALLOWED_ORIGINS`.
