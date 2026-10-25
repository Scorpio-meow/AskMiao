# AskMiao API Reference

[繁體中文](api.md) | [English](api_en.md)

> REST and SSE streaming endpoints of the AskMiao **5.0.0** backend, written against the actual routers in `backend/app/api/`. With `ENABLE_API_DOCS=true` the backend also serves interactive docs at `http://localhost:8001/docs` (Swagger UI) and `http://localhost:8001/redoc`, and the OpenAPI document at `/openapi.json`. These three paths need no sign-in and list every endpoint and parameter, so keep `ENABLE_API_DOCS=false` (the template value) for public deployments; all three then return `404`.

## Contents

- [0. Conventions](#0-conventions)
- [1. Authentication `/api/auth`](#1-authentication-apiauth)
- [2. Chat and research `/api/chat`](#2-chat-and-research-apichat)
- [3. Knowledge-base documents `/api/documents`](#3-knowledge-base-documents-apidocuments)
- [4. Custom API tools `/api/api-tools`](#4-custom-api-tools-apiapi-tools)
- [5. MCP servers `/api/mcp`](#5-mcp-servers-apimcp)
- [6. Agent Skills `/api/skills`](#6-agent-skills-apiskills)
- [7. Model lists `/api/tags`](#7-model-lists-apitags)
- [8. Admin `/api/admin`](#8-admin-apiadmin)
- [9. Health checks](#9-health-checks)
- [10. Error handling](#10-error-handling)
- [11. Known limitations](#11-known-limitations)

---

## 0. Conventions

| Item | Description |
|---|---|
| Base URL | `http://localhost:8001` (set by `HOST` / `PORT`) |
| Authentication | Send `Authorization: Bearer <access_token>`; the refresh token lives in the HttpOnly cookie `refresh_token` (path `/api/auth`) and is sent by the browser automatically |
| Content types | `multipart/form-data` for uploads, `text/event-stream` for chat streaming, `application/json` for everything else |
| Timestamps | ISO 8601 in UTC without a timezone suffix (for example `2026-09-25T02:30:00`) |
| Rate limit | `RATE_LIMIT_PER_MINUTE` requests per client IP per 60 seconds (default 60); beyond that the API returns `429`. The client IP is the direct peer unless `FORWARDED_ALLOW_IPS` names a proxy whose `X-Forwarded-For` is trusted |
| Request body limit | 1 MiB for general requests; `POST /api/chat/send` allows more with a valid access token, and `POST /api/documents/upload` and `POST /api/skills/upload` only when the valid access token's `is_admin` claim is `true`. Larger bodies get `413` `{"detail": "請求內容超過大小上限"}`; see [configuration reference: resource limits](configuration_en.md#resource-limits) |

### Permission levels

| Level | Requirement | Otherwise |
|---|---|---|
| Public | No token needed | — |
| Signed in | A valid, unrevoked access token whose account still exists and is active, issued no earlier than the account's `tokens_valid_after` | `401` |
| Admin | The account's `is_admin` is `true` in the database | `403` (`{"detail": "需要管理員權限"}`, "admin permission required") |

> [!NOTE]
> Every request loads the account named by the token's `sub` from the database: once an account is deleted or deactivated, its issued access tokens stop working immediately, and `is_admin` and the role also come from the database, so admin changes apply on the next request. Tokens issued before the account's `tokens_valid_after` get `401`: it equals the creation time when the account is created (so an old token cannot map to a new account that reuses a deleted account's id) and is set to the current time on a password change (see [Token model](#token-model)).

API messages are in Traditional Chinese; the English glosses in this document are for reference only.

### Endpoint overview

| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/api/auth/registration` | Public | Whether self-registration is open |
| POST | `/api/auth/register` | Public | Register and sign in (only with `ALLOW_REGISTRATION=true`) |
| POST | `/api/auth/login` | Public | Sign in |
| POST | `/api/auth/refresh` | Public (cookie required) | Exchange the refresh token for new tokens |
| GET | `/api/auth/me` | Signed in | Get the current profile |
| PUT | `/api/auth/me` | Signed in | Update email or password |
| POST | `/api/auth/change-password` | Signed in | Change the password |
| POST | `/api/auth/logout` | Access token (signature only) | Sign out and revoke tokens |
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
| POST | `/api/mcp/servers/{server_id}/oauth/start` | Admin | Start OAuth authorization and get the authorization URL |
| GET | `/api/mcp/oauth/callback` | Public | Where the OAuth authorization server redirects back |
| DELETE | `/api/mcp/servers/{server_id}/oauth` | Admin | Clear the stored OAuth tokens |
| GET | `/api/skills/enabled` | Signed in | Names and descriptions of the enabled skills the caller may use |
| GET | `/api/skills` | Admin | List skills |
| GET | `/api/skills/{skill_id}` | Admin | One skill with its `SKILL.md` body |
| POST | `/api/skills/upload` | Admin | Upload and install a skill |
| PATCH | `/api/skills/{skill_id}/toggle` | Admin | Toggle enabled state |
| PATCH | `/api/skills/{skill_id}/settings` | Admin | Set script execution and which accounts may use the skill |
| DELETE | `/api/skills/{skill_id}` | Admin | Delete a skill and its files |
| GET | `/api/tags` | Public | Model list in the Ollama `tags` format |
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

> [!NOTE]
> `GET /api/external-tags`, which needed no sign-in, and the demo WebSocket `/api/chat/ws/{user_id}` have been removed (the frontend used neither): use `GET /api/chat/models` or `GET /api/tags` for model lists and the [SSE endpoint in 2.1](#21-post-apichatsend) for chat.

---

## 1. Authentication `/api/auth`

### Token model

| Token | Where it lives | Lifetime | Purpose |
|---|---|---|---|
| Access token | `tokens.access_token` in the JSON response; the frontend sends it in the `Authorization` header | `ACCESS_TOKEN_EXPIRE_MINUTES` (30 minutes by default) | Calls every signed-in endpoint; carries `sub`, `username`, `email`, `role`, and `is_admin`, but the backend uses only `sub` and `iat` to find the database account, whose identity and permissions are authoritative |
| Refresh token | HttpOnly cookie `refresh_token`, path `/api/auth` | `REFRESH_TOKEN_EXPIRE_DAYS` (7 days by default) | Used only by `POST /api/auth/refresh`, and only once; every exchange resets the cookie |

Tokens are always signed RS256 with an RSA-2048 private key; the backend refuses to start if the RSA keys cannot be loaded. `tokens.refresh_token` in the JSON response is always an empty string because the real refresh token only lives in the cookie, and `expires_in` is currently always `1800`; the `exp` claim inside the token is authoritative. The `iat` of access and refresh tokens is in seconds with a microsecond fraction (RFC 7519 NumericDate allows fractions, for example `1791561600.640123`), while `exp` stays in whole seconds; clients that decode tokens themselves should not assume `iat` is an integer.

**A password change revokes every token**: `users.tokens_valid_after` equals the creation time when an account is created and is set to the current time on a password change ([1.5](#15-put-apiauthme) with `new_password`, or [1.6](#16-post-apiauthchange-password)); access and refresh tokens issued (`iat`) before it get `401`, including the access token that made the request and sessions on other devices. The comparison is to the microsecond, so tokens issued earlier in the same second as the password change are rejected too, while tokens issued after the change (for example by signing in again right away) work as usual. A successful change also clears the refresh token cookie, so the client must sign in again with the new password (the frontend clears its sign-in state and returns to the login page).

### 1.1 POST /api/auth/register

Create an account and sign in: the access token is returned and the refresh token is set as a cookie. New accounts are always regular users.

Registration is open only when the required setting `ALLOW_REGISTRATION` is `true`. With `false` (the template value) registration requests get `403` and a security log entry (`REGISTER_REJECTED`), and accounts, including the first admin, are created by an administrator running `python scripts/create_user.py --username <name> --email <email>` in `backend/`: the password is entered interactively twice and follows the same rules as registration, and `--admin` creates an admin (see [configuration reference: registration and account creation](configuration_en.md#registration-and-account-creation)). Clients can check whether registration is open with [1.9](#19-get-apiauthregistration) first.

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
| `403` | `目前不開放註冊，請聯繫管理員建立帳號` ("registration is closed; ask an administrator for an account"), when `ALLOW_REGISTRATION=false` |
| `422` | Field format errors (length, characters, email format) |

### 1.2 POST /api/auth/login

Sign in with a username **or** an email address.

**Request body**: `{"username": "miao_user", "password": "Secret123"}` (`username` at most 254 characters, `password` at most 256)

**Response**: `200 OK` with the same shape as registration (`message` is `登入成功`), and `last_login` is updated. Passwords stored as legacy bcrypt hashes are re-hashed with Argon2 on a successful sign-in.

**Login throttling**:

- Failures are counted separately per login identifier and per source IP. The login identifier is the value of the `username` field (trimmed and case-insensitive; a username and an email address are counted separately), and unknown accounts are counted too; the source IP is determined the same way as for rate limiting (see [0. Conventions](#0-conventions)).
- Once one identifier fails `LOGIN_MAX_FAILURES_PER_ACCOUNT` times, or one source IP fails `LOGIN_MAX_FAILURES_PER_ADDRESS` times, within `LOGIN_FAILURE_WINDOW_SECONDS` seconds, logins for that identifier or IP pause for `LOGIN_LOCKOUT_SECONDS` seconds. The attempt that reaches the threshold still gets `401`; during the pause every login request gets `429` with `Retry-After` set to the remaining seconds (rounded up), the password is not checked even when it is correct, and the response does not reveal whether it was. The pause lifts on its own and counting starts over; it affects only sign-ins, and tokens already issued keep working.
- A successful sign-in clears only that identifier's failures; failures from the same IP against other identifiers still count. When users reach the backend through a proxy and share one source IP, set the per-address threshold higher than the per-account one.
- All four settings are required (minimum 1); `backend/.env.example` uses `5`, `20`, `900`, and `900`. See [configuration reference: login throttling](configuration_en.md#login-throttling).

| Status | When |
|---|---|
| `401` | `使用者名稱或密碼錯誤` (wrong username or password); unknown accounts, wrong passwords, and deactivated accounts all get the same response |
| `422` | A field exceeds its length limit |
| `429` | `登入失敗次數過多，請稍後再試` ("too many failed sign-ins; try again later"): logins for the identifier or source IP are paused; the response includes `Retry-After` |

> [!NOTE]
> Failure counts and pauses live in the backend process's memory: they are cleared on restart and counted separately by each process. At most 10,000 login identifiers and 10,000 source IPs are tracked; beyond that, those that have gone longest without a new failure are evicted first, along with their failures and any pause.

### 1.3 POST /api/auth/refresh

Read the refresh token from the cookie, issue a new access token, and reset the cookie; no `Authorization` header is needed. The token is likewise mapped to the database account by `sub` (the account must exist and be active, and the token must not be older than `tokens_valid_after`), and the used refresh token is revoked immediately, so reusing it returns `401`.

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
| `401` | Refresh token missing (`找不到重新整理權杖`), of the wrong type (`重新整理權杖類型無效`), or revoked (`權杖已被撤銷`, including an already used token), or `認證權杖無效：驗證失敗` ("token verification failed": invalid signature, expired, account missing or deactivated, or the password changed after it was issued); other errors return `重新整理權杖失敗` ("refresh failed") |

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

When `new_password` is set and the change succeeds, every token issued to the account, including the access token used for this request, stops working at once; the response also clears the refresh token cookie, and the client must sign in again with the new password (see [Token model](#token-model)). Changing only `email` leaves tokens alone.

### 1.6 POST /api/auth/change-password

| Field | Type | Required | Description |
|---|---|---|---|
| `current_password` | string | Yes | Current password |
| `new_password` | string | Yes | New password, same rules as registration |
| `confirm_password` | string | Yes | Must equal `new_password`, otherwise `422` |

**Response**: `200 OK` `{"message": "密碼修改成功，所有裝置都需要以新密碼重新登入", "success": true}` ("password changed; every device must sign in again with the new password"); a wrong current password returns `400` `目前的密碼錯誤`, and a new password that breaks the rules returns `400` with a password strength message.

After a successful change, every token issued to the account, including the access token used for this request and sessions on other devices, stops working at once; the response also clears the refresh token cookie, and the client must sign in again with the new password (see [Token model](#token-model)).

### 1.7 POST /api/auth/logout

Add the access token from the `Authorization` header and the refresh token from the cookie to the revocation list (each kept until it expires), and delete the cookie.

Only the access token's signature and type are verified; its expiry, revocation, and the account's status are not checked, so you can still sign out after the access token expires: the refresh token is still revoked and the cookie still cleared (an expired access token is already invalid and is not added to the revocation list). The `Authorization` header is still required, so a cross-site form cannot trigger a logout.

**Response**: `200 OK` `{"message": "登出成功", "success": true}`

| Status | When |
|---|---|
| `401` | No `Authorization` header (`Not authenticated`), an invalid signature (`認證權杖無效：驗證失敗`), or not an access token (`權杖類型無效`, "invalid token type") |

> [!NOTE]
> The revocation list lives in the backend process's memory (at most 100,000 entries; when full, the entries expiring soonest are evicted first). It is cleared when the backend restarts, and unexpired tokens become valid again. Invalidation caused by a password change is checked against `tokens_valid_after` in the database and survives restarts.

### 1.8 POST /api/auth/validate-token

**Response**: `200 OK` `{"message": "權杖有效", "success": true}`; an invalid token returns `401`.

### 1.9 GET /api/auth/registration

Whether self-registration is open; no sign-in is needed, and the value is `ALLOW_REGISTRATION`. The frontend uses it to decide whether the login page shows the sign-up link; when registration is closed or the query fails, the sign-up page shows an explanation instead.

**Response**: `200 OK` `{"enabled": false}`

---

## 2. Chat and research `/api/chat`

### 2.1 POST /api/chat/send

Send a message and start the `ResearchAgent`. The response is a **Server-Sent Events** stream (`Content-Type: text/event-stream`, with `Cache-Control: no-cache` and `X-Accel-Buffering: no`).

**Request body**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `content` | string | Yes | — | The user's question, at most 20,000 characters; when it starts with `/skill-name` for an enabled skill, that skill is loaded first, the prefix is removed, and an `activate_skill` step is recorded in the research trace |
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

At most 50,000 characters of each attachment's text go into the model context; the rest is truncated. Text extracted from a `data_url` is subject to a chat attachment parsing budget that is stricter than for admin uploads (for example, at most 64 MiB uncompressed for a `.docx`, `.pptx`, or `.xlsx`, and at most 8 MiB in total of the XML that `.docx` and `.pptx` parsing builds into a DOM), and each backend process parses at most 2 attachments at a time while the rest wait. An attachment over budget does not fail the request; the model is told that it was not read (附件超過解析上限，未讀取內容, "the attachment exceeds the parsing limit; content not read"). See [configuration reference: resource limits](configuration_en.md#resource-limits) for all limits.

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
| `approval_required` | The tool needs approval and the agent pauses (see [2.9](#29-post-apichatapprovalsapproval_id)) | `approval_id`, `step`, `tool`, `tool_display_name`, `target`, `arguments` |
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

In `approval_required`, `tool_display_name` is the tool's display name (`<server display name> → <tool name>` for MCP tools), and `target` names where this call actually goes:

| Tool | `target` format | Example |
|---|---|---|
| Custom API tool | HTTP method and the host of the tool's configured URL (with the port when one is given; no path or query string) | `POST api.example.com` |
| MCP server (`http` / `sse`) | Upper-case transport and the host of the server URL | `HTTP mcp.example.com:8443` |
| MCP server (`stdio`) | `本機指令` ("local command") followed by the command's file name (no path or arguments) | `本機指令 npx` |

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

- When the model stops calling tools, its answer arrives in **one** `token` event; only when the model returns empty content is the answer streamed over several `token` events.
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
- When an enabled MCP server has discovered resources or prompts, `read_mcp_resource` (parameters `server`, `uri`) and `get_mcp_prompt` (parameters `server`, `name`, `arguments`), whose descriptions list the available items (see [Server object](#server-object)).
- When at least one enabled Agent Skill that the caller can see has its files present, `activate_skill` and `read_skill_resource`, plus `run_skill_script` when one of them has `allow_scripts` turned on (see [6. Agent Skills](#6-agent-skills-apiskills)); otherwise none of them appears.

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

### 2.9 POST /api/chat/approvals/{approval_id}

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
- `run_skill_script` always needs approval (`target` is `本機指令 <interpreter>`, "local command"); `read_mcp_resource` and `get_mcp_prompt` follow that MCP server's `requires_approval`.
- After a skill is activated, the tool names in its `allowed-tools` no longer ask for approval for the rest of that question (see [Skill object](#skill-object)).
- Pending items live in the backend process's memory and are lost when the backend restarts.

---

## 3. Knowledge-base documents `/api/documents`

> Every endpoint in this module requires **admin** access.

### 3.1 POST /api/documents/upload

Upload documents to the knowledge base. Each file goes through: name and extension checks → size check → text extraction (blank or garbled PDF pages are OCR'd by a vision model) → duplicate check → AI summary → saved to `documents` → chunked into `rag_chunks`, FAISS, and BM25.

**Request**: `multipart/form-data` with the field name `file`, repeatable, up to 10 files per request.

- Supported extensions: `.txt`, `.md`, `.markdown`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`, `.json`, `.jsonl`, `.yaml`, `.yml`, `.xml`, `.html`, `.htm`, `.log`, `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.java`, `.cpp`, `.c`, `.sql`, `.sh`, `.ini`, `.env`.
- Per-file limit: `MAX_FILE_SIZE_MB` (10 MB in the template). The whole request body may be 10 × `MAX_FILE_SIZE_MB` MiB + 1 MiB, but only with a valid access token whose `is_admin` claim is `true` (1 MiB otherwise); larger bodies get `413`. The limit is chosen from the token's claims before the request is parsed; admin status itself still comes from the database, so an account that has lost admin rights gets `403`.
- A `.docx`, `.pptx`, or `.xlsx` whose total uncompressed size exceeds 200 MiB, that contains more than 10,000 files, or that compresses more than 100:1 (checked for each member and for the whole file once they exceed 10 MiB uncompressed) is rejected before parsing; scanned PDF pages are rasterized at no more than 25 MP each.
- Spaces in file names become underscores; a name that already exists gets a `_1`, `_2`, … suffix; names containing `/`, `\`, `..`, `<`, `>`, `:`, `"`, `|`, `?`, or `*` are rejected.
- A file whose extracted text (with surrounding whitespace removed) is identical to an existing document's is a duplicate and is not stored again.
- Chunking: JSON, JSONL, YAML, CSV, XLSX, and JS declarations are parsed into structured records that become one chunk each, with long records split into parts; Q&A in other formats becomes one chunk per pair; everything else is split recursively by `CHUNK_SIZE` / `CHUNK_OVERLAP`. The record format is described in [Architecture](architecture_en.md#structured-data).

**Response**: `200 OK` with one result per file; `http_status` reports each file's outcome. In a successful item, `qa_pairs` is the number of Q&A pairs, `record_count` the number of structured records, and `warning` explains when a structured format failed to parse or exceeded the parse limit and was handled as plain text, and is `null` otherwise:

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
      "record_count": 0,
      "warning": null,
      "http_status": 201
    },
    {
      "filename": "posts.json",
      "status": "success",
      "document_id": 102,
      "content_length": 5120,
      "content_type": "application/json",
      "qa_detected": false,
      "qa_pairs": 0,
      "record_count": 42,
      "warning": null,
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

List every document (`id`, `filename`, `file_type`, `description`, `uploaded_by`, `created_at`, `is_processed`). The full extracted text is not included, and no summaries are generated during this request; give a document without a summary one with 3.3, or let an index rebuild fill it in.

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

Rebuild the index from the documents in the database: after clearing chunks and indexes, every document is re-extracted (from the uploaded file when it still exists, overwriting `documents.content`) and re-chunked and re-embedded with the current settings; documents without a summary get an AI summary, and existing summaries, including hand-edited ones, are kept. The knowledge base returns nothing until the rebuild finishes, and a second call while one is running returns `409` `索引重建正在進行中，請等待完成後再試` (a rebuild is already running). A document whose uploaded file is gone is chunked from the stored content as plain text and listed in `missing_source_files`; re-upload it. Run it once after upgrading from 2.x; it takes longer the more documents you have.

```json
{
  "message": "索引重建成功（已用新配置重新分塊，並替缺少摘要的文件生成 AI 智能大綱）",
  "document_count": 6,
  "chunk_count": 214,
  "qa_pairs_detected": 0,
  "records_detected": 42,
  "missing_source_files": [],
  "chunk_size": 300,
  "chunk_overlap": 100,
  "timestamp": "2026-09-25T10:00:00.000000"
}
```

With no documents in the database it returns `{"message": "索引重建完成（沒有文件）", "document_count": 0, "chunk_count": 0, "qa_pairs_detected": 0, "records_detected": 0, "missing_source_files": [], "timestamp": "..."}`.

---

## 4. Custom API tools `/api/api-tools`

Register external HTTP APIs as tools the agent can call. Enabled tools are loaded whenever tool definitions are assembled, so changes need no restart.

> Every endpoint in this module, including reads, requires **admin** access: tools are shared by every user's agent and call external APIs with the configured credentials (stored encrypted and shown as `••••••••` in responses). See [ADR-0004](adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md).

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
| `headers` | object | Fixed request headers; responses show every header value as `••••••••` except `Accept`, `Accept-Encoding`, `Accept-Language`, `Cache-Control`, `Content-Type`, and `User-Agent` |
| `auth_type` | string | `none`, `bearer`, `api_key`, `basic`, or `oauth2_client_credentials`; other values return `422` |
| `auth_config` | object | Auth settings; see the table below. `token`, `key_value`, `password`, and `client_secret` are shown as `••••••••` in responses |
| `body_content_type` | string | Request body format: `application/json` (default), `application/x-www-form-urlencoded`, or `multipart/form-data`; other values return `422` |
| `parameters_schema` | object | JSON Schema of the parameters, used as the `parameters` the model sees; calls accept only the parameters declared in its `properties` |
| `request_body_schema` | object | Request body structure; when it has `properties`, it is also used to check the fields of `request_body` |
| `param_locations` | object | Where each parameter goes: `path`, `query`, `header`, or `body` |
| `response_mapping` | string | Reserved, currently unused |
| `is_enabled` | boolean | Whether the tool is enabled |
| `requires_approval` | boolean | Whether the asking user must approve in the chat before the agent calls it (see [2.9](#29-post-apichatapprovalsapproval_id)). When omitted on create or import it follows the method: `false` for `GET`, `HEAD`, and `OPTIONS`, `true` for everything else |
| `timeout` | integer | Timeout in seconds, 15 by default |
| `spec_version` | string | Source spec version, `manual` for hand-made tools |
| `created_at` / `updated_at` | string | Timestamps |
| `credentials_unreadable` | boolean | Responses only: `true` when `headers` or `auth_config` cannot be decrypted with the current `TOOL_SECRETS_KEY`; the unreadable field is returned as `null` and must be entered again |

| `auth_type` | `auth_config` fields |
|---|---|
| `bearer` | `token` |
| `api_key` | `key_name` (default `X-API-Key`), `key_value`, `key_in` (`header` or `query`) |
| `basic` | `username`, `password` |
| `oauth2_client_credentials` | `token_url`, `client_id`, `client_secret`, `scope`, `client_auth` (`basic` sends the client credentials with HTTP Basic, `post` puts them in the form body) |

**OAuth2 client credentials**: before the call, the backend POSTs a form with `grant_type=client_credentials` (and `scope`) to `token_url` and sends the access token as `Authorization: Bearer`. The token is cached in the backend process until 30 seconds before `expires_in` (300 seconds when there is no `expires_in`); a `401` from the API drops the cached token, fetches a new one, and retries once. Token endpoint requests are SSRF-validated too, follow only same-origin redirects, and have a 15-second timeout and a 256 KiB response limit; if no token can be obtained the API is not called, `status_code` is `502`, and `error` carries only an error code. The access token and `client_secret` are replaced with `[已遮蔽]` wherever they appear in the result.

**Credential encryption and masking**: `headers` and `auth_config` are encrypted with `TOOL_SECRETS_KEY` (Fernet) before they reach the database, and at startup the backend encrypts rows that earlier versions stored in plaintext. Admin API responses show `••••••••` in place of secret values (empty values are not masked), so a credential cannot be read back through the API once saved. On update, a `headers` or `auth_config` you send replaces the whole field, and keys whose value is still `••••••••` keep their stored value; if such a key has no stored value (including when the stored credentials cannot be decrypted), the API returns `400` `欄位 <name> 沒有已儲存的值，請輸入實際內容` ("field <name> has no stored value; enter the actual value"). After `TOOL_SECRETS_KEY` changes, stored credentials can no longer be decrypted (`credentials_unreadable` is `true`), and the tool cannot run until they are entered again: an agent call returns an error with an error ID, and the [test endpoint](#49-post-apiapi-toolstool_idtest) returns `400` `無法以目前的 TOOL_SECRETS_KEY 解密工具憑證，請重新輸入` ("stored tool credentials cannot be decrypted with the current TOOL_SECRETS_KEY; enter them again"); see [configuration reference: tool credential encryption](configuration_en.md#tool-credential-encryption) for the key and what it covers.

**Parameter assembly**: parameters that appear as `{name}` in the URL or are located in `path` are substituted into the URL; `header` parameters go into headers, `query` parameters into the query string, and `body` parameters into the body. The body is sent as JSON, as a form (`application/x-www-form-urlencoded`), or as `multipart/form-data` fields (no files) according to `body_content_type`; in both form encodings, object and array values become JSON strings and booleans become `true` / `false`. Parameters without a location go into the body for `POST`, `PUT`, and `PATCH`, and into the query string otherwise. A `request_body` object passed by the model replaces the whole body.

**Only declared parameters**: every parameter the caller (the agent or the [4.9](#49-post-apiapi-toolstool_idtest) test) passes must be listed in `parameters_schema.properties`; otherwise no request is sent and the result's `status_code` is `400` (`工具參數無效：未宣告的參數 …`, "invalid tool parameters: undeclared parameter …"). A tool that declares no parameters accepts none. `request_body` must be declared as well, and when `request_body_schema` has `properties` and `additionalProperties` is not `true`, the fields of the `request_body` object must be listed there too; undeclared fields are reported as `request_body.<field>`.

**Fixed query parameters**: query parameters in the tool URL are fixed by the admin and cannot be overridden: if a parameter that would go into the query string has the same name as a fixed one, no request is sent and `status_code` is `400` (`工具參數無效：不可覆寫工具網址中固定的查詢參數 …`, "cannot override a fixed query parameter of the tool URL"). Because these values may be keys written into the URL, the `url` in the result shows the values of fixed query parameters and of a query-string API key as `[已遮蔽]`, and some failures return the URL without its query string.

**Path parameters and host**: path parameters are always percent-encoded (`/`, `?`, `#`, and `%` included), and the values `.` and `..` are rejected; after substitution the URL must keep the scheme, host, and port of the configured URL, or the request is not sent.

### 4.1 POST /api/api-tools/parse-spec

Parse an OpenAPI / Swagger spec (OAS 2.0, 3.0, 3.1) from JSON / YAML text or a spec URL.

| Field | Type | Required | Description |
|---|---|---|---|
| `spec_content_or_url` | string | Yes | Spec text, or a spec URL starting with `http://` or `https://` |
| `default_base_url` | string | No | Overrides the server URL in the spec |

Spec URLs are SSRF-validated first (every hop is pinned to the validated IP) and fetched with a 10 MB limit, a 15-second timeout, and at most 5 redirects. YAML specs must not use aliases (`*alias`), or the request gets `400`: aliases are expanded during later processing, so a spec of a few KB could produce hundreds of MB of data.

**Response**: `200 OK` with the parsed endpoints only, not the raw spec (the former `raw_spec` field has been removed)

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
        "auth_type": "api_key",
        "auth_config": {"key_name": "X-API-Key", "key_in": "header", "key_value": ""},
        "param_locations": {"petId": "path"},
        "parameters_schema": {"type": "object", "properties": {"petId": {"type": "integer"}}, "required": ["petId"]},
        "function_definition": {"type": "function", "function": {"name": "get_pet_by_id", "...": "..."}},
        "tags": ["pets"],
        "spec_version": "openapi_3.0"
      }
    ]
  }
}
```

Tool names come from `operationId` (lowercased, with non-alphanumeric characters replaced by underscores); without an `operationId`, the method and path are combined, such as `get_pets_petid`.

`body_content_type` is chosen from the spec's request body formats in the order `application/json`, `application/x-www-form-urlencoded`, `multipart/form-data`; other formats (such as XML) fall back to JSON. `auth_type` and `auth_config` come from the endpoint's `security` (or the spec's top-level `security`) and `securitySchemes` (under `components` in 3.x) or `securityDefinitions` (2.0); only the settings are filled in, and credentials are left empty:

| Auth in the spec | `auth_type` | `auth_config` filled in |
|---|---|---|
| `apiKey` (`in` is `header` or `query`) | `api_key` | `key_name`, `key_in` |
| `http` `basic`, 2.0 `basic` | `basic` | — |
| `http` `bearer` | `bearer` | — |
| `oauth2` `clientCredentials` flow, 2.0 `application` flow | `oauth2_client_credentials` | `token_url` (`tokenUrl`), `scope` (the scopes in the requirement, space-separated), `client_auth` `basic` |
| `apiKey` with `in: cookie`, other OAuth flows, requirements that combine several schemes | `none` | — |

| Status | When |
|---|---|
| `400` | Invalid spec (including one that uses YAML aliases), unrecognized version, or an unreachable URL (the message is safe to show to users); a URL rejected by the SSRF guard only reports the rejection with an error code, and the full reason goes to the server log |
| `500` | Any other unexpected exception; only an error code is returned |

### 4.2 POST /api/api-tools/import

Bulk-import the endpoints selected from a parsed spec. Tools with the same name are overwritten and re-enabled.

| Field | Type | Required | Description |
|---|---|---|---|
| `tools` | array | Yes | Endpoints with the parsed fields: `name`, `display_name`, `description`, `method`, `path`, `full_url` (required), plus optional `base_url`, `headers`, `auth_type`, `auth_config`, `body_content_type`, `parameters_schema`, `request_body_schema`, `param_locations`, `spec_version` |
| `global_base_url` | string | No | Used when an endpoint has no `base_url` |
| `global_headers` | object | No | Shared headers; an endpoint's own header of the same name wins |
| `global_auth_type` | string | No | Used when an endpoint's `auth_type` is empty or `none` |
| `global_auth_config` | object | No | Used as a whole when an endpoint's `auth_type` is empty or `none`; when the endpoint's `auth_type` equals `global_auth_type`, its non-empty values override the endpoint's `auth_config` |

An endpoint's declared auth wins: the Bearer token in the frontend import dialog only goes into endpoints that declare no auth or declare Bearer, and credentials for other auth types are entered by editing the tool with 4.6 after import. An `auth_type` or `body_content_type` outside the allowed values returns `422`.

Newly imported tools get `requires_approval` from their method (`true` for anything other than `GET`, `HEAD`, and `OPTIONS`). When an existing tool is overwritten, a tool that required approval keeps requiring it, while `headers` and `auth_config` are replaced with what this import sends (including `global_headers` and `global_auth_config`): stored credentials are not kept and are cleared when none are sent. Change tools afterwards with 4.6.

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

Send only the fields you change (`name` cannot be changed). Changing `method` to anything other than `GET`, `HEAD`, or `OPTIONS` without also sending `requires_approval` sets `requires_approval` to `true`. A `headers` or `auth_config` you send replaces the whole field; keys whose value is `••••••••` keep their stored value, and a masked key with no stored value returns `400` (see [Tool object](#tool-object)). **Response**: `{"status": "success", "message": "自訂 API 工具更新成功", "tool": {...}}`.

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
- Credentials injected into this request (header values, Bearer token, API key, Basic auth) are replaced with `[已遮蔽]` ("redacted") wherever they appear in `data` or `url`; in `url`, the values of a query-string API key and of the tool URL's fixed query parameters are masked too.
- The backend follows redirects itself, at most 5, and never reads the body of a redirect response; a redirect to another origin (different scheme, host, or port) does not carry the admin-configured headers or the auth header.
- The whole call, including redirects and reading the response, has an overall deadline of the tool's `timeout` seconds; past it the call is aborted and `status_code` is `504` (`上游在 <timeout> 秒內沒有完成回應`, "the upstream did not finish responding within <timeout> seconds").
- The first request and every redirect are SSRF-validated again, with the connection pinned to the validated IP; a rejection reports `status_code` `403`, `is_success` `false`, an `error` that only states the SSRF rejection with an error code, and `error_id`; the full reason goes to the server log.
- An undeclared parameter, an invalid path parameter, a host mismatch after substitution, or an attempt to override a fixed query parameter of the tool URL stops the request before it is sent and reports `status_code` `400` with the reason in `error` (see [Tool object](#tool-object)).
- Other failures report `status_code` `500` with only `error` (including an error code) and `error_id`.
- Custom API tools, the MCP HTTP transport, and `web_fetch`'s direct fetches ignore the `HTTP_PROXY` and `HTTPS_PROXY` environment variables and always connect directly.
- Agent calls run the same code; when `requires_approval` is `true` they need the user's approval first, while this admin test endpoint does not.

---

## 5. MCP servers `/api/mcp`

Manage Model Context Protocol servers, protocol version `2025-06-18` (the version the server replies with wins), using JSON-RPC 2.0 for `initialize`, `notifications/initialized`, `tools/list` (all pages are read by following `nextCursor`, at most 50), and `tools/call`; when the server's `initialize` capabilities declare `resources` or `prompts`, `resources/list` and `prompts/list` are read with the same paging, and `resources/read` and `prompts/get` use them. The handshake declares no client capabilities (sampling and roots are not supported). The handshake identifies the client as `AskMiao-MCP-Client` with the backend version.

> Every endpoint in this module except the OAuth callback ([5.11](#511-get-apimcpoauthcallback)), including reads, requires **admin** access: `stdio` servers run the configured command on the host, and server settings include credentials such as environment variables and headers (stored encrypted and shown as `••••••••` in responses).

### Server object

| Field | Type | Description |
|---|---|---|
| `id` | integer | Server ID |
| `name` | string | Unique name (lowercased on creation), used in tool names `mcp_<name>_<tool>` |
| `display_name` / `description` | string | Display name and description |
| `transport_type` | string | `stdio`, or `http` / `sse` (both try Streamable HTTP first: JSON-RPC over POST with `Accept: application/json, text/event-stream`, accepting a JSON or SSE response, and sending the server-issued `Mcp-Session-Id` and `MCP-Protocol-Version` on later requests; a `404` on a request that carries a session re-initializes once and retries, and closing ends the session with `DELETE`. When `initialize` gets `400`, `404`, or `405`, the legacy HTTP+SSE transport is used instead; see below) |
| `command` / `args` | string / array | Command and arguments for `stdio` |
| `env_vars` | object | Extra environment variables for the `stdio` subprocess; all are treated as credentials, so every value is shown as `••••••••` in responses |
| `url` / `headers` | string / object | Server URL and request headers for HTTP; `headers` are masked like a custom API tool's |
| `is_enabled` | boolean | Whether it is enabled; disabled servers do not provide tools to the agent |
| `requires_approval` | boolean | Whether the asking user must approve in the chat before the agent calls this server's tools (see [2.9](#29-post-apichatapprovalsapproval_id)); `true` when omitted on create, and admins can turn it off per server |
| `status` | string | `connected`, `disconnected`, or `error` |
| `last_error` | string | Why the latest discovery failed |
| `discovered_tools` | array | Cached tools from the latest discovery (`name`, `description`, `inputSchema`); tools whose names do not match `[A-Za-z0-9_.-]{1,128}` are skipped |
| `discovered_resources` | array | Resources from the latest discovery (`uri`, `name`, `description`, `mimeType`), at most 200; items without a `uri` or with a `uri` longer than 2,048 characters are skipped |
| `discovered_prompts` | array | Prompts from the latest discovery (`name`, `description`, `arguments`), at most 200; prompts and arguments whose names do not match `[A-Za-z0-9_.-]{1,128}` are skipped |
| `oauth_authorized` | boolean | Responses only: whether OAuth tokens are stored (see [5.10](#510-post-apimcpserversserver_idoauthstart)) |
| `oauth_client` | object | The admin-entered OAuth client (`client_id`, `client_secret`, `scope`), with `client_secret` shown as `••••••••`; `null` when none was entered (or dynamic registration is used) |
| `timeout` | integer | Connect and call timeout in seconds, 30 by default |
| `created_at` / `updated_at` | string | Timestamps |
| `credentials_unreadable` | boolean | Responses only: `true` when `env_vars`, `headers`, or the OAuth settings cannot be decrypted with the current `TOOL_SECRETS_KEY`; the unreadable field is returned as `null` and must be entered again |

Resource and prompt descriptions are truncated to 500 characters; the lists are empty when the server does not declare the capability or listing fails (only the server log records it). The agent uses them through `read_mcp_resource` and `get_mcp_prompt` (see [2.3](#23-get-apichattools)): the tool descriptions list each server's items, at most 8,000 characters in total (`MAX_MCP_CATALOG_CHARS`), and servers that do not fit are left out with a warning in the log; only listed `uri` values and prompt names are accepted, and anything else is refused without contacting the server. Results are wrapped as untrusted like MCP tool results, and approval follows the server's `requires_approval`.

`env_vars` and `headers` are encrypted, masked, and updated like [custom API tool credentials](#tool-object): on update, keys whose value is still `••••••••` keep their stored value, and a masked key with no stored value returns `400`. While the credentials cannot be decrypted, the server cannot be connected to and its tools cannot be called until they are entered again; the discover and tool test endpoints return `400` `無法以目前的 TOOL_SECRETS_KEY 解密工具憑證，請重新輸入`.

**The `stdio` subprocess environment** inherits only essential system variables, plus `env_vars`: `APPDATA`, `HOMEDRIVE`, `HOMEPATH`, `LOCALAPPDATA`, `PATH`, `PATHEXT`, `PROCESSOR_ARCHITECTURE`, `SYSTEMDRIVE`, `SYSTEMROOT`, `TEMP`, `USERNAME`, and `USERPROFILE` on Windows; `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, and `USER` elsewhere. Settings from the backend `.env` are never passed on.

**`stdio` subprocess lifetime**: each subprocess runs in its own process group (a new process group on Windows, a new session elsewhere), and closing it terminates the whole tree, including grandchildren started by `npx` or `uvx` (`taskkill /T /F` on Windows; `SIGTERM`, then `SIGKILL`, to the group elsewhere). Every discovery or tool call starts a subprocess; at most 4 run at once and the rest wait, failing once they have waited the server's `timeout` seconds. Each subprocess runs in a fresh, empty temporary directory that is deleted afterwards, so relative paths do not reach `.env` or `keys/` in the backend directory; it still runs under the backend's system account and can read any file that account can. stderr is drained continuously and goes only to the server log, and a single JSON-RPC message line may be at most 4 MiB.

**HTTP servers** are SSRF-validated on every request and redirect, with the connection pinned to the validated IP, so servers on loopback or intranet addresses are rejected; use `stdio` for local MCP servers. The backend follows redirects itself, only within the same origin (same scheme, host, and port), at most 5, and never reads the body of a redirect response; a redirect to another origin aborts the request, so admin-configured headers and the JSON-RPC body never go to another domain. Each JSON-RPC request, redirects included, has an overall deadline of the server's `timeout` seconds. One response may be at most 4 MiB, and error messages no longer include the peer's response body.

**Legacy HTTP+SSE transport**: when Streamable HTTP `initialize` returns `400`, `404`, or `405`, the client opens an SSE stream with GET (`Accept: text/event-stream`), waits for the server's `endpoint` event, then POSTs JSON-RPC to that address and reads the responses from the SSE stream. The `endpoint` must be on the same origin as the SSE URL, or the connection is rejected; at most 4 MiB is read from the whole stream.

**OAuth tokens**: for an authorized server (see [5.10](#510-post-apimcpserversserver_idoauthstart)), HTTP requests carry `Authorization: Bearer <access token>`; within 60 seconds of expiry, or once when connecting gets `401`, the token is refreshed with the refresh token (sending `resource`). When discovery gets `401`, `last_error` says the server requires OAuth authorization.

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
| `oauth_client` | object | No (used for HTTP) | `null`; `client_id`, `client_secret`, `scope`. `client_id` is required when the authorization server does not support dynamic registration |

**Response**: `{"status": "success", "message": "MCP 伺服器建立成功", "server": {...}}`. If discovery fails, the server is still created with `status` `error`, and `last_error` records only an error code; an SSRF rejection also says the SSRF guard rejected it, and its full reason likewise goes only to the server log. A duplicate name returns `400` `已存在同名 MCP 伺服器: <name>`.

### 5.4 GET /api/mcp/servers/{server_id}

**Response**: `{"status": "success", "server": {...}}`; `404` `找不到該 MCP 伺服器` (server not found).

### 5.5 PUT /api/mcp/servers/{server_id}

Send only the fields you change (`name` cannot be changed). An `env_vars` or `headers` you send replaces the whole field; keys whose value is `••••••••` keep their stored value, and a masked key with no stored value returns `400`. The `client_secret` in `oauth_client` can likewise stay `••••••••`; changing `url` or the admin-entered client clears the stored OAuth tokens, sending the same client keeps them, and an empty `client_id` removes the admin-entered client. Updating does not rediscover tools; call 5.7 afterwards. **Response**: `{"status": "success", "message": "MCP 伺服器配置更新成功", "server": {...}}`.

### 5.6 DELETE /api/mcp/servers/{server_id}

**Response**: `{"status": "success", "message": "MCP 伺服器已成功刪除"}`

### 5.7 POST /api/mcp/servers/{server_id}/discover

Reconnect and rediscover tools, resources, and prompts; the results are written to `discovered_tools`, `discovered_resources`, and `discovered_prompts`. Tools whose names do not match `[A-Za-z0-9_.-]{1,128}` are skipped (only the server log records them): they appear neither in `tools` nor among the tools offered to the agent.

```json
{
  "status": "success",
  "message": "成功連線並探索到 1 項 MCP 工具、0 項 resource、0 項 prompt",
  "tools_count": 1,
  "tools": [{"name": "get_current_time", "description": "查詢指定時區或城市的當前精確時間", "inputSchema": {"type": "object", "properties": {"timezone": {"type": "string"}}}}],
  "resources": [],
  "prompts": [],
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
    "content": [{"type": "text", "text": "當前時間: 2026-09-25 10:00:00 CST"}]
  }
}
```

A failed call returns `result` as `{"is_success": false, "duration_seconds": ..., "error": "伺服器內部錯誤，請聯繫系統管理員並提供錯誤代碼（錯誤代碼：…）", "error_id": "…"}` ("internal server error; contact the administrator with the error code"); the full reason (such as the subprocess's stderr, a JSON-RPC error, or an SSRF rejection reason) goes only to the server log. The agent gets the same result when an MCP tool call fails.

### 5.10 POST /api/mcp/servers/{server_id}/oauth/start

Starts the authorization code flow of the MCP authorization specification (`2025-06-18`) for an HTTP / SSE server; no request body. `stdio` servers or servers without a `url` return `400`.

1. Sends `ping` to the server and reads `resource_metadata` from the `WWW-Authenticate` response header; without it, tries `/.well-known/oauth-protected-resource<path>` and then `/.well-known/oauth-protected-resource`.
2. Reads the authorization server metadata (RFC 8414 `/.well-known/oauth-authorization-server`, falling back to the OpenID Connect locations); without protected resource metadata, the MCP server's origin is treated as the authorization server. Metadata that lists `code_challenge_methods_supported` without `S256` is rejected.
3. Uses the admin-entered client in `oauth_client`; without one, gets a client through dynamic registration (RFC 7591, a public client with `token_endpoint_auth_method` `none`).
4. Creates PKCE (S256) and a single-use `state`, and returns the authorization URL, which carries `resource` (RFC 8707) and `scope` (the admin-entered scope, or `scopes_supported` when there is none).

**Response**: `{"status": "success", "authorization_url": "https://auth.example.com/authorize?..."}`, which the admin opens in the browser.

| Status | When |
|---|---|
| `400` | The authorization server has no registration endpoint and no `client_id` was entered: `授權伺服器不支援動態註冊，請在 MCP 伺服器設定中填入 OAuth client_id` ("the authorization server does not support dynamic registration; enter an OAuth client_id in the MCP server settings"); a URL rejected by the SSRF guard, or any other discovery failure (error code only) |
| `404` | `找不到該 MCP 伺服器` (server not found) |

The `redirect_uri` the authorization server sends the browser back to is `/api/mcp/oauth/callback`, built by the backend from this request's URL; behind a reverse proxy, the proxy must pass the scheme and host the client sees to the backend, or the redirect address will be wrong. OAuth endpoint requests are SSRF-validated, follow only same-origin redirects, and have a 15-second timeout and a 256 KiB response limit.

### 5.11 GET /api/mcp/oauth/callback

**Public**: where the authorization server sends the browser back. It needs no access token; the single-use `state` from 5.10 identifies the admin who started the authorization and the server. `state` is valid for 10 minutes and only once; it lives in the backend process's memory and is lost on restart, and with multiple workers the callback must reach the same process that handled 5.10 (for example with sticky routing).

**Query parameters**: `state` and `code` (or the `error` returned by the authorization server). The backend exchanges `code` for tokens with `code_verifier`, `redirect_uri`, and `resource`, stores them encrypted, writes the security event `ADMIN_MCP_OAUTH_AUTHORIZED`, and returns a short HTML page (`200`). An invalid or expired `state`, a missing `code`, or a failed exchange returns an HTML page with `400` (a failed exchange shows only an error code), and a deleted server returns `404`. Call 5.7 afterwards to rediscover.

### 5.12 DELETE /api/mcp/servers/{server_id}/oauth

Clears the stored OAuth tokens and keeps the OAuth client settings. **Response**: `{"status": "success", "message": "已清除 OAuth 授權", "server": {...}}`

---

## 6. Agent Skills `/api/skills`

Manages skills in the [Agent Skills](https://agentskills.io/specification) format. Skill files live in `SKILLS_DIR/<name>/`; the `agent_skills` table only keeps the parsed metadata and the enabled flag. Every endpoint except 6.1 requires **admin** permission.

The agent uses skills through progressive disclosure: when at least one enabled skill has its files present, [`GET /api/chat/tools`](#23-get-apichattools) gains two built-in tools, `activate_skill` (its description lists each skill's name and description) and `read_skill_resource`. Only when the model calls `activate_skill` does it receive the `SKILL.md` body (frontmatter stripped, wrapped in `<skill_content>`) and the list of files in the skill; it then reads single UTF-8 text files with `read_skill_resource` as needed. Skill content is admin-installed instructions and is not wrapped in `<untrusted_tool_result>`, but it cannot override the system prompt's data-safety and citation rules. Neither skill tool requires approval.

**Running scripts**: scripts in a skill are not executed by default. After an admin turns on the skill's `allow_scripts` with [6.7](#67-patch-apiskillsskill_idsettings), the agent gets `run_skill_script` (parameters `skill`, `path`, `args`, `stdin`), and every run needs the asking user's approval (see [2.9](#29-post-apichatapprovalsapproval_id)). Only `.py` (the backend's Python, run with `-I`), `.sh` (`bash`), and `.js` and `.mjs` (`node`) are run; other extensions, or a missing interpreter on the host, are refused. Scripts run in a temporary copy of the skill directory (so the installed skill cannot be modified), with the same environment as `stdio` MCP subprocesses (backend settings and keys are not passed), and the whole process group is killed on timeout. The result has `exit_code`, `timed_out`, `duration_seconds`, `stdout`, `stderr`, and `output_truncated`, and is wrapped as untrusted like external tool results; see [configuration reference: resource limits](configuration_en.md#resource-limits) for the time, output, and argument limits. This is **not a sandbox**: scripts run as the backend's OS account, can read any file that account can read, and can reach the network, so enable it only for trusted skills.

### Skill object

| Field | Type | Description |
|---|---|---|
| `id` | integer | Skill ID |
| `name` | string | Skill name (from `name` in `SKILL.md`); also the directory name and the `/skill-name` command |
| `description` | string | When to use the skill; listed in the `activate_skill` tool description |
| `license` / `compatibility` / `allowed_tools` | string | Optional `SKILL.md` fields; once the skill is activated in a question (the model calls `activate_skill` or the message starts with `/skill-name`), each space-separated tool name in `allowed_tools` (the part before any `(`) no longer asks for approval for the rest of that question |
| `allow_scripts` | boolean | Whether `run_skill_script` may run this skill's scripts; `false` by default |
| `allowed_user_ids` | array \| null | Account ids that may use this skill; `null` means every user, and an empty array means nobody (for example when every listed account was deleted) |
| `metadata` | object | `metadata` from `SKILL.md`, values converted to strings |
| `warnings` | array | Problems found while parsing that did not prevent loading |
| `is_enabled` | boolean | Whether the skill is offered to the agent |
| `files_present` | boolean | Whether `SKILLS_DIR/<name>/SKILL.md` exists; skills without it are not offered to the agent |
| `created_at` / `updated_at` | string | Timestamps |

### 6.1 GET /api/skills/enabled

Sign-in required. Lists enabled skills whose files exist and that the caller may use (`allowed_user_ids` is `null` or contains the caller), for the `/` skill suggestions in the chat input. Skills restricted to other accounts are also missing from the caller's agent tools, and activating, reading, or running them is refused.

**Response**: `{"status": "success", "skills": [{"name": "meeting-minutes", "description": "…"}]}`

### 6.2 GET /api/skills

**Response**: `{"status": "success", "total": 1, "skills": [skill object, ...]}`, sorted by name.

### 6.3 GET /api/skills/{skill_id}

**Response**: `{"status": "success", "skill": {...}}`: the skill object plus `body` (the `SKILL.md` body, or `null` with `load_error` when it cannot be read; `load_error` is a fixed message with an error code, and the full reason goes only to the server log), `resources` (relative paths of the files other than `SKILL.md`, at most 100), and `resources_truncated`. Returns `404` `找不到該技能` when not found.

### 6.4 POST /api/skills/upload

`multipart/form-data` with a `file` field: a `.zip` of the skill directory (`SKILL.md` at the root or inside the single top-level directory; the `.skill` extension is treated as zip) or a single `SKILL.md`, at most 10 MiB. **Query parameter**: `replace` (default `false`); when `true`, the whole directory of a skill with the same name is replaced.

`name` must follow the specification (lowercase letters, digits and hyphens, at most 64 characters, no leading, trailing or consecutive hyphens) and `description` is required. The archive may not contain absolute paths, `..`, drive letters or symbolic links, and may hold at most 500 files and 50 MiB uncompressed; `SKILL.md` is at most 256 KiB. A `name` that differs from the top-level directory, fields longer than the specification allows, unknown frontmatter fields and similar problems go into `warnings` and the skill is installed anyway.

**Response**: `{"status": "success", "message": "已安裝技能「meeting-minutes」", "skill": skill object}`. Invalid skills return `400` with the reason; when a skill with the same name exists and `replace` is `false`, it returns `409` `已存在同名技能：<name>`.

### 6.5 PATCH /api/skills/{skill_id}/toggle

**Response**: `{"status": "success", "is_enabled": false, "message": "技能已停用"}`

### 6.6 DELETE /api/skills/{skill_id}

Deletes the database row and the skill directory. **Response**: `{"status": "success", "message": "已刪除技能「meeting-minutes」"}`

### 6.7 PATCH /api/skills/{skill_id}/settings

Sets script execution and which accounts may use the skill; send only the fields you change.

| Field | Type | Description |
|---|---|---|
| `allow_scripts` | boolean | Whether scripts may run (see "Running scripts" above) |
| `allowed_user_ids` | array | Account ids that may use the skill; an empty array means every user (stored as `null`) |

**Response**: `{"status": "success", "message": "技能設定已更新", "skill": skill object}`; ids of accounts that do not exist return `400` `找不到使用者：<id>` ("user not found"). Success writes the security event `ADMIN_SKILL_SETTINGS_UPDATED`. Deleting an account removes it from every skill's `allowed_user_ids`; a skill whose list becomes empty this way is usable by nobody, not by everyone.

---

## 7. Model lists `/api/tags`

A model list in the Ollama `tags` format; no sign-in is required. The former `GET /api/external-tags` has been removed.

### 7.1 GET /api/tags

Returns the same list and default model as `GET /api/chat/models` (both share one rule; see [Configuration: model list](configuration_en.md#model-list)), under the field `tags`. With no model source configured (`AVAILABLE_MODELS` or a cloud key), it queries the remote list at `EXTERNAL_TAGS_URL` (or `{LLM_API_BASE}/api/tags`) and returns an empty list if that fails. The remote query runs in a worker thread, its result (failures included) is cached for 30 seconds, and only one query runs at a time, so anonymous requests do not trigger an outbound call each time.

```json
{"tags": ["gpt-6-sol", "gpt-6-luna"], "default": "gpt-6-sol"}
```

---

## 8. Admin `/api/admin`

> Every endpoint in this module requires **admin** access.

### 8.1 User management

| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/users` | All users, each as a `UserProfile` (`id`, `username`, `email`, `role`, `is_active`, `is_admin`, `created_at`, `last_login`) without `hashed_password` |
| PUT | `/api/admin/users/{user_id}` | Update `username`, `email`, `is_active`, or `is_admin` (send only what changes); duplicate names or emails return `400` (`使用者名稱已存在`, `電子郵件已存在`) |
| DELETE | `/api/admin/users/{user_id}` | Delete a user and all their conversations; documents they uploaded and tools they created stay, with the creator field set to null; the account is removed from skills' `allowed_user_ids` (see [6.7](#67-patch-apiskillsskill_idsettings)) |

`PUT` returns `{"message": "使用者更新成功", "user": {...}}`, where `user` is the updated `UserProfile`, and `DELETE` returns `{"message": "使用者刪除成功"}`. Both return `404` `使用者不存在` (user not found) for an unknown user and clear the statistics cache on success. Deactivation, deletion, and removal of admin rights apply from the next request: tokens already issued to a deactivated or deleted account stop working and the account can no longer sign in, and an account that lost admin rights gets `403` from admin endpoints.

Account changes and deletions are written to the security log along with the acting admin: `PUT` writes `ADMIN_USER_UPDATED` when something actually changed (the target account id and the before and after values of `username`, `email`, `is_active`, and `is_admin`), and `DELETE` writes `ADMIN_USER_DELETED` (the target account id, the username, and whether it was an admin).

### 8.2 Statistics

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

### 8.3 Conversations and documents

| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/conversations` | The 50 most recently updated conversations system-wide |
| GET | `/api/admin/conversations/{conversation_id}/messages` | All messages of any conversation, oldest first; the table is serialized directly, including the raw `context_used` |
| DELETE | `/api/admin/conversations/{conversation_id}` | Delete any conversation and its messages |
| GET | `/api/admin/documents` | All documents, newest first, with the same fields as `GET /api/documents/` and no full text |
| DELETE | `/api/admin/documents/{document_id}` | Same as `DELETE /api/documents/{document_id}`: deletes the record, its chunks and indexes, and the uploaded file |

### 8.4 Retrieval and index maintenance

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

## 9. Health checks

| Method | Path | Response |
|---|---|---|
| GET | `/` | `{"message": "ChatBot API is running"}` |
| GET | `/health` | `{"status": "healthy"}` |

The interactive docs `/docs` and `/redoc` and the OpenAPI document `/openapi.json` are served only with `ENABLE_API_DOCS=true` (no sign-in needed); with `false` all three return `404`.

---

## 10. Error handling

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
| `400` | Bad request content: duplicate names, spec parsing failures (including YAML aliases), URLs rejected by SSRF validation, password rules not met, unsupported model, or `••••••••` sent back with no stored value when updating a tool or MCP server |
| `401` | Missing or invalid access token (`Not authenticated`, `認證權杖無效：驗證失敗` "token verification failed", `權杖已被撤銷` "token revoked"; a deleted or deactivated account, or a token issued before a password change, also gets `認證權杖無效：驗證失敗`) or a failed sign-in |
| `403` | Insufficient permission (`需要管理員權限`), or a registration request with `ALLOW_REGISTRATION=false` (`目前不開放註冊，請聯繫管理員建立帳號`) |
| `404` | The resource (conversation, document, tool, MCP server, user, pending tool call) does not exist, or `/docs`, `/redoc`, and `/openapi.json` with `ENABLE_API_DOCS=false` |
| `413` | The request body exceeds its limit, or the user's attachment storage is full |
| `422` | Field validation failed (including length, count, and size limits) |
| `429` | Rate limit exceeded (the response includes a `Retry-After` header), logins paused for a login identifier or source IP after too many failures (`登入失敗次數過多，請稍後再試`, with `Retry-After` set to the remaining seconds; this applies during the pause even with the right password), or the same user has more than 2 answers streaming |
| `500` | Unexpected exception; only an error code is returned |

Custom API tool results (from the [4.9](#49-post-apiapi-toolstool_idtest) test endpoint and the agent's tool results) carry their own `status_code` field: once the request is sent, it is the upstream status; when the backend stops the call itself, `error` is included and the status is `400` (invalid parameters), `403` (SSRF rejection), `500` (unexpected exception), `502` (upstream response over 1 MiB), or `504` (the tool's overall deadline passed). These are not HTTP statuses of the API itself; the test endpoint still returns `200`.

### Security response headers

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy: geolocation=(), microphone=(), camera=()`, and the `Server` header is removed.

---

## 11. Known limitations

The current state, worth knowing when integrating:

- `GET /api/chat/models` and `GET /api/tags` require no sign-in (`GET /api/chat/tools` now does). Restrict them at the reverse proxy when deploying on a public network.
- `expires_in` in token responses is always `1800`, regardless of `ACCESS_TOKEN_EXPIRE_MINUTES`.
- The token revocation list, rate limit counters, login throttling counts and pauses, per-user concurrent streams, and pending tool approvals live in one backend process's memory; they are not shared across processes or hosts and are cleared on restart (which also lifts any login pause). Rate limiting tracks at most 10,000 source IPs and evicts the least recently active first; login throttling likewise tracks at most 10,000 login identifiers and 10,000 source IPs and evicts those that have gone longest without a new failure first.
- Rate limiting and login throttling both work per source IP: without `FORWARDED_ALLOW_IPS`, every user who connects through the Vite dev proxy or a reverse proxy shares one source IP, so they share the rate limit and their failed logins add up toward the per-address threshold; once it is reached, every login through that proxy is paused.
- Attachment storage is never purged automatically: once a user reaches the 200 MiB limit, they must delete conversations with attachments before sending attachments again.
