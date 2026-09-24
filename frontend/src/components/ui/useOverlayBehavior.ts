import React, { useEffect, useRef } from 'react';
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(',');
// 只有最上層的浮層處理 Esc
const overlayStack: symbol[] = [];
export const getFocusableElements = (container: HTMLElement): HTMLElement[] =>
  Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => !el.closest('[inert]') && el.getClientRects().length > 0
  );
export type InitialFocus = 'auto' | 'container' | ((container: HTMLElement) => HTMLElement | null);
/**
 * 非模態浮層（選單、資訊浮層）的鍵盤與焦點行為：
 * 開啟時把焦點移入、Esc 關閉，關閉後把焦點還給原本的觸發元素。
 * 模態視窗請改用原生 <dialog>（見 useModalDialog）。
 */
export function useOverlayBehavior(
  open: boolean,
  containerRef: React.RefObject<HTMLElement | null>,
  onClose: (() => void) | undefined,
  initialFocus: InitialFocus = 'auto'
) {
  const onCloseRef = useRef(onClose);
  const initialFocusRef = useRef(initialFocus);
  useEffect(() => {
    onCloseRef.current = onClose;
    initialFocusRef.current = initialFocus;
  });
  useEffect(() => {
    if (!open) return;
    const container = containerRef.current;
    if (!container) return;
    const id = Symbol('overlay');
    overlayStack.push(id);
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!container.contains(document.activeElement)) {
      const strategy = initialFocusRef.current;
      const target =
        typeof strategy === 'function'
          ? strategy(container)
          : strategy === 'container'
            ? container
            : container.querySelector<HTMLElement>('[data-autofocus]') ?? getFocusableElements(container)[0];
      (target ?? container).focus();
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (overlayStack[overlayStack.length - 1] !== id || event.key !== 'Escape') return;
      // 阻止預設行為，避免外層原生 <dialog> 同時收到關閉要求
      event.preventDefault();
      event.stopPropagation();
      onCloseRef.current?.();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      const index = overlayStack.indexOf(id);
      if (index !== -1) overlayStack.splice(index, 1);
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, [open, containerRef]);
}
