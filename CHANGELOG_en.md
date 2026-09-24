# Changelog

[繁體中文](CHANGELOG.md) | [English](CHANGELOG_en.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

> **Breaking change**: `.env` must now define `RRF_K`, `RERANK_RELEVANCE_THRESHOLD`, `WEB_FETCH_ALLOWED_DOMAINS`, `BLOCK_WEB_TOOLS_AFTER_KB`, and `DOMAIN_PROFILE_PATH`, or the backend refuses to start; the reranker is now a required component. See [ADR-0003](docs/adr/0003-rrf-relevance-citations-and-tool-trust_en.md) for upgrade and rollback steps.

> **Permission and behavior changes**: the AI tools page and `/api/api-tools` / `/api/mcp` are now admin-only; MCP `stdio` servers no longer inherit the backend environment, so list the variables they need in the server's `env_vars`; MCP HTTP servers on loopback or private addresses are rejected. See [ADR-0004](docs/adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md).

### Added
- **RRF fusion and relevance threshold**: vector search and BM25 always both run and are merged by rank with standard RRF (`RRF_K`); `RERANK_RELEVANCE_THRESHOLD` applies directly to the reranker probability, exact URL, post ID, and date matches are exempt, and when nothing passes the tool reports that the knowledge base has nothing relevant.
- **Citations mapped to sources**: each question builds a citation table (`app/rag/research_session.py`), answers cite evidence as `[n]`, and `sources_detail` lists only the cited entries with a `citation` number; frontend badges now read like "[2] 員工手冊.pdf（段落 3）".
- **Domain profile**: new `backend/config/domain_profile.json` and `DOMAIN_PROFILE_PATH` hold domain words, record date fields, and summary fallback rules, validated at startup; the optional `JIEBA_DICTIONARY` replaces the jieba main dictionary.
- **Threshold calibration**: golden sets accept negatives with `"relevant_sources": []`, and `scripts/evaluate_retrieval.py` gains `--relevance-thresholds` to compare several thresholds over one rerank pass (positive hit@k and MRR, negative rejection rate).
- **Stop and retry**: answers can be stopped while streaming (a stopped answer is not saved) and the input stays usable during streaming; failed answers show the reason and a retry button, and a message that fails before streaming starts puts its text and attachments back into the input.
- **Appearance switch**: the account menu offers light, dark, and follow-system themes, defaulting to the system setting and applied before first paint, so dark mode no longer flashes white.
- **Confirm before deleting**: deleting conversations, users, documents, custom API tools, and MCP servers, clearing the upload list, and overwriting an edited summary now ask for confirmation (`ConfirmDialog`).
- The chat page adds a jump-to-latest button and announces completed, failed, or stopped answers to screen readers; new offline and back-online notices, a skip link, and a "no permission" page for non-admins on admin pages instead of a native `alert()`.
- `frontend/src/services/sse.ts`: a spec-compliant SSE parser with 8 Vitest tests (events split across reads, CRLF, multi-line data, and more).

### Changed
- When the model stops calling tools, its answer is used as is instead of being regenerated, and fake streaming is removed; the answer is streamed from a fresh call only when the turn limit is reached or the model returns empty content.
- The reranker is a required component: the backend refuses to start if it cannot load, and a reranking failure at query time returns an error code instead of unfiltered chunks.
- `search_knowledge_base` with `target_document` restricts candidates before reranking and no longer falls back to the whole library.
- BM25 tokens are always lowercased; the index directory records a tokenizer signature, BM25 is rebuilt automatically on a mismatch (vectors are not recomputed), and read-only evaluation refuses to run.
- Relative path settings (`DATA_DIR`, `UPLOAD_DIR`, index paths, `HF_*`, `DOMAIN_PROFILE_PATH`, `JIEBA_DICTIONARY`) are always resolved against `backend/`.
- The `RERANK_TOP_K` example value in `.env.example` changed from 50 to 20.
- `/api/admin/rag-config` now returns `rrf_k` and `rerank_relevance_threshold` and drops `hybrid_alpha`, `final_threshold`, and `normalization`.
- Realigned the documentation set with the current implementation:
  - `docs/api.md` and `docs/api_en.md` rewritten against the actual routers, adding the SSE streaming event contract, custom API tool and MCP endpoints, model listings, and admin endpoints, and removing the no longer existing workflow module plus the `/api/documents/list` and `/api/documents/bulk_delete` sections.
  - `docs/architecture.md` and `docs/architecture_en.md` updated (Redis and the multi-agent board removed) with new sections on external tool / MCP integration, SSRF protection, and the error code mechanism.
  - `README.md` and `README_en.md` updated with the new feature list, directory structure, and environment matrix, plus corrected database and frontend port guidance.
  - `llms.txt` and `llms_en.txt` extended with the new modules and system constraints.
- Dialogs, the mobile conversation list, and the image viewer use the native `<dialog>`: Esc closes them, the background is inert, and focus returns to the button that opened them; the account menu supports arrow keys.
- The mobile top bar is a single 64px row and the chat page fits one viewport height; buttons and inputs are larger on touch devices, and inputs use 16px text so iPhones no longer zoom in on focus.
- Secondary text, status colors, and dark-mode primary buttons were recolored to meet WCAG AA contrast.
- The brand reads AskMiao everywhere, each page has its own title, and the navigation uses links that mark the current page.
- Message times include the date when not sent today; source relevance is shown as a percentage.
- Frontend text and backend messages use Taiwan Mandarin terms (for example 使用者名稱, 電子郵件, 字元, 權杖), and accessibility labels no longer mix in English.
- The favicon now uses 32px and 64px versions, so visitors no longer download the 4.5 MB 2048px original (which stays as the source of the `site/assets` icons).

### Removed
- The `HYBRID_ALPHA`, `NORMALIZATION`, and `FINAL_THRESHOLD` settings and `auto_tune_alpha` (ignored if left in `.env`); query-type routing and the hard-coded FAQ keyword check.
- The hidden auto-loading of `data/jieba_dict.txt`; custom words now always live in the domain profile.
- The `documents_update` WebSocket notification sent by the uploads watcher, which the frontend never received.
- The frontend `dompurify` dependency: react-markdown already refuses to render raw HTML, and the extra pass rewrote answer content.

### Fixed
- The relevance threshold applied to the mixed score, so the top candidate always scored 0.15 and passed, and at least one irrelevant chunk always reached the model.
- Chunks found only by BM25 never reached the rerank candidates after weighted fusion.
- The uploads watcher deleted index and database records when an uploaded file went missing, and starting from another directory marked every document as missing; it now logs a single warning instead.
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
- **Tool management is admin-only**: any registered user could create a `stdio` MCP server and run arbitrary commands on the host (RCE), and could read tool credentials configured by others. Every endpoint under `/api/api-tools` and `/api/mcp`, including reads, now requires an admin, and the frontend AI tools page is shown to admins only.
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
  - Fully compatible with Azure OpenAI v1 and OpenAI reasoning models (GPT-5 series, o-series), with automated tool-call compatibility handling.
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