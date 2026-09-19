# AskMiao 系統架構與設計文件

[繁體中文](architecture.md) | [English](architecture_en.md)

> 本文件說明 AskMiao 系統整體架構、核心模組關係、增強型混合 RAG 檢索流程、Agentic 自主研究管線、外部工具與 MCP 擴充機制，以及 RSA-2048 雙 Token 認證與安全防護設計。

---

## 1. 系統整體分層架構圖

AskMiao 採前後端分離與模組化架構。前端由 React 19 與 Vite 7（Bun 建構）驅動，後端由 FastAPI 提供非同步 RESTful API、SSE 串流與 WebSocket 服務。資料持久層透過 SQLAlchemy 連接關聯式資料庫（`DATABASE_URL` 可指向 SQLite 或 PostgreSQL），快取與 Token 撤銷名單則採用行程內記憶體實作，無外部 Redis 依賴。

```mermaid
flowchart TB
    subgraph Client ["前端應用層 (React 19 + Vite 7 + Bun)"]
        UI["對話介面 (SSE 串流接收)"]
        ToolsUI["AI 工具管理頁 (AiTools)"]
        DocsUI["知識庫文件管理 (Documents)"]
        AdminUI["系統管理後台 (AdminDashboard)"]
    end

    subgraph Gateway ["API 閘道與中介軟體層"]
        SecHeaders["安全標頭中介軟體 (SecurityHeadersMiddleware)"]
        RateLimit["速率限制中介軟體 (RateLimitMiddleware)"]
        CORS["CORS 白名單中介軟體"]
        Redact["日誌雙層脫敏 (security_logging.py)"]
    end

    subgraph Backend ["FastAPI 後端核心服務層"]
        AuthModule["認證模組 (RSA-2048 JWT)"]
        ChatModule["對話與 SSE 串流處理器"]
        RAGModule["混合 RAG 檢索器 (contextual_rag.py)"]
        AgentModule["自主研究 Agent (agent.py)"]
        ToolModule["工具註冊中心 (tools.py)"]
        ApiToolModule["自訂 API 工具服務 (api_tools.py / openapi_parser.py)"]
        McpModule["MCP 用戶端 (mcp_service.py)"]
        SSRFGuard["SSRF 防護閘門 (ssrf_protection.py)"]
        ErrModule["錯誤代碼機制 (error_response.py)"]
    end

    subgraph Storage ["資料儲存與檢索引擎層"]
        DB[(SQLite / PostgreSQL)]
        MemCache[("記憶體快取與 Token 撤銷名單")]
        FAISSIndex["FAISS 向量索引 (Dense Retrieval)"]
        BM25Index["Whoosh BM25 文字索引 (Sparse Retrieval)"]
        Uploads["文件儲存目錄 (data/uploads)"]
    end

    UI --> SecHeaders
    ToolsUI --> SecHeaders
    DocsUI --> SecHeaders
    AdminUI --> SecHeaders
    SecHeaders --> RateLimit --> CORS --> Redact
    Redact --> AuthModule
    Redact --> ChatModule
    Redact --> ApiToolModule
    Redact --> McpModule

    ChatModule --> AgentModule
    AgentModule --> ToolModule
    ToolModule --> RAGModule
    ToolModule --> ApiToolModule
    ToolModule --> McpModule
    ApiToolModule --> SSRFGuard
    McpModule --> SSRFGuard
    ToolModule --> SSRFGuard

    AuthModule --> DB
    AuthModule --> MemCache
    ChatModule --> DB
    ApiToolModule --> DB
    McpModule --> DB
    RAGModule --> FAISSIndex
    RAGModule --> BM25Index
    RAGModule --> Uploads
    ApiToolModule -.-> ErrModule
    McpModule -.-> ErrModule
    ChatModule -.-> ErrModule
```

---

## 2. 增強型混合 RAG 檢索與重排序管道

系統以稠密向量搜尋（Dense Retrieval）與稀疏關鍵字搜尋（Sparse Retrieval）並行檢索，結果經歸一化分數融合後，送入 Cross-Encoder 進行深度重排序。

