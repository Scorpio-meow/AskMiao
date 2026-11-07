export const parseServerDate = (value: string | null | undefined): Date =>
  value
    ? new Date(value.includes('T') && !/(Z|[+-]\d{2}:?\d{2})$/i.test(value) ? `${value}Z` : value)
    : new Date(NaN);