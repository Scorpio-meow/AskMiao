# 安全政策 (Security Policy)

[繁體中文](SECURITY.md) | [English](SECURITY_en.md)

## 支援的版本

只有最新的主版本會收到安全修正。使用舊版時，請依 [升級指南](../docs/upgrading.md) 升級到最新版。

| 版本 | 安全修正 |
|---|---|
| 5.x | ✅ |
| 4.x 以前 | ❌ |

## 通報漏洞

> [!IMPORTANT]
> **請不要在公開的 Issue、Pull Request 或討論中揭露漏洞。**

請使用 GitHub 的私人漏洞通報：開啟 [Report a vulnerability](https://github.com/Scorpio-meow/AskMiao/security/advisories/new)，填寫後送出。通報內容只有你與維護者看得到。

請盡量附上：

- 受影響的版本（`backend/app/__init__.py` 的 `__version__`）與元件，例如 `backend/app/core/ssrf_protection.py`。
- 漏洞類型與可能的影響，例如繞過 SSRF 防護、權限提升、權杖在撤銷後仍可使用。
- 重現步驟或概念驗證，以及重現需要的條件：相關的 `.env` 設定、LLM 供應商、使用 SQLite 或 PostgreSQL。
- 你建議的修正方式（選填）。

請不要附上真實的密碼、權杖、API 金鑰或個人資料；重現需要時請使用測試用的值。

## 處理流程

1. 維護者會盡快確認收到並回覆。
2. 確認是漏洞後，在私人的 Security Advisory 中與你討論影響範圍與修正方式；你也可以在其中的私人分支提交修正。
3. 修正後發行新版本，在 [版本變更紀錄](../CHANGELOG.md) 的「安全性」分類記錄，再公開 Security Advisory。你願意的話，會在其中列名致謝。
4. 判斷不屬於漏洞時，會說明原因。

修正發行並公開之前，請不要公開漏洞細節。

## 範圍

**範圍內**：本版本庫的程式碼與設定，包括 `backend/`、`frontend/`、`site/` 介紹頁與 `backend/docker-compose.yml`。

**範圍外**：

- 管理員依設計可以做到的事，例如新增會在主機上執行指令的 `stdio` MCP 伺服器。工具設定只開放管理員，這是刻意的信任邊界，見 [ADR-0004](../docs/adr/0004-tool-admin-permissions-and-subprocess-isolation.md)。
- LLM 供應商、Ollama、外部 MCP 伺服器等第三方服務本身的漏洞，請向該專案通報。
- 相依套件本身的漏洞，請向上游通報；但若 AskMiao 的使用方式讓它可被利用，或需要更新 `requirements.txt`、`bun.lock` 才能修補，歡迎通報。
- 模型回答不正確或不恰當，本身不視為漏洞。但若文件或網頁中的提示注入能讓 Agent 越過防護，例如不經核准就呼叫有副作用的工具、讀取不該讀的網址或洩漏憑證，請通報。

## 現有的安全設計

現有的防護與對應的程式位置見 README 的 [安全設計](../README.md#安全設計)，設計背景見 [架構決策紀錄](../docs/adr/README.md)。
