# AskMiao 設定參考

[繁體中文](configuration.md) | [English](configuration_en.md)

> 本文件逐一說明後端 `backend/.env` 與前端 `frontend/.env` 的每個設定、預設值與實際作用，適用於 **5.0.0**（從 4.0.0 升級見 [升級指南](upgrading.md#從-400-升級到-500)）。設定以 `backend/app/core/config.py` 的 `Settings` 為準，範本見 [`backend/.env.example`](../backend/.env.example)。

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
- [工具憑證加密](#工具憑證加密)
- [網路存取控制](#網路存取控制)
- [伺服器與執行環境](#伺服器與執行環境)
- [資源上限](#資源上限)
- [保留設定](#保留設定)
- [已移除的設定](#已移除的設定)
- [領域設定檔](#領域設定檔)
- [校準相關性門檻](#校準相關性門檻)
- [前端環境變數](#前端環境變數)

---

## 讀取規則

- **來源**：後端從 `backend/.env` 讀取設定（與啟動目錄無關），行程環境變數優先於 `.env`。不認得的鍵會被忽略，所以已移除的舊設定留在 `.env` 中不會出錯。
- **必填設定沒有預設值**：缺少任一項時，後端在啟動時就以 `Field required` 錯誤結束，並列出缺少的欄位。
- **數值範圍與格式**：`AGENT_MAX_TURNS ≥ 1`、`CONVERSATION_HISTORY_MESSAGES ≥ 0`、`RRF_K ≥ 1`、`0 ≤ RERANK_RELEVANCE_THRESHOLD ≤ 1`、`ANTHROPIC_MAX_TOKENS ≥ 1`，`LOGIN_MAX_FAILURES_PER_ACCOUNT`、`LOGIN_MAX_FAILURES_PER_ADDRESS`、`LOGIN_FAILURE_WINDOW_SECONDS`、`LOGIN_LOCKOUT_SECONDS` 皆須 ≥ 1，`TOOL_SECRETS_KEY` 必須是有效的 Fernet 金鑰；超出範圍或格式不符同樣無法啟動。
- **布林值**：`true` / `false`、`1` / `0`、`yes` / `no` 皆可。
- **相對路徑**：`DATA_DIR`、`UPLOAD_DIR`、`FAISS_INDEX_PATH`、`BM25_INDEX_DIR`、`METADATA_PATH`、`HF_HOME`、`HF_HUB_CACHE`、`SENTENCE_TRANSFORMERS_HOME`、`DOMAIN_PROFILE_PATH`、`JIEBA_DICTIONARY` 的相對路徑一律以 `backend/` 為基準。`DATABASE_URL` 不在此列，SQLite 的相對路徑依啟動目錄而定。
- **程式預設值與範本值**：下表的「程式預設值」是 `.env` 未設定時的值；「範本值」是 `backend/.env.example` 建議的值，兩者不同時以你的 `.env` 為準。

## 必填設定

下列 20 個設定沒有預設值，缺少任一項後端就無法啟動。

| 變數 | 範本值 | 說明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://askmiao_app:your_app_db_password_here@localhost:5432/chatbot` | 資料庫連線字串，詳見 [資料庫](#資料庫) |
| `ADMIN_API_KEY` | `your_admin_api_key_here` | 管理用 API 金鑰（設定驗證要求此值，目前沒有路由使用），請換成隨機字串 |
| `TOOL_SECRETS_KEY` | `your_tool_secrets_key_here` | 加密工具憑證的 Fernet 金鑰，啟動時驗證格式；範本值不是有效的金鑰，必須換成自行產生的金鑰（指令見下方），詳見 [工具憑證加密](#工具憑證加密) |
| `ALLOW_REGISTRATION` | `false` | 是否開放自行註冊，詳見 [註冊與建立帳號](#註冊與建立帳號) |
| `LOGIN_MAX_FAILURES_PER_ACCOUNT` | `5` | 同一登入識別的登入失敗門檻（≥ 1），詳見 [登入失敗節流](#登入失敗節流) |
| `LOGIN_MAX_FAILURES_PER_ADDRESS` | `20` | 同一來源位址的登入失敗門檻（≥ 1） |
| `LOGIN_FAILURE_WINDOW_SECONDS` | `900` | 計算登入失敗次數的視窗秒數（≥ 1） |
| `LOGIN_LOCKOUT_SECONDS` | `900` | 達到門檻後暫停登入的秒數（≥ 1） |
| `COOKIE_SECURE` | `false` | 重新整理權杖 Cookie 是否帶 `Secure` 屬性；以 HTTPS 提供服務時必須為 `true` |
| `HOST` | `127.0.0.1` | `python main.py` 的監聽位址，詳見 [伺服器與執行環境](#伺服器與執行環境) |
| `RELOAD` | `false` | 程式碼變更時自動重新載入，只在開發時設為 `true` |
| `ENABLE_API_DOCS` | `false` | 是否提供 `/docs`、`/redoc` 與 `/openapi.json` 互動式文件 |
| `ENABLE_WEB_SEARCH` | `true` | 是否提供聯網工具 |
| `AGENT_MAX_TURNS` | `5` | 單次提問的工具呼叫輪數上限 |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | 帶入的前文訊息數 |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | `web_fetch` 網域白名單 |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | 讀過知識庫後停用聯網工具 |
| `RRF_K` | `60` | RRF 融合常數 |
| `RERANK_RELEVANCE_THRESHOLD` | `0.2` | 重排機率門檻 |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | 領域設定檔路徑 |

`TOOL_SECRETS_KEY` 由每個部署自行產生，例如在已安裝後端相依套件的環境執行：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

使用 Claude 模型時，`ANTHROPIC_MAX_TOKENS` 也是必填（未設定時呼叫 Claude 會失敗，但不影響啟動）。

## LLM 供應商與模型

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `LLM_API_BASE` | `http://localhost:5000` | `http://localhost:11434` | Ollama 服務位址：呼叫 Ollama 模型（`/api/chat`）與查詢遠端模型清單（`/api/tags`）時使用 |
| `LLM_TIMEOUT` | `120` | `120` | LLM 呼叫逾時秒數，也用於 PDF OCR 的視覺模型呼叫；等待連線池名額另有固定的 15 秒上限（見 [資源上限](#資源上限)） |
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
3. 以上皆為空：向 `EXTERNAL_TAGS_URL`（或 `{LLM_API_BASE}/api/tags`）查詢遠端清單，例如本機 Ollama 已下載的模型。遠端查詢在執行緒中進行，結果（含失敗）快取 30 秒，同一時間只有一個查詢在進行。

`POST /api/chat/send` 指定的 `model_name` 必須在這份清單內（或等於 `MODEL_NAME`），否則回傳 `400`，避免以操作者的金鑰呼叫清單外的模型。

| 供應商 | 內建清單（5.0.0） |
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
- 無論白名單為何，`web_fetch` 都只能讀取使用者訊息或本次工具結果中以完整網址出現過的網址（兩邊都正規化成 httpx 的形式後逐字比對），並一律經過 SSRF 驗證。

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
| `DATA_DIR` | `data` | `data` | 索引與執行資料的根目錄；jieba 的詞典快取也放在其下的 `jieba_cache/`（不再使用系統暫存目錄） |
| `UPLOAD_DIR` | `data/uploads` | `data/uploads` | 上傳原始檔；重建索引時會優先從這裡重新擷取文字 |
| `FAISS_INDEX_PATH` | `data/faiss_index.bin` | 同左 | FAISS 向量索引（`IndexIDMap2`，以 chunk_id 為 id） |
| `BM25_INDEX_DIR` | `data/bm25_index` | 同左 | Whoosh BM25 索引目錄（含 `tokenizer_signature.json`） |
| `METADATA_PATH` | `data/index_metadata.pkl` | 同左 | 索引中繼資料，例如最後重建時間 |
| `MAX_FILE_SIZE_MB` | `50` | `10` | 知識庫單一上傳檔大小上限（MB）；也決定上傳請求的本文上限，見 [資源上限](#資源上限) |
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
| `backend/docker-compose.yml` 啟動的 PostgreSQL 17 | `postgresql+psycopg2://<POSTGRES_APP_USER>:<POSTGRES_APP_PASSWORD>@localhost:7690/chatbot`（容器只綁定 `127.0.0.1:7690`） |
| 自行架設的 PostgreSQL | `postgresql+psycopg2://<使用者>:<密碼>@<主機>:5432/<資料庫>`（建議使用非超級使用者，見下節） |

資料表在後端啟動時自動建立，缺少的新欄位（例如 `custom_api_tools.requires_approval`、`mcp_servers.requires_approval`、`users.tokens_valid_after`）也會在啟動時自動補上並回填，以明文存放的舊工具憑證也在啟動時改為加密（見 [工具憑證加密](#工具憑證加密)）。新建立的 SQLite 資料庫中，`users` 與 `documents` 以 `AUTOINCREMENT` 建立，刪除後的 id 不會被重用；既有 SQLite 資料表不會被改寫。`init_db.py` 是為舊版 PostgreSQL 資料庫補欄位與索引的相容腳本，SQLite 不需要執行（其中的 `ADD COLUMN IF NOT EXISTS` 語法 SQLite 不支援）。

### PostgreSQL 非超級使用者帳號

`backend/docker-compose.yml` 不內建任何密碼，啟動前必須在 `backend/.env` 或殼層環境設定下列三項，缺少任一項時 `docker compose` 拒絕啟動。這些變數只供 compose 使用，後端不讀取。

| 變數 | 範本值 | 說明 |
|---|---|---|
| `POSTGRES_PASSWORD` | 註解範例 | 超級使用者 `postgres` 的密碼，只供管理用途，後端不以此帳號連線 |
| `POSTGRES_APP_USER` | 註解範例 `askmiao_app` | 後端連線用的非超級使用者帳號 |
| `POSTGRES_APP_PASSWORD` | 註解範例 | 該帳號的密碼，請與 `POSTGRES_PASSWORD` 使用不同的隨機字串 |

`DATABASE_URL` 使用 `POSTGRES_APP_USER` 與 `POSTGRES_APP_PASSWORD`（`@`、`:`、`/` 等字元需百分比編碼）。容器埠只對本機回送位址開放，區網與公網都連不到。

建立新的資料卷時，容器依檔名順序執行 `10-init.sql`（`backend/init.sql`，建立資料表）與 `20-app-role.sh`（`backend/init-app-role.sh`）。後者建立 `POSTGRES_APP_USER`（`NOSUPERUSER`、`NOCREATEDB`、`NOCREATEROLE`）並設定密碼，授予資料庫的 `CONNECT` 與 `public` schema 的 `USAGE`、`CREATE`，再把 `public` 中的資料表交給它擁有。後端啟動時自行建立與修改資料表，這些權限就足夠；以非超級使用者連線時，SQL 注入無法以 `COPY ... TO PROGRAM` 執行系統指令或讀取伺服器檔案。

初始化腳本只在資料卷第一次建立時執行。使用既有資料卷時，以新的 `docker-compose.yml` 啟動容器後，在 `backend/` 執行一次下列指令，再把 `DATABASE_URL` 改為這組帳號。腳本可以重複執行，每次都會把該帳號的密碼設為容器中的 `POSTGRES_APP_PASSWORD`。

```bash
docker compose exec postgres bash /docker-entrypoint-initdb.d/20-app-role.sh
```

自行架設的 PostgreSQL 也建議比照 `backend/init-app-role.sh`，讓後端以只有上述權限的非超級使用者連線。

## 認證與權杖

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `ADMIN_API_KEY` | —（必填） | 佔位字串 | 設定驗證要求此值；目前沒有路由使用 `X-API-Key` 驗證，管理端點一律依資料庫中該帳號的 `is_admin` 判斷 |
| `ALLOW_REGISTRATION` | —（必填） | `false` | 是否開放以 `POST /api/auth/register` 自行註冊；`false` 時註冊回傳 `403`，帳號改以 `scripts/create_user.py` 建立，見 [註冊與建立帳號](#註冊與建立帳號) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | `30` | 存取權杖有效分鐘數 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | `7` | 重新整理權杖有效天數，也是 Cookie 的 `max-age` |
| `LOGIN_MAX_FAILURES_PER_ACCOUNT` | —（必填，≥ 1） | `5` | 同一登入識別在視窗內失敗達此次數後，暫停該識別的登入，見 [登入失敗節流](#登入失敗節流) |
| `LOGIN_MAX_FAILURES_PER_ADDRESS` | —（必填，≥ 1） | `20` | 同一來源位址在視窗內失敗達此次數後（不論嘗試哪些帳號），暫停該位址的登入 |
| `LOGIN_FAILURE_WINDOW_SECONDS` | —（必填，≥ 1） | `900` | 計算失敗次數的滑動視窗秒數 |
| `LOGIN_LOCKOUT_SECONDS` | —（必填，≥ 1） | `900` | 暫停登入的秒數，到期自動解除 |
| `COOKIE_SECURE` | —（必填） | `false` | 重新整理權杖 Cookie 的 `Secure` 屬性，`true` 時瀏覽器只經 HTTPS 送出此 Cookie。以 HTTPS 提供服務時必須設為 `true`，本機以 `http://localhost` 開發時可設為 `false`；不再依 `ENVIRONMENT` 推導 |
| `COOKIE_SAMESITE` | `lax` | — | 重新整理權杖 Cookie 的 `SameSite` 屬性 |

存取與重新整理權杖一律以 RS256 簽署，沒有其他演算法可選。RSA 金鑰對存放於 `backend/keys/jwt_private.pem` 與 `jwt_public.pem`，首次啟動時若不存在會自動產生（2048 位元，已列入 `.gitignore`；私鑰建立當下即為 `0600`，新建立的 `backend/keys/` 為 `0700`），因此後端帳號需能寫入 `backend/keys/`；金鑰無法載入或產生時，後端在任何 `ENVIRONMENT` 下都拒絕啟動。多台後端共用同一組使用者時，請讓它們使用同一組金鑰。

每次請求都會把存取權杖對應回資料庫中的帳號：帳號必須存在且啟用，`is_admin` 與角色取自資料庫而非權杖內容，簽發時間早於帳號 `tokens_valid_after` 的權杖一律無效（見 [變更密碼與權杖撤銷](#變更密碼與權杖撤銷)）。重新整理權杖只能使用一次，換發新權杖時舊的立即撤銷。

### 登入失敗節流

`POST /api/auth/login` 的每次失敗同時計入兩個計數：

- **登入識別**：登入時輸入的使用者名稱或電子郵件，不分大小寫、忽略前後空白；同一帳號以名稱與以電子郵件登入時各自計數。不存在的帳號同樣計數，回應與存在的帳號相同。
- **來源位址**：連線的來源 IP；設定 `FORWARDED_ALLOW_IPS` 時為反向代理轉送的用戶端 IP，見 [網路存取控制](#網路存取控制)。

在 `LOGIN_FAILURE_WINDOW_SECONDS` 秒內，同一識別失敗達 `LOGIN_MAX_FAILURES_PER_ACCOUNT` 次，或同一位址失敗達 `LOGIN_MAX_FAILURES_PER_ADDRESS` 次，該識別或位址的登入就暫停 `LOGIN_LOCKOUT_SECONDS` 秒。暫停期間的登入請求不檢查密碼，直接回傳 `429` 與 `Retry-After`（剩餘秒數），正確的密碼也不接受，並以 `LOGIN_THROTTLED` 寫入安全日誌；到期後自動解除並重新計數。登入成功只清除該識別的失敗紀錄，同一位址對其他帳號的失敗照常計數。暫停只影響登入，已簽發的權杖不受影響。

經由反向代理或 Vite 開發代理連線、又沒有設定 `FORWARDED_ALLOW_IPS` 時，所有使用者共用代理的位址，因此依位址的門檻要設得比依帳號的寬（範本為 `20` 與 `5`）。

計數保存在每個後端行程的記憶體中：後端重新啟動後歸零，多個後端行程之間也不共用，各自計數。追蹤的識別數與位址數有上限（見 [資源上限](#資源上限)），超過時最久沒有新失敗的先淘汰，其失敗紀錄與暫停一併清除。

### 註冊與建立帳號

所有帳號共用整個知識庫與已啟用的工具，部署在可公開連線的環境時請保持 `ALLOW_REGISTRATION=false`。

- `true`：任何能連到 API 的人都能以 `POST /api/auth/register` 建立一般使用者帳號。
- `false`：`POST /api/auth/register` 回傳 `403`，並以 `REGISTER_REJECTED` 寫入安全日誌。前端依 `GET /api/auth/registration`（不需登入，回傳 `{"enabled": false}`）隱藏登入頁的註冊入口，註冊頁改為顯示說明。

帳號（含第一位管理員）由管理員在 `backend/` 執行 `scripts/create_user.py` 建立：

```bash
python scripts/create_user.py --username alice --email alice@example.com
python scripts/create_user.py --username root --email root@example.com --admin
```

密碼以互動方式輸入兩次，不經命令列參數，因此不會留在殼層歷史與行程清單中；使用者名稱、電子郵件與密碼套用與自行註冊相同的規則，`--admin` 建立管理員。腳本以同一份 `backend/.env` 連線資料庫，資料表不存在時會先建立。

### 變更密碼與權杖撤銷

簽發時間早於帳號 `users.tokens_valid_after` 的存取與重新整理權杖一律無效。這個欄位在建立帳號時等於建立時間（帳號刪除後 id 被重用時，舊權杖不能沿用），變更密碼時更新為當下：`POST /api/auth/change-password` 或帶新密碼的 `PUT /api/auth/me` 成功後，該帳號先前簽發的所有權杖（含目前這一個與其他裝置上的）立即失效，被盜的重新整理權杖也無法再換發；回應會清除重新整理權杖 Cookie，所有工作階段都要以新密碼重新登入。既有資料庫在後端啟動時自動補上此欄位，並以 `created_at` 回填。

## 工具憑證加密

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `TOOL_SECRETS_KEY` | —（必填） | 佔位字串（不是有效的金鑰） | 加密自訂 API 工具與 MCP 伺服器憑證的 Fernet 金鑰，每個部署各自產生 |

啟動時驗證金鑰格式：必須是 Fernet 金鑰（以 URL-safe base64 編碼的 32 位元組，共 44 個字元）。範本的佔位字串無法通過驗證，沒換掉時後端拒絕啟動。產生金鑰：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- **加密範圍**：自訂 API 工具的 `headers`、`auth_config` 與 MCP 伺服器的 `env_vars`、`headers` 寫入資料庫前以此金鑰加密（存成 `fernet:` 開頭的內容），資料庫或備份外流時不會直接暴露憑證。舊版以明文存放的值在後端啟動時自動改為加密，不是 JSON 物件的舊值會被清空，需要重新輸入。
- **管理 API 的遮蔽**：工具與 MCP 伺服器的回應以 `••••••••` 取代秘密值，憑證寫入後不會再從 API 讀出。秘密值包括 `Accept`、`Accept-Encoding`、`Accept-Language`、`Cache-Control`、`Content-Type`、`User-Agent` 以外的標頭，`auth_config` 中的 `token`、`key_value`、`password`，以及 MCP 伺服器的所有環境變數；`key_name`、`key_in`、`username` 等設定照常顯示。更新時送出的內容取代整個欄位，其中仍為 `••••••••` 的項目沿用已儲存的值；沒有已儲存的值可沿用時回傳 `400`。
- **更換或遺失金鑰**：已儲存的憑證無法以其他金鑰解密。管理 API 對這些工具與 MCP 伺服器回傳 `credentials_unreadable: true`，無法解密的欄位為 `null`，請重新輸入憑證；在此之前，Agent 呼叫這些工具會失敗。請把 `TOOL_SECRETS_KEY` 與資料庫備份一起妥善保存：只還原資料庫而沒有原本的金鑰時，所有工具憑證都要重新輸入。

## 網路存取控制

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:3001,https://localhost:3001,http://127.0.0.1:3001,https://127.0.0.1:3001` | `http://localhost:3001,https://localhost:3001` | CORS 允許的來源（逗號分隔，允許攜帶 Cookie） |
| `DEVTUNNEL_URL` | 空 | 空 | 額外加入 CORS 白名單的一個來源，例如 Dev Tunnels 網址 |
| `RATE_LIMIT_ENABLED` | `true` | `true` | 是否啟用速率限制 |
| `RATE_LIMIT_PER_MINUTE` | `60` | `60` | 每個來源 IP 在 60 秒內的請求上限，超過回傳 `429` 與 `Retry-After` |
| `FORWARDED_ALLOW_IPS` | 空 | 註解範例 `127.0.0.1` | 信任其 `X-Forwarded-For` 的反向代理位址（交給 uvicorn 的 `forwarded_allow_ips`）；未設定時 uvicorn 不處理代理標頭 |

> [!NOTE]
> 速率限制與 [登入失敗節流](#登入失敗節流) 的依位址計數都以連線的來源 IP 計算。未設定 `FORWARDED_ALLOW_IPS` 時，用戶端自帶的 `X-Forwarded-For` 一律不採信，經由 Vite 開發代理或反向代理連線的所有使用者來源 IP 相同，會共用同一個額度與同一個登入失敗計數。
>
> 只有在後端前方的反向代理會「覆寫」`X-Forwarded-For`（例如 nginx 的 `proxy_set_header X-Forwarded-For $remote_addr;`）時，才把該代理的位址設為 `FORWARDED_ALLOW_IPS`，速率限制與登入失敗節流才會以真實用戶端 IP 計算。Vite 開發代理會原樣轉送用戶端自帶的標頭，**不可**為它設定此值，否則任何人都能偽造來源 IP 繞過速率限制與依位址的登入失敗節流。此設定只在以 `python main.py` 啟動時生效。

速率限制在每個後端行程的記憶體中計數，追蹤的位址數有上限（見 [資源上限](#資源上限)）。入侵偵測只寫入警報、不封鎖任何位址，速率限制超過時一律回傳 `429`，不會以 `403` 拒絕位址（舊版從未被填入的 IP 封鎖名單已移除）。

## 伺服器與執行環境

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `ENVIRONMENT` | `development` | `development` | 目前只改變啟動日誌中 CORS 模式的說明文字；Cookie 的 `Secure` 不再依此推導，改由必填的 `COOKIE_SECURE` 設定（RSA 金鑰無法載入時，任何環境都拒絕啟動） |
| `HOST` | —（必填） | `127.0.0.1` | `python main.py` 的監聽位址（可用 `--host` 覆寫）。只有本機或同一台主機上的反向代理連入時保持 `127.0.0.1`；容器或其他主機上的反向代理需要連入時才改為 `0.0.0.0` |
| `PORT` | `8001` | `8001` | 預設埠號（可用 `--port` 覆寫） |
| `RELOAD` | —（必填） | `false` | 程式碼變更時自動重新載入，只在開發時設為 `true`（可用 `--reload` 或 `--no-reload` 覆寫） |
| `ENABLE_API_DOCS` | —（必填） | `false` | 是否提供 `/docs`、`/redoc` 與 `/openapi.json` 互動式文件；這些頁面列出所有端點與參數，對外服務時請保持 `false`，此時三個路徑都不提供 |
| `LOG_LEVEL` | `INFO` | `INFO` | 日誌層級；應用程式日誌寫入 `backend/logs/app.log`，安全事件只寫入 `backend/logs/security.log`（兩者都依大小輪替）。`httpx` 與 `httpcore` 固定為 `WARNING`，完整請求網址（可能含查詢字串型 API 金鑰）不會寫進日誌 |
| `BASE_URL` | `http://backend:8001` | `http://localhost:8001` | 只有 `healthcheck.py` 使用，而且它讀的是行程環境變數，不會讀取 `.env` |

`HOST`、`PORT`、`RELOAD` 與 `FORWARDED_ALLOW_IPS` 只在以 `python main.py` 啟動時套用；以其他方式啟動（例如直接執行 `uvicorn main:app`）時不會套用，但 `HOST` 與 `RELOAD` 仍是必填。`python main.py` 啟動的 uvicorn 只在設定 `FORWARDED_ALLOW_IPS` 時處理代理標頭（`proxy_headers`），見 [網路存取控制](#網路存取控制)。

## 資源上限

下列上限是保護單一後端行程可用性與操作者付費用量的程式常數，**不是** `.env` 設定；集中定義於 [`backend/app/core/limits.py`](../backend/app/core/limits.py)（少數與單一模組綁定的常數定義在該模組中，表中註明）。調整時請修改原始碼並同步更新本節。

**請求與聊天**

| 常數 | 值 | 說明 |
|---|---|---|
| `MAX_REQUEST_BODY_BYTES` | 1 MiB | 一般 API 請求與所有未帶有效存取權杖的請求本文上限，超過回傳 `413`；`Content-Length` 超過時直接拒絕，分塊傳輸邊讀邊計數 |
| `MAX_CHAT_REQUEST_BODY_BYTES` | 約 27.7 MiB | `POST /api/chat/send` 的本文上限（附件總量 20 MiB 經 base64 膨脹 4/3 後再加 1 MiB）；只有帶著簽章有效的存取權杖時才放寬，否則仍為 1 MiB |
| 文件上傳本文上限 | `MAX_FILES_PER_UPLOAD` × `MAX_FILE_SIZE_MB` MiB + 1 MiB | `POST /api/documents/upload` 的本文上限（範本值 `MAX_FILE_SIZE_MB=10` 時為 101 MiB）；只有存取權杖簽章有效且其 `is_admin` 聲明為 `true` 時才放寬，其他請求仍為 1 MiB |
| `MAX_FILES_PER_UPLOAD` | 10 | 單次上傳的檔案數 |
| `MAX_CHAT_MESSAGE_CHARS` | 20,000 字元 | 單則聊天訊息長度，超過回傳 `422` |
| `MAX_CHAT_ATTACHMENTS` | 5 | 單則訊息的附件數 |
| `MAX_CHAT_ATTACHMENT_BYTES` | 15 MiB | 單一附件解碼後的大小；附件的 `data_url` 必須是 base64 編碼的 `data:` URL，遠端網址會被拒絕 |
| `MAX_CHAT_ATTACHMENTS_TOTAL_BYTES` | 20 MiB | 單則訊息所有附件解碼後的合計大小 |
| `MAX_ATTACHMENT_TEXT_CHARS` | 50,000 字元 | 每個附件放進模型脈絡的文字上限（超過的部分截斷），也是請求中附件 `content` 欄位的長度上限 |
| `MAX_USER_ATTACHMENT_STORAGE_BYTES` | 200 MiB | 每位使用者存在資料庫的附件總量，超過時送出訊息回傳 `413`；系統不會自動清除舊附件，刪除含附件的對話即可釋放 |
| `MAX_CONCURRENT_CHAT_STREAMS_PER_USER` | 2 | 每位使用者同時進行中的回答串流數，超過回傳 `429` |
| `MAX_LISTED_CONVERSATIONS`（`services/chat_service.py`） | 200 | `GET /api/chat/conversations` 只列最近更新的 200 段對話 |
| `LIST_PREVIEW_MESSAGES`（`services/chat_service.py`） | 5 | 對話清單中每段對話附帶的最近訊息數（不含附件本文） |
| `MAX_CONVERSATION_MESSAGES`（`services/chat_service.py`） | 500 | 讀取單段對話時最多回傳的最新訊息數 |

**工具與出站請求**

| 常數 | 值 | 說明 |
|---|---|---|
| `MAX_TOOL_RESULT_CHARS` | 20,000 字元 | 每次工具呼叫的結果放進模型脈絡前的上限，超過的部分截斷 |
| `MAX_TEXT_CLEANUP_CHARS` | 2,000,000 字元 | `web_fetch` 抽取文字前先截斷 HTML 的長度 |
| `MAX_DATE_RANGE_CHARS`、`MAX_TARGET_DATES`、`MAX_FILTER_RECORDS`（`rag/tools.py`） | 200 字元、93 天、50 筆 | `filter_and_count_records` 的 `date_range` 長度、展開後的日期數與回傳筆數（`limit` 超過時夾到 50） |
| `MAX_API_TOOL_RESPONSE_BYTES`（`api/api_tools.py`） | 1 MiB | 自訂 API 工具的回應本文上限，超過即中止讀取並回傳 `502` |
| `MAX_API_TOOL_REDIRECTS`（`api/api_tools.py`）、`MAX_MCP_HTTP_REDIRECTS`（`services/mcp_service.py`） | 5 次、5 次 | 自訂 API 工具與 HTTP MCP 手動跟隨轉址的次數上限：轉址回應的本文不讀取，每一跳都重新做 SSRF 檢查；HTTP MCP 只跟隨同一來源的轉址，自訂 API 工具轉址到其他來源時不轉送憑證標頭。整個呼叫（含轉址）另以該工具或伺服器的 `timeout` 設定為總時限，自訂 API 工具逾時回傳 `504` |
| `MAX_MCP_HTTP_RESPONSE_BYTES`（`services/mcp_service.py`） | 4 MiB | HTTP 傳輸 MCP 伺服器的單次回應上限 |
| `MAX_MCP_STDIO_LINE_BYTES`（`services/mcp_service.py`） | 4 MiB | `stdio` MCP 子行程單行 JSON-RPC 訊息的上限，與 HTTP 回應上限相同 |
| `MCP_STDERR_TAIL_BYTES`（`services/mcp_service.py`） | 2,048 位元組 | `stdio` 子行程的 stderr 持續讀出（避免管線寫滿而卡住），只保留最後這麼多位元組，子行程異常結束時寫入伺服器日誌 |
| `MAX_CONCURRENT_STDIO_PROCESSES`（`services/mcp_service.py`） | 4 | 同時存在的 `stdio` MCP 子行程數；等待空位最多到該伺服器的 `timeout` 設定，逾時即失敗 |
| `APPROVAL_TIMEOUT_SECONDS`（`rag/tool_approval.py`） | 300 秒 | 等待使用者核准工具呼叫的時間，逾時視為拒絕 |
| `DNS_RESOLVE_TIMEOUT_SECONDS`、`DNS_RESOLVER_MAX_WORKERS`（`core/ssrf_protection.py`） | 5 秒；8 條與 4 條執行緒 | SSRF 驗證的 DNS 查詢在兩個專用執行緒池中進行：`web_fetch` 的使用者網址用 8 條（`DnsPool.USER_URL`），自訂 API 工具、HTTP MCP 與 OpenAPI 規格網址用 4 條（`DnsPool.CONFIGURED_ENDPOINT`），慢速網域占滿前者時不影響後者；逾時視為無法解析 |
| `LLM_POOL_ACQUIRE_TIMEOUT_SECONDS`（`core/llm_client.py`） | 15 秒 | 等待 LLM 連線池名額的上限，與 `LLM_TIMEOUT` 分開，池被占滿時很快失敗 |
| `REMOTE_MODELS_CACHE_SECONDS`（`api/tags.py`） | 30 秒 | 遠端模型清單的快取時間（含失敗結果） |

**文件解析**

管理員上傳的知識庫文件與聊天附件各用一組 `ExtractionLimits`（`ADMIN_UPLOAD_EXTRACTION_LIMITS`、`CHAT_ATTACHMENT_EXTRACTION_LIMITS`）。任何登入的使用者都能送出附件，而附件文字最後只取 `MAX_ATTACHMENT_TEXT_CHARS` 字，因此附件的預算小得多：

| 項目 | 管理員上傳 | 聊天附件 |
|---|---|---|
| 送 Vision OCR 的 PDF 頁數（`MAX_PDF_OCR_PAGES`） | 不限 | 20 頁 |
| `.docx`、`.pptx`、`.xlsx` 解壓後的總大小 | 200 MiB（`MAX_OOXML_UNCOMPRESSED_BYTES`） | 64 MiB（`MAX_ATTACHMENT_OOXML_UNCOMPRESSED_BYTES`） |
| OOXML 的成員數（`MAX_OOXML_MEMBERS`） | 10,000 | 10,000 |
| `.docx`、`.pptx` 會被建成 DOM 的 XML 總量 | 200 MiB（同解壓總大小） | 8 MiB（`MAX_ATTACHMENT_OOXML_XML_BYTES`） |
| 交給 `json.loads` 做結構化降噪的 JSON 與程式碼長度 | 不限 | 2,000,000 字元（`MAX_ATTACHMENT_STRUCTURED_PARSE_CHARS`） |

| 常數 | 值 | 說明 |
|---|---|---|
| `MAX_OCR_PIXELS` | 25,000,000 像素 | OCR 時單頁點陣化的像素上限，超過時降低解析度 |
| `MAX_OOXML_COMPRESSION_RATIO` | 100 | 解壓後超過 10 MiB（`OOXML_RATIO_CHECK_MIN_BYTES`）的單一成員或整個檔案，壓縮比不可超過此值；兩組預算相同 |
| `MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS` | 2 | 整個行程同時解析的聊天附件數；與單檔預算相乘即為附件解析的記憶體上界 |

OOXML 的檢查在解析前進行，依 ZIP 成員宣告的大小計算。python-docx 與 python-pptx 會把 XML 部件整份建成 DOM（記憶體約為 XML 大小的 15 至 30 倍），哪些成員算進 XML 總量依 `[Content_Types].xml` 判定（另含 `.rels` 與該檔本身），改副檔名無法繞過；`.xlsx` 以串流讀取，不套用此項。超過任一項 OOXML 預算時，管理員上傳的該檔案上傳失敗；聊天附件則不解析，改告知模型附件超過解析上限、未讀取內容。超過長度的 JSON 與程式碼附件不做結構化降噪，只做線性的雜訊清除。

**帳號、日誌與偵測**

| 常數 | 值 | 說明 |
|---|---|---|
| `MAX_PASSWORD_CHARS` | 256 字元 | 註冊、登入與修改密碼時的密碼長度上限（Argon2 成本隨長度成長） |
| `MAX_LOGIN_IDENTIFIER_CHARS` | 254 字元 | 登入時使用者名稱或電子郵件的長度上限 |
| `MAX_CONCURRENT_PASSWORD_HASHES` | 4 | 同時進行的 Argon2 雜湊與驗證數，在執行緒中執行 |
| `MAX_TRACKED_LOGIN_ACCOUNTS` | 10,000 | [登入失敗節流](#登入失敗節流) 同時追蹤的登入識別數，最久沒有新失敗的先淘汰 |
| `MAX_REVOKED_TOKENS` | 100,000 | 行程內權杖撤銷名單的條目上限，滿了以後先淘汰最早到期的條目 |
| `MAX_LOG_FIELD_CHARS` | 200 字元 | 安全日誌中單一字串欄位（例如帳號名稱、User-Agent）的長度上限 |
| `LOG_FILE_MAX_BYTES`、`LOG_FILE_BACKUP_COUNT` | 10 MiB、5 份 | `app.log` 與 `security.log` 的輪替大小與保留份數 |
| `MAX_EVENTS_PER_ADDRESS` | 200 | 入侵偵測對未列入規則的事件類型，每個位址保留的事件數 |
| `MAX_TRACKED_ADDRESSES` | 10,000 | 入侵偵測、速率限制與登入失敗節流各自同時追蹤的位址數，最久未活動的先淘汰 |

## 保留設定

下列設定可以寫進 `.env`，但目前沒有任何程式路徑使用：

| 變數 | 程式預設值 | 說明 |
|---|---|---|
| `ENABLE_BATCH_ACCUMULATION` | `false` | 嵌入批次累積器的開關，目前未接上上傳流程 |
| `BATCH_ACCUMULATOR_SIZE` | `32` | 同上 |

## 已移除的設定

留在 `.env` 中會被忽略，可以直接刪除：

| 變數 | 移除版本 | 替代方式 |
|---|---|---|
| `JWT_SECRET_KEY`、`JWT_ALGORITHM` | 4.0.0 | 權杖一律以 `backend/keys/` 的 RSA 金鑰簽署 RS256，不再有 HS256 退路 |
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
| `VITE_API_BASE` | `/api` | API 位址。設為絕對網址（例如 `http://localhost:8001`）時，瀏覽器直接呼叫後端，後端的 `ALLOWED_ORIGINS` 必須包含前端來源；此值同時是 Vite `/api` 代理的目標。路徑結尾會自動補上 `/api`。建置時其來源會寫入 CSP 的 `connect-src`，變更後需要重新建置 |
| `VITE_API_URL` | — | `VITE_API_BASE` 未設定時才使用，格式相同；為絕對網址時，其來源同樣在建置時寫入 `connect-src` |
| `PORT` | `3000` | Vite 開發伺服器埠號（`bun run preview` 固定為 3000） |
| `GENERATE_SOURCEMAP` | 輸出 | 建置時是否輸出 source map，設為 `false` 才關閉 |

`frontend/.env.example` 採用「直接呼叫」模式：`VITE_API_BASE=http://localhost:8001` 搭配 `PORT=3001`，這個來源正好在後端 `ALLOWED_ORIGINS` 的預設清單中。

Vite 開發與預覽伺服器固定只監聽 `localhost`（`frontend/vite.config.js`，不是環境變數），並送出 `X-Frame-Options: DENY` 與 `Content-Security-Policy: frame-ancestors 'none'; img-src 'self' data: blob:`；`/__open-in-editor` 只回應本機回送位址。區網裝置需要使用時，請以 `bun run build` 建置後由正式的網頁伺服器提供，並在該伺服器送出相同的反框架標頭。

### 建置時的 CSP

`bun run build` 把 CSP 以 `<meta http-equiv="Content-Security-Policy">` 寫入 `index.html`（`frontend/vite.config.js`；開發伺服器需要內嵌的 HMR 腳本，因此只在建置時套用）：`default-src 'self'`；腳本與樣式只允許同源檔案，以及 `index.html` 內嵌腳本與樣式（反框架守衛、主題初始化）的 SHA-256 雜湊；圖片只允許 `'self'`、`data:` 與 `blob:`；`connect-src` 為 `'self'` 加上 `VITE_API_BASE`、`VITE_API_URL` 中絕對網址的來源；另有 `object-src 'none'`、`base-uri 'none'` 與 `form-action 'self'`。網頁伺服器沒有設定 CSP 時，被注入的 HTML 也無法執行腳本。

`<meta>` 無法設定 `frame-ancestors`，因此提供建置產物的網頁伺服器仍要送出反框架標頭（`X-Frame-Options: DENY` 或 `Content-Security-Policy: frame-ancestors 'none'`）。
