import { useRef, useState } from 'react';
import { skillService } from '../../services/api';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Icon } from '../../components/ui';
import { CheckOption, Field } from './FormParts';
import { getRequestErrorMessage } from './shared';
import { readFolderSelection } from './skillFolder';
import styles from './AiTools.module.css';
export default function SkillUploadDialog({ skill, onClose, onSaved }) {
  const [source, setSource] = useState('folder');
  const [file, setFile] = useState(null);
  const [folder, setFolder] = useState(null);
  const folderInputRef = useRef(null);
  const [replace, setReplace] = useState(Boolean(skill));
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const [skipped, setSkipped] = useState([]);
  const [savedMessage, setSavedMessage] = useState('');
  const resetFeedback = () => {
    setError('');
    setConflict(false);
    setSkipped([]);
  };
  const close = () => (savedMessage ? onSaved(savedMessage) : onClose());
  const chooseSource = (next) => {
    setSource(next);
    setFile(null);
    setFolder(null);
    resetFeedback();
  };
  const handleUpload = async (allowReplace) => {
    if (source === 'folder' ? !folder : !file) {
      setError(source === 'folder' ? '請選擇內含 SKILL.md 的技能資料夾' : '請選擇技能的 .zip 壓縮檔或 SKILL.md');
      return;
    }
    try {
      setUploading(true);
      resetFeedback();
      const res = source === 'folder'
        ? await skillService.uploadSkillFolder(folder.entries, allowReplace)
        : await skillService.uploadSkill(file, allowReplace);
      if (res.skipped?.length) {
        setSavedMessage(res.message);
        setSkipped(res.skipped);
        return;
      }
      onSaved(res.message);
    } catch (err) {
      setConflict(err?.response?.status === 409);
      setError(getRequestErrorMessage(err, '上傳技能失敗'));
    } finally {
      setUploading(false);
    }
  };
  return (
    <Dialog open onClose={close} maxWidth="md">
      <DialogTitle onClose={close} subtitle="技能內的參考檔會提供給 AI 閱讀；腳本不會被執行">
        {skill ? `更新技能：${skill.name}` : '上傳 Agent Skill'}
      </DialogTitle>
      <DialogContent className={styles.dialogBody}>
        <fieldset className={styles.formSection}>
          <legend className={styles.formSectionTitle}>上傳方式</legend>
          <div className={styles.optionGroup}>
            <CheckOption
              type="radio"
              name="skill-upload-source"
              checked={source === 'folder'}
              onChange={() => chooseSource('folder')}
              label="技能資料夾"
              hint="直接選擇技能目錄，不必先壓縮；也可以選內含多個技能的資料夾一次安裝"
            />
            <CheckOption
              type="radio"
              name="skill-upload-source"
              checked={source === 'file'}
              onChange={() => chooseSource('file')}
              label="壓縮檔或 SKILL.md"
              hint="技能目錄的 .zip 壓縮檔，或只有指示的單一 SKILL.md"
            />
          </div>
        </fieldset>
        {source === 'folder' ? (
          <Field
            key="folder"
            id="skill-upload-folder"
            label="技能資料夾"
            hint="每個含 SKILL.md 的資料夾各安裝成一個技能，例如選 ~/.agents/skills 會安裝其中所有技能；.git、__MACOSX 與 .DS_Store 不會上傳。"
          >
            <div className={`${styles.fileInput} ${styles.folderPicker}`}>
              <Button
                id="skill-upload-folder"
                variant="secondary"
                size="sm"
                onClick={() => folderInputRef.current.click()}
                startIcon={<Icon name="folder" size={16} />}
                aria-describedby="skill-upload-folder-hint skill-upload-folder-status"
              >
                選擇資料夾
              </Button>
              <span id="skill-upload-folder-status" className={styles.folderPickerStatus}>
                {folder ? `「${folder.name}」，${folder.entries.length} 個檔案` : '尚未選擇資料夾'}
              </span>
            </div>
            <input
              ref={folderInputRef}
              type="file"
              webkitdirectory=""
              hidden
              onChange={(e) => {
                const selection = readFolderSelection(e.target.files);
                setFolder(selection);
                resetFeedback();
                if (e.target.files.length > 0 && !selection) setError('資料夾中沒有可上傳的檔案');
                e.target.value = '';
              }}
            />
          </Field>
        ) : (
          <Field
            key="file"
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
                resetFeedback();
              }}
              aria-describedby="skill-upload-file-hint"
            />
          </Field>
        )}
        <CheckOption
          type="checkbox"
          checked={replace}
          onChange={(e) => setReplace(e.target.checked)}
          label="取代同名的既有技能"
          hint="技能名稱以 SKILL.md 的 name 欄位為準，取代時會換掉整個技能目錄"
        />
        {skipped.length > 0 && (
          <Alert severity="warning">
            {savedMessage}，以下資料夾沒有安裝：
            <ul className={styles.skippedList}>
              {skipped.map((entry) => (
                <li key={entry.path}>
                  <code>{entry.path}</code>：{entry.reason}
                </li>
              ))}
            </ul>
            {skipped.some((entry) => entry.conflict) && !replace && (
              <div className={styles.alertActions}>
                <Button variant="secondary" size="sm" onClick={() => handleUpload(true)} loading={uploading}>
                  取代同名的既有技能
                </Button>
              </div>
            )}
          </Alert>
        )}
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
        {skipped.length > 0 ? (
          <Button variant="primary" onClick={close} disabled={uploading}>
            完成
          </Button>
        ) : (
          <>
            <Button variant="secondary" onClick={close} disabled={uploading}>
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
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}
