import { useState } from 'react';
import { mcpService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogForm, DialogTitle, Icon } from '../../components/ui';
import { mcpFormToPayload, mcpServerToForm } from './forms';
import { CheckOption, Field, FormRow, FormSection } from './FormParts';
import { CREDENTIALS_UNREADABLE_NOTICE, SECRET_FIELD_HINT, getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
export default function McpServerFormDialog({ server, presets, onClose, onSaved }) {
  const [form, setForm] = useState(() => mcpServerToForm(server));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const applyPreset = (preset) => setForm({ ...mcpServerToForm(preset), requires_approval: true });
  const handleSave = async (e) => {
    e.preventDefault();
    try {
      setError('');
      const payload = mcpFormToPayload(form);
      setSaving(true);
      if (server) {
        await mcpService.updateServer(server.id, payload);
        onSaved('MCP 伺服器設定更新成功');
      } else {
        await mcpService.createServer(payload);
        onSaved('MCP 伺服器建立成功並已嘗試自動連線');
      }
    } catch (err) {
      setError(getRequestErrorMessage(err, '儲存失敗，請檢查 JSON 欄位格式'));
    } finally {
      setSaving(false);
    }
  };
  const isStdio = form.transport_type === 'stdio';
  return (
    <Dialog open onClose={saving ? undefined : onClose} maxWidth="lg">
      <DialogForm onSubmit={handleSave}>
        <DialogTitle
          onClose={onClose}
          closeDisabled={saving}
          subtitle={server ? server.name : 'Model Context Protocol 工具伺服器，建立後會自動連線並探索工具'}
        >
          {server ? '編輯 MCP 伺服器' : '新增 MCP 伺服器'}
        </DialogTitle>
        <DialogContent className={styles.dialogBody}>
          {error && <Alert severity="error">{error}</Alert>}
          {server?.credentials_unreadable && <Alert severity="warning">{CREDENTIALS_UNREADABLE_NOTICE}</Alert>}
          {!server && presets.length > 0 && (
            <div className={styles.presetGroup} role="group" aria-labelledby="mcp-presets-label">
              <span className={styles.presetLabel} id="mcp-presets-label">快速套用官方與社群範本</span>
              <div className={styles.inlineButtons}>
                {presets.map((p) => (
                  <Button key={p.name} variant="secondary" size="sm" onClick={() => applyPreset(p)}>
                    {p.display_name}
                  </Button>
                ))}
              </div>
            </div>
          )}
          <FormSection title="基本資訊">
            <FormRow>
              <Field id="mcp-name" label="伺服器識別名稱" required hint={server ? '建立後無法修改' : '英文小寫與底線'}>
                <input
                  id="mcp-name"
                  type="text"
                  className={`${styles.input} ${styles.mono}`}
                  placeholder="例如 mcp_time"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  disabled={!!server}
                  required
                  autoComplete="off"
                  aria-describedby="mcp-name-hint"
                />
              </Field>
              <Field id="mcp-display-name" label="顯示名稱" required>
                <input
                  id="mcp-display-name"
                  type="text"
                  className={styles.input}
                  placeholder="例如 時間查詢服務"
                  value={form.display_name}
                  onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  required
                  autoComplete="off"
                />
              </Field>
            </FormRow>
            <Field id="mcp-description" label="說明描述">
              <input
                id="mcp-description"
                type="text"
                className={styles.input}
                placeholder="說明此 MCP 伺服器的功能與用途"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                autoComplete="off"
              />
            </Field>
          </FormSection>
          <FormSection title="連線">
            <FormRow narrowFirst>
              <Field id="mcp-transport" label="傳輸模式">
                <select
                  id="mcp-transport"
                  className={styles.select}
                  value={form.transport_type}
                  onChange={(e) => setForm({ ...form, transport_type: e.target.value })}
                >
                  <option value="stdio">Stdio (子行程)</option>
                  <option value="http">HTTP（Streamable HTTP，舊版 SSE 自動相容）</option>
                  <option value="sse">SSE（舊版 HTTP+SSE）</option>
                </select>
              </Field>
              {isStdio ? (
                <Field id="mcp-command" label="啟動指令 (Command)" required>
                  <input
                    id="mcp-command"
                    type="text"
                    className={`${styles.input} ${styles.mono}`}
                    placeholder="例如 npx, uvx, python"
                    value={form.command}
                    onChange={(e) => setForm({ ...form, command: e.target.value })}
                    required
                    autoComplete="off"
                  />
                </Field>
              ) : (
                <Field id="mcp-url" label="連線網址 (URL)" required>
                  <input
                    id="mcp-url"
                    type="url"
                    className={`${styles.input} ${styles.mono}`}
                    placeholder="例如 http://localhost:8080/sse"
                    value={form.url}
                    onChange={(e) => setForm({ ...form, url: e.target.value })}
                    required
                    autoComplete="off"
                  />
                </Field>
              )}
            </FormRow>
            {isStdio ? (
              <>
                <Field id="mcp-args" label="指令參數清單" hint="JSON 陣列格式">
                  <textarea
                    id="mcp-args"
                    className={`${styles.input} ${styles.codeInput} ${styles.textareaMd}`}
                    value={form.args_json}
                    onChange={(e) => setForm({ ...form, args_json: e.target.value })}
                    placeholder='["-y", "@modelcontextprotocol/server-filesystem@2026.8.31", "./mcp_filesystem_sandbox"]'
                    spellCheck={false}
                    aria-describedby="mcp-args-hint"
                  />
                </Field>
                <Field id="mcp-env" label="環境變數設定" hint={`JSON 物件格式。${SECRET_FIELD_HINT}`}>
                  <textarea
                    id="mcp-env"
                    className={`${styles.input} ${styles.codeInput} ${styles.textareaSm}`}
                    value={form.env_vars_json}
                    onChange={(e) => setForm({ ...form, env_vars_json: e.target.value })}
                    placeholder='{"API_KEY": "secret"}'
                    spellCheck={false}
                    aria-describedby="mcp-env-hint"
                  />
                </Field>
              </>
            ) : (
              <Field id="mcp-headers" label="自訂 HTTP Headers" hint={`JSON 物件格式。${SECRET_FIELD_HINT}`}>
                <textarea
                  id="mcp-headers"
                  className={`${styles.input} ${styles.codeInput} ${styles.textareaSm}`}
                  value={form.headers_json}
                  onChange={(e) => setForm({ ...form, headers_json: e.target.value })}
                  placeholder='{"Authorization": "Bearer ..."}'
                  spellCheck={false}
                  aria-describedby="mcp-headers-hint"
                />
              </Field>
            )}
          </FormSection>
          {!isStdio && (
            <FormSection
              title="OAuth 用戶端（選填）"
              description="伺服器要求 OAuth 時，儲存後在伺服器列按「OAuth 授權」。授權伺服器支援動態註冊時可以留空；不支援時填入在授權伺服器註冊的用戶端。"
            >
              <FormRow>
                <Field id="mcp-oauth-client-id" label="Client ID">
                  <input
                    id="mcp-oauth-client-id"
                    type="text"
                    className={styles.input}
                    value={form.oauth_client_id}
                    onChange={(e) => setForm({ ...form, oauth_client_id: e.target.value })}
                    autoComplete="off"
                  />
                </Field>
                <Field id="mcp-oauth-client-secret" label="Client Secret（公開用戶端可留空）" hint={SECRET_FIELD_HINT}>
                  <input
                    id="mcp-oauth-client-secret"
                    type="password"
                    className={styles.input}
                    value={form.oauth_client_secret}
                    onChange={(e) => setForm({ ...form, oauth_client_secret: e.target.value })}
                    autoComplete="off"
                    aria-describedby="mcp-oauth-client-secret-hint"
                  />
                </Field>
              </FormRow>
              <Field id="mcp-oauth-scope" label="Scope（選填）" hint="以空白分隔">
                <input
                  id="mcp-oauth-scope"
                  type="text"
                  className={styles.input}
                  value={form.oauth_scope}
                  onChange={(e) => setForm({ ...form, oauth_scope: e.target.value })}
                  autoComplete="off"
                  aria-describedby="mcp-oauth-scope-hint"
                />
              </Field>
            </FormSection>
          )}
          <CheckOption
            type="checkbox"
            checked={form.requires_approval}
            onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })}
            label="AI 呼叫此伺服器的工具前需使用者在對話中確認"
            hint="MCP 工具可能讀寫檔案或呼叫外部服務，建議保持開啟"
          />
        </DialogContent>
        <DialogActions>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            取消
          </Button>
          <Button variant="primary" type="submit" loading={saving} startIcon={<Icon name="save" size={16} />}>
            {server ? '儲存變更' : '建立並連線探索'}
          </Button>
        </DialogActions>
      </DialogForm>
    </Dialog>
  );
}