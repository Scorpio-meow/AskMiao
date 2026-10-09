# AskMiao Configuration Reference

[繁體中文](configuration.md) | [English](configuration_en.md)

> Every setting in the backend `backend/.env` and the frontend `frontend/.env`, with its default and what it actually does, as of the **unreleased version** after 4.0.0 (to upgrade from 4.0.0, see the [upgrade guide](upgrading_en.md#upgrading-from-400-to-the-unreleased-version)). The source of truth is `Settings` in `backend/app/core/config.py`; the template is [`backend/.env.example`](../backend/.env.example).

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
- [Tool credential encryption](#tool-credential-encryption)
- [Network access control](#network-access-control)
- [Server and runtime](#server-and-runtime)
- [Resource limits](#resource-limits)
- [Reserved settings](#reserved-settings)
- [Removed settings](#removed-settings)
- [Domain profile](#domain-profile)
- [Calibrating the relevance threshold](#calibrating-the-relevance-threshold)
- [Frontend environment variables](#frontend-environment-variables)

---

## How settings are read

- **Source**: the backend reads `backend/.env` regardless of the startup directory, and process environment variables take precedence over `.env`. Unknown keys are ignored, so removed settings left in `.env` cause no errors.
- **Required settings have no defaults**: if any is missing, the backend stops at startup with a `Field required` error that names the missing fields.
- **Value ranges and formats**: `AGENT_MAX_TURNS ≥ 1`, `CONVERSATION_HISTORY_MESSAGES ≥ 0`, `RRF_K ≥ 1`, `0 ≤ RERANK_RELEVANCE_THRESHOLD ≤ 1`, and `ANTHROPIC_MAX_TOKENS ≥ 1`; `LOGIN_MAX_FAILURES_PER_ACCOUNT`, `LOGIN_MAX_FAILURES_PER_ADDRESS`, `LOGIN_FAILURE_WINDOW_SECONDS`, and `LOGIN_LOCKOUT_SECONDS` must all be ≥ 1, and `TOOL_SECRETS_KEY` must be a valid Fernet key; out-of-range or malformed values also stop startup.
- **Booleans**: `true` / `false`, `1` / `0`, and `yes` / `no` all work.
- **Relative paths**: relative values of `DATA_DIR`, `UPLOAD_DIR`, `FAISS_INDEX_PATH`, `BM25_INDEX_DIR`, `METADATA_PATH`, `HF_HOME`, `HF_HUB_CACHE`, `SENTENCE_TRANSFORMERS_HOME`, `DOMAIN_PROFILE_PATH`, and `JIEBA_DICTIONARY` always resolve against `backend/`. `DATABASE_URL` is not one of them: a relative SQLite path depends on the startup directory.
- **Code default versus template value**: in the tables below, "Code default" applies when `.env` does not set the key, and "Template" is the value suggested by `backend/.env.example`; your `.env` wins whenever they differ.

## Required settings

These 20 settings have no default; the backend does not start if any is missing.

| Variable | Template | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://askmiao_app:your_app_db_password_here@localhost:5432/chatbot` | Database connection string; see [Database](#database) |
| `ADMIN_API_KEY` | `your_admin_api_key_here` | Admin API key (required by settings validation, currently unused by any route); replace with a random string |
| `TOOL_SECRETS_KEY` | `your_tool_secrets_key_here` | Fernet key that encrypts tool credentials, validated at startup; the template value is not a valid key and must be replaced with one you generate (command below); see [Tool credential encryption](#tool-credential-encryption) |
| `ALLOW_REGISTRATION` | `false` | Allow self-registration; see [Registration and account creation](#registration-and-account-creation) |
| `LOGIN_MAX_FAILURES_PER_ACCOUNT` | `5` | Login failure threshold per login identifier (≥ 1); see [Login throttling](#login-throttling) |
| `LOGIN_MAX_FAILURES_PER_ADDRESS` | `20` | Login failure threshold per source address (≥ 1) |
| `LOGIN_FAILURE_WINDOW_SECONDS` | `900` | Window in seconds for counting login failures (≥ 1) |
| `LOGIN_LOCKOUT_SECONDS` | `900` | Seconds logins pause once a threshold is reached (≥ 1) |
| `COOKIE_SECURE` | `false` | Whether the refresh token cookie carries the `Secure` attribute; must be `true` when serving over HTTPS |
| `HOST` | `127.0.0.1` | Bind address of `python main.py`; see [Server and runtime](#server-and-runtime) |
| `RELOAD` | `false` | Reload on code changes; set `true` only for development |
| `ENABLE_API_DOCS` | `false` | Serve the interactive documentation at `/docs`, `/redoc`, and `/openapi.json` |
| `ENABLE_WEB_SEARCH` | `true` | Offer the web tools |
| `AGENT_MAX_TURNS` | `5` | Tool-calling turn limit per question |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | Prior messages loaded as context |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | `web_fetch` domain allowlist |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | Disable web tools after knowledge-base content was read |
| `RRF_K` | `60` | RRF fusion constant |
| `RERANK_RELEVANCE_THRESHOLD` | `0.2` | Reranker probability threshold |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | Domain profile path |

Generate a `TOOL_SECRETS_KEY` for each deployment, for example in an environment where the backend dependencies are installed:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Claude models also require `ANTHROPIC_MAX_TOKENS` (without it Claude calls fail, but startup is unaffected).

## LLM providers and models

| Variable | Code default | Template | Description |
|---|---|---|---|
| `LLM_API_BASE` | `http://localhost:5000` | `http://localhost:11434` | Ollama base URL, used to call Ollama models (`/api/chat`) and to query remote model lists (`/api/tags`) |
| `LLM_TIMEOUT` | `120` | `120` | LLM call timeout in seconds, also used for the vision model calls of PDF OCR; waiting for a connection pool slot has its own fixed 15-second limit (see [Resource limits](#resource-limits)) |
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
3. Still empty: query the remote list at `EXTERNAL_TAGS_URL` (or `{LLM_API_BASE}/api/tags`), such as the models pulled into a local Ollama. The remote query runs in a worker thread, its result (failures included) is cached for 30 seconds, and only one query runs at a time.

The `model_name` given to `POST /api/chat/send` must be in this list (or equal `MODEL_NAME`); otherwise the request fails with `400`, so nobody can call an unlisted model with the operator's keys.

| Provider | Built-in list (4.0.0) |
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
- Whatever the allowlist says, `web_fetch` only reads URLs that appeared as a whole URL in the user's message or in this question's tool results (both sides normalized to httpx's form and compared exactly), and every fetch passes SSRF validation.

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
| `DATA_DIR` | `data` | `data` | Root directory for indexes and runtime data; the jieba dictionary cache also lives in its `jieba_cache/` subdirectory (no longer in the system temp directory) |
| `UPLOAD_DIR` | `data/uploads` | `data/uploads` | Original uploaded files; index rebuilds re-extract text from here first |
| `FAISS_INDEX_PATH` | `data/faiss_index.bin` | same | FAISS vector index (`IndexIDMap2`, ids are chunk_ids) |
| `BM25_INDEX_DIR` | `data/bm25_index` | same | Whoosh BM25 index directory (including `tokenizer_signature.json`) |
| `METADATA_PATH` | `data/index_metadata.pkl` | same | Index metadata such as the last rebuild time |
| `MAX_FILE_SIZE_MB` | `50` | `10` | Per-file upload limit for the knowledge base (MB); also sets the upload request body limit, see [Resource limits](#resource-limits) |
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
| PostgreSQL 17 from `backend/docker-compose.yml` | `postgresql+psycopg2://<POSTGRES_APP_USER>:<POSTGRES_APP_PASSWORD>@localhost:7690/chatbot` (the container binds `127.0.0.1:7690` only) |
| Your own PostgreSQL | `postgresql+psycopg2://<user>:<password>@<host>:5432/<database>` (a non-superuser account is recommended; see the next section) |

Tables are created automatically when the backend starts, and missing new columns (such as `custom_api_tools.requires_approval`, `mcp_servers.requires_approval`, and `users.tokens_valid_after`) are added and backfilled at startup too; tool credentials stored in plaintext by older versions are encrypted at startup as well (see [Tool credential encryption](#tool-credential-encryption)). New SQLite databases create `users` and `documents` with `AUTOINCREMENT`, so deleted ids are never reused; existing SQLite tables are not rewritten. `init_db.py` is a compatibility script that adds columns and indexes to older PostgreSQL databases; SQLite does not need it (SQLite does not support its `ADD COLUMN IF NOT EXISTS` statement).

### PostgreSQL non-superuser account

`backend/docker-compose.yml` ships no passwords: set the three variables below in `backend/.env` or the shell before starting, and `docker compose` refuses to start if any is missing. They are read by compose only; the backend ignores them.

| Variable | Template | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | commented example | Password of the `postgres` superuser, for administration only; the backend never connects with this account |
| `POSTGRES_APP_USER` | commented example `askmiao_app` | Non-superuser account the backend connects with |
| `POSTGRES_APP_PASSWORD` | commented example | Password of that account; use a random string different from `POSTGRES_PASSWORD` |

`DATABASE_URL` uses `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD` (percent-encode characters such as `@`, `:`, and `/`). The container port is published on the loopback address only, so neither the LAN nor the internet can reach it.

When a new data volume is created, the container runs `10-init.sql` (`backend/init.sql`, which creates the tables) and then `20-app-role.sh` (`backend/init-app-role.sh`), in file name order. The script creates `POSTGRES_APP_USER` (`NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`) and sets its password, grants `CONNECT` on the database and `USAGE` and `CREATE` on the `public` schema, and hands it ownership of the tables in `public`. The backend creates and alters its own tables at startup, so these privileges are enough; connected as a non-superuser, a SQL injection cannot run system commands with `COPY ... TO PROGRAM` or read server files.

Initialization scripts run only when the data volume is first created. For an existing volume, start the container with the new `docker-compose.yml`, run the command below once in `backend/`, and then switch `DATABASE_URL` to this account. The script is safe to rerun; each run sets the account's password to the container's `POSTGRES_APP_PASSWORD`.

```bash
docker compose exec postgres bash /docker-entrypoint-initdb.d/20-app-role.sh
```

For your own PostgreSQL, follow `backend/init-app-role.sh` as well and connect the backend as a non-superuser with only these privileges.

## Authentication and tokens

| Variable | Code default | Template | Description |
|---|---|---|---|
| `ADMIN_API_KEY` | — (required) | placeholder | Required by settings validation; no route currently checks `X-API-Key`, and admin endpoints rely on the account's `is_admin` flag in the database |
| `ALLOW_REGISTRATION` | — (required) | `false` | Allow self-registration through `POST /api/auth/register`; with `false`, registration returns `403` and accounts are created with `scripts/create_user.py`; see [Registration and account creation](#registration-and-account-creation) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | `30` | Access token lifetime in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | `7` | Refresh token lifetime in days, also the cookie `max-age` |
| `LOGIN_MAX_FAILURES_PER_ACCOUNT` | — (required, ≥ 1) | `5` | Once one login identifier fails this many times within the window, logins for that identifier pause; see [Login throttling](#login-throttling) |
| `LOGIN_MAX_FAILURES_PER_ADDRESS` | — (required, ≥ 1) | `20` | Once one source address fails this many times within the window (whatever accounts it tries), logins from that address pause |
| `LOGIN_FAILURE_WINDOW_SECONDS` | — (required, ≥ 1) | `900` | Sliding window in seconds for counting failures |
| `LOGIN_LOCKOUT_SECONDS` | — (required, ≥ 1) | `900` | How long logins pause, in seconds; the pause lifts automatically |
| `COOKIE_SECURE` | — (required) | `false` | `Secure` attribute of the refresh token cookie; with `true` the browser sends the cookie over HTTPS only. Must be `true` when serving over HTTPS, and `false` is fine for local development on `http://localhost`; no longer derived from `ENVIRONMENT` |
| `COOKIE_SAMESITE` | `lax` | — | `SameSite` attribute of the refresh token cookie |

Access and refresh tokens are always signed RS256; there is no other algorithm to choose. The RSA key pair lives in `backend/keys/jwt_private.pem` and `jwt_public.pem` and is generated on first start if missing (2048-bit, ignored by git; the private key is created with mode `0600`, and a newly created `backend/keys/` is `0700`), so the backend account must be able to write to `backend/keys/`; if the keys cannot be loaded or generated, the backend refuses to start in every `ENVIRONMENT`. When several backends serve the same users, give them the same key pair.

Every request maps the access token back to the account in the database: the account must exist and be active, `is_admin` and the role come from the database rather than the token, and tokens issued before the account's `tokens_valid_after` are rejected (see [Password changes and token revocation](#password-changes-and-token-revocation)). Refresh tokens are single-use: issuing a new pair revokes the old one immediately.

### Login throttling

Every failed `POST /api/auth/login` counts against two keys:

- **Login identifier**: the user name or email typed at login, case-insensitive and with surrounding whitespace ignored; signing in to one account by name and by email counts separately. Unknown accounts are counted too, with the same response as existing ones.
- **Source address**: the connecting IP; with `FORWARDED_ALLOW_IPS` set, the client IP forwarded by the reverse proxy (see [Network access control](#network-access-control)).

Once one identifier fails `LOGIN_MAX_FAILURES_PER_ACCOUNT` times, or one address fails `LOGIN_MAX_FAILURES_PER_ADDRESS` times, within `LOGIN_FAILURE_WINDOW_SECONDS`, logins for that identifier or address pause for `LOGIN_LOCKOUT_SECONDS`. During the pause, login requests get `429` with `Retry-After` (the remaining seconds) without the password being checked, so even the right password is refused, and each one is written to the security log as `LOGIN_THROTTLED`; when the pause ends, counting starts over. A successful login clears only that identifier's failures; failures from the same address against other accounts still count. The pause affects logins only; tokens already issued keep working.

When users connect through a reverse proxy or the Vite dev proxy and `FORWARDED_ALLOW_IPS` is not set, they all share the proxy's address, so set the per-address threshold higher than the per-account one (the template uses `20` and `5`).

The counters live in each backend process's memory: they reset when the backend restarts, and separate backend processes do not share them but count independently. The number of tracked identifiers and addresses is capped (see [Resource limits](#resource-limits)); beyond the cap, the entry with the oldest last failure is evicted together with its failures and any pause.

### Registration and account creation

All accounts share the whole knowledge base and the enabled tools, so keep `ALLOW_REGISTRATION=false` for deployments reachable from the public internet.

- `true`: anyone who can reach the API can create a regular account with `POST /api/auth/register`.
- `false`: `POST /api/auth/register` returns `403` and writes `REGISTER_REJECTED` to the security log. The frontend checks `GET /api/auth/registration` (no login required; it returns `{"enabled": false}`), hides the sign-up link on the login page, and shows an explanation on the sign-up page.

An admin creates accounts, including the first admin, by running `scripts/create_user.py` in `backend/`:

```bash
python scripts/create_user.py --username alice --email alice@example.com
python scripts/create_user.py --username root --email root@example.com --admin
```

The password is typed twice interactively and never passed as a command-line argument, so it stays out of the shell history and the process list; user names, emails, and passwords follow the same rules as self-registration, and `--admin` creates an admin. The script connects to the database with the same `backend/.env` and creates the tables first if they do not exist.

### Password changes and token revocation

Access and refresh tokens issued before the account's `users.tokens_valid_after` are rejected. The column equals the creation time when an account is created (so old tokens do not carry over when a deleted account's id is reused) and is set to the current time on a password change: after a successful `POST /api/auth/change-password` or a `PUT /api/auth/me` that sets a new password, every token issued to the account before then, including the current one and those on other devices, stops working immediately, and a stolen refresh token can no longer be renewed. The response clears the refresh token cookie, and every session must sign in again with the new password. Existing databases get the column automatically at backend startup, backfilled from `created_at`.

## Tool credential encryption

| Variable | Code default | Template | Description |
|---|---|---|---|
| `TOOL_SECRETS_KEY` | — (required) | placeholder (not a valid key) | Fernet key that encrypts the credentials of custom API tools and MCP servers; generate one per deployment |

The key format is validated at startup: it must be a Fernet key (32 bytes, URL-safe base64-encoded, 44 characters). The template's placeholder fails validation, so the backend refuses to start until it is replaced. To generate a key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- **What is encrypted**: custom API tools' `headers` and `auth_config` and MCP servers' `env_vars` and `headers` are encrypted with this key before they reach the database (stored with a `fernet:` prefix), so a leaked database or backup does not expose the credentials directly. Values stored in plaintext by older versions are encrypted automatically at backend startup; old values that are not JSON objects are cleared and must be entered again.
- **Masking in the admin API**: tool and MCP server responses show `••••••••` in place of secret values, so saved credentials can no longer be read back through the API. Secret values are headers other than `Accept`, `Accept-Encoding`, `Accept-Language`, `Cache-Control`, `Content-Type`, and `User-Agent`; the `token`, `key_value`, and `password` keys of `auth_config`; and every MCP server environment variable. Settings such as `key_name`, `key_in`, and `username` are shown as before. On update, the submitted value replaces the whole field, and entries still set to `••••••••` keep their stored value; with no stored value to keep, the update returns `400`.
- **Changing or losing the key**: stored credentials cannot be decrypted with another key. The admin API marks the affected tools and MCP servers with `credentials_unreadable: true` and returns `null` for the fields it cannot decrypt; enter those credentials again. Until then, the agent's calls to those tools fail. Keep `TOOL_SECRETS_KEY` safe together with your database backups: restoring the database without the original key means re-entering every tool credential.

## Network access control

| Variable | Code default | Template | Description |
|---|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:3001,https://localhost:3001,http://127.0.0.1:3001,https://127.0.0.1:3001` | `http://localhost:3001,https://localhost:3001` | Allowed CORS origins (comma-separated, credentials allowed) |
| `DEVTUNNEL_URL` | empty | empty | One extra origin added to the CORS allowlist, such as a Dev Tunnels URL |
| `RATE_LIMIT_ENABLED` | `true` | `true` | Enable rate limiting |
| `RATE_LIMIT_PER_MINUTE` | `60` | `60` | Requests allowed per client IP in 60 seconds; beyond that the backend returns `429` with `Retry-After` |
| `FORWARDED_ALLOW_IPS` | empty | commented example `127.0.0.1` | Reverse proxy addresses whose `X-Forwarded-For` is trusted (passed to uvicorn's `forwarded_allow_ips`); when unset, uvicorn ignores proxy headers |

> [!NOTE]
> Rate limiting and the per-address count of [login throttling](#login-throttling) both use the connecting IP. Without `FORWARDED_ALLOW_IPS`, a client-supplied `X-Forwarded-For` is never trusted, so behind the Vite dev proxy or a reverse proxy every user shares the proxy's IP and therefore one quota and one login failure count.
>
> Set `FORWARDED_ALLOW_IPS` to the proxy's address only when the reverse proxy in front of the backend *overwrites* `X-Forwarded-For` (for example nginx with `proxy_set_header X-Forwarded-For $remote_addr;`); rate limiting and login throttling then count real client IPs. The Vite dev proxy forwards client-supplied headers unchanged, so **never** set it for Vite, or anyone could forge their source IP to evade rate limiting and per-address login throttling. The setting only takes effect when the backend is started with `python main.py`.

Rate limiting counts in each backend process's memory, and the number of tracked addresses is capped (see [Resource limits](#resource-limits)). Intrusion detection only raises alerts and never blocks an address; exceeding the rate limit always returns `429`, never a `403` that blocks the address (the IP blocklist of earlier versions, which was never populated, has been removed).

## Server and runtime

| Variable | Code default | Template | Description |
|---|---|---|---|
| `ENVIRONMENT` | `development` | `development` | Currently changes only the wording of a CORS line in the startup log; the cookie `Secure` attribute is no longer derived from it and comes from the required `COOKIE_SECURE` (the backend refuses to start without usable RSA keys in every environment) |
| `HOST` | — (required) | `127.0.0.1` | Bind address of `python main.py` (override with `--host`). Keep `127.0.0.1` when only local clients or a reverse proxy on the same host connect; use `0.0.0.0` only when a reverse proxy in a container or on another host must reach the backend |
| `PORT` | `8001` | `8001` | Default port (override with `--port`) |
| `RELOAD` | — (required) | `false` | Reload on code changes; set `true` only for development (override with `--reload` or `--no-reload`) |
| `ENABLE_API_DOCS` | — (required) | `false` | Serve the interactive documentation at `/docs`, `/redoc`, and `/openapi.json`. These pages list every endpoint and parameter, so keep `false` for public deployments; with `false`, none of the three paths is served |
| `LOG_LEVEL` | `INFO` | `INFO` | Log level; application logs go to `backend/logs/app.log` and security events only to `backend/logs/security.log` (both rotate by size). `httpx` and `httpcore` are pinned to `WARNING`, so full request URLs (which may carry query-string API keys) are not logged |
| `BASE_URL` | `http://backend:8001` | `http://localhost:8001` | Used only by `healthcheck.py`, which reads the process environment and not `.env` |

`HOST`, `PORT`, `RELOAD`, and `FORWARDED_ALLOW_IPS` apply only when the backend is started with `python main.py`; started any other way (for example by running `uvicorn main:app` directly), they are not applied, although `HOST` and `RELOAD` are still required. The uvicorn server started by `python main.py` processes proxy headers (`proxy_headers`) only when `FORWARDED_ALLOW_IPS` is set; see [Network access control](#network-access-control).

## Resource limits

The limits below protect a single backend process and the operator's paid usage. They are code constants, **not** `.env` settings, and live in [`backend/app/core/limits.py`](../backend/app/core/limits.py) (a few constants tied to one module are defined there, as noted in the tables). To change one, edit the source and update this section.

**Requests and chat**

| Constant | Value | Description |
|---|---|---|
| `MAX_REQUEST_BODY_BYTES` | 1 MiB | Body limit for general API requests and for every request without a valid access token; larger bodies get `413`. An oversized `Content-Length` is rejected up front, and chunked bodies are counted as they arrive |
| `MAX_CHAT_REQUEST_BODY_BYTES` | about 27.7 MiB | Body limit of `POST /api/chat/send` (20 MiB of attachments inflated 4/3 by base64, plus 1 MiB); applies only with a validly signed access token, otherwise the limit stays 1 MiB |
| Document upload body limit | `MAX_FILES_PER_UPLOAD` × `MAX_FILE_SIZE_MB` MiB + 1 MiB | Body limit of `POST /api/documents/upload` (101 MiB with the template's `MAX_FILE_SIZE_MB=10`); raised only when the access token is validly signed and its `is_admin` claim is `true`, otherwise the limit stays 1 MiB |
| `MAX_FILES_PER_UPLOAD` | 10 | Files per upload |
| `MAX_CHAT_MESSAGE_CHARS` | 20,000 characters | Length of one chat message; longer messages get `422` |
| `MAX_CHAT_ATTACHMENTS` | 5 | Attachments per message |
| `MAX_CHAT_ATTACHMENT_BYTES` | 15 MiB | Decoded size of one attachment; an attachment's `data_url` must be a base64 `data:` URL, and remote URLs are rejected |
| `MAX_CHAT_ATTACHMENTS_TOTAL_BYTES` | 20 MiB | Decoded size of all attachments in one message |
| `MAX_ATTACHMENT_TEXT_CHARS` | 50,000 characters | Text per attachment placed into the model context (the rest is truncated), and the length limit of an attachment's `content` field in the request |
| `MAX_USER_ATTACHMENT_STORAGE_BYTES` | 200 MiB | Attachment storage per user in the database; beyond it, sending a message returns `413`. Old attachments are never purged automatically; deleting conversations with attachments frees the space |
| `MAX_CONCURRENT_CHAT_STREAMS_PER_USER` | 2 | Answer streams one user may run at once; more get `429` |
| `MAX_LISTED_CONVERSATIONS` (`services/chat_service.py`) | 200 | `GET /api/chat/conversations` lists only the 200 most recently updated conversations |
| `LIST_PREVIEW_MESSAGES` (`services/chat_service.py`) | 5 | Latest messages included with each conversation in the list (without attachment bodies) |
| `MAX_CONVERSATION_MESSAGES` (`services/chat_service.py`) | 500 | Latest messages returned when reading one conversation |

**Tools and outbound requests**

| Constant | Value | Description |
|---|---|---|
| `MAX_TOOL_RESULT_CHARS` | 20,000 characters | Each tool call's result is truncated to this length before it enters the model context |
| `MAX_TEXT_CLEANUP_CHARS` | 2,000,000 characters | HTML is truncated to this length before `web_fetch` extracts text |
| `MAX_DATE_RANGE_CHARS`, `MAX_TARGET_DATES`, `MAX_FILTER_RECORDS` (`rag/tools.py`) | 200 characters, 93 days, 50 records | Length of `filter_and_count_records`' `date_range`, the number of dates it may expand to, and the records returned (a larger `limit` is clamped to 50) |
| `MAX_API_TOOL_RESPONSE_BYTES` (`api/api_tools.py`) | 1 MiB | Response body limit of custom API tools; reading stops and the call returns `502` |
| `MAX_API_TOOL_REDIRECTS` (`api/api_tools.py`), `MAX_MCP_HTTP_REDIRECTS` (`services/mcp_service.py`) | 5, 5 | Redirects that custom API tools and HTTP MCP follow, manually: redirect response bodies are never read, and every hop passes SSRF validation again; HTTP MCP follows only same-origin redirects, and custom API tools drop credential headers on cross-origin redirects. The whole call, redirects included, is also bounded by the tool's or server's `timeout` setting; a custom API tool that runs out of time returns `504` |
| `MAX_MCP_HTTP_RESPONSE_BYTES` (`services/mcp_service.py`) | 4 MiB | Limit for one response from an HTTP MCP server |
| `MAX_MCP_STDIO_LINE_BYTES` (`services/mcp_service.py`) | 4 MiB | Limit for one JSON-RPC message line from a `stdio` MCP subprocess, the same as the HTTP response limit |
| `MCP_STDERR_TAIL_BYTES` (`services/mcp_service.py`) | 2,048 bytes | A `stdio` subprocess's stderr is drained continuously (so a full pipe cannot stall it) and only this many trailing bytes are kept, written to the server log if the subprocess exits abnormally |
| `MAX_CONCURRENT_STDIO_PROCESSES` (`services/mcp_service.py`) | 4 | `stdio` MCP subprocesses alive at once; waiting for a free slot is bounded by the server's `timeout` setting, after which the call fails |
| `APPROVAL_TIMEOUT_SECONDS` (`rag/tool_approval.py`) | 300 seconds | How long a tool call waits for the user's approval; a timeout counts as a denial |
| `DNS_RESOLVE_TIMEOUT_SECONDS`, `DNS_RESOLVER_MAX_WORKERS` (`core/ssrf_protection.py`) | 5 seconds; 8 and 4 threads | SSRF validation resolves DNS in two dedicated thread pools: 8 threads for user-supplied URLs from `web_fetch` (`DnsPool.USER_URL`) and 4 for custom API tools, HTTP MCP, and OpenAPI spec URLs (`DnsPool.CONFIGURED_ENDPOINT`), so slow domains that fill the first pool do not affect the second; a timeout counts as unresolvable |
| `LLM_POOL_ACQUIRE_TIMEOUT_SECONDS` (`core/llm_client.py`) | 15 seconds | Limit for waiting on an LLM connection pool slot, separate from `LLM_TIMEOUT`, so a saturated pool fails fast |
| `REMOTE_MODELS_CACHE_SECONDS` (`api/tags.py`) | 30 seconds | Cache lifetime of the remote model list (failures included) |

**Document parsing**

Admin uploads to the knowledge base and chat attachments each use their own `ExtractionLimits` (`ADMIN_UPLOAD_EXTRACTION_LIMITS` and `CHAT_ATTACHMENT_EXTRACTION_LIMITS`). Any signed-in user can send attachments, and only `MAX_ATTACHMENT_TEXT_CHARS` characters of an attachment's text are used anyway, so the attachment budget is much smaller:

| Item | Admin upload | Chat attachment |
|---|---|---|
| PDF pages sent to Vision OCR (`MAX_PDF_OCR_PAGES`) | unlimited | 20 pages |
| Total uncompressed size of a `.docx`, `.pptx`, or `.xlsx` | 200 MiB (`MAX_OOXML_UNCOMPRESSED_BYTES`) | 64 MiB (`MAX_ATTACHMENT_OOXML_UNCOMPRESSED_BYTES`) |
| OOXML members (`MAX_OOXML_MEMBERS`) | 10,000 | 10,000 |
| XML in a `.docx` or `.pptx` that is built into a DOM | 200 MiB (same as the uncompressed total) | 8 MiB (`MAX_ATTACHMENT_OOXML_XML_BYTES`) |
| Length of JSON and code passed to `json.loads` for structured cleanup | unlimited | 2,000,000 characters (`MAX_ATTACHMENT_STRUCTURED_PARSE_CHARS`) |

| Constant | Value | Description |
|---|---|---|
| `MAX_OCR_PIXELS` | 25,000,000 pixels | Pixel budget for rasterizing one page for OCR; larger pages are rendered at a lower resolution |
| `MAX_OOXML_COMPRESSION_RATIO` | 100 | Maximum compression ratio for a single member, or the whole file, larger than 10 MiB uncompressed (`OOXML_RATIO_CHECK_MIN_BYTES`); the same in both budgets |
| `MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS` | 2 | Chat attachments parsed at once across the whole process; multiplied by the per-file budget, this bounds the memory used for attachment parsing |

The OOXML checks run before parsing and use the sizes the ZIP members declare. python-docx and python-pptx build whole XML parts into a DOM (about 15 to 30 times the XML size in memory); which members count toward the XML total is decided from `[Content_Types].xml` (plus `.rels` files and `[Content_Types].xml` itself), so changing a part's file extension does not get around it. `.xlsx` files are read as a stream, so this item does not apply to them. When a file exceeds any OOXML budget, an admin upload of that file fails; a chat attachment is not parsed, and the model is told that the attachment exceeded the parsing limits and was not read. JSON and code attachments over the length limit skip the structured cleanup and get only the linear noise cleanup.

**Accounts, logs, and detection**

| Constant | Value | Description |
|---|---|---|
| `MAX_PASSWORD_CHARS` | 256 characters | Password length limit for registration, login, and password changes (Argon2 cost grows with length) |
| `MAX_LOGIN_IDENTIFIER_CHARS` | 254 characters | Length limit of the user name or email used to log in |
| `MAX_CONCURRENT_PASSWORD_HASHES` | 4 | Argon2 hashes and verifications running at once, in worker threads |
| `MAX_TRACKED_LOGIN_ACCOUNTS` | 10,000 | Login identifiers that [login throttling](#login-throttling) tracks at once; the one with the oldest last failure is evicted first |
| `MAX_REVOKED_TOKENS` | 100,000 | Entries in the in-process token revocation list; when full, the entries expiring soonest are evicted first |
| `MAX_LOG_FIELD_CHARS` | 200 characters | Length limit of one string field in the security log (such as the account name or User-Agent) |
| `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT` | 10 MiB, 5 files | Rotation size and retained backups of `app.log` and `security.log` |
| `MAX_EVENTS_PER_ADDRESS` | 200 | Events kept per address by the intrusion detector for event types without a rule |
| `MAX_TRACKED_ADDRESSES` | 10,000 | Addresses tracked at once by each of intrusion detection, rate limiting, and login throttling; the least recently active are evicted first |

## Reserved settings

These settings can appear in `.env`, but no code path currently uses them:

| Variable | Code default | Description |
|---|---|---|
| `ENABLE_BATCH_ACCUMULATION` | `false` | Switch for the embedding batch accumulator, which is not wired into the upload flow |
| `BATCH_ACCUMULATOR_SIZE` | `32` | Same as above |

## Removed settings

Ignored if left in `.env`; safe to delete:

| Variable | Removed in | Replacement |
|---|---|---|
| `JWT_SECRET_KEY`, `JWT_ALGORITHM` | 4.0.0 | Tokens are always signed RS256 with the RSA keys in `backend/keys/`; the HS256 fallback is gone |
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
| `VITE_API_BASE` | `/api` | API base. With an absolute URL (such as `http://localhost:8001`) the browser calls the backend directly, so the backend's `ALLOWED_ORIGINS` must include the frontend origin; the value is also the target of the Vite `/api` proxy. `/api` is appended to the path automatically. Its origin is written into the CSP `connect-src` at build time, so changing it requires a rebuild |
| `VITE_API_URL` | — | Used only when `VITE_API_BASE` is unset; same format. When it is an absolute URL, its origin is likewise written into `connect-src` at build time |
| `PORT` | `3000` | Vite dev server port (`bun run preview` always uses 3000) |
| `GENERATE_SOURCEMAP` | emitted | Emit source maps in builds; only `false` turns them off |

`frontend/.env.example` uses the direct mode: `VITE_API_BASE=http://localhost:8001` with `PORT=3001`, an origin already in the backend's default `ALLOWED_ORIGINS`.

The Vite dev and preview servers always listen on `localhost` only (set in `frontend/vite.config.js`, not by an environment variable) and send `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'; img-src 'self' data: blob:`; `/__open-in-editor` answers loopback clients only. To serve devices on the LAN, build with `bun run build`, serve the output from a real web server, and send the same anti-framing headers there.

### Build-time CSP

`bun run build` writes a CSP into `index.html` as a `<meta http-equiv="Content-Security-Policy">` tag (`frontend/vite.config.js`; the dev server needs inline HMR scripts, so this applies to builds only): `default-src 'self'`; scripts and styles only from same-origin files plus the SHA-256 hashes of the inline scripts and styles in `index.html` (the anti-framing guard and theme initialization); images only from `'self'`, `data:`, and `blob:`; `connect-src` set to `'self'` plus the origins of absolute URLs in `VITE_API_BASE` and `VITE_API_URL`; and `object-src 'none'`, `base-uri 'none'`, and `form-action 'self'`. Even when the web server sets no CSP, injected HTML cannot run scripts.

A `<meta>` CSP cannot set `frame-ancestors`, so the web server that serves the build must still send an anti-framing header (`X-Frame-Options: DENY` or `Content-Security-Policy: frame-ancestors 'none'`).
