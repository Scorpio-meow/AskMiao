import styles from './AiTools.module.css';
// 後端不回傳已儲存的憑證，以遮蔽字樣代替；送回遮蔽字樣的欄位沿用原值
export const SECRET_FIELD_HINT = '已儲存的金鑰以 •••••••• 顯示，保持不變即沿用原值；要更換時請輸入完整的新值';
// 後端回應 credentials_unreadable：已儲存的憑證無法以目前的 TOOL_SECRETS_KEY 解密（例如金鑰已更換），欄位會顯示為空白
export const CREDENTIALS_UNREADABLE_NOTICE = '已儲存的憑證無法以目前的 TOOL_SECRETS_KEY 解密（金鑰可能已更換），憑證欄位因此顯示為空白。重新輸入憑證並儲存之前，這個工具無法執行。';
export const getRequestErrorMessage = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (err instanceof Error && err.message && !err.response) return err.message;
  return fallback;
};
export const getMethodClass = (method) => {
  switch (method?.toUpperCase()) {
    case 'GET': return styles.methodGet;
    case 'POST': return styles.methodPost;
    case 'PUT': return styles.methodPut;
    case 'DELETE': return styles.methodDelete;
    case 'PATCH': return styles.methodPatch;
    default: return styles.methodGet;
  }
};
