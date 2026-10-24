import { useState } from 'react';
import { apiToolService } from '../../services/api';
import { describeRequestError } from '../../utils/secureLogger';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Icon } from '../../components/ui';
import { getMethodClass, getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
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
/** 解析 OpenAPI / Swagger 規格並勾選要批次建立的自訂 API 工具；輸入框開啟時保持空白，需要範例時再按按鈕載入 */
export default function OpenApiImportDialog({ onClose, onImported }) {
  const [specInput, setSpecInput] = useState('');
  const [defaultBaseUrl, setDefaultBaseUrl] = useState('');
  const [parsing, setParsing] = useState(false);
  const [parseResult, setParseResult] = useState(null);
  const [selectedEndpoints, setSelectedEndpoints] = useState({});
  const [globalAuthToken, setGlobalAuthToken] = useState('');
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const handleParseSpec = async () => {
    if (!specInput.trim()) {
      setError('請輸入 OpenAPI 規格內容或網址');
      return;
    }
    try {
      setParsing(true);
      setError('');
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
      setError(getRequestErrorMessage(err, '解析 OpenAPI 規格失敗，請檢查格式'));
    } finally {
      setParsing(false);
    }
  };
  const handleExecuteImport = async () => {
    if (!parseResult) return;
    const toImport = parseResult.endpoints.filter((ep) => selectedEndpoints[ep.name]);
    if (toImport.length === 0) {
      setError('請至少勾選一個要匯入的 API 端點');
      return;
    }
    try {
      setImporting(true);
      setError('');
      const authConfig = globalAuthToken ? { token: globalAuthToken } : {};
      const authType = globalAuthToken ? 'bearer' : 'none';
      const res = await apiToolService.importTools({
        tools: toImport,
        global_base_url: parseResult.base_url || defaultBaseUrl,
        global_auth_type: authType,
        global_auth_config: authConfig
      });
      onImported(res.message);
    } catch (err) {
      console.warn('匯入工具失敗:', describeRequestError(err));
      setError(getRequestErrorMessage(err, '匯入工具失敗'));
    } finally {
      setImporting(false);
    }
  };
  return (
    <Dialog open onClose={parsing || importing ? undefined : onClose} maxWidth="lg">
      <DialogTitle onClose={onClose} closeDisabled={parsing || importing}>
        匯入 OpenAPI / Swagger 規格
      </DialogTitle>
      <DialogContent className={styles.dialogBody}>
        {error && <Alert severity="error">{error}</Alert>}
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
        <Button variant="secondary" onClick={onClose} disabled={parsing || importing}>
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
  );
}
