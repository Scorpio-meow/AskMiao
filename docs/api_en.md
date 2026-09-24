# AskMiao API Reference

[繁體中文](api.md) | [English](api_en.md)

> This document describes the RESTful, SSE streaming, and WebSocket endpoints exposed by the AskMiao backend. A Swagger UI is also served at `http://localhost:8001/docs` for interactive testing once the server is running.

---

## 0. Conventions

| Item | Description |
|---|---|
| Base URL | `http://localhost:8001` (controlled by the `HOST` / `PORT` environment variables) |
| Authentication | Send `Authorization: Bearer <access_token>`; the refresh token travels automatically in an HttpOnly cookie |
| Content type | `application/json`, except file uploads (`multipart/form-data`) and chat streaming (`text/event-stream`) |
| Permissions | Endpoints marked "admin" require an account with `is_admin = true` |
| Timestamps | ISO 8601 (UTC) |

### Route Prefixes

| Prefix | Module | Description |
|---|---|---|
| `/api/auth` | Authentication | Registration, login, refresh, profile, logout |
| `/api/chat` | Chat & autonomous research | SSE chat streaming, model and tool listings, conversation history |
| `/api/documents` | Knowledge base | Upload, summaries, deletion, index rebuild (admin) |
| `/api/api-tools` | Custom API tools | OpenAPI parsing and import, tool CRUD, testing (admin) |
| `/api/mcp` | MCP servers | MCP server management, tool discovery, invocation tests (admin) |
| `/api/admin` | Admin dashboard | Users, statistics, conversations, vector store operations (admin) |
| `/api/tags`, `/api/external-tags` | Model listings | Ollama-compatible `tags` payloads |
| `/health`, `/` | Health checks | Unauthenticated liveness probes |

---

## 1. Authentication (`/api/auth`)

### 1.1 POST /api/auth/register

Registers a user. On success it returns an access token and writes the refresh token into an HttpOnly cookie.

**Request Body:**

| Field | Type | Required | Description | Constraints |
|---|---|---|---|---|
| `username` | string | Yes | User name | 3–50 characters, letters/digits/underscore/hyphen only |
| `email` | string | Yes | Email address | Standard email format |
| `password` | string | Yes | Password | Minimum 8 characters |

**Responses:**

- **201 Created**

```json
{
  "user": {
    "id": 1,
    "username": "miao_user",
    "email": "user@example.com",
    "role": "user",
    "is_active": true,
    "is_admin": false,
    "created_at": "2026-09-19T00:00:00",
    "last_login": null
  },
  "tokens": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 1800
  },
  "message": "註冊成功"
}
```

- **400 Bad Request**: username or email already taken.

---

### 1.2 POST /api/auth/login

Authenticates a user.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `username` | string | Yes | User name or email address |
| `password` | string | Yes | Password |

**Responses:**

- **200 OK**: same shape as registration (`user` + `tokens` + `message`).
- **401 Unauthorized**: invalid credentials.

---

### 1.3 POST /api/auth/refresh

Silently refreshes the access token. The refresh token is read from the HttpOnly cookie, so no Authorization header is required.

**Responses:**

- **200 OK**

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

- **401 Unauthorized**: refresh token invalid, revoked, or expired.

---

### 1.4 GET /api/auth/me

Returns the authenticated user's profile.

**Responses:**

- **200 OK**

```json
{
  "id": 1,
  "username": "miao_user",
  "email": "user@example.com",
  "role": "user",
  "is_active": true,
  "is_admin": false,
  "created_at": "2026-09-19T00:00:00",
  "last_login": "2026-09-19T08:30:00"
}
```

---

### 1.5 PUT /api/auth/me

Updates the profile (email or password). Changing the password requires both `current_password` and `new_password`.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string | No | New email address |
| `current_password` | string | No | Current password (required to change the password) |
| `new_password` | string | No | New password (minimum 8 characters) |

**Response:** **200 OK** with the updated `UserProfile`.

---

### 1.6 POST /api/auth/change-password

Dedicated password change endpoint.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `current_password` | string | Yes | Current password |
| `new_password` | string | Yes | New password (minimum 8 characters) |
| `confirm_password` | string | Yes | Must match `new_password` |

