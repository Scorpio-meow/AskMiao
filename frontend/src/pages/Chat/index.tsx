import React, { useState, useEffect, useCallback, useRef, useId } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import api, { Conversation, Message } from '../../services/api';
import { useChat } from '../../hooks/useChat';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { copyText } from '../../utils/clipboard';
import { SnackbarState, ModelDetail, ChatAttachment } from './types';
import ChatSidebar from './ChatSidebar';
import ChatHeader from './ChatHeader';
import ChatMessageList from './ChatMessageList';
import ChatInputArea from './ChatInputArea';
import { Snackbar, Alert, ConfirmDialog } from '../../components/ui';
import styles from './Chat.module.css';
const describeSendError = (err: unknown): string => {
  if (err instanceof TypeError) return '無法連線到伺服器，請檢查網路後再試';
  if (err instanceof Error && err.message) return err.message;
  return '請稍後再試';
};
export const ChatPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const sidebarId = useId();
  const [thinkOpenArr, setThinkOpenArr] = useState<Record<number | string, boolean>>({});
  const [newMessage, setNewMessage] = useState('');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [, setModelDetails] = useState<ModelDetail[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [userSelectedModel, setUserSelectedModel] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState<string>('medium');
  const [modelsLoading, setModelsLoading] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState(false);
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
  useDocumentTitle(currentConversation?.title || '聊天');
  const selectedModelRef = useRef(selectedModel);
  const userSelectedModelRef = useRef(userSelectedModel);
  useEffect(() => {
    selectedModelRef.current = selectedModel;
  }, [selectedModel]);
  useEffect(() => {
    userSelectedModelRef.current = userSelectedModel;
  }, [userSelectedModel]);
  const loadAvailableModels = useCallback(async (force = false) => {
    if (!force && (window as any).__tagsLoading) {
      return;
    }
    const normalizeModelList = (list: any[]): string[] => {
      const result: string[] = [];
      list.forEach((item) => {
        if (typeof item === 'string') {
          item.split(',').forEach((sub) => {
            const trimmed = sub.trim();
            if (trimmed && !result.includes(trimmed)) {
              result.push(trimmed);
            }
          });
        }
      });
      return result;
    };
    if (!force) {
      const cached = localStorage.getItem('cached_tags');
      const cacheTime = localStorage.getItem('cached_tags_time');
      if (cached && cacheTime) {
        const age = Date.now() - parseInt(cacheTime, 10);
        if (age < 5 * 60 * 1000) {
          try {
            const cachedData = JSON.parse(cached);
            const cachedModels = normalizeModelList(cachedData.models || []);
            const cachedDetails = cachedData.details || [];
            setAvailableModels(cachedModels);
            setModelDetails(cachedDetails);
            if (!selectedModelRef.current && cachedModels.length > 0) {
              const defaultModel = cachedData.default?.split(',')[0].trim() || cachedModels[0];
              setSelectedModel(defaultModel);
            }
            return;
          } catch (e) {
            console.error('Failed to parse cached models', e);
          }
        }
      }
    }
    (window as any).__tagsLoading = true;
    setModelsLoading(true);
    try {
      const res = await api.get('/chat/models');
      const models = normalizeModelList(res.data?.models || []);
      const details = res.data?.details || [];
      const rawDefault = res.data?.default || (models.length > 0 ? models[0] : '');
      const defaultModel = typeof rawDefault === 'string' ? rawDefault.split(',')[0].trim() : (models[0] || '');
      setAvailableModels(models);
      setModelDetails(details);
      try {
        localStorage.setItem('cached_tags', JSON.stringify({ ...res.data, models, default: defaultModel }));
        localStorage.setItem('cached_tags_time', Date.now().toString());
      } catch (e) {
        console.warn('Failed to save models to localStorage', e);
      }
      if (!userSelectedModelRef.current && !selectedModelRef.current) {
        setSelectedModel(defaultModel);
      } else if (selectedModelRef.current && !models.includes(selectedModelRef.current)) {
        setSelectedModel(defaultModel);
      }
    } catch (err) {
      console.warn('載入可用模型失敗', err);
      setAvailableModels([]);
      setModelDetails([]);
      if (!userSelectedModelRef.current) {
        setSelectedModel('');
      }
    } finally {
      (window as any).__tagsLoading = false;
      setModelsLoading(false);
    }
  }, []);
  const handleSelectModel = (model: string) => {
    setSelectedModel(model);
    setUserSelectedModel(true);
  };
  const handleToggleThinking = (id: number | string) => {
    setThinkOpenArr((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };
  const handleCopyMessage = async (text: string) => {
    const copied = await copyText(text);
    showSnackbar(copied ? '已複製內容至剪貼簿' : '無法自動複製，請手動選取文字後複製', copied ? 'success' : 'error');
  };
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const handleSend = async () => {
    if (sending) return;
    if (!newMessage.trim() && attachments.length === 0) return;
    const toSend = newMessage;
    const toSendAttachments = [...attachments];
    setNewMessage('');
    setAttachments([]);
    try {
      await sendChatMessage(toSend, selectedModel, reasoningEffort, toSendAttachments);
    } catch (err) {
      // 訊息沒送出去：把內容放回輸入框，使用者已開始輸入新內容時則不覆蓋
      setNewMessage((current) => current || toSend);
      setAttachments((current) => (current.length > 0 ? current : toSendAttachments));
      showSnackbar(`訊息沒有送出：${describeSendError(err)}`, 'error');
    }
  };
  const handleRetry = (failedMessage: Message) => {
    const index = messages.indexOf(failedMessage);
    const question = messages.slice(0, index).reverse().find((m) => m.is_user);
    if (!question || sending) return;
    sendChatMessage(question.content, selectedModel, reasoningEffort, question.attachments).catch((err) => {
      showSnackbar(`訊息沒有送出：${describeSendError(err)}`, 'error');
    });
  };
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
          availableModels={availableModels}
          selectedModel={selectedModel}
          onSelectModel={handleSelectModel}
          reasoningEffort={reasoningEffort}
          onSelectReasoningEffort={setReasoningEffort}
          modelsLoading={modelsLoading}
          onRefreshModels={() => loadAvailableModels(true)}
          currentConversation={currentConversation}
          onOpenSidebar={() => setMobileSidebarOpen(true)}
          sidebarOpen={mobileSidebarOpen}
          sidebarId={sidebarId}
        />
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
          onRetry={handleRetry}
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
        />
      </div>
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
