import { useState, useEffect } from 'react';
import { Snackbar, Alert } from './ui';
import networkMonitor from '../utils/networkMonitor';
const NetworkStatus = () => {
  // offline：目前離線；restored：剛從離線恢復。一開始就在線上時不顯示任何提示
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let wasOffline = false;
    const handleNetworkChange = (next) => {
      if (next === 'offline') {
        wasOffline = true;
        setStatus('offline');
      } else if (wasOffline) {
        wasOffline = false;
        setStatus('restored');
      }
    };
    networkMonitor.addListener(handleNetworkChange);
    return () => {
      networkMonitor.removeListener(handleNetworkChange);
    };
  }, []);
  const handleClose = () => {
    setStatus(null);
  };
  return (
    <>
      <Snackbar
        open={status === 'offline'}
        autoHideDuration={0}
        anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        onClose={handleClose}
      >
        <Alert onClose={handleClose} severity="warning">
          目前處於離線狀態，部分功能可能無法使用
        </Alert>
      </Snackbar>
      <Snackbar
        open={status === 'restored'}
        autoHideDuration={3000}
        anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        onClose={handleClose}
      >
        <Alert onClose={handleClose} severity="success">
          網路已恢復連線
        </Alert>
      </Snackbar>
    </>
  );
};
export default NetworkStatus;
