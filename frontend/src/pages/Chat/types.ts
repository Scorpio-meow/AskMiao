import { ChatConnectionOption, ChatMode, Message, Conversation } from '../../services/api';
import type { FileCardInfo } from './ConversationFileCard';
export interface SourceDetail {
  source: string;
  chunk?: number;
  score?: number | null;
  snippet?: string;
  url?: string;
  label?: string;
  citation?: number;
}
export interface ResearchTraceStep {
  step: number;
  tool: string;
  arguments?: unknown;
  output_preview?: unknown;
  duration_seconds?: number;
  status?: 'success' | 'error' | string;
  note?: string;
  agent?: string;
}
export interface SnackbarState {
  open: boolean;
  message: string;
  severity: 'success' | 'info' | 'warning' | 'error';
  key: number;
}
export type ReasoningEffort = 'none' | 'low' | 'medium' | 'high' | 'xhigh' | 'max';
export interface ChatHeaderProps {
  connections: ChatConnectionOption[];
  selectedChoice: string;
  onSelectChoice: (choice: string) => void;
  reasoningEffort: string;
  onSelectReasoningEffort: (effort: string) => void;
  modelsLoading: boolean;
  onRefreshModels: () => void;
  currentConversation: Conversation | null;
  onOpenSidebar?: () => void;
  sidebarOpen?: boolean;
  sidebarId?: string;
  onOpenFiles?: () => void;
}
export interface ChatSidebarProps {
  id: string;
  open: boolean;
  onClose: () => void;
  conversations: Conversation[];
  currentConversation: Conversation | null;
  onSelectConversation: (id: number) => void;
  onNewConversation: () => void;
  onDeleteConversation: (id: number) => void;
  loading: boolean;
  loadError: string | null;
  onRetryLoad: () => void;
}
export interface ChatMessageItemProps {
  message: Message;
  thinkId: number | string;
  isStreaming: boolean;
  entering?: boolean;
  isThinkingOpen: boolean;
  deferRendering: boolean;
  onToggleThinking: (id: number | string) => void;
  onCopyMessage: (text: string) => void;
  onRetry?: (failedMessage: Message) => void;
  deletedFileIds: ReadonlySet<number>;
  onDownloadFile: (file: FileCardInfo) => void;
  onDeleteFile: (file: FileCardInfo) => void;
  onPreviewFile: (file: FileCardInfo) => void;
}
export interface ChatMessageListProps {
  messages: Message[];
  conversationLoading: boolean;
  sending: boolean;
  streamingMessageId: number | null;
  loadingMore: boolean;
  hasMoreMessages: boolean;
  onLoadMore: () => void;
  thinkOpenArr: Record<number | string, boolean>;
  onToggleThinking: (id: number | string) => void;
  onCopyMessage: (text: string) => void;
  onSelectPrompt?: (prompt: string) => void;
  onRetry: (failedMessage: Message) => void;
  deletedFileIds: ReadonlySet<number>;
  onDownloadFile: (file: FileCardInfo) => void;
  onDeleteFile: (file: FileCardInfo) => void;
  onPreviewFile: (file: FileCardInfo) => void;
}
export type { ChatAttachment } from '../../services/api';
import type { ChatAttachment } from '../../services/api';
export interface ChatInputAreaProps {
  value: string;
  onChange: (val: string) => void;
  onSend: () => void;
  onStop: () => void;
  sending: boolean;
  streamingHere: boolean;
  disabled?: boolean;
  attachments?: ChatAttachment[];
  onAddAttachments?: (attachments: ChatAttachment[]) => void;
  onRemoveAttachment?: (index: number) => void;
  onRejectAttachments?: (message: string) => void;
  webSearchAvailable: boolean;
  allowWeb: boolean;
  onToggleAllowWeb: () => void;
  chatMode?: ChatMode;
  onSelectChatMode?: (mode: ChatMode) => void;
}
export interface SourceBadgesProps {
  sources?: string[];
  sourcesDetail?: SourceDetail[];
}
export interface ThinkBlockProps {
  thinkContent: string;
  isOpen: boolean;
  onToggle: () => void;
}
export interface ResearchTraceBlockProps {
  trace: ResearchTraceStep[];
}