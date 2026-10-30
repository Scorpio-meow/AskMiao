export const requestErrorMessage = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) return detail.map((item) => (item.msg || '').replace(/^Value error, /, '')).filter(Boolean).join('；') || fallback;
  return fallback;
};
