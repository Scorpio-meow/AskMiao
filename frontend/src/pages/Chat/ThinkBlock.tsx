import React, { useId } from 'react';
import { ThinkBlockProps } from './types';
import { Icon, Collapse } from '../../components/ui';
import styles from './ThinkBlock.module.css';
export const ThinkBlock: React.FC<ThinkBlockProps> = ({
  thinkContent,
  isOpen,
  onToggle,
}) => {
  const bodyId = useId();
  if (!thinkContent) return null;
  return (
    <div className={styles.container}>
      <button
        type="button"
        className={styles.header}
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-controls={bodyId}
      >
        <span className={styles.titleArea}>
          <Icon name="lightbulb" size={18} />
          <span>思考與推論過程</span>
        </span>
        <span className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`} aria-hidden="true">
          <Icon name="expand-more" size={16} />
        </span>
      </button>
      <Collapse in={isOpen} id={bodyId}>
        <div className={styles.body}>
          <pre className={styles.text}>{thinkContent}</pre>
        </div>
      </Collapse>
    </div>
  );
};
export default ThinkBlock;
