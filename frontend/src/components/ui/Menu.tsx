import React, { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useOverlayBehavior } from './useOverlayBehavior';
import { Icon } from './Icon';
import styles from './Menu.module.css';
type Placement = 'bottom-start' | 'bottom-end' | 'top-start' | 'top-end';
const ANCHOR_GAP = 6;
const VIEWPORT_PADDING = 8;
function useAnchoredPosition(
  open: boolean,
  anchorEl: HTMLElement | null,
  placement: Placement,
  panelRef: React.RefObject<HTMLDivElement | null>
) {
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  useLayoutEffect(() => {
    if (!open || !anchorEl) return;
    const update = () => {
      const panel = panelRef.current;
      if (!panel) return;
      const rect = anchorEl.getBoundingClientRect();
      const panelWidth = panel.offsetWidth;
      const panelHeight = panel.offsetHeight;
      let top = placement.startsWith('top') ? rect.top - panelHeight - ANCHOR_GAP : rect.bottom + ANCHOR_GAP;
      let left = placement.endsWith('end') ? rect.right - panelWidth : rect.left;
      if (left + panelWidth > window.innerWidth - VIEWPORT_PADDING) {
        left = window.innerWidth - panelWidth - VIEWPORT_PADDING;
      }
      left = Math.max(left, VIEWPORT_PADDING);
      if (top + panelHeight > window.innerHeight - VIEWPORT_PADDING) {
        top = rect.top - panelHeight - ANCHOR_GAP;
      }
      top = Math.max(top, VIEWPORT_PADDING);
      setCoords({ top, left });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [open, anchorEl, placement, panelRef]);
  return coords;
}
const getMenuItems = (menu: HTMLElement | null) =>
  Array.from(menu?.querySelectorAll<HTMLElement>('[role^="menuitem"]:not([disabled])') ?? []);
// 觸發元素位於模態 <dialog> 內時必須渲染在該 dialog 裡，否則會被頂層 (top layer) 蓋住且無法操作
const getPortalTarget = (anchorEl: HTMLElement) => anchorEl.closest('dialog') ?? document.body;
export interface MenuProps {
  open: boolean;
  anchorEl: HTMLElement | null;
  onClose?: () => void;
  children: React.ReactNode;
  className?: string;
  placement?: Placement;
  id?: string;
  'aria-label'?: string;
}
export const Menu: React.FC<MenuProps> = ({
  open,
  anchorEl,
  onClose,
  children,
  className = '',
  placement = 'bottom-start',
  id,
  'aria-label': ariaLabel,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);
  const coords = useAnchoredPosition(open, anchorEl, placement, menuRef);
  useOverlayBehavior(open, menuRef, onClose, (menu) => getMenuItems(menu)[0] ?? null);
  if (!open || !anchorEl) return null;
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const items = getMenuItems(menuRef.current);
    if (items.length === 0) return;
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      items[(index + 1) % items.length].focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      items[(index - 1 + items.length) % items.length].focus();
    } else if (e.key === 'Home') {
      e.preventDefault();
      items[0].focus();
    } else if (e.key === 'End') {
      e.preventDefault();
      items[items.length - 1].focus();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      onClose?.();
    }
  };
  return createPortal(
    <>
      <div className={styles.menuBackdrop} onClick={onClose} />
      <div
        ref={menuRef}
        id={id}
        role="menu"
        aria-label={ariaLabel}
        className={`${styles.menuContainer} ${className}`}
        style={{ top: `${coords.top}px`, left: `${coords.left}px` }}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        {children}
      </div>
    </>,
    getPortalTarget(anchorEl)
  );
};
export interface MenuItemProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: React.ReactNode;
  danger?: boolean;
  /** 提供時成為單選項目（menuitemradio） */
  checked?: boolean;
}
export const MenuItem: React.FC<MenuItemProps> = ({
  children,
  icon,
  danger = false,
  checked,
  className = '',
  ...props
}) => {
  const isRadio = checked !== undefined;
  return (
    <button
      type="button"
      role={isRadio ? 'menuitemradio' : 'menuitem'}
      aria-checked={isRadio ? checked : undefined}
      tabIndex={-1}
      className={`${styles.menuItem} ${danger ? styles.menuItemDanger : ''} ${checked ? styles.menuItemChecked : ''} ${className}`}
      {...props}
    >
      {icon && <span className={styles.menuItemIcon} aria-hidden="true">{icon}</span>}
      <span className={styles.menuItemLabel}>{children}</span>
      {isRadio && (
        <span className={styles.menuItemCheck} aria-hidden="true">
          {checked && <Icon name="check" size={16} />}
        </span>
      )}
    </button>
  );
};
export const MenuGroup: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div role="group" aria-label={label}>
    <div className={styles.groupLabel} aria-hidden="true">{label}</div>
    {children}
  </div>
);
export const MenuDivider: React.FC = () => <div role="separator" className={styles.divider} />;
export interface PopoverProps {
  open: boolean;
  anchorEl: HTMLElement | null;
  onClose?: () => void;
  children: React.ReactNode;
  className?: string;
  placement?: Placement;
  'aria-label': string;
}
/** 非模態的資訊浮層：焦點移入、Esc 關閉並把焦點還給觸發元素 */
export const Popover: React.FC<PopoverProps> = ({
  open,
  anchorEl,
  onClose,
  children,
  className = '',
  placement = 'bottom-start',
  'aria-label': ariaLabel,
}) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const coords = useAnchoredPosition(open, anchorEl, placement, panelRef);
  useOverlayBehavior(open, panelRef, onClose, 'container');
  if (!open || !anchorEl) return null;
  return createPortal(
    <>
      <div className={styles.menuBackdrop} onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-label={ariaLabel}
        className={`${styles.menuContainer} ${className}`}
        style={{ top: `${coords.top}px`, left: `${coords.left}px` }}
        tabIndex={-1}
      >
        {children}
      </div>
    </>,
    getPortalTarget(anchorEl)
  );
};
