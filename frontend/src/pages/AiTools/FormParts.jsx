import styles from './AiTools.module.css';
export function Field({ id, label, required, hint, children }) {
  return (
    <div className={styles.field}>
      <label className={styles.fieldLabel} htmlFor={id}>
        {label}
        {required && <span className={styles.fieldRequired} aria-hidden="true">*</span>}
      </label>
      {children}
      {hint && <p id={`${id}-hint`} className={styles.fieldHint}>{hint}</p>}
    </div>
  );
}
export function FormSection({ title, description, children }) {
  return (
    <fieldset className={styles.formSection}>
      <legend className={styles.formSectionTitle}>{title}</legend>
      {description && <p className={styles.formSectionDescription}>{description}</p>}
      <div className={styles.formSectionBody}>{children}</div>
    </fieldset>
  );
}
export function FormRow({ narrowFirst, children }) {
  return <div className={`${styles.formRow} ${narrowFirst ? styles.formRowNarrowFirst : ''}`}>{children}</div>;
}
export function CheckOption({ type, name, checked, onChange, label, hint }) {
  return (
    <label className={styles.checkOption}>
      <input type={type} name={name} checked={checked} onChange={onChange} />
      <span className={styles.checkText}>
        <span className={styles.checkLabel}>{label}</span>
        {hint && <span className={styles.checkHint}>{hint}</span>}
      </span>
    </label>
  );
}
