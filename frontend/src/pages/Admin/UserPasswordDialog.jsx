import { useState } from 'react';
import { adminService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogForm, DialogTitle, Icon, TextField } from '../../components/ui';
import { requestErrorMessage } from '../../components/LlmConnections/requestErrorMessage';
import { PASSWORD_HINT } from './UserCreateDialog';
import styles from '../AdminDashboard.module.css';
export default function UserPasswordDialog({ user, onClose, onSaved }) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const mismatch = confirmPassword.length > 0 && password !== confirmPassword;
  const handleSave = async (e) => {
    e.preventDefault();
    if (!password || password !== confirmPassword) {
      setError(password ? '兩次輸入的密碼不一致' : '請輸入新密碼');
      return;
    }
    try {
      setSaving(true);
      setError('');
      await adminService.resetPassword(user.id, password);
      onSaved(`已重設「${user.username}」的密碼，這個帳號在所有裝置都要以新密碼重新登入`);
    } catch (err) {
      setError(requestErrorMessage(err, '重設密碼失敗'));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog open onClose={saving ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogForm onSubmit={handleSave} noValidate>
        <DialogTitle onClose={onClose} closeDisabled={saving}>重設「{user.username}」的密碼</DialogTitle>
        <DialogContent>
          <div className={styles.editUserForm}>
            {error && <Alert severity="error">{error}</Alert>}
            <Alert severity="warning">重設後，這個帳號目前在所有裝置上的登入都會失效。</Alert>
            <TextField
              fullWidth
              label="新密碼"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              helperText={PASSWORD_HINT}
              autoComplete="new-password"
              disabled={saving}
              required
            />
            <TextField
              fullWidth
              label="確認新密碼"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              error={mismatch}
              helperText={mismatch ? '兩次輸入的密碼不一致' : undefined}
              autoComplete="new-password"
              disabled={saving}
              required
            />
          </div>
        </DialogContent>
        <DialogActions>
          <Button variant="secondary" onClick={onClose} disabled={saving}>取消</Button>
          <Button type="submit" variant="primary" loading={saving} startIcon={<Icon name="lock" size={16} />}>重設密碼</Button>
        </DialogActions>
      </DialogForm>
    </Dialog>
  );
}
