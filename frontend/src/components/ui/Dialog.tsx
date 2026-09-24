import React, { createContext, useContext, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useModalDialog } from './useModalDialog';
import { IconButton } from './IconButton';
import { Icon } from './Icon';
import styles from './Dialog.module.css';
const DialogTitleIdContext = createContext<string | undefined>(undefined);
export interface DialogProps {
  open: boolean;
  /** 未提供時無法以 Esc 或點擊背景關閉（例如處理中） */
  onClose?: () => void;
  maxWidth?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  fullWidth?: boolean;
  children: React.ReactNode;
  className?: string;
  /** 沒有 DialogTitle 時用來命名對話框 */
  'aria-label'?: string;
}
export const Dialog: React.FC<DialogProps> = ({
  open,
  onClose,
  maxWidth = 'sm',
  fullWidth = true,
  children,
  className = '',
  'aria-label': ariaLabel,
}) => {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const dialogHandlers = useModalDialog(dialogRef, open, onClose);
  if (!open) return null;
  const maxWidthClass =
    maxWidth === 'xs'
      ? styles.maxWidthXs
      : maxWidth === 'md'
        ? styles.maxWidthMd
        : maxWidth === 'lg'
          ? styles.maxWidthLg
          : maxWidth === 'xl'
            ? styles.maxWidthXl
            : styles.maxWidthSm;
  return createPortal(
    <dialog
      ref={dialogRef}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabel ? undefined : titleId}
      className={`${styles.dialog} ${maxWidthClass} ${fullWidth ? styles.fullWidth : ''} ${className}`}
      {...dialogHandlers}
    >
      <DialogTitleIdContext.Provider value={titleId}>{children}</DialogTitleIdContext.Provider>
    </dialog>,
    document.body
  );
};
export interface DialogTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {
  icon?: React.ReactNode;
  subtitle?: React.ReactNode;
  /** 提供時在標題列右側顯示關閉按鈕 */
  onClose?: () => void;
  closeDisabled?: boolean;
}
export const DialogTitle: React.FC<DialogTitleProps> = ({
  children,
  className = '',
  icon,
  subtitle,
  onClose,
  closeDisabled = false,
  ...props
}) => {
  const titleId = useContext(DialogTitleIdContext);
  return (
    <div className={`${styles.title} ${className}`}>
      <div className={styles.titleMain}>
        {icon}
        <div className={styles.titleTextWrap}>
          <h2 id={titleId} className={styles.titleText} {...props}>
            {children}
          </h2>
          {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        </div>
      </div>
      {onClose && (
        <IconButton size="sm" onClick={onClose} disabled={closeDisabled} aria-label="關閉">
          <Icon name="close" size={18} />
        </IconButton>
      )}
    </div>
  );
};
export const DialogContent: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  children,
  className = '',
  ...props
}) => {
  return (
    <div className={`${styles.content} ${className}`} {...props}>
      {children}
    </div>
  );
};
export const DialogActions: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  children,
  className = '',
  ...props
}) => {
  return (
    <div className={`${styles.actions} ${className}`} {...props}>
      {children}
    </div>
  );
};
/** 讓 <form> 包住 DialogContent 與 DialogActions 時仍維持內容區可捲動 */
export const DialogForm: React.FC<React.FormHTMLAttributes<HTMLFormElement>> = ({
  children,
  className = '',
  ...props
}) => {
  return (
    <form className={`${styles.form} ${className}`} {...props}>
      {children}
    </form>
  );
};
export const Modal = Dialog;
