# AskMiao API 參考手冊

[繁體中文](api.md) | [English](api_en.md)

> 本文件說明 AskMiao 後端 **3.0.0** 的 REST、SSE 串流與 WebSocket 端點，內容依 `backend/app/api/` 的實際路由撰寫。後端啟動後也可以在 `http://localhost:8001/docs`（Swagger UI）與 `http://localhost:8001/redoc` 互動測試，OpenAPI 規格位於 `/openapi.json`。

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
| 速率限制 | 每個來源 IP 每 60 秒 `RATE_LIMIT_PER_MINUTE` 次（預設 60），超過回傳 `429` |

### 權限層級

| 層級 | 條件 | 未符合時 |
|---|---|---|
| 公開 | 不需要權杖 | — |
| 登入 | 有效且未撤銷的存取權杖 | `401` |
| 管理員 | 存取權杖中的 `is_admin` 為 `true` | `403`（`{"detail": "需要管理員權限"}`） |

> [!NOTE]
> `is_admin` 取自存取權杖。變更某位使用者的管理員身分後，要等對方重新登入或權杖更新才會生效。

### 端點總覽

| 方法 | 路徑 | 權限 | 說明 |
|---|---|---|---|
| POST | `/api/auth/register` | 公開 | 註冊並登入 |
| POST | `/api/auth/login` | 公開 | 登入 |
| POST | `/api/auth/refresh` | 公開（需 Cookie） | 以重新整理權杖換發權杖 |
| GET | `/api/auth/me` | 登入 | 取得個人資料 |
| PUT | `/api/auth/me` | 登入 | 更新電子郵件或密碼 |
| POST | `/api/auth/change-password` | 登入 | 變更密碼 |
| POST | `/api/auth/logout` | 登入 | 登出並撤銷權杖 |
| POST | `/api/auth/validate-token` | 登入 | 檢查存取權杖是否有效 |
| POST | `/api/chat/send` | 登入 | 送出訊息，以 SSE 串流回應 |
| GET | `/api/chat/models` | 公開 | 可用模型與預設模型 |
| GET | `/api/chat/tools` | 公開 | Agent 目前可用的工具定義 |
| GET | `/api/chat/conversations` | 登入 | 自己的對話清單 |
| POST | `/api/chat/conversations` | 登入 | 建立對話 |
| GET | `/api/chat/conversations/{conversation_id}` | 登入 | 單一對話與全部訊息 |
| GET | `/api/chat/conversations/{conversation_id}/messages` | 登入 | 分頁取得訊息 |
| DELETE | `/api/chat/conversations/{conversation_id}` | 登入 | 刪除對話 |
| WebSocket | `/api/chat/ws/{user_id}` | 公開 | 示範用回聲通道 |
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
| GET | `/api/external-tags` | 公開 | 轉送遠端模型清單 |
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

---

## 1. 身分認證 `/api/auth`

### 權杖模型

| 權杖 | 存放位置 | 有效期 | 用途 |
|---|---|---|---|
| 存取權杖（access token） | 回應 JSON 的 `tokens.access_token`，由前端放在 `Authorization` 標頭 | `ACCESS_TOKEN_EXPIRE_MINUTES`（預設 30 分鐘） | 呼叫所有需要登入的端點；內含 `sub`、`username`、`email`、`role`、`is_admin` |
| 重新整理權杖（refresh token） | HttpOnly Cookie `refresh_token`，路徑 `/api/auth` | `REFRESH_TOKEN_EXPIRE_DAYS`（預設 7 天） | 只用於 `POST /api/auth/refresh`；每次換發都會重設 Cookie |

權杖以 RSA-2048 私鑰簽署 RS256（RSA 金鑰無法載入的開發環境改用 `JWT_SECRET_KEY` 簽署 HS256）。回應 JSON 中的 `tokens.refresh_token` 一律是空字串，真正的重新整理權杖只存在 Cookie 中；`expires_in` 目前固定回傳 `1800`，實際到期時間以權杖內的 `exp` 為準。

### 1.1 POST /api/auth/register

註冊新帳號，成功後直接登入：回傳存取權杖，並把重新整理權杖寫入 Cookie。新帳號一律是一般使用者。

**請求主體**

