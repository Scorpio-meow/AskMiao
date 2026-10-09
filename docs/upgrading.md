# 升級指南

[繁體中文](upgrading.md) | [English](upgrading_en.md)

> 本文件說明如何把既有部署升級到新版本，並附上回退步驟與常見問題。每個版本的完整變更見 [CHANGELOG](../CHANGELOG.md)。

- [從 4.0.0 升級到未發行版本](#從-400-升級到未發行版本)
  - [未發行版本的變更與需要的動作](#未發行版本的變更與需要的動作)
  - [升級到未發行版本的步驟](#升級到未發行版本的步驟)
  - [回退到 4.0.0](#回退到-400)
  - [升級到未發行版本後的常見狀況](#升級到未發行版本後的常見狀況)
- [從 3.0.0 升級到 4.0.0](#從-300-升級到-400)
  - [變更與需要的動作](#變更與需要的動作)
  - [升級步驟](#升級步驟)
  - [回退方式](#回退方式)
  - [升級後的常見狀況](#升級後的常見狀況)
- [從 2.x 升級到 3.0.0](#從-2x-升級到-300)
  - [升級總覽](#升級總覽)
  - [步驟 0：停機並備份](#步驟-0停機並備份)
  - [步驟 1：更新程式碼與相依套件](#步驟-1更新程式碼與相依套件)
  - [步驟 2：更新 `.env`](#步驟-2更新-env)
  - [步驟 3：啟動後端並重建索引](#步驟-3啟動後端並重建索引)
  - [步驟 4：確認管理員與工具設定](#步驟-4確認管理員與工具設定)
  - [步驟 5：驗證升級結果](#步驟-5驗證升級結果)
  - [回退到 2.2.x](#回退到-22x)
  - [常見問題](#常見問題)

---

## 從 4.0.0 升級到未發行版本

適用於從 4.0.0 升級到尚未定版號的下一版，完整變更見 [CHANGELOG](../CHANGELOG.md#unreleased)。這一版處理第二輪安全稽核的發現，不需要重建索引，新欄位與工具憑證的加密都會在啟動時自動完成；需要動手的主要是 `.env` 的 10 個新必填設定、相依套件的安裝方式、PostgreSQL 的連線帳號、帳號的建立方式與自訂 API 工具的參數宣告。

### 未發行版本的變更與需要的動作

| 項目 | 4.0.0 | 未發行版本 | 需要的動作 |
|---|---|---|---|
| 必填設定 | 10 項 | 20 項 | 補上 10 項 |
| `HOST`、`RELOAD`、`COOKIE_SECURE` | `HOST`、`RELOAD` 預設 `0.0.0.0`、`true`；`COOKIE_SECURE` 未設定時依 `ENVIRONMENT` 推導 | 必填，沒有預設值 | 依部署方式明確設定 |
| 互動式 API 文件 | 一律提供 `/docs`、`/redoc`、`/openapi.json` | 只在必填的 `ENABLE_API_DOCS` 為 `true` 時提供 | 對外服務時設為 `false` |
| 自行註冊 | 任何能連到 API 的人都能註冊 | `ALLOW_REGISTRATION=false` 時註冊回傳 `403`，帳號以 `scripts/create_user.py` 建立 | 決定是否開放註冊 |
| 登入失敗 | 不限次數 | 同一登入識別或來源位址失敗達門檻後暫停登入，回傳 `429` 與 `Retry-After` | 設定四個 `LOGIN_*` 門檻 |
| 變更密碼 | 既有的權杖繼續有效 | 簽發時間早於 `users.tokens_valid_after` 的權杖一律無效，包含目前的工作階段 | 無；欄位在啟動時自動加入並回填 |
| 工具憑證 | 明文存放，管理 API 原樣回傳 | 以 `TOOL_SECRETS_KEY` 加密存放，管理 API 以 `••••••••` 取代秘密值 | 產生金鑰，並與資料庫備份一起保存 |
| 自訂 API 工具參數 | 模型給的任何參數都會送出 | 只接受 `parameters_schema` 宣告的參數，工具網址中固定的查詢參數不可覆寫 | 檢查每個工具的參數宣告 |
| MCP stdio 子行程 | 在後端行程的工作目錄執行 | 每次在新建的空暫存目錄執行 | 指令與參數中的相對路徑改為絕對路徑 |
| PostgreSQL 容器 | 後端以超級使用者 `postgres` 連線 | 後端以非超級使用者 `POSTGRES_APP_USER` 連線 | 設定帳號、執行一次 `20-app-role.sh`、更新 `DATABASE_URL` |
| 相依套件 | 未鎖定版本，每次安裝取得當下最新版 | `requirements.txt` 鎖定版本與雜湊；`bun.lock` 納入版本控制且安裝時不可變更 | 建議建立新的虛擬環境；新增後端套件改為修改 `requirements.in` |
| 前端建置 | `index.html` 沒有 CSP | 建置時寫入 CSP `<meta>` | 重新建置；API 位於其他來源時在建置時設定 `VITE_API_BASE` |
| API 端點與回應 | 含 `GET /api/external-tags` 與 WebSocket `/api/chat/ws/{user_id}`；管理員使用者 API 回傳 `hashed_password` | 兩個端點移除；回應不再含密碼雜湊與工具憑證，登入可能回傳 `429` | 自行串接的客戶端依 [升級步驟](#升級到未發行版本的步驟) 第 9 點調整 |
| 聊天附件解析 | 與管理員上傳共用同一套解析上限 | 另有較小的記憶體預算，超過時告知模型附件未被讀取 | 無；需要時參考 [資源上限](configuration.md#資源上限) |

### 升級到未發行版本的步驟

1. **停機並備份**：停止後端，備份資料庫（SQLite 直接複製 `.db` 檔，PostgreSQL 以 `pg_dump` 匯出）、`backend/data/`、`backend/keys/` 與 `backend/.env`。新版啟動後會把工具憑證改為加密存放，要回退到 4.0.0 就需要這份資料庫備份。
2. **更新程式碼與相依套件**：
   - 4.0.0 沒有把 `frontend/bun.lock` 納入版本控制。以 git 更新時，先前 `bun install` 產生的這個檔案會讓 `git pull` 以「untracked working tree files would be overwritten by merge」中止，請先刪除它。
   - 後端的 `requirements.txt` 改為鎖定版本並附上雜湊，pip 會自動進入雜湊檢查模式，任何套件與鎖定的雜湊不符就停止安裝。`pip install` 不會移除新版不再使用的套件（FlagEmbedding、waitress、docxtpl、XlsxWriter、langchain、langchain-community，以及改用 PyJWT 後不再需要的 python-jose、ecdsa、rsa、pyasn1、six），建議建立新的虛擬環境再安裝，舊的保留到確定不需回退為止。
   - 使用 NVIDIA GPU 時，先依 PyTorch 官網在新的虛擬環境安裝與 `requirements.txt` 中 `torch` 同版本的 CUDA 版，再安裝其餘套件；已安裝的同版本 torch 會被視為符合鎖定版本。
   - `frontend/bunfig.toml` 改為 `frozenLockfile = true`：`bun install` 只依 `bun.lock` 安裝，`bun.lock` 與 `package.json` 不一致時直接失敗。

   ```bash
   # 在新的虛擬環境中
   cd backend
   pip install -r requirements.txt

   cd ../frontend
   bun install
   ```

   之後新增或升級後端套件時，不要手動編輯 `requirements.txt`：修改 `backend/requirements.in`（只列直接依賴），再於 `backend/` 重新產生：

   ```bash
   uv pip compile requirements.in --universal --python-version 3.10 --generate-hashes -o requirements.txt
   ```

   前端則先把 `frontend/bunfig.toml` 的 `frozenLockfile` 暫時改為 `false`，以 `bun add` 或 `bun remove` 更新後改回 `true`，並一併提交 `package.json` 與 `bun.lock`。
3. **更新 `.env`**：補上以下 10 項必填設定。它們沒有預設值，缺少任一項後端都無法啟動；建議值與 `backend/.env.example` 相同：

   | 設定 | 建議值 | 說明 |
   |---|---|---|
   | `ALLOW_REGISTRATION` | `false` | 是否開放自行註冊。所有帳號共用整個知識庫與已啟用的工具，可公開連線的部署請保持 `false`，改以 `scripts/create_user.py` 建立帳號 |
   | `LOGIN_MAX_FAILURES_PER_ACCOUNT` | `5` | 同一登入識別（不分大小寫）在時間視窗內的失敗次數門檻（≥ 1） |
   | `LOGIN_MAX_FAILURES_PER_ADDRESS` | `20` | 同一來源位址的失敗次數門檻（≥ 1）。經由代理連線時所有使用者共用同一個位址，請設得比依帳號的寬 |
   | `LOGIN_FAILURE_WINDOW_SECONDS` | `900` | 計算失敗次數的時間視窗秒數（≥ 1） |
   | `LOGIN_LOCKOUT_SECONDS` | `900` | 達到門檻後暫停登入的秒數（≥ 1） |
   | `TOOL_SECRETS_KEY` | 每個部署自行產生 | 加密工具憑證的 Fernet 金鑰；範本值不是有效的金鑰，沒換掉時後端拒絕啟動 |
   | `HOST` | `127.0.0.1` | `python main.py` 的監聽位址。只有本機或同一台主機上的反向代理連入時保持 `127.0.0.1`；容器中或其他主機上的反向代理、或其他裝置需要直接連到後端時才改為 `0.0.0.0` |
   | `RELOAD` | `false` | 程式碼變更時自動重新載入，只在開發時設為 `true` |
   | `COOKIE_SECURE` | `false`（以 HTTPS 提供服務時為 `true`） | 重新整理權杖 Cookie 是否只經 HTTPS 傳送。以 HTTPS 提供服務時必須為 `true`，本機以 `http://localhost` 開發時可為 `false`。4.0.0 在 `ENVIRONMENT=production` 時自動加上 Secure，現在必須明確設定 |
   | `ENABLE_API_DOCS` | `false` | 是否提供 `/docs`、`/redoc` 與 `/openapi.json`（列出所有端點與參數），對外服務時請保持 `false` |

   可直接貼進 `.env`，再換上自行產生的 `TOOL_SECRETS_KEY`，並依部署方式調整 `HOST` 與 `COOKIE_SECURE`：

   ```dotenv
   ALLOW_REGISTRATION=false
   LOGIN_MAX_FAILURES_PER_ACCOUNT=5
   LOGIN_MAX_FAILURES_PER_ADDRESS=20
   LOGIN_FAILURE_WINDOW_SECONDS=900
   LOGIN_LOCKOUT_SECONDS=900
   TOOL_SECRETS_KEY=<自行產生的 Fernet 金鑰>
   HOST=127.0.0.1
   RELOAD=false
   COOKIE_SECURE=false
   ENABLE_API_DOCS=false
   ```

   在 `backend/`（已啟用虛擬環境）產生 `TOOL_SECRETS_KEY`：

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   **`TOOL_SECRETS_KEY` 要與資料庫備份一起保存**：金鑰遺失或更換後，已儲存的工具憑證都無法解密（管理 API 的回應以 `credentials_unreadable` 標示），只能逐一重新輸入。
4. **PostgreSQL**：
   - **使用 `backend/docker-compose.yml` 時**，在 `backend/.env` 加上 `POSTGRES_APP_USER`（例如 `askmiao_app`）與 `POSTGRES_APP_PASSWORD`（與 `POSTGRES_PASSWORD` 不同的隨機字串），新的 compose 檔缺少這兩項時會拒絕啟動。既有的資料卷不會再執行初始化腳本，所以先以新設定重新建立容器（資料卷會保留），讓容器取得這兩個環境變數與 `20-app-role.sh` 的掛載，再手動執行一次腳本：

     ```bash
     cd backend
     docker compose up -d --wait
     docker compose exec postgres bash /docker-entrypoint-initdb.d/20-app-role.sh
     ```

     腳本以容器中的 `POSTGRES_USER`（`postgres`）連到 `POSTGRES_DB`（`chatbot`），建立 `POSTGRES_APP_USER` 帳號（`NOSUPERUSER NOCREATEDB NOCREATEROLE`）並把密碼設為 `POSTGRES_APP_PASSWORD`，授予資料庫的 `CONNECT` 與 `public` schema 的 `USAGE`、`CREATE`，再把 `public` 中所有資料表的擁有者改為這個帳號。腳本可重複執行。
   - **自行架設的 PostgreSQL**：以超級使用者建立同樣權限的帳號並移交資料表。有 `bash` 與 `psql` 時可以直接執行同一支腳本，以環境變數提供上述四個值，連線位置以 `PGHOST`、`PGPORT` 指定：

     ```bash
     cd backend
     POSTGRES_USER=<超級使用者> POSTGRES_DB=<資料庫> POSTGRES_APP_USER=askmiao_app POSTGRES_APP_PASSWORD=<密碼> \
       PGHOST=<主機> PGPORT=<埠號> bash init-app-role.sh
     ```

     沒有 `bash` 時，請以超級使用者執行腳本中的 SQL。
   - 最後把 `DATABASE_URL` 改用這個帳號，compose 的資料庫為 `postgresql+psycopg2://askmiao_app:<POSTGRES_APP_PASSWORD>@localhost:7690/chatbot`（特殊字元需百分比編碼）。`POSTGRES_PASSWORD` 只留給管理用途。
5. **啟動後端**：`python main.py`。啟動時 `upgrade_schema()` 會：
   - 替 `users` 加上 `tokens_valid_after` 欄位並以 `created_at` 回填，既有的權杖與工作階段繼續有效；之後變更密碼時會更新為當下，簽發時間更早的權杖一律無效。
   - 以 `TOOL_SECRETS_KEY` 加密 `custom_api_tools` 的 `headers`、`auth_config` 與 `mcp_servers` 的 `env_vars`、`headers` 中既有的明文，已加密的不變。內容不是有效 JSON 的值會被清空，日誌會提示重新輸入。
6. **建立帳號**：`ALLOW_REGISTRATION=false` 時，`POST /api/auth/register` 回傳 `403`，登入頁也不顯示註冊入口；既有帳號不受影響。新帳號（含管理員）由管理員在 `backend/`（已啟用虛擬環境）建立，密碼以互動方式輸入兩次，套用與註冊相同的規則：

   ```bash
   python scripts/create_user.py --username <使用者名稱> --email <電子郵件>
   python scripts/create_user.py --username <使用者名稱> --email <電子郵件> --admin   # 建立管理員
   ```
7. **檢查工具設定**：以管理員進入「AI 工具」：
   - 自訂 API 工具只接受 `parameters_schema` 的 `properties` 中宣告的參數（包含路徑、查詢、標頭與本文參數，以及 `request_body`），沒有宣告任何參數的工具不再接受參數。`request_body_schema` 有 `properties` 時，`request_body` 的欄位也必須列在其中，除非設定 `"additionalProperties": true`。
   - 工具網址中寫死的查詢參數由管理員固定，呼叫時提供同名參數會被拒絕；`parameters_schema` 宣告了與網址查詢參數同名的參數時，請擇一移除。
   - 對每個自訂 API 工具執行「即時線上測試」：結果的 `status_code` 為 `400`、錯誤以「工具參數無效」開頭時，依訊息補上宣告或移除衝突的參數。以 OpenAPI 匯入的工具通常已宣告規格中的參數，主要需要檢查手動建立的工具。
   - stdio MCP 伺服器改在每次新建的空暫存目錄中執行，不再以後端的啟動目錄為工作目錄：`command`、`args` 中的相對路徑請改為絕對路徑，原本從工作目錄的 `.env` 讀取設定的伺服器請把變數寫進 `env_vars`。HTTP MCP 伺服器只跟隨同一來源的轉址，網址會轉址到其他網域時請改填最終網址。修改後按「重新探索」；名稱不符合 `[A-Za-z0-9_.-]{1,128}` 的工具會被略過。
8. **重新建置前端**：在 `frontend/` 執行 `bun run build`。CSP 的 `<meta>` 只在建置時寫入 `build/index.html`，開發伺服器不套用：
   - 前端與 API 不同來源時，`VITE_API_BASE`（或 `VITE_API_URL`）必須在建置時設定（`frontend/.env` 或建置時的環境變數），這個來源會加入 `connect-src`；之後更換 API 位址需要重新建置。
   - `<meta>` 無法設定 `frame-ancestors`，網頁伺服器仍要送出 `X-Frame-Options: DENY` 或 `Content-Security-Policy: frame-ancestors 'none'`。
   - 腳本與樣式只允許同源與 `index.html` 內嵌內容的雜湊，圖片只允許同源與 `data:`、`blob:`；自行在 `index.html` 加入其他網站資源的部署，這些資源會被擋下。
9. **自行串接 API 的客戶端**：
   - `GET /api/external-tags` 與 WebSocket `/api/chat/ws/{user_id}` 已移除。
   - `POST /api/api-tools/parse-spec` 的回應不再包含 `raw_spec`；使用 YAML 別名的規格回傳 `400`。
   - `GET /api/admin/users` 與 `PUT /api/admin/users/{user_id}` 中的使用者只含 `id`、`username`、`email`、`role`、`is_active`、`is_admin`、`created_at`、`last_login`，不再有 `hashed_password`；`PUT` 回傳 `{message, user}`。
   - 自訂 API 工具與 MCP 伺服器的管理 API 回應以 `••••••••` 取代秘密值，並新增 `credentials_unreadable`。更新時整個欄位以送出的內容取代，值為 `••••••••` 的鍵沿用原值，該鍵沒有已儲存的值時回傳 `400`。
   - `approval_required` 事件新增 `target`，標出實際送出的位置。
   - `POST /api/auth/login` 可能回傳 `429` 與 `Retry-After`；關閉註冊時 `POST /api/auth/register` 回傳 `403`，可先以 `GET /api/auth/registration`（回傳 `{"enabled": bool}`）查詢。
   - `POST /api/auth/change-password` 或帶 `new_password` 的 `PUT /api/auth/me` 成功後，包含目前這一個在內的所有權杖都失效，需以新密碼重新登入。
   - `/docs`、`/redoc` 與 `/openapi.json` 只在 `ENABLE_API_DOCS=true` 時提供。
10. **驗證**：
    - [ ] `GET http://localhost:8001/health` 回傳 `{"status": "healthy"}`；`ENABLE_API_DOCS=false` 時 `/docs` 回傳 `404`。
    - [ ] 以 `create_user.py` 建立的帳號可以登入；`ALLOW_REGISTRATION=false` 時登入頁沒有註冊入口。
    - [ ] 測試帳號連續輸入錯誤密碼達 `LOGIN_MAX_FAILURES_PER_ACCOUNT` 次後，下一次登入回傳 `429`（重新啟動後端即可解除）。
    - [ ] 在一個瀏覽器變更測試帳號的密碼後，目前與其他瀏覽器的工作階段都要以新密碼重新登入。
    - [ ] 「AI 工具」中的金鑰以 `••••••••` 顯示，「即時線上測試」仍能呼叫需要認證的 API；資料庫中這些憑證欄位的值以 `fernet:` 開頭。
    - [ ] 使用 PostgreSQL 時，在 `psql` 執行 `\dt` 列出的資料表擁有者是應用程式帳號（compose：`docker compose exec postgres psql -U postgres -d chatbot -c '\dt'`）。
    - [ ] `frontend/build/index.html` 含有 `<meta http-equiv="Content-Security-Policy"`，使用時瀏覽器主控台沒有 CSP 違規訊息。

### 回退到 4.0.0

1. 停止後端，把程式碼切回 4.0.0。後端改回升級前保留的虛擬環境，或在新的虛擬環境依 4.0.0 的 `requirements.txt`（沒有鎖定版本與雜湊）安裝；前端的 `package.json` 沒有變更，以 4.0.0 的程式碼重新執行 `bun run build` 即可。
2. 還原步驟 1 備份的 `.env`。4.0.0 會忽略不認得的設定，留下 `ALLOW_REGISTRATION`、`TOOL_SECRETS_KEY` 等新設定不會出錯，但 `DATABASE_URL` 必須與還原後的資料庫一致。
3. 資料庫二擇一：
   - **還原備份**（建議）：最乾淨，但會遺失升級後新增的對話、文件與帳號。工具憑證已改為加密存放，4.0.0 無法解讀，會當成沒有設定。
   - **保留現有資料庫**：在 4.0.0 重新輸入每個自訂 API 工具與 MCP 伺服器的憑證。4.0.0 會忽略 `users.tokens_valid_after` 欄位；但由新版建立的全新資料庫中，這個欄位是 `NOT NULL` 且沒有預設值，4.0.0 建立帳號時會失敗，請先移除此欄位或給定預設值。日後再次升級時，回退期間建立的帳號此欄位為空值，新版每次啟動都會以 `created_at` 補上，不需要手動處理。
4. PostgreSQL 容器：4.0.0 的 `backend/docker-compose.yml` 不需要 `POSTGRES_APP_USER`、`POSTGRES_APP_PASSWORD`，以 `docker compose up -d` 重新建立容器即可，留在資料卷中的應用程式帳號不影響 4.0.0。以 `postgres` 還原 `pg_dump` 備份後資料表屬於 `postgres`，請沿用備份 `.env` 中以 `postgres` 連線的 `DATABASE_URL`；保留現有資料庫時資料表屬於應用程式帳號，4.0.0 可以繼續用它連線。

### 升級到未發行版本後的常見狀況

<details>
<summary><b>後端啟動失敗，錯誤訊息出現 <code>Field required</code></b></summary>

`.env` 缺少新的必填設定。錯誤訊息會列出每個缺少的欄位，依 [升級步驟](#升級到未發行版本的步驟) 第 3 點補上，建議值見 `backend/.env.example`。

</details>

<details>
<summary><b>後端啟動失敗，訊息為「TOOL_SECRETS_KEY 必須是 Fernet 金鑰」</b></summary>

`TOOL_SECRETS_KEY` 仍是範本值或不是有效的 Fernet 金鑰，請以 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 產生。若已經用某把金鑰加密過憑證，請改回那把金鑰，新的金鑰無法解密既有的憑證。

</details>

<details>
<summary><b>登入回傳 <code>429</code></b></summary>

同一登入識別或同一來源位址在 `LOGIN_FAILURE_WINDOW_SECONDS` 秒內失敗達到門檻，登入會暫停 `LOGIN_LOCKOUT_SECONDS` 秒，期間即使密碼正確也不接受。等 `Retry-After` 標頭指出的秒數過後再試；失敗紀錄只存在後端行程的記憶體中，重新啟動後端也會立即解除。

經由反向代理連線而沒有設定 `FORWARDED_ALLOW_IPS` 時，所有使用者的來源位址都是代理本身，依位址的門檻由所有人共用。代理會覆寫 `X-Forwarded-For` 時請設定 `FORWARDED_ALLOW_IPS`，否則調高 `LOGIN_MAX_FAILURES_PER_ADDRESS`。

</details>

<details>
<summary><b>工具憑證無法解密（<code>credentials_unreadable</code>）</b></summary>

管理 API 的回應中 `credentials_unreadable` 為 `true`、憑證欄位為 `null`；對這些工具執行線上測試或「重新探索」時回傳 `400`，訊息為「無法以目前的 TOOL_SECRETS_KEY 解密工具憑證，請重新輸入」，Agent 呼叫時則失敗並只回報錯誤代碼。這表示目前的 `TOOL_SECRETS_KEY` 不是加密時使用的金鑰：找得回原本的金鑰就改回並重新啟動後端；找不回時，在「AI 工具」重新輸入這些自訂 API 工具與 MCP 伺服器的憑證並儲存。送回遮蔽字樣 `••••••••` 的欄位因為沒有可沿用的值，會回傳 `400`。

</details>

<details>
<summary><b>自訂 API 工具回傳 <code>status_code</code> <code>400</code>：「工具參數無效」</b></summary>

- 「未宣告的參數 …」：參數沒有列在 `parameters_schema` 的 `properties`；以 `request_body.` 開頭的名稱表示本文欄位沒有列在 `request_body_schema` 的 `properties`。請補上宣告；本文欄位不固定時，可在 `request_body_schema` 設定 `"additionalProperties": true`。
- 「不可覆寫工具網址中固定的查詢參數 …」：呼叫提供了與工具網址中查詢參數同名的參數，請從網址或 `parameters_schema` 擇一移除。

</details>

<details>
<summary><b>註冊回傳 <code>403</code></b></summary>

這是 `ALLOW_REGISTRATION=false` 時的預期行為，回應訊息為「目前不開放註冊，請聯繫管理員建立帳號」。請由管理員以 `scripts/create_user.py` 建立帳號，見 [升級步驟](#升級到未發行版本的步驟) 第 6 點；確定要開放註冊時，才把 `ALLOW_REGISTRATION` 設為 `true` 並重新啟動後端。

</details>

<details>
<summary><b>PostgreSQL 回報 <code>must be owner of table</code> 或 <code>permission denied for table</code></b></summary>

後端已改以應用程式帳號連線，但資料表仍屬於 `postgres`，代表 `20-app-role.sh` 還沒執行。腳本可重複執行，執行一次就會把 `public` 中的所有資料表交給應用程式帳號，見 [升級步驟](#升級到未發行版本的步驟) 第 4 點。

- 執行腳本時出現 `No such file or directory`：容器仍是以舊的 compose 設定建立，沒有掛載腳本，請先執行 `docker compose up -d --wait` 重新建立。
- 連線時出現 `password authentication failed`：應用程式帳號尚未建立，或 `DATABASE_URL` 中的帳號密碼與 `POSTGRES_APP_USER`、`POSTGRES_APP_PASSWORD` 不一致。腳本每次執行都會把密碼重設為目前的 `POSTGRES_APP_PASSWORD`。

</details>

<details>
<summary><b><code>bun install</code> 失敗：<code>lockfile had changes, but lockfile is frozen</code></b></summary>

`package.json` 與 `bun.lock` 不一致。沒有打算變更前端套件時，把這兩個檔案還原成版本庫中的內容再安裝。要變更套件時，訊息建議的「不加 `--frozen-lockfile` 重新執行」並不適用，因為這個設定來自 `frontend/bunfig.toml`：先把其中的 `frozenLockfile` 暫時改為 `false`，以 `bun add` 或 `bun remove` 更新後改回 `true`，並一併提交 `package.json` 與 `bun.lock`。

</details>

<details>
<summary><b><code>pip install -r requirements.txt</code> 回報雜湊錯誤</b></summary>

`requirements.txt` 的每個套件都附上雜湊，pip 會以雜湊檢查模式安裝：

- `THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE`：下載到的檔案與鎖定時的不同。手動改過 `requirements.txt` 的版本時，請改從 `requirements.in` 重新產生；使用 PyPI 以外的套件來源（例如私有鏡像）時，確認它提供的是與 PyPI 相同的檔案。都不是時檔案可能遭到竄改，不要略過檢查。
- `Hashes are required in --require-hashes mode` 或 `all requirements must have their versions pinned with ==`：`requirements.txt` 中有沒有雜湊或沒有固定版本的套件，多半是手動加入的。請改為修改 `requirements.in`，再以 `uv pip compile` 重新產生。

</details>

---

## 從 3.0.0 升級到 4.0.0

適用於從 3.0.0 升級到 4.0.0，完整變更見 [CHANGELOG](../CHANGELOG.md#400---2026-09-27)。這一版是安全性修正，不需要重建索引，資料表的新欄位會在啟動時自動加入；需要動手的主要是 `.env`、`backend/keys/`、PostgreSQL 容器與前端的對外提供方式。

### 變更與需要的動作

| 項目 | 3.0.0 | 4.0.0 | 需要的動作 |
|---|---|---|---|
| JWT 簽署 | RSA 金鑰無法載入時，開發環境退回 HS256（`JWT_SECRET_KEY`） | 一律 RS256，金鑰無法載入或產生時拒絕啟動 | 確認 `backend/keys/` 存在且後端帳號可寫入；`JWT_SECRET_KEY`、`JWT_ALGORITHM` 可從 `.env` 刪除 |
| 權杖驗證 | 身分與 `is_admin` 取自權杖內容 | 每次請求依 `sub` 讀取資料庫帳號，停用或刪除的帳號立即失效 | 無；既有權杖在帳號仍存在且啟用時繼續有效 |
| 重新整理權杖 | `POST /api/auth/refresh` 讀取不存在的聲明而一律失敗 | 可以正常換發，且每個重新整理權杖只能使用一次 | 自行呼叫此端點的客戶端需改用每次回應的新 Cookie |
| PostgreSQL 容器 | 內建密碼 `postgres`，埠號對所有介面開放 | 必須設定 `POSTGRES_PASSWORD`，只綁定 `127.0.0.1:7690` | 設定 `POSTGRES_PASSWORD` 並更新 `DATABASE_URL` |
| 前端開發伺服器 | 監聽所有介面，區網可連 | 只監聽 `localhost`，並送出反框架標頭 | 區網使用者改用建置產物與正式網頁伺服器 |
| 速率限制的來源 IP | uvicorn 預設可能採信 `X-Forwarded-For` | 只採信 `FORWARDED_ALLOW_IPS` 指定的代理 | 前方有會覆寫該標頭的反向代理時設定 `FORWARDED_ALLOW_IPS` |
| 工具呼叫 | Agent 直接執行 | `requires_approval` 的工具先經使用者核准 | 欄位自動加入；依需要調整各工具的旗標 |
| MCP 範本 | `mcp_fetch`、`mcp_filesystem`（根目錄 `./data`） | 移除 `mcp_fetch`；`mcp_filesystem` 改用 `backend/mcp_filesystem_sandbox` 並釘選版本 | 檢查以舊範本建立的伺服器 |
| 出站代理 | 自訂 API 工具、MCP HTTP 與 `web_fetch` 會讀取 `HTTP(S)_PROXY` | 一律直接連線，連線固定在 SSRF 驗證過的 IP | 需要經代理連外的環境請改由網路層處理 |
| 訊息回應 | 含原始 `context_used` 字串 | `/api/chat` 的回應中 `context_used` 一律為 `null` | 改讀 `sources`、`sources_detail`、`research_trace`、`attachments` |
| 資源上限 | 大多沒有上限 | 請求本文、訊息、附件、工具結果、同時串流數等都有上限 | 無；需要時參考 [資源上限](configuration.md#資源上限) |

### 升級步驟

1. **停機並備份**：停止後端，備份資料庫、`backend/data/`、`backend/keys/` 與 `backend/.env`。
2. **更新程式碼**：取得新版程式碼後，在 `backend/` 執行 `pip install -r requirements.txt`，在 `frontend/` 執行 `bun install`。
3. **整理 `.env`**：
   - 刪除 `JWT_SECRET_KEY` 與 `JWT_ALGORITHM`。留著也不會出錯，後端會忽略。
   - 後端前方有會「覆寫」`X-Forwarded-For` 的反向代理（例如 nginx 的 `proxy_set_header X-Forwarded-For $remote_addr;`）時，加上 `FORWARDED_ALLOW_IPS=<代理位址>`；經由 Vite 開發代理時**不要**設定。
4. **確認 RSA 金鑰**：`backend/keys/jwt_private.pem` 與 `jwt_public.pem` 必須存在且可讀；沒有金鑰時後端會在首次啟動產生，因此目錄需要能讓後端帳號寫入。沿用原本的金鑰，既有的權杖就不會失效。
5. **PostgreSQL 容器（使用 `backend/docker-compose.yml` 時）**：
   - 在 `backend/.env` 加上 `POSTGRES_PASSWORD=<隨機字串>`，未設定時 `docker compose` 會拒絕啟動。
   - 既有的資料卷已以舊密碼 `postgres` 初始化，`POSTGRES_PASSWORD` 只在第一次初始化時生效。請先以舊設定啟動容器並改掉密碼，再更新 `DATABASE_URL`：

     ```bash
     cd backend
     docker compose exec postgres psql -U postgres -c "ALTER USER postgres PASSWORD '<新密碼>';"
     ```

   - 把 `DATABASE_URL` 改成 `postgresql+psycopg2://postgres:<新密碼>@localhost:7690/chatbot`（特殊字元需百分比編碼），再以 `docker compose up -d` 重新建立容器，套用只綁定 `127.0.0.1` 的埠號設定。
6. **啟動後端**：`python main.py`。啟動時 `upgrade_schema()` 會替 `custom_api_tools` 與 `mcp_servers` 加上 `requires_approval` 欄位並回填：API 工具的方法不是 `GET`、`HEAD`、`OPTIONS` 時為 `true`，MCP 伺服器一律為 `true`。
7. **檢查工具設定**：以管理員進入「AI 工具」：
   - 依實際行為調整各工具的「需使用者確認」。`GET` 工具預設不需確認，若它會改變狀態或把資料送往外部，請打開。
   - 以舊版 `mcp_fetch` 範本建立的伺服器不會被刪除，但它繞過 `web_fetch` 的出站防護，建議刪除或停用。
   - 以舊版 `mcp_filesystem` 範本建立的伺服器仍指向 `./data`（後端的資料目錄），請改為 `backend/mcp_filesystem_sandbox` 的絕對路徑或其他專屬目錄，並把套件釘選到審閱過的版本，再按「重新探索」。
8. **前端的對外提供**：`bun run dev` 與 `bun run preview` 只監聽 `localhost`。原本讓區網裝置直接連開發伺服器的部署，請改以 `bun run build` 建置，由 nginx 等正式網頁伺服器提供 `frontend/build/`、反向代理 `/api`，並送出 `X-Frame-Options: DENY` 或 `Content-Security-Policy: frame-ancestors 'none'`。
9. **驗證**：
   - [ ] 登入後閒置超過存取權杖效期，前端能自動換發並繼續使用。
   - [ ] 停用某位測試帳號後，該帳號下一個請求立即回傳 `401`。
   - [ ] 呼叫一個需要核准的工具時，聊天畫面出現確認卡片，拒絕後 Agent 改以既有資料回答。
   - [ ] 自行串接 API 的客戶端已改讀解析後的訊息欄位，不再依賴 `context_used`，並能處理 `approval_required` 事件。

### 回退方式

1. 停止後端，把程式碼切回 3.0.0，還原 `.env`（3.0.0 需要 `JWT_SECRET_KEY`）。
2. 資料庫可以沿用：3.0.0 會忽略新增的 `requires_approval` 欄位。例外是由新版建立的全新資料庫，其中這兩個欄位是 `NOT NULL` 且沒有預設值，3.0.0 新增工具時會失敗，請先移除這兩個欄位或給定預設值。
3. `backend/docker-compose.yml` 回到 3.0.0 版本時會改用內建密碼 `postgres` 的設定；若已改過資料庫密碼，`DATABASE_URL` 維持新密碼即可。

### 升級後的常見狀況

<details>
<summary><b>後端啟動失敗，錯誤與 <code>backend/keys</code> 或 RSA 金鑰有關</b></summary>

新版不再退回 HS256。請確認 `backend/keys/` 存在、後端帳號可以寫入（首次產生金鑰時需要），且 `jwt_private.pem`、`jwt_public.pem` 沒有損毀。以容器或唯讀檔案系統部署時，請把事先產生好的金鑰掛載進去。

</details>

<details>
<summary><b><code>docker compose up</code> 回報需要設定 <code>POSTGRES_PASSWORD</code></b></summary>

compose 檔已不含內建密碼。請在 `backend/.env`（或殼層環境）設定 `POSTGRES_PASSWORD`，既有資料卷的密碼需另外以 `ALTER USER` 修改，見 [升級步驟](#升級步驟) 第 5 點。

</details>

<details>
<summary><b>區網裝置連不上前端</b></summary>

開發與預覽伺服器只監聽 `localhost`，這是刻意的限制。請改以建置產物搭配正式網頁伺服器提供服務，見 [升級步驟](#升級步驟) 第 8 點。

</details>

<details>
<summary><b>所有使用者共用同一個速率限制額度</b></summary>

未設定 `FORWARDED_ALLOW_IPS` 時，速率限制以實際連線對端計算；經由反向代理時所有人的來源 IP 都是代理本身。代理會覆寫 `X-Forwarded-For` 時，把代理位址設為 `FORWARDED_ALLOW_IPS`；否則請調高 `RATE_LIMIT_PER_MINUTE`。

</details>

<details>
<summary><b>送出訊息回傳 <code>400</code>、<code>413</code>、<code>422</code> 或 <code>429</code></b></summary>

- `400`：`model_name` 不在可用模型清單內，請改用 `GET /api/chat/models` 列出的模型，或把它加進 `AVAILABLE_MODELS`。
- `413`：請求本文超過上限，或該使用者的附件儲存量已達 200 MiB，刪除含附件的舊對話即可。
- `422`：訊息超過 20,000 字、附件超過 5 個、單一附件超過 15 MiB 或合計超過 20 MiB。
- `429`：同一位使用者已有 2 個回答正在串流。

</details>

---

## 從 2.x 升級到 3.0.0

3.0.0 是主版本升級，索引格式、必填設定與工具管理權限都有不相容的變更。實際操作約 15 分鐘，另加一次索引重建的時間：重建會逐份文件重新擷取文字、呼叫 LLM 生成摘要並計算向量，所需時間與文件量成正比。

### 升級總覽

| 項目 | 2.2.x | 3.0.0 | 需要的動作 |
|---|---|---|---|
| 片段與索引 | FAISS、`documents.pkl`、BM25 依清單位置對齊 | 資料庫 `rag_chunks` 為準，FAISS 與 BM25 以 chunk_id 對應 | 升級後重建一次索引 |
| 檢索融合 | 加權正規化分數（`HYBRID_ALPHA`） | 標準 RRF（`RRF_K`）加上重排機率門檻 | 補上新設定 |
| 必填設定 | 3 項 | 11 項 | 補上 8 項 |
| 重排模型 | 載入失敗時略過重排 | 必要元件，載入失敗無法啟動 | 確認模型快取或網路可用 |
| 工具管理 | 任何登入者 | 只限管理員 | 確認至少有一位管理員 |
| MCP `stdio` 環境變數 | 繼承後端全部環境變數 | 只繼承系統必要變數 | 伺服器需要的變數寫進 `env_vars` |
| MCP HTTP 位址 | 未驗證 | 每次請求與轉址都做 SSRF 驗證 | 本機或內網的伺服器改用 `stdio` |
| Hugging Face 快取 | 預設 `./data/hf_home` | 未設定時為 `~/.cache/huggingface` | 要沿用舊快取時明確設定 `HF_HOME` |
| 內建模型清單 | GPT-4o、o 系列等 | GPT-6 / GPT-5.6、Claude 5 系列、Gemini 3.x | 仍要用舊模型時寫進 `AVAILABLE_MODELS` |

### 步驟 0：停機並備份

升級會改寫索引檔，請先停止後端，再備份以下項目：

- **資料庫**：SQLite 直接複製 `.db` 檔；PostgreSQL 以 `pg_dump` 匯出。
- **`backend/data/`**：向量索引 `faiss_index.bin`、`documents.pkl`、`index_metadata.pkl`、`bm25_index/`、上傳檔 `uploads/`，以及模型快取 `hf_home/`（若有）。
- **`backend/.env`**。

### 步驟 1：更新程式碼與相依套件

```bash
# 取得 3.0.0 的程式碼後
cd backend
pip install -r requirements.txt   # 3.0.0 新增官方 anthropic SDK

cd ../frontend
bun install
```

### 步驟 2：更新 `.env`

#### 新增的必填設定

以下 8 項沒有預設值，缺少任一項後端都無法啟動。建議值與 `backend/.env.example` 相同：

| 設定 | 建議值 | 說明 |
|---|---|---|
| `ENABLE_WEB_SEARCH` | `true` | 是否提供 `web_search` 與 `web_fetch` 兩個聯網工具 |
| `AGENT_MAX_TURNS` | `5` | 單次提問的工具呼叫輪數上限（≥ 1） |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | 提問時從資料庫帶入的前文訊息數（0 表示不帶） |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | `web_fetch` 可讀取的網域（含子網域，逗號分隔）；明確寫 `*` 才表示不限制 |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | 同一次提問讀過知識庫內容後，拒絕聯網工具 |
| `RRF_K` | `60` | RRF 融合常數 |
| `RERANK_RELEVANCE_THRESHOLD` | `0.2` | 重排機率低於此值的片段視為無關（暫定值，見 [門檻校準](configuration.md#校準相關性門檻)） |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | 領域設定檔路徑（相對路徑以 `backend/` 為基準） |

可直接貼進 `.env`：

```dotenv
ENABLE_WEB_SEARCH=true
AGENT_MAX_TURNS=5
CONVERSATION_HISTORY_MESSAGES=6
WEB_FETCH_ALLOWED_DOMAINS=*
BLOCK_WEB_TOOLS_AFTER_KB=true
RRF_K=60
RERANK_RELEVANCE_THRESHOLD=0.2
DOMAIN_PROFILE_PATH=config/domain_profile.json
```

> [!IMPORTANT]
> 使用 Claude 模型時還要設定 `ANTHROPIC_MAX_TOKENS`（例如 `16000`），否則呼叫 Claude 時會回報「使用 Claude 模型前需在 .env 設定 ANTHROPIC_MAX_TOKENS」。

#### 可以刪除的設定

以下設定已移除，留在 `.env` 中會被忽略：

`HYBRID_ALPHA`、`NORMALIZATION`、`FINAL_THRESHOLD`、`DOCUMENTS_PATH`、`ENABLE_AUTO_REINDEX`、`ENABLE_AUTO_REINDEX_TASK`、`REINDEX_HOURS`、`TRANSFORMERS_CACHE`、`HUGGINGFACE_HUB_CACHE`。

#### 行為改變、需要確認的設定

- **Hugging Face 快取**：2.2.x 預設把模型放在 `./data/hf_home`，3.0.0 未設定 `HF_HOME` 時改用 `~/.cache/huggingface`。要沿用既有快取、避免重新下載嵌入與重排模型（約 1.2 GB），請明確設定 `HF_HOME=./data/hf_home`；原本的 `HUGGINGFACE_HUB_CACHE` 改名為 `HF_HUB_CACHE`。
- **預設模型**：`OPENAI_VISION_MODEL` 預設改為 `gpt-6-sol`、`GEMINI_VISION_MODEL` 改為 `gemini-3.5-flash`（兩者用於 PDF 掃描頁 OCR）；內建模型清單不再包含 `gpt-4o`、`o1`、`o3`、`gemini-2.5-flash` 等舊型號。仍要使用舊型號時，請在 `AVAILABLE_MODELS` 與上述兩個設定中明確寫出。
- **相對路徑**：`DATA_DIR`、`UPLOAD_DIR`、索引路徑、`HF_*`、`DOMAIN_PROFILE_PATH` 與 `JIEBA_DICTIONARY` 的相對路徑一律以 `backend/` 為基準，不再依啟動目錄而定。
- **`RERANK_TOP_K`**：程式預設值為 50，`.env.example` 建議 20。CPU 上重排每對約 0.2 至 0.4 秒，候選數越多每次檢索越慢。

每個設定的完整說明見 [設定參考](configuration.md)。

### 步驟 3：啟動後端並重建索引

```bash
cd backend
python main.py
```

首次啟動時會依序看到：

1. **設定驗證**：缺少必填設定時，啟動會以 `Field required` 錯誤列出缺少的欄位。
2. **載入模型**：嵌入模型與重排模型；重排模型無法載入時會以「無法載入重排模型」結束啟動。
3. **偵測到舊版索引**：日誌出現「偵測到舊版（依位置對齊）的 FAISS 索引格式」，原檔改名為 `faiss_index.bin.legacy.bak`。
4. **知識庫暫時是空的**：新的 `rag_chunks` 資料表還沒有片段，必須重建索引後才檢索得到既有文件。

接著以下列任一方式重建索引：

| 方式 | 操作 | 適合情境 |
|---|---|---|
| 前端 | 以管理員登入 →「知識庫」→「重建索引」 | 文件量不大、想在畫面上看到結果 |
| API | `POST /api/documents/rebuild-index`（需管理員存取權杖） | 自動化部署流程 |
| 離線腳本 | **停止後端後**，在 `backend/` 執行 `python scripts/reprocess_existing_docs.py` | 文件量大、不想佔用線上服務 |

```bash
# API 方式
curl -X POST http://localhost:8001/api/documents/rebuild-index \
  -H "Authorization: Bearer <管理員的 access_token>"
```

重建會對資料庫中的每份文件：重新從 `UPLOAD_DIR` 擷取文字（檔案不在時改用資料庫內容）、重新生成 AI 摘要、依目前的 `CHUNK_SIZE` / `CHUNK_OVERLAP` 切塊，並寫入 `rag_chunks`、FAISS 與 BM25。確認問答正常後，即可刪除 `backend/data/` 內的 `faiss_index.bin.legacy.bak` 與 `documents.pkl`。

> [!NOTE]
> 之後不需要再手動重建：後端每次啟動都會依 `rag_chunks` 自動校正 FAISS 與 BM25；更換嵌入模型（向量維度改變）時，舊索引會改名為 `*.mismatch.bak` 並自動重新計算向量。

### 步驟 4：確認管理員與工具設定

- **至少一位管理員**：「AI 工具」、「知識庫」與「管理後台」都只限管理員。還沒有管理員時，請依 [README：建立第一位管理員](../README.md#4-建立第一位管理員) 操作。
- **MCP `stdio` 伺服器**：子行程只繼承系統必要變數（Windows 為 `PATH`、`SYSTEMROOT`、`USERPROFILE` 等，其他平台為 `HOME`、`PATH`、`SHELL` 等）。依賴後端環境變數的伺服器（例如 `HTTP_PROXY`、`HTTPS_PROXY`、`NODE_EXTRA_CA_CERTS` 或各種存取權杖），請把變數寫進該伺服器的 `env_vars`，再按「重新探索」。
- **MCP HTTP 伺服器**：指向 `localhost` 或內網位址的伺服器，探索會失敗，`last_error` 會註明遭 SSRF 防護拒絕並附錯誤代碼。本機的 MCP 伺服器請改用 `stdio` 傳輸。
- **自訂 API 工具**：出站請求的每一次轉址都會重新做 SSRF 驗證，轉址到內網位址的 API 會被拒絕（測試結果的 `status_code` 為 `403`）。

### 步驟 5：驗證升級結果

- [ ] `GET http://localhost:8001/health` 回傳 `{"status": "healthy"}`。
- [ ] `http://localhost:8001/docs` 標題為「AskMiao API」，版本為 `3.0.0`。
- [ ] 管理員呼叫 `GET /api/admin/vector-store/info`：`index_type` 為 `FAISS IndexIDMap2(IndexFlatIP) + Whoosh BM25`，`total_vectors` 大於 0。
- [ ] 問一個知識庫涵蓋的問題：答案附 `[n]` 引用，下方來源標籤可點開原文片段。
- [ ] 問一個知識庫沒有的問題：Agent 照實回報查無資料，而不是硬湊答案。
- [ ] （建議）以實際問答集執行 `python scripts/evaluate_retrieval.py --golden <問答集> --k 1 3 5 --relevance-thresholds 0.1 0.2 0.3`，校準 `RERANK_RELEVANCE_THRESHOLD`。

### 回退到 2.2.x

1. 停止後端，把程式碼切回 2.2.x。
2. 以步驟 0 的備份還原 `backend/data/` 與 `.env`。3.0.0 寫出的 FAISS 索引以 chunk_id 為鍵，2.2.x 無法正確使用。
3. 資料庫二擇一：
   - **還原備份**：最乾淨，但會遺失升級後新增的對話與文件。
   - **保留現有資料庫**：2.2.x 會忽略 `rag_chunks` 資料表。升級後新增的文件不在還原的索引內，請在 2.2.x 呼叫 `POST /api/documents/rebuild-index` 重建。

### 常見問題

<details>
<summary><b>啟動失敗，錯誤訊息出現 <code>Field required</code></b></summary>

`.env` 缺少必填設定。錯誤訊息會列出缺少的欄位名稱，依 [步驟 2](#步驟-2更新-env) 補上即可。

</details>

<details>
<summary><b>啟動失敗，訊息為「無法載入重排模型」</b></summary>

重排模型在 3.0.0 是必要元件。請確認：

- `RERANKER_MODEL` 名稱正確（預設 `BAAI/bge-reranker-base`）。
- 首次啟動時可以連上 Hugging Face，且 `HF_HUB_OFFLINE` 不是 `true`。
- 若要沿用舊快取，`HF_HOME` 指向原本的快取目錄。

</details>

<details>
<summary><b>升級後每個問題都回報「知識庫中查無相關資料」</b></summary>

先確認索引已重建（`GET /api/admin/vector-store/info` 的 `total_vectors` 大於 0）。索引正常時，可能是相關性門檻太高：`0.2` 是以小型語料得到的暫定值，請以實際問答集執行 `scripts/evaluate_retrieval.py --relevance-thresholds` 校準。

</details>

<details>
<summary><b>一般使用者看不到「AI 工具」頁</b></summary>

這是 3.0.0 的預期行為。工具由所有使用者的 Agent 共用，`stdio` 模式還會在主機上執行指令，因此只開放管理員管理；一般使用者仍可在對話中讓 Agent 使用已啟用的工具。詳見 [ADR-0004](adr/0004-tool-admin-permissions-and-subprocess-isolation.md)。

</details>

<details>
<summary><b>MCP 伺服器狀態變成 <code>error</code></b></summary>

查看該伺服器的 `last_error`：

- 提到 SSRF：網址或其轉址目標未通過 SSRF 驗證，多半是伺服器位於本機或內網，請改用 `stdio` 傳輸；確切原因可依錯誤代碼在伺服器日誌查到。
- 只顯示錯誤代碼：多半是 `stdio` 子行程少了原本從後端繼承的環境變數，請把需要的變數寫進 `env_vars` 後重新探索；錯誤代碼可在伺服器日誌中對應到完整例外。

</details>
