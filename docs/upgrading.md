# 升級指南

[繁體中文](upgrading.md) | [English](upgrading_en.md)

> 本文件說明如何把既有部署升級到新版本，並附上回退步驟與常見問題。每個版本的完整變更見 [CHANGELOG](../CHANGELOG.md)。

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
