# ADR-0004: Tool Management Permissions, MCP Subprocess Isolation, and Per-Hop SSRF Validation

[繁體中文](0004-tool-admin-permissions-and-subprocess-isolation.md) | [English](0004-tool-admin-permissions-and-subprocess-isolation_en.md)

## Status

Accepted - 2026-09-25

Extends [ADR-0002](./0002-external-tools-and-outbound-safety_en.md): adds tool management permissions and subprocess environment isolation, and makes ADR-0002's SSRF promise for the MCP HTTP transport actually hold.

---

## Context and Problem Statement

1. **Any registered user could run commands on the host**: `POST /api/auth/register` allows self-registration, while the `/api/mcp` and `/api/api-tools` endpoints only checked that the caller was logged in. Creating a `stdio` MCP server immediately calls `asyncio.create_subprocess_exec` with the `command` and `args` from the request body, so any registered user could execute arbitrary commands remotely (RCE).
2. **Tools are global configuration**: enabled custom API tools and MCP servers are loaded into every user's agent. A regular user could change the tool definitions everyone gets (for example, by hiding a prompt injection in a tool description) and read other people's credentials (`auth_config`, `headers`, `env_vars`) through the list endpoints.
3. **Subprocesses inherited the entire backend environment**: `McpStdioClient` started subprocesses with `dict(os.environ)`, handing `JWT_SECRET_KEY`, `DATABASE_URL`, and model API keys to any third-party MCP server package.
4. **Gaps in SSRF protection**: ADR-0002 states that the MCP HTTP transport passes the SSRF guard, but `McpHttpClient` never called it; custom API tools validated only the first URL and then followed redirects, so an external API could redirect a request to internal addresses such as `169.254.169.254`.

---

## Decision

### 1. Tool management is admin-only

- Every endpoint under `/api/mcp` and `/api/api-tools`, including reads and the preset list, now depends on `get_current_admin_user`. Non-admins always get 403, and no subprocess is started and no outbound request is sent.
- The frontend AI tools page (`/tools`) uses `AdminRoute`, and the navigation shows it to admins only. Regular users can only use enabled tools through the agent in a conversation.
- Keeping a read-only listing with redacted credentials for regular users was considered, but the page is a management interface and redaction needs a separate response model; it can be added later if needed.

### 2. stdio subprocesses inherit only essential system variables

- The subprocess environment is built by `build_stdio_env()`. It inherits only the system variables on the official MCP SDK's default list (on Windows `APPDATA`, `HOMEDRIVE`, `HOMEPATH`, `LOCALAPPDATA`, `PATH`, `PATHEXT`, `PROCESSOR_ARCHITECTURE`, `SYSTEMDRIVE`, `SYSTEMROOT`, `TEMP`, `USERNAME`, `USERPROFILE`; elsewhere `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER`), skips values that start with `()` (exported shell functions), and then adds the server's own `env_vars`.

### 3. SSRF validation on every hop

- A new httpx request hook, `reject_unsafe_request`, reruns `validate_url_ssrf` before the first request and before every redirect. It is applied to `execute_http_api_tool` and `McpHttpClient`.
- When an MCP server is rejected, `last_error` and the 400 response of the discover endpoint show the reason directly; the message only describes the URL the admin entered and contains no internal details.

### 4. No stdio command allowlist

- Restricting executables through a setting was considered, but `python`, `npx`, and `uvx`, which the presets rely on, run arbitrary code through their arguments, so an executable allowlist would not be a real boundary. The real boundary is that only admins can configure tools.

---

## Consequences

### Benefits

- **RCE closed**: regular users can no longer create, change, or run MCP servers and custom API tools.
- **Credentials stay private**: regular users cannot read tool credentials, and third-party MCP packages no longer receive the backend's keys and database URL.
- **SSRF promise kept**: ADR-0002's promise for the MCP HTTP transport holds, and redirects cannot bypass validation.
- **Regression-tested**: `backend/tests/test_tool_admin_permissions.py` enumerates every route in both modules, so a new endpoint that misses the admin check fails the test.

### Trade-offs & Risks

- **Regular users lose the tools page**, including its read-only overview.
- **MCP HTTP servers on loopback or private addresses are rejected**, consistent with the "blocks legitimate internal APIs" trade-off accepted in ADR-0002; run local MCP servers over the `stdio` transport instead.
- **Admins effectively have shell access to the host**: `stdio` still runs the commands admins configure, so admin accounts need protection to match.
- **Demotion is delayed**: `is_admin` comes from the access token, so revoking someone's admin role takes effect only when their access token expires (`ACCESS_TOKEN_EXPIRE_MINUTES`). This is existing behavior shared by every admin endpoint.

### Upgrade and rollback

- No schema or setting changes, so no migration is needed.
- `stdio` servers that relied on backend environment variables (for example `HTTP_PROXY`, `HTTPS_PROXY`, `NODE_EXTRA_CA_CERTS`, or access tokens) must list those variables in the server's `env_vars`.
- MCP HTTP servers pointing at `localhost` or private addresses fail discovery after the upgrade and show the reason in `last_error`.
- To roll back, revert the code.