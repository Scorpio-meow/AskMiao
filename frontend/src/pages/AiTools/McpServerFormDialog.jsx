import { useState } from 'react';
import { mcpService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogForm, DialogTitle, Icon } from '../../components/ui';
import { mcpFormToPayload, mcpServerToForm } from './forms';
import { CREDENTIALS_UNREADABLE_NOTICE, SECRET_FIELD_HINT, getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
/** 新增或編輯 MCP 伺服器；server 為 null 時新增，presets 是後端提供的範本 */
export default function McpServerFormDialog({ server, presets, onClose, onSaved }) {
  const [form, setForm] = useState(() => mcpServerToForm(server));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // 套用範本時一律需要確認：範本工具的行為同樣無法事先得知
  const applyPreset = (preset) => setForm({ ...mcpServerToForm(preset), requires_approval: true });
  const handleSave = async (e) => {
    e.preventDefault();
    try {
      setError('');
      const payload = mcpFormToPayload(form);
      setSaving(true);
      if (server) {
        await mcpService.updateServer(server.id, payload);
        onSaved('MCP 伺服器配置更新成功');
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
  return (
    <Dialog open onClose={saving ? undefined : onClose} maxWidth="lg">
      <DialogForm onSubmit={handleSave}>
        <DialogTitle onClose={onClose} closeDisabled={saving}>
          {server ? '編輯 MCP 伺服器' : '新增 Model Context Protocol (MCP) 伺服器'}
        </DialogTitle>
        <DialogContent className={styles.dialogBody}>
          {error && <Alert severity="error">{error}</Alert>}
          {server?.credentials_unreadable && <Alert severity="warning">{CREDENTIALS_UNREADABLE_NOTICE}</Alert>}
          {!server && presets.length > 0 && (
            <div className={styles.formGroup}>
              <span className={styles.formLabel} id="mcp-presets-label">快速套用官方與社群範本：</span>
              <div className={styles.inlineButtons} role="group" aria-labelledby="mcp-presets-label">
                {presets.map((p) => (
                  <Button
                    key={p.name}
                    variant="secondary"
                    onClick={() => applyPreset(p)}
                  >
                    {p.display_name}
                  </Button>
                ))}
              </div>
            </div>
          )}
          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="mcp-name">伺服器識別名稱（英文小寫與底線）*</label>
              <input
                id="mcp-name"
                type="text"
                className={styles.formInput}
                placeholder="例如 mcp_time"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                disabled={!!server}
                required
                autoComplete="off"
              />
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="mcp-display-name">顯示名稱*</label>
              <input
                id="mcp-display-name"
                type="text"
                className={styles.formInput}
                placeholder="例如 時間查詢服務"
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                required
                autoComplete="off"
              />
            </div>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel} htmlFor="mcp-description">說明描述</label>
            <input
              id="mcp-description"
              type="text"
              className={styles.formInput}
              placeholder="說明此 MCP 伺服器的功能與用途"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              autoComplete="off"
            />
          </div>
          <div className={`${styles.formRow} ${styles.formRowNarrowFirst}`}>
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="mcp-transport">傳輸模式</label>
              <select
                id="mcp-transport"
                className={styles.formSelect}
                value={form.transport_type}
                onChange={(e) => setForm({ ...form, transport_type: e.target.value })}
              >
                <option value="stdio">Stdio (子進程)</option>
                <option value="sse">SSE (Server-Sent Events)</option>
                <option value="http">HTTP (POST Stream)</option>
              </select>
            </div>
            {form.transport_type === 'stdio' ? (
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="mcp-command">啟動指令 (Command)*</label>
                <input
                  id="mcp-command"
                  type="text"
                  className={styles.formInput}
                  placeholder="例如 npx, uvx, python"
                  value={form.command}
                  onChange={(e) => setForm({ ...form, command: e.target.value })}
                  required
                  autoComplete="off"
                />
              </div>
            ) : (
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="mcp-url">連線網址 (URL)*</label>
                <input
                  id="mcp-url"
                  type="url"
                  className={styles.formInput}
                  placeholder="例如 http://localhost:8080/sse"
                  value={form.url}
                  onChange={(e) => setForm({ ...form, url: e.target.value })}
                  required
                  autoComplete="off"
                />
              </div>
            )}
          </div>
          {form.transport_type === 'stdio' && (
            <>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="mcp-args">指令參數清單（JSON 陣列格式）</label>
                <textarea
                  id="mcp-args"
                  className={`${styles.formTextarea} ${styles.textareaMd}`}
                  value={form.args_json}
                  onChange={(e) => setForm({ ...form, args_json: e.target.value })}
                  placeholder='["-y", "@modelcontextprotocol/server-filesystem@2026.8.31", "./mcp_filesystem_sandbox"]'
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel} htmlFor="mcp-env">環境變數配置（JSON 物件格式）</label>
                <textarea
                  id="mcp-env"
                  className={`${styles.formTextarea} ${styles.textareaSm}`}
                  value={form.env_vars_json}
                  onChange={(e) => setForm({ ...form, env_vars_json: e.target.value })}
                  placeholder='{"API_KEY": "secret"}'
                  aria-describedby="mcp-env-hint"
                />
                <span id="mcp-env-hint" className={styles.credentialHint}>{SECRET_FIELD_HINT}</span>
              </div>
            </>
          )}
          {form.transport_type !== 'stdio' && (
            <div className={styles.formGroup}>
              <label className={styles.formLabel} htmlFor="mcp-headers">自訂 HTTP Headers（JSON 物件格式）</label>
              <textarea
                id="mcp-headers"
                className={`${styles.formTextarea} ${styles.textareaSm}`}
                value={form.headers_json}
                onChange={(e) => setForm({ ...form, headers_json: e.target.value })}
                placeholder='{"Authorization": "Bearer ..."}'
                aria-describedby="mcp-headers-hint"
              />
              <span id="mcp-headers-hint" className={styles.credentialHint}>{SECRET_FIELD_HINT}</span>
            </div>
          )}
          <label className={styles.approvalOption}>
            <input
              type="checkbox"
              checked={form.requires_approval}
              onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })}
            />
            <span>
              AI 呼叫此伺服器的工具前需使用者在對話中確認
              <span className={styles.approvalHint}>MCP 工具可能讀寫檔案或呼叫外部服務，建議保持開啟</span>
            </span>
          </label>
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
