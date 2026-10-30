import { useState } from 'react';
import { adminService } from '../../services/api';
import { parseServerDate } from '../../utils/serverDate';
import { Alert, Button, Chip, ConfirmDialog, Icon } from '../../components/ui';
import { requestErrorMessage } from '../../components/LlmConnections/requestErrorMessage';
import UserCreateDialog from './UserCreateDialog';
import UserEditDialog from './UserEditDialog';
import UserPasswordDialog from './UserPasswordDialog';
import styles from '../AdminDashboard.module.css';
const DATE_TIME_FORMAT = { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false };
const formatDate = (value) => parseServerDate(value).toLocaleDateString('zh-TW');
const formatDateTime = (value) => (value ? parseServerDate(value).toLocaleString('zh-TW', DATE_TIME_FORMAT) : '尚未登入');
export default function UsersCard({ users, currentUserId, onUsersChanged, onAccessChanged }) {
  const [query, setQuery] = useState('');
  const [dialog, setDialog] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const keyword = query.trim().toLowerCase();
  const visibleUsers = users.filter((user) => `${user.username} ${user.email}`.toLowerCase().includes(keyword));
  const handleSaved = (message, accessChanged) => {
    setDialog(null);
    setError('');
    setNotice(message);
    onUsersChanged();
    if (accessChanged) onAccessChanged();
  };
  const handleConfirmDelete = async () => {
    setDeleting(true);
    try {
      await adminService.deleteUser(pendingDelete.id);
      setNotice(`已刪除使用者「${pendingDelete.username}」`);
      onUsersChanged();
      onAccessChanged();
    } catch (err) {
      setError(requestErrorMessage(err, '刪除使用者失敗'));
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  };
  return (
    <div className={styles.card}>
      <div className={styles.cardHeaderRow}>
        <h2 className={styles.cardTitle} id="admin-users-title">使用者管理（{users.length}）</h2>
        <div className={styles.headerActions}>
          <input
            type="search"
            className={styles.searchInput}
            placeholder="搜尋使用者名稱或電子郵件"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="搜尋使用者"
          />
          <Button size="sm" variant="primary" startIcon={<Icon name="person-add" size={16} />} onClick={() => setDialog({ type: 'create' })}>
            新增使用者
          </Button>
        </div>
      </div>
      {notice && <Alert severity="success" onClose={() => setNotice('')} style={{ marginBottom: '16px' }}>{notice}</Alert>}
      {error && <Alert severity="error" onClose={() => setError('')} style={{ marginBottom: '16px' }}>{error}</Alert>}
      <div className={styles.tableWrapper}>
        <table className={styles.table} aria-labelledby="admin-users-title">
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">使用者名稱</th>
              <th scope="col">電子郵件</th>
              <th scope="col">狀態與權限</th>
              <th scope="col">註冊／最後登入</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <tbody>
            {visibleUsers.map((user) => {
              const isSelf = user.id === currentUserId;
              return (
                <tr key={user.id}>
                  <td>{user.id}</td>
                  <td className={styles.wrapCell}>
                    <span className={styles.nameCell}>
                      {user.username}
                      {isSelf && <Chip label="你" size="sm" color="info" />}
                    </span>
                  </td>
                  <td className={styles.wrapCell}>{user.email}</td>
                  <td>
                    <div className={styles.chipStack}>
                      <Chip label={user.is_active ? '已啟用' : '已停用'} color={user.is_active ? 'success' : 'error'} size="sm" />
                      <Chip label={user.is_admin ? '管理員' : '一般使用者'} color={user.is_admin ? 'primary' : 'default'} size="sm" />
                    </div>
                  </td>
                  <td>
                    <div className={styles.timeStack}>
                      <span>註冊 {formatDate(user.created_at)}</span>
                      <span>登入 {formatDateTime(user.last_login)}</span>
                    </div>
                  </td>
                  <td className={styles.actionsCell}>
                    <div className={styles.tableActions}>
                      <Button size="sm" variant="secondary" onClick={() => setDialog({ type: 'edit', user })}>
                        編輯<span className="sr-only">使用者 {user.username}</span>
                      </Button>
                      {!isSelf && (
                        <Button size="sm" variant="secondary" onClick={() => setDialog({ type: 'password', user })}>
                          重設密碼<span className="sr-only">使用者 {user.username}</span>
                        </Button>
                      )}
                      {!isSelf && (
                        <Button size="sm" variant="danger" onClick={() => setPendingDelete(user)}>
                          刪除<span className="sr-only">使用者 {user.username}</span>
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
            {visibleUsers.length === 0 && (
              <tr>
                <td colSpan={6} className={styles.emptyCell}>沒有符合的使用者</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {dialog?.type === 'create' && <UserCreateDialog onClose={() => setDialog(null)} onSaved={handleSaved} />}
      {dialog?.type === 'edit' && (
        <UserEditDialog user={dialog.user} isSelf={dialog.user.id === currentUserId} onClose={() => setDialog(null)} onSaved={handleSaved} />
      )}
      {dialog?.type === 'password' && <UserPasswordDialog user={dialog.user} onClose={() => setDialog(null)} onSaved={handleSaved} />}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="刪除這位使用者？"
        description={`使用者「${pendingDelete?.username}」的帳號、對話與個人 API 連線會被永久刪除，此操作無法復原。`}
        confirmLabel="刪除"
        destructive
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
