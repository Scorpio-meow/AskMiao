# 貢獻指南 (Contributing)

[繁體中文](CONTRIBUTING.md) | [English](CONTRIBUTING_en.md)

感謝你願意改進 AskMiao！本文件說明回報問題、提出建議與提交 Pull Request 的方式。參與前請先閱讀 [行為準則](CODE_OF_CONDUCT.md)。

## 目錄

- [回報問題與提出建議](#回報問題與提出建議)
- [開發環境](#開發環境)
- [動手之前](#動手之前)
- [分支與 Commit 訊息](#分支與-commit-訊息)
- [測試與檢查](#測試與檢查)
- [相依套件](#相依套件)
- [文件與介紹頁](#文件與介紹頁)
- [開啟 Pull Request](#開啟-pull-request)
- [授權](#授權)

## 回報問題與提出建議

| 類型 | 管道 |
|---|---|
| 錯誤 | [錯誤回報範本](https://github.com/Scorpio-meow/AskMiao/issues/new?template=bug_report.yml) |
| 新功能或改進 | [功能建議範本](https://github.com/Scorpio-meow/AskMiao/issues/new?template=feature_request.yml) |
| 文件錯誤、過時或中英不一致 | [文件問題範本](https://github.com/Scorpio-meow/AskMiao/issues/new?template=documentation.yml) |
| 無障礙問題 | [無障礙問題範本](https://github.com/Scorpio-meow/AskMiao/issues/new?template=accessibility.yml)，現況見 [無障礙聲明](ACCESSIBILITY.md) |
| 安全漏洞 | **不要開公開的 Issue**，請依 [安全政策](SECURITY.md) 私下通報 |

回報前請先：

- 搜尋 [既有的 Issue](https://github.com/Scorpio-meow/AskMiao/issues)，避免重複。
- 看過 README 的 [疑難排解](../README.md#疑難排解)；從舊版升級的問題先對照 [升級指南](../docs/upgrading.md)，啟動失敗多半是缺少必填設定。
- 遮蔽密碼、權杖、API 金鑰、`TOOL_SECRETS_KEY` 與個人資料。

後端對外只回傳錯誤代碼，完整堆疊只寫在伺服器日誌。回報錯誤時請附上畫面或 API 回應中的錯誤代碼，以及日誌中對應的片段。

## 開發環境

依 README 的 [快速開始](../README.md#快速開始) 安裝後端與前端。

- 後端需要 Python 3.10 以上，套件以 `pip install -r requirements.txt` 安裝（會驗證雜湊）。
- 前端以 Bun 管理套件與執行指令，請不要用 npm 或 yarn 安裝，以免產生其他鎖定檔。
- 首次啟動會下載約 1.2 GB 的嵌入與重排模型。

## 動手之前

- **先讀系統約束**：[llms.txt](../llms.txt) 的「系統約束」一節列出修改程式時必須遵守的規則，例如出站請求一律經 SSRF 防護、管理端點的權限檢查、SSE 事件約定、資源上限集中在 `core/limits.py`、工具憑證加密存放。這些規則同樣適用於人類貢獻者。
- **大的變更先討論**：新功能、改變 API、資料表或索引格式的變更，請先開 Issue 討論方向。
- **重大設計寫 ADR**：改變架構、安全邊界或資料保存方式時，依 [何時寫 ADR](../docs/adr/README.md#何時寫-adr) 新增架構決策紀錄。

## 分支與 Commit 訊息

- 預設分支是 `New`。Fork 本專案後，從 `New` 建立功能分支，Pull Request 也以 `New` 為目標。
- Commit 訊息遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hant/v1.0.0/)，說明可用繁體中文，例如：

  ```text
  feat(rag): 新增檢索結果的相關性門檻
  fix(security): 撤銷的權杖保留到原本的到期時間
  docs: 補充 PostgreSQL 的升級步驟
  ```

- 破壞性變更在類型後加上 `!`（例如 `feat(api)!: …`），並在 Commit 訊息本文寫明 `BREAKING CHANGE:`。新增必填設定、改變 API 權限或索引格式都屬於破壞性變更。
- 一個 Pull Request 只處理一件事；無關的重構或格式調整請另外送。

## 測試與檢查

目前沒有自動執行測試的 CI，請在送出 Pull Request 前於本機執行下列檢查，並在 Pull Request 說明中列出結果。

**後端**：

```bash
cd backend
python -m pytest
```

- 版本庫沒有 `backend/.env`，測試需要的必填設定與測試用的值見 [llms.txt](../llms.txt) 的「驗證」一節。
- 部分測試會載入實際的嵌入與重排模型，完整執行約需數分鐘。
- Windows 使用者名稱含中文等非 ASCII 字元時，請加上 `--basetemp=C:\pytest-tmp` 之類的 ASCII 路徑，否則 FAISS 寫入暫存索引會失敗。

**前端**：

```bash
cd frontend
bun run test --run
bun run lint
bun x tsc --noEmit
```

修改 `vite.config.js` 或 `index.html` 的內嵌腳本時，另外執行 `bun run build`，確認建置時寫入的 CSP 正確。

修正錯誤時，請盡量附上能重現問題、修正後通過的測試。

## 相依套件

- **後端**：`requirements.in` 只列直接依賴，`requirements.txt` 由它產生並鎖定版本與雜湊，請不要手動修改。新增或升級套件時修改 `requirements.in`，在 `backend/` 執行下列指令重新產生，兩個檔案一起提交：

  ```bash
  uv pip compile requirements.in --universal --python-version 3.10 --generate-hashes -o requirements.txt
  ```

- **前端**：`frontend/bunfig.toml` 設定 `frozenLockfile = true`。新增或升級套件時，暫時把它改為 `false` 更新 `bun.lock`，再改回 `true`，並把 `package.json` 與 `bun.lock` 一起提交。

## 文件與介紹頁

- **中英雙語**：README、CHANGELOG、`docs/`、ADR 與本文件都有 `_en` 結尾的英文版，修改時兩份一起更新。
- **變更紀錄**：在 `CHANGELOG.md` 與 `CHANGELOG_en.md` 的 `[Unreleased]` 記下變更，分類沿用 Keep a Changelog（新增、變更、移除、修正、安全性）。
- **版本號**：`backend/app/__init__.py` 的 `__version__` 與 `frontend/package.json` 的 `version` 在發行時由維護者更新，Pull Request 不需要修改。
- **臺灣用語**：使用者看得到的文字使用臺灣繁體中文用語，例如使用者名稱、電子郵件、權杖、字元。
- **介紹頁同步**：介紹頁的互動示範在瀏覽器端重現後端規則。修改下列檔案（`backend/app/` 之下）的規則時，請同步更新 `site/index.html` 與 `site/main.js`：
  - `rag/research_session.py`：引用配號、網址來源限制
  - `rag/retrievers/hybrid.py`：RRF 融合、混合分數、相關性門檻
  - `rag/tools.py`、`core/config.py`：`WEB_FETCH_ALLOWED_DOMAINS`
  - `core/ssrf_protection.py`：SSRF 檢查順序與封鎖清單
  - `services/mcp_service.py`：`INHERITED_ENV_VARS`
  - `rag/tool_approval.py`、`rag/agent.py`：預設需要核准的 HTTP 方法、核准逾時秒數與 SSE 事件
  - `core/limits.py`：介紹頁「每個入口都有上限」的數值
  - `core/login_throttle.py`、`api/auth.py`：登入失敗的門檻、時間視窗、鎖定秒數與 `429` 回應
  - `core/jwt_auth.py`：以 `tokens_valid_after` 判斷權杖是否失效
  - `core/tool_secrets.py`：工具憑證的加密格式與管理 API 的遮蔽規則

## 開啟 Pull Request

1. 依 Pull Request 範本填寫變更內容、原因與驗證方式，並連結相關的 Issue（例如 `Closes #123`）。
2. 有破壞性變更時，寫明影響範圍與升級步驟，發行時會整理進 [升級指南](../docs/upgrading.md)。
3. 介面有變動時，附上變更前後的截圖。
4. 維護者審查後可能會請你調整；討論請依 [行為準則](CODE_OF_CONDUCT.md) 進行。

## 授權

提交貢獻即表示你同意以本專案的 [MIT 授權條款](../LICENSE) 釋出你的貢獻。
