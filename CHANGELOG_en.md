# Changelog

[繁體中文](CHANGELOG.md) | [English](CHANGELOG_en.md)

All notable changes to AskMiao are documented in this file. The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html): incompatible changes bump the major version, backward-compatible features bump the minor version, and bug fixes bump the patch version.

| Version | Release date | Highlights |
|---|---|---|
| [3.0.0](#300---2026-09-25) | 2026-09-25 | chunk_id index, RRF with a relevance threshold, answer citations, tool trust boundary and admin-only tool management, frontend UI/UX overhaul |
| [2.2.1](#221---2026-09-19) | 2026-09-19 | Error responses use error codes |
| [2.2.0](#220---2026-09-01) | 2026-09-01 | Centralized SSRF protection |
| [2.1.0](#210---2026-08-27) | 2026-08-27 | Custom API tools, OpenAPI import, and MCP integration |
| [2.0.1](#201---2026-08-26) | 2026-08-26 | Multimodal chat and AI document summaries |
| [2.0.0](#200---2026-08-24) | 2026-08-24 | Agentic RAG autonomous research |
| [1.0.0](#100---2026-08-01) | 2026-08-01 | Hybrid RAG and security foundations |

> [!TIP]
> Upgrading from 2.x to 3.0.0? Read the [upgrade guide](docs/upgrading_en.md) first: you need to complete your `.env` and rebuild the knowledge-base index once.

---

## [Unreleased]

### Security

- **MCP SSRF rejections no longer echo resolution results**: when the SSRF guard rejects the URL while creating or discovering an MCP server, `last_error` and the 400 response now say it was rejected and carry an error code; the full reason, which can include private IPs from server-side DNS resolution or redirect targets, goes only to the server log (CWE-209).
- **Intro page RRF demo escapes chunk IDs**: `site/main.js` now passes chunk IDs and reranker probabilities from the embedded JSON through `escapeHtml` before inserting them into HTML, so quotes or angle brackets in the data are no longer parsed as markup (CWE-79).

---

## [3.0.0] - 2026-09-25

This release turns "where did this answer come from" into a verifiable chain: chunks are keyed by a database chunk_id, retrieval fuses tracks with RRF and judges relevance by the reranker probability, and answers cite the sources they actually used as `[n]`. It also adds a trust boundary for tool output, restricts tool management to admins, and overhauls the frontend experience.

> [!WARNING]
> **This release contains breaking changes.** Follow the [upgrade guide](docs/upgrading_en.md) before upgrading:
>
> - `.env` gains 8 required settings: `ENABLE_WEB_SEARCH`, `AGENT_MAX_TURNS`, `CONVERSATION_HISTORY_MESSAGES`, `RRF_K`, `RERANK_RELEVANCE_THRESHOLD`, `WEB_FETCH_ALLOWED_DOMAINS`, `BLOCK_WEB_TOOLS_AFTER_KB`, and `DOMAIN_PROFILE_PATH`. The backend refuses to start if any is missing; Claude models also need `ANTHROPIC_MAX_TOKENS`.
> - Indexes are keyed by chunk_id: the old FAISS index is renamed to `faiss_index.bin.legacy.bak` on first startup, and the index must be rebuilt once before existing documents are searchable again.
> - The reranker is a required component; the backend refuses to start if the model cannot load.
> - The AI tools page and every endpoint under `/api/api-tools` and `/api/mcp` are admin-only; MCP `stdio` subprocesses no longer inherit the backend environment; MCP HTTP servers on loopback or private addresses are rejected.
> - Several settings were removed, `HF_HOME` no longer has a default, the default models changed, and the `/api/admin/rag-config` response fields changed (see the sections below).

### Added

#### Retrieval and indexing

- **Database-backed chunk index**: a new `rag_chunks` table is the single source of truth for chunks; FAISS now uses `IndexIDMap2(IndexFlatIP)`, and both FAISS and BM25 are keyed by chunk_id. At startup the backend reconciles the indexes against the database: it deletes orphaned chunks, removes stale vectors, embeds missing ones, and rebuilds BM25 when it disagrees with the database. See [ADR-0005](docs/adr/0005-chunk-id-index-and-database-source-of-truth_en.md).
- **RRF fusion and relevance threshold**: vector search and BM25 always both run and are merged by rank with standard RRF (`RRF_K`); `RERANK_RELEVANCE_THRESHOLD` applies directly to the reranker probability, exact URL, post ID, and date matches are exempt, and when nothing passes the tool reports that the knowledge base has nothing relevant. See [ADR-0003](docs/adr/0003-rrf-relevance-citations-and-tool-trust_en.md).
- **Domain profile**: new `backend/config/domain_profile.json` and `DOMAIN_PROFILE_PATH` hold domain words, record date fields, and summary fallback rules, validated at startup; the optional `JIEBA_DICTIONARY` replaces the jieba main dictionary.
- **Retrieval evaluation CLI**: `scripts/evaluate_retrieval.py` computes hit@k, recall@k, and MRR read-only on a copy of the index, and `--min-mrr` works as a CI gate; golden sets accept negatives with `"relevant_sources": []`, and `--relevance-thresholds` compares several thresholds over one rerank pass (positive hit rate and negative rejection rate).

#### Agent and models

- **Citations mapped to sources**: each question builds a citation table (`app/rag/research_session.py`), answers cite evidence as `[n]`, and `sources_detail` lists only the cited entries with a `citation` number; frontend badges now read like "[2] 員工手冊.pdf（段落 3）".
- **Tool calling on all five providers**: `llm_client.py` unifies OpenAI, Azure OpenAI, Anthropic Claude (official `anthropic` SDK), Google Gemini (OpenAI-compatible endpoint), and Ollama, with consistent tool calling and streaming behavior.
- Ollama generation options `OLLAMA_TEMPERATURE` and `OLLAMA_NUM_PREDICT` (optional; model defaults apply when unset).

#### Frontend

- **Stop and retry**: answers can be stopped while streaming (a stopped answer is not saved) and the input stays usable during streaming; failed answers show the reason and a retry button, and a message that fails before streaming starts puts its text and attachments back into the input.
- **Appearance switch**: the account menu offers light, dark, and follow-system themes, defaulting to the system setting and applied before first paint, so dark mode no longer flashes white.
- **Confirm before deleting**: deleting conversations, users, documents, custom API tools, and MCP servers, clearing the upload list, and overwriting an edited summary now ask for confirmation (`ConfirmDialog`).
- The chat page adds a jump-to-latest button and announces completed, failed, or stopped answers to screen readers; new offline and back-online notices, a skip link, and a "no permission" page for non-admins on admin pages instead of a native `alert()`.
- `frontend/src/services/sse.ts`: a spec-compliant SSE parser with 8 Vitest tests (events split across reads, CRLF, multi-line data, and more).

#### Documentation and tests

- New [configuration reference](docs/configuration_en.md) (every environment variable explained) and [upgrade guide](docs/upgrading_en.md); new [ADR-0003](docs/adr/0003-rrf-relevance-citations-and-tool-trust_en.md), [ADR-0004](docs/adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md), and [ADR-0005](docs/adr/0005-chunk-id-index-and-database-source-of-truth_en.md).
- 13 new backend test files covering index consistency, RRF and the relevance threshold, citation numbering, agent guardrails, tool calling per provider, conversation history, settings validation, the uploads watcher, and tool management permissions.

### Changed

#### Retrieval and indexing

- Deleting a document removes only that document's chunks and vectors instead of re-embedding everything.
- Retrieval and index writes run in worker threads and no longer block the event loop; reads and writes of chunks, FAISS, and BM25 share one lock.
- The reranker is a required component: the backend refuses to start if it cannot load, and a reranking failure at query time returns an error code instead of unfiltered chunks.
- `search_knowledge_base` with `target_document` restricts candidates before reranking and no longer falls back to the whole library.
- BM25 queries are built from analyzer tokens combined with OR; tokens are always lowercased; the index directory records a tokenizer signature, BM25 is rebuilt automatically on a mismatch (vectors are not recomputed), and read-only evaluation refuses to run.
- Relative path settings (`DATA_DIR`, `UPLOAD_DIR`, index paths, `HF_*`, `DOMAIN_PROFILE_PATH`, `JIEBA_DICTIONARY`) are always resolved against `backend/`.
- Hugging Face settings (`HF_HOME`, `HF_HUB_CACHE`, `SENTENCE_TRANSFORMERS_HOME`, `HF_HUB_OFFLINE`, `HF_HUB_DISABLE_SYMLINKS_WARNING`) are exported to the environment before any model loads; `HF_HOME` no longer defaults to `./data/hf_home` and falls back to the library default `~/.cache/huggingface`.
- The `RERANK_TOP_K` example value in `.env.example` changed from 50 to 20.
- `/api/admin/rag-config` now returns `rrf_k` and `rerank_relevance_threshold` and drops `hybrid_alpha`, `final_threshold`, and `normalization`.

#### Agent and models

- When the model stops calling tools, its answer is used as is instead of being regenerated, and fake streaming is removed; the answer is streamed from a fresh call only when the turn limit is reached or the model returns empty content.
- Conversation history is loaded from the database (the latest `CONVERSATION_HISTORY_MESSAGES` messages), so restarts no longer lose context; `[n]` markers from earlier answers are stripped first so old numbers are not reused.
- `ENABLE_WEB_SEARCH` and `AGENT_MAX_TURNS` are required; with `ENABLE_WEB_SEARCH=false`, `web_search` and `web_fetch` are left out of the tool list.
- Default models updated: `OPENAI_VISION_MODEL` changes from `gpt-4o` to `gpt-6-sol` and `GEMINI_VISION_MODEL` from `gemini-2.5-flash` to `gemini-3.5-flash`; Azure without `AZURE_OPENAI_DEPLOYMENT` now lists `gpt-6-sol`; the built-in model lists now cover GPT-6 / GPT-5.6, Claude Opus 5.5 / Fable 5.1 / Sonnet 5, and Gemini 3.x.

#### Frontend and interface

- Dialogs, the mobile conversation list, and the image viewer use the native `<dialog>`: Esc closes them, the background is inert, and focus returns to the button that opened them; the account menu supports arrow keys.
- The mobile top bar is a single 64px row and the chat page fits one viewport height; buttons and inputs are larger on touch devices, and inputs use 16px text so iPhones no longer zoom in on focus.
- Secondary text, status colors, and dark-mode primary buttons were recolored to meet WCAG AA contrast.
- The brand reads AskMiao everywhere, each page has its own title, and the navigation uses links that mark the current page.
- Message times include the date when not sent today; source relevance is shown as a percentage.
- Frontend text and backend messages use Taiwan Mandarin terms (for example 使用者名稱, 電子郵件, 字元, 權杖), and accessibility labels no longer mix in English.
- The favicon now uses 32px and 64px versions, so visitors no longer download the 4.5 MB 2048px original (which stays as the source of the `site/assets` icons).

#### Versioning and documentation

- The version is 3.0.0 everywhere: the backend reads it from `__version__` in `backend/app/__init__.py`, which both the OpenAPI document and the MCP handshake `clientInfo` use; the frontend `package.json` matches; the OpenAPI title is now "AskMiao API".
- The README, API reference, architecture document, and `llms.txt` were rewritten for 3.0.0 in both languages, fixing statements that did not match the code, such as `init_db.py` creating an admin account (it does not), the list of supported knowledge-base file extensions, and the environment variables the frontend actually reads.
- `frontend/.env.example` keeps only the variables the frontend reads, dropping the removed workflow WebSocket URL and backend-only settings.
- The intro site (`site/`) was redesigned around the current implementation: its interactive demos reproduce citation numbering, RRF with the relevance threshold, URL provenance, the SSRF check order, and MCP environment inheritance in the browser, and the screenshots show the new brand.

### Removed

- The `HYBRID_ALPHA`, `NORMALIZATION`, and `FINAL_THRESHOLD` settings and `auto_tune_alpha` (ignored if left in `.env`); query-type routing and the hard-coded FAQ keyword check.
- The daily automatic reindex task (`tasks/index_rebuilder.py`) and the `ENABLE_AUTO_REINDEX`, `ENABLE_AUTO_REINDEX_TASK`, and `REINDEX_HOURS` settings.
- The `DOCUMENTS_PATH` (`documents.pkl`), `TRANSFORMERS_CACHE`, and `HUGGINGFACE_HUB_CACHE` settings; use `HF_HOME` or `HF_HUB_CACHE` for the Hugging Face cache.
- `gpt-5.5`, `gpt-5.2`, `gpt-4o`, `gpt-4o-mini`, `o1`, `o3`, `o3-mini`, and `gemini-2.5-flash` from the built-in model lists; list them in `AVAILABLE_MODELS` to keep using them.
- The hidden auto-loading of `data/jieba_dict.txt`; custom words now always live in the domain profile.
- The `documents_update` WebSocket notification sent by the uploads watcher, which the frontend never received.
- The frontend `dompurify` dependency: react-markdown already refuses to render raw HTML, and the extra pass rewrote answer content.

### Fixed

#### Retrieval and agent

- FAISS, `documents.pkl`, and BM25 were aligned by list position, so deleting documents, rebuilding, load failures, and concurrent writes shifted chunks out of alignment.
- The `AGENT_MAX_TURNS` and `ENABLE_WEB_SEARCH` settings had no effect.
- Reranker scores went through sigmoid twice, squeezing probabilities into the 0.5 to 0.73 range where they could not judge relevance.
- BM25 parsed the whole question with the Whoosh query syntax (AND by default), so multi-word queries often found nothing and punctuation was read as query syntax.
- The relevance threshold applied to the mixed score, so the top candidate always scored 0.15 and passed, and at least one irrelevant chunk always reached the model.
- Chunks found only by BM25 never reached the rerank candidates after weighted fusion.
- The uploads watcher deleted index and database records when an uploaded file went missing, and starting from another directory marked every document as missing; it now logs a single warning instead.
- Claude model IDs used the wrong format (2.2.1 listed them as `claude-4-8-opus`).
- The PostgreSQL init script `init.sql` was missing the `documents.description` column.

#### Frontend

- Pressing Enter to pick a character in Zhuyin, Cangjie, and other input methods sent the message.
- Answers were rewritten: blockquotes broke, `<Button>` in code became lowercase, `<script>` lines disappeared, and paragraphs containing `|` were turned into social post cards.
- SSE events split across network reads were lost, so new conversations did not appear in the sidebar and the next message started yet another conversation.
- A streaming error left the page stuck on "researching" with no message, and a failed conversation list load only showed "no conversations yet".
- Switching conversations mid-stream wrote the answer into the other conversation, and the title jumped back afterwards.
- A wrong password showed "未找到刷新令牌" (refresh token not found) on the login page: 401 responses from login, register, and token refresh no longer trigger a token refresh.
- Keyboard focus was invisible; field labels were not bound to inputs, so screen readers could not name them; suggested prompts, citations, and the upload drop zone were not keyboard-operable.
- On phones the conversation list button was covered by the top bar and answer bubbles were wider than the screen; the desktop chat page had an extra page scrollbar.
- Loading older messages jumped back to the bottom, and scrolling up while streaming was pulled back down.
- A failed knowledge-base delete still reported success and its error could not be dismissed; reloading replaced the page with a spinner; upload failure reasons were dropped; "cancel all uploads" kept uploading the remaining files.
- Errors in the change-password and admin edit-user dialogs appeared on the page behind the dialog.
- AI tools page notifications had no styles, search did not filter MCP servers, forms overflowed on phones, and the OpenAPI import prefilled an example spec.
- Button loading spinners did not spin; the knowledge-base "clear list" button used a nonexistent variant, and two icon names did not exist.
- Copying failed silently where the Clipboard API is unavailable (for example over http on a LAN).
- The admin tables pushed the actions column off screen at 1024px.
- `bun run lint` could not run: the missing `@eslint/js` and `globals` dev dependencies were added.

### Security

- Every tool result is wrapped in an `<untrusted_tool_result>` marker whose id changes per question, and the system prompt treats it as data only.
- `web_fetch` may only read URLs that appear verbatim in the user's message or in this question's built-in tool results (query arguments echoed by tools do not count); new `WEB_FETCH_ALLOWED_DOMAINS` domain allowlist and `BLOCK_WEB_TOOLS_AFTER_KB` (web tools disabled once knowledge-base content has been read).
- **Tool management is admin-only**: any registered user could create a `stdio` MCP server and run arbitrary commands on the host (RCE), and could read tool credentials configured by others. Every endpoint under `/api/api-tools` and `/api/mcp`, including reads, now requires an admin, and the frontend AI tools page is shown to admins only. See [ADR-0004](docs/adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md).
- MCP `stdio` subprocesses inherit only essential system variables such as `PATH` and no longer receive the backend's JWT key, database URL, or model API keys.
- The MCP HTTP transport gains the SSRF validation it was missing, and custom API tools and the MCP HTTP transport validate every redirect again, so an external API can no longer redirect into the internal network or cloud metadata.

---

## [2.2.1] - 2026-09-19

### Fixed

- **Error responses now use error codes**:
  - Added `app/core/error_response.py`: unexpected exceptions and stack traces stay in server logs while clients receive only a random error code and `error_id` (CWE-209 / CWE-497).
  - Applied across `api_tools.py`, `mcp.py`, `chat.py`, and `openapi_parser.py`; input validation errors are marked with `SafeClientError` and returned verbatim so users keep an actionable message.
- **Removed exception text leaking through the RAG stream**: streaming output in `rag/agent.py`, `rag/pipeline.py`, and `rag/tools.py` no longer carries exception details.

---

## [2.2.0] - 2026-09-01

### Fixed

- **SSRF vulnerability in OpenAPI parsing and outbound requests (#25)**:
  - Added `app/core/ssrf_protection.py`, validating user-supplied URLs by scheme, port, hostname, and post-DNS IP ranges, blocking private ranges, loopback and link-local addresses, cloud metadata endpoints, and dangerous ports.
  - `openapi_parser.py`, `rag/tools.py` (`web_fetch`), and `api_tools.py` now route through the SSRF guard.
  - Added `backend/tests/test_ssrf_protection.py` covering both blocked and allowed cases.

---

## [2.1.0] - 2026-08-27

### Added

- **Custom API tools**:
  - New `custom_api_tools` table and `/api/api-tools` endpoints for tool CRUD, enable/disable toggling, and live connectivity tests.
  - A generic HTTP executor handling path variable substitution, query assembly, header and auth injection (Bearer / API Key / Basic), JSON and form body serialization, and timeout isolation.
- **OpenAPI / Swagger import**:
  - New `services/openapi_parser.py` parsing OAS 2.0, 3.0, and 3.1 specs from raw content or a URL, with bulk import of selected endpoints as AI tools (existing names are updated in place).
- **MCP server integration**:
  - New `mcp_servers` table and `/api/mcp` endpoints for server CRUD, preset catalog, tool discovery (`initialize` + `tools/list`), and single-tool invocation tests.
  - New `services/mcp_service.py` providing JSON-RPC clients over `stdio` subprocesses and HTTP.
- **Dynamic tool registration**: `ResearchToolRegistry` loads enabled custom API tools and MCP tools (named `mcp_<server>_<tool>`) whenever tool definitions are assembled — no backend restart required.
- **Frontend AI tools page**: new `/tools` route and `AiTools` page with a tool overview, OpenAPI import wizard, and MCP server management.

### Changed

- Simplified `.gitignore` rules and removed local database files from version control.

---

## [2.0.1] - 2026-08-26

### Added

- **Multimodal chat pipeline**: image and file attachments in chat; images are sent to vision models as `image_url` content parts while text attachments are extracted into the prompt context.
- **Dynamic knowledge base descriptions**: uploads receive an AI-generated outline and summary, with endpoints to regenerate or edit it manually.

### Changed

- Modernized the frontend interface and component library.

---

## [2.0.0] - 2026-08-24

### Added

- **Agentic RAG Autonomous Research Pipeline**:
  - Implemented ReAct research agent (`ResearchAgent`) supporting multi-turn reasoning and Native Tool Calling.
  - Provided native toolset in `ResearchToolRegistry`: internal knowledge base search (`search_knowledge_base`), live web search (`web_search` with Ollama & DuckDuckGo dual fallback), and deep web fetch (`web_fetch`).
- **Reasoning Effort Multi-Tier Selection**:
  - Added 5 reasoning depth levels in the top navigation: `None (none)`, `Low (low)`, `Medium (medium)`, `High (high)`, and `Extreme (xhigh)`.
  - Fully compatible with Azure OpenAI v1 and OpenAI reasoning models, with automated tool-call compatibility handling.
- **Frontend Research Visualization**:
  - Added `ResearchTraceBlock`: Collapsible step-by-step research trace timeline with tool execution logs.
  - Added `SourceBadges`: Clickable external source reference badges that open in new tabs.
- **Modular RAG Engine Architecture**:
  - Refactored RAG subsystem into decoupled modules: index managers (`indices/`), hybrid retrievers (`retrievers/`), pipeline orchestrator (`pipeline.py`), evaluator (`evaluator.py`), and unified facade (`contextual_rag.py`).

### Changed

- **Zero-Dependency Lightweight Core**:
  - Defaulted to built-in SQLite relational database and in-memory caching, eliminating mandatory Docker/PostgreSQL/Redis setups for local development.
  - Streamlined architecture by retiring legacy discussion board and custom agent modules.
  - Removed cache hits to ensure all queries reflect grounded knowledge and live web data.
- **Frontend Experience & Layout**:
  - Unified sidebar into a single adaptive instance (docked on desktop, drawer on mobile).
  - Adopted Bun as the preferred toolchain for package management and building.

### Fixed

- **Azure OpenAI v1 API Compatibility**:
  - Removed legacy `AZURE_OPENAI_API_VERSION` dependency in favor of standard v1 endpoints.
  - Removed unsupported `max_tokens` and `temperature` parameters for reasoning models.
- **Stability & Bug Fixes**:
  - Fixed `NameError` caused by missing `Dict, Any` imports in `MessageResponse`.
  - Fixed `TypeError` in `HybridContextualRAG.generate_response()` missing `reasoning_effort` argument.
  - Fixed 500 error in `/api/chat/models` caused by missing `settings` import and added comma-separated deployment name normalization.
  - Fixed duplicate sidebar rendering on desktop viewports.

---

## [1.0.0] - 2026-08-01

### Added

- Contextual Hybrid RAG retrieval pipeline (FAISS + Whoosh BM25 + Cross-Encoder Reranker).
- RSA-2048 JWT authentication with token revocation blacklist.
- Sensitive data two-layer redaction (`security_logging.py`).
- Document upload, chunking, embedding, and background reindexing tasks.
