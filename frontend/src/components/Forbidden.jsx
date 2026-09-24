import { useNavigate } from 'react-router-dom';
import { Button, Icon } from './ui';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import styles from './Forbidden.module.css';
const Forbidden = () => {
  const navigate = useNavigate();
  useDocumentTitle('沒有權限');
  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.icon}>
          <Icon name="lock" size={40} />
        </div>
        <h1 className={styles.title}>沒有權限檢視此頁面</h1>
        <p className={styles.description}>這個頁面只開放給管理員。如需權限，請聯絡系統管理員。</p>
        <Button variant="primary" onClick={() => navigate('/chat')} startIcon={<Icon name="chat" size={16} />}>
          回到聊天
        </Button>
      </div>
    </div>
  );
};
export default Forbidden;
