import React, { useLayoutEffect, useRef, useState } from 'react';
import styles from './Tabs.module.css';
export interface TabsProps {
  value: number | string;
  onChange: (event: React.SyntheticEvent, newValue: any) => void;
  children: React.ReactNode;
  className?: string;
}
export const Tabs: React.FC<TabsProps> = ({ value, onChange, children, className = '' }) => {
  const listRef = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState<{ x: number; width: number } | null>(null);
  const [settled, setSettled] = useState(false);
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return undefined;
    const measure = () => {
      const active = list.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]');
      setIndicator(active ? { x: active.offsetLeft, width: active.offsetWidth } : null);
    };
    measure();
    const frame = requestAnimationFrame(() => setSettled(true));
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(list);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, [value]);
  return (
    <div
      ref={listRef}
      className={`${styles.tabsContainer} ${settled ? styles.settled : ''} ${className}`}
      role="tablist"
      style={indicator ? ({ '--indicator-x': `${indicator.x}px`, '--indicator-w': indicator.width } as React.CSSProperties) : undefined}
    >
      {React.Children.map(children, (child, index) => {
        if (!React.isValidElement(child)) return null;
        const tabChild = child as React.ReactElement<any>;
        const tabValue = tabChild.props.value !== undefined ? tabChild.props.value : index;
        const isActive = tabValue === value;
        return React.cloneElement(tabChild, {
          active: isActive,
          onClick: (e: React.MouseEvent) => {
            tabChild.props.onClick?.(e);
            onChange(e, tabValue);
          },
        });
      })}
      {indicator && <span className={styles.indicator} aria-hidden="true" />}
    </div>
  );
};
export interface TabProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  label: React.ReactNode;
  icon?: React.ReactNode;
  value?: number | string;
  active?: boolean;
}
export const Tab: React.FC<TabProps> = ({
  label,
  icon,
  active = false,
  className = '',
  ...props
}) => {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={`${styles.tab} ${active ? styles.tabActive : ''} ${className}`}
      {...props}
    >
      {icon && <span className={styles.tabIcon}>{icon}</span>}
      <span>{label}</span>
    </button>
  );
};