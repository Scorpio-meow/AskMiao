import { useState } from 'react';
import { llmConnectionService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Icon } from '../ui';
import styles from './LlmConnections.module.css';
export default function ConnectionTestDialog({ connection, onClose }) {
  const [model, setModel] = useState(connection.models[0]);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);
  const handleTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      setResult(await llmConnectionService.test(connection.id, model));
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setResult({ ok: false, error: typeof detail === 'string' ? detail : '測試請求失敗，請稍後再試' });
    } finally {
      setTesting(false);
    }
  };
  return (
    <Dialog open onClose={testing ? undefined : onClose} maxWidth="sm">
      <DialogTitle onClose={onClose} closeDisabled={testing}>測試「{connection.name}」</DialogTitle>
      <DialogContent>
        <div className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="llm-connection-test-model">模型</label>
            <select
              id="llm-connection-test-model"
              className={styles.select}
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={testing}
            >
              {connection.models.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
            <span className={styles.hint}>送出一則很短的測試訊息，會用到少量 token</span>
          </div>
          <div role="status" aria-live="polite">
            {result?.ok && (
              <Alert severity="success">
                連線成功，模型回覆：<span className={styles.reply}>{result.reply || '（空白）'}</span>
              </Alert>
            )}
            {result && !result.ok && <Alert severity="error">{result.error}</Alert>}
          </div>
        </div>
      </DialogContent>
      <DialogActions>
        <Button variant="secondary" onClick={onClose} disabled={testing}>關閉</Button>
        <Button variant="primary" onClick={handleTest} loading={testing} startIcon={<Icon name="send" size={16} />}>測試</Button>
      </DialogActions>
    </Dialog>
  );
}