| 欄位 | 型態 | 必填 | 規則 |
|---|---|---|---|
| `username` | string | 是 | 3–50 字元，只能包含文字（含中文）、數字、底線與連字號 |
| `email` | string | 是 | 合法的電子郵件格式 |
| `password` | string | 是 | 至少 8 字元，且包含大寫字母、小寫字母與數字 |

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
| `422` | 欄位格式錯誤（長度、字元、電子郵件格式） |

### 1.2 POST /api/auth/login

以使用者名稱**或**電子郵件登入。

**請求主體**：`{"username": "miao_user", "password": "Secret123"}`

**回應**：`200 OK`，結構同註冊（`message` 為 `登入成功`），並更新 `last_login`。以舊版 bcrypt 雜湊儲存的密碼會在登入成功時自動改存為 Argon2。

| 狀態碼 | 情況 |
|---|---|
| `401` | `使用者名稱或密碼錯誤`（帳號停用時也回傳相同訊息） |

### 1.3 POST /api/auth/refresh

從 Cookie 讀取重新整理權杖，換發新的存取權杖並重設 Cookie，不需要 `Authorization` 標頭。

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
| `401` | `找不到重新整理權杖`、`重新整理權杖無效`、`重新整理權杖類型無效`、`權杖已被撤銷` 或已過期 |

### 1.4 GET /api/auth/me

取得目前登入者的個人資料（`UserProfile`：`id`、`username`、`email`、`role`、`is_active`、`is_admin`、`created_at`、`last_login`）。

### 1.5 PUT /api/auth/me

更新電子郵件或密碼，只需帶入要變更的欄位。

| 欄位 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `email` | string | 否 | 新的電子郵件，不可與他人重複 |
| `current_password` | string | 變更密碼時必填 | 目前的密碼 |
| `new_password` | string | 否 | 新密碼，規則同註冊 |

**回應**：`200 OK`，回傳更新後的 `UserProfile`。錯誤時回傳 `400`：`該電子郵件已被使用`、`請提供目前的密碼`、`目前的密碼錯誤` 或密碼強度訊息。

### 1.6 POST /api/auth/change-password

| 欄位 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `current_password` | string | 是 | 目前的密碼 |
| `new_password` | string | 是 | 新密碼，規則同註冊 |
| `confirm_password` | string | 是 | 須與 `new_password` 相同，否則回傳 `422` |

**回應**：`200 OK` `{"message": "密碼修改成功", "success": true}`；目前密碼錯誤時回傳 `400` `目前的密碼錯誤`。

### 1.7 POST /api/auth/logout

把 `Authorization` 標頭中的存取權杖與 Cookie 中的重新整理權杖寫入撤銷名單（保留到各自到期為止），並刪除 Cookie。

**回應**：`200 OK` `{"message": "登出成功", "success": true}`

> [!NOTE]
> 撤銷名單存在後端行程的記憶體中，後端重啟後會清空，尚未過期的舊權杖會重新有效。

### 1.8 POST /api/auth/validate-token

**回應**：`200 OK` `{"message": "權杖有效", "success": true}`；權杖無效時回傳 `401`。

---

## 2. 對話與自主研究 `/api/chat`

### 2.1 POST /api/chat/send

送出訊息並啟動 `ResearchAgent`。回應為 **Server-Sent Events** 串流（`Content-Type: text/event-stream`，附 `Cache-Control: no-cache` 與 `X-Accel-Buffering: no`）。

**請求主體**

| 欄位 | 型態 | 必填 | 預設 | 說明 |
|---|---|---|---|---|
| `content` | string | 是 | — | 使用者的問題 |
| `conversation_id` | integer | 否 | `null` | 對話 ID；留空、不存在或不屬於自己時會建立新對話 |
| `model_name` | string | 否 | 預設模型 | 要使用的模型，供應商依名稱自動路由 |
| `reasoning_effort` | string | 否 | `medium` | 推理程度，只傳給 OpenAI 與 Azure OpenAI，見下方說明 |
| `attachments` | array | 否 | `[]` | 附件，見下表 |

`attachments[]` 欄位：

| 欄位 | 型態 | 說明 |
|---|---|---|
| `filename` | string | 檔名 |
| `file_type` | string | MIME 類型；`image/*` 交給視覺模型，其他類型抽取文字 |
| `file_size` | integer | 選填，檔案大小 |
| `data_url` | string | 選填，Base64 Data URL；圖片必須提供 |
| `content` | string | 選填，已擷取好的純文字；未提供時由 `data_url` 解碼後擷取 |

