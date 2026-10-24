import { useState } from 'react';
import { apiToolService } from '../../services/api';
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Icon } from '../../components/ui';
import { emptyTestArgs } from './forms';
import { getMethodClass, getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
/** 以輸入的參數實際送出一次自訂 API 工具的請求 */
export default function ApiToolTestDialog({ tool, onClose }) {
  const [args, setArgs] = useState(() => emptyTestArgs(tool.parameters_schema));
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);
  const handleRun = async () => {
    try {
      setTesting(true);
      const res = await apiToolService.testTool(tool.id, args);
      setResult(res.result);
    } catch (err) {
      setResult({
        status_code: 500,
        is_success: false,
        error: getRequestErrorMessage(err, '測試請求發送失敗')
      });
    } finally {
      setTesting(false);
    }
  };
  return (
    <Dialog open onClose={onClose} maxWidth="lg">
      <DialogTitle onClose={onClose}>
        即時線上測試：{tool.display_name} ({tool.name})
      </DialogTitle>
      <DialogContent className={styles.dialogBody}>
        <div className={styles.specBlock}>
          <div className={styles.specLabel}>
            <span className={`${styles.methodBadge} ${getMethodClass(tool.method)}`}>
              {tool.method}
            </span>
            <span className={styles.monoText}>{tool.url}</span>
          </div>
        </div>
        <fieldset className={styles.formFieldset}>
          <legend className={styles.formLabel}>測試輸入參數 (Arguments)</legend>
          {Object.keys(tool.parameters_schema?.properties || {}).length === 0 ? (
            <p className={styles.mutedNote}>此 API 無須輸入額外參數</p>
          ) : (
            Object.entries(tool.parameters_schema?.properties || {}).map(([pName, pObj]) => {
              const inputId = `tool-arg-${pName}`;
              const isRequired = tool.parameters_schema?.required?.includes(pName);
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
                    value={args[pName] || ''}
                    onChange={(e) => setArgs({ ...args, [pName]: e.target.value })}
                    required={isRequired}
                    autoComplete="off"
                  />
                </div>
              );
            })
          )}
        </fieldset>
        {result && (
          <div className={styles.formGroup} aria-live="polite">
            <div className={styles.resultHeader}>
              <span className={styles.formLabel}>API 回應結果 (Response)</span>
              <span className={result.is_success ? styles.resultSuccess : styles.resultError}>
                {result.is_success ? '成功' : '失敗'}｜狀態碼 {result.status_code}
                {result.duration_seconds !== undefined && `｜耗時 ${result.duration_seconds}s`}
              </span>
            </div>
            <pre className={styles.jsonViewer}>
              {typeof result.data === 'object'
                ? JSON.stringify(result.data, null, 2)
                : String(result.data || result.error || '')}
            </pre>
          </div>
        )}
      </DialogContent>
      <DialogActions>
        <Button variant="secondary" onClick={onClose}>
          關閉
        </Button>
        <Button
          variant="primary"
          onClick={handleRun}
          loading={testing}
          startIcon={<Icon name="send" size={16} />}
        >
          {testing ? '正在發送請求...' : '發送測試請求'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