```mermaid
flowchart LR
    Query["用戶查詢內容 (Query)"] --> Strategy{"檢索策略調配器"}

    subgraph ParallelRetrieval ["並行雙軌檢索"]
        Strategy -->|向量比對| FAISS["FAISS 向量搜尋 (內積相似度, IndexFlatIP)"]
        Strategy -->|關鍵字比對| BM25["Whoosh BM25 (Jieba 中文分詞)"]
    end

    FAISS --> Merge["歸一化分數融合 (HYBRID_ALPHA 加權)"]
    BM25 --> Merge

    Merge --> Reranker["Cross-Encoder 重新排序 (RERANKER_MODEL)"]
    Reranker --> TopK["篩選最佳 FINAL_K 文本片段"]
    TopK --> LLM["LLM 上下文拼接與回應生成"]
```

### 檢索管道核心處理解析

1. **文字切塊 (Chunking)**：上傳文件經 `RecursiveCharacterTextSplitter` 處理，切塊大小與重疊由 `CHUNK_SIZE` / `CHUNK_OVERLAP` 控制（範本預設 300 / 100 字元）。結構化記錄與 JSON 資料另以「原子記錄分塊」方式建立，確保逐筆統計正確。
2. **向量嵌入 (Embedding)**：預設採用 `BAAI/bge-small-zh-v1.5`（`EMBEDDING_MODEL`），向量維度於載入模型時自動取得，FAISS 以 `IndexFlatIP` 內積索引建立。
3. **關鍵字檢索 (BM25)**：結合 `Whoosh` 搜尋引擎與 `Jieba` 中文分詞，補足向量檢索對專有名詞與代碼之弱點。
4. **分數融合 (Fusion)**：兩軌分數依 `NORMALIZATION` 策略歸一化後，以 `HYBRID_ALPHA` 加權合併。
5. **重排序 (Reranking)**：Cross-Encoder（預設 `BAAI/bge-reranker-base`）對候選片段計算交叉注意力分數，經 `RERANK_WEIGHT` 與 `FINAL_THRESHOLD` 過濾後，取前 `FINAL_K` 段組裝上下文。
6. **檢索評估 (Evaluation)**：`evaluator.py` 提供 Hit Rate、MRR 等指標與 Alpha 自動調優依據。

---

## 3. RSA-2048 雙 Token 認證與撤銷名單生命週期

系統採 Access Token 與 Refresh Token 雙令牌機制。Access Token 預設 30 分鐘（`ACCESS_TOKEN_EXPIRE_MINUTES`），Refresh Token 存放於 HttpOnly Cookie（預設 7 天，`REFRESH_TOKEN_EXPIRE_DAYS`），登出時兩者皆寫入行程內撤銷名單（`TokenBlacklist`）。

```mermaid
sequenceDiagram
    autonumber
    actor User as 用戶 / 前端
    participant API as FastAPI 伺服器
    participant Blacklist as 記憶體撤銷名單 (TokenBlacklist)
    participant DB as 資料庫 (SQLite / PostgreSQL)

    User->>API: 1. POST /api/auth/login (憑證)
    API->>DB: 2. 驗證密碼 Hash
    DB-->>API: 3. 驗證通過
    API->>User: 4. 回傳 Access Token (JSON) + 設置 Refresh Token (HttpOnly Cookie)

    User->>API: 5. GET /api/auth/me (帶 Access Token 標頭)
    API->>Blacklist: 6. 檢查 Token 是否已撤銷
    Blacklist-->>API: 7. 未撤銷 (合法)
    API-->>User: 8. 回傳用戶個人資料

    User->>API: 9. POST /api/auth/logout (登出請求)
    API->>Blacklist: 10. 將 Access / Refresh Token 寫入撤銷名單 (至其到期時間)
    API-->>User: 11. 清除 Refresh Token Cookie 並回傳登出成功
```

> 撤銷名單為行程內記憶體結構，具備自動清理過期項目之機制；後端重啟後名單將重置，未過期之舊 Token 於重啟後會重新被視為有效。

---

## 4. Agentic RAG 自主研究與多輪工具調用管線

系統採 ReAct 自主研究代理人架構（`ResearchAgent`），透過 Native Tool Calling 實現多輪工具協同與上下文自主搜集，最大輪數由 `AGENT_MAX_TURNS` 控制。

