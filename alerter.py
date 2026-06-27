import time
import ctypes
import threading
import winsound


EVENT_LABELS = {
    "slouch": "驼背提醒",
    "lean_forward": "前倾提醒",
    "head_tilt": "歪头提醒",
    "sedentary": "久坐提醒",
    "phone_use": "手机使用提醒",
}

SEVERITY_LABELS = {
    "mild": "轻度",
    "severe": "严重",
}


def _show_popup(title: str, message: str):
    """Windows MessageBox 弹窗，在独立线程中运行避免阻塞"""
    ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x1)


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
        if event_type == "phone_use":
            message = "你已经看手机超过 20 分钟，放下手机休息一下吧"

        # 弹窗在独立线程，不阻塞主循环
        threading.Thread(target=_show_popup, args=(title, message), daemon=True).start()

        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

        self.record_alert(event_type)