**`reasoning_effort` 的處理**：前端提供 `none`、`low`、`medium`、`high`、`xhigh` 五檔；後端接受 `none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max`，其他值不會傳給模型。名稱含 `gpt-5` 的模型在帶工具呼叫時一律改送 `none`。

#### SSE 事件

每個事件的格式為 `event: <名稱>\ndata: <JSON>\n\n`，依序如下：

| 事件 | 時機 | `data` 欄位 |
|---|---|---|
| `start` | 使用者訊息已存入資料庫 | `conversation_id`、`user_message_id` |
| `step_start` | 每次工具呼叫開始 | `step`（從 1 起算）、`tool`、`arguments` |
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
- 助理訊息的 `sources`、`sources_detail` 與 `research_trace` 會以 JSON 存入訊息的 `context_used` 欄位；附件資訊則存於使用者訊息的 `context_used`。

### 2.2 GET /api/chat/models

取得可用模型與預設模型。清單產生方式與預設模型規則見 [設定參考：模型清單](configuration.md#模型清單)。

```json
{
  "models": ["gpt-6-sol", "gpt-6-luna"],
  "default": "gpt-6-sol"
}
```

### 2.3 GET /api/chat/tools

取得 Agent 目前可用的工具定義，格式為 OpenAI Function Calling 的 `tools` 結構，包含：

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

取得自己的對話清單，依最後更新時間由新到舊排列；每段對話附**最近 5 則**訊息（依時間先後）。

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
        "context_used": "{\"sources\": [...], \"sources_detail\": [...], \"research_trace\": [...]}",
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

訊息物件的 `sources`、`sources_detail`、`research_trace` 與 `attachments` 由 `context_used` 解析而來；`reasoning_effort` 目前不會儲存，一律為 `null`。

### 2.5 POST /api/chat/conversations

建立空白對話，不需要請求主體，標題為 `DEFAULT_CONVERSATION_TITLE`（預設「新對話」）。回傳對話物件（`messages` 為空陣列）。

### 2.6 GET /api/chat/conversations/{conversation_id}

取得單一對話與全部訊息（依時間先後）。對話不存在或不屬於自己時回傳 `404` `找不到該對話`。

### 2.7 GET /api/chat/conversations/{conversation_id}/messages

分頁取得訊息。

| 查詢參數 | 預設 | 說明 |
|---|---|---|
| `limit` | `100` | 取回的訊息數 |
| `offset` | `0` | 從最新一則往回略過的數量 |

回傳最新的 `limit` 則訊息（依時間先後排列），以 `offset` 往前翻頁。對話不存在或不屬於自己時回傳空陣列。

### 2.8 DELETE /api/chat/conversations/{conversation_id}

刪除自己的對話與其所有訊息。

**回應**：`200 OK` `{"message": "對話已刪除"}`；找不到時回傳 `404`。

### 2.9 WebSocket /api/chat/ws/{user_id}

示範用的回聲通道：收到 `{"content": "..."}` 後回傳 `{"type": "message", "content": "收到訊息: ...", "timestamp": "now"}`。此通道不驗證身分，前端也沒有使用；對話請使用 [2.1 的 SSE 端點](#21-post-apichatsend)。

---

## 3. 知識庫文件 `/api/documents`

> 本模組所有端點都需要**管理員**權限。

### 3.1 POST /api/documents/upload

上傳文件至知識庫。每個檔案依序經過：檔名與副檔名檢查 → 大小檢查 → 擷取文字（PDF 空白或亂碼頁以視覺模型 OCR）→ 重複內容檢查 → 生成 AI 摘要 → 存入 `documents` → 切塊並寫入 `rag_chunks`、FAISS 與 BM25。

**請求**：`multipart/form-data`，欄位名稱為 `file`，可重複帶入，單次最多 10 個檔案。

- 支援副檔名：`.txt`、`.md`、`.markdown`、`.pdf`、`.docx`、`.pptx`、`.xlsx`、`.csv`、`.json`、`.yaml`、`.yml`、`.xml`、`.html`、`.htm`、`.log`、`.py`、`.js`、`.ts`、`.tsx`、`.jsx`、`.java`、`.cpp`、`.c`、`.sql`、`.sh`、`.ini`、`.env`。
- 單檔上限為 `MAX_FILE_SIZE_MB`（範本 10 MB）。
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

刪除文件：移除該文件的片段、向量與 BM25 項目，刪除上傳原檔，最後刪除資料庫紀錄。

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

> 本模組所有端點（含查詢）都需要**管理員**權限：工具由所有使用者的 Agent 共用，回應也包含 API 金鑰等憑證。詳見 [ADR-0004](adr/0004-tool-admin-permissions-and-subprocess-isolation.md)。

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
| `headers` | object | 固定的請求標頭 |
| `auth_type` | string | `none`、`bearer`、`api_key`、`basic` |
| `auth_config` | object | 認證設定，見下表 |
| `parameters_schema` | object | 參數的 JSON Schema，直接作為模型看到的 `parameters` |
| `request_body_schema` | object | 請求主體結構 |
| `param_locations` | object | 每個參數的位置：`path`、`query`、`header`、`body` |
| `response_mapping` | string | 保留欄位，目前未使用 |
| `is_enabled` | boolean | 是否啟用 |
| `timeout` | integer | 逾時秒數，預設 15 |
| `spec_version` | string | 來源規格版本，手動建立為 `manual` |
| `created_at` / `updated_at` | string | 時間戳記 |

| `auth_type` | `auth_config` 欄位 |
|---|---|
| `bearer` | `token` |
| `api_key` | `key_name`（預設 `X-API-Key`）、`key_value`、`key_in`（`header` 或 `query`） |
| `basic` | `username`、`password` |

**參數組裝規則**：出現在網址 `{名稱}` 中或位置為 `path` 的參數會替換進網址；`header` 放進標頭；`query` 放進查詢字串；`body` 放進 JSON 主體。未指定位置的參數，`POST`、`PUT`、`PATCH` 放進主體，其他方法放進查詢字串。模型傳入 `request_body` 物件時，整個取代主體。

### 4.1 POST /api/api-tools/parse-spec

解析 OpenAPI / Swagger 規格（OAS 2.0、3.0、3.1），可傳入 JSON / YAML 全文或規格網址。

| 欄位 | 型態 | 必填 | 說明 |
|---|---|---|---|
| `spec_content_or_url` | string | 是 | 規格全文，或以 `http://`、`https://` 開頭的規格網址 |
| `default_base_url` | string | 否 | 覆寫規格中的伺服器位址 |

規格網址會先經 SSRF 驗證，下載上限 10 MB、逾時 15 秒、最多 5 次轉址。

**回應**：`200 OK`

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
    ],
    "raw_spec": {"openapi": "3.0.0", "...": "..."}
  }
}
```

工具名稱取自 `operationId`（轉為小寫並把非英數字元換成底線）；沒有 `operationId` 時由方法與路徑組成，例如 `get_pets_petid`。

| 狀態碼 | 情況 |
|---|---|
| `400` | 規格格式不合法、無法辨識版本、網址被 SSRF 防護拒絕或無法取得（訊息可直接顯示給使用者） |
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

只需帶入要變更的欄位（`name` 無法修改）。**回應**：`{"status": "success", "message": "自訂 API 工具更新成功", "tool": {...}}`。

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

- 回應為 JSON 時 `data` 是解析後的物件，否則是前 4000 字的文字。
- 第一個請求與每次轉址都會重新經過 SSRF 驗證；被拒絕時 `status_code` 為 `403`、`is_success` 為 `false`，`error` 說明拒絕原因。
- 其他失敗時 `status_code` 為 `500`，只回傳 `error`（含錯誤代碼）與 `error_id`。

---

## 5. MCP 伺服器 `/api/mcp`

管理 Model Context Protocol 伺服器，協定版本 `2024-11-05`，以 JSON-RPC 2.0 進行 `initialize`、`tools/list` 與 `tools/call`。交握時的 `clientInfo` 為 `AskMiao-MCP-Client` 與後端版本號。

> 本模組所有端點（含查詢）都需要**管理員**權限：`stdio` 模式會在主機上執行指定的指令，回應也包含環境變數與標頭等憑證。

### 伺服器物件

| 欄位 | 型態 | 說明 |
|---|---|---|
| `id` | integer | 伺服器 ID |
| `name` | string | 唯一名稱（建立時轉為小寫），用於工具名稱 `mcp_<name>_<tool>` |
| `display_name` / `description` | string | 顯示名稱與說明 |
| `transport_type` | string | `stdio`，或 `http` / `sse`（兩者都以 HTTP POST 傳送 JSON-RPC） |
| `command` / `args` | string / array | `stdio` 模式的執行指令與參數 |
| `env_vars` | object | `stdio` 子行程的額外環境變數 |
| `url` / `headers` | string / object | HTTP 模式的伺服器位址與請求標頭 |
| `is_enabled` | boolean | 是否啟用；停用後其工具不會提供給 Agent |
| `status` | string | `connected`、`disconnected` 或 `error` |
| `last_error` | string | 最近一次探索失敗的原因 |
| `discovered_tools` | array | 最近一次探索到的工具快取（`name`、`description`、`inputSchema`） |
| `timeout` | integer | 連線與呼叫逾時秒數，預設 30 |
| `created_at` / `updated_at` | string | 時間戳記 |

**`stdio` 子行程的環境變數**只繼承系統必要變數，再加上 `env_vars`：Windows 為 `APPDATA`、`HOMEDRIVE`、`HOMEPATH`、`LOCALAPPDATA`、`PATH`、`PATHEXT`、`PROCESSOR_ARCHITECTURE`、`SYSTEMDRIVE`、`SYSTEMROOT`、`TEMP`、`USERNAME`、`USERPROFILE`；其他平台為 `HOME`、`LOGNAME`、`PATH`、`SHELL`、`TERM`、`USER`。後端 `.env` 中的設定不會傳給子行程。

**HTTP 模式**的每個請求與轉址都經 SSRF 驗證，指向本機或內網位址的伺服器會被拒絕；本機的 MCP 伺服器請改用 `stdio`。

### 5.1 GET /api/mcp/presets

取得內建範本：`mcp_time`（時間與時區，Python 內嵌腳本）、`mcp_filesystem`（`npx -y @modelcontextprotocol/server-filesystem ./data`）與 `mcp_fetch`（`uvx mcp-server-fetch`）。

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
| `timeout` | integer | 否 | `30` |

**回應**：`{"status": "success", "message": "MCP 伺服器建立成功", "server": {...}}`。探索失敗時伺服器仍會建立，但 `status` 為 `error`，`last_error` 只記錄錯誤代碼；SSRF 拒絕時另註明遭 SSRF 防護拒絕，完整原因同樣只寫入伺服器日誌。同名時回傳 `400` `已存在同名 MCP 伺服器: <名稱>`。

### 5.4 GET /api/mcp/servers/{server_id}

**回應**：`{"status": "success", "server": {...}}`；找不到時回傳 `404` `找不到該 MCP 伺服器`。

### 5.5 PUT /api/mcp/servers/{server_id}

只需帶入要變更的欄位（`name` 無法修改）。更新後不會自動重新探索，請呼叫 5.7。**回應**：`{"status": "success", "message": "MCP 伺服器配置更新成功", "server": {...}}`。

### 5.6 DELETE /api/mcp/servers/{server_id}

**回應**：`{"status": "success", "message": "MCP 伺服器已成功刪除"}`

### 5.7 POST /api/mcp/servers/{server_id}/discover

重新連線並探索工具，結果寫入 `discovered_tools`。

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

呼叫失敗時 `result` 為 `{"is_success": false, "duration_seconds": ..., "error": "呼叫 MCP 工具失敗: ..."}`。

---

## 6. 模型清單 `/api/tags`

相容 Ollama `tags` 格式的模型清單，兩個端點都不需要登入。

### 6.1 GET /api/tags

設定了任何模型來源（`AVAILABLE_MODELS` 或雲端金鑰）時，回傳 `{"tags": [...], "default": "..."}`，預設模型規則與 `GET /api/chat/models` 相同。都沒有設定時，向 `EXTERNAL_TAGS_URL`（或 `{LLM_API_BASE}/api/tags`）查詢遠端清單；查詢失敗時回傳空清單。

```json
{"tags": ["gpt-6-sol", "gpt-6-luna"], "default": "gpt-6-sol"}
```

### 6.2 GET /api/external-tags

有設定模型來源時回傳 `{"tags": [...], "default": "..."}`；否則把遠端清單原樣轉送。

| 狀態碼 | 情況 |
|---|---|
| `400` | `EXTERNAL_TAGS_URL` 與 `LLM_API_BASE` 都是空值 |
| `502` | 遠端查詢失敗，回傳 `{"error": "Failed to fetch external tags", "models": [...]}` |

---

## 7. 管理後台 `/api/admin`

> 本模組所有端點都需要**管理員**權限。

### 7.1 使用者管理

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/admin/users` | 所有使用者 |
| PUT | `/api/admin/users/{user_id}` | 更新 `username`、`email`、`is_active`、`is_admin`（只需帶入要變更的欄位）；名稱或電子郵件重複時回傳 `400` |
| DELETE | `/api/admin/users/{user_id}` | 刪除使用者與其所有對話 |

