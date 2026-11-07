import { useId, useState } from 'react';
import { apiToolService } from '../../services/api';
import { describeRequestError } from '../../utils/secureLogger';
import { Alert, Button, Collapse, Dialog, DialogActions, DialogContent, DialogTitle, Icon } from '../../components/ui';
import { MethodBadge, Tag } from './CatalogParts';
import { Field } from './FormParts';
import {
  AUTH_TYPE_LABELS,
  SAMPLE_OAS_SPECS,
  allEndpointsSelected,
  countSelected,
  describeVersion,
  endpointBadge,
  endpointParameterCount,
  endpointTarget,
  importPayload,
  parseSpecArgs,
  selectAllEndpoints,
  selectedEndpoints as pickSelected,
  toggleAllEndpoints,
} from './openApiImport';
import { getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
const STEPS = ['提供規格', '選擇端點並匯入'];
function ImportSteps({ current }) {
  return (
    <ol className={styles.steps} aria-label="匯入步驟">
      {STEPS.map((label, index) => {
        const state = index < current ? 'done' : index === current ? 'current' : 'upcoming';
        return (
          <li
            key={label}
            className={`${styles.step} ${state === 'current' ? styles.stepCurrent : ''} ${state === 'done' ? styles.stepDone : ''}`}
            aria-current={state === 'current' ? 'step' : undefined}
          >
            <span className={styles.stepMarker} aria-hidden="true">
              {state === 'done' ? <Icon name="check" size={14} /> : index + 1}
            </span>
            <span>{label}</span>
            {state === 'done' && <span className="sr-only">（已完成）</span>}
          </li>
        );
      })}
    </ol>
  );
}
export default function OpenApiImportDialog({ onClose, onImported }) {
  const overlayRegionId = useId();
  const [specInput, setSpecInput] = useState('');
  const [defaultBaseUrl, setDefaultBaseUrl] = useState('');
  const [overlayInput, setOverlayInput] = useState('');
  const [overlayOpen, setOverlayOpen] = useState(false);
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
      const res = await apiToolService.parseOpenApiSpec(...parseSpecArgs(specInput, defaultBaseUrl, overlayInput));
      if (res?.data) {
        setParseResult(res.data);
        setSelectedEndpoints(selectAllEndpoints(res.data.endpoints, true));
      }
    } catch (err) {
      setError(getRequestErrorMessage(err, '解析 OpenAPI 規格失敗，請檢查格式'));
    } finally {
      setParsing(false);
    }
  };
  const handleExecuteImport = async () => {
    if (!parseResult) return;
    const toImport = pickSelected(parseResult.endpoints, selectedEndpoints);
    if (toImport.length === 0) {
      setError('請至少勾選一個要匯入的 API 端點');
      return;
    }
    try {
      setImporting(true);
      setError('');
      const res = await apiToolService.importTools(importPayload({ tools: toImport, parseResult, defaultBaseUrl, globalAuthToken }));
      onImported(res.message);
    } catch (err) {
      console.warn('匯入工具失敗:', describeRequestError(err));
      setError(getRequestErrorMessage(err, '匯入工具失敗'));
    } finally {
      setImporting(false);
    }
  };
  const selectedCount = countSelected(selectedEndpoints);
  const endpointTotal = parseResult?.endpoints.length;
  const allSelected = endpointTotal > 0 && allEndpointsSelected(selectedEndpoints);
  const someSelected = selectedCount > 0 && !allSelected;
  return (
    <Dialog open onClose={parsing || importing ? undefined : onClose} maxWidth="lg">
      <DialogTitle
        onClose={onClose}
        closeDisabled={parsing || importing}
        subtitle="Swagger 2.0、OpenAPI 3.0～3.2 與 Arazzo 1.0～1.1，可先套用 Overlay 1.0～1.2"
      >
        匯入 API 規格
      </DialogTitle>
      <DialogContent className={styles.dialogBody}>
        <ImportSteps current={parseResult ? 1 : 0} />
        {error && <Alert severity="error">{error}</Alert>}
        {!parseResult ? (
          <>
            <Field
              id="oas-spec"
              label="規格內容（JSON / YAML）或遠端 URL"
              hint="貼上 Swagger 2.0、OpenAPI 3.0～3.2 或 Arazzo 工作流程文件，也可以輸入 https://.../openapi.json 網址。外部 $ref 只在以網址匯入時才會載入。"
            >
              <textarea
                id="oas-spec"
                className={`${styles.input} ${styles.codeInput} ${styles.textareaLg}`}
                placeholder={'openapi: 3.1.0\ninfo:\n  title: …\n\n或 https://api.example.com/openapi.json'}
                value={specInput}
                onChange={(e) => setSpecInput(e.target.value)}
                spellCheck={false}
                aria-describedby="oas-spec-hint"
              />
            </Field>
            <div className={styles.presetGroup} role="group" aria-labelledby="oas-samples-label">
              <span className={styles.presetLabel} id="oas-samples-label">載入測試範例（會取代上方內容）</span>
              <div className={styles.inlineButtons}>
                {SAMPLE_OAS_SPECS.map((sample) => (
                  <Button key={sample.key} variant="secondary" size="sm" onClick={() => setSpecInput(sample.content)}>
                    {sample.label}
                  </Button>
                ))}
              </div>
            </div>
            <Field id="oas-base-url" label="預設 Base URL（選填）" hint="覆蓋規格中的伺服器位址">
              <input
                id="oas-base-url"
                type="url"
                className={`${styles.input} ${styles.mono}`}
                placeholder="例如 https://api.example.com"
                value={defaultBaseUrl}
                onChange={(e) => setDefaultBaseUrl(e.target.value)}
                autoComplete="off"
                aria-describedby="oas-base-url-hint"
              />
            </Field>
            <div className={styles.disclosure}>
              <button
                type="button"
                className={styles.disclosureButton}
                onClick={() => setOverlayOpen((open) => !open)}
                aria-expanded={overlayOpen}
                aria-controls={overlayRegionId}
              >
                <Icon name={overlayOpen ? 'expand-less' : 'expand-more'} size={16} />
                <span>套用 Overlay（選填）</span>
                {!overlayOpen && overlayInput.trim() && <Tag tone="primary">已填寫</Tag>}
              </button>
              <Collapse in={overlayOpen} id={overlayRegionId}>
                <div className={styles.disclosureBody}>
                  <Field id="oas-overlay" label="Overlay 文件或網址" hint="匯入前先套用到上方規格，例如移除內部端點、補充說明。支援 Overlay 1.0～1.2。">
                    <textarea
                      id="oas-overlay"
                      className={`${styles.input} ${styles.codeInput} ${styles.textareaMd}`}
                      value={overlayInput}
                      onChange={(e) => setOverlayInput(e.target.value)}
                      spellCheck={false}
                      aria-describedby="oas-overlay-hint"
                    />
                  </Field>
                </div>
              </Collapse>
            </div>
          </>
        ) : (
          <>
            <div className={styles.parseSummary}>
              <div className={styles.parseSummaryText}>
                <div className={styles.parseSummaryTitleLine}>
                  <Tag tone="primary">{describeVersion(parseResult)}</Tag>
                  <strong className={styles.parseTitle}>{parseResult.title}</strong>
                </div>
                <span className={styles.parseMeta}>
                  {endpointTotal} 個可匯入項目
                  {parseResult.base_url && <> · <span className={styles.mono}>{parseResult.base_url}</span></>}
                </span>
              </div>
              <Button variant="secondary" size="sm" onClick={() => setParseResult(null)} startIcon={<Icon name="arrow-back" size={16} />}>
                返回修改規格
              </Button>
            </div>
            {parseResult.warnings?.length > 0 && (
              <Alert severity="warning">
                <ul className={styles.warningList}>
                  {parseResult.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                </ul>
              </Alert>
            )}
            <div className={styles.endpointPicker} role="group" aria-labelledby="oas-endpoints-label">
              <div className={styles.endpointPickerHeader}>
                <label className={styles.selectAll}>
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={(el) => {
                      if (el) el.indeterminate = someSelected;
                    }}
                    onChange={() => setSelectedEndpoints(toggleAllEndpoints(selectedEndpoints, parseResult.endpoints))}
                  />
                  <span>全選</span>
                </label>
                <span className={styles.endpointPickerTitle} id="oas-endpoints-label">
                  選擇要匯入的 API 端點（已選 {selectedCount} / {endpointTotal}）
                </span>
              </div>
              <ul className={styles.endpointList} role="list">
                {parseResult.endpoints.map((ep) => {
                  const isChecked = Boolean(selectedEndpoints[ep.name]);
                  return (
                    <li key={ep.name}>
                      <label className={`${styles.endpointItem} ${isChecked ? styles.endpointSelected : ''}`}>
                        <input
                          type="checkbox"
                          className={styles.endpointCheck}
                          checked={isChecked}
                          onChange={() => setSelectedEndpoints((prev) => ({ ...prev, [ep.name]: !prev[ep.name] }))}
                        />
                        <span className={styles.endpointBody}>
                          <span className={styles.endpointTitleLine}>
                            <MethodBadge method={ep.method}>{endpointBadge(ep)}</MethodBadge>
                            <span className={styles.endpointPath}>{endpointTarget(ep)}</span>
                          </span>
                          <span className={styles.endpointSummary}>{ep.display_name}</span>
                          {ep.warnings?.length > 0 && (
                            <span className={styles.endpointWarnings}>{ep.warnings.join('；')}</span>
                          )}
                        </span>
                        <span className={styles.endpointTags}>
                          {ep.auth_type && ep.auth_type !== 'none' && (
                            <Tag>{AUTH_TYPE_LABELS[ep.auth_type] || ep.auth_type}</Tag>
                          )}
                          <Tag>{endpointParameterCount(ep)} 參數</Tag>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </div>
            <Field
              id="oas-token"
              label="全域 Bearer Token（選填）"
              hint="套用到規格宣告為 Bearer 或沒有宣告驗證的端點。規格中宣告的 API Key、Basic 與 OAuth2 client credentials 會自動帶入工具設定，匯入後請編輯工具填入金鑰。"
            >
              <input
                id="oas-token"
                type="password"
                className={styles.input}
                placeholder="若 API 需要認證請填寫 Bearer Token 或 API Key"
                value={globalAuthToken}
                onChange={(e) => setGlobalAuthToken(e.target.value)}
                autoComplete="off"
                aria-describedby="oas-token-hint"
              />
            </Field>
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
            {importing ? '正在匯入中...' : `確認匯入 (${selectedCount})`}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}