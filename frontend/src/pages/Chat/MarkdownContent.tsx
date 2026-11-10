import React, { createContext, memo, useContext, useState } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfmSafe from './remarkGfmSafe';
import remarkCitations from './remarkCitations';
import { SourcePopover } from './SourceBadges';
import type { SourceDetail } from './types';
import styles from './MarkdownContent.module.css';
const SOCIAL_PLATFORM_DOMAINS = ['threads.com', 'threads.net', 'instagram.com', 'twitter.com', 'x.com'];
const ACTION_BUTTON_KEYWORDS = ['貼文', '查看', '前往', '開啟', '↗'];
const POST_TIME_PREFIX_REGEX = /^(上午|下午|\d{1,2}:\d{2}|\d{4}[-/年]\d{1,2}[-/月])/;
const POST_AUTHOR_PREFIX_REGEX = /^(?:(\d+)[\.:\s]+)?(@?[\w\.-]+)/;
const POST_LINK_PREFIX_REGEX = /^(連結|來源)[：:]\s*/;
const POST_CONTENT_PREFIX_REGEX = /^(內容)[：:]\s*/;
const REMARK_PLUGINS = [remarkGfmSafe, remarkCitations];
const CitationContext = createContext<SourceDetail[] | undefined>(undefined);
const isSocialUrl = (href?: string): boolean => {
  if (!href) return false;
  try {
    const host = new URL(href).hostname.replace(/^www\./, '');
    return SOCIAL_PLATFORM_DOMAINS.some((domain) => host === domain || host.endsWith(`.${domain}`));
  } catch {
    return false;
  }
};
const parseExternalLink = (href?: string): URL | null => {
  if (!href) return null;
  try {
    const url = new URL(href, window.location.href);
    const isWeb = url.protocol === 'http:' || url.protocol === 'https:';
    return isWeb && url.origin !== window.location.origin ? url : null;
  } catch {
    return null;
  }
};
function parsePipeDelimitedPost(children: React.ReactNode): React.ReactNode | null {
  const childArray = React.Children.toArray(children);
  let fullText = '';
  const linkNodes: React.ReactNode[] = [];
  let hasSocialLink = false;
  for (const child of childArray) {
    if (typeof child === 'string') {
      fullText += child;
    } else if (React.isValidElement(child)) {
      const props: any = child.props || {};
      if (child.type === 'code') {
        return null;
      }
      if (child.type === 'a' || props.href) {
        linkNodes.push(child);
        hasSocialLink = hasSocialLink || isSocialUrl(props.href);
        fullText += ' [[LINK]] ';
      } else if (props.children) {
        const textDesc = typeof props.children === 'string' ? props.children : ' ';
        fullText += textDesc;
      }
    }
  }
  if (!hasSocialLink) {
    return null;
  }
  if (!fullText.includes('｜') && !fullText.includes('|')) {
    return null;
  }
  const parts = fullText.split(/[｜|]/).map((p) => p.trim()).filter(Boolean);
  if (parts.length < 2) {
    return null;
  }
  let indexStr = '';
  let authorStr = '';
  let timeStr = '';
  let contentStr = '';
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (POST_TIME_PREFIX_REGEX.test(p) && !timeStr) {
      timeStr = p;
      continue;
    }
    const authorMatchPrefix = p.match(POST_AUTHOR_PREFIX_REGEX);
    if (authorMatchPrefix && authorMatchPrefix[0].length === p.length && !authorStr && !p.includes('內容') && !p.includes('連結')) {
      if (authorMatchPrefix[1]) indexStr = authorMatchPrefix[1];
      authorStr = authorMatchPrefix[2].startsWith('@') ? authorMatchPrefix[2] : `@${authorMatchPrefix[2]}`;
      continue;
    }
    if (authorMatchPrefix && !authorStr && !p.includes('內容') && !p.includes('連結') && !p.includes('[[LINK]]')) {
      if (authorMatchPrefix[1]) indexStr = authorMatchPrefix[1];
      authorStr = authorMatchPrefix[2].startsWith('@') ? authorMatchPrefix[2] : `@${authorMatchPrefix[2]}`;
      const rem = p.replace(authorMatchPrefix[0], '').trim();
      if (rem) {
        contentStr += (contentStr ? ' ' : '') + rem;
      }
      continue;
    }
    if (p.includes('[[LINK]]')) {
      const cleaned = p.replace(/\[\[LINK\]\]/g, '').replace(POST_LINK_PREFIX_REGEX, '').trim();
      if (cleaned) {
        contentStr += (contentStr ? ' ' : '') + cleaned;
      }
    } else {
      const cleaned = p.replace(POST_CONTENT_PREFIX_REGEX, '').trim();
      contentStr += (contentStr ? ' ' : '') + cleaned;
    }
  }
  if (!authorStr && !contentStr && linkNodes.length === 0) {
    return null;
  }
  return (
    <div className={styles.socialPostCard}>
      <div className={styles.socialPostHeader}>
        <div className={styles.socialPostAuthorRow}>
          {indexStr && <span className={styles.postIndexBadge}>#{indexStr}</span>}
          {authorStr && <span className={styles.postAuthorBadge}>{authorStr}</span>}
        </div>
        {timeStr && <span className={styles.socialPostTime}>{timeStr}</span>}
      </div>
      {contentStr && <div className={styles.socialPostContent}>{contentStr}</div>}
      {linkNodes.length > 0 && (
        <div className={styles.socialPostFooter}>
          {linkNodes}
        </div>
      )}
    </div>
  );
}
const CitationRef: React.FC<{ citation: number; children: React.ReactNode }> = ({ citation, children }) => {
  const details = useContext(CitationContext);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const detail = details?.find((item) => item.citation === citation);
  if (!detail) return <>{children}</>;
  return (
    <>
      <button
        type="button"
        className={styles.citationRef}
        onClick={(event) => setAnchorEl(event.currentTarget)}
        aria-haspopup="dialog"
        aria-expanded={anchorEl !== null}
        aria-label={`來源 ${citation}：${detail.label || detail.source}`}
      >
        {citation}
      </button>
      <SourcePopover detail={detail} anchorEl={anchorEl} onClose={() => setAnchorEl(null)} />
    </>
  );
};
const MARKDOWN_COMPONENTS: Components = {
  sup: ({ node, children, ...props }) => {
    const citation = node?.properties?.dataCitation;
    if (citation === undefined) return <sup {...props}>{children}</sup>;
    return <CitationRef citation={Number(citation)}>{children}</CitationRef>;
  },
  a: ({ node, href, children, ...props }) => {
    const external = parseExternalLink(href);
    const isSocial = isSocialUrl(href);
    const text = String(children);
    const isPill = isSocial || (!external && ACTION_BUTTON_KEYWORDS.some((kw) => text.includes(kw)));
    return (
      <a
        {...props}
        href={href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
        className={isPill ? styles.postLinkBadge : styles.markdownLink}
        title={external ? `在新分頁開啟 ${external.href}` : props.title}
      >
        {children}
        {external && !text.includes('↗') && (
          <span className={styles.externalIcon} aria-hidden="true">↗</span>
        )}
        {external && <span className="sr-only">（在新分頁開啟 {external.host}）</span>}
      </a>
    );
  },
  img: ({ node, src, alt }) => {
    const label = `圖片：${alt || src || '（無說明）'}`;
    const isExternal = typeof src === 'string' && /^https?:\/\//i.test(src);
    if (!isExternal) return <span>{label}</span>;
    return (
      <a
        href={src}
        target="_blank"
        rel="noopener noreferrer nofollow"
        referrerPolicy="no-referrer"
        className={styles.markdownLink}
        title={`在新分頁開啟 ${src}`}
      >
        {label}
        <span className={styles.externalIcon} aria-hidden="true">↗</span>
        <span className="sr-only">（在新分頁開啟）</span>
      </a>
    );
  },
  table: ({ node, ...props }) => (
    <div className={styles.tableContainer}>
      <table {...props} />
    </div>
  ),
  p: ({ node, children, ...props }) => {
    const card = parsePipeDelimitedPost(children);
    if (card) return card;
    return <p {...props}>{children}</p>;
  },
  li: ({ node, children, ...props }) => {
    const card = parsePipeDelimitedPost(children);
    if (card) return <li className={styles.customListItem} {...props}>{card}</li>;
    return <li {...props}>{children}</li>;
  },
};
export const MarkdownContent = memo(function MarkdownContent({ content, citations }: { content: string; citations?: SourceDetail[] }) {
  return (
    <div className={styles.markdownBody}>
      <CitationContext.Provider value={citations}>
        <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={MARKDOWN_COMPONENTS}>
          {content}
        </ReactMarkdown>
      </CitationContext.Provider>
    </div>
  );
});
export default MarkdownContent;