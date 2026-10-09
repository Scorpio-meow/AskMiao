import React, { useState } from 'react';
import { chatService, PendingToolApproval } from '../../services/api';
import { Button, Icon } from '../../components/ui';
import styles from './ToolApprovalCard.module.css';

interface ToolApprovalCardProps {
  approval: PendingToolApproval;
}

// 控制字元（保留換行與 Tab）與格式字元（雙向文字控制、零寬字元、Unicode 標籤字元等）看不見，
// 會讓參數看起來和實際送出的不同，例如反轉或藏起部分電子郵件地址，或夾帶看不見的文字
const HIDDEN_CHARACTERS = /(?![\t\n\r])[\p{Cc}\p{Cf}]/gu;

const codePointLabel = (char: string): string =>
  `⟦U+${(char.codePointAt(0) as number).toString(16).toUpperCase().padStart(4, '0')}⟧`;

const revealHiddenCharacters = (text: string): string => text.replace(HIDDEN_CHARACTERS, codePointLabel);

const formatValue = (value: unknown): string =>
  revealHiddenCharacters(typeof value === 'string' ? value : JSON.stringify(value, null, 2));

// 模型給的參數通常是物件；其他型別整個當成一個值顯示
const argumentEntries = (args: PendingToolApproval['arguments']): Array<[string, unknown]> => {
  if (args === undefined || args === null) return [];
  if (typeof args === 'object' && !Array.isArray(args)) return Object.entries(args);
  return [['（參數）', args]];
};

// Agent 要呼叫會改變外部狀態的工具時暫停，由發問者確認工具、送出位置與完整參數後才執行
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
        <Icon name="warning" size={16} />
        <span>AI 想執行外部工具，需要你確認</span>
      </div>
      <div className={styles.toolName}>{approval.tool_display_name}</div>
      <div className={styles.target}>
        送往：<code>{approval.target}</code>
      </div>
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
      <p className={styles.hint}>
        此工具可能會修改外部系統的資料。請逐一確認上方每個參數與送出位置再核准；以 ⟦U+…⟧ 標示的是原本看不見的控制字元。未回應會在 5 分鐘後視為拒絕。
      </p>
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
