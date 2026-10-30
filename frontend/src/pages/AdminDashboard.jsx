import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { describeRequestError } from '../utils/secureLogger';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { parseServerDate } from '../utils/serverDate';
import {
  Button,
  ConfirmDialog,
  Chip,
  Alert,
  Spinner,
  Icon
} from '../components/ui';
import SharedConnectionsCard from './Admin/SharedConnectionsCard';
import UsersCard from './Admin/UsersCard';
import styles from './AdminDashboard.module.css';
const cache = {
  statistics: { data: null, timestamp: 0 },
  users: { data: null, timestamp: 0 },
  documents: { data: null, timestamp: 0 }
};
const CACHE_TTL = 3 * 60 * 1000;
let loadingPromise = null;
const formatDate = (value) => parseServerDate(value).toLocaleDateString('zh-TW');
function AdminDashboard() {
  const { user: currentUser } = useAuth();
  const [statistics, setStatistics] = useState(null);
  const [users, setUsers] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pendingDelete, setPendingDelete] = useState(null);
  const [accessVersion, setAccessVersion] = useState(0);
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
  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 45000);
    setDeleting(true);
    try {
      await api.delete(`/documents/${pendingDelete.id}`, { signal: controller.signal });
      loadData(true);
    } catch (err) {
      if (err.name === 'AbortError' || err.name === 'CanceledError') {
        setError('刪除文件逾時，請稍後再試');
      } else {
        setError('刪除文件失敗：' + (err.response?.data?.detail || err.message));
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
      <UsersCard
        users={users}
        currentUserId={currentUser?.id}
        onUsersChanged={() => loadData(true)}
        onAccessChanged={() => setAccessVersion((version) => version + 1)}
      />
      <SharedConnectionsCard users={users} refreshKey={accessVersion} />
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
                      onClick={() => setPendingDelete(doc)}
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
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="刪除這份文件？"
        description={`文件「${pendingDelete?.filename}」會從知識庫移除，此操作無法復原。`}
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
