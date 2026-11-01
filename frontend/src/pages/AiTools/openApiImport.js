const VERSION_LABELS = {
  'swagger_2.0': 'Swagger 2.0',
  'openapi_3.0': 'OpenAPI 3.0',
  'openapi_3.1': 'OpenAPI 3.1',
  'openapi_3.2': 'OpenAPI 3.2',
  'arazzo_1.0': 'Arazzo 1.0',
  'arazzo_1.1': 'Arazzo 1.1',
};
export const AUTH_TYPE_LABELS = {
  bearer: 'Bearer',
  api_key: 'API Key',
  basic: 'Basic',
  oauth2_client_credentials: 'OAuth2',
};
export const describeVersion = (result) => {
  const label = VERSION_LABELS[result.version] || result.version;
  return result.spec_version ? `${label}（${result.spec_version}）` : label;
};
export const parseSpecArgs = (specInput, defaultBaseUrl, overlayInput) => [
  specInput,
  defaultBaseUrl || undefined,
  overlayInput.trim() ? [overlayInput.trim()] : [],
];
export const selectAllEndpoints = (endpoints, checked) =>
  Object.fromEntries(endpoints.map((ep) => [ep.name, checked]));
export const countSelected = (selected) => Object.values(selected).filter(Boolean).length;
export const allEndpointsSelected = (selected) => Object.values(selected).every(Boolean);
export const toggleAllEndpoints = (selected, endpoints) =>
  selectAllEndpoints(endpoints, !allEndpointsSelected(selected));
export const selectedEndpoints = (endpoints, selected) => endpoints.filter((ep) => selected[ep.name]);
export const importPayload = ({ tools, parseResult, defaultBaseUrl, globalAuthToken }) => ({
  tools,
  global_base_url: parseResult.base_url || defaultBaseUrl,
  global_auth_type: globalAuthToken ? 'bearer' : 'none',
  global_auth_config: globalAuthToken ? { token: globalAuthToken } : {},
});
export const isWorkflow = (endpoint) => endpoint.kind === 'workflow';
export const endpointBadge = (endpoint) => (isWorkflow(endpoint) ? '工作流程' : endpoint.method);
export const endpointTarget = (endpoint) => (isWorkflow(endpoint)
  ? [`${endpoint.steps_count} 個步驟`, (endpoint.step_targets || []).join('、')].filter(Boolean).join('：')
  : endpoint.path);
export const endpointParameterCount = (endpoint) => Object.keys(endpoint.parameters_schema?.properties || {}).length;
export const SAMPLE_OAS_SPECS = [
  {
    key: 'oas2',
    label: 'Swagger 2.0（即時天氣）',
    content: `swagger: '2.0'
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
  },
  {
    key: 'oas30',
    label: 'OpenAPI 3.0（匯率轉換）',
    content: `openapi: 3.0.3
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
  },
  {
    key: 'oas31',
    label: 'OpenAPI 3.1（工單派遣）',
    content: `openapi: 3.1.0
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
              required: [ticket_id, title]`,
  },
];
