# Troubleshooting

[繁體中文](troubleshooting.md) | [English](troubleshooting_en.md)

> Common error messages during installation, startup, and everyday use, and how to fix them. For problems specific to a Docker Compose deployment see the [deployment guide](deployment_en.md); for issues after upgrading from an older release see the troubleshooting part of each release in the [upgrade guide](upgrading_en.md).

- [Backend startup](#backend-startup)
- [Accounts, sign-in, and rate limits](#accounts-sign-in-and-rate-limits)
- [Frontend](#frontend)
- [Retrieval and tools](#retrieval-and-tools)

## Backend startup

<details><summary><b>The backend fails to start with <code>Field required</code></b></summary>

A required setting is missing from `.env`; the error names the fields. Add them as listed under [configuration reference: required settings](configuration_en.md#required-settings). When upgrading from an older release, the [upgrade guide](upgrading_en.md) lists the required settings each release added, such as `SKILLS_DIR` in 6.0.0 and `LOG_DIR` in 8.0.0.

</details>

<details><summary><b>The backend fails to start with <code>TOOL_SECRETS_KEY 必須是 Fernet 金鑰</code> (TOOL_SECRETS_KEY must be a Fernet key)</b></summary>

`TOOL_SECRETS_KEY` is still the template placeholder or is not a valid Fernet key. Generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and put it in `backend/.env`. Keep this key safe: after switching to a new key, the stored credentials of custom API tools and MCP servers and the keys of API connections can no longer be decrypted: enter the tool credentials again on the AI tools page, and the connection keys under Profile or "Admin → Shared API connections".

</details>

<details><summary><b>The backend fails to start with an error about the RSA keys or <code>backend/keys</code></b></summary>

JWTs are always signed with the RSA keys, and the backend refuses to start when it cannot load or generate them instead of falling back to a shared secret. Make sure `jwt_private.pem` and `jwt_public.pem` in `backend/keys/` are intact and readable; on the first start the backend account must be able to write to that directory.

</details>

<details><summary><b>The backend fails to start because the reranker cannot load</b></summary>

The reranker is required. The first start downloads it from Hugging Face, so check the network and make sure `HF_HUB_OFFLINE` is not `true`; if the models were downloaded before, point `HF_HOME` at that cache.

</details>

<details><summary><b><code>python init_db.py</code> fails with <code>near "EXISTS": syntax error</code></b></summary>

SQLite does not need `init_db.py`; the backend creates the tables at startup. The script only adds missing columns and indexes to older PostgreSQL databases.

</details>

## Accounts, sign-in, and rate limits

<details><summary><b>The knowledge base, AI tools, and admin pages are missing after signing in</b></summary>

Those pages are admin-only. Follow [Create the first admin](../README_en.md#4-create-the-first-admin) and sign in again.

</details>

<details><summary><b>Signing in returns <code>429</code> with 「登入失敗次數過多，請稍後再試」 (too many failed logins, try again later)</b></summary>

Once one login identifier (user name or email, case-insensitive) fails `LOGIN_MAX_FAILURES_PER_ACCOUNT` times, or one source address fails `LOGIN_MAX_FAILURES_PER_ADDRESS` times, within `LOGIN_FAILURE_WINDOW_SECONDS` seconds, logins for that identifier or address pause for `LOGIN_LOCKOUT_SECONDS` seconds, and even the right password is refused meanwhile; the `Retry-After` header gives the seconds left.

- The pause lifts on its own. The counts live only in the backend process's memory, so restarting the backend also clears them.
- Behind the Vite dev proxy or a reverse proxy, every user's failures add up on the same source address, and reaching `LOGIN_MAX_FAILURES_PER_ADDRESS` pauses logins for everyone. Keep the per-address threshold looser than the per-account one; if the reverse proxy in front overwrites `X-Forwarded-For`, set `FORWARDED_ALLOW_IPS` to count real client addresses instead.

</details>

<details><summary><b>The API returns <code>429 Too Many Requests</code></b></summary>

- Rate limiting counts requests per connecting IP, 60 per 60 seconds by default. Behind the Vite dev proxy or a reverse proxy every user shares one IP, so raise `RATE_LIMIT_PER_MINUTE` if needed; if the reverse proxy in front overwrites `X-Forwarded-For`, set its address as `FORWARDED_ALLOW_IPS` to count real client IPs instead.
- A 429 from `POST /api/chat/send` means the same user already has 2 answers streaming; wait for one to finish.

</details>

## Frontend

<details><summary><b>The frontend shows network or CORS errors</b></summary>

- Without `frontend/.env`, the frontend reaches `http://127.0.0.1:8001` through the Vite proxy, so make sure the backend is running on that port.
- With an absolute `VITE_API_BASE`, the browser calls the backend directly, and the backend's `ALLOWED_ORIGINS` must include the frontend origin (for example `http://localhost:3001`).
- With a `bun run build` output, the CSP's `connect-src` allows only the `VITE_API_BASE`/`VITE_API_URL` origin from build time; rebuild after changing the API address.

</details>

<details><summary><b>Other devices on the LAN cannot reach the frontend started with <code>bun run dev</code></b></summary>

The Vite dev and preview servers listen on `localhost` only, on purpose (dev-server endpoints such as `/__open-in-editor` must not be exposed). Build with `bun run build` and serve `frontend/build/` from a real web server such as nginx that reverse-proxies `/api` to the backend.

</details>

<details><summary><b><code>bun install</code> fails with <code>lockfile had changes, but lockfile is frozen</code></b></summary>

`frontend/bunfig.toml` sets `frozenLockfile = true`, so the install fails whenever `package.json` and `bun.lock` disagree instead of rewriting the pinned versions. Make sure both files come from the same revision; to add or upgrade a package on purpose, update `bun.lock` as described under [Dependencies](../README_en.md#dependencies) and commit both.

</details>

## Retrieval and tools

<details><summary><b>Every question reports that the knowledge base has nothing relevant</b></summary>

Make sure documents were uploaded and that `total_vectors` in `GET /api/admin/vector-store/info` (admin only) is above 0. If the index is fine, the relevance threshold may be too high; calibrate it with a real golden set as described in [calibrating the relevance threshold](configuration_en.md#calibrating-the-relevance-threshold).

</details>

<details><summary><b>Clicking the approval card shows 「無法送出決定，可能已逾時」 (could not send the decision, it may have timed out)</b></summary>

A pending approval lasts only 300 seconds; after that the agent treats it as a denial and carries on, and each approval can be answered only once. Replies from any account other than the asking user fail the same way. Ask again and approve within 5 minutes.

</details>

<details><summary><b>A read-only tool asks for approval every time</b></summary>

MCP servers require approval by default, and custom API tools follow their HTTP method. Once you are sure the tool does not change external systems, an admin can edit the tool on the AI tools page and untick 「AI 呼叫前需使用者在對話中確認」 ("ask the user in the chat before the AI calls it"); for an MCP server, untick 「AI 呼叫此伺服器的工具前需使用者在對話中確認」.

</details>