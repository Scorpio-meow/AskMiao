# 版本變更紀錄 (Changelog)

[繁體中文](CHANGELOG.md) | [English](CHANGELOG_en.md)

本專案遵守 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/) 規範，並遵循 [語意化版本 2.0.0](https://semver.org/lang/zh-TW/) 格式。

---

## [Unreleased]

### Changed
- 全面校正專案文件與現行實作之落差：
  - `docs/api.md`、`docs/api_en.md` 依實際路由重寫，補上 SSE 串流事件規格、自訂 API 工具與 MCP 端點、模型清單與管理後台端點，並移除已不存在之工作流（Workflow）與 `/api/documents/list`、`/api/documents/bulk_delete` 章節。
  - `docs/architecture.md`、`docs/architecture_en.md` 更新分層架構圖（移除 Redis 與多 Agent 看板），新增外部工具與 MCP 整合架構、SSRF 防護與錯誤代碼機制章節。
  - `README.md`、`README_en.md` 更新功能列表、目錄結構與環境變數矩陣，修正資料庫與前端埠號說明。
  - `llms.txt`、`llms_en.txt` 補齊新增模組之檔案地圖與系統約束。

---

## [2.2.1] - 2026-09-19

### Fixed
- **錯誤回應改用錯誤代碼**：
  - 新增 `app/core/error_response.py`，未預期例外之完整訊息與堆疊僅寫入伺服器日誌，對外僅回傳隨機錯誤代碼與 `error_id`（CWE-209 / CWE-497）。
  - `api_tools.py`、`mcp.py`、`chat.py` 與 `openapi_parser.py` 全面套用；輸入驗證類錯誤改以 `SafeClientError` 標記後原樣回傳，保留可據以修正之診斷訊息。
- **移除 RAG 串流中外洩之例外文字**：`rag/agent.py`、`rag/pipeline.py` 與 `rag/tools.py` 之串流輸出不再夾帶例外內容。

---

## [2.2.0] - 2026-09-01

### Fixed
- **修復 OpenAPI 解析與遠端請求之 SSRF 漏洞 (#25)**：
  - 新增 `app/core/ssrf_protection.py`，對使用者提供之 URL 進行協定、連接埠、主機名稱與 DNS 解析後 IP 範圍驗證，阻擋私有網段、迴環與連結本地位址、雲端中繼資料端點與危險連接埠。
  - `openapi_parser.py`、`rag/tools.py`（`web_fetch`）與 `api_tools.py` 全面改走 SSRF 防護閘門。
  - 新增 `backend/tests/test_ssrf_protection.py` 覆蓋阻擋與放行情境。

---

## [2.1.0] - 2026-08-27

### Added
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

### Changed
- 精簡 `.gitignore` 規則並自版本庫移除本地資料庫檔案。

---

## [2.0.1] - 2026-08-26

### Added
- **多模態對話管線**：對話支援附加圖片與文件；圖片以 `image_url` 內容區塊送入視覺模型，文字類附件抽取內容併入提問上下文。
- **知識庫動態描述**：文件上傳時自動生成 AI 大綱與摘要，並提供重新生成與手動修訂端點。

### Changed
- 全面現代化前端介面與元件庫。

---

## [2.0.0] - 2026-08-24

### Added
- **Agentic RAG 自主研究管線**：
  - 實作 ReAct 自主研究代理人 `ResearchAgent`，支援多輪自主推理與 Native Tool Calling。
  - 提供 `ResearchToolRegistry` 原生工具集：內部知識庫搜尋（`search_knowledge_base`）、外部聯網搜尋（`web_search`，具備 Ollama 與 DuckDuckGo 雙引擎備援）與外部網頁內容深度抓取（`web_fetch`）。
- **模型推理程度（Reasoning Effort）選擇機制**：
  - 前端頂部導覽列提供 5 檔位切換：`無 (None)`、`輕度 (Low)`、`標準 (Medium)`、`深度 (High)`、`極致 (X-High)`。
  - 後端全面適配 Azure OpenAI v1 及 OpenAI 官方推理模型（GPT-5 系列、o1/o3/o4 系列），並依微軟 Foundry 規範自動處理工具調用時之相容性。
- **全新前端視覺與研究歷程展示**：
  - 新增 `ResearchTraceBlock`：可折疊之研究步驟時間軸與工具調用日誌展示。
  - 新增 `SourceBadges`：外部參考連結徽章，支援點擊直接另開視窗閱讀來源。
- **模組化 RAG 架構**：
  - 將 RAG 系統重構為高內聚模組：向量索引（`indices/`）、混合檢索（`retrievers/`）、執行管線（`pipeline.py`）、評估器（`evaluator.py`）與門面類別（`contextual_rag.py`）。

### Changed
- **架構輕量化與零依賴化**：
  - 預設改用 SQLite 關聯式資料庫與記憶體快取，無需啟動 Docker、PostgreSQL 或 Redis 即可一鍵本機啟動。
  - 移除過時之討論看板與自訂 Agent 模組，專注於高效知識庫問答與深度研究。
  - 移除查詢快取命中，確保每次問答均能反映最新文檔與即時聯網資訊。
- **前端版面體驗升級**：
  - 側邊欄整合為單一自適應實例，桌面端無縫卡片貼合，移動端自動切換抽屜。
  - 全面使用 Bun 作為前端套件管理與建構工具。

### Fixed
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

### Added
- 增強型混合 RAG 檢索系統（FAISS + Whoosh BM25 + Cross-Encoder Reranker）。
- RSA-2048 JWT 認證與令牌黑名單撤銷機制。
- `security_logging.py` 敏感資料雙層脫敏機制（物件遞迴與正則遮罩）。
- 文件管理與知識庫切分向量化背景任務。