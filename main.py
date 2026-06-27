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
        all_types = ["slouch", "lean_forward", "head_tilt", "phone_use"]

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


class PhoneTimer:
    """手机使用计时器"""
    def __init__(self, config: AppConfig):
        self.threshold_minutes = config.phone_use_threshold
        self.minutes = 0
        self.alerted = False

    def tick(self, phone_use: bool):
        if phone_use:
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
            self._loop_thread.join(timeout=1.0)
        self.camera.stop()
        self.analyzer.reset()
        # 此时 _loop 已退出, 安全重置计时器
        self.sedentary.minutes = 0
        self.sedentary.alerted = False
        self.phone_timer.minutes = 0
        self.phone_timer.alerted = False

    def toggle_vision(self):
        self.config.vision_verify_enabled = not self.config.vision_verify_enabled

    def exit(self):
        # camera.stop() 由 pause() 负责, 此处无需重复调用
        self._running = False

    def _parse_m3_judgment(self, content) -> dict:
        """解析 M3 返回内容（可能包含 <think> 标签），提取 JSON"""
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            # 处理 <think>...</think> 包裹的情况
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()
            # 尝试找到第一个 JSON 对象
            brace = content.find("{")
            if brace >= 0:
                try:
                    return json.loads(content[brace:])
                except (json.JSONDecodeError, TypeError):
                    pass
        return {}

    def _loop(self):
        try:
            minute_counter = 0
            while self._running:
                frame = self.camera.capture()
                if frame is None:
                    time.sleep(0.5)
                    continue

                result = self.analyzer.analyze(frame)

                # MinimaX M3 二次验证（需同时满足：用户启用 + API Key 存在）
                if self.config.vision_verify_enabled and self.vision.is_available and result.person_present:
                    _, buf = cv2.imencode(".jpg", frame)
                    frame_b64 = base64.b64encode(buf).decode("utf-8")
                    verification = self.vision.verify(frame_b64, result)
                    if verification:
                        m3_raw = verification["judgment"]
                        m3 = self._parse_m3_judgment(m3_raw)
                        # 调试: 打印本地 vs M3 对比
                        print(f"[M3] 本地={result.slouch}/{result.lean_forward}/{result.head_tilt} "
                              f"M3={m3.get('slouch','?')}/{m3.get('lean_forward','?')}/{m3.get('head_tilt','?')}")
                        # M3 二次确认: 本地检测项需要 M3 也确认为 True 才保留
                        for t in ["slouch", "lean_forward", "head_tilt"]:
                            local_val = getattr(result, t)
                            m3_val = m3.get(t, local_val)
                            # 本地和 M3 都认为是 True → 确认；任一为 False → 清除
                            if local_val and not m3_val:
                                setattr(result, t, False)
                                print(f"[M3] {t}: 本地=True M3=False → 清除")
                        result.triggered = [
                            t for t in ["slouch", "lean_forward", "head_tilt"]
                            if getattr(result, t)
                        ]
                        result.severity = "severe" if result.triggered else None
                    else:
                        print(f"[M3] 调用未返回结果 (冷却中或API失败)")

                # 去抖
                confirmed = self.state_machine.update(result)

                for event_type in confirmed:
                    if event_type == "phone_use":
                        continue  # 手机使用走累计计时
                    if self.alerter.should_alert(event_type):
                        self.alerter.notify(event_type, "severe")
                    self.storage.record(event_type, "severe", result.confidence, "")

                # 每分钟计时 (约每 12 帧 = 60 秒, 5 秒采样)
                minute_counter += 1
                if minute_counter >= 12:
                    minute_counter = 0
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
    # 用可变容器共享 vision 启用状态，供托盘菜单 checked 回调读取
    vision_state = [False]

    def on_toggle_vision():
        app.toggle_vision()
        vision_state[0] = app.config.vision_verify_enabled

    controller = TrayController(
        on_start=app.start,
        on_pause=app.pause,
        on_exit=app.exit,
        on_toggle_vision=on_toggle_vision,
        vision_state=vision_state,
        minmax_available=app.config.minmax_api_available,
    )
    controller.run()


if __name__ == "__main__":
    main()
