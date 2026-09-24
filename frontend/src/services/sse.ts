export interface SseMessage {
  event: string;
  data: string;
}
/**
 * 依 SSE 規格解析串流：event 與 data 可能分散在多次 read 之間，
 * 只有讀到空行才派送事件；串流在事件中途結束時捨棄不完整的事件。
 */
export function createSseParser(onMessage: (message: SseMessage) => void) {
  let buffer = '';
  let eventName = '';
  let dataLines: string[] = [];
  const dispatch = () => {
    if (dataLines.length > 0) {
      onMessage({ event: eventName || 'message', data: dataLines.join('\n') });
    }
    eventName = '';
    dataLines = [];
  };
  const processLine = (line: string) => {
    if (line === '') {
      dispatch();
      return;
    }
    if (line.startsWith(':')) return;
    const colonIndex = line.indexOf(':');
    const field = colonIndex === -1 ? line : line.slice(0, colonIndex);
    let value = colonIndex === -1 ? '' : line.slice(colonIndex + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') {
      eventName = value;
    } else if (field === 'data') {
      dataLines.push(value);
    }
  };
  return {
    push(chunk: string) {
      buffer += chunk;
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? '';
      lines.forEach(processLine);
    },
  };
}
