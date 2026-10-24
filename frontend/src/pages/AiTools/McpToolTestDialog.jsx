import { useState } from 'react';
import { mcpService } from '../../services/api';
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Icon } from '../../components/ui';
import { emptyTestArgs } from './forms';
import { getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
/** 以 tools/call 實際呼叫 MCP 伺服器的一個工具 */
export default function McpToolTestDialog({ server, tool, onClose }) {
  const [args, setArgs] = useState(() => emptyTestArgs(tool.inputSchema));
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);
  const handleRun = async () => {
    try {
      setTesting(true);
      const res = await mcpService.testTool(server.id, tool.name, args);
      setResult(res.result);
    } catch (err) {
      setResult({
        is_success: false,
        error: getRequestErrorMessage(err, 'MCP 工具調用失敗')
      });
    } finally {
      setTesting(false);
    }
  };
  return (
    <Dialog open onClose={onClose} maxWidth="lg">
      <DialogTitle onClose={onClose}>
        即時測試 MCP 工具：{tool.name}
      </DialogTitle>
      <DialogContent className={styles.dialogBody}>
        <div className={styles.specBlock}>
          <div className={styles.specLabel}>
            <span className={`${styles.methodBadge} ${styles.methodPost}`}>{server.display_name}</span>
            <span>{tool.description || '無詳細說明'}</span>
          </div>
        </div>
        <fieldset className={styles.formFieldset}>
          <legend className={styles.formLabel}>輸入參數 (Arguments)</legend>
          {Object.keys(tool.inputSchema?.properties || {}).length === 0 ? (
            <p className={styles.mutedNote}>此 MCP 工具無須輸入額外參數</p>
          ) : (
            Object.entries(tool.inputSchema?.properties || {}).map(([pName, pObj]) => {
              const inputId = `mcp-arg-${pName}`;
              const isRequired = tool.inputSchema?.required?.includes(pName);
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
              <span className={styles.formLabel}>MCP 回傳結果 (tools/call)</span>
              <span className={result.is_success ? styles.resultSuccess : styles.resultError}>
                {result.is_success ? '成功' : '失敗'}
                {result.duration_seconds !== undefined && `｜耗時 ${result.duration_seconds}s`}
              </span>
            </div>
            <pre className={styles.jsonViewer}>
              {JSON.stringify(result.content || result, null, 2)}
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
          {testing ? '正在調用 MCP...' : '發送 MCP 測試請求'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