```mermaid
flowchart LR
    UserQuery["用戶問題 (Query) + 選用附件"] --> Agent["自主研究 Agent (ResearchAgent)"]

    subgraph ToolLoop ["多輪工具調用循環 (AGENT_MAX_TURNS)"]
        Agent -->|決策與參數| Tools{"工具註冊中心 (ResearchToolRegistry)"}
        Tools -->|內部檢索| LocalRAG["search_knowledge_base<br/>(FAISS + BM25 + Cross-Encoder)"]
        Tools -->|統計篩選| Filter["filter_and_count_records<br/>(日期 / 作者 / 關鍵字精確計數)"]
        Tools -->|即時聯網| WebSearch["web_search<br/>(Ollama / DuckDuckGo 雙引擎)"]
        Tools -->|深度閱讀| WebFetch["web_fetch<br/>(HTTP 抓取與純文字解析)"]
        Tools -->|外部系統| Extern["自訂 API 工具 / mcp_* 工具"]

        LocalRAG --> ToolResult["工具執行結果 (Tool Outputs)"]
        Filter --> ToolResult
        WebSearch --> ToolResult
        WebFetch --> ToolResult
        Extern --> ToolResult
        ToolResult -->|觀察與注入上下文| Agent
    end

    Agent -->|SSE 事件串流| FinalAnswer["結構化回應<br/>(Answer + Research Trace + Sources)"]
```

### 自主研究核心機制

1. **動態決策思考**：模型依問題語境自主判斷應查詢內部知識庫、進行統計篩選、外部即時聯網、深入閱讀 URL，或調用外部 API / MCP 工具。
2. **研究歷程追蹤 (Research Trace)**：每輪工具調用之步驟、工具名稱、輸入參數、輸出摘要與耗時皆結構化記錄，透過 `step_start` / `step_end` SSE 事件即時推送前端折疊時間軸。
3. **來源標籤與跳轉 (Sources Detail)**：整合內部文檔片段與外部網頁連結產生來源標籤，支援點擊驗證出處。
4. **多模態輸入**：附件中的圖片以 `image_url` 內容區塊送入視覺模型，文字類附件則抽取內容併入提問上下文。

---

## 5. 外部工具擴充與 MCP 整合架構

除內建工具外，系統提供兩條工具擴充路徑，皆在組裝工具定義時由資料庫動態載入，變更後無需重啟後端。

```mermaid
flowchart TB
    subgraph Registry ["ResearchToolRegistry.get_tool_definitions()"]
        Builtin["內建工具定義"]
        DynamicApi["啟用中的自訂 API 工具 (custom_api_tools)"]
        DynamicMcp["啟用中的 MCP 工具快取 (mcp_servers.discovered_tools)"]
    end

    subgraph ImportFlow ["自訂 API 工具建立流程"]
        Spec["OpenAPI / Swagger 規格 (內容或 URL)"] --> Parser["OpenApiParser (OAS 2.0 / 3.0 / 3.1)"]
        Parser --> Select["前端勾選欲匯入端點"]
        Select --> Import["POST /api/api-tools/import"]
        Import --> DB[(custom_api_tools)]
        Manual["手動表單建立"] --> DB
    end

    subgraph McpFlow ["MCP 伺服器接入流程"]
        Server["MCP 伺服器設定 (stdio / HTTP)"] --> Discover["initialize + tools/list"]
        Discover --> McpDB[(mcp_servers)]
    end

    DB --> DynamicApi
    McpDB --> DynamicMcp
    Builtin --> Agent["Agent 工具集"]
    DynamicApi --> Agent
    DynamicMcp --> Agent

    Agent -->|執行| Exec{"execute_tool(name, arguments)"}
    Exec -->|內建| Internal["內部工具實作"]
    Exec -->|自訂 API| Http["execute_http_api_tool (httpx)"]
    Exec -->|mcp_* 前綴| McpCall["McpManager.execute_mcp_tool (tools/call)"]
```

### 設計要點

