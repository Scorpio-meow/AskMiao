import React, { useState } from 'react';
import { chatService, PendingToolApproval } from '../../services/api';
import { Button, Icon } from '../../components/ui';
import { approvalHeadline } from './chatFormat';
import styles from './ToolApprovalCard.module.css';
interface ToolApprovalCardProps {
  approval: PendingToolApproval;
}
const HIDDEN_CHARACTERS = /(?![\t\n\r])[\p{Cc}\p{Cf}]/gu;
const codePointLabel = (char: string): string =>
  `⟦U+${(char.codePointAt(0) as number).toString(16).toUpperCase().padStart(4, '0')}⟧`;
const revealHiddenCharacters = (text: string): string => text.replace(HIDDEN_CHARACTERS, codePointLabel);
const formatValue = (value: unknown): string =>
  revealHiddenCharacters(typeof value === 'string' ? value : JSON.stringify(value, null, 2));
const argumentEntries = (args: PendingToolApproval['arguments']): Array<[string, unknown]> => {
  if (args === undefined || args === null) return [];
  if (typeof args === 'object' && !Array.isArray(args)) return Object.entries(args);
  return [['（參數）', args]];
};
const ToolApprovalCard: React.FC<ToolApprovalCardProps> = ({ approval }) => {
  const [submitting, setSubmitting] = useState<'approve' | 'remember' | 'deny' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const entries = argumentEntries(approval.arguments);
  const isFile = approval.kind === 'file';
  const decide = async (approved: boolean, remember: boolean) => {
    setSubmitting(remember ? 'remember' : approved ? 'approve' : 'deny');
    setError(null);
    try {
      await chatService.resolveApproval(approval.approval_id, approved, remember);
    } catch (err: any) {
      setError(err?.response?.data?.detail || '無法送出決定，可能已逾時');
      setSubmitting(null);
    }
  };
  return (
    <div className={styles.card} role="group" aria-label="工具執行確認">
      <div className={styles.header}>
        <Icon name="warning" size={16} className={styles.headerIcon} />
        <span>{approvalHeadline(approval)}</span>
      </div>
      <dl className={styles.summary}>
        <div className={styles.summaryRow}>
          <dt>工具</dt>
          <dd className={styles.toolName}>{approval.tool_display_name}</dd>
        </div>
        <div className={styles.summaryRow}>
          <dt>{isFile ? '檔案' : '送往'}</dt>
          <dd><code className={styles.target}>{approval.target}</code></dd>
        </div>
      </dl>
      <div className={styles.argumentsSection}>
        <p className={styles.sectionLabel}>參數</p>
        {entries.length === 0 ? (
          <p className={styles.noArguments}>（沒有參數）</p>
        ) : (
          <dl className={styles.arguments}>
            {entries.map(([name, value]) => (
              <div key={name} className={styles.argument}>
                <dt>{revealHiddenCharacters(name)}</dt>
                <dd>{formatValue(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      <p className={styles.hint}>
        {isFile
          ? '核准後這個檔案會永久刪除，無法復原。未回應會在 5 分鐘後視為拒絕。'
          : '此工具可能會修改外部系統的資料。請逐一確認上方每個參數與送出位置再核准；以 ⟦U+…⟧ 標示的是原本看不見的控制字元。選「這次提問都允許」時，這次回答中再呼叫同一個工具就不再詢問。未回應會在 5 分鐘後視為拒絕。'}
      </p>
      {error && <p className={styles.error} role="alert">{error}</p>}
      <div className={styles.actions}>
        <Button size="sm" variant="outline" onClick={() => decide(false, false)} disabled={submitting !== null} loading={submitting === 'deny'}>
          拒絕
        </Button>
        {!isFile && (
          <Button size="sm" variant="outline" onClick={() => decide(true, true)} disabled={submitting !== null} loading={submitting === 'remember'}>
            這次提問都允許
          </Button>
        )}
        <Button size="sm" onClick={() => decide(true, false)} disabled={submitting !== null} loading={submitting === 'approve'}>
          核准執行
        </Button>
      </div>
    </div>
  );
};
export default ToolApprovalCard;