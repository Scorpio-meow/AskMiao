<div align="center">

<img src="site/assets/logo-256.png" alt="AskMiao mascot: a black cat with a scorpion tail" width="120" height="120">

# AskMiao

**An enterprise knowledge-base chat system that checks its own sources and cites them**

AskMiao answers with hybrid retrieval (FAISS + BM25 + Cross-Encoder) and agentic RAG research,<br>so every claim in an answer traces back to a document passage or web page, and it says so when the knowledge base has nothing relevant.

[繁體中文](README.md) | [English](README_en.md)

[![Version](https://img.shields.io/badge/version-3.0.0-2563eb?style=flat)](CHANGELOG_en.md)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19.2-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-7-3178C6?style=flat&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?style=flat&logo=vite&logoColor=white)](https://vite.dev/)
[![Bun](https://img.shields.io/badge/Bun-1.x-000000?style=flat&logo=bun&logoColor=white)](https://bun.sh/)
[![License](https://img.shields.io/badge/License-MIT-16a34a?style=flat)](LICENSE)

[Website](https://scorpio-meow.github.io/AskMiao/) · [Quick Start](#quick-start) · [Documentation](#documentation) · [Changelog](CHANGELOG_en.md) · [Upgrade Guide](docs/upgrading_en.md)

</div>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="site/assets/screens/hero-chat-dark.webp">
  <img src="site/assets/screens/hero-chat-light.webp" alt="AskMiao chat: an answer comparing NIST SP 800-63B-4 with the company password policy, citing sources as [n] and listing the cited web page and document passages below" width="1440" height="900">
</picture>

> [!IMPORTANT]
> **3.0.0 contains breaking changes**: 8 new required settings, indexes keyed by chunk_id (rebuild the index once after upgrading), and admin-only tool management. Upgrading from 2.x? Read the [upgrade guide](docs/upgrading_en.md) first.

## Contents

- [Highlights](#highlights)
- [Features](#features)
- [Screenshots](#screenshots)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Development and Testing](#development-and-testing)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [Versioning](#versioning)
- [Contributing](#contributing)
- [License](#license)

---

## Highlights

| | Capability | What it means |
|---|---|---|
| 1 | **Traceable answers** | Answers cite evidence as `[n]`, and the source badges list only the passages or pages actually cited, one click away from the original text |
| 2 | **Honest "nothing found"** | Chunks below the reranker probability threshold are dropped, and when nothing passes the agent says so instead of improvising |
| 3 | **Autonomous research** | A ReAct agent decides whether to search the knowledge base, count records precisely, search the web, or read a page, with the research trace shown live |
| 4 | **Hybrid retrieval** | Vector search and BM25 always both run, fused by rank with RRF and reranked by a Cross-Encoder; chunks are keyed by a database chunk_id |
| 5 | **Five LLM providers** | Ollama, OpenAI, Azure OpenAI, Anthropic Claude, and Google Gemini all support tool calling and streaming |
| 6 | **External tools and MCP** | Paste an OpenAPI spec to import API tools or connect MCP servers; managed by admins only |
| 7 | **Defense in depth** | RSA JWT, Argon2 password hashing, per-hop SSRF validation, a trust boundary for tool output, and error codes instead of stack traces |

## Features

### Agentic RAG research

- **ReAct research loop**: `ResearchAgent` gathers evidence over several rounds with native tool calling, capped by `AGENT_MAX_TURNS`; when the model stops calling tools, that response is the final answer.
- **Four built-in tools**:

  | Tool | Purpose |
  |---|---|
  | `search_knowledge_base` | Search knowledge-base chunks, optionally restricted to one document with `target_document` |
  | `filter_and_count_records` | Count structured records precisely by date, author, or keyword (for example all posts in a month) |
  | `web_search` | Web search via Ollama Web Search when `OLLAMA_API_KEY` is set, otherwise DuckDuckGo |
  | `web_fetch` | Read a full web page, limited to URLs that appear verbatim in the user's message or in this question's tool results |

- **Research trace**: each step's tool, arguments, result preview, and duration stream over SSE and appear as a collapsible timeline.
- **Multimodal questions**: attach images and files; images go to vision models as `image_url` parts, and text attachments are extracted into the question.
- **Conversation history**: each question loads the latest `CONVERSATION_HISTORY_MESSAGES` messages from the database, so restarts keep the context.

### Traceable answers

- Each question builds a citation table keyed by chunk_id for knowledge-base chunks and by URL for web pages; numbers are assigned on first appearance and the model cites them as `[n]`.
- Source badges list only the entries the answer cites, in order of first citation, such as "[2] 員工手冊.pdf（段落 3）"; no citations means no badges.
- Every tool result is wrapped in an `<untrusted_tool_result>` marker whose id changes per question, so the model treats it as data and ignores instructions hidden in documents or web pages.

### Hybrid retrieval engine

```mermaid
flowchart LR
    Q["Question"] --> V["FAISS vector search<br/>TOP_K"]
    Q --> B["BM25 keyword search<br/>jieba tokens, TOP_K"]
    Q --> E["Exact matches<br/>URL / post ID / date / @account"]
    V --> F["RRF fusion<br/>Σ 1 / (RRF_K + rank)"]
    B --> F
    F --> R["Cross-Encoder rerank<br/>top RERANK_TOP_K"]
    E --> R
    R --> T{"Reranker probability ≥<br/>RERANK_RELEVANCE_THRESHOLD"}
    T -->|pass| K["Top FINAL_K chunks<br/>go to the model"]
    T -->|none pass| N["Report nothing relevant"]
```

- **Both tracks always run**: chunks found by only one track still reach the reranker, so proper nouns and codes are no longer drowned out.
- **The threshold reads the reranker probability**: exact URL, post ID, and date matches are exempt and ranked first.
- **The database is the source of truth**: chunks live in the `rag_chunks` table, and FAISS (`IndexIDMap2`) and BM25 are keyed by chunk_id; startup reconciles both indexes automatically, and deleting a document removes only its vectors.
- **Measurable**: `scripts/evaluate_retrieval.py` computes hit@k, recall@k, MRR, and the negative rejection rate from a golden set and compares several thresholds at once.

### Multi-provider LLM

- One calling layer supports **Ollama, OpenAI, Azure OpenAI v1, Anthropic Claude (official SDK), and Google Gemini**, routed by model name, all with tool calling and streaming.
- The frontend switches models and five reasoning levels: `None`, `Low`, `Medium`, `High`, and `X-High`; the level is passed to OpenAI and Azure OpenAI reasoning models.
- The model list comes from `AVAILABLE_MODELS` or is built from the configured keys; see the [configuration reference](docs/configuration_en.md#llm-providers-and-models).

### Knowledge base and document processing

- 27 file extensions: `.txt`, `.md`, `.markdown`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`, `.json`, `.yaml`, `.yml`, `.xml`, `.html`, `.htm`, `.log`, `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.java`, `.cpp`, `.c`, `.sql`, `.sh`, `.ini`, `.env`.
- **Robust PDF extraction**: PyMuPDF extracts text and repairs embedded fonts missing ToUnicode maps; blank or garbled pages go through vision-model OCR (Azure OpenAI, OpenAI, or Gemini), with pypdf as the last fallback.
- **Smart chunking**: Q&A documents become one chunk per question-answer pair, structured records and JSON become one chunk per record, and everything else is split recursively on Chinese punctuation.
- **AI outlines and summaries**: uploads get an AI summary that can be regenerated or edited; rule-based summaries take over when the LLM fails. The summaries also form the knowledge-base catalog the agent uses to decide which document to search.

### External tools and MCP

- **Custom API tools**: create them with a form or bulk-import from an OpenAPI / Swagger spec (OAS 2.0, 3.0, 3.1), with Bearer, API key (header / query), and Basic auth, plus a live test.
- **MCP client**: `stdio` and HTTP transports, automatic tool discovery, and tools added to the agent as `mcp_<server>_<tool>`; presets for time, filesystem, and web fetch servers are built in.
- **Loaded dynamically**: enabled tools are read from the database whenever tool definitions are assembled, so changes need no restart.
- **Admins only**: tools are shared by every user's agent, so `/api/api-tools`, `/api/mcp`, and the AI tools page are admin-only; `stdio` subprocesses inherit only system variables such as `PATH` and never see the backend's keys ([ADR-0004](docs/adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md)).

### Security

- **Authentication**: RSA-2048 signed JWT access tokens with the refresh token in an HttpOnly cookie; logout revokes both; passwords are hashed with Argon2 (legacy bcrypt hashes are upgraded at login).
- **Outbound requests**: OpenAPI spec URLs, `web_fetch`, custom API tools, and the MCP HTTP transport go through `ssrf_protection.py`, which re-checks every redirect and blocks private networks, cloud metadata endpoints, and dangerous ports.
- **Error codes**: unexpected exceptions reach clients only as a random error code, while full stack traces stay in the server log (CWE-209 / CWE-497).
- **Log redaction**: recursive object masking plus regex masking render passwords, tokens, and Authorization headers as `[REDACTED]`.
- **More**: security response headers, per-IP rate limiting, a CORS allowlist, and filename and path traversal checks.

### Frontend experience

- Stop an answer mid-stream or retry a failed one; pressing Enter to pick a character in Zhuyin, Cangjie, and other input methods does not send the message.
- Light, dark, and follow-system appearance, applied before first paint with no white flash.
- Fully usable with a keyboard and screen readers, with WCAG AA contrast; phones get a single-row top bar and a chat page that fits one viewport.
- Deletions ask for confirmation, offline and back-online states are announced, and non-admins see a "no permission" page on admin routes.

## Screenshots

<table>
  <tr>
    <td width="33%" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="site/assets/screens/feature-trace-dark.webp">
        <img src="site/assets/screens/feature-trace-light.webp" alt="AI research trace: a web search, a deep page read, and a knowledge-base search, each step showing its arguments, result preview, and duration">
      </picture>
      <p align="center"><b>Research trace</b><br>Each step's tool, arguments, and result</p>
    </td>
    <td width="33%" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="site/assets/screens/feature-docs-dark.webp">
        <img src="site/assets/screens/feature-docs-light.webp" alt="Knowledge base page: uploaded documents, each with an AI outline and summary that can be edited, regenerated, or deleted">
      </picture>
      <p align="center"><b>Knowledge base</b><br>Uploads, AI summaries, index rebuilds</p>
    </td>
    <td width="33%" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="site/assets/screens/feature-tools-dark.webp">
        <img src="site/assets/screens/feature-tools-light.webp" alt="AI tools overview: counts of built-in tools, MCP servers, and custom API tools with management shortcuts">
      </picture>
      <p align="center"><b>AI tools</b><br>OpenAPI import and MCP servers</p>
    </td>
  </tr>
</table>

> The screenshots come from the real frontend with demo data; the documents, conversations, and numbers shown are illustrative. The interface itself is in Traditional Chinese.

## Architecture

```mermaid
flowchart TB
    subgraph Client ["Frontend · React 19 + TypeScript + Vite 8 (Bun)"]
        ChatUI["Chat<br/>SSE streaming, research trace, citations"]
        DocsUI["Knowledge base (admin)"]
        ToolsUI["AI tools (admin)"]
        AdminUI["Admin dashboard (admin)"]
    end

    subgraph Backend ["Backend · FastAPI (Python 3.10+)"]
        MW["Middleware<br/>security headers, rate limit, CORS"]
        Auth["Auth /api/auth<br/>RSA JWT, revocation list"]
        ChatAPI["Chat /api/chat (SSE)"]
        DocAPI["Documents /api/documents"]
        ToolAPI["Tools /api/api-tools, /api/mcp"]

        subgraph Core ["Agentic RAG core"]
            Agent["ResearchAgent<br/>ReAct tool loop"]
            Session["ResearchSession<br/>citations, URL provenance, trust boundary"]
            Registry["ResearchToolRegistry<br/>built-in, custom API, MCP tools"]
            Retriever["HybridRetriever<br/>RRF, exact matches, rerank, threshold"]
            LLM["llm_client<br/>Ollama, OpenAI, Azure, Claude, Gemini"]
        end

        SSRF["SSRF guard<br/>per-hop validation"]
    end

    subgraph Storage ["Storage"]
        DB[("SQLite / PostgreSQL<br/>users, conversations, documents, rag_chunks, tools")]
        FAISS["FAISS IndexIDMap2<br/>keyed by chunk_id"]
        BM25["Whoosh BM25<br/>keyed by chunk_id"]
        Files["Uploads data/uploads"]
    end

    Client --> MW
    MW --> Auth & ChatAPI & DocAPI & ToolAPI
    ChatAPI --> Agent
    Agent --> Session
    Agent --> Registry
    Agent --> LLM
    Registry --> Retriever
    Registry --> SSRF
    SSRF -.-> Ext["External sites, APIs, and MCP servers"]
    Retriever --> FAISS & BM25
    DocAPI --> Files
    DocAPI --> DB
    Retriever -.->|reconciled at startup| DB
    Auth --> DB
    ToolAPI --> DB
```

The journey of one question:

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant FE as Frontend
    participant API as POST /api/chat/send
    participant AG as ResearchAgent
    participant LLM as Model provider
    participant T as Tools

    U->>FE: Ask a question (optionally with images or files)
    FE->>API: Send the message
    API->>API: Save the user message, load recent history
    API-->>FE: event: start
    loop At most AGENT_MAX_TURNS rounds
        AG->>LLM: Conversation and tool definitions
        LLM-->>AG: Tool calls
        API-->>FE: event: step_start
        AG->>T: Run tools (URL provenance and web limits checked first)
        T-->>AG: Results (numbered for citation, wrapped as untrusted data)
        API-->>FE: event: step_end
    end
    LLM-->>AG: Final answer (citing sources as [n])
    API-->>FE: event: token
    API-->>FE: event: sources (cited sources only)
    API->>API: Save the answer, sources, and research trace
    API-->>FE: event: done
```

See [Architecture & Design](docs/architecture_en.md) for module-level details.

## Quick Start

### Requirements

| Item | Requirement | Notes |
|---|---|---|
| Python | 3.10 or later | Backend |
| Bun | 1.x | Frontend package manager, dev server, and build |
| Database | SQLite (bundled with Python) or PostgreSQL | SQLite works with zero dependencies |
| Models | About 1.2 GB downloaded on first start | Embedding model `BAAI/bge-small-zh-v1.5` and reranker `BAAI/bge-reranker-base` |
| LLM | Any one | A local Ollama, or an OpenAI, Azure OpenAI, Anthropic, or Gemini API key |

### 1. Get the source

```bash
git clone https://github.com/Scorpio-meow/AskMiao.git
cd AskMiao
```

### 2. Configure and start the backend

```bash
cd backend

# create and activate a virtual environment (on Windows you can use py -m venv .venv)
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` before starting:

1. **Database**: the template's `DATABASE_URL` points to PostgreSQL; for a zero-dependency start use `DATABASE_URL=sqlite:///./chatbot.db`.
2. **Keys**: replace `JWT_SECRET_KEY` and `ADMIN_API_KEY` with random strings, for example from `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
3. **Models**: for a local Ollama keep `LLM_API_BASE=http://localhost:11434`; for cloud models fill in the matching API key, and add `ANTHROPIC_MAX_TOKENS` for Claude.

The template already contains the other required settings, so the template values are enough to start. Then run the backend:

```bash
python main.py
```

The first start creates the database tables, generates the RSA keys for JWT (`backend/keys/`), and downloads the embedding and reranker models. When it is up:

- API: `http://localhost:8001`
- Interactive API docs (Swagger UI): `http://localhost:8001/docs`

> [!NOTE]
> `init_db.py` is a compatibility script that adds columns and indexes to older PostgreSQL databases; fresh installs do not need it, and SQLite does not support its `ADD COLUMN IF NOT EXISTS` statement.

### 3. Start the frontend

In another terminal:

```bash
cd frontend
bun install
bun run dev
```

Open `http://localhost:3000`. Without `frontend/.env`, the frontend calls the relative path `/api`, which the Vite dev server proxies to `http://127.0.0.1:8001`, so no CORS setup is needed. If you copied `frontend/.env.example` (`PORT=3001`, calling the backend directly), open `http://localhost:3001` instead.

### 4. Create the first admin

The knowledge base, AI tools, and admin dashboard pages are admin-only, and no admin account exists out of the box:

1. Create an account on the frontend's register page. Passwords need at least 8 characters with an uppercase letter, a lowercase letter, and a digit.
2. In `backend/` (with the virtual environment active), run the command below, replacing `your_username` with the name you just registered:

   ```bash
   python -c "from sqlalchemy import text; from app.models.database import engine; conn = engine.connect(); conn.execute(text('UPDATE users SET is_admin = :flag WHERE username = :name'), {'flag': True, 'name': 'your_username'}); conn.commit()"
   ```

3. Sign out and sign back in to see the admin pages. From then on, admins can promote other users in the admin dashboard.

The command goes through the backend's own database settings, so it works for both SQLite and PostgreSQL.

### 5. Upload documents and ask

1. As an admin, open the knowledge base page and upload documents (up to 10 files per upload, each within `MAX_FILE_SIZE_MB`). AskMiao extracts the text, writes an AI summary, and indexes it.
2. Back in chat, pick a model and a reasoning level, then ask. Each `[n]` in the answer maps to a source badge below it.

### Using PostgreSQL (optional)

`backend/docker-compose.yml` provides PostgreSQL 17 and applies `init.sql` on first start:

```bash
cd backend
docker compose up -d
```

The container publishes port **7690**, so set `.env` to:

```dotenv
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:7690/chatbot
```

## Configuration

Backend settings live in `backend/.env`. These 11 have no defaults, and the backend refuses to start if any is missing (the template provides recommended values):

| Variable | Template | Description |
|---|---|---|
| `DATABASE_URL` | PostgreSQL example | Connection string; use `sqlite:///./chatbot.db` for SQLite |
| `JWT_SECRET_KEY` | placeholder | HS256 signing key used when the RSA keys are unavailable |
| `ADMIN_API_KEY` | placeholder | Admin API key (unused by routes today, but required by settings validation) |
| `ENABLE_WEB_SEARCH` | `true` | Offer `web_search` and `web_fetch` |
| `AGENT_MAX_TURNS` | `5` | Tool-calling turn limit per question (≥ 1) |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | Prior messages loaded as context (0 disables) |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | Domains `web_fetch` may read; only an explicit `*` means unrestricted |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | Disable web tools once knowledge-base content has been read |
| `RRF_K` | `60` | RRF fusion constant |
| `RERANK_RELEVANCE_THRESHOLD` | `0.2` | Reranker probability threshold (provisional; calibrate with a golden set) |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | Domain profile (domain words, date fields, summary fallback rules) |

Common optional settings:

| Variable | Description |
|---|---|
| `LLM_API_BASE` | Ollama base URL (template `http://localhost:11434`) |
| `OPENAI_API_KEY`, `AZURE_OPENAI_*`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | Cloud model keys; their models join the list automatically |
| `ANTHROPIC_MAX_TOKENS` | Output cap per Claude response (required for Claude) |
| `MODEL_NAME`, `AVAILABLE_MODELS` | Default model and a custom model list |
| `CHUNK_SIZE`, `CHUNK_OVERLAP` | Chunk length and overlap (template 300 / 100) |
| `HF_HOME`, `HF_HUB_OFFLINE` | Model cache location and offline mode |
| `ALLOWED_ORIGINS` | CORS origins (needed when the frontend calls the backend directly) |

Every setting, with defaults, template values, provider routing rules, and frontend variables, is in the **[configuration reference](docs/configuration_en.md)**.

## Project Structure

```text
AskMiao/
├── backend/                          # FastAPI backend
│   ├── main.py                       # Entry point (python main.py)
│   ├── app/
│   │   ├── __init__.py               # Backend version __version__
│   │   ├── api/                      # Routers: auth, chat, documents, api_tools, mcp, admin, tags
│   │   ├── core/                     # Settings, auth, security, and the LLM layer
│   │   │   ├── config.py             # Settings: every environment variable and its validation
│   │   │   ├── lifespan.py           # Startup: create tables, initialize RAG, watch uploads
│   │   │   ├── llm_client.py         # One calling layer for five providers (tool calls, streaming)
│   │   │   ├── jwt_auth.py           # RSA JWT, Argon2 password hashing, revocation checks
│   │   │   ├── ssrf_protection.py    # Outbound URL validation and per-hop SSRF checks
│   │   │   ├── error_response.py     # Client-facing error codes
│   │   │   ├── security_logging.py   # Two-layer log redaction
│   │   │   └── domain_profile.py     # Domain profile loading and validation
│   │   ├── models/                   # SQLAlchemy tables and Pydantic request models
│   │   ├── rag/                      # Retrieval and agentic RAG core
│   │   │   ├── contextual_rag.py     # HybridContextualRAG: facade for reconciliation, writes, and search
│   │   │   ├── agent.py              # ResearchAgent: ReAct tool loop and streaming events
│   │   │   ├── research_session.py   # Per-question citations, URL provenance, untrusted-data wrapping
│   │   │   ├── tools.py              # Built-in tools plus custom API / MCP tool registration and execution
│   │   │   ├── pipeline.py           # Chunking and the agent streaming pipeline
│   │   │   ├── tokenizers.py         # jieba tokenizer and tokenizer signature
│   │   │   ├── evaluator.py          # Retrieval evaluation (hit@k, MRR, negative rejection)
│   │   │   ├── indices/              # chunk_store (rag_chunks), vector_store (FAISS), bm25_store
│   │   │   └── retrievers/hybrid.py  # RRF fusion, exact matches, reranking, relevance threshold
│   │   ├── services/                 # Chat, document processing (with PDF OCR), OpenAPI parsing, MCP client
│   │   └── tasks/uploads_watcher.py  # Missing-upload watcher (warnings only)
│   ├── config/domain_profile.json    # Domain profile
│   ├── eval/                         # Retrieval evaluation golden sets
│   ├── scripts/                      # Maintenance scripts
│   ├── tests/                        # pytest suite
│   ├── docker-compose.yml            # Optional PostgreSQL 17 (published on port 7690)
│   ├── init.sql                      # PostgreSQL schema bootstrap
│   ├── init_db.py                    # Compatibility patch for older PostgreSQL databases
│   ├── requirements.txt
│   └── .env.example                  # Backend settings template
├── frontend/                         # React 19 + TypeScript + Vite 8
│   ├── src/
│   │   ├── pages/                    # Chat/, Documents, AiTools, AdminDashboard, login, register, profile
│   │   ├── components/               # Layout, route guards, and the ui/ component library
│   │   ├── hooks/                    # useChat (streaming, stop, retry), useAuth, useDocuments
│   │   ├── services/                 # api.ts (Axios and token refresh), sse.ts (SSE parser)
│   │   ├── contexts/ThemeContext.tsx # Light / dark / follow system
│   │   └── styles/                   # Design tokens and reset
│   ├── package.json                  # Frontend version and scripts
│   └── .env.example
├── site/                             # GitHub Pages intro site (static)
├── docs/
│   ├── api.md                        # API reference
│   ├── architecture.md               # Architecture and design
│   ├── configuration.md              # Configuration reference
│   ├── upgrading.md                  # Upgrade guide
│   └── adr/                          # Architecture decision records
├── .github/workflows/deploy-pages.yml # Deploys site/ to GitHub Pages when it changes
├── llms.txt                          # Project guide for AI agents
├── CHANGELOG.md                      # Release notes
└── LICENSE
```

Every document has an English counterpart ending in `_en`.

## Development and Testing

### Backend tests

```bash
cd backend
python -m pytest
```

- The tests load the settings, so the required settings must be available in `backend/.env` or the environment.
- Some tests load the real embedding and reranker models (the model cache is needed), so a full run takes a few minutes.
- On Windows accounts whose user name contains non-ASCII characters, pass an ASCII temp path such as `--basetemp=C:\pytest-tmp`; otherwise FAISS fails to write its temporary indexes.

### Frontend checks

```bash
cd frontend
bun run test --run   # Vitest unit tests (SSE parser)
bun run lint         # ESLint (JS / JSX)
bun x tsc --noEmit   # TypeScript type check
bun run build        # Build into build/
```

### Maintenance scripts

Run them from `backend/` with `python scripts/<script>`:

| Script | Purpose |
|---|---|
| `evaluate_retrieval.py` | Evaluate retrieval quality with a golden set and compare relevance thresholds (read-only, safe to run alongside the backend); see [calibrating the relevance threshold](docs/configuration_en.md#calibrating-the-relevance-threshold) |
| `reprocess_existing_docs.py` | Offline rebuild: re-extract text, regenerate summaries, re-chunk, and re-index. Stop the backend first |
| `reset_faiss.py` | Delete the FAISS and BM25 index files in `backend/data`, then recompute them from `rag_chunks` (asks for confirmation first) |
| `test_llm_clients.py` | Check the model list and each provider's request format with mocked responses, without calling any API |
| `docx_to_txt.py` | Convert `.docx` files in the upload directory to `.txt` |
| `migrate_sqlite_to_postgres.py` | Known issue: imports the removed `app.models.custom_agent` and cannot run at the moment |

## Troubleshooting

<details>
<summary><b>The backend fails to start with <code>Field required</code></b></summary>

A required setting is missing from `.env`; the error names the fields. Add them as listed under [Configuration](#configuration), or follow the [upgrade guide](docs/upgrading_en.md) when coming from 2.x.

</details>

<details>
<summary><b>The backend fails to start because the reranker cannot load</b></summary>

The reranker is required. The first start downloads it from Hugging Face, so check the network and make sure `HF_HUB_OFFLINE` is not `true`; if the models were downloaded before, point `HF_HOME` at that cache.

</details>

<details>
<summary><b><code>python init_db.py</code> fails with <code>near "EXISTS": syntax error</code></b></summary>

SQLite does not need `init_db.py`; the backend creates the tables at startup. The script only patches older PostgreSQL databases.

</details>

<details>
<summary><b>The knowledge base, AI tools, and admin pages are missing after signing in</b></summary>

Those pages are admin-only. Follow [Create the first admin](#4-create-the-first-admin) and sign in again.

</details>

<details>
<summary><b>Every question reports that the knowledge base has nothing relevant</b></summary>

Make sure documents were uploaded and that `total_vectors` in `GET /api/admin/vector-store/info` (admin only) is above 0. If the index is fine, the relevance threshold may be too high; calibrate it with a real golden set as described in [calibrating the relevance threshold](docs/configuration_en.md#calibrating-the-relevance-threshold).

</details>

<details>
<summary><b>The frontend shows network or CORS errors</b></summary>

- Without `frontend/.env`, the frontend reaches `http://127.0.0.1:8001` through the Vite proxy, so make sure the backend is running on that port.
- With an absolute `VITE_API_BASE`, the browser calls the backend directly, and the backend's `ALLOWED_ORIGINS` must include the frontend origin (for example `http://localhost:3001`).

</details>

<details>
<summary><b><code>bun install</code> on Windows fails with EPERM or creates a folder named <code>~</code> inside frontend</b></summary>

The cache path `~/.bun/install/cache` in `frontend/bunfig.toml` is not expanded on Windows. Pass a cache directory explicitly: `bun install --cache-dir <cache path>`.

</details>

<details>
<summary><b>The API returns <code>429 Too Many Requests</code></b></summary>

Rate limiting counts requests per client IP, 60 per 60 seconds by default. Behind the Vite dev proxy or a reverse proxy every user shares one IP, so raise `RATE_LIMIT_PER_MINUTE` if needed.

</details>

## Documentation

| Document | Contents |
|---|---|
| [API Reference](docs/api_en.md) | Every endpoint's permission, request and response format, the SSE event contract, and error codes |
| [Architecture & Design](docs/architecture_en.md) | Layers, data model, retrieval pipeline, agent loop, authentication, and security design |
| [Configuration Reference](docs/configuration_en.md) | Defaults and effects of every environment variable, provider routing, threshold calibration, frontend settings |
| [Upgrade Guide](docs/upgrading_en.md) | Steps from 2.x to 3.0.0, rollback, and troubleshooting |
| [Architecture Decision Records](docs/adr/README_en.md) | Context, trade-offs, and amendments of major design decisions |
| [llms_en.txt](llms_en.txt) | File map, system constraints, and verification steps for AI agents |
| [Changelog](CHANGELOG_en.md) | What was added, changed, removed, and fixed in each release |
| [Website](https://scorpio-meow.github.io/AskMiao/) | Interactive demos of citations, the retrieval threshold, and the security mechanisms |

## Versioning

- **Current version**: 3.0.0 (2026-09-25); see the [changelog](CHANGELOG_en.md).
- **Policy**: [Semantic Versioning](https://semver.org/). Incompatible changes, such as new required settings or changes to API permissions or the index format, bump the major version.
- **Where the version lives**: `__version__` in `backend/app/__init__.py` (used by the OpenAPI document and the MCP handshake) and `frontend/package.json`, updated together with `CHANGELOG.md` for each release.

## Contributing

Issues and pull requests are welcome:

1. Fork the repository and create a feature branch.
2. Write commit messages following [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) (for example `feat(rag): …` or `fix: …`; mark breaking changes with `!` and a `BREAKING CHANGE` footer).
3. Make sure the backend `python -m pytest` and the frontend `bun run test --run`, `bun run lint`, and `bun x tsc --noEmit` all pass.
4. Documentation is bilingual: whenever you change a document, update its `_en` counterpart and record the change under `[Unreleased]` in `CHANGELOG.md`.
5. The intro site's interactive demos reproduce backend rules in the browser. When you change the rules in these files, update `site/index.html` and `site/main.js` as well:
   - `rag/research_session.py`: citation numbering and URL provenance
   - `rag/retrievers/hybrid.py`: RRF fusion, mixed score, relevance threshold
   - `rag/tools.py`, `core/config.py`: `WEB_FETCH_ALLOWED_DOMAINS`
   - `core/ssrf_protection.py`: SSRF check order and block lists
   - `services/mcp_service.py`: `INHERITED_ENV_VARS`
6. Open a pull request describing the change and how you verified it.

## License

Released under the [MIT License](LICENSE).
