# AskMiao Configuration Reference

[繁體中文](configuration.md) | [English](configuration_en.md)

> Every setting in the backend `backend/.env` and the frontend `frontend/.env`, with its default and what it actually does, as of **8.4.0** (to upgrade from 8.3.0, see the [upgrade guide](upgrading_en.md#upgrading-from-830-to-840)). The source of truth is `Settings` in `backend/app/core/config.py`; the template is [`backend/.env.example`](../backend/.env.example).

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
- [Removed settings](#removed-settings)
- [Domain profile](#domain-profile)
- [Calibrating the relevance threshold](#calibrating-the-relevance-threshold)
- [Frontend environment variables](#frontend-environment-variables)

---

## How settings are read

- **Source**: the backend reads `backend/.env` regardless of the startup directory, and process environment variables take precedence over `.env`. Unknown keys are ignored, so removed settings left in `.env` cause no errors.
- **Required settings have no defaults**: if any is missing, the backend stops at startup with a `Field required` error that names the missing fields.
- **Value ranges and formats**: `CONVERSATION_HISTORY_MESSAGES ≥ 0`, `RRF_K ≥ 1`, and `0 ≤ RERANK_RELEVANCE_THRESHOLD ≤ 1`; `LOGIN_MAX_FAILURES_PER_ACCOUNT`, `LOGIN_MAX_FAILURES_PER_ADDRESS`, `LOGIN_FAILURE_WINDOW_SECONDS`, and `LOGIN_LOCKOUT_SECONDS` must all be ≥ 1, `OLLAMA_NUM_CTX` and `RERANKER_OPENVINO_MAX_LENGTH` must also be ≥ 1 when set, and `TOOL_SECRETS_KEY` must be a valid Fernet key; out-of-range or malformed values also stop startup.
- **Booleans**: `true` / `false`, `1` / `0`, and `yes` / `no` all work.
- **Relative paths**: relative values of `DATA_DIR`, `UPLOAD_DIR`, `FAISS_INDEX_PATH`, `BM25_INDEX_DIR`, `METADATA_PATH`, `HF_HOME`, `HF_HUB_CACHE`, `SENTENCE_TRANSFORMERS_HOME`, `DOMAIN_PROFILE_PATH`, `JIEBA_DICTIONARY`, `SKILLS_DIR`, and `LOG_DIR` always resolve against `backend/`. `DATABASE_URL` is not one of them: a relative SQLite path depends on the startup directory.
- **Code default versus template value**: in the tables below, "Code default" applies when `.env` does not set the key, and "Template" is the value suggested by `backend/.env.example`; your `.env` wins whenever they differ.

## Required settings

These 20 settings have no default; the backend does not start if any is missing.

| Variable | Template | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://askmiao_app:your_app_db_password_here@localhost:5432/chatbot` | Database connection string; see [Database](#database) |
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
| `LOG_DIR` | `logs` | Directory of `app.log` and `security.log`; see [Server and runtime](#server-and-runtime) |
| `ENABLE_WEB_SEARCH` | `true` | Offer the web tools |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | Prior messages loaded as context |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | `web_fetch` domain allowlist |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | Disable web tools after knowledge-base content was read |
| `RRF_K` | `60` | RRF fusion constant |
| `RERANK_RELEVANCE_THRESHOLD` | `0.02` | Reranker probability threshold |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | Domain profile path |
| `SKILLS_DIR` | `data/skills` | Agent Skills file directory; see [Storage paths and uploads](#storage-paths-and-uploads) |

Generate a `TOOL_SECRETS_KEY` for each deployment, for example in an environment where the backend dependencies are installed:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## LLM providers and models

Chat only uses the [API connections](#api-connections) available to the account, and document summaries and OCR of scanned PDFs use the [system models](#system-models) chosen by an admin. `.env` holds no provider address or key, only these settings that apply to every LLM call:

| Variable | Code default | Template | Description |
|---|---|---|---|
| `LLM_TIMEOUT` | `120` | `120` | LLM call timeout in seconds, for chat, connection tests, document summaries, and PDF OCR; waiting for a connection-pool slot has a separate fixed 15-second limit (see [resource limits](#resource-limits)) |
| `LLM_TAGS_TIMEOUT` | `10` | — | Timeout in seconds for "Fetch models from API" |
| `OLLAMA_TEMPERATURE` | empty | `0.3` | `temperature` for every Ollama connection; the model default when unset |
| `OLLAMA_NUM_PREDICT` | empty | `2048` | `num_predict` for every Ollama connection; the model default when unset |
| `OLLAMA_NUM_CTX` | empty | commented example | `num_ctx` (context length, ≥ 1) for every Ollama connection; the model default when unset, which may be too short for long retrieved context |

### API connections

Each account can only chat through two kinds of connection, and the model menu groups models by connection:

- **Personal connections**: created by the account itself under "Profile → My API connections"; only the owner sees and uses them.
- **Shared connections**: created by an admin under "Admin → Shared API connections", granted to all accounts (including accounts that register later) or only to the checked accounts. Other accounts never see them in the model list.

| Field | Description |
|---|---|
| Provider | `openai` (OpenAI or a compatible API), `anthropic`, `gemini`, `foundry`, `ollama`, `vllm`; see [provider routing](#provider-routing) for how each is called |
| API address | For example `https://api.openai.com/v1`, `https://api.anthropic.com`, `https://<resource>.services.ai.azure.com`, `https://ollama.com`, `http://<host>:8000/v1` (vLLM) |
| API key | Required for Anthropic, Gemini, and Foundry, optional for OpenAI-compatible services, Ollama, and vLLM; encrypted with `TOOL_SECRETS_KEY` and never read back through the API; leave it blank when editing to keep the stored key, except that changing the provider or API address drops it and it must be entered again |
| Models | The model names offered by this connection (deployment names for Foundry), up to 50 |
| Output token limit | Required for Claude (`anthropic`, or Claude deployments on Foundry); the smaller of it and the model's own output limit is used. Claude's thinking counts toward this limit too, so a limit set too low cuts answers off. Optional for vLLM; see [Connecting vLLM](#connecting-vllm) |

When a new connection is created, the form fills in the provider's official API address and the models below, which can be edited:

| Provider | Prefilled models (8.4.0) |
|---|---|
| OpenAI | `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.4`, `gpt-5.4-mini` |
| Anthropic | `claude-opus-5-5`, `claude-fable-5-1`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-sonnet-5`, `claude-opus-5`, `claude-fable-5`, `claude-opus-4-8`, `claude-haiku-4-5` |
| Gemini | `gemini-4-argon`, `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite` |

Members' personal connections may only point at addresses that resolve to the public internet: this is checked when the connection is saved, and every call goes through the SSRF check and is pinned to the approved IP (the same as custom API tools; see [ADR-0002](adr/0002-external-tools-and-outbound-safety_en.md)). Services on the internal network (such as a local Ollama or vLLM) should be set up by an admin as shared connections. Admins' personal connections and shared connections are not restricted.

Deleting an account deletes its personal connections and removes it from shared connection lists.

### System models

Under "Admin → System models", an admin picks one shared connection, one of its models, and a reasoning effort for each of two purposes. The choice is stored in the `system_models` database table:

| Purpose | When it is called | When nothing is chosen |
|---|---|---|
| Document summary | On upload, on "regenerate summary", and when rebuilding the index for documents that have no summary yet | A rule-based summary is used and no model is called |
| Scanned PDF recognition (OCR) | PDF pages with no text layer, or whose text is judged garbled, in knowledge-base uploads, index rebuilds, and chat attachments; the model must accept image input | Scanned pages are marked as having no extractable text; a PDF with no text at all is rejected |

- Only shared connections can be chosen, and the cost goes to that connection. Chat attachments use the same OCR model, with at most `MAX_PDF_OCR_PAGES` pages per attachment (see [resource limits](#resource-limits)).
- The reasoning effort is required and has the same choices as chat (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`); it is mapped per provider before it is sent, and the UI disables levels the model does not support. Higher levels are slower: thinking models on Ollama (such as qwen3.5 or gemma4) can exceed `LLM_TIMEOUT` on a single summary when thinking stays on, so `none` is recommended for small local models (Ollama then gets `think: false`). Choices made before this column existed become `none` on upgrade.
- When the shared connection is deleted, or edited so that it no longer offers the chosen model, that purpose is cleared automatically. If the connection's key cannot be decrypted (for example after `TOOL_SECRETS_KEY` changed), the purpose is treated as unset and a warning is logged.
- See [API reference: system models](api_en.md#86-system-models) for the endpoints.

### Provider routing

Each API connection is called according to its provider and the model name:

| Provider | Model name | Endpoint |
|---|---|---|
| `foundry` | Starts with `claude-` | `{API address}/anthropic/v1/messages`, authenticated with `x-api-key`; the API address must be `*.services.ai.azure.com` |
| `foundry` | Starts with `gpt-`, `o3`, or `o4` (except `gpt-oss` and `o3-mini`) | `{API address}/openai/v1/responses` |
| `foundry` | Anything else (models starting with `o1`, `gpt-oss`, or `o3-mini`, plus chat-completion models such as Kimi, Mistral, Grok, DeepSeek, Llama) | `{API address}/openai/v1/chat/completions`; `reasoning_effort` is sent when the name starts with `gpt-`, `o1`, `o3`, or `o4`, and not otherwise |
| `anthropic` | Any | Official `anthropic` SDK (Messages API) |
| `gemini` | Any | `{API address}/v1beta/openai/chat/completions` |
| `openai` | Starts with `gpt-6` | `{API address}/responses` |
| `openai` | Anything else | `{API address}/chat/completions` |
| `ollama` | Any | `{API address}/api/chat` |
| `vllm` | Any | `{API address}/chat/completions`; see [Connecting vLLM](#connecting-vllm) |

> [!NOTE]
> `reasoning_effort` is mapped per provider before it is sent (see the [API reference](api_en.md) for the rules); `gpt-5.x` models on Chat Completions (names containing `gpt-5.`) always get `none` when tools are attached, to respect the compatibility limits between reasoning and tool calling; the original `gpt-5`, `gpt-5-mini`, and `gpt-5-nano` do not accept `none`, `xhigh`, or `max`: `none` becomes `minimal` and `xhigh` and `max` become `high`, and otherwise the user's choice is sent.

### Connecting vLLM

vLLM serves an OpenAI-compatible API with `vllm serve`; set the API address to its `/v1` path, for example `http://<host>:8000/v1`. The research assistant sends tool definitions on every turn, which vLLM accepts only when started with `--enable-auto-tool-choice` and a `--tool-call-parser` that matches the model; without them, the connection test reports 「vLLM 伺服器沒有開啟工具呼叫」 (tool calling is not enabled on the vLLM server). Models that think also need `--reasoning-parser`, so the thinking is kept apart from the answer and the research assistant uses only the answer. For example:

```bash
vllm serve Qwen/Qwen3-8B --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3
```

- vLLM 0.23.0 or later is required. Before 0.18.0, `none` is rejected (so the connection test fails), and before 0.21.0, `minimal`, `xhigh`, and `max` are rejected with `400`; 0.21 and 0.22 accept every level, but `none` does not turn thinking off.
- The reasoning level is sent as `reasoning_effort` (`none` through `max`), and vLLM applies it through the model's chat template; with Qwen3, for example, `none` turns thinking off.
- The output token limit is optional; when set it is sent as `max_completion_tokens` and thinking counts toward it, and when empty vLLM decides from the model's context length.
- When vLLM is started with `--api-key`, enter the same key in the connection; otherwise leave the key empty.
- Model names match the model `vllm serve` loaded (or its `--served-model-name`), and "Get models from the API" reads them from `/v1/models`.
- vLLM usually runs on the internal network, so an admin should set it up as a shared connection; members' personal connections can only reach public addresses.

## Agent and web tools

| Variable | Code default | Template | Description |
|---|---|---|---|
| `ENABLE_WEB_SEARCH` | — (required) | `true` | Controls both `web_search` and `web_fetch`; with `false` both are left out of the tool list and calls to them are refused |
| `CONVERSATION_HISTORY_MESSAGES` | — (required, ≥ 0) | `6` | Prior messages loaded from the database as context (user and assistant messages combined; history always starts with a user message); `0` disables history |
| `WEB_FETCH_ALLOWED_DOMAINS` | — (required) | `*` | Domains `web_fetch` may read, including subdomains, comma-separated; only an explicit `*` means unrestricted |
| `BLOCK_WEB_TOOLS_AFTER_KB` | — (required) | `true` | Within one question, refuse `web_search` and `web_fetch` once a knowledge-base tool has returned content |
| `OLLAMA_API_KEY` | empty | commented example | Key for the Ollama Web Search / Web Fetch APIs. When set, `web_search` tries the Ollama API first and falls back to DuckDuckGo; `web_fetch` tries the Ollama API first (falling back to a direct fetch) only when `WEB_FETCH_ALLOWED_DOMAINS` is `*`, and always fetches directly when an allowlist is set. It is not used for model calls, so put an Ollama Cloud key on the API connection |
| `OLLAMA_SEARCH_ENDPOINT` | `https://ollama.com/api/web_search` | — | Ollama Web Search endpoint |
| `OLLAMA_FETCH_ENDPOINT` | `https://ollama.com/api/web_fetch` | — | Ollama Web Fetch endpoint |
| `DUCKDUCKGO_SEARCH_ENDPOINT` | `https://html.duckduckgo.com/html/` | — | Fallback search endpoint for `web_search` |
| `DEFAULT_CONVERSATION_TITLE` | `新對話` | — | Placeholder title of a new conversation; replaced by the first 50 characters of the first user message, followed by `...` when the message is longer |

Format rules for `WEB_FETCH_ALLOWED_DOMAINS`:

- It cannot be empty; write `*` explicitly for no restriction, and `*` cannot be combined with other domains.
- List bare domains only (lowercase letters, digits, hyphens, and dots) without `https://` or paths, for example `gov.tw,example.com`.
- Whatever the allowlist says, `web_fetch` only reads URLs that appeared as a whole URL in the user's message or in this question's tool results (both sides normalized to httpx's form and compared exactly), and every fetch passes SSRF validation.

## Retrieval, reranking, and chunking

Each search runs: `TOP_K` candidates from vector search and from BM25 → RRF fusion keeps the top `RERANK_TOP_K` (plus exact matches on URLs, post IDs, dates, and @accounts) → Cross-Encoder reranking → `RERANK_RELEVANCE_THRESHOLD` → the top `FINAL_K`.

| Variable | Code default | Template | Description |
|---|---|---|---|
| `EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | same | Embedding model; when a new model changes the vector dimension, the old index is renamed to `*.mismatch.bak` and vectors are recomputed from the database chunks |
| `RERANKER_MODEL` | `BAAI/bge-reranker-base` | same | Cross-Encoder reranker, a required component: the backend refuses to start if it cannot load; document-centric deployments can evaluate `BAAI/bge-reranker-v2-m3` (far better negative rejection, but about 3 times slower reranking and weaker ranking of short posts, threshold around 0.01); see the comparison in [ADR-0007](adr/0007-han-ngram-bm25-and-passage-level-evaluation_en.md#5-reranker-comparison-keep-bge-reranker-base) |
| `TOP_K` | `30` | `30` | Candidates fetched by vector search and by BM25 each |
| `RRF_K` | — (required, ≥ 1) | `60` | RRF score = Σ 1 / (`RRF_K` + rank), ranks starting at 1 |
| `RERANK_TOP_K` | `50` | `20` | Fused candidates sent to the reranker; on CPU each pair costs about 0.2 s (300 characters) to 0.4 s (800 characters) |
| `RERANK_WEIGHT` | `0.85` | `0.85` | Sort score = `RERANK_WEIGHT` × reranker probability + (1 − `RERANK_WEIGHT`) × candidate base score; it does not affect the threshold |
| `RERANK_RELEVANCE_THRESHOLD` | — (required, 0 to 1) | `0.02` | Chunks whose reranker probability falls below this are irrelevant; exact URL, post ID, and date matches are exempt; when everything is filtered out the tool reports that the knowledge base has nothing relevant |
| `FINAL_K` | `8` | `8` | Maximum chunks kept after the threshold |
| `SIMILARITY_THRESHOLD` | `0.30` | `0.30` | Used only by standalone vector search (`vector_search`); the main RRF hybrid path does not apply it |
| `CHUNK_SIZE` | `800` | `300` | Chunk length in characters; rebuild the index to apply a change to existing documents |
| `CHUNK_OVERLAP` | `150` | `100` | Characters shared by neighboring chunks |
| `DOMAIN_PROFILE_PATH` | — (required) | `config/domain_profile.json` | Domain profile; see [Domain profile](#domain-profile) |
| `JIEBA_DICTIONARY` | empty | commented example | Replacement jieba main dictionary, such as the Traditional-Chinese-friendly [`dict.txt.big`](https://raw.githubusercontent.com/fxsjy/jieba/master/extra_dict/dict.txt.big); a missing file stops startup, and changing it rebuilds BM25 automatically |

> [!TIP]
> Ordinary Q&A documents (`Q：…` / `A：…`) become one chunk per question-answer pair, not limited by `CHUNK_SIZE`. Structured records from JSON, JSONL, YAML, CSV, XLSX, and JS declarations become one chunk per record; a record longer than `CHUNK_SIZE` is split on whole field lines into several parts that each repeat the record header. `CHUNK_SIZE` must at least fit a record header, or that record cannot be indexed.

## Compute devices

| Variable | Code default | Template | Description |
|---|---|---|---|
| `FORCE_CPU` | `true` | `true` | Use the CPU even when CUDA is available; in CPU mode PyTorch uses min(16, CPU cores) threads |
| `USE_FP16_QUANTIZATION` | `false` | `false` | CUDA only: run the embedding and reranker models in FP16 |
| `RERANKER_OPENVINO_DEVICE` | empty | commented example | Device for running the reranker through OpenVINO (`GPU`, `CPU`; use `GPU` for Intel integrated graphics); empty uses PyTorch. `NPU` is not supported: compilation fails and the server does not start. When set, only the reranker's tokenizer is loaded, not the PyTorch model. The first start converts the model to an OpenVINO IR in `DATA_DIR/openvino_cache`, which takes about 10–30 seconds, or several minutes on a busy machine. The IR file name includes a fingerprint of the model files, so an updated model is converted again automatically. Each call sends 1–`RERANK_TOP_K` pairs, depending on the actual number of candidates. The GPU runs in FP16; probabilities are within 0.01 of PyTorch and the ranking is the same. Measured on an Intel Core Ultra 7 155U, 50 pairs take about 1.5–2.8 s on the GPU (depending on temperature and load), 7.6 s on the CPU, and about 13 s with PyTorch on the CPU. The first time the GPU sees a new number of candidates it spends about 0.3 s more compiling; the compiled kernels are cached in the same folder, so later starts are faster |
| `RERANKER_OPENVINO_MAX_LENGTH` | empty | commented example | Required when `RERANKER_OPENVINO_DEVICE` is set (≥ 1): token length of each query + chunk pair; shorter pairs are padded and longer pairs truncated. It must not exceed the reranker's limit (512 for `bge-reranker-base`), or startup fails |
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
| `SKILLS_DIR` | — (required) | `data/skills` | Agent Skills uploaded by admins on the AI Tools page, one subdirectory `SKILLS_DIR/<name>/` per skill; `.tmp-*` and `.old-*` directories left by an interrupted install are removed at startup |
| `FAISS_INDEX_PATH` | `data/faiss_index.bin` | same | FAISS vector index (`IndexIDMap2`, ids are chunk_ids) |
| `BM25_INDEX_DIR` | `data/bm25_index` | same | Whoosh BM25 index directory (including `tokenizer_signature.json`) |
| `METADATA_PATH` | `data/index_metadata.json` | same | Index metadata (JSON) such as the last rebuild time |
| `MAX_FILE_SIZE_MB` | `50` | `10` | Per-file upload limit for the knowledge base (MB); also sets the upload request body limit, see [Resource limits](#resource-limits). With the Docker Compose deployment in `deploy/`, nginx accepts request bodies up to 120 MiB only, so above 11 any upload larger than 120 MiB is rejected by nginx with `413` first; see [Docker Compose deployment (deploy/.env)](#docker-compose-deployment-deployenv) |
| `UPLOADS_WATCHER_INTERVAL` | `30` | `30` | Seconds between checks for missing uploads; a missing file is logged once and nothing is deleted |

## Database

| Variable | Code default | Template | Description |
|---|---|---|---|
| `DATABASE_URL` | — (required) | PostgreSQL example | SQLAlchemy connection string |
| `DB_POOL_SIZE` | `20` | `20` | Connection pool size (PostgreSQL and other non-SQLite databases; fixed at 5 for SQLite) |
| `DB_MAX_OVERFLOW` | `40` | `40` | Extra connections allowed once the pool is full (fixed at 10 for SQLite) |
| `DB_POOL_RECYCLE` | `3600` | — | Seconds before a connection is recycled |
| `DB_POOL_PRE_PING` | `true` | — | Check connections before use (non-SQLite only) |
| `SQLALCHEMY_ECHO` | `false` | — | Log SQL statements |

Common `DATABASE_URL` values:

| Scenario | Connection string |
|---|---|
| SQLite (zero dependencies) | `sqlite:///./chatbot.db` (relative to the startup directory, so starting in `backend/` gives `backend/chatbot.db`) |
| PostgreSQL 17 from `backend/docker-compose.yml` | `postgresql+psycopg2://<POSTGRES_APP_USER>:<POSTGRES_APP_PASSWORD>@localhost:7690/chatbot` (the container binds `127.0.0.1:7690` only) |
| Your own PostgreSQL | `postgresql+psycopg2://<user>:<password>@<host>:5432/<database>` (a non-superuser account is recommended; see the next section) |

At startup the backend creates the tables, adds and backfills missing new columns (such as `custom_api_tools.requires_approval`, `mcp_servers.requires_approval`, and `users.tokens_valid_after`), and encrypts tool credentials that older versions stored in plaintext (see [Tool credential encryption](#tool-credential-encryption)). New SQLite databases create `users`, `documents`, `rag_chunks`, and `llm_connections` with `AUTOINCREMENT`, so deleted ids are never reused; existing SQLite tables are not rewritten. `init_db.py` is a compatibility script that adds columns and indexes to older PostgreSQL databases; SQLite does not need it (SQLite does not support its `ADD COLUMN IF NOT EXISTS` statement).

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

Self-registered accounts can only use their own API connections and the shared connections granted to them, never the keys in `.env` (see [API connections](#api-connections)). All accounts still share the whole knowledge base and the enabled tools, though (custom API tools and MCP servers are called with the operator's credentials), so on deployments reachable from the public internet, open registration only once anyone who registers may use them.

- `true`: anyone who can reach the API can create a regular account with `POST /api/auth/register`.
- `false`: `POST /api/auth/register` returns `403` and writes `REGISTER_REJECTED` to the security log. The frontend checks `GET /api/auth/registration` (no login required; it returns `{"enabled": false}`), hides the sign-up link on the login page, and shows an explanation on the sign-up page.

Once the first admin exists, other accounts can be added, and their passwords reset, under "Admin → User management". The first admin (or any account when no admin can sign in) is created by running `scripts/create_user.py` in `backend/`:

```bash
python scripts/create_user.py --username alice --email alice@example.com
python scripts/create_user.py --username root --email root@example.com --admin
```

The password is typed twice interactively and never passed as a command-line argument, so it stays out of the shell history and the process list; user names, emails, and passwords follow the same rules as self-registration, and `--admin` creates an admin. The script connects to the database with the same `backend/.env` and creates the tables first if they do not exist.

### Password changes and token revocation

Access and refresh tokens issued before the account's `users.tokens_valid_after` are rejected. The column equals the creation time when an account is created (so old tokens do not carry over when a deleted account's id is reused) and is set to the current time on a password change: after a successful `POST /api/auth/change-password`, every token issued to the account before then, including the current one and those on other devices, stops working immediately, and a stolen refresh token can no longer be renewed. The response clears the refresh token cookie, and every session must sign in again with the new password. Existing databases get the column automatically at backend startup, backfilled from `created_at`.

## Tool credential encryption

| Variable | Code default | Template | Description |
|---|---|---|---|
| `TOOL_SECRETS_KEY` | — (required) | placeholder (not a valid key) | Fernet key that encrypts the credentials of custom API tools and MCP servers; generate one per deployment |

The key format is validated at startup: it must be a Fernet key (32 bytes, URL-safe base64-encoded, 44 characters). The template's placeholder fails validation, so the backend refuses to start until it is replaced. To generate a key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- **What is encrypted**: custom API tools' `headers` and `auth_config` and MCP servers' `env_vars`, `headers`, `oauth_config`, and `oauth_tokens` are encrypted with this key before they reach the database (stored with a `fernet:` prefix), so a leaked database or backup does not expose the credentials directly. Values stored in plaintext by older versions are encrypted automatically at backend startup; old values that are not JSON objects are cleared and must be entered again.
- **Masking in the admin API**: tool and MCP server responses show `••••••••` in place of secret values, so saved credentials can no longer be read back through the API. Secret values are headers other than `Accept`, `Accept-Encoding`, `Accept-Language`, `Cache-Control`, `Content-Type`, and `User-Agent`; the `token`, `key_value`, `password`, and `client_secret` keys of `auth_config`; and every MCP server environment variable and OAuth `client_secret` (MCP OAuth tokens never appear in responses). Settings such as `key_name`, `key_in`, and `username` are shown as before. On update, the submitted value replaces the whole field, and entries still set to `••••••••` keep their stored value; with no stored value to keep, the update returns `400`.
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

Rate limiting counts in each backend process's memory, and the number of tracked addresses is capped (see [Resource limits](#resource-limits)). Exceeding the rate limit always returns `429`, never a `403` that blocks the address (the IP blocklist of earlier versions, which was never populated, has been removed). Within one window (60 seconds), a client IP gets a single warning (with the path) when it is first blocked, and another when the window ends with the number of blocked requests and the count per path; every blocked request still appears in the access log (`status=429`).

## Server and runtime

| Variable | Code default | Template | Description |
|---|---|---|---|
| `ENVIRONMENT` | `development` | `development` | Currently changes only the wording of a CORS line in the startup log; the cookie `Secure` attribute is no longer derived from it and comes from the required `COOKIE_SECURE` (the backend refuses to start without usable RSA keys in every environment) |
| `HOST` | — (required) | `127.0.0.1` | Bind address of `python main.py` (override with `--host`). Keep `127.0.0.1` when only local clients or a reverse proxy on the same host connect; use `0.0.0.0` only when a reverse proxy in a container or on another host must reach the backend |
| `PORT` | `8001` | `8001` | Default port (override with `--port`) |
| `RELOAD` | — (required) | `false` | Reload on code changes; set `true` only for development (override with `--reload` or `--no-reload`) |
| `ENABLE_API_DOCS` | — (required) | `false` | Serve the interactive documentation at `/docs`, `/redoc`, and `/openapi.json`. These pages list every endpoint and parameter, so keep `false` for public deployments; with `false`, none of the three paths is served |
| `LOG_LEVEL` | `INFO` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` (case-insensitive); any other value stops the backend from starting. The level applies to the console and `app.log` output, so third-party packages that set their own logger to `DEBUG` (such as jieba) are limited too. `INFO` records an access entry for every `/api` request plus every model and tool call; `WARNING` keeps only warnings such as failures, timeouts, and rate limiting. Application logs go to `LOG_DIR/app.log` and security events only to `LOG_DIR/security.log` (same format, both rotate by size). `httpx` and `httpcore` are pinned to `WARNING`, so full request URLs (which may carry query-string API keys) are not logged. See [Architecture: logging and request tracing](architecture_en.md#logging-and-request-tracing) for the format and fields |
| `LOG_DIR` | — (required) | `logs` | Log directory; a relative path resolves against `backend/` and the directory is created if missing; `app.log` and `security.log` are each opened when their first entry is written. Security events from the backend tests (pytest) always go to that test run's temporary directory, never here. Windows cannot rename a file another process has open, so give each backend running at the same time (such as a separate test backend) its own `LOG_DIR`; otherwise rotation fails once the size limit is reached and entries are lost |

`HOST`, `PORT`, `RELOAD`, and `FORWARDED_ALLOW_IPS` apply only when the backend is started with `python main.py`; started any other way (for example by running `uvicorn main:app` directly), they are not applied, although `HOST` and `RELOAD` are still required. The uvicorn server started by `python main.py` processes proxy headers (`proxy_headers`) only when `FORWARDED_ALLOW_IPS` is set; see [Network access control](#network-access-control).

### Docker Compose deployment (deploy/.env)

With `deploy/docker-compose.yml`, both the compose variables and the backend container's environment (`env_file`) come from `deploy/.env`, and the backend container starts with `python main.py`. See the [deployment guide](deployment_en.md) for step-by-step instructions.

`deploy/docker-compose.yml` ships no passwords or network settings, and `docker compose` refuses to start if any of these variables is missing:

| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD`, `POSTGRES_APP_USER`, `POSTGRES_APP_PASSWORD` | Same as in [PostgreSQL non-superuser account](#postgresql-non-superuser-account) |
| `WEB_PORT` | Host port mapped to port 80 of the `web` (nginx) container |
| `WEB_CONTAINER_IP` | Fixed IP of the `web` container on the compose network |
| `NETWORK_SUBNET` | Subnet of the compose network `askmiao-net`; pick a range that does not overlap the company network, a VPN, or other Docker networks on the host |

`deploy/gen-env.sh` generates the file: `PUBLIC_ORIGIN`, `WEB_PORT`, `NETWORK_SUBNET`, and `WEB_CONTAINER_IP` must be given as environment variables, and the script refuses to overwrite an existing `deploy/.env`. It copies `backend/.env.example` and appends these values at the end:

| Variable | Value written |
|---|---|
| `HOST` | `0.0.0.0`, so the nginx container can connect |
| `ENVIRONMENT` | `production`; currently this only changes the wording of the CORS line in the startup log (`backend/app/middleware.py`) |
| `COOKIE_SECURE` | `true` when `PUBLIC_ORIGIN` starts with `https://`, otherwise `false` |
| `TOOL_SECRETS_KEY` | A randomly generated Fernet key |
| `POSTGRES_PASSWORD`, `POSTGRES_APP_USER`, `POSTGRES_APP_PASSWORD` | Two randomly generated passwords; the account is `askmiao_app` |
| `DATABASE_URL` | That account on the `chatbot` database at `postgres:5432` |
| `ALLOWED_ORIGINS` | `PUBLIC_ORIGIN` |
| `FORWARDED_ALLOW_IPS` | `WEB_CONTAINER_IP`; the nginx in the container overwrites the header with `X-Forwarded-For: $remote_addr`, so rate limiting and login throttling count real client IPs |
| `WEB_PORT`, `WEB_CONTAINER_IP`, `NETWORK_SUBNET` | The values given |

The nginx in the container accepts request bodies up to 120 MiB only (`client_max_body_size 120m` in `deploy/nginx.conf`). With `MAX_FILE_SIZE_MB` above 11, the backend's document upload body limit (see [Resource limits](#resource-limits)) exceeds 120 MiB, and uploads larger than 120 MiB are rejected by nginx with `413` first.

## Resource limits

The limits below protect a single backend process and the operator's paid usage. They are code constants, **not** `.env` settings, and live in [`backend/app/core/limits.py`](../backend/app/core/limits.py) (a few constants tied to one module are defined there, as noted in the tables). To change one, edit the source and update this section.

**Requests and chat**

| Constant | Value | Description |
|---|---|---|
| `MAX_REQUEST_BODY_BYTES` | 1 MiB | Body limit for general API requests and for every request without a valid access token; larger bodies get `413`. An oversized `Content-Length` is rejected up front, and chunked bodies are counted as they arrive |
| `MAX_CHAT_REQUEST_BODY_BYTES` | about 27.7 MiB | Body limit of `POST /api/chat/send` (20 MiB of attachments inflated 4/3 by base64, plus 1 MiB); applies only with a validly signed access token, otherwise the limit stays 1 MiB |
| Document upload body limit | `MAX_FILES_PER_UPLOAD` × `MAX_FILE_SIZE_MB` MiB + 1 MiB | Body limit of `POST /api/documents/upload` (101 MiB with the template's `MAX_FILE_SIZE_MB=10`); raised only when the access token is validly signed and its `is_admin` claim is `true`, otherwise the limit stays 1 MiB. With the deployment in `deploy/`, nginx also caps bodies at 120 MiB, which wins when `MAX_FILE_SIZE_MB` is above 11 |
| `MAX_FILES_PER_UPLOAD` | 10 | Files per upload |
| `MAX_FILENAME_BYTES` | 255 bytes | Length of an uploaded file name in UTF-8 (the Linux file-system limit); a longer name gets `400` for that file |
| `MAX_CHAT_MESSAGE_CHARS` | 20,000 characters | Length of one chat message; longer messages get `422` |
| `MAX_CHAT_ATTACHMENTS` | 5 | Attachments per message |
| `MAX_CHAT_ATTACHMENT_BYTES` | 15 MiB | Decoded size of one attachment; an attachment's `data_url` must be a base64 `data:` URL, and remote URLs are rejected |
| `MAX_CHAT_ATTACHMENTS_TOTAL_BYTES` | 20 MiB | Decoded size of all attachments in one message |
| `MAX_ATTACHMENT_TEXT_CHARS` | 50,000 characters | Text per attachment placed into the model context (the rest is truncated), and the length limit of an attachment's `content` field in the request and of the attachment text saved back to the database |
| `MAX_USER_ATTACHMENT_STORAGE_BYTES` | 200 MiB | Attachment and conversation file storage per user in the database (the length of the user's messages' `context_used` plus the size of their conversation files); beyond it, sending a message returns `413` and the research assistant can no longer create files. Nothing is purged automatically; deleting conversation files or conversations with attachments frees the space |
| `MAX_CONCURRENT_CHAT_STREAMS_PER_USER` | 2 | Answer streams one user may run at once; more get `429` |
| `MAX_LISTED_CONVERSATIONS` (`services/chat_service.py`) | 200 | `GET /api/chat/conversations` lists only the 200 most recently updated conversations |
| `MAX_CONVERSATION_MESSAGES` (`services/chat_service.py`) | 500 | Messages returned at most by one call to `GET /api/chat/conversations/{conversation_id}/messages` (the cap on `limit`) |
| `MAX_HISTORY_ATTACHMENT_CHARS` (`services/chat_service.py`) | 50,000 characters | Total attachment text from earlier user messages carried in the history, counted from the newest message back; equal to `MAX_ATTACHMENT_TEXT_CHARS` |

**Conversation files**

| Constant | Value | Description |
|---|---|---|
| `MAX_CONVERSATION_FILE_BYTES` | 15 MiB | Size of one conversation file, equal to `MAX_CHAT_ATTACHMENT_BYTES`; when a file the research assistant produces or edits is larger, the tool returns an error |
| `MAX_CONVERSATION_FILES` | 100 | Files per conversation (including attachments the user uploaded); past it, sending an attachment returns `400` and the file-creating tools return an error |
| `MAX_FILE_TOOL_CONTENT_CHARS` | 200,000 characters | Length of the `content` string when creating or editing a file, and the combined length of slide titles, bullets, and speaker notes; spreadsheets are limited by cell count instead |
| `MAX_SPREADSHEET_CELLS` | 200,000 | Total cells when creating an `.xlsx` or `.csv` |
| `MAX_PRESENTATION_SLIDES` | 100 | Slides when creating a `.pptx` |
| `MAX_FILE_EDITS` | 50 | Text replacements (`edits`) in one edit |
| `MAX_GENERATED_PDF_PAGES` | 500 | Pages in a generated PDF; past it, the file is not saved and an error is returned |
| `FILE_READ_PAGE_CHARS` | 15,000 characters | Text returned at most by each `read_conversation_file` call; the rest is read in parts with `next_offset` |
| `FILE_TEXT_CACHE_ENTRIES` | 8 | Files whose extracted text `read_conversation_file` keeps cached, so reading one file in parts does not parse it again |

**Tools and outbound requests**

| Constant | Value | Description |
|---|---|---|
| `MAX_TOOL_RESULT_CHARS` | 20,000 characters | Each tool call's result is truncated to this length before it enters the model context |
| `MAX_TOOL_NAME_CHARS` | 64 characters | Length of the tool function names given to the model (the limit of OpenAI and other providers); names generated from an OpenAPI operationId or an MCP tool are truncated with an 8-character hash appended, and longer names created by hand or sent to import return `400` |
| `MAX_OPENAPI_SCHEMA_REFS` | 200 | `$ref`s expanded at most per parameter or request body schema when an OpenAPI spec is parsed; references past this count and cyclic references are replaced by an object schema holding only a description |
| `MAX_OPENAPI_SCHEMA_DEPTH` | 32 | Nesting depth expanded per parameter or request body schema when an OpenAPI spec is parsed (each step into `$ref`, `properties`, `items`, `allOf`, and so on counts as one level); anything deeper is replaced by an object schema holding only a description |
| `MAX_OPENAPI_DOCUMENT_BYTES` | 10 MiB | Size of each document on import: the spec (including Arazzo), Overlays, the spec an Overlay points to, Arazzo `sourceDescriptions`, and external reference documents, whether pasted or fetched from a URL |
| `MAX_OPENAPI_EXTERNAL_DOCUMENTS`, `MAX_OPENAPI_TOTAL_BYTES` | 20 documents, 30 MiB | External reference documents downloaded at most while resolving external `$ref`s, and the combined size of the spec and its external documents; past either, the remaining documents are not loaded and are listed in the warnings |
| `OPENAPI_FETCH_TIMEOUT_SECONDS`, `OPENAPI_FETCH_MAX_REDIRECTS` | 15 seconds, 5 | Timeout and redirect count for fetching those documents from a URL; every hop passes SSRF validation again |
| `MAX_OVERLAY_ACTIONS` (`services/openapi_overlay.py`) | 500 | `actions` in one Overlay; more return `400` |
| `MAX_JSONPATH_CHARS`, `MAX_JSONPATH_NODES` (`services/jsonpath.py`) | 2,000 characters, 100,000 nodes | Length of a JSONPath expression in Overlays and Arazzo workflows, and nodes visited by one query; past either, the query fails |
| `MAX_ARAZZO_STEP_RUNS`, `MAX_ARAZZO_WORKFLOW_SECONDS` | 50 runs, 300 seconds | Total steps run (including `retry`, `goto`, and nested workflows) and total time for one call to an Arazzo workflow tool; past either the call fails, so `goto` or `retry` cannot loop forever |
| `MAX_ARAZZO_RETRY_AFTER_SECONDS` | 30 seconds | Longest wait per `retry` action (`retryAfter`, or a `Retry-After` in seconds from the response), also bounded by the time left |
| `MAX_ARAZZO_NESTED_WORKFLOWS` | 5 levels | Nesting depth of workflows calling other workflows through `dependsOn` or a step's or action's `workflowId` |
| `MAX_REGEX_CONTEXT_CHARS` (`services/arazzo.py`) | 20,000 characters | Arazzo `successCriteria` regex conditions match only this many leading characters of the content |
| `MAX_KB_CATALOG_CHARS` | 4,000 characters | Length of the document catalog (file names and summaries) in the `search_knowledge_base` tool description; it is sent on every model call, so past this length only the first documents are listed and the rest are counted |
| `MAX_MCP_CATALOG_CHARS` | 8,000 characters | Length of the MCP resource or prompt list in the `read_mcp_resource` and `get_mcp_prompt` tool descriptions (each tool separately); servers that do not fit are left out with a warning in the log |
| `MAX_TEXT_CLEANUP_CHARS` | 2,000,000 characters | HTML is truncated to this length before `web_fetch` extracts text and before `web_search` parses a DuckDuckGo result page |
| Web tool timeouts (`rag/tools.py`) | 15 seconds, 12 seconds | Timeout for calls to the Ollama Web Search / Web Fetch APIs, and for `web_search` when it falls back to DuckDuckGo |
| `web_fetch` direct fetch (`rag/tools.py`) | 12 seconds, 5, 5 MiB, 3,500 characters | Timeout, redirect count (every hop passes SSRF validation again and is checked against `WEB_FETCH_ALLOWED_DOMAINS`), and response size of a direct page fetch; the returned text, including text from Ollama Web Fetch, is truncated to 3,500 characters |
| `MAX_DATE_RANGE_CHARS`, `MAX_TARGET_DATES`, `MAX_FILTER_RECORDS` (`rag/tools.py`) | 200 characters, 93 days, 50 records | Length of `filter_and_count_records`' `date_range`, the number of dates it may expand to, and the records returned (a larger `limit` is clamped to 50) |
| `MAX_API_TOOL_RESPONSE_BYTES` (`api/api_tools.py`) | 1 MiB | Response body limit of custom API tools; reading stops and the call returns `502` |
| `MAX_API_TOOL_TEXT_CHARS` (`api/api_tools.py`) | 4,000 characters | Text returned to the model when a custom API tool's response is not JSON (its `Content-Type` lacks `application/json`, or the content does not parse) |
| `MAX_API_TOOL_REDIRECTS` (`api/api_tools.py`), `MAX_MCP_HTTP_REDIRECTS` (`services/mcp_service.py`) | 5, 5 | Redirects that custom API tools and HTTP MCP follow, manually: redirect response bodies are never read, and every hop passes SSRF validation again; HTTP MCP, and custom API tools with methods other than `GET`, `HEAD`, and `OPTIONS`, follow only same-origin redirects, while custom API tools with `GET`, `HEAD`, or `OPTIONS` drop credential headers on cross-origin redirects. The whole call, redirects included, is also bounded by the tool's or server's `timeout` setting; a custom API tool that runs out of time returns `504` |
| `MAX_OAUTH_RESPONSE_BYTES`, `OAUTH_TIMEOUT_SECONDS`, `OAUTH_MAX_REDIRECTS` (`services/oauth_client.py`) | 256 KiB, 15 seconds, 3 | Response size, time limit for the whole request (redirects included), and same-origin-only redirects followed for OAuth requests (the OAuth2 client credentials token endpoint of custom API tools, and the metadata, client registration, and token endpoints of MCP OAuth); every connection passes SSRF validation |
| `MAX_CACHED_TOKENS` (`services/oauth_client.py`) | 1,000 | OAuth2 client credentials tokens cached in the process; when full, the whole cache is cleared |
| `MAX_MCP_HTTP_RESPONSE_BYTES` (`services/mcp_service.py`) | 4 MiB | Limit for one response from an HTTP MCP server |
| `MAX_MCP_STDIO_LINE_BYTES` (`services/mcp_service.py`) | 4 MiB | Limit for one JSON-RPC message line from a `stdio` MCP subprocess, the same as the HTTP response limit |
| `MCP_STDERR_TAIL_BYTES` (`services/mcp_service.py`) | 2,048 bytes | A `stdio` subprocess's stderr is drained continuously (so a full pipe cannot stall it) and only this many trailing bytes are kept, written to the server log if the subprocess exits abnormally |
| `MAX_CONCURRENT_STDIO_PROCESSES` (`services/mcp_service.py`) | 4 | `stdio` MCP subprocesses alive at once; waiting for a free slot is bounded by the server's `timeout` setting, after which the call fails |
| `MCP_DISCOVER_PROBE_TIMEOUT_SECONDS` (`services/mcp_service.py`) | 5 seconds | How long connecting waits for `server/discover` to negotiate the newer protocol (never longer than the server's `timeout`); on timeout the legacy `initialize` is used |
| `MAX_MCP_ERROR_BODY_BYTES` (`services/mcp_service.py`) | 64 KiB | When an HTTP MCP response is not `200`, the body is read up to this size to extract a JSON-RPC error; larger bodies are not parsed |
| `MAX_MCP_TOOL_PAGES` (`services/mcp_service.py`) | 50 pages | Pages read through `nextCursor` for `tools/list`, `resources/list`, and `prompts/list`; more pages fail the listing |
| `MAX_MCP_CATALOG_ITEMS`, `MAX_MCP_URI_CHARS`, `MAX_MCP_CATALOG_DESCRIPTION_CHARS` (`services/mcp_service.py`) | 200 items, 2,048 characters, 500 characters | Only the first 200 resources and the first 200 prompts of each server are kept; resources with a URI longer than 2,048 characters are skipped; descriptions of resources, prompts, and prompt arguments are cut to 500 characters |
| `AUTHORIZATION_STATE_TTL_SECONDS`, `MAX_PENDING_AUTHORIZATIONS` (`services/mcp_oauth.py`) | 600 seconds, 1,000 | Time allowed between starting an MCP OAuth authorization and its callback, and pending authorizations kept in the process at once (when full, the oldest is evicted first) |
| `PROBE_TIMEOUT_SECONDS` (`services/mcp_oauth.py`) | 15 seconds | Timeout for probing the MCP server's `WWW-Authenticate` when an MCP OAuth authorization starts |
| `APPROVAL_TIMEOUT_SECONDS` (`rag/tool_approval.py`) | 300 seconds | How long a tool call waits for the user's approval; a timeout counts as a denial |
| `DNS_RESOLVE_TIMEOUT_SECONDS`, `DNS_RESOLVER_MAX_WORKERS` (`core/ssrf_protection.py`) | 5 seconds; 8 and 4 threads | SSRF validation resolves DNS in two dedicated thread pools: 8 threads for user-supplied URLs from `web_fetch` (`DnsPool.USER_URL`) and 4 for custom API tools, HTTP MCP, and OpenAPI spec URLs (`DnsPool.CONFIGURED_ENDPOINT`), so slow domains that fill the first pool do not affect the second; a timeout counts as unresolvable |
| `LLM_POOL_ACQUIRE_TIMEOUT_SECONDS` (`core/llm_client.py`) | 15 seconds | Limit for waiting on an LLM connection pool slot, separate from `LLM_TIMEOUT`, so a saturated pool fails fast |
| `MAX_DISCOVERED_MODELS` | 500 | Models returned by "Fetch models from API": the first 500 after sorting by name |

**Document parsing**

Admin uploads to the knowledge base and chat attachments each use their own `ExtractionLimits` (`ADMIN_UPLOAD_EXTRACTION_LIMITS` and `CHAT_ATTACHMENT_EXTRACTION_LIMITS`). Any signed-in user can send attachments, and only `MAX_ATTACHMENT_TEXT_CHARS` characters of an attachment's text are used anyway, so the attachment budget is much smaller:

| Item | Admin upload | Chat attachment |
|---|---|---|
| PDF pages sent to Vision OCR (`MAX_PDF_OCR_PAGES`) | unlimited | 20 pages |
| Total uncompressed size of a `.docx`, `.pptx`, or `.xlsx` | 200 MiB (`MAX_OOXML_UNCOMPRESSED_BYTES`) | 64 MiB (`MAX_ATTACHMENT_OOXML_UNCOMPRESSED_BYTES`) |
| OOXML members (`MAX_OOXML_MEMBERS`) | 10,000 | 10,000 |
| XML in a `.docx` or `.pptx` that is built into a DOM | 200 MiB (same as the uncompressed total) | 8 MiB (`MAX_ATTACHMENT_OOXML_XML_BYTES`) |
| Length of JSON, JSONL, YAML, and JS declarations parsed into structured records | unlimited | 2,000,000 characters (`MAX_ATTACHMENT_STRUCTURED_PARSE_CHARS`) |

| Constant | Value | Description |
|---|---|---|
| `MAX_OCR_PIXELS` | 25,000,000 pixels | Pixel budget for rasterizing one page for OCR; larger pages are rendered at a lower resolution |
| `MAX_RECORD_LABEL_CHARS` | 80 characters | Length of the label value in a structured record header; longer values are cut and get "…", while the field value itself is never cut |
| `MAX_SUMMARY_FIELD_NAMES` | 8 | Most field names listed in the summary of structured data |
| `MAX_OOXML_COMPRESSION_RATIO` | 100 | Maximum compression ratio for a single member, or the whole file, larger than 10 MiB uncompressed (`OOXML_RATIO_CHECK_MIN_BYTES`); the same in both budgets |
| `MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS` | 2 | Chat attachments and conversation files (reads and edits) parsed at once across the whole process; multiplied by the per-file budget, this bounds the memory used for attachment parsing |

The OOXML checks run before parsing and use the sizes the ZIP members declare. python-docx and python-pptx build whole XML parts into a DOM (about 15 to 30 times the XML size in memory); which members count toward the XML total is decided from `[Content_Types].xml` (plus `.rels` files and `[Content_Types].xml` itself), so changing a part's file extension does not get around it. `.xlsx` files are read as a stream, so this item does not apply to them. When a file exceeds any OOXML budget, an admin upload of that file fails; a chat attachment is not parsed, and the model is told that the attachment exceeded the parsing limits and was not read. JSON, JSONL, YAML, and JS declaration attachments over the length limit are not parsed into structured records and get only the linear noise cleanup. CSV and XLSX are not subject to this length limit; YAML whose aliases expand to more nodes than the source has characters is never parsed and is handled as plain text.

**Agent Skills**

| Constant | Value | Description |
|---|---|---|
| `MAX_SKILL_ARCHIVE_BYTES` | 10 MiB | Size of an uploaded skill file (`.zip` or `SKILL.md`); the body limit of `POST /api/skills/upload` is this plus 1 MiB, raised only when the access token's `is_admin` claim is `true`, as for document uploads |
| `MAX_SKILL_UNCOMPRESSED_BYTES` | 50 MiB | Total uncompressed size of a skill zip, counted from the bytes actually decompressed; also the total size of an uploaded folder (`POST /api/skills/upload-folder`), whose body limit is this plus 1 MiB, raised only for admins in the same way |
| `MAX_SKILL_FILES` | 500 | Files in one skill; applied to each skill when a folder is uploaded |
| `MAX_SKILL_FOLDER_FILES` | 1000 | Files in one folder upload (`POST /api/skills/upload-folder`), including skipped files such as `.git` |
| `MAX_SKILL_MD_BYTES` | 256 KiB | Size of `SKILL.md` |
| `MAX_SKILL_NAME_CHARS`, `MAX_SKILL_DESCRIPTION_CHARS`, `MAX_SKILL_COMPATIBILITY_CHARS` (`services/agent_skills.py`) | 64, 1,024, 500 characters | Length of `name`, `description`, and `compatibility` in `SKILL.md`; a longer `name` rejects the install, while the other two only add a warning |
| `MAX_SKILL_RESOURCE_LISTING` | 100 | Files listed to the model when a skill is activated |
| `MAX_SKILL_RESOURCE_CHARS` | 20,000 characters | The `SKILL.md` body returned on activation and each `read_skill_resource` result; the rest is truncated |
| `MAX_SKILL_CATALOG_CHARS` | 8,000 characters | Length of the skill catalog (names and descriptions) in the `activate_skill` tool description; skills that do not fit are left out with a warning in the log |
| `MAX_SKILL_SCRIPT_SECONDS` | 60 seconds | Time limit for each `run_skill_script` run; on timeout the whole process group is killed and the result's `timed_out` is `true` |
| `MAX_SKILL_SCRIPT_OUTPUT_CHARS` | 20,000 characters | How much of the script's `stdout` and of its `stderr` is kept, each; beyond it the output is truncated and `output_truncated` is set |
| `MAX_SKILL_SCRIPT_ARGS`, `MAX_SKILL_SCRIPT_ARG_CHARS` | 20 arguments, 1,000 characters | Number of command-line arguments and length of each; past either, the script does not run |
| `MAX_SKILL_SCRIPT_STDIN_CHARS` | 100,000 characters | Length of the text passed on the script's standard input; the rest is truncated |
| `MAX_CONCURRENT_SKILL_SCRIPTS` | 2 | Skill scripts running at once in the whole process; the rest wait in line |

**Accounts, logs, and rate limiting**

| Constant | Value | Description |
|---|---|---|
| `MAX_PASSWORD_CHARS` | 256 characters | Password length limit for registration, login, and password changes (Argon2 cost grows with length) |
| `MAX_LOGIN_IDENTIFIER_CHARS` | 254 characters | Length limit of the user name or email used to log in |
| `MAX_CONCURRENT_PASSWORD_HASHES` | 4 | Argon2 hashes and verifications running at once, in worker threads |
| `MAX_TRACKED_LOGIN_ACCOUNTS` | 10,000 | Login identifiers that [login throttling](#login-throttling) tracks at once; the one with the oldest last failure is evicted first |
| `MAX_REVOKED_TOKENS` | 100,000 | Entries in the in-process token revocation list; when full, the entries expiring soonest are evicted first |
| `MAX_LOG_FIELD_CHARS` | 200 characters | Length limit of one string field in the security log (such as the account name or User-Agent), and of one field in the access, model, tool, and rate-limit log lines (such as a path or error message) |
| `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT` | 10 MiB, 5 files | Rotation size and retained backups of `app.log` and `security.log` |
| `MAX_TRACKED_ADDRESSES` | 10,000 | Addresses tracked at once by each of rate limiting and login throttling; the least recently active are evicted first |
| `MAX_RATE_LIMIT_LOGGED_PATHS` | 10 | Paths counted separately per client IP in the warning written when a rate-limit window ends; other paths only add to the total |

## Removed settings

Ignored if left in `.env`; safe to delete:

| Variable | Removed in | Replacement |
|---|---|---|
| `LLM_API_BASE`, `MODEL_NAME`, `AVAILABLE_MODELS`, `FOUNDRY_API_KEY`, `FOUNDRY_ENDPOINT`, `FOUNDRY_DEPLOYMENT` (and the old `AZURE_OPENAI_*` names), `OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_VISION_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_API_BASE`, `ANTHROPIC_MAX_TOKENS`, `GEMINI_API_KEY`, `GEMINI_API_BASE`, `GEMINI_VISION_MODEL`, `EXTERNAL_TAGS_URL`, `ADD_NGROK_HEADER` | 8.0.0 | Document summaries and OCR of scanned PDFs use the shared connections an admin chooses under "Admin → System models"; see [system models](#system-models). `GET /api/tags` is removed as well |
| `ADMIN_API_KEY` | 6.0.0 | No route ever used it; admin endpoints rely on the account's `is_admin` flag in the database |
| `ENABLE_BATCH_ACCUMULATION`, `BATCH_ACCUMULATOR_SIZE` | 6.0.0 | The embedding batch accumulator was never wired into the upload flow and has been deleted |
| `BASE_URL` | 6.0.0 | Used only by the deleted `healthcheck.py`; for health checks, request `GET /health` directly |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM` | 4.0.0 | Tokens are always signed RS256 with the RSA keys in `backend/keys/`; the HS256 fallback is gone |
| `HYBRID_ALPHA`, `NORMALIZATION` | 3.0.0 | Standard RRF fusion with `RRF_K` |
| `FINAL_THRESHOLD` | 3.0.0 | `RERANK_RELEVANCE_THRESHOLD` |
| `DOCUMENTS_PATH` | 3.0.0 | Chunks live in the `rag_chunks` table |
| `ENABLE_AUTO_REINDEX`, `ENABLE_AUTO_REINDEX_TASK`, `REINDEX_HOURS` | 3.0.0 | Indexes are reconciled against the database at startup, so scheduled rebuilds are unnecessary |
| `TRANSFORMERS_CACHE`, `HUGGINGFACE_HUB_CACHE` | 3.0.0 | `HF_HOME` or `HF_HUB_CACHE` |
| `AZURE_OPENAI_API_VERSION` | 2.0.0 | The Azure OpenAI v1 endpoint |

## Domain profile

The JSON file at `DOMAIN_PROFILE_PATH` (required; template value `config/domain_profile.json`, that is `backend/config/domain_profile.json`) holds deployment-specific domain data and is validated strictly at startup: a missing field, an unknown field, or an empty string stops the backend.

```json
{
  "domain_words": ["補休", "育嬰留停", "免刷卡"],
  "record_date_fields": ["timestamp", "timestampTitle"],
  "record_label_fields": ["title", "name", "author", "id"],
  "record_ignore_fields": ["embedcode", "svg", "icon", "rawhtml", "path", "base64", "style", "imagedata", "svgdata"],
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
| `record_label_fields` | Label fields for structured records: the first top-level field with a value is appended to the record header and stored as `label` in the chunk metadata; may be an empty array, in which case headers carry no label |
| `record_ignore_fields` | Field names (case-insensitive) dropped entirely when parsing structured records, such as embedded HTML, icons, or styles; Base64 images and SVGs inside values need not be listed, since they are always replaced by placeholders |
| `summary_fallback.chat_member_noise_words` | When the LLM summary fails and rule-based summaries take over, words in chat logs that are not member names |
| `summary_fallback.chat_topic_keywords` | Keywords the rule-based summary uses to detect chat log topics |
| `summary_fallback.boilerplate_line_prefixes` | Lines starting with these prefixes (case-insensitive) are treated as footer or copyright noise |

## Calibrating the relevance threshold

The template's `RERANK_RELEVANCE_THRESHOLD=0.02` was calibrated on short social posts, and the best threshold varies widely between datasets: on the built-in enterprise benchmark the positives' top rerank probabilities have a median of about 0.87, yet half of the near-domain negatives also score above 0.12, up to 0.74; on short social posts the positives' median is only 0.37 and a tenth fall below 0.12 (see [ADR-0007](adr/0007-han-ngram-bm25-and-passage-level-evaluation_en.md)). Once your real documents are uploaded, calibrate with your own golden set:

1. **Prepare a golden set**: JSONL with one question per line; `relevant_sources` lists the file names that should be found, and questions the knowledge base cannot answer use an empty list as negatives. See [`backend/eval/retrieval_golden.example.jsonl`](../backend/eval/retrieval_golden.example.jsonl) for the format.

   ```json
   {"query": "特休假的天數如何依年資計算？", "relevant_sources": ["員工手冊.pdf"]}
   {"query": "公司附近有推薦的午餐餐廳嗎？", "relevant_sources": []}
   ```

   To see chunk-level ranking quality, add the optional `relevant_passages`: short verbatim snippets that identify the answer (a distinctive 10 to 25 characters from one sentence, not spanning lines); any knowledge base chunk containing one of them counts as relevant:

   ```json
   {"query": "年資兩年半可以休幾天特休？", "relevant_sources": ["員工手冊.pdf"], "relevant_passages": ["滿 2 年未滿 3 年：10 日"]}
   ```

2. **Compare thresholds**: run the command below in `backend/`. The evaluation runs read-only on a copy of the index and can run alongside the backend; it refuses to run when the index disagrees with the database or the tokenizer signature differs, so start the backend once to reconcile first.

   ```bash
   python scripts/evaluate_retrieval.py --golden eval/retrieval_golden.jsonl --k 1 3 5 --relevance-thresholds 0.1 0.2 0.3 0.4
   ```

3. **Read the report**: it lists MRR, hit@k, recall@k, and the negative rejection rate for the current threshold, then compares every candidate threshold over the same rerank pass; with labelled snippets it also lists chunk-level precision@k, nDCG@k, recall@k, MRR, and candidate recall. Higher thresholds reject more negatives but may miss positives; pick the value that balances the two. Low candidate recall means the answer never reached the reranker (check BM25 tokenization or raise `TOP_K`); high candidate recall with poor ranks is a reranker judgement problem.
4. **Apply it**: set the chosen value as `RERANK_RELEVANCE_THRESHOLD` in `.env` and restart the backend.

Other options: `--min-mrr 0.6` or `--min-passage-ndcg 0.8` exits with code 1 when the metric falls short, which suits CI; `--output report.json` writes the full results.

**Comparing retrieval settings or models**: `--corpus` builds a knowledge base from the files in a directory the same way uploads do, on a temporary SQLite database and temporary indexes that are deleted afterwards, without connecting to the production database; retrieval parameters and models come from `.env`, and environment variables set before the command override them for comparison. The built-in benchmark has 12 fictional company documents and Taiwan's Mass Rapid Transit Act, with 103 positive and 15 negative cases:

```bash
python scripts/evaluate_retrieval.py --corpus eval/corpus --golden eval/corpus_golden.jsonl --k 1 3 5
```

## Frontend environment variables

The frontend works without a `.env`: the API base defaults to the relative path `/api`, which the Vite dev server (port 3000) proxies to `http://127.0.0.1:8001`, so the browser never goes cross-origin and the backend needs no CORS setup.

| Variable | When unset | Description |
|---|---|---|
| `VITE_API_BASE` | `/api` | API base. With an absolute URL (such as `http://localhost:8001`) the browser calls the backend directly, so the backend's `ALLOWED_ORIGINS` must include the frontend origin; the value is also the target of the Vite `/api` proxy. `/api` is appended to the path automatically. Its origin is written into the CSP `connect-src` at build time, so changing it requires a rebuild. When the host name contains `devtunnels.ms`, the port is dropped both from request URLs and from the origin written into `connect-src` (`frontend/src/services/api.ts`, `frontend/vite.config.js`) |
| `VITE_API_URL` | — | Used only when `VITE_API_BASE` is unset; same format. When it is an absolute URL, its origin is likewise written into `connect-src` at build time |
| `PORT` | `3000` | Vite dev server port (`bun run preview` always uses 3000) |
| `GENERATE_SOURCEMAP` | emitted | Emit source maps in builds; only `false` turns them off |

`frontend/.env.example` uses the direct mode: `VITE_API_BASE=http://localhost:8001` with `PORT=3001`, an origin already in the backend's default `ALLOWED_ORIGINS`.

The Vite dev and preview servers always listen on `localhost` only (set in `frontend/vite.config.js`, not by an environment variable) and send `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'; img-src 'self' data: blob:`; `/__open-in-editor` answers loopback clients only. To serve devices on the LAN, build with `bun run build`, serve the output from a real web server, and send the same anti-framing headers there.

### Build-time CSP

`bun run build` writes a CSP into `index.html` as a `<meta http-equiv="Content-Security-Policy">` tag (`frontend/vite.config.js`; the dev server needs inline HMR scripts, so this applies to builds only): `default-src 'self'`; scripts and styles only from same-origin files plus the SHA-256 hashes of the inline scripts and styles in `index.html` (the anti-framing guard and theme initialization); images only from `'self'`, `data:`, and `blob:`; `connect-src` set to `'self'` plus the origins of absolute URLs in `VITE_API_BASE` and `VITE_API_URL` (without the port when the host name contains `devtunnels.ms`); and `object-src 'none'`, `base-uri 'none'`, and `form-action 'self'`. Even when the web server sets no CSP, injected HTML cannot run scripts.

A `<meta>` CSP cannot set `frame-ancestors`, so the web server that serves the build must still send an anti-framing header (`X-Frame-Options: DENY` or `Content-Security-Policy: frame-ancestors 'none'`).