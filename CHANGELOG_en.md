# Changelog

[繁體中文](CHANGELOG.md) | [English](CHANGELOG_en.md)

All notable changes to AskMiao are documented in this file. The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html): incompatible changes bump the major version, backward-compatible features bump the minor version, and bug fixes bump the patch version.

| Version | Release date | Highlights |
|---|---|---|
| [4.0.0](#400---2026-09-27) | 2026-09-27 | Security audit fixes: tokens bound to database accounts, user approval for tool calls, IP-pinned outbound connections, resource limits |
| [3.0.0](#300---2026-09-25) | 2026-09-25 | chunk_id index, RRF with a relevance threshold, answer citations, tool trust boundary and admin-only tool management, frontend UI/UX overhaul |
| [2.2.1](#221---2026-09-19) | 2026-09-19 | Error responses use error codes |
| [2.2.0](#220---2026-09-01) | 2026-09-01 | Centralized SSRF protection |
| [2.1.0](#210---2026-08-27) | 2026-08-27 | Custom API tools, OpenAPI import, and MCP integration |
| [2.0.1](#201---2026-08-26) | 2026-08-26 | Multimodal chat and AI document summaries |
| [2.0.0](#200---2026-08-24) | 2026-08-24 | Agentic RAG autonomous research |
| [1.0.0](#100---2026-08-01) | 2026-08-01 | Hybrid RAG and security foundations |

> [!TIP]
> Upgrading from 3.0.0 to 4.0.0? Read the [upgrade guide](docs/upgrading_en.md#upgrading-from-300-to-400) first: RSA keys are now mandatory, compose needs `POSTGRES_PASSWORD`, and the dev server only accepts local connections. Coming from 2.x, first follow [upgrading to 3.0.0](docs/upgrading_en.md#upgrading-from-2x-to-300).

---

## [Unreleased]

This release addresses the findings of a second security audit: chat attachment parsing has a memory budget, failed logins pause the account or source address, a password change revokes every token, self-registration can be turned off, tool credentials are encrypted at rest and no longer readable through the admin API, custom API tools accept only declared parameters, dependencies are pinned by hash, and PostgreSQL is accessed as a non-superuser.

> [!WARNING]
> **This release requires manual changes.** Before upgrading, work through the [upgrade guide](docs/upgrading_en.md#upgrading-from-400-to-the-unreleased-version):
>
> - `.env` has 10 new required settings: `ALLOW_REGISTRATION`, `LOGIN_MAX_FAILURES_PER_ACCOUNT`, `LOGIN_MAX_FAILURES_PER_ADDRESS`, `LOGIN_FAILURE_WINDOW_SECONDS`, `LOGIN_LOCKOUT_SECONDS`, `TOOL_SECRETS_KEY`, `HOST`, `RELOAD`, `COOKIE_SECURE`, and `ENABLE_API_DOCS`. The backend does not start if any is missing, and `TOOL_SECRETS_KEY` must be a Fernet key generated for each deployment.
> - `HOST` and `RELOAD` no longer default to `0.0.0.0` and `true`, and `COOKIE_SECURE` is no longer derived from `ENVIRONMENT`; `/docs`, `/redoc`, and `/openapi.json` are served only with `ENABLE_API_DOCS=true`.
> - With `backend/docker-compose.yml`, `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD` are required and `DATABASE_URL` must use that non-superuser account; existing data volumes need a one-time run of `20-app-role.sh`.
> - Tool parameters not declared in `parameters_schema` return `400`; `GET /api/external-tags` and the WebSocket `/api/chat/ws/{user_id}` are removed; the `POST /api/api-tools/parse-spec` response no longer includes `raw_spec`.
> - To add or upgrade a backend package, edit `requirements.in` and regenerate `requirements.txt`; `bun install` fails when `bun.lock` and `package.json` disagree.
> - After a password change, every session, including the current one, must sign in again with the new password.

### Security

#### Authentication and accounts

- **Login failure throttling**: once one login identifier (case-insensitive) or one source address reaches its failure threshold within `LOGIN_FAILURE_WINDOW_SECONDS`, logins for that identifier or address pause for `LOGIN_LOCKOUT_SECONDS` with `429` and `Retry-After`. Unknown accounts are counted too, the right password is not accepted during a lockout, and the response does not reveal whether the password was correct (CWE-307).
- **A password change revokes every token**: `users` gains `tokens_valid_after`, which is set to the current time on a password change; access and refresh tokens issued before it are rejected, so a stolen refresh token cannot keep renewing after the victim changes their password. `POST /api/auth/change-password` and a `PUT /api/auth/me` that sets a new password clear the refresh token cookie (CWE-613).
- **Self-registration can be turned off**: with the new required `ALLOW_REGISTRATION` set to false, `POST /api/auth/register` returns `403` and writes a security log entry, and accounts (including the first admin) are created with `scripts/create_user.py`. Previously anyone who could reach the API could register, query the whole knowledge base, and call the enabled tools with the operator's credentials (CWE-284).
- **The admin user API no longer returns password hashes**: `GET /api/admin/users` and `PUT /api/admin/users/{user_id}` filter fields through `UserProfile`, so responses no longer contain `hashed_password` (CWE-200).
- **Logout works with an expired access token**: `POST /api/auth/logout` verifies only the access token's signature, so it still revokes the refresh token and clears the cookie after the access token expires; the `Authorization` header is still required, so a cross-site form cannot trigger a logout (CWE-613).
- Admin changes to an account's role or status and account deletions are written to the security log (`ADMIN_USER_UPDATED`, `ADMIN_USER_DELETED`) with the acting admin and the changes (CWE-778).
- The JWT private key is created with mode `0600` from the start instead of being written with default permissions and changed afterwards; a newly created `backend/keys/` is `0700` (CWE-276).

#### Deployment and dependencies

- **PostgreSQL is accessed as a non-superuser**: `docker-compose.yml` requires `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD`, and `backend/init-app-role.sh` runs after `init.sql` to create the account, grant `USAGE` and `CREATE` on the `public` schema, and hand it ownership of existing tables. A SQL injection can no longer run system commands with `COPY ... TO PROGRAM` or read server files (CWE-250).
- **Insecure defaults are now required settings**: `HOST`, `RELOAD`, and `COOKIE_SECURE` no longer default to listening on all interfaces, auto-reloading, or deriving Secure from `ENVIRONMENT`; the new required `ENABLE_API_DOCS` turns off the interactive documentation that lists every endpoint and parameter (CWE-1188).
- **Dependencies are pinned by hash**: `backend/requirements.in` lists only direct dependencies, and `requirements.txt` is generated with `uv pip compile --universal --generate-hashes` and verified on install; `frontend/bun.lock` is committed and `frozenLockfile = true`. Previously neither side pinned versions, so every install took the newest release available at the time (CWE-1357, CWE-494).
- Removed `GET /api/external-tags`, which needed no login, was not cached, and relayed upstream JSON as is, and the WebSocket `/api/chat/ws/{user_id}`, which needed no authentication and bypassed rate limiting; the frontend used neither (CWE-306).
- The larger upload body limit applies only to requests whose token carries `is_admin`, so regular users cannot make the backend parse a multipart body of about 500 MiB; the rate limiter tracks a bounded number of addresses and evicts the least recently active first (CWE-770).

#### Tool credentials and outbound requests

- **Tool credentials are encrypted at rest**: custom API tools' `headers` and `auth_config` and MCP servers' `env_vars` and `headers` are encrypted with `TOOL_SECRETS_KEY` (Fernet) before they reach the database, and existing plaintext rows are encrypted at startup. Admin API responses show `••••••••` in place of secret values, and fields sent back masked keep their stored value on update. They used to be stored in plaintext and returned as is (CWE-312, CWE-522).
- **Custom API tools accept only declared parameters**: parameters must be declared in `parameters_schema`, and body fields are checked too when `request_body` has a schema with declared properties. Query parameters in the tool URL are fixed by the admin, and a call that supplies a parameter with the same name is rejected. Previously every key from the model was sent, and on httpx 0.28 any query parameter replaced the fixed parameters in the URL entirely (CWE-20, CWE-915).
- **Redirects are followed manually**: custom API tools and HTTP MCP never read the body of a redirect response, and the whole call has a deadline (`504`); HTTP MCP follows only same-origin redirects, so admin-configured headers and the JSON-RPC body are never sent to another domain (CWE-200, CWE-400).
- **MCP subprocesses and errors**: stdio subprocesses run in a fresh empty temporary directory, waiting for a free slot has a timeout, stderr is drained continuously, and a single message line is capped at 4 MiB; only tools whose names match `[A-Za-z0-9_.-]{1,128}` are kept; tool failures return only an error ID, and startup failures no longer include the command's arguments (CWE-400, CWE-209).
- User-supplied URLs (`web_fetch`) and admin-configured endpoints use separate DNS thread pools, so a slow domain cannot stall the SSRF checks for tools and spec imports; the SSRF deny list explicitly covers 6to4 (`2002::/16`) and NAT64 local-use (`64:ff9b:1::/48`) (CWE-400, CWE-918).
- Fixed query parameter values in a tool URL (which may be keys written into the URL) no longer appear in URLs returned to the model and the user; the `approval_required` event gains `target`, which names where the request is actually sent (CWE-200).
- OpenAPI specs with YAML aliases are rejected, and the parse result no longer carries the whole raw spec (CWE-776).

#### Resource limits

- **A parsing budget for chat attachments**: admin uploads and chat attachments each use their own `ExtractionLimits`. For chat attachments, the XML parts of a docx or pptx that are built into a DOM, counted from `[Content_Types].xml` so renaming does not bypass the check, are capped at 8 MiB; the total uncompressed size is capped at 64 MiB and the member count at 10,000, and the compression ratio is checked for the whole file as well as for each member. JSON and code over 2,000,000 characters are not passed to `json.loads`. At most 2 attachments are parsed at a time per process, and an attachment over budget is reported to the model as unread (CWE-409, CWE-400).
- The separator pattern in `split_structured_records` now runs in linear time (CWE-1333).

#### Frontend

- **The build ships a CSP**: `bun run build` writes a CSP `<meta>` tag into `index.html` that allows only the built scripts and the hashes of the inline scripts in `index.html`, adds the API origin from `VITE_API_BASE`/`VITE_API_URL` to `connect-src`, and allows images only from the same origin, `data:`, and `blob:`. Even when the web server sets no CSP, injected HTML cannot run scripts (CWE-79).
- **The tool approval card shows everything**: it lists where the request is sent and every parameter, no longer inside a scrolling box, and marks control and format characters (bidirectional controls, zero-width characters, Unicode tag characters, and so on) as `⟦U+…⟧` (CWE-451).
- **External links show the real site**: whether a link is external is decided from the resolved URL; external links open in a new tab and name the actual host, a Markdown `title` cannot replace the URL hint, and external links no longer get the in-app action button style (CWE-451).
- Failed requests log only the status code and error message to the console, not the axios error object with passwords, API keys, and access tokens (CWE-532).
- When the logout request fails, the login page says so: the server did not revoke the refresh token, and the httpOnly cookie holding it can still obtain access tokens until it expires (CWE-613).
- Research trace arguments and output previews are always rendered as text, so an object from the model no longer crashes the conversation page (the trace is stored in the database, so the page used to crash every time the conversation was opened); the post author field no longer uses a pattern that backtracks in quadratic time on a long run of dots (CWE-1333).

### Added

- Required settings `ALLOW_REGISTRATION`, `LOGIN_MAX_FAILURES_PER_ACCOUNT`, `LOGIN_MAX_FAILURES_PER_ADDRESS`, `LOGIN_FAILURE_WINDOW_SECONDS`, `LOGIN_LOCKOUT_SECONDS`, `TOOL_SECRETS_KEY`, `HOST`, `RELOAD`, `COOKIE_SECURE`, and `ENABLE_API_DOCS`; `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD` in `docker-compose.yml`.
- `GET /api/auth/registration` reports whether self-registration is open; the frontend uses it to hide the sign-up link on the login page and shows an explanation on the sign-up page.
- `backend/scripts/create_user.py` creates an account with an interactively entered password, applying the same rules as registration; `--admin` creates an admin.
- `backend/init-app-role.sh` (the PostgreSQL application account, safe to rerun), `backend/requirements.in`, and `frontend/bun.lock`.
- Tool and MCP server responses from the admin API gain `credentials_unreadable`, so credentials that cannot be decrypted with the current key can be re-entered instead of breaking the page.
- New backend tests `test_admin_user_api.py`, `test_login_throttle.py`, `test_registration.py`, and `test_tool_secrets.py`.
- **"Tool approval" section on the website**: an interactive approval card (approve, deny, simulate a timeout) that shows the resulting SSE events such as `approval_required` and `approval_resolved`, plus a switch between HTTP methods that shows a custom API tool's default approval rule, matching `tool_approval.py`.
- The website gains a 4.0.0 release pill and stats row, a "Every entry point has a limit" resource-limit table in the security section, and ADR-0006 in the documentation list.
- The README gains "What's new in 4.0.0", "Tool call approval", "Threat coverage", and "Key resource limits" sections, and two troubleshooting entries on approval timeouts and read-only tools asking for approval.

### Changed

- A password change also signs out the current session; the frontend clears the sign-in state and returns to the login page.
- Custom API tools that declare no parameters no longer accept any; the `POST /api/api-tools/parse-spec` response no longer includes `raw_spec`.
- Tool and MCP credentials in admin API responses are shown as `••••••••`; ordinary headers such as `Accept` and `Content-Type` and settings such as `key_name` and `username` are shown as before. After changing `TOOL_SECRETS_KEY`, stored credentials must be entered again.
- Intrusion detection now only raises alerts; `RateLimitMiddleware` no longer has a blocking branch that returns `403`.
- `backend/.env.example` adds the required settings above and its `DATABASE_URL` example uses `askmiao_app`; `frontend/.env.example` notes that `VITE_API_BASE` is written into the CSP `connect-src`.

### Removed

- `GET /api/external-tags` and the WebSocket `/api/chat/ws/{user_id}`.
- The intrusion detection IP blocklist, which was never populated.
- The unused `app/core/secret_manager.py`, which silently fell back to a random key when its key was missing, and the unused `reject_unsafe_request`, which did not pin the connection IP.
- Backend packages no code used: FlagEmbedding, waitress, docxtpl, XlsxWriter, PyJWT, langchain, and langchain-community.

### Fixed

- Installing from `requirements.txt` paired an old datasets release pulled in by FlagEmbedding with a new pyarrow, so sentence-transformers failed to import; pydantic-settings, PyYAML, and lxml, previously installed only as transitive dependencies, are now direct dependencies.
- `cache = "~/.bun/install/cache"` in `bunfig.toml` did not expand `~` and created a cache directory literally named `~` under `frontend/`, whose third-party tests vitest then picked up.
- The website's web_fetch inspector now matches URL provenance on the full normalized URL, as `research_session.py` does; it used to match a decoded substring, which counted fragments of a URL as having appeared.
- The website no longer mentions the removed `JWT_SECRET_KEY` (quick start, required settings, and the subprocess environment table) and explains RSA keys, `POSTGRES_PASSWORD`, and the local-only dev server instead; the security notes now cover IP pinning and tokens resolved to database accounts.

---

## [4.0.0] - 2026-09-27

This release addresses the 52 leads from a security audit: tokens are mapped to the database account on every request, tool calls with side effects need the user's approval, outbound connections are pinned to the SSRF-validated IP, and request bodies, attachments, tool results, concurrent streams, and other resources are capped.

> [!WARNING]
> **This release needs manual steps**; go through the [upgrade guide](docs/upgrading_en.md#upgrading-from-300-to-400) before upgrading:
>
> - `JWT_SECRET_KEY` and `JWT_ALGORITHM` are gone; the RSA keys in `backend/keys/` are required in every environment, and the backend refuses to start if they cannot be loaded or generated.
> - `backend/docker-compose.yml` requires `POSTGRES_PASSWORD` and binds `127.0.0.1:7690` only; the password of an existing data volume must be changed separately.
> - The Vite dev and preview servers listen on `localhost` only; LAN devices need a production build behind a real web server.
> - `/api/chat` message responses no longer include the raw `context_used` (always `null`); `GET /api/chat/tools` requires sign-in; `model_name` must be in the available model list.
> - Custom API tools and MCP servers gain `requires_approval` (added and backfilled at startup), so calls to existing MCP servers' tools now ask the user for approval first.

### Security

#### Authentication

- **HS256 fallback removed**: development setups no longer sign tokens with the shared secret from `.env` when the RSA keys cannot load; the keys must be usable in every environment, or the backend refuses to start (CWE-1188).
- **Tokens bound to the database account**: every request loads the account by `sub`; it must exist and be active, `is_admin` and the role come from the database rather than the token, and tokens issued before the account was created (a deleted account's id reused) are rejected, so deactivation, deletion, and demotion apply immediately (CWE-613, CWE-285). New SQLite databases create `users` and `documents` with `AUTOINCREMENT`, so ids are never reused.
- **Single-use refresh tokens**: the old token is revoked as soon as a new pair is issued (CWE-294).
- Passwords are capped at 256 characters and login identifiers at 254; Argon2 hashing and verification run in worker threads, at most 4 at once; the revocation list holds at most 100,000 entries (CWE-400).

#### Deployment

- **No built-in PostgreSQL password**: `POSTGRES_PASSWORD` is required, and the port binds `127.0.0.1:7690` only (CWE-798, CWE-1327).
- **Client-supplied `X-Forwarded-For` is not trusted**: `python main.py` turns uvicorn's `proxy_headers` off by default, so rate limiting and the block list use the direct peer; only reverse proxies named in the new `FORWARDED_ALLOW_IPS` setting are trusted (CWE-348).
- **Vite dev server for this machine only**: the dev and preview servers listen on `localhost` only, and `/__open-in-editor` answers loopback clients only (CWE-1327); both send `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'; img-src 'self' data: blob:`, and `index.html` adds an anti-framing style guard (CWE-1021).

#### Tools and outbound requests

- **Approval before calls**: custom API and MCP tools with side effects run only after the asking user approves in the chat; see Added below (CWE-862).
- **SSRF validation pins the connection IP**: custom API tools, the MCP HTTP transport, and `safe_fetch_text` pin every hop to the approved IP after validation, so DNS rebinding cannot change the target between validation and connection; DNS lookups run in a dedicated 4-thread pool with a 5-second timeout (CWE-918, CWE-367).
- **Custom API tools**: path parameters are percent-encoded and the host after substitution must match the configured one; cross-origin redirects drop the admin-configured headers and auth header; credential values in results and URLs are masked as `[已遮蔽]`; response bodies are capped at 1 MiB (CWE-918, CWE-522, CWE-200, CWE-400).
- **SSRF rejections return only an error code**: custom API tools, `web_fetch`, and `POST /api/api-tools/parse-spec` no longer return reasons that may contain intranet IPs; MCP HTTP errors no longer include the peer's response body, and one response is capped at 4 MiB (CWE-209, CWE-400).
- **Stricter `web_fetch` URL provenance**: only URLs that appeared as a whole URL count, both sides are normalized by httpx and compared exactly, and the matched URL is what gets fetched (CWE-918).
- **MCP presets**: `mcp_fetch`, which bypassed `web_fetch`'s outbound protections, is removed; `mcp_filesystem` is rooted at the dedicated `backend/mcp_filesystem_sandbox` (instead of `./data`, which holds pickled index metadata) and pins `@modelcontextprotocol/server-filesystem@2026.8.31` (CWE-918, CWE-552, CWE-829).
- **MCP subprocesses**: each runs in its own process group, closing it terminates the whole tree, and at most 4 run at once (CWE-404, CWE-400).
- **Chat attachments accept base64 `data:` URLs only**, so remote URLs are no longer handed to model providers to fetch (CWE-918); Markdown images in answers become links that open only when clicked instead of loading from external hosts automatically (CWE-201).
- The `httpx` and `httpcore` loggers are pinned to `WARNING`, so full URLs with query-string keys are no longer logged (CWE-532).

#### Resource limits

- New `RequestBodyLimitMiddleware`: request bodies are capped at 1 MiB, raised for chat sends and document uploads only with a valid access token; larger bodies get `413` (CWE-770).
- Chat messages are capped at 20,000 characters and 5 attachments (15 MiB each, 20 MiB in total), and attachment text and tool results are truncated before reaching the model; each user may store 200 MiB of attachments (`413`) and run 2 answer streams at once (`429`); PDF chat attachments are OCR'd for at most 20 pages at no more than 25 MP per page; waiting for the LLM connection pool is capped at 15 seconds (CWE-400, CWE-770).
- OOXML files have their uncompressed size and compression ratio checked before parsing (CWE-409); HTML extraction, SVG stripping, JSON declaration extraction, Q&A splitting, and table-of-contents cleanup run in linear time, and `filter_and_count_records` limits its date range and result count (CWE-1333).
- The conversation list returns at most 200 conversations with 5 preview messages each and no attachment bodies; one conversation returns at most its latest 500 messages; the remote model list is cached for 30 seconds and queried in a worker thread (CWE-400).
- Security log fields are capped at 200 characters, `app.log` and `security.log` rotate at 10 MiB × 5 files, and security events are no longer duplicated into `app.log`; the intrusion detector bounds its events and tracked addresses (CWE-779, CWE-400).

#### Other

- **`send` only accepts listed models**, so nobody can call an unlisted model with the operator's keys (CWE-770); `GET /api/chat/tools` now requires sign-in (CWE-200).
- The jieba dictionary cache moved to `DATA_DIR/jieba_cache` (mode `0700`) instead of a predictable file name in the system temp directory (CWE-377).
- **MCP SSRF rejections no longer echo resolution results**: when the SSRF guard rejects the URL while creating or discovering an MCP server, `last_error` and the 400 response now say it was rejected and carry an error code; the full reason, which can include private IPs from server-side DNS resolution or redirect targets, goes only to the server log (CWE-209).
- **Intro page RRF demo escapes chunk IDs**: `site/main.js` now passes chunk IDs and reranker probabilities from the embedded JSON through `escapeHtml` before inserting them into HTML, so quotes or angle brackets in the data are no longer parsed as markup (CWE-79).

### Added

- **Tool call approval**: custom API tools and MCP servers gain `requires_approval` (API tools default by HTTP method, `true` for anything other than `GET`, `HEAD`, and `OPTIONS`; MCP servers default to `true`). When the agent calls such a tool it sends the SSE event `approval_required` and pauses; once the user answers through `POST /api/chat/approvals/{approval_id}`, it sends `approval_resolved`. Only the asking user can answer, and nothing runs after a 300-second timeout or without an approver. The frontend shows a confirmation card in the answer, and the AI tools page forms gain a matching checkbox. See [ADR-0006](docs/adr/0006-tool-call-approval_en.md).
- `FORWARDED_ALLOW_IPS` setting: names reverse proxies that overwrite `X-Forwarded-For`, so rate limiting counts real client IPs.
- `backend/app/core/limits.py` defines the resource limits in one place, documented in a new "Resource limits" section of the [configuration reference](docs/configuration_en.md#resource-limits).
- `upgrade_schema()`: adds new columns to existing tables and backfills them at startup (and in `init_db.py`).
- When sending a message fails with a `422` validation error, the frontend shows each reason (for example an oversized attachment).
- New [ADR-0006](docs/adr/0006-tool-call-approval_en.md) and follow-up amendments to ADR-0004; the [upgrade guide](docs/upgrading_en.md#upgrading-from-300-to-400) covers this release.
- New backend tests `test_auth_token_binding.py`, `test_outbound_tool_security.py`, `test_process_hardening.py`, `test_resource_limits.py`, and `test_tool_approval.py`.

### Changed

- `/api/chat` message responses no longer include the raw `context_used` (always `null`); the parsed `sources`, `sources_detail`, `research_trace`, and `attachments` carry the data, and attachments in the conversation list have no `data_url`.
- During a chat stream the database connection goes back to the pool, and database access plus attachment decoding and parsing run in worker threads; conversation read routes are now sync functions run in the thread pool.
- Custom API tools, the MCP HTTP transport, and `web_fetch`'s direct fetches no longer use the `HTTP_PROXY` and `HTTPS_PROXY` environment variables.
- PDF OCR rasterizes pages one at a time on the document's thread, with only the vision calls in parallel; XLSX files are opened read-only.
- Deleting a document removes its database record before its index chunks, and index writes skip chunks whose document was deleted after taking the lock.
- `backend/.env.example`: `JWT_SECRET_KEY` and `JWT_ALGORITHM` removed; `POSTGRES_PASSWORD` and `FORWARDED_ALLOW_IPS` examples added.

### Removed

- The `JWT_SECRET_KEY` and `JWT_ALGORITHM` settings and the HS256 signing path (ignored if left in `.env`).
- The `mcp_fetch` MCP preset (`uvx mcp-server-fetch`).

### Fixed

- `POST /api/auth/refresh` read a `user_id` claim that does not exist, so every exchange failed; it now maps the account by `sub`.
- A document deletion racing an index write could write the deleted document's chunks back into the knowledge base (CWE-362).
- SQLite reused the ids of deleted users and documents, so old tokens or chunks could map to new rows.

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
