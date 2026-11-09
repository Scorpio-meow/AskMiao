import React, { useEffect, useId, useRef, useState } from 'react';
import type { FilePreview, PreviewBlock, PreviewRun, PreviewSheet, PreviewSlide, PreviewSource } from '../services/api';
import { describeRequestError } from '../utils/secureLogger';
import { Alert, Icon, IconButton, Spinner, Tab, Tabs, Tooltip } from './ui';
import MarkdownContent from '../pages/Chat/MarkdownContent';
import styles from './FilePreviewPanel.module.css';
const PAGE_LOAD_DELAY_MS = 300;
const PAGE_PRELOAD_MARGIN = '300px 0px';
const PANEL_MIN_WIDTH = 320;
const SPLIT_MAIN_MIN_WIDTH = 360;
const PEEK_PAGE_GAP = 96;
const RESIZE_STEP = 32;
const LEVEL_CLASSES = [styles.level0, styles.level1, styles.level2, styles.level3, styles.level4];
const levelClass = (level: number) => LEVEL_CLASSES[Math.min(Math.max(level, 0), LEVEL_CLASSES.length - 1)];
const Loading: React.FC<{ label: string }> = ({ label }) => (
  <div className={styles.loading}>
    <Spinner size={18} color="var(--color-primary)" />
    <span>{label}</span>
  </div>
);
const Runs: React.FC<{ runs: PreviewRun[] }> = ({ runs }) => (
  <>
    {runs.map((run, index) => {
      let node: React.ReactNode = run.text;
      if (run.italic) node = <em>{node}</em>;
      if (run.bold) node = <strong>{node}</strong>;
      return <React.Fragment key={index}>{node}</React.Fragment>;
    })}
  </>
);
const TableView: React.FC<{ rows: string[][]; truncated: boolean }> = ({ rows, truncated }) => (
  <>
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (rowIndex === 0
                ? <th key={cellIndex} scope="col">{cell}</th>
                : <td key={cellIndex}>{cell}</td>))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    {truncated && <p className={styles.note}>表格很大，只顯示前面一部分；完整內容請下載檔案。</p>}
  </>
);
const listNumbers = (blocks: PreviewBlock[]): Array<number | null> => {
  const counters: number[] = [];
  return blocks.map((block) => {
    if (block.type !== 'list_item') {
      counters.length = 0;
      return null;
    }
    counters.length = block.level + 1;
    counters[block.level] = (counters[block.level] || 0) + 1;
    return block.ordered ? counters[block.level] : null;
  });
};
const DocumentView: React.FC<{ blocks: PreviewBlock[]; truncated: boolean }> = ({ blocks, truncated }) => {
  const numbers = listNumbers(blocks);
  return (
    <article className={styles.document}>
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const Heading = block.level <= 1 ? 'h3' : block.level === 2 ? 'h4' : 'h5';
          return <Heading key={index}><Runs runs={block.runs} /></Heading>;
        }
        if (block.type === 'list_item') {
          return (
            <p key={index} className={`${styles.listItem} ${levelClass(block.level)}`}>
              <span className={styles.marker} aria-hidden="true">{numbers[index] !== null ? `${numbers[index]}.` : '•'}</span>
              <span><Runs runs={block.runs} /></span>
            </p>
          );
        }
        if (block.type === 'table') return <TableView key={index} rows={block.rows} truncated={block.truncated} />;
        return <p key={index}><Runs runs={block.runs} /></p>;
      })}
      {truncated && <p className={styles.note}>文件很長，只顯示前面一部分；完整內容請下載檔案。</p>}
    </article>
  );
};
const SheetsView: React.FC<{ sheets: PreviewSheet[] }> = ({ sheets }) => {
  const [active, setActive] = useState(0);
  const sheet = sheets[active];
  return (
    <>
      {sheets.length > 1 && (
        <Tabs value={active} onChange={(_, value) => setActive(value)}>
          {sheets.map((item, index) => <Tab key={index} label={item.name} value={index} />)}
        </Tabs>
      )}
      {!sheet || sheet.rows.length === 0
        ? <p className={styles.note}>這張工作表沒有內容。</p>
        : <TableView rows={sheet.rows} truncated={sheet.truncated} />}
    </>
  );
};
const SlidesView: React.FC<{ slides: PreviewSlide[]; truncated: boolean }> = ({ slides, truncated }) => (
  <>
    <ol className={styles.slides}>
      {slides.map((slide) => (
        <li key={slide.number} className={styles.slide}>
          <p className={styles.slideNumber}>第 {slide.number} 頁</p>
          {slide.title && <h3 className={styles.slideTitle}>{slide.title}</h3>}
          {slide.items.map((item, index) => (item.type === 'table'
            ? <TableView key={index} rows={item.rows} truncated={item.truncated} />
            : <p key={index} className={`${styles.listItem} ${levelClass(item.level)}`}><span className={styles.marker} aria-hidden="true">•</span><span>{item.text}</span></p>))}
          {slide.images > 0 && <p className={styles.note}>這一頁有 {slide.images} 張圖片，預覽不顯示圖片。</p>}
          {slide.notes && (
            <div className={styles.notes}>
              <span className={styles.notesLabel}>備忘稿</span>
              <p>{slide.notes}</p>
            </div>
          )}
        </li>
      ))}
    </ol>
    {truncated && <p className={styles.note}>簡報很長，只顯示前面一部分；完整內容請下載檔案。</p>}
  </>
);
const PdfPage: React.FC<{ source: PreviewSource; pageNumber: number }> = ({ source, pageNumber }) => {
  const frame = useRef<HTMLElement>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const element = frame.current;
    if (!element) return undefined;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    let timer: number | undefined;
    let loading = false;
    const load = () => {
      loading = true;
      setFailed(false);
      source.page(pageNumber, controller.signal)
        .then((blob) => {
          if (controller.signal.aborted) return;
          observer?.disconnect();
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
        })
        .catch((err) => {
          if (controller.signal.aborted) return;
          console.warn('載入預覽頁面失敗', describeRequestError(err));
          loading = false;
          setFailed(true);
        });
    };
    const observer = typeof IntersectionObserver === 'undefined'
      ? null
      : new IntersectionObserver((entries) => {
        window.clearTimeout(timer);
        if (!loading && entries.some((entry) => entry.isIntersecting)) {
          timer = window.setTimeout(load, PAGE_LOAD_DELAY_MS);
        }
      }, { rootMargin: PAGE_PRELOAD_MARGIN });
    if (observer) observer.observe(element);
    else load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
      observer?.disconnect();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [source, pageNumber]);
  return (
    <figure ref={frame} className={styles.page}>
      {url
        ? <img src={url} alt={`第 ${pageNumber} 頁`} className={styles.pageImage} />
        : <div className={styles.pagePlaceholder}>{failed ? '這一頁暫時無法顯示，捲開再回來會重新載入' : <Spinner size={18} color="var(--color-primary)" />}</div>}
      <figcaption className={styles.pageNumber}>第 {pageNumber} 頁</figcaption>
    </figure>
  );
};
const HtmlFrame: React.FC<{ source: PreviewSource }> = ({ source }) => {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    if (!source.viewUrl) return undefined;
    source.viewUrl()
      .then((value) => {
        if (active) setUrl(value);
      })
      .catch((err) => {
        console.warn('開啟網頁預覽失敗', describeRequestError(err));
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [source]);
  if (failed || !source.viewUrl) return <Alert severity="error">無法開啟網頁預覽，請稍後再試</Alert>;
  if (!url) return <Loading label="準備網頁預覽…" />;
  return (
    <iframe className={styles.frame} src={url} sandbox="allow-scripts" referrerPolicy="no-referrer" title={`${source.filename} 的網頁預覽`} />
  );
};
export const PreviewContent: React.FC<{ preview: FilePreview; source: PreviewSource }> = ({ preview, source }) => {
  switch (preview.type) {
    case 'pages':
      return (
        <div className={styles.pages}>
          {Array.from({ length: preview.page_count }, (_, index) => <PdfPage key={index} source={source} pageNumber={index + 1} />)}
        </div>
      );
    case 'document':
      return <DocumentView blocks={preview.blocks} truncated={preview.truncated} />;
    case 'sheets':
      return <SheetsView sheets={preview.sheets} />;
    case 'slides':
      return <SlidesView slides={preview.slides} truncated={preview.truncated} />;
    case 'html':
      return <HtmlFrame source={source} />;
    case 'unsupported':
      return <Alert severity="info">{preview.reason}</Alert>;
    default:
      return (
        <>
          {preview.notice && <Alert severity="info">{preview.notice}</Alert>}
          {preview.type === 'markdown' ? <MarkdownContent content={preview.text} /> : <pre className={styles.text}>{preview.text}</pre>}
          {preview.truncated && <p className={styles.note}>內容很長，只顯示前面一部分；完整內容請下載檔案。</p>}
        </>
      );
  }
};
interface FilePreviewPanelProps {
  source: PreviewSource;
  placement: 'split' | 'peek';
  onClose: () => void;
  onDownload?: () => void;
}
export const FilePreviewPanel: React.FC<FilePreviewPanelProps> = ({ source, placement, onClose, onDownload }) => {
  const titleId = useId();
  const panel = useRef<HTMLElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const drag = useRef<{ startX: number; startWidth: number } | null>(null);
  const [width, setWidth] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    source.load()
      .then((value) => {
        if (active) setPreview(value);
      })
      .catch((err) => {
        console.warn('載入檔案預覽失敗', describeRequestError(err));
        if (active) setError('無法預覽這個檔案，可能已被刪除；請稍後再試或直接下載');
      });
    return () => {
      active = false;
    };
  }, [source]);
  const [opener] = useState(() => (document.activeElement instanceof HTMLElement ? document.activeElement : null));
  useEffect(() => {
    title.current?.focus();
    return () => {
      if (opener?.isConnected && (!document.activeElement || document.activeElement === document.body)) opener.focus();
    };
  }, [opener]);
  const currentWidth = () => panel.current?.getBoundingClientRect().width ?? PANEL_MIN_WIDTH;
  const clampWidth = (value: number) => {
    const element = panel.current;
    const neighbor = element?.previousElementSibling;
    const available = placement === 'split' && element && neighbor
      ? element.getBoundingClientRect().width + neighbor.getBoundingClientRect().width - SPLIT_MAIN_MIN_WIDTH
      : window.innerWidth - PEEK_PAGE_GAP;
    return Math.round(Math.min(Math.max(value, PANEL_MIN_WIDTH), Math.max(available, PANEL_MIN_WIDTH)));
  };
  const stopDragging = () => {
    drag.current = null;
    setDragging(false);
  };
  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { startX: event.clientX, startWidth: currentWidth() };
    setDragging(true);
  };
  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (drag.current) setWidth(clampWidth(drag.current.startWidth + drag.current.startX - event.clientX));
  };
  const handleSeparatorKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && drag.current) {
      event.stopPropagation();
      setWidth(Math.round(drag.current.startWidth));
      stopDragging();
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      setWidth(clampWidth(currentWidth() + (event.key === 'ArrowLeft' ? RESIZE_STEP : -RESIZE_STEP)));
    }
  };
  const handlePanelKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape' && !drag.current) {
      event.stopPropagation();
      onClose();
    }
  };
  const className = [
    styles.panel,
    placement === 'split' ? styles.split : styles.peek,
    expanded ? styles.expanded : '',
    dragging ? styles.dragging : '',
  ].filter(Boolean).join(' ');
  return (
    <aside
      ref={panel}
      className={className}
      aria-labelledby={titleId}
      onKeyDown={handlePanelKeyDown}
      style={width === null ? undefined : ({ '--preview-width': `${width}px` } as React.CSSProperties)}
    >
      {!expanded && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="調整預覽寬度"
          aria-valuemin={PANEL_MIN_WIDTH}
          aria-valuenow={width ?? undefined}
          tabIndex={0}
          className={styles.separator}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={stopDragging}
          onPointerCancel={stopDragging}
          onLostPointerCapture={stopDragging}
          onKeyDown={handleSeparatorKeyDown}
        />
      )}
      <header className={styles.header}>
        <h2 id={titleId} ref={title} tabIndex={-1} className={styles.title} title={source.filename}>{source.filename}</h2>
        {onDownload && (
          <Tooltip title="下載">
            <IconButton size="sm" onClick={onDownload} aria-label="下載">
              <Icon name="download" size={16} />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title={expanded ? '還原' : '放大'}>
          <IconButton size="sm" className={styles.expandToggle} onClick={() => setExpanded((value) => !value)} aria-label={expanded ? '還原預覽大小' : '放大預覽'} aria-pressed={expanded}>
            <Icon name={expanded ? 'minimize' : 'maximize'} size={16} />
          </IconButton>
        </Tooltip>
        <Tooltip title="關閉">
          <IconButton size="sm" onClick={onClose} aria-label="關閉預覽">
            <Icon name="close" size={16} />
          </IconButton>
        </Tooltip>
      </header>
      <div className={styles.body}>
        {error && <Alert severity="error">{error}</Alert>}
        {!error && !preview && <Loading label="載入預覽…" />}
        {preview && <PreviewContent preview={preview} source={source} />}
      </div>
    </aside>
  );
};
export default FilePreviewPanel;