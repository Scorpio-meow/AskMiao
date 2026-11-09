import React, { useState } from 'react';
import { chatService, PendingQuestion } from '../../services/api';
import { Button, Icon, TextField } from '../../components/ui';
import styles from './QuestionCard.module.css';
interface QuestionCardProps {
  question: PendingQuestion;
}
const QuestionCard: React.FC<QuestionCardProps> = ({ question }) => {
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const send = async (value: string) => {
    const answer = value.trim();
    if (!answer || sending !== null) return;
    setSending(answer);
    setError(null);
    try {
      await chatService.answerQuestion(question.question_id, answer);
    } catch (err: any) {
      setError(err?.response?.data?.detail || '無法送出回答，可能已逾時');
      setSending(null);
    }
  };
  const hasOptions = question.options.length > 0;
  return (
    <div className={styles.card} role="group" aria-label="研究助理的提問">
      <div className={styles.header}>
        <Icon name="help" size={16} className={styles.headerIcon} />
        <span>需要你的回答</span>
      </div>
      <p className={styles.question}>{question.question}</p>
      {hasOptions && (
        <div className={styles.options}>
          {question.options.map((option) => (
            <Button
              key={option}
              size="sm"
              variant="outline"
              onClick={() => send(option)}
              disabled={sending !== null}
              loading={sending === option}
            >
              {option}
            </Button>
          ))}
        </div>
      )}
      <form
        className={styles.custom}
        onSubmit={(event) => {
          event.preventDefault();
          send(draft);
        }}
      >
        <TextField
          fullWidth
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={hasOptions ? '或輸入其他回答' : '輸入回答'}
          aria-label="輸入回答"
          disabled={sending !== null}
        />
        <Button size="sm" type="submit" disabled={sending !== null || !draft.trim()} loading={sending !== null && sending === draft.trim()}>
          送出
        </Button>
      </form>
      <p className={styles.hint}>請勿在回答中提供密碼、金鑰等機密。5 分鐘內沒有回答，研究助理會依現有資訊自行判斷並說明假設。</p>
      {error && <p className={styles.error} role="alert">{error}</p>}
    </div>
  );
};
export default QuestionCard;