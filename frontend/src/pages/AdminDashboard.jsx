import { useState, useEffect, useRef, useCallback } from 'react';
import api, { llmConnectionService } from '../services/api';
import { useLlmProviders } from '../hooks/useLlmProviders';
import ConnectionFormDialog from '../components/LlmConnections/ConnectionFormDialog';
import ConnectionTestDialog from '../components/LlmConnections/ConnectionTestDialog';
import ConnectionList from '../components/LlmConnections/ConnectionList';
import { describeRequestError } from '../utils/secureLogger';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { parseServerDate } from '../utils/serverDate';
import {
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  DialogForm,
  ConfirmDialog,
  TextField,
  Switch,
  Chip,
  Alert,
  Spinner,
  Icon
} from '../components/ui';
import styles from './AdminDashboard.module.css';
const cache = {
  statistics: { data: null, timestamp: 0 },
  users: { data: null, timestamp: 0 },
  documents: { data: null, timestamp: 0 }
};
const CACHE_TTL = 3 * 60 * 1000;
let loadingPromise = null;
const formatDate = (value) => parseServerDate(value).toLocaleDateString('zh-TW');
function SharedConnectionsCard({ users }) {
  const providers = useLlmProviders();
  const [connections, setConnections] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editing, setEditing] = useState(null);
  const [testing, setTesting] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const load = useCallback(async () => {
    try {
      setError('');
      setConnections(await llmConnectionService.getShared());
    } catch (err) {
      setError('載入共用 API 連線失敗：' + (err.response?.data?.detail || err.message));
    }
  }, []);
  useEffect(() => {
    queueMicrotask(load);
  }, [load]);
  const describeAccess = (connection) => {
    if (connection.allowed_user_ids === null) return '可使用的帳號：所有帳號';
    const names = connection.allowed_user_ids
      .map((id) => users.find((user) => user.id === id)?.username)
      .filter(Boolean);
    return names.length > 0 ? `可使用的帳號：${names.join('、')}` : '可使用的帳號：無';
  };
  const handleSaved = (message) => {
    setEditing(null);
    setNotice(message);
    load();
  };
  const handleConfirmDelete = async () => {
    setDeleting(true);
    try {
      await llmConnectionService.removeShared(pendingDelete.id);
      setNotice(`已刪除「${pendingDelete.name}」`);
      load();
    } catch (err) {
      setError('刪除共用 API 連線失敗：' + (err.response?.data?.detail || err.message));
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  };
  return (
    <div className={styles.card}>
      <div className={styles.cardHeaderRow}>
        <h2 className={styles.cardTitle}>共用 API 連線</h2>
        <Button
          size="sm"
          variant="primary"
          startIcon={<Icon name="add" size={16} />}
          onClick={() => setEditing({ connection: null })}
          disabled={!providers?.length}
        >
          新增共用連線
        </Button>
      </div>
      <p className={styles.cardHint}>
        各帳號預設只能用自己在「個人資料」設定的 API，不會使用 .env 的金鑰。要讓某些帳號使用公司的金鑰或內部網路的模型（例如本機 Ollama），在這裡建立共用連線並指定可使用的帳號。
      </p>
      {notice && <Alert severity="success" onClose={() => setNotice('')} style={{ marginBottom: '16px' }}>{notice}</Alert>}
      {error && <Alert severity="error" onClose={() => setError('')} style={{ marginBottom: '16px' }}>{error}</Alert>}
      {connections === null && !error ? (
        <Spinner size={24} color="var(--color-primary)" />
      ) : connections?.length === 0 ? (
        <p className={styles.cardHint}>還沒有共用 API 連線。</p>
      ) : connections && (
        <ConnectionList
          connections={connections}
          providers={providers}
          label="共用 API 連線"
          describeAccess={describeAccess}
          onTest={setTesting}
          onEdit={(connection) => setEditing({ connection })}
          onDelete={setPendingDelete}
        />
      )}
      {editing && providers?.length > 0 && (
        <ConnectionFormDialog
          connection={editing.connection}
          shared
          providers={providers}
          users={users}
          publicOnly={false}
          onClose={() => setEditing(null)}
          onSaved={handleSaved}
        />
      )}
      {testing && <ConnectionTestDialog connection={testing} onClose={() => setTesting(null)} />}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="刪除這個共用 API 連線？"
        description={`「${pendingDelete?.name}」與其中儲存的金鑰會被刪除，所有帳號都無法再用它的模型對話。`}
        confirmLabel="刪除"
        destructive
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
function AdminDashboard() {
  const [statistics, setStatistics] = useState(null);
  const [users, setUsers] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editUserDialog, setEditUserDialog] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [savingUser, setSavingUser] = useState(false);
  const [dialogError, setDialogError] = useState('');
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const abortControllerRef = useRef(null);
  const isMountedRef = useRef(true);
  useDocumentTitle('管理後台');
  const loadData = useCallback(async (force = false) => {
    if (loadingPromise && !force) {
      return loadingPromise;
    }
    const now = Date.now();
    if (!force) {
      const statsValid = cache.statistics.data && (now - cache.statistics.timestamp) < CACHE_TTL;
      const usersValid = cache.users.data && (now - cache.users.timestamp) < CACHE_TTL;
      const docsValid = cache.documents.data && (now - cache.documents.timestamp) < CACHE_TTL;
      if (statsValid && usersValid && docsValid) {
        setStatistics(cache.statistics.data);
        setUsers(cache.users.data);
        setDocuments(cache.documents.data);
        setLoading(false);
        return;
      }
    }
    setLoading(true);
    setError('');
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();
    const timeoutId = setTimeout(() => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    }, 45000);
    loadingPromise = (async () => {
      try {
        const [statsResponse, usersResponse, docsResponse] = await Promise.all([
          api.get('/admin/statistics', { signal: abortControllerRef.current.signal }),
          api.get('/admin/users', { signal: abortControllerRef.current.signal }),
          api.get('/admin/documents', { signal: abortControllerRef.current.signal })
        ]);
        if (!isMountedRef.current) return;
        const timestamp = Date.now();
        cache.statistics = { data: statsResponse.data, timestamp };
        cache.users = { data: usersResponse.data, timestamp };
        cache.documents = { data: docsResponse.data, timestamp };
        setStatistics(statsResponse.data);
        setUsers(usersResponse.data);
        setDocuments(docsResponse.data);
      } catch (err) {
        if (!isMountedRef.current) return;
        if (err.name === 'AbortError' || err.name === 'CanceledError') {
          if (import.meta.env.DEV) console.debug('Admin data loading was cancelled', describeRequestError(err));
        } else {
          setError('載入資料失敗：' + (err.response?.data?.detail || err.message || '未知錯誤'));
        }
        console.error('Admin data loading error:', describeRequestError(err));
      } finally {
        clearTimeout(timeoutId);
        setLoading(false);
        loadingPromise = null;
      }
    })();
    return loadingPromise;
  }, []);
  useEffect(() => {
    isMountedRef.current = true;
    queueMicrotask(() => {
      loadData();
    });
    return () => {
      isMountedRef.current = false;
    };
  }, [loadData]);
  const handleEditUser = (user) => {
    setEditingUser({ ...user });
    setDialogError('');
    setEditUserDialog(true);
  };
  const handleSaveUser = async (e) => {
    e.preventDefault();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 45000);
    setSavingUser(true);
    setDialogError('');
    try {
      await api.put(`/admin/users/${editingUser.id}`, {
        username: editingUser.username,
        email: editingUser.email,
        is_active: editingUser.is_active,
        is_admin: editingUser.is_admin
      }, { signal: controller.signal });
      setEditUserDialog(false);
      loadData(true);
    } catch (err) {
      if (err.name === 'AbortError' || err.name === 'CanceledError') {
        setDialogError('更新使用者逾時，請稍後再試');
      } else {
        setDialogError('更新使用者失敗：' + (err.response?.data?.detail || err.message));
      }
      console.error('Update user error:', describeRequestError(err));
    } finally {
      clearTimeout(timeoutId);
      setSavingUser(false);
    }
  };
  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    const { type, item } = pendingDelete;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 45000);
    const subject = type === 'user' ? '使用者' : '文件';
    setDeleting(true);
    try {
      await api.delete(type === 'user' ? `/admin/users/${item.id}` : `/documents/${item.id}`, { signal: controller.signal });
      loadData(true);
    } catch (err) {
      if (err.name === 'AbortError' || err.name === 'CanceledError') {
        setError(`刪除${subject}逾時，請稍後再試`);
      } else {
        setError(`刪除${subject}失敗：` + (err.response?.data?.detail || err.message));
      }
      console.error('Delete error:', describeRequestError(err));
    } finally {
      clearTimeout(timeoutId);
      setDeleting(false);
      setPendingDelete(null);
    }
  };
  // 只有第一次載入時顯示整頁載入；之後重新整理保留目前內容與捲動位置
  if (loading && !statistics) {
    return (
      <div className={styles.loadingState}>
        <Spinner size={36} color="var(--color-primary)" />
      </div>
    );
  }
  return (
    <div className={styles.container}>
      <div className={styles.titleRow}>
        <h1 className={styles.title}>管理後台</h1>
        {loading && (
          <span className={styles.refreshing}>
            <Spinner size={16} color="var(--color-primary)" aria-hidden="true" />
            <span>更新中...</span>
          </span>
        )}
      </div>
      {error && (
        <Alert severity="error" style={{ marginBottom: '16px' }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      {/* 統計卡片 */}
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <div className={styles.statIcon}>
            <Icon name="people" size={24} />
          </div>
          <div>
            <div className={styles.statValue}>{statistics?.users?.total || 0}</div>
            <div className={styles.statLabel}>使用者總數</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}>
            <Icon name="chat" size={24} />
          </div>
          <div>
            <div className={styles.statValue}>{statistics?.conversations?.total || 0}</div>
            <div className={styles.statLabel}>對話總數</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}>
            <Icon name="description" size={24} />
          </div>
          <div>
            <div className={styles.statValue}>{statistics?.documents?.total || 0}</div>
            <div className={styles.statLabel}>文件數量</div>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statIcon}>
            <Icon name="speed" size={24} />
          </div>
          <div>
            <div className={styles.statValue}>{statistics?.messages?.recent_7_days || 0}</div>
            <div className={styles.statLabel}>近 7 天訊息</div>
          </div>
        </div>
      </div>
      {/* 使用者管理表格 */}
      <div className={styles.card}>
        <h2 className={styles.cardTitle} id="admin-users-title">使用者管理</h2>
        <div className={styles.tableWrapper}>
          <table className={styles.table} aria-labelledby="admin-users-title">
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">使用者名稱</th>
                <th scope="col">電子郵件</th>
                <th scope="col">狀態</th>
                <th scope="col">權限</th>
                <th scope="col">註冊時間</th>
                <th scope="col">操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.id}</td>
                  <td className={styles.wrapCell}>{user.username}</td>
                  <td className={styles.wrapCell}>{user.email}</td>
                  <td>
                    <Chip
                      label={user.is_active ? '已啟用' : '已停用'}
                      color={user.is_active ? 'success' : 'error'}
                      size="sm"
                    />
                  </td>
                  <td>
                    <Chip
                      label={user.is_admin ? '管理員' : '一般使用者'}
                      color={user.is_admin ? 'primary' : 'default'}
                      size="sm"
                    />
                  </td>
                  <td>
                    {formatDate(user.created_at)}
                  </td>
                  <td>
                    <div className={styles.tableActions}>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleEditUser(user)}
                      >
                        編輯<span className="sr-only">使用者 {user.username}</span>
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => setPendingDelete({ type: 'user', item: user })}
                      >
                        刪除<span className="sr-only">使用者 {user.username}</span>
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <SharedConnectionsCard users={users} />
      {/* 文件管理表格 */}
      <div className={styles.card}>
        <h2 className={styles.cardTitle} id="admin-documents-title">文件管理</h2>
        <div className={styles.tableWrapper}>
          <table className={styles.table} aria-labelledby="admin-documents-title">
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">檔案名稱</th>
                <th scope="col">類型</th>
                <th scope="col">狀態</th>
                <th scope="col">上傳時間</th>
                <th scope="col">操作</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.id}</td>
                  <td className={styles.wrapCell}>{doc.filename}</td>
                  <td className={styles.wrapCell}>{doc.file_type}</td>
                  <td>
                    <Chip
                      label={doc.is_processed ? '已處理' : '處理中'}
                      color={doc.is_processed ? 'success' : 'warning'}
                      size="sm"
                    />
                  </td>
                  <td>
                    {formatDate(doc.created_at)}
                  </td>
                  <td>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => setPendingDelete({ type: 'document', item: doc })}
                    >
                      刪除<span className="sr-only">文件 {doc.filename}</span>
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {/* 編輯使用者 Dialog */}
      <Dialog
        open={editUserDialog}
        onClose={savingUser ? undefined : () => setEditUserDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogForm onSubmit={handleSaveUser} noValidate>
          <DialogTitle>編輯使用者</DialogTitle>
          <DialogContent>
            {editingUser && (
              <div className={styles.editUserForm}>
                {dialogError && <Alert severity="error">{dialogError}</Alert>}
                <TextField
                  fullWidth
                  label="使用者名稱"
                  autoComplete="off"
                  value={editingUser.username}
                  onChange={(e) => setEditingUser({ ...editingUser, username: e.target.value })}
                  disabled={savingUser}
                />
                <TextField
                  fullWidth
                  label="電子郵件"
                  type="email"
                  autoComplete="off"
                  value={editingUser.email}
                  onChange={(e) => setEditingUser({ ...editingUser, email: e.target.value })}
                  disabled={savingUser}
                />
                <Switch
                  checked={editingUser.is_active}
                  onChange={(e) => setEditingUser({ ...editingUser, is_active: e.target.checked })}
                  label="帳號啟用"
                  disabled={savingUser}
                />
                <Switch
                  checked={editingUser.is_admin}
                  onChange={(e) => setEditingUser({ ...editingUser, is_admin: e.target.checked })}
                  label="管理員權限"
                  disabled={savingUser}
                />
              </div>
            )}
          </DialogContent>
          <DialogActions>
            <Button variant="secondary" onClick={() => setEditUserDialog(false)} disabled={savingUser}>
              取消
            </Button>
            <Button type="submit" variant="primary" loading={savingUser}>
              儲存
            </Button>
          </DialogActions>
        </DialogForm>
      </Dialog>
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={pendingDelete?.type === 'user' ? '刪除這位使用者？' : '刪除這份文件？'}
        description={
          pendingDelete?.type === 'user'
            ? `使用者「${pendingDelete?.item.username}」會被永久刪除，此操作無法復原。`
            : `文件「${pendingDelete?.item.filename}」會從知識庫移除，此操作無法復原。`
        }
        confirmLabel="刪除"
        destructive
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
export default AdminDashboard;
