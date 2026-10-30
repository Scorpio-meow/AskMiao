# Upgrade Guide

[繁體中文](upgrading.md) | [English](upgrading_en.md)

> How to upgrade an existing deployment to a new release, with rollback steps and troubleshooting. See the [CHANGELOG](../CHANGELOG_en.md) for the full list of changes in each version.

- [Upgrading from 6.0.0 to 7.0.0](#upgrading-from-600-to-700)
  - [7.0.0 changes and required actions](#700-changes-and-required-actions)
  - [Upgrade steps for 7.0.0](#upgrade-steps-for-700)
  - [Rolling back to 6.0.0](#rolling-back-to-600)
  - [After upgrading to 7.0.0](#after-upgrading-to-700)
- [Upgrading from 5.0.0 to 6.0.0](#upgrading-from-500-to-600)
  - [6.0.0 changes and required actions](#600-changes-and-required-actions)
  - [Upgrade steps for 6.0.0](#upgrade-steps-for-600)
  - [Rolling back to 5.0.0](#rolling-back-to-500)
  - [After upgrading to 6.0.0](#after-upgrading-to-600)
- [Upgrading from 4.0.0 to 5.0.0](#upgrading-from-400-to-500)
  - [5.0.0 changes and required actions](#500-changes-and-required-actions)
  - [Upgrade steps for 5.0.0](#upgrade-steps-for-500)
  - [Rolling back to 4.0.0](#rolling-back-to-400)
  - [After upgrading to 5.0.0](#after-upgrading-to-500)
- [Upgrading from 3.0.0 to 4.0.0](#upgrading-from-300-to-400)
  - [Changes and required actions](#changes-and-required-actions)
  - [Upgrade steps](#upgrade-steps)
  - [Rolling back](#rolling-back)
  - [After the upgrade](#after-the-upgrade)
- [Upgrading from 2.x to 3.0.0](#upgrading-from-2x-to-300)
  - [Overview](#overview)
  - [Step 0: stop and back up](#step-0-stop-and-back-up)
  - [Step 1: update code and dependencies](#step-1-update-code-and-dependencies)
  - [Step 2: update `.env`](#step-2-update-env)
  - [Step 3: start the backend and rebuild the index](#step-3-start-the-backend-and-rebuild-the-index)
  - [Step 4: check admins and tool settings](#step-4-check-admins-and-tool-settings)
  - [Step 5: verify the upgrade](#step-5-verify-the-upgrade)
  - [Rolling back to 2.2.x](#rolling-back-to-22x)
  - [Troubleshooting](#troubleshooting)

---

## Upgrading from 6.0.0 to 7.0.0

For upgrading from 6.0.0 to 7.0.0 (2026-10-31); see the [CHANGELOG](../CHANGELOG_en.md#700---2026-10-31) for the changes. This release moves chat to per-account API connections, and the database gains an `llm_connections` table (created automatically at startup); the backend and frontend dependencies are the same as in 6.0.0, and `.env` has no new required settings. What you need to do is give every account an API connection, update API clients, and rebuild the frontend; rebuilding the index once after upgrading is recommended so existing documents pick up this release's extraction and chunking fixes.

### 7.0.0 changes and required actions

| Item | 6.0.0 | 7.0.0 | Action |
|---|---|---|---|
| Models and keys used by chat | `MODEL_NAME`, `AVAILABLE_MODELS`, the provider keys, and `LLM_API_BASE` in `.env`, shared by every account | Only the account's own personal connections and the shared connections an admin grants it, stored in the new `llm_connections` table; an account without any connection (admins included) cannot chat | Create connections as in step 4 of the [upgrade steps](#upgrade-steps-for-700) |
| LLM settings in `.env` | Shared by chat, AI summaries, `GET /api/tags`, and OCR of scanned PDF pages | Used only for AI summaries, `GET /api/tags`, and OCR of scanned PDF pages | Keep them if you use these features; there is no need to delete them |
| Claude output token limit | `ANTHROPIC_MAX_TOKENS` in `.env` | Every Claude connection (`anthropic`, or a Claude deployment on Foundry) requires an "output token limit", which is capped by the model's own output limit; `ANTHROPIC_MAX_TOKENS` only serves the system model | Fill it in when creating Claude connections; the `ANTHROPIC_MAX_TOKENS` value works |
| API address of personal connections | None | Members' personal connections can only point at public addresses; admins' personal connections and shared connections are not restricted | Have an admin create internal services (for example a local Ollama) as shared connections |
| `POST /api/chat/send` and `GET /api/chat/models` | `model_name` is optional and defaults to `MODEL_NAME`; `GET /api/chat/models` returns the `.env` model list | `connection_id` and `model_name` are required, and a connection that is not the caller's own or granted to them, or a model not in its list, returns `400`; `GET /api/chat/models` requires sign-in and returns `{"connections": [{id, name, provider, scope, models}]}` | API clients fetch the available connections and models first and send both |
| `PUT /api/auth/me` | Updates the email, or changes the password with `current_password` and `new_password` | Only updates the email; password fields are ignored without an error, and the password does not change | Change passwords with `POST /api/auth/change-password` |
| Conversation endpoints | `GET /api/chat/conversations` includes the 5 most recent messages per conversation, and `GET /api/chat/conversations/{conversation_id}` the newest 500 | `messages` is always an empty array in both | Read messages from `GET /api/chat/conversations/{conversation_id}/messages` (`limit`, `offset`) |
| Rebuild index | Clears the whole index and writes documents back one by one, so the knowledge base returns nothing meanwhile | Replaces each document's chunks in turn, so other documents stay searchable; the response gains `failed_documents` | Integrations that read the response handle `failed_documents` as needed |
| Index write failures | A failed BM25 write is only logged; deleting a document reports success even when removing it from the indexes fails | Uploading, deleting, or rebuilding that document, or startup, fails; a delete returns `500` | When it happens, check the permissions and disk space of `BM25_INDEX_DIR` |
| Document extraction and chunking | A document with an FAQ section in the middle keeps only what follows the first 「Q：」 line; an overlong Q&A pair becomes one chunk; DOCX tables come at the end; PPTX leaves out shapes in groups and speaker notes; digits in some PDFs come out as characters such as 「俸」 | Fixed | Rebuild the index once so documents whose uploaded file still exists are re-extracted |
| PDFs without text | Pages without extractable text are stored as placeholder text | A PDF with no extractable text on any page returns `400` | To store scans, first set up the vision model for OCR of scanned PDF pages (see the [configuration reference](configuration_en.md#llm-providers-and-models)) |
| Usernames | The `\w` rule, accepting letters of any script, full-width letters, and a trailing newline | Only Chinese characters, ASCII letters, digits, `_`, and `-` | Existing accounts sign in as before; when editing an account whose name breaks the rule in the admin dashboard, rename it to a valid name in the same edit |
| Accounts deactivated and then reactivated | Tokens issued before deactivation work again after reactivation | Deactivation revokes them, so the account signs in again after reactivation | None |
| Tool name length | Names generated from an OpenAPI `operationId` or an MCP tool have no length limit | Names given to the model are at most 64 characters, and longer ones become the first 55 characters plus `_` and an 8-character hash; creating or importing a tool with a longer name returns `400` | If a skill's `allowed-tools` lists an overlong tool name, use the new name listed by `GET /api/chat/tools` |
| Custom API tool redirects | Every method follows cross-origin redirects (without credential headers) | Methods other than `GET`, `HEAD`, and `OPTIONS` follow only same-origin redirects; a refused redirect or more than 5 redirects returns `400` | For `POST` and similar tools that redirect to another domain, use the final URL |
| `web_fetch` domain allowlist | Only the initial URL is checked; with `OLLAMA_API_KEY` set, Ollama Web Fetch is tried first | Every redirect is checked; Ollama Web Fetch is not used unless the allowlist is `*` | Add the redirect target domains you need to `WEB_FETCH_ALLOWED_DOMAINS` |
| Docker images | No application Dockerfile was provided | `deploy/` (Docker Compose) and a `.dockerignore` at the repository root, which leaves `.env`, `backend/keys`, `backend/data`, `backend/logs`, `node_modules`, and similar out of the build context | Deployments that build their own images from the repository root and rely on the `.env`, keys, or data inside the image provide them through `env_file` and volumes instead, as `deploy/docker-compose.yml` does |
| `COOKIE_SECURE` from `deploy/gen-env.sh` | None | Written as `true` when `PUBLIC_ORIGIN` starts with `https://` | If `deploy/.env` came from a pre-7.0.0 `gen-env.sh` and the site is served over HTTPS, set `COOKIE_SECURE` to `true` |
| `rag_chunks` ids | SQLite may reuse deleted ids | New SQLite databases create the table with `AUTOINCREMENT` | None; existing SQLite tables are not rewritten |
| Dependencies | — | `backend/requirements.txt`, `requirements.in`, and `frontend/bun.lock` are the same as in 6.0.0 | No reinstall needed; the frontend still has to be rebuilt |

### Upgrade steps for 7.0.0

1. **Stop and back up**: stop the backend and back up the database, `backend/data/`, and `backend/.env`. API connection keys are encrypted with `TOOL_SECRETS_KEY`, so keep that key with your database backups.
2. **Update the code and rebuild the frontend**: the backend and frontend dependencies are the same as in 6.0.0, so there is no need to run `pip install` or `bun install`; run `bun run build` in `frontend/`. `.env` needs no new settings, and the existing LLM settings stay for AI summaries, `GET /api/tags`, and PDF OCR.
3. **Start the backend**: `python main.py`. The `llm_connections` table is created automatically at startup; documents left without any chunks by an interrupted upload are indexed at this point too, and the log says 「上傳時未完成索引，已補建 N 個分塊」 (not indexed during upload, N chunks added).
4. **Create API connections**: sign in as an admin, add connections under "Admin → Shared API connections", and enter the provider, API address, and key from `.env`; check off models with "從 API 取得模型" (fetch models from the API), except on Foundry, where deployment names are typed in, and fill in the output token limit for Claude connections. Under the accounts that may use it, pick all accounts (including accounts that register later) or check specific ones; you can also check the shared connections an account may use when editing that account. After saving, click "測試" (test) on the connection to confirm it works. If you would rather not share keys, have each account add its own under "Profile → My API connections"; see [Configuration: API connections](configuration_en.md#api-connections) for the fields.
5. **API clients**:
   - `POST /api/chat/send` sends `connection_id` and `model_name`, taken from `GET /api/chat/models` (sign-in required).
   - Change passwords with `POST /api/auth/change-password`; password fields sent to `PUT /api/auth/me` are ignored without an error.
   - Read a conversation's messages page by page from `GET /api/chat/conversations/{conversation_id}/messages`; the `attachments` of user messages carry the extracted attachment text in `content`.
   - The `POST /api/documents/rebuild-index` response gains `failed_documents`.
   - Settings that match tools by name (such as a skill's `allowed-tools`): custom API tools or MCP tools with names over 64 characters are given to the model as the first 55 characters plus `_` and an 8-character hash, so use the names listed by `GET /api/chat/tools`.
6. **When deploying with Docker**:
   - The `.dockerignore` at the repository root keeps `.env`, `backend/keys`, `backend/data`, and `backend/logs` out of images. Deployments that build their own images from the repository root provide `.env` through `env_file` and keep `data`, `keys`, and `logs` on volumes, as `deploy/docker-compose.yml` does; without a persistent `keys`, every recreated container generates new RSA keys and everyone has to sign in again.
   - When serving over HTTPS, make sure `COOKIE_SECURE` in `deploy/.env` is `true`. The 7.0.0 `gen-env.sh` sets it from `PUBLIC_ORIGIN`; versions before 7.0.0 always wrote `false`, so correct it by hand and recreate the backend container.
7. **Rebuild the index (recommended)**: as an admin, run "Rebuild index" on the knowledge base page. Documents whose uploaded file is still in `UPLOAD_DIR` are re-extracted and re-chunked the way this release does it (FAQ detection, splitting overlong Q&A pairs, DOCX table order, PPTX groups and speaker notes, PDF alternate glyphs). Other documents stay searchable during the rebuild; if the result lists failed documents, check the backend log and rebuild again.
8. **Verify**:
   - [ ] `GET http://localhost:8001/health` returns `{"status": "healthy"}`.
   - [ ] A member's chat model menu lists the shared connections granted to it (or its own personal connections), and a sent message gets an answer; an account without any connection sees the notice 「這個帳號還沒有可用的 AI 模型」 (this account has no AI model available yet).
   - [ ] After changing a password under "Profile", the current session and those in other browsers must sign in again with the new password.
   - [ ] After deactivating and reactivating a test account in the admin dashboard, that account's existing sessions must sign in again.
   - [ ] The rebuild-index result lists no failed documents.
   - [ ] Uploading a password-protected PDF reports 「PDF 文件被密碼保護，無法讀取」 (the PDF is password-protected and cannot be read) rather than a server error.

### Rolling back to 6.0.0

1. Stop the backend, switch the code back to 6.0.0, and run `bun run build` in `frontend/` again; the dependencies are the same, so nothing needs reinstalling.
2. Make sure `.env` still has the `MODEL_NAME`, `AVAILABLE_MODELS`, and provider keys chat needs: 6.0.0 chat uses only `.env` and never reads API connections, so every account shares those keys again.
3. The `llm_connections` table can stay: 6.0.0 never reads it, and the connections are still there when you upgrade again. But 6.0.0 does not handle this table when deleting an account: PostgreSQL refuses to delete an account that owns personal connections because of the foreign key, so first delete the rows in `llm_connections` whose `owner_id` is that account's id; SQLite leaves the connections behind without an owner. Deleted accounts also stay in the `allowed_user_ids` of shared connections, so review those lists under "Admin → Shared API connections" after upgrading again.
4. The attachment text 7.0.0 saved in `messages.context_used` can stay: 6.0.0 never reads it, but it still counts against each user's attachment quota.
5. The database and indexes need no restore or rebuild: a `rag_chunks` table created with `AUTOINCREMENT` in a new SQLite database works in 6.0.0, and 6.0.0 compares the `users.tokens_valid_after` set on deactivation as usual.
6. Switch API clients back to 6.0.0 usage: `POST /api/chat/send` ignores `connection_id`, and `model_name` may be omitted (to use `MODEL_NAME`) but, when sent, must be in the `.env` model list.

### After upgrading to 7.0.0

<details>
<summary><b>The chat page has no model to choose</b></summary>

The account has no personal connection and no shared connection granted to it; the `.env` models no longer appear on the chat page. Have an admin grant a shared connection as in step 4 of the [upgrade steps](#upgrade-steps-for-700), or have the account add its own under "Profile → My API connections".

</details>

<details>
<summary><b>Sending a message returns <code>400</code>: 「找不到這個 API 連線，或你沒有使用權限」 (connection not found or not permitted) or 「這個 API 連線沒有提供此模型」 (the connection does not offer this model)</b></summary>

The `connection_id` sent is not the caller's own or not granted to them (for example an admin just removed the account from a shared connection's list), or `model_name` is not in that connection's model list. Reload the chat page and pick the model again; API clients fetch `GET /api/chat/models` again. A request without `connection_id` or `model_name` returns `422`.

</details>

<details>
<summary><b>Adding a personal connection returns 「API 位址無法使用：個人連線只能連到可從網際網路解析的公開位址…」 (personal connections can only reach public addresses)</b></summary>

A member's personal connection cannot point at an internal or local service, such as Ollama at `http://localhost:11434`. Have an admin create it as a shared connection and grant it to the accounts that need it.

</details>

<details>
<summary><b>Editing a connection asks for the key again</b></summary>

The message is 「這個供應商需要 API 金鑰；變更供應商或 API 位址後不會沿用原本的金鑰，請重新輸入」 (this provider needs an API key; the stored key is not kept after the provider or API address changes): when the provider or API address changes, the stored key is not reused, as intended. Enter the key and save again.

</details>

<details>
<summary><b>Editing an account in the admin dashboard returns <code>422</code> with an error about the username</b></summary>

The account was created before 7.0.0 with characters that are no longer accepted (such as Cyrillic or full-width letters). It still signs in, but the edit dialog always sends the username, so rename it to use only Chinese characters, ASCII letters, digits, `_`, and `-` before saving, or send only the fields to change with `PUT /api/admin/users/{user_id}`.

</details>

<details>
<summary><b>Uploading a PDF returns <code>400</code>: 「PDF 文件中沒有可提取的文字…」 (the PDF has no extractable text)</b></summary>

Every page is an image or unreadable text, and OCR is not configured or failed. Set up the vision model for OCR of scanned PDF pages in `.env` (Microsoft Foundry, OpenAI, or Gemini, in that order; see the [configuration reference](configuration_en.md#llm-providers-and-models)) and upload the file again. Such PDFs stored by 6.0.0 hold only placeholder text, and a rebuild falls back to the stored content when re-extraction fails; delete those documents, set up OCR, and upload them again.

</details>

<details>
<summary><b>After a rebuild: 「以下文件重建索引失敗，請查看後端日誌後再重建一次」 (these documents failed to rebuild; check the backend log and rebuild again)</b></summary>

The backend log has 「處理文檔 &lt;id&gt; (&lt;file name&gt;) 失敗」 (processing document failed) with the reason. Documents whose re-extraction or chunking failed keep their old chunks, and other documents are unaffected; fix the cause and rebuild again.

</details>

<details>
<summary><b>An upload, delete, or startup fails and the log says 「BM25 add attempt 3 failed」 or 「BM25 delete attempt 3 failed」</b></summary>

A BM25 index write still failed after 3 attempts. 6.0.0 ignored this error and left BM25 out of step with the vector index; 7.0.0 fails the operation instead. Check that the backend account can write to `BM25_INDEX_DIR`, that there is enough disk space, and that no other process keeps holding the `bm25_write.lock` inside it, then try again.

</details>

<details>
<summary><b>A custom API tool returns <code>status_code</code> <code>400</code>: 「上游轉址未跟隨：…」 (upstream redirect not followed)</b></summary>

- 「轉址到其他來源，已拒絕」 (redirect to another origin refused): a method other than `GET`, `HEAD`, or `OPTIONS` got a redirect to another origin (different scheme, host, or port).
- 「轉址次數超過上限 (5)」 (too many redirects): there were more than 5 redirects.

Change the tool URL to the final URL and test again.

</details>

<details>
<summary><b><code>web_fetch</code> reports 「網頁讀取失敗：該網址遭安全防護拒絕或格式無效」 (blocked by security checks or invalid) and the log says 「轉址目標不在允許的網域內」 (redirect target not in the allowed domains)</b></summary>

The URL redirects to a domain that is not in `WEB_FETCH_ALLOWED_DOMAINS`. If it is safe to read, add the redirect target's domain to the allowlist and restart the backend.

</details>

---

## Upgrading from 5.0.0 to 6.0.0

For upgrading from 5.0.0 to 6.0.0 (2026-10-26); see the [CHANGELOG](../CHANGELOG_en.md#600---2026-10-26) for the changes. This release reworks how structured data is parsed and chunked and adds Agent Skills support. The database gains an `agent_skills` table and a few columns in `custom_api_tools` and `mcp_servers`, all created automatically at startup, and the backend drops the `passlib` dependency; what you need to do is add two new required fields to the domain profile, add one new required setting, `SKILLS_DIR`, to `.env`, reinstall the backend packages from the new `requirements.txt`, and rebuild the index once after upgrading. Index metadata is now stored as JSON, so update `METADATA_PATH` as well.

### 6.0.0 changes and required actions

| Item | 5.0.0 | 6.0.0 | Action |
|---|---|---|---|
| Domain profile | `domain_words`, `record_date_fields`, `summary_fallback` | Adds the required `record_label_fields` and `record_ignore_fields` | Add both fields, or the backend will not start |
| Structured records | `【記錄 N】` with Chinese labels for author, content, link, and tags; nested data dropped; one chunk per record regardless of length | Original field names and dotted paths; long records split into parts that repeat the header | Rebuild the index once |
| CSV, XLSX, YAML | Chunked as plain text | CSV and XLSX rows become records; YAML is parsed into records | Rebuild the index once |
| `.jsonl` | Cannot be uploaded | Can be uploaded, one record per line | None |
| `filter_and_count_records` results | `author`, `link` | `label`, `links` | Integrations that read tool results use the new fields |
| Upload and rebuild-index responses | Structured record counts were included in `qa_pairs` | `qa_pairs` counts Q&A only; adds `record_count`, `warning`, `records_detected`, and `missing_source_files` | Read the new fields as needed |
| Index metadata | `METADATA_PATH` defaults to `data/index_metadata.pkl`, read and written with pickle | Defaults to `data/index_metadata.json`, read and written as JSON | Point `METADATA_PATH` in `.env` at the new name; the old name still works |
| Settings that did nothing | `ADMIN_API_KEY` is required, and `ENABLE_BATCH_ACCUMULATION`, `BATCH_ACCUMULATOR_SIZE`, and `BASE_URL` can be set, but no code uses them | Removed; ignored if left in `.env` | Delete them from `.env` if you like |
| Document lists | `GET /api/documents/` and `GET /api/admin/documents` return each document's full text in `content`, and the former calls the model for documents without a summary during the request | Only the fields the lists need, without `content`, and no summaries generated during the request | Integrations that read `content` query the database directly |
| Rebuild index | Regenerates every document's AI summary, overwriting hand edits | Summarizes only documents without a summary; a second call while one is running returns `409` | To regenerate every summary, use "Regenerate" on each document in the knowledge base page |
| MCP tool results | Both `content` and a duplicate `raw_result` | `content` only | Integrations that read `raw_result` read `content` |
| Password hashing package | `passlib` calling argon2 | `argon2-cffi` directly, with the same hash format and parameters | Reinstall from the new `requirements.txt`; existing passwords keep working |
| `SKILLS_DIR` | None | Required; the Agent Skills file directory | Add `SKILLS_DIR=data/skills` to `.env`, or the backend will not start |
| Azure OpenAI settings | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` | Renamed for Microsoft Foundry: `FOUNDRY_API_KEY`, `FOUNDRY_ENDPOINT`, `FOUNDRY_DEPLOYMENT`; the old names are still read (the new names win when both are set) | Move to the new names; to deploy Claude on Foundry, `FOUNDRY_ENDPOINT` must be `*.services.ai.azure.com` |
| Call path for Foundry and gpt-6 | Everything uses Chat Completions | OpenAI `gpt-6*` and Foundry deployments whose names start with `gpt-`, `o3`, or `o4` use the Responses API; other Foundry models stay on Chat Completions; Foundry deployments starting with `claude-` use `/anthropic` | Keep Foundry deployment names equal to the model names, otherwise they are treated as generic models and take the wrong path; organizations must not enable zero data retention for the Responses API path |
| Gemini default models | The list has `gemini-3.5-flash` and `gemini-3-pro`; `GEMINI_VISION_MODEL=gemini-3.5-flash` | The list is `gemini-4-argon`, `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`; `GEMINI_VISION_MODEL` defaults to `gemini-3.8-flash` | Nothing changes if you set `AVAILABLE_MODELS` or `GEMINI_VISION_MODEL` yourself; remove the retired `gemini-3-pro` if it is there |
| Reasoning effort | `reasoning_effort` goes only to OpenAI and Azure OpenAI | Mapped per provider and also sent to Claude, Gemini, and Ollama; the frontend gains `max` | None; set the optional `OLLAMA_NUM_CTX` if Ollama's context is too small |
| Python version | 3.10 or later | 3.12 or later | Install Python 3.12, recreate the virtual environment, and install packages from the new `requirements.txt`; 3.10 and 3.11 are no longer supported |
| `agent_skills` table | None | Holds installed skills' metadata, enabled state, `allow_scripts`, and `allowed_user_ids` | None; created automatically at startup |
| New columns in existing tables | None | `custom_api_tools.body_content_type`; `mcp_servers.discovered_resources`, `discovered_prompts`, `oauth_config`, and `oauth_tokens` (the last two encrypted) | None; added automatically at startup, and existing tools get `body_content_type` `application/json` |
| HTTP MCP protocol | JSON-only POST, protocol version `2024-11-05` | Streamable HTTP, protocol version `2025-06-18`; falls back to legacy HTTP+SSE when `initialize` returns `400`, `404`, or `405` | None; rediscover servers whose discovery failed |
| Remote MCP OAuth | Not supported | HTTP / SSE servers can be authorized with OAuth; the callback address is `/api/mcp/oauth/callback` | When the backend is behind a reverse proxy, the proxy must pass the scheme and host the client sees to the backend (`redirect_uri` is built from the request URL); with multiple workers, the authorization callback must reach the same process that started it |
| Custom API tools | `auth_type` is not checked, and form bodies are sent as JSON too | `auth_type` accepts only `none`, `bearer`, `api_key`, `basic`, and `oauth2_client_credentials`, and the body is sent according to `body_content_type` | Integrations that create or import tools through the API with another `auth_type` get `422`; use an allowed value |

### Upgrade steps for 6.0.0

1. Stop the backend and back up the database and `backend/data/`.
2. Update the code, run `pip install -r requirements.txt` in `backend/` to reinstall the backend packages (`passlib` is no longer needed; remove it with `pip uninstall passlib` if you like), and run `bun run build` for the frontend again. Add `SKILLS_DIR=data/skills` to `.env` (relative paths resolve against `backend/`); `ADMIN_API_KEY`, `ENABLE_BATCH_ACCUMULATION`, `BATCH_ACCUMULATOR_SIZE`, and `BASE_URL` can be deleted from `.env`.
3. Add both fields to the domain profile that `DOMAIN_PROFILE_PATH` points to. The bundled `backend/config/domain_profile.json` already has them; deployments with their own profile add them, for example:

   ```json
   "record_label_fields": ["title", "name", "author", "id"],
   "record_ignore_fields": ["embedcode", "svg", "icon", "rawhtml", "path", "base64", "style", "imagedata", "svgdata"]
   ```

   Either may be an empty array. `record_ignore_fields` holds exactly the noise fields that 5.0.0 hard-coded; if your data has a real `path` field, remove `path` from the list.
4. Set `METADATA_PATH` in `.env` to `data/index_metadata.json` and delete the old `backend/data/index_metadata.pkl`. Keeping the old name also works: the content is rewritten as JSON on the next index write, and until then the last rebuild time shows as empty.
5. Start the backend and, as an admin, run "Rebuild index" on the knowledge base page. Documents whose uploaded file is still in `UPLOAD_DIR` are re-extracted into the new format; `missing_source_files` in the response lists documents whose uploaded file is gone, which are chunked from the stored content as plain text and should be uploaded again.
6. Upload a JSON or CSV file to confirm: the upload result shows how many structured records it produced.

### Rolling back to 5.0.0

1. Stop the backend, switch the code back to 5.0.0, and rebuild the frontend.
2. Remove `record_label_fields` and `record_ignore_fields` from the domain profile: 5.0.0 rejects unknown fields and will not start with them.
3. Rebuild the index once so the chunks return to the 5.0.0 format. Documents whose uploaded file is gone keep content in the new format, which 5.0.0 chunks as plain text.
4. `METADATA_PATH` can go back to `data/index_metadata.pkl` or stay as it is; 5.0.0 cannot read JSON metadata, so the last rebuild time shows as empty until its next index write.
5. `ADMIN_API_KEY` is required in 5.0.0: if you deleted it from `.env`, add it back (any random string), and reinstall the backend packages from the 5.0.0 `requirements.txt` (which includes `passlib`).
6. The `agent_skills` table and the `SKILLS_DIR` directory can stay: 5.0.0 never reads them, and it ignores `SKILLS_DIR` in `.env`.
7. The new columns in `custom_api_tools` and `mcp_servers` can stay, and 5.0.0 ignores them: MCP servers' OAuth authorization, resources, and prompts are no longer used; tools with `auth_type` `oauth2_client_credentials` are called without auth, and form bodies are sent as JSON again.

### After upgrading to 6.0.0

<details>
<summary><b>Startup fails with an error naming <code>record_label_fields</code> or <code>record_ignore_fields</code></b></summary>

The domain profile is missing a new required field; add it as in step 3 of the [upgrade steps](#upgrade-steps-for-600).

</details>

<details>
<summary><b>Startup fails with an error naming <code>SKILLS_DIR</code></b></summary>

`.env` is missing the new required setting; add `SKILLS_DIR=data/skills` as in step 2 of the [upgrade steps](#upgrade-steps-for-600).

</details>

<details>
<summary><b>Uploading the same file again is not reported as a duplicate</b></summary>

Until the index is rebuilt, existing documents still hold `documents.content` in the 5.0.0 format, which differs from the new format, so they are not matched as duplicates. Rebuilding the index fixes this.

</details>

<details>
<summary><b>The upload result says 「結構化解析失敗，已改用純文字處理」 (structured parsing failed, handled as plain text)</b></summary>

The file is not valid JSON, JSONL, or YAML: for example a JSON trailing comma, a JSONL line that does not parse, or YAML whose aliases expand too far. The file is still stored as plain text; fix it, then delete and upload it again to get one record per entry.

</details>

<details>
<summary><b>The log says 「CHUNK_SIZE 太小，容納不下結構化記錄的標頭」 (CHUNK_SIZE too small for the record header)</b></summary>

`CHUNK_SIZE` is too small to hold a record header and its part number, so that document cannot be indexed. Raise `CHUNK_SIZE`, then upload again or rebuild the index.

</details>

---

## Upgrading from 4.0.0 to 5.0.0

For upgrading from 4.0.0 to 5.0.0; see the [CHANGELOG](../CHANGELOG_en.md#500---2026-10-10) for every change. This release addresses the findings of a second security audit. No index rebuild is needed, and the new column and the encryption of tool credentials are handled automatically at startup. The hands-on work is mostly the 10 new required settings in `.env`, how dependencies are installed, the PostgreSQL account the backend connects as, how accounts are created, and the parameter declarations of custom API tools.

### 5.0.0 changes and required actions

| Item | 4.0.0 | 5.0.0 | Action |
|---|---|---|---|
| Required settings | 10 | 20 | Add 10 |
| `HOST`, `RELOAD`, `COOKIE_SECURE` | `HOST` and `RELOAD` defaulted to `0.0.0.0` and `true`; `COOKIE_SECURE` was derived from `ENVIRONMENT` when unset | Required, with no default | Set them explicitly for your deployment |
| Interactive API docs | `/docs`, `/redoc`, and `/openapi.json` were always served | Served only when the required `ENABLE_API_DOCS` is `true` | Set it to `false` for public deployments |
| Self-registration | Anyone who could reach the API could register | With `ALLOW_REGISTRATION=false`, registration returns `403` and accounts are created with `scripts/create_user.py` | Decide whether to allow registration |
| Failed logins | Unlimited | Once a login identifier or source address reaches its failure threshold, logins pause with `429` and `Retry-After` | Set the four `LOGIN_*` thresholds |
| Password changes | Existing tokens stayed valid | Tokens issued before `users.tokens_valid_after` are rejected, including the current session's | None; the column is added and backfilled at startup |
| Tool credentials | Stored in plaintext and returned as is by the admin API | Encrypted with `TOOL_SECRETS_KEY`; the admin API shows `••••••••` in place of secret values | Generate a key and keep it with your database backups |
| Custom API tool parameters | Every parameter from the model was sent | Only parameters declared in `parameters_schema` are accepted, and fixed query parameters in the tool URL cannot be overridden | Review each tool's parameter declarations |
| MCP stdio subprocesses | Ran in the backend process's working directory | Run in a fresh empty temporary directory each time | Make relative paths in commands and arguments absolute |
| PostgreSQL container | The backend connected as the superuser `postgres` | The backend connects as the non-superuser `POSTGRES_APP_USER` | Set up the account, run `20-app-role.sh` once, and update `DATABASE_URL` |
| Dependencies | Unpinned; every install took the newest releases available | `requirements.txt` pins versions with hashes; `bun.lock` is committed and cannot change during install | Prefer a fresh virtualenv; add backend packages through `requirements.in` |
| Frontend build | No CSP in `index.html` | The build writes a CSP `<meta>` tag | Rebuild; set `VITE_API_BASE` at build time when the API is on another origin |
| API endpoints and responses | Included `GET /api/external-tags` and the WebSocket `/api/chat/ws/{user_id}`; the admin user API returned `hashed_password` | Both endpoints are removed; responses no longer contain password hashes or tool credentials, and login can return `429` | Update API clients as described in step 9 of the [upgrade steps](#upgrade-steps-for-500) |
| Chat attachment parsing | Shared the parsing limits of admin uploads | Has its own smaller memory budget; an attachment over budget is reported to the model as unread | None; see [resource limits](configuration_en.md#resource-limits) when needed |

### Upgrade steps for 5.0.0

1. **Stop and back up**: stop the backend and back up the database (copy the `.db` file for SQLite; use `pg_dump` for PostgreSQL), `backend/data/`, `backend/keys/`, and `backend/.env`. Once the new release starts, tool credentials are stored encrypted, so rolling back to 4.0.0 needs this database backup.
2. **Update code and dependencies**:
   - 4.0.0 did not track `frontend/bun.lock`. When you update with git, the copy an earlier `bun install` created makes `git pull` abort with "untracked working tree files would be overwritten by merge"; delete it first.
   - The backend `requirements.txt` now pins every version with hashes, so pip switches to hash-checking mode and stops if any package does not match its hash. `pip install` does not remove packages the new release no longer uses (FlagEmbedding, waitress, docxtpl, XlsxWriter, langchain, and langchain-community, plus python-jose, ecdsa, rsa, pyasn1, and six, which are no longer needed now that PyJWT is used), so installing into a fresh virtualenv is recommended; keep the old one until you are sure you will not roll back.
   - With an NVIDIA GPU, first install the CUDA build of the same `torch` version as in `requirements.txt` into the new virtualenv, following the PyTorch website, and then install the rest; an installed torch of the same version counts as matching the pin.
   - `frontend/bunfig.toml` now sets `frozenLockfile = true`: `bun install` installs exactly what `bun.lock` lists and fails when `bun.lock` and `package.json` disagree.

   ```bash
   # inside the new virtualenv
   cd backend
   pip install -r requirements.txt

   cd ../frontend
   bun install
   ```

   From now on, do not edit `requirements.txt` by hand to add or upgrade a backend package: edit `backend/requirements.in` (direct dependencies only) and regenerate it in `backend/`:

   ```bash
   uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes -o requirements.txt
   ```

   For the frontend, temporarily set `frozenLockfile` in `frontend/bunfig.toml` to `false`, run `bun add` or `bun remove`, set it back to `true`, and commit `package.json` and `bun.lock` together.
3. **Update `.env`**: add the 10 new required settings below. They have no defaults, and the backend refuses to start if any is missing; the recommended values match `backend/.env.example`:

   | Setting | Recommended | Description |
   |---|---|---|
   | `ALLOW_REGISTRATION` | `false` | Whether self-registration is open. Every account shares the whole knowledge base and the enabled tools, so keep it `false` on deployments others can reach and create accounts with `scripts/create_user.py` |
   | `LOGIN_MAX_FAILURES_PER_ACCOUNT` | `5` | Failure threshold per login identifier (case-insensitive) within the window (≥ 1) |
   | `LOGIN_MAX_FAILURES_PER_ADDRESS` | `20` | Failure threshold per source address (≥ 1). Users behind a proxy share one address, so keep it looser than the per-account threshold |
   | `LOGIN_FAILURE_WINDOW_SECONDS` | `900` | Window in seconds in which failures are counted (≥ 1) |
   | `LOGIN_LOCKOUT_SECONDS` | `900` | Seconds logins stay paused once a threshold is reached (≥ 1) |
   | `TOOL_SECRETS_KEY` | Generate one per deployment | Fernet key that encrypts tool credentials; the template value is not a valid key, so the backend refuses to start until it is replaced |
   | `HOST` | `127.0.0.1` | Listen address of `python main.py`. Keep `127.0.0.1` when only local clients or a reverse proxy on the same host connect; use `0.0.0.0` only when a reverse proxy in a container or on another host, or other devices, must reach the backend directly |
   | `RELOAD` | `false` | Reload automatically when code changes; set it to `true` only for development |
   | `COOKIE_SECURE` | `false` (`true` when served over HTTPS) | Whether the refresh token cookie is sent over HTTPS only. It must be `true` when the site is served over HTTPS, and `false` is fine for local development on `http://localhost`. 4.0.0 added Secure automatically with `ENVIRONMENT=production`; now it must be set explicitly |
   | `ENABLE_API_DOCS` | `false` | Serve `/docs`, `/redoc`, and `/openapi.json`, which list every endpoint and parameter; keep it `false` for public deployments |

   Ready to paste into `.env`; then put in a `TOOL_SECRETS_KEY` you generate, and adjust `HOST` and `COOKIE_SECURE` for your deployment:

   ```dotenv
   ALLOW_REGISTRATION=false
   LOGIN_MAX_FAILURES_PER_ACCOUNT=5
   LOGIN_MAX_FAILURES_PER_ADDRESS=20
   LOGIN_FAILURE_WINDOW_SECONDS=900
   LOGIN_LOCKOUT_SECONDS=900
   TOOL_SECRETS_KEY=<your generated Fernet key>
   HOST=127.0.0.1
   RELOAD=false
   COOKIE_SECURE=false
   ENABLE_API_DOCS=false
   ```

   Generate `TOOL_SECRETS_KEY` in `backend/` with the virtualenv active:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   **Keep `TOOL_SECRETS_KEY` with your database backups**: if the key is lost or changed, stored tool credentials can no longer be decrypted (admin API responses flag them with `credentials_unreadable`) and must be entered again one by one.
4. **PostgreSQL**:
   - **With `backend/docker-compose.yml`**, add `POSTGRES_APP_USER` (for example `askmiao_app`) and `POSTGRES_APP_PASSWORD` (a random string different from `POSTGRES_PASSWORD`) to `backend/.env`; the new compose file refuses to start without them. Init scripts do not run again on an existing data volume, so first recreate the container with the new setup (the volume is kept) to give it the two variables and the `20-app-role.sh` mount, and then run the script once by hand:

     ```bash
     cd backend
     docker compose up -d --wait
     docker compose exec postgres bash /docker-entrypoint-initdb.d/20-app-role.sh
     ```

     The script connects to `POSTGRES_DB` (`chatbot`) as the container's `POSTGRES_USER` (`postgres`), creates the `POSTGRES_APP_USER` account (`NOSUPERUSER NOCREATEDB NOCREATEROLE`) with the password `POSTGRES_APP_PASSWORD`, grants `CONNECT` on the database and `USAGE` and `CREATE` on the `public` schema, and makes the account the owner of every table in `public`. It is safe to rerun.
   - **Self-managed PostgreSQL**: as a superuser, create an account with the same privileges and hand it the tables. With `bash` and `psql` available you can run the same script, passing the four values as environment variables and the server location in `PGHOST` and `PGPORT`:

     ```bash
     cd backend
     POSTGRES_USER=<superuser> POSTGRES_DB=<database> POSTGRES_APP_USER=askmiao_app POSTGRES_APP_PASSWORD=<password> \
       PGHOST=<host> PGPORT=<port> bash init-app-role.sh
     ```

     Without `bash`, run the SQL in the script as a superuser.
   - Finally, point `DATABASE_URL` at that account; for the compose database it is `postgresql+psycopg2://askmiao_app:<POSTGRES_APP_PASSWORD>@localhost:7690/chatbot` (percent-encode special characters). `POSTGRES_PASSWORD` is now for administration only.
5. **Start the backend**: `python main.py`. At startup `upgrade_schema()`:
   - Adds `tokens_valid_after` to `users` and backfills it with `created_at`, so existing tokens and sessions stay valid; from then on a password change sets it to the current time, and every token issued earlier is rejected.
   - Encrypts the existing plaintext in `headers` and `auth_config` of `custom_api_tools` and in `env_vars` and `headers` of `mcp_servers` with `TOOL_SECRETS_KEY`, leaving values that are already encrypted alone. Values that are not valid JSON are cleared, and the log asks you to enter them again.
6. **Create accounts**: with `ALLOW_REGISTRATION=false`, `POST /api/auth/register` returns `403` and the login page hides the sign-up link; existing accounts are not affected. An admin creates new accounts, admins included, in `backend/` with the virtualenv active; the password is entered interactively twice and follows the same rules as registration:

   ```bash
   python scripts/create_user.py --username <username> --email <email>
   python scripts/create_user.py --username <username> --email <email> --admin   # create an admin
   ```
7. **Review the tools**: as an admin, open the AI tools page:
   - Custom API tools accept only parameters declared in the `properties` of `parameters_schema` (path, query, header, and body parameters, and `request_body`); a tool that declares no parameters no longer accepts any. When `request_body_schema` has `properties`, the fields of `request_body` must be listed there too, unless it sets `"additionalProperties": true`.
   - Query parameters written into the tool URL are fixed by the admin, and a call that supplies a parameter with the same name is rejected; if `parameters_schema` declares a parameter with the same name as a URL query parameter, remove one of them.
   - Run the live test (即時線上測試) of each custom API tool: when the result has `status_code` `400` and an invalid-parameter error (工具參數無效), add the declaration or remove the conflicting parameter as the message says. Tools imported from OpenAPI usually declare the parameters of their spec already, so tools created by hand need the closest look.
   - stdio MCP servers now run in a fresh empty temporary directory instead of the backend's startup directory: make relative paths in `command` and `args` absolute, and put the variables of servers that read a `.env` from their working directory into `env_vars`. HTTP MCP servers follow only same-origin redirects; if the URL redirects to another domain, enter the final URL. Run discovery again afterwards; tools whose names do not match `[A-Za-z0-9_.-]{1,128}` are skipped.
8. **Rebuild the frontend**: run `bun run build` in `frontend/`. The CSP `<meta>` tag is written into `build/index.html` only at build time; the dev server does not use it:
   - When the frontend and the API are on different origins, `VITE_API_BASE` (or `VITE_API_URL`) must be set at build time (in `frontend/.env` or the build environment); its origin is added to `connect-src`, and changing the API address later requires a rebuild.
   - A `<meta>` tag cannot set `frame-ancestors`, so the web server must still send `X-Frame-Options: DENY` or `Content-Security-Policy: frame-ancestors 'none'`.
   - Scripts and styles are allowed only from the same origin and by the hashes of the inline content in `index.html`, and images only from the same origin, `data:`, and `blob:`; resources from other sites that a deployment added to `index.html` are blocked.
9. **API clients**:
   - `GET /api/external-tags` and the WebSocket `/api/chat/ws/{user_id}` are removed.
   - The `POST /api/api-tools/parse-spec` response no longer includes `raw_spec`, and specs that use YAML aliases return `400`.
   - Users in `GET /api/admin/users` and `PUT /api/admin/users/{user_id}` contain only `id`, `username`, `email`, `role`, `is_active`, `is_admin`, `created_at`, and `last_login`, without `hashed_password`; `PUT` returns `{message, user}`.
   - Admin API responses for custom API tools and MCP servers show `••••••••` in place of secret values and gain `credentials_unreadable`. An update replaces the whole field with what you send; keys whose value is `••••••••` keep their stored value, and such a key with no stored value returns `400`.
   - The `approval_required` event gains `target`, which names where the request is actually sent.
   - `POST /api/auth/login` can return `429` with `Retry-After`; with registration closed, `POST /api/auth/register` returns `403`, and `GET /api/auth/registration` (which returns `{"enabled": bool}`) tells you beforehand.
   - After a successful `POST /api/auth/change-password`, or a `PUT /api/auth/me` with `new_password`, every token, the current one included, is invalid; sign in again with the new password.
   - `/docs`, `/redoc`, and `/openapi.json` are served only with `ENABLE_API_DOCS=true`.
10. **Verify**:
    - [ ] `GET http://localhost:8001/health` returns `{"status": "healthy"}`, and with `ENABLE_API_DOCS=false` `/docs` returns `404`.
    - [ ] An account created with `create_user.py` can sign in, and with `ALLOW_REGISTRATION=false` the login page shows no sign-up link.
    - [ ] After a test account enters a wrong password `LOGIN_MAX_FAILURES_PER_ACCOUNT` times in a row, the next login returns `429` (restarting the backend clears it).
    - [ ] After a test account's password is changed in one browser, both the current session and the sessions in other browsers must sign in again with the new password.
    - [ ] Keys on the AI tools page show as `••••••••`, the live test can still call APIs that need authentication, and the stored credential columns in the database start with `fernet:`.
    - [ ] With PostgreSQL, `\dt` in `psql` lists the application account as the owner of the tables (compose: `docker compose exec postgres psql -U postgres -d chatbot -c '\dt'`).
    - [ ] `frontend/build/index.html` contains `<meta http-equiv="Content-Security-Policy"`, and the browser console shows no CSP violations while you use the app.

### Rolling back to 4.0.0

1. Stop the backend and check out the 4.0.0 code. Switch back to the virtualenv you kept from before the upgrade, or install 4.0.0's `requirements.txt` (no pinned versions or hashes) into a new one. The frontend's `package.json` did not change, so running `bun run build` again with the 4.0.0 code is enough.
2. Restore `.env` from the step 1 backup. 4.0.0 ignores settings it does not know, so leftover settings such as `ALLOW_REGISTRATION` and `TOOL_SECRETS_KEY` are harmless, but `DATABASE_URL` must match the database you restore.
3. For the database, pick one:
   - **Restore the backup** (recommended): the cleanest option, but conversations, documents, and accounts added after the upgrade are lost. Tool credentials are now encrypted, and 4.0.0 cannot read them; it treats them as not set.
   - **Keep the current database**: re-enter the credentials of every custom API tool and MCP server in 4.0.0. 4.0.0 ignores the `users.tokens_valid_after` column; however, in a brand-new database created by the new release this column is `NOT NULL` without a default, so 4.0.0 fails to create accounts until you drop the column or give it a default. If you upgrade again later, accounts created during the rollback have no value in this column; the new release fills it with `created_at` on every start, so no manual step is needed.
4. PostgreSQL container: the 4.0.0 `backend/docker-compose.yml` does not need `POSTGRES_APP_USER` or `POSTGRES_APP_PASSWORD`; recreate the container with `docker compose up -d`, and the application account left in the volume does not affect 4.0.0. A `pg_dump` backup restored as `postgres` leaves the tables owned by `postgres`, so keep the `DATABASE_URL` from the backed-up `.env`, which connects as `postgres`; if you keep the current database, the application account owns the tables and 4.0.0 can keep connecting with it.

### After upgrading to 5.0.0

<details>
<summary><b>Startup fails with <code>Field required</code></b></summary>

`.env` is missing new required settings. The error names each missing field; add them as described in step 3 of the [upgrade steps](#upgrade-steps-for-500), with the recommended values from `backend/.env.example`.

</details>

<details>
<summary><b>Startup fails because <code>TOOL_SECRETS_KEY</code> is not a Fernet key</b></summary>

The error is logged in Chinese as TOOL_SECRETS_KEY 必須是 Fernet 金鑰. `TOOL_SECRETS_KEY` still holds the template value or is not a valid Fernet key; generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. If credentials were already encrypted with a key, put that key back instead, because a new key cannot decrypt them.

</details>

<details>
<summary><b>Logins return <code>429</code></b></summary>

One login identifier or one source address reached its failure threshold within `LOGIN_FAILURE_WINDOW_SECONDS`, so logins pause for `LOGIN_LOCKOUT_SECONDS`, and even the right password is refused meanwhile. Try again after the number of seconds in the `Retry-After` header; the failure records live only in the backend process's memory, so restarting the backend also clears them at once.

Behind a reverse proxy without `FORWARDED_ALLOW_IPS`, every user's source address is the proxy, so all users share the per-address threshold. If the proxy overwrites `X-Forwarded-For`, set `FORWARDED_ALLOW_IPS`; otherwise raise `LOGIN_MAX_FAILURES_PER_ADDRESS`.

</details>

<details>
<summary><b>Tool credentials cannot be decrypted (<code>credentials_unreadable</code>)</b></summary>

Admin API responses show `credentials_unreadable` as `true` with the credential fields set to `null`; the live test and discovery of those tools return `400` saying the credentials cannot be decrypted with the current `TOOL_SECRETS_KEY` and must be entered again (無法以目前的 TOOL_SECRETS_KEY 解密工具憑證，請重新輸入), and calls from the agent fail with only an error code. The current `TOOL_SECRETS_KEY` is not the key the credentials were encrypted with: if you can recover the original key, put it back and restart the backend; otherwise re-enter the credentials of those custom API tools and MCP servers on the AI tools page and save. Fields sent back with the `••••••••` mask return `400`, because there is no stored value to keep.

</details>

<details>
<summary><b>A custom API tool returns <code>status_code</code> <code>400</code> with an invalid-parameter error (工具參數無效)</b></summary>

- Undeclared parameter (未宣告的參數 …): the parameter is not listed in the `properties` of `parameters_schema`; a name starting with `request_body.` means a body field is not listed in the `properties` of `request_body_schema`. Add the declaration; if the body fields vary, set `"additionalProperties": true` in `request_body_schema`.
- Fixed query parameter (不可覆寫工具網址中固定的查詢參數 …): the call supplied a parameter with the same name as a query parameter in the tool URL. Remove it from either the URL or `parameters_schema`.

</details>

<details>
<summary><b>Registration returns <code>403</code></b></summary>

This is expected with `ALLOW_REGISTRATION=false`; the response says registration is closed and asks the user to contact an admin (目前不開放註冊，請聯繫管理員建立帳號). Have an admin create the account with `scripts/create_user.py`, as in step 6 of the [upgrade steps](#upgrade-steps-for-500); set `ALLOW_REGISTRATION` to `true` and restart the backend only if you do want open registration.

</details>

<details>
<summary><b>PostgreSQL reports <code>must be owner of table</code> or <code>permission denied for table</code></b></summary>

The backend now connects as the application account, but the tables still belong to `postgres`, which means `20-app-role.sh` has not run yet. The script is safe to rerun, and one run hands every table in `public` to the application account; see step 4 of the [upgrade steps](#upgrade-steps-for-500).

- Running the script reports `No such file or directory`: the container was created from the old compose setup and has no mount for the script; recreate it with `docker compose up -d --wait` first.
- Connecting reports `password authentication failed`: the application account does not exist yet, or the user name or password in `DATABASE_URL` differs from `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD`. Every run of the script resets the password to the current `POSTGRES_APP_PASSWORD`.

</details>

<details>
<summary><b><code>bun install</code> fails with <code>lockfile had changes, but lockfile is frozen</code></b></summary>

`package.json` and `bun.lock` disagree. If you did not mean to change frontend packages, restore both files to the versions in the repository and install again. If you did, the message's suggestion to re-run without `--frozen-lockfile` does not apply, because the setting comes from `frontend/bunfig.toml`: temporarily set `frozenLockfile` there to `false`, run `bun add` or `bun remove`, set it back to `true`, and commit `package.json` and `bun.lock` together.

</details>

<details>
<summary><b><code>pip install -r requirements.txt</code> reports a hash error</b></summary>

Every package in `requirements.txt` carries hashes, so pip installs in hash-checking mode:

- `THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE`: a downloaded file differs from the one that was locked. If you changed a version in `requirements.txt` by hand, regenerate the file from `requirements.in` instead; if you install from a source other than PyPI (such as a private mirror), make sure it serves the same files as PyPI. Otherwise the file may have been tampered with, so do not bypass the check.
- `Hashes are required in --require-hashes mode` or `all requirements must have their versions pinned with ==`: `requirements.txt` contains a package without hashes or without a pinned version, usually one added by hand. Edit `requirements.in` instead and regenerate the file with `uv pip compile`.

</details>

---

## Upgrading from 3.0.0 to 4.0.0

For upgrading from 3.0.0 to 4.0.0; see the [CHANGELOG](../CHANGELOG_en.md#400---2026-09-27) for every change. This release is a security pass: no index rebuild is needed, and new table columns are added automatically at startup. The hands-on work is mostly about `.env`, `backend/keys/`, the PostgreSQL container, and how the frontend is served.

### Changes and required actions

| Item | 3.0.0 | 4.0.0 | Action |
|---|---|---|---|
| JWT signing | Development fell back to HS256 (`JWT_SECRET_KEY`) when the RSA keys could not load | Always RS256; the backend refuses to start if the keys cannot be loaded or generated | Make sure `backend/keys/` exists and is writable by the backend account; `JWT_SECRET_KEY` and `JWT_ALGORITHM` can be removed from `.env` |
| Token validation | Identity and `is_admin` came from the token | Every request loads the account by `sub`; deactivated or deleted accounts lose access immediately | None; existing tokens stay valid while the account exists and is active |
| Refresh tokens | `POST /api/auth/refresh` read a claim that does not exist and always failed | Works, and each refresh token is single-use | Clients that call it themselves must use the new cookie from every response |
| PostgreSQL container | Built-in password `postgres`, port open on every interface | `POSTGRES_PASSWORD` is required, and only `127.0.0.1:7690` is bound | Set `POSTGRES_PASSWORD` and update `DATABASE_URL` |
| Frontend dev server | Listened on every interface, reachable from the LAN | Listens on `localhost` only and sends anti-framing headers | LAN users switch to a production build behind a real web server |
| Rate limiting source IP | uvicorn's defaults could trust `X-Forwarded-For` | Only proxies named in `FORWARDED_ALLOW_IPS` are trusted | Set `FORWARDED_ALLOW_IPS` if a reverse proxy in front overwrites that header |
| Tool calls | The agent ran them directly | Tools with `requires_approval` wait for the user's approval | The columns are added automatically; adjust each tool's flag as needed |
| MCP presets | `mcp_fetch`, `mcp_filesystem` (root `./data`) | `mcp_fetch` removed; `mcp_filesystem` uses `backend/mcp_filesystem_sandbox` with a pinned version | Review servers created from the old presets |
| Outbound proxies | Custom API tools, MCP HTTP, and `web_fetch` honored `HTTP(S)_PROXY` | Always connect directly, pinned to the SSRF-validated IP | Environments that must go through a proxy need to handle it at the network layer |
| Message responses | Included the raw `context_used` string | `context_used` is always `null` in `/api/chat` responses | Read `sources`, `sources_detail`, `research_trace`, and `attachments` instead |
| Resource limits | Mostly unlimited | Request bodies, messages, attachments, tool results, concurrent streams, and more are capped | None; see [resource limits](configuration_en.md#resource-limits) when needed |

### Upgrade steps

1. **Stop and back up**: stop the backend and back up the database, `backend/data/`, `backend/keys/`, and `backend/.env`.
2. **Update the code**: after fetching the new code, run `pip install -r requirements.txt` in `backend/` and `bun install` in `frontend/`.
3. **Tidy `.env`**:
   - Remove `JWT_SECRET_KEY` and `JWT_ALGORITHM`. Leaving them is harmless; the backend ignores them.
   - If a reverse proxy in front of the backend *overwrites* `X-Forwarded-For` (for example nginx with `proxy_set_header X-Forwarded-For $remote_addr;`), add `FORWARDED_ALLOW_IPS=<proxy address>`; do **not** set it behind the Vite dev proxy.
4. **Check the RSA keys**: `backend/keys/jwt_private.pem` and `jwt_public.pem` must exist and be readable; without them the backend generates a pair on first start, so the directory must be writable by the backend account. Keeping the existing keys keeps existing tokens valid.
5. **PostgreSQL container (when using `backend/docker-compose.yml`)**:
   - Add `POSTGRES_PASSWORD=<random string>` to `backend/.env`; without it `docker compose` refuses to start.
   - An existing data volume was initialized with the old password `postgres`, and `POSTGRES_PASSWORD` only applies on first initialization. Start the container with the old setup, change the password, and then update `DATABASE_URL`:

     ```bash
     cd backend
     docker compose exec postgres psql -U postgres -c "ALTER USER postgres PASSWORD '<new password>';"
     ```

   - Set `DATABASE_URL` to `postgresql+psycopg2://postgres:<new password>@localhost:7690/chatbot` (percent-encode special characters), then recreate the container with `docker compose up -d` to apply the port binding on `127.0.0.1` only.
6. **Start the backend**: `python main.py`. At startup `upgrade_schema()` adds the `requires_approval` column to `custom_api_tools` and `mcp_servers` and backfills it: `true` for API tools whose method is not `GET`, `HEAD`, or `OPTIONS`, and `true` for every MCP server.
7. **Review the tools**: as an admin, open the AI tools page:
   - Adjust each tool's "requires user confirmation" to match what it really does. `GET` tools default to no confirmation; turn it on if a tool changes state or sends data out.
   - Servers created from the old `mcp_fetch` preset are not deleted, but they bypass `web_fetch`'s outbound protections; delete or disable them.
   - Servers created from the old `mcp_filesystem` preset still point at `./data` (the backend's data directory). Change the root to the absolute path of `backend/mcp_filesystem_sandbox` or another dedicated directory, pin the package to a reviewed version, and run discovery again.
8. **Serving the frontend**: `bun run dev` and `bun run preview` listen on `localhost` only. Deployments that let LAN devices reach the dev server directly should build with `bun run build`, serve `frontend/build/` from a real web server such as nginx that reverse-proxies `/api`, and send `X-Frame-Options: DENY` or `Content-Security-Policy: frame-ancestors 'none'`.
9. **Verify**:
   - [ ] After staying idle past the access token lifetime, the frontend refreshes the token and keeps working.
   - [ ] After deactivating a test account, that account's next request gets `401` right away.
   - [ ] Calling a tool that needs approval shows a confirmation card in the chat, and after a denial the agent answers from what it already has.
   - [ ] Clients that integrate with the API read the parsed message fields instead of `context_used` and handle the `approval_required` event.

### Rolling back

1. Stop the backend, switch the code back to 3.0.0, and restore `.env` (3.0.0 requires `JWT_SECRET_KEY`).
2. The database can stay as is: 3.0.0 ignores the new `requires_approval` columns. The exception is a brand-new database created by the new version, where these columns are `NOT NULL` without a default, so 3.0.0 fails to create tools; drop the two columns or give them a default first.
3. The 3.0.0 `backend/docker-compose.yml` goes back to the built-in password `postgres`; if you already changed the database password, keep the new password in `DATABASE_URL`.

### After the upgrade

<details>
<summary><b>The backend fails to start with an error about <code>backend/keys</code> or the RSA keys</b></summary>

The new release no longer falls back to HS256. Make sure `backend/keys/` exists and is writable by the backend account (needed when the keys are first generated), and that `jwt_private.pem` and `jwt_public.pem` are intact. For containers or read-only file systems, mount pre-generated keys.

</details>

<details>
<summary><b><code>docker compose up</code> says <code>POSTGRES_PASSWORD</code> must be set</b></summary>

The compose file no longer ships a password. Set `POSTGRES_PASSWORD` in `backend/.env` (or the shell), and change the password of an existing volume separately with `ALTER USER`; see step 5 of the [upgrade steps](#upgrade-steps).

</details>

<details>
<summary><b>LAN devices cannot reach the frontend</b></summary>

The dev and preview servers listen on `localhost` only, on purpose. Serve a production build from a real web server instead; see step 8 of the [upgrade steps](#upgrade-steps).

</details>

<details>
<summary><b>All users share one rate limit quota</b></summary>

Without `FORWARDED_ALLOW_IPS`, rate limiting counts the direct peer, so behind a reverse proxy everyone's source IP is the proxy. If the proxy overwrites `X-Forwarded-For`, set its address as `FORWARDED_ALLOW_IPS`; otherwise raise `RATE_LIMIT_PER_MINUTE`.

</details>

<details>
<summary><b>Sending a message returns <code>400</code>, <code>413</code>, <code>422</code>, or <code>429</code></b></summary>

- `400`: `model_name` is not in the available model list; use a model from `GET /api/chat/models` or add it to `AVAILABLE_MODELS`.
- `413`: the request body exceeds its limit, or the user's attachment storage reached 200 MiB; delete old conversations with attachments.
- `422`: the message exceeds 20,000 characters, or there are more than 5 attachments, one over 15 MiB, or more than 20 MiB in total.
- `429`: the same user already has 2 answers streaming.

</details>

---

## Upgrading from 2.x to 3.0.0

3.0.0 is a major release with incompatible changes to the index format, the required settings, and tool management permissions. The hands-on work takes about 15 minutes, plus one index rebuild: the rebuild re-extracts text, asks the LLM for a new summary, and embeds every document, so its duration grows with the size of your library.

### Overview

| Area | 2.2.x | 3.0.0 | Action |
|---|---|---|---|
| Chunks and indexes | FAISS, `documents.pkl`, and BM25 aligned by list position | The `rag_chunks` table is the source of truth; FAISS and BM25 are keyed by chunk_id | Rebuild the index once after upgrading |
| Retrieval fusion | Weighted normalized scores (`HYBRID_ALPHA`) | Standard RRF (`RRF_K`) plus a reranker probability threshold | Add the new settings |
| Required settings | 3 | 11 | Add 8 |
| Reranker | Skipped when it failed to load | Required; the backend refuses to start without it | Make sure the model cache or network is available |
| Tool management | Any signed-in user | Admins only | Make sure at least one admin exists |
| MCP `stdio` environment | Inherited the whole backend environment | Inherits essential system variables only | Put the variables a server needs in its `env_vars` |
| MCP HTTP URLs | Not validated | SSRF-validated on every request and redirect | Switch loopback or intranet servers to `stdio` |
| Hugging Face cache | Defaulted to `./data/hf_home` | `~/.cache/huggingface` when unset | Set `HF_HOME` explicitly to keep the old cache |
| Built-in model lists | GPT-4o, o-series, and others | GPT-6 / GPT-5.6, Claude 5 family, Gemini 3.x | List older models in `AVAILABLE_MODELS` |

### Step 0: stop and back up

The upgrade rewrites index files, so stop the backend first and back up:

- **Database**: copy the `.db` file for SQLite; use `pg_dump` for PostgreSQL.
- **`backend/data/`**: the vector index `faiss_index.bin`, `documents.pkl`, `index_metadata.pkl`, `bm25_index/`, the uploads in `uploads/`, and the model cache `hf_home/` if present.
- **`backend/.env`**.

### Step 1: update code and dependencies

```bash
# after checking out the 3.0.0 code
cd backend
pip install -r requirements.txt   # 3.0.0 adds the official anthropic SDK

cd ../frontend
bun install
```

### Step 2: update `.env`

#### New required settings

These 8 settings have no defaults, and the backend refuses to start if any is missing. The recommended values match `backend/.env.example`:

| Setting | Recommended | Description |
|---|---|---|
| `ENABLE_WEB_SEARCH` | `true` | Offer the `web_search` and `web_fetch` web tools |
| `AGENT_MAX_TURNS` | `5` | Maximum tool-calling turns per question (≥ 1) |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | Prior messages loaded from the database as context (0 disables) |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | Domains `web_fetch` may read (subdomains included, comma-separated); only an explicit `*` means unrestricted |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | Refuse web tools once knowledge-base content has been read in the same question |
| `RRF_K` | `60` | RRF fusion constant |
| `RERANK_RELEVANCE_THRESHOLD` | `0.2` | Chunks whose reranker probability falls below this are irrelevant (provisional value; see [calibrating the threshold](configuration_en.md#calibrating-the-relevance-threshold)) |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | Domain profile path (relative paths resolve against `backend/`) |

Ready to paste into `.env`:

```dotenv
ENABLE_WEB_SEARCH=true
AGENT_MAX_TURNS=5
CONVERSATION_HISTORY_MESSAGES=6
WEB_FETCH_ALLOWED_DOMAINS=*
BLOCK_WEB_TOOLS_AFTER_KB=true
RRF_K=60
RERANK_RELEVANCE_THRESHOLD=0.2
DOMAIN_PROFILE_PATH=config/domain_profile.json
```

> [!IMPORTANT]
> Claude models also need `ANTHROPIC_MAX_TOKENS` (for example `16000`); without it every Claude call fails with a message asking you to set it in `.env`.

#### Settings you can delete

These settings were removed and are ignored if left in `.env`:

`HYBRID_ALPHA`, `NORMALIZATION`, `FINAL_THRESHOLD`, `DOCUMENTS_PATH`, `ENABLE_AUTO_REINDEX`, `ENABLE_AUTO_REINDEX_TASK`, `REINDEX_HOURS`, `TRANSFORMERS_CACHE`, `HUGGINGFACE_HUB_CACHE`.

#### Behavior changes to review

- **Hugging Face cache**: 2.2.x stored models in `./data/hf_home` by default; 3.0.0 uses `~/.cache/huggingface` when `HF_HOME` is unset. To reuse the existing cache and avoid downloading the embedding and reranker models again (about 1.2 GB), set `HF_HOME=./data/hf_home`; `HUGGINGFACE_HUB_CACHE` is now `HF_HUB_CACHE`.
- **Default models**: `OPENAI_VISION_MODEL` now defaults to `gpt-6-sol` and `GEMINI_VISION_MODEL` to `gemini-3.5-flash` (both are used for OCR of scanned PDF pages), and the built-in lists no longer include `gpt-4o`, `o1`, `o3`, `gemini-2.5-flash`, and other older models. To keep using them, name them in `AVAILABLE_MODELS` and in those two settings.
- **Relative paths**: relative values of `DATA_DIR`, `UPLOAD_DIR`, the index paths, `HF_*`, `DOMAIN_PROFILE_PATH`, and `JIEBA_DICTIONARY` always resolve against `backend/`, no longer against the startup directory.
- **`RERANK_TOP_K`**: the code default is 50 and `.env.example` suggests 20. Reranking costs about 0.2 to 0.4 seconds per pair on CPU, so more candidates make every search slower.

The [configuration reference](configuration_en.md) documents every setting.

### Step 3: start the backend and rebuild the index

```bash
cd backend
python main.py
```

On the first start you will see, in order:

1. **Settings validation**: missing required settings stop startup with a `Field required` error that names each missing field.
2. **Model loading**: the embedding and reranker models; if the reranker cannot load, startup ends with a "cannot load the reranker model" error (logged in Chinese as 無法載入重排模型).
3. **Legacy index detected**: the log reports the old position-aligned FAISS format, and the file is renamed to `faiss_index.bin.legacy.bak`.
4. **An empty knowledge base for now**: the new `rag_chunks` table has no chunks yet, so existing documents are not searchable until you rebuild.

Rebuild the index in one of these ways:

| Method | How | Best for |
|---|---|---|
| Frontend | Sign in as an admin → Knowledge base (知識庫) → Rebuild index (重建索引) | Small libraries, seeing the result on screen |
| API | `POST /api/documents/rebuild-index` with an admin access token | Automated deployments |
| Offline script | **With the backend stopped**, run `python scripts/reprocess_existing_docs.py` in `backend/` | Large libraries, keeping the live service free |

```bash
# API method
curl -X POST http://localhost:8001/api/documents/rebuild-index \
  -H "Authorization: Bearer <admin access_token>"
```

For every document in the database the rebuild re-extracts text from `UPLOAD_DIR` (falling back to the stored content when the file is gone), regenerates the AI summary, chunks it with the current `CHUNK_SIZE` / `CHUNK_OVERLAP`, and writes `rag_chunks`, FAISS, and BM25. Once answers look right, you can delete `faiss_index.bin.legacy.bak` and `documents.pkl` from `backend/data/`.

> [!NOTE]
> You will not need manual rebuilds after this: every startup reconciles FAISS and BM25 against `rag_chunks`, and switching to an embedding model with a different vector dimension renames the old index to `*.mismatch.bak` and re-embeds automatically.

### Step 4: check admins and tool settings

- **At least one admin**: the AI tools, knowledge base, and admin dashboard pages are admin-only. If you have no admin yet, follow [README: create the first admin](../README_en.md#4-create-the-first-admin).
- **MCP `stdio` servers**: subprocesses inherit only essential system variables (`PATH`, `SYSTEMROOT`, `USERPROFILE`, and a few more on Windows; `HOME`, `PATH`, `SHELL`, and a few more elsewhere). Servers that relied on backend variables (such as `HTTP_PROXY`, `HTTPS_PROXY`, `NODE_EXTRA_CA_CERTS`, or access tokens) need those variables in their `env_vars`; then run discovery again.
- **MCP HTTP servers**: servers on `localhost` or intranet addresses fail discovery, and `last_error` says the SSRF guard rejected them, with an error code. Use the `stdio` transport for local MCP servers.
- **Custom API tools**: every redirect of an outbound request is SSRF-validated again, so APIs that redirect into the intranet are rejected (the test result reports `status_code` `403`).

### Step 5: verify the upgrade

- [ ] `GET http://localhost:8001/health` returns `{"status": "healthy"}`.
- [ ] `http://localhost:8001/docs` is titled "AskMiao API" with version `3.0.0`.
- [ ] As an admin, `GET /api/admin/vector-store/info` reports `index_type` `FAISS IndexIDMap2(IndexFlatIP) + Whoosh BM25` and `total_vectors` above 0.
- [ ] A question the knowledge base covers gets `[n]` citations, and the source badges open the cited chunks.
- [ ] A question the knowledge base does not cover gets an honest "nothing relevant" answer instead of a made-up one.
- [ ] (Recommended) Run `python scripts/evaluate_retrieval.py --golden <golden set> --k 1 3 5 --relevance-thresholds 0.1 0.2 0.3` on a real golden set to calibrate `RERANK_RELEVANCE_THRESHOLD`.

### Rolling back to 2.2.x

1. Stop the backend and check out the 2.2.x code.
2. Restore `backend/data/` and `.env` from the Step 0 backup. The FAISS index written by 3.0.0 is keyed by chunk_id, which 2.2.x cannot use correctly.
3. For the database, pick one:
   - **Restore the backup**: the cleanest option, but conversations and documents added after the upgrade are lost.
   - **Keep the current database**: 2.2.x ignores the `rag_chunks` table. Documents added after the upgrade are missing from the restored index, so call `POST /api/documents/rebuild-index` on 2.2.x to rebuild it.

### Troubleshooting

<details>
<summary><b>Startup fails with <code>Field required</code></b></summary>

A required setting is missing from `.env`. The error names each missing field; add them as described in [Step 2](#step-2-update-env).

</details>

<details>
<summary><b>Startup fails because the reranker cannot load</b></summary>

The reranker is required in 3.0.0. Check that:

- `RERANKER_MODEL` is correct (default `BAAI/bge-reranker-base`).
- The first start can reach Hugging Face and `HF_HUB_OFFLINE` is not `true`.
- `HF_HOME` points at the old cache directory if you want to reuse it.

</details>

<details>
<summary><b>Every question reports that the knowledge base has nothing relevant</b></summary>

First confirm the index was rebuilt (`total_vectors` above 0 in `GET /api/admin/vector-store/info`). If the index is fine, the relevance threshold may be too high: `0.2` is a provisional value from a small corpus, so calibrate it with `scripts/evaluate_retrieval.py --relevance-thresholds` on a real golden set.

</details>

<details>
<summary><b>Regular users cannot see the AI tools page</b></summary>

This is expected in 3.0.0. Tools are shared by every user's agent and `stdio` servers run commands on the host, so only admins manage them; regular users can still let the agent use enabled tools in chat. See [ADR-0004](adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md).

</details>

<details>
<summary><b>An MCP server shows the <code>error</code> status</b></summary>

Check the server's `last_error`:

- It mentions SSRF: the URL or one of its redirect targets failed SSRF validation, most likely because the server is local or on the intranet; switch it to the `stdio` transport. The error code maps to the exact reason in the server log.
- It shows only an error code: most likely the `stdio` subprocess is missing a variable it used to inherit from the backend. Add it to `env_vars` and run discovery again; the error code maps to the full exception in the server log.

</details>
