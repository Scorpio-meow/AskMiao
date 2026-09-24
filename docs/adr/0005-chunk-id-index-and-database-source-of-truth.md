# ADR-0005: 以資料庫 chunk_id 為準的片段索引

[繁體中文](0005-chunk-id-index-and-database-source-of-truth.md) | [English](0005-chunk-id-index-and-database-source-of-truth_en.md)

## 狀態

已通過 (Accepted) - 2026-09-24

補充 [ADR-0001](./0001-hybrid-rag-and-security.md)：保留 FAISS 與 BM25 的混合檢索，改變片段的保存位置與索引的對應鍵。本紀錄於 3.0.0 發行時（2026-09-25）依當時的實作補記。

---

## 背景與問題陳述

2.x 的片段分存在三個地方，彼此靠「清單中的第幾筆」對應：

- `documents.pkl`：以 pickle 保存的片段清單。
- FAISS `IndexFlatIP`：向量的 id 就是加入的順序。
- Whoosh BM25：`doc_id` 是片段在清單中的位置。

這個設計造成四個問題：

1. **錯位**：任何一份寫入或載入失敗（例如 `documents.pkl` 讀取失敗而被清空）、刪除文件或兩個上傳請求同時寫入，都會讓三者的順序不再一致。錯位後檢索會回傳別的片段，而且不會出現任何錯誤。
2. **刪除成本**：`IndexFlatIP` 無法依 id 移除向量，每刪除一份文件，就要重算其餘所有片段的向量並重建 BM25。
3. **無從校正**：片段只存在檔案裡，無法與 `documents` 資料表比對，也無法判斷索引是否與資料一致；唯一的補救是每日自動全量重建（`ENABLE_AUTO_REINDEX_TASK`、`REINDEX_HOURS`）。
4. **阻塞**：檢索、寫入與定期重建都在事件迴圈中同步執行，嵌入大型文件或重建期間，其他請求全部卡住。

---

## 架構決策內容

### 1. 資料庫是片段的唯一來源

- 新增 `rag_chunks` 資料表（`id`、`document_id`、`chunk_index`、`content`、`chunk_metadata`），`id` 即 chunk_id。
- 移除 `documents.pkl` 與 `DOCUMENTS_PATH` 設定。

### 2. 索引以 chunk_id 為鍵

- FAISS 改用 `IndexIDMap2(IndexFlatIP)`，以 `add_with_ids` 與 `remove_ids` 依 chunk_id 新增與刪除；BM25 的 `doc_id` 改存 chunk_id。
- 刪除文件只移除該文件的片段、向量與 BM25 項目，不動其他片段。

### 3. 固定的寫入順序

- 新增片段時，在同一把鎖內依序：計算向量 → 寫入 `rag_chunks` 並取得 id（尚未 commit）→ 以 id 加入 FAISS → commit（失敗時移除剛加入的向量）→ 加入 BM25 → 以暫存檔取代的方式寫回索引檔。
- 檢索也持有同一把鎖；檢索與寫入改在背景執行緒執行，不再阻塞事件迴圈。

### 4. 啟動時依資料庫校正，取代定期重建

- 每次啟動都以 `rag_chunks` 為準：刪除所屬文件已不存在的孤立片段、移除 FAISS 中多餘的 id、補算缺少的向量；BM25 的 chunk_id 集合與資料庫不同時，依資料庫重建。
- 移除每日自動重建任務與 `ENABLE_AUTO_REINDEX`、`ENABLE_AUTO_REINDEX_TASK`、`REINDEX_HOURS` 設定。

### 5. 舊索引不做轉換

- 偵測到舊格式（不是 `IndexIDMap2`）的 FAISS 索引時，改名為 `*.legacy.bak` 保留，不嘗試轉換：舊索引可能早已錯位，轉換只會把錯位帶進新結構。升級後以 `POST /api/documents/rebuild-index` 從 `documents` 資料表重新切塊與嵌入。
- 更換嵌入模型導致向量維度不同時，舊索引改名為 `*.mismatch.bak`，再依資料庫片段重新計算。

---

## 決定產生的影響與權衡

### 正面影響 (Benefits)

- **檢索結果必定對應正確的片段**：任一份索引遺失或損毀，都能在下次啟動時由資料庫補回。
- **刪除成本與文件大小成正比**：不再因為刪除一份文件而重算整個知識庫。
- **引用有穩定的鍵**：[ADR-0003](./0003-rrf-relevance-citations-and-tool-trust.md) 的引用編號以 chunk_id 為鍵，同一片段在一次提問中永遠對應同一個號碼。
- **不再需要定期重建**，檢索與寫入也不再阻塞其他請求。

### 負面影響與挑戰 (Trade-offs & Risks)

- **片段內容存兩份**：資料庫與 BM25 索引都保存片段全文，佔用的空間增加。
- **升級必須完整重建一次**：舊索引無法沿用，重建時每份文件都會重新呼叫 LLM 生成摘要，耗時與文件量成正比。
- **啟動時間**：啟動校正要讀出全部片段；缺少大量向量時，第一次啟動會先補算。
- **鎖只在單一行程內有效**：鎖是行程內的 `threading.RLock`。以多個 worker 或多台主機寫入同一份索引檔時，彼此的變更會互相覆蓋，因此只能由單一後端行程寫入索引。
- **SQLite 外鍵**：SQLite 預設不啟用外鍵，刪除文件列不會連帶刪除片段。正常流程會先刪除片段再刪除文件，例外情況由啟動時的孤立片段清理處理。

### 升級與回退

- **升級**：依 [升級指南](../upgrading.md) 操作。首次啟動後舊索引改名為 `faiss_index.bin.legacy.bak`，執行一次完整重建；確認問答正常後即可刪除 `faiss_index.bin.legacy.bak` 與 `documents.pkl`。
- **回退**：還原升級前備份的 `backend/data/`。`rag_chunks` 資料表可以保留，舊版不會讀取它。
