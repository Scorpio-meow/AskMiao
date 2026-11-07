# 疑難排解

[繁體中文](troubleshooting.md) | [English](troubleshooting_en.md)

> 安裝、啟動與日常使用時常見的錯誤訊息與處理方式。以 Docker Compose 部署時的問題另見 [部署指南](deployment.md)，從舊版升級後的狀況見 [升級指南](upgrading.md) 各版本的「常見狀況」。

- [後端啟動](#後端啟動)
- [帳號、登入與速率限制](#帳號登入與速率限制)
- [前端](#前端)
- [檢索與工具](#檢索與工具)

## 後端啟動

<details><summary><b>後端啟動失敗，出現 <code>Field required</code></b></summary>

`.env` 缺少必填設定，錯誤訊息會列出欄位名稱，對照 [設定參考：必填設定](configuration.md#必填設定) 補上。從舊版升級時，每一版新增的必填設定列在 [升級指南](upgrading.md)，例如 6.0.0 的 `SKILLS_DIR` 與 8.0.0 的 `LOG_DIR`。

</details>

<details><summary><b>後端啟動失敗，訊息為 <code>TOOL_SECRETS_KEY 必須是 Fernet 金鑰</code></b></summary>

`TOOL_SECRETS_KEY` 仍是範本的佔位字串，或不是有效的 Fernet 金鑰。以 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 產生一組填入 `backend/.env`。請妥善保存這把金鑰：換成新金鑰後，原本儲存的自訂 API 工具與 MCP 伺服器憑證，以及 API 連線的金鑰都無法解密：工具憑證要在「AI 工具」頁重新輸入，連線金鑰要在「個人資料」或「管理後台 → 共用 API 連線」重新輸入。

</details>

<details><summary><b>後端啟動失敗，錯誤與 RSA 金鑰或 <code>backend/keys</code> 有關</b></summary>

JWT 一律以 RSA 金鑰簽署，金鑰無法載入或產生時後端拒絕啟動，不再退回共用金鑰。請確認 `backend/keys/` 內的 `jwt_private.pem`、`jwt_public.pem` 完整可讀；首次啟動時該目錄需要能讓後端帳號寫入。

</details>

<details><summary><b>後端啟動失敗，訊息為「無法載入重排模型」</b></summary>

重排模型是必要元件。首次啟動需要連上 Hugging Face 下載模型，請確認網路可用且 `HF_HUB_OFFLINE` 不是 `true`；已下載過模型時，確認 `HF_HOME` 指向原本的快取目錄。

</details>

<details><summary><b>執行 <code>python init_db.py</code> 出現 <code>near "EXISTS": syntax error</code></b></summary>

使用 SQLite 時不需要執行 `init_db.py`，資料表會在後端啟動時自動建立。這個腳本只用來替舊版 PostgreSQL 資料庫補欄位與索引。

</details>

## 帳號、登入與速率限制

<details><summary><b>登入後看不到「知識庫」、「AI 工具」與「管理後台」</b></summary>

這些頁面只限管理員。請依 [建立第一位管理員](../README.md#4-建立第一位管理員) 設定後重新登入。

</details>

<details><summary><b>登入時回傳 <code>429</code>，訊息為「登入失敗次數過多，請稍後再試」</b></summary>

同一登入識別（使用者名稱或電子郵件，不分大小寫）在 `LOGIN_FAILURE_WINDOW_SECONDS` 秒內失敗 `LOGIN_MAX_FAILURES_PER_ACCOUNT` 次，或同一來源位址失敗 `LOGIN_MAX_FAILURES_PER_ADDRESS` 次後，該識別或位址的登入暫停 `LOGIN_LOCKOUT_SECONDS` 秒，期間即使密碼正確也不接受；回應的 `Retry-After` 標頭是剩餘秒數。

- 到期後自動解除。計數只存在後端行程的記憶體中，重新啟動後端也會清除。
- 經由 Vite 開發代理或反向代理連線時，所有使用者的失敗次數都累計在同一個來源位址上，達到 `LOGIN_MAX_FAILURES_PER_ADDRESS` 時所有人都暫停登入。請讓依位址的門檻比依帳號的寬；前方的反向代理會覆寫 `X-Forwarded-For` 時，可設定 `FORWARDED_ALLOW_IPS`，改以真實用戶端位址計數。

</details>

<details><summary><b>API 回傳 <code>429 Too Many Requests</code></b></summary>

- 速率限制依實際連線的來源 IP 計算，預設每 60 秒 60 次。經由 Vite 開發代理或反向代理時所有使用者共用同一個 IP，可視需要調高 `RATE_LIMIT_PER_MINUTE`；前方的反向代理會覆寫 `X-Forwarded-For` 時，可把代理位址設為 `FORWARDED_ALLOW_IPS`，改以真實用戶端 IP 計算。
- `POST /api/chat/send` 回傳 429 時，是同一位使用者已有 2 個回答正在串流，等其中一個完成即可。

</details>

## 前端

<details><summary><b>前端出現網路錯誤或 CORS 錯誤</b></summary>

- 沒有 `frontend/.env` 時，前端經 Vite 代理連到 `http://127.0.0.1:8001`，請確認後端已在該埠啟動。
- 設定了 `VITE_API_BASE` 等絕對網址時，瀏覽器會直接呼叫後端，後端的 `ALLOWED_ORIGINS` 必須包含前端的來源（例如 `http://localhost:3001`）。
- 使用 `bun run build` 的建置產物時，CSP 的 `connect-src` 只允許建置當時 `VITE_API_BASE`／`VITE_API_URL` 的來源；變更 API 位址後請重新建置。

</details>

<details><summary><b>區網內的其他裝置連不上 <code>bun run dev</code> 的前端</b></summary>

Vite 開發與預覽伺服器只監聽 `localhost`，這是刻意的限制（開發伺服器的 `/__open-in-editor` 等端點不應對外開放）。請以 `bun run build` 建置，再由 nginx 等正式網頁伺服器提供 `frontend/build/` 並把 `/api` 反向代理到後端。

</details>

<details><summary><b><code>bun install</code> 失敗，訊息為 <code>lockfile had changes, but lockfile is frozen</code></b></summary>

`frontend/bunfig.toml` 設定 `frozenLockfile = true`，`package.json` 與 `bun.lock` 不一致時安裝直接失敗，不會改寫鎖定的版本。請確認兩個檔案來自同一個版本；有意新增或升級套件時，依 [相依套件](../README.md#相依套件) 更新 `bun.lock` 並一起提交。

</details>

## 檢索與工具

<details><summary><b>每個問題都回報「知識庫中查無相關資料」</b></summary>

先確認已上傳文件，且管理員呼叫 `GET /api/admin/vector-store/info` 時 `total_vectors` 大於 0。索引正常時，可能是相關性門檻太高，請依 [校準相關性門檻](configuration.md#校準相關性門檻) 以實際問答集調整。

</details>

<details><summary><b>核准卡片按下後顯示「無法送出決定，可能已逾時」</b></summary>

待核准項目只保留 300 秒，逾時後 Agent 已視為拒絕並繼續回答，同一項目也只能回覆一次；以發問者以外的帳號回覆同樣會失敗。請重新提問，並在 5 分鐘內按下核准。

</details>

<details><summary><b>只會讀取資料的工具，每次都要求核准</b></summary>

MCP 伺服器預設需要核准，自訂 API 工具則依 HTTP 方法決定。確認工具不會改動外部系統後，管理員可在「AI 工具」頁編輯該工具，取消勾選「AI 呼叫前需使用者在對話中確認」；MCP 伺服器則取消勾選「AI 呼叫此伺服器的工具前需使用者在對話中確認」。

</details>