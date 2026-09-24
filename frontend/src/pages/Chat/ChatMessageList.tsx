import React, { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { ChatMessageListProps } from './types';
import ChatMessageItem from './ChatMessageItem';
import { Button, Spinner, Chip, Icon } from '../../components/ui';
import styles from './ChatMessageList.module.css';
// 距離底部在這個範圍內視為「正在看最新訊息」，新內容出現時才自動捲動
const NEAR_BOTTOM_THRESHOLD_PX = 80;
const SUGGESTED_PROMPTS = [
  '請幫我分析並總結文件的核心重點',
  '如何結合知識庫與網路搜尋進行自主研究？',
  '請解釋大型語言模型與 RAG 技術的運作原理',
  '幫我撰寫一份專案規劃與技術選型建議',
];
const messageKey = (id: number | undefined, index: number) => (id !== undefined ? `id-${id}` : `index-${index}`);
export const ChatMessageList: React.FC<ChatMessageListProps> = ({
  messages,
  conversationLoading,
  sending,
  streamingMessageId,
  loadingMore,
  hasMoreMessages,
  onLoadMore,
  thinkOpenArr,
  onToggleThinking,
  onCopyMessage,
  onSelectPrompt,
  onRetry,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showJumpButton, setShowJumpButton] = useState(false);
  const prependSnapshotRef = useRef<{ scrollHeight: number; scrollTop: number } | null>(null);
  const previousFirstKeyRef = useRef<string | undefined>(undefined);
  const previousCountRef = useRef(0);
  const previousScrollHeightRef = useRef(0);
  const [previousSending, setPreviousSending] = useState(sending);
  const [announcement, setAnnouncement] = useState('');
  const isEmpty = messages.length === 0;
  const firstMessageKey = messages.length > 0 ? messageKey(messages[0].id, 0) : undefined;
  const [jumpButtonKey, setJumpButtonKey] = useState(firstMessageKey);
  // 換對話時先隱藏「回到最新訊息」；之後由捲動事件重新判斷
  if (jumpButtonKey !== firstMessageKey) {
    setJumpButtonKey(firstMessageKey);
    setShowJumpButton(false);
  }
  // 回答結束時才更新播報內容（完成、失敗或停止），不播報「產生中」這類過渡狀態
  if (previousSending !== sending) {
    setPreviousSending(sending);
    const lastMessage = messages[messages.length - 1];
    if (sending || !lastMessage || lastMessage.is_user) {
      setAnnouncement('');
    } else if (lastMessage.error) {
      setAnnouncement(`回答失敗：${lastMessage.error}`);
    } else if (lastMessage.stopped) {
      setAnnouncement('已停止產生回答');
    } else {
      setAnnouncement('AI 已完成回答');
    }
  }
  // 只捲動 DOM；「回到最新訊息」按鈕的顯示由捲動事件更新
  const scrollToBottom = useCallback((behavior: ScrollBehavior) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
  }, []);
  const updateJumpButton = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_THRESHOLD_PX;
    setShowJumpButton(!nearBottom);
  }, []);
  const handleLoadMore = () => {
    const el = scrollRef.current;
    if (el) {
      prependSnapshotRef.current = { scrollHeight: el.scrollHeight, scrollTop: el.scrollTop };
    }
    onLoadMore();
  };
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const previousCount = previousCountRef.current;
    const previousScrollHeight = previousScrollHeightRef.current;
    const firstKeyChanged = firstMessageKey !== previousFirstKeyRef.current;
    previousFirstKeyRef.current = firstMessageKey;
    previousCountRef.current = messages.length;
    const snapshot = prependSnapshotRef.current;
    if (snapshot && firstKeyChanged && messages.length > previousCount) {
      // 載入更早的訊息後維持原本看到的位置
      prependSnapshotRef.current = null;
      el.scrollTop = snapshot.scrollTop + (el.scrollHeight - snapshot.scrollHeight);
    } else {
      if (snapshot && !loadingMore) {
        prependSnapshotRef.current = null;
      }
      const lastMessage = messages[messages.length - 1];
      const userJustSent = messages.length > previousCount && lastMessage?.id === streamingMessageId;
      // 以更新前的內容高度和目前的捲動位置判斷使用者原本是否在看最新內容，
      // 不依賴 scroll 事件（新 token 可能在使用者往上捲、但 scroll 事件還沒觸發前就先渲染）
      const wasNearBottom = previousScrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_THRESHOLD_PX;
      if (firstKeyChanged || userJustSent) {
        // 換了一段對話，或使用者剛送出訊息：直接到最底
        scrollToBottom('auto');
      } else if (wasNearBottom) {
        el.scrollTop = el.scrollHeight;
      }
    }
    previousScrollHeightRef.current = el.scrollHeight;
    // 內容變多但使用者不在底部時不會有 scroll 事件，下一個畫格再更新「回到最新訊息」按鈕
    const frame = requestAnimationFrame(updateJumpButton);
    return () => cancelAnimationFrame(frame);
  }, [messages, firstMessageKey, streamingMessageId, loadingMore, scrollToBottom, updateJumpButton]);
  return (
    <div className={styles.wrapper}>
      <div
        ref={scrollRef}
        className={styles.container}
        onScroll={updateJumpButton}
        aria-busy={conversationLoading || undefined}
      >
        {hasMoreMessages && (
          <div className={styles.loadMoreContainer}>
            <Button
              size="sm"
              variant="outline"
              onClick={handleLoadMore}
              disabled={loadingMore}
              startIcon={loadingMore ? <Spinner size={14} /> : undefined}
            >
              {loadingMore ? '正在載入更早訊息...' : '載入更早訊息'}
            </Button>
          </div>
        )}
        {isEmpty && conversationLoading ? (
          <div className={styles.centerState}>
            <Spinner size={24} color="var(--color-primary)" />
            <span className={styles.loadingText}>正在載入對話...</span>
          </div>
        ) : isEmpty ? (
          <div className={styles.emptyContainer}>
            <div className={styles.emptyCard}>
              <div className={styles.emptyIcon}>
                <Icon name="bot" size={48} color="var(--color-primary)" />
              </div>
              <h2 className={styles.emptyTitle}>歡迎使用智慧知識庫對話</h2>
              <p className={styles.emptyDesc}>
                我是您的智慧知識助理。您可以詢問知識庫文件、技術指引、專案流程或任何即時資訊問題。
              </p>
              <div className={styles.suggestPrompts}>
                <span className={styles.suggestTitle} id="suggested-prompts-title">常見問題提示：</span>
                <div className={styles.suggestList} role="group" aria-labelledby="suggested-prompts-title">
                  {SUGGESTED_PROMPTS.map((prompt) => (
                    <Chip
                      key={prompt}
                      icon={<Icon name="chat" size={14} />}
                      label={prompt}
                      size="sm"
                      variant="outlined"
                      wrap
                      onClick={() => {
                        if (onSelectPrompt) {
                          onSelectPrompt(prompt);
                        } else {
                          onCopyMessage(prompt);
                        }
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg, index) => {
            const thinkId = msg.id ?? index;
            return (
              <ChatMessageItem
                key={`${msg.is_user ? 'user' : 'assistant'}-${messageKey(msg.id, index)}`}
                message={msg}
                isStreaming={msg.id !== undefined && msg.id === streamingMessageId}
                isThinkingOpen={Boolean(thinkOpenArr[thinkId])}
                onToggleThinking={() => onToggleThinking(thinkId)}
                onCopyMessage={onCopyMessage}
                onRetry={msg.error && !sending ? () => onRetry(msg) : undefined}
              />
            );
          })
        )}
      </div>
      {!isEmpty && conversationLoading && (
        <div className={styles.loadingOverlay}>
          <Spinner size={20} color="var(--color-primary)" />
          <span className={styles.loadingText}>正在載入對話...</span>
        </div>
      )}
      {showJumpButton && !isEmpty && (
        <button type="button" className={styles.jumpButton} onClick={() => scrollToBottom('smooth')}>
          <Icon name="arrow-down" size={16} />
          <span>{sending ? '最新回答' : '回到最新訊息'}</span>
        </button>
      )}
      <div className="sr-only" role="status" aria-live="polite">
        {announcement}
      </div>
    </div>
  );
};
export default ChatMessageList;
