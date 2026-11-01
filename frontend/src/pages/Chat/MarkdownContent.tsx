import React, { memo } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfmSafe from './remarkGfmSafe';
import styles from './MarkdownContent.module.css';
const SOCIAL_PLATFORM_DOMAINS = ['threads.com', 'threads.net', 'instagram.com', 'twitter.com', 'x.com'];
const ACTION_BUTTON_KEYWORDS = ['貼文', '查看', '前往', '開啟', '↗'];
const POST_TIME_PREFIX_REGEX = /^(上午|下午|\d{1,2}:\d{2}|\d{4}[-/年]\d{1,2}[-/月])/;
// 不在結尾加上 $：分隔符號與作者名稱都接受「.」，加上 $ 後一長串「.」會回溯成二次方時間，
// 模型輸出的長段落可讓分頁凍結；需要整段比對時改以比對長度是否等於整段判斷
const POST_AUTHOR_PREFIX_REGEX = /^(?:(\d+)[\.:\s]+)?(@?[\w\.-]+)/;
const POST_LINK_PREFIX_REGEX = /^(連結|來源)[：:]\s*/;
const POST_CONTENT_PREFIX_REGEX = /^(內容)[：:]\s*/;
const REMARK_PLUGINS = [remarkGfmSafe];
const isSocialUrl = (href?: string): boolean => {
  if (!href) return false;
  try {
    const host = new URL(href).hostname.replace(/^www\./, '');
    return SOCIAL_PLATFORM_DOMAINS.some((domain) => host === domain || host.endsWith(`.${domain}`));
  } catch {
    return false;
  }
};
/** 連到其他網站的 http(s) 連結回傳解析後的網址；站內連結與 mailto 等其他協定回傳 null */
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
/**
 * 把「作者 ｜ 時間 ｜ 內容 ｜ 社群連結」這類貼文清單轉成卡片。
 * 只在段落確實連到社群平台、且不含行內程式碼時套用，避免一般文字或指令中的 | 被誤判。
 */
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
const MARKDOWN_COMPONENTS: Components = {
  // 回答可能受外部資料影響，連結文字可以與實際網址不同；外部連結一律標示實際前往的網站，
  // 不套用站內動作按鈕的樣式，Markdown 中的 title 也不能取代實際網址的提示
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
  // 模型回答可能受外部資料影響，圖片若自動載入會在不需點擊的情況下把網址中的資料送往外部主機；
  // 一律改成需使用者點擊的連結
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
export const MarkdownContent = memo(function MarkdownContent({ content }: { content: string }) {
  return (
    <div className={styles.markdownBody}>
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={MARKDOWN_COMPONENTS}>
        {content}
      </ReactMarkdown>
    </div>
  );
});
export default MarkdownContent;
