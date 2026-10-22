# 安全政策

**繁體中文** | [English](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/.github/SECURITY_en.md)

## 支援的版本

只有最新的主版本會收到安全修正。使用舊版時，請依[升級指南](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/docs/upgrading.md)升級到最新版。

| 版本 | 安全修正 |
|---|---|
| 5.x | ✅ |
| 4.x 以前 | ❌ |

## 回報漏洞

**請不要在公開的 Issue、Pull Request 或討論區揭露漏洞細節。**

請擇一管道私下回報：

1. **GitHub 私下回報（建議）**：到本專案的 **Security** 分頁按 **Report a vulnerability**，或直接開啟[私下回報表單](https://github.com/Scorpio-meow/AskMiao/security/advisories/new)。內容只有你和維護者看得到。
2. **電子郵件**：無法使用 GitHub 時，寄到 [yao921024@gmail.com](mailto:yao921024@gmail.com)，主旨開頭加上 `[Security] AskMiao`。電子郵件不是端對端加密，信裡先簡述問題就好，細節等收到回覆後再提供。

回報時請盡量附上：

- 受影響的版本（`backend/app/__init__.py` 的 `__version__`）與元件，例如 `backend/app/core/ssrf_protection.py`。
- 漏洞類型與可能的影響，例如繞過 SSRF 防護、權限提升、權杖在撤銷後仍可使用。
- 重現步驟或概念驗證，以及重現需要的條件：相關的 `.env` 設定、LLM 供應商、使用 SQLite 或 PostgreSQL。
- 你建議的修正方式（選填）。

重現需要時請用測試用的值，不要附上真實的密碼、權杖、API 金鑰或個人資料。

## 處理流程與時限

本專案由個人維護，沒有漏洞獎勵，但會遵守以下時限：

| 階段 | 時限 |
|---|---|
| 確認收到並首次回覆 | 收到回報後 14 天內 |
| 公開漏洞細節 | 修正發布時，最晚在回報後 90 天 |

1. **確認收到**：回覆已收到，並說明初步評估。
2. **評估**：確認是否屬於漏洞、影響範圍與嚴重程度，必要時向你詢問細節；不屬於漏洞時會說明原因。
3. **修正**：在私下的 GitHub Security Advisory 中與你討論修正方式，你也可以在其中的私人分支提交修正。
4. **發布**：發行修正版本、公開 Security Advisory，適用時透過 GitHub 申請 CVE 編號，並在[版本變更紀錄](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/CHANGELOG.md)的「安全性」分類記錄。
5. **致謝**：你願意的話，會在 Advisory 中列名致謝。

修正發布前請不要公開漏洞細節。90 天內來不及修正時，會在期限前向你說明原因，並協商新的公開日期。

## 範圍

### 範圍內

本版本庫的程式碼與設定，包括 `backend/`、`frontend/`、`site/` 介紹頁與 `backend/docker-compose.yml`。

### 不在範圍內

- 管理員依設計可以做到的事，例如新增會在主機上執行指令的 `stdio` MCP 伺服器。工具設定只開放管理員，這是刻意的信任邊界，見 [ADR-0004](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/docs/adr/0004-tool-admin-permissions-and-subprocess-isolation.md)。
- LLM 供應商、Ollama、外部 MCP 伺服器等第三方服務本身的漏洞，請向該專案回報。
- 相依套件本身的漏洞，請向上游回報；但若 AskMiao 的使用方式讓它可被利用，或需要更新 `requirements.txt`、`bun.lock` 才能修補，歡迎回報。
- 模型回答不正確或不恰當，本身不視為漏洞。但若文件或網頁中的提示注入能讓 Agent 越過防護，例如不經核准就呼叫有副作用的工具、讀取不該讀的網址或洩漏憑證，請回報。

## 現有的安全設計

現有的防護與對應的程式位置見 README 的[安全設計](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/README.md#安全設計)，設計背景見[架構決策紀錄](https://github.com/Scorpio-meow/AskMiao/blob/HEAD/docs/adr/README.md)。
