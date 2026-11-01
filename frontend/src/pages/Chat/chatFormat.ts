import type { ChatAttachment, Conversation, EnabledSkill, Message } from '../../services/api';
import { parseServerDate } from '../../utils/serverDate';
const timeFormatter = new Intl.DateTimeFormat('zh-TW', { hour: '2-digit', minute: '2-digit' });
const monthDayTimeFormatter = new Intl.DateTimeFormat('zh-TW', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
const fullDateTimeFormatter = new Intl.DateTimeFormat('zh-TW', { year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
const SKILL_COMMAND_PATTERN = /^\/([a-z0-9-]*)$/;
const DAY_MS = 24 * 60 * 60 * 1000;
const RECENT_DAYS = 7;
const CODE_EXTENSIONS = ['js', 'ts', 'jsx', 'tsx', 'py', 'json', 'html', 'css', 'sql'];
export const formatMessageTime = (value: string, now: Date) => {
  const date = parseServerDate(value);
  if (Number.isNaN(date.getTime())) return null;
  const label =
    date.toDateString() === now.toDateString()
      ? timeFormatter.format(date)
      : date.getFullYear() === now.getFullYear()
        ? monthDayTimeFormatter.format(date)
        : fullDateTimeFormatter.format(date);
  return { label, full: fullDateTimeFormatter.format(date) };
};
export const splitThinkContent = (rawContent: string): { thinkContent: string | null; mainContent: string } => {
  const thinkMatch = rawContent.match(/<think>([\s\S]*?)<\/think>/);
  if (thinkMatch) {
    return {
      thinkContent: thinkMatch[1].trim(),
      mainContent: rawContent.replace(/<think>[\s\S]*?<\/think>/, '').trim(),
    };
  }
  return { thinkContent: null, mainContent: rawContent };
};
export const messageKey = (id: number | undefined, index: number) => (id !== undefined ? `id-${id}` : `index-${index}`);
export const isImageAttachment = (attachment: Pick<ChatAttachment, 'file_type' | 'data_url'>): boolean =>
  Boolean(attachment.file_type?.startsWith('image/')) || Boolean(attachment.data_url?.startsWith('data:image/'));
export const formatFileSize = (bytes?: number): string => {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};
export type AttachmentKind = 'pdf' | 'doc' | 'sheet' | 'slide' | 'code' | 'other';
export const describeAttachmentType = (filename: string): { kind: AttachmentKind; label: string } => {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (ext === 'pdf') return { kind: 'pdf', label: 'PDF' };
  if (['doc', 'docx'].includes(ext)) return { kind: 'doc', label: 'DOC' };
  if (['xls', 'xlsx', 'csv'].includes(ext)) return { kind: 'sheet', label: ext.toUpperCase() };
  if (['ppt', 'pptx'].includes(ext)) return { kind: 'slide', label: 'PPT' };
  if (CODE_EXTENSIONS.includes(ext)) return { kind: 'code', label: ext.toUpperCase() };
  return { kind: 'other', label: ext ? ext.toUpperCase() : 'FILE' };
};
export const isImeComposition = (event: { isComposing: boolean; keyCode: number }): boolean =>
  event.isComposing || event.keyCode === 229;
export const skillSuggestionsFor = (
  value: string,
  skills: EnabledSkill[],
  dismissedCommand: string | null,
  limit: number
): EnabledSkill[] => {
  const commandMatch = SKILL_COMMAND_PATTERN.exec(value);
  if (!commandMatch || dismissedCommand === value) return [];
  return skills.filter((skill) => skill.name.startsWith(commandMatch[1])).slice(0, limit);
};
export const findRetryQuestion = (messages: Message[], failedMessage: Message): Message | undefined => {
  const index = messages.indexOf(failedMessage);
  return messages.slice(0, index).reverse().find((message) => message.is_user);
};
export const completionAnnouncement = (lastMessage: Message | undefined): string => {
  if (!lastMessage || lastMessage.is_user) return '';
  if (lastMessage.error) return `回答失敗：${lastMessage.error}`;
  if (lastMessage.stopped) return '已停止產生回答';
  return 'AI 已完成回答';
};
export interface ConversationGroup {
  key: string;
  label: string;
  conversations: Conversation[];
}
const startOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
const conversationBucket = (conversation: Conversation, todayStart: number): { key: string; label: string } => {
  const updated = parseServerDate(conversation.updated_at);
  if (Number.isNaN(updated.getTime())) return { key: 'older', label: '更早' };
  const daysAgo = Math.round((todayStart - startOfDay(updated)) / DAY_MS);
  if (daysAgo <= 0) return { key: 'today', label: '今天' };
  if (daysAgo === 1) return { key: 'yesterday', label: '昨天' };
  if (daysAgo < RECENT_DAYS) return { key: 'week', label: `過去 ${RECENT_DAYS} 天` };
  return { key: 'older', label: '更早' };
};
export const groupConversations = (conversations: Conversation[], now: Date): ConversationGroup[] => {
  const todayStart = startOfDay(now);
  const groups = new Map<string, ConversationGroup>();
  for (const conversation of conversations) {
    const bucket = conversationBucket(conversation, todayStart);
    const group = groups.get(bucket.key);
    if (group) {
      group.conversations.push(conversation);
    } else {
      groups.set(bucket.key, { ...bucket, conversations: [conversation] });
    }
  }
  return [...groups.values()];
};
