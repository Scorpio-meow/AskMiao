import { jwtDecode, JwtPayload } from 'jwt-decode';
const decodeToken = (token: string): JwtPayload | null => {
  try {
    return jwtDecode<JwtPayload>(token);
  } catch (error) {
    console.error('Token 解碼失敗:', error);
    return null;
  }
};
export const isTokenExpired = (token: string, bufferTime: number = 300): boolean => {
  const decoded = decodeToken(token);
  if (!decoded || !decoded.exp) {
    return true;
  }
  const currentTime = Date.now() / 1000;
  return decoded.exp - currentTime < bufferTime;
};
export const clearAuth = (): void => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('user_info');
  console.log('[Auth] 已清除認證信息');
};
