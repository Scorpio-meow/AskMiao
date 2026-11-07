import { useState } from 'react';
import { apiToolService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogForm, DialogTitle, Icon } from '../../components/ui';
import { BODY_CONTENT_TYPES, HTTP_METHODS, defaultRequiresApproval, toolFormToPayload, toolToForm } from './forms';
import { CheckOption, Field, FormRow, FormSection } from './FormParts';
import { CREDENTIALS_UNREADABLE_NOTICE, SECRET_FIELD_HINT, getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
const AUTH_INPUTS = {
  bearer: [{ key: 'token', label: 'Bearer Token', secret: true }],
  api_key: [
    { key: 'key_name', label: '金鑰名稱', hint: '標頭、查詢參數或 Cookie 的名稱', placeholder: '例如 X-API-Key' },
    { key: 'key_in', label: '金鑰位置', options: [['header', 'HTTP 標頭'], ['query', '查詢參數'], ['cookie', 'Cookie']] },
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
    { key: 'scope', label: 'Scope（選填）', hint: '以空白分隔' },
    { key: 'client_auth', label: '用戶端驗證方式', options: [['basic', 'HTTP Basic（client_secret_basic）'], ['post', '放在表單本文（client_secret_post）']] },
  ],
};
const AUTH_TYPE_OPTIONS = [
  ['none', '無認證 (None)'],
  ['bearer', 'Bearer Token'],
  ['api_key', 'API Key'],
  ['basic', 'HTTP Basic'],
  ['oauth2_client_credentials', 'OAuth2 Client Credentials'],
];
const BODY_CONTENT_TYPE_LABELS = {
  'application/json': 'JSON',
  'application/x-www-form-urlencoded': '表單（x-www-form-urlencoded）',
  'multipart/form-data': '多部分表單（multipart/form-data）',
  'application/xml': 'XML',
  'text/plain': '純文字',
};
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
  const authInputs = AUTH_INPUTS[form.auth_type] || [];
  return (
    <Dialog open onClose={saving ? undefined : onClose} maxWidth="lg">
      <DialogForm onSubmit={handleSave}>
        <DialogTitle
          onClose={onClose}
          closeDisabled={saving}
          subtitle={tool ? tool.name : '定義一個 HTTP 端點，AI 會依用途描述判斷何時呼叫'}
        >
          {tool ? '編輯自訂 API 工具' : '手動建立自訂 API 工具'}
        </DialogTitle>
        <DialogContent className={styles.dialogBody}>
          {error && <Alert severity="error">{error}</Alert>}
          {tool?.credentials_unreadable && <Alert severity="warning">{CREDENTIALS_UNREADABLE_NOTICE}</Alert>}
          <FormSection title="基本資訊">
            <FormRow>
              <Field id="tool-name" label="工具識別碼" required hint="英文小寫與底線，供 LLM 呼叫">
                <input
                  id="tool-name"
                  type="text"
                  className={`${styles.input} ${styles.mono}`}
                  placeholder="例如 get_user_profile"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                  autoComplete="off"
                  aria-describedby="tool-name-hint"
                />
              </Field>
              <Field id="tool-display-name" label="顯示名稱" required>
                <input
                  id="tool-display-name"
                  type="text"
                  className={styles.input}
                  placeholder="例如 查詢使用者個人檔案"
                  value={form.display_name}
                  onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  required
                  autoComplete="off"
                />
              </Field>
            </FormRow>
            <Field id="tool-description" label="工具用途描述" required hint="詳細說明工具功能與呼叫時機，AI 會依此判斷何時使用">
              <textarea
                id="tool-description"
                className={`${styles.input} ${styles.textareaSm}`}
                placeholder="例如：當使用者需要查詢特定 ID 的使用者基本資料時呼叫。"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                required
                aria-describedby="tool-description-hint"
              />
            </Field>
          </FormSection>
          <FormSection title="請求">
            <FormRow narrowFirst>
              <Field id="tool-method" label="HTTP 方法">
                <select
                  id="tool-method"
                  className={styles.select}
                  value={form.method}
                  onChange={(e) => setForm({
                    ...form,
                    method: e.target.value,
                    requires_approval: defaultRequiresApproval(e.target.value)
                  })}
                >
                  {[...new Set([...HTTP_METHODS, form.method])].map((method) => (
                    <option key={method} value={method}>{method}</option>
                  ))}
                </select>
              </Field>
              <Field id="tool-url" label="請求完整 URL" required hint="支援 {param} 路徑變數">
                <input
                  id="tool-url"
                  type="text"
                  className={`${styles.input} ${styles.mono}`}
                  placeholder="例如 https://api.example.com/users/{userId}"
                  value={form.url}
                  onChange={(e) => setForm({ ...form, url: e.target.value })}
                  required
                  autoComplete="off"
                  aria-describedby="tool-url-hint"
                />
              </Field>
            </FormRow>
            <Field id="tool-body-type" label="請求本文格式">
              <select
                id="tool-body-type"
                className={styles.select}
                value={form.body_content_type}
                onChange={(e) => setForm({ ...form, body_content_type: e.target.value })}
              >
                {[...new Set([...BODY_CONTENT_TYPES, form.body_content_type])].map((type) => (
                  <option key={type} value={type}>{BODY_CONTENT_TYPE_LABELS[type] || type}</option>
                ))}
              </select>
            </Field>
          </FormSection>
          <FormSection title="認證">
            <Field id="tool-auth-type" label="認證方式">
              <select
                id="tool-auth-type"
                className={styles.select}
                value={form.auth_type}
                onChange={(e) => setForm({ ...form, auth_type: e.target.value })}
              >
                {AUTH_TYPE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </Field>
            {authInputs.length > 0 && (
              <FormRow>
                {authInputs.map((field) => {
                  const inputId = `tool-auth-${field.key}`;
                  const hint = field.secret ? SECRET_FIELD_HINT : field.hint;
                  const setValue = (value) => setForm({ ...form, auth: { ...form.auth, [field.key]: value } });
                  return (
                    <Field key={field.key} id={inputId} label={field.label} hint={hint}>
                      {field.options ? (
                        <select id={inputId} className={styles.select} value={form.auth[field.key]} onChange={(e) => setValue(e.target.value)}>
                          {field.options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                        </select>
                      ) : (
                        <input
                          id={inputId}
                          type={field.secret ? 'password' : 'text'}
                          className={styles.input}
                          placeholder={field.placeholder}
                          value={form.auth[field.key]}
                          onChange={(e) => setValue(e.target.value)}
                          autoComplete="off"
                          aria-describedby={hint ? `${inputId}-hint` : undefined}
                        />
                      )}
                    </Field>
                  );
                })}
              </FormRow>
            )}
          </FormSection>
          <FormSection title="參數">
            <Field id="tool-parameters" label="參數 JSON Schema 定義" hint="以 JSON Schema 描述 AI 呼叫時要提供的參數">
              <textarea
                id="tool-parameters"
                className={`${styles.input} ${styles.codeInput} ${styles.textareaLg}`}
                value={form.parameters_json}
                onChange={(e) => setForm({ ...form, parameters_json: e.target.value })}
                spellCheck={false}
                aria-describedby="tool-parameters-hint"
              />
            </Field>
          </FormSection>
          <CheckOption
            type="checkbox"
            checked={form.requires_approval}
            onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })}
            label="AI 呼叫前需使用者在對話中確認"
            hint="會修改外部資料的工具（POST、PUT、PATCH、DELETE）預設開啟"
          />
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