// 內建工具的說明卡片；後端回傳的工具說明會以 backendDescription 附加上去
export const DEFAULT_TOOLS_METADATA = [
  {
    name: 'search_knowledge_base',
    displayName: '知識庫智能檢索',
    category: 'knowledge',
    categoryName: '內部知識庫',
    icon: 'search',
    summary: '基於 FAISS 向量語意與 BM25 關鍵字混合檢索演算法，深入內部專業文件庫進行高精度段落匹配與置信度評分。',
    executionMode: '自主調用 / Function Calling',
    priority: '內部專業提問第一優先級',
    triggerTiming: '當使用者詢問公司制度、專案架構、技術文件、內部貼文細節或特定檔案內容時自動觸發。',
    examples: [
      '請查詢知識庫中關於專案架構的相關文件',
      '知識庫中有提到系統的佈署流程與注意事項嗎？',
      '查詢關於 API 規格說明的檔案內容'
    ],
    parameters: [
      { name: 'query', type: 'string', required: true, desc: '要檢索的繁體中文、英文關鍵字、作者帳號或特定網址' },
      { name: 'target_document', type: 'string', required: false, desc: '可選：限定搜尋的特定文件檔案名稱（如特定 .md 或 .js 檔）' },
      { name: 'top_k', type: 'integer', required: false, desc: '返回的最相關片段數量（預設 3，最大 5）' }
    ]
  },
  {
    name: 'filter_and_count_records',
    displayName: '記錄精準統計與篩選',
    category: 'knowledge',
    categoryName: '內部知識庫',
    icon: 'analytics',
    summary: '針對知識庫中的結構化記錄、貼文與文檔進行條件過濾與計數（精確 count），支援精確發布時間、作者帳號與全文關鍵字篩選。',
    executionMode: '自主調用 / Function Calling',
    priority: '統計與清單查詢最高優先級',
    triggerTiming: '當使用者提問「總共有幾則」、「統計某年某月貼文數量」、「列出某作者的所有記錄」時強制調用。',
    examples: [
      '統計知識庫中 2026年8月 的全部貼文數量與內容',
      '查詢某作者的所有記錄總共有幾則？',
      '篩選包含特定關鍵字的結構化記錄清單'
    ],
    parameters: [
      { name: 'date_range', type: 'string', required: false, desc: '篩選發布日期或月份（如 2026-08、2026年8月、2025-10-22）' },
      { name: 'author', type: 'string', required: false, desc: '篩選特定作者帳號（如 @username）' },
      { name: 'keyword', type: 'string', required: false, desc: '篩選內容中包含的關鍵字' },
      { name: 'target_document', type: 'string', required: false, desc: '限定的文件名稱' },
      { name: 'limit', type: 'integer', required: false, desc: '返回清單筆數上限（預設 50，最大 200）' }
    ]
  },
  {
    name: 'web_search',
    displayName: '即時聯網搜尋',
    category: 'web',
    categoryName: '聯網與外部',
    icon: 'language',
    summary: '當內部知識庫未收錄相關資料時，調用外部搜尋引擎（優先使用官方 Search API，自動容錯切換 DuckDuckGo 備援）獲取最新即時公開資訊。',
    executionMode: '自主調用 / 備援引擎容錯',
    priority: '即時外部資訊優先',
    triggerTiming: '當詢問外部時事新聞、最新科技動態、或內部知識庫無收錄的外部公開資訊時自動調用。',
    examples: [
      '搜尋目前最新的 AI 技術發展動態',
      '查詢今日最新科技產業時事新聞',
      '搜尋外部開源專案的最新版本與更新紀錄'
    ],
    parameters: [
      { name: 'query', type: 'string', required: true, desc: '搜尋引擎關鍵字' },
      { name: 'max_results', type: 'integer', required: false, desc: '最大搜尋結果筆數（預設 5）' }
    ]
  },
  {
    name: 'web_fetch',
    displayName: '網頁全文深入閱讀',
    category: 'web',
    categoryName: '聯網與外部',
    icon: 'description',
    summary: '針對指定的公開網址進行全文抓取與 HTML 結構清洗，擷取核心文章本文供 AI 深度閱讀、交叉驗證與摘要總結。',
    executionMode: '自主調用 / 內容解析',
    priority: '網址深入探討專用',
    triggerTiming: '當使用者在問題中提供特定網址連結，或搜尋摘要需要進一步深入探討閱讀全文時調用。',
    examples: [
      '請深入閱讀這個網頁並整理出重點摘要：https://example.com/article',
      '分析指定網址的技術架構與特點說明'
    ],
    parameters: [
      { name: 'url', type: 'string', required: true, desc: '要讀取的完整網址（http:// 或 https://）' }
    ]
  }
];
