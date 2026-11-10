interface MdastNode {
  type: string;
  value?: string;
  children?: MdastNode[];
  data?: Record<string, unknown>;
}
const CITATION_MARK = /\[(\d+)\]/g;
const LITERAL_PARENTS = new Set(['link', 'linkReference']);
function splitCitations(value: string): MdastNode[] | null {
  const parts: MdastNode[] = [];
  let last = 0;
  for (const match of value.matchAll(CITATION_MARK)) {
    if (match.index > last) parts.push({ type: 'text', value: value.slice(last, match.index) });
    parts.push({
      type: 'citation',
      data: { hName: 'sup', hProperties: { dataCitation: match[1] }, hChildren: [{ type: 'text', value: match[0] }] },
    });
    last = match.index + match[0].length;
  }
  if (parts.length === 0) return null;
  if (last < value.length) parts.push({ type: 'text', value: value.slice(last) });
  return parts;
}
export default function remarkCitations() {
  return (tree: MdastNode) => {
    const pending: MdastNode[] = [tree];
    while (pending.length > 0) {
      const parent = pending.pop() as MdastNode;
      if (parent.children === undefined) continue;
      parent.children = parent.children.flatMap((child) => {
        if (child.type === 'text' && typeof child.value === 'string') return splitCitations(child.value) ?? [child];
        if (!LITERAL_PARENTS.has(child.type)) pending.push(child);
        return [child];
      });
    }
  };
}