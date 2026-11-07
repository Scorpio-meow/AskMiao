import { useCallback, useEffect, useId, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { chatService, apiToolService, mcpService, skillService } from '../../services/api';
import { describeRequestError } from '../../utils/secureLogger';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { Alert, Button, ConfirmDialog, Icon, Menu, MenuItem, Snackbar } from '../../components/ui';
import ApiToolFormDialog from './ApiToolFormDialog';
import ApiToolTestDialog from './ApiToolTestDialog';
import BuiltinToolRow from './BuiltinToolRow';
import { DEFAULT_TOOLS_METADATA } from './builtinTools';
import {
  CATEGORY_FILTERS,
  DELETE_TITLES,
  attentionItems,
  categoryCounts,
  deleteDescription,
  filterCatalog,
  normalizeQuery,
  sectionSummaries,
  withBackendDescriptions,
} from './catalog';
import { CatalogSection, RowList, RowSkeleton, SectionMessage } from './CatalogParts';
import CustomToolRow from './CustomToolRow';
import McpServerFormDialog from './McpServerFormDialog';
import McpServerRow from './McpServerRow';
import McpToolTestDialog from './McpToolTestDialog';
import OpenApiImportDialog from './OpenApiImportDialog';
import SkillAccessDialog from './SkillAccessDialog';
import SkillDetailDialog from './SkillDetailDialog';
import SkillRow from './SkillRow';
import SkillUploadDialog from './SkillUploadDialog';
import { getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
const ADD_ACTIONS = [
  { key: 'import', label: '匯入 API 規格', icon: 'upload', dialog: { type: 'import' } },
  { key: 'toolForm', label: '手動新增 API 工具', icon: 'add', dialog: { type: 'toolForm', tool: null } },
  { key: 'mcpForm', label: '新增 MCP 伺服器', icon: 'build', dialog: { type: 'mcpForm', server: null } },
  { key: 'skillUpload', label: '上傳 Agent Skill', icon: 'sparkles', dialog: { type: 'skillUpload', skill: null } },
];
export default function AiTools() {
  const navigate = useNavigate();
  const addMenuId = useId();
  const [defaultTools, setDefaultTools] = useState(DEFAULT_TOOLS_METADATA);
  const [customTools, setCustomTools] = useState([]);
  const [mcpServers, setMcpServers] = useState([]);
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadState, setLoadState] = useState({ loaded: false, failed: {} });
  const [activeCategory, setActiveCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [expanded, setExpanded] = useState(() => new Set());
  const [addMenuAnchor, setAddMenuAnchor] = useState(null);
  useDocumentTitle('AI 工具');
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info', key: 0 });
  const [pendingDelete, setPendingDelete] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [mcpPresets, setMcpPresets] = useState([]);
  const [discoveringId, setDiscoveringId] = useState(null);
  const showSnackbar = (message, severity) => {
    setSnackbar((prev) => ({ open: true, message, severity, key: prev.key + 1 }));
  };
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
        setDefaultTools(withBackendDescriptions(DEFAULT_TOOLS_METADATA, resDefault.value.tools));
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
      setLoadState({
        loaded: true,
        failed: {
          custom: resCustom.status === 'rejected',
          mcp: resMcp.status === 'rejected',
          skills: resSkills.status === 'rejected',
        },
      });
    } catch (err) {
      console.warn('載入工具清單失敗:', describeRequestError(err));
      setLoadState((prev) => ({ ...prev, loaded: true }));
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
  const toggleDetails = (key) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
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
      fetchAllTools();
    } finally {
      setDiscoveringId(null);
    }
  };
  const inventory = { builtinTools: defaultTools, customTools, servers: mcpServers, skills };
  const query = normalizeQuery(searchQuery);
  const catalog = filterCatalog({ ...inventory, category: activeCategory, query });
  const counts = categoryCounts(inventory);
  const summaries = sectionSummaries(inventory);
  const attention = attentionItems(inventory);
  const summaryFor = (summary, failed, items) =>
    (loadState.loaded && !(failed && items.length === 0) ? summary : null);
  const retryAction = (
    <Button variant="secondary" size="sm" onClick={fetchAllTools} loading={loading} startIcon={<Icon name="refresh" size={16} />}>
      重試
    </Button>
  );
  const renderSectionBody = ({ items, failed, failedText, staleText, emptyText, renderRow }) => {
    if (!loadState.loaded) return <RowSkeleton rows={2} />;
    return (
      <>
        {failed && (
          <SectionMessage tone="error" actions={retryAction}>
            {items.length > 0 ? staleText : failedText}
          </SectionMessage>
        )}
        {items.length > 0 && <RowList>{items.map(renderRow)}</RowList>}
        {items.length === 0 && !failed && <SectionMessage>{emptyText}</SectionMessage>}
      </>
    );
  };
  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>AI 工具</h1>
          <p className={styles.pageSubtitle}>
            AI 在對話中會依問題自主呼叫這些工具：內建的知識庫檢索與聯網閱讀、自訂 API、MCP 伺服器與 Agent Skills。
          </p>
        </div>
        <div className={styles.pageActions}>
          <Button variant="secondary" onClick={() => navigate('/chat')} startIcon={<Icon name="chat" size={16} />}>
            <span className={styles.compactLabel}>前往對話體驗工具</span>
          </Button>
          <Button variant="secondary" onClick={fetchAllTools} loading={loading} startIcon={<Icon name="refresh" size={16} />}>
            <span className={styles.compactLabel}>重新整理狀態</span>
          </Button>
          <Button
            className={styles.primaryAction}
            variant="primary"
            onClick={(e) => setAddMenuAnchor(e.currentTarget)}
            aria-haspopup="menu"
            aria-expanded={Boolean(addMenuAnchor)}
            aria-controls={addMenuAnchor ? addMenuId : undefined}
            startIcon={<Icon name="add" size={16} />}
            endIcon={<Icon name="expand-more" size={16} />}
          >
            新增工具
          </Button>
        </div>
      </header>
      <Menu
        id={addMenuId}
        aria-label="新增工具"
        anchorEl={addMenuAnchor}
        open={Boolean(addMenuAnchor)}
        onClose={() => setAddMenuAnchor(null)}
        placement="bottom-end"
      >
        {ADD_ACTIONS.map((action) => (
          <MenuItem
            key={action.key}
            icon={<Icon name={action.icon} size={16} />}
            onClick={() => {
              setAddMenuAnchor(null);
              setDialog(action.dialog);
            }}
          >
            {action.label}
          </MenuItem>
        ))}
      </Menu>
      {attention.length > 0 && (
        <Alert severity="warning" role="status" className={styles.attention}>
          <strong className={styles.attentionTitle}>{attention.length} 項需要處理</strong>
          <ul className={styles.attentionList}>
            {attention.map((item) => <li key={item.key}>{item.text}</li>)}
          </ul>
        </Alert>
      )}
      <div className={styles.toolbar}>
        <div className={styles.filterTabs} role="group" aria-label="工具分類">
          {CATEGORY_FILTERS.map((filter) => {
            const isActive = activeCategory === filter.value;
            return (
              <button
                key={filter.value}
                type="button"
                className={`${styles.filterTab} ${isActive ? styles.filterTabActive : ''}`}
                onClick={() => setActiveCategory(filter.value)}
                aria-pressed={isActive}
              >
                <span>{filter.label}</span>
                <span className={styles.filterCount}>{counts[filter.value]}</span>
              </button>
            );
          })}
        </div>
        <search className={styles.searchBox}>
          <Icon name="search" size={16} className={styles.searchIcon} />
          <input
            type="search"
            className={styles.searchInput}
            placeholder="搜尋名稱、網址、MCP 伺服器或技能"
            aria-label="搜尋工具"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </search>
      </div>
      <div className={styles.sections}>
        {catalog.nothingMatches && (
          <div className={styles.noResults} role="status">
            <p>查無符合「{searchQuery.trim()}」的工具、MCP 伺服器或技能</p>
            <Button variant="secondary" size="sm" onClick={() => setSearchQuery('')}>
              清除搜尋
            </Button>
          </div>
        )}
        {catalog.visible.custom && (
          <CatalogSection
            title="自訂 API 工具"
            summary={summaryFor(summaries.custom, loadState.failed.custom, customTools)}
            description="匯入 Swagger 2.0、OpenAPI 3.0～3.2 或 Arazzo 1.0～1.1 工作流程（可先套用 Overlay），或手動建立單一端點。"
            busy={!loadState.loaded}
            actions={(
              <>
                <Button variant="secondary" size="sm" onClick={() => setDialog({ type: 'import' })} startIcon={<Icon name="upload" size={16} />}>
                  匯入 API 規格
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setDialog({ type: 'toolForm', tool: null })} startIcon={<Icon name="add" size={16} />}>
                  手動新增 API 工具
                </Button>
              </>
            )}
          >
            {renderSectionBody({
              items: catalog.custom,
              failed: loadState.failed.custom,
              failedText: '無法載入自訂 API 工具。',
              staleText: '無法更新自訂 API 工具，下方是上次載入的資料。',
              emptyText: '尚未新增自訂 API 工具。可以匯入 OpenAPI 規格或 Arazzo 工作流程一次建立多個工具，或手動新增單一工具。',
              renderRow: (tool) => (
                <CustomToolRow
                  key={tool.id}
                  tool={tool}
                  expanded={expanded.has(`custom-${tool.id}`)}
                  onToggleDetails={() => toggleDetails(`custom-${tool.id}`)}
                  onToggle={handleToggleCustomTool}
                  onTest={() => setDialog({ type: 'toolTest', tool })}
                  onEdit={() => setDialog({ type: 'toolForm', tool })}
                  onDelete={() => setPendingDelete({ type: 'tool', item: tool })}
                />
              ),
            })}
          </CatalogSection>
        )}
        {catalog.visible.mcp && (
          <CatalogSection
            title="MCP 伺服器"
            summary={summaryFor(summaries.mcp, loadState.failed.mcp, mcpServers)}
            description="透過 Model Context Protocol 連接外部工具伺服器，支援 Stdio、Streamable HTTP 與舊版 SSE。"
            busy={!loadState.loaded}
            actions={(
              <Button variant="secondary" size="sm" onClick={() => setDialog({ type: 'mcpForm', server: null })} startIcon={<Icon name="add" size={16} />}>
                新增 MCP 伺服器
              </Button>
            )}
          >
            {renderSectionBody({
              items: catalog.mcp,
              failed: loadState.failed.mcp,
              failedText: '無法載入 MCP 伺服器。',
              staleText: '無法更新 MCP 伺服器，下方是上次載入的資料。',
              emptyText: '尚未設定任何 MCP 伺服器，點擊「新增 MCP 伺服器」即可套用 Time、Filesystem 等預設範本或自訂指令。',
              renderRow: (server) => (
                <McpServerRow
                  key={server.id}
                  server={server}
                  expanded={expanded.has(`mcp-${server.id}`)}
                  discovering={discoveringId === server.id}
                  onToggleDetails={() => toggleDetails(`mcp-${server.id}`)}
                  onToggle={handleToggleMcpServer}
                  onDiscover={() => handleDiscoverMcpServer(server.id)}
                  onEdit={() => setDialog({ type: 'mcpForm', server })}
                  onStartOAuth={() => handleStartOAuth(server)}
                  onRevokeOAuth={() => handleRevokeOAuth(server)}
                  onTestTool={(tool) => setDialog({ type: 'mcpTest', server, tool })}
                  onDelete={() => setPendingDelete({ type: 'server', item: server })}
                />
              ),
            })}
          </CatalogSection>
        )}
        {catalog.visible.skills && (
          <CatalogSection
            title="Agent Skills"
            summary={summaryFor(summaries.skills, loadState.failed.skills, skills)}
            description="符合 Agent Skills 規格的技能；AI 會在任務符合技能描述時自動載入，也可以在對話中輸入「/技能名稱」指定使用。"
            busy={!loadState.loaded}
            actions={(
              <Button variant="secondary" size="sm" onClick={() => setDialog({ type: 'skillUpload', skill: null })} startIcon={<Icon name="upload" size={16} />}>
                上傳技能
              </Button>
            )}
          >
            {renderSectionBody({
              items: catalog.skills,
              failed: loadState.failed.skills,
              failedText: '無法載入技能。',
              staleText: '無法更新技能，下方是上次載入的資料。',
              emptyText: '尚未安裝任何技能。上傳符合 Agent Skills 規格的技能後，AI 會在任務符合技能描述時自動載入，使用者也可以在對話中輸入「/技能名稱」指定使用。',
              renderRow: (skill) => (
                <SkillRow
                  key={skill.id}
                  skill={skill}
                  expanded={expanded.has(`skill-${skill.id}`)}
                  onToggleDetails={() => toggleDetails(`skill-${skill.id}`)}
                  onToggle={handleToggleSkill}
                  onToggleScripts={() => handleSkillScripts(skill)}
                  onView={() => setDialog({ type: 'skillDetail', skill })}
                  onUpload={() => setDialog({ type: 'skillUpload', skill })}
                  onAccess={() => setDialog({ type: 'skillAccess', skill })}
                  onUseInChat={() => handleTestExample(`/${skill.name} `)}
                  onDelete={() => setPendingDelete({ type: 'skill', item: skill })}
                />
              ),
            })}
          </CatalogSection>
        )}
        {catalog.visible.builtin && (
          <CatalogSection
            title="內建工具"
            summary={summaries.builtin}
            description="知識庫混合檢索、結構化記錄統計、即時聯網搜尋與網頁全文閱讀，由系統提供。"
          >
            {catalog.builtin.length === 0 ? (
              <SectionMessage>這個分類目前沒有工具</SectionMessage>
            ) : (
              <RowList grid>
                {catalog.builtin.map((tool) => (
                  <BuiltinToolRow
                    key={tool.name}
                    tool={tool}
                    expanded={expanded.has(`builtin-${tool.name}`)}
                    onToggleDetails={() => toggleDetails(`builtin-${tool.name}`)}
                    onTryExample={handleTestExample}
                  />
                ))}
              </RowList>
            )}
          </CatalogSection>
        )}
      </div>
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
        description={deleteDescription(pendingDelete)}
        confirmLabel="刪除"
        destructive
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
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