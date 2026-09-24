import { describe, expect, it } from 'vitest';
import { createSseParser, SseMessage } from './sse';
const collect = (chunks: string[]) => {
  const messages: SseMessage[] = [];
  const parser = createSseParser((message) => messages.push(message));
  chunks.forEach((chunk) => parser.push(chunk));
  return messages;
};
describe('createSseParser', () => {
  it('派送單一完整事件', () => {
    expect(collect(['event: token\ndata: {"content":"你好"}\n\n'])).toEqual([
      { event: 'token', data: '{"content":"你好"}' },
    ]);
  });
  it('event 行與 data 落在不同 read 時仍保留事件名稱', () => {
    expect(collect(['event: done\n', 'data: {"message_id":1}\n\n'])).toEqual([
      { event: 'done', data: '{"message_id":1}' },
    ]);
  });
  it('data 被切在 JSON 中間時等到空行才派送', () => {
    const payload = JSON.stringify({ answer: '很長的回答', conversation_id: 7 });
    expect(
      collect([`event: done\ndata: ${payload.slice(0, 10)}`, `${payload.slice(10)}\n`, '\n'])
    ).toEqual([{ event: 'done', data: payload }]);
  });
  it('一次 read 內含多個事件', () => {
    expect(
      collect(['event: step_start\ndata: {"step":1}\n\nevent: token\ndata: {"content":"a"}\n\n'])
    ).toEqual([
      { event: 'step_start', data: '{"step":1}' },
      { event: 'token', data: '{"content":"a"}' },
    ]);
  });
  it('處理 CRLF 換行與跨 read 的 \\r\\n', () => {
    expect(collect(['event: token\r', '\ndata: {"content":"b"}\r\n\r\n'])).toEqual([
      { event: 'token', data: '{"content":"b"}' },
    ]);
  });
  it('多行 data 以換行合併，註解行被忽略', () => {
    expect(collect([': keep-alive\ndata: 第一行\ndata: 第二行\n\n'])).toEqual([
      { event: 'message', data: '第一行\n第二行' },
    ]);
  });
  it('事件派送後事件名稱重設', () => {
    expect(collect(['event: sources\ndata: {}\n\ndata: {}\n\n'])).toEqual([
      { event: 'sources', data: '{}' },
      { event: 'message', data: '{}' },
    ]);
  });
  it('串流在事件中途結束時不派送不完整的事件', () => {
    expect(collect(['event: done\ndata: {"partial"'])).toEqual([]);
  });
});
