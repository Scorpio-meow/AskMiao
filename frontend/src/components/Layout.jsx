import { useEffect, useId, useState } from 'react';
import { useNavigate, useLocation, Outlet, NavLink } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { LOGOUT_UNCONFIRMED_NOTICE } from '../services/authService';
import { useTheme } from '../contexts/ThemeContext';
import { APP_NAME } from '../config/brand';
import NetworkStatus from './NetworkStatus';
import { Avatar, Menu, MenuItem, MenuDivider, MenuGroup, Icon } from './ui';
import { runViewTransition } from '../utils/viewTransition';
import markUrl from '../assets/brand/askmiao-mark.png';
import styles from './Layout.module.css';
const THEME_OPTIONS = [
  { value: 'light', label: '淺色', icon: 'sun' },
  { value: 'dark', label: '深色', icon: 'moon' },
  { value: 'system', label: '跟隨系統', icon: 'monitor' },
];
function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout, getCurrentUser, isAuthenticated } = useAuth();
  const { theme, setTheme } = useTheme();
  useEffect(() => {
    if (isAuthenticated) getCurrentUser();
  }, [isAuthenticated, getCurrentUser, location.pathname]);
  const [anchorEl, setAnchorEl] = useState(null);
  const menuId = useId();
  const open = Boolean(anchorEl);
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
    handleMenuClose();
    if (value === theme) return;
    runViewTransition('theme', () => setTheme(value));
  };
  const handleLogout = async () => {
    handleMenuClose();
    const confirmed = await logout();
    navigate('/login', { replace: true, state: confirmed ? null : { notice: LOGOUT_UNCONFIRMED_NOTICE } });
  };
  return (
    <div className={`${styles.wrapper} ${isFixedLayout ? styles.wrapperFixed : ''}`}>
      <a href="#main-content" className={styles.skipLink}>跳到主要內容</a>
      <header className={styles.appBar}>
        <div className={styles.toolbar}>
          <div className={styles.brand}>
            <img src={markUrl} alt="" className={styles.brandMark} width="28" height="28" />
            <span className={styles.brandName}>{APP_NAME}</span>
          </div>
          <div className={styles.navGroup}>
            <nav aria-label="主要功能">
              <ul className={styles.navList}>
                {navItems.map((item, index) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      title={item.label}
                      viewTransition
                      className={({ isActive }) => `${styles.navButton} ${isActive ? styles.navButtonActive : ''}`}
                    >
                      {({ isActive }) => (
                        <>
                          {isActive && <span className={styles.navIndicator} aria-hidden="true" />}
                          <span className={styles.navContent} style={{ viewTransitionName: `nav-item-${index}` }}>
                            <Icon name={item.icon} size={17} />
                            <span className={styles.navLabel}>{item.label}</span>
                          </span>
                        </>
                      )}
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
              <Avatar size={30}>
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
        <Outlet context={user} />
      </main>
      <NetworkStatus />
    </div>
  );
}
export default Layout;