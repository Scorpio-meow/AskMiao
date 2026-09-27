# ADR-0006: In-Chat Approval for Tools with Side Effects

[繁體中文](0006-tool-call-approval.md) | [English](0006-tool-call-approval_en.md)

## Status

Accepted - 2026-09-27

Extends [ADR-0003](./0003-rrf-relevance-citations-and-tool-trust_en.md) and [ADR-0004](./0004-tool-admin-permissions-and-subprocess-isolation_en.md): ADR-0003 lists "outbound requests of custom API and MCP tools are outside the web restrictions" as a known risk, and ADR-0004 only limits who can configure tools; this record addresses when the agent may *call* those tools in a chat.

---

## Context and Problem Statement

1. **Prompt injection can drive calls with side effects**: the agent picks tools from the model's output. Instructions hidden in knowledge-base documents, web pages, or external API responses are wrapped in `<untrusted_tool_result>`, yet can still steer the model into calling `POST`- or `DELETE`-style custom API tools or MCP tools that write files. The trust boundary is a hint to the model, not a guarantee enforced in code.
2. **Calls run with the operator's credentials**: tools are configured by admins, and their credentials (API keys, Bearer tokens, MCP server environment variables) belong to the operator. Anyone who can ask a question can indirectly make those credentials write, delete, or pay in external systems, and none of it can be undone.
3. **Existing protections cover configuration, not calls**: ADR-0004 stops regular users from creating or changing tools, but every enabled tool is available to every user's agent, and nobody confirms a call before it happens.
4. **MCP tool behavior is unknown in advance**: MCP servers report their tools and parameters only at discovery, so the backend cannot tell from a name or method whether a tool is read-only.

---

## Decision

### 1. A flag marks tools that need approval

- `custom_api_tools` and `mcp_servers` each gain a `requires_approval` column. MCP is configured per server: the tool list changes on rediscovery, so per-tool settings are easy to miss.
- **Defaults**: custom API tools follow their HTTP method, `false` for `GET`, `HEAD`, and `OPTIONS` and `true` for everything else; MCP servers are always `true`, and admins can turn it off per server. OpenAPI imports follow the method too, and overwriting an existing tool keeps approval on if it was on; an update that changes the method to a state-changing one without an explicit flag turns approval on.
- **Existing data**: `upgrade_schema()` adds the columns at startup and backfills them with the same rules.

### 2. The agent pauses and the asking user approves

- `ResearchAgent` checks `requires_approval` before running a tool. When approval is needed, `ToolApprovalBroker` creates a pending item bound to the asking user's `user_id` (with a random `approval_id`), the SSE stream sends `approval_required` (tool name, display name, and arguments), and the agent waits in place.
- The frontend shows a confirmation card inside that answer, and the user's decision comes back through `POST /api/chat/approvals/{approval_id}`. Only the user who created the item can answer; anyone else (admins included), and items already handled or timed out, get `404`, which does not reveal whether the item exists.
- After the stream sends `approval_resolved`, an approved call runs as usual; a denial, or no answer within 300 seconds, counts as a denial: the tool does not run, and the model receives a tool result saying the user did not approve, telling it to answer from what it already has and not to call the same tool again.
- When no user can approve (`approval_user_id` is `None`, for example in a non-interactive run), tools that need approval never run instead of being let through.

### 3. Alternatives considered and rejected

- **Allow read-only tools only**: disabling everything but `GET` is simplest, but loses legitimate uses such as opening tickets or submitting forms.
- **An admin review queue**: admins do not see the question's context and cannot answer in real time; the person who knows whether "this call is what I wanted" is the one who asked.
- **Have the model ask the user in text first**: the model's output is exactly what prompt injection targets, so the confirmation must be enforced by code, not left to the model.
- **Per-tool settings for MCP**: the tool list changes on rediscovery, so per-server settings are harder to miss; they can be refined later if needed.

---

## Consequences and Trade-offs

### Benefits

- **Calls with side effects need a human**: prompt injection cannot change external systems with the operator's credentials without the user knowing.
- **Decide after seeing the arguments**: the card lists the tool and its full arguments, so users can spot data spliced into URLs or bodies.
- **Safe by default**: new MCP servers and state-changing API tools require approval by default, and non-interactive runs never execute them.
- **Regression-tested**: `backend/tests/test_tool_approval.py` covers the defaults, approval and denial, timeouts, approval by another user, runs without an approver, disconnects while waiting, and the column backfill on existing databases.

### Trade-offs & Risks

- **One more click**: every call to a tool that needs approval asks for confirmation, and frequent prompts can cause "approval fatigue", where users approve without reading the arguments.
- **`GET` is not automatically harmless**: `GET` tools, which need no approval by default, can still have side effects or send data out in the query string; admins must set the flag according to what the API really does.
- **Streams stay open**: waiting for approval keeps the stream open for up to 5 more minutes, holding one of the user's concurrent stream slots (at most 2 per user).
- **Single process**: pending items live in process memory. With several workers or hosts, the approval request must reach the process that holds the stream (for example through sticky sessions), and items are lost when the backend restarts.
- **Admin tests skip approval**: `/api/api-tools/{id}/test` and the MCP tool test endpoint are triggered by admins directly and need no approval.

### Upgrade and Rollback

- The columns are added and backfilled automatically at startup; no manual migration is needed. After the upgrade every existing MCP server requires approval, so users will see confirmation cards at first; admins can turn it off per server on the AI tools page.
- API clients must handle the new SSE events `approval_required` and `approval_resolved` and offer a way to approve; clients that do not will wait for the 300-second timeout, and that tool call counts as denied.
- To roll back, restore the code; the old version ignores the two columns. However, in a brand-new database created by the new version these columns are `NOT NULL` without a default, so the old version fails to create tools; drop the two columns or give them a default first.
