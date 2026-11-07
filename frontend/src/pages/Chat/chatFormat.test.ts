import { describe, expect, it } from 'vitest';
import type { Conversation, Message } from '../../services/api';
import {
  completionAnnouncement,
  describeAttachmentType,
  findRetryQuestion,
  formatFileSize,
  formatMessageTime,
  groupConversations,
  isImageAttachment,
  isImeComposition,
  messageKey,
  skillSuggestionsFor,
  splitThinkContent,
} from './chatFormat';
const conversation = (id: number, updated_at: string): Conversation => ({
  id,
  title: `對話 ${id}`,
  created_at: updated_at,
  updated_at,
});
describe('formatMessageTime', () => {
  const now = new Date(2026, 10, 2, 15, 0);
  it('shows only the time for messages sent today', () => {
    const sent = new Date(2026, 10, 2, 9, 5);
    expect(formatMessageTime(sent.toISOString(), now)?.label).toBe(
      new Intl.DateTimeFormat('zh-TW', { hour: '2-digit', minute: '2-digit' }).format(sent)
    );
  });
  it('adds the date for older messages and the year for other years', () => {
    const lastMonth = new Date(2026, 9, 20, 9, 5);
    const lastYear = new Date(2025, 9, 20, 9, 5);
    expect(formatMessageTime(lastMonth.toISOString(), now)?.label).toBe(
      new Intl.DateTimeFormat('zh-TW', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(lastMonth)
    );
    expect(formatMessageTime(lastYear.toISOString(), now)?.label).toBe(formatMessageTime(lastYear.toISOString(), now)?.full);
  });
  it('treats server times without a time zone as UTC and rejects invalid values', () => {
    expect(formatMessageTime('2026-11-02T01:00:00', now)?.full).toBe(formatMessageTime('2026-11-02T01:00:00Z', now)?.full);
    expect(formatMessageTime('not a date', now)).toBeNull();
  });
});
describe('splitThinkContent', () => {
  it('separates the first think block from the answer', () => {
    expect(splitThinkContent('<think>\n先查文件\n</think>\n\n答案 [1]')).toEqual({ thinkContent: '先查文件', mainContent: '答案 [1]' });
  });
  it('keeps content without a think block untouched', () => {
    expect(splitThinkContent('  答案  ')).toEqual({ thinkContent: null, mainContent: '  答案  ' });
  });
});
describe('attachments', () => {
  it('labels file types the same way as before', () => {
    expect(describeAttachmentType('報告.PDF')).toEqual({ kind: 'pdf', label: 'PDF' });
    expect(describeAttachmentType('合約.docx')).toEqual({ kind: 'doc', label: 'DOC' });
    expect(describeAttachmentType('名單.csv')).toEqual({ kind: 'sheet', label: 'CSV' });
    expect(describeAttachmentType('簡報.pptx')).toEqual({ kind: 'slide', label: 'PPT' });
    expect(describeAttachmentType('main.tsx')).toEqual({ kind: 'code', label: 'TSX' });
    expect(describeAttachmentType('notes.md')).toEqual({ kind: 'other', label: 'MD' });
    expect(describeAttachmentType('')).toEqual({ kind: 'other', label: 'FILE' });
  });
  it('formats sizes and recognises images by type or data URL', () => {
    expect(formatFileSize(undefined)).toBe('');
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(2048)).toBe('2.0 KB');
    expect(formatFileSize(3 * 1024 * 1024)).toBe('3.0 MB');
    expect(isImageAttachment({ file_type: 'image/png' })).toBe(true);
    expect(isImageAttachment({ file_type: 'application/octet-stream', data_url: 'data:image/webp;base64,AA' })).toBe(true);
    expect(isImageAttachment({ file_type: 'application/pdf', data_url: 'data:application/pdf;base64,AA' })).toBe(false);
  });
});
describe('isImeComposition', () => {
  it('ignores Enter while an input method is composing', () => {
    expect(isImeComposition({ isComposing: true, keyCode: 13 })).toBe(true);
    expect(isImeComposition({ isComposing: false, keyCode: 229 })).toBe(true);
    expect(isImeComposition({ isComposing: false, keyCode: 13 })).toBe(false);
  });
});
describe('skillSuggestionsFor', () => {
  const skills = [
    { name: 'release-notes', description: '整理發行說明' },
    { name: 'report', description: '產生報告' },
    { name: 'translate', description: '翻譯' },
  ];
  it('suggests skills only for a bare slash command', () => {
    expect(skillSuggestionsFor('/re', skills, null, 8).map((s) => s.name)).toEqual(['release-notes', 'report']);
    expect(skillSuggestionsFor('/', skills, null, 2).map((s) => s.name)).toEqual(['release-notes', 'report']);
    expect(skillSuggestionsFor('/re 內容', skills, null, 8)).toEqual([]);
    expect(skillSuggestionsFor('請 /re', skills, null, 8)).toEqual([]);
  });
  it('stays closed after Escape until the command changes', () => {
    expect(skillSuggestionsFor('/re', skills, '/re', 8)).toEqual([]);
    expect(skillSuggestionsFor('/rep', skills, '/re', 8).map((s) => s.name)).toEqual(['report']);
  });
});
describe('message helpers', () => {
  const question: Message = { id: 1, content: '第一題', is_user: true };
  const answer: Message = { id: 2, content: '', is_user: false, error: '逾時' };
  const followUp: Message = { id: 3, content: '第二題', is_user: true };
  const failed: Message = { id: 4, content: '', is_user: false, error: '連線中斷' };
  it('retries the closest question before the failed answer', () => {
    const messages = [question, answer, followUp, failed];
    expect(findRetryQuestion(messages, failed)).toBe(followUp);
    expect(findRetryQuestion(messages, answer)).toBe(question);
  });
  it('announces how the last answer ended', () => {
    expect(completionAnnouncement(undefined)).toBe('');
    expect(completionAnnouncement(question)).toBe('');
    expect(completionAnnouncement(failed)).toBe('回答失敗：連線中斷');
    expect(completionAnnouncement({ ...failed, error: undefined, stopped: true })).toBe('已停止產生回答');
    expect(completionAnnouncement({ id: 5, content: '好', is_user: false })).toBe('AI 已完成回答');
  });
  it('builds keys from ids when present', () => {
    expect(messageKey(7, 0)).toBe('id-7');
    expect(messageKey(undefined, 3)).toBe('index-3');
  });
});
describe('groupConversations', () => {
  const now = new Date(2026, 10, 2, 10, 0);
  const at = (days: number, hour: number) => new Date(2026, 10, 2 - days, hour).toISOString();
  it('groups by the last update in the order the server returned', () => {
    const groups = groupConversations([
      conversation(1, at(0, 8)),
      conversation(2, at(1, 23)),
      conversation(3, at(3, 12)),
      conversation(4, at(6, 9)),
      conversation(5, at(7, 9)),
      conversation(6, 'invalid'),
    ], now);
    expect(groups.map((g) => [g.label, g.conversations.map((c) => c.id)])).toEqual([
      ['今天', [1]],
      ['昨天', [2]],
      ['過去 7 天', [3, 4]],
      ['更早', [5, 6]],
    ]);
  });
  it('returns no groups for an empty list', () => {
    expect(groupConversations([], now)).toEqual([]);
  });
});