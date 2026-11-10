import React, { useState, useEffect, useCallback, useMemo, useRef, useId } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { chatService, ChatConnectionOption, ChatMode, Conversation, Message } from '../../services/api';
import { useChat } from '../../hooks/useChat';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { copyText } from '../../utils/clipboard';
import { saveBlob } from '../../utils/saveBlob';
import { describeRequestError } from '../../utils/secureLogger';
import { SnackbarState, ChatAttachment } from './types';
import ChatSidebar from './ChatSidebar';
import ChatHeader, { choiceKey, parseChoice } from './ChatHeader';
import { REASONING_EFFORT_OPTIONS, resolveReasoningEffort } from '../../utils/reasoningEffort';
import ChatMessageList from './ChatMessageList';
import ChatInputArea from './ChatInputArea';
import ConversationFilesDialog from './ConversationFilesDialog';
import FilePreviewPanel from '../../components/FilePreviewPanel';
import type { FileCardInfo } from './ConversationFileCard';
import { findRetryQuestion } from './chatFormat';
import { Snackbar, Alert, ConfirmDialog } from '../../components/ui';
import styles from './Chat.module.css';
const describeSendError = (err: unknown): string => {
  if (err instanceof TypeError) return '無法連線到伺服器，請檢查網路後再試';
  if (err instanceof Error && err.message) return err.message;
  return '請稍後再試';
};
const isNotFound = (err: unknown): boolean => (err as { response?: { status?: number } })?.response?.status === 404;
const MODEL_STORAGE_KEY = 'askmiao_selected_model';
const REASONING_EFFORT_STORAGE_KEY = 'askmiao_reasoning_effort';
const CHAT_MODE_STORAGE_KEY = 'askmiao_chat_mode';
const ALLOW_WEB_STORAGE_KEY = 'askmiao_allow_web';
const readStorage = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};
const writeStorage = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value);
  } catch (e) {
    console.warn('Failed to save preference to localStorage', e);
  }
};
export const ChatPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const sidebarId = useId();
  const [thinkOpenArr, setThinkOpenArr] = useState<Record<number | string, boolean>>({});
  const [newMessage, setNewMessage] = useState('');
  const [connections, setConnections] = useState<ChatConnectionOption[] | null>(null);
  const [selectedChoice, setSelectedChoice] = useState(() => readStorage(MODEL_STORAGE_KEY) || '');
  const [reasoningEffort, setReasoningEffort] = useState<string>(() => {
    const saved = readStorage(REASONING_EFFORT_STORAGE_KEY);
    return REASONING_EFFORT_OPTIONS.some((opt) => opt.value === saved) ? saved! : 'medium';
  });
  const [chatMode, setChatMode] = useState<ChatMode>(() => (readStorage(CHAT_MODE_STORAGE_KEY) === 'agent' ? 'agent' : 'research'));
  const [allowWeb, setAllowWeb] = useState(() => readStorage(ALLOW_WEB_STORAGE_KEY) !== 'false');
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [pendingFileDelete, setPendingFileDelete] = useState<FileCardInfo | null>(null);
  const [preview, setPreview] = useState<{ file: FileCardInfo; conversationId: number | undefined } | null>(null);
  const [deletingFile, setDeletingFile] = useState(false);
  const [removedFileIds, setRemovedFileIds] = useState<ReadonlySet<number>>(() => new Set());
  const [snackbar, setSnackbar] = useState<SnackbarState>({
    open: false,
    message: '',
    severity: 'info',
    key: 0,
  });
  const showSnackbar = useCallback((message: string, severity: SnackbarState['severity']) => {
    setSnackbar((prev) => ({ open: true, message, severity, key: prev.key + 1 }));
  }, []);
  const {
    conversationsLoading,
    conversationsError,
    conversationLoading,
    loadingMore,
    sending,
    isStreamingInView,
    streamingMessageId,
    conversations,
    currentConversation,
    messages,
    hasMoreMessages,
    fetchConversations,
    fetchConversation,
    loadMoreMessages,
    sendChatMessage,
    stopGenerating,
    deleteConversation,
    startNewConversation,
  } = useChat((message) => showSnackbar(message, 'error'));
  const previewFile = preview && preview.conversationId === currentConversation?.id ? preview.file : null;
  const previewSource = useMemo(() => (previewFile ? chatService.conversationFilePreview(previewFile) : null), [previewFile]);
  const openPreview = useCallback((file: FileCardInfo) => {
    setFilesOpen(false);
    setPreview({ file, conversationId: currentConversation?.id });
  }, [currentConversation?.id]);
  useDocumentTitle(currentConversation?.title || '聊天');
  const deletedFileIds = useMemo(() => {
    const ids = new Set(removedFileIds);
    messages.forEach((m) => (m.files || []).forEach((event) => {
      if (event.action === 'deleted') ids.add(event.file.id);
    }));
    return ids;
  }, [messages, removedFileIds]);
  const handleDownloadFile = useCallback(async (file: FileCardInfo) => {
    try {
      saveBlob(await chatService.downloadConversationFile(file.id), file.filename);
    } catch (err) {
      if (isNotFound(err)) {
        setRemovedFileIds((prev) => new Set(prev).add(file.id));
        showSnackbar(`「${file.filename}」已被刪除`, 'error');
      } else {
        showSnackbar(`無法下載「${file.filename}」，請稍後再試`, 'error');
      }
    }
  }, [showSnackbar]);
  const handleConfirmFileDelete = async () => {
    if (!pendingFileDelete) return;
    const file = pendingFileDelete;
    setDeletingFile(true);
    try {
      await chatService.deleteConversationFile(file.id);
      setRemovedFileIds((prev) => new Set(prev).add(file.id));
      showSnackbar(`已刪除「${file.filename}」`, 'success');
    } catch (err) {
      if (isNotFound(err)) {
        setRemovedFileIds((prev) => new Set(prev).add(file.id));
      }
      showSnackbar(isNotFound(err) ? `「${file.filename}」已被刪除` : `無法刪除「${file.filename}」，請稍後再試`, 'error');
    } finally {
      setDeletingFile(false);
      setPendingFileDelete(null);
    }
  };
  const selectedChoiceRef = useRef(selectedChoice);
  useEffect(() => {
    selectedChoiceRef.current = selectedChoice;
  }, [selectedChoice]);
  const loadAvailableModels = useCallback(async () => {
    setModelsLoading(true);
    try {
      const options = await chatService.getChatOptions();
      const choices = options.connections.flatMap((connection) => connection.models.map((model) => choiceKey(connection.id, model)));
      setConnections(options.connections);
      setWebSearchEnabled(options.web_search_enabled);
      if (!choices.includes(selectedChoiceRef.current)) {
        setSelectedChoice(choices[0] || '');
      }
    } catch (err) {
      console.warn('載入可用模型失敗', describeRequestError(err));
      setConnections([]);
    } finally {
      setModelsLoading(false);
    }
  }, []);
  const handleSelectChoice = (choice: string) => {
    setSelectedChoice(choice);
    writeStorage(MODEL_STORAGE_KEY, choice);
  };
  const availableChoices = (connections || []).flatMap((connection) => connection.models.map((model) => choiceKey(connection.id, model)));
  const selectedModel = availableChoices.includes(selectedChoice) ? parseChoice(selectedChoice) : null;
  const effectiveReasoningEffort = resolveReasoningEffort(selectedModel?.model || '', reasoningEffort);
  const handleSelectChatMode = (mode: ChatMode) => {
    setChatMode(mode);
    writeStorage(CHAT_MODE_STORAGE_KEY, mode);
  };
  const handleToggleAllowWeb = () => {
    setAllowWeb(!allowWeb);
    writeStorage(ALLOW_WEB_STORAGE_KEY, String(!allowWeb));
  };
  const handleSelectReasoningEffort = (effort: string) => {
    setReasoningEffort(effort);
    writeStorage(REASONING_EFFORT_STORAGE_KEY, effort);
  };
  const handleToggleThinking = useCallback((id: number | string) => {
    setThinkOpenArr((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  }, []);
  const handleCopyMessage = useCallback(async (text: string) => {
    const copied = await copyText(text);
    showSnackbar(copied ? '已複製內容至剪貼簿' : '無法自動複製，請手動選取文字後複製', copied ? 'success' : 'error');
  }, [showSnackbar]);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const handleSend = async () => {
    if (sending) return;
    if (!newMessage.trim() && attachments.length === 0) return;
    if (!selectedModel) {
      showSnackbar('請先選擇模型；尚未設定 API 連線時，請到「個人資料」新增', 'error');
      return;
    }
    const toSend = newMessage;
    const toSendAttachments = [...attachments];
    setNewMessage('');
    setAttachments([]);
    try {
      await sendChatMessage(toSend, selectedModel, effectiveReasoningEffort, chatMode, allowWeb, toSendAttachments);
    } catch (err) {
      setNewMessage((current) => current || toSend);
      setAttachments((current) => (current.length > 0 ? current : toSendAttachments));
      showSnackbar(`訊息沒有送出：${describeSendError(err)}`, 'error');
    }
  };
  const handleRetry = (failedMessage: Message) => {
    const question = findRetryQuestion(messages, failedMessage);
    if (!question || sending || !selectedModel) return;
    sendChatMessage(question.content, selectedModel, effectiveReasoningEffort, chatMode, allowWeb, question.attachments).catch((err) => {
      showSnackbar(`訊息沒有送出：${describeSendError(err)}`, 'error');
    });
  };
  const retryRef = useRef(handleRetry);
  useEffect(() => {
    retryRef.current = handleRetry;
  });
  const handleStableRetry = useCallback((failedMessage: Message) => retryRef.current(failedMessage), []);
  const handleSelectConversation = useCallback(async (id: number) => {
    await fetchConversation(id);
  }, [fetchConversation]);
  const handleRequestDelete = (id: number) => {
    setPendingDelete(conversations.find((c) => c.id === id) ?? null);
  };
  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    const ok = await deleteConversation(pendingDelete.id);
    setDeleting(false);
    setPendingDelete(null);
    if (ok) {
      showSnackbar('對話已刪除', 'success');
    }
  };
  useEffect(() => {
    queueMicrotask(() => {
      loadAvailableModels();
      fetchConversations();
    });
  }, [loadAvailableModels, fetchConversations]);
  useEffect(() => {
    if (location.state?.prefillPrompt) {
      setNewMessage(location.state.prefillPrompt);
      navigate(location.pathname, { replace: true, state: {} });
    } else if (location.state?.conversationId) {
      const conversationId = location.state.conversationId;
      queueMicrotask(() => {
        handleSelectConversation(conversationId);
      });
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [location, navigate, handleSelectConversation]);
  return (
    <div className={styles.chatContainer}>
      <ChatSidebar
        id={sidebarId}
        open={mobileSidebarOpen}
        onClose={() => setMobileSidebarOpen(false)}
        conversations={conversations}
        currentConversation={currentConversation}
        onSelectConversation={handleSelectConversation}
        onNewConversation={startNewConversation}
        onDeleteConversation={handleRequestDelete}
        loading={conversationsLoading}
        loadError={conversationsError}
        onRetryLoad={fetchConversations}
      />
      <div className={styles.mainArea}>
        <ChatHeader
          connections={connections || []}
          selectedChoice={selectedChoice}
          onSelectChoice={handleSelectChoice}
          reasoningEffort={effectiveReasoningEffort}
          onSelectReasoningEffort={handleSelectReasoningEffort}
          chatMode={chatMode}
          onSelectChatMode={handleSelectChatMode}
          modelsLoading={modelsLoading}
          onRefreshModels={loadAvailableModels}
          currentConversation={currentConversation}
          onOpenSidebar={() => setMobileSidebarOpen(true)}
          sidebarOpen={mobileSidebarOpen}
          sidebarId={sidebarId}
          onOpenFiles={currentConversation ? () => setFilesOpen(true) : undefined}
        />
        {connections?.length === 0 && (
          <Alert severity="info" className={styles.noModelsNotice}>
            這個帳號還沒有可用的 AI 模型。請到<Link to="/profile">個人資料</Link>新增自己的 API 連線，或請管理員開放共用連線給你。
          </Alert>
        )}
        <ChatMessageList
          messages={messages}
          conversationLoading={conversationLoading}
          sending={sending}
          streamingMessageId={streamingMessageId}
          loadingMore={loadingMore}
          hasMoreMessages={hasMoreMessages}
          onLoadMore={loadMoreMessages}
          thinkOpenArr={thinkOpenArr}
          onToggleThinking={handleToggleThinking}
          onCopyMessage={handleCopyMessage}
          onSelectPrompt={setNewMessage}
          onRetry={handleStableRetry}
          deletedFileIds={deletedFileIds}
          onDownloadFile={handleDownloadFile}
          onDeleteFile={setPendingFileDelete}
          onPreviewFile={openPreview}
        />
        <ChatInputArea
          value={newMessage}
          onChange={setNewMessage}
          onSend={handleSend}
          onStop={stopGenerating}
          sending={sending}
          streamingHere={isStreamingInView}
          attachments={attachments}
          onAddAttachments={(newAtts) => setAttachments((prev) => [...prev, ...newAtts])}
          onRemoveAttachment={(idx) => setAttachments((prev) => prev.filter((_, i) => i !== idx))}
          onRejectAttachments={(message) => showSnackbar(message, 'error')}
          webSearchAvailable={webSearchEnabled}
          allowWeb={allowWeb}
          onToggleAllowWeb={handleToggleAllowWeb}
        />
      </div>
      {previewFile && previewSource && (
        <FilePreviewPanel
          key={previewFile.id}
          placement="split"
          source={previewSource}
          onClose={() => setPreview(null)}
          onDownload={() => handleDownloadFile(previewFile)}
        />
      )}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="刪除這段對話？"
        description={`「${pendingDelete?.title || '未命名對話'}」的所有訊息都會被刪除，刪除後無法復原。`}
        confirmLabel="刪除"
        destructive
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
      {filesOpen && currentConversation && (
        <ConversationFilesDialog
          conversationId={currentConversation.id}
          deletedFileIds={deletedFileIds}
          onClose={() => setFilesOpen(false)}
          onDownload={handleDownloadFile}
          onDelete={setPendingFileDelete}
          onPreview={openPreview}
        />
      )}
      <ConfirmDialog
        open={Boolean(pendingFileDelete)}
        title="刪除這個檔案？"
        description={`「${pendingFileDelete?.filename || ''}」會從這個對話中刪除，刪除後無法復原；同一檔案的其他版本不受影響。`}
        confirmLabel="刪除"
        destructive
        loading={deletingFile}
        onConfirm={handleConfirmFileDelete}
        onCancel={() => setPendingFileDelete(null)}
      />
      <Snackbar
        key={snackbar.key}
        open={snackbar.open}
        autoHideDuration={snackbar.severity === 'error' ? 6000 : 3000}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
      >
        <Alert
          onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
          severity={snackbar.severity}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </div>
  );
};
export default ChatPage;