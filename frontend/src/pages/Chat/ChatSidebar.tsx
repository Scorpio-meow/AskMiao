import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { ChatSidebarProps } from './types';
import { Button, IconButton, Tooltip, Spinner, Icon, useModalDialog } from '../../components/ui';
import styles from './ChatSidebar.module.css';
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
  const renderContent = (inDrawer: boolean) => (
    <div className={styles.sidebarInner}>
      <div className={styles.newButtonArea}>
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
      <div className={styles.divider} />
      <nav className={styles.listArea} aria-label="歷史對話">
        <p className={styles.sectionTitle}>歷史對話記錄</p>
        {loadError ? (
          <div className={styles.errorState} role="alert">
            <span>{loadError}</span>
            <Button size="sm" variant="outline" onClick={onRetryLoad} startIcon={<Icon name="refresh" size={14} />}>
              重新載入
            </Button>
          </div>
        ) : loading && conversations.length === 0 ? (
          <div className={styles.loadingCenter}>
            <Spinner size={24} color="var(--color-primary)" />
          </div>
        ) : conversations.length === 0 ? (
          <div className={styles.emptyText}>尚無歷史對話</div>
        ) : (
          <ul className={styles.conversationList}>
            {conversations.map((conv, idx) => {
              const isSelected = currentConversation?.id === conv.id;
              const title = conv.title || '未命名對話';
              return (
                <li
                  key={conv.id ? `conv-${conv.id}` : `conv-${idx}`}
                  className={styles.conversationItem}
                >
                  <button
                    type="button"
                    className={`${styles.conversationButton} ${isSelected ? styles.conversationSelected : ''}`}
                    onClick={() => {
                      onSelectConversation(conv.id);
                      if (inDrawer) onClose();
                    }}
                    aria-current={isSelected ? 'true' : undefined}
                    title={title}
                  >
                    <Icon name="chat" size={18} />
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
