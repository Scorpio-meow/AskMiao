# Upgrade Guide

[繁體中文](upgrading.md) | [English](upgrading_en.md)

> How to upgrade an existing deployment to a new release, with rollback steps and troubleshooting. See the [CHANGELOG](../CHANGELOG_en.md) for the full list of changes in each version.

- [Upgrading from 4.0.0 to the unreleased version](#upgrading-from-400-to-the-unreleased-version)
  - [Unreleased changes and required actions](#unreleased-changes-and-required-actions)
  - [Upgrade steps for the unreleased version](#upgrade-steps-for-the-unreleased-version)
  - [Rolling back to 4.0.0](#rolling-back-to-400)
  - [After upgrading to the unreleased version](#after-upgrading-to-the-unreleased-version)
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

## Upgrading from 4.0.0 to the unreleased version

For upgrading from 4.0.0 to the next release, which has no version number yet; see the [CHANGELOG](../CHANGELOG_en.md#unreleased) for every change. This release addresses the findings of a second security audit. No index rebuild is needed, and the new column and the encryption of tool credentials are handled automatically at startup. The hands-on work is mostly the 10 new required settings in `.env`, how dependencies are installed, the PostgreSQL account the backend connects as, how accounts are created, and the parameter declarations of custom API tools.

### Unreleased changes and required actions

| Item | 4.0.0 | Unreleased | Action |
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
| API endpoints and responses | Included `GET /api/external-tags` and the WebSocket `/api/chat/ws/{user_id}`; the admin user API returned `hashed_password` | Both endpoints are removed; responses no longer contain password hashes or tool credentials, and login can return `429` | Update API clients as described in step 9 of the [upgrade steps](#upgrade-steps-for-the-unreleased-version) |
| Chat attachment parsing | Shared the parsing limits of admin uploads | Has its own smaller memory budget; an attachment over budget is reported to the model as unread | None; see [resource limits](configuration_en.md#resource-limits) when needed |

### Upgrade steps for the unreleased version

1. **Stop and back up**: stop the backend and back up the database (copy the `.db` file for SQLite; use `pg_dump` for PostgreSQL), `backend/data/`, `backend/keys/`, and `backend/.env`. Once the new release starts, tool credentials are stored encrypted, so rolling back to 4.0.0 needs this database backup.
2. **Update code and dependencies**:
   - 4.0.0 did not track `frontend/bun.lock`. When you update with git, the copy an earlier `bun install` created makes `git pull` abort with "untracked working tree files would be overwritten by merge"; delete it first.
   - The backend `requirements.txt` now pins every version with hashes, so pip switches to hash-checking mode and stops if any package does not match its hash. `pip install` does not remove packages the new release no longer uses (FlagEmbedding, waitress, docxtpl, XlsxWriter, PyJWT, langchain, and langchain-community), so installing into a fresh virtualenv is recommended; keep the old one until you are sure you will not roll back.
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
   uv pip compile requirements.in --universal --python-version 3.10 --generate-hashes -o requirements.txt
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

### After upgrading to the unreleased version

<details>
<summary><b>Startup fails with <code>Field required</code></b></summary>

`.env` is missing new required settings. The error names each missing field; add them as described in step 3 of the [upgrade steps](#upgrade-steps-for-the-unreleased-version), with the recommended values from `backend/.env.example`.

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

This is expected with `ALLOW_REGISTRATION=false`; the response says registration is closed and asks the user to contact an admin (目前不開放註冊，請聯繫管理員建立帳號). Have an admin create the account with `scripts/create_user.py`, as in step 6 of the [upgrade steps](#upgrade-steps-for-the-unreleased-version); set `ALLOW_REGISTRATION` to `true` and restart the backend only if you do want open registration.

</details>

<details>
<summary><b>PostgreSQL reports <code>must be owner of table</code> or <code>permission denied for table</code></b></summary>

The backend now connects as the application account, but the tables still belong to `postgres`, which means `20-app-role.sh` has not run yet. The script is safe to rerun, and one run hands every table in `public` to the application account; see step 4 of the [upgrade steps](#upgrade-steps-for-the-unreleased-version).

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
