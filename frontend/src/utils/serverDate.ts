// 後端以 UTC 存放時間，回傳的字串卻不帶時區（例如 2026-10-24T05:00:00）；直接交給 Date 會被當成本地時間
export const parseServerDate = (value: string | null | undefined): Date =>
  value
    ? new Date(value.includes('T') && !/(Z|[+-]\d{2}:?\d{2})$/i.test(value) ? `${value}Z` : value)
    : new Date(NaN);
