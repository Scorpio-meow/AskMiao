# AskMiao API 參考手冊

[繁體中文](api.md) | [English](api_en.md)

> 本文件說明 AskMiao 後端提供之 RESTful、SSE 串流與 WebSocket 端點。系統同時提供 Swagger UI 動態文件，伺服器啟動後可造訪 `http://localhost:8001/docs` 進行互動式測試。

---

## 0. 通用約定 (Conventions)

| 項目 | 說明 |
|---|---|
| 基礎位址 | `http://localhost:8001`（由 `HOST` / `PORT` 環境變數決定） |
| 認證方式 | 於標頭帶入 `Authorization: Bearer <access_token>`；Refresh Token 由 HttpOnly Cookie 自動攜帶 |
| 內容型態 | 除檔案上傳（`multipart/form-data`）與對話串流（`text/event-stream`）外，皆為 `application/json` |
| 權限層級 | 標示「管理員」之端點需 `is_admin = true` 的帳號 |
| 時間格式 | ISO 8601（UTC） |

### 路由前綴總覽

| 前綴 | 模組 | 說明 |
|---|---|---|
| `/api/auth` | 身份認證 | 註冊、登入、刷新、個人資料與登出 |
| `/api/chat` | 對話與自主研究 | SSE 串流對話、模型與工具清單、對話歷史 |
| `/api/documents` | 知識庫文件 | 上傳、摘要、刪除與索引重建（管理員） |
| `/api/api-tools` | 自訂 API 工具 | OpenAPI 解析匯入與工具 CRUD、測試 |
| `/api/mcp` | MCP 伺服器 | MCP 伺服器管理、工具探索與調用測試 |
| `/api/admin` | 管理後台 | 使用者、統計、對話與向量庫維運（管理員） |
| `/api/tags`、`/api/external-tags` | 模型清單 | 相容 Ollama `tags` 格式之模型清單 |
| `/health`、`/` | 健康檢查 | 無需認證之存活探測 |

---

## 1. 身份認證模組 (`/api/auth`)

### 1.1 POST /api/auth/register

用戶註冊。成功後同時回傳 Access Token 並將 Refresh Token 寫入 HttpOnly Cookie。

**請求參數 (Request Body):**

| 欄位名稱 | 型態 | 必填 | 說明 | 格式與限制 |
|---|---|---|---|---|
| `username` | string | 是 | 用戶名稱 | 3–50 字元，僅允許英數字、底線與連字號 |
| `email` | string | 是 | 電子郵件 | 標準 Email 格式 |
| `password` | string | 是 | 密碼 | 至少 8 字元 |

**回應結果:**

- **201 Created**

```json
{
  "user": {
    "id": 1,
    "username": "miao_user",
    "email": "user@example.com",
    "role": "user",
    "is_active": true,
    "is_admin": false,
    "created_at": "2026-09-19T00:00:00",
    "last_login": null
  },
  "tokens": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 1800
  },
  "message": "註冊成功"
}
```

- **400 Bad Request**：用戶名稱或 Email 已被使用。

---

### 1.2 POST /api/auth/login

用戶登入。

**請求參數 (Request Body):**

| 欄位名稱 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `username` | string | 是 | 用戶名稱或電子郵件 |
| `password` | string | 是 | 用戶密碼 |

**回應結果:**

- **200 OK**：回應結構同註冊端點（`user` + `tokens` + `message`）。
- **401 Unauthorized**：帳號或密碼錯誤。

---

### 1.3 POST /api/auth/refresh

無感刷新 Access Token，系統自動從 HttpOnly Cookie 讀取 `refresh_token` 驗證，無需帶入 Authorization 標頭。

**回應結果:**

- **200 OK**

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

- **401 Unauthorized**：Refresh Token 無效、已撤銷或已過期。

---

### 1.4 GET /api/auth/me

取得當前登入用戶之個人資料。

**回應結果:**

