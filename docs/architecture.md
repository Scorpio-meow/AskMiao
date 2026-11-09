# AskMiao 系統架構與設計

[繁體中文](architecture.md) | [English](architecture_en.md)

> 本文件說明 AskMiao **8.5.0** 的架構、啟動流程、資料模型、文件處理與檢索管線、Agentic RAG 研究迴圈、LLM 呼叫層、外部工具整合、認證與安全設計，以及前端架構（本版變更見 [CHANGELOG](../CHANGELOG.md#850---2026-11-09)）。設計背後的取捨記錄在 [架構決策紀錄（ADR）](adr/README.md)。

## 目錄

1. [系統總覽](#1-系統總覽)
2. [啟動流程](#2-啟動流程)
3. [資料模型](#3-資料模型)
4. [文件擷取與切塊](#4-文件擷取與切塊)
5. [片段儲存與索引一致性](#5-片段儲存與索引一致性)
6. [混合檢索與重排](#6-混合檢索與重排)
7. [Agentic RAG 研究迴圈](#7-agentic-rag-研究迴圈)
8. [LLM 呼叫層](#8-llm-呼叫層)
9. [外部工具與 MCP](#9-外部工具與-mcp)
10. [認證與授權](#10-認證與授權)
11. [安全設計](#11-安全設計)
12. [前端架構](#12-前端架構)
13. [部署與維運](#13-部署與維運)
14. [架構決策紀錄](#14-架構決策紀錄)

---

## 1. 系統總覽

AskMiao 採前後端分離架構。前端以 React 19、TypeScript 7 與 Vite 8 建構（Bun 管理套件）；後端以 FastAPI 提供 REST API 與 SSE 串流，SQLAlchemy 連接 SQLite 或 PostgreSQL。向量索引（FAISS）與關鍵字索引（Whoosh BM25）存在本機檔案，片段的權威資料存在資料庫；權杖撤銷名單、速率限制與登入失敗計數、同時串流數、待核准的工具呼叫與統計快取都在後端行程的記憶體中，沒有 Redis 等外部依賴。

```mermaid
flowchart TB
    subgraph Client ["前端 · React 19 + TypeScript 7 + Vite 8"]
        ChatUI["聊天頁（SSE 串流、研究歷程、引用來源）"]
        DocsUI["知識庫（管理員）"]
        ToolsUI["AI 工具（管理員）"]
        AdminUI["管理後台（管理員）"]
    end

    subgraph Gateway ["中介軟體（由外而內）"]
        AccessLog["AccessLogMiddleware<br/>請求 ID 與存取日誌"]
        BodyLimit["RequestBodyLimitMiddleware<br/>請求本文上限"]
        CORS["CORSMiddleware<br/>來源白名單"]
        RateLimit["RateLimitMiddleware<br/>依 IP 速率限制（RATE_LIMIT_ENABLED 時）"]
        SecHeaders["SecurityHeadersMiddleware<br/>安全回應標頭"]
    end

    subgraph Backend ["FastAPI 路由與服務"]
        AuthAPI["/api/auth<br/>jwt_auth.py"]
        ChatAPI["/api/chat<br/>SSE 串流"]
        DocAPI["/api/documents<br/>document_processor.py"]
        ToolAPI["/api/api-tools、/api/mcp<br/>openapi_parser.py、arazzo.py、mcp_service.py、mcp_oauth.py"]
        AdminAPI["/api/admin"]
        LlmConnAPI["/api/llm-connections、/api/admin/llm-connections、/api/admin/system-models<br/>llm_connections.py、system_models.py"]
        SkillAPI["/api/skills<br/>agent_skills.py"]
        RAG["HybridContextualRAG<br/>索引校正、寫入與檢索"]
        Agent["ResearchAgent + ResearchSession"]
        Approval["ToolApprovalBroker<br/>工具呼叫核准"]
        Registry["ResearchToolRegistry"]
        LLM["llm_client.py"]
        SSRF["ssrf_protection.py"]
        Err["error_response.py"]
    end

    subgraph Storage ["儲存"]
        DB[("SQLite / PostgreSQL")]
        FAISS["FAISS IndexIDMap2"]
        BM25["Whoosh BM25"]
        Files["data/uploads"]
        Skills["SKILLS_DIR<br/>技能檔案"]
        Mem[("行程記憶體<br/>撤銷名單、速率與登入失敗計數、待核准項目、快取")]
    end

    Client --> AccessLog --> BodyLimit --> CORS --> RateLimit --> SecHeaders
    SecHeaders --> AuthAPI & ChatAPI & DocAPI & ToolAPI & AdminAPI & LlmConnAPI & SkillAPI
    ChatAPI --> Agent --> Registry
    Agent --> Approval
    ChatAPI --> Approval
    Agent --> LLM
    DocAPI --> LLM
    LLM --> SSRF
    Registry --> RAG
    Registry --> SSRF
    Registry --> Skills
    ToolAPI --> SSRF
    LlmConnAPI --> SSRF
    DocAPI --> RAG
    AdminAPI --> RAG
    RAG --> FAISS & BM25
    RAG --> DB
    DocAPI --> Files
    AuthAPI --> DB
    AuthAPI --> Mem
    ToolAPI --> DB
    LlmConnAPI --> DB
    SkillAPI --> DB
    SkillAPI --> Skills
    ChatAPI -.-> Err
    ToolAPI -.-> Err
```

| 層 | 主要模組 | 職責 |
|---|---|---|
| 路由 | `app/api/*.py` | 請求驗證、權限檢查、回應格式 |
| 核心 | `app/core/*.py` | 設定、認證與登入節流、LLM 呼叫、SSRF、工具憑證加密、錯誤代碼、日誌遮蔽 |
| RAG | `app/rag/` | 片段儲存、索引、混合檢索、研究 Agent 與工具 |
| 服務 | `app/services/` | 對話持久化、文件擷取與摘要、OpenAPI 與 Arazzo 解析、MCP 用戶端與遠端 OAuth、LLM API 連線與系統模型（`llm_connections.py`、`system_models.py`）、Agent Skills（`agent_skills.py`） |
| 背景任務 | `app/tasks/uploads_watcher.py` | 定期檢查上傳檔是否遺失（只記警告） |

---

## 2. 啟動流程

```mermaid
sequenceDiagram
    autonumber
    participant Main as python main.py
    participant Cfg as Settings
    participant Imp as 模組匯入
    participant Life as lifespan
    participant RAG as HybridContextualRAG

    Main->>Cfg: 讀取 backend/.env 與環境變數
    Cfg->>Cfg: 驗證必填設定、數值範圍與 TOOL_SECRETS_KEY 格式，解析相對路徑
    Cfg->>Cfg: 寫出 HF_* 環境變數（載入模型前）
    Main->>Imp: 匯入路由
    Imp->>Imp: 驗證領域設定檔、載入或產生 RSA 金鑰
    Main->>Main: 設定日誌、註冊中介軟體與路由（ENABLE_API_DOCS=true 時才提供 /docs）
    Main->>Life: uvicorn 依 HOST、PORT、RELOAD 啟動
    Life->>Life: 建立資料表（create_all），補上缺少的欄位並加密明文的工具憑證（upgrade_schema）
    Life->>Life: 刪除 SKILLS_DIR 中上次未完成的技能暫存目錄（cleanup_staging_directories）
    Life->>RAG: 初始化
    RAG->>RAG: 設定 jieba 詞典並計算斷詞簽章
    RAG->>RAG: 載入嵌入模型與 FAISS（舊格式改名 .legacy.bak，維度不符改名 .mismatch.bak）
    RAG->>RAG: 載入 BM25 與重排模型（重排模型失敗即中止啟動）
    RAG->>RAG: 依 rag_chunks 校正 FAISS 與 BM25
    Life->>RAG: 補建未完成索引的文件（index_unprocessed_documents，PDF 可能呼叫 OCR 系統模型）
    Life->>Life: 啟動上傳檔監看任務
```

啟動失敗的常見原因：

| 階段 | 失敗原因 | 訊息 |
|---|---|---|
| 設定驗證 | 缺少必填設定、數值超出範圍、`WEB_FETCH_ALLOWED_DOMAINS` 格式錯誤、`TOOL_SECRETS_KEY` 不是有效的 Fernet 金鑰（例如仍是範本值） | `Field required`、`Input should be ...`、網域格式說明或 `TOOL_SECRETS_KEY 必須是 Fernet 金鑰` |
| 領域設定檔 | 檔案不存在或格式不符 | `找不到 DOMAIN_PROFILE_PATH 指定的領域設定檔`、`領域設定檔 ... 格式錯誤` |
| RSA 金鑰 | `backend/keys/` 的金鑰無法載入或產生（任何 `ENVIRONMENT`） | 匯入 `jwt_auth.py` 時的金鑰讀取或寫入例外 |
| jieba 詞典 | `JIEBA_DICTIONARY` 指向不存在的檔案 | `找不到 JIEBA_DICTIONARY 指定的詞典檔` |
| 模型 | 嵌入或重排模型無法載入 | `無法載入嵌入模型`、`無法載入重排模型` |
| FAISS | 索引檔損毀或被占用 | `向量索引載入失敗`（原檔保留，移出後重啟即可依資料庫重建） |

---

## 3. 資料模型

```mermaid
erDiagram
    users ||--o{ conversations : "擁有"
    conversations ||--o{ messages : "包含"
    conversations ||--o{ conversation_files : "存放"
    users ||--o{ documents : "上傳"
    documents ||--o{ rag_chunks : "切成"
    users ||--o{ llm_connections : "擁有（個人連線）"
    llm_connections ||--o{ system_models : "提供"

    users {
        int id PK
        string username UK
        string email UK
        string hashed_password "Argon2"
        bool is_active
        bool is_admin
        string role
        datetime created_at
        datetime last_login
        datetime tokens_valid_after "早於此時刻簽發的權杖無效"
    }
    conversations {
        int id PK
        int user_id FK
        string title
        datetime created_at
        datetime updated_at
    }
    messages {
        int id PK
        int conversation_id FK
        text content
        bool is_user
        text context_used "JSON：來源與研究歷程或附件"
        string model_name
        datetime created_at
    }
    documents {
        int id PK
        string filename
        text content "擷取出的完整文字"
        string file_type
        text description "AI 摘要"
        int uploaded_by FK
        bool is_processed
        datetime created_at
    }
    rag_chunks {
        int id PK "chunk_id"
        int document_id FK
        int chunk_index
        text content
        text chunk_metadata "JSON"
        datetime created_at
    }
    custom_api_tools {
        int id PK
        string name UK
        string method
        string url
        text headers "加密 JSON"
        text auth_config "加密 JSON"
        text parameters_schema "JSON"
        text param_locations "JSON"
        string body_content_type
        bool is_enabled
        bool requires_approval
    }
    mcp_servers {
        int id PK
        string name UK
        string transport_type
        string command
        text env_vars "加密 JSON"
        string url
        text headers "加密 JSON"
        text discovered_tools "JSON 工具快取"
        text discovered_resources "JSON resources 快取"
        text discovered_prompts "JSON prompts 快取"
        string protocol_version "協商到的 MCP 版本"
        text oauth_config "加密 JSON"
        text oauth_tokens "加密 JSON"
        string status
        bool is_enabled
        bool requires_approval
    }
    agent_skills {
        int id PK
        string name UK
        text description
        text allowed_tools
        bool is_enabled
        bool allow_scripts
        text allowed_user_ids "JSON，空值為所有人"
    }
    llm_connections {
        int id PK
        string name
        string provider
        string api_base
        text api_key "加密 JSON"
        text models "JSON"
        int max_output_tokens
        int owner_id FK "空值為共用連線"
        text allowed_user_ids "JSON，共用連線的使用者"
    }
    system_models {
        string purpose PK "document_summary、pdf_ocr"
        int connection_id FK
        string model_name
        string reasoning_effort
    }
    conversation_files {
        int id PK
        int conversation_id FK
        int user_id FK
        string filename
        string media_type
        int size_bytes
        bytes data "延遲載入"
        string origin "user、assistant"
        int parent_id "修改來源"
        int root_id "同一系列的第一版"
        int version
        datetime created_at
    }
```

- **`rag_chunks` 是片段的權威來源**：`id` 就是 chunk_id，FAISS 與 BM25 都以它為鍵。`chunk_metadata` 保存 `source`、`document_id`、`chunk_index`、`original_filename`、`content_type`，Q&A 片段另有 `question`，結構化記錄另有 `record_index`、`part`、`part_count`，以及視來源而定的 `label`、`links`、`group`、`sheet`、`row`（見第 4 節）。
- **`messages.context_used`**：助理訊息存 `sources`、`sources_detail`、`research_trace` 與 `files`（這次回答建立、修改、刪除的對話檔案）；使用者訊息存 `attachments`。圖片附件保留 base64 的 `data_url`；其他附件的原始檔存成對話檔案，這裡只留 `file_id`，不再存 base64。附件抽出的文字最多 50,000 字元存入該附件的 `content`，供之後的提問帶入前文。`/api/chat` 的回應只提供解析後的欄位，`context_used` 一律為 `null`。
- **`conversation_files`**：對話中的檔案，包括使用者上傳的文件類附件（`origin=user`）與研究助理建立或修改的檔案（`origin=assistant`），內容存在 `data` 欄位，只在下載或讀取時載入。修改一律另存新版本：`parent_id` 指向修改來源，`root_id` 指向同一系列的第一版，`version` 依系列遞增。每位使用者的使用者訊息 `context_used` 長度加上對話檔案大小，合計上限 200 MiB。刪除對話（含管理員刪除對話或使用者）時一併刪除，見 [對話檔案](#對話檔案)。
- **`requires_approval`**：自訂 API 工具與 MCP 伺服器的呼叫前核准旗標，見第 9 節。
- **`users.tokens_valid_after`**：簽發時間早於此時刻的存取與重新整理權杖一律無效。建立帳號時等於 `created_at`（帳號刪除後 id 被重用時，舊權杖不會對應到新帳號），變更密碼或管理員重設密碼時更新為當下，見第 10 節。
- **工具憑證欄位**：`custom_api_tools` 的 `headers`、`auth_config` 與 `mcp_servers` 的 `env_vars`、`headers`、`oauth_config`、`oauth_tokens` 以 `TOOL_SECRETS_KEY`（Fernet）加密後存放，內容以 `fernet:` 開頭，見第 9 節；LLM API 連線的金鑰（`llm_connections.api_key`）也以同一把金鑰加密。
- **LLM API 連線與系統模型**：`llm_connections.owner_id` 有值時是該使用者的個人連線，空值時是管理員建立的共用連線（`allowed_user_ids` 限定可使用的帳號，空值為所有人）；`system_models` 為文件摘要（`document_summary`）與 PDF OCR（`pdf_ocr`）各指定一條共用連線中的模型與思考程度。
- **`agent_skills`**：只存技能的中繼資料與設定，檔案在 `SKILLS_DIR`，資料庫沒有副本。
- **資料庫以外的檔案**：`backend/data/`（`faiss_index.bin`、`index_metadata.json`、`bm25_index/`、`uploads/`、`jieba_cache/`，以及設定 `RERANKER_OPENVINO_DEVICE` 時重排模型的編譯快取 `openvino_cache/`）、`SKILLS_DIR`（Agent Skills 的檔案，範本值 `data/skills`）、`backend/keys/`（JWT 金鑰對）、`backend/mcp_filesystem_sandbox/`（檔案系統 MCP 範本的根目錄）與 `backend/logs/`（日誌，位置由 `LOG_DIR` 決定）。

資料表在後端啟動時以 SQLAlchemy `create_all` 建立，接著由 `upgrade_schema()` 為既有資料表補上後來新增的欄位並回填（目前為兩個 `requires_approval`：API 工具依方法回填，`GET`、`HEAD`、`OPTIONS` 以外為 `true`；MCP 伺服器一律為 `true`；`custom_api_tools.body_content_type`，以 `application/json` 回填；`custom_api_tools` 的 `param_styles`、`workflow_definition`，`mcp_servers` 的 `discovered_resources`、`discovered_prompts`、`protocol_version`、`oauth_config`、`oauth_tokens` 與 `agent_skills` 的 `allow_scripts`、`allowed_user_ids`；`system_models.reasoning_effort`，以 `none` 回填；以及 `users.tokens_valid_after`，以 `created_at` 回填；此欄位為空的帳號，例如回退到舊版期間建立的，每次啟動都會補值），再把仍以明文存放的工具憑證改為加密（無法解析為 JSON 的值會清空並記下警告）。新建立的 SQLite 資料庫中，`users`、`documents`、`rag_chunks` 與 `llm_connections` 使用 `AUTOINCREMENT`，刪除後的 id 不會被新資料重用。`backend/init.sql` 是 PostgreSQL 容器的初始化結構，`backend/init-app-role.sh` 接著建立後端連線用的非超級使用者並把資料表交給它擁有（見第 13 節）。

---

## 4. 文件擷取與切塊

```mermaid
flowchart TB
    Up["POST /api/documents/upload<br/>單次最多 10 個檔案"] --> Name["檔名與副檔名檢查<br/>28 種副檔名、危險字元"]
    Name --> Size["大小檢查<br/>MAX_FILE_SIZE_MB"]
    Size --> Ext["擷取文字與結構化記錄<br/>依副檔名分派，只解析一次"]
    Ext --> Dup{"內容與既有文件相同？"}
    Dup -->|是| Skip["回報 duplicate"]
    Dup -->|否| Sum["AI 摘要<br/>未指定系統模型或呼叫失敗時改用規則摘要"]
    Sum --> Save["寫入 documents"]
    Save --> Split{"切塊策略"}
    Split -->|解析出結構化記錄| Rec["每筆記錄一個片段<br/>過長時切成多段並重複標頭"]
    Split -->|非結構化格式且為 Q：/A：| QA["一問一答一個片段<br/>超過 CHUNK_SIZE 時改用遞迴切塊"]
    Split -->|其他| Rcs["遞迴切塊<br/>CHUNK_SIZE / CHUNK_OVERLAP"]
    QA & Rec & Rcs --> Index["寫入 rag_chunks、FAISS、BM25"]
```

### 文字擷取

| 格式 | 擷取方式 |
|---|---|
| PDF | PyMuPDF 擷取文字，擷取前先替內嵌 TrueType 字型中 ToUnicode 沒有對應（或對到 U+FFFD）的替代字形補上對應：依字型 GSUB 的單一替換反查原本的字元，例如 Illustrator 輸出的 Noto Sans TC 數字，否則會被擷取成「俸」這類字；空白或判定為亂碼的頁面，以 150 DPI 轉成圖片交給管理員指定的 PDF OCR 系統模型辨識（見 [設定參考：系統模型](configuration.md#系統模型)），未指定時不做 OCR。在文件的執行緒上逐頁點陣化，每頁最多 25 MP（超過時降低解析度），只有模型呼叫最多 4 頁平行，並交回主事件迴圈經共用的 LLM 用戶端送出；聊天附件最多 OCR 20 頁，管理員上傳不限。沒有任何一頁擷取到文字（例如 OCR 未設定或辨識失敗）或有密碼保護時拒絕。PyMuPDF 無法讀取時以 pypdf 備援 |
| DOCX | 依文件中的順序輸出段落與表格（每列以 `\|` 串接），表格留在所屬標題下 |
| PPTX | 逐頁投影片文字（含群組內的圖形與表格），以及每頁的備忘稿 |
| XLSX | 以唯讀模式逐工作表讀取，每個工作表的第一個非空列為表頭，後面每列成為一筆結構化記錄；沒有資料列時逐列以 `\|` 串接 |
| CSV | 第一個非空列為表頭，後面每列成為一筆結構化記錄；沒有資料列時逐列以 `\|` 串接 |
| JSON、JSONL、YAML | 解析成結構化記錄（見下方「結構化資料」） |
| JS、TS、JSX、TSX | 含 `const x = [...]`、`module.exports = {...}` 這類宣告且右側是嚴格 JSON 時解析成結構化記錄；否則以程式碼文字讀取 |
| PY、INI、ENV、SQL | 以文字讀取，Base64 圖片與 SVG 以佔位字取代；JS、TS、JSX、TSX、JSON、JSONL、YAML 未解析成結構化記錄時也是如此 |
| HTML | 以 `app/core/html_text.py` 單次線性掃描去除標籤、`script`、`style` 與 `noscript` 後的文字 |
| JAVA、CPP、C、SH 與其他文字檔 | 依序嘗試 UTF-8、UTF-8 BOM、Big5、GBK、GB2312、Latin-1 編碼讀取，不取代 Base64 圖片與 SVG |

擷取前會依宣告的類型檢查檔頭特徵。管理員上傳與聊天附件各用一組資源預算（`app/core/limits.py` 的 `ExtractionLimits`，呼叫端必須指定）：OOXML（DOCX、PPTX、XLSX）先檢查 ZIP 的成員數（≤ 10,000）、成員宣告的解壓大小合計（管理員上傳 ≤ 200 MiB、聊天附件 ≤ 64 MiB）與壓縮比（解壓後超過 10 MiB 的單一成員或整個檔案 ≤ 100），擋下壓縮炸彈；聊天附件的 DOCX、PPTX 另依 `[Content_Types].xml` 加總會被建成 DOM 的 XML 部件（另含 `.rels`），上限 8 MiB，改副檔名無法繞過。聊天附件的 JSON、JSONL、YAML 與 JS 宣告超過 2,000,000 字時不解析，改以純文字處理並只做線性的雜訊清除；整個行程同時最多解析 2 個聊天附件，超過預算或無法讀取（例如無效的 Office 文件、PDF 有密碼保護或沒有可擷取的文字）的附件不讀取內容，改以一段說明告知模型。管理員上傳的檔案擷取不出文字時回報失敗並刪除暫存檔。SVG 去除、JSON 宣告抽取、Q&A 切分與目錄行清理都以線性時間實作，惡意構造的輸入不會觸發二次時間的正規式回溯。

### 結構化資料

JSON、JSONL、YAML、JS 宣告、CSV 與 XLSX 由 `app/services/structured_data/` 解析一次，產生 `ExtractionResult`（渲染後的文字、記錄清單、格式與警告）。渲染後的文字存入 `documents.content`，供摘要與重複檢查；記錄清單直接交給切塊，不再從文字解析回來。聊天附件只使用渲染後的文字。

- **記錄的界定**：根層級是陣列時每個元素一筆（JSONL 每行一筆，空白行略過）；根層級是物件時，每個「物件陣列」屬性各自是一組記錄，其餘頂層欄位合成一筆 `【上下文】` 記錄；沒有物件陣列時整個物件是一筆。陣列中的純量元素各自成為一筆只有值的記錄；根層級就是純量時當作一般文字。YAML 有多份文件時視為陣列。
- **欄位**：一律使用原始欄位名，以 `key: 值` 逐行輸出。巢狀物件攤平成點路徑（`contact.email`），物件陣列寫成 `items[0].name`，純量陣列以逗號串接；`null` 與空字串不輸出。日期輸出為 ISO 格式（午夜時只輸出日期），整數值的浮點數輸出為整數，布林值輸出為 `true` / `false`。
- **表格**：表頭的空白名稱，XLSX 以欄位字母、CSV 以從 1 起算的欄序號代替，重複名稱加上 `_2`、`_3`；空白儲存格不輸出；列號與試算表上看到的一致。
- **雜訊**：值中的 Base64 圖片與 SVG 換成佔位字但保留欄位；領域設定檔 `record_ignore_fields` 列出的欄位（不分大小寫）整個略過。
- **標頭與識別欄位**：每筆記錄的第一行是標頭，例如 `【記錄 3】`、`【data 記錄 3】`、`【第 5 列】`、`【工作表1 第 5 列】`，後面接上 `record_label_fields` 中第一個有值的欄位，依 `MAX_RECORD_LABEL_CHARS` 截斷；記錄之間以 `\n\n---\n\n` 分隔。以 `http://`、`https://` 開頭的值收進 `links`。
- **解析失敗**：JSON、JSONL、YAML 解析失敗、超過解析上限，或 YAML 別名展開後的節點數超過原始文字長度時，改以純文字切塊並在上傳結果附上 `warning`；JS 宣告解析失敗時視為一般程式碼，不提示。結構化格式不做 Q&A 偵測。

### AI 摘要

上傳、重新生成摘要，以及重建索引遇到沒有摘要的文件時，以管理員指定的文件摘要系統模型與思考程度生成兩三句的繁體中文摘要，說明文件類型、主題與涵蓋的重點（逾時為 `LLM_TIMEOUT`）。長文件取開頭、中段與結尾各一段作為樣本；結構化資料另附上記錄數、格式與欄位名稱。未指定系統模型時不呼叫模型，直接使用規則摘要；模型呼叫失敗時同樣改用規則摘要，並依領域設定檔的 `summary_fallback` 過濾雜訊；結構化資料的規則摘要直接使用記錄數與欄位名稱（最多 `MAX_SUMMARY_FIELD_NAMES` 個），只有資料庫內容可用時（重新生成摘要、知識庫目錄）改為計數記錄標頭。摘要也會組成 `search_knowledge_base` 工具說明中的知識庫目錄，幫助 Agent 判斷該查哪份文件；目錄每次呼叫模型都會送出，長度以 `MAX_KB_CATALOG_CHARS`（4,000 字）為上限，超過時只列出前面的文件並告知其餘份數。組目錄時遇到沒有摘要的文件只用規則摘要，不呼叫模型。

### 切塊策略

一般文件以 `RecursiveCharacterTextSplitter` 切塊，分隔符號依序為段落分隔線、空行、換行、中文句末與句中標點（`。！？；：，`）、英文標點與空白。Q&A（只在非結構化格式中偵測）一問一答一個片段；整組問答超過 `CHUNK_SIZE` 時改以上述切塊器切開，段落之間有 `CHUNK_OVERLAP` 的重疊。結構化記錄不超過 `CHUNK_SIZE` 時整筆一個片段；過長時以整行欄位為單位切成多段，單一欄位的值本身過長時再以上述切塊器切開，每段都重複標頭並加上 `（2/3）`，段落之間不重疊。不超過 `CHUNK_SIZE` 的 Q&A 與結構化記錄的每一段都標記為 `preserve_whole`，不再交給一般切塊。

重建索引時，原始檔還在 `UPLOAD_DIR` 的文件會重新擷取並覆寫 `documents.content`；原始檔已遺失的文件改以資料庫內容當一般文字切塊，並列在回應的 `missing_source_files`。既有摘要（含管理員手動修訂的）會保留，只替沒有摘要的文件生成；重建逐份處理，其他文件照常可查：每份文件完成擷取、摘要與切塊後，才移除舊片段並寫入新片段。在擷取、摘要或切塊時失敗的文件保留舊片段；在寫入索引時失敗的文件，舊片段已移除，會沒有任何片段，需要再執行一次重建。兩者都列在 `failed_documents`；重建進行中再次呼叫回傳 `409`。

---

## 5. 片段儲存與索引一致性

片段以資料庫 `rag_chunks` 為準，FAISS 使用 `IndexIDMap2(IndexFlatIP)`、BM25 使用 `doc_id` 欄位，兩者都以 chunk_id 對應。這個設計取代了 2.x 依清單位置對齊的做法，背景見 [ADR-0005](adr/0005-chunk-id-index-and-database-source-of-truth.md)。

### 寫入順序

新增文件時先在鎖外計算所有片段的向量（可能需要數分鐘，期間檢索不必等待），接著在同一把鎖（`vector_store.lock`）內依序：

1. 確認片段所屬的文件仍存在，略過已刪除文件的片段與向量。
2. 寫入 `rag_chunks` 並 flush 取得 chunk_id（尚未 commit）。
3. 以 chunk_id 加入 FAISS。
4. commit 資料庫交易；失敗時從 FAISS 移除剛加入的向量並拋出例外。
5. 加入 BM25，最後把 FAISS 與中繼資料寫回檔案（先寫暫存檔再取代）。

檢索與寫入都持有同一把鎖，並在背景執行緒中執行，不會阻塞事件迴圈。寫入時持鎖後才確認片段所屬的文件仍在 `documents` 中；刪除文件則先刪除 `documents` 紀錄再移除片段，兩者搭配，確保與刪除同時進行的索引寫入不會把片段寫回知識庫。

### 啟動時校正

| 狀況 | 處理 |
|---|---|
| `rag_chunks` 中有所屬文件已不存在的片段 | 刪除孤立片段 |
| FAISS 有資料庫沒有的 chunk_id | 移除多餘向量 |
| 資料庫有 FAISS 沒有的 chunk_id | 補算缺少的向量 |
| BM25 的 chunk_id 與資料庫不一致 | 依資料庫重建 BM25 |
| BM25 的斷詞簽章（規則版本、主詞典雜湊、領域詞雜湊）與目前設定不同 | 依資料庫重建 BM25 |
| FAISS 是 2.x 依位置對齊的舊格式 | 改名為 `*.legacy.bak`，需執行一次完整重建 |
| FAISS 維度與目前嵌入模型不同 | 改名為 `*.mismatch.bak`，依資料庫補算全部向量 |
| `documents` 中 `is_processed` 不為 true 且沒有任何片段的文件（上傳後未完成索引） | 重新擷取（原始檔已遺失時改用資料庫內容）、切塊並建立索引，完成後標記為已處理；PDF 的空白或亂碼頁可能呼叫 PDF OCR 系統模型 |

### 三種重建方式

| 操作 | 範圍 | 會重新呼叫 LLM | 適用情境 |
|---|---|---|---|
| 重新啟動後端 | 只補齊差異，並補建未完成索引的文件 | 不生成摘要；補建的 PDF 可能呼叫 OCR 系統模型 | 索引檔遺失或與資料庫不一致 |
| `POST /api/admin/vector-store/reindex` | 以現有片段重算全部向量、重建 BM25 | 否 | 懷疑向量損毀 |
| `POST /api/documents/rebuild-index` | 逐份重新擷取、切塊與建立索引，並替沒有摘要的文件生成摘要 | 只對沒有摘要的文件 | 從 2.x 升級、修改切塊設定 |

刪除文件時只移除該文件的片段與向量；`DELETE /api/admin/vector-store/clear` 會清空全部片段與索引，但保留文件紀錄。

---

## 6. 混合檢索與重排

```mermaid
flowchart LR
    Query["查詢"] --> FAISS["FAISS 向量搜尋<br/>TOP_K 筆"]
    Query --> BM25["BM25<br/>jieba 詞＋漢字單字＋漢字雙字，以 OR 組合，TOP_K 筆"]
    Query --> Exact["精確比對<br/>網址／貼文 ID／日期／@帳號"]
    FAISS --> RRF["RRF 融合：Σ 1 / (RRF_K + 名次)<br/>取前 RERANK_TOP_K 筆"]
    BM25 --> RRF
    RRF --> Rerank["Cross-Encoder 重排<br/>RERANKER_MODEL（必要元件）"]
    Exact --> Rerank
    Rerank --> Gate{"重排機率 ≥ RERANK_RELEVANCE_THRESHOLD？<br/>網址、貼文 ID、日期精確比對者免檢"}
    Gate -->|通過| Top["取前 FINAL_K 筆"]
    Gate -->|全部未通過| None["回報「知識庫中查無相關資料」"]
```

1. **兩軌檢索**：向量（`BAAI/bge-small-zh-v1.5`，內積索引、向量經 L2 正規化）與 BM25（Whoosh BM25F）每次必跑，各取 `TOP_K` 筆。BM25 索引有三個欄位：jieba 詞、漢字單字與相鄰兩個漢字（只取漢字連續區段，不跨標點與英數字），查詢在三個欄位產生的詞項以 OR 組合、BM25F 合併計分；jieba 切錯詞（例如繁體的「大眾捷運系統」被切成「大眾捷／運系統」）時仍可由單字與雙字對上，雙字欄位讓字序相連的片段排在字散落的片段前面。詞欄位一律轉小寫（查 `mes` 對得到 `MES`），主詞典可用 `JIEBA_DICTIONARY` 替換，領域詞來自領域設定檔。依據與量測見 [ADR-0007](adr/0007-han-ngram-bm25-and-passage-level-evaluation.md)。
2. **RRF 融合**：分數 = Σ 1 / (`RRF_K` + 名次)，名次從 1 起算，不加權，以 chunk_id 辨識同一片段，取前 `RERANK_TOP_K` 筆。只有單一軌道找到的片段也能進入候選。
3. **精確比對**：查詢含網址、`/post/<ID>`、日期（`2025-10-22`、`2025年10月22日`）或 `@帳號` 時，另外掃描所有片段，比對結果依分數取前 `RERANK_TOP_K` 筆進入重排。網址、貼文 ID、日期的比對結果標記為 `pinned`：排在最前面，且不受相關性門檻限制；`@帳號` 的比對結果只加入候選，仍依分數排序並受門檻限制。
4. **重排**：Cross-Encoder 為每個候選輸出相關機率（模型本身沒有 sigmoid 輸出層時才補上 sigmoid；設定 `RERANKER_OPENVINO_DEVICE` 改用 OpenVINO 編譯的模型時一律補上 sigmoid，且必須同時設定 `RERANKER_OPENVINO_MAX_LENGTH`，否則啟動失敗）。排序用的混合分數 = `RERANK_WEIGHT` × 重排機率 + (1 − `RERANK_WEIGHT`) × 候選原分數，其中融合結果的原分數是 RRF 分數除以最高分，精確比對的原分數是比對分數。
5. **相關性門檻**：`RERANK_RELEVANCE_THRESHOLD` 只看重排機率；通過者取前 `FINAL_K` 筆。全部未通過時，`search_knowledge_base` 回傳「知識庫中查無相關資料」。
6. **限定文件**：指定 `target_document` 時，檢索前先找出 `source` 或 `original_filename` 包含該字串（不分大小寫）的片段，三種檢索都只在這些片段中進行：向量搜尋只對這些 chunk_id 計分（CPU 索引以 `IDSelectorBatch` 限定），BM25 以 `doc_id` 篩選，精確比對也只掃描這些片段，因此兩軌各在指定文件內取 `TOP_K` 筆。查不到時回報「指定文件《<target_document>》中查無相關資料」，不會改用全庫結果。
7. **失敗處理**：重排失敗時直接拋出例外，工具回傳錯誤代碼，不會把未過濾的片段交給模型。

**檢索評估**：`evaluator.py` 以與線上相同的流程（重排後套用門檻）計算文件層級的 hit@k、recall@k 與 MRR，反例（`"relevant_sources": []`）計算拒絕率；題目標註 `relevant_passages`（短原文片段）時，另計片段層級的 precision@k、nDCG@k、原文片段 recall@k、MRR 與候選召回（重排前的候選是否已包含正解，用來分辨召回與排序問題）。`scripts/evaluate_retrieval.py` 預設在索引副本上以唯讀模式執行，索引與資料庫不一致或斷詞簽章不符時拒絕執行；`--corpus` 改以指定目錄的文件在暫存 SQLite 與暫存索引上建立知識庫，不碰正式資料；`--relevance-thresholds` 對同一次重排結果比較多個門檻。內建基準為 `backend/eval/corpus/` 與 `backend/eval/corpus_golden.jsonl`。操作步驟見 [設定參考：校準相關性門檻](configuration.md#校準相關性門檻)。

---

## 7. Agentic RAG 研究迴圈

```mermaid
flowchart TB
    Q["使用者問題 + 附件 + 前文"] --> Build["組裝訊息<br/>系統提示、前文（移除舊 [n]）、附件文字與圖片"]
    Build --> Call["呼叫模型（附工具定義）"]
    Call --> HasTools{"模型要呼叫工具？"}
    HasTools -->|否| Answer["該次內容即最終答案<br/>以一個 token 事件送出"]
    HasTools -->|是| Check["ResearchSession 檢查<br/>聯網限制、網址來源"]
    Check --> Approve{"工具需要核准？"}
    Approve -->|否| Exec["執行工具"]
    Approve -->|是| Ask["approval_required<br/>等待使用者，最多 300 秒"]
    Ask -->|核准| Exec
    Ask -->|拒絕或逾時| Record
    Exec --> Record["配引用編號<br/>記錄網址來源與是否讀過知識庫"]
    Record --> Wrap["包進 &lt;untrusted_tool_result&gt;"]
    Wrap --> Call
    Answer --> Cite["解析 [n]<br/>sources_detail 只列被引用的來源"]
```

### 工具

| 工具 | 行為 |
|---|---|
| `search_knowledge_base` | 依第 6 節檢索，回傳 `chunk_id`、`source`、`chunk_index`、`score` 與片段全文；精確比對到網址、貼文 ID 或日期的片段不受 `top_k` 限制，最多回傳 `FINAL_K` 筆，其餘依 `top_k`（預設 3） |
| `filter_and_count_records` | 在執行緒中掃描所有片段，同一筆結構化記錄的分段依 `(document_id, record_index)` 合併後再篩選，每筆記錄只計一次；依日期（優先比對領域設定檔的日期欄位）、作者、關鍵字與文件精確篩選，回傳總數與前 `limit` 筆（預設 50，也是上限），每筆附 `label` 與 `links`；`date_range` 最多 200 字元，只比對其中明確寫出的日期或月份（區間不逐日展開），每個日期或月份產生 2 至 3 種寫法，合計最多 93 種（約 31 個日期） |
| `web_search` | 有 `OLLAMA_API_KEY` 時先用 Ollama Web Search，失敗或未設定時改用 DuckDuckGo；DuckDuckGo 結果頁逐筆解析標題、網址與摘要並略過廣告，解析不到任何結果時回傳錯誤，不回空清單 |
| `web_fetch` | 先檢查網域白名單與 SSRF；有 `OLLAMA_API_KEY` 時先用 Ollama Web Fetch，否則以安全抓取讀取 HTML，並在執行緒中以線性掃描轉成純文字（前 3500 字）。有 `<main>`、`role="main"` 或 `<article>` 時只取正文區塊並略過其中的 `nav`、`aside` 與導覽、側欄角色；沒有正文區塊時略過整頁的 `nav`、`aside`、`header`、`footer` 與對應的 ARIA 角色 |
| 自訂 API 工具 | 依工具設定組裝 HTTP 請求，見第 9 節；`requires_approval` 為 `true` 時先經使用者核准 |
| `mcp_<伺服器>_<工具>` | 透過 `tools/call` 呼叫 MCP 伺服器；伺服器的 `requires_approval` 為 `true` 時先經使用者核准 |
| `activate_skill` | 只在有啟用的 Agent Skills 時提供；工具說明列出技能名稱與描述（最多 8,000 字元），呼叫後重新讀取 `SKILL.md`，回傳去掉 frontmatter 的內文（包在 `<skill_content>`）與技能內的檔案清單，不讀取那些檔案；同一次提問重複啟用時只回覆已載入 |
| `read_skill_resource` | 讀取已啟用技能目錄內的單一 UTF-8 文字檔（只接受相對路徑，拒絕 `..` 與符號連結），每次最多 20,000 字元；讀取腳本不會執行它 |
| `run_skill_script` | 只在使用者看得到、開啟 `allow_scripts` 的技能時提供；以後端的 Python（`-I`）、`bash` 或 `node` 在技能目錄的暫存複本中執行腳本，環境變數同 `stdio` MCP，最多 60 秒，`stdout`、`stderr` 各最多 20,000 字元，同時最多 2 個；一律需要使用者核准，除非要執行的技能本身已啟用並在 `allowed-tools` 列出它 |
| `read_mcp_resource` | 只在啟用中的 MCP 伺服器有已探索的 resources 時提供；以 `resources/read` 讀取清單中的 uri，不在清單中的直接拒絕；核准依伺服器的 `requires_approval` |
| `get_mcp_prompt` | 只在啟用中的 MCP 伺服器有已探索的 prompts 時提供；以 `prompts/get` 取得清單中的 prompt；核准依伺服器的 `requires_approval` |
| `list_conversation_files`、`read_conversation_file`、`create_conversation_file`、`edit_conversation_file`、`delete_conversation_file` | 只在聊天中（有對話 id）提供，列出、讀取、建立、修改（另存新版本）與刪除這個對話的檔案；`delete_conversation_file` 一律需要使用者核准，見 [對話檔案](#對話檔案) |

每次工具結果放進模型脈絡前最多 20,000 字元，附件抽出的文字每個最多 50,000 字元，超過即截斷。模型給的參數不是物件時當成空物件；工具執行時拋出例外（例如 `top_k` 為 `null`）會轉成錯誤代碼交給模型，不會中斷整個回答。工具清單（含知識庫目錄、自訂 API 工具與 MCP 工具）在執行緒中組成。

### 提示詞與工具說明

送給模型的文字都集中在 `backend/app/prompts.py`，包括系統提示詞、工具與參數說明、各種包裝文字，以及文件摘要、OCR 與連線測試的提示詞。其他模組只引用這些常數，要調整措辭時只改這個檔案。

| 用途 | 常數 | 何時送出 |
|---|---|---|
| 研究助理的系統提示詞 | `SYSTEM_PROMPT` | 每次提問的第一則訊息，規則見下一節 |
| 現在時間 | `CURRENT_TIME`、`WEEKDAYS` | 加在最新一則使用者訊息的開頭，寫明現在的日期、星期、時刻（到分鐘）與時區，取自後端主機的本地時間；系統提示詞要求以它為準 |
| 技能規則 | `SKILL_RULES` | 呼叫者有可用的技能時接在系統提示詞後面，說明技能內容不能推翻引用與資料安全規則 |
| 使用者指定的技能 | `EXPLICIT_SKILL` | 訊息以 `/技能名稱` 開頭時，把技能內容接在系統提示詞最後 |
| 技能內容的包裝 | `SKILL_PATHS`、`SKILL_SCRIPTS_ALLOWED`、`SKILL_SCRIPTS_DISABLED` 等 | `activate_skill` 回傳的 `<skill_content>` 與 `read_skill_resource` 回傳的 `<skill_resource>` |
| 工具與參數說明 | `SEARCH_*`、`FILTER_*`、`WEB_*`、`MCP_*`、`SKILL_*` 等 | 每次呼叫模型時隨工具定義送出。`search_knowledge_base` 的說明是依現有文件組成的知識庫目錄（`KNOWLEDGE_BASE_CATALOG`），`top_k` 的上限取自 `FINAL_K` |
| 自訂 API 與 MCP 工具的說明 | `CUSTOM_API_TOOL`、`MCP_TOOL` | 寫成 `[自訂 API] <顯示名稱>：<說明>` 與 `[MCP 工具] <伺服器>／<工具>：<說明>` |
| 工具結果與附件的包裝 | `TOOL_RESULT_NOTICE`、`ATTACHMENT`、`ATTACHMENT_FILE`、`ATTACHMENT_QUESTION` 等 | 工具結果包在 `<untrusted_tool_result>` 內並加上一行提醒；附件文字以 `[附件：<檔名>]` 開頭（已存成對話檔案的附件為 `[附件 #<檔案編號>：<檔名>]`，沒有擷取到文字時仍附上這個標記），接在 `[使用者問題]` 之前 |
| 對話檔案工具的說明與結果 | `LIST_FILES`、`READ_FILE`、`CREATE_FILE`、`EDIT_FILE`、`DELETE_FILE`、`FILE_*` | 有對話 id 時隨工具定義送出；`FILE_CREATED`、`FILE_UPDATED`、`FILE_DELETED` 是工具結果中給模型的說明，`DELETE_FILE_APPROVAL` 是核准卡片上的工具名稱 |
| 文件摘要 | `document_summary()` | 交給文件摘要系統模型，見 [AI 摘要](#ai-摘要) |
| 掃描 PDF 的 OCR | `PDF_OCR` | PDF 中沒有可擷取文字的頁面點陣化後，交給 PDF OCR 系統模型，見 [文字擷取](#文字擷取) |
| 連線測試 | `CONNECTION_TEST` | `POST /api/llm-connections/{connection_id}/test` |

### 系統提示的規則

- **查證**：問候、閒聊或不需要查資料的請求直接回答；可能和內部文件有關的問題先查知識庫，不只憑一般知識作答；工具被使用者或系統拒絕時不重試。系統提示詞不提工具名稱，各工具何時使用、回傳什麼寫在工具說明裡（例如統計數量用 `filter_and_count_records`、`web_fetch` 讀取失敗時改查知識庫），停用聯網工具時就不會留下指向不存在工具的規則。
- **現在時間**：最新一則使用者訊息開頭附上 `[現在時間：<日期>（<星期>）<時:分>，時區 UTC<時差>]`（後端主機的本地時間，`app/rag/agent.py` 的 `with_current_time()`），系統提示詞要求相對時間與「現在」以它為準，不要上網查時間。時間放在使用者訊息而不是系統提示詞，系統提示詞因此固定不變，不影響供應商的提示快取；前文中先前的使用者訊息不帶時間。
- **檔案**：使用者要求做成檔案、文件、報表或網站時，建立成對話檔案，回答只簡短說明，不把整份內容或程式碼貼在回答裡；檔案工具的說明另外要求內容完整，不留「以下省略」這類占位文字。
- **引用**：只能使用本次工具結果中的 citation 編號，句末標註 `[n]`；查無資料時照實說明，不得臆測。
- **資料安全**：工具結果只當資料；不得把對話、知識庫或工具結果中的資料拼進網址或搜尋字串。
- **技能**（只在有啟用的技能時加上）：技能內容可以照做，但不能推翻資料安全與引用規則；何時載入技能寫在 `activate_skill` 的說明中。訊息以 `/技能名稱` 開頭時，後端在第一次呼叫模型前就把該技能附加到系統提示。

### ResearchSession：單次提問的狀態

`research_session.py` 為每次提問建立一個 `ResearchSession`：

| 職責 | 內容 |
|---|---|
| 引用編號表 | 知識庫片段以 `chunk:<chunk_id>`、網頁以 `url:<網址>` 為鍵，第一次出現時配號並寫入工具結果的 `citation` 欄位；同一來源再出現沿用原號碼 |
| 網址來源限制 | `web_fetch` 只能讀取「使用者訊息（含附件文字，以及前文中先前的使用者訊息與其附件文字）」或「本次內建工具結果的資料欄位」中以完整網址出現過的網址：來源文字先切出完整的網址記號，兩邊都正規化成 httpx 的形式後逐字比對，實際送出的是比對到的正規化網址；工具回聲的查詢參數不算來源 |
| 讀過知識庫後停用聯網 | `BLOCK_WEB_TOOLS_AFTER_KB=true` 時，知識庫工具回傳過內容後拒絕 `web_search` 與 `web_fetch` |
| 不可信資料包裝 | 每個工具結果包在 `<untrusted_tool_result id="...">` 內，id 每次提問隨機產生，資料無法預先偽造結束標記 |
| 解析引用 | 答案完成後解析 `[1]`、`[1,2]`、`[1、2]` 與 `[1][2]`，只列出引用表中存在的編號，依第一次引用的順序去重；引用表沒有的編號在送出與儲存前從內文移除（程式碼區塊與行內程式碼不動） |

自訂 API 與 MCP 工具的結果同樣包上不可信標記，但不列入網址來源與引用編號。

### 串流與儲存

- 每次工具呼叫前後推送 `step_start` / `step_end`，需要核准時中間穿插 `approval_required` / `approval_resolved`；對話檔案工具成功後在 `step_end` 之後推送 `file`；最終答案以 `token` 推送，完成後推送 `sources` 與 `done`。事件格式見 [API 參考 2.1](api.md#21-post-apichatsend)。
- 使用者訊息在串流開始前寫入資料庫，文件類附件同時存成對話檔案，附件抽出的文字在呼叫模型前寫回該訊息附件的 `content`；助理訊息在串流完成後才寫入，因此中途停止的回答不會被儲存，串流期間對話已被刪除時也不寫入（`done` 的 `message_id` 為 `null`）。串流期間資料庫連線先還給連線池，資料庫存取與附件解碼、解析都在執行緒中進行，不阻塞事件迴圈。
- 每位使用者同時最多 2 個回答串流（超過回傳 `429`）；送出前檢查 `model_name` 是否在可用模型清單內，以及附件與對話檔案的儲存量是否超過每位使用者 200 MiB。
- 前文由資料庫讀取最近 `CONVERSATION_HISTORY_MESSAGES` 則訊息，一律從使用者訊息開始，並移除先前回答中的 `[n]`（程式碼區塊與行內程式碼中的不動），避免模型沿用舊編號。先前使用者訊息的附件文字（附件的 `content`）一併帶入，從最新的訊息往前合計最多 50,000 字元（`MAX_HISTORY_ATTACHMENT_CHARS`）。

### 工具呼叫核准

`app/rag/tool_approval.py` 的 `ToolApprovalBroker` 讓發問的使用者在對話中決定有副作用的工具是否執行，設計背景見 [ADR-0006](adr/0006-tool-call-approval.md)：

1. Agent 準備執行工具時，`ResearchToolRegistry.approval_requirement()` 依名稱查詢對應的自訂 API 工具或 MCP 伺服器的 `requires_approval`；內建工具不需要核准，`run_skill_script` 與 `delete_conversation_file` 一律需要核准。同一次提問中已啟用的技能在 `allowed-tools` 列出的工具名稱記在 `ResearchSession.preapproved_tools`，這些工具略過核准，但 `delete_conversation_file` 不受影響；`run_skill_script` 例外，記在 `preapproved_script_skills`，只有執行列出它的那個技能自己的腳本時才略過核准。
2. 需要核准時，Broker 建立綁定發問者 `user_id` 的待核准項目（隨機 `approval_id`），串流送出 `approval_required`（含工具名稱、類別 `kind`、顯示名稱、參數，以及實際送出的位置 `target`：自訂 API 工具為 HTTP 方法與主機，MCP 為傳輸方式與主機或本機指令名稱，刪除對話檔案為檔案編號與檔名），Agent 暫停等待。前端依 `kind` 選擇卡片的說明文字，刪除對話檔案時寫明檔案會永久刪除。
3. 前端在該則回答中顯示確認卡片；使用者按下核准或拒絕後呼叫 `POST /api/chat/approvals/{approval_id}`。只有同一位使用者能處理，其他人或已處理、已逾時的項目回傳 `404`。
4. 串流送出 `approval_resolved`。核准時照常執行工具；拒絕或 300 秒逾時時不執行，Agent 收到「使用者未核准」的工具結果並改以已取得的資料回答。
5. 沒有可核准的使用者時（`approval_user_id` 為 `None`，例如非互動式呼叫），需要核准的工具一律不執行。

待核准項目只存在行程記憶體中；使用者中斷串流時，等待中的項目隨之取消。

### 對話檔案

研究助理可以在對話中建立、讀取、修改與刪除檔案，使用者在對話中下載。儲存、權限與額度在 `app/services/conversation_files.py`，各格式的產生、修改與讀取在 `app/services/file_builders.py`，工具定義與執行在 `app/rag/file_tools.py`。

| 格式 | 建立 | 修改 |
|---|---|---|
| `.md`、`.txt`、`.json`、`.html` | `content` 原樣寫入 UTF-8 | `edits` 取代文字，或以 `content` 整份重寫 |
| `.csv` | `sheets` 的第一張，以 UTF-8（含 BOM）寫入 | 同上，也可以用 `sheets` 整份重寫 |
| `.docx` | `content` 的 Markdown 以 markdown-it-py 解析（不接受原始 HTML），對應到 Word 的標題、項目與編號清單、表格、粗體、斜體、引言與程式碼 | `edits` 在段落與表格儲存格中取代文字並保留段落樣式；比對到的文字跨多個文字片段（run）時只合併這幾段，其他片段的粗體、斜體不受影響。也可以 `content` 整份重寫 |
| `.xlsx` | `sheets`，標題列粗體並凍結 | `cells` 修改儲存格（`value` 為 `null` 時清空），或以 `sheets` 整份重寫 |
| `.pptx` | `slides`，16:9 的「標題及內容」版面，`notes` 寫入演講者備忘稿 | `edits` 取代文字，或以 `slides` 整份重寫 |
| `.pdf` | `content` 的 Markdown 轉成 HTML 後以 PyMuPDF 的 `Story` 排版成 A4，中日韓文字用 PyMuPDF 內建字型，存檔前只保留用到的字形 | 只能以 `content` 整份重寫 |

- **版本**：`edit_conversation_file` 的結果一律另存成新檔，檔名為 `<來源檔名> v<n><副檔名>`（來源本身是研究助理產生的第 m 版時，先去掉它結尾的「 vm」；使用者上傳的「報告 v3.docx」改出來是「報告 v3 v2.docx」），`version` 為同一系列目前最大版本加 1，原檔不變。`edits` 的每個 `find` 必須在檔案中剛好出現一次，否則整次修改失敗，不產生新版本。舊版 `.doc`、`.xls`、`.ppt` 不能修改，要以 `create_conversation_file` 另存成新格式。
- **讀取**：`read_conversation_file` 每次最多回傳 15,000 字元，以 `offset` 與回傳的 `next_offset` 分段讀；`.xlsx` 列出每個儲存格的位址與值，其他格式沿用聊天附件的文字擷取。擷取出的文字依檔案快取最近 8 個（`FILE_TEXT_CACHE_ENTRIES`），分段讀同一個檔案時不會每次重新解析；讀取與修改和聊天附件共用「整個行程同時最多解析 2 個檔案」的上限（`MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS`）。讀取結果和其他工具結果一樣包在 `<untrusted_tool_result>` 內，檔案中的文字不會被當成指示。
- **試算表公式**：`.xlsx` 的字串一律以文字寫入，開頭為 `=` 的值不會變成公式；`.csv` 中以 `=`、`+`、`-`、`@`、Tab 或 `\r` 開頭的字串前面加上 `'`。
- **權限**：每個工具都在服務層檢查檔案屬於這個對話與這位使用者，不採信模型給的編號；`/api/chat/files/{file_id}` 只限檔案擁有者，其他人一律 `404`。刪除需要核准，所以檔案內容中的指示無法讓研究助理刪除檔案。
- **下載**：回應帶 `Content-Disposition: attachment`（非 ASCII 檔名以 RFC 5987 編碼）、`X-Content-Type-Options: nosniff` 與 `Cache-Control: private, no-store`；`Content-Type` 依副檔名從允許清單決定，`.html`、`.js`、`.css` 等一律以 `text/plain` 回傳，不會在瀏覽器執行。
- **上限**：單一檔案 15 MiB、每個對話 100 個檔案、工具輸入的內容 200,000 字元、試算表 200,000 個儲存格、簡報 100 頁、一次最多 50 個文字取代、PDF 最多 500 頁（見 [設定參考：資源上限](configuration.md#資源上限)）。產生與修改在執行緒中進行，存檔與額度檢查在同一把鎖內完成。
- **串流**：工具成功後送出 `file` 事件（`action` 為 `created`、`updated` 或 `deleted`），前端在該則回答下方顯示檔案卡片；這些事件也存進助理訊息的 `context_used.files`，重新載入對話時照樣顯示。

### 檔案與網頁預覽

對話檔案與知識庫文件都可以在介面上預覽，不必先下載。`app/services/file_preview.py` 把檔案轉成結構化的 JSON，前端的 `FilePreviewPanel` 依 `type` 以 React 元件排版，不會把檔案內容當成 HTML 插入頁面。預覽不是置中的對話框，而是側邊面板：聊天頁的面板在對話右側，對話仍可閱讀與輸入；知識庫頁的面板固定在畫面右側。面板有獨立的捲動區，左緣可以拖曳或用方向鍵調整寬度（拖曳時按 Esc 還原），可以放大到整個區域，按 Esc 或關閉鈕收起並把焦點還給原本的預覽按鈕；寬度小於 1100 像素時直接佔滿畫面；更寬時對話欄至少保留 360 像素，視窗變窄時面板會自動縮小（最小 320 像素）：

- **PDF**：只回傳頁數，前端捲動到某一頁時才以 PyMuPDF 把那一頁轉成 PNG（120 dpi，最長邊 2,000 像素，超大頁面也不會產生巨大的圖片）。
- **Word**：依段落與表格的順序列出標題、段落、清單項目與表格，保留粗體與斜體，超連結只取文字。
- **Excel 與 CSV**：每張工作表最多 500 列、50 欄，先去掉後面的空白列與空白欄再判斷是否截斷。
- **PowerPoint**：每頁的標題、文字（含層級）、表格、備忘稿與圖片數。
- **Markdown 與文字檔**：Markdown 以聊天回答相同的元件顯示；其他檔案以 `decode_text` 解碼，含有 NUL 字元或無法解碼時視為無法預覽。

Office 檔案先經過與附件相同的 zip 炸彈檢查，對話檔案用聊天附件的預算、知識庫文件用管理員上傳的預算；解析與 PDF 轉圖都在執行緒中進行，並與附件擷取、檔案工具共用 `extraction_slots`（同時最多 2 個）；檔案內容在取得名額之後才讀進記憶體，排隊中的請求不會先佔住一份完整檔案。對話檔案中最近 2 份 PDF 的內容留在記憶體（`FILE_PREVIEW_PDF_CACHE_ENTRIES`），逐頁轉圖時不必每頁都從資料庫重讀整個檔案。關閉預覽時，前端會取消還沒完成的頁面請求。知識庫文件的原始檔不在 `UPLOAD_DIR` 時，改顯示資料庫中擷取出的文字。

**研究助理做的網頁**：`create_conversation_file` 可以建立 `.html`。預覽時前端先以 `POST /api/chat/files/{file_id}/view-token` 取得以 `TOOL_SECRETS_KEY`（Fernet）加密、5 分鐘失效、只對這個檔案與使用者有效的權杖，再把 `<iframe sandbox="allow-scripts">` 指向 `GET /api/chat/files/{file_id}/view?token=…`。這個回應的 CSP 以 `sandbox allow-scripts` 讓網頁落在 opaque origin，讀不到 AskMiao 的 Cookie 與 `localStorage`；`default-src 'none'` 只允許內嵌的腳本與樣式、`data:` 圖片與字型，`fetch`、表單與外部資源一律被擋；`frame-ancestors` 只允許 AskMiao 自己與 `ALLOWED_ORIGINS` 嵌入。正式環境的前端 CSP 有 `frame-src 'self'`（另加 `VITE_API_BASE`／`VITE_API_URL` 的來源），網頁就算以腳本把 iframe 導向外部網址也會被瀏覽器擋下，無法把內容送出去。不以 `srcdoc` 或 `blob:` 嵌入，因為它們會繼承前端的 CSP，網頁的內嵌腳本無法執行。

**網址預覽卡**：回答的參考來源中，網頁來源（`web_search`、`web_fetch`）改為按一下先開啟預覽卡，顯示標題、網站名稱與摘要，再由卡片上的「開啟網頁」在新分頁開啟。預覽卡只使用 `sources_detail` 已有的資料，不會為了預覽另外連線到該網站。

---

## 8. LLM 呼叫層

`app/core/llm_client.py` 以 OpenAI 的訊息格式（`messages`、`tools`、`tool_calls`）作為內部標準，再轉換成各家的格式。

| 供應商 | 端點 | 轉換重點 |
|---|---|---|
| Microsoft Foundry | `{API 位址}/openai/v1/responses`（`gpt-`、`o3`、`o4` 開頭，但 `gpt-oss`、`o3-mini` 除外）或 `/openai/v1/chat/completions`（其他模型，例如 `o1`、`gpt-oss`、`o3-mini`）；`claude-` 開頭的部署走 `{API 位址}/anthropic` | 同時帶 `api-key` 與 `Authorization` 標頭；模型名稱即部署名稱 |
| OpenAI | `{API 位址}/chat/completions`；`gpt-6*` 走 `{API 位址}/responses` | 原生格式 |
| Google Gemini | `{API 位址}/v1beta/openai/chat/completions` | 使用 OpenAI 相容端點 |
| Anthropic Claude | 官方 `anthropic` SDK | system 訊息抽出；連續的工具結果併成一則 `tool_result`；工具呼叫回合原樣送回 `response.content`（含 thinking 區塊）；需要連線設定的輸出 token 上限；拒答（`refusal`）與工具參數被截斷時回報錯誤 |
| Ollama | `{API 位址}/api/chat` | 圖片轉為 `images` 欄位；工具呼叫參數轉為物件；可設定 `OLLAMA_TEMPERATURE`、`OLLAMA_NUM_PREDICT`、`OLLAMA_NUM_CTX`（套用到所有 Ollama 連線） |
| vLLM | `{API 位址}/chat/completions` | OpenAI 相容格式；`reasoning_effort` 直接傳送，輸出 token 上限以 `max_completion_tokens` 送出，串流以 `stream_options.include_usage` 取得用量；回應的 `reasoning` 隨工具呼叫回合原樣送回；伺服器沒有開啟工具呼叫時回報明確的錯誤 |

- **路由**：每次呼叫都使用一條 API 連線：聊天是使用者選的個人或共用連線，文件摘要與 PDF OCR 是管理員指定的系統模型。端點依連線的供應商與模型名稱決定，完整規則見 [設定參考：供應商路由](configuration.md#供應商路由)；`.env` 不設定任何模型供應商。
- **推理程度**：`reasoning_effort` 依供應商對應後傳給模型（對應規則見 [API 參考](api.md)）；走 Chat Completions 的 `gpt-5.x` 模型（名稱含 `gpt-5.`）帶工具時一律送 `none`，原始的 `gpt-5`、`gpt-5-mini`、`gpt-5-nano` 不接受 `none`、`xhigh`、`max`，選 `none` 時改送 `minimal`，選 `xhigh`、`max` 時改送 `high`，其他情況送使用者選擇的程度；`gpt-6*` 與 Foundry 上走 Responses API 的模型（見上表）以 Responses API 同時支援工具與推理。
- **兩種呼叫**：`chat_completion` 用在研究迴圈的每一輪（非串流，回傳 `content` 與 `tool_calls`）；`stream_completion` 只在需要重新生成最終答案時使用，Claude 串流時以 `tool_choice: none` 避免再觸發工具。
- **逾時**：共用的 httpx 用戶端以 `LLM_TIMEOUT` 為逾時，等待連線池名額另以 15 秒為上限（池被占滿時很快失敗），每次請求各自設定的逾時也保留這個上限。
- **日誌**：每次呼叫在開始與結束時各寫一行，結束的那一行記下耗時、成功或失敗與供應商回傳的 token 用量；逾時時記下例外類別（`ConnectTimeout`、`ReadTimeout`、`PoolTimeout` 分別代表連線、等待回應、等待連線池名額）與當次的逾時秒數，串流另記第一段文字抵達的時間。欄位見 [日誌與請求追蹤](#日誌與請求追蹤)。
- **影像輸入**：只接受內嵌的 `data:` URL，遠端圖片網址一律拒絕，避免模型供應商代為擷取使用者指定的任意位址。聊天附件只有 PNG、JPEG、GIF、WebP 以圖片交給模型；SVG 以文字讀取；其他圖片格式（例如 BMP、TIFF）不讀取，並告知模型請使用者改用 PNG、JPEG、GIF 或 WebP。
- **模型清單**：建立連線時可「從 API 取得模型」，依供應商查詢模型清單，逾時為 `LLM_TAGS_TIMEOUT`；送出訊息時指定的模型必須在該連線的模型清單內。

---

## 9. 外部工具與 MCP

```mermaid
flowchart TB
    subgraph Registry ["ResearchToolRegistry.get_tool_definitions()"]
        Builtin["內建工具"]
        DynamicApi["啟用中的自訂 API 工具（custom_api_tools）"]
        DynamicMcp["啟用中 MCP 伺服器的工具快取（discovered_tools）"]
    end

    subgraph ImportFlow ["建立自訂 API 工具"]
        Spec["Swagger 2.0、OpenAPI 3.0～3.2、Arazzo（內容或網址）"] --> Overlay["套用 Overlay（RFC 9535 JSONPath）"]
        Overlay --> Parser["OpenApiParser／parse_arazzo<br/>外部 $ref、schema 正規化"]
        Parser --> Select["前端勾選端點"]
        Select --> Import["POST /api/api-tools/import"]
        Manual["手動表單"] --> DB[(custom_api_tools)]
        Import --> DB
    end

    subgraph McpFlow ["接入 MCP 伺服器"]
        Server["伺服器設定（stdio / HTTP）"] --> Discover["initialize + tools/list<br/>resources/list、prompts/list"]
        Discover --> McpDB[(mcp_servers)]
    end

    DB --> DynamicApi
    McpDB --> DynamicMcp
    Builtin & DynamicApi & DynamicMcp --> Agent["Agent 工具集"]
    Agent --> Gate{"requires_approval？"}
    Gate -->|是| Ask["使用者在對話中核准"]
    Gate -->|否| Exec{"execute_tool(name, arguments)"}
    Ask -->|核准| Exec
    Exec -->|內建| Internal["內部實作"]
    Exec -->|mcp_ 前綴| McpCall["McpManager.execute_mcp_tool（tools/call）"]
    Exec -->|其他名稱| Dispatch{"execute_api_tool"}
    Dispatch -->|一般工具| Http["execute_http_api_tool（httpx + SSRFSafeTransport）"]
    Dispatch -->|workflow_definition| Workflow["run_workflow（Arazzo 步驟依序呼叫 execute_http_request）"]
```

1. **動態載入**：每次組裝工具定義時查詢資料庫，工具異動即時生效。MCP 工具使用探索時寫入的快取，不必每次連線。
2. **命名**：自訂 API 工具以 `name` 註冊（取自 `operationId` 或方法與路徑，只含英數與底線）；MCP 工具為 `mcp_<伺服器>_<工具>`，名稱中的非英數字元換成底線並轉小寫，`execute_tool` 依此前綴路由。
3. **HTTP 執行器**：呼叫端（模型）只能使用 `parameters_schema` 宣告的參數，`request_body` 有宣告欄位的 `request_body_schema` 且 `additionalProperties` 不是 `true` 時一併檢查其中的欄位，未宣告的參數不送出，直接回傳 `400`。接著依 `param_styles`（`app/services/api_tool_request.py`）以 OpenAPI 的 `style`／`explode` 序列化路徑（`simple`、`label`、`matrix`，百分比編碼並拒絕 `.`、`..`，代入後的 scheme、主機與埠號必須與設定相同）、查詢字串（`form`、`spaceDelimited`、`pipeDelimited`、`deepObject`、3.2 的整段 `querystring`）、標頭與 Cookie，注入認證（Bearer、API Key 標頭／查詢／Cookie、Basic，或以 OAuth2 client credentials 向 `token_url` 取得並快取的 Bearer 權杖，API 回傳 `401` 時重新取得並重試一次）；參數不能設定認證、`Content-Type`、`Cookie` 等標頭。主體依 `body_content_type` 編碼為 JSON 家族、表單、`multipart/form-data`、XML 或文字，並保留宣告的媒體型別。工具網址中的查詢參數由管理員固定，呼叫端提供同名參數時回傳 `400`；查詢字串一律自行組好，不依賴 httpx 對既有查詢字串的處理。請求經 `SSRFSafeTransport` 在第一個請求與每次轉址前重新做 SSRF 驗證、把連線固定在驗證過的 IP；轉址由 `send_following_redirects` 手動跟隨（最多 5 次），轉址回應的本文不讀取；`GET`、`HEAD`、`OPTIONS` 可跟隨跨來源轉址，此時移除管理員設定的標頭與認證標頭，其他會改變狀態的方法只接受同一來源的轉址，轉址到其他來源時中止，請求主體不會送往其他網域。整個呼叫（含轉址與逐段讀取）以工具的 `timeout` 為總時限，逾時回傳 `504`；回應本文上限 1 MiB。結果與網址中出現的憑證值換成 `[已遮蔽]`，工具網址中固定的查詢參數值（可能是寫在網址裡的金鑰）也不出現在回傳的網址中。
4. **MCP 協定與傳輸**：用戶端以 MCP `2026-07-28` 為主（無狀態，每個請求的 `_meta` 帶 `io.modelcontextprotocol/protocolVersion`、`clientInfo`、`clientCapabilities`，不宣告任何 client capability），並相容以 `initialize` 交握的舊版（`2025-11-25`、`2025-06-18`、`2025-03-26`、`2024-11-05`）。`McpStdioClient` 先送 `server/discover` 探測：收到 `DiscoverResult` 就用新版，收到 `UnsupportedProtocolVersionError`（`-32022`）就改用對方列出的版本，其他錯誤或 `MCP_DISCOVER_PROBE_TIMEOUT_SECONDS`（5 秒）內沒有回應就退回 `initialize`；單行訊息上限 4 MiB。`McpHttpClient` 以 Streamable HTTP 的 POST 先送新版的 `server/discover`，每個請求帶 `MCP-Protocol-Version`、`Mcp-Method`，`tools/call`、`resources/read`、`prompts/get` 另帶 `Mcp-Name`，工具 `inputSchema` 中標了 `x-mcp-header` 的參數以 `Mcp-Param-{名稱}` 標頭送出（非 ASCII、控制字元或前後空白以 `=?base64?…?=` 編碼），伺服器回 `HeaderMismatch`（`-32020`）時重新讀取工具清單再試一次；收到 `400`、`404`、`405` 且本文不是新版 JSON-RPC 錯誤時視為舊版伺服器，改走 `initialize`（帶工作階段，收到 `404` 時重新交握一次，關閉時以 `DELETE` 結束），`initialize` 也收到 `400`、`404`、`405` 時改用 `McpLegacySseClient` 的舊版 HTTP+SSE（GET 開啟串流、等待同一來源的 `endpoint` 事件後 POST，串流最多 4 MiB）。探索時協商到的版本存入 `mcp_servers.protocol_version`，呼叫工具時沿用（新版直接送出請求、舊版直接交握），沿用的版本失效時重新協商並重試一次。回應的 `resultType` 為 `input_required`（伺服器要求 elicitation、sampling 或 roots）時當作失敗，未知的 `resultType` 也視為無效。兩種傳輸同樣經 `SSRFSafeTransport` 逐跳驗證並固定 IP，單次回應上限 4 MiB；HTTP 轉址由 `send_following_redirects` 手動跟隨，只接受同一來源（最多 5 次），管理員設定的標頭與 JSON-RPC 本文不會送往其他網域；每次請求以伺服器的逾時設定為總時限，每次呼叫都重新建立連線。工具失敗只回傳錯誤代碼（stderr、JSON-RPC 錯誤與 SSRF 拒絕原因只寫入日誌），啟動失敗的訊息只含指令名稱、不含參數。
5. **子行程隔離**：`build_stdio_env()` 只繼承 MCP 官方 SDK 預設清單中的系統變數，略過以 `()` 開頭的 shell 函式定義，再加上伺服器的 `env_vars`；後端的資料庫連線與模型金鑰不會傳給第三方 MCP 伺服器。子行程的工作目錄是每次新建的空暫存目錄，後端目錄下的 `.env` 與 `keys/` 不在它的相對路徑範圍內（子行程仍以後端的系統帳號執行，能讀取該帳號可讀的檔案）。每個子行程自成一個行程群組，關閉時連同 `npx`、`uvx` 啟動的孫行程整棵終止；同時最多 4 個子行程，等待空位的時間不超過該伺服器的逾時設定。stderr 持續讀出以免管線寫滿卡住，只保留最後 2 KiB 供日誌診斷。
6. **內建範本**：只提供 `mcp_time` 與 `mcp_filesystem`。檔案系統範本釘選 `@modelcontextprotocol/server-filesystem@2026.8.31`，根目錄是專屬的 `backend/mcp_filesystem_sandbox`（絕對路徑，與 `DATA_DIR` 分開，因為其中的 BM25 索引由 Whoosh 以 pickle 載入）。網頁擷取類範本已移除，因為 `stdio` 子行程的出站連線不受 `web_fetch` 的 SSRF、網域白名單與網址來源限制。
7. **呼叫前核准**：自訂 API 工具與 MCP 伺服器各有 `requires_approval` 旗標；Agent 呼叫這類工具前須由發問的使用者核准，見第 7 節「工具呼叫核准」與 [ADR-0006](adr/0006-tool-call-approval.md)。
8. **管理權限**：工具由所有使用者的 Agent 共用，`stdio` 模式還會在主機上執行指令，因此 `/api/api-tools` 與 `/api/mcp` 的所有端點（含查詢）只開放管理員；例外是供 OAuth 授權伺服器連入的 `GET /api/mcp/oauth/callback` 與 `GET /api/mcp/oauth/client-metadata.json`，不需登入（見第 12 點）。一般使用者只能在對話中讓 Agent 使用已啟用的工具。詳見 [ADR-0002](adr/0002-external-tools-and-outbound-safety.md) 與 [ADR-0004](adr/0004-tool-admin-permissions-and-subprocess-isolation.md)。
9. **憑證加密與遮蔽**：`app/core/tool_secrets.py` 在寫入資料庫前以 `TOOL_SECRETS_KEY`（Fernet）加密自訂 API 工具的 `headers`、`auth_config` 與 MCP 伺服器的 `env_vars`、`headers`，執行工具時才解密；個人與共用 LLM API 連線的金鑰也以同一把金鑰加密（`app/services/llm_connections.py`）。管理 API 的回應以 `••••••••` 取代秘密值：`accept`、`accept-encoding`、`accept-language`、`cache-control`、`content-type`、`user-agent` 以外的標頭，`auth_config` 的 `token`、`key_value`、`password`、`client_secret`，以及 MCP 的所有環境變數與 OAuth `client_secret`；`key_name`、`username` 等設定照常顯示，MCP 的 OAuth 權杖不出現在回應中。更新時仍為遮蔽字樣的欄位沿用已儲存的值，沒有已儲存的值時回傳 `400`。無法以目前的金鑰解密時（例如更換了 `TOOL_SECRETS_KEY`），回應帶 `credentials_unreadable: true`，由管理員重新輸入。
10. **規格解析**：`openapi_documents.py` 載入文件（拒絕 YAML 別名：先以事件串流檢查，沒有別名才以 `yaml.safe_load` 載入）並經 SSRF 驗證下載外部 `$ref` 文件（最多 20 份、合計 30 MB），建立 `$id`／`$anchor` 索引；`openapi_overlay.py` 以 `jsonpath.py`（RFC 9535）套用 Overlay；`openapi_parser.py` 判斷版本（Swagger 2.0、OpenAPI 3.0～3.2，其他版本拒絕）、合併路徑與操作層級的伺服器與參數、展開路徑項目 `$ref`、3.2 的 `query` 與 `additionalOperations`，並把 `security` 轉成 `auth_type` 與不含憑證的 `auth_config`；`openapi_schema.py` 把 `allOf`、`oneOf`／`anyOf`（含 `discriminator`）、JSON Schema 2020-12 的 `type` 陣列、`const`、`prefixItems`、`$defs` 正規化成各家模型都接受的參數 schema，循環參照、超過 200 個參照（`MAX_OPENAPI_SCHEMA_REFS`）或 32 層的結構改以只含說明的物件取代。無法完整匯入的部分列在回應的 `warnings`。`POST /api/api-tools/parse-spec` 的回應不含原始規格。
11. **MCP resources 與 prompts**：探索時依伺服器宣告的 capability 讀取 `resources/list`、`prompts/list`（失敗只寫入日誌），各最多 200 項存入 `discovered_resources`、`discovered_prompts`。Agent 的 `read_mcp_resource`、`get_mcp_prompt` 說明列出這些項目（`MAX_MCP_CATALOG_CHARS`），執行前先比對清單，不在清單中的 uri 或 prompt 不會送到伺服器。
12. **MCP 遠端 OAuth**（`app/services/mcp_oauth.py`）：依 MCP 授權規格 `2026-07-28`。先以不帶權杖的 `server/discover` 取得 `401` 的 `WWW-Authenticate`，依其中的 `resource_metadata` 或 `/.well-known/oauth-protected-resource`（先路徑、後根目錄）找到授權伺服器，再依序嘗試 OAuth 授權伺服器中繼資料與 OpenID Connect 探索；中繼資料的 `issuer` 必須與用來組網址的 issuer 完全相同，`code_challenge_methods_supported` 必須含 `S256`，授權伺服器端點必須是 HTTPS（loopback 除外），否則拒絕。用戶端依序採用管理員填入的 client、Client ID Metadata Document（授權伺服器宣告 `client_id_metadata_document_supported` 且 AskMiao 以 HTTPS 提供時，`client_id` 是 `GET /api/mcp/oauth/client-metadata.json` 的網址）、動態註冊（帶 `application_type`：回呼網址是 localhost 時為 `native`，否則 `web`）；註冊得到的 client 綁定核發它的 issuer，授權伺服器變更時重新註冊並清除權杖，管理員填入的 client 則要求管理員更新。scope 依序取管理員設定、上次授權要求的 scope、`WWW-Authenticate` 的 `scope`、`scopes_supported`；連線收到 `403` 且 `error="insufficient_scope"` 時記下所需 scope，下次授權時合併進去（step-up）。以授權碼 + PKCE（S256）與 `resource` 取得權杖，回呼網址必須是 HTTPS 或 localhost。一次性的 `state` 連同預期的 issuer 存在行程記憶體中 10 分鐘；回呼 `GET /api/mcp/oauth/callback` 不需登入，先依 RFC 9207 比對 `iss`（授權伺服器宣告支援時必須有 `iss`，有 `iss` 時一律逐字比對），不符時拒絕、不換取權杖。權杖加密存入 `oauth_tokens`，HTTP 請求帶 Bearer，快到期或連線收到 `401` 時以 refresh token 換新。OAuth 端點的請求共用 `app/services/oauth_client.py`（SSRF 驗證、只跟隨同一來源的轉址、15 秒、256 KiB），自訂 API 工具的 client credentials 也使用它。
13. **Arazzo 工作流程**（`app/services/arazzo.py`）：匯入時下載 `sourceDescriptions` 的 OpenAPI 來源，把每個步驟的 `operationId`／`operationPath` 解析成操作，連同工作流程存入 `workflow_definition`。執行時依序呼叫步驟，以執行期運算式代入參數與主體，依 `successCriteria`（simple、regex、JSONPath）與 `onSuccess`／`onFailure`（end、goto、retry）決定下一步；每一步都走 `execute_http_request`，與一般工具同樣經 SSRF 驗證與憑證遮蔽。一次最多 50 個步驟、300 秒，避免 `goto` 或 `retry` 形成迴圈。
14. **MCP 工具定義與結果**（`app/services/mcp_tools.py`）：探索時只保留名稱符合 `[A-Za-z0-9_.-]{1,128}` 的工具；`inputSchema` 以 `openapi_schema.py` 正規化成各家模型都接受的參數 schema（`$schema` 為 draft-04／06／07 時依舊版語意，其餘當 2020-12），只解析工具定義內的 `$ref`，指向網路或其他文件的 `$ref` 不下載、該工具直接略過；HTTP 傳輸另檢查 `x-mcp-header`（只能放在從根結構只經 `properties` 到達的 string、integer、boolean 參數，名稱是 HTTP 欄位名稱且不分大小寫不重複），不合規則的工具略過並寫入日誌。工具的 `title` 用在說明與管理頁；`annotations` 依規格視為不可信的宣告，只在管理頁標成「唯讀」「可能變更資料」「會連到外部」，不影響呼叫前核准。工具結果交給模型前，圖片、音訊與內嵌資源的二進位內容換成說明文字，`resource_link` 只保留 uri、名稱與說明；有 `structuredContent` 時一併提供，與它相同的 JSON 文字區塊略過；`outputSchema` 不做驗證。內建的 `mcp_time` 範本同時支援兩個世代，宣告四個工具註記。

---

## 10. 認證與授權

```mermaid
sequenceDiagram
    autonumber
    actor User as 使用者（前端）
    participant API as FastAPI
    participant BL as 撤銷名單（記憶體）
    participant DB as 資料庫

    User->>API: POST /api/auth/login（使用者名稱或電子郵件、密碼）
    API->>API: 登入節流：識別或來源位址暫停中時直接回傳 429
    API->>DB: 查詢帳號並以 Argon2 驗證密碼（失敗時計入節流）
    API-->>User: 存取權杖（JSON）＋ 重新整理權杖（HttpOnly Cookie）
    User->>API: 呼叫 API（Authorization: Bearer）
    API->>BL: 檢查權杖是否已撤銷
    API->>API: 驗證 RS256 簽章、到期時間與權杖類型
    API->>DB: 依 sub 讀取帳號：存在、啟用、權杖簽發不早於 tokens_valid_after
    API-->>User: 回應（身分與權限取自資料庫）
    Note over User,API: 存取權杖剩不到 5 分鐘或收到 401 時，前端自動呼叫 /api/auth/refresh
    User->>API: POST /api/auth/refresh（Cookie）
    API->>DB: 同樣依 sub 確認帳號存在、啟用且權杖不早於 tokens_valid_after
    API->>BL: 撤銷用過的重新整理權杖
    API-->>User: 新的存取權杖＋重設 Cookie
    User->>API: POST /api/auth/logout（只驗簽章，存取權杖過期也可）
    API->>BL: 兩個權杖寫入撤銷名單直到各自到期
    API-->>User: 刪除 Cookie
```

| 項目 | 設計 |
|---|---|
| 簽章 | 一律 RSA-2048 RS256；金鑰對在 `backend/keys/`，首次啟動自動產生。金鑰無法載入或產生時，任何環境都拒絕啟動，沒有共用金鑰的退路 |
| 存取權杖 | 有效 `ACCESS_TOKEN_EXPIRE_MINUTES` 分鐘，內含 `sub`、`username`、`email`、`role`、`is_admin`、`iat` 與 `type: access` |
| 帳號綁定 | 每次請求由 `resolve_token_user()` 依 `sub` 讀取帳號：不存在、已停用，或 `iat` 早於帳號的 `tokens_valid_after`（建立帳號時等於 `created_at`，防止帳號刪除後 id 被重用；變更密碼時更新為當下；`iat` 保留微秒，同一秒內稍早簽發的權杖同樣無效）時回傳 `401`；`username`、`role`、`is_admin` 取自資料庫而非權杖 |
| 重新整理權杖 | 有效 `REFRESH_TOKEN_EXPIRE_DAYS` 天，只含 `sub` 與 `type: refresh`，存在 HttpOnly Cookie（路徑 `/api/auth`，`Secure` 由必填的 `COOKIE_SECURE` 決定，不再依 `ENVIRONMENT` 推導，`SameSite` 預設 `lax`）；只能使用一次，換發時撤銷舊權杖並重設 Cookie |
| 密碼 | Argon2 雜湊；舊的 bcrypt 雜湊仍可驗證，登入成功時自動改存 Argon2。註冊與改密碼要求 8 至 256 字元並包含大小寫字母與數字；雜湊與驗證在執行緒中進行，同時最多 4 個 |
| 變更密碼 | `POST /api/auth/change-password` 把 `tokens_valid_after` 更新為當下並清除重新整理權杖 Cookie：該帳號先前簽發的權杖（含其他裝置、可能已外洩者與目前這一個）全部失效，前端隨即清除登入狀態並導回登入頁 |
| 登入節流 | `app/core/login_throttle.py` 對登入識別（不分大小寫、忽略前後空白）與來源位址分別計數：`LOGIN_FAILURE_WINDOW_SECONDS` 內失敗達 `LOGIN_MAX_FAILURES_PER_ACCOUNT` 或 `LOGIN_MAX_FAILURES_PER_ADDRESS` 次，該識別或位址的登入暫停 `LOGIN_LOCKOUT_SECONDS` 秒，期間不驗證密碼，直接回傳 `429` 與 `Retry-After`（`LOGIN_THROTTLED` 寫入安全日誌）。拿到密碼雜湊名額後會再檢查一次是否鎖定，失敗也在釋放名額前記錄，同時送出的大量請求在鎖定後最多只有已在驗證中的 4 個會完成。不存在或已停用的帳號同樣計數，並對假雜湊驗一次密碼，回應內容與時間都與存在的帳號相同；登入成功只清除該識別的紀錄。計數在行程記憶體中，追蹤的識別與位址各最多 10,000 個，最久沒有新失敗者先淘汰 |
| 註冊 | `ALLOW_REGISTRATION=false` 時 `POST /api/auth/register` 回傳 `403` 並寫入安全日誌（`REGISTER_REJECTED`）；`GET /api/auth/registration`（不需登入）回傳 `{"enabled": bool}`，前端據此顯示或隱藏註冊入口。帳號（含第一位管理員）由 `backend/scripts/create_user.py` 建立，套用與註冊相同的規則，`--admin` 建立管理員，密碼以互動方式輸入；管理員也可以在管理後台以 `POST /api/admin/users` 建立帳號（安全日誌 `ADMIN_USER_CREATED`） |
| 授權 | 管理員端點依資料庫中該帳號的 `is_admin` 判斷，變更後下一個請求就生效。`GET /api/admin/users` 與 `PUT /api/admin/users/{user_id}` 的回應只含 `UserProfile` 欄位，不含密碼雜湊；變更帳號權限、狀態與刪除帳號時寫入安全日誌（`ADMIN_USER_UPDATED`、`ADMIN_USER_DELETED`）。管理員以 `PUT /api/admin/users/{user_id}/password` 重設其他帳號的密碼（自己的密碼仍要在個人資料變更），同樣把 `tokens_valid_after` 更新為當下，並寫入安全日誌（`ADMIN_PASSWORD_RESET`） |
| 撤銷 | 登出時把權杖的 SHA-256 雜湊（不是權杖本身）寫入行程內撤銷名單，保留到權杖到期，並自動清理過期項目；名單最多 100,000 筆，滿了先淘汰最早到期者。登出只驗存取權杖的簽章，存取權杖過期時仍能撤銷重新整理權杖並清除 Cookie，但仍要求 `Authorization` 標頭，跨站表單無法觸發登出 |

**已知限制**：撤銷名單與登入失敗計數在後端重啟後清空，多行程部署時也不共享。詳見 [API 參考：已知限制](api.md#11-已知限制)。

---

## 11. 安全設計

### 11.1 日誌雙層遮蔽

`app/core/security_logging.py` 在寫入安全日誌前套用兩道遮罩：

1. **物件遞迴遮罩（`sanitize_sensitive_data`）**：走訪字典、清單與 tuple，鍵名（不分大小寫）包含 `password`、`pass`、`passwd`、`secret`、`token`、`api_key`、`apikey`、`authorization`、`auth`、`cred`、`credentials`、`private_key`、`ssn`、`card_number`、`credit_card`、`cookie` 等字樣的值一律換成 `[REDACTED]`。
2. **字串正規表示式遮罩**：序列化成 JSON 後再掃描一次，遮蔽殘留的敏感欄位。

安全日誌的單一字串欄位（例如匿名請求可控的帳號名稱、User-Agent）最多保留 200 字元；安全事件只寫入 `security.log`，不再重複寫進 `app.log`，兩者都以 10 MiB × 5 份輪替。`httpx` 與 `httpcore` 的日誌層級固定為 `WARNING`，完整請求網址（可能含查詢字串型 API 金鑰）不會寫入日誌。

### 11.2 錯誤代碼（CWE-209 / CWE-497）

`app/core/error_response.py`：

- `log_and_get_error_id()`：把完整例外與堆疊寫入伺服器日誌，回傳 12 碼隨機代碼。
- `format_client_error()` / `build_error_payload()`：組出不含內部細節的訊息與 `error_id`；`build_error_payload()` 另附當下請求的 `request_id`，日誌中同一行也帶著這個 ID（見 [日誌與請求追蹤](#日誌與請求追蹤)）。
- `SafeClientError`：標記「訊息只描述使用者輸入本身」的驗證錯誤，可原樣回傳，讓使用者知道如何修正。

- `format_ssrf_rejection()`：SSRF 拒絕原因可能含伺服器端解析出的內網 IP 或轉址目標，對外只說明遭拒並附錯誤代碼（`parse-spec`、自訂 API 工具與 `web_fetch` 都適用）。

REST 回應、SSE 的 `error` 事件，以及研究迴圈中以 `token` 回報的錯誤都使用錯誤代碼。

### 11.3 SSRF 防護

所有由使用者輸入驅動的出站請求（OpenAPI 規格網址、`web_fetch`、自訂 API 工具、MCP HTTP 傳輸，以及非管理員使用者的個人 LLM API 連線）都經過 `app/core/ssrf_protection.py`：

```mermaid
flowchart LR
    Input["網址"] --> Scheme{"協定<br/>http / https"}
    Scheme --> Port{"連接埠<br/>危險埠清單"}
    Port --> Host{"主機名稱<br/>localhost、.internal 等"}
    Host --> Resolve["DNS 解析取得所有 IP<br/>依來源使用專用執行緒池，5 秒逾時"]
    Resolve --> IPCheck{"IP 範圍"}
    IPCheck -->|私有、迴環、連結本地、保留、雲端中繼資料| Block["拒絕（SSRFProtectionError）"]
    IPCheck -->|公開位址| Allow["連線固定到驗證過的 IP 送出；每次轉址重新驗證"]
```

| 類別 | 封鎖清單 |
|---|---|
| IPv4 | `0.0.0.0/8`、`10.0.0.0/8`、`100.64.0.0/10`、`127.0.0.0/8`、`169.254.0.0/16`（含雲端中繼資料 `169.254.169.254`）、`172.16.0.0/12`、`192.0.0.0/24`、`192.0.2.0/24`、`192.88.99.0/24`、`192.168.0.0/16`、`198.18.0.0/15`、`198.51.100.0/24`、`203.0.113.0/24`、`224.0.0.0/4`、`240.0.0.0/4`、`255.255.255.255/32` |
| IPv6 | `::/128`、`::1/128`、`::ffff:0:0/96`（另會拆出內嵌的 IPv4 再檢查）、`64:ff9b::/96`、`64:ff9b:1::/48`（NAT64 local-use）、`100::/64`、`2001::/23`、`2001:db8::/32`、`2002::/16`（6to4）、`fc00::/7`、`fe80::/10`、`ff00::/8` |
| 主機名稱 | `localhost`、`localhost.localdomain`、`broadcasthost`、`ip6-localhost`、`ip6-loopback`、`local`、`internal`、`metadata.google.internal`、`metadata.internal`，以及 `.localhost`、`.local`、`.internal`、`.lan`、`.home.arpa`、`.localdomain`、`.corp` 結尾的名稱 |
| 連接埠 | 22、23、25、111、135、139、445、1433、1521、2375、2376、3306、5432、6379、11211、27017 |

自訂 API 工具與 MCP HTTP 傳輸的 httpx 用戶端使用 `SSRFSafeTransport`：第一個請求與每次轉址前都重新驗證，並把連線固定在驗證時核可的 IP（`Host` 標頭與 TLS SNI、憑證驗證仍使用原主機名稱），避免驗證與連線各做一次 DNS 解析時被 DNS rebinding 導向內網；轉址由 `send_following_redirects` 手動跟隨，轉址回應的本文不讀取。`safe_fetch_text`（`web_fetch` 與規格網址）手動逐跳驗證轉址、同樣固定 IP，並限制下載大小與轉址次數。DNS 查詢依來源分到兩個專用執行緒池：使用者網址（`web_fetch` 與非管理員的個人 LLM API 連線端點，`DnsPool.USER_URL`，8 條執行緒）與管理員設定的端點（自訂 API 工具、MCP HTTP 伺服器、OpenAPI 規格網址，`DnsPool.CONFIGURED_ENDPOINT`，4 條執行緒）。`getaddrinfo` 無法取消，使用者以慢速網域占滿前者時，工具與規格匯入的檢查不受影響；5 秒逾時視為無法解析，兩個池都不占用共用執行緒池。這些用戶端不讀取 `HTTP_PROXY`、`HTTPS_PROXY` 環境變數。`backend/tests/test_ssrf_protection.py` 涵蓋這些行為。

LLM API 連線依擁有者決定是否檢查：非管理員使用者的個人連線在建立與更新時先以上述規則驗證 API 位址，實際送出的請求（聊天、測試連線、取得模型清單）也經 `SSRFSafeTransport`（Claude 的 SDK 用戶端為 `SSRFSafeHttpx2Transport`）在每個請求前重新驗證並固定在驗證過的 IP，不能連到內網位址。共用連線、管理員的個人連線與系統模型由管理員設定，不做這項檢查（`public_only=False`），可以指向內網的模型服務。

> [!NOTE]
> 介紹頁（`site/`）的 SSRF 互動示範在瀏覽器端重現這裡的檢查順序與封鎖清單，修改規則時請同步更新 `site/index.html` 與 `site/main.js`。

### 11.4 工具輸出信任邊界與聯網限制

工具結果（知識庫片段、網頁內容、外部 API 回應）可能夾帶提示注入。Agent 一律把工具結果包在每次提問 id 不同的 `<untrusted_tool_result>` 標記內，系統提示要求只把它當資料看，也不把對話或知識庫內容拼進網址或搜尋字串。程式層另有三道限制：

1. **網址來源限制**：`web_fetch` 只能讀取使用者訊息或本次內建工具結果資料欄位中以完整網址出現過的網址（兩邊都正規化成 httpx 的形式後逐字比對，實際送出比對到的網址）。
2. **網域白名單**：`WEB_FETCH_ALLOWED_DOMAINS` 限定可讀取的網域（含子網域），明確寫 `*` 才表示不限制；初始網址與每一次轉址的目標都要在白名單內，白名單不是 `*` 時不使用 Ollama Web Fetch（轉址由 Ollama 端追蹤，無法逐跳檢查）。
3. **讀過知識庫後停用聯網**：`BLOCK_WEB_TOOLS_AFTER_KB=true` 時，同一次提問只要知識庫工具回傳過內容，之後的 `web_search` 與 `web_fetch` 一律拒絕。

Agent Skills 的內容例外：技能由管理員上傳，`activate_skill` 與 `read_skill_resource` 的結果以 `<skill_content>`、`<skill_resource>` 原樣交給模型當作指示，其中出現的網址也列入網址來源。上傳的 zip 拒絕絕對路徑、`..` 與符號連結，並以實際解壓的位元組數計算上限；直接上傳的資料夾同樣拒絕絕對路徑與 `..`；兩者都拒絕含冒號的路徑段落，避免在 Windows 上以磁碟代號或替代資料流寫到技能目錄外。技能中的腳本預設不會執行；管理員為技能開啟 `allow_scripts` 後，`run_skill_script` 的結果包上不可信標記，每次執行都要使用者核准。腳本在暫存複本中以最小環境變數執行，但**不是沙箱**：它以後端的系統帳號執行，能讀取該帳號可讀的檔案並連上網路，不受上述三道限制，只應為信任的技能開啟。技能的 `allowed-tools` 會讓列出的工具在該次提問中略過核准（包括有副作用的外部工具；列出 `run_skill_script` 時只限該技能自己的腳本；`delete_conversation_file` 不受影響，一律要核准），因此安裝技能前也要檢查這個欄位。

自訂 API 與 MCP 工具的結果同樣包上不可信標記，但不列入網址來源與引用編號，它們的出站請求不受上述三道限制（已知風險，見 [ADR-0003](adr/0003-rrf-relevance-citations-and-tool-trust.md)）。緩解方式是呼叫前核准：有副作用的工具由發問的使用者看過工具、送出的位置與參數後才執行（[ADR-0006](adr/0006-tool-call-approval.md)）；自訂 API 工具也只接受管理員在 `parameters_schema` 宣告的參數，不能夾帶其他查詢參數或本文欄位（第 9 節）。

### 11.5 其他防護

| 機制 | 內容 |
|---|---|
| 安全回應標頭 | `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`（回應自己帶 CSP `frame-ancestors` 時不加，例如網頁檔的隔離預覽）、`X-XSS-Protection: 1; mode=block`、`Referrer-Policy: strict-origin-when-cross-origin`、`Permissions-Policy: geolocation=(), microphone=(), camera=()`，並移除 `Server` 標頭 |
| 請求本文上限 | `RequestBodyLimitMiddleware`（純 ASGI，只在不讀本文的存取日誌之內）在 FastAPI 讀取本文前檢查：一般請求 1 MiB；聊天送出只有帶著簽章有效、未撤銷的存取權杖時才放寬，文件上傳與技能上傳（`/api/skills/upload`、`/api/skills/upload-folder`）另要求權杖帶有 `is_admin` 聲明（只用來決定本文上限，路由本身仍以資料庫判定是否為管理員）；`Content-Length` 超過即回 `413`，分塊傳輸邊讀邊計數 |
| 速率限制 | 每個來源 IP 在 60 秒滑動視窗內最多 `RATE_LIMIT_PER_MINUTE` 次，超過回傳 `429` 與 `Retry-After`；追蹤的位址最多 10,000 個，最久未活動者先淘汰。來源 IP 預設是實際連線對端（uvicorn 的 `proxy_headers` 只在設定 `FORWARDED_ALLOW_IPS` 時開啟），用戶端自行附上的 `X-Forwarded-For` 不會被採信。同一個 IP 在一個視窗內只在第一次被擋時寫一筆警告，視窗結束時再彙總被擋次數與路徑 |
| 部署設定 | `HOST`、`RELOAD`、`COOKIE_SECURE`、`ENABLE_API_DOCS` 都是必填設定，沒有預設值；列出所有端點與參數的互動式文件（`/docs`、`/redoc`、`/openapi.json`）只在 `ENABLE_API_DOCS=true` 時提供 |
| 資料庫帳號 | compose 的 PostgreSQL 由 `backend/init-app-role.sh` 建立後端連線用的 `POSTGRES_APP_USER`（`NOSUPERUSER`、`NOCREATEDB`、`NOCREATEROLE`），只授予資料庫的 `CONNECT` 與 `public` schema 的 `USAGE`、`CREATE`，並把資料表交給它擁有；SQL 注入無法以 `COPY ... TO PROGRAM` 執行系統指令或讀取伺服器檔案 |
| 相依套件 | `backend/requirements.txt` 由 `requirements.in` 以 `uv pip compile --universal --generate-hashes` 產生，安裝時驗證雜湊；`frontend/bun.lock` 隨版本庫提交，`frontend/bunfig.toml` 設定 `frozenLockfile = true` |
| CORS | 只允許 `ALLOWED_ORIGINS`（可加上 `DEVTUNNEL_URL`），允許攜帶 Cookie |
| 上傳檢查 | 檔名長度與危險字元、副檔名白名單、檔頭特徵、大小上限、OOXML 壓縮炸彈檢查；聊天附件另有解析預算（第 4 節） |
| 資源上限 | 訊息長度、附件數量與大小、聊天附件的解析預算、工具結果長度、每位使用者的同時串流數與附件儲存量等，集中定義在 `app/core/limits.py`，完整清單見 [設定參考：資源上限](configuration.md#資源上限) |
| 前端渲染 | 回答以 react-markdown 渲染，不渲染原始 HTML；GFM 語法由 `remarkGfmSafe` 轉換，它沿用 remark-gfm，但自動連結轉換前先以線性時間估算每個文字節點的掃描量，超過上限（一長串「.」「-」「_」或重複的「www.」會讓原本的轉換耗時隨長度平方成長）的節點不產生自動連結；Markdown 圖片改為點擊才開啟的連結，不自動向外部主機載入；外部連結以解析後的網址判斷，在新分頁開啟並標示實際主機；研究軌跡的參數與輸出預覽一律轉成文字顯示 |
| 建置產物的 CSP | `bun run build` 由 `frontend/vite.config.js` 的外掛把 CSP `<meta>` 寫入 `index.html`：`default-src 'self'`；`script-src`、`style-src` 只允許同源與 `index.html` 內嵌內容的 SHA-256 雜湊；`img-src 'self' data: blob:`；`connect-src` 與 `frame-src` 另加入 `VITE_API_BASE`／`VITE_API_URL` 的來源（`frame-src` 也讓網頁預覽的 iframe 無法被導向外部網址）；`object-src 'none'`、`base-uri 'none'`、`form-action 'self'`。網頁伺服器沒有設定 CSP 時，被注入的 HTML 也無法執行腳本。只在建置時套用，開發伺服器需要內嵌的 HMR 腳本 |
| 反點擊劫持 | Vite 開發與預覽伺服器送出 `X-Frame-Options: DENY` 與 `Content-Security-Policy: frame-ancestors 'none'; img-src 'self' data: blob:`；`index.html` 另有內嵌樣式守衛，頁面被嵌入 iframe 時保持隱藏。`<meta>` 形式的 CSP 不支援 `frame-ancestors`，正式環境的反框架標頭須由網頁伺服器送出 |

---

## 12. 前端架構

| 路由 | 頁面 | 權限 |
|---|---|---|
| `/login`、`/register` | 登入、註冊（未開放自行註冊時，註冊頁只顯示說明） | 未登入（已登入時導向首頁） |
| `/` | 導向 `/chat` | — |
| `/chat` | 聊天 | 登入 |
| `/profile` | 個人資料、改密碼與個人 API 連線（另列出可用的共用連線） | 登入 |
| `/documents` | 知識庫 | 管理員 |
| `/tools` | AI 工具：自訂 API 工具、MCP 伺服器與 Agent Skills | 管理員 |
| `/admin` | 管理後台：統計、使用者、共用 API 連線與系統模型 | 管理員 |

- **路由守衛**：`PrivateRoute` 未登入時導向登入頁；`AdminRoute` 對非管理員顯示「沒有權限」頁面；`PublicRoute` 讓已登入者離開登入與註冊頁。頁面以 `React.lazy` 延遲載入。
- **API 用戶端**（`services/api.ts`）：Axios 實例自動附上存取權杖；權杖剩不到 5 分鐘或已過期時先換發，收到 `401` 時換發後重試一次；換發同一時間只送一個請求（重新整理權杖只能用一次），聊天送出的 `fetch` 也共用同一套換發，收到 `401` 時換發後重送一次；登入、註冊與換發端點本身的 `401` 不會觸發換發。請求失敗時主控台只記錄狀態碼與錯誤訊息（`utils/secureLogger.ts`），不記錄帶有密碼、API 金鑰與存取權杖的 axios 錯誤物件。
- **登入狀態**：登入頁依 `GET /api/auth/registration` 決定是否顯示註冊入口（查詢失敗時視為未開放）；變更密碼成功後清除登入狀態並導回登入頁；登出請求失敗時在登入頁提示伺服器沒有撤銷重新整理權杖。
- **SSE**（`services/sse.ts`、`hooks/useChat.ts`）：以 `fetch` 讀取串流，依規格解析事件（可處理跨讀取切段、CRLF 與多行資料）；支援停止產生、重新傳送與串流中切換對話。送出失敗且回應是 `422` 欄位驗證錯誤時，取出每一項的說明顯示（例如附件過大）。
- **工具核准卡片**（`pages/Chat/ToolApprovalCard`）：收到 `approval_required` 時在該則回答中顯示工具名稱、實際送出的位置（`target`）與每個參數，不放在需要捲動的區域，控制字元與格式字元（雙向文字控制、零寬字元、Unicode 標籤字元等）以 `⟦U+…⟧` 標示；按下核准或拒絕後呼叫 `POST /api/chat/approvals/{approval_id}`；收到 `approval_resolved` 或停止串流時收起。「AI 工具」頁的自訂 API 工具與 MCP 伺服器表單各有要求使用者確認的核取方塊（「AI 呼叫前需使用者在對話中確認」與「AI 呼叫此伺服器的工具前需使用者在對話中確認」），API 工具依 HTTP 方法預設勾選。
- **外觀**：`ThemeContext` 提供淺色、深色與跟隨系統，設定存在 `localStorage` 的 `askmiao_theme_mode`；`index.html` 的內嵌腳本在第一次繪製前套用，避免閃白。
- **元件庫**（`components/ui/`）：Dialog、Menu、Tooltip、Snackbar 等以原生 `<dialog>` 與 ARIA 規範實作，支援鍵盤操作與焦點管理；設計 token 集中在 `styles/tokens.css`。
- **模型清單**：聊天頁每次載入時呼叫 `GET /api/chat/models` 取得可用的連線與模型，不做快取；`localStorage` 只記住選擇的連線與模型（`askmiao_selected_model`）與思考程度（`askmiao_reasoning_effort`）。
- **時間**：後端以 UTC 存放時間，回傳的字串不帶時區；前端一律經 `utils/serverDate.ts` 的 `parseServerDate()` 以 UTC 解讀，再依瀏覽器時區顯示。

---

## 13. 部署與維運

- **單一行程**：權杖撤銷名單、速率限制與登入失敗計數、每位使用者的同時串流數、待核准的工具呼叫與統計快取都存在後端行程的記憶體中。以多個 worker 或多台主機部署時，這些狀態不會共享（登入節流在每個行程各自計數），撤銷名單與登入失敗計數在重啟後也會清空。
- **對外提供**：後端以 `python main.py` 啟動時監聽 `HOST`（範本為 `127.0.0.1`），只有容器或其他主機上的反向代理需要連入時才改為 `0.0.0.0`；以 HTTPS 提供服務時 `COOKIE_SECURE` 必須為 `true`。Vite 開發與預覽伺服器只監聽 `localhost`。讓其他裝置使用時，請以 `bun run build` 建置，由正式的網頁伺服器提供 `frontend/build/`、送出反框架標頭並反向代理 `/api`；該代理會覆寫 `X-Forwarded-For` 時，可把它的位址設為 `FORWARDED_ALLOW_IPS`，速率限制與依位址的登入節流才會以真實用戶端 IP 計算。
- **Docker Compose 部署**：以 `deploy/` 的 Docker Compose 在一台主機上執行 PostgreSQL、後端與 nginx，見 [部署指南](deployment.md)。
- **PostgreSQL 容器**：`backend/docker-compose.yml` 需要 `POSTGRES_PASSWORD`（超級使用者，只供管理用途）與 `POSTGRES_APP_USER`、`POSTGRES_APP_PASSWORD`（後端連線用的非超級使用者，`DATABASE_URL` 使用這組帳號），且只綁定 `127.0.0.1:7690`。資料庫的 volume 第一次初始化時依序執行 `10-init.sql`（`backend/init.sql`）與 `20-app-role.sh`（`backend/init-app-role.sh`）；以舊版初始化的 volume 要執行一次 `docker compose exec postgres bash /docker-entrypoint-initdb.d/20-app-role.sh`（可重複執行）。
- **資料與備份**：需要備份的是資料庫、`backend/data/`（索引、上傳檔、模型快取）與 `SKILLS_DIR`（技能檔案，資料庫沒有副本；範本值 `data/skills` 在 `backend/data/` 內）；索引可由資料庫重建，上傳原檔則用來重新擷取文字。`backend/keys/` 遺失時會產生新金鑰，所有既有權杖隨之失效；目錄無法寫入或金鑰損毀時後端無法啟動。`TOOL_SECRETS_KEY` 遺失或更換時，資料庫中已加密的工具憑證與 LLM API 連線金鑰無法解密，需要重新輸入。
- **相依套件**：後端依 `requirements.txt` 的雜湊安裝；新增或升級套件時修改 `requirements.in`，然後在 `backend/` 執行 `uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes -o requirements.txt` 重新產生。前端 `bun install` 依凍結的 `bun.lock` 安裝，與 `package.json` 不一致時失敗。
- **日誌**：應用程式日誌寫入 `LOG_DIR/app.log`，安全事件只寫入 `LOG_DIR/security.log`（範本值 `logs` 以 `backend/` 為基準，即 `backend/logs/`），兩者都以 10 MiB × 5 份輪替。後端測試的安全事件寫到 pytest 的暫存目錄。錯誤代碼可在日誌中搜尋對應的完整例外，格式與請求 ID 見下一節。
- **介紹頁**：`.github/workflows/deploy-pages.yml` 在 `New` 分支的 `site/` 有變更時，把整個目錄部署到 GitHub Pages。
- **版本號**：後端以 `backend/app/__init__.py` 的 `__version__` 為準（OpenAPI 文件與 MCP 交握都引用），前端為 `frontend/package.json` 的 `version`，發行時與 `CHANGELOG.md` 一併更新。

### 日誌與請求追蹤

主控台、`app.log` 與 `security.log` 使用同一個格式，一筆一行；訊息中的換行會換成 `\n`，無法偽造出另一行。層級由 `LOG_LEVEL` 決定，輪替見 [設定參考：資源上限](configuration.md#資源上限)。

```text
2026-11-02 03:10:12 - app.access - INFO - [4f9c2a7e1b3d5f60] method=POST path=/api/chat/send status=200 duration_ms=8123 bytes=5120 ip=127.0.0.1 user=1
```

方括號中是請求 ID。`AccessLogMiddleware`（純 ASGI，在最外層）替每個 HTTP 請求產生 16 碼的 ID；請求帶有格式正確的 `X-Request-ID`（英數字開頭，只含英數字與 `.`、`_`、`-`，8 到 64 字）時沿用，方便與反向代理的紀錄對照。對外服務時請讓反向代理覆寫這個標頭（例如 nginx 的 `proxy_set_header X-Request-ID $request_id;`），避免用戶端自行附上的值混進來。這個 ID 會出現在：

- 回應的 `X-Request-ID` 標頭（CORS 也允許前端讀取）；
- 該請求期間的每一行日誌，包括交給執行緒處理的部分（例如文件解析與建立索引）；請求以外的日誌（啟動、定期掃描）顯示 `[-]`；
- `security.log` 中 JSON 的 `request_id` 欄位；
- `build_error_payload()` 回傳的錯誤內容（例如聊天串流的 `error` 事件）。

| 日誌 | 記錄器 | 層級 | 欄位 |
|---|---|---|---|
| 存取紀錄 | `app.access` | `INFO`；`5xx` 或例外為 `WARNING` | 每個 `/api` 請求結束時一行：`method`、`path`、`query_keys`（只有參數名稱）、`status`、`duration_ms`（串流回應算到最後一個位元組）、`bytes`、`ip`、`user`（權杖對應或剛登入的帳號 id，匿名為 `-`）、`error`（例外類別） |
| 模型呼叫 | `app.core.llm_client` | 開始、完成、中止為 `INFO`，失敗為 `WARNING` | 開始：`mode`（`chat`／`stream`）、`provider`、`model`、`host`、`messages`、`prompt_chars`、`images`、`tools`、`reasoning`、`timeout_s`。完成：`duration_ms`、`output_chars`、`tool_calls`、`stop_reason`，以及供應商有回傳的用量 `input_tokens`、`output_tokens`、`cached_tokens`、`reasoning_tokens`（Claude 為 `cache_read_tokens`、`cache_creation_tokens`，伺服器端改用其他模型時另記 `served_model`；Ollama 另記 `load_ms`、`prompt_eval_ms`、`eval_ms`、`total_ms`）。串流另記 `first_chunk_ms`、`chunks`。失敗：`error`（例外類別）、`detail`、`timeout_s` |
| 工具呼叫 | `app.rag.tools` | 成功為 `INFO`，結果含 `error` 或拋出例外為 `WARNING` | `tool`、`kind`（`builtin`、`skill_script`、`mcp`、`api`）、`status`（`ok`、`error`、`exception`、`cancelled`）、`duration_ms`、`arg_keys`（只有參數名稱）、`result_chars`、`error` |
| 未執行的工具呼叫 | `app.rag.agent` | `INFO` | 研究迴圈擋下或沒有執行的呼叫：`tool`、`status`（`refused` 為研究規則拒絕、`not_approved` 為使用者未核准或逾時、`approval_unavailable` 為沒有可核准的使用者）、`duration_ms`（含等待核准的時間） |
| 速率限制 | `app.core.security` | `WARNING` | 每個來源 IP 在一個視窗內兩行：第一次被擋時（`ip`、`path`、`limit`、`period_s`）與視窗結束時（`blocked`、各路徑次數，最多 `MAX_RATE_LIMIT_LOGGED_PATHS` 條） |

模型逾時的例外類別可以看出卡在哪一段：`ConnectTimeout` 是連不上，`PoolTimeout` 是等不到連線池名額，`ReadTimeout` 是請求已送出但在 `timeout_s` 內沒收到回應（非串流）或兩段文字之間等太久（串流，看 `first_chunk_ms` 是否已有值）。Ollama 成功時的 `load_ms`、`prompt_eval_ms`、`eval_ms` 分別是載入模型、讀入提示與產生回答的時間。

以上日誌不記錄密碼、API 金鑰、JWT、Cookie、`Authorization` 標頭與查詢參數的值，也不記錄提示、對話或文件內容，只記參數名稱、字數與用量；研究迴圈的 `[Agent Step n] 呼叫工具` 同樣只記參數名稱，檢索器的 `Retrieval` 一行只記查詢字數（`query_chars`）與各階段的片段數。查問題時先以錯誤代碼或時間找到一行，再以方括號中的請求 ID 搜尋同一個請求的所有紀錄。

---

## 14. 架構決策紀錄

| ADR | 標題 | 狀態 |
|---|---|---|
| [ADR-0001](adr/0001-hybrid-rag-and-security.md) | 增強型混合 RAG 檢索架構與雙 Token 安全防護 | 已通過；融合方式已由 ADR-0003 取代 |
| [ADR-0002](adr/0002-external-tools-and-outbound-safety.md) | 外部工具擴充機制與出站請求安全防護 | 已通過；由 ADR-0004 補充 |
| [ADR-0003](adr/0003-rrf-relevance-citations-and-tool-trust.md) | RRF 融合、相關性門檻、引用對應與工具輸出信任邊界 | 已通過 |
| [ADR-0004](adr/0004-tool-admin-permissions-and-subprocess-isolation.md) | 工具管理權限、MCP 子行程隔離與逐跳 SSRF 驗證 | 已通過；後續修訂見文末 |
| [ADR-0005](adr/0005-chunk-id-index-and-database-source-of-truth.md) | 以資料庫 chunk_id 為準的片段索引 | 已通過 |
| [ADR-0006](adr/0006-tool-call-approval.md) | 有副作用工具的對話內核准 | 已通過 |
| [ADR-0007](adr/0007-han-ngram-bm25-and-passage-level-evaluation.md) | BM25 加入漢字單字與雙字欄位，並以片段層級基準評估檢索 | 已通過 |

撰寫規範與完整索引見 [ADR 索引](adr/README.md)。