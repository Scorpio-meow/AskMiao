# 版本變更紀錄 (Changelog)

[繁體中文](CHANGELOG.md) | [English](CHANGELOG_en.md)

本檔記錄 AskMiao 每個版本的重要變更。格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-TW/1.1.0/)，版本號遵循 [語意化版本 2.0.0](https://semver.org/lang/zh-TW/)：不相容的變更升主版號，向下相容的新功能升次版號，錯誤修正升修訂號。

| 版本 | 發行日期 | 重點 |
|---|---|---|
| [3.0.0](#300---2026-09-25) | 2026-09-25 | chunk_id 索引、RRF 與相關性門檻、答案引用出處、工具信任邊界與管理權限、前端 UI/UX 全面修整 |
| [2.2.1](#221---2026-09-19) | 2026-09-19 | 錯誤回應改用錯誤代碼 |
| [2.2.0](#220---2026-09-01) | 2026-09-01 | 集中式 SSRF 防護 |
| [2.1.0](#210---2026-08-27) | 2026-08-27 | 自訂 API 工具、OpenAPI 匯入與 MCP 整合 |
| [2.0.1](#201---2026-08-26) | 2026-08-26 | 多模態對話與 AI 文件摘要 |
| [2.0.0](#200---2026-08-24) | 2026-08-24 | Agentic RAG 自主研究 |
| [1.0.0](#100---2026-08-01) | 2026-08-01 | 混合 RAG 與安全基礎 |

> [!TIP]
> 從 2.x 升級到 3.0.0 前，請先閱讀 [升級指南](docs/upgrading.md)：需要補齊 `.env` 設定，並重建一次知識庫索引。

---

## [Unreleased]

### 安全性 (Security)

- **MCP 伺服器的 SSRF 拒絕訊息不再帶出解析結果**：建立或探索 MCP 伺服器時網址被 SSRF 防護拒絕，`last_error` 與 400 回應改為註明遭拒並附錯誤代碼；完整原因可能含伺服器端 DNS 解析出的內網 IP 或轉址目標，只寫入伺服器日誌（CWE-209）。
- **介紹頁 RRF 示範跳脫片段 ID**：`site/main.js` 把內嵌 JSON 的片段 ID 與重排機率插入 HTML 前改經 `escapeHtml`，資料含引號或角括號時不再被當成 HTML 解析（CWE-79）。

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
