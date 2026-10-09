import remarkGfm, { type Options } from 'remark-gfm';
import type { Processor } from 'unified';

/*
 * remark-gfm 加上自動連結的掃描量上限。
 *
 * remark-gfm 4 把文字中的網址與電子郵件轉成連結時（mdast-util-gfm-autolink-literal 2.0.1，目前的最新版），
 * 電子郵件的正規式會從一段連續 [-.\w+] 字元中每個 . - + _ 之後重新掃描到該段結尾；網址判定無效時，
 * 也會從下一個字元重新搜尋並掃描到下一個空白。一長串「.」或重複的「www.」因此讓耗時隨長度平方成長
 * （2 萬字元約 0.4 至 1.1 秒），而回答的內容受外部資料影響，可以讓檢視訊息的分頁凍結，每次開啟該對話都會重來。
 *
 * 這裡沿用 remark-gfm 的解析與轉換，只在轉換前以線性時間估算每個文字節點的掃描量：超過上限的節點暫時包進
 * linkReference（轉換本來就不處理連結內的文字），轉換結束後放回原處。一般文字的結果與 remark-gfm 相同，
 * 只有病態的文字節點不產生自動連結。
 */

// 掃描量上限：節點長度的 64 倍再加 10 萬步。一般文字遠低於此；病態文字約為長度的平方
const AUTOLINK_WORK_PER_CHAR = 64;
const AUTOLINK_WORK_BASE = 100_000;

interface MdastNode {
  type: string;
  value?: string;
  children?: MdastNode[];
}

type FromMarkdownTransform = (tree: MdastNode) => MdastNode | undefined | void;

interface FromMarkdownExtension {
  enter?: Record<string, unknown>;
  transforms?: FromMarkdownTransform[];
}

// 網址的路徑延伸到這幾種空白為止（與 mdast-util-gfm-autolink-literal 的正規式相同）
const isPathBreak = (code: number): boolean => code === 32 || code === 9 || code === 13 || code === 10;

const isAsciiAlphanumericOrUnderscore = (code: number): boolean =>
  (code >= 48 && code <= 57) || (code >= 65 && code <= 90) || (code >= 97 && code <= 122) || code === 95;

// 電子郵件帳號部分的字元 [-.\w+]
const isLocalPartChar = (code: number): boolean =>
  isAsciiAlphanumericOrUnderscore(code) || code === 45 || code === 46 || code === 43;

// 網域部分的字元 [-.\w]
const isDomainChar = (code: number): boolean => isAsciiAlphanumericOrUnderscore(code) || code === 45 || code === 46;

// 帳號部分中屬於標點或符號的字元：其後的位置也符合正規式開頭的 lookbehind，會被當成新的起點重新掃描
const isRestartPoint = (code: number): boolean => code === 45 || code === 46 || code === 43 || code === 95;

const startsUrlCandidate = (text: string, index: number): boolean => {
  // 以 | 0x20 把 ASCII 大寫字母轉成小寫；只有 W、w 會得到 0x77，只有 H、h 會得到 0x68
  const lower = text.charCodeAt(index) | 0x20;
  if (lower === 0x77) return text.slice(index, index + 4).toLowerCase() === 'www.';
  if (lower === 0x68) {
    const prefix = text.slice(index, index + 8).toLowerCase();
    return prefix.startsWith('http://') || prefix === 'https://';
  }
  return false;
};

/** 估算 GFM 自動連結轉換在這段文字上的掃描步數（上界），本身為線性時間 */
export function estimateAutolinkWork(text: string): number {
  let work = 0;

  // 網址：每個 http://、https://、www. 起點都可能掃描到下一個空白
  let segmentEnd = 0;
  for (let i = 0; i < text.length; i++) {
    if (i === segmentEnd) {
      if (isPathBreak(text.charCodeAt(i))) {
        segmentEnd = i + 1;
        continue;
      }
      while (segmentEnd < text.length && !isPathBreak(text.charCodeAt(segmentEnd))) segmentEnd++;
    }
    if (startsUrlCandidate(text, i)) work += segmentEnd - i;
  }

  // 電子郵件：每段連續 [-.\w+] 的開頭與其中每個 . - + _ 之後，都會掃描到該段結尾（後接 @ 時再加上網域）
  let i = 0;
  while (i < text.length) {
    if (!isLocalPartChar(text.charCodeAt(i))) {
      i++;
      continue;
    }
    const runStart = i;
    while (i < text.length && isLocalPartChar(text.charCodeAt(i))) i++;
    const runEnd = i;
    let domainLength = 0;
    if (runEnd < text.length && text.charCodeAt(runEnd) === 64) {
      let j = runEnd + 1;
      while (j < text.length && isDomainChar(text.charCodeAt(j))) j++;
      domainLength = j - runEnd;
    }
    work += runEnd - runStart + domainLength;
    for (let p = runStart + 1; p < runEnd; p++) {
      if (isRestartPoint(text.charCodeAt(p - 1))) work += runEnd - p + domainLength;
    }
  }

  return work;
}

