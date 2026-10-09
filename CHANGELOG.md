# 版本變更紀錄 (Changelog)

[繁體中文](CHANGELOG.md) | [English](CHANGELOG_en.md)

本檔記錄 AskMiao 每個版本的重要變更。格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-TW/1.1.0/)，版本號遵循 [語意化版本 2.0.0](https://semver.org/lang/zh-TW/)：不相容的變更升主版號，向下相容的新功能升次版號，錯誤修正升修訂號。

| 版本 | 發行日期 | 重點 |
|---|---|---|
| [4.0.0](#400---2026-09-27) | 2026-09-27 | 安全稽核修正：權杖綁定資料庫帳號、工具呼叫需使用者核准、出站連線固定 IP、資源上限 |
| [3.0.0](#300---2026-09-25) | 2026-09-25 | chunk_id 索引、RRF 與相關性門檻、答案引用出處、工具信任邊界與管理權限、前端 UI/UX 全面修整 |
| [2.2.1](#221---2026-09-19) | 2026-09-19 | 錯誤回應改用錯誤代碼 |
| [2.2.0](#220---2026-09-01) | 2026-09-01 | 集中式 SSRF 防護 |
| [2.1.0](#210---2026-08-27) | 2026-08-27 | 自訂 API 工具、OpenAPI 匯入與 MCP 整合 |
| [2.0.1](#201---2026-08-26) | 2026-08-26 | 多模態對話與 AI 文件摘要 |
| [2.0.0](#200---2026-08-24) | 2026-08-24 | Agentic RAG 自主研究 |
| [1.0.0](#100---2026-08-01) | 2026-08-01 | 混合 RAG 與安全基礎 |

> [!TIP]
> 從 3.0.0 升級到 4.0.0 前，請先閱讀 [升級指南](docs/upgrading.md#從-300-升級到-400)：RSA 金鑰改為必要、compose 需設定 `POSTGRES_PASSWORD`，開發伺服器只接受本機連線。從 2.x 升級請先完成 [升級到 3.0.0](docs/upgrading.md#從-2x-升級到-300) 的步驟。

---

## [Unreleased]

這一版處理第二輪安全稽核的發現：聊天附件解析有記憶體預算、登入失敗會暫停該帳號或來源位址、變更密碼即撤銷所有權杖、可以關閉自行註冊、工具憑證加密存放且管理 API 不再讀出、自訂 API 工具只接受宣告的參數、相依套件以雜湊鎖定，PostgreSQL 改以非超級使用者連線。

> [!WARNING]
> **本版含需要手動處理的變更**，升級前請依 [升級指南](docs/upgrading.md#從-400-升級到未發行版本) 逐項確認：
>
> - `.env` 新增 10 個必填設定：`ALLOW_REGISTRATION`、`LOGIN_MAX_FAILURES_PER_ACCOUNT`、`LOGIN_MAX_FAILURES_PER_ADDRESS`、`LOGIN_FAILURE_WINDOW_SECONDS`、`LOGIN_LOCKOUT_SECONDS`、`TOOL_SECRETS_KEY`、`HOST`、`RELOAD`、`COOKIE_SECURE`、`ENABLE_API_DOCS`，缺少任一項後端就無法啟動；`TOOL_SECRETS_KEY` 必須是各部署自行產生的 Fernet 金鑰。
> - `HOST` 與 `RELOAD` 不再預設 `0.0.0.0` 與 `true`，`COOKIE_SECURE` 不再依 `ENVIRONMENT` 推導；`/docs`、`/redoc`、`/openapi.json` 只在 `ENABLE_API_DOCS=true` 時提供。
> - 使用 `backend/docker-compose.yml` 時必須設定 `POSTGRES_APP_USER`、`POSTGRES_APP_PASSWORD`，`DATABASE_URL` 改用這組非超級使用者帳號；既有資料卷要執行一次 `20-app-role.sh`。
> - 沒有在 `parameters_schema` 宣告的工具參數一律回傳 `400`；`GET /api/external-tags`、WebSocket `/api/chat/ws/{user_id}` 已移除；`POST /api/api-tools/parse-spec` 的回應不再包含 `raw_spec`。
> - 新增或升級後端套件改為修改 `requirements.in` 再重新產生 `requirements.txt`；`bun install` 在 `bun.lock` 與 `package.json` 不一致時會失敗。
> - 變更密碼後，包含目前這一個在內的所有工作階段都需要以新密碼重新登入。

### 安全性 (Security)

#### 認證與帳號

- **登入失敗節流**：同一登入識別（不分大小寫）或同一來源位址在 `LOGIN_FAILURE_WINDOW_SECONDS` 內失敗達門檻後，暫停該識別或位址的登入 `LOGIN_LOCKOUT_SECONDS` 秒，回傳 `429` 與 `Retry-After`；不存在的帳號同樣計數，鎖定期間正確密碼也不接受，回應不透露密碼是否正確（CWE-307）。
- **變更密碼撤銷所有權杖**：`users` 新增 `tokens_valid_after`，變更密碼時更新為當下，簽發時間早於它的存取與重新整理權杖一律無效；權杖的 `iat` 保留微秒，同一秒內稍早簽發的權杖也會失效，被盜的重新整理權杖不能在受害者改密碼後繼續換發。`POST /api/auth/change-password` 與帶新密碼的 `PUT /api/auth/me` 會清除重新整理權杖 Cookie（CWE-613）。
- **可以關閉自行註冊**：新增必填設定 `ALLOW_REGISTRATION`，關閉時 `POST /api/auth/register` 回傳 `403` 並寫入安全日誌；帳號（含第一位管理員）改以 `scripts/create_user.py` 建立。原本任何能連到 API 的人都能註冊，查詢整個知識庫並以營運者的憑證呼叫已啟用的工具（CWE-284）。
- **管理員使用者 API 不再回傳密碼雜湊**：`GET /api/admin/users` 與 `PUT /api/admin/users/{user_id}` 改以 `UserProfile` 篩選欄位，回應不再帶有 `hashed_password`（CWE-200）。
- **權杖過期也能登出**：`POST /api/auth/logout` 只驗存取權杖的簽章，權杖過期時仍會撤銷重新整理權杖並清除 Cookie；仍要求 `Authorization` 標頭，跨站表單無法觸發登出（CWE-613）。
- 管理員變更帳號權限、狀態與刪除帳號時寫入安全日誌（`ADMIN_USER_UPDATED`、`ADMIN_USER_DELETED`），記錄操作者與變更內容（CWE-778）。
- JWT 私鑰建立當下即為 `0600`，不再先以預設權限寫入再修改；新建立的 `backend/keys/` 為 `0700`（CWE-276）。

#### 部署與相依套件

- **PostgreSQL 改以非超級使用者連線**：`docker-compose.yml` 新增必填的 `POSTGRES_APP_USER`、`POSTGRES_APP_PASSWORD`，`backend/init-app-role.sh` 在 `init.sql` 之後建立帳號、授予 `public` schema 的 `USAGE` 與 `CREATE`，並把既有資料表交給它擁有；SQL 注入不再能以 `COPY ... TO PROGRAM` 執行系統指令或讀取伺服器檔案（CWE-250）。
- **不安全的預設值改為必填**：`HOST`、`RELOAD`、`COOKIE_SECURE` 不再預設對所有介面監聽、自動重新載入或依 `ENVIRONMENT` 推導 Secure；新增必填的 `ENABLE_API_DOCS`，關閉時不提供列出所有端點與參數的互動式文件（CWE-1188）。
- **相依套件以雜湊鎖定**：`backend/requirements.in` 只列直接依賴，`requirements.txt` 由 `uv pip compile --universal --generate-hashes` 產生並在安裝時驗證雜湊；提交 `frontend/bun.lock` 並改為 `frozenLockfile = true`。原本兩邊都沒有鎖定版本，每次安裝都取得當下最新版（CWE-1357、CWE-494）。
- 移除不需登入、未快取並原樣轉送上游 JSON 的 `GET /api/external-tags`，以及不需認證、繞過速率限制的 WebSocket `/api/chat/ws/{user_id}`；前端都沒有使用（CWE-306）。
- 文件上傳的大本文上限只放寬給權杖帶有 `is_admin` 的請求，一般使用者不能讓後端先解析約 500 MiB 的 multipart；速率限制追蹤的位址數有上限，最久未活動的先淘汰（CWE-770）。

#### 工具憑證與出站請求

- **工具憑證加密存放**：自訂 API 工具的 `headers`、`auth_config` 與 MCP 伺服器的 `env_vars`、`headers` 寫入資料庫前以 `TOOL_SECRETS_KEY`（Fernet）加密，啟動時把既有明文資料改為加密；管理 API 的回應以 `••••••••` 取代秘密值，更新時送回遮蔽字樣的欄位沿用原值。原本以明文存放且管理 API 原樣回傳（CWE-312、CWE-522）。
- **自訂 API 工具只接受宣告的參數**：參數必須在 `parameters_schema` 中宣告，`request_body` 有宣告欄位的 schema 時一併檢查；工具網址中的查詢參數由管理員固定，呼叫端提供同名參數時拒絕。原本模型給的任何鍵都會送出，在 httpx 0.28 上帶任何查詢參數還會整段取代網址中的固定參數（CWE-20、CWE-915）。
- **轉址改為手動跟隨**：自訂 API 工具與 HTTP MCP 不讀取轉址回應的本文，整個呼叫另有總時限（`504`）；HTTP MCP 只跟隨同一來源的轉址，管理員設定的標頭與 JSON-RPC 本文不會送往其他網域（CWE-200、CWE-400）。
- **MCP 子行程與錯誤**：stdio 子行程在每次新建的空暫存目錄執行，等待執行空位有時限，stderr 持續讀出，單行訊息上限 4 MiB；只保留名稱符合 `[A-Za-z0-9_.-]{1,128}` 的工具；工具失敗只回傳錯誤代碼，啟動失敗的訊息不含指令參數（CWE-400、CWE-209）。
- 使用者網址（`web_fetch`）與管理員設定的端點各用一個 DNS 執行緒池，慢速網域不會拖垮工具與規格匯入的 SSRF 檢查；SSRF 拒絕清單明確列出 6to4（`2002::/16`）與 NAT64 local-use（`64:ff9b:1::/48`）（CWE-400、CWE-918）。
- 工具網址中固定的查詢參數值（可能是寫在網址裡的金鑰）不出現在回傳給模型與使用者的網址中；`approval_required` 事件新增 `target`，標出實際送出的位置（CWE-200）。
- OpenAPI 規格拒絕 YAML 別名，解析結果不再夾帶整份原始規格（CWE-776）。

#### 資源上限

- **聊天附件的解析預算**：管理員上傳與聊天附件各用一組 `ExtractionLimits`。聊天附件的 docx／pptx 依 `[Content_Types].xml` 加總會建成 DOM 的 XML 部件，上限 8 MiB（改副檔名無法繞過）；解壓總量上限 64 MiB、成員數上限 10,000，壓縮比除了逐一成員也檢查整個檔案；JSON 與程式碼超過 2,000,000 字時不交給 `json.loads`；整個行程同時最多解析 2 個附件，超過預算時告知模型附件未被讀取（CWE-409、CWE-400）。
- `split_structured_records` 的分隔線正規式改為線性時間（CWE-1333）。

#### 前端

- **建置產物帶有 CSP**：`bun run build` 把 CSP 以 `<meta>` 寫入 `index.html`：腳本只允許建置產物與 `index.html` 內嵌腳本的雜湊，`connect-src` 依 `VITE_API_BASE`／`VITE_API_URL` 加入 API 來源，圖片只允許同源與 `data:`／`blob:`。網頁伺服器沒有設定 CSP 時，被注入的 HTML 也無法執行腳本（CWE-79）。
- **工具核准卡片顯示完整內容**：列出實際送出的位置與每一個參數，不再藏在需要捲動的區域；控制字元與格式字元（雙向文字控制、零寬字元、Unicode 標籤字元等）以 `⟦U+…⟧` 標示（CWE-451）。
- **外部連結標示實際網站**：以解析後的網址判斷是否為外部連結，在新分頁開啟並標示實際主機；Markdown 中的 `title` 不能取代網址提示，外部連結也不套用站內動作按鈕的樣式（CWE-451）。
- 請求失敗時主控台只記錄狀態碼與錯誤訊息，不再記錄帶有密碼、API 金鑰與存取權杖的 axios 錯誤物件（CWE-532）。
- 登出請求失敗時在登入頁提示：伺服器沒有撤銷重新整理權杖，存放它的 httpOnly Cookie 在到期前仍可換發存取權杖（CWE-613）。
- 研究軌跡的參數與輸出預覽一律轉成文字顯示：模型給出物件時不再讓對話頁面崩潰（軌跡存在資料庫中，原本之後每次開啟該對話都會崩潰）；貼文作者欄位不再使用在一長串「.」上回溯成二次方時間的正規式（CWE-1333）。

### 新增 (Added)

- 必填設定 `ALLOW_REGISTRATION`、`LOGIN_MAX_FAILURES_PER_ACCOUNT`、`LOGIN_MAX_FAILURES_PER_ADDRESS`、`LOGIN_FAILURE_WINDOW_SECONDS`、`LOGIN_LOCKOUT_SECONDS`、`TOOL_SECRETS_KEY`、`HOST`、`RELOAD`、`COOKIE_SECURE`、`ENABLE_API_DOCS`；`docker-compose.yml` 的 `POSTGRES_APP_USER`、`POSTGRES_APP_PASSWORD`。
- `GET /api/auth/registration` 回傳是否開放自行註冊；前端據此隱藏登入頁的註冊入口，註冊頁改為顯示說明。
- `backend/scripts/create_user.py`：以互動方式輸入密碼建立帳號，套用與註冊相同的規則，`--admin` 建立管理員。
- `backend/init-app-role.sh`（PostgreSQL 應用程式帳號，可重複執行）與 `backend/requirements.in`、`frontend/bun.lock`。
- 管理 API 的工具與 MCP 伺服器回應新增 `credentials_unreadable`：無法以目前的金鑰解密時讓管理員重新輸入，而不是整頁失敗。
- 新增後端測試 `test_admin_user_api.py`、`test_login_throttle.py`、`test_registration.py`、`test_tool_secrets.py`。
- **介紹頁「工具核准」區段**：可操作的核准卡片示範（核准、拒絕、模擬逾時），同步顯示 `approval_required`、`approval_resolved` 等 SSE 事件；另依 HTTP 方法切換自訂 API 工具的預設核准規則，規則與 `tool_approval.py` 相同。
- 介紹頁新增 4.0.0 版本標籤與數據列、安全區段的「每個入口都有上限」資源上限表，文件導覽補上 ADR-0006。
- README 新增「4.0.0 重點」、「工具呼叫核准」、「防護對照」與「主要資源上限」各節，疑難排解新增核准逾時與唯讀工具要求核准兩項。

### 變更 (Changed)

- 變更密碼後目前的工作階段也會登出，前端清除登入狀態並導回登入頁。
- 存取與重新整理權杖的 `iat` 改為含微秒的小數（RFC 7519 的 NumericDate 允許小數）；自行解析權杖的客戶端不要假設它是整數。
- 未宣告任何參數的自訂 API 工具不再接受參數；`POST /api/api-tools/parse-spec` 的回應不再包含 `raw_spec`。
- 管理 API 回應中的工具與 MCP 憑證以 `••••••••` 顯示；`Accept`、`Content-Type` 等一般標頭與 `key_name`、`username` 等設定照常顯示。更換 `TOOL_SECRETS_KEY` 後已儲存的憑證需要重新輸入。
- 入侵偵測只保留警報；`RateLimitMiddleware` 不再有回傳 `403` 的封鎖分支。
- `backend/.env.example` 新增上述必填設定，`DATABASE_URL` 範例改用 `askmiao_app`；`frontend/.env.example` 註明 `VITE_API_BASE` 會寫入 CSP 的 `connect-src`。

### 移除 (Removed)

- `GET /api/external-tags` 與 WebSocket `/api/chat/ws/{user_id}`。
- 入侵偵測中從未被填入的 IP 封鎖名單。
- 未使用、且缺少金鑰時會悄悄改用隨機金鑰的 `app/core/secret_manager.py`；未使用、且不固定連線 IP 的 `reject_unsafe_request`。
- 沒有任何程式使用的後端套件：FlagEmbedding、waitress、docxtpl、XlsxWriter、PyJWT、langchain、langchain-community。

### 修正 (Fixed)

- 依 `requirements.txt` 安裝時，FlagEmbedding 帶入的舊版 datasets 與新版 pyarrow 不相容，使 sentence-transformers 無法匯入；原本只靠其他套件間接安裝的 pydantic-settings、PyYAML、lxml 改為直接依賴。
- `bunfig.toml` 的 `cache = "~/.bun/install/cache"` 不會展開 `~`，在 `frontend/` 下建立名為 `~` 的快取目錄，vitest 也會掃到其中第三方套件的測試。
- 介紹頁的 web_fetch 檢查器改以正規化後的完整網址比對來源，與 `research_session.py` 一致；原本以解碼後的子字串比對，會把網址的片段也當成出現過。
- 介紹頁移除已不存在的 `JWT_SECRET_KEY`（快速開始、必填設定與子行程環境變數表），改說明 RSA 金鑰、`POSTGRES_PASSWORD` 與開發伺服器只接受本機連線；安全說明補上連線固定 IP 與權杖對應資料庫帳號。

---

## [4.0.0] - 2026-09-27

這一版處理安全稽核提出的 52 項線索：權杖改為每次請求對應資料庫帳號、有副作用的工具呼叫前須由使用者核准、出站連線固定在 SSRF 驗證過的 IP，並為請求本文、附件、工具結果與同時串流數等資源加上上限。

> [!WARNING]
> **本版含需要手動處理的變更**，升級前請依 [升級指南](docs/upgrading.md#從-300-升級到-400) 逐項確認：
>
> - `JWT_SECRET_KEY` 與 `JWT_ALGORITHM` 已移除；`backend/keys/` 的 RSA 金鑰在任何環境都是必要的，無法載入或產生時後端拒絕啟動。
> - `backend/docker-compose.yml` 必須設定 `POSTGRES_PASSWORD`，且只綁定 `127.0.0.1:7690`；既有資料卷的密碼需另外修改。
> - Vite 開發與預覽伺服器只監聽 `localhost`，區網裝置請改用建置產物與正式網頁伺服器。
> - `/api/chat` 的訊息回應不再包含原始 `context_used`（一律為 `null`）；`GET /api/chat/tools` 需要登入；`model_name` 必須在可用模型清單內。
> - 自訂 API 工具與 MCP 伺服器新增 `requires_approval`（啟動時自動加入並回填），既有 MCP 伺服器的工具呼叫起會先要求使用者核准。

### 安全性 (Security)

#### 認證

- **移除 HS256 退路**：RSA 金鑰無法載入時，開發環境不再改用 `.env` 中的共用密鑰簽署權杖；金鑰在任何環境都必須可用，否則拒絕啟動（CWE-1188）。
- **權杖綁定資料庫帳號**：每次請求依 `sub` 讀取帳號，帳號必須存在且啟用，`is_admin` 與角色取自資料庫而非權杖內容，簽發時間早於帳號建立時間的權杖（刪除後 id 被重用）一律拒絕；停用、刪除或降權即時生效（CWE-613、CWE-285）。新建立的 SQLite 資料庫中 `users` 與 `documents` 改用 `AUTOINCREMENT`，id 不再重用。
- **重新整理權杖只能使用一次**：換發後立即撤銷舊權杖（CWE-294）。
- 密碼最多 256 字元、登入識別最多 254 字元，Argon2 雜湊與驗證移到執行緒並限制同時 4 個；撤銷名單最多 100,000 筆（CWE-400）。

#### 部署

- **PostgreSQL 容器不再內建密碼**：`POSTGRES_PASSWORD` 改為必填，埠號只綁定 `127.0.0.1:7690`（CWE-798、CWE-1327）。
- **不採信用戶端的 `X-Forwarded-For`**：`python main.py` 預設關閉 uvicorn 的 `proxy_headers`，速率限制與封鎖名單以實際連線對端為準；只有新設定 `FORWARDED_ALLOW_IPS` 指定的反向代理才被信任（CWE-348）。
- **Vite 開發伺服器只對本機開放**：開發與預覽伺服器改為只監聽 `localhost`，`/__open-in-editor` 只回應本機回送位址（CWE-1327）；兩者送出 `X-Frame-Options: DENY` 與 `Content-Security-Policy: frame-ancestors 'none'; img-src 'self' data: blob:`，`index.html` 另加反框架樣式守衛（CWE-1021）。

#### 工具與出站請求

- **呼叫前核准**：有副作用的自訂 API 工具與 MCP 工具由發問的使用者在對話中核准後才執行，見下方「新增」（CWE-862）。
- **SSRF 驗證固定連線 IP**：自訂 API 工具、MCP HTTP 傳輸與 `safe_fetch_text` 每一跳驗證後把連線固定在核可的 IP，DNS rebinding 無法在驗證與連線之間改變目標；DNS 查詢改在 4 條執行緒的專用執行緒池中進行，5 秒逾時（CWE-918、CWE-367）。
- **自訂 API 工具**：路徑參數百分比編碼，代入後的主機必須與設定相同；跨來源轉址時移除管理員設定的標頭與認證標頭；結果與網址中的憑證值遮蔽為 `[已遮蔽]`；回應本文上限 1 MiB（CWE-918、CWE-522、CWE-200、CWE-400）。
- **SSRF 拒絕只回錯誤代碼**：自訂 API 工具、`web_fetch` 與 `POST /api/api-tools/parse-spec` 遭拒時不再回傳可能含內網 IP 的原因；MCP HTTP 錯誤不再夾帶對端回應本文，單次回應上限 4 MiB（CWE-209、CWE-400）。
- **`web_fetch` 網址來源比對更嚴格**：只接受以完整網址出現過的網址，兩邊以 httpx 正規化後逐字比對，實際送出比對到的網址（CWE-918）。
- **MCP 範本**：移除繞過 `web_fetch` 出站防護的 `mcp_fetch`；`mcp_filesystem` 改以專屬的 `backend/mcp_filesystem_sandbox` 為根目錄（原本是含 pickle 索引中繼資料的 `./data`），並釘選 `@modelcontextprotocol/server-filesystem@2026.8.31`（CWE-918、CWE-552、CWE-829）。
- **MCP 子行程**：自成程序群組，關閉時終止整個子行程樹，同時最多 4 個（CWE-404、CWE-400）。
- **聊天附件只接受 base64 `data:` URL**，遠端網址不再交給模型供應商擷取（CWE-918）；回答中的 Markdown 圖片改為點擊才開啟的連結，不再自動向外部主機載入（CWE-201）。
- `httpx` 與 `httpcore` 日誌層級固定為 `WARNING`，含查詢字串金鑰的完整網址不再寫進日誌（CWE-532）。

#### 資源上限

- 新增 `RequestBodyLimitMiddleware`：一般請求本文上限 1 MiB，聊天送出與文件上傳只有帶有效存取權杖時才放寬，超過回傳 `413`（CWE-770）。
- 聊天訊息最多 20,000 字、附件最多 5 個（單一 15 MiB、合計 20 MiB）、附件文字與工具結果放進模型前截斷；每位使用者附件儲存量 200 MiB（`413`）、同時最多 2 個回答串流（`429`）；聊天附件 PDF 最多 OCR 20 頁、每頁點陣化最多 25 MP；LLM 連線池等待上限 15 秒（CWE-400、CWE-770）。
- OOXML 解析前檢查解壓大小與壓縮比（CWE-409）；HTML 抽取、SVG 去除、JSON 宣告抽取、Q&A 切分與目錄行清理改為線性時間，`filter_and_count_records` 限制日期範圍與筆數（CWE-1333）。
- 對話清單最多 200 段、每段 5 則預覽且不含附件本文；單段對話最多回傳 500 則；遠端模型清單快取 30 秒並在執行緒中查詢（CWE-400）。
- 安全日誌欄位最多 200 字元，`app.log` 與 `security.log` 以 10 MiB × 5 份輪替，安全事件不再重複寫入 `app.log`；入侵偵測的事件與追蹤位址數有上限（CWE-779、CWE-400）。

#### 其他

- **`send` 的模型名稱必須在可用清單內**：避免以操作者的金鑰呼叫清單外的模型（CWE-770）；`GET /api/chat/tools` 改為需要登入（CWE-200）。
- jieba 詞典快取改放 `DATA_DIR/jieba_cache`（權限 `0700`），不再以可預測的檔名放在系統暫存目錄（CWE-377）。
- **MCP 伺服器的 SSRF 拒絕訊息不再帶出解析結果**：建立或探索 MCP 伺服器時網址被 SSRF 防護拒絕，`last_error` 與 400 回應改為註明遭拒並附錯誤代碼；完整原因可能含伺服器端 DNS 解析出的內網 IP 或轉址目標，只寫入伺服器日誌（CWE-209）。
- **介紹頁 RRF 示範跳脫片段 ID**：`site/main.js` 把內嵌 JSON 的片段 ID 與重排機率插入 HTML 前改經 `escapeHtml`，資料含引號或角括號時不再被當成 HTML 解析（CWE-79）。

### 新增 (Added)

- **工具呼叫核准**：自訂 API 工具與 MCP 伺服器新增 `requires_approval`（API 工具依 HTTP 方法預設，`GET`、`HEAD`、`OPTIONS` 以外為 `true`；MCP 伺服器預設 `true`）。Agent 呼叫這類工具時送出 SSE `approval_required` 並暫停，使用者以 `POST /api/chat/approvals/{approval_id}` 回覆後送出 `approval_resolved`；只有發問者能回覆，300 秒逾時或沒有可核准的使用者時不執行。前端在回答中顯示確認卡片，「AI 工具」頁的表單新增對應核取方塊。詳見 [ADR-0006](docs/adr/0006-tool-call-approval.md)。
- `FORWARDED_ALLOW_IPS` 設定：指定會覆寫 `X-Forwarded-For` 的反向代理，速率限制才以真實用戶端 IP 計算。
- `backend/app/core/limits.py` 集中定義資源上限，[設定參考](docs/configuration.md#資源上限) 新增「資源上限」一節。
- `upgrade_schema()`：啟動時（以及 `init_db.py`）替既有資料表補上新欄位並回填。
- 前端送出訊息遇到 `422` 欄位驗證錯誤時，逐項顯示原因（例如附件過大）。
- 新增 [ADR-0006](docs/adr/0006-tool-call-approval.md) 與 ADR-0004 的後續修訂；[升級指南](docs/upgrading.md#從-300-升級到-400) 新增本版的升級步驟。
- 新增後端測試 `test_auth_token_binding.py`、`test_outbound_tool_security.py`、`test_process_hardening.py`、`test_resource_limits.py`、`test_tool_approval.py`。

### 變更 (Changed)

- `/api/chat` 的訊息回應不再包含原始 `context_used`（一律為 `null`），改由已解析的 `sources`、`sources_detail`、`research_trace` 與 `attachments` 提供；對話清單的附件不含 `data_url`。
- 聊天串流期間把資料庫連線還給連線池，資料庫存取與附件解碼、解析改在執行緒中進行；對話讀取路由改為同步函式，由執行緒池執行。
- 自訂 API 工具、MCP HTTP 傳輸與 `web_fetch` 的直接抓取不再使用 `HTTP_PROXY`、`HTTPS_PROXY` 環境變數。
- PDF OCR 的點陣化改在文件執行緒上逐頁進行，只有視覺模型呼叫平行；XLSX 以唯讀模式開啟。
- 刪除文件時先刪除資料庫紀錄再移除索引片段，索引寫入持鎖後略過所屬文件已刪除的片段。
- `backend/.env.example`：移除 `JWT_SECRET_KEY`、`JWT_ALGORITHM`，新增 `POSTGRES_PASSWORD` 與 `FORWARDED_ALLOW_IPS` 範例。

### 移除 (Removed)

- `JWT_SECRET_KEY`、`JWT_ALGORITHM` 設定與 HS256 簽署路徑（留在 `.env` 中會被忽略）。
- MCP 範本 `mcp_fetch`（`uvx mcp-server-fetch`）。

### 修正 (Fixed)

- `POST /api/auth/refresh` 讀取不存在的 `user_id` 聲明，換發一律失敗；改以 `sub` 對應帳號。
- 刪除文件與同時進行的索引寫入競爭時，已刪除文件的片段可能被寫回知識庫（CWE-362）。
- SQLite 重用已刪除的使用者或文件 id，舊權杖或舊片段因此對應到新資料。

---

## [3.0.0] - 2026-09-25

這一版把「答案從哪裡來」做成可以驗證的鏈條：片段以資料庫的 chunk_id 為準，檢索改用 RRF 融合並以重排機率判斷相關性，答案以 `[n]` 對應實際引用的來源。同時為工具輸出設立信任邊界、把工具管理收斂給管理員，並全面修整前端的操作體驗。

> [!WARNING]
> **本版含破壞性變更**，升級前請依 [升級指南](docs/upgrading.md) 逐項處理：
>
> - `.env` 新增 8 個必填設定：`ENABLE_WEB_SEARCH`、`AGENT_MAX_TURNS`、`CONVERSATION_HISTORY_MESSAGES`、`RRF_K`、`RERANK_RELEVANCE_THRESHOLD`、`WEB_FETCH_ALLOWED_DOMAINS`、`BLOCK_WEB_TOOLS_AFTER_KB`、`DOMAIN_PROFILE_PATH`，缺少任一項後端就無法啟動；使用 Claude 模型時另需 `ANTHROPIC_MAX_TOKENS`。
> - 索引改以 chunk_id 對應：舊版 FAISS 索引在首次啟動時會改名為 `faiss_index.bin.legacy.bak`，必須重建一次索引才能再檢索既有文件。
> - 重排模型改為必要元件，模型載入失敗時後端無法啟動。
> - 「AI 工具」頁與 `/api/api-tools`、`/api/mcp` 的所有端點只限管理員；MCP `stdio` 子行程不再繼承後端的環境變數；指向本機或內網位址的 MCP HTTP 伺服器會被拒絕。
> - 多項設定移除、`HF_HOME` 不再有預設值、未設定時的預設模型改變，`/api/admin/rag-config` 的回應欄位也已調整（詳見下方各節）。

### 新增 (Added)

#### 檢索與索引

- **以資料庫為準的片段索引**：新增 `rag_chunks` 資料表作為片段的唯一來源；FAISS 改用 `IndexIDMap2(IndexFlatIP)`，FAISS 與 BM25 皆以 chunk_id 對應。後端啟動時依資料庫校正索引：刪除孤立片段、移除多餘向量、補算缺少的向量，BM25 與資料庫不一致時自動重建。詳見 [ADR-0005](docs/adr/0005-chunk-id-index-and-database-source-of-truth.md)。
- **RRF 融合與相關性門檻**：向量與 BM25 每次必跑，以標準 RRF（`RRF_K`）依名次融合；`RERANK_RELEVANCE_THRESHOLD` 直接套在重排機率上，精確比對到網址、貼文 ID、日期的片段不受限制，全部未通過時回報「知識庫中查無相關資料」。詳見 [ADR-0003](docs/adr/0003-rrf-relevance-citations-and-tool-trust.md)。
- **領域設定檔**：新增 `backend/config/domain_profile.json` 與 `DOMAIN_PROFILE_PATH`，收納領域詞、記錄日期欄位與摘要備援規則，啟動時驗證格式；選填的 `JIEBA_DICTIONARY` 可替換 jieba 主詞典。
- **檢索評估工具**：`scripts/evaluate_retrieval.py` 在索引副本上唯讀計算 hit@k、recall@k 與 MRR，`--min-mrr` 可當作 CI 門檻；問答集允許 `"relevant_sources": []` 的反例，`--relevance-thresholds` 以同一次重排結果比較多個門檻的正例命中率與反例拒絕率。

#### Agent 與模型

- **引用對應來源**：每次提問建立引用編號表（`app/rag/research_session.py`），答案以 `[n]` 標註出處，`sources_detail` 只列實際被引用的條目並附 `citation` 編號；前端標籤改為「[2] 員工手冊.pdf（段落 3）」格式。
- **五家供應商都能呼叫工具**：`llm_client.py` 統一 OpenAI、Azure OpenAI、Anthropic Claude（官方 `anthropic` SDK）、Google Gemini（OpenAI 相容端點）與 Ollama 的呼叫格式，工具呼叫與串流行為一致。
- Ollama 生成參數 `OLLAMA_TEMPERATURE`、`OLLAMA_NUM_PREDICT`（選填，未設定時使用模型預設值）。

#### 前端

- **停止產生與重新傳送**：串流中可停止回答（已停止的回答不會儲存），串流時仍可繼續輸入；失敗的回答顯示原因與「重新傳送」，送出前就失敗時把文字與附件放回輸入框。
- **外觀切換**：帳號選單新增淺色、深色與跟隨系統，預設跟隨系統，並在第一次繪製前套用，深色模式不再先閃白。
- **刪除前確認**：刪除對話、使用者、文件、自訂 API 工具與 MCP 伺服器，以及清空上傳清單、覆寫已編輯的摘要前都會先確認（`ConfirmDialog`）。
- 聊天頁新增「回到最新訊息」按鈕，並以讀螢幕軟體播報回答完成、失敗或停止；新增網路離線與恢復提示、「跳到主要內容」連結，非管理員進入管理頁時改顯示「沒有權限」頁面，取代原生 `alert()`。
- `frontend/src/services/sse.ts`：依規格實作的 SSE 解析器與 8 個 Vitest 測試（事件跨讀取切段、CRLF、多行資料等）。

#### 文件與測試

- 新增 [設定參考](docs/configuration.md)（逐一說明每個環境變數）與 [升級指南](docs/upgrading.md)；新增 [ADR-0003](docs/adr/0003-rrf-relevance-citations-and-tool-trust.md)、[ADR-0004](docs/adr/0004-tool-admin-permissions-and-subprocess-isolation.md)、[ADR-0005](docs/adr/0005-chunk-id-index-and-database-source-of-truth.md)。
- 新增 13 個後端測試檔，涵蓋索引一致性、RRF 與相關性門檻、引用配號、Agent 防護、各供應商工具呼叫、對話前文、設定驗證、uploads watcher 與工具管理權限。

### 變更 (Changed)

#### 檢索與索引

- 刪除文件只移除該文件的片段與向量，不再重算全部向量。
- 檢索與索引寫入改在背景執行緒執行，不再阻塞事件迴圈；片段、FAISS 與 BM25 的讀寫以同一把鎖保護。
- 重排模型改為必要元件：載入失敗時啟動報錯，執行時重排失敗回傳錯誤代碼，不再回傳未過濾的片段。
- `search_knowledge_base` 指定 `target_document` 時在重排前限定文件，查不到不再改用全庫結果。
- BM25 查詢改由斷詞器產生詞項後以 OR 組合；斷詞結果一律轉小寫；索引目錄記錄斷詞簽章，簽章不符時自動重建 BM25（向量不需重算），唯讀評估則拒絕執行。
- 設定中的相對路徑（`DATA_DIR`、`UPLOAD_DIR`、索引路徑、`HF_*`、`DOMAIN_PROFILE_PATH`、`JIEBA_DICTIONARY`）一律以 `backend/` 為基準。
- Hugging Face 設定（`HF_HOME`、`HF_HUB_CACHE`、`SENTENCE_TRANSFORMERS_HOME`、`HF_HUB_OFFLINE`、`HF_HUB_DISABLE_SYMLINKS_WARNING`）在載入模型前寫入環境變數；`HF_HOME` 不再預設為 `./data/hf_home`，未設定時使用函式庫預設的 `~/.cache/huggingface`。
- `.env.example` 的 `RERANK_TOP_K` 範例值由 50 改為 20。
- `/api/admin/rag-config` 改回傳 `rrf_k` 與 `rerank_relevance_threshold`，移除 `hybrid_alpha`、`final_threshold`、`normalization`。

#### Agent 與模型

- 模型不再呼叫工具時直接採用該次答案，不再重新生成，並移除假串流；只有工具輪數用完或模型回傳空內容時才以串流生成。
- 對話前文改由資料庫讀取最近 `CONVERSATION_HISTORY_MESSAGES` 則訊息，後端重啟不再遺失上下文；帶入前會先移除先前回答中的 `[n]`，避免沿用舊編號。
- `ENABLE_WEB_SEARCH` 與 `AGENT_MAX_TURNS` 改為必填；`ENABLE_WEB_SEARCH=false` 時 `web_search`、`web_fetch` 不會出現在工具清單中。
- 更新各供應商預設模型：`OPENAI_VISION_MODEL` 由 `gpt-4o` 改為 `gpt-6-sol`、`GEMINI_VISION_MODEL` 由 `gemini-2.5-flash` 改為 `gemini-3.5-flash`；啟用 Azure 但未設定 `AZURE_OPENAI_DEPLOYMENT` 時改列 `gpt-6-sol`；內建模型清單改為 GPT-6 / GPT-5.6、Claude Opus 5.5 / Fable 5.1 / Sonnet 5 與 Gemini 3.x 系列。

#### 前端與介面

- 對話框、手機版對話清單與圖片檢視改用原生 `<dialog>`：Esc 可關閉、背景無法操作、關閉後焦點回到原本的按鈕；帳號選單支援方向鍵操作。
- 手機版頂欄縮為一列（64px），聊天頁固定為一個視窗高度；觸控裝置上的按鈕與輸入框加大，輸入框字級 16px，iPhone 聚焦時不再自動放大。
- 調整次要文字、狀態色與深色模式主要按鈕的配色，文字對比達 WCAG AA。
- 品牌名稱統一為 AskMiao，每頁有各自的網頁標題；導覽列改用連結並標示目前所在頁面。
- 訊息不是當天送出時一併顯示日期；來源相關度改以百分比顯示。
- 前端文字與後端回傳的訊息改用臺灣用語（例如「使用者名稱」「電子郵件」「字元」「權杖」），無障礙標籤不再混用英文。
- 網頁圖示改用 32px 與 64px 版本，訪客不再下載 4.5MB 的 2048px 原圖（原圖仍保留作為 `site/assets` 圖示的來源）。

#### 版本與文件

- 版本號統一為 3.0.0：後端以 `backend/app/__init__.py` 的 `__version__` 為準，OpenAPI 文件與 MCP 交握的 `clientInfo` 皆引用此值；前端 `package.json` 同步更新；OpenAPI 標題改為「AskMiao API」。
- 依 3.0.0 的實作重寫 README、API 參考、系統架構與 `llms.txt`（中英雙語），修正先前與程式不符的描述，例如 `init_db.py` 並不會建立管理員帳號、知識庫支援的副檔名清單，以及前端實際讀取的環境變數。
- `frontend/.env.example` 只保留前端實際讀取的變數，移除已不存在的 workflow WebSocket 位址與後端專用設定。
- 介紹頁（`site/`）依現行實作改版：互動示範在瀏覽器端重現引用配號、RRF 與相關性門檻、網址來源限制、SSRF 檢查順序與 MCP 環境變數繼承規則，截圖改用新品牌介面。

### 移除 (Removed)

- `HYBRID_ALPHA`、`NORMALIZATION`、`FINAL_THRESHOLD` 設定與 `auto_tune_alpha`（留在 `.env` 中會被忽略）；依查詢型態分流與寫死的 FAQ 關鍵字判斷。
- 每日自動重建索引的背景任務（`tasks/index_rebuilder.py`）與 `ENABLE_AUTO_REINDEX`、`ENABLE_AUTO_REINDEX_TASK`、`REINDEX_HOURS` 設定。
- `DOCUMENTS_PATH`（`documents.pkl`）、`TRANSFORMERS_CACHE`、`HUGGINGFACE_HUB_CACHE` 設定；Hugging Face 快取位置改用 `HF_HOME` 或 `HF_HUB_CACHE`。
- 內建模型清單中的 `gpt-5.5`、`gpt-5.2`、`gpt-4o`、`gpt-4o-mini`、`o1`、`o3`、`o3-mini` 與 `gemini-2.5-flash`；仍要使用請寫進 `AVAILABLE_MODELS`。
- `data/jieba_dict.txt` 存在即自動載入的隱藏機制；自訂詞一律放在領域設定檔。
- uploads watcher 發出、但前端沒有接收的 `documents_update` WebSocket 通知。
- 前端的 `dompurify` 相依套件：react-markdown 預設就不渲染原始 HTML，這一層反而會改寫回答內容。

### 修正 (Fixed)

#### 檢索與 Agent

- FAISS、`documents.pkl` 與 BM25 依清單位置對齊，刪除文件、重建、載入失敗與並行寫入都會讓片段錯位。
- `AGENT_MAX_TURNS` 與 `ENABLE_WEB_SEARCH` 設定沒有作用。
- 重排分數重複套用 sigmoid，機率被壓縮到 0.5 至 0.73 之間，無法作為相關性判斷。
- BM25 以 Whoosh 查詢語法（預設 AND）解析整句查詢，多詞查詢常找不到結果，標點也會被當成查詢語法。
- 相關性門檻套在混合分數上，第一名一定拿到 0.15 而過門檻，導致永遠至少送一段無關片段給模型。
- 只有 BM25 找到的片段在加權融合後進不了重排候選。
- uploads watcher 在上傳檔不見時刪除索引與資料庫紀錄；從其他目錄啟動時會把所有文件判為遺失。現改為只記一次警告。
- Claude 模型 ID 格式錯誤（2.2.1 誤寫為 `claude-4-8-opus` 形式）。
- PostgreSQL 初始化腳本 `init.sql` 缺少 `documents.description` 欄位。

#### 前端

- 用注音、倉頡等輸入法按 Enter 選字時，訊息被直接送出。
- AI 回答被改寫：引用區塊失效、程式碼中的 `<Button>` 變成小寫、`<script>` 那一行消失；含 `|` 的段落被誤轉成社群貼文卡。
- SSE 事件被網路切成兩段時遺失，新對話因此不出現在側欄，下一則訊息還會再開一段新對話。
- 串流出錯時畫面停在「AI 自主研究中」且沒有任何提示；對話清單載入失敗時只顯示「尚無歷史對話」。
- 串流中切換對話時，回答被寫進另一段對話，完成後標題又跳回原對話。
- 密碼打錯時登入頁顯示「未找到刷新令牌」：登入、註冊與重新整理權杖的 401 不再觸發權杖重新整理。
- 用鍵盤操作時看不到焦點；欄位標籤沒有綁定輸入框，讀螢幕軟體讀不出欄位名稱；建議提問、引用來源與上傳拖放區無法用鍵盤操作。
- 手機上對話清單入口被頂欄蓋住、回答泡泡比畫面寬；桌面版聊天頁多出一條頁面捲軸。
- 按「載入更早訊息」後跳回最底，串流時往上捲會被拉回底部。
- 知識庫刪除失敗仍顯示「刪除成功」且錯誤提示關不掉；重新載入時整頁變成轉圈；上傳失敗的原因被丟掉；「取消全部上傳」後仍繼續上傳剩下的檔案。
- 改密碼與後台編輯使用者時，錯誤顯示在對話框後方的頁面上。
- AI 工具頁的通知沒有樣式、搜尋不會篩選 MCP 伺服器、表單在手機上溢出、匯入 OpenAPI 時預設帶入範例規格。
- 按鈕的載入圈圈不會轉；知識庫頁「清空清單」使用不存在的按鈕樣式，兩個圖示名稱不存在。
- 在沒有剪貼簿 API 的環境（例如以 http 從區網連線）複製會靜默失敗。
- 後台表格在 1024px 寬時「操作」欄被擠出畫面。
- `bun run lint` 無法執行：補上缺少的 `@eslint/js` 與 `globals` 開發相依套件。

### 安全性 (Security)

- 工具結果一律包在每次提問 id 不同的 `<untrusted_tool_result>` 標記內，系統提示規定只當資料看。
- `web_fetch` 只能讀取使用者訊息或本次內建工具結果中原樣出現過的網址（工具回聲的查詢參數不算）；新增網域白名單 `WEB_FETCH_ALLOWED_DOMAINS` 與 `BLOCK_WEB_TOOLS_AFTER_KB`（讀過知識庫內容後停用聯網工具）。
- **工具管理只限管理員**：任何註冊使用者原本都能建立 `stdio` MCP 伺服器，在主機上執行任意指令（RCE），也能讀到別人設定的工具憑證。現在 `/api/api-tools` 與 `/api/mcp` 的所有端點（含查詢）都需要管理員，前端「AI 工具」頁也只對管理員顯示。詳見 [ADR-0004](docs/adr/0004-tool-admin-permissions-and-subprocess-isolation.md)。
- MCP `stdio` 子行程只繼承 `PATH` 等系統必要變數，不再取得後端的 JWT 金鑰、資料庫連線與模型 API 金鑰。
- MCP HTTP 傳輸補上原本缺少的 SSRF 驗證；自訂 API 工具與 MCP HTTP 傳輸的每次轉址都會重新驗證，外部 API 無法再以轉址導向內網或雲端 Metadata。

---

## [2.2.1] - 2026-09-19

### 修正 (Fixed)

- **錯誤回應改用錯誤代碼**：
  - 新增 `app/core/error_response.py`，未預期例外之完整訊息與堆疊僅寫入伺服器日誌，對外僅回傳隨機錯誤代碼與 `error_id`（CWE-209 / CWE-497）。
  - `api_tools.py`、`mcp.py`、`chat.py` 與 `openapi_parser.py` 全面套用；輸入驗證類錯誤改以 `SafeClientError` 標記後原樣回傳，保留可據以修正之診斷訊息。
- **移除 RAG 串流中外洩之例外文字**：`rag/agent.py`、`rag/pipeline.py` 與 `rag/tools.py` 之串流輸出不再夾帶例外內容。

---

## [2.2.0] - 2026-09-01

### 修正 (Fixed)

- **修復 OpenAPI 解析與遠端請求之 SSRF 漏洞 (#25)**：
  - 新增 `app/core/ssrf_protection.py`，對使用者提供之 URL 進行協定、連接埠、主機名稱與 DNS 解析後 IP 範圍驗證，阻擋私有網段、迴環與連結本地位址、雲端中繼資料端點與危險連接埠。
  - `openapi_parser.py`、`rag/tools.py`（`web_fetch`）與 `api_tools.py` 全面改走 SSRF 防護閘門。
  - 新增 `backend/tests/test_ssrf_protection.py` 覆蓋阻擋與放行情境。

---

## [2.1.0] - 2026-08-27

### 新增 (Added)

- **自訂 API 工具**：
  - 新增 `custom_api_tools` 資料表與 `/api/api-tools` 端點，支援工具 CRUD、啟用切換與即時連通性測試。
  - 通用 HTTP 執行器支援 Path 變數替換、Query 組裝、Header 與認證注入（Bearer / API Key / Basic）、JSON 與表單主體序列化及逾時隔離。
- **OpenAPI / Swagger 匯入**：
  - 新增 `services/openapi_parser.py`，支援 OAS 2.0、3.0、3.1 規格內容或規格 URL 解析，並可批次匯入選定端點為 AI 工具（同名覆寫更新）。
- **MCP 伺服器整合**：
  - 新增 `mcp_servers` 資料表與 `/api/mcp` 端點，支援伺服器 CRUD、範本清單、工具探索（`initialize` + `tools/list`）與單一工具調用測試。
  - 新增 `services/mcp_service.py`，提供 `stdio` 子行程與 HTTP 兩種 JSON-RPC 傳輸用戶端。
- **工具動態註冊**：`ResearchToolRegistry` 於組裝工具定義時自動載入啟用中的自訂 API 工具與 MCP 工具（命名慣例 `mcp_<伺服器>_<工具>`），變更後無需重啟後端。
- **前端 AI 工具管理頁**：新增 `/tools` 路由與 `AiTools` 頁面，提供工具總覽、OpenAPI 匯入精靈與 MCP 伺服器管理。

### 變更 (Changed)

- 精簡 `.gitignore` 規則並自版本庫移除本地資料庫檔案。

---

## [2.0.1] - 2026-08-26

### 新增 (Added)

- **多模態對話管線**：對話支援附加圖片與文件；圖片以 `image_url` 內容區塊送入視覺模型，文字類附件抽取內容併入提問上下文。
- **知識庫動態描述**：文件上傳時自動生成 AI 大綱與摘要，並提供重新生成與手動修訂端點。

### 變更 (Changed)

- 全面現代化前端介面與元件庫。

---

## [2.0.0] - 2026-08-24

### 新增 (Added)

- **Agentic RAG 自主研究管線**：
  - 實作 ReAct 自主研究代理人 `ResearchAgent`，支援多輪自主推理與 Native Tool Calling。
  - 提供 `ResearchToolRegistry` 原生工具集：內部知識庫搜尋（`search_knowledge_base`）、外部聯網搜尋（`web_search`，具備 Ollama 與 DuckDuckGo 雙引擎備援）與外部網頁內容深度抓取（`web_fetch`）。
- **模型推理程度（Reasoning Effort）選擇機制**：
  - 前端頂部導覽列提供 5 檔位切換：`無 (None)`、`輕度 (Low)`、`標準 (Medium)`、`深度 (High)`、`極致 (X-High)`。
  - 後端全面適配 Azure OpenAI v1 及 OpenAI 官方推理模型，並依微軟 Foundry 規範自動處理工具調用時之相容性。
- **全新前端視覺與研究歷程展示**：
  - 新增 `ResearchTraceBlock`：可折疊之研究步驟時間軸與工具調用日誌展示。
  - 新增 `SourceBadges`：外部參考連結徽章，支援點擊直接另開視窗閱讀來源。
- **模組化 RAG 架構**：
  - 將 RAG 系統重構為高內聚模組：向量索引（`indices/`）、混合檢索（`retrievers/`）、執行管線（`pipeline.py`）、評估器（`evaluator.py`）與門面類別（`contextual_rag.py`）。

### 變更 (Changed)

- **架構輕量化與零依賴化**：
  - 預設改用 SQLite 關聯式資料庫與記憶體快取，無需啟動 Docker、PostgreSQL 或 Redis 即可一鍵本機啟動。
  - 移除過時之討論看板與自訂 Agent 模組，專注於高效知識庫問答與深度研究。
  - 移除查詢快取命中，確保每次問答均能反映最新文檔與即時聯網資訊。
- **前端版面體驗升級**：
  - 側邊欄整合為單一自適應實例，桌面端無縫卡片貼合，移動端自動切換抽屜。
  - 全面使用 Bun 作為前端套件管理與建構工具。

### 修正 (Fixed)

- **Azure OpenAI v1 API 相容性**：
  - 移除已過時之 `AZURE_OPENAI_API_VERSION` 依賴，採用標準 v1 端點路徑。
  - 移除推理模型中不支援的 `max_tokens` 與 `temperature` 參數，改採相容之 payload 結構。
- **系統穩定性與錯誤修復**：
  - 修復 `MessageResponse` 缺少 `Dict, Any` 導入引發之 `NameError`。
  - 修復 `HybridContextualRAG.generate_response()` 遺漏 `reasoning_effort` 參數傳遞之 `TypeError`。
  - 修復 `/api/chat/models` 遺漏 `settings` 導入導致 500 錯誤與模型選單未正確拆分逗號字串之問題。
  - 修復前端側邊欄雙重渲染重疊之版面異常。

---

## [1.0.0] - 2026-08-01

### 新增 (Added)

- 增強型混合 RAG 檢索系統（FAISS + Whoosh BM25 + Cross-Encoder Reranker）。
- RSA-2048 JWT 認證與令牌黑名單撤銷機制。
- `security_logging.py` 敏感資料雙層脫敏機制（物件遞迴與正則遮罩）。
- 文件管理與知識庫切分向量化背景任務。
