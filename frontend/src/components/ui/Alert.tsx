import React from 'react';
import styles from './Alert.module.css';
import { Icon } from './Icon';
export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  severity?: 'success' | 'info' | 'warning' | 'error';
  icon?: React.ReactNode;
  action?: React.ReactNode;
  onClose?: () => void;
}
export const Alert: React.FC<AlertProps> = ({
  severity = 'info',
  icon,
  action,
  onClose,
  children,
  className = '',
  role,
  ...props
}) => {
  const severityClass =
    severity === 'success'
      ? styles.success
      : severity === 'warning'
        ? styles.warning
        : severity === 'error'
          ? styles.error
          : styles.info;
  const defaultIcon =
    severity === 'success' ? (
      <Icon name="check-circle" size={18} />
    ) : severity === 'warning' ? (
      <Icon name="warning" size={18} />
    ) : severity === 'error' ? (
      <Icon name="error" size={18} />
    ) : (
      <Icon name="info" size={18} />
    );
  // 錯誤與警告需要立即播報；成功與資訊以禮貌模式播報即可
  const liveRole = role ?? (severity === 'error' || severity === 'warning' ? 'alert' : 'status');
  return (
    <div className={`${styles.alert} ${severityClass} ${className}`} role={liveRole} {...props}>
      <div className={styles.icon}>{icon !== undefined ? icon : defaultIcon}</div>
      <div className={styles.message}>{children}</div>
      {(action || onClose) && (
        <div className={styles.action}>
          {action}
          {onClose && (
            <button type="button" className={styles.closeButton} onClick={onClose} aria-label="關閉提示">
              <Icon name="close" size={16} />
            </button>
          )}
        </div>
      )}
    </div>
  );
};
