import React, { useState } from 'react';
import { chatService, PendingToolApproval } from '../../services/api';
import { Button, Icon } from '../../components/ui';
import styles from './ToolApprovalCard.module.css';

interface ToolApprovalCardProps {
  approval: PendingToolApproval;
}

// Agent 要呼叫會改變外部狀態的工具時暫停，由發問者確認工具與參數後才執行
const ToolApprovalCard: React.FC<ToolApprovalCardProps> = ({ approval }) => {
  const [submitting, setSubmitting] = useState<'approve' | 'deny' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decide = async (approved: boolean) => {
    setSubmitting(approved ? 'approve' : 'deny');
    setError(null);
    try {
      await chatService.resolveApproval(approval.approval_id, approved);
    } catch (err: any) {
      setError(err?.response?.data?.detail || '無法送出決定，可能已逾時');
      setSubmitting(null);
    }
  };

  return (
    <div className={styles.card} role="group" aria-label="工具執行確認">
      <div className={styles.header}>
        <Icon name="warning" size={16} />
        <span>AI 想執行外部工具，需要你確認</span>
      </div>
      <div className={styles.toolName}>{approval.tool_display_name}</div>
      <pre className={styles.arguments}>{JSON.stringify(approval.arguments ?? {}, null, 2)}</pre>
      <p className={styles.hint}>此工具可能會修改外部系統的資料。請確認參數無誤再核准；未回應會在 5 分鐘後視為拒絕。</p>
      {error && <p className={styles.error}>{error}</p>}
      <div className={styles.actions}>
        <Button size="sm" variant="outline" onClick={() => decide(false)} disabled={submitting !== null} loading={submitting === 'deny'}>
          拒絕
        </Button>
        <Button size="sm" onClick={() => decide(true)} disabled={submitting !== null} loading={submitting === 'approve'}>
          核准執行
        </Button>
      </div>
    </div>
  );
};

export default ToolApprovalCard;
