import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useLlmProviders } from '../hooks/useLlmProviders';
import { llmConnectionService } from '../services/api';
import ConnectionFormDialog from '../components/LlmConnections/ConnectionFormDialog';
import ConnectionTestDialog from '../components/LlmConnections/ConnectionTestDialog';
import ConnectionList from '../components/LlmConnections/ConnectionList';
import { LOGOUT_UNCONFIRMED_NOTICE } from '../services/authService';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { parseServerDate } from '../utils/serverDate';
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
  ConfirmDialog,
  Spinner,
  Icon
} from '../components/ui';
import styles from './ProfilePage.module.css';
const EMPTY_PASSWORD_FORM = {
  currentPassword: '',
  newPassword: '',
  confirmPassword: ''
};
const LlmConnectionsCard = ({ isAdmin }) => {
  const providers = useLlmProviders();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [notice, setNotice] = useState('');
  const [editing, setEditing] = useState(null);
  const [testing, setTesting] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const load = useCallback(async () => {
    try {
      setLoadError('');
      setData(await llmConnectionService.getMine());
    } catch {
      setLoadError('無法載入 API 連線，請稍後再試');
    }
  }, []);
  useEffect(() => {
    queueMicrotask(load);
  }, [load]);
  const handleSaved = (message) => {
    setEditing(null);
    setNotice(message);
    load();
  };
  const handleConfirmDelete = async () => {
    setDeleting(true);
    try {
      await llmConnectionService.remove(pendingDelete.id);
      setNotice(`已刪除「${pendingDelete.name}」`);
      load();
    } catch (err) {
      setLoadError(err?.response?.data?.detail || '刪除失敗，請稍後再試');
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  };
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <h2 className={styles.cardTitle}>
          <Icon name="key" size={20} />
          <span>我的 API 連線</span>
        </h2>
        <Button
          size="sm"
          variant="primary"
          startIcon={<Icon name="add" size={16} />}
          onClick={() => setEditing({ connection: null })}
          disabled={!providers?.length}
        >
          新增
        </Button>
      </div>
      <p className={styles.sectionHint}>
        對話時使用你自己的 API 金鑰與模型，其他帳號看不到也用不到。金鑰加密存放，儲存後不會再顯示。
      </p>
      {notice && <Alert severity="success" onClose={() => setNotice('')} style={{ marginBottom: '16px' }}>{notice}</Alert>}
      {loadError && <Alert severity="error" style={{ marginBottom: '16px' }}>{loadError}</Alert>}
      {data === null && !loadError ? (
        <Spinner size={24} color="var(--color-primary)" />
      ) : data && (
        <>
          {data.personal.length === 0 ? (
            <p className={styles.sectionHint}>還沒有個人 API 連線。</p>
          ) : (
            <ConnectionList
              connections={data.personal}
              providers={providers}
              label="我的 API 連線"
              onTest={setTesting}
              onEdit={(connection) => setEditing({ connection })}
              onDelete={setPendingDelete}
            />
          )}
          <h3 className={styles.sectionTitle}>管理員開放給你的共用連線</h3>
          {data.shared.length === 0 ? (
            <p className={styles.sectionHint}>目前沒有。</p>
          ) : (
            <ConnectionList connections={data.shared} providers={providers} label="共用 API 連線" />
          )}
        </>
      )}
      {editing && providers?.length > 0 && (
        <ConnectionFormDialog
          connection={editing.connection}
          shared={false}
          providers={providers}
          publicOnly={!isAdmin}
          onClose={() => setEditing(null)}
          onSaved={handleSaved}
        />
      )}
      {testing && <ConnectionTestDialog connection={testing} onClose={() => setTesting(null)} />}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="刪除這個 API 連線？"
        description={`「${pendingDelete?.name}」與其中儲存的金鑰會被刪除，之後無法再用它的模型對話。`}
        confirmLabel="刪除"
        destructive
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
};
const ProfilePage = () => {
  const navigate = useNavigate();
  const { user, logout, changePassword } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [dialogError, setDialogError] = useState('');
  const [mismatch, setMismatch] = useState(false);
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
      // 變更密碼會讓所有裝置的登入失效，包含目前這一個
      navigate('/login', { replace: true, state: { notice: { message: '密碼已變更，請以新密碼重新登入', severity: 'info' } } });
    } else {
      setDialogError(result.error || '修改密碼失敗');
    }
  };
  const handleLogout = async () => {
    const confirmed = await logout();
    navigate('/login', { replace: true, state: confirmed ? null : { notice: LOGOUT_UNCONFIRMED_NOTICE } });
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
              {parseServerDate(user.created_at).toLocaleString('zh-TW')}
            </dd>
          </div>
          {user.last_login && (
            <div className={styles.infoItem}>
              <dt className={styles.infoLabel}>最後登入</dt>
              <dd className={styles.infoValue}>
                {parseServerDate(user.last_login).toLocaleString('zh-TW')}
              </dd>
            </div>
          )}
        </dl>
      </div>
      <LlmConnectionsCard isAdmin={user.is_admin} />
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
