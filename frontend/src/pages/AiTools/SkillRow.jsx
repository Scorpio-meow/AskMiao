import { Button, Icon, Switch } from '../../components/ui';
import { CatalogRow, DangerAction, DetailBlock, DetailList, MetaText, StatusChip, Tag } from './CatalogParts';
import styles from './AiTools.module.css';
export default function SkillRow({
  skill,
  expanded,
  onToggleDetails,
  onToggle,
  onToggleScripts,
  onView,
  onUpload,
  onAccess,
  onUseInChat,
  onDelete,
}) {
  const isEnabled = skill.is_enabled;
  return (
    <CatalogRow
      titleId={`skill-${skill.id}`}
      inactive={!isEnabled}
      title={skill.name}
      chips={(
        <>
          {skill.license && <Tag>{skill.license}</Tag>}
          {skill.allowed_user_ids !== null && <Tag>限 {skill.allowed_user_ids.length} 位使用者</Tag>}
          {skill.allow_scripts && <Tag tone="warning">可執行腳本</Tag>}
          {skill.warnings.length > 0 && <Tag>{skill.warnings.length} 項規格提醒</Tag>}
        </>
      )}
      meta={<MetaText mono>/{skill.name}</MetaText>}
      description={skill.description}
      status={(
        <>
          {!skill.files_present && <StatusChip tone="error">找不到技能檔案</StatusChip>}
          <Switch
            checked={isEnabled}
            onChange={() => onToggle(skill.id)}
            aria-label={`啟用技能「${skill.name}」`}
            label={isEnabled ? '已啟用' : '已停用'}
          />
        </>
      )}
      actions={(
        <>
          <Button variant="secondary" size="sm" onClick={onView} startIcon={<Icon name="description" size={16} />}>
            檢視內容<span className="sr-only">「{skill.name}」</span>
          </Button>
          <Button variant="secondary" size="sm" onClick={onUpload} startIcon={<Icon name="upload" size={16} />}>
            上傳新版本<span className="sr-only">「{skill.name}」</span>
          </Button>
          <Button variant="secondary" size="sm" onClick={onAccess} startIcon={<Icon name="people" size={16} />}>
            使用者範圍<span className="sr-only">「{skill.name}」</span>
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={onUseInChat}
            disabled={!isEnabled || !skill.files_present}
            startIcon={<Icon name="chat" size={16} />}
          >
            在對話中使用<span className="sr-only">「{skill.name}」</span>
          </Button>
        </>
      )}
      dangerAction={<DangerAction label="刪除技能" itemName={skill.name} onClick={onDelete} />}
      detailsLabel="腳本與相容性"
      expanded={expanded}
      onToggleDetails={onToggleDetails}
      details={(
        <>
          <div className={styles.settingRow}>
            <div className={styles.settingText}>
              <span className={styles.settingTitle}>允許執行技能內的腳本</span>
              <p className={styles.settingDescription}>
                開啟後 AI 可以要求在主機上執行技能中的 .py、.sh、.js 腳本，每次都需要提問者在對話中核准（技能的 allowed-tools 列出 run_skill_script 時，載入技能後免核准）。腳本以後端帳號的權限執行，只對信任的技能開啟。
              </p>
            </div>
            <Switch
              checked={Boolean(skill.allow_scripts)}
              onChange={onToggleScripts}
              aria-label={`允許技能「${skill.name}」執行腳本`}
            />
          </div>
          {skill.compatibility && <DetailList items={[{ label: '相容性需求', value: skill.compatibility }]} />}
          {skill.warnings.length > 0 && (
            <DetailBlock title="與規格不符之處（不影響使用）">
              <ul className={styles.warningList}>
                {skill.warnings.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            </DetailBlock>
          )}
        </>
      )}
    />
  );
}
