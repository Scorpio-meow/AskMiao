import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useHeldWhileClosing, usePresence } from './usePresence';
import styles from './Snackbar.module.css';
export interface SnackbarProps {
  open: boolean;
  autoHideDuration?: number;
  onClose?: (event?: React.SyntheticEvent | Event, reason?: string) => void;
  children: React.ReactNode;
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
  children,
  anchorOrigin = { vertical: 'bottom', horizontal: 'center' },
  className = '',
}) => {
  const onCloseRef = useRef(onClose);
  const rootRef = useRef<HTMLDivElement>(null);
  const mounted = usePresence(open, rootRef);
  const content = useHeldWhileClosing(open, children);
  useEffect(() => {
    onCloseRef.current = onClose;
  });
  useEffect(() => {
    if (!open || !autoHideDuration) return;
    const timer = setTimeout(() => {
      onCloseRef.current?.(undefined, 'timeout');
    }, autoHideDuration);
    return () => clearTimeout(timer);
  }, [open, autoHideDuration]);
  if (!mounted) return null;
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
    <div
      ref={rootRef}
      className={`${styles.snackbar} ${positionClass} ${vertical === 'top' ? styles.fromTop : styles.fromBottom} ${className}`}
      data-state={open ? 'open' : 'closed'}
    >
      {content}
    </div>,
    document.body
  );
};