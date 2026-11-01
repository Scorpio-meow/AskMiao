import { useEffect, useState } from 'react';
import { skillService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Spinner } from '../../components/ui';
import styles from './AiTools.module.css';
import { getRequestErrorMessage } from './shared';
export default function SkillDetailDialog({ skill, onClose }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    skillService.getSkill(skill.id)
      .then((res) => {
        if (!cancelled) setDetail(res.skill);
      })
      .catch((err) => {
        if (!cancelled) setError(getRequestErrorMessage(err, '載入技能內容失敗'));
      });
    return () => {
      cancelled = true;
    };
  }, [skill.id]);
  return (
    <Dialog open onClose={onClose} maxWidth="lg">
      <DialogTitle onClose={onClose} subtitle={`/${skill.name}`}>技能內容：{skill.name}</DialogTitle>
      <DialogContent className={styles.dialogBody}>
        {error && <Alert severity="error">{error}</Alert>}
        {!detail && !error && (
          <div className={styles.loadingRow}><Spinner size="sm" /><span>正在載入技能內容…</span></div>
        )}
        {detail && (
          <>
            {detail.load_error && <Alert severity="error">{detail.load_error}</Alert>}
            <div className={styles.detailBlock}>
              <h3 className={styles.detailBlockTitle}>SKILL.md 指示</h3>
              <pre className={`${styles.codeViewer} ${styles.skillBody}`}>{detail.body || '（沒有內容）'}</pre>
            </div>
            <div className={styles.detailBlock}>
              <h3 className={styles.detailBlockTitle}>
                技能資源（{detail.resources.length}{detail.resources_truncated ? '+' : ''} 個檔案）
              </h3>
              {detail.resources.length === 0 ? (
                <p className={styles.mutedNote}>這個技能只有 SKILL.md</p>
              ) : (
                <ul className={styles.fileList} role="list">
                  {detail.resources.map((path) => (
                    <li key={path} className={styles.fileItem}>{path}</li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button variant="secondary" onClick={onClose}>
          關閉
        </Button>
      </DialogActions>
    </Dialog>
  );
}
