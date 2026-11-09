import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { Message } from '../../services/api';
import ChatMessageItem from './ChatMessageItem';
import ChatMessageList from './ChatMessageList';
import ChatSidebar from './ChatSidebar';
import ResearchTraceBlock from './ResearchTraceBlock';
import ToolApprovalCard from './ToolApprovalCard';
import SourceBadges from './SourceBadges';
import { PreviewContent } from '../../components/FilePreviewPanel';
import type { FilePreview, PreviewSource } from '../../services/api';
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
const NO_DELETED_FILES: ReadonlySet<number> = new Set();
const renderMessage = (
  message: Message,
  options: { isStreaming?: boolean; onRetry?: (m: Message) => void; deletedFileIds?: ReadonlySet<number> } = {}
) =>
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
      deletedFileIds={options.deletedFileIds ?? NO_DELETED_FILES}
      onDownloadFile={noop}
      onDeleteFile={noop}
      onPreviewFile={noop}
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
    const webSource = buttonNamed(html, 'https://example.com/leave');
    expect(webSource?.text).toBe('2https://example.com/leaveexample.com');
    expect(webSource?.attrs).toContain('aria-haspopup="dialog"');
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
        kind: 'custom_api',
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
          kind: 'custom_api',
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
    expect(buttonNamed(html, '這次提問都允許')).toBeDefined();
    expect(buttonNamed(html, '核准執行')).toBeDefined();
  });
  it('says when there are no arguments', () => {
    const html = renderToStaticMarkup(
      <ToolApprovalCard approval={{ approval_id: 'a3', step: 1, tool: 'ping', kind: 'custom_api', tool_display_name: 'Ping', target: 'GET api.example.com' }} />
    );
    expect(textOf(html)).toContain('（沒有參數）');
  });
  it('words a file deletion as a deletion, not an external call', () => {
    const html = renderToStaticMarkup(
      <ToolApprovalCard
        approval={{ approval_id: 'a4', step: 1, tool: 'delete_conversation_file', kind: 'file', tool_display_name: '刪除對話檔案', target: '#5「採購合約.docx」', arguments: { file_id: 5 } }}
      />
    );
    expect(textOf(html)).toContain('AI 想刪除對話檔案，需要你確認');
    expect(textOf(html)).toContain('永久刪除');
    expect(textOf(html)).not.toContain('外部');
    expect(buttonNamed(html, '這次提問都允許')).toBeUndefined();
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
  deletedFileIds: NO_DELETED_FILES,
  onDownloadFile: noop,
  onDeleteFile: noop,
  onPreviewFile: noop,
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
describe('conversation files', () => {
  const created = { id: 7, filename: '旅費.docx', media_type: 'application/vnd', size_bytes: 2048, origin: 'assistant' as const, version: 1, parent_id: null, created_at: null };
  const updated = { ...created, id: 8, filename: '旅費 v2.docx', version: 2, parent_id: 7 };
  it('shows the files an answer created with download and delete buttons', () => {
    const html = renderMessage({ id: 20, content: '完成', is_user: false, files: [{ action: 'created', file: created }, { action: 'updated', file: updated }] });
    expect(textOf(html)).toContain('旅費.docx');
    expect(textOf(html)).toContain('已存成新版本2.0 KB');
    expect(buttons(html).map((button) => button.attrs.match(/aria-label="([^"]*)"/)?.[1])).toEqual(
      expect.arrayContaining(['下載 旅費.docx', '刪除 旅費.docx', '下載 旅費 v2.docx', '刪除 旅費 v2.docx'])
    );
  });
  it('marks deleted files and drops their buttons', () => {
    const html = renderMessage(
      { id: 21, content: '完成', is_user: false, files: [{ action: 'created', file: created }, { action: 'deleted', file: updated }] },
      { deletedFileIds: new Set([7]) }
    );
    expect(textOf(html).match(/已刪除/g)).toHaveLength(2);
    expect(buttons(html).some((button) => button.attrs.includes('下載'))).toBe(false);
  });
  it('lets the user download a stored attachment but not one sent before files existed', () => {
    const html = renderMessage({
      id: 22,
      content: '看附件',
      is_user: true,
      attachments: [{ filename: '合約.docx', file_type: 'application/msword', file_id: 9 }, { filename: '舊.pdf', file_type: 'application/pdf' }],
    });
    expect(buttons(html).map((button) => button.attrs.match(/aria-label="([^"]*)"/)?.[1])).toEqual(
      expect.arrayContaining(['下載 合約.docx'])
    );
    expect(buttons(html).some((button) => button.attrs.includes('舊.pdf'))).toBe(false);
  });
  it('labels file tools in the research trace', () => {
    const html = renderToStaticMarkup(
      <ResearchTraceBlock trace={[{ step: 1, tool: 'create_conversation_file', arguments: { filename: '報告.pdf' }, status: 'success' }]} />
    );
    expect(textOf(html)).toContain('建立檔案');
    expect(textOf(html)).toContain('報告.pdf');
  });
});
const previewSource: PreviewSource = {
  filename: '報告.docx',
  load: async () => ({ type: 'unsupported', reason: '' }),
  page: async () => new Blob(),
};
const renderPreview = (preview: FilePreview) => renderToStaticMarkup(<PreviewContent preview={preview} source={previewSource} />);
describe('file preview', () => {
  it('lays out a Word document with headings, numbered lists, bold text and tables', () => {
    const html = renderPreview({
      type: 'document',
      truncated: false,
      blocks: [
        { type: 'heading', level: 1, runs: [{ text: '出差規定', bold: false, italic: false }] },
        { type: 'paragraph', runs: [{ text: '上限 ', bold: false, italic: false }, { text: '5,500 元', bold: true, italic: false }] },
        { type: 'list_item', ordered: true, level: 0, runs: [{ text: '申請', bold: false, italic: false }] },
        { type: 'list_item', ordered: true, level: 0, runs: [{ text: '核准', bold: false, italic: false }] },
        { type: 'table', rows: [['項目', '上限'], ['住宿', '5,500 元']], truncated: true },
      ],
    });
    expect(html).toContain('<h3>出差規定</h3>');
    expect(html).toContain('<strong>5,500 元</strong>');
    expect(textOf(html)).toContain('1.申請');
    expect(textOf(html)).toContain('2.核准');
    expect(html).toContain('<th scope="col">項目</th>');
    expect(textOf(html)).toContain('只顯示前面一部分');
  });
  it('shows sheets, slides, pages and unsupported files', () => {
    expect(textOf(renderPreview({ type: 'sheets', sheets: [{ name: '表', rows: [['a', 'b'], ['1', '2']], truncated: false }] }))).toContain('ab12');
    const slides = renderPreview({ type: 'slides', truncated: false, slides: [{ number: 1, title: '重點', notes: '提醒申請', images: 2, items: [{ type: 'text', level: 1, text: '住宿' }] }] });
    expect(textOf(slides)).toContain('第 1 頁');
    expect(textOf(slides)).toContain('2 張圖片');
    expect(textOf(slides)).toContain('提醒申請');
    expect(textOf(renderPreview({ type: 'pages', page_count: 3 })).match(/第 \d 頁/g)).toEqual(['第 1 頁', '第 2 頁', '第 3 頁']);
    expect(textOf(renderPreview({ type: 'unsupported', reason: '這種檔案無法預覽，請下載後開啟' }))).toContain('請下載後開啟');
    expect(textOf(renderPreview({ type: 'text', text: '原文', truncated: false, notice: '伺服器上找不到原始檔' }))).toContain('伺服器上找不到原始檔');
  });
  it('offers a preview button on file cards', () => {
    const file = { id: 8, filename: '網頁.html', media_type: 'text/plain', size_bytes: 10, origin: 'assistant' as const, version: 1, parent_id: null, created_at: null };
    const html = renderMessage({ id: 23, content: '完成', is_user: false, files: [{ action: 'created', file }] });
    expect(buttons(html).some((button) => button.attrs.includes('預覽 網頁.html'))).toBe(true);
  });
});
describe('web source preview', () => {
  it('opens a preview card instead of leaving the chat straight away', () => {
    const html = renderToStaticMarkup(
      <SourceBadges sources={['新聞']} sourcesDetail={[{ citation: 1, source: '颱風假公告', url: 'https://www.example.gov.tw/news/1', snippet: '明天停班停課' }]} />
    );
    const button = buttonNamed(html, '颱風假公告');
    expect(button?.attrs).toContain('aria-haspopup="dialog"');
    expect(textOf(html)).toContain('example.gov.tw');
    expect(html).not.toContain('href="https://www.example.gov.tw/news/1"');
  });
});
describe('PlanChecklist', () => {
  const plan: Message['plan'] = [
    { step: '查特休規定', status: 'completed' },
    { step: '整理成表格', status: 'in_progress' },
    { step: '讀回檔案核對', status: 'pending' },
  ];
  it('shows the plan above the research trace with its progress', () => {
    const html = renderMessage({ id: 30, content: '', is_user: false, plan, research_trace: [{ step: 1, tool: 'search_knowledge_base', status: 'success' }] }, { isStreaming: true });
    const text = textOf(html);
    expect(text).toContain('計畫1/3 步已完成');
    expect(text).toContain('查特休規定（已完成）');
    expect(text).toContain('整理成表格（進行中）');
    expect(text).toContain('讀回檔案核對（尚未開始）');
    expect(html.indexOf('任務計畫')).toBeLessThan(html.indexOf('研究過程'));
  });
  it('spins only while the step is still running', () => {
    const planHtml = (message: Message) => {
      const html = renderMessage(message, { isStreaming: true });
      return html.slice(html.indexOf('任務計畫'), html.indexOf('</section>'));
    };
    expect(planHtml({ id: 31, content: '', is_user: false, plan })).toContain('aria-label="載入中"');
    expect(planHtml({ id: 32, content: '中斷', is_user: false, plan, stopped: true })).not.toContain('aria-label="載入中"');
  });
  it('renders nothing for a message without a plan', () => {
    const html = renderMessage({ id: 33, content: '你好', is_user: false });
    expect(html).not.toContain('任務計畫');
  });
});
describe('QuestionCard', () => {
  const pending = { question_id: 'q1', step: 1, question: '要整理哪個月份？', options: ['八月', '九月'] };
  it('asks the question with its options and a free answer box', () => {
    const html = renderMessage({
      id: 40,
      content: '',
      is_user: false,
      pending_question: pending,
      research_trace: [{ step: 1, tool: 'ask_user', status: 'running', note: '先確認要整理的月份' }],
    }, { isStreaming: true });
    const text = textOf(html);
    expect(text).toContain('需要你的回答要整理哪個月份？');
    expect(buttonNamed(html, '八月')).toBeTruthy();
    expect(buttonNamed(html, '九月')).toBeTruthy();
    expect(html).toContain('aria-label="輸入回答"');
    expect(text).toContain('請勿在回答中提供密碼、金鑰等機密');
    expect(text).toContain('研究中：先確認要整理的月份（步驟 1）');
  });
  it('leaves the question out once the answer stream has ended', () => {
    const html = renderMessage({ id: 41, content: '完成', is_user: false, pending_question: pending });
    expect(textOf(html)).not.toContain('需要你的回答');
  });
});
describe('ResearchTraceBlock with subagents', () => {
  it('orders steps by number and names the sub-task of each subagent step', () => {
    const html = renderMessage({
      id: 50,
      content: '完成',
      is_user: false,
      research_trace: [
        { step: 3, tool: 'search_knowledge_base', status: 'success', agent: '子任務 2：國外出差' },
        { step: 2, tool: 'search_knowledge_base', status: 'success', agent: '子任務 1：國內出差' },
        { step: 1, tool: 'delegate_research', status: 'success' },
      ],
    });
    const text = textOf(html);
    const first = text.indexOf('步驟 1：交給子代理平行研究');
    const second = text.indexOf('子任務 1：國內出差');
    const third = text.indexOf('子任務 2：國外出差');
    expect(first).toBeGreaterThan(-1);
    expect(first).toBeLessThan(second);
    expect(second).toBeLessThan(third);
  });
  it('titles the research with the newest running subagent step', () => {
    const html = renderMessage({
      id: 51,
      content: '',
      is_user: false,
      research_trace: [
        { step: 1, tool: 'delegate_research', status: 'running' },
        { step: 2, tool: 'search_knowledge_base', status: 'running', agent: '子任務 1：國內出差', note: '查國內規定' },
      ],
    }, { isStreaming: true });
    expect(textOf(html)).toContain('研究中：查國內規定（步驟 2）');
  });
});