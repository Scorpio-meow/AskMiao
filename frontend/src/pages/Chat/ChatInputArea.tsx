import React, { useRef, useEffect, useLayoutEffect, useState, useCallback, useId } from 'react';
import { ChatInputAreaProps, ChatAttachment } from './types';
import { Tooltip, Icon } from '../../components/ui';
import { skillService, EnabledSkill } from '../../services/api';
import { AttachmentKind, describeAttachmentType, formatFileSize, isImageAttachment, isImeComposition, skillSuggestionsFor } from './chatFormat';
import styles from './ChatInputArea.module.css';
const ATTACHMENT_KIND_CLASS: Record<AttachmentKind, string> = {
  pdf: styles.badgePdf,
  doc: styles.badgeDoc,
  sheet: styles.badgeSheet,
  slide: styles.badgeSlide,
  code: styles.badgeCode,
  other: '',
};
const canAutoFocus = () => window.matchMedia('(pointer: fine)').matches;
const supportsFieldSizing = typeof CSS !== 'undefined' && CSS.supports('field-sizing', 'content');
const MAX_SKILL_SUGGESTIONS = 8;
const MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024;
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
  onRejectAttachments,
}) => {
  const suggestionsId = useId();
  const hintId = useId();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [skills, setSkills] = useState<EnabledSkill[]>([]);
  const [activeSkillIndex, setActiveSkillIndex] = useState(0);
  const [dismissedCommand, setDismissedCommand] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    skillService.getEnabledSkills()
      .then((res) => {
        if (!cancelled) setSkills(res.skills);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  const skillSuggestions = skillSuggestionsFor(value, skills, dismissedCommand, MAX_SKILL_SUGGESTIONS);
  const suggestionsOpen = skillSuggestions.length > 0 && !disabled;
  const highlightedSkill = suggestionsOpen ? Math.min(activeSkillIndex, skillSuggestions.length - 1) : -1;
  const optionId = (name: string) => `${suggestionsId}-${name}`;
  const chooseSkill = (name: string) => {
    onChange(`/${name} `);
    setActiveSkillIndex(0);
    textareaRef.current?.focus();
  };
  const processFiles = useCallback((files: FileList | File[]) => {
    const newAttachments: ChatAttachment[] = [];
    const tooLarge = Array.from(files).filter((file) => file.size > MAX_ATTACHMENT_BYTES);
    if (tooLarge.length > 0) {
      onRejectAttachments?.(`單一附件不可超過 ${MAX_ATTACHMENT_BYTES / (1024 * 1024)} MiB：${tooLarge.map((file) => file.name).join('、')}`);
    }
    const fileList = Array.from(files).filter((file) => file.size <= MAX_ATTACHMENT_BYTES);
    let processedCount = 0;
    fileList.forEach((file) => {
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
      reader.readAsDataURL(file);
    });
  }, [onAddAttachments, onRejectAttachments]);
  const hasContent = Boolean(value.trim()) || attachments.length > 0;
  const canSend = hasContent && !sending && !disabled;
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (isImeComposition({ isComposing: e.nativeEvent.isComposing, keyCode: e.keyCode })) return;
    if (suggestionsOpen) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const step = e.key === 'ArrowDown' ? 1 : -1;
        setActiveSkillIndex((highlightedSkill + step + skillSuggestions.length) % skillSuggestions.length);
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        chooseSkill(skillSuggestions[highlightedSkill].name);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setDismissedCommand(value);
        return;
      }
    }
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
      <div className={styles.composerArea}>
        {suggestionsOpen && (
          <ul id={suggestionsId} className={styles.skillSuggestions} role="listbox" aria-label="可使用的技能">
            {skillSuggestions.map((skill, idx) => (
              <li
                key={skill.name}
                id={optionId(skill.name)}
                role="option"
                aria-selected={idx === highlightedSkill}
                className={`${styles.skillOption} ${idx === highlightedSkill ? styles.skillOptionActive : ''}`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  chooseSkill(skill.name);
                }}
                onMouseEnter={() => setActiveSkillIndex(idx)}
              >
                <span className={styles.skillOptionName}>/{skill.name}</span>
                <span className={styles.skillOptionDescription}>{skill.description}</span>
              </li>
            ))}
          </ul>
        )}
        <div
          className={`${styles.composer} ${isDragging ? styles.dropActive : ''} ${disabled ? styles.composerDisabled : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {attachments.length > 0 && (
            <ul className={styles.attachmentList} role="list" aria-label="待傳送的附件">
              {attachments.map((att, idx) => {
                if (isImageAttachment(att) && att.data_url) {
                  return (
                    <li key={att.id || idx} className={styles.imagePreview}>
                      <img src={att.data_url} alt={att.filename} className={styles.imagePreviewThumb} />
                      <button
                        type="button"
                        className={styles.removeImageButton}
                        onClick={() => onRemoveAttachment && onRemoveAttachment(idx)}
                        aria-label={`移除圖片 ${att.filename}`}
                      >
                        <Icon name="close" size={12} />
                      </button>
                    </li>
                  );
                }
                const badge = describeAttachmentType(att.filename);
                return (
                  <li key={att.id || idx} className={styles.filePreview}>
                    <span className={`${styles.fileBadge} ${ATTACHMENT_KIND_CLASS[badge.kind]}`}>
                      {badge.label}
                    </span>
                    <span className={styles.fileInfo}>
                      <span className={styles.fileName} title={att.filename}>{att.filename}</span>
                      {att.file_size && <span className={styles.fileSize}>{formatFileSize(att.file_size)}</span>}
                    </span>
                    <button
                      type="button"
                      className={styles.removeFileButton}
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
          <textarea
            ref={textareaRef}
            rows={1}
            className={styles.textarea}
            placeholder="輸入您的問題..."
            aria-label="輸入訊息"
            aria-describedby={hint ? hintId : undefined}
            value={value}
            onChange={(e) => {
              onChange(e.target.value);
              setActiveSkillIndex(0);
            }}
            onKeyDown={handleKeyDown}
            aria-autocomplete={skills.length > 0 ? 'list' : undefined}
            aria-controls={suggestionsOpen ? suggestionsId : undefined}
            aria-activedescendant={suggestionsOpen ? optionId(skillSuggestions[highlightedSkill].name) : undefined}
            onPaste={handlePaste}
            disabled={disabled}
          />
          <input
            type="file"
            ref={fileInputRef}
            className={styles.hiddenFileInput}
            multiple
            accept=".png,.jpg,.jpeg,.webp,.gif,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.txt,.md,.json,.js,.ts,.py,.html,.css"
            onChange={handleFileInputChange}
          />
          <Tooltip title="上傳檔案或圖片（也可以貼上截圖或拖曳檔案）" className={styles.attachSlot}>
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
          {streamingHere ? (
            <Tooltip title="停止產生回答" className={styles.sendSlot}>
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
            <Tooltip title="發送訊息 (Enter)" className={styles.sendSlot}>
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
          {isDragging && (
            <div className={styles.dropOverlay} aria-hidden="true">
              <Icon name="upload" size={18} />
              <span>放開以附加檔案</span>
            </div>
          )}
        </div>
        <div className={styles.hintRow}>
          {hint ? (
            <span className={`${styles.hint} ${styles.hintActive}`} id={hintId}>{hint}</span>
          ) : (
            <span className={styles.hint}>
              可貼上截圖或拖曳檔案{skills.length > 0 && '，輸入 / 指定技能'}
            </span>
          )}
          <span className={`${styles.hint} ${styles.keyboardHint}`}>按 Enter 發送，Shift + Enter 換行</span>
        </div>
      </div>
    </div>
  );
};
export default ChatInputArea;