- **200 OK**

```json
{
  "id": 1,
  "username": "miao_user",
  "email": "user@example.com",
  "role": "user",
  "is_active": true,
  "is_admin": false,
  "created_at": "2026-09-19T00:00:00",
  "last_login": "2026-09-19T08:30:00"
}
```

---

### 1.5 PUT /api/auth/me

更新個人資料（電子郵件或密碼）。變更密碼時必須同時提供 `current_password` 與 `new_password`。

**請求參數 (Request Body):**

| 欄位名稱 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `email` | string | 否 | 新電子郵件 |
| `current_password` | string | 否 | 現行密碼（變更密碼時必填） |
| `new_password` | string | 否 | 新密碼（至少 8 字元） |

**回應結果:** **200 OK**，回傳更新後之 `UserProfile`。

---

### 1.6 POST /api/auth/change-password

變更密碼專用端點。

**請求參數 (Request Body):**

| 欄位名稱 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `current_password` | string | 是 | 現行密碼 |
| `new_password` | string | 是 | 新密碼（至少 8 字元） |
| `confirm_password` | string | 是 | 再次輸入新密碼，須與 `new_password` 一致 |

**回應結果:** **200 OK** `{"message": "密碼修改成功", "success": true}`

---

### 1.7 POST /api/auth/logout

登出。系統會將 Access Token 與 Refresh Token 的 JTI 寫入撤銷名單，並清除 Refresh Token Cookie。

**回應結果:** **200 OK** `{"message": "登出成功", "success": true}`

---

### 1.8 POST /api/auth/validate-token

驗證當前 Access Token 是否仍然有效。

**回應結果:** **200 OK** `{"message": "令牌有效", "success": true}`

---

## 2. 對話與 Agentic RAG 自主研究模組 (`/api/chat`)

### 2.1 POST /api/chat/send

發送對話訊息並啟動 ReAct 自主研究 Agent。**本端點以 Server-Sent Events (SSE) 串流回應**，`Content-Type` 為 `text/event-stream`。

**請求參數 (Request Body):**

| 欄位名稱 | 型態 | 必填 | 說明 | 預設值 |
|---|---|---|---|---|
| `content` | string | 是 | 用戶提問或對話內容 | - |
| `conversation_id` | integer | 否 | 對話 ID（新對話留空，系統自動建立） | `null` |
| `model_name` | string | 否 | 指定使用之 LLM 模型名稱 | 系統預設模型 |
| `reasoning_effort` | string | 否 | 推理程度（`none`、`low`、`medium`、`high`、`xhigh`） | `medium` |
| `attachments` | array | 否 | 附件清單（圖片走視覺模型，文字檔抽取內容併入上下文） | `[]` |

`attachments[]` 欄位：`filename`（string）、`file_type`（string）、`file_size`（integer，選填）、`data_url`（string，Base64 Data URL，選填）、`content`（string，純文字內容，選填）。

**SSE 事件序列:**

| 事件名稱 | 觸發時機 | `data` 內容 |
|---|---|---|
| `start` | 串流開始 | `{"conversation_id": 42, "user_message_id": 107}` |
| `step_start` | 每一輪工具調用開始 | 工具名稱與輸入參數 |
| `step_end` | 每一輪工具調用結束 | 步驟結果摘要與耗時，累積為 `research_trace` |
| `token` | 模型輸出（用到工具後的答案會一次整段送出） | `{"content": "片段文字"}` |
| `sources` | 答案完成後，列出答案以 `[n]` 實際引用的來源 | `{"sources": [...], "sources_detail": [...]}` |
| `done` | 串流結束並完成訊息落庫 | 完整答案、來源與研究歷程 |
| `error` | 串流過程發生例外 | `{"detail": "...（錯誤代碼：xxxxxxxx）", "error_id": "xxxxxxxx"}` |

**串流範例:**

