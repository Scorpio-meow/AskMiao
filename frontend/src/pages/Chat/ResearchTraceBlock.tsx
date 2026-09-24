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
  toneClass: string;
}
const getToolDisplayInfo = (toolName: string): ToolDisplayInfo => {
  switch (toolName) {
    case 'search_knowledge_base':
      return { label: '檢索內部知識庫', icon: 'menu-book', toneClass: styles.toneKnowledge };
    case 'filter_and_count_records':
      return { label: '結構化統計與篩選', icon: 'analytics', toneClass: styles.toneRecords };
    case 'web_search':
      return { label: '外部聯網搜尋', icon: 'language', toneClass: styles.toneSearch };
    case 'web_fetch':
      return { label: '深度閱讀網頁', icon: 'article', toneClass: styles.toneFetch };
    default:
      return { label: toolName, icon: 'code', toneClass: styles.toneDefault };
  }
};
const formatStepQueryParam = (step: ResearchTraceStep): string => {
  const args = step.arguments || {};
  if (step.tool === 'filter_and_count_records') {
    const parts: string[] = [];
    if (args.date_range) parts.push(`日期: ${args.date_range}`);
    if (args.author) parts.push(`作者: ${args.author}`);
    if (args.keyword) parts.push(`關鍵字: ${args.keyword}`);
    if (args.target_document) parts.push(`文件: ${args.target_document}`);
    if (parts.length > 0) return parts.join(' | ');
  }
  return args.query || args.url || '';
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
  return (
    <div className={`${styles.container} ${hasRunningStep ? styles.containerActive : ''}`}>
      <button
        type="button"
        className={styles.header}
        onClick={handleHeaderClick}
        aria-expanded={isOpen}
        aria-controls={stepListId}
      >
        <span className={styles.titleArea}>
          {hasRunningStep ? (
            <Spinner size={16} color="var(--color-primary)" aria-hidden="true" />
          ) : (
            <Icon name="search" size={18} color="var(--color-primary)" />
          )}
          <span className={styles.titleText}>
            {hasRunningStep
              ? `AI 自主研究中：${activeToolInfo?.label || '執行中'} (步驟 ${activeStep.step})`
              : `AI 自主研究歷程 (${trace.length} 個步驟)`}
          </span>
        </span>
        <span className={styles.metaArea}>
          <span className={styles.stepsChipRow} aria-hidden="true">
            {trace.map((step, idx) => {
              const info = getToolDisplayInfo(step.tool);
              const isStepRunning = step.status === 'running';
              return (
                <span
                  key={idx}
                  className={`${styles.stepChip} ${info.toneClass} ${isStepRunning ? styles.stepChipRunning : ''} ${step.status === 'error' ? styles.stepChipError : ''}`}
                >
                  S{step.step}
                </span>
              );
            })}
          </span>
          <span className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`} aria-hidden="true">
            <Icon name="expand-more" size={16} />
          </span>
        </span>
      </button>
      <Collapse in={isOpen} id={stepListId}>
        <div className={styles.divider} />
        <ol className={styles.stepList} role="list">
          {trace.map((step: ResearchTraceStep, index: number) => {
            const toolInfo = getToolDisplayInfo(step.tool);
            const queryParam = formatStepQueryParam(step);
            const isStepRunning = step.status === 'running';
            const isStepError = step.status === 'error';
            return (
              <li
                key={index}
                className={`${styles.stepItem} ${isStepRunning ? styles.stepItemRunning : ''}`}
              >
                <div className={styles.stepHeader}>
                  <div className={styles.stepTitle}>
                    <span className={`${styles.toolIcon} ${toolInfo.toneClass}`}>
                      <Icon name={toolInfo.icon} size={16} />
                    </span>
                    <span>
                      步驟 {step.step}：{toolInfo.label}
                      {isStepRunning && <span className={styles.runningBadge}>進行中</span>}
                    </span>
                  </div>
                  <div className={styles.stepMeta}>
                    {step.duration_seconds !== undefined && !isStepRunning && (
                      <span className={styles.duration}>{step.duration_seconds}s</span>
                    )}
                    {isStepRunning ? (
                      <Spinner size={14} color="var(--color-primary)" aria-hidden="true" />
                    ) : isStepError ? (
                      <span className={styles.statusError}>
                        <Icon name="error" size={14} />
                        <span className="sr-only">失敗</span>
                      </span>
                    ) : (
                      <span className={styles.statusSuccess}>
                        <Icon name="check-circle" size={14} />
                        <span className="sr-only">完成</span>
                      </span>
                    )}
                  </div>
                </div>
                {queryParam && (
                  <div className={styles.queryBox}>
                    <span className={styles.queryText}>
                      關鍵字/目標: {queryParam}
                    </span>
                  </div>
                )}
                {step.output_preview && (
                  <pre className={styles.outputPreview}>
                    {step.output_preview}
                  </pre>
                )}
              </li>
            );
          })}
        </ol>
      </Collapse>
    </div>
  );
};
export default ResearchTraceBlock;
