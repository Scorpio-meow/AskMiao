import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { APP_NAME, APP_TAGLINE } from '../config/brand';
import { TextField, Button, Alert, IconButton, Icon } from '../components/ui';
import styles from './Auth.module.css';
const RegisterPage = () => {
  const navigate = useNavigate();
  const { register, loading, error: authError } = useAuth();
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState('');
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [success, setSuccess] = useState(false);
  useDocumentTitle('註冊');
  const passwordRequirements = [
    { key: 'length', label: '至少 8 個字元', met: formData.password.length >= 8 },
    { key: 'uppercase', label: '包含大寫字母', met: /[A-Z]/.test(formData.password) },
    { key: 'lowercase', label: '包含小寫字母', met: /[a-z]/.test(formData.password) },
    { key: 'number', label: '包含數字', met: /[0-9]/.test(formData.password) },
    {
      key: 'match',
      label: '兩次密碼輸入一致',
      met: formData.password === formData.confirmPassword && formData.password.length > 0
    },
  ];
  const isPasswordValid = passwordRequirements.every((req) => req.met);
  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
    if (localError) setLocalError('');
  };
  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitAttempted(true);
    if (!formData.username || !formData.email || !formData.password) {
      setLocalError('請填寫所有必填欄位');
      return;
    }
    if (!isPasswordValid) {
      setLocalError('密碼尚未符合下列要求');
      return;
    }
    setLocalError('');
    const result = await register(
      formData.username,
      formData.email,
      formData.password
    );
    if (result.success) {
      setSuccess(true);
      setTimeout(() => {
        navigate('/', { replace: true });
      }, 2000);
    }
  };
  const error = localError || authError;
  if (success) {
    return (
      <div className={styles.container}>
        <div className={`${styles.card} ${styles.successCard}`} role="status">
          <div className={styles.successIcon}>
            <Icon name="check-circle" size={64} />
          </div>
          <h1 className={styles.title}>註冊成功！</h1>
          <p className={styles.subtitle}>正在前往首頁...</p>
        </div>
      </div>
    );
  }
  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerIcon}>
            <Icon name="person-add" size={48} />
          </div>
          <h1 className={styles.title}>建立新帳號</h1>
          <p className={styles.subtitle}>填寫以下資料完成註冊</p>
        </div>
        {error && (
          <Alert severity="error" style={{ marginBottom: '16px' }}>
            {error}
          </Alert>
        )}
        <form onSubmit={handleSubmit} className={styles.form} noValidate>
          <TextField
            fullWidth
            label="使用者名稱"
            name="username"
            value={formData.username}
            onChange={handleChange}
            disabled={loading}
            autoFocus
            autoComplete="username"
            required
            helperText="3–50 個字元，只能包含英文字母、數字、底線（_）與連字號（-）"
          />
          <TextField
            fullWidth
            label="電子郵件"
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            disabled={loading}
            autoComplete="email"
            required
          />
          <TextField
            fullWidth
            label="密碼"
            name="password"
            type={showPassword ? 'text' : 'password'}
            value={formData.password}
            onChange={handleChange}
            disabled={loading}
            autoComplete="new-password"
            required
            aria-describedby="password-requirements"
            endAdornment={
              <IconButton
                size="sm"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? '隱藏密碼' : '顯示密碼'}
              >
                <Icon name={showPassword ? 'visibility-off' : 'visibility'} size={18} />
              </IconButton>
            }
          />
          <TextField
            fullWidth
            label="確認密碼"
            name="confirmPassword"
            type={showPassword ? 'text' : 'password'}
            value={formData.confirmPassword}
            onChange={handleChange}
            disabled={loading}
            autoComplete="new-password"
            required
          />
          <div className={styles.requirements} id="password-requirements">
            <div className={styles.requirementsTitle}>密碼要求：</div>
            <ul className={styles.requirementList} role="list">
              {passwordRequirements.map((req) => {
                const state = req.met ? 'met' : submitAttempted ? 'unmet' : 'pending';
                return (
                  <li
                    key={req.key}
                    className={`${styles.requirement} ${state === 'met' ? styles.requirementMet : state === 'unmet' ? styles.requirementUnmet : ''}`}
                  >
                    <Icon name={state === 'met' ? 'check' : state === 'unmet' ? 'close' : 'info'} size={14} />
                    <span>{req.label}</span>
                    <span className="sr-only">{state === 'met' ? '（已符合）' : '（尚未符合）'}</span>
                  </li>
                );
              })}
            </ul>
          </div>
          <Button
            fullWidth
            type="submit"
            variant="primary"
            size="lg"
            disabled={loading}
            loading={loading}
            className={styles.submitBtn}
          >
            註冊
          </Button>
        </form>
        <div className={styles.footer}>
          已有帳號？
          <Link to="/login" className={styles.link}>
            立即登入
          </Link>
        </div>
      </div>
      <p className={styles.copyright}>
        {APP_NAME} · {APP_TAGLINE}
      </p>
    </div>
  );
};
export default RegisterPage;
