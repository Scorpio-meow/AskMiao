# 部署指南

[繁體中文](deployment.md) | [English](deployment_en.md)

> 以 `deploy/` 的 Docker Compose 在一台主機（例如 VM）上執行 AskMiao：PostgreSQL、後端與提供前端的 nginx 三個容器。在自己電腦上開發與試用請見 [README：快速開始](../README.md#快速開始)；每個設定的作用見 [設定參考](configuration.md)。

## 目錄

- [架構](#架構)
- [需求](#需求)
- [部署步驟](#部署步驟)
- [以 HTTPS 對外提供](#以-https-對外提供)
- [資料保存與備份](#資料保存與備份)
- [更新到新版本](#更新到新版本)
- [常用指令](#常用指令)

## 架構

| 服務 | 映像 | 作用 |
|---|---|---|
| `postgres` | `postgres:17.9` | 資料庫 `chatbot`。資料庫的 volume 第一次初始化時依序執行 `backend/init.sql`（建立資料表）與 `backend/init-app-role.sh`（建立非超級使用者 `POSTGRES_APP_USER`，後端以這個帳號連線）。不對主機開放連接埠 |
| `backend` | `deploy/Dockerfile.backend`（`python:3.12-slim`，安裝 CPU 版 PyTorch） | FastAPI 後端，以 uid 1000 的 `askmiao` 帳號執行。等 `postgres` 健康檢查通過才啟動；第一次啟動要下載嵌入與重排模型，健康檢查（`GET /health`）最多等待 180 秒再開始計算失敗 |
| `web` | `deploy/Dockerfile.frontend`（以 `oven/bun:1` 建置，`nginx:1.27-alpine` 提供） | 提供前端建置產物，並把 `/api/` 反向代理到 `backend:8001`。唯一對主機開放的服務，連接埠為 `WEB_PORT` |

三個容器都在 compose 的 `askmiao-net` 網路（子網路 `NETWORK_SUBNET`），`web` 固定使用 `WEB_CONTAINER_IP`。nginx 允許的請求本文最多 120 MiB，SSE 串流不經緩衝，讀寫逾時 900 秒（`deploy/nginx.conf`）。

## 需求

- Docker Engine 與 Compose v2（`docker compose` 指令）。
- 執行 `deploy/gen-env.sh` 需要 bash 與 openssl。
- 第一次啟動會下載約 1.2 GB 的模型到 `backend_data` volume，主機需要能連上 Hugging Face。
- 模型的位址與金鑰不寫在設定檔，啟動後在介面上設定成 API 連線（見 [部署步驟](#部署步驟) 第 5 步）。

## 部署步驟

### 1. 取得原始碼

```bash
git clone https://github.com/Scorpio-meow/AskMiao.git
cd AskMiao/deploy
```

### 2. 產生 `deploy/.env`

```bash
PUBLIC_ORIGIN=https://askmiao.example.com \
WEB_PORT=8080 \
NETWORK_SUBNET=172.31.240.0/24 \
WEB_CONTAINER_IP=172.31.240.10 \
./gen-env.sh
```

| 變數 | 說明 |
|---|---|
| `PUBLIC_ORIGIN` | 使用者在瀏覽器開啟 AskMiao 的來源（協定、主機與連接埠）。寫入 `ALLOWED_ORIGINS`；以 `https://` 開頭時 `COOKIE_SECURE` 設為 `true` |
| `WEB_PORT` | 主機上對應到 `web` 容器 80 埠的連接埠 |
| `NETWORK_SUBNET` | compose 內部網路的子網路。請選不會和公司內網、VPN 或主機上其他 Docker 網路重疊的網段 |
| `WEB_CONTAINER_IP` | `web` 容器在該子網路中的固定 IP，寫入 `FORWARDED_ALLOW_IPS`，讓後端採信 nginx 轉送的 `X-Forwarded-For` |

`gen-env.sh` 複製 `backend/.env.example`，再在檔尾加上部署用的設定：`HOST=0.0.0.0`、`ENVIRONMENT=production`、`COOKIE_SECURE`、隨機產生的 `TOOL_SECRETS_KEY`、`POSTGRES_PASSWORD` 與 `POSTGRES_APP_PASSWORD`、`POSTGRES_APP_USER=askmiao_app`、指向 `postgres:5432` 的 `DATABASE_URL`，以及上表的四個值。檔案權限只有擁有者可讀寫；`deploy/.env` 已存在時腳本拒絕覆寫。

這份檔案同時是 compose 的變數來源與後端容器的環境變數。其他設定（例如 `MAX_FILE_SIZE_MB`、`ALLOW_REGISTRATION`）可以直接編輯 `deploy/.env`，各項說明見 [設定參考](configuration.md)。

> [!IMPORTANT]
> 請把 `deploy/.env` 與資料庫備份分開、妥善保存。`TOOL_SECRETS_KEY` 遺失或更換後，已儲存的自訂 API 工具、MCP 伺服器憑證與 API 連線金鑰都無法解密，需要重新輸入。

### 3. 建置並啟動

```bash
docker compose up -d --build
```

`web` 會等 `backend` 健康檢查通過才啟動。第一次啟動下載模型需要幾分鐘，可以用 `docker compose logs -f backend` 觀察進度。

### 4. 建立第一位管理員

```bash
docker compose exec backend python scripts/create_user.py --username admin --email admin@example.com --admin
```

依提示輸入兩次密碼。範本的 `ALLOW_REGISTRATION=false` 不開放自行註冊，其他帳號同樣以這個指令建立（不加 `--admin` 就是一般使用者），也可以由管理員在「管理後台」新增。

### 5. 設定模型並上傳文件

以瀏覽器開啟 `PUBLIC_ORIGIN`，用管理員登入後，到「管理後台 → 共用 API 連線」建立連線，再到「知識庫」上傳文件，步驟與 [README：上傳文件並開始提問](../README.md#5-上傳文件並開始提問) 相同。

## 以 HTTPS 對外提供

`web` 容器只提供 HTTP。對外以 HTTPS 提供時，在主機上或前方的反向代理終結 TLS，再轉送到 `WEB_PORT`：

- `PUBLIC_ORIGIN` 要填使用者實際開啟的 `https://` 網址，重新整理權杖的 Cookie 才會設定 `Secure`。
- 前方的反向代理要允許與容器內 nginx 相同的 120 MiB 請求本文，關閉 SSE 回應的緩衝，並把讀取逾時設為 900 秒以上，否則長時間的研究會被中斷。
- 容器內的 nginx 以 `X-Forwarded-For: $remote_addr` 轉送，前方還有一層反向代理時，後端看到的來源位址都是那一層代理，速率限制與依位址的登入節流會由所有使用者共用。調整門檻時請參考 [設定參考：登入失敗節流](configuration.md#登入失敗節流)。

## 資料保存與備份

| Volume | 容器內位置 | 內容 |
|---|---|---|
| `postgres_data` | `/var/lib/postgresql/data` | 使用者、對話、文件與片段（`rag_chunks`）、工具、技能與 API 連線的資料 |
| `backend_data` | `/app/data` | 上傳的原始檔、FAISS 與 BM25 索引、Agent Skills 的技能檔案（`SKILLS_DIR`）、模型快取 |
| `backend_keys` | `/app/keys` | 簽署 JWT 的 RSA 金鑰。遺失後所有人都要重新登入 |
| `backend_logs` | `/app/logs` | `app.log` 與 `security.log` |

備份時一併保存：

1. 資料庫：`docker compose exec postgres pg_dump -U postgres chatbot > askmiao.sql`。
2. `deploy/.env`（含 `TOOL_SECRETS_KEY` 與資料庫密碼）。
3. `backend_data` 中的上傳檔與技能檔案。FAISS 與 BM25 索引不必備份：後端啟動時會依資料庫的 `rag_chunks` 補齊缺少的索引（見 [系統架構：啟動時校正](architecture.md#啟動時校正)），模型快取也可以重新下載。

`docker compose down` 會保留 volume；`docker compose down -v` 會連同所有資料一起刪除。

## 更新到新版本

1. 先閱讀 [升級指南](upgrading.md) 中從目前版本到新版本的每一節，並備份資料。
2. 更新原始碼後，在 `deploy/` 重新建置並啟動：

   ```bash
   docker compose up -d --build
   ```

3. 新版本新增的必填設定要手動加進 `deploy/.env`（`gen-env.sh` 不會覆寫既有檔案），例如 8.0.0 新增的 `LOG_DIR`。缺少時後端無法啟動，`docker compose logs backend` 會列出欄位名稱。

資料表的新欄位在後端啟動時自動補上，不需要另外執行遷移。

## 常用指令

在 `deploy/` 執行：

| 指令 | 用途 |
|---|---|
| `docker compose ps` | 查看三個服務的狀態與健康檢查結果 |
| `docker compose logs -f backend` | 追蹤後端日誌 |
| `docker compose up -d` | 修改 `deploy/.env` 後套用：重建設定有變更的容器（`restart` 不會重新讀取 `deploy/.env`） |
| `docker compose exec backend python scripts/<腳本>` | 執行維運腳本，見 [README：維運腳本](../README.md#維運腳本) |
| `docker compose down` | 停止並移除容器，保留 volume |