import React, { useEffect, useState } from 'react';
import { chatService, ConversationFile } from '../../services/api';
import { describeRequestError } from '../../utils/secureLogger';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Spinner } from '../../components/ui';
import ConversationFileCard, { FileCardInfo } from './ConversationFileCard';
import { formatMessageTime } from './chatFormat';
import styles from './ConversationFilesDialog.module.css';
interface ConversationFilesDialogProps {
  conversationId: number;
  deletedFileIds: ReadonlySet<number>;
  onClose: () => void;
  onDownload: (file: FileCardInfo) => void;
  onDelete: (file: FileCardInfo) => void;
}
const ORIGIN_LABELS: Record<ConversationFile['origin'], string> = {
  user: '你上傳',
  assistant: '研究助理建立',
};
export const ConversationFilesDialog: React.FC<ConversationFilesDialogProps> = ({
  conversationId,
  deletedFileIds,
  onClose,
  onDownload,
  onDelete,
}) => {
  const [files, setFiles] = useState<ConversationFile[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    chatService.listConversationFiles(conversationId)
      .then((list) => {
        if (active) setFiles(list);
      })
      .catch((err) => {
        console.warn('載入對話檔案失敗', describeRequestError(err));
        if (active) setError('無法載入這個對話的檔案，請稍後再試');
      });
    return () => {
      active = false;
    };
  }, [conversationId]);
  const visible = (files || []).filter((file) => !deletedFileIds.has(file.id));
  const now = new Date();
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle subtitle="你上傳的文件與研究助理建立的檔案；修改會另存新版本，原檔保留" onClose={onClose}>
        對話檔案
      </DialogTitle>
      <DialogContent>
        {error && <Alert severity="error">{error}</Alert>}
        {!error && files === null && (
          <div className={styles.loading}>
            <Spinner size={18} color="var(--color-primary)" />
            <span>載入中…</span>
          </div>
        )}
        {files !== null && visible.length === 0 && <p className={styles.empty}>這個對話還沒有檔案。</p>}
        {visible.length > 0 && (
          <ul className={styles.list} role="list">
            {visible.map((file) => {
              const created = file.created_at ? formatMessageTime(file.created_at, now) : null;
              return (
                <li key={file.id} className={styles.item}>
                  <ConversationFileCard file={file} deleted={false} onDownload={onDownload} onDelete={onDelete} />
                  <span className={styles.details}>
                    #{file.id}
                    {file.version > 1 ? ` · 第 ${file.version} 版` : ''}
                    {` · ${ORIGIN_LABELS[file.origin]}`}
                    {created ? ` · ${created.label}` : ''}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </DialogContent>
      <DialogActions>
        <Button variant="secondary" onClick={onClose}>關閉</Button>
      </DialogActions>
    </Dialog>
  );
};
export default ConversationFilesDialog;