```text
event: start
data: {"conversation_id": 42, "user_message_id": 107}

event: step_start
data: {"step": 1, "tool": "search_knowledge_base", "arguments": {"query": "特休假申請流程"}}

event: step_end
data: {"step": 1, "tool": "search_knowledge_base", "duration_seconds": 0.83, "status": "success"}

event: token
data: {"content": "依照公司規章，特休假需於系統填寫假單並經主管核准 [1]。"}

event: sources
data: {"sources": ["員工規範2026.pdf"], "sources_detail": [{"citation": 1, "source": "員工規範2026.pdf", "chunk": 3, "score": 0.92, "snippet": "特休假申請需於系統填寫假單……"}]}

event: done
data: {"message_id": 108, "conversation_id": 42, "answer": "依照公司規章，...", "sources": ["員工規範2026.pdf"], "sources_detail": [...], "research_trace": [...]}
```

> `sources_detail` 只列答案實際引用的條目，依第一次引用的順序排列；`citation` 對應答案中的 `[n]`，網頁來源另含 `url`。答案沒有任何引用時兩者皆為空陣列。完成後系統會將機器人回覆與 `sources`、`sources_detail`、`research_trace` 一併寫入訊息紀錄的 `context_used` 欄位。

---

### 2.2 GET /api/chat/models

取得系統當前可用之語言模型清單與預設模型。

**回應結果:** **200 OK**

```json
{
  "models": ["gpt-4o", "gpt-4o-mini"],
  "default": "gpt-4o"
}
```

---

### 2.3 GET /api/chat/tools

取得 Agent 當前已註冊並啟用之工具定義（含內建工具、啟用中的自訂 API 工具與 MCP 工具），格式為 OpenAI Function Calling 之 `tools` 結構。

**回應結果:** **200 OK**

```json
{
  "status": "success",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_knowledge_base",
        "description": "搜尋內部知識庫...",
        "parameters": { "type": "object", "properties": { "query": { "type": "string" } } }
      }
    }
  ]
}
```

> 若動態載入過程發生例外，`status` 會回傳 `partial`，並附帶 `error` 與 `error_id`，`tools` 則退回內建工具集。

---

### 2.4 GET /api/chat/conversations

查詢當前用戶之所有對話（含訊息內容），回傳陣列。

**回應結果:** **200 OK**

```json
[
  {
    "id": 42,
    "title": "特休假申請流程詢問",
    "created_at": "2026-09-19T01:00:00",
    "updated_at": "2026-09-19T01:30:00",
    "messages": []
  }
]
```

---

### 2.5 GET /api/chat/conversations/{conversation_id}

取得單一對話完整內容（含訊息陣列）。查無資料時回傳 **404 Not Found**。

### 2.6 GET /api/chat/conversations/{conversation_id}/messages

僅取得指定對話之訊息清單。每則訊息包含 `id`、`content`、`is_user`、`created_at`、`model_name`，機器人訊息另含 `sources`、`sources_detail` 與 `research_trace`。

**查詢參數:** `limit`（integer，預設 `100`）、`offset`（integer，預設 `0`）。

### 2.7 POST /api/chat/conversations

建立新對話，無需帶入請求主體，標題採用 `DEFAULT_CONVERSATION_TITLE`（預設「新對話」）。

**回應結果:** **200 OK**，回傳新建立之對話物件。

### 2.8 DELETE /api/chat/conversations/{conversation_id}

刪除指定對話與其所有訊息。

**回應結果:** **200 OK** `{"message": "對話已刪除"}`

---

### 2.9 WebSocket /api/chat/ws/{user_id}

雙向即時通道，供伺服器主動推播訊息至指定用戶連線。

**連線位址:** `ws://localhost:8001/api/chat/ws/1`

> 一般對話請使用 2.1 的 SSE 端點；此 WebSocket 通道用於連線保持與伺服器端推播。

---

## 3. 知識庫與文件管理模組 (`/api/documents`)

