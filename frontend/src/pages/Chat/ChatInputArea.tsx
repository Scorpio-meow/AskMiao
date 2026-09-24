import React, { useRef, useEffect, useLayoutEffect, useState, useCallback } from 'react';
import { ChatInputAreaProps, ChatAttachment } from './types';
import { Tooltip, Icon } from '../../components/ui';
import styles from './ChatInputArea.module.css';
const formatFileSize = (bytes?: number): string => {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};
const getBadgeClass = (filename: string): { className: string; label: string } => {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (ext === 'pdf') return { className: styles.badgePdf, label: 'PDF' };
  if (['doc', 'docx'].includes(ext)) return { className: styles.badgeDocx, label: 'DOC' };
  if (['xls', 'xlsx', 'csv'].includes(ext)) return { className: styles.badgeXlsx, label: ext.toUpperCase() };
  if (['ppt', 'pptx'].includes(ext)) return { className: styles.badgePptx, label: 'PPT' };
  if (['js', 'ts', 'jsx', 'tsx', 'py', 'json', 'html', 'css', 'sql'].includes(ext)) {
    return { className: styles.badgeCode, label: ext.toUpperCase() };
  }
  return { className: '', label: ext ? ext.toUpperCase() : 'FILE' };
};
// 觸控裝置聚焦輸入框會彈出螢幕鍵盤，只在有滑鼠等精確指標的裝置自動聚焦
const canAutoFocus = () => window.matchMedia('(pointer: fine)').matches;
// 支援 field-sizing 的瀏覽器由 CSS 自動長高，其餘才用 JS 計算高度
const supportsFieldSizing = typeof CSS !== 'undefined' && CSS.supports('field-sizing', 'content');
export const ChatInputArea: React.FC<ChatInputAreaProps> = ({
  value,
  onChange,
  onSend,
  onStop,
  sending,
  streamingHere,
  disabled = false,
  attachments = [],
  onAddAttachments,
  onRemoveAttachment,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const processFiles = useCallback((files: FileList | File[]) => {
    const newAttachments: ChatAttachment[] = [];
    const fileList = Array.from(files);
    let processedCount = 0;
    fileList.forEach((file) => {
      const isImg = file.type.startsWith('image/');
      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target?.result as string;
        newAttachments.push({
          id: `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          filename: file.name,
          file_type: file.type || 'application/octet-stream',
          file_size: file.size,
          data_url: dataUrl,
          file,
        });
        processedCount++;
        if (processedCount === fileList.length && onAddAttachments) {
          onAddAttachments(newAttachments);
        }
      };
      if (isImg || file.size < 15 * 1024 * 1024) {
        reader.readAsDataURL(file);
      } else {
        newAttachments.push({
          id: `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          filename: file.name,
          file_type: file.type || 'application/octet-stream',
          file_size: file.size,
          file,
        });
        processedCount++;
        if (processedCount === fileList.length && onAddAttachments) {
          onAddAttachments(newAttachments);
        }
      }
    });
  }, [onAddAttachments]);
  const hasContent = Boolean(value.trim()) || attachments.length > 0;
  const canSend = hasContent && !sending && !disabled;
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // 注音、倉頡等輸入法組字時按 Enter 是在選字，不能當成送出
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (canSend) {
        onSend();
      }
    }
  };
  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const pastedFiles: File[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type.indexOf('image') !== -1 || item.kind === 'file') {
        const file = item.getAsFile();
        if (file) {
          pastedFiles.push(file);
        }
      }
    }
    if (pastedFiles.length > 0) {
      e.preventDefault();
      processFiles(pastedFiles);
    }
  };
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDragging) setIsDragging(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // 移到子元素上也會觸發 dragleave，只有真的離開輸入區才取消提示
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
      setIsDragging(false);
    }
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files);
    }
  };
  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files);
      e.target.value = '';
    }
  };
  // 不支援 field-sizing 時依內容調整高度，上限由 CSS 的 max-height 決定
  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (supportsFieldSizing || !textarea) return;
    textarea.style.height = 'auto';
    const maxHeight = parseFloat(getComputedStyle(textarea).maxHeight);
    const nextHeight = Number.isNaN(maxHeight) ? textarea.scrollHeight : Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > nextHeight ? 'auto' : 'hidden';
  }, [value]);
  useEffect(() => {
    if (sending || !canAutoFocus()) return;
    const active = document.activeElement;
    // 使用者正在操作其他元素時不搶焦點
    if (!active || active === document.body) {
      textareaRef.current?.focus();
    }
  }, [sending]);
  const hint = streamingHere
    ? '回答產生中，可以先輸入下一個問題'
    : sending
      ? '其他對話的回答仍在產生中，完成後才能傳送'
      : null;
  return (
    <div className={styles.container}>
      <div
        className={`${styles.inputCard} ${isDragging ? styles.dropActive : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* 附件預覽列 */}
        {attachments.length > 0 && (
          <ul className={styles.attachmentPreviewBar} role="list" aria-label="待傳送的附件">
            {attachments.map((att, idx) => {
              const isImg = att.file_type.startsWith('image/') || Boolean(att.data_url?.startsWith('data:image/'));
              const badge = getBadgeClass(att.filename);
              if (isImg && att.data_url) {
                return (
                  <li key={att.id || idx} className={styles.imagePreviewCard}>
                    <img src={att.data_url} alt={att.filename} className={styles.imagePreviewThumb} />
                    <button
                      type="button"
                      className={styles.removeAttachmentBtn}
                      onClick={() => onRemoveAttachment && onRemoveAttachment(idx)}
                      aria-label={`移除圖片 ${att.filename}`}
                    >
                      <Icon name="close" size={12} />
                    </button>
                  </li>
                );
              }
              return (
                <li key={att.id || idx} className={styles.filePreviewCard}>
                  <span className={`${styles.fileFormatBadge} ${badge.className}`}>
                    {badge.label}
                  </span>
                  <div className={styles.fileInfo}>
                    <span className={styles.fileName} title={att.filename}>{att.filename}</span>
                    {att.file_size && <span className={styles.fileSize}>{formatFileSize(att.file_size)}</span>}
                  </div>
                  <button
                    type="button"
                    className={styles.removeFileBtn}
                    onClick={() => onRemoveAttachment && onRemoveAttachment(idx)}
                    aria-label={`移除檔案 ${att.filename}`}
                  >
                    <Icon name="close" size={14} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <div className={styles.inputRow}>
          {/* 上傳檔案/圖片按鈕 */}
          <input
            type="file"
            ref={fileInputRef}
            className={styles.hiddenFileInput}
            multiple
            accept=".png,.jpg,.jpeg,.webp,.gif,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.txt,.md,.json,.js,.ts,.py,.html,.css"
            onChange={handleFileInputChange}
          />
          <Tooltip title="上傳檔案或圖片（也可以貼上截圖或拖曳檔案）">
            <button
              type="button"
              className={styles.attachButton}
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              aria-label="上傳檔案或圖片"
            >
              <Icon name="upload" size={18} />
            </button>
          </Tooltip>
          <textarea
            ref={textareaRef}
            rows={1}
            className={styles.textarea}
            placeholder="輸入您的問題..."
            aria-label="輸入訊息"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            disabled={disabled}
          />
          {streamingHere ? (
            <Tooltip title="停止產生回答">
              <button
                type="button"
                className={`${styles.sendButton} ${styles.stopButton}`}
                onClick={onStop}
                aria-label="停止產生回答"
              >
                <Icon name="stop" size={16} />
              </button>
            </Tooltip>
          ) : (
            <Tooltip title="發送訊息 (Enter)">
              <button
                type="button"
                className={`${styles.sendButton} ${canSend ? styles.sendButtonActive : ''}`}
                onClick={onSend}
                disabled={!canSend}
                aria-label="發送訊息"
              >
                <Icon name="send" size={18} />
              </button>
            </Tooltip>
          )}
        </div>
      </div>
      <div className={styles.hintRow}>
        {hint ? (
          <span className={styles.hint}>{hint}</span>
        ) : (
          <span className={styles.dragHint}>
            <Icon name="image" size={13} /> 可貼上截圖或拖曳檔案
          </span>
        )}
        <span className={`${styles.hint} ${styles.keyboardHint}`}>按 Enter 發送，Shift + Enter 換行</span>
      </div>
    </div>
  );
};
export default ChatInputArea;
