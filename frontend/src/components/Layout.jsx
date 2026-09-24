import { useId, useState } from 'react';
import { useNavigate, useLocation, Outlet, NavLink } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../contexts/ThemeContext';
import { APP_NAME } from '../config/brand';
import NetworkStatus from './NetworkStatus';
import { Avatar, Menu, MenuItem, MenuDivider, MenuGroup, Icon } from './ui';
import styles from './Layout.module.css';
const THEME_OPTIONS = [
  { value: 'light', label: '淺色', icon: 'sun' },
  { value: 'dark', label: '深色', icon: 'moon' },
  { value: 'system', label: '跟隨系統', icon: 'monitor' },
];
function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const [anchorEl, setAnchorEl] = useState(null);
  const menuId = useId();
  const open = Boolean(anchorEl);
  // 聊天頁需要固定在一個視窗高度內，讓訊息列表自己捲動
  const isFixedLayout = location.pathname.startsWith('/chat');
  const navItems = [
    { to: '/chat', icon: 'chat', label: '聊天' },
    ...(user?.is_admin
      ? [
        { to: '/tools', icon: 'tools', label: 'AI 工具' },
        { to: '/documents', icon: 'description', label: '知識庫' },
        { to: '/admin', icon: 'admin', label: '管理後台' },
      ]
      : []),
  ];
  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };
  const handleMenuClose = () => {
    setAnchorEl(null);
  };
  const handleProfile = () => {
    handleMenuClose();
    navigate('/profile');
  };
  const handleSelectTheme = (value) => {
    setTheme(value);
    handleMenuClose();
  };
  const handleLogout = async () => {
    handleMenuClose();
    await logout();
    navigate('/login', { replace: true });
  };
  return (
    <div className={`${styles.wrapper} ${isFixedLayout ? styles.wrapperFixed : ''}`}>
      <a href="#main-content" className={styles.skipLink}>跳到主要內容</a>
      <header className={styles.appBar}>
        <div className={styles.toolbar}>
          <div className={styles.brand}>{APP_NAME}</div>
          <div className={styles.navGroup}>
            <nav aria-label="主要功能">
              <ul className={styles.navList}>
                {navItems.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      title={item.label}
                      className={({ isActive }) => `${styles.navButton} ${isActive ? styles.navButtonActive : ''}`}
                    >
                      <Icon name={item.icon} size={18} />
                      <span className={styles.navLabel}>{item.label}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </nav>
            <button
              type="button"
              onClick={handleMenuOpen}
              className={styles.userAvatarBtn}
              aria-label={user?.username ? `帳號選單（${user.username}）` : '帳號選單'}
              aria-haspopup="menu"
              aria-expanded={open}
              aria-controls={open ? menuId : undefined}
            >
              <Avatar size={34} style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary-text)' }}>
                {user?.username?.[0]?.toUpperCase() || <Icon name="account-circle" size={20} />}
              </Avatar>
            </button>
          </div>
        </div>
      </header>
      <Menu
        id={menuId}
        aria-label="帳號選單"
        anchorEl={anchorEl}
        open={open}
        onClose={handleMenuClose}
        placement="bottom-end"
      >
        <div className={styles.userMenuHeader} role="presentation">
          {user?.username}
        </div>
        <MenuItem
          icon={<Icon name="person" size={16} />}
          onClick={handleProfile}
        >
          個人資料
        </MenuItem>
        <MenuDivider />
        <MenuGroup label="外觀">
          {THEME_OPTIONS.map((option) => (
            <MenuItem
              key={option.value}
              icon={<Icon name={option.icon} size={16} />}
              checked={theme === option.value}
              onClick={() => handleSelectTheme(option.value)}
            >
              {option.label}
            </MenuItem>
          ))}
        </MenuGroup>
        <MenuDivider />
        <MenuItem
          icon={<Icon name="logout" size={16} />}
          danger
          onClick={handleLogout}
        >
          登出
        </MenuItem>
      </Menu>
      <main
        id="main-content"
        tabIndex={-1}
        className={`${styles.mainContent} ${isFixedLayout ? styles.mainContentFixed : ''}`}
      >
        <Outlet />
      </main>
      <NetworkStatus />
    </div>
  );
}
export default Layout;
