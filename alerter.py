import time
import winsound
from plyer import notification


EVENT_LABELS = {
    "slouch": "驼背提醒",
    "lean_forward": "前倾提醒",
    "head_tilt": "歪头提醒",
    "sedentary": "久坐提醒",
}

SEVERITY_LABELS = {
    "mild": "轻度",
    "severe": "严重",
}


class AlertManager:
    def __init__(self, cooldown_minutes: int = 5):
        self.cooldown_seconds = cooldown_minutes * 60
        self._last_alert: dict[str, float] = {}

    def should_alert(self, event_type: str) -> bool:
        last = self._last_alert.get(event_type)
        if last is None:
            return True
        return (time.time() - last) >= self.cooldown_seconds

    def record_alert(self, event_type: str):
        self._last_alert[event_type] = time.time()

    def notify(self, event_type: str, severity: str):
        label = EVENT_LABELS.get(event_type, event_type)
        sev_label = SEVERITY_LABELS.get(severity, severity)
        title = f"[{sev_label}] {label}"
        message = "请调整坐姿，保持脊柱直立"
        if event_type == "sedentary":
            message = "你已经久坐超过 60 分钟，起身活动一下吧"

        try:
            notification.notify(title=title, message=message, timeout=5)
        except Exception:
            pass

        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

        self.record_alert(event_type)
