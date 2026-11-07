import { useEffect, useState } from 'react';
import authService from '../services/authService';
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