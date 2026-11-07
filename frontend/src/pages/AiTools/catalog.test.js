import { describe, expect, it } from 'vitest';
import { DEFAULT_TOOLS_METADATA } from './builtinTools';
import {
  attentionItems,
  categoryCounts,
  deleteDescription,
  describeCustomTool,
  filterCatalog,
  mcpToolHints,
  normalizeQuery,
  sectionSummaries,
  toolParameters,
  withBackendDescriptions,
} from './catalog';
const customTools = [
  {
    id: 1,
    name: 'get_exchange_rate',
    display_name: '匯率換算',
    description: '查詢即時匯率',
    method: 'GET',
    url: 'https://rates.example.com/v1/convert',
    is_enabled: true,
    parameters_schema: {
      type: 'object',
      properties: { from: { type: 'string', description: '來源貨幣' }, amount: { description: '金額' } },
      required: ['from'],
    },
  },
  { id: 2, name: 'send_ticket', display_name: '派遣工單', description: '', method: 'POST', url: 'https://tickets.example.com/dispatch', is_enabled: false, credentials_unreadable: true },
];
const servers = [
  {
    id: 7,
    name: 'mcp_time',
    display_name: '時間服務',
    transport_type: 'stdio',
    command: 'uvx',
    args: ['mcp-server-time'],
    is_enabled: true,
    status: 'connected',
    discovered_tools: [{ name: 'get_current_time' }, { name: 'convert_time' }],
  },
  {
    id: 8,
    name: 'mcp_docs',
    display_name: '文件搜尋',
    transport_type: 'http',
    url: 'https://mcp.example.com/mcp',
    is_enabled: false,
    status: 'error',
    credentials_unreadable: true,
    discovered_tools: [],
  },
];
const skills = [
  { id: 3, name: 'release-notes', description: '整理發行說明', compatibility: '需要 Git 歷史', is_enabled: true, files_present: true },
  { id: 4, name: 'pdf-forms', description: '填寫 PDF 表單', is_enabled: false, files_present: false },
];
const inventory = { builtinTools: DEFAULT_TOOLS_METADATA, customTools, servers, skills };
const filter = (category, searchQuery = '') =>
  filterCatalog({ ...inventory, category, query: normalizeQuery(searchQuery) });