**Response:** **200 OK** `{"message": "密碼修改成功", "success": true}`

---

### 1.7 POST /api/auth/logout

Logs the user out. Both the access and refresh token JTIs are added to the revocation list and the refresh cookie is cleared.

**Response:** **200 OK** `{"message": "登出成功", "success": true}`

---

### 1.8 POST /api/auth/validate-token

Checks whether the current access token is still valid.

**Response:** **200 OK** `{"message": "令牌有效", "success": true}`

---

## 2. Chat & Agentic RAG Research (`/api/chat`)

### 2.1 POST /api/chat/send

Sends a chat message and starts the ReAct research agent. **This endpoint streams Server-Sent Events (SSE)** with `Content-Type: text/event-stream`.

**Request Body:**

| Field | Type | Required | Description | Default |
|---|---|---|---|---|
| `content` | string | Yes | User question or message | - |
| `conversation_id` | integer | No | Conversation ID (omit for a new conversation; one is created automatically) | `null` |
| `model_name` | string | No | LLM model to use | System default |
| `reasoning_effort` | string | No | Reasoning depth (`none`, `low`, `medium`, `high`, `xhigh`) | `medium` |
| `attachments` | array | No | Attachments (images go to vision models; text files are extracted into the prompt context) | `[]` |

`attachments[]` fields: `filename` (string), `file_type` (string), `file_size` (integer, optional), `data_url` (string, Base64 data URL, optional), `content` (string, plain text, optional).

**SSE event sequence:**

| Event | When | `data` payload |
|---|---|---|
| `start` | Stream opens | `{"conversation_id": 42, "user_message_id": 107}` |
| `step_start` | A tool call begins | Tool name and input arguments |
| `step_end` | A tool call finishes | Step summary and duration; accumulated into `research_trace` |
| `token` | Model output (an answer produced after tool use arrives in one piece) | `{"content": "partial text"}` |
| `sources` | After the answer completes, the sources it actually cites as `[n]` | `{"sources": [...], "sources_detail": [...]}` |
| `done` | Stream finished and the message persisted | Final answer, sources, and research trace |
| `error` | Unexpected exception during streaming | `{"detail": "...(error code: xxxxxxxx)", "error_id": "xxxxxxxx"}` |

**Example stream:**

```text
event: start
data: {"conversation_id": 42, "user_message_id": 107}

event: step_start
data: {"step": 1, "tool": "search_knowledge_base", "arguments": {"query": "annual leave policy"}}

event: step_end
data: {"step": 1, "tool": "search_knowledge_base", "duration_seconds": 0.83, "status": "success"}

event: token
data: {"content": "According to the handbook, leave requests need a form in the system and manager approval [1]."}

event: sources
data: {"sources": ["handbook_2026.pdf"], "sources_detail": [{"citation": 1, "source": "handbook_2026.pdf", "chunk": 3, "score": 0.92, "snippet": "Annual leave requests are filed in the system..."}]}

event: done
data: {"message_id": 108, "conversation_id": 42, "answer": "According to the handbook, ...", "sources": ["handbook_2026.pdf"], "sources_detail": [...], "research_trace": [...]}
```

> `sources_detail` lists only the entries the answer actually cites, in order of first citation; `citation` matches the `[n]` in the answer, and web sources also carry `url`. Both arrays are empty when the answer cites nothing. When the stream completes, the assistant message is persisted together with `sources`, `sources_detail`, and `research_trace` inside the message's `context_used` field.

---

### 2.2 GET /api/chat/models

Returns the available language models and the default selection.

**Response:** **200 OK**

```json
{
  "models": ["gpt-4o", "gpt-4o-mini"],
  "default": "gpt-4o"
}
```

---

### 2.3 GET /api/chat/tools

Returns the tool definitions currently registered for the agent (built-in tools plus enabled custom API and MCP tools), in OpenAI function-calling format.

**Response:** **200 OK**

```json
{
  "status": "success",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_knowledge_base",
        "description": "Search the internal knowledge base...",
        "parameters": { "type": "object", "properties": { "query": { "type": "string" } } }
      }
    }
  ]
}
```

