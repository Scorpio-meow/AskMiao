# AskMiao 介紹頁（GitHub Pages）

此目錄是專案介紹頁的完整原始檔：純靜態 HTML、CSS 與 JavaScript，沒有建置步驟，直接部署即可。

## 目錄結構

```text
site/
├── index.html          # 單頁介紹（內含 Phosphor 圖示 sprite）
├── styles.css          # 設計 token、淺色 / 深色主題與版面
├── main.js             # 主題切換、捲動顯示、推理檔位與 SSRF 檢查示意、複製指令
└── assets/
    ├── logo-*.png / favicon-*.png / apple-touch-icon.png   # 由 frontend/public/favicon.png 產生
    ├── og-image.png    # 社群分享預覽圖（1200 x 630）
    ├── logos/          # 技術堆疊圖示（Simple Icons，CC0）
    └── screens/        # 實際前端介面截圖，淺色與深色各一版（WebP）
```

## 部署

`.github/workflows/deploy-pages.yml` 會在 `Bun` 分支的 `site/` 有變更時，把整個目錄上傳並部署到 GitHub Pages，也可從 Actions 頁面手動觸發。

一次性設定：GitHub 儲存庫 **Settings → Pages → Build and deployment → Source** 選擇 **GitHub Actions**。

部署完成後的網址為 `https://scorpio-meow.github.io/AskMiao/`。若改用自訂網域，請同步更新 `index.html` 中的 `canonical` 與 `og:*` 網址。

## 本機預覽

```bash
python -m http.server 4173 --directory site
```

或使用 Bun：

```bash
bunx serve site -l 4173
```

## 截圖來源

`assets/screens/` 的畫面是以本專案的真實前端（`frontend/`）搭配回傳示意資料的模擬後端，於無頭 Chrome 中擷取而成，並非手繪示意圖。畫面中的文件名稱、對話內容與統計數字皆為示意資料。介面有重大改版時，請重新擷取淺色與深色兩版並覆蓋同名檔案。

## 第三方素材

- 字型：Geist、Geist Mono、Noto Sans TC（Google Fonts，SIL Open Font License）
- 品牌圖示：[Simple Icons](https://simpleicons.org/)（CC0 1.0）
- 介面圖示：[Phosphor Icons](https://phosphoricons.com/)（MIT）
