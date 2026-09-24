import { useState, useCallback, useEffect, useRef } from 'react';
import api, { chatService, ChatAttachment, Conversation, Message } from '../services/api';
type ResearchStep = NonNullable<Message['research_trace']>[number];
const INITIAL_PAGE_SIZE = 100;
const OLDER_PAGE_SIZE = 50;
const STREAM_INTERRUPTED_MESSAGE = '連線中斷，回答可能不完整，請重新傳送。';
const isAbortError = (err: any) => err?.name === 'CanceledError' || err?.name === 'AbortError';
const getErrorDetail = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' && detail ? detail : fallback;
};
const settleRunningSteps = (trace: ResearchStep[] | undefined): ResearchStep[] | undefined =>
  trace?.map((step) => (step.status === 'running' ? { ...step, status: 'error' } : step));
/** onError：載入或刪除失敗時通知呼叫端顯示訊息（串流失敗則直接標示在該則回覆上） */
export function useChat(onError: (message: string) => void) {
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [conversationsError, setConversationsError] = useState<string | null>(null);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [sending, setSending] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<number | null>(null);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onErrorRef.current = onError;
  });
  const reportError = useCallback((message: string) => {
    onErrorRef.current(message);
  }, []);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messagesOffset, setMessagesOffset] = useState(0);
  const [hasMoreMessages, setHasMoreMessages] = useState(false);
  const loadConversationAbortRef = useRef<AbortController | null>(null);
  const loadConversationsAbortRef = useRef<AbortController | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  // 每次切換或開新對話都會換號；非同步結果回來時用來確認使用者還停在同一個畫面
  const viewTokenRef = useRef(0);
  const fetchConversations = useCallback(async (): Promise<Conversation[]> => {
    loadConversationsAbortRef.current?.abort();
    const abortController = new AbortController();
    loadConversationsAbortRef.current = abortController;
    setConversationsLoading(true);
    setConversationsError(null);
    try {
      const response = await api.get<Conversation[]>('/chat/conversations', {
        signal: abortController.signal
      });
      setConversations(response.data);
      return response.data;
    } catch (err: any) {
      if (isAbortError(err)) {
        return [];
      }
      setConversationsError(getErrorDetail(err, '無法載入對話清單'));
      return [];
    } finally {
      if (loadConversationsAbortRef.current === abortController) {
        loadConversationsAbortRef.current = null;
        setConversationsLoading(false);
      }
    }
  }, []);
  const fetchConversation = useCallback(async (conversationId: number): Promise<Conversation | null> => {
    loadConversationAbortRef.current?.abort();
    const abortController = new AbortController();
    loadConversationAbortRef.current = abortController;
    viewTokenRef.current += 1;
    setConversationLoading(true);
    try {
      const convResp = await api.get<Conversation>(`/chat/conversations/${conversationId}`, {
        signal: abortController.signal
      });
      const msgsResp = await api.get<Message[]>(
        `/chat/conversations/${conversationId}/messages?limit=${INITIAL_PAGE_SIZE}&offset=0`,
        { signal: abortController.signal }
      );
      const fetchedMessages = msgsResp.data || [];
      setCurrentConversation(convResp.data);
      setMessages(fetchedMessages);
      setMessagesOffset(fetchedMessages.length);
      setHasMoreMessages(fetchedMessages.length === INITIAL_PAGE_SIZE);
      return convResp.data;
    } catch (err: any) {
      if (isAbortError(err)) {
        return null;
      }
      reportError(getErrorDetail(err, '無法載入這段對話，請稍後再試'));
      return null;
    } finally {
      if (loadConversationAbortRef.current === abortController) {
        loadConversationAbortRef.current = null;
        setConversationLoading(false);
      }
    }
  }, [reportError]);
  const loadMoreMessages = useCallback(async () => {
    if (!currentConversation || loadingMore || !hasMoreMessages) return;
    const viewToken = viewTokenRef.current;
    setLoadingMore(true);
    try {
      const response = await api.get<Message[]>(
        `/chat/conversations/${currentConversation.id}/messages?limit=${OLDER_PAGE_SIZE}&offset=${messagesOffset}`
      );
      if (viewTokenRef.current !== viewToken) return;
      const olderMessages = response.data || [];
      if (olderMessages.length > 0) {
        setMessages(prev => [...olderMessages, ...prev]);
        setMessagesOffset(prev => prev + olderMessages.length);
      }
      setHasMoreMessages(olderMessages.length === OLDER_PAGE_SIZE);
    } catch (err: any) {
      if (!isAbortError(err)) {
        reportError(getErrorDetail(err, '無法載入更早的訊息'));
      }
    } finally {
      setLoadingMore(false);
    }
  }, [currentConversation, loadingMore, hasMoreMessages, messagesOffset, reportError]);
  const sendChatMessage = useCallback(async (
    content: string,
    selectedModel: string,
    reasoningEffort: string,
    attachments?: ChatAttachment[]
  ) => {
    if (!content.trim() && (!attachments || attachments.length === 0)) return;
    // 一次只處理一個串流
    if (streamAbortRef.current) return;
    const abortController = new AbortController();
    streamAbortRef.current = abortController;
    const viewToken = viewTokenRef.current;
    const userMsgId = Date.now();
    const userMessage: Message = {
      id: userMsgId,
      content,
      is_user: true,
      created_at: new Date().toISOString(),
      attachments: attachments || []
    };
    const botMsgId = userMsgId + 1;
    const botMessage: Message = {
      id: botMsgId,
      content: '',
      is_user: false,
      created_at: new Date().toISOString(),
      model_name: selectedModel,
      reasoning_effort: reasoningEffort,
      research_trace: [],
      sources: [],
      sources_detail: []
    };
    // 只更新這次串流的回覆；找不到代表使用者已切到其他對話，回答仍會由後端儲存
    const updateBotMessage = (update: (message: Message) => Message) => {
      setMessages(prev => {
        const index = prev.findIndex(m => m.id === botMsgId);
        if (index === -1) return prev;
        const next = [...prev];
        next[index] = update(next[index]);
        return next;
      });
    };
    const markInterrupted = () => {
      updateBotMessage(m => ({
        ...m,
        error: STREAM_INTERRUPTED_MESSAGE,
        research_trace: settleRunningSteps(m.research_trace)
      }));
    };
    setMessages(prev => [...prev, userMessage, botMessage]);
    setSending(true);
    setStreamingMessageId(botMsgId);
    let started = false;
    let finished = false;
    // 後端在 start 事件就已建立對話並存下使用者訊息，之後即使出錯或被停止也要同步到畫面上
    let streamConversationId: number | null = currentConversation?.id ?? null;
    try {
      await chatService.sendMessageStream(
        content,
        currentConversation?.id || null,
        selectedModel,
        reasoningEffort,
        (ev) => {
          if (ev.event === 'start') {
            started = true;
            streamConversationId = ev.data?.conversation_id ?? streamConversationId;
          } else if (ev.event === 'step_start') {
            const stepData = ev.data;
            updateBotMessage(m => {
              const currentTrace = m.research_trace || [];
              if (currentTrace.some(s => s.step === stepData.step)) return m;
              return { ...m, research_trace: [...currentTrace, { ...stepData, status: 'running' }] };
            });
          } else if (ev.event === 'step_end') {
            const stepData = ev.data;
            updateBotMessage(m => {
              const currentTrace = m.research_trace || [];
              const updated = currentTrace.map(s => s.step === stepData.step ? { ...s, ...stepData } : s);
              if (!currentTrace.some(s => s.step === stepData.step)) {
                updated.push(stepData);
              }
              return { ...m, research_trace: updated };
            });
          } else if (ev.event === 'token') {
            const token = ev.data?.content || '';
            updateBotMessage(m => ({ ...m, content: (m.content || '') + token }));
          } else if (ev.event === 'sources') {
            updateBotMessage(m => ({
              ...m,
              sources: ev.data?.sources || [],
              sources_detail: ev.data?.sources_detail || []
            }));
          } else if (ev.event === 'done') {
            finished = true;
            const doneData = ev.data;
            updateBotMessage(m => ({
              ...m,
              id: doneData.message_id || m.id,
              content: doneData.answer || m.content,
              sources: doneData.sources || m.sources,
              sources_detail: doneData.sources_detail || m.sources_detail,
              research_trace: doneData.research_trace || m.research_trace
            }));
            streamConversationId = doneData.conversation_id ?? streamConversationId;
          } else if (ev.event === 'error') {
            finished = true;
            updateBotMessage(m => ({
              ...m,
              error: ev.data?.detail || '處理訊息時發生錯誤',
              research_trace: settleRunningSteps(m.research_trace)
            }));
          }
        },
        abortController.signal,
        attachments
      );
      if (!finished) {
        markInterrupted();
      }
    } catch (err: any) {
      if (isAbortError(err)) {
        updateBotMessage(m => ({ ...m, stopped: true, research_trace: settleRunningSteps(m.research_trace) }));
      } else if (!started) {
        // 後端尚未開始處理：移除剛加入的兩則訊息，交由呼叫端把內容放回輸入框
        setMessages(prev => prev.filter(m => m.id !== userMsgId && m.id !== botMsgId));
        throw err;
      } else {
        markInterrupted();
      }
    } finally {
      streamAbortRef.current = null;
      setSending(false);
      setStreamingMessageId(null);
      const conversationId = streamConversationId;
      if (conversationId && conversationId !== currentConversation?.id) {
        fetchConversations().then(fresh => {
          // 使用者已切到其他對話時只更新清單，不把畫面拉回來
          if (viewTokenRef.current !== viewToken) return;
          const found = fresh.find(c => c.id === conversationId);
          if (found) setCurrentConversation(found);
        });
      }
    }
  }, [currentConversation, fetchConversations]);
  const stopGenerating = useCallback(() => {
    streamAbortRef.current?.abort();
  }, []);
  const startNewConversation = useCallback(() => {
    loadConversationAbortRef.current?.abort();
    viewTokenRef.current += 1;
    setCurrentConversation(null);
    setMessages([]);
    setMessagesOffset(0);
    setHasMoreMessages(false);
  }, []);
  const deleteConversation = useCallback(async (conversationId: number): Promise<boolean> => {
    try {
      await chatService.deleteConversation(conversationId);
      setConversations(prev => prev.filter(c => c.id !== conversationId));
      if (currentConversation?.id === conversationId) {
        startNewConversation();
      }
      return true;
    } catch (err: any) {
      reportError(getErrorDetail(err, '刪除對話失敗，請稍後再試'));
      return false;
    }
  }, [currentConversation, startNewConversation, reportError]);
  const isStreamingInView = sending && streamingMessageId !== null && messages.some(m => m.id === streamingMessageId);
  return {
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
    startNewConversation
  };
}
export default useChat;