> 本模組所有端點均需**管理員**權限。

### 3.1 POST /api/documents/upload

上傳文件至知識庫。系統會自動解析內容、生成 AI 摘要、切塊並建立 FAISS 向量索引與 Whoosh BM25 文字索引。

**請求標頭:**

```http
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

**請求參數:**

- `file`：檔案欄位（可重複帶入多筆，單次最多 10 個檔案）。
- 支援副檔名：`.txt`、`.md`、`.markdown`、`.pdf`、`.docx`、`.doc`、`.pptx`、`.xlsx`、`.xls`、`.csv`、`.json`、`.yaml`、`.yml`、`.xml`、`.html`、`.htm`、`.log`、`.py`、`.js`、`.ts`、`.tsx`、`.jsx`、`.java`、`.cpp`、`.c`、`.sql`、`.sh`、`.ini`、`.env`、`.jpg`、`.png`、`.gif`。
- 單檔大小上限由 `MAX_FILE_SIZE_MB` 控制（範本預設 10 MB）。

**回應結果:** **200 OK**，逐檔回報處理結果。

```json
{
  "results": [
    {
      "filename": "員工規範2026.pdf",
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
    }
  ]
}
```

---

### 3.2 GET /api/documents/

列出知識庫中所有文件。若文件尚無摘要，系統會在此次請求中補生成並寫回。

**回應結果:** **200 OK**

```json
[
  {
    "id": 101,
    "filename": "員工規範2026.pdf",
    "file_type": "application/pdf",
    "description": "本文件說明差勤與請假制度...",
    "uploaded_by": 1,
    "is_processed": true,
    "created_at": "2026-09-19T10:00:00"
  }
]
```

---

### 3.3 POST /api/documents/{document_id}/regenerate-summary

重新生成指定文件之 AI 大綱與摘要。

**回應結果:** **200 OK**，回傳 `document_id` 與新的 `description`。

### 3.4 PUT /api/documents/{document_id}/summary

手動修訂文件摘要。

**請求參數 (Request Body):** `{"description": "自訂摘要內容"}`

### 3.5 DELETE /api/documents/{document_id}

刪除指定文件、實體檔案與其對應索引資料。

### 3.6 POST /api/documents/rebuild-index

以資料庫現存文件為來源，重新建立 FAISS 與 BM25 全量索引。

---

## 4. 自訂 API 工具模組 (`/api/api-tools`)

將外部 HTTP API 註冊為 AI 可自主調用之工具。啟用中的工具會於組裝工具定義時自動載入 Agent 工具集。

### 4.1 POST /api/api-tools/parse-spec

解析 OpenAPI / Swagger 規格（支援 OAS 2.0、3.0、3.1），可傳入規格全文或規格網址。

**請求參數 (Request Body):**

| 欄位名稱 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `spec_content_or_url` | string | 是 | OpenAPI 規格內容（JSON / YAML）或可存取之規格 URL |
| `default_base_url` | string | 否 | 規格未宣告 `servers` 時使用之預設基底位址 |

> 傳入 URL 時會先經 SSRF 防護驗證；指向內網位址、雲端中繼資料端點或危險連接埠之網址將被拒絕。

**回應結果:** **200 OK** `{"status": "success", "data": { ...解析後之端點清單... }}`

- **400 Bad Request**：規格格式不合法或網址未通過驗證（訊息可直接顯示給使用者）。
- **500 Internal Server Error**：其他未預期例外，僅回傳錯誤代碼。

---

### 4.2 POST /api/api-tools/import

將解析後選定之端點批次匯入為自訂工具。同名工具將被覆寫更新。

**請求參數 (Request Body):**

| 欄位名稱 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `tools` | array | 是 | 待匯入端點清單 |
| `global_base_url` | string | 否 | 套用至所有端點之基底位址 |
| `global_headers` | object | 否 | 套用至所有端點之共用標頭 |
| `global_auth_type` | string | 否 | 共用認證方式（`none`、`bearer`、`api_key`、`basic`） |
| `global_auth_config` | object | 否 | 共用認證設定 |

`tools[]` 主要欄位：`name`、`display_name`、`description`、`method`、`path`、`full_url`、`base_url`、`headers`、`auth_type`、`auth_config`、`parameters_schema`、`request_body_schema`、`param_locations`、`spec_version`。

**回應結果:** **200 OK**

```json
{
  "status": "success",
  "message": "成功匯入 4 個新工具，更新 1 個既有工具。",
  "imported": 4,
  "updated": 1
}
```

---

### 4.3 GET /api/api-tools

取得自訂 API 工具清單。

**查詢參數:** `category`（string）、`is_enabled`（boolean）、`search`（string，模糊比對名稱、顯示名稱、描述與 URL）。

**回應結果:** **200 OK** `{"status": "success", "total": 5, "tools": [ ... ]}`

---

### 4.4 POST /api/api-tools

手動建立單一自訂 API 工具。

**請求參數 (Request Body):**

| 欄位名稱 | 型態 | 必填 | 說明 | 預設值 |
|---|---|---|---|---|
| `name` | string | 是 | 工具唯一識別名稱（供模型調用） | - |
| `display_name` | string | 是 | 顯示名稱 | - |
| `description` | string | 是 | 工具用途描述（影響模型調用判斷） | - |
| `url` | string | 是 | 完整請求位址 | - |
| `method` | string | 否 | HTTP 方法 | `GET` |
| `base_url` / `path` | string | 否 | 基底位址與路徑（可取代 `url` 組合） | `null` |
| `headers` | object | 否 | 自訂請求標頭 | `null` |
| `auth_type` | string | 否 | `none`、`bearer`、`api_key`、`basic` | `none` |
| `auth_config` | object | 否 | 認證設定（如 `token`、`key_name`、`key_in`、`username`） | `null` |
| `parameters_schema` | object | 否 | JSON Schema 形式之參數定義 | `null` |
| `request_body_schema` | object | 否 | 請求主體結構 | `null` |
| `param_locations` | object | 否 | 各參數位置（`path` / `query` / `header` / `body`） | `null` |
| `is_enabled` | boolean | 否 | 是否啟用 | `true` |
| `timeout` | integer | 否 | 呼叫逾時秒數 | `15` |

**回應結果:** **200 OK**，回傳建立後之工具物件。

---

### 4.5 GET /api/api-tools/{tool_id}

取得單一工具詳細設定。查無資料回傳 **404 Not Found**。

### 4.6 PUT /api/api-tools/{tool_id}

更新工具設定（僅需帶入欲變更欄位）。

### 4.7 PATCH /api/api-tools/{tool_id}/toggle

切換工具啟用狀態。

**回應結果:** **200 OK** `{"status": "success", "is_enabled": false, "message": "..."}`

### 4.8 DELETE /api/api-tools/{tool_id}

刪除指定工具。

### 4.9 POST /api/api-tools/{tool_id}/test

以指定參數實際發送一次請求，驗證工具連通性與回應格式。

**請求參數 (Request Body):** `{"arguments": {"petId": 3}}`

**回應結果:** **200 OK**

```json
{
  "status": "success",
  "tool_name": "get_pet_by_id",
  "result": {
    "success": true,
    "status_code": 200,
    "duration_seconds": 0.42,
    "url": "https://api.example.com/pets/3",
    "data": { "id": 3, "name": "Miao" }
  }
}
```

> 呼叫失敗時 `result.success` 為 `false`，並回傳 `error` 與 `error_id`，不揭露內部例外內容。

---

## 5. MCP 伺服器模組 (`/api/mcp`)

管理 Model Context Protocol 伺服器，支援 `stdio`（本機子行程）與 HTTP 兩種傳輸方式。

### 5.1 GET /api/mcp/presets

取得內建之常用 MCP 伺服器範本清單。

**回應結果:** **200 OK** `{"status": "success", "presets": [ ... ]}`

### 5.2 GET /api/mcp/servers

取得所有已配置之 MCP 伺服器。

**查詢參數:** `is_enabled`（boolean，選填）

**回應結果:** **200 OK** `{"status": "success", "total": 2, "servers": [ ... ]}`

伺服器物件欄位：`id`、`name`、`display_name`、`description`、`transport_type`、`command`、`args`、`env_vars`、`url`、`headers`、`is_enabled`、`status`（`connected` / `disconnected` / `error`）、`last_error`、`discovered_tools`、`timeout`、`created_at`、`updated_at`。

---

### 5.3 POST /api/mcp/servers

新增 MCP 伺服器。建立後系統會立即嘗試連線並探索工具清單；探索失敗時伺服器仍會建立，但 `status` 為 `error` 且 `last_error` 帶回錯誤代碼。

**請求參數 (Request Body):**

| 欄位名稱 | 型態 | 必填 | 說明 | 預設值 |
|---|---|---|---|---|
| `name` | string | 是 | 伺服器唯一識別名稱（自動轉小寫） | - |
| `display_name` | string | 是 | 顯示名稱 | - |
| `description` | string | 否 | 說明 | `null` |
| `transport_type` | string | 否 | `stdio` 或 HTTP 傳輸 | `stdio` |
| `command` | string | 否 | `stdio` 模式之執行指令 | `null` |
| `args` | array | 否 | 指令參數陣列 | `null` |
| `env_vars` | object | 否 | 子行程環境變數 | `null` |
| `url` | string | 否 | HTTP 傳輸之伺服器位址（經 SSRF 驗證） | `null` |
| `headers` | object | 否 | HTTP 傳輸之請求標頭 | `null` |
| `is_enabled` | boolean | 否 | 是否啟用 | `true` |
| `timeout` | integer | 否 | 連線與呼叫逾時秒數 | `30` |

- **400 Bad Request**：已存在同名伺服器。

---

### 5.4 GET /api/mcp/servers/{server_id}

取得單一 MCP 伺服器詳細設定與已探索工具快取。

### 5.5 PUT /api/mcp/servers/{server_id}

更新伺服器設定（僅需帶入欲變更欄位）。

### 5.6 DELETE /api/mcp/servers/{server_id}

刪除指定 MCP 伺服器設定。

### 5.7 POST /api/mcp/servers/{server_id}/discover

重新連線並探索伺服器工具清單（`initialize` + `tools/list`），結果會寫入 `discovered_tools` 快取。

**回應結果:** **200 OK**

```json
{
  "status": "success",
  "server_name": "filesystem",
  "total_tools": 6,
  "tools": [{ "name": "read_file", "description": "..." }],
  "server_info": { "protocolVersion": "2024-11-05" }
}
```

### 5.8 PATCH /api/mcp/servers/{server_id}/toggle

切換伺服器啟用狀態。停用後其工具將不再注入 Agent 工具集。

### 5.9 POST /api/mcp/servers/{server_id}/tools/{tool_name}/test

實際調用一次指定 MCP 工具（`tools/call`）以驗證連通性。

**請求參數 (Request Body):** `{"arguments": {"path": "/tmp/demo.txt"}}`

**回應結果:** **200 OK** `{"status": "success", "server_name": "filesystem", "tool_name": "read_file", "result": { ... }}`

> Agent 調用 MCP 工具時使用 `mcp_<伺服器名稱>_<工具名稱>` 之命名慣例。

---

## 6. 模型清單模組 (`/api/tags`、`/api/external-tags`)

相容 Ollama `tags` 格式之模型清單端點，供前端模型選單與外部整合使用。

### 6.1 GET /api/tags

**回應結果:** **200 OK** `{"tags": ["gpt-4o", "gpt-4o-mini"], "default": "gpt-4o"}`

若未設定任何雲端供應商金鑰，系統會嘗試自 `LLM_API_BASE` 取得遠端模型清單，最後才回退至內建備援清單。

### 6.2 GET /api/external-tags

自 `EXTERNAL_TAGS_URL` 或 `LLM_API_BASE` 取得外部模型清單。

- **400 Bad Request**：兩者皆未設定。

---

## 7. 管理後台模組 (`/api/admin`)

> 本模組所有端點均需**管理員**權限。

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/admin/users` | 取得所有使用者清單 |
| PUT | `/api/admin/users/{user_id}` | 更新使用者角色、啟用狀態或重設密碼 |
| DELETE | `/api/admin/users/{user_id}` | 刪除使用者 |
| GET | `/api/admin/statistics` | 取得系統統計數據（快取 180 秒） |
| GET | `/api/admin/conversations` | 取得全系統對話清單 |
| GET | `/api/admin/conversations/{conversation_id}/messages` | 取得指定對話之訊息 |
| DELETE | `/api/admin/conversations/{conversation_id}` | 刪除指定對話 |
| GET | `/api/admin/documents` | 取得全系統文件清單 |
| DELETE | `/api/admin/documents/{document_id}` | 刪除指定文件 |
| GET | `/api/admin/rag-config` | 取得當前 RAG 檢索參數配置 |
| GET | `/api/admin/vector-store/info` | 取得向量索引基本資訊 |
| GET | `/api/admin/vector-store/statistics` | 取得向量索引統計數據 |
| POST | `/api/admin/vector-store/reindex` | 觸發全量重建索引 |
| DELETE | `/api/admin/vector-store/clear` | 清空向量索引 |