describe('category filter', () => {
  it('shows every section under all tools', () => {
    const catalog = filter('all');
    expect(catalog.visible).toEqual({ builtin: true, custom: true, mcp: true, skills: true });
    expect(catalog.builtin.map((t) => t.name)).toEqual(DEFAULT_TOOLS_METADATA.map((t) => t.name));
    expect(catalog.custom.map((t) => t.id)).toEqual([1, 2]);
    expect(catalog.nothingMatches).toBe(false);
  });
  it('limits built-in categories to their own tools', () => {
    const knowledge = filter('knowledge');
    expect(knowledge.visible).toEqual({ builtin: true, custom: false, mcp: false, skills: false });
    expect(knowledge.builtin.map((t) => t.name)).toEqual(['search_knowledge_base', 'filter_and_count_records']);
    expect(filter('web').builtin.map((t) => t.name)).toEqual(['web_search', 'web_fetch']);
  });
  it('shows only the managed section that was picked', () => {
    expect(filter('custom_api').visible).toEqual({ builtin: false, custom: true, mcp: false, skills: false });
    expect(filter('mcp').visible).toEqual({ builtin: false, custom: false, mcp: true, skills: false });
    expect(filter('skills').visible).toEqual({ builtin: false, custom: false, mcp: false, skills: true });
  });
  it('keeps an empty section visible when nothing is being searched', () => {
    const catalog = filterCatalog({ ...inventory, customTools: [], servers: [], skills: [], category: 'all', query: '' });
    expect(catalog.visible).toEqual({ builtin: true, custom: true, mcp: true, skills: true });
    expect(catalog.nothingMatches).toBe(false);
  });
});
describe('search', () => {
  it('matches case-insensitively across names, URLs, MCP commands and discovered tools', () => {
    expect(filter('all', '  RATES.example ').custom.map((t) => t.id)).toEqual([1]);
    expect(filter('all', 'mcp-server-time').mcp.map((s) => s.id)).toEqual([7]);
    expect(filter('all', 'convert_time').mcp.map((s) => s.id)).toEqual([7]);
    expect(filter('all', 'git 歷史').skills.map((s) => s.id)).toEqual([3]);
  });
  it('matches the fallback summary of a custom tool without a description', () => {
    expect(filter('custom_api', '外部自訂 API').custom.map((t) => t.id)).toEqual([2]);
  });
  it('hides sections without a match and reports when nothing matches', () => {
    const catalog = filter('all', '工單');
    expect(catalog.visible).toEqual({ builtin: false, custom: true, mcp: false, skills: false });
    expect(catalog.nothingMatches).toBe(false);
    expect(filter('all', 'no-such-tool').nothingMatches).toBe(true);
    expect(filter('skills', '匯率').nothingMatches).toBe(true);
  });
});
describe('counts and summaries', () => {
  it('counts tabs the same way as before the redesign', () => {
    expect(categoryCounts(inventory)).toEqual({
      all: DEFAULT_TOOLS_METADATA.length + 2 + 2 + 2,
      knowledge: 2,
      web: 2,
      custom_api: 2,
      mcp: 2,
      skills: 2,
    });
  });
  it('summarises each section from its rows', () => {
    expect(sectionSummaries(inventory)).toEqual({
      builtin: `${DEFAULT_TOOLS_METADATA.length} 項，一律啟用`,
      custom: '2 項，1 項啟用',
      mcp: '2 台，1 台已連線並啟用，提供 2 個工具',
      skills: '2 個，1 個啟用',
    });
  });
  it('lists every item that needs attention', () => {
    expect(attentionItems(inventory).map((item) => item.text)).toEqual([
      'MCP 伺服器「文件搜尋」連線錯誤',
      'MCP 伺服器「文件搜尋」的憑證需要重新輸入',
      '自訂工具「派遣工單」的憑證需要重新輸入',
      '技能「pdf-forms」找不到技能檔案',
    ]);
    expect(attentionItems({ customTools: [customTools[0]], servers: [servers[0]], skills: [skills[0]] })).toEqual([]);
  });
});
describe('tool details', () => {
  it('describes a custom tool for the catalog', () => {
    expect(describeCustomTool(customTools[0])).toMatchObject({
      isCustom: true,
      categoryName: '自訂 API',
      executionMode: '外部 RESTful API',
      priority: '自主按需呼叫',
      triggerTiming: '當使用者提問與「匯率換算」相關之業務或資料時自主呼叫。',
      summary: '查詢即時匯率',
    });
    expect(describeCustomTool(customTools[1]).summary).toBe('外部自訂 API 服務端點。');
  });
  it('lists custom parameters from the JSON schema and built-in ones as declared', () => {
    expect(toolParameters(describeCustomTool(customTools[0]))).toEqual([
      { name: 'from', type: 'string', required: true, desc: '來源貨幣' },
      { name: 'amount', type: 'string', required: false, desc: '金額' },
    ]);
    expect(toolParameters(describeCustomTool(customTools[1]))).toEqual([]);
    expect(toolParameters(DEFAULT_TOOLS_METADATA[3])).toEqual(DEFAULT_TOOLS_METADATA[3].parameters);
  });
  it('attaches the backend description to the matching built-in tool', () => {
    const merged = withBackendDescriptions(DEFAULT_TOOLS_METADATA, [
      { type: 'function', function: { name: 'web_search', description: '搜尋網路' } },
      { name: 'web_fetch', description: '讀取網頁' },
    ]);
    expect(merged.find((t) => t.name === 'web_search').backendDescription).toBe('搜尋網路');
    expect(merged.find((t) => t.name === 'web_fetch').backendDescription).toBe('讀取網頁');
    expect(merged.find((t) => t.name === 'search_knowledge_base')).toBe(DEFAULT_TOOLS_METADATA[0]);
  });
  it('explains what deleting removes', () => {
    expect(deleteDescription({ type: 'skill', item: skills[0] })).toBe('「release-notes」刪除後會一併移除技能檔案，AI 就無法再使用這個技能，此操作無法復原。');
    expect(deleteDescription({ type: 'server', item: servers[0] })).toBe('「時間服務」刪除後，AI 就無法再使用它提供的工具，此操作無法復原。');
  });
});
describe('mcp tool hints', () => {
  it('reads the four annotations with the spec defaults', () => {
    expect(mcpToolHints({ annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false } })).toEqual(['唯讀']);
    expect(mcpToolHints({ annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true } })).toEqual(['會連到外部']);
    expect(mcpToolHints({})).toEqual(['可能變更資料', '會連到外部']);
  });
});