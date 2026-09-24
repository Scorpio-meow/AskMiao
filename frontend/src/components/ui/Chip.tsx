import React from 'react';
import styles from './Chip.module.css';
import { Icon } from './Icon';
export interface ChipProps extends Omit<React.HTMLAttributes<HTMLElement>, 'onClick'> {
  label?: React.ReactNode;
  icon?: React.ReactNode;
  onDelete?: () => void;
  deleteLabel?: string;
  /** 提供時渲染成 <button> */
  onClick?: (e: React.MouseEvent<HTMLElement>) => void;
  /** 提供時渲染成 <a> */
  href?: string;
  target?: string;
  rel?: string;
  variant?: 'filled' | 'outlined';
  color?: 'default' | 'primary' | 'success' | 'warning' | 'error' | 'info' | 'secondary';
  size?: 'sm' | 'md' | 'small' | 'medium';
  /** 長標籤換行而不撐寬容器 */
  wrap?: boolean;
}
export const Chip: React.FC<ChipProps> = ({
  label,
  icon,
  onDelete,
  deleteLabel = '移除',
  onClick,
  href,
  target,
  rel,
  variant = 'filled',
  color = 'default',
  size = 'md',
  wrap = false,
  children,
  className = '',
  ...props
}) => {
  const normalizedSize = size === 'small' || size === 'sm' ? styles.sizeSm : styles.sizeMd;
  const colorClass =
    color === 'primary' || color === 'secondary'
      ? styles.primary
      : color === 'success'
        ? styles.success
        : color === 'warning'
          ? styles.warning
          : color === 'error'
            ? styles.error
            : color === 'info'
              ? styles.info
              : '';
  const interactive = Boolean(onClick || href);
  const classes = [
    styles.chip,
    normalizedSize,
    colorClass,
    variant === 'outlined' ? styles.outlined : '',
    interactive ? styles.clickable : '',
    wrap ? styles.wrap : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');
  const content = (
    <>
      {icon && <span className={styles.icon} aria-hidden="true">{icon}</span>}
      <span className={styles.label}>{label || children}</span>
    </>
  );
  if (onDelete) {
    return (
      <span className={classes} {...props}>
        {onClick ? (
          <button type="button" className={styles.labelButton} onClick={onClick}>
            {content}
          </button>
        ) : (
          content
        )}
        <button
          type="button"
          className={styles.deleteButton}
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          aria-label={deleteLabel}
        >
          <Icon name="close" size={12} />
        </button>
      </span>
    );
  }
  if (href) {
    return (
      <a className={classes} href={href} target={target} rel={rel} onClick={onClick} {...props}>
        {content}
      </a>
    );
  }
  if (onClick) {
    return (
      <button type="button" className={classes} onClick={onClick} {...props}>
        {content}
      </button>
    );
  }
  return (
    <span className={classes} {...props}>
      {content}
    </span>
  );
};
export const Badge = Chip;
