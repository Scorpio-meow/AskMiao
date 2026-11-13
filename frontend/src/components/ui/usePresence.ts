import React, { useEffect, useState } from 'react';
const EXIT_FAILSAFE_MS = 700;
export function usePresence(open: boolean, ref: React.RefObject<HTMLElement | null>): boolean {
  const [mounted, setMounted] = useState(open);
  if (open && !mounted) setMounted(true);
  useEffect(() => {
    if (open || !mounted) return undefined;
    const element = ref.current;
    const running = element?.getAnimations({ subtree: true }).filter((animation) => animation.playState === 'running' && animation.effect?.getComputedTiming().endTime !== Infinity) ?? [];
    let active = true;
    const finish = () => {
      if (active) setMounted(false);
    };
    if (running.length === 0) {
      queueMicrotask(finish);
    } else {
      Promise.race([
        Promise.allSettled(running.map((animation) => animation.finished)),
        new Promise((resolve) => setTimeout(resolve, EXIT_FAILSAFE_MS)),
      ]).then(finish);
    }
    return () => {
      active = false;
    };
  }, [open, mounted, ref]);
  return mounted;
}
export function useHeldWhileClosing<T>(open: boolean, value: T): T {
  const [held, setHeld] = useState(value);
  if (open && held !== value) setHeld(value);
  return open ? value : held;
}