
class NetworkMonitor {
  constructor() {
    this.listeners = [];
    this.isOnline = navigator.onLine;
    window.addEventListener('online', this.handleOnline.bind(this));
    window.addEventListener('offline', this.handleOffline.bind(this));
  }
  handleOnline() {
    console.log('[Network] 網絡已連接');
    this.isOnline = true;
    this.notifyListeners('online');
  }
  handleOffline() {
    console.log('[Network] 網絡已斷開');
    this.isOnline = false;
    this.notifyListeners('offline');
  }
  addListener(callback) {
    this.listeners.push(callback);
    callback(this.isOnline ? 'online' : 'offline');
  }
  removeListener(callback) {
    this.listeners = this.listeners.filter(listener => listener !== callback);
  }
  notifyListeners(status) {
    this.listeners.forEach(listener => {
      try {
        listener(status);
      } catch (error) {
        console.error('[Network] 監聽器執行錯誤:', error);
      }
    });
  }
  checkOnline() {
    return this.isOnline;
  }
}
const networkMonitor = new NetworkMonitor();
export default networkMonitor;