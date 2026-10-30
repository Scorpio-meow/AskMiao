import { useState } from 'react';
import { llmConnectionService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogForm, DialogTitle, Icon, Spinner, TextField } from '../ui';
import { requestErrorMessage } from './requestErrorMessage';
import styles from './LlmConnections.module.css';
const API_BASE_HINTS = {
  openai: 'OpenAI 官方為 https://api.openai.com/v1；OpenAI 相容的服務（OpenRouter、vLLM 等）請填它的 /v1 位址',
  anthropic: 'Claude API 的位址',
  gemini: 'Gemini API 的位址',
  foundry: 'Foundry 資源端點，例如 https://<資源名稱>.services.ai.azure.com；Claude 部署必須使用這種端點',
  ollama: 'Ollama 的位址，例如 https://ollama.com',
};
const SEARCH_THRESHOLD = 8;
const presetOf = (providers, provider) => providers.find((preset) => preset.provider === provider);
const parseModels = (text) => [...new Set(text.split(/[\n,]/).map((model) => model.trim()).filter(Boolean))];
const matches = (text, query) => text.toLowerCase().includes(query.trim().toLowerCase());
const initialForm = (connection, providers) => {
  if (connection) {
    return {
      name: connection.name,
      provider: connection.provider,
      api_base: connection.api_base,
      api_key: '',
      models: connection.models.join('\n'),
      max_output_tokens: connection.max_output_tokens ? String(connection.max_output_tokens) : '',
      restricted: connection.allowed_user_ids !== null,
      selected: new Set(connection.allowed_user_ids || []),
    };
  }
  const preset = providers[0];
  return {
    name: '',
    provider: preset.provider,
    api_base: preset.api_base,
    api_key: '',
    models: preset.models.join('\n'),
    max_output_tokens: '',
    restricted: true,
    selected: new Set(),
  };
};
export default function ConnectionFormDialog({ connection, shared, providers, users, publicOnly, onClose, onSaved }) {
  const [form, setForm] = useState(() => initialForm(connection, providers));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [discovered, setDiscovered] = useState(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState('');
  const [modelQuery, setModelQuery] = useState('');
  const [userQuery, setUserQuery] = useState('');
  const preset = presetOf(providers, form.provider);
  const selectedModels = parseModels(form.models);
  const visibleModels = (discovered || []).filter((model) => matches(model, modelQuery));
  const visibleUsers = (users || []).filter((user) => matches(`${user.username} ${user.email}`, userQuery));
  const update = (changes) => setForm((prev) => ({ ...prev, ...changes }));
  const handleProviderChange = (provider) => {
    const next = presetOf(providers, provider);
    update({ provider, api_base: next.api_base, models: next.models.join('\n') });
    setDiscovered(null);
    setDiscoverError('');
  };
  const toggleModel = (model) => {
    const next = selectedModels.includes(model)
      ? selectedModels.filter((name) => name !== model)
      : [...selectedModels, model];
    update({ models: next.join('\n') });
  };
  const handleDiscover = async () => {
    setDiscovering(true);
    setDiscoverError('');
    try {
      const payload = { provider: form.provider, api_base: form.api_base };
      if (form.api_key) payload.api_key = form.api_key;
      else if (connection?.has_api_key) payload.connection_id = connection.id;
      const models = await llmConnectionService.discoverModels(payload);
      setDiscovered(models);
      setModelQuery('');
      if (models.length === 0) setDiscoverError('這個 API 沒有回報任何模型，請手動填寫');
    } catch (err) {
      setDiscovered(null);
      setDiscoverError(requestErrorMessage(err, '無法取得模型清單，請確認 API 位址與金鑰'));
    } finally {
      setDiscovering(false);
    }
  };
  const setUsersSelected = (userIds, selected) => setForm((prev) => {
    const next = new Set(prev.selected);
    userIds.forEach((userId) => (selected ? next.add(userId) : next.delete(userId)));
    return { ...prev, selected: next };
  });
  const handleSave = async (e) => {
    e.preventDefault();
    if (selectedModels.length === 0) {
      setError('至少要填一個模型名稱');
      return;
    }
    if (shared && form.restricted && form.selected.size === 0) {
      setError('限定帳號時至少要選擇一個帳號');
      return;
    }
    const payload = {
      name: form.name,
      provider: form.provider,
      api_base: form.api_base,
      models: selectedModels,
      max_output_tokens: preset.uses_max_output_tokens && form.max_output_tokens ? Number(form.max_output_tokens) : null,
    };
    if (form.api_key) payload.api_key = form.api_key;
    if (shared) payload.allowed_user_ids = form.restricted ? [...form.selected] : [];
    try {
      setSaving(true);
      setError('');
      if (shared) {
        if (connection) await llmConnectionService.updateShared(connection.id, payload);
        else await llmConnectionService.createShared(payload);
      } else if (connection) {
        await llmConnectionService.update(connection.id, payload);
      } else {
        await llmConnectionService.create(payload);
      }
      onSaved(connection ? `已更新「${form.name}」` : `已新增「${form.name}」`);
    } catch (err) {
      setError(requestErrorMessage(err, '儲存失敗，請檢查欄位內容'));
    } finally {
      setSaving(false);
    }
  };
  const keyHint = connection?.has_api_key
    ? '已設定金鑰，留空即沿用原本的金鑰；金鑰儲存後不會再顯示'
    : preset.requires_api_key
      ? '金鑰加密存放，儲存後不會再顯示'
      : '選填；自架的服務通常不需要';
  const busy = saving || discovering;
  return (
    <Dialog open onClose={busy ? undefined : onClose} maxWidth="md">
      <DialogForm onSubmit={handleSave} noValidate>
        <DialogTitle onClose={onClose} closeDisabled={busy}>
          {connection ? '編輯 API 連線' : shared ? '新增共用 API 連線' : '新增 API 連線'}
        </DialogTitle>
        <DialogContent>
          <div className={styles.form}>
            {error && <Alert severity="error">{error}</Alert>}
            {publicOnly && (
              <Alert severity="info">個人連線只能連到可從網際網路連線的公開位址；公司內部網路的服務請管理員設為共用連線。</Alert>
            )}
            <TextField
              fullWidth
              label="名稱"
              placeholder="例如 我的 OpenAI"
              value={form.name}
              onChange={(e) => update({ name: e.target.value })}
              disabled={saving}
              autoComplete="off"
              required
            />
            <div className={styles.field}>
              <label className={styles.label} htmlFor="llm-connection-provider">供應商</label>
              <select
                id="llm-connection-provider"
                className={styles.select}
                value={form.provider}
                onChange={(e) => handleProviderChange(e.target.value)}
                disabled={busy}
              >
                {providers.map((option) => (
                  <option key={option.provider} value={option.provider}>{option.label}</option>
                ))}
              </select>
            </div>
            <TextField
              fullWidth
              label="API 位址"
              type="url"
              value={form.api_base}
              onChange={(e) => update({ api_base: e.target.value })}
              helperText={API_BASE_HINTS[form.provider]}
              disabled={saving}
              autoComplete="off"
              required
            />
            <TextField
              fullWidth
              label="API 金鑰"
              type="password"
              value={form.api_key}
              onChange={(e) => update({ api_key: e.target.value })}
              placeholder={connection?.has_api_key ? '••••••••' : ''}
              helperText={keyHint}
              disabled={saving}
              autoComplete="new-password"
              required={preset.requires_api_key && !connection?.has_api_key}
            />
            <div className={styles.field}>
              <div className={styles.fieldHeader}>
                <span className={styles.label} id="llm-connection-models-label">模型（已選 {selectedModels.length} 個）</span>
                {form.provider !== 'foundry' && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleDiscover}
                    loading={discovering}
                    disabled={saving || !form.api_base}
                    startIcon={<Icon name="refresh" size={14} />}
                  >
                    從 API 取得模型
                  </Button>
                )}
              </div>
              {discoverError && <Alert severity="warning">{discoverError}</Alert>}
              {discovering && <Spinner size={20} color="var(--color-primary)" />}
              {discovered?.length > 0 && (
                <div className={styles.picker}>
                  {discovered.length > SEARCH_THRESHOLD && (
                    <input
                      type="search"
                      className={styles.search}
                      placeholder={`搜尋 ${discovered.length} 個模型`}
                      value={modelQuery}
                      onChange={(e) => setModelQuery(e.target.value)}
                      aria-label="搜尋模型"
                    />
                  )}
                  <ul className={styles.pickerList} role="list" aria-label="API 回報的模型">
                    {visibleModels.map((model) => (
                      <li key={model}>
                        <label className={styles.option}>
                          <input type="checkbox" checked={selectedModels.includes(model)} onChange={() => toggleModel(model)} disabled={saving} />
                          <span className={styles.mono}>{model}</span>
                        </label>
                      </li>
                    ))}
                    {visibleModels.length === 0 && <li className={styles.hint}>沒有符合的模型</li>}
                  </ul>
                </div>
              )}
              <TextField
                fullWidth
                multiline
                rows={4}
                aria-labelledby="llm-connection-models-label"
                value={form.models}
                onChange={(e) => update({ models: e.target.value })}
                helperText={form.provider === 'foundry'
                  ? '每行一個部署名稱；Foundry 無法從 API 列出部署，請手動填寫'
                  : '每行一個模型名稱，對話時可從中選擇；也可以按「從 API 取得模型」勾選'}
                disabled={saving}
                required
              />
            </div>
            {preset.uses_max_output_tokens && (
              <TextField
                fullWidth
                label="輸出 token 上限"
                type="number"
                min={1}
                inputMode="numeric"
                value={form.max_output_tokens}
                onChange={(e) => update({ max_output_tokens: e.target.value })}
                helperText="Claude 每次回應最多產生的 token 數（例如 16000），超過模型上限時自動取較小值；Foundry 只有 Claude 部署需要"
                disabled={saving}
              />
            )}
            {shared && (
              <fieldset className={styles.fieldset}>
                <legend className={styles.label}>可使用的帳號</legend>
                <label className={styles.option}>
                  <input type="radio" name="llm-connection-access" checked={!form.restricted} onChange={() => update({ restricted: false })} disabled={saving} />
                  <span>所有帳號<span className={styles.hint}>包含之後自行註冊的帳號</span></span>
                </label>
                <label className={styles.option}>
                  <input type="radio" name="llm-connection-access" checked={form.restricted} onChange={() => update({ restricted: true })} disabled={saving} />
                  <span>只限下列帳號（已選 {form.selected.size} 個）<span className={styles.hint}>其他帳號的模型清單看不到這個連線</span></span>
                </label>
                {form.restricted && (
                  <div className={styles.picker}>
                    <div className={styles.pickerToolbar}>
                      <input
                        type="search"
                        className={styles.search}
                        placeholder="搜尋使用者名稱或電子郵件"
                        value={userQuery}
                        onChange={(e) => setUserQuery(e.target.value)}
                        aria-label="搜尋帳號"
                      />
                      <Button size="sm" variant="secondary" onClick={() => setUsersSelected(visibleUsers.map((user) => user.id), true)} disabled={saving || visibleUsers.length === 0}>
                        全選
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => setUsersSelected(visibleUsers.map((user) => user.id), false)} disabled={saving || visibleUsers.length === 0}>
                        全部取消
                      </Button>
                    </div>
                    <ul className={styles.userList} role="list" aria-label="可使用的帳號">
                      {visibleUsers.map((user) => (
                        <li key={user.id} className={styles.userItem}>
                          <label className={styles.option}>
                            <input type="checkbox" checked={form.selected.has(user.id)} onChange={() => setUsersSelected([user.id], !form.selected.has(user.id))} disabled={saving} />
                            <span>
                              {user.username}{user.is_admin ? '（管理員）' : ''}{user.is_active ? '' : '（已停用）'}
                              <span className={styles.hint}>{user.email}</span>
                            </span>
                          </label>
                        </li>
                      ))}
                      {visibleUsers.length === 0 && <li className={styles.hint}>沒有符合的帳號</li>}
                    </ul>
                  </div>
                )}
              </fieldset>
            )}
          </div>
        </DialogContent>
        <DialogActions>
          <Button variant="secondary" onClick={onClose} disabled={busy}>取消</Button>
          <Button type="submit" variant="primary" loading={saving} disabled={discovering} startIcon={<Icon name="save" size={16} />}>儲存</Button>
        </DialogActions>
      </DialogForm>
    </Dialog>
  );
}
