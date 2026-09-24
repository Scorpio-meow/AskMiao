import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import styles from './Snackbar.module.css';
export interface SnackbarProps {
  open: boolean;
  autoHideDuration?: number;
  onClose?: (event?: React.SyntheticEvent | Event, reason?: string) => void;
  message?: React.ReactNode;
  children?: React.ReactNode;
  anchorOrigin?: {
    vertical: 'top' | 'bottom';
    horizontal: 'left' | 'center' | 'right';
  };
  className?: string;
}
export const Snackbar: React.FC<SnackbarProps> = ({
  open,
  autoHideDuration = 4000,
  onClose,
  message,
  children,
  anchorOrigin = { vertical: 'bottom', horizontal: 'center' },
  className = '',
}) => {
  // 以 ref 保存 onClose，父層每次重新渲染都傳新函式時計時器才不會一直被重設
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });
  useEffect(() => {
    if (!open || !autoHideDuration) return;
    const timer = setTimeout(() => {
      onCloseRef.current?.(undefined, 'timeout');
    }, autoHideDuration);
    return () => clearTimeout(timer);
  }, [open, autoHideDuration, message]);
  if (!open) return null;
  const { vertical, horizontal } = anchorOrigin;
  const positionClass =
    vertical === 'top'
      ? horizontal === 'left'
        ? styles.topLeft
        : horizontal === 'right'
          ? styles.topRight
          : styles.topCenter
      : horizontal === 'left'
        ? styles.bottomLeft
        : horizontal === 'right'
          ? styles.bottomRight
          : styles.bottomCenter;
  return createPortal(
    <div className={`${styles.snackbar} ${positionClass} ${className}`}>
      {children || (
        <div className={styles.defaultMessage} role="status">
          {message}
        </div>
      )}
    </div>,
    document.body
  );
};
