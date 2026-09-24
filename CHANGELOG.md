# 版本變更紀錄 (Changelog)

[繁體中文](CHANGELOG.md) | [English](CHANGELOG_en.md)

本專案遵守 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/) 規範，並遵循 [語意化版本 2.0.0](https://semver.org/lang/zh-TW/) 格式。

---

## [Unreleased]

> **破壞性變更**：`.env` 須新增必填的 `RRF_K`、`RERANK_RELEVANCE_THRESHOLD`、`WEB_FETCH_ALLOWED_DOMAINS`、`BLOCK_WEB_TOOLS_AFTER_KB`、`DOMAIN_PROFILE_PATH`，否則後端無法啟動；重排模型改為必要元件。升級與回退步驟見 [ADR-0003](docs/adr/0003-rrf-relevance-citations-and-tool-trust.md)。

> **權限與行為變更**：「AI 工具」頁與 `/api/api-tools`、`/api/mcp` 改為只限管理員；MCP `stdio` 伺服器不再繼承後端的環境變數，需要的變數要寫在該伺服器的 `env_vars`；指向本機或內網位址的 MCP HTTP 伺服器會被拒絕。詳見 [ADR-0004](docs/adr/0004-tool-admin-permissions-and-subprocess-isolation.md)。

### Added
- **RRF 融合與相關性門檻**：向量與 BM25 每次必跑，以標準 RRF（`RRF_K`）依名次融合；`RERANK_RELEVANCE_THRESHOLD` 直接套在重排機率上，精確比對到網址、貼文 ID、日期者不受限制，全部未通過時回報「知識庫中查無相關資料」。
- **引用對應來源**：每次提問建立引用編號表（`app/rag/research_session.py`），答案以 `[n]` 標註出處，`sources_detail` 只列實際被引用的條目並附 `citation` 編號；前端標籤改為「[2] 員工手冊.pdf（段落 3）」格式。
- **領域設定檔**：新增 `backend/config/domain_profile.json` 與 `DOMAIN_PROFILE_PATH`，收納領域詞、記錄日期欄位與摘要備援規則，啟動時驗證格式；選填 `JIEBA_DICTIONARY` 可替換 jieba 主詞典。
- **門檻校準工具**：問答集允許 `"relevant_sources": []` 的反例；`scripts/evaluate_retrieval.py` 新增 `--relevance-thresholds`，對同一次重排結果比較多個門檻的正例 hit@k、MRR 與反例拒絕率。
- **停止產生與重新傳送**：串流中可停止回答（已停止的回答不會儲存），串流時仍可繼續輸入；失敗的回答顯示原因與「重新傳送」，送出前就失敗時把文字與附件放回輸入框。
- **外觀切換**：帳號選單新增淺色、深色與跟隨系統，預設跟隨系統，並在第一次繪製前套用，深色模式不再先閃白。
- **刪除前確認**：刪除對話、使用者、文件、自訂 API 工具與 MCP 伺服器，以及清空上傳清單、覆寫已編輯的摘要前都會先確認（`ConfirmDialog`）。
- 聊天頁新增「回到最新訊息」按鈕，並以讀螢幕軟體播報回答完成、失敗或停止；新增網路離線與恢復提示、「跳到主要內容」連結，非管理員進入管理頁時改顯示「沒有權限」頁面，取代原生 `alert()`。
- `frontend/src/services/sse.ts`：依規格實作的 SSE 解析器與 8 個 Vitest 測試（事件跨讀取切段、CRLF、多行資料等）。

### Changed
- 模型不再呼叫工具時直接採用該次答案，不再重新生成，並移除假串流；只有工具輪數用完或模型回傳空內容時才以串流生成。
- 重排模型改為必要元件：載入失敗時啟動報錯，執行時重排失敗回傳錯誤代碼，不再回傳未過濾的片段。
- `search_knowledge_base` 指定 `target_document` 時在重排前限定文件，查不到不再改用全庫結果。
- BM25 斷詞結果一律轉小寫；索引目錄記錄斷詞簽章，簽章不符時自動重建 BM25（向量不需重算），唯讀評估則拒絕執行。
- 設定中的相對路徑（`DATA_DIR`、`UPLOAD_DIR`、索引路徑、`HF_*`、`DOMAIN_PROFILE_PATH`、`JIEBA_DICTIONARY`）一律以 `backend/` 為基準。
- `.env.example` 的 `RERANK_TOP_K` 範例值由 50 改為 20。
- `/api/admin/rag-config` 改回傳 `rrf_k` 與 `rerank_relevance_threshold`，移除 `hybrid_alpha`、`final_threshold`、`normalization`。
- 全面校正專案文件與現行實作之落差：
  - `docs/api.md`、`docs/api_en.md` 依實際路由重寫，補上 SSE 串流事件規格、自訂 API 工具與 MCP 端點、模型清單與管理後台端點，並移除已不存在之工作流（Workflow）與 `/api/documents/list`、`/api/documents/bulk_delete` 章節。
  - `docs/architecture.md`、`docs/architecture_en.md` 更新分層架構圖（移除 Redis 與多 Agent 看板），新增外部工具與 MCP 整合架構、SSRF 防護與錯誤代碼機制章節。
  - `README.md`、`README_en.md` 更新功能列表、目錄結構與環境變數矩陣，修正資料庫與前端埠號說明。
  - `llms.txt`、`llms_en.txt` 補齊新增模組之檔案地圖與系統約束。
- 對話框、手機版對話清單與圖片檢視改用原生 `<dialog>`：Esc 可關閉、背景無法操作、關閉後焦點回到原本的按鈕；帳號選單支援方向鍵操作。
- 手機版頂欄縮為一列（64px），聊天頁固定為一個視窗高度；觸控裝置上的按鈕與輸入框加大，輸入框字級 16px，iPhone 聚焦時不再自動放大。
- 調整次要文字、狀態色與深色模式主要按鈕的配色，文字對比達 WCAG AA。
- 品牌名稱統一為 AskMiao，每頁有各自的網頁標題；導覽列改用連結並標示目前所在頁面。
- 訊息不是當天送出時一併顯示日期；來源相關度改以百分比顯示。
- 前端文字與後端回傳的訊息改用臺灣用語（例如「使用者名稱」「電子郵件」「字元」「權杖」），無障礙標籤不再混用英文。
- 網頁圖示改用 32px 與 64px 版本，訪客不再下載 4.5MB 的 2048px 原圖（原圖仍保留作為 `site/assets` 圖示的來源）。

### Removed
- `HYBRID_ALPHA`、`NORMALIZATION`、`FINAL_THRESHOLD` 設定與 `auto_tune_alpha`（留在 `.env` 中會被忽略）；依查詢型態分流與寫死的 FAQ 關鍵字判斷。
- `data/jieba_dict.txt` 存在即自動載入的隱藏機制；自訂詞一律放在領域設定檔。
- uploads watcher 發出、但前端沒有接收的 `documents_update` WebSocket 通知。
- 前端的 `dompurify` 相依套件：react-markdown 預設就不渲染原始 HTML，這一層反而會改寫回答內容。

### Fixed
- 相關性門檻套在混合分數上，第一名一定拿到 0.15 而過門檻，導致永遠至少送一段無關片段給模型。
- 只有 BM25 找到的片段在加權融合後進不了重排候選。
- uploads watcher 在上傳檔不見時刪除索引與資料庫紀錄；從其他目錄啟動時會把所有文件判為遺失。現改為只記一次警告。
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

### Security
- 工具結果一律包在每次提問 id 不同的 `<untrusted_tool_result>` 標記內，系統提示規定只當資料看。
- `web_fetch` 只能讀取使用者訊息或本次內建工具結果中原樣出現過的網址（工具回聲的查詢參數不算）；新增網域白名單 `WEB_FETCH_ALLOWED_DOMAINS` 與 `BLOCK_WEB_TOOLS_AFTER_KB`（讀過知識庫內容後停用聯網工具）。
- **工具管理只限管理員**：任何註冊使用者原本都能建立 `stdio` MCP 伺服器，在主機上執行任意指令（RCE），也能讀到別人設定的工具憑證。現在 `/api/api-tools` 與 `/api/mcp` 的所有端點（含查詢）都需要管理員，前端「AI 工具」頁也只對管理員顯示。
- MCP `stdio` 子行程只繼承 `PATH` 等系統必要變數，不再取得後端的 JWT 金鑰、資料庫連線與模型 API 金鑰。
- MCP HTTP 傳輸補上原本缺少的 SSRF 驗證；自訂 API 工具與 MCP HTTP 傳輸的每次轉址都會重新驗證，外部 API 無法再以轉址導向內網或雲端 Metadata。

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
  - 後端全面適配 Azure OpenAI v1 及 OpenAI 官方推理模型，並依微軟 Foundry 規範自動處理工具調用時之相容性。
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