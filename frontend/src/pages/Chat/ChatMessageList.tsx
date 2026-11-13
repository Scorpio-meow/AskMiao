import React, { useCallback, useId, useLayoutEffect, useRef, useState } from 'react';
import { ChatMessageListProps } from './types';
import ChatMessageItem from './ChatMessageItem';
import { approvalHeadline, completionAnnouncement, messageKey } from './chatFormat';
import { Button, Spinner, Icon } from '../../components/ui';
import markUrl from '../../assets/brand/askmiao-mark.png';
import styles from './ChatMessageList.module.css';
const NEAR_BOTTOM_THRESHOLD_PX = 80;
const EAGER_RENDER_TAIL = 6;
const SUGGESTED_PROMPTS = [
  '請幫我分析並總結文件的核心重點',
  '如何結合知識庫與網路搜尋進行自主研究？',
  '請解釋大型語言模型與 RAG 技術的運作原理',
  '幫我撰寫一份專案規劃與技術選型建議',
];
const SKELETON_BLOCKS: Array<{ kind: 'user' | 'assistant'; lines: number; short?: boolean }> = [
  { kind: 'user', lines: 1 },
  { kind: 'assistant', lines: 3 },
  { kind: 'user', lines: 1, short: true },
  { kind: 'assistant', lines: 2 },
];
const ThreadSkeleton: React.FC = () => (
  <div className={styles.skeleton} aria-hidden="true">
    {SKELETON_BLOCKS.map((block, blockIndex) => (
      <div key={blockIndex} className={block.kind === 'user' ? styles.skeletonUser : styles.skeletonAssistant}>
        {Array.from({ length: block.lines }, (_, lineIndex) => (
          <span
            key={lineIndex}
            className={block.kind === 'user' ? `${styles.skeletonBubble} ${block.short ? styles.skeletonBubbleShort : ''}` : styles.skeletonLine}
            style={{ '--i': blockIndex * 2 + lineIndex } as React.CSSProperties}
          />
        ))}
      </div>
    ))}
  </div>
);
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
  deletedFileIds,
  onDownloadFile,
  onDeleteFile,
  onPreviewFile,
}) => {
  const promptsTitleId = useId();
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
  const streamingMessage = streamingMessageId !== null ? messages.find((m) => m.id === streamingMessageId) : undefined;
  const pendingApproval = streamingMessage?.pending_approval ?? null;
  const pendingApprovalId = pendingApproval?.approval_id ?? null;
  const [announcedApprovalId, setAnnouncedApprovalId] = useState(pendingApprovalId);
  const pendingQuestion = streamingMessage?.pending_question ?? null;
  const pendingQuestionId = pendingQuestion?.question_id ?? null;
  const [announcedQuestionId, setAnnouncedQuestionId] = useState(pendingQuestionId);
  if (jumpButtonKey !== firstMessageKey) {
    setJumpButtonKey(firstMessageKey);
    setShowJumpButton(false);
  }
  if (previousSending !== sending) {
    setPreviousSending(sending);
    setAnnouncement(sending ? '' : completionAnnouncement(messages[messages.length - 1]));
  }
  if (announcedApprovalId !== pendingApprovalId) {
    setAnnouncedApprovalId(pendingApprovalId);
    if (pendingApproval) {
      setAnnouncement(approvalHeadline(pendingApproval));
    }
  }
  if (announcedQuestionId !== pendingQuestionId) {
    setAnnouncedQuestionId(pendingQuestionId);
    if (pendingQuestion) {
      setAnnouncement(`研究助理提問：${pendingQuestion.question}`);
    }
  }
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
      prependSnapshotRef.current = null;
      el.scrollTop = snapshot.scrollTop + (el.scrollHeight - snapshot.scrollHeight);
    } else {
      if (snapshot && !loadingMore) {
        prependSnapshotRef.current = null;
      }
      const lastMessage = messages[messages.length - 1];
      const userJustSent = messages.length > previousCount && lastMessage?.id === streamingMessageId;
      const wasNearBottom = previousScrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_THRESHOLD_PX;
      if (firstKeyChanged || userJustSent) {
        scrollToBottom('auto');
      } else if (wasNearBottom) {
        el.scrollTop = el.scrollHeight;
      }
    }
    previousScrollHeightRef.current = el.scrollHeight;
    const frame = requestAnimationFrame(updateJumpButton);
    return () => cancelAnimationFrame(frame);
  }, [messages, firstMessageKey, streamingMessageId, loadingMore, scrollToBottom, updateJumpButton]);
  const deferBefore = messages.length - EAGER_RENDER_TAIL;
  const streamingIndex = streamingMessage ? messages.indexOf(streamingMessage) : -1;
  return (
    <div className={styles.wrapper}>
      <div
        ref={scrollRef}
        className={styles.container}
        onScroll={updateJumpButton}
        aria-busy={conversationLoading || undefined}
      >
        <div className={`${styles.thread} ${isEmpty ? styles.threadEmpty : ''}`}>
          {hasMoreMessages && (
            <div className={styles.loadMoreContainer}>
              <Button
                size="sm"
                variant="outline"
                onClick={handleLoadMore}
                disabled={loadingMore}
                startIcon={loadingMore ? <Spinner size={14} /> : <Icon name="expand-less" size={16} />}
              >
                {loadingMore ? '正在載入更早訊息...' : '載入更早訊息'}
              </Button>
            </div>
          )}
          {isEmpty && conversationLoading ? (
            <>
              <ThreadSkeleton />
              <span className="sr-only">正在載入對話...</span>
            </>
          ) : isEmpty ? (
            <div className={styles.emptyState}>
              <span className={styles.emptyMark} aria-hidden="true">
                <img src={markUrl} alt="" width="56" height="56" />
              </span>
              <h2 className={styles.emptyTitle}>開始新的對話</h2>
              <p className={styles.emptyDesc}>
                詢問知識庫裡的文件、技術指引與專案流程，或請 AI 查詢即時資訊。
              </p>
              <p className={styles.suggestTitle} id={promptsTitleId}>試試這些問題</p>
              <div className={styles.suggestList} role="group" aria-labelledby={promptsTitleId}>
                {SUGGESTED_PROMPTS.map((prompt, promptIndex) => (
                  <button
                    key={prompt}
                    type="button"
                    className={styles.suggestButton}
                    style={{ '--i': promptIndex } as React.CSSProperties}
                    onClick={() => {
                      if (onSelectPrompt) {
                        onSelectPrompt(prompt);
                      } else {
                        onCopyMessage(prompt);
                      }
                    }}
                  >
                    <span className={styles.suggestText}>{prompt}</span>
                    <Icon name="arrow-up" size={15} className={styles.suggestIcon} />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg, index) => {
              const thinkId = msg.id ?? index;
              return (
                <ChatMessageItem
                  key={`${msg.is_user ? 'user' : 'assistant'}-${messageKey(msg.id, index)}`}
                  message={msg}
                  thinkId={thinkId}
                  isStreaming={msg.id !== undefined && msg.id === streamingMessageId}
                  entering={streamingIndex !== -1 && (index === streamingIndex || index === streamingIndex - 1)}
                  isThinkingOpen={Boolean(thinkOpenArr[thinkId])}
                  deferRendering={index < deferBefore}
                  onToggleThinking={onToggleThinking}
                  onCopyMessage={onCopyMessage}
                  onRetry={msg.error && !sending ? onRetry : undefined}
                  deletedFileIds={deletedFileIds}
                  onDownloadFile={onDownloadFile}
                  onDeleteFile={onDeleteFile}
                  onPreviewFile={onPreviewFile}
                />
              );
            })
          )}
        </div>
      </div>
      {!isEmpty && conversationLoading && (
        <div className={styles.loadingOverlay}>
          <Spinner size={16} color="var(--color-primary)" />
          <span className={styles.loadingText}>正在載入對話...</span>
        </div>
      )}
      {showJumpButton && !isEmpty && (
        <button type="button" className={styles.jumpButton} onClick={() => scrollToBottom('smooth')}>
          <Icon name="arrow-down" size={15} />
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