import { Button, Icon, Switch } from '../../components/ui';
import { CatalogRow, DangerAction, DetailBlock, MetaText, RowNotice, StatusChip, Tag } from './CatalogParts';
import { mcpToolHints } from './catalog';
import { CREDENTIALS_UNREADABLE_NOTICE } from './shared';
import styles from './AiTools.module.css';
const connectionStatus = (server) => {
  if (server.status === 'connected') return { tone: 'success', label: '已連線' };
  if (server.status === 'error') return { tone: 'error', label: '連線錯誤' };
  return { tone: 'neutral', label: '未連線' };
};
export default function McpServerRow({
  server,
  expanded,
  discovering,
  onToggleDetails,
  onToggle,
  onDiscover,
  onEdit,
  onStartOAuth,
  onRevokeOAuth,
  onTestTool,
  onDelete,
}) {
  const title = server.display_name;
  const tools = server.discovered_tools || [];
  const resources = server.discovered_resources || [];
  const prompts = server.discovered_prompts || [];
  const isStdio = server.transport_type === 'stdio';
  const connection = connectionStatus(server);
  return (
    <CatalogRow
      titleId={`mcp-server-${server.id}`}
      inactive={!server.is_enabled}
      badge={<span className={styles.transportBadge}>{server.transport_type}</span>}
      title={title}
      chips={(
        <>
          {server.oauth_authorized && <Tag tone="primary">OAuth 已授權</Tag>}
          {server.requires_approval && <Tag>呼叫前需確認</Tag>}
        </>
      )}
      meta={(
        <>
          <MetaText mono>{server.name}</MetaText>
          <MetaText mono truncate>
            {isStdio ? `${server.command || ''} ${(server.args || []).join(' ')}` : server.url}
          </MetaText>
          {server.protocol_version && <MetaText mono>MCP {server.protocol_version}</MetaText>}
        </>
      )}
      description={server.description || 'MCP 協定外部工具伺服器。'}
      notices={(
        <>
          {server.credentials_unreadable && (
            <RowNotice tone="error" title="憑證需要重新輸入">{CREDENTIALS_UNREADABLE_NOTICE}</RowNotice>
          )}
          {server.last_error && (
            <RowNotice tone="error" title="最近一次連線或探索的錯誤">{server.last_error}</RowNotice>
          )}
        </>
      )}
      status={(
        <>
          <StatusChip tone={connection.tone}>{connection.label}</StatusChip>
          <Switch
            checked={server.is_enabled}
            onChange={() => onToggle(server.id)}
            aria-label={`啟用 MCP 伺服器「${title}」`}
            label={server.is_enabled ? '已啟用' : '已停用'}
          />
        </>
      )}
      actions={(
        <>
          <Button
            variant="secondary"
            size="sm"
            onClick={onDiscover}
            loading={discovering}
            startIcon={<Icon name="refresh" size={16} />}
          >
            {discovering ? '正在連線探索...' : '重新探索工具'}<span className="sr-only">「{title}」</span>
          </Button>
          <Button variant="secondary" size="sm" onClick={onEdit} startIcon={<Icon name="edit" size={16} />}>
            編輯設定<span className="sr-only">「{title}」</span>
          </Button>
          {!isStdio && (
            <Button variant="secondary" size="sm" onClick={onStartOAuth} startIcon={<Icon name="lock" size={16} />}>
              {server.oauth_authorized ? '重新 OAuth 授權' : 'OAuth 授權'}<span className="sr-only">「{title}」</span>
            </Button>
          )}
          {server.oauth_authorized && (
            <Button variant="secondary" size="sm" onClick={onRevokeOAuth} startIcon={<Icon name="close" size={16} />}>
              清除授權<span className="sr-only">「{title}」</span>
            </Button>
          )}
        </>
      )}
      dangerAction={<DangerAction label="刪除伺服器" itemName={title} onClick={onDelete} />}
      detailsLabel={`提供的工具（${tools.length}）`}
      expanded={expanded}
      onToggleDetails={onToggleDetails}
      details={(
        <>
          <DetailBlock
            title={`MCP 工具（${tools.length} 項）`}
            aside={tools.length > 0 && <span className={styles.detailBlockHint}>標籤是伺服器自行宣告的工具性質，僅供參考</span>}
          >
            {tools.length === 0 ? (
              <p className={styles.detailEmpty}>尚未探索到工具，請按「重新探索工具」連線並取得工具清單。</p>
            ) : (
              <ul className={styles.entryList} role="list">
                {tools.map((tool) => (
                  <li key={tool.name} className={styles.entryItem}>
                    <div className={styles.entryText}>
                      <span className={styles.entryName}>
                        {tool.name}{tool.title && tool.title !== tool.name ? `（${tool.title}）` : ''}
                      </span>
                      <span className={styles.entryDescription}>{tool.description || '無詳細說明'}</span>
                      <span className={styles.entryTags}>
                        {mcpToolHints(tool).map((hint) => (
                          <Tag key={hint} tone={hint === '唯讀' ? undefined : 'warning'}>{hint}</Tag>
                        ))}
                      </span>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => onTestTool(tool)}
                      startIcon={<Icon name="speed" size={16} />}
                    >
                      線上測試<span className="sr-only"> {tool.name}</span>
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </DetailBlock>
          {(resources.length > 0 || prompts.length > 0) && (
            <DetailBlock title={`Resources（${resources.length} 項）與 Prompts（${prompts.length} 項）`}>
              <ul className={styles.entryList} role="list">
                {resources.map((resource) => (
                  <li key={`r-${resource.uri}`} className={styles.entryItem}>
                    <div className={styles.entryText}>
                      <span className={styles.entryName}>{resource.uri}</span>
                      <span className={styles.entryDescription}>
                        {resource.name}{resource.description ? `：${resource.description}` : ''}
                      </span>
                    </div>
                    <Tag>resource</Tag>
                  </li>
                ))}
                {prompts.map((prompt) => (
                  <li key={`p-${prompt.name}`} className={styles.entryItem}>
                    <div className={styles.entryText}>
                      <span className={styles.entryName}>{prompt.name}</span>
                      <span className={styles.entryDescription}>{prompt.description || '無詳細說明'}</span>
                    </div>
                    <Tag>prompt</Tag>
                  </li>
                ))}
              </ul>
            </DetailBlock>
          )}
        </>
      )}
    />
  );
}