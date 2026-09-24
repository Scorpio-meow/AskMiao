# AskMiao 設定參考

[繁體中文](configuration.md) | [English](configuration_en.md)

> 本文件逐一說明後端 `backend/.env` 與前端 `frontend/.env` 的每個設定、預設值與實際作用，適用於 **3.0.0**。設定以 `backend/app/core/config.py` 的 `Settings` 為準，範本見 [`backend/.env.example`](../backend/.env.example)。

- [讀取規則](#讀取規則)
- [必填設定](#必填設定)
- [LLM 供應商與模型](#llm-供應商與模型)
- [Agent 與聯網工具](#agent-與聯網工具)
- [檢索、重排與切塊](#檢索重排與切塊)
- [運算裝置](#運算裝置)
- [Hugging Face 模型快取](#hugging-face-模型快取)
- [儲存路徑與上傳](#儲存路徑與上傳)
- [資料庫](#資料庫)
- [認證與權杖](#認證與權杖)
- [網路存取控制](#網路存取控制)
- [伺服器與執行環境](#伺服器與執行環境)
- [保留設定](#保留設定)
- [已移除的設定](#已移除的設定)
- [領域設定檔](#領域設定檔)
- [校準相關性門檻](#校準相關性門檻)
- [前端環境變數](#前端環境變數)

---

## 讀取規則

- **來源**：後端從 `backend/.env` 讀取設定（與啟動目錄無關），行程環境變數優先於 `.env`。不認得的鍵會被忽略，所以已移除的舊設定留在 `.env` 中不會出錯。
- **必填設定沒有預設值**：缺少任一項時，後端在啟動時就以 `Field required` 錯誤結束，並列出缺少的欄位。
- **數值範圍**：`AGENT_MAX_TURNS ≥ 1`、`CONVERSATION_HISTORY_MESSAGES ≥ 0`、`RRF_K ≥ 1`、`0 ≤ RERANK_RELEVANCE_THRESHOLD ≤ 1`、`ANTHROPIC_MAX_TOKENS ≥ 1`，超出範圍同樣無法啟動。
- **布林值**：`true` / `false`、`1` / `0`、`yes` / `no` 皆可。
- **相對路徑**：`DATA_DIR`、`UPLOAD_DIR`、`FAISS_INDEX_PATH`、`BM25_INDEX_DIR`、`METADATA_PATH`、`HF_HOME`、`HF_HUB_CACHE`、`SENTENCE_TRANSFORMERS_HOME`、`DOMAIN_PROFILE_PATH`、`JIEBA_DICTIONARY` 的相對路徑一律以 `backend/` 為基準。`DATABASE_URL` 不在此列，SQLite 的相對路徑依啟動目錄而定。
- **程式預設值與範本值**：下表的「程式預設值」是 `.env` 未設定時的值；「範本值」是 `backend/.env.example` 建議的值，兩者不同時以你的 `.env` 為準。

## 必填設定

| 變數 | 範本值 | 說明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@localhost:5432/chatbot` | 資料庫連線字串，詳見 [資料庫](#資料庫) |
| `JWT_SECRET_KEY` | `your_jwt_secret_key_here` | RSA 金鑰無法使用時的 HS256 簽署金鑰，請換成隨機字串 |
| `ADMIN_API_KEY` | `your_admin_api_key_here` | 管理用 API 金鑰（設定驗證要求此值，目前沒有路由使用），請換成隨機字串 |
| `ENABLE_WEB_SEARCH` | `true` | 是否提供聯網工具 |
| `AGENT_MAX_TURNS` | `5` | 單次提問的工具呼叫輪數上限 |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | 帶入的前文訊息數 |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | `web_fetch` 網域白名單 |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | 讀過知識庫後停用聯網工具 |
| `RRF_K` | `60` | RRF 融合常數 |
| `RERANK_RELEVANCE_THRESHOLD` | `0.2` | 重排機率門檻 |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | 領域設定檔路徑 |

使用 Claude 模型時，`ANTHROPIC_MAX_TOKENS` 也是必填（未設定時呼叫 Claude 會失敗，但不影響啟動）。

## LLM 供應商與模型

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `LLM_API_BASE` | `http://localhost:5000` | `http://localhost:11434` | Ollama 服務位址：呼叫 Ollama 模型（`/api/chat`）與查詢遠端模型清單（`/api/tags`）時使用 |
| `LLM_TIMEOUT` | `120` | `120` | LLM 呼叫逾時秒數，也用於 PDF OCR 的視覺模型呼叫 |
| `MODEL_NAME` | 空 | — | 預設模型；未設定時依下方「預設模型」規則決定 |
| `AVAILABLE_MODELS` | 空 | 註解範例 | 前端可選的模型清單（逗號分隔）；設定後完全取代自動產生的清單 |
| `OLLAMA_TEMPERATURE` | 空 | `0.3` | Ollama 的 `temperature`，未設定時使用模型預設值 |
| `OLLAMA_NUM_PREDICT` | 空 | `2048` | Ollama 的 `num_predict`，未設定時使用模型預設值 |
| `AZURE_OPENAI_API_KEY` | 空 | 註解範例 | 與 `AZURE_OPENAI_ENDPOINT` 同時設定才啟用 Azure OpenAI |
| `AZURE_OPENAI_ENDPOINT` | 空 | 註解範例 | 例如 `https://<資源名稱>.openai.azure.com`，呼叫 `/openai/v1/chat/completions` |
| `AZURE_OPENAI_DEPLOYMENT` | 空 | 註解範例 | 部署名稱，逗號分隔可列多個，第一個為預設；啟用 Azure 但未設定時，清單列出 `gpt-6-sol` |
| `OPENAI_API_KEY` | 空 | 註解範例 | OpenAI 金鑰 |
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | 註解範例 | OpenAI 或相容服務的基底位址 |
| `OPENAI_VISION_MODEL` | `gpt-6-sol` | — | PDF 掃描頁 OCR 使用的 OpenAI 模型；Azure 未設定部署時也當作部署名稱 |
| `ANTHROPIC_API_KEY` | 空 | 註解範例 | Anthropic 金鑰 |
| `ANTHROPIC_API_BASE` | `https://api.anthropic.com` | 註解範例 | Anthropic API 位址 |
| `ANTHROPIC_MAX_TOKENS` | 空 | 註解範例 `16000` | Claude 單次回應的輸出 token 上限（使用 Claude 時必填）；工具呼叫參數被截斷時會回報錯誤，請調高 |
| `GEMINI_API_KEY` | 空 | 註解範例 | Google Gemini 金鑰 |
| `GEMINI_API_BASE` | `https://generativelanguage.googleapis.com` | 註解範例 | 呼叫 OpenAI 相容端點 `/v1beta/openai/chat/completions` |
| `GEMINI_VISION_MODEL` | `gemini-3.5-flash` | — | PDF 掃描頁 OCR 使用的 Gemini 模型 |
| `EXTERNAL_TAGS_URL` | 空 | — | 沒有任何雲端模型時，查詢遠端模型清單的網址；未設定時使用 `{LLM_API_BASE}/api/tags` |
| `LLM_TAGS_TIMEOUT` | `10` | — | 查詢遠端模型清單的逾時秒數 |
| `ADD_NGROK_HEADER` | `false` | — | 查詢遠端模型清單時加上 `ngrok-skip-browser-warning` 標頭（網址含 `ngrok-free.app` 時自動加上） |

### 模型清單

`GET /api/chat/models` 與 `GET /api/tags` 依下列順序產生模型清單：

1. 設定了 `AVAILABLE_MODELS`：直接使用這份清單。
2. 否則依序合併：Azure 部署（未設定部署時為 `gpt-6-sol`）、有 `OPENAI_API_KEY` 時的 OpenAI 內建清單、有 `ANTHROPIC_API_KEY` 時的 Claude 內建清單、有 `GEMINI_API_KEY` 時的 Gemini 內建清單。
3. 以上皆為空：向 `EXTERNAL_TAGS_URL`（或 `{LLM_API_BASE}/api/tags`）查詢遠端清單，例如本機 Ollama 已下載的模型。

| 供應商 | 內建清單（3.0.0） |
|---|---|
| OpenAI | `gpt-6-sol`、`gpt-6-luna`、`gpt-6-astra`、`gpt-5.6-sol`、`gpt-5.6-luna`、`gpt-5.6-terra`、`gpt-5.4`、`gpt-5.4-mini` |
| Anthropic | `claude-opus-5-5`、`claude-fable-5-1`、`claude-sonnet-5`、`claude-opus-5`、`claude-fable-5`、`claude-opus-4-8`、`claude-haiku-4-5` |
| Gemini | `gemini-3.5-flash`、`gemini-3.1-flash-lite`、`gemini-3-pro` |

**預設模型**：`MODEL_NAME` → 第一個 Azure 部署 → 清單第一個；選出的模型不在清單內時改用清單第一個。

### 供應商路由

每次呼叫依模型名稱決定供應商，規則由上而下取第一個符合者：

| 條件 | 供應商 | 端點 |
|---|---|---|
| 已啟用 Azure，且模型名稱是 `AZURE_OPENAI_DEPLOYMENT` 中的一個 | Azure OpenAI | `{AZURE_OPENAI_ENDPOINT}/openai/v1/chat/completions` |
| 名稱以 `claude-` 開頭且有 `ANTHROPIC_API_KEY` | Anthropic | 官方 `anthropic` SDK（Messages API） |
| 名稱以 `gemini-` 開頭且有 `GEMINI_API_KEY` | Google Gemini | `{GEMINI_API_BASE}/v1beta/openai/chat/completions` |
| 名稱以 `gpt-`、`o1`、`o3`、`o4` 開頭 | 有 `OPENAI_API_KEY` 時為 OpenAI；否則在已啟用 Azure 時改走 Azure | `{OPENAI_API_BASE}/chat/completions` |
| 以上皆不符合 | Ollama | `{LLM_API_BASE}/api/chat` |

> [!NOTE]
> `reasoning_effort` 只會傳給 OpenAI 與 Azure OpenAI；名稱含 `gpt-5` 的模型在帶工具呼叫時一律改送 `none`，以符合推理模型與工具呼叫的相容性限制。

## Agent 與聯網工具

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `ENABLE_WEB_SEARCH` | —（必填） | `true` | 同時控制 `web_search` 與 `web_fetch`；`false` 時兩者不會出現在工具清單中，呼叫也會被拒絕 |
| `AGENT_MAX_TURNS` | —（必填，≥ 1） | `5` | 單次提問最多呼叫模型幾輪（每輪可同時呼叫多個工具）；用完仍未得到答案時，改以串流生成最終答案 |
| `CONVERSATION_HISTORY_MESSAGES` | —（必填，≥ 0） | `6` | 提問時從資料庫帶入的前文訊息數（使用者與助理訊息合計，前文一律從使用者訊息開始）；`0` 表示不帶前文 |
| `WEB_FETCH_ALLOWED_DOMAINS` | —（必填） | `*` | `web_fetch` 可讀取的網域，含子網域，逗號分隔；明確寫 `*` 才表示不限制 |
| `BLOCK_WEB_TOOLS_AFTER_KB` | —（必填） | `true` | 同一次提問中，知識庫工具回傳過內容後，拒絕之後的 `web_search` 與 `web_fetch` |
| `OLLAMA_API_KEY` | 空 | 註解範例 | Ollama 官方 Web Search / Web Fetch API 的金鑰。設定後聯網工具優先使用 Ollama API，失敗時改用 DuckDuckGo 或直接抓取；與 LLM 呼叫無關 |
| `OLLAMA_SEARCH_ENDPOINT` | `https://ollama.com/api/web_search` | — | Ollama Web Search 端點 |
| `OLLAMA_FETCH_ENDPOINT` | `https://ollama.com/api/web_fetch` | — | Ollama Web Fetch 端點 |
| `DUCKDUCKGO_SEARCH_ENDPOINT` | `https://html.duckduckgo.com/html/` | — | `web_search` 的備援搜尋端點 |
| `DEFAULT_CONVERSATION_TITLE` | `新對話` | — | 新對話的暫時標題；第一則使用者訊息送出後改為該訊息的前 50 字 |

`WEB_FETCH_ALLOWED_DOMAINS` 的格式規則：

- 不可為空；不限制時請明確寫 `*`，且 `*` 不能與其他網域並列。
- 只填網域（小寫英數、連字號與點），不含 `https://` 與路徑，例如 `gov.tw,example.com`。
- 無論白名單為何，`web_fetch` 都只能讀取使用者訊息或本次工具結果中原樣出現過的網址，並一律經過 SSRF 驗證。

## 檢索、重排與切塊

每次檢索的流程：向量與 BM25 各取 `TOP_K` 筆 → RRF 融合取前 `RERANK_TOP_K` 筆（加上網址、貼文 ID、日期與 @帳號的精確比對結果）→ Cross-Encoder 重排 → 套用 `RERANK_RELEVANCE_THRESHOLD` → 取前 `FINAL_K` 筆。

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 同左 | 嵌入模型；更換後向量維度不同時，舊索引改名為 `*.mismatch.bak` 並依資料庫片段重新計算 |
| `RERANKER_MODEL` | `BAAI/bge-reranker-base` | 同左 | Cross-Encoder 重排模型，必要元件，載入失敗時後端無法啟動 |
| `TOP_K` | `30` | `30` | 向量與 BM25 各自取回的候選數 |
| `RRF_K` | —（必填，≥ 1） | `60` | RRF 分數 = Σ 1 / (`RRF_K` + 名次)，名次從 1 起算 |
| `RERANK_TOP_K` | `50` | `20` | 融合後送進重排的候選數；CPU 上每對約 0.2（300 字）至 0.4 秒（800 字） |
| `RERANK_WEIGHT` | `0.85` | `0.85` | 排序用混合分數 = `RERANK_WEIGHT` × 重排機率 + (1 − `RERANK_WEIGHT`) × 候選原分數；不影響門檻判斷 |
| `RERANK_RELEVANCE_THRESHOLD` | —（必填，0~1） | `0.2` | 重排機率低於此值的片段視為無關；精確比對到網址、貼文 ID、日期者不受限制；全部被濾掉時回報「知識庫中查無相關資料」 |
| `FINAL_K` | `8` | `8` | 通過門檻後最多保留的片段數 |
| `SIMILARITY_THRESHOLD` | `0.30` | `0.30` | 只用於單獨的向量搜尋（`vector_search`）；RRF 混合檢索的主流程不套用 |
| `CHUNK_SIZE` | `800` | `300` | 切塊長度（字元）；修改後需重建索引才會套用到既有文件 |
| `CHUNK_OVERLAP` | `150` | `100` | 相鄰片段的重疊字元數 |
| `DOMAIN_PROFILE_PATH` | —（必填） | `config/domain_profile.json` | 領域設定檔，格式見 [領域設定檔](#領域設定檔) |
| `JIEBA_DICTIONARY` | 空 | 註解範例 | 替換 jieba 主詞典，例如繁體較友善的 [`dict.txt.big`](https://raw.githubusercontent.com/fxsjy/jieba/master/extra_dict/dict.txt.big)；檔案不存在時無法啟動，變更後 BM25 索引自動重建 |

> [!TIP]
> Q&A 格式（`Q：…` / `A：…`）的文件會一問一答各成一個片段，結構化記錄與 JSON 資料會逐筆成為獨立片段，這兩種情況不受 `CHUNK_SIZE` 限制。

## 運算裝置

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `FORCE_CPU` | `true` | `true` | 即使有 CUDA 也使用 CPU；CPU 模式的 PyTorch 執行緒數為 min(16, CPU 核心數) |
| `USE_FP16_QUANTIZATION` | `false` | `false` | 只在 CUDA 上生效：嵌入與重排模型改用 FP16 |
| `GPU_BATCH_SIZE` | `128` | `128` | GPU 嵌入批次大小 |
| `CPU_BATCH_SIZE` | `64` | `32` | CPU 嵌入批次大小 |
| `USE_FAISS_GPU` | `false` | `false` | FAISS 使用 GPU（需安裝 `faiss-gpu`，初始化失敗時退回 CPU） |
| `FAISS_GPU_DEVICE` | `0` | `0` | FAISS 使用的 GPU 編號 |
| `FAISS_GPU_TEMP_MEMORY` | `2147483648` | 同左 | FAISS GPU 暫存記憶體（位元組，預設 2 GiB） |

## Hugging Face 模型快取

這些設定會在載入任何模型前寫入環境變數（布林值寫成 `1` / `0`），未設定的鍵不會寫入。

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `HF_HOME` | 空（函式庫預設 `~/.cache/huggingface`） | `./data/hf_home` | 模型快取根目錄 |
| `HF_HUB_CACHE` | 空（跟隨 `HF_HOME`） | 註解範例 | 只想把 Hub 快取放在別處時設定 |
| `SENTENCE_TRANSFORMERS_HOME` | 空（跟隨 `HF_HOME`） | 註解範例 | sentence-transformers 的快取位置 |
| `HF_HUB_OFFLINE` | 空 | `false` | `true` 時只從快取載入、啟動時不連線檢查；首次下載模型前請保持 `false` |
| `HF_HUB_DISABLE_SYMLINKS_WARNING` | 空 | `true` | Windows 無法建立符號連結時隱藏警告；此時快取改以複製檔案保存，重排模型下載約 1.1 GB、佔用約 2.2 GB |

## 儲存路徑與上傳

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `DATA_DIR` | `data` | `data` | 索引與執行資料的根目錄 |
| `UPLOAD_DIR` | `data/uploads` | `data/uploads` | 上傳原始檔；重建索引時會優先從這裡重新擷取文字 |
| `FAISS_INDEX_PATH` | `data/faiss_index.bin` | 同左 | FAISS 向量索引（`IndexIDMap2`，以 chunk_id 為 id） |
| `BM25_INDEX_DIR` | `data/bm25_index` | 同左 | Whoosh BM25 索引目錄（含 `tokenizer_signature.json`） |
| `METADATA_PATH` | `data/index_metadata.pkl` | 同左 | 索引中繼資料，例如最後重建時間 |
| `MAX_FILE_SIZE_MB` | `50` | `10` | 知識庫單一上傳檔大小上限（MB） |
| `UPLOADS_WATCHER_INTERVAL` | `30` | `30` | 背景檢查上傳檔是否遺失的間隔秒數；檔案遺失只記一次警告，不會刪除任何資料 |

## 資料庫

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `DATABASE_URL` | —（必填） | PostgreSQL 範例 | SQLAlchemy 連線字串 |
| `DB_POOL_SIZE` | `20` | `20` | 連線池大小（PostgreSQL 等非 SQLite 資料庫；SQLite 固定為 5） |
| `DB_MAX_OVERFLOW` | `40` | `40` | 連線池溢出上限（SQLite 固定為 10） |
| `DB_POOL_RECYCLE` | `3600` | — | 連線回收秒數 |
| `DB_POOL_PRE_PING` | `true` | — | 取用連線前先檢查（僅非 SQLite） |
| `SQLALCHEMY_ECHO` | `false` | — | 在日誌輸出 SQL |

常見的 `DATABASE_URL`：

| 情境 | 連線字串 |
|---|---|
| SQLite（零依賴） | `sqlite:///./chatbot.db`（相對路徑依啟動目錄而定，在 `backend/` 啟動即為 `backend/chatbot.db`） |
| `backend/docker-compose.yml` 啟動的 PostgreSQL 17 | `postgresql+psycopg2://postgres:postgres@localhost:7690/chatbot`（容器對外埠號為 7690） |
| 自行架設的 PostgreSQL | `postgresql+psycopg2://<使用者>:<密碼>@<主機>:5432/<資料庫>` |

資料表在後端啟動時自動建立。`init_db.py` 是為舊版 PostgreSQL 資料庫補欄位與索引的相容腳本，SQLite 不需要執行（其中的 `ADD COLUMN IF NOT EXISTS` 語法 SQLite 不支援）。

## 認證與權杖

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `JWT_SECRET_KEY` | —（必填） | 佔位字串 | 平常以 RSA 金鑰簽署 RS256；RSA 金鑰無法載入時（僅限非 `production`）改用此金鑰簽署 HS256 |
| `JWT_ALGORITHM` | `RS256` | `RS256` | 目前未被程式採用：RSA 金鑰可用時固定為 RS256，否則退回 HS256 |
| `ADMIN_API_KEY` | —（必填） | 佔位字串 | 設定驗證要求此值；目前沒有路由使用 `X-API-Key` 驗證，管理端點一律依存取權杖中的 `is_admin` 判斷 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | `30` | 存取權杖有效分鐘數 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | `7` | 重新整理權杖有效天數，也是 Cookie 的 `max-age` |
| `COOKIE_SECURE` | 空（`ENVIRONMENT=production` 時為 `true`） | — | 重新整理權杖 Cookie 的 `Secure` 屬性 |
| `COOKIE_SAMESITE` | `lax` | — | 重新整理權杖 Cookie 的 `SameSite` 屬性 |

RSA 金鑰對存放於 `backend/keys/jwt_private.pem` 與 `jwt_public.pem`，首次啟動時若不存在會自動產生（2048 位元，已列入 `.gitignore`）。多台後端共用同一組使用者時，請讓它們使用同一組金鑰。

## 網路存取控制

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:3001,https://localhost:3001,http://127.0.0.1:3001,https://127.0.0.1:3001` | `http://localhost:3001,https://localhost:3001` | CORS 允許的來源（逗號分隔，允許攜帶 Cookie） |
| `DEVTUNNEL_URL` | 空 | 空 | 額外加入 CORS 白名單的一個來源，例如 Dev Tunnels 網址 |
| `RATE_LIMIT_ENABLED` | `true` | `true` | 是否啟用速率限制 |
| `RATE_LIMIT_PER_MINUTE` | `60` | `60` | 每個來源 IP 在 60 秒內的請求上限，超過回傳 `429` 與 `Retry-After` |

> [!NOTE]
> 速率限制依連線的來源 IP 計算。經由 Vite 開發代理或反向代理連線時，所有使用者的來源 IP 相同，會共用同一個額度。

## 伺服器與執行環境

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `ENVIRONMENT` | `development` | `development` | 設為 `production` 時：Cookie 預設加上 `Secure`，RSA 金鑰無法載入時拒絕啟動 |
| `HOST` | `0.0.0.0` | `0.0.0.0` | `python main.py` 的預設監聽位址（可用 `--host` 覆寫） |
| `PORT` | `8001` | `8001` | 預設埠號（可用 `--port` 覆寫） |
| `RELOAD` | `true` | `true` | 程式變更時自動重新載入（可用 `--no-reload` 關閉） |
| `LOG_LEVEL` | `INFO` | `INFO` | 日誌層級；應用程式日誌寫入 `backend/logs/app.log` |
| `BASE_URL` | `http://backend:8001` | `http://localhost:8001` | 只有 `healthcheck.py` 使用，而且它讀的是行程環境變數，不會讀取 `.env` |

## 保留設定

下列設定可以寫進 `.env`，但 3.0.0 沒有任何程式路徑使用：

| 變數 | 程式預設值 | 說明 |
|---|---|---|
| `ENABLE_BATCH_ACCUMULATION` | `false` | 嵌入批次累積器的開關，目前未接上上傳流程 |
| `BATCH_ACCUMULATOR_SIZE` | `32` | 同上 |

## 已移除的設定

留在 `.env` 中會被忽略，可以直接刪除：

| 變數 | 移除版本 | 替代方式 |
|---|---|---|
| `HYBRID_ALPHA`、`NORMALIZATION` | 3.0.0 | 改用 `RRF_K` 的標準 RRF 融合 |
| `FINAL_THRESHOLD` | 3.0.0 | 改用 `RERANK_RELEVANCE_THRESHOLD` |
| `DOCUMENTS_PATH` | 3.0.0 | 片段改存資料庫 `rag_chunks` 表 |
| `ENABLE_AUTO_REINDEX`、`ENABLE_AUTO_REINDEX_TASK`、`REINDEX_HOURS` | 3.0.0 | 啟動時自動依資料庫校正索引，不再需要定時重建 |
| `TRANSFORMERS_CACHE`、`HUGGINGFACE_HUB_CACHE` | 3.0.0 | 改用 `HF_HOME` 或 `HF_HUB_CACHE` |
| `AZURE_OPENAI_API_VERSION` | 2.0.0 | 改用 Azure OpenAI v1 端點 |

## 領域設定檔

`DOMAIN_PROFILE_PATH` 指向的 JSON 檔（預設 `backend/config/domain_profile.json`）收納部署領域專屬的資料，啟動時以嚴格格式驗證：缺少欄位、多出未知欄位或出現空字串都會讓後端無法啟動。

```json
{
  "domain_words": ["補休", "育嬰留停", "免刷卡"],
  "record_date_fields": ["timestamp", "timestampTitle"],
  "summary_fallback": {
    "chat_member_noise_words": ["All", "收到", "好的"],
    "chat_topic_keywords": ["Agent", "部署", "會議"],
    "boilerplate_line_prefixes": ["copyright", "all rights reserved", "www."]
  }
}
```

| 欄位 | 用途 |
|---|---|
| `domain_words` | 加入 jieba 詞典的領域詞，讓 BM25 不會把專有名詞切碎；變更後 BM25 索引自動重建 |
| `record_date_fields` | 結構化記錄中代表發布日期的欄位名稱（內容格式為「欄位: 日期」）；`filter_and_count_records` 依日期篩選時只比對這些欄位，記錄沒有這些欄位時才比對全文 |
| `summary_fallback.chat_member_noise_words` | LLM 摘要失敗、改用規則摘要時，通訊紀錄中不應當成成員名稱的雜訊詞 |
| `summary_fallback.chat_topic_keywords` | 規則摘要偵測通訊紀錄主題時使用的關鍵字 |
| `summary_fallback.boilerplate_line_prefixes` | 以這些字首開頭（不分大小寫）的行視為頁尾、版權等雜訊 |

## 校準相關性門檻

`RERANK_RELEVANCE_THRESHOLD=0.2` 是以小型繁體中文語料得到的暫定值：完整問句的正例通常高於 0.9，但單一關鍵字查詢與同領域的反例會在 0.3 至 0.42 之間重疊（詳見 [ADR-0003](adr/0003-rrf-relevance-citations-and-tool-trust.md)）。上傳實際文件後，請用自己的問答集校準：

1. **準備問答集**：JSONL 格式，每行一題，`relevant_sources` 填應該命中的文件檔名；知識庫本來就沒有答案的題目填空陣列當作反例。格式見 [`backend/eval/retrieval_golden.example.jsonl`](../backend/eval/retrieval_golden.example.jsonl)。

   ```json
   {"query": "特休假的天數如何依年資計算？", "relevant_sources": ["員工手冊.pdf"]}
   {"query": "公司附近有推薦的午餐餐廳嗎？", "relevant_sources": []}
   ```

2. **比較多個門檻**：在 `backend/` 執行下列指令。評估在索引副本上唯讀執行，可以與後端同時運作；索引與資料庫不一致或斷詞簽章不符時會拒絕執行，請先啟動一次後端完成校正。

   ```bash
   python scripts/evaluate_retrieval.py --golden eval/retrieval_golden.jsonl --k 1 3 5 --relevance-thresholds 0.1 0.2 0.3 0.4
   ```

3. **判讀結果**：報表列出目前門檻的 MRR、hit@k、recall@k 與反例拒絕率，並以同一次重排結果比較每個候選門檻。門檻越高，反例拒絕率越高，但正例命中率可能下降；選擇在兩者間取得平衡的值。
4. **套用**：把選定的值寫進 `.env` 的 `RERANK_RELEVANCE_THRESHOLD`，重新啟動後端。

其他選項：`--min-mrr 0.6` 在 MRR 未達標時以結束碼 1 結束，適合放進 CI；`--output report.json` 輸出完整結果。

## 前端環境變數

前端不建立 `.env` 也能運作：API 位址預設為相對路徑 `/api`，由 Vite 開發伺服器（埠號 3000）代理到 `http://127.0.0.1:8001`，瀏覽器不會跨來源，後端也不必設定 CORS。

| 變數 | 未設定時 | 說明 |
|---|---|---|
| `VITE_API_BASE` | `/api` | API 位址。設為絕對網址（例如 `http://localhost:8001`）時，瀏覽器直接呼叫後端，後端的 `ALLOWED_ORIGINS` 必須包含前端來源；此值同時是 Vite `/api` 代理的目標。路徑結尾會自動補上 `/api` |
| `VITE_API_URL` | — | `VITE_API_BASE` 未設定時才使用，格式相同 |
| `PORT` | `3000` | Vite 開發伺服器埠號（`bun run preview` 固定為 3000） |
| `GENERATE_SOURCEMAP` | 輸出 | 建置時是否輸出 source map，設為 `false` 才關閉 |

`frontend/.env.example` 採用「直接呼叫」模式：`VITE_API_BASE=http://localhost:8001` 搭配 `PORT=3001`，這個來源正好在後端 `ALLOWED_ORIGINS` 的預設清單中。
