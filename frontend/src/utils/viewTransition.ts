import { flushSync } from 'react-dom';
type Update = () => void | Promise<void>;
export const runViewTransition = (kind: string, update: Update): Promise<void> => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!document.startViewTransition || reduceMotion || document.visibilityState !== 'visible') {
    return Promise.resolve(update());
  }
  const root = document.documentElement;
  root.dataset.vt = kind;
  return new Promise<void>((resolve, reject) => {
    const transition = document.startViewTransition(() => {
      let result: void | Promise<void> = undefined;
      try {
        flushSync(() => {
          result = update();
        });
      } catch (err) {
        reject(err);
        return;
      }
      Promise.resolve(result).then(resolve, reject);
    });
    transition.finished.finally(() => {
      if (root.dataset.vt === kind) delete root.dataset.vt;
    });
  });
};