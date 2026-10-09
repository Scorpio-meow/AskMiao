import { useEffect, useState } from 'react';
import authService from '../services/authService';
/** 是否開放自行註冊：null 表示仍在查詢；查詢失敗時視為未開放，不顯示註冊入口 */
export function useRegistrationStatus(): boolean | null {
  const [open, setOpen] = useState<boolean | null>(null);
  useEffect(() => {
    let active = true;
    authService.isRegistrationOpen()
      .then((enabled) => {
        if (active) setOpen(enabled);
      })
      .catch(() => {
        if (active) setOpen(false);
      });
    return () => {
      active = false;
    };
  }, []);
  return open;
}
export default useRegistrationStatus;
