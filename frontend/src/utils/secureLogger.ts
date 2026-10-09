import { isAxiosError } from 'axios';
const isDevelopment = import.meta.env.DEV;
/**
 * 請求失敗時寫進主控台的說明。axios 的錯誤物件帶有完整的請求設定：config.data 是送出的內容
 * （登入、註冊、修改密碼時含密碼，匯入工具時含 API 金鑰），config.headers 含存取權杖。
 * 使用者回報問題時常整段複製主控台內容，因此只記錄狀態碼與錯誤訊息，不記錄錯誤物件本身
 */
export const describeRequestError = (error: unknown): string => {
  if (isAxiosError(error)) {
    return [error.response?.status, error.code, error.message].filter(Boolean).join(' ');
  }
  return error instanceof Error ? error.message : String(error);
};
export const devLog = (...args: any[]): void => {
  if (isDevelopment) {
    console.log(...args);
  }
};
export const devWarn = (...args: any[]): void => {
  console.warn(...args);
};
export const devError = (...args: any[]): void => {
  console.error(...args);
};
export const devInfo = (...args: any[]): void => {
  if (isDevelopment) {
    console.info(...args);
  }
};
export const secureLog = (label: string, data: any): void => {
  if (!isDevelopment) {
    return;
  }
  const sanitized = JSON.parse(JSON.stringify(data));
  const sensitiveKeys = ['password', 'token', 'access_token', 'refresh_token', 'apiKey', 'secret'];
  const removeSensitive = (obj: any): any => {
    if (!obj || typeof obj !== 'object') return obj;
    Object.keys(obj).forEach((key) => {
      if (sensitiveKeys.some((sensitive) => key.toLowerCase().includes(sensitive))) {
        obj[key] = '[REDACTED]';
      } else if (typeof obj[key] === 'object') {
        removeSensitive(obj[key]);
      }
    });
    return obj;
  };
  console.log(label, removeSensitive(sanitized));
};
if (!isDevelopment) {
  const originalError = console.error;
  const originalWarn = console.warn;
  console.log = () => { };
  console.info = () => { };
  console.debug = () => { };
  console.error = originalError;
  console.warn = originalWarn;
  console.warn('🔒 生產環境模式：調試日誌已禁用');
}
const secureLogger = {
  log: devLog,
  warn: devWarn,
  error: devError,
  info: devInfo,
  secure: secureLog,
};
export default secureLogger;
