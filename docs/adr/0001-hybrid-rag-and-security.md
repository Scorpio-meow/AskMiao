# ADR-0001: 增強型混合 RAG 檢索架構與雙 Token 安全防護決策

[繁體中文](0001-hybrid-rag-and-security.md) | [English](0001-hybrid-rag-and-security_en.md)

## 狀態

已通過 (Accepted) - 2026-08-01

---

## 背景與問題陳述

AskMiao 是智慧對話與多 Agent 協作系統，在知識庫檢索與安全認證上面臨兩個核心挑戰：

1. **單一檢索機制的限制**：
   - 純向量搜尋（Dense Retrieval）擅長捕捉語意相似度，但遇到專業術語、專有名詞、型號或需要精確比對的關鍵字時，容易漏掉或產生幻覺。
   - 純關鍵字搜尋（Sparse Retrieval，例如 BM25）擅長精確比對，但缺乏語意理解與同義詞擴展。
2. **認證安全性與敏感資料洩漏防範**：
   - 單一長效 JWT Token 一旦被側錄，風險會一直存在；純 Session 機制則在分散式與非同步 API 架構下擴充性較差。
   - 系統日誌容易在無意間記下使用者密碼與 API 金鑰，觸發 CodeQL 安全警報。

---

## 架構決策內容

團隊評估後，採用以下方案：

### 1. 增強型混合 RAG 管道 (Hybrid RAG Pipeline)

- 結合 **FAISS 向量檢索**（`BAAI/bge-small-zh-v1.5` 模型）與 **Whoosh BM25 關鍵字檢索**（以 `Jieba` 斷詞）。
- ~~採用分數正規化融合演算法~~（**已被取代**：自 2026-09-24 起改為兩軌必跑的標準 RRF 融合，見 [ADR-0003](./0003-rrf-relevance-citations-and-tool-trust.md)），並以 **Cross-Encoder 模型 (`bge-reranker-base`)** 重新排序 Top-K 片段。

### 2. RSA-2048 雙 Token 認證與 Redis 黑名單

- **Access Token**：以 RSA-2048 私鑰簽署，有效期限 30 分鐘，經由 HTTP 標頭傳送。
- **Refresh Token**：存放在 HttpOnly / Secure / SameSite 的 Cookie，有效期限 7 天。
- **即時撤銷機制**：登出時把 Access Token 的 JTI 寫入 Redis 黑名單，避免權限殘留。

### 3. 雙層敏感資料遞迴遮蔽機制 (`security_logging.py`)

- 以 `sanitize_sensitive_data` 在物件層級遞迴替換敏感值。
- 日誌輸出與 JSON 序列化前，再以正規表示式遮罩一次，把所有敏感欄位換成 `[REDACTED]`。

---

## 決定產生的影響與權衡

### 正面影響 (Benefits)

- **檢索精準度顯著提升**：混合檢索加上重排大幅減少幻覺，中文領域名詞與精確字詞的檢索成功率也大幅提高。
- **安全性顯著增強**：無感重新整理權杖兼顧使用者體驗與短效 Token 的安全；雙層遮蔽徹底消除日誌洩漏資料的隱患，並通過 CodeQL 安全評估。

### 負面影響與挑戰 (Trade-offs & Risks)

- **系統複雜度增加**：後端要同時維護 FAISS 向量索引檔與 Whoosh 關鍵字索引。
- **運算與延遲成本**：Cross-Encoder 重排讓回應多出數十毫秒的延遲，需以 Redis 快取熱門查詢來改善。

---

## 後續修訂 (Amendments)

- **2026-08-24｜Token 撤銷名單改為行程內記憶體實作**：架構輕量化後移除 Redis 依賴，改由 `app/core/redis_client.py` 的 `TokenBlacklist` 在行程記憶體中維護撤銷名單，並自動清理過期項目。權衡：不再依賴外部服務，但後端重啟後名單會重置，未過期的舊 Token 重新被視為有效；多行程部署時也要改回共享儲存。
- **2026-08-24｜移除多 Agent 協作看板**：專案聚焦在知識庫問答與 Agentic 自主研究，原本的多 Agent 討論看板與工作流程模組已下線。
- **2026-09-01｜出站請求安全防護**：外部呼叫的安全設計改由 [ADR-0002](./0002-external-tools-and-outbound-safety.md) 規範。
- **2026-09-24｜分數正規化融合已被取代**：檢索融合改為兩軌必跑的標準 RRF，相關性門檻改套在重排模型的機率上，重排模型成為必要元件，詳見 [ADR-0003](./0003-rrf-relevance-citations-and-tool-trust.md)。實測 CPU 重排每對約 0.2 至 0.4 秒，遠高於上文估計的數十毫秒。
- **2026-09-24｜片段改以資料庫 chunk_id 為準**：片段存在 `rag_chunks` 資料表，FAISS 改用 `IndexIDMap2`，並與 BM25 一起以 chunk_id 對應，啟動時依資料庫校正，取代依清單位置對齊的 `documents.pkl`，詳見 [ADR-0005](./0005-chunk-id-index-and-database-source-of-truth.md)。