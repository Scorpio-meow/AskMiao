import { useState } from 'react';
import { apiToolService } from '../../services/api';
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Icon } from '../../components/ui';
import { MethodBadge } from './CatalogParts';
import { emptyTestArgs } from './forms';
import { getRequestErrorMessage } from './shared';
import { TestArgsFields, TestResult } from './ToolTestParts';
import styles from './AiTools.module.css';
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
      <DialogTitle onClose={onClose} subtitle={tool.name}>
        即時線上測試：{tool.display_name}
      </DialogTitle>
      <DialogContent className={styles.dialogBody}>
        <div className={styles.requestLine}>
          <MethodBadge method={tool.method}>{tool.method}</MethodBadge>
          <span className={styles.requestTarget}>{tool.url}</span>
        </div>
        <TestArgsFields
          idPrefix="tool-arg"
          schema={tool.parameters_schema}
          args={args}
          onChange={setArgs}
          emptyText="此 API 無須輸入額外參數"
        />
        <div aria-live="polite">
          {result && (
            <TestResult
              title="API 回應結果"
              success={result.is_success}
              facts={[
                `狀態碼 ${result.status_code}`,
                ...(result.duration_seconds !== undefined ? [`耗時 ${result.duration_seconds}s`] : []),
              ]}
              body={typeof result.data === 'object'
                ? JSON.stringify(result.data, null, 2)
                : String(result.data || result.error || '')}
            />
          )}
        </div>
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
