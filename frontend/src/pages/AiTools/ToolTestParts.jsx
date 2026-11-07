import { Field } from './FormParts';
import styles from './AiTools.module.css';
export function TestArgsFields({ idPrefix, schema, args, onChange, emptyText }) {
  const properties = Object.entries(schema?.properties || {});
  return (
    <fieldset className={styles.formSection}>
      <legend className={styles.formSectionTitle}>測試參數</legend>
      <div className={styles.formSectionBody}>
        {properties.length === 0 ? (
          <p className={styles.mutedNote}>{emptyText}</p>
        ) : (
          properties.map(([name, property]) => {
            const inputId = `${idPrefix}-${name}`;
            const isRequired = schema?.required?.includes(name);
            return (
              <Field key={name} id={inputId} label={<span className={styles.mono}>{name}</span>} required={isRequired} hint={property.description || property.type}>
                <input
                  id={inputId}
                  type="text"
                  className={styles.input}
                  value={args[name] || ''}
                  onChange={(e) => onChange({ ...args, [name]: e.target.value })}
                  required={isRequired}
                  autoComplete="off"
                  aria-describedby={property.description || property.type ? `${inputId}-hint` : undefined}
                />
              </Field>
            );
          })
        )}
      </div>
    </fieldset>
  );
}
export function TestResult({ title, success, facts, body }) {
  return (
    <div className={styles.testResult}>
      <div className={styles.testResultHeader}>
        <h3 className={styles.testResultTitle}>{title}</h3>
        <span className={`${styles.testResultStatus} ${success ? styles.testResultSuccess : styles.testResultError}`}>
          {[success ? '成功' : '失敗', ...facts].join('｜')}
        </span>
      </div>
      <pre className={styles.codeViewer}>{body}</pre>
    </div>
  );
}