import React, { useState } from 'react';
import { chatService, PendingToolApproval } from '../../services/api';
import { Button, Icon } from '../../components/ui';
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
  const [submitting, setSubmitting] = useState<'approve' | 'deny' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const entries = argumentEntries(approval.arguments);
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
        <Icon name="warning" size={16} className={styles.headerIcon} />
        <span>AI 想執行外部工具，需要你確認</span>
      </div>
      <dl className={styles.summary}>
        <div className={styles.summaryRow}>
          <dt>工具</dt>
          <dd className={styles.toolName}>{approval.tool_display_name}</dd>
        </div>
        <div className={styles.summaryRow}>
          <dt>送往</dt>
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
        此工具可能會修改外部系統的資料。請逐一確認上方每個參數與送出位置再核准；以 ⟦U+…⟧ 標示的是原本看不見的控制字元。未回應會在 5 分鐘後視為拒絕。
      </p>
      {error && <p className={styles.error} role="alert">{error}</p>}
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