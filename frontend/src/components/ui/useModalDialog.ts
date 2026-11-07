import React, { useEffect, useLayoutEffect, useRef } from 'react';
const isOutsideDialogBox = (dialog: HTMLDialogElement, x: number, y: number) => {
  const rect = dialog.getBoundingClientRect();
  return x < rect.left || x > rect.right || y < rect.top || y > rect.bottom;
};
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