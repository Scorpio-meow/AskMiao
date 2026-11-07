import remarkGfm, { type Options } from 'remark-gfm';
import type { Processor } from 'unified';
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
const isPathBreak = (code: number): boolean => code === 32 || code === 9 || code === 13 || code === 10;
const isAsciiAlphanumericOrUnderscore = (code: number): boolean =>
  (code >= 48 && code <= 57) || (code >= 65 && code <= 90) || (code >= 97 && code <= 122) || code === 95;
const isLocalPartChar = (code: number): boolean =>
  isAsciiAlphanumericOrUnderscore(code) || code === 45 || code === 46 || code === 43;
const isDomainChar = (code: number): boolean => isAsciiAlphanumericOrUnderscore(code) || code === 45 || code === 46;
const isRestartPoint = (code: number): boolean => code === 45 || code === 46 || code === 43 || code === 95;
const startsUrlCandidate = (text: string, index: number): boolean => {
  const lower = text.charCodeAt(index) | 0x20;
  if (lower === 0x77) return text.slice(index, index + 4).toLowerCase() === 'www.';
  if (lower === 0x68) {
    const prefix = text.slice(index, index + 8).toLowerCase();
    return prefix.startsWith('http://') || prefix === 'https://';
  }
  return false;
};
export function estimateAutolinkWork(text: string): number {
  let work = 0;
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
function shieldUnboundedText(tree: MdastNode): ShieldedText[] {
  const shielded: ShieldedText[] = [];
  const pending: MdastNode[] = [tree];
  while (pending.length > 0) {
    const parent = pending.pop() as MdastNode;
    const children = parent.children;
    if (children === undefined) continue;
    children.forEach((child, index) => {
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
export default function remarkGfmSafe(this: Processor, options?: Options | null): undefined {
  remarkGfm.call(this, options);
  const data = this.data() as unknown as { fromMarkdownExtensions: unknown[] };
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