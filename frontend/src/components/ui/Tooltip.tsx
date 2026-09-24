import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import styles from './Tooltip.module.css';
const SHOW_DELAY_MS = 100;
const ANCHOR_GAP = 6;
const VIEWPORT_PADDING = 8;
export interface TooltipProps {
  title: React.ReactNode;
  placement?: 'top' | 'bottom' | 'left' | 'right';
  children: React.ReactElement;
  className?: string;
  arrow?: boolean;
}
// 以 portal + fixed 定位繪製，避免被捲動容器裁切或撐出捲軸
export const Tooltip: React.FC<TooltipProps> = ({
  title,
  placement = 'top',
  children,
  className = '',
}) => {
  // 顯示中時存放渲染位置：位於模態 <dialog> 內要渲染在 dialog 裡，否則會被頂層 (top layer) 蓋住
  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const descriptionId = useId();
  useEffect(() => () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }, []);
  useEffect(() => {
    if (!portalTarget) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPortalTarget(null);
    };
    const handleScroll = () => setPortalTarget(null);
    document.addEventListener('keydown', handleKeyDown);
    window.addEventListener('scroll', handleScroll, true);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('scroll', handleScroll, true);
    };
  }, [portalTarget]);
  if (!title) return children;
  const show = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      const wrapper = wrapperRef.current;
      if (wrapper) setPortalTarget(wrapper.closest('dialog') ?? document.body);
    }, SHOW_DELAY_MS);
  };
  const hide = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setPortalTarget(null);
  };
  // 提示框掛上 DOM 後依實際尺寸定位並限制在視窗內
  const positionTooltip = (tooltip: HTMLDivElement | null) => {
    const wrapper = wrapperRef.current;
    if (!tooltip || !wrapper) return;
    const rect = wrapper.getBoundingClientRect();
    const width = tooltip.offsetWidth;
    const height = tooltip.offsetHeight;
    let top = rect.top - height - ANCHOR_GAP;
    let left = rect.left + rect.width / 2 - width / 2;
    if (placement === 'bottom') {
      top = rect.bottom + ANCHOR_GAP;
    } else if (placement === 'left') {
      top = rect.top + rect.height / 2 - height / 2;
      left = rect.left - width - ANCHOR_GAP;
    } else if (placement === 'right') {
      top = rect.top + rect.height / 2 - height / 2;
      left = rect.right + ANCHOR_GAP;
    }
    left = Math.min(Math.max(left, VIEWPORT_PADDING), window.innerWidth - width - VIEWPORT_PADDING);
    top = Math.min(Math.max(top, VIEWPORT_PADDING), window.innerHeight - height - VIEWPORT_PADDING);
    tooltip.style.top = `${top}px`;
    tooltip.style.left = `${left}px`;
    tooltip.classList.add(styles.visible);
  };
  // 子元素的名稱已與提示相同時不再重複描述
  const childProps = children.props as { 'aria-label'?: string };
  const describes = typeof title === 'string' && childProps['aria-label'] !== title;
  const child = describes
    ? React.cloneElement(children as React.ReactElement<Record<string, unknown>>, { 'aria-describedby': descriptionId })
    : children;
  return (
    <span
      ref={wrapperRef}
      className={`${styles.wrapper} ${className}`}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {child}
      {describes && (
        <span id={descriptionId} className="sr-only">
          {title}
        </span>
      )}
      {portalTarget &&
        createPortal(
          <div ref={positionTooltip} className={styles.tooltip} aria-hidden="true">
            {title}
          </div>,
          portalTarget
        )}
    </span>
  );
};
