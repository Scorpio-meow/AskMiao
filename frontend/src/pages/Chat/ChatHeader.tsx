import React from 'react';
import { ChatHeaderProps } from './types';
import { IconButton, Tooltip, Spinner, Icon } from '../../components/ui';
import styles from './ChatHeader.module.css';
export const REASONING_EFFORT_OPTIONS = [
  { value: 'none', label: '無推理 (None / 快速)', shortLabel: '無 (None)' },
  { value: 'low', label: '輕度推理 (Low / 平衡)', shortLabel: '輕度 (Low)' },
  { value: 'medium', label: '標準推理 (Medium / 預設)', shortLabel: '標準 (Medium)' },
  { value: 'high', label: '深度推理 (High / 嚴密)', shortLabel: '深度 (High)' },
  { value: 'xhigh', label: '極致推理 (X-High / 長程)', shortLabel: '極致 (X-High)' },
  { value: 'max', label: '最大推理 (Max / 無限制)', shortLabel: '最大 (Max)' },
];
const CLAUDE_XHIGH_MODELS = [
  'claude-fable-5-1',
  'claude-fable-5',
  'claude-opus-5-5',
  'claude-opus-5',
  'claude-opus-4-8',
  'claude-opus-4-7',
  'claude-sonnet-5-5',
  'claude-sonnet-5',
  'claude-haiku-5-5',
];
export const supportsReasoningEffort = (model: string, effort: string): boolean => {
  if (model.startsWith('claude-')) {
    return (effort !== 'xhigh' && effort !== 'max') || CLAUDE_XHIGH_MODELS.includes(model);
  }
  if (model.startsWith('gemini-')) {
    if (effort === 'none') {
      return model.startsWith('gemini-2.5');
    }
    return effort !== 'xhigh' && effort !== 'max';
  }
  if (effort === 'max') {
    return model.startsWith('gpt-6');
  }
  return true;
};
export const choiceKey = (connectionId: number, model: string): string => `${connectionId}::${model}`;
export const parseChoice = (choice: string): { connectionId: number; model: string } | null => {
  const separator = choice.indexOf('::');
  if (separator <= 0) return null;
  const connectionId = Number(choice.slice(0, separator));
  return Number.isInteger(connectionId) ? { connectionId, model: choice.slice(separator + 2) } : null;
};
export const resolveReasoningEffort = (model: string, effort: string): string => {
  if (supportsReasoningEffort(model, effort)) {
    return effort;
  }
  return effort === 'none' ? 'low' : 'high';
};
export const ChatHeader: React.FC<ChatHeaderProps> = ({
  connections,
  selectedChoice,
  onSelectChoice,
  reasoningEffort,
  onSelectReasoningEffort,
  modelsLoading,
  onRefreshModels,
  currentConversation,
  onOpenSidebar,
  sidebarOpen = false,
  sidebarId,
}) => {
  const choices = connections.flatMap((connection) => connection.models.map((model) => choiceKey(connection.id, model)));
  const currentChoice = choices.includes(selectedChoice) ? selectedChoice : choices[0] || '';
  const currentModelValue = parseChoice(currentChoice)?.model || '';
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
            value={currentChoice}
            onChange={(e) => onSelectChoice(e.target.value)}
            disabled={modelsLoading}
            aria-label="選擇 AI 模型"
          >
            {choices.length === 0 ? (
              <option value="" disabled>
                {modelsLoading ? '載入模型中...' : '尚未設定 API 連線'}
              </option>
            ) : (
              connections.map((connection) => (
                <optgroup
                  key={connection.id}
                  label={`${connection.name}（${connection.scope === 'shared' ? '共用' : '個人'}）`}
                >
                  {connection.models.map((model) => (
                    <option key={model} value={choiceKey(connection.id, model)}>
                      {model}
                    </option>
                  ))}
                </optgroup>
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
                <option
                  key={opt.value}
                  value={opt.value}
                  title={supportsReasoningEffort(currentModelValue, opt.value) ? opt.label : '此模型不支援'}
                  disabled={!supportsReasoningEffort(currentModelValue, opt.value)}
                >
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
