# ADR-0004: 工具管理權限、MCP 子行程隔離與逐跳 SSRF 驗證

[繁體中文](0004-tool-admin-permissions-and-subprocess-isolation.md) | [English](0004-tool-admin-permissions-and-subprocess-isolation_en.md)

## 狀態

已通過 (Accepted) - 2026-09-25

補充 [ADR-0002](./0002-external-tools-and-outbound-safety.md)：新增工具管理權限與子行程環境隔離，並讓 ADR-0002 對 MCP HTTP 傳輸的 SSRF 防護承諾實際生效。

---

## 背景與問題陳述

1. **任何註冊使用者都能在主機上執行指令**：`POST /api/auth/register` 開放自行註冊，而 `/api/mcp` 與 `/api/api-tools` 的端點只檢查是否登入。建立 `stdio` 類型的 MCP 伺服器時，後端會立即以請求內容中的 `command`、`args` 呼叫 `asyncio.create_subprocess_exec`，等同任何註冊使用者都能遠端執行任意指令（RCE）。
2. **工具是全域設定**：啟用中的自訂 API 工具與 MCP 伺服器會載入每位使用者的 Agent。一般使用者可以改動所有人的工具定義（例如在工具描述中夾帶提示注入），也能透過查詢端點讀到別人設定的憑證（`auth_config`、`headers`、`env_vars`）。
3. **子行程繼承後端全部環境變數**：`McpStdioClient` 以 `dict(os.environ)` 啟動子行程，任何第三方 MCP 伺服器套件都拿得到 `JWT_SECRET_KEY`、`DATABASE_URL` 與模型 API 金鑰。
4. **SSRF 防護有缺口**：ADR-0002 寫明 MCP HTTP 傳輸須通過 SSRF 驗證，但 `McpHttpClient` 從未呼叫驗證函式；自訂 API 工具只驗第一個網址就跟隨轉址，外部 API 可以把請求轉到 `169.254.169.254` 等內部位址。

---

## 架構決策內容

### 1. 工具管理只開放管理員

- `/api/mcp` 與 `/api/api-tools` 的所有端點（含查詢與範本清單）改用 `get_current_admin_user`，非管理員一律回傳 403，且不會啟動子行程或送出外部請求。
- 前端「AI 工具」頁（`/tools`）改用 `AdminRoute`，導覽列只對管理員顯示此項。一般使用者只能在對話中讓 Agent 使用已啟用的工具。
- 考慮過保留唯讀清單給一般使用者並遮蔽憑證，但此頁本質是管理介面，遮蔽需另設回應模型；確有需求時再另行加入。

### 2. stdio 子行程只繼承系統必要變數

- 子行程環境改由 `build_stdio_env()` 組成：只繼承 MCP 官方 SDK 預設清單中的系統變數（Windows 為 `APPDATA`、`HOMEDRIVE`、`HOMEPATH`、`LOCALAPPDATA`、`PATH`、`PATHEXT`、`PROCESSOR_ARCHITECTURE`、`SYSTEMDRIVE`、`SYSTEMROOT`、`TEMP`、`USERNAME`、`USERPROFILE`；其他平台為 `HOME`、`LOGNAME`、`PATH`、`SHELL`、`TERM`、`USER`），略過以 `()` 開頭的 shell 函式定義，再加上該伺服器設定的 `env_vars`。

### 3. 每一跳都做 SSRF 驗證

- 新增 httpx request hook `reject_unsafe_request`，在第一個請求與每次轉址送出前重新執行 `validate_url_ssrf`，套用於 `execute_http_api_tool` 與 `McpHttpClient`。
- MCP 伺服器被拒絕時，`last_error` 與探索端點的 400 回應直接顯示拒絕原因；此訊息只描述管理員填入的網址，不含內部資訊。

### 4. 不採用 stdio 指令白名單

- 考慮過以設定檔限制可執行的指令，但預設範本依賴的 `python`、`npx`、`uvx` 本身就能透過參數執行任意程式碼，執行檔白名單無法構成真正的邊界。真正的邊界是「只有管理員能設定工具」。

---

## 決定產生的影響與權衡

### 正面影響 (Benefits)

- **封閉 RCE**：一般使用者無法再建立、修改或執行 MCP 伺服器與自訂 API 工具。
- **憑證不外流**：一般使用者讀不到工具憑證；第三方 MCP 套件拿不到後端的金鑰與資料庫連線。
- **SSRF 承諾落實**：ADR-0002 對 MCP HTTP 傳輸的承諾生效，轉址也無法繞過驗證。
- **可回歸測試**：`backend/tests/test_tool_admin_permissions.py` 逐一列舉兩個模組的所有路由，新增端點若漏掉管理員檢查會直接測試失敗。

