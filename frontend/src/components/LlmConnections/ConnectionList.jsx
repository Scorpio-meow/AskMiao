import { Button, Chip } from '../ui';
import { providerLabel } from '../../hooks/useLlmProviders';
import styles from './LlmConnections.module.css';
export default function ConnectionList({ connections, providers, label, describeAccess, onTest, onEdit, onDelete }) {
  return (
    <ul className={styles.list} role="list" aria-label={label}>
      {connections.map((connection) => (
        <li key={connection.id} className={styles.item}>
          <div className={styles.itemHeader}>
            <span className={styles.itemName}>{connection.name}</span>
            <Chip label={providerLabel(providers, connection.provider)} size="sm" />
          </div>
          {connection.api_base && <span className={styles.itemMeta}>{connection.api_base}</span>}
          {describeAccess && <span className={styles.itemMeta}>{describeAccess(connection)}</span>}
          <div className={styles.models} aria-label="模型">
            {connection.models.map((model) => (
              <Chip key={model} label={model} size="sm" color="info" />
            ))}
          </div>
          {(onTest || onEdit || onDelete) && (
            <div className={styles.actions}>
              {onTest && (
                <Button size="sm" variant="secondary" onClick={() => onTest(connection)}>
                  測試<span className="sr-only">連線 {connection.name}</span>
                </Button>
              )}
              {onEdit && (
                <Button size="sm" variant="secondary" onClick={() => onEdit(connection)}>
                  編輯<span className="sr-only">連線 {connection.name}</span>
                </Button>
              )}
              {onDelete && (
                <Button size="sm" variant="danger" onClick={() => onDelete(connection)}>
                  刪除<span className="sr-only">連線 {connection.name}</span>
                </Button>
              )}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
