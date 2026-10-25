import { useEffect, useState } from 'react';
import { adminService, skillService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Icon, Spinner } from '../../components/ui';
import { getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
export default function SkillAccessDialog({ skill, onClose, onSaved }) {
  const [users, setUsers] = useState(null);
  const [restricted, setRestricted] = useState(skill.allowed_user_ids !== null);
  const [selected, setSelected] = useState(() => new Set(skill.allowed_user_ids || []));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    adminService.getUsers()
      .then((list) => {
        if (!cancelled) setUsers(list);
      })
      .catch((err) => {
        if (!cancelled) setError(getRequestErrorMessage(err, '載入使用者清單失敗'));
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const toggle = (userId) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(userId)) next.delete(userId);
    else next.add(userId);
    return next;
  });
  const handleSave = async () => {
    if (restricted && selected.size === 0) {
      setError('限定使用者時至少要選擇一位使用者');
      return;
    }
    try {
      setSaving(true);
      setError('');
      await skillService.updateSkillSettings(skill.id, { allowed_user_ids: restricted ? [...selected] : [] });
      onSaved(`已更新技能「${skill.name}」的使用者範圍`);
    } catch (err) {
      setError(getRequestErrorMessage(err, '更新使用者範圍失敗'));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog open onClose={saving ? undefined : onClose} maxWidth="md">
      <DialogTitle onClose={onClose} closeDisabled={saving}>可使用「{skill.name}」的使用者</DialogTitle>
      <DialogContent className={styles.dialogBody}>
        {error && <Alert severity="error">{error}</Alert>}
        <fieldset className={styles.formFieldset}>
          <legend className={styles.formLabel}>使用者範圍</legend>
          <label className={styles.approvalOption}>
            <input type="radio" name="skill-access" checked={!restricted} onChange={() => setRestricted(false)} />
            <span>所有使用者</span>
          </label>
          <label className={styles.approvalOption}>
            <input type="radio" name="skill-access" checked={restricted} onChange={() => setRestricted(true)} />
            <span>
              只限下列使用者
              <span className={styles.approvalHint}>其他使用者的 AI 看不到這個技能，也無法用 /{skill.name} 指定</span>
            </span>
          </label>
        </fieldset>
        {restricted && (
          users === null && !error ? <Spinner /> : (
            <ul className={styles.mcpToolList} role="list" aria-label="使用者">
              {(users || []).map((user) => (
                <li key={user.id} className={styles.mcpToolItem}>
                  <label className={styles.approvalOption}>
                    <input type="checkbox" checked={selected.has(user.id)} onChange={() => toggle(user.id)} />
                    <span>
                      {user.username}
                      <span className={styles.approvalHint}>{user.email}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )
        )}
      </DialogContent>
      <DialogActions>
        <Button variant="secondary" onClick={onClose} disabled={saving}>
          取消
        </Button>
        <Button variant="primary" onClick={handleSave} loading={saving} startIcon={<Icon name="save" size={16} />}>
          儲存
        </Button>
      </DialogActions>
    </Dialog>
  );
}
