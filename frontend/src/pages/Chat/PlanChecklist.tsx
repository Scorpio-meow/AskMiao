import React from 'react';
import { PlanItem } from '../../services/api';
import { Icon, Spinner } from '../../components/ui';
import styles from './PlanChecklist.module.css';
export interface PlanChecklistProps {
  plan: PlanItem[];
  isStreaming?: boolean;
}
const STATUS_LABELS: Record<PlanItem['status'], string> = {
  pending: '尚未開始',
  in_progress: '進行中',
  completed: '已完成',
};
const PlanMarker: React.FC<{ status: PlanItem['status']; isStreaming: boolean }> = ({ status, isStreaming }) => {
  if (status === 'completed') return <Icon name="check-circle" size={16} />;
  if (status === 'in_progress' && isStreaming) return <Spinner size={14} color="var(--color-primary)" aria-hidden="true" />;
  return <span className={status === 'in_progress' ? styles.dotActive : styles.dot} />;
};
export const PlanChecklist: React.FC<PlanChecklistProps> = ({ plan, isStreaming = false }) => {
  const completed = plan.filter((item) => item.status === 'completed').length;
  return (
    <section className={styles.container} aria-label="任務計畫">
      <div className={styles.header}>
        <Icon name="timeline" size={16} className={styles.headerIcon} />
        <span className={styles.title}>計畫</span>
        <span className={styles.progress}>
          {completed}/{plan.length}
          <span className="sr-only"> 步已完成</span>
        </span>
      </div>
      <ol className={styles.list}>
        {plan.map((item, index) => (
          <li key={index} className={`${styles.item} ${styles[item.status]}`}>
            <span className={styles.marker} aria-hidden="true">
              <PlanMarker status={item.status} isStreaming={isStreaming} />
            </span>
            <span className={styles.step}>{item.step}</span>
            <span className="sr-only">（{STATUS_LABELS[item.status]}）</span>
          </li>
        ))}
      </ol>
    </section>
  );
};
export default PlanChecklist;