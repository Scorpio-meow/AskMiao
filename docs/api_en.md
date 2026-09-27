# AskMiao API Reference

[繁體中文](api.md) | [English](api_en.md)

> REST, SSE streaming, and WebSocket endpoints of the AskMiao **4.0.0** backend, written against the actual routers in `backend/app/api/`. Once the backend is running you can also try them at `http://localhost:8001/docs` (Swagger UI) and `http://localhost:8001/redoc`; the OpenAPI document is served at `/openapi.json`.

## Contents

- [0. Conventions](#0-conventions)
- [1. Authentication `/api/auth`](#1-authentication-apiauth)
- [2. Chat and research `/api/chat`](#2-chat-and-research-apichat)
- [3. Knowledge-base documents `/api/documents`](#3-knowledge-base-documents-apidocuments)
- [4. Custom API tools `/api/api-tools`](#4-custom-api-tools-apiapi-tools)
- [5. MCP servers `/api/mcp`](#5-mcp-servers-apimcp)
- [6. Model lists `/api/tags`](#6-model-lists-apitags)
- [7. Admin `/api/admin`](#7-admin-apiadmin)
- [8. Health checks](#8-health-checks)
- [9. Error handling](#9-error-handling)
- [10. Known limitations](#10-known-limitations)

---

## 0. Conventions

| Item | Description |
|---|---|
| Base URL | `http://localhost:8001` (set by `HOST` / `PORT`) |
| Authentication | Send `Authorization: Bearer <access_token>`; the refresh token lives in the HttpOnly cookie `refresh_token` (path `/api/auth`) and is sent by the browser automatically |
| Content types | `multipart/form-data` for uploads, `text/event-stream` for chat streaming, `application/json` for everything else |
| Timestamps | ISO 8601 in UTC without a timezone suffix (for example `2026-09-25T02:30:00`) |
| Rate limit | `RATE_LIMIT_PER_MINUTE` requests per client IP per 60 seconds (default 60); beyond that the API returns `429`. The client IP is the direct peer unless `FORWARDED_ALLOW_IPS` names a proxy whose `X-Forwarded-For` is trusted |
| Request body limit | 1 MiB for general requests; `POST /api/chat/send` and `POST /api/documents/upload` allow more with a valid access token. Larger bodies get `413` `{"detail": "請求內容超過大小上限"}`; see [configuration reference: resource limits](configuration_en.md#resource-limits) |

### Permission levels

| Level | Requirement | Otherwise |
|---|---|---|
| Public | No token needed | — |
| Signed in | A valid, unrevoked access token whose account still exists and is active | `401` |
| Admin | The account's `is_admin` is `true` in the database | `403` (`{"detail": "需要管理員權限"}`, "admin permission required") |

> [!NOTE]
> Every request loads the account named by the token's `sub` from the database: once an account is deleted or deactivated, its issued access tokens stop working immediately, and `is_admin` and the role also come from the database, so admin changes apply on the next request. Tokens issued before the account was created (for example after a deleted account's id was reused) get `401`.

API messages are in Traditional Chinese; the English glosses in this document are for reference only.

### Endpoint overview

| Method | Path | Access | Description |
|---|---|---|---|
| POST | `/api/auth/register` | Public | Register and sign in |
| POST | `/api/auth/login` | Public | Sign in |
| POST | `/api/auth/refresh` | Public (cookie required) | Exchange the refresh token for new tokens |
| GET | `/api/auth/me` | Signed in | Get the current profile |
| PUT | `/api/auth/me` | Signed in | Update email or password |
| POST | `/api/auth/change-password` | Signed in | Change the password |
| POST | `/api/auth/logout` | Signed in | Sign out and revoke tokens |
| POST | `/api/auth/validate-token` | Signed in | Check that the access token is valid |
| POST | `/api/chat/send` | Signed in | Send a message; the reply streams over SSE |
| GET | `/api/chat/models` | Public | Available models and the default model |
| GET | `/api/chat/tools` | Signed in | Tool definitions currently available to the agent |
| POST | `/api/chat/approvals/{approval_id}` | Signed in (asking user only) | Approve or deny a pending tool call |
| GET | `/api/chat/conversations` | Signed in | Your conversations |
| POST | `/api/chat/conversations` | Signed in | Create a conversation |
| GET | `/api/chat/conversations/{conversation_id}` | Signed in | One conversation with all messages |
| GET | `/api/chat/conversations/{conversation_id}/messages` | Signed in | Paged messages |
| DELETE | `/api/chat/conversations/{conversation_id}` | Signed in | Delete a conversation |
| WebSocket | `/api/chat/ws/{user_id}` | Public | Demo echo channel |
| POST | `/api/documents/upload` | Admin | Upload and index documents |
| GET | `/api/documents/` | Admin | List documents |
| POST | `/api/documents/{document_id}/regenerate-summary` | Admin | Regenerate the AI summary |
| PUT | `/api/documents/{document_id}/summary` | Admin | Edit the summary |
| DELETE | `/api/documents/{document_id}` | Admin | Delete a document |
| POST | `/api/documents/rebuild-index` | Admin | Fully rebuild the index from the database |
| POST | `/api/api-tools/parse-spec` | Admin | Parse an OpenAPI spec |
| POST | `/api/api-tools/import` | Admin | Bulk-import tools |
| GET | `/api/api-tools` | Admin | List tools |
| POST | `/api/api-tools` | Admin | Create a tool manually |
| GET | `/api/api-tools/{tool_id}` | Admin | Get one tool |
| PUT | `/api/api-tools/{tool_id}` | Admin | Update a tool |
| PATCH | `/api/api-tools/{tool_id}/toggle` | Admin | Enable or disable a tool |
| DELETE | `/api/api-tools/{tool_id}` | Admin | Delete a tool |
| POST | `/api/api-tools/{tool_id}/test` | Admin | Call a tool once |
| GET | `/api/mcp/presets` | Admin | MCP server presets |
| GET | `/api/mcp/servers` | Admin | List MCP servers |
| POST | `/api/mcp/servers` | Admin | Add a server and discover its tools |
| GET | `/api/mcp/servers/{server_id}` | Admin | Get one server |
| PUT | `/api/mcp/servers/{server_id}` | Admin | Update a server |
| DELETE | `/api/mcp/servers/{server_id}` | Admin | Delete a server |
| POST | `/api/mcp/servers/{server_id}/discover` | Admin | Rediscover tools |
| PATCH | `/api/mcp/servers/{server_id}/toggle` | Admin | Enable or disable a server |
| POST | `/api/mcp/servers/{server_id}/tools/{tool_name}/test` | Admin | Call an MCP tool once |
| GET | `/api/tags` | Public | Model list in the Ollama `tags` format |
| GET | `/api/external-tags` | Public | Relay a remote model list |
| GET | `/api/admin/users` | Admin | List users |
| PUT | `/api/admin/users/{user_id}` | Admin | Update a user |
| DELETE | `/api/admin/users/{user_id}` | Admin | Delete a user |
| GET | `/api/admin/statistics` | Admin | System statistics (cached for 180 seconds) |
| GET | `/api/admin/conversations` | Admin | The 50 most recent conversations |
| GET | `/api/admin/conversations/{conversation_id}/messages` | Admin | Messages of any conversation |
| DELETE | `/api/admin/conversations/{conversation_id}` | Admin | Delete any conversation |
| GET | `/api/admin/documents` | Admin | List documents (newest first) |
| DELETE | `/api/admin/documents/{document_id}` | Admin | Delete a document |
| GET | `/api/admin/rag-config` | Admin | Current retrieval parameters |
| GET | `/api/admin/vector-store/info` | Admin | Basic index information |
| GET | `/api/admin/vector-store/statistics` | Admin | Index statistics |
| POST | `/api/admin/vector-store/reindex` | Admin | Recompute vectors from the existing chunks |
| DELETE | `/api/admin/vector-store/clear` | Admin | Clear chunks and indexes |
| GET | `/` | Public | Liveness message |
| GET | `/health` | Public | Health check |

---

## 1. Authentication `/api/auth`

### Token model

| Token | Where it lives | Lifetime | Purpose |
|---|---|---|---|
| Access token | `tokens.access_token` in the JSON response; the frontend sends it in the `Authorization` header | `ACCESS_TOKEN_EXPIRE_MINUTES` (30 minutes by default) | Calls every signed-in endpoint; carries `sub`, `username`, `email`, `role`, and `is_admin`, but the backend uses only `sub` and `iat` to find the database account, whose identity and permissions are authoritative |
| Refresh token | HttpOnly cookie `refresh_token`, path `/api/auth` | `REFRESH_TOKEN_EXPIRE_DAYS` (7 days by default) | Used only by `POST /api/auth/refresh`, and only once; every exchange resets the cookie |

Tokens are always signed RS256 with an RSA-2048 private key; the backend refuses to start if the RSA keys cannot be loaded. `tokens.refresh_token` in the JSON response is always an empty string because the real refresh token only lives in the cookie, and `expires_in` is currently always `1800`; the `exp` claim inside the token is authoritative.

### 1.1 POST /api/auth/register

Create an account and sign in: the access token is returned and the refresh token is set as a cookie. New accounts are always regular users.

**Request body**

| Field | Type | Required | Rules |
|---|---|---|---|
| `username` | string | Yes | 3–50 characters: letters (including CJK), digits, underscores, and hyphens only |
| `email` | string | Yes | A valid email address |
| `password` | string | Yes | 8–256 characters with an uppercase letter, a lowercase letter, and a digit |

**Response**: `201 Created`

```json
{
  "user": {
    "id": 1,
    "username": "miao_user",
    "email": "user@example.com",
    "role": "user",
    "is_active": true,
    "is_admin": false,
    "created_at": "2026-09-25T02:30:00",
    "last_login": null
  },
  "tokens": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "",
    "token_type": "bearer",
    "expires_in": 1800
  },
  "message": "註冊成功"
}
```

| Status | When |
|---|---|
| `400` | The username or email is taken (`使用者名稱已被使用`, `電子郵件已被使用`), or the password is too weak (for example `密碼必須包含至少一個大寫字母`, "must contain an uppercase letter") |
| `422` | Field format errors (length, characters, email format) |

### 1.2 POST /api/auth/login

Sign in with a username **or** an email address.

**Request body**: `{"username": "miao_user", "password": "Secret123"}` (`username` at most 254 characters, `password` at most 256)

**Response**: `200 OK` with the same shape as registration (`message` is `登入成功`), and `last_login` is updated. Passwords stored as legacy bcrypt hashes are re-hashed with Argon2 on a successful sign-in.

| Status | When |
|---|---|
| `401` | `使用者名稱或密碼錯誤` (wrong username or password); deactivated accounts get the same response |
| `422` | A field exceeds its length limit |

### 1.3 POST /api/auth/refresh

Read the refresh token from the cookie, issue a new access token, and reset the cookie; no `Authorization` header is needed. The token is likewise mapped to the database account by `sub` (the account must exist and be active), and the used refresh token is revoked immediately, so reusing it returns `401`.

**Response**: `200 OK`

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "",
  "token_type": "bearer",
  "expires_in": 1800
}
```

| Status | When |
|---|---|
| `401` | Refresh token missing (`找不到重新整理權杖`), invalid (`重新整理權杖無效`), of the wrong type (`重新整理權杖類型無效`), revoked (`權杖已被撤銷`, including an already used token), belonging to a missing or deactivated account, or expired |

### 1.4 GET /api/auth/me

Get the signed-in user's profile (`UserProfile`: `id`, `username`, `email`, `role`, `is_active`, `is_admin`, `created_at`, `last_login`).

### 1.5 PUT /api/auth/me

Update the email or password; send only the fields you change.

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string | No | New email, unique across users |
| `current_password` | string | When changing the password | Current password |
| `new_password` | string | No | New password, same rules as registration |

Password fields accept at most 256 characters. **Response**: `200 OK` with the updated `UserProfile`. Errors return `400`: email taken (`該電子郵件已被使用`), current password missing (`請提供目前的密碼`) or wrong (`目前的密碼錯誤`), or a password strength message.

### 1.6 POST /api/auth/change-password

| Field | Type | Required | Description |
|---|---|---|---|
| `current_password` | string | Yes | Current password |
| `new_password` | string | Yes | New password, same rules as registration |
| `confirm_password` | string | Yes | Must equal `new_password`, otherwise `422` |

**Response**: `200 OK` `{"message": "密碼修改成功", "success": true}`; a wrong current password returns `400` `目前的密碼錯誤`.

### 1.7 POST /api/auth/logout

Add the access token from the `Authorization` header and the refresh token from the cookie to the revocation list (each kept until it expires), and delete the cookie.

**Response**: `200 OK` `{"message": "登出成功", "success": true}`

> [!NOTE]
> The revocation list lives in the backend process's memory (at most 100,000 entries; when full, the entries expiring soonest are evicted first). It is cleared when the backend restarts, and unexpired tokens become valid again.

### 1.8 POST /api/auth/validate-token

**Response**: `200 OK` `{"message": "權杖有效", "success": true}`; an invalid token returns `401`.

---

## 2. Chat and research `/api/chat`

### 2.1 POST /api/chat/send

Send a message and start the `ResearchAgent`. The response is a **Server-Sent Events** stream (`Content-Type: text/event-stream`, with `Cache-Control: no-cache` and `X-Accel-Buffering: no`).

**Request body**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `content` | string | Yes | — | The user's question, at most 20,000 characters |
| `conversation_id` | integer | No | `null` | Conversation ID; a new conversation is created when it is empty, unknown, or not yours |
| `model_name` | string | No | Default model | Model to use; it must be in the [available model list](configuration_en.md#model-list) or equal `MODEL_NAME`, otherwise `400` `不支援的模型` ("unsupported model"); the provider is routed by name |
| `reasoning_effort` | string | No | `medium` | Reasoning level, sent only to OpenAI and Azure OpenAI; see below |
| `attachments` | array | No | `[]` | Attachments, at most 5; see the table below |

`attachments[]` fields:

| Field | Type | Description |
|---|---|---|
| `filename` | string | File name, at most 255 characters |
| `file_type` | string | MIME type, at most 255 characters; `image/*` goes to the vision model, other types are extracted as text |
| `file_size` | integer | Optional file size |
| `data_url` | string | Optional; must be a base64 `data:` URL (remote URLs such as `http(s)://` are rejected), at most 15 MiB decoded per attachment and 20 MiB in total per message; required for images |
| `content` | string | Optional pre-extracted plain text, at most 50,000 characters; when absent, text is extracted from the decoded `data_url` (at most 20 PDF pages are OCR'd) |

At most 50,000 characters of each attachment's text go into the model context; the rest is truncated.

| Status | When |
|---|---|
| `400` | `model_name` is not in the available model list |
| `413` | The request body exceeds its limit (1 MiB without a valid access token), or this user's stored attachments would exceed 200 MiB (`附件儲存空間已達上限…`, "attachment storage is full") |
| `422` | Field validation failed: message too long, too many or too large attachments, a `data_url` that is not a base64 `data:` URL, and so on |
| `429` | This user already has 2 answers streaming |

**How `reasoning_effort` is handled**: the frontend offers `none`, `low`, `medium`, `high`, and `xhigh`; the backend accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and `max`, and drops any other value. Models whose name contains `gpt-5` always get `none` when tools are attached.

#### SSE events

Each event is formatted as `event: <name>\ndata: <JSON>\n\n`, in this order:

| Event | When | `data` fields |
|---|---|---|
| `start` | The user message has been saved | `conversation_id`, `user_message_id` |
| `step_start` | A tool call starts | `step` (from 1), `tool`, `arguments` |
| `approval_required` | The tool needs approval and the agent pauses (see [2.10](#210-post-apichatapprovalsapproval_id)) | `approval_id`, `step`, `tool`, `tool_display_name`, `arguments` |
| `approval_resolved` | The user answered or the wait timed out | `approval_id`, `approved` (`false` on timeout) |
| `step_end` | A tool call ends | `step`, `tool`, `arguments`, `output_preview` (first 300 characters of the result JSON), `duration_seconds`, `status` (`success` / `error`) |
| `token` | Answer text | `content` |
| `sources` | After the answer | `sources` (deduplicated source names), `sources_detail` (see below) |
| `done` | The assistant message has been saved | `message_id`, `conversation_id`, `answer`, `sources`, `sources_detail`, `research_trace` (every `step_end` payload) |
| `error` | An unexpected exception in the API layer | `detail` (a message with an error code), `error_id` |

`sources_detail` lists only the entries the answer cites as `[n]`, in order of first citation; with no citations, `sources` and `sources_detail` are both empty. Fields depend on the source:

| Source tool | Fields |
|---|---|
| `search_knowledge_base` | `citation`, `source` (file name), `chunk` (chunk number), `score`, `snippet` (first 200 characters) |
| `filter_and_count_records` | `citation`, `source`, `snippet` |
| `web_search`, `web_fetch` | `citation`, `source` (page title or URL), `url`, `snippet` |

**Stream example**

```text
event: start
data: {"conversation_id": 42, "user_message_id": 107}

event: step_start
data: {"step": 1, "tool": "search_knowledge_base", "arguments": {"query": "特休假 申請流程"}}

event: step_end
data: {"step": 1, "tool": "search_knowledge_base", "arguments": {"query": "特休假 申請流程"}, "output_preview": "{\"query\": \"特休假 申請流程\", \"target_document\": null, \"total_found\": 2, ...", "duration_seconds": 4.21, "status": "success"}

event: token
data: {"content": "特休假需先在系統填寫假單，經直屬主管核准後生效 [1]。"}

event: sources
data: {"sources": ["員工手冊.pdf"], "sources_detail": [{"citation": 1, "source": "員工手冊.pdf", "chunk": 3, "score": 0.9412, "snippet": "特休假申請需於系統填寫假單……"}]}

event: done
data: {"message_id": 108, "conversation_id": 42, "answer": "特休假需先在系統填寫假單，經直屬主管核准後生效 [1]。", "sources": ["員工手冊.pdf"], "sources_detail": [...], "research_trace": [...]}
```

**Behavior details**

- When the model stops calling tools, its answer arrives in **one** `token` event; only when the tool turns (`AGENT_MAX_TURNS`) run out or the model returns empty content is the answer streamed over several `token` events.
- A failed model call or an interrupted stream is reported inside a `token` event with an error code (for example 在執行自主研究時遇到連線異常（錯誤代碼：…）, "a connection error occurred during research"), not as an `error` event; the code maps to the full exception in the server log.
- The assistant message is saved only after the stream completes. If the client disconnects mid-stream (for example by pressing stop), that answer is not saved, while the user message already is.
- A new conversation takes the first 50 characters of its first message as its title.
- The assistant message stores `sources`, `sources_detail`, and `research_trace` as JSON in its `context_used` database column; attachment details are stored in the user message's `context_used`. API responses carry only the parsed fields and no longer return the raw `context_used`.
- Each tool result is truncated to 20,000 characters before it enters the model context.
- While streaming, the backend returns its database connection to the pool and takes one again at the end to save the answer.

### 2.2 GET /api/chat/models

Available models and the default model. See [configuration reference: model list](configuration_en.md#model-list) for how the list and the default are chosen; when the remote list is queried, the result (failures included) is cached for 30 seconds.

```json
{
  "models": ["gpt-6-sol", "gpt-6-luna"],
  "default": "gpt-6-sol"
}
```

### 2.3 GET /api/chat/tools

The tool definitions currently available to the agent (sign-in required), in the OpenAI Function Calling `tools` format:

- Built-in tools `search_knowledge_base`, `filter_and_count_records`, `web_search`, and `web_fetch` (the last two are omitted when `ENABLE_WEB_SEARCH=false`). The `search_knowledge_base` description lists every document's file name and AI summary so the model can choose where to search.
- Enabled custom API tools (description prefixed with `【外部自訂 API】`).
- Discovered tools of enabled MCP servers, named `mcp_<server>_<tool>` (description prefixed with `【MCP 協定工具】`).

```json
{
  "status": "success",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_knowledge_base",
        "description": "檢索內部知識庫。目前知識庫收錄以下各具不同主題之專屬文件庫……",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {"type": "string"},
            "target_document": {"type": "string"},
            "top_k": {"type": "integer", "default": 3}
          },
          "required": ["query"]
        }
      }
    }
  ]
}
```

If loading external tools raises an exception, `status` is `partial` with `error` and `error_id`, and `tools` contains the built-in tools only.

### 2.4 GET /api/chat/conversations

Your conversations, most recently updated first, at most **200**; each includes its **5 most recent** messages in chronological order, whose attachments list the file name and similar details but no `data_url`.

```json
[
  {
    "id": 42,
    "title": "特休假申請流程",
    "created_at": "2026-09-25T01:00:00",
    "updated_at": "2026-09-25T01:30:00",
    "messages": [
      {
        "id": 108,
        "content": "特休假需先在系統填寫假單……[1]。",
        "is_user": false,
        "created_at": "2026-09-25T01:30:00",
        "context_used": null,
        "model_name": "gpt-6-sol",
        "reasoning_effort": null,
        "attachments": [],
        "sources": ["員工手冊.pdf"],
        "sources_detail": [...],
        "research_trace": [...]
      }
    ]
  }
]
```

A message's `sources`, `sources_detail`, `research_trace`, and `attachments` are parsed from the `context_used` database column; `context_used` in the response is always `null` (the raw value holds attachment base64 and is no longer repeated). `reasoning_effort` is not stored and is always `null`.

### 2.5 POST /api/chat/conversations

Create an empty conversation; no request body is needed, and the title is `DEFAULT_CONVERSATION_TITLE` (新對話, "new conversation", by default). Returns the conversation object with an empty `messages` array.

### 2.6 GET /api/chat/conversations/{conversation_id}

One conversation with its latest 500 messages in chronological order. Returns `404` `找不到該對話` (conversation not found) when it does not exist or is not yours.

### 2.7 GET /api/chat/conversations/{conversation_id}/messages

Paged messages.

| Query parameter | Default | Description |
|---|---|---|
| `limit` | `100` | Number of messages to return, at most 500 |
| `offset` | `0` | Number of newest messages to skip |

Returns the newest `limit` messages in chronological order; page back with `offset`. An unknown conversation, or one that is not yours, returns an empty array.

### 2.8 DELETE /api/chat/conversations/{conversation_id}

Delete one of your conversations and all its messages.

**Response**: `200 OK` `{"message": "對話已刪除"}`; `404` when not found.

### 2.9 WebSocket /api/chat/ws/{user_id}

A demo echo channel: for `{"content": "..."}` it replies `{"type": "message", "content": "收到訊息: ...", "timestamp": "now"}`. It does not authenticate and the frontend does not use it; use the [SSE endpoint in 2.1](#21-post-apichatsend) for chat.

### 2.10 POST /api/chat/approvals/{approval_id}

Approve or deny a tool call the agent is waiting on. Custom API tools and MCP servers carry a `requires_approval` flag (see [Tool object](#tool-object) and [Server object](#server-object)); when the agent wants to call such a tool, the `POST /api/chat/send` stream first sends an `approval_required` event and pauses until the user answers through this endpoint, then sends `approval_resolved`. See [ADR-0006](adr/0006-tool-call-approval_en.md) for the rationale.

**Request body**: `{"approved": true}` (`false` denies)

**Response**: `200 OK` `{"approval_id": "…", "approved": true}`

| Status | When |
|---|---|
| `404` | `找不到待核准的工具呼叫，可能已逾時或已處理` ("no pending tool call; it may have timed out or been handled"): the `approval_id` is unknown, already handled, timed out, or was not created by a stream the signed-in user started |

- Only the asking user can answer their own items; admins cannot approve on their behalf.
- No answer within 300 seconds counts as a denial; when the user interrupts the stream, the pending item is cancelled with it.
- On a denial or timeout the tool does not run, and the agent receives a "not approved by the user" tool result and answers from what it already has.
- When no user can approve (a non-interactive run), tools that need approval never run.
- Pending items live in the backend process's memory and are lost when the backend restarts.

---

## 3. Knowledge-base documents `/api/documents`

> Every endpoint in this module requires **admin** access.

### 3.1 POST /api/documents/upload

Upload documents to the knowledge base. Each file goes through: name and extension checks → size check → text extraction (blank or garbled PDF pages are OCR'd by a vision model) → duplicate check → AI summary → saved to `documents` → chunked into `rag_chunks`, FAISS, and BM25.

**Request**: `multipart/form-data` with the field name `file`, repeatable, up to 10 files per request.

- Supported extensions: `.txt`, `.md`, `.markdown`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`, `.json`, `.yaml`, `.yml`, `.xml`, `.html`, `.htm`, `.log`, `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.java`, `.cpp`, `.c`, `.sql`, `.sh`, `.ini`, `.env`.
- Per-file limit: `MAX_FILE_SIZE_MB` (10 MB in the template). The whole request body may be 10 × `MAX_FILE_SIZE_MB` MiB + 1 MiB, and only with a valid access token (1 MiB otherwise); larger bodies get `413`.
- A `.docx`, `.pptx`, or `.xlsx` whose total uncompressed size exceeds 200 MiB, or whose large members compress more than 100:1, is rejected before parsing; scanned PDF pages are rasterized at no more than 25 MP each.
- Spaces in file names become underscores; a name that already exists gets a `_1`, `_2`, … suffix; names containing `/`, `\`, `..`, `<`, `>`, `:`, `"`, `|`, `?`, or `*` are rejected.
- A file whose extracted text is identical to an existing document's is a duplicate and is not stored again.
- Chunking: Q&A documents become one chunk per pair, structured records and JSON become one chunk per record, and everything else is split recursively by `CHUNK_SIZE` / `CHUNK_OVERLAP`.

**Response**: `200 OK` with one result per file; `http_status` reports each file's outcome:

```json
{
  "results": [
    {
      "filename": "員工手冊.pdf",
      "status": "success",
      "document_id": 101,
      "content_length": 28460,
      "content_type": "application/pdf",
      "qa_detected": false,
      "qa_pairs": 0,
      "http_status": 201
    },
    {
      "filename": "重複文件.txt",
      "status": "duplicate",
      "detail": "內容已存在",
      "existing_document_id": 88,
      "http_status": 409
    },
    {
      "filename": "setup.exe",
      "status": "failed",
      "detail": "檔名驗證失敗: 無效的檔名或不允許的副檔名",
      "http_status": 400
    }
  ]
}
```

A request with no files or more than 10 files returns `400` as a whole.

### 3.2 GET /api/documents/

List every document (`id`, `filename`, `content`, `file_type`, `description`, `uploaded_by`, `created_at`, `is_processed`). `content` is the full extracted text and can be large. Documents without a summary get one generated and saved during this request, so it can be slow.

### 3.3 POST /api/documents/{document_id}/regenerate-summary

Regenerate the AI outline and summary.

```json
{
  "message": "文件大綱與摘要重新生成成功",
  "document_id": 101,
  "description": "本文件說明差勤與請假制度……"
}
```

### 3.4 PUT /api/documents/{document_id}/summary

Edit the summary. **Request body**: `{"description": "Custom summary"}`; **response**: `{"message": "文件大綱更新成功", "document_id": 101, "description": "Custom summary"}`.

### 3.5 DELETE /api/documents/{document_id}

Delete a document: delete the database record first, then remove its chunks, vectors, and BM25 entries, and finally delete the uploaded file. An index write in progress checks, while holding the lock, that the document still exists, so chunks of a deleted document are never written back.

**Response**: `200 OK` `{"message": "文件刪除成功"}`; `404` `文件不存在` (document not found).

### 3.6 POST /api/documents/rebuild-index

Rebuild the index from the documents in the database: after clearing chunks and indexes, every document is re-extracted (from the uploaded file when it still exists), gets a new AI summary, and is re-chunked and re-embedded with the current settings. Run it once after upgrading from 2.x; it takes longer the more documents you have.

```json
{
  "message": "索引重建成功（已用新配置重新分塊，並重新生成 AI 智能大綱）",
  "document_count": 6,
  "chunk_count": 214,
  "qa_pairs_detected": 0,
  "chunk_size": 300,
  "chunk_overlap": 100,
  "timestamp": "2026-09-25T10:00:00.000000"
}
```

With no documents in the database it returns `{"message": "索引重建完成（沒有文件）", "document_count": 0, "chunk_count": 0, "timestamp": "..."}`.

---

## 4. Custom API tools `/api/api-tools`

Register external HTTP APIs as tools the agent can call. Enabled tools are loaded whenever tool definitions are assembled, so changes need no restart.

> Every endpoint in this module, including reads, requires **admin** access: tools are shared by every user's agent and responses include credentials such as API keys. See [ADR-0004](adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md).

### Tool object

| Field | Type | Description |
|---|---|---|
| `id` | integer | Tool ID |
| `name` | string | Unique name the model calls (letters, digits, and underscores, up to 64 characters) |
| `display_name` | string | Display name |
| `description` | string | Purpose; it affects whether the model calls the tool |
| `category` | string | Category, `custom_api` by default |
| `method` | string | HTTP method |
| `url` | string | Full request URL, with path parameters written as `{name}` |
| `base_url` / `path` | string | Base URL and path, combined when `url` is empty |
| `headers` | object | Fixed request headers |
| `auth_type` | string | `none`, `bearer`, `api_key`, or `basic` |
| `auth_config` | object | Auth settings; see the table below |
| `parameters_schema` | object | JSON Schema of the parameters, used as the `parameters` the model sees |
| `request_body_schema` | object | Request body structure |
| `param_locations` | object | Where each parameter goes: `path`, `query`, `header`, or `body` |
| `response_mapping` | string | Reserved, currently unused |
| `is_enabled` | boolean | Whether the tool is enabled |
| `requires_approval` | boolean | Whether the asking user must approve in the chat before the agent calls it (see [2.10](#210-post-apichatapprovalsapproval_id)). When omitted on create or import it follows the method: `false` for `GET`, `HEAD`, and `OPTIONS`, `true` for everything else |
| `timeout` | integer | Timeout in seconds, 15 by default |
| `spec_version` | string | Source spec version, `manual` for hand-made tools |
| `created_at` / `updated_at` | string | Timestamps |

| `auth_type` | `auth_config` fields |
|---|---|
| `bearer` | `token` |
| `api_key` | `key_name` (default `X-API-Key`), `key_value`, `key_in` (`header` or `query`) |
| `basic` | `username`, `password` |

**Parameter assembly**: parameters that appear as `{name}` in the URL or are located in `path` are substituted into the URL; `header` parameters go into headers, `query` parameters into the query string, and `body` parameters into the JSON body. Parameters without a location go into the body for `POST`, `PUT`, and `PATCH`, and into the query string otherwise. A `request_body` object passed by the model replaces the whole body.

**Path parameters and host**: path parameters are always percent-encoded (`/`, `?`, `#`, and `%` included), and the values `.` and `..` are rejected; after substitution the URL must keep the scheme, host, and port of the configured URL, or the request is not sent.

### 4.1 POST /api/api-tools/parse-spec

Parse an OpenAPI / Swagger spec (OAS 2.0, 3.0, 3.1) from JSON / YAML text or a spec URL.

| Field | Type | Required | Description |
|---|---|---|---|
| `spec_content_or_url` | string | Yes | Spec text, or a spec URL starting with `http://` or `https://` |
| `default_base_url` | string | No | Overrides the server URL in the spec |

Spec URLs are SSRF-validated first (every hop is pinned to the validated IP) and fetched with a 10 MB limit, a 15-second timeout, and at most 5 redirects.

**Response**: `200 OK`

```json
{
  "status": "success",
  "data": {
    "version": "openapi_3.0",
    "title": "Pet Store",
    "description": "",
    "base_url": "https://api.example.com",
    "endpoints_count": 4,
    "endpoints": [
      {
        "name": "get_pet_by_id",
        "display_name": "Get a pet",
        "description": "Get a pet",
        "long_description": "",
        "method": "GET",
        "path": "/pets/{petId}",
        "base_url": "https://api.example.com",
        "full_url": "https://api.example.com/pets/{petId}",
        "has_body": false,
        "body_content_type": "application/json",
        "param_locations": {"petId": "path"},
        "parameters_schema": {"type": "object", "properties": {"petId": {"type": "integer"}}, "required": ["petId"]},
        "function_definition": {"type": "function", "function": {"name": "get_pet_by_id", "...": "..."}},
        "tags": ["pets"],
        "spec_version": "openapi_3.0"
      }
    ],
    "raw_spec": {"openapi": "3.0.0", "...": "..."}
  }
}
```

Tool names come from `operationId` (lowercased, with non-alphanumeric characters replaced by underscores); without an `operationId`, the method and path are combined, such as `get_pets_petid`.

| Status | When |
|---|---|
| `400` | Invalid spec, unrecognized version, or an unreachable URL (the message is safe to show to users); a URL rejected by the SSRF guard only reports the rejection with an error code, and the full reason goes to the server log |
| `500` | Any other unexpected exception; only an error code is returned |

### 4.2 POST /api/api-tools/import

Bulk-import the endpoints selected from a parsed spec. Tools with the same name are overwritten and re-enabled.

| Field | Type | Required | Description |
|---|---|---|---|
| `tools` | array | Yes | Endpoints with the parsed fields: `name`, `display_name`, `description`, `method`, `path`, `full_url` (required), plus optional `base_url`, `headers`, `auth_type`, `auth_config`, `parameters_schema`, `request_body_schema`, `param_locations`, `spec_version` |
| `global_base_url` | string | No | Used when an endpoint has no `base_url` |
| `global_headers` | object | No | Shared headers; an endpoint's own header of the same name wins |
| `global_auth_type` | string | No | Used when an endpoint has no auth type |
| `global_auth_config` | object | No | Used when an endpoint has no auth settings |

Newly imported tools get `requires_approval` from their method (`true` for anything other than `GET`, `HEAD`, and `OPTIONS`); when an existing tool is overwritten, a tool that required approval keeps requiring it. Change it afterwards with 4.6.

```json
{
  "status": "success",
  "message": "成功匯入 4 個新工具，更新 1 個既有工具。",
  "imported": 4,
  "updated": 1
}
```

### 4.3 GET /api/api-tools

| Query parameter | Description |
|---|---|
| `category` | Filter by category |
| `is_enabled` | Filter by enabled state |
| `search` | Fuzzy match on `name`, `display_name`, `description`, and `url` |

**Response**: `{"status": "success", "total": 5, "tools": [tool object, ...]}`, newest ID first.

### 4.4 POST /api/api-tools

Create a tool manually. `name`, `display_name`, `description`, and `url` are required; the other fields follow the [tool object](#tool-object). `name` is normalized to letters, digits, and underscores.

**Response**: `{"status": "success", "message": "自訂 API 工具建立成功", "tool": {...}}`; a duplicate name returns `400` `已存在同名工具: <name>`.

### 4.5 GET /api/api-tools/{tool_id}

**Response**: `{"status": "success", "tool": {...}}`; `404` `找不到該自訂 API 工具` (tool not found).

### 4.6 PUT /api/api-tools/{tool_id}

Send only the fields you change (`name` cannot be changed). Changing `method` to anything other than `GET`, `HEAD`, or `OPTIONS` without also sending `requires_approval` sets `requires_approval` to `true`. **Response**: `{"status": "success", "message": "自訂 API 工具更新成功", "tool": {...}}`.

### 4.7 PATCH /api/api-tools/{tool_id}/toggle

**Response**: `{"status": "success", "is_enabled": false, "message": "工具已停用"}`

### 4.8 DELETE /api/api-tools/{tool_id}

**Response**: `{"status": "success", "message": "自訂 API 工具已成功刪除"}`

### 4.9 POST /api/api-tools/{tool_id}/test

Send one real request with the given arguments.

**Request body**: `{"arguments": {"petId": 3}}`

```json
{
  "status": "success",
  "tool_name": "get_pet_by_id",
  "result": {
    "status_code": 200,
    "is_success": true,
    "duration_seconds": 0.42,
    "url": "https://api.example.com/pets/3",
    "data": {"id": 3, "name": "Miao"}
  }
}
```

- `data` is the parsed object for JSON responses and the first 4000 characters of text otherwise. If the upstream body exceeds 1 MiB, reading stops and `status_code` is `502`.
- Credentials injected into this request (header values, Bearer token, API key, Basic auth) are replaced with `[已遮蔽]` ("redacted") wherever they appear in `data` or `url`; a query-string API key is masked in `url` too.
- At most 5 redirects are followed; a redirect to another origin (different scheme, host, or port) does not carry the admin-configured headers or the auth header.
- The first request and every redirect are SSRF-validated again, with the connection pinned to the validated IP; a rejection reports `status_code` `403`, `is_success` `false`, an `error` that only states the SSRF rejection with an error code, and `error_id`; the full reason goes to the server log.
- An invalid path parameter or a host mismatch after substitution reports `status_code` `400`.
- Other failures report `status_code` `500` with only `error` (including an error code) and `error_id`.
- Custom API tools, the MCP HTTP transport, and `web_fetch`'s direct fetches ignore the `HTTP_PROXY` and `HTTPS_PROXY` environment variables and always connect directly.
- Agent calls run the same code; when `requires_approval` is `true` they need the user's approval first, while this admin test endpoint does not.

---

## 5. MCP servers `/api/mcp`

Manage Model Context Protocol servers, protocol version `2024-11-05`, using JSON-RPC 2.0 for `initialize`, `tools/list`, and `tools/call`. The handshake identifies the client as `AskMiao-MCP-Client` with the backend version.

> Every endpoint in this module, including reads, requires **admin** access: `stdio` servers run the configured command on the host, and responses include credentials such as environment variables and headers.

### Server object

| Field | Type | Description |
|---|---|---|
| `id` | integer | Server ID |
| `name` | string | Unique name (lowercased on creation), used in tool names `mcp_<name>_<tool>` |
| `display_name` / `description` | string | Display name and description |
| `transport_type` | string | `stdio`, or `http` / `sse` (both send JSON-RPC over HTTP POST) |
| `command` / `args` | string / array | Command and arguments for `stdio` |
| `env_vars` | object | Extra environment variables for the `stdio` subprocess |
| `url` / `headers` | string / object | Server URL and request headers for HTTP |
| `is_enabled` | boolean | Whether it is enabled; disabled servers do not provide tools to the agent |
| `requires_approval` | boolean | Whether the asking user must approve in the chat before the agent calls this server's tools (see [2.10](#210-post-apichatapprovalsapproval_id)); `true` when omitted on create, and admins can turn it off per server |
| `status` | string | `connected`, `disconnected`, or `error` |
| `last_error` | string | Why the latest discovery failed |
| `discovered_tools` | array | Cached tools from the latest discovery (`name`, `description`, `inputSchema`) |
| `timeout` | integer | Connect and call timeout in seconds, 30 by default |
| `created_at` / `updated_at` | string | Timestamps |

**The `stdio` subprocess environment** inherits only essential system variables, plus `env_vars`: `APPDATA`, `HOMEDRIVE`, `HOMEPATH`, `LOCALAPPDATA`, `PATH`, `PATHEXT`, `PROCESSOR_ARCHITECTURE`, `SYSTEMDRIVE`, `SYSTEMROOT`, `TEMP`, `USERNAME`, and `USERPROFILE` on Windows; `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, and `USER` elsewhere. Settings from the backend `.env` are never passed on.

**`stdio` subprocess lifetime**: each subprocess runs in its own process group (a new process group on Windows, a new session elsewhere), and closing it terminates the whole tree, including grandchildren started by `npx` or `uvx` (`taskkill /T /F` on Windows; `SIGTERM`, then `SIGKILL`, to the group elsewhere). Every discovery or tool call starts a subprocess; at most 4 run at once and the rest wait.

**HTTP servers** are SSRF-validated on every request and redirect, with the connection pinned to the validated IP, so servers on loopback or intranet addresses are rejected; use `stdio` for local MCP servers. One response may be at most 4 MiB, and error messages no longer include the peer's response body.

### 5.1 GET /api/mcp/presets

The built-in presets: `mcp_time` (time and time zones, an inline Python script) and `mcp_filesystem` (`npx -y @modelcontextprotocol/server-filesystem@2026.8.31 <absolute path of backend/mcp_filesystem_sandbox>`). The filesystem preset pins the package version and exposes only its dedicated sandbox directory (kept apart from `DATA_DIR`, which holds index metadata); calling this endpoint creates the directory. There is no web-fetch preset: outbound connections from a `stdio` subprocess are not bound by `web_fetch`'s SSRF checks, domain allowlist, or URL provenance rule.

**Response**: `{"status": "success", "presets": [...]}`

### 5.2 GET /api/mcp/servers

**Query parameter**: `is_enabled` (optional). **Response**: `{"status": "success", "total": 2, "servers": [server object, ...]}`, newest ID first.

### 5.3 POST /api/mcp/servers

Add a server; it connects and discovers tools right away.

| Field | Type | Required | Default |
|---|---|---|---|
| `name` | string | Yes | — |
| `display_name` | string | Yes | — |
| `description` | string | No | `null` |
| `transport_type` | string | No | `stdio` |
| `command` / `args` / `env_vars` | string / array / object | `command` for `stdio` | `null` |
| `url` / `headers` | string / object | `url` for HTTP | `null` |
| `is_enabled` | boolean | No | `true` |
| `requires_approval` | boolean | No | `true` |
| `timeout` | integer | No | `30` |

**Response**: `{"status": "success", "message": "MCP 伺服器建立成功", "server": {...}}`. If discovery fails, the server is still created with `status` `error`, and `last_error` records only an error code; an SSRF rejection also says the SSRF guard rejected it, and its full reason likewise goes only to the server log. A duplicate name returns `400` `已存在同名 MCP 伺服器: <name>`.

### 5.4 GET /api/mcp/servers/{server_id}

**Response**: `{"status": "success", "server": {...}}`; `404` `找不到該 MCP 伺服器` (server not found).

### 5.5 PUT /api/mcp/servers/{server_id}

Send only the fields you change (`name` cannot be changed). Updating does not rediscover tools; call 5.7 afterwards. **Response**: `{"status": "success", "message": "MCP 伺服器配置更新成功", "server": {...}}`.

### 5.6 DELETE /api/mcp/servers/{server_id}

**Response**: `{"status": "success", "message": "MCP 伺服器已成功刪除"}`

### 5.7 POST /api/mcp/servers/{server_id}/discover

Reconnect and rediscover tools; the result is written to `discovered_tools`.

```json
{
  "status": "success",
  "message": "成功連線並探索到 1 項 MCP 工具",
  "tools_count": 1,
  "tools": [{"name": "get_current_time", "description": "查詢指定時區或城市的當前精確時間", "inputSchema": {"type": "object", "properties": {"timezone": {"type": "string"}}}}],
  "init_info": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "mcp-time-server", "version": "1.0"}},
  "server": {...}
}
```

Failures return `400` with only an error code in `detail` (an SSRF rejection also says the SSRF guard rejected it); the server's `status` becomes `error`.

### 5.8 PATCH /api/mcp/servers/{server_id}/toggle

**Response**: `{"status": "success", "is_enabled": false, "message": "MCP 伺服器已停用"}`

### 5.9 POST /api/mcp/servers/{server_id}/tools/{tool_name}/test

Call a tool once (`tools/call`). `tool_name` is the tool's original name on the MCP server.

**Request body**: `{"arguments": {"timezone": "Asia/Taipei"}}`

```json
{
  "status": "success",
  "server_name": "mcp_time",
  "tool_name": "get_current_time",
  "result": {
    "is_success": true,
    "duration_seconds": 0.35,
    "content": [{"type": "text", "text": "當前時間: 2026-09-25 10:00:00 CST"}],
    "raw_result": {"content": [...], "isError": false}
  }
}
```

A failed call returns `result` as `{"is_success": false, "duration_seconds": ..., "error": "呼叫 MCP 工具失敗: ..."}`.

---

## 6. Model lists `/api/tags`

Model lists in the Ollama `tags` format; neither endpoint requires sign-in.

### 6.1 GET /api/tags

When any model source is configured (`AVAILABLE_MODELS` or a cloud key), returns `{"tags": [...], "default": "..."}` with the same default rule as `GET /api/chat/models`. Otherwise it queries the remote list at `EXTERNAL_TAGS_URL` (or `{LLM_API_BASE}/api/tags`) and returns an empty list if that fails. The remote query runs in a worker thread, its result (failures included) is cached for 30 seconds, and only one query runs at a time, so anonymous requests do not trigger an outbound call each time.

```json
{"tags": ["gpt-6-sol", "gpt-6-luna"], "default": "gpt-6-sol"}
```

### 6.2 GET /api/external-tags

Returns `{"tags": [...], "default": "..."}` when a model source is configured; otherwise it relays the remote list as is.

| Status | When |
|---|---|
| `400` | Both `EXTERNAL_TAGS_URL` and `LLM_API_BASE` are empty |
| `502` | The remote query failed; returns `{"error": "Failed to fetch external tags", "models": [...]}` |

---

## 7. Admin `/api/admin`

> Every endpoint in this module requires **admin** access.

### 7.1 User management

| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/users` | All users |
| PUT | `/api/admin/users/{user_id}` | Update `username`, `email`, `is_active`, or `is_admin` (send only what changes); duplicate names or emails return `400` |
| DELETE | `/api/admin/users/{user_id}` | Delete a user and all their conversations |

`PUT` returns `{"message": "使用者更新成功", "user": {...}}` and `DELETE` returns `{"message": "使用者刪除成功"}`; both clear the statistics cache. Deactivating an account (`is_active=false`) only blocks later password sign-ins; see [known limitations](#10-known-limitations).

### 7.2 Statistics

`GET /api/admin/statistics`, cached for 180 seconds:

```json
{
  "users": {"total": 12, "active": 11, "admins": 2},
  "conversations": {"total": 340},
  "messages": {"total": 2870, "recent_7_days": 412},
  "documents": {"total": 58, "processed": 57},
  "daily_stats": [{"date": "2026-09-25", "messages": 63}]
}
```

`daily_stats` covers the last 7 days (from today backwards, by UTC date).

### 7.3 Conversations and documents

| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/conversations` | The 50 most recently updated conversations system-wide |
| GET | `/api/admin/conversations/{conversation_id}/messages` | All messages of any conversation, oldest first; the table is serialized directly, including the raw `context_used` |
| DELETE | `/api/admin/conversations/{conversation_id}` | Delete any conversation and its messages |
| GET | `/api/admin/documents` | All documents, newest first, including the full `content` |
| DELETE | `/api/admin/documents/{document_id}` | Remove a document's chunks and indexes and delete its record (the uploaded file stays; use `DELETE /api/documents/{document_id}` to remove it too) |

### 7.4 Retrieval and index maintenance

| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/rag-config` | Current retrieval parameters |
| GET | `/api/admin/vector-store/info` | Basic index information |
| GET | `/api/admin/vector-store/statistics` | Index statistics |
| POST | `/api/admin/vector-store/reindex` | Recompute every vector from the existing chunks and rebuild BM25, without re-chunking |
| DELETE | `/api/admin/vector-store/clear` | Clear `rag_chunks`, FAISS, and BM25; document records remain, so call `POST /api/documents/rebuild-index` to rebuild when needed |

`GET /api/admin/rag-config`:

```json
{
  "chunk_size": 300,
  "chunk_overlap": 100,
  "top_k": 30,
  "similarity_threshold": 0.3,
  "rrf_k": 60,
  "rerank_top_k": 20,
  "final_k": 8,
  "rerank_weight": 0.85,
  "rerank_relevance_threshold": 0.2,
  "batch_size": 32,
  "embedding_dimension": 512,
  "device": "cpu",
  "use_faiss_gpu": false
}
```

`GET /api/admin/vector-store/info`:

```json
{
  "total_vectors": 214,
  "total_documents": 214,
  "embedding_dimension": 512,
  "index_type": "FAISS IndexIDMap2(IndexFlatIP) + Whoosh BM25",
  "vector_index_exists": true,
  "bm25_index_exists": true,
  "last_reindex": "2026-09-25T10:00:00.000000"
}
```

`total_documents` counts chunks. `GET /api/admin/vector-store/statistics` additionally returns `bm25_status`, `similarity_threshold`, `chunk_size`, and `chunk_overlap`.

`POST /api/admin/vector-store/reindex` returns `{"message": "索引重建已觸發", "ok": true, "info": {...}}`; `DELETE /api/admin/vector-store/clear` returns `{"message": "向量庫已清空"}`.

---

## 8. Health checks

| Method | Path | Response |
|---|---|---|
| GET | `/` | `{"message": "ChatBot API is running"}` |
| GET | `/health` | `{"status": "healthy"}` |

---

## 9. Error handling

### Response format

Error messages are in the `detail` field:

```json
{"detail": "找不到該自訂 API 工具"}
```

For field validation failures (`422`), `detail` is FastAPI's error array (when sending a chat message, the frontend shows each item's `msg`, for example an oversized attachment):

```json
{"detail": [{"type": "missing", "loc": ["body", "content"], "msg": "Field required", "input": {}}]}
```

### Error codes

Unexpected server exceptions **never** return exception messages or stack traces, only a random 12-character error code; the full exception goes to the server log under that code (CWE-209 / CWE-497):

```json
{
  "detail": "伺服器內部錯誤，請聯繫系統管理員並提供錯誤代碼（錯誤代碼：9f2c71a4b8de）",
  "error_id": "9f2c71a4b8de"
}
```

Validation errors that only describe the user's own input (such as an invalid OpenAPI spec) return an actionable message instead. SSRF rejection reasons can contain intranet IPs resolved on the server or redirect targets, so `parse-spec`, custom API tools, and `web_fetch` only report "SSRF 防護拒絕連線" (connection rejected by the SSRF guard) with an error code, and the full reason goes to the server log.

### Common status codes

| Status | Meaning |
|---|---|
| `400` | Bad request content: duplicate names, spec parsing failures, URLs rejected by SSRF validation, password rules not met, unsupported model |
| `401` | Missing or invalid access token (`Not authenticated`, `認證權杖無效：驗證失敗` "token verification failed", `權杖已被撤銷` "token revoked"; a deleted or deactivated account also gets `認證權杖無效：驗證失敗`) or a failed sign-in |
| `403` | Insufficient permission (`需要管理員權限`), or the client IP was blocked for suspicious activity (the block list lives in memory and clears on restart) |
| `404` | The resource (conversation, document, tool, MCP server, user, pending tool call) does not exist |
| `413` | The request body exceeds its limit, or the user's attachment storage is full |
| `422` | Field validation failed (including length, count, and size limits) |
| `429` | Rate limit exceeded (the response includes a `Retry-After` header), or the same user has more than 2 answers streaming |
| `500` | Unexpected exception; only an error code is returned |
| `502` | `GET /api/external-tags` failed to reach the remote list |

### Security response headers

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy: geolocation=(), microphone=(), camera=()`, and the `Server` header is removed.

---

## 10. Known limitations

The current state, worth knowing when integrating:

- `GET /api/chat/models`, `GET /api/tags`, `GET /api/external-tags`, and the WebSocket `/api/chat/ws/{user_id}` require no sign-in (`GET /api/chat/tools` now does). Restrict them at the reverse proxy when deploying on a public network.
- `GET /api/admin/users` and `PUT /api/admin/users/{user_id}` serialize the table directly, so responses include the `hashed_password` field (visible to admins only).
- `GET /api/documents/` and `GET /api/admin/documents` return each document's full text in `content`.
- Failed MCP tool calls include the raw exception message in `error` instead of an error code.
- `expires_in` in token responses is always `1800`, regardless of `ACCESS_TOKEN_EXPIRE_MINUTES`.
- The token revocation list, rate limit counters, per-user concurrent streams, and pending tool approvals live in one backend process's memory; they are not shared across processes or hosts and are cleared on restart.
- Attachment storage is never purged automatically: once a user reaches the 200 MiB limit, they must delete conversations with attachments before sending attachments again.
