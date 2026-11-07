import { isAxiosError } from 'axios';
const isDevelopment = import.meta.env.DEV;
export const describeRequestError = (error: unknown): string => {
  if (isAxiosError(error)) {
    return [error.response?.status, error.code, error.message].filter(Boolean).join(' ');
  }
  return error instanceof Error ? error.message : String(error);
};
export const devWarn = (...args: any[]): void => {
  console.warn(...args);
};
if (!isDevelopment) {
  const originalError = console.error;
  const originalWarn = console.warn;
  console.log = () => { };
  console.info = () => { };
  console.debug = () => { };
  console.error = originalError;
  console.warn = originalWarn;
  console.warn('🔒 正式環境模式：除錯日誌已停用');
}