> If dynamic loading fails, `status` becomes `partial` with `error` and `error_id` attached, and `tools` falls back to the built-in toolset.

---

### 2.4 GET /api/chat/conversations

Returns all conversations owned by the current user as an array.

**Response:** **200 OK**

```json
[
  {
    "id": 42,
    "title": "Annual leave policy",
    "created_at": "2026-09-19T01:00:00",
    "updated_at": "2026-09-19T01:30:00",
    "messages": []
  }
]
```

---

### 2.5 GET /api/chat/conversations/{conversation_id}

Returns a single conversation including its messages. Responds **404 Not Found** when it does not exist.

### 2.6 GET /api/chat/conversations/{conversation_id}/messages

Returns only the messages of a conversation. Each message carries `id`, `content`, `is_user`, `created_at`, and `model_name`; assistant messages also carry `sources`, `sources_detail`, and `research_trace`.

**Query parameters:** `limit` (integer, default `100`), `offset` (integer, default `0`).

### 2.7 POST /api/chat/conversations

Creates a new conversation. No request body is required; the title falls back to `DEFAULT_CONVERSATION_TITLE`.

**Response:** **200 OK** with the created conversation.

### 2.8 DELETE /api/chat/conversations/{conversation_id}

Deletes a conversation and all of its messages.

**Response:** **200 OK** `{"message": "對話已刪除"}`

---

### 2.9 WebSocket /api/chat/ws/{user_id}

Bidirectional channel used to push server-side messages to a specific user connection.

**Endpoint:** `ws://localhost:8001/api/chat/ws/1`

> Regular chat should use the SSE endpoint in 2.1; this WebSocket channel is for connection keep-alive and server-initiated pushes.

---

## 3. Knowledge Base & Documents (`/api/documents`)

> Every endpoint in this module requires **admin** privileges.

### 3.1 POST /api/documents/upload

Uploads documents into the knowledge base. Content is parsed, an AI summary is generated, then the text is chunked and indexed into both FAISS and Whoosh BM25.

**Headers:**

