import { useState } from 'react';
import { adminService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogForm, DialogTitle, Icon, IconButton, Switch, TextField } from '../../components/ui';
import { requestErrorMessage } from '../../components/LlmConnections/requestErrorMessage';
import styles from '../AdminDashboard.module.css';
const EMPTY_FORM = { username: '', email: '', password: '', confirmPassword: '', is_admin: false };
export const PASSWORD_HINT = '至少 8 個字元，需包含大寫字母、小寫字母和數字';
export default function UserCreateDialog({ onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [showPassword, setShowPassword] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const update = (changes) => setForm((prev) => ({ ...prev, ...changes }));
  const mismatch = form.confirmPassword.length > 0 && form.password !== form.confirmPassword;
  const handleSave = async (e) => {
    e.preventDefault();
    if (!form.username || !form.email || !form.password) {
      setError('請填寫使用者名稱、電子郵件與密碼');
      return;
    }
    if (form.password !== form.confirmPassword) {
      setError('兩次輸入的密碼不一致');
      return;
    }
    try {
      setSaving(true);
      setError('');
      const user = await adminService.createUser({
        username: form.username,
        email: form.email,
        password: form.password,
        is_admin: form.is_admin,
      });
      onSaved(`已新增${user.is_admin ? '管理員' : '帳號'}「${user.username}」`);
    } catch (err) {
      setError(requestErrorMessage(err, '新增帳號失敗'));
    } finally {
      setSaving(false);
    }
  };
  const visibilityToggle = (
    <IconButton size="sm" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? '隱藏密碼' : '顯示密碼'}>
      <Icon name={showPassword ? 'visibility-off' : 'visibility'} size={18} />
    </IconButton>
  );
  return (
    <Dialog open onClose={saving ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogForm onSubmit={handleSave} noValidate>
        <DialogTitle onClose={onClose} closeDisabled={saving}>新增使用者</DialogTitle>
        <DialogContent>
          <div className={styles.editUserForm}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              fullWidth
              label="使用者名稱"
              value={form.username}
              onChange={(e) => update({ username: e.target.value })}
              helperText="3–50 個字元，只能包含英文字母、數字、底線（_）與連字號（-）"
              autoComplete="off"
              disabled={saving}
              required
            />
            <TextField
              fullWidth
              label="電子郵件"
              type="email"
              value={form.email}
              onChange={(e) => update({ email: e.target.value })}
              autoComplete="off"
              disabled={saving}
              required
            />
            <TextField
              fullWidth
              label="密碼"
              type={showPassword ? 'text' : 'password'}
              value={form.password}
              onChange={(e) => update({ password: e.target.value })}
              helperText={PASSWORD_HINT}
              autoComplete="new-password"
              endAdornment={visibilityToggle}
              disabled={saving}
              required
            />
            <TextField
              fullWidth
              label="確認密碼"
              type={showPassword ? 'text' : 'password'}
              value={form.confirmPassword}
              onChange={(e) => update({ confirmPassword: e.target.value })}
              error={mismatch}
              helperText={mismatch ? '兩次輸入的密碼不一致' : undefined}
              autoComplete="new-password"
              disabled={saving}
              required
            />
            <Switch
              checked={form.is_admin}
              onChange={(e) => update({ is_admin: e.target.checked })}
              label="管理員權限"
              disabled={saving}
            />
            <p className={styles.cardHint}>
              新帳號沒有任何可用的模型：可在下方「共用 API 連線」開放給他，或請他在「個人資料」設定自己的 API。
            </p>
          </div>
        </DialogContent>
        <DialogActions>
          <Button variant="secondary" onClick={onClose} disabled={saving}>取消</Button>
          <Button type="submit" variant="primary" loading={saving} startIcon={<Icon name="person-add" size={16} />}>新增</Button>
        </DialogActions>
      </DialogForm>
    </Dialog>
  );
}