1. **工具命名與路由**：自訂 API 工具以其 `name` 直接註冊；MCP 工具統一採 `mcp_<伺服器名稱>_<工具名稱>` 命名，`execute_tool` 依前綴判斷路由目標。
2. **HTTP 執行器**：`execute_http_api_tool` 統一處理 Path 變數替換、Query 組裝、Header 與認證注入（Bearer / API Key / Basic）、JSON 或表單主體序列化，以及逾時與錯誤隔離。
3. **MCP 傳輸**：`McpStdioClient` 以子行程 stdio 進行 JSON-RPC 交握；`McpHttpClient` 以 HTTP 傳輸，兩者皆支援 `initialize`、`tools/list` 與 `tools/call`。
4. **工具快取**：MCP 工具清單於建立或手動探索時寫入 `discovered_tools`，避免每次組裝工具定義都需重新連線。

---

## 6. 安全性設計

### 6.1 敏感資料雙層脫敏

為通過安全稽核（修復 CodeQL `py/clear-text-logging-sensitive-data` 告警），`backend/app/core/security_logging.py` 實施兩道遮罩防線：

1. **物件層級遞迴脫敏 (`sanitize_sensitive_data`)**：遍歷字典與列表，匹配敏感 Key（`password`、`token`、`secret`、`authorization`、`cookie` 等，不分大小寫），將值替換為 `[REDACTED]`。
2. **字串層級二次正則遮罩**：於 JSON 序列化或日誌輸出前再次掃描，確保任何格式之敏感金鑰皆不遺留於日誌。

### 6.2 錯誤代碼機制（CWE-209 / CWE-497）

`error_response.py` 將未預期例外之完整訊息與堆疊僅寫入伺服器日誌，對外回傳隨機錯誤代碼：

- `log_and_get_error_id()`：記錄例外並產生 12 碼識別碼。
- `format_client_error()` / `build_error_payload()`：組出不含內部細節之對外訊息與 `error_id`。
- `SafeClientError`：標記「訊息僅描述使用者輸入本身」之驗證錯誤，可原樣回傳協助使用者修正。

此機制亦套用於 SSE 串流之 `error` 事件，避免例外文字經串流外洩。

### 6.3 SSRF 防護

所有由使用者輸入驅動之外部請求（OpenAPI 規格 URL、`web_fetch`、MCP HTTP 傳輸、自訂 API 工具）皆須通過 `ssrf_protection.py`：

```mermaid
flowchart LR
    Input["使用者提供之 URL"] --> Scheme{"協定檢查 (http / https)"}
    Scheme --> Port{"連接埠檢查 (阻擋危險埠)"}
    Port --> Host{"主機名稱檢查 (localhost / .internal 等)"}
    Host --> Resolve["DNS 解析取得所有 IP"]
    Resolve --> IPCheck{"IP 範圍檢查"}
    IPCheck -->|私有 / 迴環 / 連結本地 / 雲端中繼資料| Block["拒絕請求 (SSRFProtectionError)"]
    IPCheck -->|公開位址| Allow["允許並以 safe_fetch_text 發送"]
```

阻擋範圍涵蓋 IPv4 / IPv6 私有與保留網段、迴環與連結本地位址、雲端中繼資料端點（如 `169.254.169.254`）、內部網域後綴，以及危險連接埠清單。相關行為由 `backend/tests/test_ssrf_protection.py` 覆蓋。

### 6.4 其他防護

- **安全標頭**：`SecurityHeadersMiddleware` 統一注入安全回應標頭。
- **速率限制**：`RateLimitMiddleware` 依 `RATE_LIMIT_PER_MINUTE` 限制單位時間請求數。
- **CORS 白名單**：僅允許 `ALLOWED_ORIGINS`（可附加 `DEVTUNNEL_URL`）之來源，並允許憑證攜帶。
- **輸入驗證**：`input_validator.py` 檢查檔名、副檔名與路徑遍歷攻擊樣態。

---

## 7. 架構決策紀錄 (ADR)

專案重大架構決策均獨立記載於 ADR 文件中：

- [ADR 索引與說明](./adr/README.md)
- [ADR-0001: 增強型混合 RAG 檢索架構與雙 Token 安全防護決策](./adr/0001-hybrid-rag-and-security.md)