```http
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

**Parameters:**

- `file`: file field, repeatable (maximum 10 files per request).
- Allowed extensions: `.txt`, `.md`, `.markdown`, `.pdf`, `.docx`, `.doc`, `.pptx`, `.xlsx`, `.xls`, `.csv`, `.json`, `.yaml`, `.yml`, `.xml`, `.html`, `.htm`, `.log`, `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.java`, `.cpp`, `.c`, `.sql`, `.sh`, `.ini`, `.env`, `.jpg`, `.png`, `.gif`.
- Per-file size limit is controlled by `MAX_FILE_SIZE_MB` (10 MB in the shipped template).

**Response:** **200 OK** with a per-file result list.

```json
{
  "results": [
    {
      "filename": "handbook_2026.pdf",
      "status": "success",
      "document_id": 101,
      "content_length": 28460,
      "content_type": "application/pdf",
      "qa_detected": false,
      "qa_pairs": 0,
      "http_status": 201
    },
    {
      "filename": "duplicate.txt",
      "status": "duplicate",
      "detail": "內容已存在",
      "existing_document_id": 88,
      "http_status": 409
    }
  ]
}
```

---

### 3.2 GET /api/documents/

Lists every document in the knowledge base. Documents without a summary get one generated and persisted during this request.

**Response:** **200 OK**

```json
[
  {
    "id": 101,
    "filename": "handbook_2026.pdf",
    "file_type": "application/pdf",
    "description": "Covers attendance and leave policies...",
    "uploaded_by": 1,
    "is_processed": true,
    "created_at": "2026-09-19T10:00:00"
  }
]
```

---

### 3.3 POST /api/documents/{document_id}/regenerate-summary

Regenerates the AI outline and summary for a document.

**Response:** **200 OK** with `document_id` and the new `description`.

### 3.4 PUT /api/documents/{document_id}/summary

Manually overrides a document summary.

**Request Body:** `{"description": "custom summary"}`

### 3.5 DELETE /api/documents/{document_id}

Deletes the document, its stored file, and the corresponding index entries.

### 3.6 POST /api/documents/rebuild-index

Rebuilds the full FAISS and BM25 indices from the documents currently stored in the database.

---

## 4. Custom API Tools (`/api/api-tools`)

Registers external HTTP APIs as tools the agent can call autonomously. Enabled tools are loaded automatically whenever tool definitions are assembled.

> Every endpoint in this module, including the read-only ones, requires **admin** privileges: the tools are shared by every user's agent, and responses include credentials such as API keys.

### 4.1 POST /api/api-tools/parse-spec

Parses an OpenAPI / Swagger specification (OAS 2.0, 3.0, 3.1) supplied either as raw content or as a URL.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `spec_content_or_url` | string | Yes | Spec content (JSON / YAML) or a reachable spec URL |
| `default_base_url` | string | No | Base URL used when the spec declares no `servers` |

> URLs are validated by the SSRF guard first; private ranges, cloud metadata endpoints, and dangerous ports are rejected.

**Response:** **200 OK** `{"status": "success", "data": { ...parsed endpoints... }}`

- **400 Bad Request**: invalid specification or rejected URL (the message is safe to show to the user).
- **500 Internal Server Error**: any other unexpected exception; only an error code is returned.

---

### 4.2 POST /api/api-tools/import

Bulk-imports the selected endpoints as custom tools. Tools with an existing name are updated in place.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `tools` | array | Yes | Endpoints to import |
| `global_base_url` | string | No | Base URL applied to all endpoints |
| `global_headers` | object | No | Shared headers applied to all endpoints |
| `global_auth_type` | string | No | Shared authentication (`none`, `bearer`, `api_key`, `basic`) |
| `global_auth_config` | object | No | Shared authentication settings |

Key `tools[]` fields: `name`, `display_name`, `description`, `method`, `path`, `full_url`, `base_url`, `headers`, `auth_type`, `auth_config`, `parameters_schema`, `request_body_schema`, `param_locations`, `spec_version`.

**Response:** **200 OK**

```json
{
  "status": "success",
  "message": "成功匯入 4 個新工具，更新 1 個既有工具。",
  "imported": 4,
  "updated": 1
}
```

---

### 4.3 GET /api/api-tools

Lists custom API tools.

**Query parameters:** `category` (string), `is_enabled` (boolean), `search` (string; fuzzy match over name, display name, description, and URL).

**Response:** **200 OK** `{"status": "success", "total": 5, "tools": [ ... ]}`

---

### 4.4 POST /api/api-tools

Creates a single custom API tool manually.

**Request Body:**

| Field | Type | Required | Description | Default |
|---|---|---|---|---|
| `name` | string | Yes | Unique tool identifier used by the model | - |
| `display_name` | string | Yes | Display name | - |
| `description` | string | Yes | Purpose description (drives the model's calling decision) | - |
| `url` | string | Yes | Full request URL | - |
| `method` | string | No | HTTP method | `GET` |
| `base_url` / `path` | string | No | Base URL and path (can replace `url`) | `null` |
| `headers` | object | No | Custom request headers | `null` |
| `auth_type` | string | No | `none`, `bearer`, `api_key`, `basic` | `none` |
| `auth_config` | object | No | Auth settings (`token`, `key_name`, `key_in`, `username`, ...) | `null` |
| `parameters_schema` | object | No | JSON Schema describing the parameters | `null` |
| `request_body_schema` | object | No | Request body structure | `null` |
| `param_locations` | object | No | Per-parameter location (`path` / `query` / `header` / `body`) | `null` |
| `is_enabled` | boolean | No | Whether the tool is active | `true` |
| `timeout` | integer | No | Request timeout in seconds | `15` |

**Response:** **200 OK** with the created tool.

---

### 4.5 GET /api/api-tools/{tool_id}

Returns a single tool. Responds **404 Not Found** when it does not exist.

### 4.6 PUT /api/api-tools/{tool_id}

Updates a tool (send only the fields you want to change).

### 4.7 PATCH /api/api-tools/{tool_id}/toggle

Toggles the enabled state.

**Response:** **200 OK** `{"status": "success", "is_enabled": false, "message": "..."}`

### 4.8 DELETE /api/api-tools/{tool_id}

Deletes a tool.

### 4.9 POST /api/api-tools/{tool_id}/test

Issues a real request with the supplied arguments to verify connectivity and response shape.

**Request Body:** `{"arguments": {"petId": 3}}`

**Response:** **200 OK**

```json
{
  "status": "success",
  "tool_name": "get_pet_by_id",
  "result": {
    "success": true,
    "status_code": 200,
    "duration_seconds": 0.42,
    "url": "https://api.example.com/pets/3",
    "data": { "id": 3, "name": "Miao" }
  }
}
```

> On failure `result.success` is `false` and `error` / `error_id` are returned instead of the internal exception text.
>
> The first request and every redirect target are validated by the SSRF guard; a rejected request returns `result.status_code` `403` with the reason in `error`.

---

## 5. MCP Servers (`/api/mcp`)

Manages Model Context Protocol servers over `stdio` (local subprocess) and HTTP transports.

> Every endpoint in this module, including the read-only ones, requires **admin** privileges: `stdio` servers run the configured command on the host, and responses include credentials such as environment variables and headers.

### 5.1 GET /api/mcp/presets

Returns the built-in catalog of common MCP server templates.

**Response:** **200 OK** `{"status": "success", "presets": [ ... ]}`

### 5.2 GET /api/mcp/servers

Returns all configured MCP servers.

**Query parameters:** `is_enabled` (boolean, optional)

**Response:** **200 OK** `{"status": "success", "total": 2, "servers": [ ... ]}`

Server fields: `id`, `name`, `display_name`, `description`, `transport_type`, `command`, `args`, `env_vars`, `url`, `headers`, `is_enabled`, `status` (`connected` / `disconnected` / `error`), `last_error`, `discovered_tools`, `timeout`, `created_at`, `updated_at`.

---

### 5.3 POST /api/mcp/servers

Creates an MCP server. The backend immediately attempts to connect and discover tools; if discovery fails the server is still created with `status: "error"` and an error code in `last_error`. When the SSRF guard rejects the URL, `last_error` states the reason instead.

**Request Body:**

| Field | Type | Required | Description | Default |
|---|---|---|---|---|
| `name` | string | Yes | Unique server identifier (lower-cased automatically) | - |
| `display_name` | string | Yes | Display name | - |
| `description` | string | No | Description | `null` |
| `transport_type` | string | No | `stdio` or an HTTP transport | `stdio` |
| `command` | string | No | Executable for `stdio` transport | `null` |
| `args` | array | No | Command arguments | `null` |
| `env_vars` | object | No | Environment variables for the subprocess. The subprocess inherits only essential system variables such as `PATH`, never the backend `.env` settings, so list every variable the server needs here | `null` |
| `url` | string | No | Server URL for HTTP transport (every request and redirect is SSRF-validated; loopback and private addresses are rejected) | `null` |
| `headers` | object | No | Headers for HTTP transport | `null` |
| `is_enabled` | boolean | No | Whether the server is active | `true` |
| `timeout` | integer | No | Connection and call timeout in seconds | `30` |

- **400 Bad Request**: a server with the same name already exists.

---

### 5.4 GET /api/mcp/servers/{server_id}

Returns one server with its cached discovered tools.

### 5.5 PUT /api/mcp/servers/{server_id}

Updates the server configuration (send only the fields you want to change).

### 5.6 DELETE /api/mcp/servers/{server_id}

Deletes the server configuration.

### 5.7 POST /api/mcp/servers/{server_id}/discover

Reconnects and re-discovers the server toolset (`initialize` + `tools/list`), refreshing the `discovered_tools` cache.

**Response:** **200 OK**

```json
{
  "status": "success",
  "server_name": "filesystem",
  "total_tools": 6,
  "tools": [{ "name": "read_file", "description": "..." }],
  "server_info": { "protocolVersion": "2024-11-05" }
}
```

- **400 Bad Request**: connection or discovery failed (error code returned), or the SSRF guard rejected the URL (reason returned).

### 5.8 PATCH /api/mcp/servers/{server_id}/toggle

Toggles the server. Disabled servers no longer contribute tools to the agent toolset.

### 5.9 POST /api/mcp/servers/{server_id}/tools/{tool_name}/test

Invokes an MCP tool once (`tools/call`) to verify connectivity.

**Request Body:** `{"arguments": {"path": "/tmp/demo.txt"}}`

**Response:** **200 OK** `{"status": "success", "server_name": "filesystem", "tool_name": "read_file", "result": { ... }}`

> The agent calls MCP tools using the naming convention `mcp_<server_name>_<tool_name>`.

---

## 6. Model Listings (`/api/tags`, `/api/external-tags`)

Ollama-compatible model listing endpoints used by the frontend model selector and external integrations.

### 6.1 GET /api/tags

**Response:** **200 OK** `{"tags": ["gpt-4o", "gpt-4o-mini"], "default": "gpt-4o"}`

If no cloud provider key is configured, the backend tries to read the model list from `LLM_API_BASE` and finally falls back to the built-in list.

### 6.2 GET /api/external-tags

Fetches the model list from `EXTERNAL_TAGS_URL` or `LLM_API_BASE`.

- **400 Bad Request**: neither is configured.

---

## 7. Admin Dashboard (`/api/admin`)

> Every endpoint in this module requires **admin** privileges.

| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/users` | List all users |
| PUT | `/api/admin/users/{user_id}` | Update role, active state, or reset a password |
| DELETE | `/api/admin/users/{user_id}` | Delete a user |
| GET | `/api/admin/statistics` | System statistics (cached for 180 seconds) |
| GET | `/api/admin/conversations` | List all conversations |
| GET | `/api/admin/conversations/{conversation_id}/messages` | Messages of a conversation |
| DELETE | `/api/admin/conversations/{conversation_id}` | Delete a conversation |
| GET | `/api/admin/documents` | List all documents |
| DELETE | `/api/admin/documents/{document_id}` | Delete a document |
| GET | `/api/admin/rag-config` | Current RAG retrieval configuration |
| GET | `/api/admin/vector-store/info` | Vector index information |
| GET | `/api/admin/vector-store/statistics` | Vector index statistics |
| POST | `/api/admin/vector-store/reindex` | Trigger a full reindex |
| DELETE | `/api/admin/vector-store/clear` | Clear the vector index |

