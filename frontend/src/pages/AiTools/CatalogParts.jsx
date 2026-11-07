import { useId } from 'react';
import { Button, Collapse, Icon } from '../../components/ui';
import { getMethodClass } from './shared';
import styles from './AiTools.module.css';
export function CatalogSection({ title, summary, description, actions, busy, children }) {
  const headingId = useId();
  return (
    <section className={styles.section} aria-labelledby={headingId} aria-busy={busy || undefined}>
      <header className={styles.sectionHeader}>
        <div className={styles.sectionHeading}>
          <div className={styles.sectionTitleLine}>
            <h2 className={styles.sectionTitle} id={headingId}>{title}</h2>
            {summary && <span className={styles.sectionSummary}>{summary}</span>}
          </div>
          {description && <p className={styles.sectionDescription}>{description}</p>}
        </div>
        {actions && <div className={styles.sectionActions}>{actions}</div>}
      </header>
      {children}
    </section>
  );
}
export function SectionMessage({ tone, children, actions }) {
  return (
    <div className={`${styles.sectionMessage} ${tone === 'error' ? styles.sectionMessageError : ''}`}>
      <p className={styles.sectionMessageText}>
        {tone === 'error' && <Icon name="error" size={16} className={styles.sectionMessageIcon} />}
        <span>{children}</span>
      </p>
      {actions && <div className={styles.sectionMessageActions}>{actions}</div>}
    </div>
  );
}
export function RowSkeleton({ rows }) {
  return (
    <ul className={styles.rowList} aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <li key={index} className={styles.row}>
          <span className={`${styles.skeleton} ${styles.skeletonTitle}`} />
          <span className={`${styles.skeleton} ${styles.skeletonMeta}`} />
          <span className={`${styles.skeleton} ${styles.skeletonText}`} />
        </li>
      ))}
    </ul>
  );
}
export function RowList({ grid, children }) {
  return <ul className={`${styles.rowList} ${grid ? styles.rowGrid : ''}`} role="list">{children}</ul>;
}
export function CatalogRow({
  titleId,
  title,
  badge,
  chips,
  meta,
  description,
  notices,
  status,
  actions,
  dangerAction,
  details,
  detailsLabel,
  expanded,
  onToggleDetails,
  inactive,
}) {
  const detailsId = useId();
  return (
    <li className={`${styles.row} ${inactive ? styles.rowInactive : ''}`}>
      <article aria-labelledby={titleId}>
        <div className={styles.rowHead}>
          <div className={styles.rowIdentity}>
            <div className={styles.rowTitleLine}>
              {badge}
              <h3 className={styles.rowTitle} id={titleId}>{title}</h3>
              {chips}
            </div>
            {meta && <div className={styles.rowMeta}>{meta}</div>}
          </div>
          {status && <div className={styles.rowStatus}>{status}</div>}
        </div>
        {description && <p className={styles.rowDescription}>{description}</p>}
        {notices}
        <div className={styles.rowActions}>
          {details && (
            <Button
              variant="text"
              size="sm"
              onClick={onToggleDetails}
              aria-expanded={expanded}
              aria-controls={detailsId}
              endIcon={<Icon name={expanded ? 'expand-less' : 'expand-more'} size={16} />}
            >
              {detailsLabel}<span className="sr-only">：{title}</span>
            </Button>
          )}
          {actions}
          {dangerAction && <span className={styles.rowActionsEnd}>{dangerAction}</span>}
        </div>
        {details && (
          <Collapse in={expanded} id={detailsId}>
            <div className={styles.rowDetails}>{details}</div>
          </Collapse>
        )}
      </article>
    </li>
  );
}
export function DangerAction({ label, itemName, onClick }) {
  return (
    <Button
      variant="text"
      size="sm"
      className={styles.dangerAction}
      onClick={onClick}
      startIcon={<Icon name="delete" size={16} />}
    >
      {label}<span className="sr-only">「{itemName}」</span>
    </Button>
  );
}
export function RowNotice({ tone, title, children }) {
  return (
    <div className={`${styles.rowNotice} ${tone === 'warning' ? styles.rowNoticeWarning : styles.rowNoticeError}`}>
      <Icon name="warning" size={16} className={styles.rowNoticeIcon} />
      <div className={styles.rowNoticeBody}>
        <strong className={styles.rowNoticeTitle}>{title}</strong>
        <div className={styles.rowNoticeText}>{children}</div>
      </div>
    </div>
  );
}
export function StatusChip({ tone, children }) {
  const toneClass = tone === 'success' ? styles.statusSuccess : tone === 'error' ? styles.statusError : styles.statusNeutral;
  return (
    <span className={`${styles.statusChip} ${toneClass}`}>
      <span className={styles.statusDot} aria-hidden="true" />
      {children}
    </span>
  );
}
export function Tag({ tone, children }) {
  const toneClass = tone === 'primary' ? styles.tagPrimary : tone === 'warning' ? styles.tagWarning : '';
  return <span className={`${styles.tag} ${toneClass}`}>{children}</span>;
}
export function MethodBadge({ method, children }) {
  return <span className={`${styles.methodBadge} ${getMethodClass(method)}`}>{children}</span>;
}
export function MetaText({ mono, truncate, children }) {
  return (
    <span
      className={`${styles.metaText} ${mono ? styles.mono : ''} ${truncate ? styles.metaTruncate : ''}`}
      title={truncate && typeof children === 'string' ? children : undefined}
    >
      {children}
    </span>
  );
}
export function DetailList({ items }) {
  return (
    <dl className={styles.detailList}>
      {items.map((item) => (
        <div key={item.label} className={styles.detailItem}>
          <dt className={styles.detailLabel}>{item.label}</dt>
          <dd className={`${styles.detailValue} ${item.mono ? styles.mono : ''}`}>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
export function DetailBlock({ title, aside, children }) {
  return (
    <div className={styles.detailBlock}>
      <div className={styles.detailBlockHeader}>
        <h4 className={styles.detailBlockTitle}>{title}</h4>
        {aside}
      </div>
      {children}
    </div>
  );
}
export function ParamsTable({ parameters }) {
  return (
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
          {parameters.map((param) => (
            <tr key={param.name}>
              <td>
                <span className={styles.paramName}>{param.name}</span>
                {param.required && <span className={styles.paramRequired} aria-label="必填">*</span>}
              </td>
              <td><span className={styles.paramType}>{param.type}</span></td>
              <td>{param.desc || '無特定說明'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}