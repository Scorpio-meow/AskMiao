import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { chatService, apiToolService, mcpService, skillService } from '../../services/api';
import { describeRequestError } from '../../utils/secureLogger';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import {
  Alert,
  Button,
  ConfirmDialog,
  Icon,
  Snackbar,
  Switch
} from '../../components/ui';
import ApiToolFormDialog from './ApiToolFormDialog';
import ApiToolTestDialog from './ApiToolTestDialog';
import { DEFAULT_TOOLS_METADATA } from './builtinTools';
import McpServerFormDialog from './McpServerFormDialog';
import McpToolTestDialog from './McpToolTestDialog';
import OpenApiImportDialog from './OpenApiImportDialog';
import SkillAccessDialog from './SkillAccessDialog';
import SkillDetailDialog from './SkillDetailDialog';
import SkillUploadDialog from './SkillUploadDialog';
import { CREDENTIALS_UNREADABLE_NOTICE, getMethodClass, getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
const matchesQuery = (query, ...values) =>
  values.some((value) => typeof value === 'string' && value.toLowerCase().includes(query));
const CATEGORY_FILTERS = [
  { value: 'all', label: '全部工具' },
  { value: 'mcp', label: 'MCP 協定伺服器' },
  { value: 'skills', label: 'Agent Skills' },
  { value: 'knowledge', label: '知識庫與資料' },
  { value: 'web', label: '聯網與閱讀' },
  { value: 'custom_api', label: '自訂 API 工具' },
];
const DELETE_TITLES = {
  tool: '刪除這個自訂 API 工具？',
  server: '刪除這台 MCP 伺服器？',
  skill: '刪除這個技能？',
};
export default function AiTools() {
  const navigate = useNavigate();
  const [defaultTools, setDefaultTools] = useState(DEFAULT_TOOLS_METADATA);
  const [customTools, setCustomTools] = useState([]);
  const [mcpServers, setMcpServers] = useState([]);
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeCategory, setActiveCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  useDocumentTitle('AI 工具');
  // 提示訊息（對話框開啟時的錯誤改顯示在對話框內）
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info', key: 0 });
  const [pendingDelete, setPendingDelete] = useState(null);
  // 目前開啟的對話框：{ type, ...props }；對話框關閉時卸載，下次開啟從空白狀態開始
  const [dialog, setDialog] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [mcpPresets, setMcpPresets] = useState([]);
  const [discoveringId, setDiscoveringId] = useState(null);
  const showSnackbar = (message, severity) => {
    setSnackbar((prev) => ({ open: true, message, severity, key: prev.key + 1 }));
  };
  // 載入後端工具清單與 MCP 伺服器
  const fetchAllTools = useCallback(async () => {
    try {
      setLoading(true);
      const [resDefault, resCustom, resMcp, resPresets, resSkills] = await Promise.allSettled([
        chatService.getTools(),
        apiToolService.getTools(),
        mcpService.getServers(),
        mcpService.getPresets(),
        skillService.getSkills()
      ]);
      if (resDefault.status === 'fulfilled' && resDefault.value?.tools) {
        const updated = DEFAULT_TOOLS_METADATA.map((meta) => {
          const matched = resDefault.value.tools.find(
            (t) => (t.function ? t.function.name : t.name) === meta.name
          );
          if (matched) {
            const func = matched.function || matched;
            return { ...meta, backendDescription: func.description };
          }
          return meta;
        });
        setDefaultTools(updated);
      }
      if (resCustom.status === 'fulfilled' && resCustom.value?.tools) {
        setCustomTools(resCustom.value.tools);
      }
      if (resMcp.status === 'fulfilled' && resMcp.value?.servers) {
        setMcpServers(resMcp.value.servers);
      }
      if (resPresets.status === 'fulfilled' && resPresets.value?.presets) {
        setMcpPresets(resPresets.value.presets);
      }
      if (resSkills.status === 'fulfilled' && resSkills.value?.skills) {
        setSkills(resSkills.value.skills);
      }
    } catch (err) {
      console.warn('載入工具清單失敗:', describeRequestError(err));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    queueMicrotask(() => {
      fetchAllTools();
    });
  }, [fetchAllTools]);
  const handleTestExample = (exampleText) => {
    navigate('/chat', { state: { prefillPrompt: exampleText } });
  };
  // 切換自訂 API 工具啟用狀態
  const handleToggleCustomTool = async (toolId) => {
    try {
      const res = await apiToolService.toggleTool(toolId);
      setCustomTools((prev) =>
        prev.map((t) => (t.id === toolId ? { ...t, is_enabled: res.is_enabled } : t))
      );
      showSnackbar(res.message, 'success');
    } catch (err) {
      console.warn('切換工具狀態失敗:', describeRequestError(err));
      showSnackbar(getRequestErrorMessage(err, '切換狀態失敗'), 'error');
    }
  };
  // 刪除自訂 API 工具或 MCP 伺服器（先經過確認對話框）
  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    const { type, item } = pendingDelete;
    setDeleting(true);
    try {
      if (type === 'tool') {
        await apiToolService.deleteTool(item.id);
        setCustomTools((prev) => prev.filter((t) => t.id !== item.id));
        showSnackbar(`已刪除工具「${item.display_name}」`, 'success');
      } else if (type === 'skill') {
        await skillService.deleteSkill(item.id);
        setSkills((prev) => prev.filter((s) => s.id !== item.id));
        showSnackbar(`已刪除技能「${item.name}」`, 'success');
      } else {
        await mcpService.deleteServer(item.id);
        setMcpServers((prev) => prev.filter((s) => s.id !== item.id));
        showSnackbar(`已刪除 MCP 伺服器「${item.display_name}」`, 'success');
      }
    } catch (err) {
      console.warn('刪除失敗:', describeRequestError(err));
      showSnackbar(getRequestErrorMessage(err, '刪除失敗，請稍後再試'), 'error');
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  };
  const closeDialog = () => setDialog(null);
  const handleDialogSaved = (message) => {
    setDialog(null);
    showSnackbar(message, 'success');
    fetchAllTools();
  };
  // --- MCP 相關操作 ---
  // 切換 MCP 伺服器啟用狀態
  const handleToggleMcpServer = async (serverId) => {
    try {
      const res = await mcpService.toggleServer(serverId);
      setMcpServers((prev) =>
        prev.map((s) => (s.id === serverId ? { ...s, is_enabled: res.is_enabled } : s))
      );
      showSnackbar(res.message, 'success');
    } catch (err) {
      console.warn('切換 MCP 狀態失敗:', describeRequestError(err));
      showSnackbar(getRequestErrorMessage(err, '切換狀態失敗'), 'error');
    }
  };
  const handleSkillScripts = async (skill) => {
    try {
      const res = await skillService.updateSkillSettings(skill.id, { allow_scripts: !skill.allow_scripts });
      setSkills((prev) => prev.map((s) => (s.id === skill.id ? res.skill : s)));
      showSnackbar(res.skill.allow_scripts ? `已允許「${skill.name}」執行腳本` : `已停止「${skill.name}」執行腳本`, 'success');
    } catch (err) {
      console.warn('更新技能設定失敗:', describeRequestError(err));
      showSnackbar(getRequestErrorMessage(err, '更新技能設定失敗'), 'error');
    }
  };
  const handleStartOAuth = async (server) => {
    const popup = window.open('', '_blank');
    try {
      const res = await mcpService.startOAuth(server.id);
      if (popup) {
        popup.opener = null;
        popup.location.href = res.authorization_url;
      } else {
        window.location.assign(res.authorization_url);
      }
      showSnackbar('已開啟授權頁面，完成登入後回到這裡重新探索工具', 'info');
    } catch (err) {
      popup?.close();
      console.warn('啟動 OAuth 授權失敗:', describeRequestError(err));
      showSnackbar(getRequestErrorMessage(err, '啟動 OAuth 授權失敗'), 'error');
    }
  };
  const handleRevokeOAuth = async (server) => {
    try {
      const res = await mcpService.revokeOAuth(server.id);
      setMcpServers((prev) => prev.map((s) => (s.id === server.id ? res.server : s)));
      showSnackbar(res.message, 'success');
    } catch (err) {
      console.warn('清除 OAuth 授權失敗:', describeRequestError(err));
      showSnackbar(getRequestErrorMessage(err, '清除 OAuth 授權失敗'), 'error');
    }
  };
  const handleToggleSkill = async (skillId) => {
    try {
      const res = await skillService.toggleSkill(skillId);
      setSkills((prev) =>
        prev.map((s) => (s.id === skillId ? { ...s, is_enabled: res.is_enabled } : s))
      );
      showSnackbar(res.message, 'success');
    } catch (err) {
      console.warn('切換技能狀態失敗:', describeRequestError(err));
      showSnackbar(getRequestErrorMessage(err, '切換狀態失敗'), 'error');
    }
  };
  // 探索 MCP 工具清單
  const handleDiscoverMcpServer = async (serverId) => {
    try {
      setDiscoveringId(serverId);
      const res = await mcpService.discoverServer(serverId);
      setMcpServers((prev) =>
        prev.map((s) => (s.id === serverId ? res.server : s))
      );
      showSnackbar(res.message, 'success');
    } catch (err) {
      console.warn('探索 MCP 伺服器失敗:', describeRequestError(err));
      showSnackbar(getRequestErrorMessage(err, '連線與探索 MCP 工具失敗'), 'error');
      // 重新整理取得更新後的 error status
      fetchAllTools();
    } finally {
      setDiscoveringId(null);
    }
  };
  // 計算 MCP 工具總數
  const totalMcpToolsCount = mcpServers.reduce((acc, s) => {
    return acc + (s.discovered_tools?.length || 0);
  }, 0);
  // 整理所有工具以供呈現
  const allUnifiedTools = [
    ...defaultTools.map((t) => ({ ...t, isCustom: false, isMcp: false, is_enabled: true })),
    ...customTools.map((t) => ({
      ...t,
      isCustom: true,
      isMcp: false,
      categoryName: '自訂 API',
      icon: 'code',
      executionMode: '外部 RESTful API',
      priority: '自主按需調用',
      triggerTiming: `當使用者提問與「${t.display_name}」相關之業務或資料時自主調用。`,
      summary: t.description || '外部自訂 API 服務端點。',
      examples: [`請調用 ${t.display_name} 查詢相關資料`, `查詢 ${t.name} 的即時結果`]
    }))
  ];
  const query = searchQuery.trim().toLowerCase();
  const filteredTools = allUnifiedTools.filter((tool) => {
    let matchesCategory = true;
    if (activeCategory === 'knowledge') matchesCategory = tool.category === 'knowledge';
    else if (activeCategory === 'web') matchesCategory = tool.category === 'web';
    else if (activeCategory === 'custom_api') matchesCategory = tool.isCustom;
    const matches = !query || matchesQuery(query, tool.displayName, tool.display_name, tool.name, tool.summary, tool.description, tool.url);
    return matchesCategory && matches;
  });
  const filteredServers = mcpServers.filter((server) => (
    !query || matchesQuery(
      query,
      server.display_name,
      server.name,
      server.description,
      server.command,
      ...(server.args || []),
      server.url,
      ...(server.discovered_tools || []).map((t) => t.name)
    )
  ));
  const filteredSkills = skills.filter((skill) => (
    !query || matchesQuery(query, skill.name, skill.description, skill.compatibility)
  ));
  const showServers = activeCategory === 'all' || activeCategory === 'mcp';
  const showSkills = activeCategory === 'all' || activeCategory === 'skills';
  const showTools = activeCategory !== 'mcp' && activeCategory !== 'skills';
  const nothingMatches = Boolean(query)
    && (!showServers || filteredServers.length === 0)
    && (!showSkills || filteredSkills.length === 0)
    && (!showTools || filteredTools.length === 0);
  const categoryCounts = {
    all: allUnifiedTools.length + totalMcpToolsCount + skills.length,
    mcp: mcpServers.length,
    skills: skills.length,
    knowledge: defaultTools.filter((t) => t.category === 'knowledge').length,
    web: defaultTools.filter((t) => t.category === 'web').length,
    custom_api: customTools.length,
  };
  return (
    <div className={styles.container}>
      {/* 頂部 Hero 區塊 */}
      <section className={styles.heroSection}>
        <div className={styles.heroContent}>
          <div className={styles.heroBadge}>
            <Icon name="tune" size={14} />
            <span>AI 工具與 MCP 協定核心中心</span>
          </div>
          <h1 className={styles.heroTitle}>AI 可用工具與 MCP 全景總覽</h1>
          <p className={styles.heroSubtitle}>
            本系統內建自主研究調度引擎（Agentic Research Engine），支援內部知識庫混合檢索、結構化記錄篩選統計、即時聯網搜尋與深入閱讀，並全面原生支援 Model Context Protocol (MCP) 開放標準與全版本 OpenAPI Specification（Swagger 2.0、OpenAPI 3.0 / 3.1）。
          </p>
          <div className={styles.heroActions}>
            <Button
              variant="primary"
              onClick={() => navigate('/chat')}
              startIcon={<Icon name="chat" size={18} />}
            >
              前往對話體驗工具
            </Button>
            <Button
              variant="secondary"
              onClick={() => setDialog({ type: 'mcpForm', server: null })}
              startIcon={<Icon name="build" size={18} />}
            >
              新增 MCP 伺服器
            </Button>
            <Button
              variant="secondary"
              onClick={() => setDialog({ type: 'skillUpload', skill: null })}
              startIcon={<Icon name="sparkles" size={18} />}
            >
              上傳 Agent Skill
            </Button>
            <Button
              variant="secondary"
              onClick={() => setDialog({ type: 'import' })}
              startIcon={<Icon name="upload" size={18} />}
            >
              匯入 OpenAPI 規格
            </Button>
            <Button
              variant="secondary"
              onClick={() => setDialog({ type: 'toolForm', tool: null })}
              startIcon={<Icon name="add" size={18} />}
            >
              手動新增 API 工具
            </Button>
            <Button
              variant="secondary"
              onClick={fetchAllTools}
              loading={loading}
              startIcon={<Icon name="refresh" size={18} />}
            >
              重新整理狀態
            </Button>
          </div>
        </div>
      </section>
      {/* 指標概覽 */}
      <div className={styles.metricsGrid}>
        <div className={styles.metricCard}>
          <span className={styles.metricLabel}>內建核心工具</span>
          <div className={styles.metricValue}>
            <Icon name="tools" size={24} color="var(--color-primary)" />
            <span>{defaultTools.length} 項</span>
          </div>
          <span className={styles.metricDesc}>知識庫檢索、統計、聯網與閱讀</span>
        </div>
        <div className={styles.metricCard}>
          <span className={styles.metricLabel}>MCP 協定伺服器</span>
          <div className={styles.metricValue}>
            <Icon name="build" size={24} color="var(--color-warning)" />
            <span>{mcpServers.length} 台 ({totalMcpToolsCount} 工具)</span>
          </div>
          <span className={styles.metricDesc}>已連線啟用：{mcpServers.filter((s) => s.is_enabled && s.status === 'connected').length} 台</span>
        </div>
        <div className={styles.metricCard}>
          <span className={styles.metricLabel}>自訂 API 工具</span>
          <div className={styles.metricValue}>
            <Icon name="code" size={24} color="var(--color-info)" />
            <span>{customTools.length} 項</span>
          </div>
          <span className={styles.metricDesc}>已啟用：{customTools.filter((t) => t.is_enabled).length} 項</span>
        </div>
        <div className={styles.metricCard}>
          <span className={styles.metricLabel}>標準相容性</span>
          <div className={styles.metricValue}>
            <Icon name="check-circle" size={24} color="var(--color-success)" />
            <span>MCP & OAS 全版本</span>
          </div>
          <span className={styles.metricDesc}>Model Context Protocol + Swagger 2.0 / 3.0 / 3.1</span>
        </div>
      </div>
      {/* 篩選與搜尋列 */}
      <div className={styles.filterBar}>
        <div className={styles.tabGroup} role="group" aria-label="工具分類">
          {CATEGORY_FILTERS.map((filter) => (
            <button
              key={filter.value}
              type="button"
              className={`${styles.tabBtn} ${activeCategory === filter.value ? styles.tabBtnActive : ''}`}
              onClick={() => setActiveCategory(filter.value)}
              aria-pressed={activeCategory === filter.value}
            >
              {filter.label} ({categoryCounts[filter.value]})
            </button>
          ))}
        </div>
        <search className={styles.searchBox}>
          <Icon name="search" size={16} color="var(--text-tertiary)" />
          <input
            type="search"
            className={styles.searchInput}
            placeholder="搜尋工具名稱、網址、MCP 伺服器、技能…"
            aria-label="搜尋工具"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </search>
      </div>
      {nothingMatches && (
        <div className={styles.emptyNotice}>
          <p>查無符合「{searchQuery.trim()}」的工具、MCP 伺服器或技能</p>
          <Button variant="secondary" size="sm" onClick={() => setSearchQuery('')}>
            清除搜尋
          </Button>
        </div>
      )}
      {/* 1. MCP 伺服器列表區塊 (當 activeCategory === 'mcp' 或 'all' 時展示) */}
      {showServers && !(query && filteredServers.length === 0) && (
        <section className={styles.serverSection} aria-labelledby="mcp-section-title">
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle} id="mcp-section-title">
              <Icon name="build" size={20} color="var(--color-primary)" />
              <span>Model Context Protocol (MCP) 伺服器</span>
            </h2>
            <Button
              variant="secondary"
              onClick={() => setDialog({ type: 'mcpForm', server: null })}
              startIcon={<Icon name="add" size={16} />}
            >
              新增 MCP 伺服器
            </Button>
          </div>
          {filteredServers.length === 0 ? (
            <div className={styles.emptyNotice}>
              <p>尚未配置任何 MCP 伺服器，點擊「新增 MCP 伺服器」即可套用 Time、Filesystem 等預設範本或自訂指令。</p>
            </div>
          ) : (
            <div className={styles.toolsList}>
              {filteredServers.map((server) => {
                const isEnabled = server.is_enabled;
                const isConnected = server.status === 'connected';
                const isError = server.status === 'error';
                const tools = server.discovered_tools || [];
                return (
                  <article key={server.id} className={styles.toolOuterShell} aria-labelledby={`mcp-server-${server.id}`}>
                    <div className={styles.toolInnerCore}>
                      <div className={styles.toolHeader}>
                        <div className={styles.toolIdentity}>
                          <div className={`${styles.toolIconBox} ${styles.toolIconBoxMcp}`}>
                            <Icon name="build" size={22} />
                          </div>
                          <div className={styles.toolTitleWrap}>
                            <h3 className={styles.toolTitle} id={`mcp-server-${server.id}`}>
                              <span className={`${styles.methodBadge} ${styles.methodPost}`}>
                                {server.transport_type}
                              </span>
                              <span>{server.display_name}</span>
                            </h3>
                            <div className={styles.toolIdentifier}>{server.name}</div>
                          </div>
                        </div>
                        <div className={styles.toolStatusWrap}>
                          <span className={styles.categoryTag}>MCP Server</span>
                          {server.oauth_authorized && <span className={styles.versionTag}>OAuth 已授權</span>}
                          <span className={`${styles.statusPill} ${isConnected ? styles.statusActive : isError ? styles.statusError : styles.statusDisabled}`}>
                            <span className={styles.statusDot} />
                            <span>
                              {isConnected ? '已連線 (Connected)' : isError ? '連線錯誤 (Error)' : '未連線'}
                            </span>
                          </span>
                          <div className={styles.switchGroup}>
                            <span className={`${styles.enabledText} ${isEnabled ? styles.enabledTextOn : ''}`}>
                              {isEnabled ? '已啟用' : '已停用'}
                            </span>
                            <Switch
                              checked={isEnabled}
                              onChange={() => handleToggleMcpServer(server.id)}
                              aria-label={`啟用 MCP 伺服器「${server.display_name}」`}
                            />
                          </div>
                        </div>
                      </div>
                      <p className={styles.toolDescription}>{server.description || 'MCP 協定外部工具伺服器。'}</p>
                      {/* 連線執行配置 */}
                      <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                        <div className={styles.specLabel}>
                          <Icon name="terminal" size={14} color="var(--color-primary)" />
                          <span>
                            {server.transport_type === 'stdio' ? 'Stdio 啟動指令與參數' : 'HTTP / SSE 連線網址'}
                          </span>
                        </div>
                        <div className={`${styles.specContent} ${styles.monoText}`}>
                          {server.transport_type === 'stdio'
                            ? `${server.command || ''} ${(server.args || []).join(' ')}`
                            : server.url}
                        </div>
                      </div>
                      {server.credentials_unreadable && (
                        <div className={`${styles.specBlock} ${styles.specBlockSpaced} ${styles.specBlockError}`}>
                          <div className={styles.specLabel}>
                            <Icon name="warning" size={14} />
                            <span>憑證需要重新輸入</span>
                          </div>
                          <div className={styles.specContent}>{CREDENTIALS_UNREADABLE_NOTICE}</div>
                        </div>
                      )}
                      {/* 錯誤資訊 */}
                      {server.last_error && (
                        <div className={`${styles.specBlock} ${styles.specBlockSpaced} ${styles.specBlockError}`}>
                          <div className={styles.specLabel}>
                            <Icon name="warning" size={14} />
                            <span>最近一次連線/探索異常紀錄</span>
                          </div>
                          <div className={styles.specContent}>
                            {server.last_error}
                          </div>
                        </div>
                      )}
                      {/* 探索到的 MCP Tools 清單 */}
                      <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                        <div className={`${styles.specLabel} ${styles.specLabelSplit}`}>
                          <div className={styles.inlineGroup}>
                            <Icon name="code" size={14} color="var(--color-primary)" />
                            <span>提供之 MCP 工具 ({tools.length} 項)</span>
                          </div>
                          <Button
                            variant="secondary"
                            onClick={() => handleDiscoverMcpServer(server.id)}
                            loading={discoveringId === server.id}
                            startIcon={<Icon name="refresh" size={14} />}
                          >
                            {discoveringId === server.id ? '正在連線探索...' : '重新探索工具 (tools/list)'}
                          </Button>
                        </div>
                        {tools.length === 0 ? (
                          <p className={styles.mutedNote}>
                            尚未探索到工具，請點擊上方按鈕執行工具探索。
                          </p>
                        ) : (
                          <ul className={styles.mcpToolList} role="list">
                            {tools.map((t) => (
                              <li key={t.name} className={styles.mcpToolItem}>
                                <div className={styles.mcpToolText}>
                                  <div className={styles.mcpToolName}>{t.name}</div>
                                  <div className={styles.mcpToolDescription}>{t.description || '無詳細說明'}</div>
                                </div>
                                <Button
                                  variant="secondary"
                                  onClick={() => setDialog({ type: 'mcpTest', server, tool: t })}
                                  startIcon={<Icon name="speed" size={14} />}
                                >
                                  線上測試<span className="sr-only"> {t.name}</span>
                                </Button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                      {(server.discovered_resources?.length > 0 || server.discovered_prompts?.length > 0) && (
                        <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                          <div className={styles.specLabel}>
                            <Icon name="description" size={14} color="var(--color-primary)" />
                            <span>
                              提供之 resources ({server.discovered_resources?.length || 0} 項) 與 prompts ({server.discovered_prompts?.length || 0} 項)
                            </span>
                          </div>
                          <ul className={styles.mcpToolList} role="list">
                            {(server.discovered_resources || []).map((r) => (
                              <li key={`r-${r.uri}`} className={styles.mcpToolItem}>
                                <div className={styles.mcpToolText}>
                                  <div className={`${styles.mcpToolName} ${styles.monoText}`}>{r.uri}</div>
                                  <div className={styles.mcpToolDescription}>{r.name}{r.description ? `：${r.description}` : ''}</div>
                                </div>
                                <span className={styles.versionTag}>resource</span>
                              </li>
                            ))}
                            {(server.discovered_prompts || []).map((pr) => (
                              <li key={`p-${pr.name}`} className={styles.mcpToolItem}>
                                <div className={styles.mcpToolText}>
                                  <div className={styles.mcpToolName}>{pr.name}</div>
                                  <div className={styles.mcpToolDescription}>{pr.description || '無詳細說明'}</div>
                                </div>
                                <span className={styles.versionTag}>prompt</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {/* 伺服器操作按鈕 */}
                      <div className={styles.toolActionsFooter}>
                        <div className={styles.toolActionGroup}>
                          <Button
                            variant="secondary"
                            onClick={() => setDialog({ type: 'mcpForm', server })}
                            startIcon={<Icon name="edit" size={16} />}
                          >
                            編輯伺服器配置
                          </Button>
                          {server.transport_type !== 'stdio' && (
                            <Button
                              variant="secondary"
                              onClick={() => handleStartOAuth(server)}
                              startIcon={<Icon name="lock" size={16} />}
                            >
                              {server.oauth_authorized ? '重新 OAuth 授權' : 'OAuth 授權'}
                            </Button>
                          )}
                          {server.oauth_authorized && (
                            <Button variant="secondary" onClick={() => handleRevokeOAuth(server)} startIcon={<Icon name="close" size={16} />}>
                              清除授權
                            </Button>
                          )}
                        </div>
                        <Button
                          variant="danger"
                          onClick={() => setPendingDelete({ type: 'server', item: server })}
                          startIcon={<Icon name="delete" size={16} />}
                        >
                          刪除伺服器
                        </Button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}
      {showSkills && !(query && filteredSkills.length === 0) && (
        <section className={styles.serverSection} aria-labelledby="skills-section-title">
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle} id="skills-section-title">
              <Icon name="sparkles" size={20} color="var(--color-primary)" />
              <span>Agent Skills 技能</span>
            </h2>
            <Button
              variant="secondary"
              onClick={() => setDialog({ type: 'skillUpload', skill: null })}
              startIcon={<Icon name="upload" size={16} />}
            >
              上傳技能
            </Button>
          </div>
          {filteredSkills.length === 0 ? (
            <div className={styles.emptyNotice}>
              <p>尚未安裝任何技能。上傳符合 Agent Skills 規格的技能後，AI 會在任務符合技能描述時自動載入，使用者也可以在對話中輸入「/技能名稱」指定使用。</p>
            </div>
          ) : (
            <div className={styles.toolsList}>
              {filteredSkills.map((skill) => {
                const isEnabled = skill.is_enabled;
                return (
                  <article key={skill.id} className={styles.toolOuterShell} aria-labelledby={`skill-${skill.id}`}>
                    <div className={styles.toolInnerCore}>
                      <div className={styles.toolHeader}>
                        <div className={styles.toolIdentity}>
                          <div className={styles.toolIconBox}>
                            <Icon name="sparkles" size={22} />
                          </div>
                          <div className={styles.toolTitleWrap}>
                            <h3 className={styles.toolTitle} id={`skill-${skill.id}`}>
                              <span>{skill.name}</span>
                            </h3>
                            <div className={styles.toolIdentifier}>/{skill.name}</div>
                          </div>
                        </div>
                        <div className={styles.toolStatusWrap}>
                          <span className={styles.categoryTag}>Agent Skill</span>
                          {skill.license && <span className={styles.versionTag}>{skill.license}</span>}
                          {!skill.files_present && (
                            <span className={`${styles.statusPill} ${styles.statusError}`}>
                              <span className={styles.statusDot} />
                              <span>找不到技能檔案</span>
                            </span>
                          )}
                          {skill.allowed_user_ids !== null && (
                            <span className={styles.versionTag}>限 {skill.allowed_user_ids.length} 位使用者</span>
                          )}
                          <div className={styles.switchGroup}>
                            <span className={`${styles.enabledText} ${isEnabled ? styles.enabledTextOn : ''}`}>
                              {isEnabled ? '已啟用' : '已停用'}
                            </span>
                            <Switch
                              checked={isEnabled}
                              onChange={() => handleToggleSkill(skill.id)}
                              aria-label={`啟用技能「${skill.name}」`}
                            />
                          </div>
                        </div>
                      </div>
                      <p className={styles.toolDescription}>{skill.description}</p>
                      {skill.compatibility && (
                        <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                          <div className={styles.specLabel}>
                            <Icon name="info" size={14} color="var(--color-primary)" />
                            <span>相容性需求</span>
                          </div>
                          <div className={styles.specContent}>{skill.compatibility}</div>
                        </div>
                      )}
                      <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                        <div className={`${styles.specLabel} ${styles.specLabelSplit}`}>
                          <div className={styles.inlineGroup}>
                            <Icon name="terminal" size={14} color="var(--color-primary)" />
                            <span>允許執行技能內的腳本</span>
                          </div>
                          <Switch
                            checked={Boolean(skill.allow_scripts)}
                            onChange={() => handleSkillScripts(skill)}
                            aria-label={`允許技能「${skill.name}」執行腳本`}
                          />
                        </div>
                        <div className={styles.specContent}>
                          開啟後 AI 可以要求在主機上執行技能中的 .py、.sh、.js 腳本，每次都需要提問者在對話中核准（技能的 allowed-tools 列出 run_skill_script 時，載入技能後免核准）。腳本以後端帳號的權限執行，只對信任的技能開啟。
                        </div>
                      </div>
                      {skill.warnings.length > 0 && (
                        <div className={`${styles.specBlock} ${styles.specBlockSpaced} ${styles.specBlockError}`}>
                          <div className={styles.specLabel}>
                            <Icon name="warning" size={14} />
                            <span>與規格不符之處（不影響使用）</span>
                          </div>
                          <ul className={styles.specContent}>
                            {skill.warnings.map((w) => <li key={w}>{w}</li>)}
                          </ul>
                        </div>
                      )}
                      <div className={styles.toolActionsFooter}>
                        <div className={styles.toolActionGroup}>
                          <Button
                            variant="secondary"
                            onClick={() => setDialog({ type: 'skillDetail', skill })}
                            startIcon={<Icon name="description" size={16} />}
                          >
                            檢視內容
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => setDialog({ type: 'skillUpload', skill })}
                            startIcon={<Icon name="upload" size={16} />}
                          >
                            上傳新版本
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => setDialog({ type: 'skillAccess', skill })}
                            startIcon={<Icon name="people" size={16} />}
                          >
                            使用者範圍
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => handleTestExample(`/${skill.name} `)}
                            disabled={!isEnabled || !skill.files_present}
                            startIcon={<Icon name="chat" size={16} />}
                          >
                            在對話中使用
                          </Button>
                        </div>
                        <Button
                          variant="danger"
                          onClick={() => setPendingDelete({ type: 'skill', item: skill })}
                          startIcon={<Icon name="delete" size={16} />}
                        >
                          刪除技能
                        </Button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}
      {/* 2. 內部工具與自訂 API 工具列表區塊 */}
      {showTools && !nothingMatches && (
        <div className={styles.toolsList}>
          {filteredTools.length === 0 ? (
            query ? null : activeCategory === 'custom_api' ? (
              <div className={styles.emptyNotice}>
                <p>尚未新增自訂 API 工具。可以匯入 OpenAPI 規格一次建立多個工具，或手動新增單一工具。</p>
                <div className={styles.emptyActions}>
                  <Button variant="primary" size="sm" onClick={() => setDialog({ type: 'import' })} startIcon={<Icon name="upload" size={16} />}>
                    匯入 OpenAPI 規格
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => setDialog({ type: 'toolForm', tool: null })} startIcon={<Icon name="add" size={16} />}>
                    手動新增 API 工具
                  </Button>
                </div>
              </div>
            ) : (
              <div className={styles.emptyNotice}>
                <p>這個分類目前沒有工具</p>
              </div>
            )
          ) : (
            filteredTools.map((tool) => {
              const title = tool.display_name || tool.displayName;
              const isEnabled = tool.is_enabled !== false;
              const toolKey = tool.isCustom ? `custom_${tool.id}` : tool.name;
              const parametersList = tool.isCustom
                ? Object.entries(tool.parameters_schema?.properties || {}).map(([pName, pObj]) => ({
                  name: pName,
                  type: pObj.type || 'string',
                  required: tool.parameters_schema?.required?.includes(pName),
                  desc: pObj.description || ''
                }))
                : tool.parameters || [];
              return (
                <article key={toolKey} className={styles.toolOuterShell} aria-labelledby={`tool-${toolKey}`}>
                  <div className={styles.toolInnerCore}>
                    {/* 工具頭部資訊 */}
                    <div className={styles.toolHeader}>
                      <div className={styles.toolIdentity}>
                        <div className={styles.toolIconBox}>
                          <Icon name={tool.icon || 'code'} size={22} />
                        </div>
                        <div className={styles.toolTitleWrap}>
                          <h3 className={styles.toolTitle} id={`tool-${toolKey}`}>
                            {tool.isCustom && tool.method && (
                              <span className={`${styles.methodBadge} ${getMethodClass(tool.method)}`}>
                                {tool.method}
                              </span>
                            )}
                            <span>{title}</span>
                          </h3>
                          <div className={styles.toolIdentifier}>{tool.name}</div>
                        </div>
                      </div>
                      <div className={styles.toolStatusWrap}>
                        <span className={styles.categoryTag}>{tool.categoryName || '工具'}</span>
                        {tool.spec_version && (
                          <span className={styles.versionTag}>{tool.spec_version}</span>
                        )}
                        {tool.isCustom ? (
                          <div className={styles.switchGroup}>
                            <span className={`${styles.statusPill} ${isEnabled ? styles.statusActive : styles.statusDisabled}`}>
                              <span className={styles.statusDot} />
                              <span>{isEnabled ? '已啟用' : '已停用'}</span>
                            </span>
                            <Switch
                              checked={isEnabled}
                              onChange={() => handleToggleCustomTool(tool.id)}
                              aria-label={`啟用工具「${title}」`}
                            />
                          </div>
                        ) : (
                          <span className={`${styles.statusPill} ${styles.statusActive}`}>
                            <span className={styles.statusDot} />
                            <span>內建線上</span>
                          </span>
                        )}
                      </div>
                    </div>
                    {/* 功能簡介 */}
                    <p className={styles.toolDescription}>{tool.summary}</p>
                    {/* URL 與路徑 (自訂工具) */}
                    {tool.isCustom && tool.url && (
                      <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                        <div className={styles.specLabel}>
                          <Icon name="link" size={14} color="var(--color-primary)" />
                          <span>目標 API 請求網址 (Endpoint URL)</span>
                        </div>
                        <div className={`${styles.specContent} ${styles.monoText}`}>
                          {tool.url}
                        </div>
                      </div>
                    )}
                    {tool.isCustom && tool.credentials_unreadable && (
                      <div className={`${styles.specBlock} ${styles.specBlockSpaced} ${styles.specBlockError}`}>
                        <div className={styles.specLabel}>
                          <Icon name="warning" size={14} />
                          <span>憑證需要重新輸入</span>
                        </div>
                        <div className={styles.specContent}>{CREDENTIALS_UNREADABLE_NOTICE}</div>
                      </div>
                    )}
                    {/* 核心規格與時機 */}
                    <div className={styles.specsGrid}>
                      <div className={styles.specBlock}>
                        <div className={styles.specLabel}>
                          <Icon name="timeline" size={14} color="var(--color-primary)" />
                          <span>觸發調用時機</span>
                        </div>
                        <div className={styles.specContent}>{tool.triggerTiming}</div>
                      </div>
                      <div className={styles.specBlock}>
                        <div className={styles.specLabel}>
                          <Icon name="tune" size={14} color="var(--color-primary)" />
                          <span>調度機制與特性</span>
                        </div>
                        <div className={styles.specContent}>
                          <div>模式：{tool.executionMode}</div>
                          <div>優先級：{tool.priority}</div>
                        </div>
                      </div>
                    </div>
                    {/* 參數規格說明 */}
                    {parametersList.length > 0 && (
                      <div className={`${styles.specBlock} ${styles.specBlockSpaced}`}>
                        <div className={styles.specLabel}>
                          <Icon name="code" size={14} color="var(--color-primary)" />
                          <span>支援參數規格 (Parameters Schema)</span>
                        </div>
                        <div className={styles.paramsTableWrap}>
                          <table className={styles.paramsTable}>
                            <thead>
                              <tr>
                                <th scope="col" className={styles.paramsColName}>參數名稱</th>
                                <th scope="col" className={styles.paramsColType}>資料型態</th>
                                <th scope="col">說明</th>
                              </tr>
                            </thead>
                            <tbody>
                              {parametersList.map((param) => (
                                <tr key={param.name}>
                                  <td>
                                    <span className={styles.paramName}>{param.name}</span>
                                    {param.required && (
                                      <span className={styles.paramRequired} aria-label="必填">*</span>
                                    )}
                                  </td>
                                  <td>
                                    <span className={styles.paramType}>{param.type}</span>
                                  </td>
                                  <td>{param.desc || '無特定說明'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {/* 自訂工具專屬操作按鈕 */}
                    {tool.isCustom && (
                      <div className={styles.toolActionsFooter}>
                        <div className={styles.toolActionGroup}>
                          <Button
                            variant="secondary"
                            onClick={() => setDialog({ type: 'toolTest', tool })}
                            startIcon={<Icon name="speed" size={16} />}
                          >
                            即時線上測試
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => setDialog({ type: 'toolForm', tool })}
                            startIcon={<Icon name="edit" size={16} />}
                          >
                            編輯配置
                          </Button>
                        </div>
                        <Button
                          variant="danger"
                          onClick={() => setPendingDelete({ type: 'tool', item: tool })}
                          startIcon={<Icon name="delete" size={16} />}
                        >
                          刪除工具
                        </Button>
                      </div>
                    )}
                    {/* 推薦提問測試 (內建工具) */}
                    {!tool.isCustom && tool.examples && (
                      <div className={styles.examplesSection}>
                        <div className={styles.examplesTitle}>
                          <Icon name="lightbulb" size={14} color="var(--color-warning)" />
                          <span>測試提問範例（點擊可直接帶入聊天提問）</span>
                        </div>
                        <div className={styles.examplePillsWrap}>
                          {tool.examples.map((ex, idx) => (
                            <button
                              key={idx}
                              type="button"
                              className={styles.examplePill}
                              onClick={() => handleTestExample(ex)}
                            >
                              <Icon name="send" size={12} color="var(--color-primary)" />
                              <span>{ex}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </article>
              );
            })
          )}
        </div>
      )}
      {dialog?.type === 'mcpForm' && (
        <McpServerFormDialog server={dialog.server} presets={mcpPresets} onClose={closeDialog} onSaved={handleDialogSaved} />
      )}
      {dialog?.type === 'mcpTest' && (
        <McpToolTestDialog server={dialog.server} tool={dialog.tool} onClose={closeDialog} />
      )}
      {dialog?.type === 'import' && <OpenApiImportDialog onClose={closeDialog} onImported={handleDialogSaved} />}
      {dialog?.type === 'toolForm' && (
        <ApiToolFormDialog tool={dialog.tool} onClose={closeDialog} onSaved={handleDialogSaved} />
      )}
      {dialog?.type === 'toolTest' && <ApiToolTestDialog tool={dialog.tool} onClose={closeDialog} />}
      {dialog?.type === 'skillUpload' && (
        <SkillUploadDialog skill={dialog.skill} onClose={closeDialog} onSaved={handleDialogSaved} />
      )}
      {dialog?.type === 'skillDetail' && <SkillDetailDialog skill={dialog.skill} onClose={closeDialog} />}
      {dialog?.type === 'skillAccess' && (
        <SkillAccessDialog skill={dialog.skill} onClose={closeDialog} onSaved={handleDialogSaved} />
      )}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={DELETE_TITLES[pendingDelete?.type]}
        description={pendingDelete?.type === 'skill'
          ? `「${pendingDelete.item.name}」刪除後會一併移除技能檔案，AI 就無法再使用這個技能，此操作無法復原。`
          : `「${pendingDelete?.item.display_name}」刪除後，AI 就無法再使用它提供的工具，此操作無法復原。`}
        confirmLabel="刪除"
        destructive
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
      {/* 通知提示 */}
      <Snackbar
        key={snackbar.key}
        open={snackbar.open}
        autoHideDuration={snackbar.severity === 'error' ? 6000 : 3000}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
      >
        <Alert
          severity={snackbar.severity}
          onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </div>
  );
}
