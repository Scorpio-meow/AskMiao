# 升級指南

[繁體中文](upgrading.md) | [English](upgrading_en.md)

> 本文件說明如何把既有部署升級到新版本，並附上回退步驟與常見問題。每個版本的完整變更見 [CHANGELOG](../CHANGELOG.md)。

- [從 3.0.0 升級到 4.0.0](#從-300-升級到-400)
  - [變更與需要的動作](#變更與需要的動作)
  - [升級步驟](#升級步驟)
  - [回退方式](#回退方式)
  - [升級後的常見狀況](#升級後的常見狀況)
- [從 2.x 升級到 3.0.0](#從-2x-升級到-300)
  - [升級總覽](#升級總覽)
  - [步驟 0：停機並備份](#步驟-0停機並備份)
  - [步驟 1：更新程式碼與相依套件](#步驟-1更新程式碼與相依套件)
  - [步驟 2：更新 `.env`](#步驟-2更新-env)
  - [步驟 3：啟動後端並重建索引](#步驟-3啟動後端並重建索引)
  - [步驟 4：確認管理員與工具設定](#步驟-4確認管理員與工具設定)
  - [步驟 5：驗證升級結果](#步驟-5驗證升級結果)
  - [回退到 2.2.x](#回退到-22x)
  - [常見問題](#常見問題)

---

## 從 3.0.0 升級到 4.0.0

適用於從 3.0.0 升級到 4.0.0，完整變更見 [CHANGELOG](../CHANGELOG.md#400---2026-09-27)。這一版是安全性修正，不需要重建索引，資料表的新欄位會在啟動時自動加入；需要動手的主要是 `.env`、`backend/keys/`、PostgreSQL 容器與前端的對外提供方式。

### 變更與需要的動作

| 項目 | 3.0.0 | 4.0.0 | 需要的動作 |
|---|---|---|---|
| JWT 簽署 | RSA 金鑰無法載入時，開發環境退回 HS256（`JWT_SECRET_KEY`） | 一律 RS256，金鑰無法載入或產生時拒絕啟動 | 確認 `backend/keys/` 存在且後端帳號可寫入；`JWT_SECRET_KEY`、`JWT_ALGORITHM` 可從 `.env` 刪除 |
| 權杖驗證 | 身分與 `is_admin` 取自權杖內容 | 每次請求依 `sub` 讀取資料庫帳號，停用或刪除的帳號立即失效 | 無；既有權杖在帳號仍存在且啟用時繼續有效 |
| 重新整理權杖 | `POST /api/auth/refresh` 讀取不存在的聲明而一律失敗 | 可以正常換發，且每個重新整理權杖只能使用一次 | 自行呼叫此端點的客戶端需改用每次回應的新 Cookie |
| PostgreSQL 容器 | 內建密碼 `postgres`，埠號對所有介面開放 | 必須設定 `POSTGRES_PASSWORD`，只綁定 `127.0.0.1:7690` | 設定 `POSTGRES_PASSWORD` 並更新 `DATABASE_URL` |
| 前端開發伺服器 | 監聽所有介面，區網可連 | 只監聽 `localhost`，並送出反框架標頭 | 區網使用者改用建置產物與正式網頁伺服器 |
| 速率限制的來源 IP | uvicorn 預設可能採信 `X-Forwarded-For` | 只採信 `FORWARDED_ALLOW_IPS` 指定的代理 | 前方有會覆寫該標頭的反向代理時設定 `FORWARDED_ALLOW_IPS` |
| 工具呼叫 | Agent 直接執行 | `requires_approval` 的工具先經使用者核准 | 欄位自動加入；依需要調整各工具的旗標 |
| MCP 範本 | `mcp_fetch`、`mcp_filesystem`（根目錄 `./data`） | 移除 `mcp_fetch`；`mcp_filesystem` 改用 `backend/mcp_filesystem_sandbox` 並釘選版本 | 檢查以舊範本建立的伺服器 |
| 出站代理 | 自訂 API 工具、MCP HTTP 與 `web_fetch` 會讀取 `HTTP(S)_PROXY` | 一律直接連線，連線固定在 SSRF 驗證過的 IP | 需要經代理連外的環境請改由網路層處理 |
| 訊息回應 | 含原始 `context_used` 字串 | `/api/chat` 的回應中 `context_used` 一律為 `null` | 改讀 `sources`、`sources_detail`、`research_trace`、`attachments` |
| 資源上限 | 大多沒有上限 | 請求本文、訊息、附件、工具結果、同時串流數等都有上限 | 無；需要時參考 [資源上限](configuration.md#資源上限) |

### 升級步驟

1. **停機並備份**：停止後端，備份資料庫、`backend/data/`、`backend/keys/` 與 `backend/.env`。
2. **更新程式碼**：取得新版程式碼後，在 `backend/` 執行 `pip install -r requirements.txt`，在 `frontend/` 執行 `bun install`。
3. **整理 `.env`**：
   - 刪除 `JWT_SECRET_KEY` 與 `JWT_ALGORITHM`。留著也不會出錯，後端會忽略。
   - 後端前方有會「覆寫」`X-Forwarded-For` 的反向代理（例如 nginx 的 `proxy_set_header X-Forwarded-For $remote_addr;`）時，加上 `FORWARDED_ALLOW_IPS=<代理位址>`；經由 Vite 開發代理時**不要**設定。
4. **確認 RSA 金鑰**：`backend/keys/jwt_private.pem` 與 `jwt_public.pem` 必須存在且可讀；沒有金鑰時後端會在首次啟動產生，因此目錄需要能讓後端帳號寫入。沿用原本的金鑰，既有的權杖就不會失效。
5. **PostgreSQL 容器（使用 `backend/docker-compose.yml` 時）**：
   - 在 `backend/.env` 加上 `POSTGRES_PASSWORD=<隨機字串>`，未設定時 `docker compose` 會拒絕啟動。
   - 既有的資料卷已以舊密碼 `postgres` 初始化，`POSTGRES_PASSWORD` 只在第一次初始化時生效。請先以舊設定啟動容器並改掉密碼，再更新 `DATABASE_URL`：

     ```bash
     cd backend
     docker compose exec postgres psql -U postgres -c "ALTER USER postgres PASSWORD '<新密碼>';"
     ```

   - 把 `DATABASE_URL` 改成 `postgresql+psycopg2://postgres:<新密碼>@localhost:7690/chatbot`（特殊字元需百分比編碼），再以 `docker compose up -d` 重新建立容器，套用只綁定 `127.0.0.1` 的埠號設定。
6. **啟動後端**：`python main.py`。啟動時 `upgrade_schema()` 會替 `custom_api_tools` 與 `mcp_servers` 加上 `requires_approval` 欄位並回填：API 工具的方法不是 `GET`、`HEAD`、`OPTIONS` 時為 `true`，MCP 伺服器一律為 `true`。
7. **檢查工具設定**：以管理員進入「AI 工具」：
   - 依實際行為調整各工具的「需使用者確認」。`GET` 工具預設不需確認，若它會改變狀態或把資料送往外部，請打開。
   - 以舊版 `mcp_fetch` 範本建立的伺服器不會被刪除，但它繞過 `web_fetch` 的出站防護，建議刪除或停用。
   - 以舊版 `mcp_filesystem` 範本建立的伺服器仍指向 `./data`（後端的資料目錄），請改為 `backend/mcp_filesystem_sandbox` 的絕對路徑或其他專屬目錄，並把套件釘選到審閱過的版本，再按「重新探索」。
8. **前端的對外提供**：`bun run dev` 與 `bun run preview` 只監聽 `localhost`。原本讓區網裝置直接連開發伺服器的部署，請改以 `bun run build` 建置，由 nginx 等正式網頁伺服器提供 `frontend/build/`、反向代理 `/api`，並送出 `X-Frame-Options: DENY` 或 `Content-Security-Policy: frame-ancestors 'none'`。
9. **驗證**：
   - [ ] 登入後閒置超過存取權杖效期，前端能自動換發並繼續使用。
   - [ ] 停用某位測試帳號後，該帳號下一個請求立即回傳 `401`。
   - [ ] 呼叫一個需要核准的工具時，聊天畫面出現確認卡片，拒絕後 Agent 改以既有資料回答。
   - [ ] 自行串接 API 的客戶端已改讀解析後的訊息欄位，不再依賴 `context_used`，並能處理 `approval_required` 事件。

### 回退方式

1. 停止後端，把程式碼切回 3.0.0，還原 `.env`（3.0.0 需要 `JWT_SECRET_KEY`）。
2. 資料庫可以沿用：3.0.0 會忽略新增的 `requires_approval` 欄位。例外是由新版建立的全新資料庫，其中這兩個欄位是 `NOT NULL` 且沒有預設值，3.0.0 新增工具時會失敗，請先移除這兩個欄位或給定預設值。
3. `backend/docker-compose.yml` 回到 3.0.0 版本時會改用內建密碼 `postgres` 的設定；若已改過資料庫密碼，`DATABASE_URL` 維持新密碼即可。

### 升級後的常見狀況

<details>
<summary><b>後端啟動失敗，錯誤與 <code>backend/keys</code> 或 RSA 金鑰有關</b></summary>

新版不再退回 HS256。請確認 `backend/keys/` 存在、後端帳號可以寫入（首次產生金鑰時需要），且 `jwt_private.pem`、`jwt_public.pem` 沒有損毀。以容器或唯讀檔案系統部署時，請把事先產生好的金鑰掛載進去。

</details>

<details>
<summary><b><code>docker compose up</code> 回報需要設定 <code>POSTGRES_PASSWORD</code></b></summary>

compose 檔已不含內建密碼。請在 `backend/.env`（或殼層環境）設定 `POSTGRES_PASSWORD`，既有資料卷的密碼需另外以 `ALTER USER` 修改，見 [升級步驟](#升級步驟) 第 5 點。

</details>

<details>
<summary><b>區網裝置連不上前端</b></summary>

開發與預覽伺服器只監聽 `localhost`，這是刻意的限制。請改以建置產物搭配正式網頁伺服器提供服務，見 [升級步驟](#升級步驟) 第 8 點。

</details>

<details>
<summary><b>所有使用者共用同一個速率限制額度</b></summary>

未設定 `FORWARDED_ALLOW_IPS` 時，速率限制以實際連線對端計算；經由反向代理時所有人的來源 IP 都是代理本身。代理會覆寫 `X-Forwarded-For` 時，把代理位址設為 `FORWARDED_ALLOW_IPS`；否則請調高 `RATE_LIMIT_PER_MINUTE`。

</details>

<details>
<summary><b>送出訊息回傳 <code>400</code>、<code>413</code>、<code>422</code> 或 <code>429</code></b></summary>

- `400`：`model_name` 不在可用模型清單內，請改用 `GET /api/chat/models` 列出的模型，或把它加進 `AVAILABLE_MODELS`。
- `413`：請求本文超過上限，或該使用者的附件儲存量已達 200 MiB，刪除含附件的舊對話即可。
- `422`：訊息超過 20,000 字、附件超過 5 個、單一附件超過 15 MiB 或合計超過 20 MiB。
- `429`：同一位使用者已有 2 個回答正在串流。

</details>

---

## 從 2.x 升級到 3.0.0

3.0.0 是主版本升級，索引格式、必填設定與工具管理權限都有不相容的變更。實際操作約 15 分鐘，另加一次索引重建的時間：重建會逐份文件重新擷取文字、呼叫 LLM 生成摘要並計算向量，所需時間與文件量成正比。

### 升級總覽

| 項目 | 2.2.x | 3.0.0 | 需要的動作 |
|---|---|---|---|
| 片段與索引 | FAISS、`documents.pkl`、BM25 依清單位置對齊 | 資料庫 `rag_chunks` 為準，FAISS 與 BM25 以 chunk_id 對應 | 升級後重建一次索引 |
| 檢索融合 | 加權正規化分數（`HYBRID_ALPHA`） | 標準 RRF（`RRF_K`）加上重排機率門檻 | 補上新設定 |
| 必填設定 | 3 項 | 11 項 | 補上 8 項 |
| 重排模型 | 載入失敗時略過重排 | 必要元件，載入失敗無法啟動 | 確認模型快取或網路可用 |
| 工具管理 | 任何登入者 | 只限管理員 | 確認至少有一位管理員 |
| MCP `stdio` 環境變數 | 繼承後端全部環境變數 | 只繼承系統必要變數 | 伺服器需要的變數寫進 `env_vars` |
| MCP HTTP 位址 | 未驗證 | 每次請求與轉址都做 SSRF 驗證 | 本機或內網的伺服器改用 `stdio` |
| Hugging Face 快取 | 預設 `./data/hf_home` | 未設定時為 `~/.cache/huggingface` | 要沿用舊快取時明確設定 `HF_HOME` |
| 內建模型清單 | GPT-4o、o 系列等 | GPT-6 / GPT-5.6、Claude 5 系列、Gemini 3.x | 仍要用舊模型時寫進 `AVAILABLE_MODELS` |

### 步驟 0：停機並備份

升級會改寫索引檔，請先停止後端，再備份以下項目：

- **資料庫**：SQLite 直接複製 `.db` 檔；PostgreSQL 以 `pg_dump` 匯出。
- **`backend/data/`**：向量索引 `faiss_index.bin`、`documents.pkl`、`index_metadata.pkl`、`bm25_index/`、上傳檔 `uploads/`，以及模型快取 `hf_home/`（若有）。
- **`backend/.env`**。

### 步驟 1：更新程式碼與相依套件

```bash
# 取得 3.0.0 的程式碼後
cd backend
pip install -r requirements.txt   # 3.0.0 新增官方 anthropic SDK

cd ../frontend
bun install
```

### 步驟 2：更新 `.env`

#### 新增的必填設定

以下 8 項沒有預設值，缺少任一項後端都無法啟動。建議值與 `backend/.env.example` 相同：

| 設定 | 建議值 | 說明 |
|---|---|---|
| `ENABLE_WEB_SEARCH` | `true` | 是否提供 `web_search` 與 `web_fetch` 兩個聯網工具 |
| `AGENT_MAX_TURNS` | `5` | 單次提問的工具呼叫輪數上限（≥ 1） |
| `CONVERSATION_HISTORY_MESSAGES` | `6` | 提問時從資料庫帶入的前文訊息數（0 表示不帶） |
| `WEB_FETCH_ALLOWED_DOMAINS` | `*` | `web_fetch` 可讀取的網域（含子網域，逗號分隔）；明確寫 `*` 才表示不限制 |
| `BLOCK_WEB_TOOLS_AFTER_KB` | `true` | 同一次提問讀過知識庫內容後，拒絕聯網工具 |
| `RRF_K` | `60` | RRF 融合常數 |
| `RERANK_RELEVANCE_THRESHOLD` | `0.2` | 重排機率低於此值的片段視為無關（暫定值，見 [門檻校準](configuration.md#校準相關性門檻)） |
| `DOMAIN_PROFILE_PATH` | `config/domain_profile.json` | 領域設定檔路徑（相對路徑以 `backend/` 為基準） |

可直接貼進 `.env`：

```dotenv
ENABLE_WEB_SEARCH=true
AGENT_MAX_TURNS=5
CONVERSATION_HISTORY_MESSAGES=6
WEB_FETCH_ALLOWED_DOMAINS=*
BLOCK_WEB_TOOLS_AFTER_KB=true
RRF_K=60
RERANK_RELEVANCE_THRESHOLD=0.2
DOMAIN_PROFILE_PATH=config/domain_profile.json
```

> [!IMPORTANT]
> 使用 Claude 模型時還要設定 `ANTHROPIC_MAX_TOKENS`（例如 `16000`），否則呼叫 Claude 時會回報「使用 Claude 模型前需在 .env 設定 ANTHROPIC_MAX_TOKENS」。

#### 可以刪除的設定

以下設定已移除，留在 `.env` 中會被忽略：

`HYBRID_ALPHA`、`NORMALIZATION`、`FINAL_THRESHOLD`、`DOCUMENTS_PATH`、`ENABLE_AUTO_REINDEX`、`ENABLE_AUTO_REINDEX_TASK`、`REINDEX_HOURS`、`TRANSFORMERS_CACHE`、`HUGGINGFACE_HUB_CACHE`。

#### 行為改變、需要確認的設定

- **Hugging Face 快取**：2.2.x 預設把模型放在 `./data/hf_home`，3.0.0 未設定 `HF_HOME` 時改用 `~/.cache/huggingface`。要沿用既有快取、避免重新下載嵌入與重排模型（約 1.2 GB），請明確設定 `HF_HOME=./data/hf_home`；原本的 `HUGGINGFACE_HUB_CACHE` 改名為 `HF_HUB_CACHE`。
- **預設模型**：`OPENAI_VISION_MODEL` 預設改為 `gpt-6-sol`、`GEMINI_VISION_MODEL` 改為 `gemini-3.5-flash`（兩者用於 PDF 掃描頁 OCR）；內建模型清單不再包含 `gpt-4o`、`o1`、`o3`、`gemini-2.5-flash` 等舊型號。仍要使用舊型號時，請在 `AVAILABLE_MODELS` 與上述兩個設定中明確寫出。
- **相對路徑**：`DATA_DIR`、`UPLOAD_DIR`、索引路徑、`HF_*`、`DOMAIN_PROFILE_PATH` 與 `JIEBA_DICTIONARY` 的相對路徑一律以 `backend/` 為基準，不再依啟動目錄而定。
- **`RERANK_TOP_K`**：程式預設值為 50，`.env.example` 建議 20。CPU 上重排每對約 0.2 至 0.4 秒，候選數越多每次檢索越慢。

每個設定的完整說明見 [設定參考](configuration.md)。

### 步驟 3：啟動後端並重建索引

```bash
cd backend
python main.py
```

首次啟動時會依序看到：

1. **設定驗證**：缺少必填設定時，啟動會以 `Field required` 錯誤列出缺少的欄位。
2. **載入模型**：嵌入模型與重排模型；重排模型無法載入時會以「無法載入重排模型」結束啟動。
3. **偵測到舊版索引**：日誌出現「偵測到舊版（依位置對齊）的 FAISS 索引格式」，原檔改名為 `faiss_index.bin.legacy.bak`。
4. **知識庫暫時是空的**：新的 `rag_chunks` 資料表還沒有片段，必須重建索引後才檢索得到既有文件。

接著以下列任一方式重建索引：

| 方式 | 操作 | 適合情境 |
|---|---|---|
| 前端 | 以管理員登入 →「知識庫」→「重建索引」 | 文件量不大、想在畫面上看到結果 |
| API | `POST /api/documents/rebuild-index`（需管理員存取權杖） | 自動化部署流程 |
| 離線腳本 | **停止後端後**，在 `backend/` 執行 `python scripts/reprocess_existing_docs.py` | 文件量大、不想佔用線上服務 |

```bash
# API 方式
curl -X POST http://localhost:8001/api/documents/rebuild-index \
  -H "Authorization: Bearer <管理員的 access_token>"
```

重建會對資料庫中的每份文件：重新從 `UPLOAD_DIR` 擷取文字（檔案不在時改用資料庫內容）、重新生成 AI 摘要、依目前的 `CHUNK_SIZE` / `CHUNK_OVERLAP` 切塊，並寫入 `rag_chunks`、FAISS 與 BM25。確認問答正常後，即可刪除 `backend/data/` 內的 `faiss_index.bin.legacy.bak` 與 `documents.pkl`。

> [!NOTE]
> 之後不需要再手動重建：後端每次啟動都會依 `rag_chunks` 自動校正 FAISS 與 BM25；更換嵌入模型（向量維度改變）時，舊索引會改名為 `*.mismatch.bak` 並自動重新計算向量。

### 步驟 4：確認管理員與工具設定

- **至少一位管理員**：「AI 工具」、「知識庫」與「管理後台」都只限管理員。還沒有管理員時，請依 [README：建立第一位管理員](../README.md#4-建立第一位管理員) 操作。
- **MCP `stdio` 伺服器**：子行程只繼承系統必要變數（Windows 為 `PATH`、`SYSTEMROOT`、`USERPROFILE` 等，其他平台為 `HOME`、`PATH`、`SHELL` 等）。依賴後端環境變數的伺服器（例如 `HTTP_PROXY`、`HTTPS_PROXY`、`NODE_EXTRA_CA_CERTS` 或各種存取權杖），請把變數寫進該伺服器的 `env_vars`，再按「重新探索」。
- **MCP HTTP 伺服器**：指向 `localhost` 或內網位址的伺服器，探索會失敗，`last_error` 會註明遭 SSRF 防護拒絕並附錯誤代碼。本機的 MCP 伺服器請改用 `stdio` 傳輸。
- **自訂 API 工具**：出站請求的每一次轉址都會重新做 SSRF 驗證，轉址到內網位址的 API 會被拒絕（測試結果的 `status_code` 為 `403`）。

### 步驟 5：驗證升級結果

- [ ] `GET http://localhost:8001/health` 回傳 `{"status": "healthy"}`。
- [ ] `http://localhost:8001/docs` 標題為「AskMiao API」，版本為 `3.0.0`。
- [ ] 管理員呼叫 `GET /api/admin/vector-store/info`：`index_type` 為 `FAISS IndexIDMap2(IndexFlatIP) + Whoosh BM25`，`total_vectors` 大於 0。
- [ ] 問一個知識庫涵蓋的問題：答案附 `[n]` 引用，下方來源標籤可點開原文片段。
- [ ] 問一個知識庫沒有的問題：Agent 照實回報查無資料，而不是硬湊答案。
- [ ] （建議）以實際問答集執行 `python scripts/evaluate_retrieval.py --golden <問答集> --k 1 3 5 --relevance-thresholds 0.1 0.2 0.3`，校準 `RERANK_RELEVANCE_THRESHOLD`。

### 回退到 2.2.x

1. 停止後端，把程式碼切回 2.2.x。
2. 以步驟 0 的備份還原 `backend/data/` 與 `.env`。3.0.0 寫出的 FAISS 索引以 chunk_id 為鍵，2.2.x 無法正確使用。
3. 資料庫二擇一：
   - **還原備份**：最乾淨，但會遺失升級後新增的對話與文件。
   - **保留現有資料庫**：2.2.x 會忽略 `rag_chunks` 資料表。升級後新增的文件不在還原的索引內，請在 2.2.x 呼叫 `POST /api/documents/rebuild-index` 重建。

### 常見問題

<details>
<summary><b>啟動失敗，錯誤訊息出現 <code>Field required</code></b></summary>

`.env` 缺少必填設定。錯誤訊息會列出缺少的欄位名稱，依 [步驟 2](#步驟-2更新-env) 補上即可。

</details>

<details>
<summary><b>啟動失敗，訊息為「無法載入重排模型」</b></summary>

重排模型在 3.0.0 是必要元件。請確認：

- `RERANKER_MODEL` 名稱正確（預設 `BAAI/bge-reranker-base`）。
- 首次啟動時可以連上 Hugging Face，且 `HF_HUB_OFFLINE` 不是 `true`。
- 若要沿用舊快取，`HF_HOME` 指向原本的快取目錄。

</details>

<details>
<summary><b>升級後每個問題都回報「知識庫中查無相關資料」</b></summary>

先確認索引已重建（`GET /api/admin/vector-store/info` 的 `total_vectors` 大於 0）。索引正常時，可能是相關性門檻太高：`0.2` 是以小型語料得到的暫定值，請以實際問答集執行 `scripts/evaluate_retrieval.py --relevance-thresholds` 校準。

</details>

<details>
<summary><b>一般使用者看不到「AI 工具」頁</b></summary>

這是 3.0.0 的預期行為。工具由所有使用者的 Agent 共用，`stdio` 模式還會在主機上執行指令，因此只開放管理員管理；一般使用者仍可在對話中讓 Agent 使用已啟用的工具。詳見 [ADR-0004](adr/0004-tool-admin-permissions-and-subprocess-isolation.md)。

</details>

<details>
<summary><b>MCP 伺服器狀態變成 <code>error</code></b></summary>

查看該伺服器的 `last_error`：

- 提到 SSRF：網址或其轉址目標未通過 SSRF 驗證，多半是伺服器位於本機或內網，請改用 `stdio` 傳輸；確切原因可依錯誤代碼在伺服器日誌查到。
- 只顯示錯誤代碼：多半是 `stdio` 子行程少了原本從後端繼承的環境變數，請把需要的變數寫進 `env_vars` 後重新探索；錯誤代碼可在伺服器日誌中對應到完整例外。

</details>
