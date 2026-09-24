import React, { useEffect, useLayoutEffect, useRef } from 'react';
const isOutsideDialogBox = (dialog: HTMLDialogElement, x: number, y: number) => {
  const rect = dialog.getBoundingClientRect();
  return x < rect.left || x > rect.right || y < rect.top || y > rect.bottom;
};
/**
 * 以原生 <dialog> + showModal() 呈現受 React 狀態控制的模態視窗：
 * 瀏覽器負責把背景設為 inert 與處理 Esc，關閉後把焦點還給開啟前的元素。
 * - Esc / 返回手勢觸發的 cancel 會轉成 onClose，由呼叫端決定是否關閉；未提供 onClose 時無法關閉
 * - 點擊背景關閉：Safari 尚不支援 closedby="any"，統一用點擊座標判斷，
 *   並要求按下與放開都在對話框外，避免在內容中選取文字時拖到外面就被關掉
 * - 開啟後若內容有 [data-autofocus]，焦點移到該元素
 */
export function useModalDialog(
  dialogRef: React.RefObject<HTMLDialogElement | null>,
  open: boolean,
  onClose: (() => void) | undefined
) {
  const onCloseRef = useRef(onClose);
  const pointerDownOutsideRef = useRef(false);
  useEffect(() => {
    onCloseRef.current = onClose;
  });
  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (!open || !dialog) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!dialog.open) dialog.showModal();
    dialog.querySelector<HTMLElement>('[data-autofocus]')?.focus();
    return () => {
      if (dialog.open) dialog.close();
      // React 會先移除 <dialog> 節點才執行這裡，瀏覽器已無法自動歸還焦點，改由這裡還給開啟前的元素
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, [open, dialogRef]);
  return {
    onCancel: (event: React.SyntheticEvent<HTMLDialogElement>) => {
      event.preventDefault();
      onCloseRef.current?.();
    },
    onPointerDown: (event: React.PointerEvent<HTMLDialogElement>) => {
      pointerDownOutsideRef.current =
        event.target === event.currentTarget && isOutsideDialogBox(event.currentTarget, event.clientX, event.clientY);
    },
    onClick: (event: React.MouseEvent<HTMLDialogElement>) => {
      const startedOutside = pointerDownOutsideRef.current;
      pointerDownOutsideRef.current = false;
      if (
        startedOutside &&
        event.target === event.currentTarget &&
        isOutsideDialogBox(event.currentTarget, event.clientX, event.clientY)
      ) {
        onCloseRef.current?.();
      }
    },
  };
}
