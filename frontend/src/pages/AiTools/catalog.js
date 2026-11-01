export const CATEGORY_FILTERS = [
  { value: 'all', label: '全部工具' },
  { value: 'custom_api', label: '自訂 API 工具' },
  { value: 'mcp', label: 'MCP 伺服器' },
  { value: 'skills', label: 'Agent Skills' },
  { value: 'knowledge', label: '知識庫與資料' },
  { value: 'web', label: '聯網與閱讀' },
];
const SECTION_CATEGORIES = {
  builtin: ['all', 'knowledge', 'web'],
  custom: ['all', 'custom_api'],
  mcp: ['all', 'mcp'],
  skills: ['all', 'skills'],
};
export const DELETE_TITLES = {
  tool: '刪除這個自訂 API 工具？',
  server: '刪除這台 MCP 伺服器？',
  skill: '刪除這個技能？',
};
export const deleteDescription = (pending) => (pending?.type === 'skill'
  ? `「${pending.item.name}」刪除後會一併移除技能檔案，AI 就無法再使用這個技能，此操作無法復原。`
  : `「${pending?.item.display_name}」刪除後，AI 就無法再使用它提供的工具，此操作無法復原。`);
export const matchesQuery = (query, ...values) =>
  values.some((value) => typeof value === 'string' && value.toLowerCase().includes(query));
export const normalizeQuery = (searchQuery) => searchQuery.trim().toLowerCase();
export const withBackendDescriptions = (metadata, backendTools) => metadata.map((meta) => {
  const matched = backendTools.find((t) => (t.function ? t.function.name : t.name) === meta.name);
  if (!matched) return meta;
  const func = matched.function || matched;
  return { ...meta, backendDescription: func.description };
});
export const describeBuiltinTool = (tool) => ({ ...tool, isCustom: false, isMcp: false, is_enabled: true });
export const describeCustomTool = (tool) => ({
  ...tool,
  isCustom: true,
  isMcp: false,
  categoryName: '自訂 API',
  icon: 'code',
  executionMode: '外部 RESTful API',
  priority: '自主按需調用',
  triggerTiming: `當使用者提問與「${tool.display_name}」相關之業務或資料時自主調用。`,
  summary: tool.description || '外部自訂 API 服務端點。',
  examples: [`請調用 ${tool.display_name} 查詢相關資料`, `查詢 ${tool.name} 的即時結果`],
});
export const toolParameters = (tool) => (tool.isCustom
  ? Object.entries(tool.parameters_schema?.properties || {}).map(([name, schema]) => ({
    name,
    type: schema.type || 'string',
    required: tool.parameters_schema?.required?.includes(name),
    desc: schema.description || '',
  }))
  : tool.parameters || []);
export const countMcpTools = (servers) => servers.reduce((acc, s) => acc + (s.discovered_tools?.length || 0), 0);
const toolMatches = (query, tool) =>
  matchesQuery(query, tool.displayName, tool.display_name, tool.name, tool.summary, tool.description, tool.url);
const serverMatches = (query, server) => matchesQuery(
  query,
  server.display_name,
  server.name,
  server.description,
  server.command,
  ...(server.args || []),
  server.url,
  ...(server.discovered_tools || []).map((t) => t.name)
);
const skillMatches = (query, skill) => matchesQuery(query, skill.name, skill.description, skill.compatibility);
const builtinInCategory = (tool, category) => (category === 'knowledge' || category === 'web'
  ? tool.category === category
  : category === 'all');
export const filterCatalog = ({ builtinTools, customTools, servers, skills, category, query }) => {
  const shown = Object.fromEntries(
    Object.entries(SECTION_CATEGORIES).map(([section, categories]) => [section, categories.includes(category)])
  );
  const builtin = builtinTools
    .map(describeBuiltinTool)
    .filter((tool) => builtinInCategory(tool, category) && (!query || toolMatches(query, tool)));
  const custom = customTools
    .map(describeCustomTool)
    .filter((tool) => shown.custom && (!query || toolMatches(query, tool)));
  const matchedServers = servers.filter((server) => !query || serverMatches(query, server));
  const matchedSkills = skills.filter((skill) => !query || skillMatches(query, skill));
  const results = { builtin, custom, mcp: matchedServers, skills: matchedSkills };
  const visible = Object.fromEntries(
    Object.keys(SECTION_CATEGORIES).map((section) => [section, shown[section] && !(query && results[section].length === 0)])
  );
  const nothingMatches = Boolean(query) && Object.values(visible).every((isVisible) => !isVisible);
  return { ...results, visible, nothingMatches };
};
export const categoryCounts = ({ builtinTools, customTools, servers, skills }) => ({
  all: builtinTools.length + customTools.length + countMcpTools(servers) + skills.length,
  knowledge: builtinTools.filter((t) => t.category === 'knowledge').length,
  web: builtinTools.filter((t) => t.category === 'web').length,
  custom_api: customTools.length,
  mcp: servers.length,
  skills: skills.length,
});
export const sectionSummaries = ({ builtinTools, customTools, servers, skills }) => ({
  builtin: `${builtinTools.length} 項，一律啟用`,
  custom: `${customTools.length} 項，${customTools.filter((t) => t.is_enabled).length} 項啟用`,
  mcp: `${servers.length} 台，${servers.filter((s) => s.is_enabled && s.status === 'connected').length} 台已連線並啟用，提供 ${countMcpTools(servers)} 個工具`,
  skills: `${skills.length} 個，${skills.filter((s) => s.is_enabled).length} 個啟用`,
});
export const attentionItems = ({ customTools, servers, skills }) => [
  ...servers.filter((s) => s.status === 'error').map((s) => ({ key: `server-error-${s.id}`, text: `MCP 伺服器「${s.display_name}」連線錯誤` })),
  ...servers.filter((s) => s.credentials_unreadable).map((s) => ({ key: `server-credentials-${s.id}`, text: `MCP 伺服器「${s.display_name}」的憑證需要重新輸入` })),
  ...customTools.filter((t) => t.credentials_unreadable).map((t) => ({ key: `tool-credentials-${t.id}`, text: `自訂工具「${t.display_name}」的憑證需要重新輸入` })),
  ...skills.filter((s) => !s.files_present).map((s) => ({ key: `skill-files-${s.id}`, text: `技能「${s.name}」找不到技能檔案` })),
];
