import { Icon } from '../../components/ui';
import { CatalogRow, DetailBlock, DetailList, MetaText, ParamsTable, StatusChip, Tag } from './CatalogParts';
import { toolParameters } from './catalog';
import styles from './AiTools.module.css';
export default function BuiltinToolRow({ tool, expanded, onToggleDetails, onTryExample }) {
  const parameters = toolParameters(tool);
  return (
    <CatalogRow
      titleId={`tool-${tool.name}`}
      title={tool.displayName}
      chips={<Tag>{tool.categoryName}</Tag>}
      meta={<MetaText mono>{tool.name}</MetaText>}
      description={tool.summary}
      status={<StatusChip tone="success">內建線上</StatusChip>}
      detailsLabel="觸發時機、參數與範例"
      expanded={expanded}
      onToggleDetails={onToggleDetails}
      details={(
        <>
          <DetailList
            items={[
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
          {tool.examples && (
            <DetailBlock title="測試提問範例" aside={<span className={styles.detailBlockHint}>點擊即可帶入對話</span>}>
              <ul className={styles.exampleList} role="list">
                {tool.examples.map((example) => (
                  <li key={example}>
                    <button type="button" className={styles.exampleButton} onClick={() => onTryExample(example)}>
                      <Icon name="send" size={14} className={styles.exampleIcon} />
                      <span>{example}</span>
                    </button>
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