export function isAutolinkWorkBounded(text: string): boolean {
  return estimateAutolinkWork(text) <= AUTOLINK_WORK_PER_CHAR * text.length + AUTOLINK_WORK_BASE;
}

interface ShieldedText {
  parent: MdastNode;
  placeholder: MdastNode;
}

// 以明確的堆疊走訪，深層巢狀的引言或清單不會用盡呼叫堆疊
function shieldUnboundedText(tree: MdastNode): ShieldedText[] {
  const shielded: ShieldedText[] = [];
  const pending: MdastNode[] = [tree];
  while (pending.length > 0) {
    const parent = pending.pop() as MdastNode;
    const children = parent.children;
    if (children === undefined) continue;
    children.forEach((child, index) => {
      // 轉換本來就不處理連結內的文字
      if (child.type === 'link' || child.type === 'linkReference') return;
      if (child.type === 'text' && typeof child.value === 'string') {
        if (!isAutolinkWorkBounded(child.value)) {
          const placeholder: MdastNode = { type: 'linkReference', children: [child] };
          children[index] = placeholder;
          shielded.push({ parent, placeholder });
        }
        return;
      }
      pending.push(child);
    });
  }
  return shielded;
}

function restoreShieldedText(shielded: ShieldedText[]): void {
  for (const { parent, placeholder } of shielded) {
    const siblings = parent.children as MdastNode[];
    const index = siblings.indexOf(placeholder);
    // 轉換只會替換文字節點，暫時的 linkReference 一定還在原處；找不到時不能以 -1 刪掉其他內容
    if (index === -1) throw new Error('GFM 自動連結轉換移除了暫時包住的文字節點');
    siblings.splice(index, 1, ...(placeholder.children as MdastNode[]));
  }
}

function boundAutolinkTransform(transform: FromMarkdownTransform): FromMarkdownTransform {
  return (tree) => {
    const shielded = shieldUnboundedText(tree);
    try {
      return transform(tree);
    } finally {
      restoreShieldedText(shielded);
    }
  };
}

function findAutolinkExtensions(value: unknown, found: FromMarkdownExtension[]): FromMarkdownExtension[] {
  if (Array.isArray(value)) {
    value.forEach((item) => findAutolinkExtensions(item, found));
  } else if (typeof value === 'object' && value !== null) {
    const extension = value as FromMarkdownExtension;
    if (extension.enter !== undefined && 'literalAutolink' in extension.enter && Array.isArray(extension.transforms)) {
      found.push(extension);
    }
  }
  return found;
}

/** 與 remark-gfm 相同的 GFM 支援（表格、刪除線、工作清單、註腳、自動連結），自動連結的轉換有掃描量上限 */
export default function remarkGfmSafe(this: Processor, options?: Options | null): undefined {
  remarkGfm.call(this, options);
  const data = this.data() as unknown as { fromMarkdownExtensions: unknown[] };
  // remark-gfm 剛把它的 mdast 擴充推入清單尾端
  const added = data.fromMarkdownExtensions[data.fromMarkdownExtensions.length - 1];
  const autolinkExtensions = findAutolinkExtensions(added, []);
  if (autolinkExtensions.length === 0) {
    throw new Error('remark-gfm 的結構與預期不同，找不到 GFM 自動連結的轉換，無法套用掃描量上限');
  }
  for (const extension of autolinkExtensions) {
    extension.transforms = (extension.transforms as FromMarkdownTransform[]).map(boundAutolinkTransform);
  }
  return undefined;
}
