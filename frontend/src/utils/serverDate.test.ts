import { describe, expect, it } from 'vitest';
import { parseServerDate } from './serverDate';

describe('parseServerDate', () => {
  it('treats timestamps without a zone as UTC', () => {
    expect(parseServerDate('2026-10-24T05:00:00').toISOString()).toBe('2026-10-24T05:00:00.000Z');
    expect(parseServerDate('2026-10-24T05:00:00.123456').toISOString()).toBe('2026-10-24T05:00:00.123Z');
  });

  it('keeps timestamps that already carry a zone', () => {
    expect(parseServerDate('2026-10-24T05:00:00Z').toISOString()).toBe('2026-10-24T05:00:00.000Z');
    expect(parseServerDate('2026-10-24T13:00:00+08:00').toISOString()).toBe('2026-10-24T05:00:00.000Z');
  });
});