### 負面影響與挑戰 (Trade-offs & Risks)

- **一般使用者看不到工具頁**：包含原本的唯讀概覽。
- **本機或內網的 MCP HTTP 伺服器會被拒絕**：與 ADR-0002 接受的「誤擋內網 API」取捨一致；本機的 MCP 伺服器請改用 `stdio` 傳輸。
- **管理員等同主機的 shell 權限**：`stdio` 仍會執行管理員設定的指令，管理員帳號需以同等級的方式保護。
- **降權有延遲**：`is_admin` 取自存取權杖，取消某人的管理員身分後，要等其存取權杖到期（`ACCESS_TOKEN_EXPIRE_MINUTES`）才生效；這是所有管理員端點的既有行為。

### 升級與回退

- 無資料表或設定變更，不需遷移。
- 依賴後端環境變數的 `stdio` 伺服器（例如 `HTTP_PROXY`、`HTTPS_PROXY`、`NODE_EXTRA_CA_CERTS` 或各種存取權杖）需把變數寫進該伺服器的 `env_vars`。
- 指向 `localhost` 或內網位址的 MCP HTTP 伺服器，升級後探索會失敗並在 `last_error` 顯示原因。
- 回退時還原程式碼即可。

---

## 後續修訂 (Amendments)

- **2026-09-25｜SSRF 拒絕原因只寫入日誌**：拒絕原因可能含伺服器端 DNS 解析出的內網 IP 或轉址目標，不只描述管理員填入的網址（CodeQL `py/stack-trace-exposure`）。MCP 伺服器被拒絕時，`last_error` 與探索端點的 400 回應改為註明遭 SSRF 防護拒絕並附錯誤代碼，完整原因只寫入伺服器日誌。
- **2026-09-27｜移除 `mcp_fetch` 範本**：`uvx mcp-server-fetch` 以 `stdio` 子行程自行連外，完全繞過 `web_fetch` 的 SSRF 驗證、`WEB_FETCH_ALLOWED_DOMAINS` 與網址來源限制，且子行程無法套用本 ADR 第 3 點的逐跳驗證。範本清單不再提供網頁擷取類伺服器；已建立的同名伺服器不會被刪除，由管理員自行評估。
- **2026-09-27｜檔案系統範本改用專屬沙箱**：`mcp_filesystem` 原本以相對路徑 `./data` 為根目錄，實際指向後端的資料目錄（含以 pickle 載入的索引中繼資料與上傳原檔）。範本改為絕對路徑 `backend/mcp_filesystem_sandbox`（呼叫範本清單時自動建立），並釘選 `@modelcontextprotocol/server-filesystem@2026.8.31`，避免每次執行時解析到未審閱的新版。
- **2026-09-27｜終止整個子行程樹並限制數量**：`npx`、`uvx` 會再啟動孫行程，原本只終止直接子行程會留下孤兒行程。`stdio` 子行程改為自成一個程序群組（Windows 為新的 process group，其他平台為新的 session），關閉時以 `taskkill /T /F` 或對整個群組送 `SIGTERM`、`SIGKILL` 終止；同時最多 4 個子行程，其餘排隊等候。
- **2026-09-27｜SSRF 驗證固定連線 IP**：第 3 點的 request hook 驗證與實際連線各做一次 DNS 解析，可被 DNS rebinding 繞過。自訂 API 工具與 MCP HTTP 傳輸改用 `SSRFSafeTransport`，每一跳驗證後把連線固定在核可的 IP（`Host` 與 TLS SNI 仍用原主機名稱）；這些請求因此不再使用 `HTTP_PROXY`、`HTTPS_PROXY`。
- **2026-09-27｜降權即時生效**：負面影響中的「降權有延遲」不再成立。每次請求都依權杖的 `sub` 從資料庫讀取帳號，`is_admin` 取自資料庫，停用或刪除帳號後既有權杖立即失效。
- **2026-09-27｜呼叫前核准**：管理員啟用的工具仍可能被提示注入誘導執行有副作用的呼叫。自訂 API 工具與 MCP 伺服器新增 `requires_approval` 旗標，Agent 呼叫前須由發問的使用者在對話中核准，見 [ADR-0006](./0006-tool-call-approval.md)。
