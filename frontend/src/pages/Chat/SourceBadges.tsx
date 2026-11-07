import React, { useState, useMemo, useId } from 'react';
import { SourceBadgesProps, SourceDetail } from './types';
import { Popover, Icon } from '../../components/ui';
import styles from './SourceBadges.module.css';
const isWebUrl = (value: string) => value.startsWith('http://') || value.startsWith('https://');
const SourceLabel: React.FC<{ citation?: number; icon: 'language' | 'description'; name: string; meta?: string }> = ({
  citation,
  icon,
  name,
  meta,
}) => (
  <>
    {citation !== undefined ? (
      <span className={styles.citation}>{citation}</span>
    ) : (
      <Icon name={icon} size={14} className={styles.sourceIcon} />
    )}
    <span className={styles.sourceName}>{name}</span>
    {meta && <span className={styles.sourceMeta}>{meta}</span>}
  </>
);
export const SourceBadges: React.FC<SourceBadgesProps> = ({
  sources,
  sourcesDetail,
}) => {
  const headingId = useId();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const [activeDetail, setActiveDetail] = useState<SourceDetail | null>(null);
  const normalizedDetails: SourceDetail[] = useMemo(() => {
    if (!sourcesDetail) return [];
    if (Array.isArray(sourcesDetail)) return sourcesDetail;
    return [];
  }, [sourcesDetail]);
  const normalizedSources: string[] = useMemo(() => {
    if (!sources) return [];
    if (Array.isArray(sources)) {
      return sources.map((s) => (typeof s === 'string' ? s : (s as any)?.source || JSON.stringify(s)));
    }
    return [];
  }, [sources]);
  const handleOpenDetail = (
    event: React.MouseEvent<HTMLElement>,
    detail: SourceDetail
  ) => {
    setAnchorEl(event.currentTarget);
    setActiveDetail(detail);
  };
  const handleCloseDetail = () => {
    setAnchorEl(null);
    setActiveDetail(null);
  };
  const hasDetails = normalizedDetails.length > 0;
  const hasSources = normalizedSources.length > 0;
  if (!hasDetails && !hasSources) return null;
  const newTabNote = <span className="sr-only">（在新分頁開啟）</span>;
  return (
    <div className={styles.container}>
      <p className={styles.heading} id={headingId}>參考來源</p>
      <ul className={styles.sourceList} aria-labelledby={headingId}>
        {hasDetails
          ? normalizedDetails.map((detail, idx) => {
            const chunkLabel = detail.chunk !== undefined ? `段落 ${detail.chunk}` : undefined;
            if (detail.url) {
              return (
                <li key={idx} className={styles.sourceItem}>
                  <a className={`${styles.source} ${styles.sourceWeb}`} href={detail.url} target="_blank" rel="noopener noreferrer">
                    <SourceLabel citation={detail.citation} icon="language" name={detail.label || detail.source} />
                    <span className={styles.externalIcon} aria-hidden="true">↗</span>
                    {newTabNote}
                  </a>
                </li>
              );
            }
            return (
              <li key={idx} className={styles.sourceItem}>
                <button
                  type="button"
                  className={styles.source}
                  onClick={(e) => handleOpenDetail(e, detail)}
                  aria-haspopup="dialog"
                  aria-expanded={activeDetail === detail}
                >
                  <SourceLabel citation={detail.citation} icon="description" name={detail.source} meta={chunkLabel} />
                </button>
              </li>
            );
          })
          : normalizedSources.map((src, idx) => {
            const isWeb = isWebUrl(src);
            return (
              <li key={idx} className={styles.sourceItem}>
                {isWeb ? (
                  <a className={`${styles.source} ${styles.sourceWeb}`} href={src} target="_blank" rel="noopener noreferrer">
                    <SourceLabel icon="language" name={src} />
                    <span className={styles.externalIcon} aria-hidden="true">↗</span>
                    {newTabNote}
                  </a>
                ) : (
                  <span className={`${styles.source} ${styles.sourceStatic}`}>
                    <SourceLabel icon="description" name={src} />
                  </span>
                )}
              </li>
            );
          })}
      </ul>
      <Popover
        open={Boolean(anchorEl)}
        anchorEl={anchorEl}
        onClose={handleCloseDetail}
        aria-label={activeDetail ? `來源詳情：${activeDetail.source}` : '來源詳情'}
      >
        {activeDetail && (
          <div className={styles.popoverCard}>
            <div className={styles.popoverHeader}>
              {activeDetail.citation !== undefined ? (
                <span className={styles.citation}>{activeDetail.citation}</span>
              ) : (
                <Icon name="description" size={16} className={styles.sourceIcon} />
              )}
              <span className={styles.popoverTitle}>{activeDetail.source}</span>
            </div>
            {(activeDetail.chunk !== undefined || (activeDetail.score !== undefined && activeDetail.score !== null)) && (
              <div className={styles.popoverMeta}>
                {activeDetail.chunk !== undefined && <span>段落 {activeDetail.chunk}</span>}
                {activeDetail.score !== undefined && activeDetail.score !== null && (
                  <span className={styles.score}>相關度 {Math.round(activeDetail.score * 100)}%</span>
                )}
              </div>
            )}
            {activeDetail.snippet && (
              <div className={styles.snippet}>
                {activeDetail.snippet}
              </div>
            )}
          </div>
        )}
      </Popover>
    </div>
  );
};
export default SourceBadges;