# Security Policy

[繁體中文](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/.github/SECURITY.md) | **English**

## Supported versions

Only the latest major version receives security fixes. If you run an older version, upgrade to the latest release by following the [Upgrade Guide](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/docs/upgrading_en.md).

| Version | Security fixes |
|---|---|
| 5.x | ✅ |
| 4.x and earlier | ❌ |

## Reporting a vulnerability

**Do not disclose vulnerability details in public issues, pull requests, or discussions.**

Report privately through one of these channels:

1. **GitHub private reporting (preferred)**: go to the repository's **Security** tab and click **Report a vulnerability**, or open the [private reporting form](https://github.com/Scorpio-meow/AskMiao/security/advisories/new) directly. Only you and the maintainer can see the report.
2. **Email**: if you can't use GitHub, write to [yao921024@gmail.com](mailto:yao921024@gmail.com) with a subject starting with `[Security] AskMiao`. Email is not end-to-end encrypted, so start with a short summary and send the details after you get a reply.

If you can, include:

- The affected version (`__version__` in `backend/app/__init__.py`) and component, for example `backend/app/core/ssrf_protection.py`.
- The type of vulnerability and its possible impact, for example an SSRF protection bypass, privilege escalation, or a token that still works after it was revoked.
- Steps to reproduce or a proof of concept, and the conditions needed to reproduce it: the relevant `.env` settings, the LLM provider, and whether you use SQLite or PostgreSQL.
- A suggested fix (optional).

Use test values when reproduction needs them; don't include real passwords, tokens, API keys, or personal data.

## Response process and timelines

This project is maintained by one person and has no bug bounty, but it commits to these timelines:

| Stage | Timeline |
|---|---|
| Acknowledge and first reply | Within 14 days of the report |
| Public disclosure | When the fix is released, and no later than 90 days after the report |

1. **Acknowledge**: confirm receipt and share an initial assessment.
2. **Assess**: confirm whether it is a vulnerability, its impact, and its severity, and ask you for details if needed; if it is not a vulnerability, explain why.
3. **Fix**: discuss the fix with you in a private GitHub security advisory, where you can also submit a fix on a private fork.
4. **Release**: release a fixed version, publish the security advisory, request a CVE ID through GitHub when applicable, and record the fix under Security in the [Changelog](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/CHANGELOG_en.md).
5. **Credit**: credit you in the advisory if you wish.

Please do not disclose details until the fix is released. If a fix cannot be ready within 90 days, the maintainer will explain why before the deadline and agree on a new disclosure date with you.

## Scope

### In scope

The code and configuration in this repository, including `backend/`, `frontend/`, the `site/` intro site, and `backend/docker-compose.yml`.

### Out of scope

- Things an administrator can do by design, such as adding a `stdio` MCP server that runs commands on the host. Tool configuration is limited to administrators as a deliberate trust boundary; see [ADR-0004](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/docs/adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md).
- Vulnerabilities in third-party services such as LLM providers, Ollama, or external MCP servers; please report them to those projects.
- Vulnerabilities in dependencies themselves; please report them upstream. Reports are welcome when the way AskMiao uses a dependency makes it exploitable, or when fixing it requires updating `requirements.txt` or `bun.lock`.
- Incorrect or inappropriate model answers are not vulnerabilities in themselves. However, if prompt injection in a document or web page lets the agent get past a safeguard, such as calling a tool with side effects without approval, reading a URL it should not read, or leaking credentials, please report it.

## Existing security design

See [Security](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/README_en.md#security) in the README for the existing safeguards and where they live in the code, and the [Architecture Decision Records](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/docs/adr/README_en.md) for the reasoning behind them.
