export const REASONING_EFFORT_OPTIONS = [
  { value: 'none', label: '無推理 (None / 快速)', shortLabel: '無 (None)' },
  { value: 'low', label: '輕度推理 (Low / 平衡)', shortLabel: '輕度 (Low)' },
  { value: 'medium', label: '標準推理 (Medium / 預設)', shortLabel: '標準 (Medium)' },
  { value: 'high', label: '深度推理 (High / 嚴密)', shortLabel: '深度 (High)' },
  { value: 'xhigh', label: '極致推理 (X-High / 長程)', shortLabel: '極致 (X-High)' },
  { value: 'max', label: '最大推理 (Max / 無限制)', shortLabel: '最大 (Max)' },
];
const CLAUDE_XHIGH_MODELS = [
  'claude-fable-5-1',
  'claude-fable-5',
  'claude-opus-5-5',
  'claude-opus-5',
  'claude-opus-4-8',
  'claude-opus-4-7',
  'claude-sonnet-5-5',
  'claude-sonnet-5',
  'claude-haiku-5-5',
];
export const supportsReasoningEffort = (model: string, effort: string): boolean => {
  if (model.startsWith('claude-')) {
    return (effort !== 'xhigh' && effort !== 'max') || CLAUDE_XHIGH_MODELS.includes(model);
  }
  if (model.startsWith('gemini-')) {
    if (effort === 'none') {
      return model.startsWith('gemini-2.5');
    }
    return effort !== 'xhigh' && effort !== 'max';
  }
  if (effort === 'max') {
    return model.startsWith('gpt-6');
  }
  return true;
};
export const resolveReasoningEffort = (model: string, effort: string): string => {
  if (supportsReasoningEffort(model, effort)) {
    return effort;
  }
  return effort === 'none' ? 'low' : 'high';
};
