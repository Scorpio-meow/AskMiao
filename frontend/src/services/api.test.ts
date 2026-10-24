import axios from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { chatService } from './api';

const tokenExpiringIn = (seconds: number): string => {
  const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + seconds })).replace(/=+$/, '');
  return `header.${payload}.signature`;
};

const sseResponse = () => new Response('event: done\ndata: {"answer":"好"}\n\n', { status: 200 });

const authorizationOf = (call: unknown[]) => ((call[1] as RequestInit).headers as Record<string, string>).Authorization;

describe('chatService.sendMessageStream', () => {
  let storage: Map<string, string>;

  beforeEach(() => {
    storage = new Map();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
      removeItem: (key: string) => storage.delete(key),
    });
    vi.stubGlobal('window', { location: { pathname: '/', href: '/' } });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('refreshes an expired access token before sending', async () => {
    storage.set('access_token', tokenExpiringIn(-60));
    const refresh = vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'fresh-token' } });
    const fetchMock = vi.fn().mockResolvedValue(sseResponse());
    vi.stubGlobal('fetch', fetchMock);
    const events: unknown[] = [];

    await chatService.sendMessageStream('你好', null, null, 'medium', (event) => events.push(event));

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(authorizationOf(fetchMock.mock.calls[0])).toBe('Bearer fresh-token');
    expect(storage.get('access_token')).toBe('fresh-token');
    expect(events).toEqual([{ event: 'done', data: { answer: '好' } }]);
  });

  it('refreshes once and resends when the server rejects the token', async () => {
    const valid = tokenExpiringIn(3600);
    storage.set('access_token', valid);
    vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'fresh-token' } });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('{"detail":"權杖已被撤銷"}', { status: 401 }))
      .mockResolvedValueOnce(sseResponse());
    vi.stubGlobal('fetch', fetchMock);

    await chatService.sendMessageStream('你好', null, null, 'medium', () => {});

    expect(fetchMock.mock.calls.map(authorizationOf)).toEqual([`Bearer ${valid}`, 'Bearer fresh-token']);
  });
});
