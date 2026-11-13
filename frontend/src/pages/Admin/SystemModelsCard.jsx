import { useCallback, useEffect, useState } from 'react';
import { llmConnectionService, systemModelService } from '../../services/api';
import { REASONING_EFFORT_OPTIONS, supportsReasoningEffort } from '../../utils/reasoningEffort';
import { Alert, Button, Spinner } from '../../components/ui';
import connectionStyles from '../../components/LlmConnections/LlmConnections.module.css';
import styles from '../AdminDashboard.module.css';
const PURPOSES = [
  {
    key: 'document_summary',
    label: '文件摘要',
    hint: '上傳文件與重建索引時產生知識庫摘要；未指定時改用規則產生摘要。',
  },
  {
    key: 'pdf_ocr',
    label: '掃描 PDF 辨識（OCR）',
    hint: '知識庫上傳與聊天附件中沒有文字層的 PDF 頁面會送給這個模型辨識，模型須支援圖片輸入；未指定時掃描頁不做 OCR。',
  },
];
const choiceOf = (assignment) => (assignment ? JSON.stringify([assignment.connection_id, assignment.model_name]) : '');
const modelOf = (choice) => (choice ? JSON.parse(choice)[1] : '');
const toForm = (assigned) => Object.fromEntries(PURPOSES.map(({ key }) => [
  key,
  { choice: choiceOf(assigned[key]), effort: assigned[key]?.reasoning_effort ?? '' },
]));
const toPayload = (form) => Object.fromEntries(PURPOSES.map(({ key }) => {
  if (!form[key].choice) return [key, null];
  const [connectionId, modelName] = JSON.parse(form[key].choice);
  return [key, { connection_id: connectionId, model_name: modelName, reasoning_effort: form[key].effort }];
}));
export default function SystemModelsCard({ refreshKey }) {
  const [connections, setConnections] = useState(null);
  const [values, setValues] = useState(null);
  const [saved, setSaved] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const load = useCallback(async () => {
    try {
      setError('');
      setNotice('');
      const [shared, assigned] = await Promise.all([llmConnectionService.getShared(), systemModelService.get()]);
      setConnections(shared);
      setValues(toForm(assigned));
      setSaved(toForm(assigned));
    } catch (err) {
      setError('載入系統模型失敗：' + (err.response?.data?.detail || err.message));
    }
  }, []);
  useEffect(() => {
    queueMicrotask(load);
  }, [load, refreshKey]);
  const selectModel = (key, choice) => setValues((prev) => {
    const effort = prev[key].effort;
    const keepEffort = choice && effort && supportsReasoningEffort(modelOf(choice), effort);
    return { ...prev, [key]: { choice, effort: keepEffort ? effort : '' } };
  });
  const selectEffort = (key, effort) => setValues((prev) => ({ ...prev, [key]: { ...prev[key], effort } }));
  const handleSave = async () => {
    setSaving(true);
    setNotice('');
    try {
      const assigned = await systemModelService.update(toPayload(values));
      setValues(toForm(assigned));
      setSaved(toForm(assigned));
      setNotice('已儲存系統模型');
    } catch (err) {
      setError('儲存系統模型失敗：' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };
  const changed = values && saved && JSON.stringify(values) !== JSON.stringify(saved);
  const missingEffort = values && PURPOSES.some(({ key }) => values[key].choice && !values[key].effort);
  return (
    <div className={styles.card}>
      <div className={styles.cardHeaderRow}>
        <h2 className={styles.cardTitle}>系統模型</h2>
        <Button size="sm" variant="primary" onClick={handleSave} loading={saving} disabled={!changed || missingEffort}>
          儲存
        </Button>
      </div>
      <p className={styles.cardHint}>
        文件摘要與掃描 PDF 辨識由系統代為呼叫模型，費用算在所選的共用 API 連線上。思考程度越高越慢，小型本機模型建議選「無」，以免逾時。
      </p>
      {notice && <Alert severity="success" onClose={() => setNotice('')} className={styles.pageAlert}>{notice}</Alert>}
      {error && <Alert severity="error" onClose={() => setError('')} className={styles.pageAlert}>{error}</Alert>}
      {values === null && !error ? (
        <Spinner size={24} color="var(--color-primary)" />
      ) : values && (
        <div className={connectionStyles.form}>
          {connections.length === 0 && (
            <p className={styles.cardHint}>還沒有共用 API 連線，請先在上方「共用 API 連線」新增。</p>
          )}
          {PURPOSES.map(({ key, label, hint }) => {
            const { choice, effort } = values[key];
            const model = modelOf(choice);
            return (
              <fieldset className={connectionStyles.fieldset} key={key}>
                <legend>{label}</legend>
                <div className={connectionStyles.field}>
                  <label className={connectionStyles.label} htmlFor={`system-model-${key}`}>模型</label>
                  <select
                    id={`system-model-${key}`}
                    className={connectionStyles.select}
                    value={choice}
                    onChange={(e) => selectModel(key, e.target.value)}
                    disabled={saving}
                  >
                    <option value="">未指定</option>
                    {connections.map((connection) => (
                      <optgroup key={connection.id} label={connection.name}>
                        {connection.models.map((name) => (
                          <option key={name} value={choiceOf({ connection_id: connection.id, model_name: name })}>
                            {name}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </div>
                <div className={connectionStyles.field}>
                  <label className={connectionStyles.label} htmlFor={`system-model-${key}-effort`}>思考程度</label>
                  <select
                    id={`system-model-${key}-effort`}
                    className={connectionStyles.select}
                    value={effort}
                    onChange={(e) => selectEffort(key, e.target.value)}
                    disabled={saving || !choice}
                    aria-invalid={Boolean(choice && !effort)}
                  >
                    <option value="" disabled>{choice ? '請選擇思考程度' : '先選擇模型'}</option>
                    {REASONING_EFFORT_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value} disabled={!supportsReasoningEffort(model, option.value)}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <span className={connectionStyles.hint}>{hint}</span>
              </fieldset>
            );
          })}
        </div>
      )}
    </div>
  );
}