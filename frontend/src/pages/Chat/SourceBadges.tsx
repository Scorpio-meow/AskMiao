import React, { useState, useMemo } from 'react';
import { SourceBadgesProps, SourceDetail } from './types';
import { Chip, Popover, Icon } from '../../components/ui';
import styles from './SourceBadges.module.css';
const isWebUrl = (value: string) => value.startsWith('http://') || value.startsWith('https://');
export const SourceBadges: React.FC<SourceBadgesProps> = ({
  sources,
  sourcesDetail,
}) => {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const [activeDetail, setActiveDetail] = useState<SourceDetail | null>(null);
  const normalizedDetails: SourceDetail[] = useMemo(() => {
    if (!sourcesDetail) return [];
    if (Array.isArray(sourcesDetail)) return sourcesDetail;
    if (typeof sourcesDetail === 'string') {
      try {
        const parsed = JSON.parse(sourcesDetail);
        if (Array.isArray(parsed)) return parsed;
      } catch {
        return [];
      }
    }
    return [];
  }, [sourcesDetail]);
  const normalizedSources: string[] = useMemo(() => {
    if (!sources) return [];
    if (Array.isArray(sources)) {
      return sources.map((s) => (typeof s === 'string' ? s : (s as any)?.source || JSON.stringify(s)));
    }
    if (typeof sources === 'string') {
      const trimmed = (sources as string).trim();
      if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
        try {
          const parsed = JSON.parse(trimmed);
          if (Array.isArray(parsed)) {
            return parsed.map((s) => (typeof s === 'string' ? s : (s as any)?.source || JSON.stringify(s)));
          }
        } catch { }
      }
      return trimmed.split(/[,;\n]+/).map((s) => s.trim()).filter(Boolean);
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
  const webIcon = <Icon name="language" size={14} />;
  const documentIcon = <Icon name="description" size={14} />;
  return (
    <div className={styles.container}>
      <span className={styles.heading}>參考來源：</span>
      <div className={styles.badgesList}>
        {hasDetails
          ? normalizedDetails.map((detail, idx) => {
            const hasCitation = detail.citation !== undefined;
            const chunkLabel = detail.chunk !== undefined
              ? (hasCitation ? `（段落 ${detail.chunk}）` : ` (段落 ${detail.chunk})`)
              : '';
            if (detail.url) {
              const label = hasCitation ? `[${detail.citation}] ${detail.source}` : detail.source;
              return (
                <Chip
                  key={idx}
                  icon={webIcon}
                  label={<>{label}<span className="sr-only">（在新分頁開啟）</span></>}
                  size="sm"
                  variant="outlined"
                  wrap
                  href={detail.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.badgeWeb}
                />
              );
            }
            const baseLabel = `${detail.source}${chunkLabel}`;
            const label = hasCitation ? `[${detail.citation}] ${baseLabel}` : baseLabel;
            return (
              <Chip
                key={idx}
                icon={documentIcon}
                label={label}
                size="sm"
                variant="outlined"
                wrap
                onClick={(e) => handleOpenDetail(e, detail)}
                aria-haspopup="dialog"
                aria-expanded={activeDetail === detail}
              />
            );
          })
          : normalizedSources.map((src, idx) => {
            const isWeb = isWebUrl(src);
            return (
              <Chip
                key={idx}
                icon={isWeb ? webIcon : documentIcon}
                label={isWeb ? <>{src}<span className="sr-only">（在新分頁開啟）</span></> : src}
                size="sm"
                variant="outlined"
                wrap
                href={isWeb ? src : undefined}
                target={isWeb ? '_blank' : undefined}
                rel={isWeb ? 'noopener noreferrer' : undefined}
                className={isWeb ? styles.badgeWeb : ''}
              />
            );
          })}
      </div>
      <Popover
        open={Boolean(anchorEl)}
        anchorEl={anchorEl}
        onClose={handleCloseDetail}
        aria-label={activeDetail ? `來源詳情：${activeDetail.source}` : '來源詳情'}
      >
        {activeDetail && (
          <div className={styles.popoverCard}>
            <div className={styles.popoverHeader}>
              <Icon name="description" size={18} />
              <span>{activeDetail.source}</span>
            </div>
            {activeDetail.score !== undefined && activeDetail.score !== null && (
              <div className={styles.scoreRow}>
                <Icon name="analytics" size={14} />
                <span>相關度 {Math.round(activeDetail.score * 100)}%</span>
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
