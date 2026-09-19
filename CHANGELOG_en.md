# Changelog

[繁體中文](CHANGELOG.md) | [English](CHANGELOG_en.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed
- Realigned the documentation set with the current implementation:
  - `docs/api.md` and `docs/api_en.md` rewritten against the actual routers, adding the SSE streaming event contract, custom API tool and MCP endpoints, model listings, and admin endpoints, and removing the no longer existing workflow module plus the `/api/documents/list` and `/api/documents/bulk_delete` sections.
  - `docs/architecture.md` and `docs/architecture_en.md` updated (Redis and the multi-agent board removed) with new sections on external tool / MCP integration, SSRF protection, and the error code mechanism.
  - `README.md` and `README_en.md` updated with the new feature list, directory structure, and environment matrix, plus corrected database and frontend port guidance.
  - `llms.txt` and `llms_en.txt` extended with the new modules and system constraints.

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