`PUT` 回傳 `{"message": "使用者更新成功", "user": {...}}`，`DELETE` 回傳 `{"message": "使用者刪除成功"}`；兩者都會清除統計快取。停用帳號（`is_active=false`）只會阻止之後以密碼登入，見 [已知限制](#10-已知限制)。

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
| GET | `/api/admin/conversations/{conversation_id}/messages` | 任一對話的全部訊息（依時間先後） |
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

---

## 9. 錯誤處理

### 回應格式

錯誤訊息放在 `detail` 欄位：

```json
{"detail": "找不到該自訂 API 工具"}
```

欄位驗證失敗（`422`）時，`detail` 是 FastAPI 的錯誤陣列：

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

只描述使用者輸入本身的驗證錯誤（例如 OpenAPI 規格格式不合法、規格網址被 SSRF 防護拒絕）則直接回傳可據以修正的訊息。

### 常見狀態碼

| 狀態碼 | 說明 |
|---|---|
| `400` | 請求內容錯誤：名稱重複、規格解析失敗、網址未通過 SSRF 驗證、密碼規則不符 |
| `401` | 缺少或無效的存取權杖（`Not authenticated`、`認證權杖無效：驗證失敗`、`權杖已被撤銷`）、登入失敗 |
| `403` | 權限不足（`需要管理員權限`），或來源 IP 因可疑活動被封鎖（封鎖名單存在記憶體中，後端重啟後清除） |
| `404` | 資源不存在（對話、文件、工具、MCP 伺服器、使用者） |
| `422` | 欄位驗證失敗 |
| `429` | 超過速率限制，回應附 `Retry-After` 標頭 |
| `500` | 未預期例外，只回傳錯誤代碼 |
| `502` | `GET /api/external-tags` 查詢遠端清單失敗 |

### 安全回應標頭

所有回應都會加上 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`X-XSS-Protection: 1; mode=block`、`Referrer-Policy: strict-origin-when-cross-origin` 與 `Permissions-Policy: geolocation=(), microphone=(), camera=()`，並移除 `Server` 標頭。

---

## 10. 已知限制

以下是 3.0.0 的現況，整合時請留意：

- `GET /api/chat/models`、`GET /api/chat/tools`、`GET /api/tags`、`GET /api/external-tags` 與 WebSocket `/api/chat/ws/{user_id}` 不需要登入；其中 `GET /api/chat/tools` 的工具說明含知識庫文件的檔名與摘要。部署在公開網路時，請在反向代理層限制存取。
- `GET /api/admin/users` 與 `PUT /api/admin/users/{user_id}` 直接序列化資料表，回應包含 `hashed_password` 欄位（僅管理員可見）。
- `GET /api/documents/` 與 `GET /api/admin/documents` 回傳每份文件的完整文字 `content`。
- MCP 工具呼叫失敗時，`error` 欄位含原始例外訊息，未套用錯誤代碼機制。
- 停用帳號（`is_active=false`）只阻止之後以密碼登入：已發出的存取權杖在到期前仍然有效，`POST /api/auth/refresh` 也不檢查帳號狀態，已登入的工作階段可以繼續換發權杖。需要中止存取時請刪除該帳號：之後的權杖換發會失敗，但尚未到期的存取權杖仍可使用到到期為止。
- 存取權杖回應的 `expires_in` 固定為 `1800`，不隨 `ACCESS_TOKEN_EXPIRE_MINUTES` 變動。
- 權杖撤銷名單與速率限制計數都存在單一後端行程的記憶體中；多行程或多台部署時彼此不共享。
