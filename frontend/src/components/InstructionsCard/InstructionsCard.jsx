import { useCallback, useEffect, useId, useState } from 'react';
import { Alert, Button, Spinner, TextField } from '../ui';
import styles from './InstructionsCard.module.css';
export default function InstructionsCard({ className, titleClassName, title, hint, placeholder, load, save }) {
  const titleId = useId();
  const [saved, setSaved] = useState(null);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const reload = useCallback(async () => {
    try {
      setError('');
      const content = await load();
      setSaved(content);
      setDraft(content);
    } catch (err) {
      setError(`載入${title}失敗：${err.response?.data?.detail || err.message}`);
    }
  }, [load, title]);
  useEffect(() => {
    queueMicrotask(reload);
  }, [reload]);
  const handleSave = async () => {
    setSaving(true);
    setNotice('');
    setError('');
    try {
      const content = await save(draft);
      setSaved(content);
      setDraft(content);
      setNotice(content ? `已儲存${title}` : `已清除${title}`);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(`儲存${title}失敗：${Array.isArray(detail) ? '內容過長' : detail || err.message}`);
    } finally {
      setSaving(false);
    }
  };
  const changed = saved !== null && draft.trim() !== saved;
  return (
    <section className={className} aria-labelledby={titleId}>
      <div className={styles.headerRow}>
        <h2 className={titleClassName} id={titleId}>{title}</h2>
        <Button size="sm" variant="primary" onClick={handleSave} loading={saving} disabled={!changed}>
          儲存
        </Button>
      </div>
      <p className={styles.hint}>{hint}</p>
      {notice && <Alert severity="success" onClose={() => setNotice('')} className={styles.alert}>{notice}</Alert>}
      {error && <Alert severity="error" onClose={() => setError('')} className={styles.alert}>{error}</Alert>}
      {saved === null && !error ? (
        <Spinner size={24} color="var(--color-primary)" />
      ) : (
        <TextField
          multiline
          rows={8}
          fullWidth
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={placeholder}
          aria-label={title}
          disabled={saving || saved === null}
        />
      )}
    </section>
  );
}