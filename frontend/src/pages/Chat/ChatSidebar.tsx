import React, { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { ChatSidebarProps } from './types';
import { groupConversations } from './chatFormat';
import { Button, IconButton, Tooltip, Icon, useModalDialog } from '../../components/ui';
import styles from './ChatSidebar.module.css';
const SKELETON_ROWS = 5;
export const ChatSidebar: React.FC<ChatSidebarProps> = ({
  id,
  open,
  onClose,
  conversations,
  currentConversation,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  loading,
  loadError,
  onRetryLoad,
}) => {
  const drawerRef = useRef<HTMLDialogElement>(null);
  const drawerHandlers = useModalDialog(drawerRef, open, onClose);
  // 桌面版改用常駐側欄，視窗放大時關閉抽屜，避免頁面仍處於模態狀態
  useEffect(() => {
    if (!open) return;
    const desktopQuery = window.matchMedia('(min-width: 900px)');
    const handleChange = () => {
      if (desktopQuery.matches) onClose();
    };
    desktopQuery.addEventListener('change', handleChange);
    return () => desktopQuery.removeEventListener('change', handleChange);
  }, [open, onClose]);
  const groupIdPrefix = useId();
  const groups = groupConversations(conversations, new Date());
  const renderContent = (inDrawer: boolean) => (
    <div className={styles.sidebarInner}>
      <div className={styles.sidebarTop}>
        <Button
          fullWidth
          variant="primary"
          startIcon={<Icon name="add" size={18} />}
          onClick={() => {
            onNewConversation();
            if (inDrawer) onClose();
          }}
        >
          開啟新對話
        </Button>
        {inDrawer && (
          <IconButton size="md" onClick={onClose} aria-label="關閉對話清單">
            <Icon name="close" size={20} />
          </IconButton>
        )}
      </div>
      <nav className={styles.listArea} aria-label="歷史對話" aria-busy={loading || undefined}>
        {loadError ? (
          <div className={styles.errorState} role="alert">
            <span>{loadError}</span>
            <Button size="sm" variant="outline" onClick={onRetryLoad} startIcon={<Icon name="refresh" size={14} />}>
              重新載入
            </Button>
          </div>
        ) : loading && conversations.length === 0 ? (
          <>
            <ul className={styles.skeletonList} aria-hidden="true">
              {Array.from({ length: SKELETON_ROWS }, (_, idx) => (
                <li key={idx} className={styles.skeletonRow} />
              ))}
            </ul>
            <span className="sr-only">正在載入對話清單...</span>
          </>
        ) : conversations.length === 0 ? (
          <div className={styles.emptyState}>
            <Icon name="chat" size={20} className={styles.emptyIcon} />
            <p className={styles.emptyTitle}>尚無歷史對話</p>
            <p className={styles.emptyText}>送出第一個問題後，對話會出現在這裡。</p>
          </div>
        ) : (
          groups.map((group) => {
            const labelId = `${groupIdPrefix}-${inDrawer ? 'drawer' : 'side'}-${group.key}`;
            return (
              <section key={group.key} className={styles.group}>
                <p className={styles.groupLabel} id={labelId}>{group.label}</p>
                <ul className={styles.conversationList} aria-labelledby={labelId}>
                  {group.conversations.map((conv, idx) => {
                    const isSelected = currentConversation?.id === conv.id;
                    const title = conv.title || '未命名對話';
                    return (
                      <li
                        key={conv.id ? `conv-${conv.id}` : `conv-${idx}`}
                        className={`${styles.conversationItem} ${isSelected ? styles.conversationSelected : ''}`}
                      >
                        <button
                          type="button"
                          className={styles.conversationButton}
                          onClick={() => {
                            onSelectConversation(conv.id);
                            if (inDrawer) onClose();
                          }}
                          aria-current={isSelected ? 'true' : undefined}
                          title={title}
                        >
                          <span className={styles.conversationTitle}>{title}</span>
                        </button>
                        <Tooltip title="刪除此對話">
                          <IconButton
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteConversation(conv.id);
                            }}
                            className={styles.deleteButton}
                            aria-label={`刪除對話「${title}」`}
                          >
                            <Icon name="delete" size={16} />
                          </IconButton>
                        </Tooltip>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })
        )}
      </nav>
    </div>
  );
  return (
    <>
      <aside className={styles.desktopSidebar} aria-label="對話清單">
        {renderContent(false)}
      </aside>
      {open &&
        createPortal(
          <dialog
            ref={drawerRef}
            id={id}
            className={styles.mobileDrawer}
            aria-label="對話清單"
            {...drawerHandlers}
          >
            {renderContent(true)}
          </dialog>,
          document.body
        )}
    </>
  );
};
export default ChatSidebar;