**GET /api/admin/statistics example:**

```json
{
  "users": { "total": 12, "active": 11, "admins": 2 },
  "conversations": { "total": 340 },
  "messages": { "total": 2870, "recent_7_days": 412 },
  "documents": { "total": 58, "processed": 57 },
  "daily_stats": [{ "date": "2026-09-19", "messages": 63 }]
}
```

---

## 8. Error Handling Schema

The API uses FastAPI's standard error envelope, with the message in `detail`:

```json
{
  "detail": "找不到該自訂 API 工具"
}
```

### Error code mechanism

Unexpected server-side exceptions never return the exception text or stack trace. Instead a random error code is returned while the full exception is written to the server log, where it can be located by that code (CWE-209 / CWE-497):

```json
{
  "detail": "伺服器內部錯誤，請聯繫系統管理員並提供錯誤代碼（錯誤代碼：9f2c71a4b8de）",
  "error_id": "9f2c71a4b8de"
}
```

Input validation errors (for example a malformed OpenAPI specification supplied by the user) return an actionable message directly and do not use the error code mechanism.

### Common status codes

| Status | Cause |
|---|---|
| **400 Bad Request** | Malformed request, duplicate name, spec parsing failure, or a URL rejected by the SSRF guard |
| **401 Unauthorized** | Missing Authorization header, or an invalid / expired / revoked JWT |
| **403 Forbidden** | Insufficient permissions (non-admin accessing an admin endpoint) |
| **404 Not Found** | Requested resource (conversation, document, tool, MCP server) does not exist |
| **409 Conflict** | Uploaded document duplicates existing content |
| **422 Unprocessable Entity** | Pydantic field validation failed |
| **429 Too Many Requests** | Exceeded the `RATE_LIMIT_PER_MINUTE` limit |
| **500 Internal Server Error** | Unexpected exception; the response carries only an error code |
