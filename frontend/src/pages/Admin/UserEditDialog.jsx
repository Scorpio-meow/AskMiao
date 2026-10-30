import { useEffect, useState } from 'react';
import { adminService } from '../../services/api';
import { Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogForm, DialogTitle, Icon, Spinner, Switch, TextField } from '../../components/ui';
import { requestErrorMessage } from '../../components/LlmConnections/requestErrorMessage';
import formStyles from '../../components/LlmConnections/LlmConnections.module.css';
import styles from '../AdminDashboard.module.css';
const allowedRestrictedIds = (access) => new Set(access.shared.filter((c) => !c.all_users && c.allowed).map((c) => c.id));
const sameIds = (a, b) => a.size === b.size && [...a].every((id) => b.has(id));
export default function UserEditDialog({ user, isSelf, onClose, onSaved }) {
  const [form, setForm] = useState({
    username: user.username,
    email: user.email,
    is_active: user.is_active,
    is_admin: user.is_admin,
  });
  const [access, setAccess] = useState(null);
  const [accessError, setAccessError] = useState('');
  const [allowed, setAllowed] = useState(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    adminService.getUserConnections(user.id)
      .then((data) => {
        if (!active) return;
        setAccess(data);
        setAllowed(allowedRestrictedIds(data));
      })
      .catch((err) => {
        if (active) setAccessError(requestErrorMessage(err, '無法載入這個帳號的 API 連線'));
      });
    return () => {
      active = false;
    };
  }, [user.id]);
  const update = (changes) => setForm((prev) => ({ ...prev, ...changes }));
  const toggleConnection = (connectionId) => setAllowed((prev) => {
    const next = new Set(prev);
    if (next.has(connectionId)) next.delete(connectionId);
    else next.add(connectionId);
    return next;
  });
  const handleSave = async (e) => {
    e.preventDefault();
    const accessChanged = access !== null && !sameIds(allowed, allowedRestrictedIds(access));
    try {
      setSaving(true);
      setError('');
      await adminService.updateUser(user.id, form);
      if (accessChanged) {
        await adminService.updateUserConnections(user.id, [...allowed]);
      }
      onSaved(`已更新「${form.username}」`, accessChanged);
    } catch (err) {
      setError(requestErrorMessage(err, '更新使用者失敗'));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog open onClose={saving ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogForm onSubmit={handleSave} noValidate>
        <DialogTitle onClose={onClose} closeDisabled={saving}>編輯使用者</DialogTitle>
        <DialogContent>
          <div className={styles.editUserForm}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              fullWidth
              label="使用者名稱"
              autoComplete="off"
              value={form.username}
              onChange={(e) => update({ username: e.target.value })}
              helperText="3–50 個字元，只能包含中文、英文字母、數字、底線（_）與連字號（-）"
              disabled={saving}
            />
            <TextField
              fullWidth
              label="電子郵件"
              type="email"
              autoComplete="off"
              value={form.email}
              onChange={(e) => update({ email: e.target.value })}
              disabled={saving}
            />
            <Switch
              checked={form.is_active}
              onChange={(e) => update({ is_active: e.target.checked })}
              label="帳號啟用"
              disabled={saving || isSelf}
            />
            <Switch
              checked={form.is_admin}
              onChange={(e) => update({ is_admin: e.target.checked })}
              label="管理員權限"
              disabled={saving || isSelf}
            />
            {isSelf && <p className={styles.cardHint}>不能停用自己的帳號或移除自己的管理員權限，以免沒有人能管理系統。</p>}
            <fieldset className={formStyles.fieldset}>
              <legend className={formStyles.label}>可使用的共用 API 連線</legend>
              {accessError && <Alert severity="error">{accessError}</Alert>}
              {access === null && !accessError && <Spinner size={20} color="var(--color-primary)" />}
              {access?.shared.length === 0 && (
                <p className={styles.cardHint}>還沒有共用 API 連線，可在「共用 API 連線」新增。</p>
              )}
              {access?.shared.length > 0 && (
                <ul className={formStyles.userList} role="list" aria-label="共用 API 連線">
                  {access.shared.map((connection) => (
                    <li key={connection.id} className={formStyles.userItem}>
                      <label className={formStyles.option}>
                        <input
                          type="checkbox"
                          checked={connection.all_users || allowed.has(connection.id)}
                          onChange={() => toggleConnection(connection.id)}
                          disabled={saving || connection.all_users}
                        />
                        <span>
                          {connection.name}
                          <span className={formStyles.hint}>
                            {connection.all_users ? '開放給所有帳號；要限定帳號請到「共用 API 連線」編輯' : connection.models.join('、')}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </fieldset>
            {access && (
              <div className={formStyles.field}>
                <span className={formStyles.label}>這個帳號自己設定的 API 連線</span>
                {access.personal.length === 0 ? (
                  <p className={styles.cardHint}>沒有。個人連線只能由帳號本人在「個人資料」管理。</p>
                ) : (
                  <div className={formStyles.models}>
                    {access.personal.map((connection) => (
                      <Chip key={connection.id} label={`${connection.name}（${connection.models.length} 個模型）`} size="sm" />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </DialogContent>
        <DialogActions>
          <Button variant="secondary" onClick={onClose} disabled={saving}>取消</Button>
          <Button type="submit" variant="primary" loading={saving} startIcon={<Icon name="save" size={16} />}>儲存</Button>
        </DialogActions>
      </DialogForm>
    </Dialog>
  );
}
