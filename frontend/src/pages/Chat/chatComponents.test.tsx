import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { Message } from '../../services/api';
import ChatMessageItem from './ChatMessageItem';
import ChatMessageList from './ChatMessageList';
import ChatSidebar from './ChatSidebar';
import ResearchTraceBlock from './ResearchTraceBlock';
import ToolApprovalCard from './ToolApprovalCard';
const noop = () => {};
const ENTITIES: Record<string, string> = { '&quot;': '"', '&#x27;': "'", '&lt;': '<', '&gt;': '>', '&amp;': '&' };
const stripTags = (html: string) => {
  let text = '';
  let inTag = false;
  for (const char of html) {
    if (char === '<') inTag = true;
    else if (char === '>') inTag = false;
    else if (!inTag) text += char;
  }
  return text;
};
const textOf = (html: string) => stripTags(html).replace(/&(quot|#x27|lt|gt|amp);/g, (entity) => ENTITIES[entity]);
const buttons = (html: string) => [...html.matchAll(/<button([^>]*)>(.*?)<\/button>/gs)]
  .map(([, attrs, inner]) => ({ attrs, text: textOf(inner) }));
const buttonNamed = (html: string, text: string) => buttons(html).find((button) => button.text.includes(text));
const renderMessage = (message: Message, options: { isStreaming?: boolean; onRetry?: (m: Message) => void } = {}) =>
  renderToStaticMarkup(
    <ChatMessageItem
      message={message}
      thinkId={message.id ?? 0}
      isStreaming={options.isStreaming ?? false}
      isThinkingOpen={false}
      deferRendering={false}
      onToggleThinking={noop}
      onCopyMessage={noop}
      onRetry={options.onRetry}
    />
  );
describe('ChatMessageItem', () => {
  it('renders the user message as plain text with a copy action', () => {
    const html = renderMessage({ id: 1, content: '**不要**轉成粗體', is_user: true, created_at: '2026-11-02T01:00:00' });
    expect(textOf(html)).toContain('您說：**不要**轉成粗體');
    expect(html).not.toContain('<strong>');
    expect(html).toContain('aria-label="複製訊息內容"');
    expect(html).toContain('dateTime="2026-11-02T01:00:00"');
  });
  it('shows the waiting state before anything arrives', () => {
    const html = renderMessage({ id: 2, content: '', is_user: false, model_name: 'fake-text' }, { isStreaming: true });
    expect(textOf(html)).toContain('AI 正在分析您的問題...');
    expect(textOf(html)).toContain('fake-text');
    expect(html).not.toContain('aria-label="複製訊息內容"');
  });
  it('renders markdown answers with the think block collapsed', () => {
    const html = renderMessage({ id: 3, content: '<think>先找規定</think>## 特休\n\n滿一年 **七天** [1]', is_user: false });
    expect(html).toContain('<h2>特休</h2>');
    expect(html).toContain('<strong>七天</strong>');
    const toggle = buttonNamed(html, '思考與推論過程');
    expect(toggle?.attrs).toContain('aria-expanded="false"');
    expect(textOf(html)).toContain('先找規定');
  });
  it('offers to resend a failed answer only when retry is allowed', () => {
    const failed: Message = { id: 4, content: '', is_user: false, error: '連線中斷，回答可能不完整，請重新傳送。' };
    expect(buttonNamed(renderMessage(failed, { onRetry: noop }), '重新傳送')).toBeDefined();
    const html = renderMessage(failed);
    expect(textOf(html)).toContain('連線中斷，回答可能不完整，請重新傳送。');
    expect(buttonNamed(html, '重新傳送')).toBeUndefined();
    expect(textOf(html)).not.toContain('AI 正在分析您的問題...');
  });
  it('explains that a stopped answer was not saved', () => {
    const html = renderMessage({ id: 5, content: '部分內容', is_user: false, stopped: true });
    expect(textOf(html)).toContain('已停止產生。這則回答沒有被儲存，重新整理後不會出現。');
  });
  it('lists cited sources with their citation numbers', () => {
    const html = renderMessage({
      id: 6,
      content: '滿一年七天 [1]，參考網站 [2]',
      is_user: false,
      sources: ['leave_rules.txt', 'https://example.com/leave'],
      sources_detail: [
        { source: 'leave_rules.txt', chunk: 2, score: 0.82, snippet: '滿一年七天', citation: 1 },
        { source: 'https://example.com/leave', url: 'https://example.com/leave', citation: 2 },
      ],
    });
    expect(textOf(html)).toContain('參考來源');
    const documentSource = buttonNamed(html, 'leave_rules.txt');
    expect(documentSource?.text).toBe('1leave_rules.txt段落 2');
    expect(documentSource?.attrs).toContain('aria-haspopup="dialog"');
    expect(html).toMatch(/<a[^>]*href="https:\/\/example\.com\/leave"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/);
    expect(textOf(html)).toContain('（在新分頁開啟）');
  });
  it('falls back to plain source names from older answers', () => {
    const html = renderMessage({ id: 7, content: '舊回答', is_user: false, sources: ['舊文件.pdf'] });
    expect(textOf(html)).toContain('舊文件.pdf');
    expect(buttonNamed(html, '舊文件.pdf')).toBeUndefined();
  });
  it('shows the approval card only while the answer is streaming', () => {
    const message: Message = {
      id: 8,
      content: '',
      is_user: false,
      research_trace: [{ step: 1, tool: 'send_ticket', status: 'running' }],
      pending_approval: {
        approval_id: 'a1',
        step: 1,
        tool: 'send_ticket',
        tool_display_name: '派遣工單',
        target: 'POST tickets.example.com',
        arguments: { note: '你好' },
      },
    };
    expect(textOf(renderMessage(message, { isStreaming: true }))).toContain('AI 想執行外部工具，需要你確認');
    expect(textOf(renderMessage(message))).not.toContain('AI 想執行外部工具，需要你確認');
  });
});
describe('ResearchTraceBlock', () => {
  it('names the running step and keeps arbitrary arguments as text', () => {
    const html = renderToStaticMarkup(
      <ResearchTraceBlock
        isStreaming
        trace={[
          { step: 1, tool: 'search_knowledge_base', arguments: { query: '特休' }, output_preview: { hits: 3 }, duration_seconds: 0.4, status: 'success' },
          { step: 2, tool: 'web_fetch', arguments: { url: 'https://example.com' }, status: 'running' },
        ]}
      />
    );
    expect(textOf(html)).toContain('研究中：深度閱讀網頁（步驟 2）');
    expect(textOf(html)).toContain('關鍵字/目標：特休');
    expect(textOf(html)).toContain('{"hits":3}');
    expect(textOf(html)).toContain('0.4s');
    expect(textOf(html)).toContain('進行中');
  });
  it('summarises a finished trace and counts failures', () => {
    const html = renderToStaticMarkup(
      <ResearchTraceBlock
        hasContent
        trace={[
          { step: 1, tool: 'filter_and_count_records', arguments: { author: '王', keyword: '請假' }, status: 'success' },
          { step: 2, tool: 'custom_tool', arguments: ['a', 1], status: 'error' },
        ]}
      />
    );
    expect(textOf(html)).toContain('研究過程（2 個步驟）');
    expect(textOf(html)).toContain('1 個失敗');
    expect(textOf(html)).toContain('作者: 王 | 關鍵字: 請假');
    expect(textOf(html)).toContain('步驟 2：custom_tool');
    expect(textOf(html)).toContain('["a",1]');
  });
});
describe('ToolApprovalCard', () => {
  it('reveals hidden characters in the tool arguments', () => {
    const html = renderToStaticMarkup(
      <ToolApprovalCard
        approval={{
          approval_id: 'a2',
          step: 1,
          tool: 'send_mail',
          tool_display_name: '寄送郵件',
          target: 'POST mail.example.com',
          arguments: { to: 'boss‮@example.com', count: 2 },
        }}
      />
    );
    expect(textOf(html)).toContain('寄送郵件');
    expect(textOf(html)).toContain('POST mail.example.com');
    expect(textOf(html)).toContain('boss⟦U+202E⟧@example.com');
    expect(textOf(html)).toContain('2');
    expect(buttonNamed(html, '拒絕')).toBeDefined();
    expect(buttonNamed(html, '核准執行')).toBeDefined();
  });
  it('says when there are no arguments', () => {
    const html = renderToStaticMarkup(
      <ToolApprovalCard approval={{ approval_id: 'a3', step: 1, tool: 'ping', tool_display_name: 'Ping', target: 'GET api.example.com' }} />
    );
    expect(textOf(html)).toContain('（沒有參數）');
  });
});
const listProps = {
  conversationLoading: false,
  sending: false,
  streamingMessageId: null,
  loadingMore: false,
  hasMoreMessages: false,
  onLoadMore: noop,
  thinkOpenArr: {},
  onToggleThinking: noop,
  onCopyMessage: noop,
  onSelectPrompt: noop,
  onRetry: noop,
};
describe('ChatMessageList', () => {
  it('offers suggested prompts for a new conversation', () => {
    const html = renderToStaticMarkup(<ChatMessageList {...listProps} messages={[]} />);
    expect(textOf(html)).toContain('開始新的對話');
    expect(buttonNamed(html, '請幫我分析並總結文件的核心重點')).toBeDefined();
    expect(html).toMatch(/role="group" aria-labelledby="[^"]+"/);
  });
  it('shows placeholders while a conversation loads', () => {
    const html = renderToStaticMarkup(<ChatMessageList {...listProps} messages={[]} conversationLoading />);
    expect(html).toContain('aria-busy="true"');
    expect(textOf(html)).toContain('正在載入對話...');
    expect(textOf(html)).not.toContain('開始新的對話');
  });
  it('renders messages and the button to load older ones', () => {
    const html = renderToStaticMarkup(
      <ChatMessageList
        {...listProps}
        hasMoreMessages
        messages={[
          { id: 1, content: '問題', is_user: true },
          { id: 2, content: '回答', is_user: false },
        ]}
      />
    );
    expect(buttonNamed(html, '載入更早訊息')).toBeDefined();
    expect(textOf(html)).toContain('您說：問題');
    expect(textOf(html)).toContain('AskMiao 回覆：回答');
  });
});
describe('ChatSidebar', () => {
  const sidebarProps = {
    id: 'sidebar',
    open: false,
    onClose: noop,
    currentConversation: null,
    onSelectConversation: noop,
    onNewConversation: noop,
    onDeleteConversation: noop,
    loading: false,
    loadError: null,
    onRetryLoad: noop,
  };
  it('groups conversations by date and marks the current one', () => {
    const today = new Date().toISOString();
    const older = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
    const conversations = [
      { id: 1, title: '請假規定', created_at: today, updated_at: today },
      { id: 2, title: '', created_at: older, updated_at: older },
    ];
    const html = renderToStaticMarkup(
      <ChatSidebar {...sidebarProps} conversations={conversations} currentConversation={conversations[0]} />
    );
    expect(textOf(html)).toContain('今天');
    expect(textOf(html)).toContain('更早');
    expect(buttonNamed(html, '請假規定')?.attrs).toContain('aria-current="true"');
    expect(html).toContain('aria-label="刪除對話「未命名對話」"');
  });
  it('shows the load error with a retry button', () => {
    const html = renderToStaticMarkup(<ChatSidebar {...sidebarProps} conversations={[]} loadError="無法載入對話清單" />);
    expect(html).toContain('role="alert"');
    expect(buttonNamed(html, '重新載入')).toBeDefined();
  });
  it('shows the empty state once loading has finished', () => {
    const html = renderToStaticMarkup(<ChatSidebar {...sidebarProps} conversations={[]} />);
    expect(textOf(html)).toContain('尚無歷史對話');
    const loadingHtml = renderToStaticMarkup(<ChatSidebar {...sidebarProps} conversations={[]} loading />);
    expect(textOf(loadingHtml)).toContain('正在載入對話清單...');
    expect(textOf(loadingHtml)).not.toContain('尚無歷史對話');
  });
});