# main.py
import time
import threading
import cv2
from config import AppConfig, ALL_EVENT_TYPES
from camera import CameraService
from analyzer import PostureAnalyzer
from alerter import AlertManager
from storage import EventStore
from tray_ui import TrayController


class StateMachine:
    """去抖状态机"""
    def __init__(self, config: AppConfig):
        self.config = config
        self.bad_frames: dict[str, int] = {}
        self.good_frames: dict[str, int] = {}
        self.confirmed: set[str] = set()

    def update(self, result) -> list:
        """返回待触发的告警类型列表"""
        for t in ALL_EVENT_TYPES:
            triggered = getattr(result, t, False)
            if triggered:
                self.bad_frames[t] = self.bad_frames.get(t, 0) + 1
                self.good_frames[t] = 0
                if self.bad_frames[t] >= self.config.debounce_frames:
                    self.confirmed.add(t)
            else:
                self.good_frames[t] = self.good_frames.get(t, 0) + 1
                self.bad_frames[t] = 0
                if self.good_frames[t] >= self.config.debounce_frames:
                    self.confirmed.discard(t)

        return list(self.confirmed)


class SedentaryTimer:
    """久坐计时器"""
    def __init__(self, config: AppConfig):
        self.threshold_minutes = config.sedentary_threshold
        self.minutes = 0
        self.alerted = False

    def tick(self, person_present: bool):
        if person_present:
            self.minutes += 1
        else:
            self.minutes = 0
            self.alerted = False

    def should_alert(self) -> bool:
        if self.minutes >= self.threshold_minutes and not self.alerted:
            self.alerted = True
            return True
        return False


class PhoneTimer:
    """手机使用计时器，短暂抬头(默认2分钟内)不重置累计"""
    def __init__(self, config: AppConfig):
        self.threshold_minutes = config.phone_use_threshold
        self.grace_minutes = config.phone_grace_minutes
        self.minutes = 0
        self.absent_minutes = 0
        self.alerted = False

    def tick(self, phone_use: bool):
        if phone_use:
            self.minutes += 1
            self.absent_minutes = 0
        else:
            self.absent_minutes += 1
            # 连续离开超过容差期才重置
            if self.absent_minutes > self.grace_minutes:
                self.minutes = 0
                self.absent_minutes = 0
                self.alerted = False

    def should_alert(self) -> bool:
        if self.minutes >= self.threshold_minutes and not self.alerted:
            self.alerted = True
            return True
        return False


class App:
    def __init__(self):
        self.config = AppConfig()
        self.camera = CameraService(self.config.camera_device_id)
        self.analyzer = PostureAnalyzer(self.config)
        self.alerter = AlertManager(self.config.cooldown_minutes)
        self.storage = EventStore()
        self.state_machine = StateMachine(self.config)
        self.sedentary = SedentaryTimer(self.config)
        self.phone_timer = PhoneTimer(self.config)
        self._running = False
        self._loop_thread = None

    def start(self):
        self.camera.start()
        self._running = True
        self._loop_thread = threading.Thread(target=self._loop, daemon=True)
        self._loop_thread.start()

    def pause(self):
        self._running = False
        # 等待 daemon 线程退出后再操作共享状态 (避免 SedentaryTimer 竞态)
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=self.config.pause_join_timeout)
        self.camera.stop()
        self.analyzer.reset()
        # 此时 _loop 已退出, 安全重置计时器
        self.sedentary.minutes = 0
        self.sedentary.alerted = False
        self.phone_timer.minutes = 0
        self.phone_timer.alerted = False

    def exit(self):
        # camera.stop() 由 pause() 负责, 此处无需重复调用
        self._running = False

    def _handle_confirmed_alerts(self, confirmed, result):
        """处理去抖确认的姿态告警 (不含 phone_use, 走累计计时器)"""
        for event_type in confirmed:
            if event_type == "phone_use":
                continue  # 手机使用走累计计时
            if self.alerter.should_alert(event_type):
                self.alerter.notify(event_type, "severe")
            self.storage.record(event_type, "severe", result.confidence, "")

    def _tick_minute_timers(self, result):
        """每分钟触发一次: 更新久坐/手机计时器, 检查是否告警"""
        self.sedentary.tick(result.person_present)
        self.phone_timer.tick(result.phone_use and result.person_present)
        if result.person_present:
            self.storage.record_sitting_minute()
        if self.sedentary.should_alert():
            self.alerter.notify("sedentary", "severe")
            self.storage.record("sedentary", "severe", 1.0, "")
        if self.phone_timer.should_alert():
            self.alerter.notify("phone_use", "severe")
            self.storage.record("phone_use", "severe", 1.0, "")

    def _loop(self):
        try:
            minute_counter = 0
            while self._running:
                frame = self.camera.capture()
                if frame is None:
                    time.sleep(0.5)
                    continue

                result = self.analyzer.analyze(frame)

                # 去抖 + 告警
                confirmed = self.state_machine.update(result)
                self._handle_confirmed_alerts(confirmed, result)

                # 每分钟计时
                minute_counter += 1
                if minute_counter >= self.config.frames_per_minute:
                    minute_counter = 0
                    self._tick_minute_timers(result)

                time.sleep(self.config.sample_interval)
        except Exception as e:
            import traceback
            print(f"监控循环异常: {e}")
            traceback.print_exc()


def main():
    try:
        _main()
    except Exception as e:
        import traceback
        print(f"程序异常退出: {e}")
        traceback.print_exc()


def _main():
    app = App()

    controller = TrayController(
        on_start=app.start,
        on_pause=app.pause,
        on_exit=app.exit,
    )
    controller.run()


if __name__ == "__main__":
    main()
