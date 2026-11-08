import React, { useState, useEffect, useRef, useId } from 'react';
import { ResearchTraceStep } from './types';
import { Collapse, Spinner, Icon, IconName } from '../../components/ui';
import styles from './ResearchTraceBlock.module.css';
export interface ResearchTraceBlockProps {
  trace: ResearchTraceStep[];
  hasContent?: boolean;
  isStreaming?: boolean;
}
interface ToolDisplayInfo {
  label: string;
  icon: IconName;
}
const getToolDisplayInfo = (toolName: string): ToolDisplayInfo => {
  switch (toolName) {
    case 'search_knowledge_base':
      return { label: '檢索內部知識庫', icon: 'menu-book' };
    case 'filter_and_count_records':
      return { label: '結構化統計與篩選', icon: 'analytics' };
    case 'web_search':
      return { label: '外部聯網搜尋', icon: 'language' };
    case 'web_fetch':
      return { label: '深度閱讀網頁', icon: 'article' };
    case 'list_conversation_files':
      return { label: '列出對話檔案', icon: 'folder' };
    case 'read_conversation_file':
      return { label: '讀取對話檔案', icon: 'file' };
    case 'create_conversation_file':
      return { label: '建立檔案', icon: 'add' };
    case 'edit_conversation_file':
      return { label: '修改檔案（另存新版本）', icon: 'edit' };
    case 'delete_conversation_file':
      return { label: '刪除對話檔案', icon: 'delete' };
    default:
      return { label: toolName, icon: 'code' };
  }
};
const toDisplayText = (value: unknown): string => {
  if (value === undefined || value === null) return '';
  return typeof value === 'string' ? value : JSON.stringify(value);
};
const formatStepQueryParam = (step: ResearchTraceStep): string => {
  const args = step.arguments;
  if (typeof args !== 'object' || args === null || Array.isArray(args)) return toDisplayText(args);
  const fields = args as Record<string, unknown>;
  if (step.tool === 'filter_and_count_records') {
    const parts: string[] = [];
    if (fields.date_range) parts.push(`日期: ${toDisplayText(fields.date_range)}`);
    if (fields.author) parts.push(`作者: ${toDisplayText(fields.author)}`);
    if (fields.keyword) parts.push(`關鍵字: ${toDisplayText(fields.keyword)}`);
    if (fields.target_document) parts.push(`文件: ${toDisplayText(fields.target_document)}`);
    if (parts.length > 0) return parts.join(' | ');
  }
  if (fields.filename) return toDisplayText(fields.filename);
  if (fields.file_id !== undefined && fields.file_id !== null) return `#${toDisplayText(fields.file_id)}`;
  return toDisplayText(fields.query) || toDisplayText(fields.url);
};
const StepStatus: React.FC<{ status: ResearchTraceStep['status'] }> = ({ status }) => {
  if (status === 'running') {
    return (
      <span className={`${styles.stepStatus} ${styles.statusRunning}`}>
        <Spinner size={14} color="var(--color-primary)" aria-hidden="true" />
        <span className="sr-only">進行中</span>
      </span>
    );
  }
  if (status === 'error') {
    return (
      <span className={`${styles.stepStatus} ${styles.statusError}`}>
        <Icon name="error" size={16} />
        <span className="sr-only">失敗</span>
      </span>
    );
  }
  if (status === 'interrupted') {
    return (
      <span className={`${styles.stepStatus} ${styles.statusUnknown}`}>
        <Icon name="help" size={16} />
        <span className="sr-only">結果不明</span>
      </span>
    );
  }
  return (
    <span className={`${styles.stepStatus} ${styles.statusSuccess}`}>
      <Icon name="check-circle" size={16} />
      <span className="sr-only">完成</span>
    </span>
  );
};
export const ResearchTraceBlock: React.FC<ResearchTraceBlockProps> = ({
  trace,
  hasContent = false,
  isStreaming = false
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const userInteractedRef = useRef(false);
  const prevHasContentRef = useRef(hasContent);
  const stepListId = useId();
  const hasRunningStep = trace.some(s => s.status === 'running');
  const isResearching = isStreaming && !hasContent;
  useEffect(() => {
    if (userInteractedRef.current) return;
    if (isResearching || hasRunningStep) {
      setIsOpen(true);
    } else if (hasContent && !prevHasContentRef.current) {
      setIsOpen(false);
    }
    prevHasContentRef.current = hasContent;
  }, [isResearching, hasRunningStep, hasContent]);
  if (!trace || trace.length === 0) return null;
  const handleHeaderClick = () => {
    userInteractedRef.current = true;
    setIsOpen(prev => !prev);
  };
  const activeStep = trace.find(s => s.status === 'running') || trace[trace.length - 1];
  const activeToolInfo = activeStep ? getToolDisplayInfo(activeStep.tool) : null;
  const failedCount = trace.filter(s => s.status === 'error').length;
  return (
    <div className={`${styles.container} ${hasRunningStep ? styles.containerActive : ''}`}>
      <button
        type="button"
        className={styles.header}
        onClick={handleHeaderClick}
        aria-expanded={isOpen}
        aria-controls={stepListId}
      >
        <span className={styles.headerIcon} aria-hidden="true">
          {hasRunningStep ? (
            <Spinner size={14} color="var(--color-primary)" />
          ) : (
            <Icon name="search" size={16} />
          )}
        </span>
        <span className={styles.titleText}>
          {hasRunningStep
            ? `研究中：${activeToolInfo?.label || '執行中'}（步驟 ${activeStep.step}）`
            : `研究過程（${trace.length} 個步驟）`}
        </span>
        {!hasRunningStep && failedCount > 0 && (
          <span className={styles.failedCount}>{failedCount} 個失敗</span>
        )}
        <span className={styles.stepDots} aria-hidden="true">
          {trace.map((step, idx) => (
            <span
              key={idx}
              className={`${styles.stepDot} ${step.status === 'running' ? styles.stepDotRunning : ''} ${step.status === 'error' ? styles.stepDotError : ''}`}
            />
          ))}
        </span>
        <span className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`} aria-hidden="true">
          <Icon name="expand-more" size={16} />
        </span>
      </button>
      <Collapse in={isOpen} id={stepListId}>
        <ol className={styles.stepList} role="list">
          {trace.map((step: ResearchTraceStep, index: number) => {
            const toolInfo = getToolDisplayInfo(step.tool);
            const queryParam = formatStepQueryParam(step);
            const outputPreview = toDisplayText(step.output_preview);
            const isStepRunning = step.status === 'running';
            return (
              <li key={index} className={styles.stepItem}>
                <StepStatus status={step.status} />
                <div className={styles.stepBody}>
                  <div className={styles.stepHeader}>
                    <span className={styles.stepTitle}>
                      <Icon name={toolInfo.icon} size={14} className={styles.toolIcon} />
                      <span>步驟 {step.step}：{toolInfo.label}</span>
                    </span>
                    {step.duration_seconds !== undefined && !isStepRunning && (
                      <span className={styles.duration}>{step.duration_seconds}s</span>
                    )}
                  </div>
                  {queryParam && (
                    <p className={styles.queryText}>
                      <span className={styles.queryLabel}>關鍵字/目標：</span>
                      {queryParam}
                    </p>
                  )}
                  {outputPreview && (
                    <pre className={styles.outputPreview} tabIndex={0}>
                      {outputPreview}
                    </pre>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </Collapse>
    </div>
  );
};
export default ResearchTraceBlock;