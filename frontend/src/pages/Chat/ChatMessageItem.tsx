import React, { memo, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChatMessageItemProps, ResearchTraceStep } from './types';
import ThinkBlock from './ThinkBlock';
import SourceBadges from './SourceBadges';
import ResearchTraceBlock from './ResearchTraceBlock';
import ToolApprovalCard from './ToolApprovalCard';
import MarkdownContent from './MarkdownContent';
import ConversationFileCard from './ConversationFileCard';
import { describeAttachmentType, formatMessageTime, isImageAttachment, splitThinkContent } from './chatFormat';
import { Tooltip, IconButton, Spinner, Icon, Button, useModalDialog } from '../../components/ui';
import styles from './ChatMessageItem.module.css';
const NO_TRACE: ResearchTraceStep[] = [];
const ImageLightbox: React.FC<{ src: string; alt: string; onClose: () => void }> = ({ src, alt, onClose }) => {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const dialogHandlers = useModalDialog(dialogRef, true, onClose);
  return createPortal(
    <dialog
      ref={dialogRef}
      aria-label={`圖片預覽：${alt}`}
      className={styles.lightboxDialog}
      {...dialogHandlers}
    >
      <img src={src} alt={alt} className={styles.lightboxImage} />
      <button type="button" className={styles.lightboxClose} onClick={onClose} aria-label="關閉圖片預覽">
        <Icon name="close" size={20} />
      </button>
    </dialog>,
    document.body
  );
};
const ChatMessageItemView: React.FC<ChatMessageItemProps> = ({
  message,
  thinkId,
  isStreaming,
  isThinkingOpen,
  deferRendering,
  onToggleThinking,
  onCopyMessage,
  onRetry,
  deletedFileIds,
  onDownloadFile,
  onDeleteFile,
  onPreviewFile,
}) => {
  const isUser = message.is_user;
  const { thinkContent, mainContent } = useMemo(() => splitThinkContent(message.content || ''), [message.content]);
  const [lightboxImg, setLightboxImg] = useState<{ src: string; alt: string } | null>(null);
  const trace = message.research_trace || NO_TRACE;
  const attachments = message.attachments || [];
  const files = message.files || [];
  const hasTrace = trace.length > 0;
  const hasText = Boolean(mainContent.trim());
  const isSettled = Boolean(message.error || message.stopped);
  const timestamp = message.created_at ? formatMessageTime(message.created_at, new Date()) : null;
  const attachmentGallery = attachments.length > 0 && (
    <div className={styles.attachmentGallery}>
      {attachments.map((att, idx) => {
        const name = att.filename || '圖片';
        if (isImageAttachment(att) && att.data_url) {
          const src = att.data_url;
          return (
            <button
              key={idx}
              type="button"
              className={styles.imageButton}
              onClick={() => setLightboxImg({ src, alt: name })}
              aria-label={`放大圖片：${name}`}
            >
              <img src={src} alt="" className={styles.messageImage} />
            </button>
          );
        }
        if (att.file_id) {
          return (
            <ConversationFileCard
              key={idx}
              file={{ id: att.file_id, filename: att.filename, size_bytes: att.file_size }}
              deleted={deletedFileIds.has(att.file_id)}
              onDownload={onDownloadFile}
              onDelete={onDeleteFile}
              onPreview={onPreviewFile}
            />
          );
        }
        return (
          <div key={idx} className={styles.fileCard}>
            <span className={styles.fileBadge}>{describeAttachmentType(att.filename || '').label}</span>
            <span className={styles.fileName}>{att.filename}</span>
          </div>
        );
      })}
    </div>
  );
  const footer = (
    <div className={styles.footer}>
      {timestamp && message.created_at && (
        <time className={styles.meta} dateTime={message.created_at} title={timestamp.full}>
          {timestamp.label}
        </time>
      )}
      {!isUser && message.model_name && <span className={`${styles.meta} ${styles.modelName}`}>{message.model_name}</span>}
      {hasText && (
        <Tooltip title="複製訊息內容">
          <IconButton
            size="sm"
            onClick={() => onCopyMessage(mainContent)}
            className={styles.copyButton}
            aria-label="複製訊息內容"
          >
            <Icon name="copy" size={14} />
          </IconButton>
        </Tooltip>
      )}
    </div>
  );
  return (
    <div className={`${styles.row} ${isUser ? styles.rowUser : styles.rowAssistant} ${deferRendering ? styles.deferred : ''}`}>
      {isUser ? (
        <div className={styles.userColumn}>
          <div className={styles.userBubble}>
            <span className="sr-only">您說：</span>
            {attachmentGallery}
            {mainContent && <div className={styles.userText}>{mainContent}</div>}
          </div>
          {footer}
        </div>
      ) : (
        <>
          <span className={styles.assistantMark} aria-hidden="true">
            <Icon name="bot" size={16} />
          </span>
          <div className={styles.assistantColumn}>
            <span className="sr-only">AskMiao 回覆：</span>
            {attachmentGallery}
            {hasTrace && (
              <ResearchTraceBlock trace={trace} hasContent={hasText} isStreaming={isStreaming} />
            )}
            {isStreaming && message.pending_approval && (
              <ToolApprovalCard key={message.pending_approval.approval_id} approval={message.pending_approval} />
            )}
            {thinkContent && (
              <ThinkBlock thinkContent={thinkContent} isOpen={isThinkingOpen} onToggle={() => onToggleThinking(thinkId)} />
            )}
            {!hasText && !hasTrace && !isSettled ? (
              <div className={styles.pending}>
                <Spinner size={14} color="var(--color-primary)" />
                <span>AI 正在分析您的問題...</span>
              </div>
            ) : hasText ? (
              <MarkdownContent content={mainContent} />
            ) : null}
            {message.error && (
              <div className={styles.errorBlock}>
                <Icon name="error" size={16} className={styles.errorIcon} />
                <span className={styles.errorText}>{message.error}</span>
                {onRetry && (
                  <Button size="sm" variant="outline" onClick={() => onRetry(message)} startIcon={<Icon name="refresh" size={14} />}>
                    重新傳送
                  </Button>
                )}
              </div>
            )}
            {message.stopped && (
              <div className={styles.stoppedNote}>
                <Icon name="info" size={14} />
                <span>已停止產生。這則回答沒有被儲存，重新整理後不會出現。</span>
              </div>
            )}
            {files.length > 0 && (
              <div className={styles.attachmentGallery} role="list" aria-label="這則回答的檔案">
                {files.map((event, idx) => (
                  <div role="listitem" key={`${event.action}-${event.file.id}-${idx}`}>
                    <ConversationFileCard
                      file={event.file}
                      action={event.action}
                      deleted={event.action === 'deleted' || deletedFileIds.has(event.file.id)}
                      onDownload={onDownloadFile}
                      onDelete={onDeleteFile}
                      onPreview={onPreviewFile}
                    />
                  </div>
                ))}
              </div>
            )}
            <SourceBadges sources={message.sources} sourcesDetail={message.sources_detail} />
            {footer}
          </div>
        </>
      )}
      {lightboxImg && (
        <ImageLightbox src={lightboxImg.src} alt={lightboxImg.alt} onClose={() => setLightboxImg(null)} />
      )}
    </div>
  );
};
export const ChatMessageItem = memo(ChatMessageItemView);
export default ChatMessageItem;