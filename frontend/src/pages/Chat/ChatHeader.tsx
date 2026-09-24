import React from 'react';
import { ChatHeaderProps } from './types';
import { IconButton, Tooltip, Spinner, Icon } from '../../components/ui';
import styles from './ChatHeader.module.css';
const REASONING_EFFORT_OPTIONS = [
  { value: 'none', label: '無推理 (None / 快速)', shortLabel: '無 (None)' },
  { value: 'low', label: '輕度推理 (Low / 平衡)', shortLabel: '輕度 (Low)' },
  { value: 'medium', label: '標準推理 (Medium / 預設)', shortLabel: '標準 (Medium)' },
  { value: 'high', label: '深度推理 (High / 嚴密)', shortLabel: '深度 (High)' },
  { value: 'xhigh', label: '極致推理 (X-High / 長程)', shortLabel: '極致 (X-High)' },
];
export const ChatHeader: React.FC<ChatHeaderProps> = ({
  availableModels,
  selectedModel,
  onSelectModel,
  reasoningEffort,
  onSelectReasoningEffort,
  modelsLoading,
  onRefreshModels,
  currentConversation,
  onOpenSidebar,
  sidebarOpen = false,
  sidebarId,
}) => {
  const currentModelValue = availableModels.includes(selectedModel)
    ? selectedModel
    : availableModels[0] || '';
  const title = currentConversation?.title || '新對話';
  return (
    <header className={styles.header}>
      <div className={styles.leftGroup}>
        {onOpenSidebar && (
          <IconButton
            size="sm"
            onClick={onOpenSidebar}
            className={styles.mobileMenuBtn}
            aria-label="開啟對話清單"
            aria-expanded={sidebarOpen}
            aria-controls={sidebarOpen ? sidebarId : undefined}
          >
            <Icon name="menu" size={20} />
          </IconButton>
        )}
        <h1 className={styles.title} title={title}>
          {title}
        </h1>
      </div>
      <div className={styles.rightGroup}>
        <div className={styles.selectWrapper}>
          <select
            className={styles.select}
            value={currentModelValue}
            onChange={(e) => onSelectModel(e.target.value)}
            disabled={modelsLoading}
            aria-label="選擇 AI 模型"
          >
            {availableModels.length === 0 ? (
              <option value="" disabled>
                {modelsLoading ? '載入模型中...' : '無可用模型'}
              </option>
            ) : (
              availableModels.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))
            )}
          </select>
          <span className={styles.selectIcon} aria-hidden="true">
            <Icon name="expand-more" size={16} />
          </span>
        </div>
        <Tooltip title="設定模型思考與推理深度 (Reasoning Effort)" placement="bottom">
          <div className={styles.selectWrapper}>
            <select
              className={styles.select}
              value={reasoningEffort}
              onChange={(e) => onSelectReasoningEffort(e.target.value)}
              aria-label="選擇推理程度"
            >
              {REASONING_EFFORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value} title={opt.label}>
                  {opt.shortLabel}
                </option>
              ))}
            </select>
            <span className={styles.selectIcon} aria-hidden="true">
              <Icon name="expand-more" size={16} />
            </span>
          </div>
        </Tooltip>
        <Tooltip title="重新整理可用模型清單" placement="bottom">
          <IconButton
            size="sm"
            onClick={onRefreshModels}
            disabled={modelsLoading}
            aria-label="重新整理可用模型清單"
          >
            {modelsLoading ? (
              <Spinner size={18} aria-hidden="true" />
            ) : (
              <Icon name="refresh" size={18} />
            )}
          </IconButton>
        </Tooltip>
      </div>
    </header>
  );
};
export default ChatHeader;
