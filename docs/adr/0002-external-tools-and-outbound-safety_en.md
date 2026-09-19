# ADR-0002: External Tool Extensibility & Outbound Request Safety

[繁體中文](0002-external-tools-and-outbound-safety.md) | [English](0002-external-tools-and-outbound-safety_en.md)

## Status

Accepted - 2026-09-01

---

## Context & Problem Statement

Once the agentic RAG pipeline was in production, the built-in toolset (knowledge base retrieval, record counting, web search, web fetch) no longer covered real enterprise needs:

1. **Extension cost too high**: onboarding each external system (ticketing, approvals, inventory lookups) required editing `rag/tools.py` and redeploying the backend, tying integrations to release cycles.
2. **Ecosystem integration**: MCP (Model Context Protocol) has become the common protocol for tool servers; connecting to existing MCP servers avoids wrapping each one by hand.
3. **Outbound requests create a new attack surface**: allowing users to supply URLs (spec sources, API endpoints, remote MCP servers) lets an attacker steer the server toward internal addresses or cloud metadata endpoints (SSRF).
4. **Exception leakage**: failures from external calls frequently carry internal paths, hostnames, and stack traces that must not reach the client.

---

## Decision Outcome

### 1. Database-driven tool registration instead of code-driven

- Added the `custom_api_tools` and `mcp_servers` tables holding custom HTTP API tools and MCP server configuration (including the `discovered_tools` cache).
- `ResearchToolRegistry.get_tool_definitions()` queries the enabled records on every assembly and merges them into the toolset, so changes take effect without restarting the backend.
- MCP tools follow the `mcp_<server_name>_<tool_name>` convention, and `execute_tool` routes on that prefix to `McpManager.execute_mcp_tool`.

### 2. OpenAPI import instead of per-endpoint manual entry

- Added `OpenApiParser` supporting OAS 2.0 / 3.0 / 3.1. Parsed endpoints are selected in the UI and imported in bulk; tools with an existing name are updated in place, keeping repeated imports idempotent.
- Parameter locations (`path` / `query` / `header` / `body`) are stored in `param_locations` and applied at execution time by the generic HTTP executor.

### 3. Centralized SSRF guard

- Added `app/core/ssrf_protection.py`. Every outbound request driven by user input (spec URLs, `web_fetch`, MCP HTTP transport, custom API tools) must pass validation first.
- Validation order: scheme → port → hostname → all IP addresses resolved via DNS; private and reserved ranges, loopback and link-local addresses, cloud metadata endpoints, and dangerous ports are blocked.

### 4. Unified error code mechanism

- Added `app/core/error_response.py`. Unexpected exceptions return only a 12-character `error_id`, while the full message and stack trace stay in the server log (CWE-209 / CWE-497).
- `SafeClientError` marks validation errors that only describe the user's own input, so they can be returned verbatim without sacrificing safety.

---

## Consequences & Trade-offs

### Positive Consequences

- **Much lower integration cost**: onboarding a system drops from "edit code and deploy" to "paste a spec and pick endpoints".
- **Ecosystem compatibility**: existing MCP servers can be reused directly.
- **Reduced attack surface**: outbound traffic funnels through one guard, so any new call site inherits the same protection by calling the same validator.
- **Leak prevention**: the error code mechanism covers both REST responses and SSE stream events.

### Negative Consequences & Risks

- **Assembly overhead**: tool definitions require a database query on every assembly. The MCP `discovered_tools` cache limits reconnection cost, but a caching layer will be needed if the tool count grows substantially.
- **Credential custody**: API keys for custom tools are stored in the database (`auth_config`) and require encryption or secret management appropriate to the deployment.
- **False positives**: the SSRF guard also blocks legitimate internal APIs on private addresses; such cases must be explicitly allowed at the deployment layer — an accepted trade-off.
- **Debugging experience**: clients only see an error code, so operations must correlate it with the server log via `error_id`.
