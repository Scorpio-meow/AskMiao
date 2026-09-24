import React from 'react';
import styles from './Collapse.module.css';
export interface CollapseProps {
  in: boolean;
  children: React.ReactNode;
  className?: string;
  /** 供觸發按鈕的 aria-controls 使用 */
  id?: string;
}
export const Collapse: React.FC<CollapseProps> = ({ in: isOpen, children, className = '', id }) => {
  return (
    <div
      id={id}
      className={`${styles.collapseContainer} ${isOpen ? styles.collapseExpanded : ''} ${className}`}
    >
      {/* 收合時設為 inert，內容不會被 Tab 或螢幕報讀器讀到 */}
      <div className={styles.collapseInner} inert={!isOpen}>
        {children}
      </div>
    </div>
  );
};
