# Contributing

[繁體中文](CONTRIBUTING.md) | [English](CONTRIBUTING_en.md)

Thank you for helping improve AskMiao! This document explains how to report problems, suggest changes, and submit pull requests. Please read the [Code of Conduct](CODE_OF_CONDUCT_en.md) before taking part.

## Contents

- [Reporting problems and suggesting changes](#reporting-problems-and-suggesting-changes)
- [Development environment](#development-environment)
- [Before you start](#before-you-start)
- [Branches and commit messages](#branches-and-commit-messages)
- [Tests and checks](#tests-and-checks)
- [Dependencies](#dependencies)
- [Documentation and the intro site](#documentation-and-the-intro-site)
- [Opening a pull request](#opening-a-pull-request)
- [License](#license)

## Reporting problems and suggesting changes

| Type | Where |
|---|---|
| Bugs | [Bug report template](https://github.com/Scorpio-meow/AskMiao/issues/new?template=bug_report.yml) |
| New features or improvements | [Feature request template](https://github.com/Scorpio-meow/AskMiao/issues/new?template=feature_request.yml) |
| Wrong, outdated, or mismatched (Chinese vs. English) documentation | [Documentation issue template](https://github.com/Scorpio-meow/AskMiao/issues/new?template=documentation.yml) |
| Accessibility barriers | [Accessibility issue template](https://github.com/Scorpio-meow/AskMiao/issues/new?template=accessibility.yml); see the [Accessibility Statement](ACCESSIBILITY_en.md) for the current state |
| Security vulnerabilities | **Do not open a public issue.** Report privately as described in the [Security Policy](SECURITY_en.md) |

Before reporting:

- Search the [existing issues](https://github.com/Scorpio-meow/AskMiao/issues) to avoid duplicates.
- Check [Troubleshooting](../README_en.md#troubleshooting) in the README. For problems after an upgrade, check the [Upgrade Guide](../docs/upgrading_en.md) first; most startup failures come from a missing required setting.
- Redact passwords, tokens, API keys, `TOOL_SECRETS_KEY`, and personal data.

The backend only returns an error code to clients; the full stack trace is written to the server log. When reporting a bug, include the error code shown in the UI or API response and the matching lines from the log.

## Development environment

Install the backend and frontend by following [Quick Start](../README_en.md#quick-start) in the README.

- The backend needs Python 3.12 or later; install packages with `pip install -r requirements.txt` (hashes are verified).
- The frontend uses Bun for packages and scripts. Do not install with npm or yarn, which would create another lockfile.
- The first start downloads about 1.2 GB of embedding and reranker models.

## Before you start

- **Read the system constraints**: the "System constraints" section of [llms_en.txt](../llms_en.txt) lists the rules every code change must follow, such as routing outbound requests through the SSRF protection, admin checks on management endpoints, the SSE event contract, keeping resource limits in `core/limits.py`, and encrypting tool credentials. They apply to human contributors too.
- **Discuss large changes first**: open an issue before working on new features or changes to the API, database tables, or index format.
- **Record major design decisions**: when you change the architecture, a security boundary, or how data is stored, add an architecture decision record as described in [When to write an ADR](../docs/adr/README_en.md#when-to-write-an-adr).

## Branches and commit messages

- The default branch is `New`. Fork the repository, create a feature branch from `New`, and target `New` with your pull request.
- Write commit messages following [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). The description may be in English or Traditional Chinese, for example:

  ```text
  feat(rag): add a relevance threshold for retrieval results
  fix(security): keep revoked tokens until their original expiry
  docs: document the PostgreSQL upgrade steps
  ```

- Mark breaking changes with `!` after the type (for example `feat(api)!: …`) and add a `BREAKING CHANGE:` footer. New required settings and changes to API permissions or the index format are breaking changes.
- Keep each pull request to one change; send unrelated refactoring or formatting separately.

## Tests and checks

There is no CI that runs the tests yet. Run the checks below locally before opening a pull request and list the results in its description.

**Backend**:

```bash
cd backend
python -m pytest
```

- The repository has no `backend/.env`. The required settings and test values are listed in the "Verification" section of [llms_en.txt](../llms_en.txt).
- Some tests load the real embedding and reranker models; a full run takes several minutes.
- On Windows, if your user name contains non-ASCII characters, add an ASCII path such as `--basetemp=C:\pytest-tmp`; otherwise FAISS fails to write temporary indexes.

**Frontend**:

```bash
cd frontend
bun run test --run
bun run lint
bun x tsc --noEmit
```

When you change `vite.config.js` or the inline scripts in `index.html`, also run `bun run build` to check the CSP written at build time.

When fixing a bug, add a test that reproduces it and passes after the fix whenever you can.

## Dependencies

- **Backend**: `requirements.in` lists only direct dependencies; `requirements.txt` is generated from it with pinned versions and hashes, so do not edit it by hand. To add or upgrade a package, edit `requirements.in`, regenerate in `backend/` with the command below, and commit both files:

  ```bash
  uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes -o requirements.txt
  ```

- **Frontend**: `frontend/bunfig.toml` sets `frozenLockfile = true`. To add or upgrade a package, temporarily set it to `false`, update `bun.lock`, set it back to `true`, and commit `package.json` together with `bun.lock`.

## Documentation and the intro site

- **Bilingual documents**: the README, CHANGELOG, `docs/`, ADRs, and this document each have an English `_en` twin. Update both versions together.
- **Changelog**: record your change under `[Unreleased]` in both `CHANGELOG.md` and `CHANGELOG_en.md`, using the Keep a Changelog categories (Added, Changed, Removed, Fixed, Security).
- **Version numbers**: `__version__` in `backend/app/__init__.py` and `version` in `frontend/package.json` are updated by the maintainer at release time; pull requests do not need to change them.
- **Taiwanese terms**: user-facing text uses Traditional Chinese as written in Taiwan, for example 使用者名稱, 電子郵件, 權杖, and 字元.
- **Intro site sync**: the intro site's interactive demos reproduce backend rules in the browser. When you change the rules in these files (under `backend/app/`), update `site/index.html` and `site/main.js` as well:
  - `rag/research_session.py`: citation numbering and URL provenance
  - `rag/retrievers/hybrid.py`: RRF fusion, mixed score, relevance threshold
  - `rag/tools.py`, `core/config.py`: `WEB_FETCH_ALLOWED_DOMAINS`
  - `core/ssrf_protection.py`: SSRF check order and block lists
  - `services/mcp_service.py`: `INHERITED_ENV_VARS`
  - `rag/tool_approval.py`, `rag/agent.py`: HTTP methods that need no approval by default, the approval timeout, and the SSE events
  - `core/limits.py`: the numbers in the site's resource-limit table
  - `core/login_throttle.py`, `api/auth.py`: login-failure thresholds, time window, lockout seconds, and the `429` response
  - `core/jwt_auth.py`: how `tokens_valid_after` decides whether a token is revoked
  - `core/tool_secrets.py`: the encrypted format of tool credentials and how the admin API masks them

## Opening a pull request

1. Fill in the pull request template with what changed, why, and how you verified it, and link related issues (for example `Closes #123`).
2. For breaking changes, describe what is affected and the upgrade steps; they are collected into the [Upgrade Guide](../docs/upgrading_en.md) at release time.
3. For UI changes, attach before-and-after screenshots.
4. The maintainer may ask for changes during review; keep the discussion in line with the [Code of Conduct](CODE_OF_CONDUCT_en.md).

## License

By submitting a contribution, you agree that it is released under the project's [MIT License](../LICENSE).
