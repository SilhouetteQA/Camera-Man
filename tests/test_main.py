from config import AppConfig
from main import StateMachine, SedentaryTimer, PhoneTimer


# ---- 模拟 PostureResult, 避免导入 analyzer ----
class FakeResult:
    def __init__(self, **kwargs):
        defaults = {
            "person_present": True,
            "slouch": False,
            "lean_forward": False,
            "head_tilt": False,
            "phone_use": False,
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


# ==================== StateMachine ====================

class TestStateMachine:
    def test_no_trigger_initially(self):
        sm = StateMachine(AppConfig())
        result = FakeResult()
        assert sm.update(result) == []

    def test_single_frame_not_confirmed(self):
        sm = StateMachine(AppConfig(debounce_frames=3))
        result = FakeResult(slouch=True)
        confirmed = sm.update(result)
        assert "slouch" not in confirmed  # 仅 1 帧, 不够 debounce

    def test_confirmed_after_debounce_frames(self):
        sm = StateMachine(AppConfig(debounce_frames=3))
        result = FakeResult(slouch=True)
        for _ in range(3):
            confirmed = sm.update(result)
        assert "slouch" in confirmed

    def test_confirmed_clears_after_good_frames(self):
        sm = StateMachine(AppConfig(debounce_frames=3))
        bad = FakeResult(slouch=True)
        good = FakeResult(slouch=False)
        # 先触发确认
        for _ in range(3):
            sm.update(bad)
        assert "slouch" in sm.confirmed
        # 恢复正常后解除
        for _ in range(3):
            sm.update(good)
        assert "slouch" not in sm.confirmed

    def test_multiple_types_independent(self):
        sm = StateMachine(AppConfig(debounce_frames=2))
        result = FakeResult(slouch=True, head_tilt=True)
        for _ in range(2):
            confirmed = sm.update(result)
        assert "slouch" in confirmed
        assert "head_tilt" in confirmed

    def test_partial_recovery_keeps_others(self):
        sm = StateMachine(AppConfig(debounce_frames=3))
        # 先让 slouch 和 head_tilt 都确认
        both = FakeResult(slouch=True, head_tilt=True)
        for _ in range(3):
            sm.update(both)
        assert "slouch" in sm.confirmed
        assert "head_tilt" in sm.confirmed
        # 只恢复 head_tilt
        only_slouch = FakeResult(slouch=True, head_tilt=False)
        for _ in range(3):
            sm.update(only_slouch)
        assert "slouch" in sm.confirmed
        assert "head_tilt" not in sm.confirmed

    def test_phone_use_tracked_by_state_machine(self):
        """phone_use 也被状态机追踪 (虽然告警走累计计时器)"""
        sm = StateMachine(AppConfig(debounce_frames=3))
        result = FakeResult(phone_use=True)
        for _ in range(3):
            confirmed = sm.update(result)
        assert "phone_use" in confirmed


# ==================== SedentaryTimer ====================

class TestSedentaryTimer:
    def test_no_alert_below_threshold(self):
        timer = SedentaryTimer(AppConfig(sedentary_threshold=60))
        for _ in range(59):
            timer.tick(person_present=True)
        assert timer.should_alert() is False

    def test_alert_at_threshold(self):
        timer = SedentaryTimer(AppConfig(sedentary_threshold=60))
        for _ in range(60):
            timer.tick(person_present=True)
        assert timer.should_alert() is True

    def test_no_double_alert(self):
        timer = SedentaryTimer(AppConfig(sedentary_threshold=60))
        for _ in range(60):
            timer.tick(person_present=True)
        assert timer.should_alert() is True
        # 再次调用不应重复告警
        timer.tick(person_present=True)
        assert timer.should_alert() is False

    def test_reset_when_person_leaves(self):
        timer = SedentaryTimer(AppConfig(sedentary_threshold=60))
        for _ in range(45):
            timer.tick(person_present=True)
        # 离开后累积分钟数重置
        timer.tick(person_present=False)
        assert timer.minutes == 0
        assert timer.alerted is False

    def test_resets_alerted_flag_after_leave(self):
        timer = SedentaryTimer(AppConfig(sedentary_threshold=2))
        # 触发告警
        for _ in range(2):
            timer.tick(person_present=True)
        assert timer.should_alert() is True
        # 离开并返回
        timer.tick(person_present=False)
        timer.tick(person_present=True)
        # 仅回来 1 分钟, 不够触发告警
        assert timer.should_alert() is False


# ==================== PhoneTimer ====================

class TestPhoneTimer:
    def test_no_alert_below_threshold(self):
        timer = PhoneTimer(AppConfig(phone_use_threshold=10, phone_grace_minutes=2))
        for _ in range(9):
            timer.tick(phone_use=True)
        assert timer.should_alert() is False

    def test_alert_at_threshold(self):
        timer = PhoneTimer(AppConfig(phone_use_threshold=10, phone_grace_minutes=2))
        for _ in range(10):
            timer.tick(phone_use=True)
        assert timer.should_alert() is True

    def test_no_double_alert(self):
        timer = PhoneTimer(AppConfig(phone_use_threshold=10, phone_grace_minutes=2))
        for _ in range(10):
            timer.tick(phone_use=True)
        assert timer.should_alert() is True
        timer.tick(phone_use=True)
        assert timer.should_alert() is False

    def test_brief_lookup_does_not_reset(self):
        """短暂抬头 (在容差期内) 不重置累计"""
        timer = PhoneTimer(AppConfig(phone_use_threshold=10, phone_grace_minutes=2))
        # 使用手机 5 分钟
        for _ in range(5):
            timer.tick(phone_use=True)
        assert timer.minutes == 5
        # 抬头 1 分钟 (在 2 分钟容差期内)
        timer.tick(phone_use=False)
        assert timer.minutes == 5  # 累计不变
        # 再次使用手机
        timer.tick(phone_use=True)
        assert timer.minutes == 6  # 继续累计

    def test_prolonged_lookup_resets(self):
        """连续离开超过容差期后重置累计"""
        timer = PhoneTimer(AppConfig(phone_use_threshold=10, phone_grace_minutes=2))
        # 使用手机 5 分钟
        for _ in range(5):
            timer.tick(phone_use=True)
        assert timer.minutes == 5
        # 离开 3 分钟 (超过 2 分钟容差期)
        for _ in range(3):
            timer.tick(phone_use=False)
        assert timer.minutes == 0
        assert timer.alerted is False

    def test_alert_flag_reset_after_prolonged_lookup(self):
        timer = PhoneTimer(AppConfig(phone_use_threshold=3, phone_grace_minutes=2))
        # 触发告警
        for _ in range(3):
            timer.tick(phone_use=True)
        assert timer.should_alert() is True
        # 超过容差期的离开重置告警标志
        for _ in range(3):
            timer.tick(phone_use=False)
        assert timer.alerted is False
        # 重新使用手机, 可再次告警
        for _ in range(3):
            timer.tick(phone_use=True)
        assert timer.should_alert() is True

    def test_absent_minutes_reset_on_phone_use(self):
        """恢复使用手机时 absent_minutes 归零"""
        timer = PhoneTimer(AppConfig(phone_use_threshold=10, phone_grace_minutes=2))
        timer.tick(phone_use=False)
        timer.tick(phone_use=False)
        assert timer.absent_minutes == 2
        timer.tick(phone_use=True)
        assert timer.absent_minutes == 0
