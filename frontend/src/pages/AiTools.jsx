import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { chatService, apiToolService, mcpService } from '../services/api';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import {
  Alert,
  Button,
  ConfirmDialog,
  Dialog,
  DialogActions,
  DialogContent,
  DialogForm,
  DialogTitle,
  Icon,
  Snackbar,
  Switch
} from '../components/ui';
import styles from './AiTools.module.css';
const DEFAULT_TOOLS_METADATA = [
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
const SAMPLE_OAS_SPECS = {
  oas2: `swagger: '2.0'
info:
  title: 即時天氣查詢 API (Swagger 2.0)
  version: 1.0.0
host: httpbin.org
basePath: /
schemes:
  - https
paths:
  /get:
    get:
      summary: 查詢指定城市之即時天氣與氣溫
      operationId: get_weather_by_city
      parameters:
        - name: city
          in: query
          required: true
          type: string
          description: 城市名稱（例如 Taipei, Tokyo, New York）`,
  oas30: `openapi: 3.0.3
info:
  title: 匯率即時轉換服務 (OpenAPI 3.0)
  version: 1.0.0
servers:
  - url: https://httpbin.org
paths:
  /anything/rates:
    get:
      summary: 查詢法幣與加密貨幣即時匯率換算
      operationId: get_exchange_rate
      parameters:
        - name: from_currency
          in: query
          required: true
          schema:
            type: string
          description: 來源貨幣代碼（例如 USD, TWD, EUR）
        - name: to_currency
          in: query
          required: true
          schema:
            type: string
          description: 目標貨幣代碼（例如 TWD, JPY, USD）`,
  oas31: `openapi: 3.1.0
info:
  title: 工單通知派遣服務 (OpenAPI 3.1)
  version: 2.0.0
servers:
  - url: https://httpbin.org
paths:
  /post:
    post:
      summary: 發送緊急工單派遣通知
      operationId: send_dispatch_ticket
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                ticket_id:
                  type:
                    - string
                    - integer
                  description: 工單編號
                title:
                  type: string
                  description: 工單標題
                priority:
                  type: string
                  enum: [low, medium, high, urgent]
                  description: 優先等級
              required: [ticket_id, title]`
};
const EMPTY_MCP_FORM = {
  name: '',
  display_name: '',
  description: '',
  transport_type: 'stdio',
  command: '',
  args_json: '[]',
  env_vars_json: '{}',
  url: '',
  headers_json: '{}',
  timeout: 30
};
const EMPTY_TOOL_FORM = {
  name: '',
  display_name: '',
  description: '',
  method: 'GET',
  url: '',
  auth_type: 'none',
  auth_token: '',
  timeout: 15,
  parameters_json: '{\n  "type": "object",\n  "properties": {\n    "query": {\n      "type": "string",\n      "description": "參數說明"\n    }\n  },\n  "required": ["query"]\n}'
};
// 解析 JSON 欄位；失敗時指出是哪個欄位，讓錯誤訊息能對應到表單上的位置
const parseJsonField = (value, fieldLabel) => {
  if (!value) return undefined;
  try {
    return JSON.parse(value);
  } catch (e) {
    throw new Error(`「${fieldLabel}」不是有效的 JSON：${e.message}`, { cause: e });
  }
};
const getRequestErrorMessage = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (err instanceof Error && err.message && !err.response) return err.message;
  return fallback;
};
const matchesQuery = (query, ...values) =>
  values.some((value) => typeof value === 'string' && value.toLowerCase().includes(query));
