# AskMiao 架構決策紀錄 (Architecture Decision Records)

[繁體中文](README.md) | [English](README_en.md)

本目錄記錄 AskMiao 系統開發過程中的重要架構決策、技術選型背景、替換方案評估與最終權衡結果。

---

## 決策紀錄索引

| ADR 編號 | 標題 | 狀態 | 決策日期 | 摘要 |
|---|---|---|---|---|
| [ADR-0001](./0001-hybrid-rag-and-security.md) | 增強型混合 RAG 檢索架構與雙 Token 安全防護決策 | 已通過 (Accepted) | 2026-08-01 | 採用 FAISS + Whoosh + Cross-Encoder 混合 RAG 與 RSA-2048 JWT 雙 Token 防護 |
| [ADR-0002](./0002-external-tools-and-outbound-safety.md) | 外部工具擴充機制與出站請求安全防護決策 | 已通過 (Accepted) | 2026-09-01 | 以資料庫驅動之自訂 API / MCP 工具註冊，並集中實施 SSRF 防護與錯誤代碼機制 |
| [ADR-0003](./0003-rrf-relevance-citations-and-tool-trust.md) | RRF 融合、相關性門檻、引用對應與工具輸出信任邊界 | 已通過 (Accepted) | 2026-09-24 | 兩軌必跑的標準 RRF、以重排機率為相關性門檻、答案引用對應來源，並為工具輸出設立信任邊界與聯網限制；取代 ADR-0001 的分數歸一化融合 |

---

## ADR 撰寫規範

新增架構決策紀錄時，請遵循以下結構範本：

1. **標題與編號**：格式為 `ADR-XXXX: [決策標題]`
2. **狀態**：`提議 (Proposed)` / `已通過 (Accepted)` / `已廢棄 (Deprecated)` / `已被取代 (Superseded)`
3. **背景 (Context)**：為何需要做出此項決策？面臨何種技術挑戰或業務需求？
4. **決策內容 (Decision)**：我們選擇了什麼方案？
5. **影響與權衡 (Consequences)**：該決策帶來的優點、風險與相應的權衡。