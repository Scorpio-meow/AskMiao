# Security Policy

[繁體中文](SECURITY.md) | [English](SECURITY_en.md)

## Supported versions

Only the latest major version receives security fixes. If you run an older version, upgrade to the latest release by following the [Upgrade Guide](../docs/upgrading_en.md).

| Version | Security fixes |
|---|---|
| 5.x | ✅ |
| 4.x and earlier | ❌ |

## Reporting a vulnerability

> [!IMPORTANT]
> **Do not disclose vulnerabilities in public issues, pull requests, or discussions.**

Use GitHub's private vulnerability reporting: open [Report a vulnerability](https://github.com/Scorpio-meow/AskMiao/security/advisories/new), fill in the form, and submit it. Only you and the maintainer can see the report.

If you can, include:

- The affected version (`__version__` in `backend/app/__init__.py`) and component, for example `backend/app/core/ssrf_protection.py`.
- The type of vulnerability and its possible impact, for example an SSRF protection bypass, privilege escalation, or a token that still works after it was revoked.
- Steps to reproduce or a proof of concept, and the conditions needed to reproduce it: the relevant `.env` settings, the LLM provider, and whether you use SQLite or PostgreSQL.
- A suggested fix (optional).

Do not include real passwords, tokens, API keys, or personal data; use test values when reproduction needs them.

## What happens next

1. The maintainer will acknowledge and reply as soon as possible.
2. Once the vulnerability is confirmed, the impact and the fix are discussed with you in a private security advisory, where you can also submit a fix on a private fork.
3. After the fix, a new version is released and recorded under Security in the [Changelog](../CHANGELOG_en.md), and the security advisory is published. If you wish, you will be credited in it.
4. If the report is not considered a vulnerability, you will get an explanation.

Please do not disclose details of the vulnerability until the fix is released and the advisory is published.

## Scope

**In scope**: the code and configuration in this repository, including `backend/`, `frontend/`, the `site/` intro site, and `backend/docker-compose.yml`.

**Out of scope**:

- Things an administrator can do by design, such as adding a `stdio` MCP server that runs commands on the host. Tool configuration is limited to administrators as a deliberate trust boundary; see [ADR-0004](../docs/adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md).
- Vulnerabilities in third-party services such as LLM providers, Ollama, or external MCP servers; please report them to those projects.
- Vulnerabilities in dependencies themselves; please report them upstream. Reports are welcome when the way AskMiao uses a dependency makes it exploitable, or when fixing it requires updating `requirements.txt` or `bun.lock`.
- Incorrect or inappropriate model answers are not vulnerabilities in themselves. However, if prompt injection in a document or web page lets the agent get past a safeguard, such as calling a tool with side effects without approval, reading a URL it should not read, or leaking credentials, please report it.

## Existing security design

See [Security](../README_en.md#security) in the README for the existing safeguards and where they live in the code, and the [Architecture Decision Records](../docs/adr/README_en.md) for the reasoning behind them.