**GET /api/admin/statistics 回應範例:**

```json
{
  "users": { "total": 12, "active": 11, "admins": 2 },
  "conversations": { "total": 340 },
  "messages": { "total": 2870, "recent_7_days": 412 },
  "documents": { "total": 58, "processed": 57 },
  "daily_stats": [{ "date": "2026-09-19", "messages": 63 }]
}
```

---

## 8. 全域錯誤回應規範 (Error Handling Schema)

系統採用 FastAPI 標準錯誤結構，錯誤訊息置於 `detail` 欄位：

```json
{
  "detail": "找不到該自訂 API 工具"
}
```

### 錯誤代碼機制

未預期之伺服器端例外**不會**回傳例外訊息或堆疊，僅回傳一組隨機錯誤代碼；完整例外內容記錄於伺服器日誌，可依代碼定位（CWE-209 / CWE-497）：

```json
{
  "detail": "伺服器內部錯誤，請聯繫系統管理員並提供錯誤代碼（錯誤代碼：9f2c71a4b8de）",
  "error_id": "9f2c71a4b8de"
}
```

輸入驗證類錯誤（如使用者提供之 OpenAPI 規格格式不合法）則直接回傳可據以修正之訊息，不套用錯誤代碼機制。

### 常見 HTTP 狀態碼

| HTTP 狀態碼 | 說明與可能原因 |
|---|---|
| **400 Bad Request** | 請求格式錯誤、名稱重複、規格解析失敗或網址未通過 SSRF 驗證 |
| **401 Unauthorized** | 缺少 Authorization 標頭，或 JWT 無效、過期、已撤銷 |
| **403 Forbidden** | 權限不足（非管理員存取管理端點） |
| **404 Not Found** | 請求資源（對話、文件、工具、MCP 伺服器）不存在 |
| **409 Conflict** | 上傳文件內容與既有文件重複 |
| **422 Unprocessable Entity** | Pydantic 欄位驗證失敗 |
| **429 Too Many Requests** | 超出 `RATE_LIMIT_PER_MINUTE` 速率限制 |
| **500 Internal Server Error** | 未預期例外，回應僅含錯誤代碼 |
