import React from 'react';
import { describeAttachmentType, formatFileSize } from './chatFormat';
import { Icon, IconButton, Tooltip } from '../../components/ui';
import type { ConversationFileEvent } from '../../services/api';
import styles from './ConversationFileCard.module.css';
export interface FileCardInfo {
  id: number;
  filename: string;
  size_bytes?: number;
}
const ACTION_LABELS: Record<ConversationFileEvent['action'], string> = {
  created: '已建立',
  updated: '已存成新版本',
  deleted: '已刪除',
};
interface ConversationFileCardProps {
  file: FileCardInfo;
  action?: ConversationFileEvent['action'];
  deleted: boolean;
  onDownload?: (file: FileCardInfo) => void;
  onDelete?: (file: FileCardInfo) => void;
}
export const ConversationFileCard: React.FC<ConversationFileCardProps> = ({ file, action, deleted, onDownload, onDelete }) => {
  const status = deleted ? '已刪除' : action ? ACTION_LABELS[action] : '';
  const size = deleted ? '' : formatFileSize(file.size_bytes);
  const meta = [status, size].filter(Boolean).join(' · ');
  return (
    <div className={`${styles.card} ${deleted ? styles.deleted : ''}`}>
      <span className={styles.badge}>{describeAttachmentType(file.filename).label}</span>
      <span className={styles.name}>{file.filename}</span>
      {meta && <span className={styles.meta}>{meta}</span>}
      {!deleted && onDownload && (
        <Tooltip title="下載">
          <IconButton size="sm" onClick={() => onDownload(file)} aria-label={`下載 ${file.filename}`}>
            <Icon name="download" size={14} />
          </IconButton>
        </Tooltip>
      )}
      {!deleted && onDelete && (
        <Tooltip title="刪除">
          <IconButton size="sm" onClick={() => onDelete(file)} aria-label={`刪除 ${file.filename}`}>
            <Icon name="delete" size={14} />
          </IconButton>
        </Tooltip>
      )}
    </div>
  );
};
export default ConversationFileCard;