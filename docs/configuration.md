# AskMiao 設定參考

[繁體中文](configuration.md) | [English](configuration_en.md)

> 本文件逐一說明後端 `backend/.env` 與前端 `frontend/.env` 的每個設定、預設值與實際作用，適用於 **8.8.0**（從 8.7.0 升級見 [升級指南](upgrading.md#從-870-升級到-880)）。設定以 `backend/app/core/config.py` 的 `Settings` 為準，範本見 [`backend/.env.example`](../backend/.env.example)。

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
- [已移除的設定](#已移除的設定)
- [領域設定檔](#領域設定檔)
- [校準相關性門檻](#校準相關性門檻)
- [前端環境變數](#前端環境變數)

---

## 讀取規則

- **來源**：後端從 `backend/.env` 讀取設定（與啟動目錄無關），行程環境變數優先於 `.env`。不認得的鍵會被忽略，所以已移除的舊設定留在 `.env` 中不會出錯。
- **必填設定沒有預設值**：缺少任一項時，後端在啟動時就以 `Field required` 錯誤結束，並列出缺少的欄位。
- **數值範圍與格式**：`CONVERSATION_HISTORY_MESSAGES ≥ 0`、`RRF_K ≥ 1`、`0 ≤ RERANK_RELEVANCE_THRESHOLD ≤ 1`，`LOGIN_MAX_FAILURES_PER_ACCOUNT`、`LOGIN_MAX_FAILURES_PER_ADDRESS`、`LOGIN_FAILURE_WINDOW_SECONDS`、`LOGIN_LOCKOUT_SECONDS` 都須 ≥ 1，`OLLAMA_NUM_CTX` 與 `RERANKER_OPENVINO_MAX_LENGTH` 有設定時也須 ≥ 1，`TOOL_SECRETS_KEY` 必須是有效的 Fernet 金鑰；超出範圍或格式不符同樣無法啟動。
- **布林值**：`true` / `false`、`1` / `0`、`yes` / `no` 都可以。
- **相對路徑**：`DATA_DIR`、`UPLOAD_DIR`、`FAISS_INDEX_PATH`、`BM25_INDEX_DIR`、`METADATA_PATH`、`HF_HOME`、`HF_HUB_CACHE`、`SENTENCE_TRANSFORMERS_HOME`、`DOMAIN_PROFILE_PATH`、`JIEBA_DICTIONARY`、`SKILLS_DIR`、`LOG_DIR` 的相對路徑一律以 `backend/` 為基準。`DATABASE_URL` 不在此列，SQLite 的相對路徑依啟動目錄而定。
- **程式預設值與範本值**：下表的「程式預設值」是 `.env` 未設定時的值；「範本值」是 `backend/.env.example` 建議的值，兩者不同時以你的 `.env` 為準。

## 必填設定

下列 20 個設定沒有預設值，缺少任一項後端就無法啟動。

| 變數 | 範本值 | 說明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://askmiao_app:your_app_db_password_here@localhost:5432/chatbot` | 資料庫連線字串，詳見 [資料庫](#資料庫) |
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
| `LOG_DIR` | `logs` | `app.log` 與 `security.log` 的目錄，見 [伺服器與執行環境](#伺服器與執行環境) |
| `ENABLE_WEB_SEARCH` | `true` | 是否提供聯網工具 |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | 帶入的前文訊息數 |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | `web_fetch` 網域白名單 |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | 讀過知識庫後停用聯網工具 |
| `RRF_K` | `60` | RRF 融合常數 |
| `RERANK_RELEVANCE_THRESHOLD` | `0.02` | 重排機率門檻 |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | 領域設定檔路徑 |
| `SKILLS_DIR` | `data/skills` | Agent Skills 的技能檔案目錄，見 [儲存路徑與上傳](#儲存路徑與上傳) |

`TOOL_SECRETS_KEY` 由每個部署自行產生，例如在已安裝後端相依套件的環境執行：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## LLM 供應商與模型

聊天只使用帳號可用的 [API 連線](#api-連線)，文件摘要與掃描 PDF 的 OCR 使用管理員指定的 [系統模型](#系統模型)。`.env` 不放任何模型商的位址或金鑰，只有下列套用到所有 LLM 呼叫的設定：

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `LLM_TIMEOUT` | `120` | `120` | LLM 呼叫逾時秒數，套用到聊天、連線測試、文件摘要與 PDF OCR；等待連線池名額另有固定的 15 秒上限（見 [資源上限](#資源上限)） |
| `LLM_TAGS_TIMEOUT` | `10` | — | 「從 API 取得模型」查詢模型清單的逾時秒數 |
| `OLLAMA_TEMPERATURE` | 空 | `0.3` | 所有 Ollama 連線的 `temperature`，未設定時使用模型預設值 |
| `OLLAMA_NUM_PREDICT` | 空 | `2048` | 所有 Ollama 連線的 `num_predict`，未設定時使用模型預設值 |
| `OLLAMA_NUM_CTX` | 空 | 註解範例 | 所有 Ollama 連線的 `num_ctx`（上下文長度，≥ 1），未設定時使用模型預設值；檢索內容較長時預設值可能不夠 |

### API 連線

每個帳號對話時只能使用兩種連線，模型選單依連線分組：

- **個人連線**：帳號在「個人資料 → 我的 API 連線」自己建立，只有本人看得到、用得到。
- **共用連線**：管理員在「管理後台 → 共用 API 連線」建立，並指定可使用的帳號：所有帳號（包含之後自行註冊的帳號），或只限勾選的帳號。沒被指定的帳號在模型清單裡看不到它。

| 欄位 | 說明 |
|---|---|
| 供應商 | `openai`（OpenAI 或相容的 API）、`anthropic`、`gemini`、`foundry`、`ollama`、`vllm`；呼叫方式見 [供應商路由](#供應商路由) |
| API 位址 | 例如 `https://api.openai.com/v1`、`https://api.anthropic.com`、`https://<資源名稱>.services.ai.azure.com`、`https://ollama.com`、`http://<主機>:8000/v1`（vLLM） |
| API 金鑰 | Anthropic、Gemini、Foundry 必填，OpenAI 相容服務、Ollama 與 vLLM 選填；以 `TOOL_SECRETS_KEY` 加密存放，儲存後不會再從 API 讀出；編輯時留空即沿用原值，但變更供應商或 API 位址時不會沿用，需要重新輸入 |
| 模型 | 這個連線可選的模型名稱（Foundry 為部署名稱），最多 50 個 |
| 輸出 token 上限 | Claude 直接連 Anthropic 時選填：留空時使用 Models API 查到的模型輸出上限，有填時與它取較小值；Foundry 上的 Claude 部署查不到模型上限，必填。Claude 的思考也計入這個上限，設得太小時回答會被截斷。vLLM 選填，見 [連接 vLLM](#連接-vllm) |

新增連線時，表單依供應商預先帶入官方 API 位址與下列模型清單，可以再增刪：

| 供應商 | 預先帶入的模型（8.8.0） |
|---|---|
| OpenAI | `gpt-6.1-sol`、`gpt-6-sol`、`gpt-6-luna`、`gpt-6-astra`、`gpt-5.6-sol`、`gpt-5.6-luna`、`gpt-5.6-terra`、`gpt-5.4`、`gpt-5.4-mini` |
| Anthropic | `claude-opus-5-5`、`claude-fable-5-1`、`claude-sonnet-5-5`、`claude-haiku-5-5`、`claude-sonnet-5`、`claude-opus-5`、`claude-fable-5`、`claude-opus-4-8`、`claude-haiku-4-5` |
| Gemini | `gemini-4-argon`、`gemini-3.8-flash`、`gemini-3.6-flash`、`gemini-3.5-flash-lite`、`gemini-3.1-flash-lite` |

一般帳號的個人連線只能指向可從網際網路解析的公開位址：建立與修改時檢查，每次呼叫也經 SSRF 檢查並固定到核可的 IP（與自訂 API 工具相同，見 [ADR-0002](adr/0002-external-tools-and-outbound-safety.md)），內部網路的服務（例如本機的 Ollama 或 vLLM）請由管理員設為共用連線。管理員的個人連線與共用連線不受此限制。

刪除帳號時，該帳號的個人連線一併刪除，並從共用連線的名單移除。

### 系統模型

管理員在「管理後台 → 系統模型」替兩個用途各指定一條共用連線、其中一個模型與思考程度，存放在資料庫的 `system_models` 資料表：

| 用途 | 何時呼叫 | 未指定時 |
|---|---|---|
| 文件摘要 | 上傳文件、重新產生摘要，以及重建索引時替還沒有摘要的文件產生摘要 | 改用規則產生摘要，不呼叫模型 |
| 掃描 PDF 辨識（OCR） | 知識庫上傳、重建索引與聊天附件中，沒有文字層或文字判定為亂碼的 PDF 頁面；模型須支援圖片輸入 | 掃描頁標示為無可提取的文字；整份 PDF 都沒有文字時拒絕上傳 |

- 只能指定共用連線，費用算在該連線上。聊天附件的 OCR 也用這裡的模型，每份附件最多送 `MAX_PDF_OCR_PAGES` 頁（見 [資源上限](#資源上限)）。
- 思考程度必填，選項與聊天相同（`none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max`），依供應商對應後傳給模型，介面上停用該模型不支援的檔位。程度越高越慢：Ollama 上的思考模型（例如 qwen3.5、gemma4）不關閉思考時，產生一份摘要可能超過 `LLM_TIMEOUT`，小型本機模型建議選 `none`（Ollama 會送 `think: false`）。資料表在加入這個欄位前已有的指定，升級後為 `none`。
- 共用連線被刪除，或編輯後不再提供指定的模型時，該用途自動取消指定；連線的金鑰無法解密（例如更換了 `TOOL_SECRETS_KEY`）時視同未指定，並記錄警告。
- 端點見 [API 參考：系統模型](api.md#86-系統模型)。

### 供應商路由

每條 API 連線依它的供應商與模型名稱決定呼叫方式：

| 供應商 | 模型名稱 | 端點 |
|---|---|---|
| `foundry` | 以 `claude-` 開頭 | `{API 位址}/anthropic/v1/messages`，以 `x-api-key` 驗證；API 位址必須是 `*.services.ai.azure.com` |
| `foundry` | 以 `gpt-`、`o3`、`o4` 開頭（`gpt-oss`、`o3-mini` 除外） | `{API 位址}/openai/v1/responses` |
| `foundry` | 其他（以 `o1`、`gpt-oss`、`o3-mini` 開頭的模型，以及 Kimi、Mistral、Grok、DeepSeek、Llama 等 chat-completion 模型） | `{API 位址}/openai/v1/chat/completions`；名稱以 `gpt-`、`o1`、`o3`、`o4` 開頭時送 `reasoning_effort`，其他不送 |
| `anthropic` | 任何 | 官方 `anthropic` SDK（Messages API） |
| `gemini` | 任何 | `{API 位址}/v1beta/openai/chat/completions` |
| `openai` | 以 `gpt-6` 開頭 | `{API 位址}/responses` |
| `openai` | 其他 | `{API 位址}/chat/completions` |
| `ollama` | 任何 | `{API 位址}/api/chat` |
| `vllm` | 任何 | `{API 位址}/chat/completions`，見 [連接 vLLM](#連接-vllm) |

> [!NOTE]
> `reasoning_effort` 會依供應商對應後傳給模型（規則見 [API 參考](api.md)）；走 Chat Completions 的 `gpt-5.x` 模型（名稱含 `gpt-5.`）在帶工具呼叫時一律改送 `none`，以符合推理模型與工具呼叫的相容性限制；原始的 `gpt-5`、`gpt-5-mini`、`gpt-5-nano` 不接受 `none`、`xhigh`、`max`，選 `none` 時改送 `minimal`，選 `xhigh`、`max` 時改送 `high`，其他情況送使用者選擇的程度。

### 連接 vLLM

vLLM 以 `vllm serve` 提供 OpenAI 相容的 API，API 位址填到 `/v1`，例如 `http://<主機>:8000/v1`。研究助理每一輪都會帶工具定義，vLLM 必須加上 `--enable-auto-tool-choice` 與符合模型的 `--tool-call-parser` 才能接受；沒有加時，連線測試會回報「vLLM 伺服器沒有開啟工具呼叫」。會思考的模型另外加上 `--reasoning-parser`，思考內容才會和回答分開，研究助理只採用回答。例如：

```bash
vllm serve Qwen/Qwen3-8B --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3
```

- 需要 vLLM 0.23.0 以上。0.18.0 之前不接受 `none`（連線測試會失敗），0.21.0 之前不接受 `minimal`、`xhigh`、`max`，選到時回傳 `400`；0.21、0.22 雖然都接受，但 `none` 不會關閉思考。
- 思考程度直接以 `reasoning_effort` 送出（`none` 至 `max`），由 vLLM 依模型的對話範本套用，例如 Qwen3 選 `none` 時關閉思考。
- 輸出 token 上限選填，設定時以 `max_completion_tokens` 送出，思考內容也計入；留空時由 vLLM 依模型的上下文長度決定。有設定時，後端從 `{API 位址}/models` 讀取模型的上下文長度（`max_model_len`，每 5 分鐘重新讀取）；上限大於或等於上下文長度時不送出，改由 vLLM 依剩餘長度決定，避免 vLLM 回傳 `400`；讀不到上下文長度時照設定值送出。vLLM 0.23 會把這個上限從上下文長度預留給輸出，提示詞加上上限超過上下文長度時同樣回傳 `400`；帶著上限的請求收到 `400` 時，後端拿掉上限再送一次。
- vLLM 以 `--api-key` 啟動時，在連線填入同一把金鑰；沒有設定時金鑰留空。
- 模型名稱與 `vllm serve` 載入的模型（或 `--served-model-name`）相同，可以按「從 API 取得模型」讀取 `/v1/models`。
- vLLM 通常架在內部網路，請由管理員設為共用連線；一般帳號的個人連線只能連到公開位址。

## Agent 與聯網工具

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `ENABLE_WEB_SEARCH` | —（必填） | `true` | 同時控制 `web_search` 與 `web_fetch`；`false` 時兩者不會出現在工具清單中，呼叫也會被拒絕 |
| `CONVERSATION_HISTORY_MESSAGES` | —（必填，≥ 0） | `6` | 提問時從資料庫帶入的前文訊息數（使用者與助理訊息合計，前文一律從使用者訊息開始）；`0` 表示不帶前文 |
| `WEB_FETCH_ALLOWED_DOMAINS` | —（必填） | `*` | `web_fetch` 可讀取的網域，含子網域，逗號分隔；明確寫 `*` 才表示不限制 |
| `BLOCK_WEB_TOOLS_AFTER_KB` | —（必填） | `true` | 同一次提問中，知識庫工具回傳過內容後，拒絕之後的 `web_search` 與 `web_fetch` |
| `OLLAMA_API_KEY` | 空 | 註解範例 | Ollama 官方 Web Search / Web Fetch API 的金鑰。設定後 `web_search` 優先使用 Ollama API，失敗時改用 DuckDuckGo；`web_fetch` 只在 `WEB_FETCH_ALLOWED_DOMAINS` 為 `*` 時優先使用 Ollama API（失敗時改為直接抓取），設定白名單時一律直接抓取。不用於模型呼叫，Ollama Cloud 的金鑰請填在 API 連線 |
| `OLLAMA_SEARCH_ENDPOINT` | `https://ollama.com/api/web_search` | — | Ollama Web Search 端點 |
| `OLLAMA_FETCH_ENDPOINT` | `https://ollama.com/api/web_fetch` | — | Ollama Web Fetch 端點 |
| `DUCKDUCKGO_SEARCH_ENDPOINT` | `https://html.duckduckgo.com/html/` | — | `web_search` 的備援搜尋端點 |
| `DEFAULT_CONVERSATION_TITLE` | `新對話` | — | 新對話的暫時標題；第一則使用者訊息送出後改為該訊息的前 50 字，超過 50 字時再加上 `...` |

`WEB_FETCH_ALLOWED_DOMAINS` 的格式規則：

- 不可為空；不限制時請明確寫 `*`，且 `*` 不能與其他網域並列。
- 只填網域（小寫英數、連字號與點），不含 `https://` 與路徑，例如 `gov.tw,example.com`。
- 無論白名單為何，`web_fetch` 都只能讀取使用者訊息或本次工具結果中以完整網址出現過的網址（兩邊都正規化成 httpx 的形式後逐字比對），並一律經過 SSRF 驗證。

## 檢索、重排與切塊

每次檢索的流程：向量與 BM25 各取 `TOP_K` 筆 → RRF 融合取前 `RERANK_TOP_K` 筆（加上網址、貼文 ID、日期與 @帳號的精確比對結果）→ Cross-Encoder 重排 → 套用 `RERANK_RELEVANCE_THRESHOLD` → 取前 `FINAL_K` 筆。

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 同左 | 嵌入模型；更換後向量維度不同時，舊索引改名為 `*.mismatch.bak` 並依資料庫片段重新計算 |
| `RERANKER_MODEL` | `BAAI/bge-reranker-base` | 同左 | Cross-Encoder 重排模型，必要元件，載入失敗時後端無法啟動；以文件為主的部署可評估 `BAAI/bge-reranker-v2-m3`（反例拒絕好得多，但重排慢約 3 倍、短貼文排序較差，門檻約 0.01），比較見 [ADR-0007](adr/0007-han-ngram-bm25-and-passage-level-evaluation.md#5-重排模型比較維持-bge-reranker-base) |
| `TOP_K` | `30` | `30` | 向量與 BM25 各自取回的候選數 |
| `RRF_K` | —（必填，≥ 1） | `60` | RRF 分數 = Σ 1 / (`RRF_K` + 名次)，名次從 1 起算 |
| `RERANK_TOP_K` | `50` | `20` | 融合後送進重排的候選數；CPU 上每對約 0.2（300 字）至 0.4 秒（800 字） |
| `RERANK_WEIGHT` | `0.85` | `0.85` | 排序用混合分數 = `RERANK_WEIGHT` × 重排機率 + (1 − `RERANK_WEIGHT`) × 候選原分數；不影響門檻判斷 |
| `RERANK_RELEVANCE_THRESHOLD` | —（必填，0~1） | `0.02` | 重排機率低於此值的片段視為無關；精確比對到網址、貼文 ID、日期者不受限制；全部被濾掉時回報「知識庫中查無相關資料」 |
| `FINAL_K` | `8` | `8` | 通過門檻後最多保留的片段數 |
| `SIMILARITY_THRESHOLD` | `0.30` | `0.30` | 只用於單獨的向量搜尋（`vector_search`）；RRF 混合檢索的主流程不套用 |
| `CHUNK_SIZE` | `800` | `300` | 切塊長度（字元）；修改後需重建索引才會套用到既有文件 |
| `CHUNK_OVERLAP` | `150` | `100` | 相鄰片段的重疊字元數 |
| `DOMAIN_PROFILE_PATH` | —（必填） | `config/domain_profile.json` | 領域設定檔，格式見 [領域設定檔](#領域設定檔) |
| `JIEBA_DICTIONARY` | 空 | 註解範例 | 替換 jieba 主詞典，例如繁體較友善的 [`dict.txt.big`](https://raw.githubusercontent.com/fxsjy/jieba/master/extra_dict/dict.txt.big)；檔案不存在時無法啟動，變更後 BM25 索引自動重建 |

> [!TIP]
> Q&A 格式（`Q：…` / `A：…`）的一般文件會一問一答各成一個片段，不受 `CHUNK_SIZE` 限制。JSON、JSONL、YAML、CSV、XLSX 與 JS 宣告的結構化記錄逐筆成為獨立片段；超過 `CHUNK_SIZE` 的記錄會以整行欄位為單位切成多段，每段重複記錄標頭。`CHUNK_SIZE` 至少要容納記錄標頭，否則該記錄無法入庫。

## 運算裝置

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `FORCE_CPU` | `true` | `true` | 即使有 CUDA 也使用 CPU；CPU 模式的 PyTorch 執行緒數為 min(16, CPU 核心數) |
| `USE_FP16_QUANTIZATION` | `false` | `false` | 只在 CUDA 上生效：嵌入與重排模型改用 FP16 |
| `RERANKER_OPENVINO_DEVICE` | 空 | 註解範例 | 重排改用 OpenVINO 執行的裝置（`GPU`、`CPU`，Intel 內顯填 `GPU`）；留空使用 PyTorch。不支援 `NPU`（編譯失敗、無法啟動）。啟用後只載入重排模型的 tokenizer，不載入 PyTorch 模型。首次啟動會把模型轉成 OpenVINO IR，存在 `DATA_DIR/openvino_cache`，約需 10～30 秒，機器忙碌時可能要數分鐘。IR 檔名含模型檔案的指紋，模型更新後會自動重新轉換。每次依實際候選數送出 1～`RERANK_TOP_K` 組。GPU 以 FP16 推論，機率與 PyTorch 相差 0.01 以內、排名相同。Intel Core Ultra 7 155U 實測每 50 組：GPU 約 1.5～2.8 秒（視機器溫度與負載），CPU 約 7.6 秒，PyTorch CPU 約 13 秒。GPU 每遇到一種新的候選數，第一次要多花約 0.3 秒編譯；編譯結果會快取在同一個資料夾，重新啟動後會比較快 |
| `RERANKER_OPENVINO_MAX_LENGTH` | 空 | 註解範例 | 設定 `RERANKER_OPENVINO_DEVICE` 時必填（≥ 1）：每組「查詢 + 片段」的 token 長度，不足補齊、超過截斷；不得大於重排模型的上限（`bge-reranker-base` 為 512），否則啟動失敗 |
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
| `DATA_DIR` | `data` | `data` | 索引與執行資料的根目錄；jieba 的詞典快取也放在這個目錄下的 `jieba_cache/`（不再使用系統暫存目錄） |
| `UPLOAD_DIR` | `data/uploads` | `data/uploads` | 上傳原始檔；重建索引時會優先從這裡重新擷取文字 |
| `SKILLS_DIR` | —（必填） | `data/skills` | 管理員在「AI 工具」頁上傳的 Agent Skills，每個技能一個子目錄 `SKILLS_DIR/<name>/`；啟動時清除安裝中斷留下的 `.tmp-*`、`.old-*` 目錄 |
| `FAISS_INDEX_PATH` | `data/faiss_index.bin` | 同左 | FAISS 向量索引（`IndexIDMap2`，以 chunk_id 為 id） |
| `BM25_INDEX_DIR` | `data/bm25_index` | 同左 | Whoosh BM25 索引目錄（含 `tokenizer_signature.json`） |
| `METADATA_PATH` | `data/index_metadata.json` | 同左 | 索引中繼資料（JSON），例如最後重建時間 |
| `MAX_FILE_SIZE_MB` | `50` | `10` | 知識庫單一上傳檔大小上限（MB）；也決定上傳請求的本文上限，見 [資源上限](#資源上限)。以 `deploy/` 的 Docker Compose 部署時，nginx 只接受 120 MiB 以內的請求本文，此值大於 11 時超過 120 MiB 的上傳會先被 nginx 以 `413` 拒絕，見 [Docker Compose 部署（deploy/.env）](#docker-compose-部署deployenv) |
| `UPLOADS_WATCHER_INTERVAL` | `30` | `30` | 背景檢查上傳檔是否遺失的間隔秒數；檔案遺失只記一次警告，不會刪除任何資料 |

## 資料庫

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `DATABASE_URL` | —（必填） | PostgreSQL 範例 | SQLAlchemy 連線字串 |
| `DB_POOL_SIZE` | `20` | `20` | 連線池大小（PostgreSQL 等非 SQLite 資料庫；SQLite 固定為 5） |
| `DB_MAX_OVERFLOW` | `40` | `40` | 連線池額滿時可再額外建立的連線數（SQLite 固定為 10） |
| `DB_POOL_RECYCLE` | `3600` | — | 連線回收秒數 |
| `DB_POOL_PRE_PING` | `true` | — | 取用連線前先檢查（只用於非 SQLite） |
| `SQLALCHEMY_ECHO` | `false` | — | 在日誌輸出 SQL |

常見的 `DATABASE_URL`：

| 情境 | 連線字串 |
|---|---|
| SQLite（零依賴） | `sqlite:///./chatbot.db`（相對路徑依啟動目錄而定，在 `backend/` 啟動即為 `backend/chatbot.db`） |
| `backend/docker-compose.yml` 啟動的 PostgreSQL 17 | `postgresql+psycopg2://<POSTGRES_APP_USER>:<POSTGRES_APP_PASSWORD>@localhost:7690/chatbot`（容器只綁定 `127.0.0.1:7690`） |
| 自行架設的 PostgreSQL | `postgresql+psycopg2://<使用者>:<密碼>@<主機>:5432/<資料庫>`（建議使用非超級使用者，見下節） |

後端啟動時會自動建立資料表、補上並回填缺少的新欄位（例如 `custom_api_tools.requires_approval`、`mcp_servers.requires_approval`、`users.tokens_valid_after`），並把以明文存放的舊工具憑證改為加密（見 [工具憑證加密](#工具憑證加密)）。新建立的 SQLite 資料庫中，`users`、`documents`、`rag_chunks` 與 `llm_connections` 以 `AUTOINCREMENT` 建立，刪除後的 id 不會被重用；既有 SQLite 資料表不會被改寫。`init_db.py` 是為舊版 PostgreSQL 資料庫補欄位與索引的相容腳本，SQLite 不需要執行（SQLite 不支援腳本中的 `ADD COLUMN IF NOT EXISTS` 語法）。

### PostgreSQL 非超級使用者帳號

`backend/docker-compose.yml` 不內建任何密碼，啟動前必須在 `backend/.env` 或殼層環境設定下列三項，缺少任一項時 `docker compose` 拒絕啟動。這些變數只供 compose 使用，後端不讀取。

| 變數 | 範本值 | 說明 |
|---|---|---|
| `POSTGRES_PASSWORD` | 註解範例 | 超級使用者 `postgres` 的密碼，只供管理用途，後端不以此帳號連線 |
| `POSTGRES_APP_USER` | 註解範例 `askmiao_app` | 後端連線用的非超級使用者帳號 |
| `POSTGRES_APP_PASSWORD` | 註解範例 | 該帳號的密碼，請與 `POSTGRES_PASSWORD` 使用不同的隨機字串 |

`DATABASE_URL` 使用 `POSTGRES_APP_USER` 與 `POSTGRES_APP_PASSWORD`（`@`、`:`、`/` 等字元需百分比編碼）。容器埠只對本機回送位址開放，區網與公網都連不到。

建立新的 volume 時，容器依檔名順序執行 `10-init.sql`（`backend/init.sql`，建立資料表）與 `20-app-role.sh`（`backend/init-app-role.sh`）。後者建立 `POSTGRES_APP_USER`（`NOSUPERUSER`、`NOCREATEDB`、`NOCREATEROLE`）並設定密碼，授予資料庫的 `CONNECT` 與 `public` schema 的 `USAGE`、`CREATE`，再把 `public` 中的資料表交給它擁有。後端啟動時自行建立與修改資料表，這些權限就足夠；以非超級使用者連線時，SQL 注入無法以 `COPY ... TO PROGRAM` 執行系統指令或讀取伺服器檔案。

初始化腳本只在 volume 第一次建立時執行。使用既有 volume 時，以新的 `docker-compose.yml` 啟動容器後，在 `backend/` 執行一次下列指令，再把 `DATABASE_URL` 改為這組帳號。腳本可以重複執行，每次都會把該帳號的密碼設為容器中的 `POSTGRES_APP_PASSWORD`。

```bash
docker compose exec postgres bash /docker-entrypoint-initdb.d/20-app-role.sh
```

自行架設的 PostgreSQL 也建議比照 `backend/init-app-role.sh`，讓後端以只有上述權限的非超級使用者連線。

## 認證與權杖

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `ALLOW_REGISTRATION` | —（必填） | `false` | 是否開放以 `POST /api/auth/register` 自行註冊；`false` 時註冊回傳 `403`，帳號改以 `scripts/create_user.py` 建立，見 [註冊與建立帳號](#註冊與建立帳號) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | `30` | 存取權杖有效分鐘數 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | `7` | 重新整理權杖有效天數，也是 Cookie 的 `max-age` |
| `LOGIN_MAX_FAILURES_PER_ACCOUNT` | —（必填，≥ 1） | `5` | 同一登入識別在視窗內失敗達此次數後，暫停該識別的登入，見 [登入失敗節流](#登入失敗節流) |
| `LOGIN_MAX_FAILURES_PER_ADDRESS` | —（必填，≥ 1） | `20` | 同一來源位址在視窗內失敗達此次數後（不論嘗試哪些帳號），暫停該位址的登入 |
| `LOGIN_FAILURE_WINDOW_SECONDS` | —（必填，≥ 1） | `900` | 計算失敗次數的滑動視窗秒數 |
| `LOGIN_LOCKOUT_SECONDS` | —（必填，≥ 1） | `900` | 暫停登入的秒數，到期自動解除 |
| `COOKIE_SECURE` | —（必填） | `false` | 重新整理權杖 Cookie 的 `Secure` 屬性，`true` 時瀏覽器只經 HTTPS 送出此 Cookie。以 HTTPS 提供服務時必須設為 `true`，本機以 `http://localhost` 開發時可設為 `false`；不再依 `ENVIRONMENT` 推導 |
| `COOKIE_SAMESITE` | `lax` | — | 重新整理權杖 Cookie 的 `SameSite` 屬性 |

存取與重新整理權杖一律以 RS256 簽署，沒有其他演算法可選。RSA 金鑰對存放在 `backend/keys/jwt_private.pem` 與 `jwt_public.pem`，首次啟動時若不存在會自動產生（2048 位元，已列入 `.gitignore`；私鑰建立當下即為 `0600`，新建立的 `backend/keys/` 為 `0700`），因此後端帳號需能寫入 `backend/keys/`；金鑰無法載入或產生時，後端在任何 `ENVIRONMENT` 下都拒絕啟動。多台後端共用同一組使用者時，請讓它們使用同一組金鑰。

每次請求都會把存取權杖對應回資料庫中的帳號：帳號必須存在且啟用，`is_admin` 與角色取自資料庫而非權杖內容，簽發時間早於帳號 `tokens_valid_after` 的權杖一律無效（見 [變更密碼與權杖撤銷](#變更密碼與權杖撤銷)）。重新整理權杖只能使用一次，換發新權杖時舊的立即撤銷。

### 登入失敗節流

`POST /api/auth/login` 的每次失敗同時計入兩個計數：

- **登入識別**：登入時輸入的使用者名稱或電子郵件，不分大小寫、忽略前後空白；同一帳號以名稱與以電子郵件登入時各自計數。不存在的帳號同樣計數，回應與存在的帳號相同。
- **來源位址**：連線的來源 IP；設定 `FORWARDED_ALLOW_IPS` 時為反向代理轉送的用戶端 IP，見 [網路存取控制](#網路存取控制)。

在 `LOGIN_FAILURE_WINDOW_SECONDS` 秒內，同一識別失敗達 `LOGIN_MAX_FAILURES_PER_ACCOUNT` 次，或同一位址失敗達 `LOGIN_MAX_FAILURES_PER_ADDRESS` 次，該識別或位址的登入就暫停 `LOGIN_LOCKOUT_SECONDS` 秒。暫停期間的登入請求不檢查密碼，直接回傳 `429` 與 `Retry-After`（剩餘秒數），正確的密碼也不接受，並以 `LOGIN_THROTTLED` 寫入安全日誌；到期後自動解除並重新計數。登入成功只清除該識別的失敗紀錄，同一位址對其他帳號的失敗照常計數。暫停只影響登入，已簽發的權杖不受影響。

經由反向代理或 Vite 開發代理連線、又沒有設定 `FORWARDED_ALLOW_IPS` 時，所有使用者共用代理的位址，因此依位址的門檻要設得比依帳號的寬（範本為 `20` 與 `5`）。

計數保存在每個後端行程的記憶體中：後端重新啟動後歸零，多個後端行程之間也不共用，各自計數。追蹤的識別數與位址數有上限（見 [資源上限](#資源上限)），超過時最久沒有新失敗的先淘汰，它的失敗紀錄與暫停一併清除。

### 註冊與建立帳號

自行註冊的帳號只能使用自己設定的 API 連線與管理員開放給它的共用連線，不會用到 `.env` 的金鑰（見 [API 連線](#api-連線)）。但所有帳號仍共用整個知識庫與已啟用的工具（自訂 API 工具與 MCP 以營運者的憑證呼叫），部署在可公開連線的環境時，請確認這些內容可以讓任何註冊者使用後再開放。

- `true`：任何能連到 API 的人都能以 `POST /api/auth/register` 建立一般使用者帳號。
- `false`：`POST /api/auth/register` 回傳 `403`，並以 `REGISTER_REJECTED` 寫入安全日誌。前端依 `GET /api/auth/registration`（不需登入，回傳 `{"enabled": false}`）隱藏登入頁的註冊入口，註冊頁改為顯示說明。

有了第一位管理員之後，其他帳號可以在「管理後台 → 使用者管理」新增，也可以在那裡替帳號重設密碼。第一位管理員（或沒有登入介面時）由管理員在 `backend/` 執行 `scripts/create_user.py` 建立：

```bash
python scripts/create_user.py --username alice --email alice@example.com
python scripts/create_user.py --username root --email root@example.com --admin
```

密碼以互動方式輸入兩次，不經命令列參數，因此不會留在殼層歷史與行程清單中；使用者名稱、電子郵件與密碼套用與自行註冊相同的規則，`--admin` 建立管理員。腳本以同一份 `backend/.env` 連線資料庫，資料表不存在時會先建立。

### 變更密碼與權杖撤銷

簽發時間早於帳號 `users.tokens_valid_after` 的存取與重新整理權杖一律無效。這個欄位在建立帳號時等於建立時間（帳號刪除後 id 被重用時，舊權杖不能沿用），變更密碼時更新為當下：`POST /api/auth/change-password` 成功後，該帳號先前簽發的所有權杖（含目前這一個與其他裝置上的）立即失效，被盜的重新整理權杖也無法再換發；回應會清除重新整理權杖 Cookie，所有工作階段都要以新密碼重新登入。既有資料庫在後端啟動時自動補上此欄位，並以 `created_at` 回填。

## 工具憑證加密

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `TOOL_SECRETS_KEY` | —（必填） | 佔位字串（不是有效的金鑰） | 加密自訂 API 工具與 MCP 伺服器憑證的 Fernet 金鑰，每個部署各自產生 |

啟動時驗證金鑰格式：必須是 Fernet 金鑰（以 URL-safe base64 編碼的 32 位元組，共 44 個字元）。範本的佔位字串無法通過驗證，沒換掉時後端拒絕啟動。產生金鑰：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- **加密範圍**：自訂 API 工具的 `headers`、`auth_config` 與 MCP 伺服器的 `env_vars`、`headers`、`oauth_config`、`oauth_tokens` 寫入資料庫前以此金鑰加密（存成 `fernet:` 開頭的內容），資料庫或備份外流時不會直接暴露憑證。舊版以明文存放的值在後端啟動時自動改為加密，不是 JSON 物件的舊值會被清空，需要重新輸入。
- **管理 API 的遮蔽**：工具與 MCP 伺服器的回應以 `••••••••` 取代秘密值，憑證寫入後不會再從 API 讀出。秘密值包括 `Accept`、`Accept-Encoding`、`Accept-Language`、`Cache-Control`、`Content-Type`、`User-Agent` 以外的標頭，`auth_config` 中的 `token`、`key_value`、`password`、`client_secret`，MCP 伺服器的所有環境變數與 OAuth `client_secret`（OAuth 權杖不會出現在回應中）；`key_name`、`key_in`、`username` 等設定照常顯示。更新時送出的內容取代整個欄位，其中仍為 `••••••••` 的項目沿用已儲存的值；沒有已儲存的值可沿用時回傳 `400`。
- **更換或遺失金鑰**：已儲存的憑證無法以其他金鑰解密。管理 API 對這些工具與 MCP 伺服器回傳 `credentials_unreadable: true`，無法解密的欄位為 `null`，請重新輸入憑證；在此之前，Agent 呼叫這些工具會失敗。請把 `TOOL_SECRETS_KEY` 與資料庫備份一起妥善保存：只還原資料庫而沒有原本的金鑰時，所有工具憑證都要重新輸入。

## 網路存取控制

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:3001,https://localhost:3001,http://127.0.0.1:3001,https://127.0.0.1:3001` | `http://localhost:3001,https://localhost:3001` | CORS 允許的來源（逗號分隔，允許攜帶 Cookie） |
| `DEVTUNNEL_URL` | 空 | 空 | 額外加入 CORS 白名單的一個來源，例如 Dev Tunnels 網址 |
| `RATE_LIMIT_ENABLED` | `true` | `true` | 是否啟用速率限制 |
| `RATE_LIMIT_PER_MINUTE` | `60` | `60` | 每個來源 IP 在 60 秒內的請求上限，超過回傳 `429` 與 `Retry-After` |
| `FORWARDED_ALLOW_IPS` | 空 | 註解範例 `127.0.0.1` | 反向代理的位址，後端信任這些位址送來的 `X-Forwarded-For`（交給 uvicorn 的 `forwarded_allow_ips`）；未設定時 uvicorn 不處理代理標頭 |

> [!NOTE]
> 速率限制與 [登入失敗節流](#登入失敗節流) 的依位址計數都以連線的來源 IP 計算。未設定 `FORWARDED_ALLOW_IPS` 時，用戶端送來的 `X-Forwarded-For` 一律不採信，經由 Vite 開發代理或反向代理連線的所有使用者來源 IP 相同，會共用同一個額度與同一個登入失敗計數。
>
> 只有在後端前方的反向代理會「覆寫」`X-Forwarded-For`（例如 nginx 的 `proxy_set_header X-Forwarded-For $remote_addr;`）時，才把該代理的位址設為 `FORWARDED_ALLOW_IPS`，速率限制與登入失敗節流才會以真實用戶端 IP 計算。Vite 開發代理會原樣轉送用戶端送來的標頭，**不可**為它設定此值，否則任何人都能偽造來源 IP 繞過速率限制與依位址的登入失敗節流。此設定只在以 `python main.py` 啟動時生效。

速率限制在每個後端行程的記憶體中計數，追蹤的位址數有上限（見 [資源上限](#資源上限)）。速率限制超過時一律回傳 `429`，不會以 `403` 拒絕位址（舊版從未被填入的 IP 封鎖名單已移除）。同一個來源 IP 在一個視窗（60 秒）內只在第一次被擋時寫一筆警告（含路徑），視窗結束時再寫一筆被擋次數與各路徑的次數；每個被擋的請求仍會出現在存取日誌（`status=429`）。

## 伺服器與執行環境

| 變數 | 程式預設值 | 範本值 | 說明 |
|---|---|---|---|
| `ENVIRONMENT` | `development` | `development` | 目前只改變啟動日誌中 CORS 模式的說明文字；Cookie 的 `Secure` 不再依此推導，改由必填的 `COOKIE_SECURE` 設定（RSA 金鑰無法載入時，任何環境都拒絕啟動） |
| `HOST` | —（必填） | `127.0.0.1` | `python main.py` 的監聽位址（可用 `--host` 覆寫）。只有本機或同一台主機上的反向代理連入時保持 `127.0.0.1`；容器或其他主機上的反向代理需要連入時才改為 `0.0.0.0` |
| `PORT` | `8001` | `8001` | 預設埠號（可用 `--port` 覆寫） |
| `RELOAD` | —（必填） | `false` | 程式碼變更時自動重新載入，只在開發時設為 `true`（可用 `--reload` 或 `--no-reload` 覆寫） |
| `ENABLE_API_DOCS` | —（必填） | `false` | 是否提供 `/docs`、`/redoc` 與 `/openapi.json` 互動式文件；這些頁面列出所有端點與參數，對外服務時請保持 `false`，此時三個路徑都不提供 |
| `LOG_LEVEL` | `INFO` | `INFO` | 日誌層級，可填 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`（不分大小寫），其他值會讓後端拒絕啟動。這個層級套用在主控台與 `app.log` 的輸出上，自行把層級設成 `DEBUG` 的第三方套件（例如 jieba）也一樣受限。`INFO` 會記錄每個 `/api` 請求的存取紀錄、模型呼叫與工具呼叫，設為 `WARNING` 時只剩失敗、逾時與速率限制等警告。應用程式日誌寫入 `LOG_DIR/app.log`，安全事件只寫入 `LOG_DIR/security.log`（兩者格式相同、都依大小輪替）。`httpx` 與 `httpcore` 固定為 `WARNING`，完整請求網址（可能含查詢字串型 API 金鑰）不會寫進日誌。格式與欄位見 [架構說明：日誌與請求追蹤](architecture.md#日誌與請求追蹤) |
| `LOG_DIR` | —（必填） | `logs` | 日誌目錄，相對路徑以 `backend/` 為基準，不存在時自動建立；`app.log` 與 `security.log` 都在第一筆紀錄寫入時才開啟。後端測試（pytest）的安全事件一律寫到該次測試的暫存目錄，不會寫進這裡。Windows 上正在開啟的檔案無法改名，同時執行多個後端（例如另一組測試用的後端）時請各自設定不同的 `LOG_DIR`，否則到達輪替大小時無法輪替，紀錄會遺失 |

`HOST`、`PORT`、`RELOAD` 與 `FORWARDED_ALLOW_IPS` 只在以 `python main.py` 啟動時套用；以其他方式啟動（例如直接執行 `uvicorn main:app`）時不會套用，但 `HOST` 與 `RELOAD` 仍是必填。`python main.py` 啟動的 uvicorn 只在設定 `FORWARDED_ALLOW_IPS` 時處理代理標頭（`proxy_headers`），見 [網路存取控制](#網路存取控制)。

### Docker Compose 部署（deploy/.env）

以 `deploy/docker-compose.yml` 部署時，compose 的變數與後端容器的環境變數（`env_file`）都來自 `deploy/.env`，後端容器以 `python main.py` 啟動。逐步說明見 [部署指南](deployment.md)。

`deploy/docker-compose.yml` 不內建任何密碼與網路設定，下列變數缺少任一項時 `docker compose` 拒絕啟動：

| 變數 | 說明 |
|---|---|
| `POSTGRES_PASSWORD`、`POSTGRES_APP_USER`、`POSTGRES_APP_PASSWORD` | 同 [PostgreSQL 非超級使用者帳號](#postgresql-非超級使用者帳號) |
| `WEB_PORT` | 主機上對應到 `web`（nginx）容器 80 埠的連接埠 |
| `WEB_CONTAINER_IP` | `web` 容器在 compose 網路中的固定 IP |
| `NETWORK_SUBNET` | compose 網路 `askmiao-net` 的子網路；請選不與公司內網、VPN 或主機上其他 Docker 網路重疊的網段 |

`deploy/gen-env.sh` 產生這份檔案：必須以環境變數提供 `PUBLIC_ORIGIN`、`WEB_PORT`、`NETWORK_SUBNET`、`WEB_CONTAINER_IP`，`deploy/.env` 已存在時拒絕覆寫。腳本複製 `backend/.env.example`，再在檔尾附加下列值：

| 變數 | 寫入的值 |
|---|---|
| `HOST` | `0.0.0.0`，讓 nginx 容器連入 |
| `ENVIRONMENT` | `production`；目前只改變啟動日誌中 CORS 模式的說明文字（`backend/app/middleware.py`） |
| `COOKIE_SECURE` | `PUBLIC_ORIGIN` 以 `https://` 開頭時為 `true`，否則為 `false` |
| `TOOL_SECRETS_KEY` | 隨機產生的 Fernet 金鑰 |
| `POSTGRES_PASSWORD`、`POSTGRES_APP_USER`、`POSTGRES_APP_PASSWORD` | 隨機產生的兩組密碼；帳號為 `askmiao_app` |
| `DATABASE_URL` | 以上述帳號連到 `postgres:5432` 的 `chatbot` 資料庫 |
| `ALLOWED_ORIGINS` | `PUBLIC_ORIGIN` |
| `FORWARDED_ALLOW_IPS` | `WEB_CONTAINER_IP`；容器內的 nginx 以 `X-Forwarded-For: $remote_addr` 覆寫該標頭，速率限制與登入失敗節流因此以真實用戶端 IP 計算 |
| `WEB_PORT`、`WEB_CONTAINER_IP`、`NETWORK_SUBNET` | 輸入的值 |

容器內的 nginx 只接受 120 MiB 以內的請求本文（`deploy/nginx.conf` 的 `client_max_body_size 120m`）。`MAX_FILE_SIZE_MB` 大於 11 時，後端的文件上傳本文上限（見 [資源上限](#資源上限)）會超過 120 MiB，超過 120 MiB 的上傳先被 nginx 以 `413` 拒絕。

## 資源上限

下列上限是保護單一後端行程可用性與操作者付費用量的程式常數，**不是** `.env` 設定；集中定義在 [`backend/app/core/limits.py`](../backend/app/core/limits.py)（少數與單一模組綁定的常數定義在該模組中，表中註明）。調整時請修改原始碼並同步更新本節。

**請求與聊天**

| 常數 | 值 | 說明 |
|---|---|---|
| `MAX_REQUEST_BODY_BYTES` | 1 MiB | 一般 API 請求與所有未帶有效存取權杖的請求本文上限，超過回傳 `413`；`Content-Length` 超過時直接拒絕，分塊傳輸邊讀邊計數 |
| `MAX_CHAT_REQUEST_BODY_BYTES` | 約 27.7 MiB | `POST /api/chat/send` 的本文上限（附件總量 20 MiB 經 base64 膨脹 4/3 後再加 1 MiB）；只有帶著簽章有效的存取權杖時才放寬，否則仍為 1 MiB |
| 文件上傳本文上限 | `MAX_FILES_PER_UPLOAD` × `MAX_FILE_SIZE_MB` MiB + 1 MiB | `POST /api/documents/upload` 的本文上限（範本值 `MAX_FILE_SIZE_MB=10` 時為 101 MiB）；只有存取權杖簽章有效且 `is_admin` 聲明為 `true` 時才放寬，其他請求仍為 1 MiB。以 `deploy/` 部署時另受 nginx 的 120 MiB 限制，`MAX_FILE_SIZE_MB` 大於 11 時以 nginx 為準 |
| `MAX_FILES_PER_UPLOAD` | 10 | 單次上傳的檔案數 |
| `MAX_FILENAME_BYTES` | 255 位元組 | 上傳檔名以 UTF-8 計算的長度（Linux 檔案系統的檔名上限），超過時該檔回報 `400` |
| `MAX_CHAT_MESSAGE_CHARS` | 20,000 字元 | 單則聊天訊息長度，超過回傳 `422` |
| `MAX_CHAT_ATTACHMENTS` | 5 | 單則訊息的附件數 |
| `MAX_CHAT_ATTACHMENT_BYTES` | 15 MiB | 單一附件解碼後的大小；附件的 `data_url` 必須是 base64 編碼的 `data:` URL，遠端網址會被拒絕 |
| `MAX_CHAT_ATTACHMENTS_TOTAL_BYTES` | 20 MiB | 單則訊息所有附件解碼後的合計大小 |
| `MAX_ATTACHMENT_TEXT_CHARS` | 50,000 字元 | 每個附件放進模型脈絡的文字上限（超過的部分截斷），也是請求中附件 `content` 欄位與存回資料庫的附件文字的長度上限 |
| `MAX_USER_ATTACHMENT_STORAGE_BYTES` | 200 MiB | 每位使用者存在資料庫的附件與對話檔案總量（使用者訊息的 `context_used` 長度加上對話檔案大小），超過時送出訊息回傳 `413`，研究助理也無法再建立檔案；系統不會自動清除，刪除對話檔案或含附件的對話即可釋放 |
| `MAX_CONCURRENT_CHAT_STREAMS_PER_USER` | 2 | 每位使用者同時進行中的回答串流數，超過回傳 `429` |
| `MAX_LISTED_CONVERSATIONS`（`services/chat_service.py`） | 200 | `GET /api/chat/conversations` 只列最近更新的 200 段對話 |
| `MAX_CONVERSATION_MESSAGES`（`services/chat_service.py`） | 500 | `GET /api/chat/conversations/{conversation_id}/messages` 單次最多回傳的訊息數（`limit` 的上限） |
| `MAX_HISTORY_ATTACHMENT_CHARS`（`services/chat_service.py`） | 50,000 字元 | 前文帶入的先前使用者訊息附件文字合計上限，從最新的訊息往前計算；等於 `MAX_ATTACHMENT_TEXT_CHARS` |

**對話檔案**

| 常數 | 值 | 說明 |
|---|---|---|
| `MAX_CONVERSATION_FILE_BYTES` | 15 MiB | 單一對話檔案的大小，等於 `MAX_CHAT_ATTACHMENT_BYTES`；研究助理產生或修改的檔案超過時工具回傳錯誤 |
| `MAX_CONVERSATION_FILES` | 100 | 每個對話的檔案數（含使用者上傳的附件），超過時送出附件回傳 `400`、建立檔案的工具回傳錯誤 |
| `MAX_FILE_TOOL_CONTENT_CHARS` | 200,000 字元 | 建立或修改檔案時，`content` 字串的長度，以及簡報標題、項目與備忘稿的合計長度；試算表另以儲存格數限制 |
| `MAX_SPREADSHEET_CELLS` | 200,000 | 建立 `.xlsx`、`.csv` 時的儲存格總數 |
| `MAX_PRESENTATION_SLIDES` | 100 | 建立 `.pptx` 時的投影片數 |
| `MAX_FILE_EDITS` | 50 | 單次修改的文字取代（`edits`）數 |
| `MAX_GENERATED_PDF_PAGES` | 500 | 產生的 PDF 頁數，超過時不存檔並回傳錯誤 |
| `FILE_READ_PAGE_CHARS` | 15,000 字元 | `read_conversation_file` 每次回傳的文字上限，其餘以 `next_offset` 分段讀取 |
| `FILE_TEXT_CACHE_ENTRIES` | 8 | `read_conversation_file` 快取擷取文字的檔案數，同一個檔案分段讀取時不重新解析 |
| `FILE_PREVIEW_TEXT_CHARS` | 200,000 字元 | 檔案預覽中 Markdown 與文字檔顯示的長度 |
| `FILE_PREVIEW_ITEMS` | 5,000 | Word 預覽的區塊數，以及簡報預覽的文字與表格項目數 |
| `FILE_PREVIEW_SHEET_ROWS`、`FILE_PREVIEW_SHEET_COLUMNS` | 500 列、50 欄 | 試算表、CSV 與文件內表格預覽的大小 |
| `FILE_PREVIEW_PAGE_DPI`、`FILE_PREVIEW_PAGE_MAX_PIXELS` | 120 dpi、2,000 像素 | PDF 預覽每一頁轉成圖片的解析度，以及圖片最長邊的上限 |
| `FILE_PREVIEW_PDF_CACHE_ENTRIES` | 2 | 預覽時留在記憶體中的 PDF 對話檔案數，逐頁轉圖時不必每頁都從資料庫重讀整個檔案（最多約 2 × 15 MiB） |
| `FILE_VIEW_TOKEN_SECONDS` | 300 秒 | 網頁檔預覽權杖的有效時間 |

**工具與出站請求**

| 常數 | 值 | 說明 |
|---|---|---|
| `MAX_TOOL_RESULT_CHARS` | 20,000 字元 | 每次工具呼叫的結果放進模型脈絡前的上限，超過的部分截斷 |
| `MAX_AGENT_TURNS` | 30 | 代理模式最多呼叫模型幾輪，用完後請模型回報進度 |
| `AGENT_TOOL_RESULT_BUDGET_CHARS` | 40,000 字元 | 代理模式中所有工具結果合計的上限，超過時從最舊的換成一行說明 |
| `MAX_PLAN_STEPS` | 12 | 代理模式計畫最多幾步 |
| `MAX_PLAN_STEP_CHARS` | 120 字元 | 計畫每一步的長度上限 |
| `MAX_QUESTION_CHARS` | 300 字元 | 代理模式中 `ask_user` 問題的長度上限 |
| `MAX_QUESTION_OPTIONS` | 4 | `ask_user` 最多幾個選項 |
| `MAX_QUESTION_OPTION_CHARS` | 60 字元 | 每個選項的長度上限 |
| `MAX_QUESTION_ANSWER_CHARS` | 2,000 字元 | 使用者回答的長度上限 |
| `MAX_STEP_NOTE_CHARS` | 300 字元 | 研究步驟進度說明的長度上限，超過的部分截斷 |
| `FILE_CHECK_ITEMS` | 20 | 建檔結構檢查最多列出幾個標題、工作表或投影片標題 |
| `MAX_TOOL_NAME_CHARS` | 64 字元 | 交給模型的工具函式名稱長度（OpenAI 等供應商的上限）；由 OpenAPI operationId 或 MCP 產生的名稱超過時截斷並加上 8 碼雜湊，手動建立或匯入的名稱超過時回傳 `400` |
| `MAX_OPENAPI_SCHEMA_REFS` | 200 | 解析 OpenAPI 規格時，每個參數或請求主體 schema 最多展開的 `$ref` 數；超過的參照與循環參照改以只含說明的物件 schema 取代 |
| `MAX_OPENAPI_SCHEMA_DEPTH` | 32 | 解析 OpenAPI 規格時，參數或請求主體 schema 展開的巢狀層數（`$ref`、`properties`、`items`、`allOf` 等每進一層計一次）；更深的部分改以只含說明的物件 schema 取代 |
| `MAX_OPENAPI_DOCUMENT_BYTES` | 10 MiB | 匯入時每份文件的大小：規格（含 Arazzo）、Overlay、Overlay 指向的規格、Arazzo 的 `sourceDescriptions` 與外部參照文件，貼上的內容與從網址取得的都適用 |
| `MAX_OPENAPI_EXTERNAL_DOCUMENTS`、`MAX_OPENAPI_TOTAL_BYTES` | 20 份、30 MiB | 解析外部 `$ref` 時最多下載的外部參照文件數，以及規格與外部參照文件的合計大小；超過時其餘文件不載入，改列在警告中 |
| `OPENAPI_FETCH_TIMEOUT_SECONDS`、`OPENAPI_FETCH_MAX_REDIRECTS` | 15 秒、5 次 | 從網址取得上述文件的逾時與轉址次數，每一跳都重新做 SSRF 檢查 |
| `MAX_OVERLAY_ACTIONS`（`services/openapi_overlay.py`） | 500 | 單份 Overlay 的 `actions` 數，超過回傳 `400` |
| `MAX_JSONPATH_CHARS`、`MAX_JSONPATH_NODES`（`services/jsonpath.py`） | 2,000 字元、100,000 個 | Overlay 與 Arazzo 工作流程中 JSONPath 運算式的長度，以及單次查詢走訪的節點數，超過即失敗 |
| `MAX_ARAZZO_STEP_RUNS`、`MAX_ARAZZO_WORKFLOW_SECONDS` | 50 次、300 秒 | 一次 Arazzo 工作流程工具呼叫執行的步驟總數（含 `retry`、`goto` 與巢狀工作流程）與總時限，超過即失敗，避免 `goto` 或 `retry` 形成迴圈 |
| `MAX_ARAZZO_RETRY_AFTER_SECONDS` | 30 秒 | `retry` 動作每次等待的上限（`retryAfter`，或回應中以秒數表示的 `Retry-After`），也不超過剩餘時限 |
| `MAX_ARAZZO_NESTED_WORKFLOWS` | 5 層 | 工作流程以 `dependsOn`、步驟或動作的 `workflowId` 呼叫其他工作流程的巢狀層數 |
| `MAX_REGEX_CONTEXT_CHARS`（`services/arazzo.py`） | 20,000 字元 | Arazzo `successCriteria` 的 regex 條件只比對內容的前這麼多字元 |
| `MAX_KB_CATALOG_CHARS` | 4,000 字元 | `search_knowledge_base` 工具說明中文件目錄（檔名與摘要）的長度；每次呼叫模型都會送出，超過時只列出前面的文件並告知其餘份數 |
| `MAX_MCP_CATALOG_CHARS` | 8,000 字元 | `read_mcp_resource`、`get_mcp_prompt` 工具說明中各自列出的 MCP resources 或 prompts 清單長度；放不下的伺服器不列出並寫入警告日誌 |
| `MAX_TEXT_CLEANUP_CHARS` | 2,000,000 字元 | `web_fetch` 抽取文字前，以及 `web_search` 解析 DuckDuckGo 結果頁前，先截斷 HTML 的長度 |
| 聯網工具的逾時（`rag/tools.py`） | 15 秒、12 秒 | 呼叫 Ollama Web Search／Web Fetch API 的逾時，以及 `web_search` 改用 DuckDuckGo 時的逾時 |
| `web_fetch` 直接抓取（`rag/tools.py`） | 12 秒、5 次、5 MiB、3,500 字元 | 直接抓取網頁的逾時、轉址次數（每一跳都重新做 SSRF 檢查並比對 `WEB_FETCH_ALLOWED_DOMAINS`）與回應大小；回傳的內文（含經 Ollama Web Fetch 取得的）截斷為 3,500 字元 |
| `MAX_DATE_RANGE_CHARS`、`MAX_TARGET_DATES`、`MAX_FILTER_RECORDS`（`rag/tools.py`） | 200 字元、93 天、50 筆 | `filter_and_count_records` 的 `date_range` 長度、展開後的日期數與回傳筆數（`limit` 超過時夾到 50） |
| `MAX_API_TOOL_RESPONSE_BYTES`（`api/api_tools.py`） | 1 MiB | 自訂 API 工具的回應本文上限，超過即中止讀取並回傳 `502` |
| `MAX_API_TOOL_TEXT_CHARS`（`api/api_tools.py`） | 4,000 字元 | 自訂 API 工具的回應不是 JSON（`Content-Type` 不含 `application/json`，或內容無法解析）時，回傳給模型的文字長度 |
| `MAX_API_TOOL_REDIRECTS`（`api/api_tools.py`）、`MAX_MCP_HTTP_REDIRECTS`（`services/mcp_service.py`） | 5 次、5 次 | 自訂 API 工具與 HTTP MCP 手動跟隨轉址的次數上限：轉址回應的本文不讀取，每一跳都重新做 SSRF 檢查；HTTP MCP 與自訂 API 工具的 `GET`、`HEAD`、`OPTIONS` 以外的方法只跟隨同一來源的轉址，自訂 API 工具的 `GET`、`HEAD`、`OPTIONS` 轉址到其他來源時不轉送憑證標頭。整個呼叫（含轉址）另以該工具或伺服器的 `timeout` 設定為總時限，自訂 API 工具逾時回傳 `504` |
| `MAX_OAUTH_RESPONSE_BYTES`、`OAUTH_TIMEOUT_SECONDS`、`OAUTH_MAX_REDIRECTS`（`services/oauth_client.py`） | 256 KiB、15 秒、3 次 | OAuth 請求（自訂 API 工具的 OAuth2 client credentials 權杖端點，MCP OAuth 的中繼資料、用戶端註冊與權杖端點）的回應大小、整個請求（含轉址）的時限，以及只跟隨同一來源轉址的次數；連線一律經 SSRF 驗證 |
| `MAX_CACHED_TOKENS`（`services/oauth_client.py`） | 1,000 | 行程內快取的 OAuth2 client credentials 權杖數，滿了以後整個清空 |
| `MAX_MCP_HTTP_RESPONSE_BYTES`（`services/mcp_service.py`） | 4 MiB | HTTP 傳輸 MCP 伺服器的單次回應上限 |
| `MAX_MCP_STDIO_LINE_BYTES`（`services/mcp_service.py`） | 4 MiB | `stdio` MCP 子行程單行 JSON-RPC 訊息的上限，與 HTTP 回應上限相同 |
| `MCP_STDERR_TAIL_BYTES`（`services/mcp_service.py`） | 2,048 位元組 | `stdio` 子行程的 stderr 持續讀出（避免管線寫滿而卡住），只保留最後這麼多位元組，子行程異常結束時寫入伺服器日誌 |
| `MAX_CONCURRENT_STDIO_PROCESSES`（`services/mcp_service.py`） | 4 | 同時存在的 `stdio` MCP 子行程數；等待空位最多到該伺服器的 `timeout` 設定，逾時即失敗 |
| `MCP_DISCOVER_PROBE_TIMEOUT_SECONDS`（`services/mcp_service.py`） | 5 秒 | 連線時以 `server/discover` 協商新版協定的等待時間（不超過伺服器的 `timeout`），逾時改用舊版的 `initialize` |
| `MAX_MCP_ERROR_BODY_BYTES`（`services/mcp_service.py`） | 64 KiB | HTTP MCP 回應不是 `200` 時，讀取本文以取出 JSON-RPC 錯誤的上限，超過時不解析 |
| `MAX_MCP_TOOL_PAGES`（`services/mcp_service.py`） | 50 頁 | `tools/list`、`resources/list`、`prompts/list` 依 `nextCursor` 分頁讀取的頁數，超過即失敗 |
| `MAX_MCP_CATALOG_ITEMS`、`MAX_MCP_URI_CHARS`、`MAX_MCP_CATALOG_DESCRIPTION_CHARS`（`services/mcp_service.py`） | 200 個、2,048 字元、500 字元 | 每個伺服器的 resources 與 prompts 各只取前 200 個；URI 超過 2,048 字元的 resource 略過；resource、prompt 與 prompt 參數的說明截斷為 500 字元 |
| `AUTHORIZATION_STATE_TTL_SECONDS`、`MAX_PENDING_AUTHORIZATIONS`（`services/mcp_oauth.py`） | 600 秒、1,000 個 | MCP OAuth 授權從開始到回呼的時限，以及行程內同時保留的待完成授權數（滿了以後先淘汰最早開始的） |
| `PROBE_TIMEOUT_SECONDS`（`services/mcp_oauth.py`） | 15 秒 | 開始 MCP OAuth 授權時，向 MCP 伺服器探測 `WWW-Authenticate` 的逾時 |
| `APPROVAL_TIMEOUT_SECONDS`（`rag/tool_approval.py`） | 300 秒 | 等待使用者核准工具呼叫的時間，逾時視為拒絕 |
| `DNS_RESOLVE_TIMEOUT_SECONDS`、`DNS_RESOLVER_MAX_WORKERS`（`core/ssrf_protection.py`） | 5 秒；8 條與 4 條執行緒 | SSRF 驗證在兩個專用執行緒池中查詢 DNS：`web_fetch` 的使用者網址用 8 條（`DnsPool.USER_URL`），自訂 API 工具、HTTP MCP 與 OpenAPI 規格網址用 4 條（`DnsPool.CONFIGURED_ENDPOINT`），慢速網域占滿前者時不影響後者；逾時視為無法解析 |
| `LLM_POOL_ACQUIRE_TIMEOUT_SECONDS`（`core/llm_client.py`） | 15 秒 | 等待 LLM 連線池名額的上限，與 `LLM_TIMEOUT` 分開，池被占滿時很快失敗 |
| `MAX_DISCOVERED_MODELS` | 500 | 「從 API 取得模型」回傳的模型數，依名稱排序後取前 500 個 |
| `VLLM_MODEL_LENGTH_CACHE_SECONDS` | 300 | vLLM 模型上下文長度的快取秒數，過期後重新讀取 `/models` |

**文件解析**

管理員上傳的知識庫文件與聊天附件各用一組 `ExtractionLimits`（`ADMIN_UPLOAD_EXTRACTION_LIMITS`、`CHAT_ATTACHMENT_EXTRACTION_LIMITS`）。任何登入的使用者都能送出附件，而附件文字最後只取 `MAX_ATTACHMENT_TEXT_CHARS` 字，因此附件的預算小得多：

| 項目 | 管理員上傳 | 聊天附件 |
|---|---|---|
| 送 Vision OCR 的 PDF 頁數（`MAX_PDF_OCR_PAGES`） | 不限 | 20 頁 |
| `.docx`、`.pptx`、`.xlsx` 解壓後的總大小 | 200 MiB（`MAX_OOXML_UNCOMPRESSED_BYTES`） | 64 MiB（`MAX_ATTACHMENT_OOXML_UNCOMPRESSED_BYTES`） |
| OOXML 的成員數（`MAX_OOXML_MEMBERS`） | 10,000 | 10,000 |
| `.docx`、`.pptx` 會被建成 DOM 的 XML 總量 | 200 MiB（同解壓總大小） | 8 MiB（`MAX_ATTACHMENT_OOXML_XML_BYTES`） |
| 解析成結構化記錄的 JSON、JSONL、YAML 與 JS 宣告長度 | 不限 | 2,000,000 字元（`MAX_ATTACHMENT_STRUCTURED_PARSE_CHARS`） |

| 常數 | 值 | 說明 |
|---|---|---|
| `MAX_OCR_PIXELS` | 25,000,000 像素 | OCR 時單頁點陣化的像素上限，超過時降低解析度 |
| `MAX_RECORD_LABEL_CHARS` | 80 字元 | 結構化記錄標頭中識別欄位值的長度，超過時截斷並加上「…」；欄位本身的值不截斷 |
| `MAX_SUMMARY_FIELD_NAMES` | 8 個 | 結構化資料的摘要最多列出的欄位名稱數 |
| `MAX_OOXML_COMPRESSION_RATIO` | 100 | 解壓後超過 10 MiB（`OOXML_RATIO_CHECK_MIN_BYTES`）的單一成員或整個檔案，壓縮比不可超過此值；兩組預算相同 |
| `MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS` | 2 | 整個行程同時解析的聊天附件與對話檔案（讀取與修改）數；與單檔預算相乘即為附件解析的記憶體上界 |

OOXML 的檢查在解析前進行，依 ZIP 成員宣告的大小計算。python-docx 與 python-pptx 會把 XML 部件整份建成 DOM（記憶體約為 XML 大小的 15 至 30 倍），哪些成員算進 XML 總量依 `[Content_Types].xml` 判定（另含 `.rels` 與該檔本身），改副檔名無法繞過；`.xlsx` 以串流讀取，不套用此項。超過任一項 OOXML 預算時，管理員上傳的該檔案上傳失敗；聊天附件則不解析，改告知模型附件超過解析上限、未讀取內容。超過長度的 JSON、JSONL、YAML 與 JS 宣告附件不解析成結構化記錄，只做線性的雜訊清除。CSV 與 XLSX 不套用這個長度上限；YAML 的別名展開後節點數超過原始文字長度時一律放棄解析，改以純文字處理。

**Agent Skills**

| 常數 | 值 | 說明 |
|---|---|---|
| `MAX_SKILL_ARCHIVE_BYTES` | 10 MiB | 上傳的技能檔（`.zip` 或 `SKILL.md`）大小；`POST /api/skills/upload` 的本文上限為此值加 1 MiB，與文件上傳相同只在存取權杖的 `is_admin` 聲明為 `true` 時放寬 |
| `MAX_SKILL_UNCOMPRESSED_BYTES` | 50 MiB | 技能 zip 解壓後的總大小，以實際解壓的位元組數計算；也是上傳資料夾（`POST /api/skills/upload-folder`）的總大小，該端點的本文上限為此值加 1 MiB，同樣只對管理員放寬 |
| `MAX_SKILL_FILES` | 500 | 單一技能的檔案數；上傳資料夾時逐一套用在每個技能 |
| `MAX_SKILL_FOLDER_FILES` | 1000 | 一次上傳資料夾（`POST /api/skills/upload-folder`）的檔案數，含會被略過的 `.git` 等檔案 |
| `MAX_SKILL_MD_BYTES` | 256 KiB | `SKILL.md` 的大小 |
| `MAX_SKILL_NAME_CHARS`、`MAX_SKILL_DESCRIPTION_CHARS`、`MAX_SKILL_COMPATIBILITY_CHARS`（`services/agent_skills.py`） | 64、1,024、500 字元 | `SKILL.md` 的 `name`、`description`、`compatibility` 長度；`name` 超過時拒絕安裝，其他兩項超過時只加上警告 |
| `MAX_SKILL_RESOURCE_LISTING` | 100 | 啟用技能時列給模型的檔案數 |
| `MAX_SKILL_RESOURCE_CHARS` | 20,000 字元 | 啟用技能時回傳的 `SKILL.md` 內文與每次 `read_skill_resource` 的結果，超過的部分截斷 |
| `MAX_SKILL_CATALOG_CHARS` | 8,000 字元 | `activate_skill` 工具說明中技能目錄（名稱與描述）的長度；放不下的技能不列出並寫入警告日誌 |
| `MAX_SKILL_SCRIPT_SECONDS` | 60 秒 | `run_skill_script` 每次執行的時限，逾時終止整個行程群組，結果的 `timed_out` 為 `true` |
| `MAX_SKILL_SCRIPT_OUTPUT_CHARS` | 20,000 字元 | 腳本的 `stdout` 與 `stderr` 各自保留的長度，超過時截斷並設 `output_truncated` |
| `MAX_SKILL_SCRIPT_ARGS`、`MAX_SKILL_SCRIPT_ARG_CHARS` | 20 個、1,000 字元 | 腳本命令列參數的個數與每個參數的長度，超過時不執行 |
| `MAX_SKILL_SCRIPT_STDIN_CHARS` | 100,000 字元 | 傳給腳本標準輸入的長度，超過的部分截斷 |
| `MAX_CONCURRENT_SKILL_SCRIPTS` | 2 | 整個行程同時執行的技能腳本數，其餘排隊等候 |

**帳號、日誌與速率限制**

| 常數 | 值 | 說明 |
|---|---|---|
| `MAX_PASSWORD_CHARS` | 256 字元 | 註冊、登入與修改密碼時的密碼長度上限（Argon2 成本隨長度成長） |
| `MAX_LOGIN_IDENTIFIER_CHARS` | 254 字元 | 登入時使用者名稱或電子郵件的長度上限 |
| `MAX_CONCURRENT_PASSWORD_HASHES` | 4 | 同時進行的 Argon2 雜湊與驗證數，在執行緒中執行 |
| `MAX_TRACKED_LOGIN_ACCOUNTS` | 10,000 | [登入失敗節流](#登入失敗節流) 同時追蹤的登入識別數，最久沒有新失敗的先淘汰 |
| `MAX_REVOKED_TOKENS` | 100,000 | 行程內權杖撤銷名單的條目上限，滿了以後先淘汰最早到期的條目 |
| `MAX_LOG_FIELD_CHARS` | 200 字元 | 安全日誌中單一字串欄位（例如帳號名稱、User-Agent），以及存取、模型、工具與速率限制日誌中單一欄位（例如路徑、錯誤訊息）的長度上限 |
| `LOG_FILE_MAX_BYTES`、`LOG_FILE_BACKUP_COUNT` | 10 MiB、5 份 | `app.log` 與 `security.log` 的輪替大小與保留份數 |
| `MAX_TRACKED_ADDRESSES` | 10,000 | 速率限制與登入失敗節流各自同時追蹤的位址數，最久未活動的先淘汰 |
| `MAX_RATE_LIMIT_LOGGED_PATHS` | 10 | 速率限制視窗結束的警告中，每個來源 IP 分別計數的路徑數；其餘路徑只計入總次數 |

## 已移除的設定

留在 `.env` 中會被忽略，可以直接刪除：

| 變數 | 移除版本 | 替代方式 |
|---|---|---|
| `LLM_API_BASE`、`MODEL_NAME`、`AVAILABLE_MODELS`、`FOUNDRY_API_KEY`、`FOUNDRY_ENDPOINT`、`FOUNDRY_DEPLOYMENT`（含舊名稱 `AZURE_OPENAI_*`）、`OPENAI_API_KEY`、`OPENAI_API_BASE`、`OPENAI_VISION_MODEL`、`ANTHROPIC_API_KEY`、`ANTHROPIC_API_BASE`、`ANTHROPIC_MAX_TOKENS`、`GEMINI_API_KEY`、`GEMINI_API_BASE`、`GEMINI_VISION_MODEL`、`EXTERNAL_TAGS_URL`、`ADD_NGROK_HEADER` | 8.0.0 | 文件摘要與掃描 PDF 的 OCR 改用管理員在「管理後台 → 系統模型」指定的共用連線，見 [系統模型](#系統模型)；`GET /api/tags` 一併移除 |
| `ADMIN_API_KEY` | 6.0.0 | 沒有任何路由使用；管理端點一律依資料庫中該帳號的 `is_admin` 判斷 |
| `ENABLE_BATCH_ACCUMULATION`、`BATCH_ACCUMULATOR_SIZE` | 6.0.0 | 嵌入批次累積器從未接上上傳流程，已刪除 |
| `BASE_URL` | 6.0.0 | 只有已刪除的 `healthcheck.py` 使用；健康檢查請直接請求 `GET /health` |
| `JWT_SECRET_KEY`、`JWT_ALGORITHM` | 4.0.0 | 權杖一律以 `backend/keys/` 的 RSA 金鑰簽署 RS256，不再有 HS256 退路 |
| `HYBRID_ALPHA`、`NORMALIZATION` | 3.0.0 | 改用 `RRF_K` 的標準 RRF 融合 |
| `FINAL_THRESHOLD` | 3.0.0 | 改用 `RERANK_RELEVANCE_THRESHOLD` |
| `DOCUMENTS_PATH` | 3.0.0 | 片段改存資料庫 `rag_chunks` 表 |
| `ENABLE_AUTO_REINDEX`、`ENABLE_AUTO_REINDEX_TASK`、`REINDEX_HOURS` | 3.0.0 | 啟動時自動依資料庫校正索引，不再需要定時重建 |
| `TRANSFORMERS_CACHE`、`HUGGINGFACE_HUB_CACHE` | 3.0.0 | 改用 `HF_HOME` 或 `HF_HUB_CACHE` |
| `AZURE_OPENAI_API_VERSION` | 2.0.0 | 改用 Azure OpenAI v1 端點 |

## 領域設定檔

`DOMAIN_PROFILE_PATH`（必填）指向的 JSON 檔（範本值 `config/domain_profile.json`，即 `backend/config/domain_profile.json`）收納部署領域專屬的資料，啟動時以嚴格格式驗證：缺少欄位、多出未知欄位或出現空字串都會讓後端無法啟動。

```json
{
  "domain_words": ["補休", "育嬰留停", "免刷卡"],
  "record_date_fields": ["timestamp", "timestampTitle"],
  "record_label_fields": ["title", "name", "author", "id"],
  "record_ignore_fields": ["embedcode", "svg", "icon", "rawhtml", "path", "base64", "style", "imagedata", "svgdata"],
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
| `record_label_fields` | 結構化記錄的識別欄位，依序取第一個有值的頂層欄位接在記錄標頭後，並寫入片段 metadata 的 `label`；可以是空陣列，此時標頭不帶識別值 |
| `record_ignore_fields` | 解析結構化記錄時整個略過的欄位名稱（不分大小寫），例如內嵌 HTML、圖示或樣式；值中的 Base64 圖片與 SVG 不必列在這裡，一律換成佔位字 |
| `summary_fallback.chat_member_noise_words` | LLM 摘要失敗、改用規則摘要時，通訊紀錄中不應當成成員名稱的雜訊詞 |
| `summary_fallback.chat_topic_keywords` | 規則摘要偵測通訊紀錄主題時使用的關鍵字 |
| `summary_fallback.boilerplate_line_prefixes` | 以這些字首開頭（不分大小寫）的行視為頁尾、版權等雜訊 |

## 校準相關性門檻

範本的 `RERANK_RELEVANCE_THRESHOLD=0.02` 是依短貼文資料校準的值，不同資料的最佳門檻差距很大：內建企業文件基準的正例最高重排機率中位數約 0.87，但領域相近的反例也有一半高於 0.12、最高到 0.74；社群短貼文的正例中位數只有 0.37，十分之一低於 0.12（詳見 [ADR-0007](adr/0007-han-ngram-bm25-and-passage-level-evaluation.md)）。上傳實際文件後，請用自己的問答集校準：

1. **準備問答集**：JSONL 格式，每行一題，`relevant_sources` 填應該命中的文件檔名；知識庫本來就沒有答案的題目填空陣列當作反例。格式見 [`backend/eval/retrieval_golden.example.jsonl`](../backend/eval/retrieval_golden.example.jsonl)。

   ```json
   {"query": "特休假的天數如何依年資計算？", "relevant_sources": ["員工手冊.pdf"]}
   {"query": "公司附近有推薦的午餐餐廳嗎？", "relevant_sources": []}
   ```

   想看片段層級的排序品質時，再加上選填的 `relevant_passages`，列出能代表正解的短原文片段（取一句中有辨識度的 10 到 25 字，不要跨行），內容包含任一片段的知識庫片段即視為相關：

   ```json
   {"query": "年資兩年半可以休幾天特休？", "relevant_sources": ["員工手冊.pdf"], "relevant_passages": ["滿 2 年未滿 3 年：10 日"]}
   ```

2. **比較多個門檻**：在 `backend/` 執行下列指令。評估在索引副本上唯讀執行，可以與後端同時運作；索引與資料庫不一致或斷詞簽章不符時會拒絕執行，請先啟動一次後端完成校正。

   ```bash
   python scripts/evaluate_retrieval.py --golden eval/retrieval_golden.jsonl --k 1 3 5 --relevance-thresholds 0.1 0.2 0.3 0.4
   ```

3. **判讀結果**：報表列出目前門檻的 MRR、hit@k、recall@k 與反例拒絕率，並以同一次重排結果比較每個候選門檻；有標註原文片段時另列片段層級的 precision@k、nDCG@k、recall@k、MRR 與候選召回。門檻越高，反例拒絕率越高，但正例命中率可能下降；選擇在兩者間取得平衡的值。候選召回低代表正解沒有進入重排（檢查 BM25 斷詞或調高 `TOP_K`），候選召回高但排名差則是重排模型的判斷問題。
4. **套用**：把選定的值寫進 `.env` 的 `RERANK_RELEVANCE_THRESHOLD`，重新啟動後端。

其他選項：`--min-mrr 0.6` 或 `--min-passage-ndcg 0.8` 在指標未達標時以結束碼 1 結束，適合放進 CI；`--output report.json` 輸出完整結果。

**比較檢索設定或模型**：`--corpus` 以指定目錄的文件、依上傳時相同的流程在暫存 SQLite 與暫存索引上建立知識庫，不連線正式資料庫，結束後刪除；檢索參數與模型沿用 `.env`，可在命令前以環境變數覆寫來比較。內建基準有 12 份虛構企業文件與《大眾捷運法》，共 103 個正例、15 個反例：

```bash
python scripts/evaluate_retrieval.py --corpus eval/corpus --golden eval/corpus_golden.jsonl --k 1 3 5
```

## 前端環境變數

前端不建立 `.env` 也能運作：API 位址預設為相對路徑 `/api`，由 Vite 開發伺服器（埠號 3000）代理到 `http://127.0.0.1:8001`，瀏覽器不會跨來源，後端也不必設定 CORS。

| 變數 | 未設定時 | 說明 |
|---|---|---|
| `VITE_API_BASE` | `/api` | API 位址。設為絕對網址（例如 `http://localhost:8001`）時，瀏覽器直接呼叫後端，後端的 `ALLOWED_ORIGINS` 必須包含前端來源；此值同時是 Vite `/api` 代理的目標。路徑結尾會自動補上 `/api`。它的來源會在建置時寫入 CSP 的 `connect-src`，變更後需要重新建置。主機名稱含 `devtunnels.ms` 時，請求網址與寫入 `connect-src` 的來源都會去掉連接埠（`frontend/src/services/api.ts`、`frontend/vite.config.js`） |
| `VITE_API_URL` | — | `VITE_API_BASE` 未設定時才使用，格式相同；為絕對網址時，它的來源同樣在建置時寫入 `connect-src` |
| `PORT` | `3000` | Vite 開發伺服器埠號（`bun run preview` 固定為 3000） |
| `GENERATE_SOURCEMAP` | 輸出 | 建置時是否輸出 source map，設為 `false` 才關閉 |

`frontend/.env.example` 採用「直接呼叫」模式：`VITE_API_BASE=http://localhost:8001` 搭配 `PORT=3001`，這個來源正好在後端 `ALLOWED_ORIGINS` 的預設清單中。

Vite 開發與預覽伺服器固定只監聽 `localhost`（`frontend/vite.config.js`，不是環境變數），並送出 `X-Frame-Options: DENY` 與 `Content-Security-Policy: frame-ancestors 'none'; img-src 'self' data: blob:`；`/__open-in-editor` 只回應本機回送位址。區網裝置需要使用時，請以 `bun run build` 建置後由正式的網頁伺服器提供，並在該伺服器送出相同的反框架標頭。

### 建置時的 CSP

`bun run build` 把 CSP 以 `<meta http-equiv="Content-Security-Policy">` 寫入 `index.html`（`frontend/vite.config.js`；開發伺服器需要內嵌的 HMR 腳本，因此只在建置時套用）：`default-src 'self'`；腳本與樣式只允許同源檔案，以及 `index.html` 內嵌腳本與樣式（反框架守衛、主題初始化）的 SHA-256 雜湊；圖片只允許 `'self'`、`data:` 與 `blob:`；`connect-src` 為 `'self'` 加上 `VITE_API_BASE`、`VITE_API_URL` 中絕對網址的來源（主機名稱含 `devtunnels.ms` 時去掉連接埠）；另有 `object-src 'none'`、`base-uri 'none'` 與 `form-action 'self'`。網頁伺服器沒有設定 CSP 時，被注入的 HTML 也無法執行腳本。

`<meta>` 無法設定 `frame-ancestors`，因此提供建置產物的網頁伺服器仍要送出反框架標頭（`X-Frame-Options: DENY` 或 `Content-Security-Policy: frame-ancestors 'none'`）。