const CATEGORY_FILTERS = [
  { value: 'all', label: '全部工具' },
  { value: 'mcp', label: 'MCP 協定伺服器' },
  { value: 'knowledge', label: '知識庫與資料' },
  { value: 'web', label: '聯網與閱讀' },
  { value: 'custom_api', label: '自訂 API 工具' },
];
export default function AiTools() {
  const navigate = useNavigate();
  const [defaultTools, setDefaultTools] = useState(DEFAULT_TOOLS_METADATA);
  const [customTools, setCustomTools] = useState([]);
  const [mcpServers, setMcpServers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeCategory, setActiveCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  useDocumentTitle('AI 工具');
  // 提示訊息（對話框開啟時的錯誤改顯示在對話框內）
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info', key: 0 });
  const [dialogError, setDialogError] = useState('');
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  // OpenAPI 匯入 Modal 狀態
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [specInput, setSpecInput] = useState('');
  const [defaultBaseUrl, setDefaultBaseUrl] = useState('');
  const [parsing, setParsing] = useState(false);
  const [parseResult, setParseResult] = useState(null);
  const [selectedEndpoints, setSelectedEndpoints] = useState({});
  const [globalAuthToken, setGlobalAuthToken] = useState('');
  const [importing, setImporting] = useState(false);
  // 手動自訂 API 工具 Modal 狀態
  const [toolModalOpen, setToolModalOpen] = useState(false);
  const [editingTool, setEditingTool] = useState(null);
  const [formData, setFormData] = useState(EMPTY_TOOL_FORM);
  const [savingTool, setSavingTool] = useState(false);
  // 自訂 API 工具線上測試 Modal 狀態
  const [testModalOpen, setTestModalOpen] = useState(false);
  const [testingTool, setTestingTool] = useState(null);
  const [testArgs, setTestArgs] = useState({});
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  // MCP 伺服器 Modal 狀態
  const [mcpModalOpen, setMcpModalOpen] = useState(false);
  const [mcpPresets, setMcpPresets] = useState([]);
  const [editingMcpServer, setEditingMcpServer] = useState(null);
  const [mcpFormData, setMcpFormData] = useState(EMPTY_MCP_FORM);
  const [savingMcp, setSavingMcp] = useState(false);
  // MCP 工具線上測試 Modal 狀態
  const [mcpTestModalOpen, setMcpTestModalOpen] = useState(false);
  const [testingMcpServer, setTestingMcpServer] = useState(null);
  const [testingMcpTool, setTestingMcpTool] = useState(null);
  const [mcpTestArgs, setMcpTestArgs] = useState({});
  const [mcpTesting, setMcpTesting] = useState(false);
  const [mcpTestResult, setMcpTestResult] = useState(null);
  const [discoveringId, setDiscoveringId] = useState(null);
  const showSnackbar = (message, severity) => {
    setSnackbar((prev) => ({ open: true, message, severity, key: prev.key + 1 }));
  };
  // 載入後端工具清單與 MCP 伺服器
  const fetchAllTools = useCallback(async () => {
    try {
      setLoading(true);
      const [resDefault, resCustom, resMcp, resPresets] = await Promise.allSettled([
        chatService.getTools(),
        apiToolService.getTools(),
        mcpService.getServers(),
        mcpService.getPresets()
      ]);
      if (resDefault.status === 'fulfilled' && resDefault.value?.tools) {
        const updated = DEFAULT_TOOLS_METADATA.map((meta) => {
          const matched = resDefault.value.tools.find(
            (t) => (t.function ? t.function.name : t.name) === meta.name
          );
          if (matched) {
            const func = matched.function || matched;
            return { ...meta, backendDescription: func.description };
          }
          return meta;
        });
        setDefaultTools(updated);
      }
      if (resCustom.status === 'fulfilled' && resCustom.value?.tools) {
        setCustomTools(resCustom.value.tools);
      }
      if (resMcp.status === 'fulfilled' && resMcp.value?.servers) {
        setMcpServers(resMcp.value.servers);
      }
      if (resPresets.status === 'fulfilled' && resPresets.value?.presets) {
        setMcpPresets(resPresets.value.presets);
      }
    } catch (err) {
      console.warn('載入工具清單失敗:', err);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    queueMicrotask(() => {
      fetchAllTools();
    });
  }, [fetchAllTools]);
  const handleTestExample = (exampleText) => {
    navigate('/chat', { state: { prefillPrompt: exampleText } });
  };
  // 切換自訂 API 工具啟用狀態
  const handleToggleCustomTool = async (toolId) => {
    try {
      const res = await apiToolService.toggleTool(toolId);
      setCustomTools((prev) =>
        prev.map((t) => (t.id === toolId ? { ...t, is_enabled: res.is_enabled } : t))
      );
      showSnackbar(res.message, 'success');
    } catch (err) {
      console.warn('切換工具狀態失敗:', err);
      showSnackbar(getRequestErrorMessage(err, '切換狀態失敗'), 'error');
    }
  };
  // 刪除自訂 API 工具或 MCP 伺服器（先經過確認對話框）
  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    const { type, item } = pendingDelete;
    setDeleting(true);
    try {
      if (type === 'tool') {
        await apiToolService.deleteTool(item.id);
        setCustomTools((prev) => prev.filter((t) => t.id !== item.id));
        showSnackbar(`已刪除工具「${item.display_name}」`, 'success');
      } else {
        await mcpService.deleteServer(item.id);
        setMcpServers((prev) => prev.filter((s) => s.id !== item.id));
        showSnackbar(`已刪除 MCP 伺服器「${item.display_name}」`, 'success');
      }
    } catch (err) {
      console.warn('刪除失敗:', err);
      showSnackbar(getRequestErrorMessage(err, '刪除失敗，請稍後再試'), 'error');
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  };
  // 開啟 OpenAPI 匯入 Modal：輸入框保持空白，需要範例時再按按鈕載入
  const handleOpenImportModal = () => {
    setSpecInput('');
    setDefaultBaseUrl('');
    setParseResult(null);
    setGlobalAuthToken('');
    setDialogError('');
    setImportModalOpen(true);
  };
  // 解析 OpenAPI 規格
  const handleParseSpec = async () => {
    if (!specInput.trim()) {
      setDialogError('請輸入 OpenAPI 規格內容或網址');
      return;
    }
    try {
      setParsing(true);
      setDialogError('');
      const res = await apiToolService.parseOpenApiSpec(specInput, defaultBaseUrl);
      if (res?.data) {
        setParseResult(res.data);
        const sel = {};
        res.data.endpoints.forEach((ep) => {
          sel[ep.name] = true;
        });
        setSelectedEndpoints(sel);
      }
    } catch (err) {
      setDialogError(getRequestErrorMessage(err, '解析 OpenAPI 規格失敗，請檢查格式'));
    } finally {
      setParsing(false);
    }
  };
  // 執行批次匯入
  const handleExecuteImport = async () => {
    if (!parseResult) return;
    const toImport = parseResult.endpoints.filter((ep) => selectedEndpoints[ep.name]);
    if (toImport.length === 0) {
      setDialogError('請至少勾選一個要匯入的 API 端點');
      return;
    }
    try {
      setImporting(true);
      setDialogError('');
      const authConfig = globalAuthToken ? { token: globalAuthToken } : {};
      const authType = globalAuthToken ? 'bearer' : 'none';
      const res = await apiToolService.importTools({
        tools: toImport,
        global_base_url: parseResult.base_url || defaultBaseUrl,
        global_auth_type: authType,
        global_auth_config: authConfig
      });
      setImportModalOpen(false);
      setParseResult(null);
      setSpecInput('');
      showSnackbar(res.message, 'success');
      fetchAllTools();
    } catch (err) {
      console.warn('匯入工具失敗:', err);
      setDialogError(getRequestErrorMessage(err, '匯入工具失敗'));
    } finally {
      setImporting(false);
    }
  };
  // 開啟手動新增/編輯自訂 API Modal
  const handleOpenToolModal = (tool = null) => {
    if (tool) {
      setEditingTool(tool);
      setFormData({
        name: tool.name,
        display_name: tool.display_name,
        description: tool.description,
        method: tool.method,
        url: tool.url,
        auth_type: tool.auth_type || 'none',
        auth_token: tool.auth_config?.token || '',
        timeout: tool.timeout || 15,
        parameters_json: JSON.stringify(tool.parameters_schema || { type: 'object', properties: {} }, null, 2)
      });
    } else {
      setEditingTool(null);
      setFormData(EMPTY_TOOL_FORM);
    }
    setDialogError('');
    setToolModalOpen(true);
  };
  // 儲存自訂 API 工具
  const handleSaveTool = async (e) => {
    e.preventDefault();
    try {
      setDialogError('');
      const parsedSchema = parseJsonField(formData.parameters_json, '參數 JSON Schema 定義') || {};
      const payload = {
        name: formData.name,
        display_name: formData.display_name,
        description: formData.description,
        method: formData.method,
        url: formData.url,
        auth_type: formData.auth_type,
        auth_config: formData.auth_token ? { token: formData.auth_token } : {},
        timeout: Number(formData.timeout) || 15,
        parameters_schema: parsedSchema
      };
      setSavingTool(true);
      if (editingTool) {
        await apiToolService.updateTool(editingTool.id, payload);
        showSnackbar('工具更新成功', 'success');
      } else {
        await apiToolService.createTool(payload);
        showSnackbar('自訂 API 工具建立成功', 'success');
      }
      setToolModalOpen(false);
      fetchAllTools();
    } catch (err) {
      setDialogError(getRequestErrorMessage(err, '儲存失敗，請檢查參數格式與必填欄位'));
    } finally {
      setSavingTool(false);
    }
  };
  // 開啟自訂 API 線上測試 Modal
  const handleOpenTestModal = (tool) => {
    setTestingTool(tool);
    setTestResult(null);
    const initialArgs = {};
    if (tool.parameters_schema?.properties) {
      Object.keys(tool.parameters_schema.properties).forEach((k) => {
        initialArgs[k] = '';
      });
    }
    setTestArgs(initialArgs);
    setTestModalOpen(true);
  };
  // 執行自訂 API 線上測試
  const handleRunTest = async () => {
    if (!testingTool) return;
    try {
      setTesting(true);
      const res = await apiToolService.testTool(testingTool.id, testArgs);
      setTestResult(res.result);
    } catch (err) {
      setTestResult({
        status_code: 500,
        is_success: false,
        error: getRequestErrorMessage(err, '測試請求發送失敗')
      });
    } finally {
      setTesting(false);
    }
  };
  // --- MCP 相關操作 ---
  // 切換 MCP 伺服器啟用狀態
  const handleToggleMcpServer = async (serverId) => {
    try {
      const res = await mcpService.toggleServer(serverId);
      setMcpServers((prev) =>
        prev.map((s) => (s.id === serverId ? { ...s, is_enabled: res.is_enabled } : s))
      );
      showSnackbar(res.message, 'success');
    } catch (err) {
      console.warn('切換 MCP 狀態失敗:', err);
      showSnackbar(getRequestErrorMessage(err, '切換狀態失敗'), 'error');
    }
  };
  // 探索 MCP 工具清單
  const handleDiscoverMcpServer = async (serverId) => {
    try {
      setDiscoveringId(serverId);
      const res = await mcpService.discoverServer(serverId);
      setMcpServers((prev) =>
        prev.map((s) => (s.id === serverId ? res.server : s))
      );
      showSnackbar(res.message, 'success');
    } catch (err) {
      console.warn('探索 MCP 伺服器失敗:', err);
      showSnackbar(getRequestErrorMessage(err, '連線與探索 MCP 工具失敗'), 'error');
      // 重新整理取得更新後的 error status
      fetchAllTools();
    } finally {
      setDiscoveringId(null);
    }
  };
  // 開啟 MCP 新增/編輯 Modal
  const handleOpenMcpModal = (server = null) => {
    if (server) {
      setEditingMcpServer(server);
      setMcpFormData({
        name: server.name,
        display_name: server.display_name,
        description: server.description || '',
        transport_type: server.transport_type || 'stdio',
        command: server.command || '',
        args_json: JSON.stringify(server.args || [], null, 2),
        env_vars_json: JSON.stringify(server.env_vars || {}, null, 2),
        url: server.url || '',
        headers_json: JSON.stringify(server.headers || {}, null, 2),
        timeout: server.timeout || 30
      });
    } else {
      setEditingMcpServer(null);
      setMcpFormData(EMPTY_MCP_FORM);
    }
    setDialogError('');
    setMcpModalOpen(true);
  };
  // 套用 MCP 官方範本
  const handleApplyMcpPreset = (preset) => {
    setMcpFormData({
      name: preset.name,
      display_name: preset.display_name,
      description: preset.description || '',
      transport_type: preset.transport_type || 'stdio',
      command: preset.command || '',
      args_json: JSON.stringify(preset.args || [], null, 2),
      env_vars_json: JSON.stringify(preset.env_vars || {}, null, 2),
      url: preset.url || '',
      headers_json: JSON.stringify(preset.headers || {}, null, 2),
      timeout: preset.timeout || 30
    });
  };
  // 儲存 MCP 伺服器
  const handleSaveMcpServer = async (e) => {
    e.preventDefault();
    try {
      setDialogError('');
      const payload = {
        name: mcpFormData.name,
        display_name: mcpFormData.display_name,
        description: mcpFormData.description,
        transport_type: mcpFormData.transport_type,
        command: mcpFormData.command,
        args: parseJsonField(mcpFormData.args_json, '指令參數清單') || [],
        env_vars: parseJsonField(mcpFormData.env_vars_json, '環境變數配置') || {},
        url: mcpFormData.url,
        headers: parseJsonField(mcpFormData.headers_json, '自訂 HTTP Headers') || {},
        timeout: Number(mcpFormData.timeout) || 30
      };
      setSavingMcp(true);
      if (editingMcpServer) {
        await mcpService.updateServer(editingMcpServer.id, payload);
        showSnackbar('MCP 伺服器配置更新成功', 'success');
      } else {
        await mcpService.createServer(payload);
        showSnackbar('MCP 伺服器建立成功並已嘗試自動連線', 'success');
      }
      setMcpModalOpen(false);
      fetchAllTools();
    } catch (err) {
      setDialogError(getRequestErrorMessage(err, '儲存失敗，請檢查 JSON 欄位格式'));
    } finally {
      setSavingMcp(false);
    }
  };
  // 開啟 MCP 工具測試 Modal
  const handleOpenMcpTestModal = (server, tool) => {
    setTestingMcpServer(server);
    setTestingMcpTool(tool);
    setMcpTestResult(null);
    const initialArgs = {};
    if (tool.inputSchema?.properties) {
      Object.keys(tool.inputSchema.properties).forEach((k) => {
        initialArgs[k] = '';
      });
    }
    setMcpTestArgs(initialArgs);
    setMcpTestModalOpen(true);
  };
  // 執行 MCP 工具線上測試
  const handleRunMcpTest = async () => {
    if (!testingMcpServer || !testingMcpTool) return;
    try {
      setMcpTesting(true);
      const res = await mcpService.testTool(testingMcpServer.id, testingMcpTool.name, mcpTestArgs);
      setMcpTestResult(res.result);
    } catch (err) {
      setMcpTestResult({
        is_success: false,
        error: getRequestErrorMessage(err, 'MCP 工具調用失敗')
      });
    } finally {
      setMcpTesting(false);
    }
  };
  // 計算 MCP 工具總數
  const totalMcpToolsCount = mcpServers.reduce((acc, s) => {
    return acc + (s.discovered_tools?.length || 0);
  }, 0);
  // 整理所有工具以供呈現
  const allUnifiedTools = [
    ...defaultTools.map((t) => ({ ...t, isCustom: false, isMcp: false, is_enabled: true })),
    ...customTools.map((t) => ({
      ...t,
      isCustom: true,
      isMcp: false,
      categoryName: '自訂 API',
      icon: 'code',
      executionMode: '外部 RESTful API',
      priority: '自主按需調用',
      triggerTiming: `當使用者提問與「${t.display_name}」相關之業務或資料時自主調用。`,
      summary: t.description || '外部自訂 API 服務端點。',
      examples: [`請調用 ${t.display_name} 查詢相關資料`, `查詢 ${t.name} 的即時結果`]
    }))
  ];
  const query = searchQuery.trim().toLowerCase();
  const filteredTools = allUnifiedTools.filter((tool) => {
    let matchesCategory = true;
    if (activeCategory === 'knowledge') matchesCategory = tool.category === 'knowledge';
    else if (activeCategory === 'web') matchesCategory = tool.category === 'web';
    else if (activeCategory === 'custom_api') matchesCategory = tool.isCustom;
    const matches = !query || matchesQuery(query, tool.displayName, tool.display_name, tool.name, tool.summary, tool.description, tool.url);
    return matchesCategory && matches;
  });
  const filteredServers = mcpServers.filter((server) => (
    !query || matchesQuery(
      query,
      server.display_name,
      server.name,
      server.description,
      server.command,
      ...(server.args || []),
      server.url,
      ...(server.discovered_tools || []).map((t) => t.name)
    )
  ));
  const showServers = activeCategory === 'all' || activeCategory === 'mcp';
  const showTools = activeCategory !== 'mcp';
  const nothingMatches = Boolean(query) && (!showServers || filteredServers.length === 0) && (!showTools || filteredTools.length === 0);
  const categoryCounts = {
    all: allUnifiedTools.length + totalMcpToolsCount,
    mcp: mcpServers.length,
    knowledge: defaultTools.filter((t) => t.category === 'knowledge').length,
    web: defaultTools.filter((t) => t.category === 'web').length,
    custom_api: customTools.length,
  };
  const getMethodClass = (method) => {
    switch (method?.toUpperCase()) {
      case 'GET': return styles.methodGet;
      case 'POST': return styles.methodPost;
      case 'PUT': return styles.methodPut;
      case 'DELETE': return styles.methodDelete;
      case 'PATCH': return styles.methodPatch;
      default: return styles.methodGet;
    }
  };
  return (
    <div className={styles.container}>
      {/* 頂部 Hero 區塊 */}
      <section className={styles.heroSection}>
        <div className={styles.heroContent}>
          <div className={styles.heroBadge}>
            <Icon name="tune" size={14} />
            <span>AI 工具與 MCP 協定核心中心</span>
          </div>
          <h1 className={styles.heroTitle}>AI 可用工具與 MCP 全景總覽</h1>
          <p className={styles.heroSubtitle}>
            本系統內建自主研究調度引擎（Agentic Research Engine），支援內部知識庫混合檢索、結構化記錄篩選統計、即時聯網搜尋與深入閱讀，並全面原生支援 Model Context Protocol (MCP) 開放標準與全版本 OpenAPI Specification（Swagger 2.0、OpenAPI 3.0 / 3.1）。
          </p>
          <div className={styles.heroActions}>
            <Button
              variant="primary"
              onClick={() => navigate('/chat')}
              startIcon={<Icon name="chat" size={18} />}
            >
              前往對話體驗工具
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleOpenMcpModal()}
              startIcon={<Icon name="build" size={18} />}
            >
              新增 MCP 伺服器
            </Button>
            <Button
              variant="secondary"
              onClick={handleOpenImportModal}
              startIcon={<Icon name="upload" size={18} />}
            >
              匯入 OpenAPI 規格
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleOpenToolModal()}
              startIcon={<Icon name="add" size={18} />}
            >
              手動新增 API 工具
            </Button>
            <Button
              variant="secondary"
              onClick={fetchAllTools}
              loading={loading}
              startIcon={<Icon name="refresh" size={18} />}
            >
              重新整理狀態
            </Button>
          </div>
        </div>
      </section>
      {/* 指標概覽 */}
      <div className={styles.metricsGrid}>
        <div className={styles.metricCard}>
          <span className={styles.metricLabel}>內建核心工具</span>
          <div className={styles.metricValue}>
            <Icon name="tools" size={24} color="var(--color-primary)" />
            <span>{defaultTools.length} 項</span>
          </div>
          <span className={styles.metricDesc}>知識庫檢索、統計、聯網與閱讀</span>
        </div>
        <div className={styles.metricCard}>
          <span className={styles.metricLabel}>MCP 協定伺服器</span>
          <div className={styles.metricValue}>
            <Icon name="build" size={24} color="var(--color-warning)" />
            <span>{mcpServers.length} 台 ({totalMcpToolsCount} 工具)</span>
          </div>
          <span className={styles.metricDesc}>已連線啟用：{mcpServers.filter((s) => s.is_enabled && s.status === 'connected').length} 台</span>
        </div>
        <div className={styles.metricCard}>
          <span className={styles.metricLabel}>自訂 API 工具</span>
          <div className={styles.metricValue}>
            <Icon name="code" size={24} color="var(--color-info)" />
            <span>{customTools.length} 項</span>
          </div>
          <span className={styles.metricDesc}>已啟用：{customTools.filter((t) => t.is_enabled).length} 項</span>
        </div>
        <div className={styles.metricCard}>
          <span className={styles.metricLabel}>標準相容性</span>
          <div className={styles.metricValue}>
            <Icon name="check-circle" size={24} color="var(--color-success)" />
            <span>MCP & OAS 全版本</span>
          </div>
          <span className={styles.metricDesc}>Model Context Protocol + Swagger 2.0 / 3.0 / 3.1</span>
        </div>
      </div>
      {/* 篩選與搜尋列 */}
      <div className={styles.filterBar}>
        <div className={styles.tabGroup} role="group" aria-label="工具分類">
          {CATEGORY_FILTERS.map((filter) => (
            <button
              key={filter.value}
              type="button"
              className={`${styles.tabBtn} ${activeCategory === filter.value ? styles.tabBtnActive : ''}`}
              onClick={() => setActiveCategory(filter.value)}
              aria-pressed={activeCategory === filter.value}
            >
              {filter.label} ({categoryCounts[filter.value]})
            </button>
          ))}
        </div>
        <search className={styles.searchBox}>
          <Icon name="search" size={16} color="var(--text-tertiary)" />
          <input
            type="search"
            className={styles.searchInput}
            placeholder="搜尋工具名稱、網址、MCP 伺服器…"
            aria-label="搜尋工具"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </search>
      </div>
      {nothingMatches && (
        <div className={styles.emptyNotice}>
          <p>查無符合「{searchQuery.trim()}」的工具或 MCP 伺服器</p>
          <Button variant="secondary" size="sm" onClick={() => setSearchQuery('')}>
            清除搜尋
          </Button>
        </div>
      )}
      {/* 1. MCP 伺服器列表區塊 (當 activeCategory === 'mcp' 或 'all' 時展示) */}
      {showServers && !(query && filteredServers.length === 0) && (
        <section className={styles.serverSection} aria-labelledby="mcp-section-title">
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle} id="mcp-section-title">
              <Icon name="build" size={20} color="var(--color-primary)" />
              <span>Model Context Protocol (MCP) 伺服器</span>
            </h2>
            <Button
              variant="secondary"
              onClick={() => handleOpenMcpModal()}
              startIcon={<Icon name="add" size={16} />}
            >
              新增 MCP 伺服器
            </Button>
          </div>
          {filteredServers.length === 0 ? (
            <div className={styles.emptyNotice}>
              <p>尚未配置任何 MCP 伺服器，點擊「新增 MCP 伺服器」即可套用 Time、Filesystem 等預設範本或自訂指令。</p>
            </div>
          ) : (
            <div className={styles.toolsList}>
              {filteredServers.map((server) => {
                const isEnabled = server.is_enabled;
                const isConnected = server.status === 'connected';
                const isError = server.status === 'error';
                const tools = server.discovered_tools || [];
                return (
                  <article key={server.id} className={styles.toolOuterShell} aria-labelledby={`mcp-server-${server.id}`}>
                    <div className={styles.toolInnerCore}>
                      <div className={styles.toolHeader}>
                        <div className={styles.toolIdentity}>
                          <div className={`${styles.toolIconBox} ${styles.toolIconBoxMcp}`}>
                            <Icon name="build" size={22} />
                          </div>
                          <div className={styles.toolTitleWrap}>
                            <h3 className={styles.toolTitle} id={`mcp-server-${server.id}`}>
                              <span className={`${styles.methodBadge} ${styles.methodPost}`}>
                                {server.transport_type}
                              </span>
                              <span>{server.display_name}</span>
                            </h3>
                            <div className={styles.toolIdentifier}>{server.name}</div>
                          </div>
                        </div>
                        <div className={styles.toolStatusWrap}>
                          <span className={styles.categoryTag}>MCP Server</span>
                          <span className={`${styles.statusPill} ${isConnected ? styles.statusActive : isError ? styles.statusError : styles.statusDisabled}`}>
                            <span className={styles.statusDot} />
                            <span>
                              {isConnected ? '已連線 (Connected)' : isError ? '連線錯誤 (Error)' : '未連線'}
                            </span>
                          </span>
                          <div className={styles.switchGroup}>
                            <span className={`${styles.enabledText} ${isEnabled ? styles.enabledTextOn : ''}`}>
                              {isEnabled ? '已啟用' : '已停用'}
                            </span>
                            <Switch
                              checked={isEnabled}
                              onChange={() => handleToggleMcpServer(server.id)}
                              aria-label={`啟用 MCP 伺服器「${server.display_name}」`}
                            />
                          </div>
                        </div>
                      </div>
                      <p className={styles.toolDescription}>{server.description || 'MCP 協定外部工具伺服器。'}</p>
                      {/* 連線執行配置 */}
                      <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                        <div className={styles.specLabel}>
                          <Icon name="terminal" size={14} color="var(--color-primary)" />
                          <span>
                            {server.transport_type === 'stdio' ? 'Stdio 啟動指令與參數' : 'HTTP / SSE 連線網址'}
                          </span>
                        </div>
                        <div className={`${styles.specContent} ${styles.monoText}`}>
                          {server.transport_type === 'stdio'
                            ? `${server.command || ''} ${(server.args || []).join(' ')}`
                            : server.url}
                        </div>
                      </div>
                      {/* 錯誤資訊 */}
                      {server.last_error && (
                        <div className={`${styles.specBlock} ${styles.specBlockSpaced} ${styles.specBlockError}`}>
                          <div className={styles.specLabel}>
                            <Icon name="warning" size={14} />
                            <span>最近一次連線/探索異常紀錄</span>
                          </div>
                          <div className={styles.specContent}>
                            {server.last_error}
                          </div>
                        </div>
                      )}
                      {/* 探索到的 MCP Tools 清單 */}
                      <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                        <div className={`${styles.specLabel} ${styles.specLabelSplit}`}>
                          <div className={styles.inlineGroup}>
                            <Icon name="code" size={14} color="var(--color-primary)" />
                            <span>提供之 MCP 工具 ({tools.length} 項)</span>
                          </div>
                          <Button
                            variant="secondary"
                            onClick={() => handleDiscoverMcpServer(server.id)}
                            loading={discoveringId === server.id}
                            startIcon={<Icon name="refresh" size={14} />}
                          >
                            {discoveringId === server.id ? '正在連線探索...' : '重新探索工具 (tools/list)'}
                          </Button>
                        </div>
                        {tools.length === 0 ? (
                          <p className={styles.mutedNote}>
                            尚未探索到工具，請點擊上方按鈕執行工具探索。
                          </p>
                        ) : (
                          <ul className={styles.mcpToolList} role="list">
                            {tools.map((t) => (
                              <li key={t.name} className={styles.mcpToolItem}>
                                <div className={styles.mcpToolText}>
                                  <div className={styles.mcpToolName}>{t.name}</div>
                                  <div className={styles.mcpToolDescription}>{t.description || '無詳細說明'}</div>
                                </div>
                                <Button
                                  variant="secondary"
                                  onClick={() => handleOpenMcpTestModal(server, t)}
                                  startIcon={<Icon name="speed" size={14} />}
                                >
                                  線上測試<span className="sr-only"> {t.name}</span>
                                </Button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                      {/* 伺服器操作按鈕 */}
                      <div className={styles.toolActionsFooter}>
                        <div className={styles.toolActionGroup}>
                          <Button
                            variant="secondary"
                            onClick={() => handleOpenMcpModal(server)}
                            startIcon={<Icon name="edit" size={16} />}
                          >
                            編輯伺服器配置
                          </Button>
                        </div>
                        <Button
                          variant="danger"
                          onClick={() => setPendingDelete({ type: 'server', item: server })}
                          startIcon={<Icon name="delete" size={16} />}
                        >
                          刪除伺服器
                        </Button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}
      {/* 2. 內部工具與自訂 API 工具列表區塊 */}
      {showTools && !nothingMatches && (
        <div className={styles.toolsList}>
          {filteredTools.length === 0 ? (
            query ? null : activeCategory === 'custom_api' ? (
              <div className={styles.emptyNotice}>
                <p>尚未新增自訂 API 工具。可以匯入 OpenAPI 規格一次建立多個工具，或手動新增單一工具。</p>
                <div className={styles.emptyActions}>
                  <Button variant="primary" size="sm" onClick={handleOpenImportModal} startIcon={<Icon name="upload" size={16} />}>
                    匯入 OpenAPI 規格
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => handleOpenToolModal()} startIcon={<Icon name="add" size={16} />}>
                    手動新增 API 工具
                  </Button>
                </div>
              </div>
            ) : (
              <div className={styles.emptyNotice}>
                <p>這個分類目前沒有工具</p>
              </div>
            )
          ) : (
            filteredTools.map((tool) => {
              const title = tool.display_name || tool.displayName;
              const isEnabled = tool.is_enabled !== false;
              const toolKey = tool.isCustom ? `custom_${tool.id}` : tool.name;
              const parametersList = tool.isCustom
                ? Object.entries(tool.parameters_schema?.properties || {}).map(([pName, pObj]) => ({
                  name: pName,
                  type: pObj.type || 'string',
                  required: tool.parameters_schema?.required?.includes(pName),
                  desc: pObj.description || ''
                }))
                : tool.parameters || [];
              return (
                <article key={toolKey} className={styles.toolOuterShell} aria-labelledby={`tool-${toolKey}`}>
                  <div className={styles.toolInnerCore}>
                    {/* 工具頭部資訊 */}
                    <div className={styles.toolHeader}>
                      <div className={styles.toolIdentity}>
                        <div className={styles.toolIconBox}>
                          <Icon name={tool.icon || 'code'} size={22} />
                        </div>
                        <div className={styles.toolTitleWrap}>
                          <h3 className={styles.toolTitle} id={`tool-${toolKey}`}>
                            {tool.isCustom && tool.method && (
                              <span className={`${styles.methodBadge} ${getMethodClass(tool.method)}`}>
                                {tool.method}
                              </span>
                            )}
                            <span>{title}</span>
                          </h3>
                          <div className={styles.toolIdentifier}>{tool.name}</div>
                        </div>
                      </div>
                      <div className={styles.toolStatusWrap}>
                        <span className={styles.categoryTag}>{tool.categoryName || '工具'}</span>
                        {tool.spec_version && (
                          <span className={styles.versionTag}>{tool.spec_version}</span>
                        )}
                        {tool.isCustom ? (
                          <div className={styles.switchGroup}>
                            <span className={`${styles.statusPill} ${isEnabled ? styles.statusActive : styles.statusDisabled}`}>
                              <span className={styles.statusDot} />
                              <span>{isEnabled ? '已啟用' : '已停用'}</span>
                            </span>
                            <Switch
                              checked={isEnabled}
                              onChange={() => handleToggleCustomTool(tool.id)}
                              aria-label={`啟用工具「${title}」`}
                            />
                          </div>
                        ) : (
                          <span className={`${styles.statusPill} ${styles.statusActive}`}>
                            <span className={styles.statusDot} />
                            <span>內建線上</span>
                          </span>
                        )}
                      </div>
                    </div>
                    {/* 功能簡介 */}
                    <p className={styles.toolDescription}>{tool.summary}</p>
                    {/* URL 與路徑 (自訂工具) */}
                    {tool.isCustom && tool.url && (
                      <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                        <div className={styles.specLabel}>
                          <Icon name="link" size={14} color="var(--color-primary)" />
                          <span>目標 API 請求網址 (Endpoint URL)</span>
                        </div>
                        <div className={`${styles.specContent} ${styles.monoText}`}>
                          {tool.url}
                        </div>
                      </div>
                    )}
                    {/* 核心規格與時機 */}
                    <div className={styles.specsGrid}>
                      <div className={styles.specBlock}>
                        <div className={styles.specLabel}>
                          <Icon name="timeline" size={14} color="var(--color-primary)" />
                          <span>觸發調用時機</span>
                        </div>
                        <div className={styles.specContent}>{tool.triggerTiming}</div>
                      </div>
                      <div className={styles.specBlock}>
                        <div className={styles.specLabel}>
                          <Icon name="tune" size={14} color="var(--color-primary)" />
                          <span>調度機制與特性</span>
                        </div>
                        <div className={styles.specContent}>
                          <div>模式：{tool.executionMode}</div>
                          <div>優先級：{tool.priority}</div>
                        </div>
                      </div>
                    </div>
                    {/* 參數規格說明 */}
                    {parametersList.length > 0 && (
                      <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                        <div className={styles.specLabel}>
                          <Icon name="code" size={14} color="var(--color-primary)" />
                          <span>支援參數規格 (Parameters Schema)</span>
                        </div>
                        <div className={styles.paramsTableWrap}>
                          <table className={styles.paramsTable}>
                            <thead>
                              <tr>
                                <th scope="col" className={styles.paramsColName}>參數名稱</th>
                                <th scope="col" className={styles.paramsColType}>資料型態</th>
                                <th scope="col">說明</th>
                              </tr>
                            </thead>
                            <tbody>
                              {parametersList.map((param) => (
                                <tr key={param.name}>
                                  <td>
                                    <span className={styles.paramName}>{param.name}</span>
                                    {param.required && (
                                      <span className={styles.paramRequired} aria-label="必填">*</span>
                                    )}
                                  </td>
                                  <td>
                                    <span className={styles.paramType}>{param.type}</span>
                                  </td>
                                  <td>{param.desc || '無特定說明'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {/* 自訂工具專屬操作按鈕 */}
                    {tool.isCustom && (
                      <div className={styles.toolActionsFooter}>
                        <div className={styles.toolActionGroup}>
                          <Button
                            variant="secondary"
                            onClick={() => handleOpenTestModal(tool)}
                            startIcon={<Icon name="speed" size={16} />}
                          >
                            即時線上測試
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => handleOpenToolModal(tool)}
                            startIcon={<Icon name="edit" size={16} />}
                          >
                            編輯配置
                          </Button>
                        </div>
                        <Button
                          variant="danger"
                          onClick={() => setPendingDelete({ type: 'tool', item: tool })}
                          startIcon={<Icon name="delete" size={16} />}
                        >
                          刪除工具
                        </Button>
                      </div>
                    )}
                    {/* 推薦提問測試 (內建工具) */}
                    {!tool.isCustom && tool.examples && (
                      <div className={styles.examplesSection}>
                        <div className={styles.examplesTitle}>
                          <Icon name="lightbulb" size={14} color="var(--color-warning)" />
                          <span>測試提問範例（點擊可直接帶入聊天提問）</span>
                        </div>
                        <div className={styles.examplePillsWrap}>
                          {tool.examples.map((ex, idx) => (
                            <button
                              key={idx}
                              type="button"
                              className={styles.examplePill}
                              onClick={() => handleTestExample(ex)}
                            >
                              <Icon name="send" size={12} color="var(--color-primary)" />
                              <span>{ex}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </article>
              );
            })
          )}
        </div>
      )}
      {/* 3. MCP 伺服器新增 / 編輯 */}
      <Dialog open={mcpModalOpen} onClose={savingMcp ? undefined : () => setMcpModalOpen(false)} maxWidth="lg">
        <DialogForm onSubmit={handleSaveMcpServer}>
          <DialogTitle onClose={() => setMcpModalOpen(false)} closeDisabled={savingMcp}>
            {editingMcpServer ? '編輯 MCP 伺服器' : '新增 Model Context Protocol (MCP) 伺服器'}
          </DialogTitle>
          <DialogContent className={styles.dialogBody}>
            {dialogError && <Alert severity="error">{dialogError}</Alert>}
            {!editingMcpServer && mcpPresets.length > 0 && (
              <div className={styles.formGroup}>
                <span className={styles.formLabel} id="mcp-presets-label">快速套用官方與社群範本：</span>
                <div className={styles.inlineButtons} role="group" aria-labelledby="mcp-presets-label">
                  {mcpPresets.map((p) => (
                    <Button
                      key={p.name}
                      variant="secondary"
                      onClick={() => handleApplyMcpPreset(p)}
                    >
                      {p.display_name}
                    </Button>
                  ))}
                </div>
              </div>
            )}
            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="mcp-name">伺服器識別名稱（英文小寫與底線）*</label>
                <input
                  id="mcp-name"
                  type="text"
                  className={styles.formInput}
                  placeholder="例如 mcp_time"
                  value={mcpFormData.name}
                  onChange={(e) => setMcpFormData({ ...mcpFormData, name: e.target.value })}
                  disabled={!!editingMcpServer}
                  required
                  autoComplete="off"
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="mcp-display-name">顯示名稱*</label>
                <input
                  id="mcp-display-name"
                  type="text"
                  className={styles.formInput}
                  placeholder="例如 時間查詢服務"
                  value={mcpFormData.display_name}
                  onChange={(e) => setMcpFormData({ ...mcpFormData, display_name: e.target.value })}
                  required
                  autoComplete="off"
                />
              </div>
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="mcp-description">說明描述</label>
              <input
                id="mcp-description"
                type="text"
                className={styles.formInput}
                placeholder="說明此 MCP 伺服器的功能與用途"
                value={mcpFormData.description}
                onChange={(e) => setMcpFormData({ ...mcpFormData, description: e.target.value })}
                autoComplete="off"
              />
            </div>
            <div className={`${styles.formRow} ${styles.formRowNarrowFirst}`}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="mcp-transport">傳輸模式</label>
                <select
                  id="mcp-transport"
                  className={styles.formSelect}
                  value={mcpFormData.transport_type}
                  onChange={(e) => setMcpFormData({ ...mcpFormData, transport_type: e.target.value })}
                >
                  <option value="stdio">Stdio (子進程)</option>
                  <option value="sse">SSE (Server-Sent Events)</option>
                  <option value="http">HTTP (POST Stream)</option>
                </select>
              </div>
              {mcpFormData.transport_type === 'stdio' ? (
                <div className={styles.formGroup}>
                  <label className={styles.formLabel} htmlFor="mcp-command">啟動指令 (Command)*</label>
                  <input
                    id="mcp-command"
                    type="text"
                    className={styles.formInput}
                    placeholder="例如 npx, uvx, python"
                    value={mcpFormData.command}
                    onChange={(e) => setMcpFormData({ ...mcpFormData, command: e.target.value })}
                    required
                    autoComplete="off"
                  />
                </div>
              ) : (
                <div className={styles.formGroup}>
                  <label className={styles.formLabel} htmlFor="mcp-url">連線網址 (URL)*</label>
                  <input
                    id="mcp-url"
                    type="url"
                    className={styles.formInput}
                    placeholder="例如 http://localhost:8080/sse"
                    value={mcpFormData.url}
                    onChange={(e) => setMcpFormData({ ...mcpFormData, url: e.target.value })}
                    required
                    autoComplete="off"
                  />
                </div>
              )}
            </div>
            {mcpFormData.transport_type === 'stdio' && (
              <>
                <div className={styles.formGroup}>
                  <label className={styles.formLabel} htmlFor="mcp-args">指令參數清單（JSON 陣列格式）</label>
                  <textarea
                    id="mcp-args"
                    className={`${styles.formTextarea} ${styles.textareaMd}`}
                    value={mcpFormData.args_json}
                    onChange={(e) => setMcpFormData({ ...mcpFormData, args_json: e.target.value })}
                    placeholder='["-y", "@modelcontextprotocol/server-filesystem", "./data"]'
                  />
                </div>
                <div className={styles.formGroup}>
                  <label className={styles.formLabel} htmlFor="mcp-env">環境變數配置（JSON 物件格式）</label>
                  <textarea
                    id="mcp-env"
                    className={`${styles.formTextarea} ${styles.textareaSm}`}
                    value={mcpFormData.env_vars_json}
                    onChange={(e) => setMcpFormData({ ...mcpFormData, env_vars_json: e.target.value })}
                    placeholder='{"API_KEY": "secret"}'
                  />
                </div>
              </>
            )}
            {mcpFormData.transport_type !== 'stdio' && (
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="mcp-headers">自訂 HTTP Headers（JSON 物件格式）</label>
                <textarea
                  id="mcp-headers"
                  className={`${styles.formTextarea} ${styles.textareaSm}`}
                  value={mcpFormData.headers_json}
                  onChange={(e) => setMcpFormData({ ...mcpFormData, headers_json: e.target.value })}
                  placeholder='{"Authorization": "Bearer ..."}'
                />
              </div>
            )}
          </DialogContent>
          <DialogActions>
            <Button variant="secondary" onClick={() => setMcpModalOpen(false)} disabled={savingMcp}>
              取消
            </Button>
            <Button variant="primary" type="submit" loading={savingMcp} startIcon={<Icon name="save" size={16} />}>
              {editingMcpServer ? '儲存變更' : '建立並連線探索'}
            </Button>
          </DialogActions>
        </DialogForm>
      </Dialog>
      {/* 4. MCP 工具線上測試 */}
      <Dialog open={mcpTestModalOpen && Boolean(testingMcpServer && testingMcpTool)} onClose={() => setMcpTestModalOpen(false)} maxWidth="lg">
        {testingMcpServer && testingMcpTool && (
          <>
            <DialogTitle onClose={() => setMcpTestModalOpen(false)}>
              即時測試 MCP 工具：{testingMcpTool.name}
            </DialogTitle>
            <DialogContent className={styles.dialogBody}>
              <div className={styles.specBlock}>
                <div className={styles.specLabel}>
                  <span className={`${styles.methodBadge} ${styles.methodPost}`}>{testingMcpServer.display_name}</span>
                  <span>{testingMcpTool.description || '無詳細說明'}</span>
                </div>
              </div>
              <fieldset className={styles.formFieldset}>
                <legend className={styles.formLabel}>輸入參數 (Arguments)</legend>
                {Object.keys(testingMcpTool.inputSchema?.properties || {}).length === 0 ? (
                  <p className={styles.mutedNote}>此 MCP 工具無須輸入額外參數</p>
                ) : (
                  Object.entries(testingMcpTool.inputSchema?.properties || {}).map(([pName, pObj]) => {
                    const inputId = `mcp-arg-${pName}`;
                    const isRequired = testingMcpTool.inputSchema?.required?.includes(pName);
                    return (
                      <div key={pName} className={styles.argField}>
                        <label className={styles.argLabel} htmlFor={inputId}>
                          {pName}{isRequired && <span className={styles.paramRequired} aria-hidden="true">*</span>}
                          <span className={styles.argHint}>({pObj.description || pObj.type})</span>
                        </label>
                        <input
                          id={inputId}
                          type="text"
                          className={styles.formInput}
                          value={mcpTestArgs[pName] || ''}
                          onChange={(e) => setMcpTestArgs({ ...mcpTestArgs, [pName]: e.target.value })}
                          required={isRequired}
                          autoComplete="off"
                        />
                      </div>
                    );
                  })
                )}
              </fieldset>
              {mcpTestResult && (
                <div className={styles.formGroup} aria-live="polite">
                  <div className={styles.resultHeader}>
                    <span className={styles.formLabel}>MCP 回傳結果 (tools/call)</span>
                    <span className={mcpTestResult.is_success ? styles.resultSuccess : styles.resultError}>
                      {mcpTestResult.is_success ? '成功' : '失敗'}
                      {mcpTestResult.duration_seconds !== undefined && `｜耗時 ${mcpTestResult.duration_seconds}s`}
                    </span>
                  </div>
                  <pre className={styles.jsonViewer}>
                    {JSON.stringify(mcpTestResult.content || mcpTestResult, null, 2)}
                  </pre>
                </div>
              )}
            </DialogContent>
            <DialogActions>
              <Button variant="secondary" onClick={() => setMcpTestModalOpen(false)}>
                關閉
              </Button>
              <Button
                variant="primary"
                onClick={handleRunMcpTest}
                loading={mcpTesting}
                startIcon={<Icon name="send" size={16} />}
              >
                {mcpTesting ? '正在調用 MCP...' : '發送 MCP 測試請求'}
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>
      {/* 5. OpenAPI 匯入 */}
      <Dialog open={importModalOpen} onClose={parsing || importing ? undefined : () => setImportModalOpen(false)} maxWidth="lg">
        <DialogTitle onClose={() => setImportModalOpen(false)} closeDisabled={parsing || importing}>
          匯入 OpenAPI / Swagger 規格
        </DialogTitle>
        <DialogContent className={styles.dialogBody}>
          {dialogError && <Alert severity="error">{dialogError}</Alert>}
          {!parseResult ? (
            <>
              <div className={styles.formGroup}>
                <span className={styles.formLabel} id="oas-samples-label">載入測試範例（會取代下方內容）：</span>
                <div className={styles.inlineButtons} role="group" aria-labelledby="oas-samples-label">
                  <Button variant="secondary" onClick={() => setSpecInput(SAMPLE_OAS_SPECS.oas2)}>
                    Swagger 2.0 (即時天氣)
                  </Button>
                  <Button variant="secondary" onClick={() => setSpecInput(SAMPLE_OAS_SPECS.oas30)}>
                    OpenAPI 3.0 (匯率轉換)
                  </Button>
                  <Button variant="secondary" onClick={() => setSpecInput(SAMPLE_OAS_SPECS.oas31)}>
                    OpenAPI 3.1 (工單派遣)
                  </Button>
                </div>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="oas-spec">OpenAPI 規格內容 (JSON / YAML) 或遠端 URL</label>
                <textarea
                  id="oas-spec"
                  className={`${styles.formTextarea} ${styles.textareaLg}`}
                  placeholder="貼上 OpenAPI / Swagger 規範 YAML/JSON，或輸入 https://.../openapi.json 網址"
                  value={specInput}
                  onChange={(e) => setSpecInput(e.target.value)}
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="oas-base-url">預設 Base URL（選填，覆蓋規格中的伺服器位址）</label>
                <input
                  id="oas-base-url"
                  type="url"
                  className={styles.formInput}
                  placeholder="例如 https://api.example.com"
                  value={defaultBaseUrl}
                  onChange={(e) => setDefaultBaseUrl(e.target.value)}
                  autoComplete="off"
                />
              </div>
            </>
          ) : (
            <>
              <div className={styles.parseSummary}>
                <div>
                  <span className={styles.versionTag}>{parseResult.version}</span>
                  <strong className={styles.parseTitle}>{parseResult.title}</strong>
                </div>
                <Button variant="secondary" onClick={() => setParseResult(null)}>
                  重新解析
                </Button>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="oas-token">全域 Bearer Token（選填，將自動注入 Authorization Header）</label>
                <input
                  id="oas-token"
                  type="password"
                  className={styles.formInput}
                  placeholder="若 API 需要認證請填寫 Bearer Token 或 API Key"
                  value={globalAuthToken}
                  onChange={(e) => setGlobalAuthToken(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className={styles.formGroup} role="group" aria-labelledby="oas-endpoints-label">
                <div className={styles.resultHeader}>
                  <span className={styles.formLabel} id="oas-endpoints-label">
                    選擇要匯入的 API 端點 ({Object.values(selectedEndpoints).filter(Boolean).length} / {parseResult.endpoints.length})
                  </span>
                  <button
                    type="button"
                    className={styles.linkButton}
                    onClick={() => {
                      const allChecked = Object.values(selectedEndpoints).every(Boolean);
                      const updated = {};
                      parseResult.endpoints.forEach((ep) => {
                        updated[ep.name] = !allChecked;
                      });
                      setSelectedEndpoints(updated);
                    }}
                  >
                    全選 / 全不選
                  </button>
                </div>
                <div className={styles.endpointList}>
                  {parseResult.endpoints.map((ep) => {
                    const isChecked = Boolean(selectedEndpoints[ep.name]);
                    return (
                      <label
                        key={ep.name}
                        className={`${styles.endpointItem} ${isChecked ? styles.endpointSelected : ''}`}
                      >
                        <span className={styles.endpointInfo}>
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => setSelectedEndpoints((prev) => ({ ...prev, [ep.name]: !prev[ep.name] }))}
                          />
                          <span className={`${styles.methodBadge} ${getMethodClass(ep.method)}`}>
                            {ep.method}
                          </span>
                          <span className={styles.endpointText}>
                            <span className={styles.endpointPath}>{ep.path}</span>
                            <span className={styles.endpointSummary}>{ep.display_name}</span>
                          </span>
                        </span>
                        <span className={styles.versionTag}>
                          {Object.keys(ep.parameters_schema?.properties || {}).length} 參數
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button variant="secondary" onClick={() => setImportModalOpen(false)} disabled={parsing || importing}>
            取消
          </Button>
          {!parseResult ? (
            <Button
              variant="primary"
              onClick={handleParseSpec}
              loading={parsing}
              startIcon={<Icon name="search" size={16} />}
            >
              {parsing ? '正在解析規格...' : '解析規格'}
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={handleExecuteImport}
              loading={importing}
              startIcon={<Icon name="check" size={16} />}
            >
              {importing ? '正在匯入中...' : `確認匯入 (${Object.values(selectedEndpoints).filter(Boolean).length})`}
            </Button>
          )}
        </DialogActions>
      </Dialog>
      {/* 6. 手動新增 / 編輯自訂 API */}
      <Dialog open={toolModalOpen} onClose={savingTool ? undefined : () => setToolModalOpen(false)} maxWidth="lg">
        <DialogForm onSubmit={handleSaveTool}>
          <DialogTitle onClose={() => setToolModalOpen(false)} closeDisabled={savingTool}>
            {editingTool ? '編輯自訂 API 工具' : '手動建立自訂 API 工具'}
          </DialogTitle>
          <DialogContent className={styles.dialogBody}>
            {dialogError && <Alert severity="error">{dialogError}</Alert>}
            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="tool-name">工具識別碼（英文小寫與底線，供 LLM 調用）*</label>
                <input
                  id="tool-name"
                  type="text"
                  className={styles.formInput}
                  placeholder="例如 get_user_profile"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  autoComplete="off"
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="tool-display-name">顯示名稱*</label>
                <input
                  id="tool-display-name"
                  type="text"
                  className={styles.formInput}
                  placeholder="例如 查詢使用者個人檔案"
                  value={formData.display_name}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  required
                  autoComplete="off"
                />
              </div>
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="tool-description">工具用途描述（詳細說明工具功能與調用時機，供 AI 判斷何時使用）*</label>
              <textarea
                id="tool-description"
                className={`${styles.formInput} ${styles.textareaSm}`}
                placeholder="例如：當使用者需要查詢特定 ID 的使用者基本資料時調用。"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                required
              />
            </div>
            <div className={`${styles.formRow} ${styles.formRowNarrowFirst}`}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="tool-method">HTTP 方法</label>
                <select
                  id="tool-method"
                  className={styles.formSelect}
                  value={formData.method}
                  onChange={(e) => setFormData({ ...formData, method: e.target.value })}
                >
                  <option value="GET">GET</option>
                  <option value="POST">POST</option>
                  <option value="PUT">PUT</option>
                  <option value="DELETE">DELETE</option>
                  <option value="PATCH">PATCH</option>
                </select>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="tool-url">請求完整 URL（支援 &#123;param&#125; 路徑變數）*</label>
                <input
                  id="tool-url"
                  type="text"
                  className={styles.formInput}
                  placeholder="例如 https://api.example.com/users/{userId}"
                  value={formData.url}
                  onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                  required
                  autoComplete="off"
                />
              </div>
            </div>
            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="tool-auth-type">認證方式</label>
                <select
                  id="tool-auth-type"
                  className={styles.formSelect}
                  value={formData.auth_type}
                  onChange={(e) => setFormData({ ...formData, auth_type: e.target.value })}
                >
                  <option value="none">無認證 (None)</option>
                  <option value="bearer">Bearer Token</option>
                  <option value="api_key">API Key (Header)</option>
                </select>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="tool-auth-token">認證金鑰 / Token</label>
                <input
                  id="tool-auth-token"
                  type="password"
                  className={styles.formInput}
                  placeholder="例如 token_abc123"
                  value={formData.auth_token}
                  onChange={(e) => setFormData({ ...formData, auth_token: e.target.value })}
                  autoComplete="off"
                />
              </div>
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="tool-parameters">參數 JSON Schema 定義 (Parameters Schema)</label>
              <textarea
                id="tool-parameters"
                className={`${styles.formTextarea} ${styles.textareaLg}`}
                value={formData.parameters_json}
                onChange={(e) => setFormData({ ...formData, parameters_json: e.target.value })}
              />
            </div>
          </DialogContent>
          <DialogActions>
            <Button variant="secondary" onClick={() => setToolModalOpen(false)} disabled={savingTool}>
              取消
            </Button>
            <Button variant="primary" type="submit" loading={savingTool} startIcon={<Icon name="save" size={16} />}>
              {editingTool ? '儲存變更' : '建立工具'}
            </Button>
          </DialogActions>
        </DialogForm>
      </Dialog>
      {/* 7. 自訂 API 線上即時測試 */}
      <Dialog open={testModalOpen && Boolean(testingTool)} onClose={() => setTestModalOpen(false)} maxWidth="lg">
        {testingTool && (
          <>
            <DialogTitle onClose={() => setTestModalOpen(false)}>
              即時線上測試：{testingTool.display_name} ({testingTool.name})
            </DialogTitle>
            <DialogContent className={styles.dialogBody}>
              <div className={styles.specBlock}>
                <div className={styles.specLabel}>
                  <span className={`${styles.methodBadge} ${getMethodClass(testingTool.method)}`}>
                    {testingTool.method}
                  </span>
                  <span className={styles.monoText}>{testingTool.url}</span>
                </div>
              </div>
              <fieldset className={styles.formFieldset}>
                <legend className={styles.formLabel}>測試輸入參數 (Arguments)</legend>
                {Object.keys(testingTool.parameters_schema?.properties || {}).length === 0 ? (
                  <p className={styles.mutedNote}>此 API 無須輸入額外參數</p>
                ) : (
                  Object.entries(testingTool.parameters_schema?.properties || {}).map(([pName, pObj]) => {
                    const inputId = `tool-arg-${pName}`;
                    const isRequired = testingTool.parameters_schema?.required?.includes(pName);
                    return (
                      <div key={pName} className={styles.argField}>
                        <label className={styles.argLabel} htmlFor={inputId}>
                          {pName}{isRequired && <span className={styles.paramRequired} aria-hidden="true">*</span>}
                          <span className={styles.argHint}>({pObj.description || pObj.type})</span>
                        </label>
                        <input
                          id={inputId}
                          type="text"
                          className={styles.formInput}
                          value={testArgs[pName] || ''}
                          onChange={(e) => setTestArgs({ ...testArgs, [pName]: e.target.value })}
                          required={isRequired}
                          autoComplete="off"
                        />
                      </div>
                    );
                  })
                )}
              </fieldset>
              {testResult && (
                <div className={styles.formGroup} aria-live="polite">
                  <div className={styles.resultHeader}>
                    <span className={styles.formLabel}>API 回應結果 (Response)</span>
                    <span className={testResult.is_success ? styles.resultSuccess : styles.resultError}>
                      {testResult.is_success ? '成功' : '失敗'}｜狀態碼 {testResult.status_code}
                      {testResult.duration_seconds !== undefined && `｜耗時 ${testResult.duration_seconds}s`}
                    </span>
                  </div>
                  <pre className={styles.jsonViewer}>
                    {typeof testResult.data === 'object'
                      ? JSON.stringify(testResult.data, null, 2)
                      : String(testResult.data || testResult.error || '')}
                  </pre>
                </div>
              )}
            </DialogContent>
            <DialogActions>
              <Button variant="secondary" onClick={() => setTestModalOpen(false)}>
                關閉
              </Button>
              <Button
                variant="primary"
                onClick={handleRunTest}
                loading={testing}
                startIcon={<Icon name="send" size={16} />}
              >
                {testing ? '正在發送請求...' : '發送測試請求'}
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={pendingDelete?.type === 'tool' ? '刪除這個自訂 API 工具？' : '刪除這台 MCP 伺服器？'}
        description={`「${pendingDelete?.item.display_name}」刪除後，AI 就無法再使用它提供的工具，此操作無法復原。`}
        confirmLabel="刪除"
        destructive
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
      {/* 通知提示 */}
      <Snackbar
        key={snackbar.key}
        open={snackbar.open}
        autoHideDuration={snackbar.severity === 'error' ? 6000 : 3000}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
      >
        <Alert
          severity={snackbar.severity}
          onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </div>
  );
}
