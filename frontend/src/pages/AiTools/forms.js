// 自訂 API 工具與 MCP 伺服器表單：表單欄位與 API 資料之間的轉換
// 與後端 tool_approval.SAFE_HTTP_METHODS 一致：其他方法可能改變外部狀態，預設需要確認
const SAFE_HTTP_METHODS = ['GET', 'HEAD', 'OPTIONS'];
export const defaultRequiresApproval = (method) => !SAFE_HTTP_METHODS.includes((method || 'GET').toUpperCase());
export const AUTH_FIELDS = {
  none: [],
  bearer: ['token'],
  api_key: ['key_name', 'key_in', 'key_value'],
  basic: ['username', 'password'],
  oauth2_client_credentials: ['token_url', 'client_id', 'client_secret', 'scope', 'client_auth'],
};
const EMPTY_AUTH = {
  token: '',
  key_name: '',
  key_in: 'header',
  key_value: '',
  username: '',
  password: '',
  token_url: '',
  client_id: '',
  client_secret: '',
  scope: '',
  client_auth: 'basic',
};
export const BODY_CONTENT_TYPES = ['application/json', 'application/x-www-form-urlencoded', 'multipart/form-data'];
export const EMPTY_TOOL_FORM = {
  name: '',
  display_name: '',
  description: '',
  method: 'GET',
  url: '',
  auth_type: 'none',
  auth: EMPTY_AUTH,
  body_content_type: 'application/json',
  requires_approval: false,
  timeout: 15,
  parameters_json: '{\n  "type": "object",\n  "properties": {\n    "query": {\n      "type": "string",\n      "description": "參數說明"\n    }\n  },\n  "required": ["query"]\n}'
};
export const EMPTY_MCP_FORM = {
  name: '',
  display_name: '',
  description: '',
  transport_type: 'stdio',
  command: '',
  args_json: '[]',
  env_vars_json: '{}',
  url: '',
  headers_json: '{}',
  oauth_client_id: '',
  oauth_client_secret: '',
  oauth_scope: '',
  // MCP 工具的行為無法事先得知，預設每次呼叫都要使用者在對話中確認
  requires_approval: true,
  timeout: 30
};
// 解析 JSON 欄位；失敗時指出是哪個欄位，讓錯誤訊息能對應到表單上的位置
export const parseJsonField = (value, fieldLabel) => {
  if (!value) return undefined;
  try {
    return JSON.parse(value);
  } catch (e) {
    throw new Error(`「${fieldLabel}」不是有效的 JSON：${e.message}`, { cause: e });
  }
};
export const toolToForm = (tool) => (tool ? {
  name: tool.name,
  display_name: tool.display_name,
  description: tool.description,
  method: tool.method,
  url: tool.url,
  auth_type: tool.auth_type || 'none',
  auth: { ...EMPTY_AUTH, ...(tool.auth_config || {}) },
  body_content_type: tool.body_content_type || 'application/json',
  requires_approval: Boolean(tool.requires_approval),
  timeout: tool.timeout || 15,
  parameters_json: JSON.stringify(tool.parameters_schema || { type: 'object', properties: {} }, null, 2)
} : EMPTY_TOOL_FORM);
// 憑證欄位保持後端回傳的遮蔽字樣時，後端沿用原值
export const toolFormToPayload = (form) => ({
  name: form.name,
  display_name: form.display_name,
  description: form.description,
  method: form.method,
  url: form.url,
  auth_type: form.auth_type,
  auth_config: Object.fromEntries((AUTH_FIELDS[form.auth_type] || []).map((key) => [key, form.auth[key]])),
  body_content_type: form.body_content_type,
  requires_approval: form.requires_approval,
  timeout: Number(form.timeout) || 15,
  parameters_schema: parseJsonField(form.parameters_json, '參數 JSON Schema 定義') || {}
});
// 編輯既有伺服器與套用範本共用
export const mcpServerToForm = (server) => (server ? {
  name: server.name,
  display_name: server.display_name,
  description: server.description || '',
  transport_type: server.transport_type || 'stdio',
  command: server.command || '',
  args_json: JSON.stringify(server.args || [], null, 2),
  env_vars_json: JSON.stringify(server.env_vars || {}, null, 2),
  url: server.url || '',
  headers_json: JSON.stringify(server.headers || {}, null, 2),
  oauth_client_id: server.oauth_client?.client_id || '',
  oauth_client_secret: server.oauth_client?.client_secret || '',
  oauth_scope: server.oauth_client?.scope || '',
  requires_approval: Boolean(server.requires_approval),
  timeout: server.timeout || 30
} : EMPTY_MCP_FORM);
export const mcpFormToPayload = (form) => ({
  name: form.name,
  display_name: form.display_name,
  description: form.description,
  transport_type: form.transport_type,
  command: form.command,
  args: parseJsonField(form.args_json, '指令參數清單') || [],
  env_vars: parseJsonField(form.env_vars_json, '環境變數配置') || {},
  url: form.url,
  headers: parseJsonField(form.headers_json, '自訂 HTTP Headers') || {},
  ...(form.transport_type === 'stdio' ? {} : {
    oauth_client: {
      client_id: form.oauth_client_id,
      client_secret: form.oauth_client_secret,
      scope: form.oauth_scope,
    },
  }),
  requires_approval: form.requires_approval,
  timeout: Number(form.timeout) || 30
});
// 測試對話框的參數欄位：schema 宣告的每個參數一個空白欄位
export const emptyTestArgs = (schema) =>
  Object.fromEntries(Object.keys(schema?.properties || {}).map((name) => [name, '']));
