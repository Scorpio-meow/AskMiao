
import logging
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Optional
from collections import OrderedDict, deque
import json
from pathlib import Path
from app.core.limits import MAX_EVENTS_PER_ADDRESS, MAX_TRACKED_ADDRESSES
logger = logging.getLogger(__name__)
# 沒有專屬門檻的事件類型保留多久
DEFAULT_EVENT_WINDOW_SECONDS = 3600
class IntrusionDetector:
    """以位址與事件類型分組的滑動視窗計數。

    每種事件只保留門檻所需的最近事件（deque 有長度上限、依時間排序，過期的從左端移除），
    追蹤的位址數也有上限（最久未活動的先淘汰），單次記錄的成本與歷史事件數無關。
    """
    
    def __init__(self, log_file: str = "logs/intrusion_detection.log"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(exist_ok=True)
        
        self.ip_events: "OrderedDict[str, Dict[str, Deque[datetime]]]" = OrderedDict()
        
        # 只發出警報、不封鎖位址；登入失敗的節流見 app.core.login_throttle
        self.thresholds = {
            'api_requests_max': 1000,
            'api_requests_window': 3600,
            'file_uploads_max': 50,
            'file_uploads_window': 3600,
        }
        # 事件類型 -> (門檻, 視窗秒數, 警報類型)
        self._rules = {
            'api_request': ('api_requests', 'DDOS_ATTACK'),
            'file_upload': ('file_uploads', 'SUSPICIOUS_FILE_UPLOAD'),
        }
    
    def _limits_for(self, event_type: str):
        rule = self._rules.get(event_type)
        if rule is None:
            return MAX_EVENTS_PER_ADDRESS, DEFAULT_EVENT_WINDOW_SECONDS
        prefix = rule[0]
        return self.thresholds[f'{prefix}_max'], self.thresholds[f'{prefix}_window']
    
    def record_event(
        self, 
        event_type: str, 
        ip_address: str, 
        user_id: Optional[int] = None,
        details: Optional[Dict] = None
    ):
        now = datetime.utcnow()
        events_by_type = self.ip_events.get(ip_address)
        if events_by_type is None:
            events_by_type = {}
            self.ip_events[ip_address] = events_by_type
            while len(self.ip_events) > MAX_TRACKED_ADDRESSES:
                self.ip_events.popitem(last=False)
        else:
            self.ip_events.move_to_end(ip_address)
        max_events, window = self._limits_for(event_type)
        events = events_by_type.get(event_type)
        if events is None:
            # 多留一格：計數停在門檻 +1，不會每筆新事件都重新「達到門檻」而重複警報
            events = deque(maxlen=max_events + 1)
            events_by_type[event_type] = events
        events.append(now)
        cutoff = now - timedelta(seconds=window)
        while events and events[0] <= cutoff:
            events.popleft()
        self._check_threshold(ip_address, event_type, len(events))
    
    def _check_threshold(self, ip_address: str, event_type: str, count: int):
        rule = self._rules.get(event_type)
        if rule is None:
            return
        threshold, _ = self._limits_for(event_type)
        # 只在剛達到門檻時發出一次警報，之後持續超量不重複寫檔
        if count != threshold:
            return
        prefix, threat_type = rule
        messages = {
            'api_request': f"檢測到異常高頻率的 API 請求: {count} 次",
            'file_upload': f"檢測到異常高頻率的文件上傳: {count} 次",
        }
        self._trigger_alert(ip_address, threat_type, messages[event_type], {'count': count})
    
    def _trigger_alert(
        self, 
        ip_address: str, 
        threat_type: str, 
        message: str,
        details: Dict
    ):
        alert = {
            'timestamp': datetime.utcnow().isoformat(),
            'ip_address': ip_address,
            'threat_type': threat_type,
            'message': message,
            'details': details
        }
        
        logger.warning(f"🚨 安全警報: {json.dumps(alert, ensure_ascii=False)}")
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(alert, ensure_ascii=False) + '\n')
    
    def get_suspicious_ips(self, limit: int = 10) -> List[Dict]:
        ip_scores = []
        cutoff = datetime.utcnow() - timedelta(hours=1)
        
        for ip, events_by_type in self.ip_events.items():
            recent = {event_type: sum(1 for ts in events if ts > cutoff) for event_type, events in events_by_type.items()}
            event_count = sum(recent.values())
            if event_count:
                ip_scores.append({
                    'ip': ip,
                    'event_count': event_count,
                })
        
        ip_scores.sort(key=lambda x: x['event_count'], reverse=True)
        
        return ip_scores[:limit]
_intrusion_detector_instance: Optional[IntrusionDetector] = None
def get_intrusion_detector() -> IntrusionDetector:
    global _intrusion_detector_instance
    
    if _intrusion_detector_instance is None:
        _intrusion_detector_instance = IntrusionDetector()
    
    return _intrusion_detector_instance
