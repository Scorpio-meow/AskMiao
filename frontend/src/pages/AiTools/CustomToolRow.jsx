import { Button, Icon, Switch } from '../../components/ui';
import {
  CatalogRow,
  DangerAction,
  DetailBlock,
  DetailList,
  MetaText,
  MethodBadge,
  ParamsTable,
  RowNotice,
  Tag,
} from './CatalogParts';
import { toolParameters } from './catalog';
import { CREDENTIALS_UNREADABLE_NOTICE } from './shared';
export default function CustomToolRow({ tool, expanded, onToggleDetails, onToggle, onTest, onEdit, onDelete }) {
  const title = tool.display_name;
  const isEnabled = tool.is_enabled !== false;
  const parameters = toolParameters(tool);
  return (
    <CatalogRow
      titleId={`tool-custom_${tool.id}`}
      inactive={!isEnabled}
      badge={tool.method && <MethodBadge method={tool.method}>{tool.method}</MethodBadge>}
      title={title}
      chips={(
        <>
          {tool.spec_version && <Tag tone="primary">{tool.spec_version}</Tag>}
          {tool.requires_approval && <Tag>呼叫前需確認</Tag>}
        </>
      )}
      meta={(
        <>
          <MetaText mono>{tool.name}</MetaText>
          {tool.url && <MetaText mono truncate>{tool.url}</MetaText>}
        </>
      )}
      description={tool.summary}
      notices={tool.credentials_unreadable && (
        <RowNotice tone="error" title="憑證需要重新輸入">{CREDENTIALS_UNREADABLE_NOTICE}</RowNotice>
      )}
      status={(
        <Switch
          checked={isEnabled}
          onChange={() => onToggle(tool.id)}
          aria-label={`啟用工具「${title}」`}
          label={isEnabled ? '已啟用' : '已停用'}
        />
      )}
      actions={(
        <>
          <Button variant="secondary" size="sm" onClick={onTest} startIcon={<Icon name="speed" size={16} />}>
            即時線上測試<span className="sr-only">「{title}」</span>
          </Button>
          <Button variant="secondary" size="sm" onClick={onEdit} startIcon={<Icon name="edit" size={16} />}>
            編輯設定<span className="sr-only">「{title}」</span>
          </Button>
        </>
      )}
      dangerAction={<DangerAction label="刪除工具" itemName={title} onClick={onDelete} />}
      detailsLabel="詳細資訊"
      expanded={expanded}
      onToggleDetails={onToggleDetails}
      details={(
        <>
          <DetailList
            items={[
              ...(tool.url ? [{ label: '請求網址', value: tool.url, mono: true }] : []),
              { label: '觸發呼叫時機', value: tool.triggerTiming },
              { label: '調度模式', value: tool.executionMode },
              { label: '優先級', value: tool.priority },
            ]}
          />
          {parameters.length > 0 && (
            <DetailBlock title="支援參數">
              <ParamsTable parameters={parameters} />
            </DetailBlock>
          )}
        </>
      )}
    />
  );
}