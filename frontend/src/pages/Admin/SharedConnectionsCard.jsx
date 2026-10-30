import { useCallback, useEffect, useState } from 'react';
import { llmConnectionService } from '../../services/api';
import { useLlmProviders } from '../../hooks/useLlmProviders';
import ConnectionFormDialog from '../../components/LlmConnections/ConnectionFormDialog';
import ConnectionTestDialog from '../../components/LlmConnections/ConnectionTestDialog';
import ConnectionList from '../../components/LlmConnections/ConnectionList';
import { Alert, Button, ConfirmDialog, Icon, Spinner } from '../../components/ui';
import styles from '../AdminDashboard.module.css';
export default function SharedConnectionsCard({ users, refreshKey }) {
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
  }, [load, refreshKey]);
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
