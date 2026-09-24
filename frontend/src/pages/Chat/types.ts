import { Message, Conversation } from '../../services/api';
export interface SourceDetail {
  source: string;
  chunk?: number;
  score?: number | null;
  snippet?: string;
  url?: string;
  // 答案中 [n] 引用對應的編號；舊訊息沒有此欄位
  citation?: number;
}
export interface ResearchTraceStep {
  step: number;
  tool: string;
  arguments?: Record<string, any>;
  output_preview?: string;
  duration_seconds?: number;
  status?: 'success' | 'error' | string;
}
export interface ModelDetail {
  name: string;
  description?: string;
  context_window?: number;
  pricing?: string;
}
export interface SnackbarState {
  open: boolean;
  message: string;
  severity: 'success' | 'info' | 'warning' | 'error';
  /** 每則通知的序號，讓新通知重新開始自動關閉的計時 */
  key: number;
}
export type ReasoningEffort = 'none' | 'low' | 'medium' | 'high' | 'xhigh';
export interface ChatHeaderProps {
  availableModels: string[];
  selectedModel: string;
  onSelectModel: (model: string) => void;
  reasoningEffort: string;
  onSelectReasoningEffort: (effort: string) => void;
  modelsLoading: boolean;
  onRefreshModels: () => void;
  currentConversation: Conversation | null;
  onOpenSidebar?: () => void;
  sidebarOpen?: boolean;
  sidebarId?: string;
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
  isStreaming: boolean;
  isThinkingOpen: boolean;
  onToggleThinking: () => void;
  onCopyMessage: (text: string) => void;
  onRetry?: () => void;
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
}
export type { ChatAttachment } from '../../services/api';
import type { ChatAttachment } from '../../services/api';
export interface ChatInputAreaProps {
  value: string;
  onChange: (val: string) => void;
  onSend: () => void;
  onStop: () => void;
  /** 有任何回答正在產生 */
  sending: boolean;
  /** 正在產生的回答就在目前這段對話裡 */
  streamingHere: boolean;
  disabled?: boolean;
  attachments?: ChatAttachment[];
  onAddAttachments?: (attachments: ChatAttachment[]) => void;
  onRemoveAttachment?: (index: number) => void;
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
