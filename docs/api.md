# AskMiao API 參考手冊

[繁體中文](api.md) | [English](api_en.md)

> 本文件說明 AskMiao 後端（**4.0.0** 之後的未發行版本）的 REST 與 SSE 串流端點，內容依 `backend/app/api/` 的實際路由撰寫。設定 `ENABLE_API_DOCS=true` 時，後端另外在 `http://localhost:8001/docs`（Swagger UI）與 `http://localhost:8001/redoc` 提供互動測試，OpenAPI 規格位於 `/openapi.json`；這三個路徑不需要登入且會列出所有端點與參數，對外服務時請保持 `ENABLE_API_DOCS=false`（範本值），此時三者一律回傳 `404`。

## 目錄

- [0. 通用約定](#0-通用約定)
- [1. 身分認證 `/api/auth`](#1-身分認證-apiauth)
- [2. 對話與自主研究 `/api/chat`](#2-對話與自主研究-apichat)
- [3. 知識庫文件 `/api/documents`](#3-知識庫文件-apidocuments)
- [4. 自訂 API 工具 `/api/api-tools`](#4-自訂-api-工具-apiapi-tools)
- [5. MCP 伺服器 `/api/mcp`](#5-mcp-伺服器-apimcp)
- [6. 模型清單 `/api/tags`](#6-模型清單-apitags)
- [7. 管理後台 `/api/admin`](#7-管理後台-apiadmin)
- [8. 健康檢查](#8-健康檢查)
- [9. 錯誤處理](#9-錯誤處理)
- [10. 已知限制](#10-已知限制)

---

## 0. 通用約定

| 項目 | 說明 |
|---|---|
| 基礎位址 | `http://localhost:8001`（由 `HOST` / `PORT` 決定） |
| 認證方式 | 標頭帶 `Authorization: Bearer <access_token>`；重新整理權杖放在 HttpOnly Cookie `refresh_token`（路徑 `/api/auth`），由瀏覽器自動攜帶 |
| 內容型態 | 檔案上傳為 `multipart/form-data`，對話串流為 `text/event-stream`，其餘皆為 `application/json` |
| 時間格式 | ISO 8601，時間為 UTC 但不含時區標記（例如 `2026-09-25T02:30:00`） |
| 速率限制 | 每個來源 IP 每 60 秒 `RATE_LIMIT_PER_MINUTE` 次（預設 60），超過回傳 `429`；來源 IP 預設為實際連線對端，只有設定 `FORWARDED_ALLOW_IPS` 時才採信該代理送來的 `X-Forwarded-For` |
| 請求本文上限 | 一般請求 1 MiB；`POST /api/chat/send` 帶有效存取權杖時放寬，`POST /api/documents/upload` 只在有效存取權杖的 `is_admin` 聲明為 `true` 時放寬；超過回傳 `413` `{"detail": "請求內容超過大小上限"}`，詳見 [設定參考：資源上限](configuration.md#資源上限) |

### 權限層級

| 層級 | 條件 | 未符合時 |
|---|---|---|
| 公開 | 不需要權杖 | — |
| 登入 | 有效且未撤銷的存取權杖，對應的帳號仍存在並為啟用狀態，且簽發時間不早於該帳號的 `tokens_valid_after` | `401` |
| 管理員 | 資料庫中該帳號的 `is_admin` 為 `true` | `403`（`{"detail": "需要管理員權限"}`） |

> [!NOTE]
> 每次請求都依權杖的 `sub` 從資料庫讀取帳號：帳號被刪除或停用後，已簽發的存取權杖立即失效；`is_admin` 與角色也取自資料庫，變更管理員身分後下一個請求就生效。簽發時間早於帳號 `tokens_valid_after` 的權杖一律回傳 `401`：建立帳號時它等於建立時間（帳號刪除後 id 被新帳號重用時，舊權杖不會對應到新帳號），變更密碼時更新為當下（見 [權杖模型](#權杖模型)）。

### 端點總覽

| 方法 | 路徑 | 權限 | 說明 |
|---|---|---|---|
| GET | `/api/auth/registration` | 公開 | 是否開放自行註冊 |
| POST | `/api/auth/register` | 公開 | 註冊並登入（只在 `ALLOW_REGISTRATION=true` 時開放） |
| POST | `/api/auth/login` | 公開 | 登入 |
| POST | `/api/auth/refresh` | 公開（需 Cookie） | 以重新整理權杖換發權杖 |
| GET | `/api/auth/me` | 登入 | 取得個人資料 |
| PUT | `/api/auth/me` | 登入 | 更新電子郵件或密碼 |
| POST | `/api/auth/change-password` | 登入 | 變更密碼 |
| POST | `/api/auth/logout` | 存取權杖（只驗簽章） | 登出並撤銷權杖 |
| POST | `/api/auth/validate-token` | 登入 | 檢查存取權杖是否有效 |
| POST | `/api/chat/send` | 登入 | 送出訊息，以 SSE 串流回應 |
| GET | `/api/chat/models` | 公開 | 可用模型與預設模型 |
| GET | `/api/chat/tools` | 登入 | Agent 目前可用的工具定義 |
| POST | `/api/chat/approvals/{approval_id}` | 登入（僅限發問者） | 核准或拒絕等待中的工具呼叫 |
| GET | `/api/chat/conversations` | 登入 | 自己的對話清單 |
| POST | `/api/chat/conversations` | 登入 | 建立對話 |
| GET | `/api/chat/conversations/{conversation_id}` | 登入 | 單一對話與全部訊息 |
| GET | `/api/chat/conversations/{conversation_id}/messages` | 登入 | 分頁取得訊息 |
| DELETE | `/api/chat/conversations/{conversation_id}` | 登入 | 刪除對話 |
| POST | `/api/documents/upload` | 管理員 | 上傳文件並建立索引 |
| GET | `/api/documents/` | 管理員 | 文件清單 |
| POST | `/api/documents/{document_id}/regenerate-summary` | 管理員 | 重新生成 AI 摘要 |
| PUT | `/api/documents/{document_id}/summary` | 管理員 | 手動修訂摘要 |
| DELETE | `/api/documents/{document_id}` | 管理員 | 刪除文件 |
| POST | `/api/documents/rebuild-index` | 管理員 | 從資料庫完整重建索引 |
| POST | `/api/api-tools/parse-spec` | 管理員 | 解析 OpenAPI 規格 |
| POST | `/api/api-tools/import` | 管理員 | 批次匯入工具 |
| GET | `/api/api-tools` | 管理員 | 工具清單 |
| POST | `/api/api-tools` | 管理員 | 手動建立工具 |
| GET | `/api/api-tools/{tool_id}` | 管理員 | 單一工具 |
| PUT | `/api/api-tools/{tool_id}` | 管理員 | 更新工具 |
| PATCH | `/api/api-tools/{tool_id}/toggle` | 管理員 | 切換啟用狀態 |
| DELETE | `/api/api-tools/{tool_id}` | 管理員 | 刪除工具 |
| POST | `/api/api-tools/{tool_id}/test` | 管理員 | 實際呼叫一次工具 |
| GET | `/api/mcp/presets` | 管理員 | MCP 伺服器範本 |
| GET | `/api/mcp/servers` | 管理員 | MCP 伺服器清單 |
| POST | `/api/mcp/servers` | 管理員 | 新增伺服器並探索工具 |
| GET | `/api/mcp/servers/{server_id}` | 管理員 | 單一伺服器 |
| PUT | `/api/mcp/servers/{server_id}` | 管理員 | 更新伺服器 |
| DELETE | `/api/mcp/servers/{server_id}` | 管理員 | 刪除伺服器 |
| POST | `/api/mcp/servers/{server_id}/discover` | 管理員 | 重新探索工具 |
| PATCH | `/api/mcp/servers/{server_id}/toggle` | 管理員 | 切換啟用狀態 |
| POST | `/api/mcp/servers/{server_id}/tools/{tool_name}/test` | 管理員 | 實際呼叫一次 MCP 工具 |
| GET | `/api/tags` | 公開 | 相容 Ollama 格式的模型清單 |
| GET | `/api/admin/users` | 管理員 | 使用者清單 |
| PUT | `/api/admin/users/{user_id}` | 管理員 | 更新使用者 |
| DELETE | `/api/admin/users/{user_id}` | 管理員 | 刪除使用者 |
| GET | `/api/admin/statistics` | 管理員 | 系統統計（快取 180 秒） |
| GET | `/api/admin/conversations` | 管理員 | 最近 50 段對話 |
| GET | `/api/admin/conversations/{conversation_id}/messages` | 管理員 | 任一對話的訊息 |
| DELETE | `/api/admin/conversations/{conversation_id}` | 管理員 | 刪除任一對話 |
| GET | `/api/admin/documents` | 管理員 | 文件清單（新到舊） |
| DELETE | `/api/admin/documents/{document_id}` | 管理員 | 刪除文件 |
| GET | `/api/admin/rag-config` | 管理員 | 目前的檢索參數 |
| GET | `/api/admin/vector-store/info` | 管理員 | 索引基本資訊 |
| GET | `/api/admin/vector-store/statistics` | 管理員 | 索引統計 |
| POST | `/api/admin/vector-store/reindex` | 管理員 | 以現有片段重新計算向量 |
| DELETE | `/api/admin/vector-store/clear` | 管理員 | 清空片段與索引 |
| GET | `/` | 公開 | 存活訊息 |
| GET | `/health` | 公開 | 健康檢查 |

> [!NOTE]
> 不需登入的 `GET /api/external-tags` 與示範用的 WebSocket `/api/chat/ws/{user_id}` 已移除（前端都沒有使用）：模型清單請改用 `GET /api/chat/models` 或 `GET /api/tags`，對話一律使用 [2.1 的 SSE 端點](#21-post-apichatsend)。

---

## 1. 身分認證 `/api/auth`

### 權杖模型

| 權杖 | 存放位置 | 有效期 | 用途 |
|---|---|---|---|
| 存取權杖（access token） | 回應 JSON 的 `tokens.access_token`，由前端放在 `Authorization` 標頭 | `ACCESS_TOKEN_EXPIRE_MINUTES`（預設 30 分鐘） | 呼叫所有需要登入的端點；內含 `sub`、`username`、`email`、`role`、`is_admin`，但後端只用 `sub` 與 `iat` 對應資料庫帳號，身分與權限以資料庫為準 |
| 重新整理權杖（refresh token） | HttpOnly Cookie `refresh_token`，路徑 `/api/auth` | `REFRESH_TOKEN_EXPIRE_DAYS`（預設 7 天） | 只用於 `POST /api/auth/refresh`，只能使用一次；每次換發都會重設 Cookie |

權杖一律以 RSA-2048 私鑰簽署 RS256，後端無法載入 RSA 金鑰時拒絕啟動。回應 JSON 中的 `tokens.refresh_token` 一律是空字串，真正的重新整理權杖只存在 Cookie 中；`expires_in` 目前固定回傳 `1800`，實際到期時間以權杖內的 `exp` 為準。存取與重新整理權杖的 `iat` 是保留微秒小數的秒數（RFC 7519 的 NumericDate 允許小數，例如 `1791561600.640123`），`exp` 仍為整數秒；自行解析權杖的用戶端不要假設 `iat` 是整數。

**變更密碼會撤銷所有權杖**：`users.tokens_valid_after` 在建立帳號時等於建立時間，變更密碼（帶 `new_password` 的 [1.5](#15-put-apiauthme) 或 [1.6](#16-post-apiauthchange-password)）時更新為當下；簽發時間（`iat`）早於它的存取與重新整理權杖一律回傳 `401`，包括發出這次請求的存取權杖與其他裝置上的工作階段。兩者比對到微秒，與變更密碼同一秒內、但較早簽發的權杖也會失效；變更後才簽發的權杖（例如立刻重新登入）照常有效。變更成功的回應會同時清除重新整理權杖 Cookie，用戶端必須以新密碼重新登入（前端會清除登入狀態並導回登入頁）。

### 1.1 POST /api/auth/register

註冊新帳號，成功後直接登入：回傳存取權杖，並把重新整理權杖寫入 Cookie。新帳號一律是一般使用者。

只有必填設定 `ALLOW_REGISTRATION` 為 `true` 時才開放註冊；設為 `false`（範本值）時回傳 `403` 並寫入安全日誌（`REGISTER_REJECTED`），帳號（含第一位管理員）改由管理員在 `backend/` 下執行 `python scripts/create_user.py --username <名稱> --email <電子郵件>` 建立：密碼以互動方式輸入兩次，套用與註冊相同的規則，加上 `--admin` 則建立管理員（見 [設定參考：註冊與建立帳號](configuration.md#註冊與建立帳號)）。用戶端可先以 [1.9](#19-get-apiauthregistration) 查詢是否開放註冊。

**請求主體**

| 欄位 | 型態 | 必填 | 規則 |
|---|---|---|---|
| `username` | string | 是 | 3–50 字元，只能包含文字（含中文）、數字、底線與連字號 |
| `email` | string | 是 | 合法的電子郵件格式 |
| `password` | string | 是 | 8–256 字元，且包含大寫字母、小寫字母與數字 |

**回應**：`201 Created`

```json
{
  "user": {
    "id": 1,
    "username": "miao_user",
    "email": "user@example.com",
    "role": "user",
    "is_active": true,
    "is_admin": false,
    "created_at": "2026-09-25T02:30:00",
    "last_login": null
  },
  "tokens": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "",
    "token_type": "bearer",
    "expires_in": 1800
  },
  "message": "註冊成功"
}
```

| 狀態碼 | 情況 |
|---|---|
| `400` | `使用者名稱已被使用`、`電子郵件已被使用`，或密碼強度不足（例如 `密碼必須包含至少一個大寫字母`） |
| `403` | `目前不開放註冊，請聯繫管理員建立帳號`（`ALLOW_REGISTRATION=false`） |
| `422` | 欄位格式錯誤（長度、字元、電子郵件格式） |

### 1.2 POST /api/auth/login

以使用者名稱**或**電子郵件登入。

**請求主體**：`{"username": "miao_user", "password": "Secret123"}`（`username` 最多 254 字元，`password` 最多 256 字元）

**回應**：`200 OK`，結構同註冊（`message` 為 `登入成功`），並更新 `last_login`。以舊版 bcrypt 雜湊儲存的密碼會在登入成功時自動改存為 Argon2。

**登入失敗節流**：

- 失敗次數依登入識別與來源 IP 分別計算。登入識別是 `username` 欄位的值（去除前後空白、不分大小寫；使用者名稱與電子郵件各自計數），不存在的帳號同樣計數；來源 IP 的判定方式與速率限制相同（見 [0. 通用約定](#0-通用約定)）。
- 在 `LOGIN_FAILURE_WINDOW_SECONDS` 秒內，同一識別失敗達 `LOGIN_MAX_FAILURES_PER_ACCOUNT` 次，或同一來源 IP 失敗達 `LOGIN_MAX_FAILURES_PER_ADDRESS` 次時，該識別或 IP 的登入暫停 `LOGIN_LOCKOUT_SECONDS` 秒。達到門檻的那次請求仍回傳 `401`；暫停期間的登入請求一律回傳 `429`，`Retry-After` 為剩餘秒數（無條件進位），即使密碼正確也不驗證，回應不透露密碼是否正確。到期後自動解除並重新計數；暫停只影響登入，已簽發的權杖照常有效。
- 登入成功只清除該識別的失敗紀錄，同一 IP 對其他識別的失敗仍然計數。經由代理連線而所有使用者共用同一個來源 IP 時，依位址的門檻要設得比依帳號的寬。
- 這四個設定都是必填（最小值 1），`backend/.env.example` 的範本值依序為 `5`、`20`、`900`、`900`，詳見 [設定參考：登入失敗節流](configuration.md#登入失敗節流)。

| 狀態碼 | 情況 |
|---|---|
| `401` | `使用者名稱或密碼錯誤`（帳號不存在、密碼錯誤或帳號停用時都回傳相同訊息） |
| `422` | 欄位超過長度上限 |
| `429` | `登入失敗次數過多，請稍後再試`：該識別或來源 IP 的登入暫停中，回應附 `Retry-After` 標頭 |

> [!NOTE]
> 失敗計數與暫停狀態存在後端行程的記憶體中，後端重啟後清空，多行程部署時各自計算；追蹤的登入識別與來源 IP 各最多 10,000 個，超過時最久沒有新失敗的先淘汰，其失敗紀錄與暫停一併清除。

### 1.3 POST /api/auth/refresh

從 Cookie 讀取重新整理權杖，換發新的存取權杖並重設 Cookie，不需要 `Authorization` 標頭。權杖同樣依 `sub` 對應資料庫帳號（帳號須存在且啟用，簽發時間不早於 `tokens_valid_after`），用過的重新整理權杖立即寫入撤銷名單，重複使用會回傳 `401`。

**回應**：`200 OK`

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "",
  "token_type": "bearer",
  "expires_in": 1800
}
```

| 狀態碼 | 情況 |
|---|---|
| `401` | `找不到重新整理權杖`、`重新整理權杖類型無效`、`權杖已被撤銷`（含已用過的權杖），或 `認證權杖無效：驗證失敗`（簽章無效、已過期、帳號不存在或已停用，或簽發後變更過密碼）；其他錯誤為 `重新整理權杖失敗` |

### 1.4 GET /api/auth/me

取得目前登入者的個人資料（`UserProfile`：`id`、`username`、`email`、`role`、`is_active`、`is_admin`、`created_at`、`last_login`）。

### 1.5 PUT /api/auth/me

更新電子郵件或密碼，只需帶入要變更的欄位。

| 欄位 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `email` | string | 否 | 新的電子郵件，不可與他人重複 |
| `current_password` | string | 變更密碼時必填 | 目前的密碼 |
| `new_password` | string | 否 | 新密碼，規則同註冊 |

密碼欄位最多 256 字元。**回應**：`200 OK`，回傳更新後的 `UserProfile`。錯誤時回傳 `400`：`該電子郵件已被使用`、`請提供目前的密碼`、`目前的密碼錯誤` 或密碼強度訊息。

帶 `new_password` 且變更成功時，該帳號所有已簽發的權杖（含這次請求使用的存取權杖）立即失效，回應同時清除重新整理權杖 Cookie，用戶端必須以新密碼重新登入（見 [權杖模型](#權杖模型)）；只變更 `email` 不影響權杖。

### 1.6 POST /api/auth/change-password

| 欄位 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `current_password` | string | 是 | 目前的密碼 |
| `new_password` | string | 是 | 新密碼，規則同註冊 |
| `confirm_password` | string | 是 | 須與 `new_password` 相同，否則回傳 `422` |

**回應**：`200 OK` `{"message": "密碼修改成功，所有裝置都需要以新密碼重新登入", "success": true}`；目前密碼錯誤時回傳 `400` `目前的密碼錯誤`，新密碼不符規則時回傳 `400` 與密碼強度訊息。

變更成功後，該帳號所有已簽發的權杖（含這次請求使用的存取權杖與其他裝置上的工作階段）立即失效，回應同時清除重新整理權杖 Cookie，用戶端必須以新密碼重新登入（見 [權杖模型](#權杖模型)）。

### 1.7 POST /api/auth/logout

把 `Authorization` 標頭中的存取權杖與 Cookie 中的重新整理權杖寫入撤銷名單（保留到各自到期為止），並刪除 Cookie。

存取權杖只驗簽章與類型，不檢查是否過期、是否已撤銷或帳號狀態，因此存取權杖過期後仍能登出：重新整理權杖照樣撤銷、Cookie 照樣清除（已過期的存取權杖本來就無效，不會再寫入撤銷名單）。`Authorization` 標頭仍為必要，跨站表單無法觸發登出。

**回應**：`200 OK` `{"message": "登出成功", "success": true}`

| 狀態碼 | 情況 |
|---|---|
| `401` | 缺少 `Authorization` 標頭（`Not authenticated`）、簽章無效（`認證權杖無效：驗證失敗`），或不是存取權杖（`權杖類型無效`） |

> [!NOTE]
> 撤銷名單存在後端行程的記憶體中（最多 100,000 筆，滿了先淘汰最早到期者），後端重啟後會清空，尚未過期的舊權杖會重新有效。變更密碼造成的失效以資料庫中的 `tokens_valid_after` 判斷，不受重啟影響。

### 1.8 POST /api/auth/validate-token

**回應**：`200 OK` `{"message": "權杖有效", "success": true}`；權杖無效時回傳 `401`。

### 1.9 GET /api/auth/registration

回傳是否開放自行註冊，不需要登入，值即 `ALLOW_REGISTRATION`。前端據此決定登入頁是否顯示註冊入口；未開放或查詢失敗時，註冊頁改為顯示說明。

**回應**：`200 OK` `{"enabled": false}`

---

## 2. 對話與自主研究 `/api/chat`

### 2.1 POST /api/chat/send

送出訊息並啟動 `ResearchAgent`。回應為 **Server-Sent Events** 串流（`Content-Type: text/event-stream`，附 `Cache-Control: no-cache` 與 `X-Accel-Buffering: no`）。

**請求主體**

| 欄位 | 型態 | 必填 | 預設 | 說明 |
|---|---|---|---|---|
| `content` | string | 是 | — | 使用者的問題，最多 20,000 字元 |
| `conversation_id` | integer | 否 | `null` | 對話 ID；留空、不存在或不屬於自己時會建立新對話 |
| `model_name` | string | 否 | 預設模型 | 要使用的模型，必須在 [可用模型清單](configuration.md#模型清單) 內或等於 `MODEL_NAME`，否則回傳 `400` `不支援的模型`；供應商依名稱自動路由 |
| `reasoning_effort` | string | 否 | `medium` | 推理程度，只傳給 OpenAI 與 Azure OpenAI，見下方說明 |
| `attachments` | array | 否 | `[]` | 附件，最多 5 個，見下表 |

`attachments[]` 欄位：

| 欄位 | 型態 | 說明 |
|---|---|---|
| `filename` | string | 檔名，最多 255 字元 |
| `file_type` | string | MIME 類型，最多 255 字元；`image/*` 交給視覺模型，其他類型抽取文字 |
| `file_size` | integer | 選填，檔案大小 |
| `data_url` | string | 選填，必須是 base64 編碼的 `data:` URL（`http(s)://` 等遠端網址一律拒絕），解碼後單一附件最多 15 MiB、同一則訊息合計最多 20 MiB；圖片必須提供 |
| `content` | string | 選填，已擷取好的純文字，最多 50,000 字元；未提供時由 `data_url` 解碼後擷取（PDF 最多 OCR 20 頁） |

每個附件放進模型脈絡的文字最多 50,000 字元，超過的部分截斷。由 `data_url` 擷取文字時套用比管理員上傳更嚴格的聊天附件解析預算（例如 `.docx`、`.pptx`、`.xlsx` 解壓總量最多 64 MiB，`.docx`、`.pptx` 會建成 DOM 的 XML 合計最多 8 MiB），整個後端行程同時最多解析 2 個附件，其餘排隊等候；超過預算的附件不會讓請求失敗，而是以「附件超過解析上限，未讀取內容」告知模型。完整上限見 [設定參考：資源上限](configuration.md#資源上限)。

| 狀態碼 | 情況 |
|---|---|
| `400` | `model_name` 不在可用模型清單內 |
| `413` | 請求本文超過上限（未帶有效存取權杖時為 1 MiB），或這位使用者存在資料庫的附件總量將超過 200 MiB（`附件儲存空間已達上限…`） |
| `422` | 欄位驗證失敗：訊息過長、附件過多或過大、`data_url` 不是 base64 `data:` URL 等 |
| `429` | 這位使用者已有 2 個回答正在串流 |

**`reasoning_effort` 的處理**：前端提供 `none`、`low`、`medium`、`high`、`xhigh` 五檔；後端接受 `none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max`，其他值不會傳給模型。名稱含 `gpt-5` 的模型在帶工具呼叫時一律改送 `none`。

#### SSE 事件

每個事件的格式為 `event: <名稱>\ndata: <JSON>\n\n`，依序如下：

| 事件 | 時機 | `data` 欄位 |
|---|---|---|
| `start` | 使用者訊息已存入資料庫 | `conversation_id`、`user_message_id` |
| `step_start` | 每次工具呼叫開始 | `step`（從 1 起算）、`tool`、`arguments` |
| `approval_required` | 工具需要核准，Agent 暫停等待（見 [2.9](#29-post-apichatapprovalsapproval_id)） | `approval_id`、`step`、`tool`、`tool_display_name`、`target`、`arguments` |
| `approval_resolved` | 使用者回覆或等待逾時 | `approval_id`、`approved`（逾時為 `false`） |
| `step_end` | 每次工具呼叫結束 | `step`、`tool`、`arguments`、`output_preview`（結果 JSON 的前 300 字）、`duration_seconds`、`status`（`success` / `error`） |
| `token` | 答案文字 | `content` |
| `sources` | 答案完成後 | `sources`（來源名稱，去重）、`sources_detail`（見下表） |
| `done` | 助理訊息已存入資料庫 | `message_id`、`conversation_id`、`answer`、`sources`、`sources_detail`、`research_trace`（所有 `step_end` 的內容） |
| `error` | API 層發生未預期例外 | `detail`（含錯誤代碼的訊息）、`error_id` |

`sources_detail` 只列答案以 `[n]` 實際引用的條目，依第一次引用的順序排列；沒有任何引用時 `sources` 與 `sources_detail` 皆為空陣列。每筆的欄位依來源而定：

| 來源工具 | 欄位 |
|---|---|
| `search_knowledge_base` | `citation`、`source`（檔名）、`chunk`（段落序號）、`score`、`snippet`（前 200 字） |
| `filter_and_count_records` | `citation`、`source`、`snippet` |
| `web_search`、`web_fetch` | `citation`、`source`（網頁標題或網址）、`url`、`snippet` |

`approval_required` 的 `tool_display_name` 是工具的顯示名稱（MCP 工具為 `<伺服器顯示名稱> → <工具名稱>`），`target` 標出這次呼叫實際送往的位置：

| 工具 | `target` 格式 | 範例 |
|---|---|---|
| 自訂 API 工具 | HTTP 方法與工具設定網址的主機（有指定埠號時含埠號，不含路徑與查詢字串） | `POST api.example.com` |
| MCP 伺服器（`http` / `sse`） | 大寫的傳輸方式與伺服器網址的主機 | `HTTP mcp.example.com:8443` |
| MCP 伺服器（`stdio`） | `本機指令` 加上指令的檔名（不含路徑與參數） | `本機指令 npx` |

**串流範例**

```text
event: start
data: {"conversation_id": 42, "user_message_id": 107}

event: step_start
data: {"step": 1, "tool": "search_knowledge_base", "arguments": {"query": "特休假 申請流程"}}

event: step_end
data: {"step": 1, "tool": "search_knowledge_base", "arguments": {"query": "特休假 申請流程"}, "output_preview": "{\"query\": \"特休假 申請流程\", \"target_document\": null, \"total_found\": 2, ...", "duration_seconds": 4.21, "status": "success"}

event: token
data: {"content": "特休假需先在系統填寫假單，經直屬主管核准後生效 [1]。"}

event: sources
data: {"sources": ["員工手冊.pdf"], "sources_detail": [{"citation": 1, "source": "員工手冊.pdf", "chunk": 3, "score": 0.9412, "snippet": "特休假申請需於系統填寫假單……"}]}

event: done
data: {"message_id": 108, "conversation_id": 42, "answer": "特休假需先在系統填寫假單，經直屬主管核准後生效 [1]。", "sources": ["員工手冊.pdf"], "sources_detail": [...], "research_trace": [...]}
```

**行為細節**

- 模型不再呼叫工具時，該次答案會以**一個** `token` 事件整段送出；只有工具輪數（`AGENT_MAX_TURNS`）用完或模型回傳空內容時，才會以多個 `token` 事件逐段串流。
- 模型呼叫失敗或串流中斷時，錯誤會以 `token` 事件夾帶錯誤代碼送出（例如 `在執行自主研究時遇到連線異常（錯誤代碼：…）`），而不是 `error` 事件；伺服器日誌可依代碼查到完整例外。
- 助理訊息在串流完成後才寫入資料庫。用戶端中途中斷連線（例如按下「停止」）時，這次的回答不會被儲存，使用者訊息則已存入。
- 新對話的標題是第一則訊息的前 50 字。
- 助理訊息的 `sources`、`sources_detail` 與 `research_trace` 會以 JSON 存入訊息的 `context_used` 資料庫欄位；附件資訊則存於使用者訊息的 `context_used`。API 回應只提供解析後的欄位，不再回傳原始的 `context_used`。
- 每次工具結果放進模型脈絡前最多 20,000 字元，超過的部分截斷。
- 串流期間後端會先把資料庫連線還給連線池，結束時再取得連線儲存回答。

### 2.2 GET /api/chat/models

取得可用模型與預設模型。清單產生方式與預設模型規則見 [設定參考：模型清單](configuration.md#模型清單)；需要查詢遠端清單時，結果（含失敗）快取 30 秒。

```json
{
  "models": ["gpt-6-sol", "gpt-6-luna"],
  "default": "gpt-6-sol"
}
```

### 2.3 GET /api/chat/tools

取得 Agent 目前可用的工具定義（需登入），格式為 OpenAI Function Calling 的 `tools` 結構，包含：

- 內建工具 `search_knowledge_base`、`filter_and_count_records`、`web_search`、`web_fetch`（`ENABLE_WEB_SEARCH=false` 時不含後兩者）。`search_knowledge_base` 的說明會列出知識庫中每份文件的檔名與 AI 摘要，幫助模型判斷該查哪份文件。
- 啟用中的自訂 API 工具（說明前綴 `【外部自訂 API】`）。
- 啟用中 MCP 伺服器的已探索工具，名稱為 `mcp_<伺服器>_<工具>`（說明前綴 `【MCP 協定工具】`）。

```json
{
  "status": "success",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_knowledge_base",
        "description": "檢索內部知識庫。目前知識庫收錄以下各具不同主題之專屬文件庫……",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {"type": "string"},
            "target_document": {"type": "string"},
            "top_k": {"type": "integer", "default": 3}
          },
          "required": ["query"]
        }
      }
    }
  ]
}
```

載入外部工具發生例外時，`status` 為 `partial`，附 `error` 與 `error_id`，`tools` 只含內建工具。

### 2.4 GET /api/chat/conversations

取得自己的對話清單，依最後更新時間由新到舊排列，最多 **200** 段；每段對話附**最近 5 則**訊息（依時間先後），其中附件只列檔名等資訊，不含 `data_url`。

```json
[
  {
    "id": 42,
    "title": "特休假申請流程",
    "created_at": "2026-09-25T01:00:00",
    "updated_at": "2026-09-25T01:30:00",
    "messages": [
      {
        "id": 108,
        "content": "特休假需先在系統填寫假單……[1]。",
        "is_user": false,
        "created_at": "2026-09-25T01:30:00",
        "context_used": null,
        "model_name": "gpt-6-sol",
        "reasoning_effort": null,
        "attachments": [],
        "sources": ["員工手冊.pdf"],
        "sources_detail": [...],
        "research_trace": [...]
      }
    ]
  }
]
```

訊息物件的 `sources`、`sources_detail`、`research_trace` 與 `attachments` 由資料庫的 `context_used` 欄位解析而來；回應中的 `context_used` 一律為 `null`（原始內容含附件的 base64，不再重複輸出）。`reasoning_effort` 目前不會儲存，一律為 `null`。

### 2.5 POST /api/chat/conversations

建立空白對話，不需要請求主體，標題為 `DEFAULT_CONVERSATION_TITLE`（預設「新對話」）。回傳對話物件（`messages` 為空陣列）。

### 2.6 GET /api/chat/conversations/{conversation_id}

取得單一對話與最新的 500 則訊息（依時間先後）。對話不存在或不屬於自己時回傳 `404` `找不到該對話`。

### 2.7 GET /api/chat/conversations/{conversation_id}/messages

分頁取得訊息。

| 查詢參數 | 預設 | 說明 |
|---|---|---|
| `limit` | `100` | 取回的訊息數，最多 500 |
| `offset` | `0` | 從最新一則往回略過的數量 |

回傳最新的 `limit` 則訊息（依時間先後排列），以 `offset` 往前翻頁。對話不存在或不屬於自己時回傳空陣列。

### 2.8 DELETE /api/chat/conversations/{conversation_id}

刪除自己的對話與其所有訊息。

**回應**：`200 OK` `{"message": "對話已刪除"}`；找不到時回傳 `404`。

### 2.9 POST /api/chat/approvals/{approval_id}

核准或拒絕 Agent 暫停等待中的工具呼叫。自訂 API 工具與 MCP 伺服器設有 `requires_approval` 旗標（見 [工具物件](#工具物件) 與 [伺服器物件](#伺服器物件)）；Agent 要呼叫這類工具時，`POST /api/chat/send` 的串流先送出 `approval_required` 事件並暫停，等使用者以此端點回覆，再送出 `approval_resolved` 事件。設計背景見 [ADR-0006](adr/0006-tool-call-approval.md)。

**請求主體**：`{"approved": true}`（`false` 表示拒絕）

**回應**：`200 OK` `{"approval_id": "…", "approved": true}`

| 狀態碼 | 情況 |
|---|---|
| `404` | `找不到待核准的工具呼叫，可能已逾時或已處理`：`approval_id` 不存在、已處理、已逾時，或不是由目前登入者發問的串流所建立 |

- 只有發問的使用者能處理自己的項目，管理員也不能代為核准。
- 300 秒內沒有回覆視為拒絕；使用者中斷串流時，等待中的項目一併取消。
- 拒絕或逾時時工具不會執行，Agent 收到「使用者未核准」的工具結果後改以已取得的資料回答。
- 沒有可核准的使用者時（非互動式呼叫），需要核准的工具一律不執行。
- 待核准項目存在後端行程的記憶體中，後端重啟後失效。

---

## 3. 知識庫文件 `/api/documents`

> 本模組所有端點都需要**管理員**權限。

### 3.1 POST /api/documents/upload

上傳文件至知識庫。每個檔案依序經過：檔名與副檔名檢查 → 大小檢查 → 擷取文字（PDF 空白或亂碼頁以視覺模型 OCR）→ 重複內容檢查 → 生成 AI 摘要 → 存入 `documents` → 切塊並寫入 `rag_chunks`、FAISS 與 BM25。

**請求**：`multipart/form-data`，欄位名稱為 `file`，可重複帶入，單次最多 10 個檔案。

- 支援副檔名：`.txt`、`.md`、`.markdown`、`.pdf`、`.docx`、`.pptx`、`.xlsx`、`.csv`、`.json`、`.yaml`、`.yml`、`.xml`、`.html`、`.htm`、`.log`、`.py`、`.js`、`.ts`、`.tsx`、`.jsx`、`.java`、`.cpp`、`.c`、`.sql`、`.sh`、`.ini`、`.env`。
- 單檔上限為 `MAX_FILE_SIZE_MB`（範本 10 MB）；整個請求本文上限為 10 × `MAX_FILE_SIZE_MB` MiB + 1 MiB，而且只有存取權杖有效且其 `is_admin` 聲明為 `true` 時才適用（否則為 1 MiB），超過回傳 `413`。本文上限在解析請求前依權杖內的聲明決定；是否為管理員仍以資料庫為準，已被取消管理員身分的帳號會收到 `403`。
- `.docx`、`.pptx`、`.xlsx` 解壓後總大小超過 200 MiB、內含超過 10,000 個檔案，或壓縮比超過 100（解壓後超過 10 MiB 的單一成員與整個檔案都檢查）時拒絕解析；PDF 掃描頁點陣化時每頁最多 25 MP。
- 檔名中的空白會換成底線；與既有檔名相同時自動加上 `_1`、`_2` 等後綴；含 `/`、`\`、`..`、`<`、`>`、`:`、`"`、`|`、`?`、`*` 的檔名會被拒絕。
- 擷取出的文字與既有文件完全相同時視為重複，不會重複建立。
- 切塊方式：Q&A 格式一問一答成一個片段；結構化記錄與 JSON 逐筆成為片段；其餘依 `CHUNK_SIZE` / `CHUNK_OVERLAP` 遞迴切塊。

**回應**：`200 OK`，逐檔回報結果，每筆以 `http_status` 標示該檔的處理狀態：

```json
{
  "results": [
    {
      "filename": "員工手冊.pdf",
      "status": "success",
      "document_id": 101,
      "content_length": 28460,
      "content_type": "application/pdf",
      "qa_detected": false,
      "qa_pairs": 0,
      "http_status": 201
    },
    {
      "filename": "重複文件.txt",
      "status": "duplicate",
      "detail": "內容已存在",
      "existing_document_id": 88,
      "http_status": 409
    },
    {
      "filename": "setup.exe",
      "status": "failed",
      "detail": "檔名驗證失敗: 無效的檔名或不允許的副檔名",
      "http_status": 400
    }
  ]
}
```

未帶檔案或超過 10 個檔案時，整個請求回傳 `400`。

### 3.2 GET /api/documents/

列出所有文件（`id`、`filename`、`content`、`file_type`、`description`、`uploaded_by`、`created_at`、`is_processed`）。`content` 是擷取出的完整文字，資料量可能很大。尚未有摘要的文件會在這次請求中補生成並寫回，因此可能較慢。

### 3.3 POST /api/documents/{document_id}/regenerate-summary

重新生成 AI 大綱與摘要。

```json
{
  "message": "文件大綱與摘要重新生成成功",
  "document_id": 101,
  "description": "本文件說明差勤與請假制度……"
}
```

### 3.4 PUT /api/documents/{document_id}/summary

手動修訂摘要。**請求主體**：`{"description": "自訂摘要內容"}`；**回應**：`{"message": "文件大綱更新成功", "document_id": 101, "description": "自訂摘要內容"}`。

### 3.5 DELETE /api/documents/{document_id}

刪除文件：先刪除資料庫紀錄，再移除該文件的片段、向量與 BM25 項目，最後刪除上傳原檔。進行中的索引寫入會在持鎖後確認文件仍存在，已刪除文件的片段不會被寫回知識庫。

**回應**：`200 OK` `{"message": "文件刪除成功"}`；找不到時回傳 `404` `文件不存在`。

### 3.6 POST /api/documents/rebuild-index

以資料庫中的文件完整重建索引：清空片段與索引後，逐份文件重新擷取文字（上傳原檔存在時優先使用）、重新生成 AI 摘要，並依目前的切塊設定重新切塊與建立向量。從 2.x 升級後需要執行一次，文件越多耗時越久。

```json
{
  "message": "索引重建成功（已用新配置重新分塊，並重新生成 AI 智能大綱）",
  "document_count": 6,
  "chunk_count": 214,
  "qa_pairs_detected": 0,
  "chunk_size": 300,
  "chunk_overlap": 100,
  "timestamp": "2026-09-25T10:00:00.000000"
}
```

資料庫沒有文件時回傳 `{"message": "索引重建完成（沒有文件）", "document_count": 0, "chunk_count": 0, "timestamp": "..."}`。

---

## 4. 自訂 API 工具 `/api/api-tools`

把外部 HTTP API 註冊成 Agent 可呼叫的工具。啟用中的工具會在每次組裝工具定義時載入，變更後不需重啟。

> 本模組所有端點（含查詢）都需要**管理員**權限：工具由所有使用者的 Agent 共用，並以設定中的憑證呼叫外部 API（憑證加密存放，回應中以 `••••••••` 遮蔽）。詳見 [ADR-0004](adr/0004-tool-admin-permissions-and-subprocess-isolation.md)。

### 工具物件

| 欄位 | 型態 | 說明 |
|---|---|---|
| `id` | integer | 工具 ID |
| `name` | string | 供模型呼叫的唯一名稱（英數與底線，最長 64 字元） |
| `display_name` | string | 顯示名稱 |
| `description` | string | 用途描述，會影響模型是否呼叫 |
| `category` | string | 分類，預設 `custom_api` |
| `method` | string | HTTP 方法 |
| `url` | string | 完整請求網址，路徑參數以 `{名稱}` 表示 |
| `base_url` / `path` | string | 基底位址與路徑；`url` 為空時以兩者組合 |
| `headers` | object | 固定的請求標頭；回應中除了 `Accept`、`Accept-Encoding`、`Accept-Language`、`Cache-Control`、`Content-Type`、`User-Agent` 以外，每個標頭的值都以 `••••••••` 遮蔽 |
| `auth_type` | string | `none`、`bearer`、`api_key`、`basic` |
| `auth_config` | object | 認證設定，見下表；`token`、`key_value`、`password` 在回應中以 `••••••••` 遮蔽 |
| `parameters_schema` | object | 參數的 JSON Schema，直接作為模型看到的 `parameters`；呼叫時只接受其中 `properties` 宣告的參數 |
| `request_body_schema` | object | 請求主體結構；有 `properties` 時也用來檢查 `request_body` 的欄位 |
| `param_locations` | object | 每個參數的位置：`path`、`query`、`header`、`body` |
| `response_mapping` | string | 保留欄位，目前未使用 |
| `is_enabled` | boolean | 是否啟用 |
| `requires_approval` | boolean | Agent 呼叫前是否需要發問的使用者在對話中核准（見 [2.9](#29-post-apichatapprovalsapproval_id)）。建立或匯入時未指定則依方法決定：`GET`、`HEAD`、`OPTIONS` 為 `false`，其他方法為 `true` |
| `timeout` | integer | 逾時秒數，預設 15 |
| `spec_version` | string | 來源規格版本，手動建立為 `manual` |
| `created_at` / `updated_at` | string | 時間戳記 |
| `credentials_unreadable` | boolean | 只出現在回應中：`headers` 或 `auth_config` 無法以目前的 `TOOL_SECRETS_KEY` 解密時為 `true`，無法解密的欄位回傳 `null`，需要重新輸入 |

| `auth_type` | `auth_config` 欄位 |
|---|---|
| `bearer` | `token` |
| `api_key` | `key_name`（預設 `X-API-Key`）、`key_value`、`key_in`（`header` 或 `query`） |
| `basic` | `username`、`password` |

**憑證的加密與遮蔽**：`headers` 與 `auth_config` 以 `TOOL_SECRETS_KEY`（Fernet）加密後才寫入資料庫，後端啟動時也會把舊版以明文存放的資料改為加密。管理 API 的回應以 `••••••••` 取代秘密值（空值不遮蔽），憑證寫入後無法再從 API 讀出。更新時送出的 `headers` 或 `auth_config` 整個取代原值，其中值仍為 `••••••••` 的鍵沿用已儲存的值；該鍵沒有已儲存的值（包括已儲存的憑證無法解密）時回傳 `400` `欄位 <名稱> 沒有已儲存的值，請輸入實際內容`。更換 `TOOL_SECRETS_KEY` 後，已儲存的憑證都無法解密（`credentials_unreadable` 為 `true`），重新輸入之前該工具無法執行：Agent 呼叫時回傳附錯誤代碼的錯誤，[測試端點](#49-post-apiapi-toolstool_idtest) 回傳 `400` `無法以目前的 TOOL_SECRETS_KEY 解密工具憑證，請重新輸入`；金鑰與加密範圍見 [設定參考：工具憑證加密](configuration.md#工具憑證加密)。

**參數組裝規則**：出現在網址 `{名稱}` 中或位置為 `path` 的參數會替換進網址；`header` 放進標頭；`query` 放進查詢字串；`body` 放進 JSON 主體。未指定位置的參數，`POST`、`PUT`、`PATCH` 放進主體，其他方法放進查詢字串。模型傳入 `request_body` 物件時，整個取代主體。

**只接受宣告的參數**：呼叫端（Agent 或 [4.9](#49-post-apiapi-toolstool_idtest) 的測試）傳入的每個參數都必須列在 `parameters_schema.properties` 中，否則不送出請求，結果的 `status_code` 為 `400`（`工具參數無效：未宣告的參數 …`）；沒有宣告任何參數的工具不接受任何參數。`request_body` 同樣必須宣告；`request_body_schema` 有 `properties` 且 `additionalProperties` 不是 `true` 時，`request_body` 物件中的欄位也必須列在其中，未宣告的欄位以 `request_body.<欄位>` 列出。

**固定的查詢參數**：工具網址中的查詢參數由管理員固定，呼叫端不可覆寫：要放進查詢字串的參數與固定查詢參數同名時不送出請求，`status_code` 為 `400`（`工具參數無效：不可覆寫工具網址中固定的查詢參數 …`）。這些值可能是寫在網址裡的金鑰，因此結果的 `url` 中，固定查詢參數與查詢字串型 API Key 的值一律換成 `[已遮蔽]`，部分失敗情況則只回傳不含查詢字串的網址。

**路徑參數與主機**：路徑參數一律百分比編碼（`/`、`?`、`#`、`%` 都會被編碼），值為 `.` 或 `..` 時拒絕；代入後的網址必須與工具設定的網址同一個 scheme、主機與埠號，否則不送出請求。

### 4.1 POST /api/api-tools/parse-spec

解析 OpenAPI / Swagger 規格（OAS 2.0、3.0、3.1），可傳入 JSON / YAML 全文或規格網址。

| 欄位 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `spec_content_or_url` | string | 是 | 規格全文，或以 `http://`、`https://` 開頭的規格網址 |
| `default_base_url` | string | 否 | 覆寫規格中的伺服器位址 |

規格網址會先經 SSRF 驗證（每一跳都把連線固定在驗證過的 IP），下載上限 10 MB、逾時 15 秒、最多 5 次轉址。YAML 規格不可使用別名（`*alias`），否則回傳 `400`：別名會在後續處理時逐一展開，幾 KB 的規格就可能產生上百 MB 的資料。

**回應**：`200 OK`，只含解析出的端點，不含原始規格（舊版回應中的 `raw_spec` 已移除）

```json
{
  "status": "success",
  "data": {
    "version": "openapi_3.0",
    "title": "Pet Store",
    "description": "",
    "base_url": "https://api.example.com",
    "endpoints_count": 4,
    "endpoints": [
      {
        "name": "get_pet_by_id",
        "display_name": "查詢寵物",
        "description": "查詢寵物",
        "long_description": "",
        "method": "GET",
        "path": "/pets/{petId}",
        "base_url": "https://api.example.com",
        "full_url": "https://api.example.com/pets/{petId}",
        "has_body": false,
        "body_content_type": "application/json",
        "param_locations": {"petId": "path"},
        "parameters_schema": {"type": "object", "properties": {"petId": {"type": "integer"}}, "required": ["petId"]},
        "function_definition": {"type": "function", "function": {"name": "get_pet_by_id", "...": "..."}},
        "tags": ["pets"],
        "spec_version": "openapi_3.0"
      }
    ]
  }
}
```

工具名稱取自 `operationId`（轉為小寫並把非英數字元換成底線）；沒有 `operationId` 時由方法與路徑組成，例如 `get_pets_petid`。

| 狀態碼 | 情況 |
|---|---|
| `400` | 規格格式不合法（含使用 YAML 別名）、無法辨識版本或網址無法取得（訊息可直接顯示給使用者）；網址被 SSRF 防護拒絕時只說明遭拒並附錯誤代碼，完整原因只寫入伺服器日誌 |
| `500` | 其他未預期例外，只回傳錯誤代碼 |

### 4.2 POST /api/api-tools/import

把解析後勾選的端點批次匯入。同名工具會被覆寫並重新啟用。

| 欄位 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `tools` | array | 是 | 端點清單，欄位同解析結果：`name`、`display_name`、`description`、`method`、`path`、`full_url`（必填），以及選填的 `base_url`、`headers`、`auth_type`、`auth_config`、`parameters_schema`、`request_body_schema`、`param_locations`、`spec_version` |
| `global_base_url` | string | 否 | 端點沒有 `base_url` 時使用 |
| `global_headers` | object | 否 | 共用標頭，端點的同名標頭優先 |
| `global_auth_type` | string | 否 | 端點未指定認證時使用 |
| `global_auth_config` | object | 否 | 端點未指定認證設定時使用 |

新匯入的工具依方法決定 `requires_approval`（`GET`、`HEAD`、`OPTIONS` 以外為 `true`）。覆寫既有工具時，原本需要核准的仍維持需要核准；`headers` 與 `auth_config` 則改為這次匯入的內容（含 `global_headers`、`global_auth_config`），不沿用已儲存的憑證，沒有提供時即清空。匯入後可以 4.6 修改。

```json
{
  "status": "success",
  "message": "成功匯入 4 個新工具，更新 1 個既有工具。",
  "imported": 4,
  "updated": 1
}
```

### 4.3 GET /api/api-tools

| 查詢參數 | 說明 |
|---|---|
| `category` | 依分類篩選 |
| `is_enabled` | 依啟用狀態篩選 |
| `search` | 模糊比對 `name`、`display_name`、`description` 與 `url` |

**回應**：`{"status": "success", "total": 5, "tools": [工具物件, ...]}`，依 ID 由新到舊。

### 4.4 POST /api/api-tools

手動建立工具。必填 `name`、`display_name`、`description`、`url`，其餘欄位同[工具物件](#工具物件)。`name` 會正規化為英數與底線組成的名稱。

**回應**：`{"status": "success", "message": "自訂 API 工具建立成功", "tool": {...}}`；同名時回傳 `400` `已存在同名工具: <名稱>`。

### 4.5 GET /api/api-tools/{tool_id}

**回應**：`{"status": "success", "tool": {...}}`；找不到時回傳 `404` `找不到該自訂 API 工具`。

### 4.6 PUT /api/api-tools/{tool_id}

只需帶入要變更的欄位（`name` 無法修改）。把 `method` 改成 `GET`、`HEAD`、`OPTIONS` 以外的方法而未同時指定 `requires_approval` 時，`requires_approval` 自動改為 `true`。送出 `headers` 或 `auth_config` 時整個取代原值，值為 `••••••••` 的鍵沿用已儲存的值，沒有已儲存的值時回傳 `400`（見 [工具物件](#工具物件)）。**回應**：`{"status": "success", "message": "自訂 API 工具更新成功", "tool": {...}}`。

### 4.7 PATCH /api/api-tools/{tool_id}/toggle

**回應**：`{"status": "success", "is_enabled": false, "message": "工具已停用"}`

### 4.8 DELETE /api/api-tools/{tool_id}

**回應**：`{"status": "success", "message": "自訂 API 工具已成功刪除"}`

### 4.9 POST /api/api-tools/{tool_id}/test

以指定參數實際送出一次請求。

**請求主體**：`{"arguments": {"petId": 3}}`

```json
{
  "status": "success",
  "tool_name": "get_pet_by_id",
  "result": {
    "status_code": 200,
    "is_success": true,
    "duration_seconds": 0.42,
    "url": "https://api.example.com/pets/3",
    "data": {"id": 3, "name": "Miao"}
  }
}
```

- 回應為 JSON 時 `data` 是解析後的物件，否則是前 4000 字的文字。上游回應本文超過 1 MiB 時中止讀取，`status_code` 為 `502`。
- 本次請求注入的憑證（標頭值、Bearer 權杖、API Key、Basic 認證）出現在 `data` 或 `url` 中時會換成 `[已遮蔽]`；`url` 中查詢字串型 API Key 與工具網址固定查詢參數的值同樣遮蔽。
- 轉址由後端手動跟隨，最多 5 次，轉址回應的本文一律不讀取；轉址到其他來源（scheme、主機或埠號不同）時，不轉送管理員設定的標頭與認證標頭。
- 整個呼叫（含轉址與逐段讀取回應）的總時限為工具的 `timeout` 秒，超過時中止，`status_code` 為 `504`（`上游在 <timeout> 秒內沒有完成回應`）。
- 第一個請求與每次轉址都會重新經過 SSRF 驗證，並把連線固定在驗證過的 IP；被拒絕時 `status_code` 為 `403`、`is_success` 為 `false`，`error` 只說明遭 SSRF 防護拒絕並附錯誤代碼，另附 `error_id`，完整原因只寫入伺服器日誌。
- 參數未宣告、路徑參數無效、代入後的主機不符，或覆寫工具網址中固定的查詢參數時不送出請求，`status_code` 為 `400`，`error` 說明原因（見 [工具物件](#工具物件)）。
- 其他失敗時 `status_code` 為 `500`，只回傳 `error`（含錯誤代碼）與 `error_id`。
- 自訂 API 工具、MCP HTTP 傳輸與 `web_fetch` 的直接抓取不使用 `HTTP_PROXY`、`HTTPS_PROXY` 環境變數，一律直接連線。
- Agent 呼叫工具時套用相同的執行邏輯；`requires_approval` 為 `true` 時先經使用者核准，本端點（管理員測試）則不需要核准。

---

## 5. MCP 伺服器 `/api/mcp`

管理 Model Context Protocol 伺服器，協定版本 `2024-11-05`，以 JSON-RPC 2.0 進行 `initialize`、`tools/list` 與 `tools/call`。交握時的 `clientInfo` 為 `AskMiao-MCP-Client` 與後端版本號。

> 本模組所有端點（含查詢）都需要**管理員**權限：`stdio` 模式會在主機上執行指定的指令，伺服器設定也含環境變數與標頭等憑證（加密存放，回應中以 `••••••••` 遮蔽）。

### 伺服器物件

| 欄位 | 型態 | 說明 |
|---|---|---|
| `id` | integer | 伺服器 ID |
| `name` | string | 唯一名稱（建立時轉為小寫），用於工具名稱 `mcp_<name>_<tool>` |
| `display_name` / `description` | string | 顯示名稱與說明 |
| `transport_type` | string | `stdio`，或 `http` / `sse`（兩者都以 HTTP POST 傳送 JSON-RPC） |
| `command` / `args` | string / array | `stdio` 模式的執行指令與參數 |
| `env_vars` | object | `stdio` 子行程的額外環境變數；一律視為憑證，回應中每個值都以 `••••••••` 遮蔽 |
| `url` / `headers` | string / object | HTTP 模式的伺服器位址與請求標頭；`headers` 的遮蔽規則同自訂 API 工具 |
| `is_enabled` | boolean | 是否啟用；停用後其工具不會提供給 Agent |
| `requires_approval` | boolean | Agent 呼叫此伺服器的工具前是否需要發問的使用者在對話中核准（見 [2.9](#29-post-apichatapprovalsapproval_id)）；建立時未指定為 `true`，管理員可逐台關閉 |
| `status` | string | `connected`、`disconnected` 或 `error` |
| `last_error` | string | 最近一次探索失敗的原因 |
| `discovered_tools` | array | 最近一次探索到的工具快取（`name`、`description`、`inputSchema`）；名稱不符合 `[A-Za-z0-9_.-]{1,128}` 的工具會被略過 |
| `timeout` | integer | 連線與呼叫逾時秒數，預設 30 |
| `created_at` / `updated_at` | string | 時間戳記 |
| `credentials_unreadable` | boolean | 只出現在回應中：`env_vars` 或 `headers` 無法以目前的 `TOOL_SECRETS_KEY` 解密時為 `true`，無法解密的欄位回傳 `null`，需要重新輸入 |

`env_vars` 與 `headers` 的加密、遮蔽與更新規則同 [自訂 API 工具的憑證](#工具物件)：更新時值仍為 `••••••••` 的鍵沿用已儲存的值，沒有已儲存的值時回傳 `400`；憑證無法解密時，重新輸入之前無法連線或呼叫該伺服器的工具：探索與工具測試端點回傳 `400` `無法以目前的 TOOL_SECRETS_KEY 解密工具憑證，請重新輸入`。

**`stdio` 子行程的環境變數**只繼承系統必要變數，再加上 `env_vars`：Windows 為 `APPDATA`、`HOMEDRIVE`、`HOMEPATH`、`LOCALAPPDATA`、`PATH`、`PATHEXT`、`PROCESSOR_ARCHITECTURE`、`SYSTEMDRIVE`、`SYSTEMROOT`、`TEMP`、`USERNAME`、`USERPROFILE`；其他平台為 `HOME`、`LOGNAME`、`PATH`、`SHELL`、`TERM`、`USER`。後端 `.env` 中的設定不會傳給子行程。

**`stdio` 子行程的生命週期**：每個子行程自成一個程序群組（Windows 為新的 process group，其他平台為新的 session），關閉時連同 `npx`、`uvx` 啟動的孫行程整棵終止（Windows 以 `taskkill /T /F`，其他平台送 `SIGTERM` 再 `SIGKILL` 給整個群組）。每次探索或工具呼叫都會啟動一個子行程，同時最多 4 個，其餘排隊等候，等候超過該伺服器的 `timeout` 秒即失敗。子行程在每次新建的空暫存目錄中執行（結束後刪除），以相對路徑讀不到後端目錄下的 `.env` 與 `keys/`；子行程仍以後端的系統帳號執行，能讀取該帳號可讀的檔案。stderr 持續讀出且只寫入伺服器日誌，單行 JSON-RPC 訊息最多 4 MiB。

**HTTP 模式**的每個請求與轉址都經 SSRF 驗證並把連線固定在驗證過的 IP，指向本機或內網位址的伺服器會被拒絕；本機的 MCP 伺服器請改用 `stdio`。轉址由後端手動跟隨，只接受同一來源（scheme、主機與埠號相同）的轉址，最多 5 次，轉址回應的本文不讀取；轉址到其他來源時中止，管理員設定的標頭與 JSON-RPC 本文不會送往其他網域。每個 JSON-RPC 請求（含轉址）的總時限為該伺服器的 `timeout` 秒。單次回應最多 4 MiB，錯誤訊息不再夾帶對端的回應本文。

### 5.1 GET /api/mcp/presets

取得內建範本：`mcp_time`（時間與時區，Python 內嵌腳本）與 `mcp_filesystem`（`npx -y @modelcontextprotocol/server-filesystem@2026.8.31 <backend/mcp_filesystem_sandbox 的絕對路徑>`）。檔案系統範本釘選套件版本，只開放專屬的沙箱目錄（與含索引中繼資料的 `DATA_DIR` 完全分開），呼叫本端點時自動建立該目錄。不提供網頁擷取類範本：`stdio` 子行程的出站連線不受 `web_fetch` 的 SSRF、網域白名單與網址來源限制約束。

**回應**：`{"status": "success", "presets": [...]}`

### 5.2 GET /api/mcp/servers

**查詢參數**：`is_enabled`（選填）。**回應**：`{"status": "success", "total": 2, "servers": [伺服器物件, ...]}`，依 ID 由新到舊。

### 5.3 POST /api/mcp/servers

新增伺服器，建立後立即連線並探索工具。

| 欄位 | 型態 | 必填 | 預設 |
|---|---|---|---|
| `name` | string | 是 | — |
| `display_name` | string | 是 | — |
| `description` | string | 否 | `null` |
| `transport_type` | string | 否 | `stdio` |
| `command` / `args` / `env_vars` | string / array / object | `stdio` 時 `command` 必填 | `null` |
| `url` / `headers` | string / object | HTTP 時 `url` 必填 | `null` |
| `is_enabled` | boolean | 否 | `true` |
| `requires_approval` | boolean | 否 | `true` |
| `timeout` | integer | 否 | `30` |

**回應**：`{"status": "success", "message": "MCP 伺服器建立成功", "server": {...}}`。探索失敗時伺服器仍會建立，但 `status` 為 `error`，`last_error` 只記錄錯誤代碼；SSRF 拒絕時另註明遭 SSRF 防護拒絕，完整原因同樣只寫入伺服器日誌。同名時回傳 `400` `已存在同名 MCP 伺服器: <名稱>`。

### 5.4 GET /api/mcp/servers/{server_id}

**回應**：`{"status": "success", "server": {...}}`；找不到時回傳 `404` `找不到該 MCP 伺服器`。

### 5.5 PUT /api/mcp/servers/{server_id}

只需帶入要變更的欄位（`name` 無法修改）。送出 `env_vars` 或 `headers` 時整個取代原值，值為 `••••••••` 的鍵沿用已儲存的值，沒有已儲存的值時回傳 `400`。更新後不會自動重新探索，請呼叫 5.7。**回應**：`{"status": "success", "message": "MCP 伺服器配置更新成功", "server": {...}}`。

### 5.6 DELETE /api/mcp/servers/{server_id}

**回應**：`{"status": "success", "message": "MCP 伺服器已成功刪除"}`

### 5.7 POST /api/mcp/servers/{server_id}/discover

重新連線並探索工具，結果寫入 `discovered_tools`。名稱不符合 `[A-Za-z0-9_.-]{1,128}` 的工具會被略過（只寫入伺服器日誌），不會出現在 `tools` 中，也不會提供給 Agent。

```json
{
  "status": "success",
  "message": "成功連線並探索到 1 項 MCP 工具",
  "tools_count": 1,
  "tools": [{"name": "get_current_time", "description": "查詢指定時區或城市的當前精確時間", "inputSchema": {"type": "object", "properties": {"timezone": {"type": "string"}}}}],
  "init_info": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "mcp-time-server", "version": "1.0"}},
  "server": {...}
}
```

失敗時回傳 `400`，`detail` 只含錯誤代碼（SSRF 拒絕時另註明遭 SSRF 防護拒絕）；伺服器的 `status` 同時改為 `error`。

### 5.8 PATCH /api/mcp/servers/{server_id}/toggle

**回應**：`{"status": "success", "is_enabled": false, "message": "MCP 伺服器已停用"}`

### 5.9 POST /api/mcp/servers/{server_id}/tools/{tool_name}/test

實際呼叫一次工具（`tools/call`）。`tool_name` 是 MCP 伺服器上的原始工具名稱。

**請求主體**：`{"arguments": {"timezone": "Asia/Taipei"}}`

```json
{
  "status": "success",
  "server_name": "mcp_time",
  "tool_name": "get_current_time",
  "result": {
    "is_success": true,
    "duration_seconds": 0.35,
    "content": [{"type": "text", "text": "當前時間: 2026-09-25 10:00:00 CST"}],
    "raw_result": {"content": [...], "isError": false}
  }
}
```

呼叫失敗時 `result` 為 `{"is_success": false, "duration_seconds": ..., "error": "伺服器內部錯誤，請聯繫系統管理員並提供錯誤代碼（錯誤代碼：…）", "error_id": "…"}`；完整原因（例如子行程的 stderr、JSON-RPC 錯誤或 SSRF 拒絕原因）只寫入伺服器日誌。Agent 呼叫 MCP 工具失敗時收到相同的結果。

---

## 6. 模型清單 `/api/tags`

相容 Ollama `tags` 格式的模型清單，不需要登入。原本的 `GET /api/external-tags` 已移除。

### 6.1 GET /api/tags

設定了任何模型來源（`AVAILABLE_MODELS` 或雲端金鑰）時，回傳 `{"tags": [...], "default": "..."}`，預設模型規則與 `GET /api/chat/models` 相同。都沒有設定時，向 `EXTERNAL_TAGS_URL`（或 `{LLM_API_BASE}/api/tags`）查詢遠端清單；查詢失敗時回傳空清單。遠端查詢在執行緒中進行，結果（含失敗）快取 30 秒，同一時間只有一個查詢在進行，匿名請求不會每次都觸發對外連線。

```json
{"tags": ["gpt-6-sol", "gpt-6-luna"], "default": "gpt-6-sol"}
```

---

## 7. 管理後台 `/api/admin`

> 本模組所有端點都需要**管理員**權限。

### 7.1 使用者管理

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/admin/users` | 所有使用者，每筆為 `UserProfile`（`id`、`username`、`email`、`role`、`is_active`、`is_admin`、`created_at`、`last_login`），不含 `hashed_password` |
| PUT | `/api/admin/users/{user_id}` | 更新 `username`、`email`、`is_active`、`is_admin`（只需帶入要變更的欄位）；名稱或電子郵件重複時回傳 `400`（`使用者名稱已存在`、`電子郵件已存在`） |
| DELETE | `/api/admin/users/{user_id}` | 刪除使用者與其所有對話 |

`PUT` 回傳 `{"message": "使用者更新成功", "user": {...}}`，`user` 是更新後的 `UserProfile`；`DELETE` 回傳 `{"message": "使用者刪除成功"}`。兩者找不到使用者時回傳 `404` `使用者不存在`，成功時都會清除統計快取。停用、刪除帳號或取消管理員身分在下一個請求立即生效：停用或刪除的帳號已簽發的權杖隨即失效，也無法再登入；取消管理員身分後，管理端點回傳 `403`。

變更與刪除帳號會寫入安全日誌並記錄操作的管理員：`PUT` 有實際變更時寫入 `ADMIN_USER_UPDATED`（目標帳號 id，以及 `username`、`email`、`is_active`、`is_admin` 變更前後的值），`DELETE` 寫入 `ADMIN_USER_DELETED`（目標帳號 id、使用者名稱與是否為管理員）。

### 7.2 統計

`GET /api/admin/statistics`，結果快取 180 秒：

```json
{
  "users": {"total": 12, "active": 11, "admins": 2},
  "conversations": {"total": 340},
  "messages": {"total": 2870, "recent_7_days": 412},
  "documents": {"total": 58, "processed": 57},
  "daily_stats": [{"date": "2026-09-25", "messages": 63}]
}
```

`daily_stats` 列出最近 7 天（從今天往前，以 UTC 日期計）的訊息數。

### 7.3 對話與文件

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/admin/conversations` | 全系統最近更新的 50 段對話 |
| GET | `/api/admin/conversations/{conversation_id}/messages` | 任一對話的全部訊息（依時間先後）；直接序列化資料表，含原始 `context_used` |
| DELETE | `/api/admin/conversations/{conversation_id}` | 刪除任一對話與其訊息 |
| GET | `/api/admin/documents` | 全部文件（新到舊，含完整 `content`） |
| DELETE | `/api/admin/documents/{document_id}` | 移除文件的片段與索引並刪除資料庫紀錄（不刪除上傳原檔；需要一併刪除原檔時請用 `DELETE /api/documents/{document_id}`） |

### 7.4 檢索與索引維運

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/admin/rag-config` | 目前的檢索參數 |
| GET | `/api/admin/vector-store/info` | 索引基本資訊 |
| GET | `/api/admin/vector-store/statistics` | 索引統計 |
| POST | `/api/admin/vector-store/reindex` | 以現有片段重新計算全部向量並重建 BM25，不重新切塊 |
| DELETE | `/api/admin/vector-store/clear` | 清空 `rag_chunks`、FAISS 與 BM25；文件紀錄保留，需要時再呼叫 `POST /api/documents/rebuild-index` 重建 |

`GET /api/admin/rag-config`：

```json
{
  "chunk_size": 300,
  "chunk_overlap": 100,
  "top_k": 30,
  "similarity_threshold": 0.3,
  "rrf_k": 60,
  "rerank_top_k": 20,
  "final_k": 8,
  "rerank_weight": 0.85,
  "rerank_relevance_threshold": 0.2,
  "batch_size": 32,
  "embedding_dimension": 512,
  "device": "cpu",
  "use_faiss_gpu": false
}
```

`GET /api/admin/vector-store/info`：

```json
{
  "total_vectors": 214,
  "total_documents": 214,
  "embedding_dimension": 512,
  "index_type": "FAISS IndexIDMap2(IndexFlatIP) + Whoosh BM25",
  "vector_index_exists": true,
  "bm25_index_exists": true,
  "last_reindex": "2026-09-25T10:00:00.000000"
}
```

`total_documents` 是片段數。`GET /api/admin/vector-store/statistics` 另外回傳 `bm25_status`、`similarity_threshold`、`chunk_size`、`chunk_overlap`。

`POST /api/admin/vector-store/reindex` 回傳 `{"message": "索引重建已觸發", "ok": true, "info": {...}}`；`DELETE /api/admin/vector-store/clear` 回傳 `{"message": "向量庫已清空"}`。

---

## 8. 健康檢查

| 方法 | 路徑 | 回應 |
|---|---|---|
| GET | `/` | `{"message": "ChatBot API is running"}` |
| GET | `/health` | `{"status": "healthy"}` |

互動式文件 `/docs`、`/redoc` 與 OpenAPI 規格 `/openapi.json` 只在 `ENABLE_API_DOCS=true` 時提供（不需要登入），設為 `false` 時這三個路徑回傳 `404`。

---

## 9. 錯誤處理

### 回應格式

錯誤訊息放在 `detail` 欄位：

```json
{"detail": "找不到該自訂 API 工具"}
```

欄位驗證失敗（`422`）時，`detail` 是 FastAPI 的錯誤陣列（前端送出聊天訊息時會把每一項的 `msg` 取出顯示，例如附件過大）：

```json
{"detail": [{"type": "missing", "loc": ["body", "content"], "msg": "Field required", "input": {}}]}
```

### 錯誤代碼機制

未預期的伺服器例外**不會**回傳例外訊息或堆疊，只回傳一組 12 碼的隨機錯誤代碼；完整例外寫入伺服器日誌，可依代碼查詢（CWE-209 / CWE-497）：

```json
{
  "detail": "伺服器內部錯誤，請聯繫系統管理員並提供錯誤代碼（錯誤代碼：9f2c71a4b8de）",
  "error_id": "9f2c71a4b8de"
}
```

只描述使用者輸入本身的驗證錯誤（例如 OpenAPI 規格格式不合法）則直接回傳可據以修正的訊息。SSRF 防護的拒絕原因可能含伺服器端解析出的內網 IP 或轉址目標，因此 `parse-spec`、自訂 API 工具與 `web_fetch` 遭拒時只說明「SSRF 防護拒絕連線」並附錯誤代碼，完整原因只寫入伺服器日誌。

### 常見狀態碼

| 狀態碼 | 說明 |
|---|---|
| `400` | 請求內容錯誤：名稱重複、規格解析失敗（含 YAML 別名）、網址未通過 SSRF 驗證、密碼規則不符、不支援的模型，或更新工具與 MCP 伺服器時送回 `••••••••` 但沒有已儲存的值 |
| `401` | 缺少或無效的存取權杖（`Not authenticated`、`認證權杖無效：驗證失敗`、`權杖已被撤銷`；帳號已刪除或停用，或權杖簽發後變更過密碼時也是 `認證權杖無效：驗證失敗`）、登入失敗 |
| `403` | 權限不足（`需要管理員權限`），或 `ALLOW_REGISTRATION=false` 時的註冊請求（`目前不開放註冊，請聯繫管理員建立帳號`） |
| `404` | 資源不存在（對話、文件、工具、MCP 伺服器、使用者、待核准的工具呼叫），或 `ENABLE_API_DOCS=false` 時的 `/docs`、`/redoc`、`/openapi.json` |
| `413` | 請求本文超過上限，或使用者的附件儲存量已達上限 |
| `422` | 欄位驗證失敗（含長度、數量與大小上限） |
| `429` | 超過速率限制（回應附 `Retry-After` 標頭）、登入識別或來源 IP 因登入失敗次數過多而暫停登入（`登入失敗次數過多，請稍後再試`，`Retry-After` 為剩餘秒數；暫停期間即使密碼正確也一樣），或同一位使用者同時進行的回答串流超過 2 個 |
| `500` | 未預期例外，只回傳錯誤代碼 |

自訂 API 工具的執行結果（[4.9](#49-post-apiapi-toolstool_idtest) 的測試端點與 Agent 的工具結果）另以 `status_code` 欄位回報：請求送出後為上游回傳的狀態碼；後端自行中止時附 `error`，狀態碼為 `400`（參數無效）、`403`（SSRF 防護拒絕）、`500`（未預期例外）、`502`（上游回應超過 1 MiB）或 `504`（超過工具的總時限）。這些不是 API 本身的 HTTP 狀態碼，測試端點仍回傳 `200`。

### 安全回應標頭

所有回應都會加上 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`X-XSS-Protection: 1; mode=block`、`Referrer-Policy: strict-origin-when-cross-origin` 與 `Permissions-Policy: geolocation=(), microphone=(), camera=()`，並移除 `Server` 標頭。

---

## 10. 已知限制

以下是目前的現況，整合時請留意：

- `GET /api/chat/models` 與 `GET /api/tags` 不需要登入（`GET /api/chat/tools` 已改為需要登入）。部署在公開網路時，請在反向代理層限制存取。
- `GET /api/documents/` 與 `GET /api/admin/documents` 回傳每份文件的完整文字 `content`。
- 存取權杖回應的 `expires_in` 固定為 `1800`，不隨 `ACCESS_TOKEN_EXPIRE_MINUTES` 變動。
- 權杖撤銷名單、速率限制計數、登入失敗節流的計數與暫停狀態、每位使用者的同時串流數與待核准的工具呼叫都存在單一後端行程的記憶體中；多行程或多台部署時彼此不共享，後端重啟後清空（暫停中的登入隨即解除）。速率限制追蹤的來源 IP 最多 10,000 個，最久未活動的先淘汰；登入節流追蹤的登入識別與來源 IP 也各最多 10,000 個，最久沒有新失敗的先淘汰。
- 速率限制與登入節流都依來源 IP 計算：未設定 `FORWARDED_ALLOW_IPS` 時，經由 Vite 開發代理或反向代理連線的所有使用者共用同一個來源 IP，除了共用速率限制的額度，依位址的登入失敗次數也一起累計，達到門檻時經由該代理的所有登入都會暫停。
- 附件儲存量沒有自動清除機制：使用者達到 200 MiB 上限後，需刪除含附件的對話才能再送出附件。
