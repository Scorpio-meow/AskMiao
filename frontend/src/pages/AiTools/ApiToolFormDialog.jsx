import { useState } from 'react';
import { apiToolService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogForm, DialogTitle, Icon } from '../../components/ui';
import { BODY_CONTENT_TYPES, defaultRequiresApproval, toolFormToPayload, toolToForm } from './forms';
import { CREDENTIALS_UNREADABLE_NOTICE, SECRET_FIELD_HINT, getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
const AUTH_INPUTS = {
  bearer: [{ key: 'token', label: 'Bearer Token', secret: true }],
  api_key: [
    { key: 'key_name', label: '金鑰名稱（標頭或查詢參數名）', placeholder: '例如 X-API-Key' },
    { key: 'key_in', label: '金鑰位置', options: [['header', 'HTTP 標頭'], ['query', '查詢參數']] },
    { key: 'key_value', label: 'API Key', secret: true },
  ],
  basic: [
    { key: 'username', label: '使用者名稱' },
    { key: 'password', label: '密碼', secret: true },
  ],
  oauth2_client_credentials: [
    { key: 'token_url', label: 'Token 端點網址', placeholder: 'https://auth.example.com/oauth/token' },
    { key: 'client_id', label: 'Client ID' },
    { key: 'client_secret', label: 'Client Secret', secret: true },
    { key: 'scope', label: 'Scope（選填，以空白分隔）' },
    { key: 'client_auth', label: '用戶端驗證方式', options: [['basic', 'HTTP Basic（client_secret_basic）'], ['post', '放在表單本文（client_secret_post）']] },
  ],
};
const BODY_CONTENT_TYPE_LABELS = {
  'application/json': 'JSON',
  'application/x-www-form-urlencoded': '表單（x-www-form-urlencoded）',
  'multipart/form-data': '多部分表單（multipart/form-data）',
};
/** 手動新增或編輯自訂 API 工具；tool 為 null 時新增 */
export default function ApiToolFormDialog({ tool, onClose, onSaved }) {
  const [form, setForm] = useState(() => toolToForm(tool));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const handleSave = async (e) => {
    e.preventDefault();
    try {
      setError('');
      const payload = toolFormToPayload(form);
      setSaving(true);
      if (tool) {
        await apiToolService.updateTool(tool.id, payload);
        onSaved('工具更新成功');
      } else {
        await apiToolService.createTool(payload);
        onSaved('自訂 API 工具建立成功');
      }
    } catch (err) {
      setError(getRequestErrorMessage(err, '儲存失敗，請檢查參數格式與必填欄位'));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog open onClose={saving ? undefined : onClose} maxWidth="lg">
      <DialogForm onSubmit={handleSave}>
        <DialogTitle onClose={onClose} closeDisabled={saving}>
          {tool ? '編輯自訂 API 工具' : '手動建立自訂 API 工具'}
        </DialogTitle>
        <DialogContent className={styles.dialogBody}>
          {error && <Alert severity="error">{error}</Alert>}
          {tool?.credentials_unreadable && <Alert severity="warning">{CREDENTIALS_UNREADABLE_NOTICE}</Alert>}
          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="tool-name">工具識別碼（英文小寫與底線，供 LLM 調用）*</label>
              <input
                id="tool-name"
                type="text"
                className={styles.formInput}
                placeholder="例如 get_user_profile"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                autoComplete="off"
              />
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="tool-display-name">顯示名稱*</label>
              <input
                id="tool-display-name"
                type="text"
                className={styles.formInput}
                placeholder="例如 查詢使用者個人檔案"
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                required
                autoComplete="off"
              />
            </div>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel} htmlFor="tool-description">工具用途描述（詳細說明工具功能與調用時機，供 AI 判斷何時使用）*</label>
            <textarea
              id="tool-description"
              className={`${styles.formInput} ${styles.textareaSm}`}
              placeholder="例如：當使用者需要查詢特定 ID 的使用者基本資料時調用。"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              required
            />
          </div>
          <div className={`${styles.formRow} ${styles.formRowNarrowFirst}`}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="tool-method">HTTP 方法</label>
              <select
                id="tool-method"
                className={styles.formSelect}
                value={form.method}
                onChange={(e) => setForm({
                  ...form,
                  method: e.target.value,
                  requires_approval: defaultRequiresApproval(e.target.value)
                })}
              >
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="DELETE">DELETE</option>
                <option value="PATCH">PATCH</option>
              </select>
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="tool-url">請求完整 URL（支援 &#123;param&#125; 路徑變數）*</label>
              <input
                id="tool-url"
                type="text"
                className={styles.formInput}
                placeholder="例如 https://api.example.com/users/{userId}"
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                required
                autoComplete="off"
              />
            </div>
          </div>
          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="tool-auth-type">認證方式</label>
              <select
                id="tool-auth-type"
                className={styles.formSelect}
                value={form.auth_type}
                onChange={(e) => setForm({ ...form, auth_type: e.target.value })}
              >
                <option value="none">無認證 (None)</option>
                <option value="bearer">Bearer Token</option>
                <option value="api_key">API Key</option>
                <option value="basic">HTTP Basic</option>
                <option value="oauth2_client_credentials">OAuth2 Client Credentials</option>
              </select>
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="tool-body-type">請求本文格式</label>
              <select
                id="tool-body-type"
                className={styles.formSelect}
                value={form.body_content_type}
                onChange={(e) => setForm({ ...form, body_content_type: e.target.value })}
              >
                {BODY_CONTENT_TYPES.map((type) => (
                  <option key={type} value={type}>{BODY_CONTENT_TYPE_LABELS[type]}</option>
                ))}
              </select>
            </div>
          </div>
          {(AUTH_INPUTS[form.auth_type] || []).length > 0 && (
            <div className={styles.formRow}>
              {AUTH_INPUTS[form.auth_type].map((field) => {
                const inputId = `tool-auth-${field.key}`;
                const setValue = (value) => setForm({ ...form, auth: { ...form.auth, [field.key]: value } });
                return (
                  <div key={field.key} className={styles.formGroup}>
                    <label className={styles.formLabel} htmlFor={inputId}>{field.label}</label>
                    {field.options ? (
                      <select id={inputId} className={styles.formSelect} value={form.auth[field.key]} onChange={(e) => setValue(e.target.value)}>
                        {field.options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    ) : (
                      <input
                        id={inputId}
                        type={field.secret ? 'password' : 'text'}
                        className={styles.formInput}
                        placeholder={field.placeholder}
                        value={form.auth[field.key]}
                        onChange={(e) => setValue(e.target.value)}
                        autoComplete="off"
                        aria-describedby={field.secret ? `${inputId}-hint` : undefined}
                      />
                    )}
                    {field.secret && <span id={`${inputId}-hint`} className={styles.credentialHint}>{SECRET_FIELD_HINT}</span>}
                  </div>
                );
              })}
            </div>
          )}
          <div className={styles.formGroup}>
            <label className={styles.formLabel} htmlFor="tool-parameters">參數 JSON Schema 定義 (Parameters Schema)</label>
            <textarea
              id="tool-parameters"
              className={`${styles.formTextarea} ${styles.textareaLg}`}
              value={form.parameters_json}
              onChange={(e) => setForm({ ...form, parameters_json: e.target.value })}
            />
          </div>
          <label className={styles.approvalOption}>
            <input
              type="checkbox"
              checked={form.requires_approval}
              onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })}
            />
            <span>
              AI 呼叫前需使用者在對話中確認
              <span className={styles.approvalHint}>會修改外部資料的工具（POST、PUT、PATCH、DELETE）預設開啟</span>
            </span>
          </label>
        </DialogContent>
        <DialogActions>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            取消
          </Button>
          <Button variant="primary" type="submit" loading={saving} startIcon={<Icon name="save" size={16} />}>
            {tool ? '儲存變更' : '建立工具'}
          </Button>
        </DialogActions>
      </DialogForm>
    </Dialog>
  );
}
