import { useState } from 'react';
import { skillService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Icon } from '../../components/ui';
import { CheckOption, Field } from './FormParts';
import { getRequestErrorMessage } from './shared';
import styles from './AiTools.module.css';
export default function SkillUploadDialog({ skill, onClose, onSaved }) {
  const [file, setFile] = useState(null);
  const [replace, setReplace] = useState(Boolean(skill));
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const handleUpload = async (allowReplace) => {
    if (!file) {
      setError('請選擇技能的 .zip 壓縮檔或 SKILL.md');
      return;
    }
    try {
      setUploading(true);
      setError('');
      setConflict(false);
      const res = await skillService.uploadSkill(file, allowReplace);
      onSaved(res.message);
    } catch (err) {
      setConflict(err?.response?.status === 409);
      setError(getRequestErrorMessage(err, '上傳技能失敗'));
    } finally {
      setUploading(false);
    }
  };
  return (
    <Dialog open onClose={onClose} maxWidth="md">
      <DialogTitle onClose={onClose} subtitle="技能內的參考檔會提供給 AI 閱讀；腳本不會被執行">
        {skill ? `更新技能：${skill.name}` : '上傳 Agent Skill'}
      </DialogTitle>
      <DialogContent className={styles.dialogBody}>
        <Field
          id="skill-upload-file"
          label="技能檔案"
          hint="技能目錄的 .zip 壓縮檔（根目錄或唯一的頂層目錄內含 SKILL.md），或只有指示的單一 SKILL.md。"
        >
          <input
            id="skill-upload-file"
            type="file"
            accept=".zip,.skill,.md"
            className={styles.fileInput}
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              setError('');
              setConflict(false);
            }}
            aria-describedby="skill-upload-file-hint"
          />
        </Field>
        <CheckOption
          type="checkbox"
          checked={replace}
          onChange={(e) => setReplace(e.target.checked)}
          label="取代同名的既有技能"
          hint="技能名稱以 SKILL.md 的 name 欄位為準，取代時會換掉整個技能目錄"
        />
        {error && (
          <Alert severity="error">
            {error}
            {conflict && !replace && (
              <div className={styles.alertActions}>
                <Button variant="secondary" size="sm" onClick={() => handleUpload(true)} loading={uploading}>
                  取代既有技能
                </Button>
              </div>
            )}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button variant="secondary" onClick={onClose} disabled={uploading}>
          取消
        </Button>
        <Button
          variant="primary"
          onClick={() => handleUpload(replace)}
          loading={uploading}
          startIcon={<Icon name="upload" size={16} />}
        >
          上傳並安裝
        </Button>
      </DialogActions>
    </Dialog>
  );
}
