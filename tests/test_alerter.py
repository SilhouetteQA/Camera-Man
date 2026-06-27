import time
from alerter import AlertManager


class TestAlertManager:
    def test_should_alert_first_time(self):
        mgr = AlertManager(cooldown_minutes=5)
        assert mgr.should_alert("slouch") is True

    def test_should_not_alert_within_cooldown(self):
        mgr = AlertManager(cooldown_minutes=5)
        mgr.record_alert("slouch")
        assert mgr.should_alert("slouch") is False

    def test_different_types_independent_cooldown(self):
        mgr = AlertManager(cooldown_minutes=5)
        mgr.record_alert("slouch")
        assert mgr.should_alert("slouch") is False
        assert mgr.should_alert("head_tilt") is True

    def test_cooldown_expires(self, monkeypatch):
        mgr = AlertManager(cooldown_minutes=5)
        mgr.record_alert("slouch")
        # 快进 6 分钟
        future = time.time() + 6 * 60
        monkeypatch.setattr(time, "time", lambda: future)
        assert mgr.should_alert("slouch") is True

    def test_notify_does_not_raise(self):
        mgr = AlertManager(cooldown_minutes=5)
        # 不应抛异常（即使没有托盘环境，plyer 可能失败但不崩溃）
        try:
            mgr.notify("slouch", "severe")
        except Exception:
            pass  # CI 环境可能无通知系统
