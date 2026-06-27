# main.py
import time
import threading
import base64
import json
import cv2
from config import AppConfig
from camera import CameraService
from analyzer import PostureAnalyzer
from alerter import AlertManager
from storage import EventStore
from vision_client import VisionClient
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
        events = []
        all_types = ["slouch", "lean_forward", "head_tilt"]

        for t in all_types:
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


class App:
    def __init__(self):
        self.config = AppConfig()
        self.camera = CameraService(self.config.camera_device_id)
        self.analyzer = PostureAnalyzer(self.config)
        self.alerter = AlertManager(self.config.cooldown_minutes)
        self.storage = EventStore()
        self.vision = VisionClient(self.config)
        self.state_machine = StateMachine(self.config)
        self.sedentary = SedentaryTimer(self.config)
        self._running = False

    def start(self):
        self.camera.start()
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def pause(self):
        self._running = False
        self.camera.stop()
        self.analyzer.reset()
        self.sedentary.minutes = 0
        self.sedentary.alerted = False

    def exit(self):
        self._running = False
        self.camera.stop()

    def _parse_m3_judgment(self, content) -> dict:
        """解析 M3 返回的 JSON 字符串为字典"""
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            try:
                return json.loads(content)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    def _loop(self):
        minute_counter = 0
        while self._running:
            frame = self.camera.capture()
            if frame is None:
                time.sleep(0.5)
                continue

            result = self.analyzer.analyze(frame)

            # MinimaX M3 二次验证
            if self.vision.is_available and result.person_present:
                _, buf = cv2.imencode(".jpg", frame)
                frame_b64 = base64.b64encode(buf).decode("utf-8")
                verification = self.vision.verify(frame_b64, result)
                if verification:
                    m3_raw = verification["judgment"]
                    m3 = self._parse_m3_judgment(m3_raw)
                    # 对比: 如果 M3 判断不一致，以 M3 为准
                    result.slouch = m3.get("slouch", result.slouch)
                    result.lean_forward = m3.get("lean_forward", result.lean_forward)
                    result.head_tilt = m3.get("head_tilt", result.head_tilt)
                    result.person_present = m3.get("person_present", result.person_present)
                    result.triggered = [
                        t for t in ["slouch", "lean_forward", "head_tilt"]
                        if getattr(result, t)
                    ]
                    result.severity = "severe" if result.triggered else None

            # 去抖
            confirmed = self.state_machine.update(result)

            for event_type in confirmed:
                if self.alerter.should_alert(event_type):
                    self.alerter.notify(event_type, "severe")
                self.storage.record(event_type, "severe", result.confidence, "")

            # 久坐计时 (约每 12 帧 = 60 秒, 5 秒采样)
            minute_counter += 1
            if minute_counter >= 12:
                minute_counter = 0
                self.sedentary.tick(result.person_present)
                if result.person_present:
                    self.storage.record_sitting_minute()
                if self.sedentary.should_alert():
                    self.alerter.notify("sedentary", "severe")
                    self.storage.record("sedentary", "severe", 1.0, "")

            time.sleep(self.config.sample_interval)


def main():
    app = App()
    controller = TrayController(
        on_start=app.start,
        on_pause=app.pause,
        on_exit=app.exit,
    )
    controller.run()


if __name__ == "__main__":
    main()
