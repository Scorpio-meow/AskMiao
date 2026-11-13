import React from 'react';
import styles from './Collapse.module.css';
export interface CollapseProps {
  in: boolean;
  children: React.ReactNode;
  className?: string;
  id?: string;
}
export const Collapse: React.FC<CollapseProps> = ({ in: isOpen, children, className = '', id }) => {
  return (
    <div
      id={id}
      className={`${styles.collapseContainer} ${isOpen ? styles.collapseExpanded : ''} ${className}`}
    >
      <div className={styles.collapseInner} inert={!isOpen}>
        {children}
      </div>
    </div>
  );
};