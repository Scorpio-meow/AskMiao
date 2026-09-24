import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import {
  TextField,
  Button,
  Alert,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  DialogForm,
  Icon
} from '../components/ui';
import styles from './ProfilePage.module.css';
const EMPTY_PASSWORD_FORM = {
  currentPassword: '',
  newPassword: '',
  confirmPassword: ''
};
const ProfilePage = () => {
  const navigate = useNavigate();
  const { user, logout, changePassword } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [dialogError, setDialogError] = useState('');
  const [mismatch, setMismatch] = useState(false);
  const [success, setSuccess] = useState('');
  const [passwordDialog, setPasswordDialog] = useState(false);
  const [passwordData, setPasswordData] = useState(EMPTY_PASSWORD_FORM);
  useDocumentTitle('個人資料');
  const openPasswordDialog = () => {
    setPasswordData(EMPTY_PASSWORD_FORM);
    setDialogError('');
    setMismatch(false);
    setPasswordDialog(true);
  };
  const closePasswordDialog = () => {
    setPasswordDialog(false);
  };
  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (!passwordData.currentPassword || !passwordData.newPassword || !passwordData.confirmPassword) {
      setDialogError('請填寫所有密碼欄位');
      return;
    }
    if (passwordData.newPassword !== passwordData.confirmPassword) {
      setMismatch(true);
      setDialogError('');
      return;
    }
    setSubmitting(true);
    setDialogError('');
    const result = await changePassword(
      passwordData.currentPassword,
      passwordData.newPassword,
      passwordData.confirmPassword
    );
    setSubmitting(false);
    if (result.success) {
      setSuccess('密碼修改成功');
      setPasswordDialog(false);
      setPasswordData(EMPTY_PASSWORD_FORM);
    } else {
      setDialogError(result.error || '修改密碼失敗');
    }
  };
  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };
  if (!user) {
    return (
      <div className={styles.container}>
        <Alert severity="error">無法載入使用者資料，請重新登入</Alert>
      </div>
    );
  }
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>
          <Icon name="person" size={28} />
          <span>個人資料</span>
        </h1>
        <p className={styles.subtitle}>管理您的帳號資訊和安全設定</p>
      </div>
      {success && (
        <Alert severity="success" style={{ marginBottom: '16px' }} onClose={() => setSuccess('')}>
          {success}
        </Alert>
      )}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>基本資訊</h2>
          {user.is_admin && (
            <Chip
              icon={<Icon name="admin" size={14} />}
              label="管理員"
              color="primary"
              size="sm"
            />
          )}
        </div>
        <dl className={styles.infoGrid}>
          <div className={styles.infoItem}>
            <dt className={styles.infoLabel}>使用者名稱</dt>
            <dd className={styles.infoValue}>{user.username}</dd>
          </div>
          <div className={styles.infoItem}>
            <dt className={styles.infoLabel}>電子郵件</dt>
            <dd className={styles.infoValue}>{user.email}</dd>
          </div>
          <div className={styles.infoItem}>
            <dt className={styles.infoLabel}>角色</dt>
            <dd className={styles.infoValue}>{user.role}</dd>
          </div>
          <div className={styles.infoItem}>
            <dt className={styles.infoLabel}>帳號狀態</dt>
            <dd>
              {user.is_active ? (
                <Chip label="已啟用" color="success" size="sm" />
              ) : (
                <Chip label="已停用" color="error" size="sm" />
              )}
            </dd>
          </div>
          <div className={styles.infoItem}>
            <dt className={styles.infoLabel}>註冊時間</dt>
            <dd className={styles.infoValue}>
              {new Date(user.created_at).toLocaleString('zh-TW')}
            </dd>
          </div>
          {user.last_login && (
            <div className={styles.infoItem}>
              <dt className={styles.infoLabel}>最後登入</dt>
              <dd className={styles.infoValue}>
                {new Date(user.last_login).toLocaleString('zh-TW')}
              </dd>
            </div>
          )}
        </dl>
      </div>
      <div className={styles.card}>
        <h2 className={styles.cardTitle} style={{ marginBottom: '16px' }}>
          <Icon name="lock" size={20} />
          <span>安全設定</span>
        </h2>
        <Button
          variant="outline"
          startIcon={<Icon name="lock" size={16} />}
          onClick={openPasswordDialog}
          fullWidth
        >
          修改密碼
        </Button>
      </div>
      <Button
        variant="danger"
        fullWidth
        onClick={handleLogout}
        size="lg"
      >
        登出
      </Button>
      <Dialog
        open={passwordDialog}
        onClose={submitting ? undefined : closePasswordDialog}
        maxWidth="sm"
        fullWidth
      >
        <DialogForm onSubmit={handleChangePassword} noValidate>
          <DialogTitle>修改密碼</DialogTitle>
          <DialogContent>
            <div className={styles.dialogForm}>
              {dialogError && (
                <Alert severity="error">{dialogError}</Alert>
              )}
              <TextField
                fullWidth
                label="目前的密碼"
                type="password"
                autoComplete="current-password"
                required
                value={passwordData.currentPassword}
                onChange={(e) =>
                  setPasswordData({ ...passwordData, currentPassword: e.target.value })
                }
                disabled={submitting}
              />
              <TextField
                fullWidth
                label="新密碼"
                type="password"
                autoComplete="new-password"
                required
                value={passwordData.newPassword}
                onChange={(e) => {
                  setPasswordData({ ...passwordData, newPassword: e.target.value });
                  setMismatch(false);
                }}
                helperText="至少 8 個字元，需包含大寫字母、小寫字母和數字"
                disabled={submitting}
              />
              <TextField
                fullWidth
                label="確認新密碼"
                type="password"
                autoComplete="new-password"
                required
                value={passwordData.confirmPassword}
                onChange={(e) => {
                  setPasswordData({ ...passwordData, confirmPassword: e.target.value });
                  setMismatch(false);
                }}
                error={mismatch}
                helperText={mismatch ? '兩次輸入的新密碼不一致' : undefined}
                disabled={submitting}
              />
            </div>
          </DialogContent>
          <DialogActions>
            <Button variant="secondary" onClick={closePasswordDialog} disabled={submitting}>
              取消
            </Button>
            <Button
              type="submit"
              variant="primary"
              loading={submitting}
            >
              確認修改
            </Button>
          </DialogActions>
        </DialogForm>
      </Dialog>
    </div>
  );
};
export default ProfilePage;
