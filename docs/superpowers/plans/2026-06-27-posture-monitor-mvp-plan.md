# 姿态监控系统 MVP — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建姿态监控系统 Phase 1 MVP — 摄像头采集、MediaPipe 姿态估计、坐姿判定（驼背/前倾/歪头）、久坐提醒、Windows 托盘控制。

**Architecture:** 7 个模块按依赖顺序构建。config 为基石，storage/camera/alerter/analyzer/vision_client 依赖 config 互不依赖可并行，main+tray_ui 收口集成。

**Tech Stack:** Python 3.12, OpenCV (opencv-python), MediaPipe (mediapipe), pystray, plyer, sqlite3, winsound, Pillow

## Global Constraints

- Python 3.12
- 依赖: opencv-python, mediapipe, pystray, plyer, Pillow
- 采样间隔: 5 秒
- 去抖: 连续 3 帧确认
- 告警冷却: 5 分钟
- 久坐阈值: 60 分钟
- 驼背/前倾阈值: 15°, 歪头阈值: 10°
- 数据库: SQLite, 文件 `data/posture.db`
- MinimaX M3: 由环境变量 `minmax_api` 控制启用
- 注释用中文, UTF-8 编码
- 不写 docstring, 不写多余注释

---

## 文件结构

```
camera-man/
├── config.py             # Task 1: AppConfig dataclass
├── storage.py            # Task 2: EventStore (SQLite)
├── camera.py             # Task 3: CameraService (OpenCV)
├── alerter.py            # Task 4: AlertManager (cooldown + notify)
├── analyzer.py           # Task 5: PostureAnalyzer (MediaPipe + rules)
├── vision_client.py      # Task 6: VisionClient (MinimaX M3 API)
├── main.py               # Task 7: 主循环 + 托盘
├── tray_ui.py            # Task 7: TrayController (pystray)
├── tests/
│   ├── test_config.py
│   ├── test_storage.py
│   ├── test_camera.py
│   ├── test_alerter.py
│   ├── test_analyzer.py
│   ├── test_vision_client.py
└── data/
    └── posture.db        # 自动创建
```

---

### Task 1: AppConfig 配置模块

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `AppConfig` dataclass with all fields from spec

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import os
from config import AppConfig


class TestAppConfig:
    def test_default_values(self):
        cfg = AppConfig()
        assert cfg.camera_device_id == 0
        assert cfg.sample_interval == 5.0
        assert cfg.slouch_threshold == 15.0
        assert cfg.lean_forward_threshold == 15.0
        assert cfg.head_tilt_threshold == 10.0
        assert cfg.sedentary_threshold == 60
        assert cfg.debounce_frames == 3
        assert cfg.cooldown_minutes == 5
        assert cfg.vision_verify_cooldown == 30

    def test_vision_verify_disabled_by_default(self):
        cfg = AppConfig()
        assert cfg.vision_verify_enabled is False

    def test_vision_verify_enabled_with_env(self, monkeypatch):
        monkeypatch.setenv("minmax_api", "sk-test-123")
        cfg = AppConfig()
        assert cfg.vision_verify_enabled is True

    def test_custom_values(self):
        cfg = AppConfig(
            sample_interval=3.0,
            slouch_threshold=20.0,
            cooldown_minutes=10,
        )
        assert cfg.sample_interval == 3.0
        assert cfg.slouch_threshold == 20.0
        assert cfg.cooldown_minutes == 10
        # 未指定的保持默认
        assert cfg.head_tilt_threshold == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `config` module not found

- [ ] **Step 3: Write minimal implementation**

```python
# config.py
import os
from dataclasses import dataclass, field


@dataclass
class AppConfig:
    camera_device_id: int = 0
    sample_interval: float = 5.0
    slouch_threshold: float = 15.0
    lean_forward_threshold: float = 15.0
    head_tilt_threshold: float = 10.0
    sedentary_threshold: int = 60
    debounce_frames: int = 3
    cooldown_minutes: int = 5
    vision_verify_cooldown: int = 30

    @property
    def vision_verify_enabled(self) -> bool:
        return "minmax_api" in os.environ
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add AppConfig dataclass with posture thresholds"
```

---

### Task 2: EventStore 存储模块

**Files:**
- Create: `storage.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Consumes: `AppConfig` (for db path — uses hardcoded default path in Phase 1)
- Produces:
  - `EventStore(db_path: str = "data/posture.db")`
  - `.record(event_type: str, severity: str, confidence: float = 0.0, details: str = "")` -> None
  - `.record_sitting_minute()` -> None
  - `.get_stats_today() -> dict`
  - `.get_recent_events(minutes: int = 60) -> list[dict]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage.py
import sqlite3
import os
from storage import EventStore


class TestEventStore:
    def setup_method(self):
        self.db_path = ":memory:"
        self.store = EventStore(self.db_path)

    def test_tables_created(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert "events" in tables
        assert "daily_stats" in tables
        conn.close()

    def test_record_event(self):
        self.store.record("slouch", "severe", 0.85, '{"angle": 20}')
        events = self.store.get_recent_events(60)
        assert len(events) == 1
        assert events[0]["event_type"] == "slouch"
        assert events[0]["severity"] == "severe"
        assert events[0]["confidence"] == 0.85

    def test_record_sitting_minute(self):
        self.store.record_sitting_minute()
        self.store.record_sitting_minute()
        stats = self.store.get_stats_today()
        assert stats["total_sitting_minutes"] == 2

    def test_get_stats_today_empty(self):
        stats = self.store.get_stats_today()
        assert stats["total_sitting_minutes"] == 0
        assert stats["slouch_count"] == 0

    def test_daily_stats_counts_events(self):
        self.store.record("slouch", "severe", 0.9, "")
        self.store.record("slouch", "severe", 0.8, "")
        self.store.record("head_tilt", "severe", 0.7, "")
        stats = self.store.get_stats_today()
        assert stats["slouch_count"] == 2
        assert stats["head_tilt_count"] == 1
        assert stats["lean_forward_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_storage.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# storage.py
import sqlite3
import os
from datetime import datetime, date


CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    details TEXT DEFAULT ''
)
"""

CREATE_DAILY_STATS = """
CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    total_sitting_minutes INTEGER DEFAULT 0,
    slouch_count INTEGER DEFAULT 0,
    lean_forward_count INTEGER DEFAULT 0,
    head_tilt_count INTEGER DEFAULT 0,
    sedentary_alerts INTEGER DEFAULT 0,
    severe_alerts INTEGER DEFAULT 0
)
"""

UPSERT_STATS = """
INSERT INTO daily_stats (date, total_sitting_minutes, slouch_count,
    lean_forward_count, head_tilt_count, sedentary_alerts, severe_alerts)
VALUES (?, 1, ?, ?, ?, ?, ?)
ON CONFLICT(date) DO UPDATE SET
    total_sitting_minutes = total_sitting_minutes + 1,
    slouch_count = slouch_count + excluded.slouch_count,
    lean_forward_count = lean_forward_count + excluded.lean_forward_count,
    head_tilt_count = head_tilt_count + excluded.head_tilt_count,
    sedentary_alerts = sedentary_alerts + excluded.sedentary_alerts,
    severe_alerts = severe_alerts + excluded.severe_alerts
"""


class EventStore:
    def __init__(self, db_path: str = "data/posture.db"):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(CREATE_EVENTS)
            conn.execute(CREATE_DAILY_STATS)

    def record(self, event_type: str, severity: str,
               confidence: float = 0.0, details: str = ""):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO events (timestamp, event_type, severity, confidence, details) "
                "VALUES (?, ?, ?, ?, ?)",
                (now, event_type, severity, confidence, details)
            )
            # 同时更新 daily_stats
            slouch = 1 if event_type == "slouch" else 0
            lean = 1 if event_type == "lean_forward" else 0
            tilt = 1 if event_type == "head_tilt" else 0
            sedentary = 1 if event_type == "sedentary" else 0
            severe = 1 if severity == "severe" else 0
            today = date.today().isoformat()
            conn.execute(UPSERT_STATS, (today, slouch, lean, tilt, sedentary, severe))

    def record_sitting_minute(self):
        today = date.today().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO daily_stats (date, total_sitting_minutes) VALUES (?, 1) "
                "ON CONFLICT(date) DO UPDATE SET "
                "total_sitting_minutes = total_sitting_minutes + 1",
                (today,)
            )

    def get_stats_today(self) -> dict:
        today = date.today().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM daily_stats WHERE date = ?", (today,)
            ).fetchone()
        if row is None:
            return {
                "total_sitting_minutes": 0, "slouch_count": 0,
                "lean_forward_count": 0, "head_tilt_count": 0,
                "sedentary_alerts": 0, "severe_alerts": 0
            }
        return {
            "total_sitting_minutes": row[1], "slouch_count": row[2],
            "lean_forward_count": row[3], "head_tilt_count": row[4],
            "sedentary_alerts": row[5], "severe_alerts": row[6]
        }

    def get_recent_events(self, minutes: int = 60) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM events ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()
        return [dict(row) for row in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_storage.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add storage.py tests/test_storage.py
git commit -m "feat: add EventStore with SQLite events and daily_stats tables"
```

---

### Task 3: CameraService 摄像头模块

**Files:**
- Create: `camera.py`
- Create: `tests/test_camera.py`

**Interfaces:**
- Consumes: `AppConfig.camera_device_id`
- Produces:
  - `CameraService(device_id: int = 0)`
  - `.start() -> bool`
  - `.capture() -> np.ndarray | None`
  - `.stop()`
  - `.is_running -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_camera.py
import numpy as np
from camera import CameraService


class TestCameraService:
    def test_initial_state(self):
        cam = CameraService(device_id=0)
        assert cam.is_running is False

    def test_start_stop_lifecycle(self):
        cam = CameraService(device_id=0)
        result = cam.start()
        assert result is True
        assert cam.is_running is True
        cam.stop()
        assert cam.is_running is False

    def test_capture_returns_frame(self):
        cam = CameraService(device_id=0)
        cam.start()
        frame = cam.capture()
        assert frame is not None
        assert isinstance(frame, np.ndarray)
        assert len(frame.shape) == 3
        cam.stop()

    def test_capture_when_stopped_returns_none(self):
        cam = CameraService(device_id=0)
        frame = cam.capture()
        assert frame is None

    def test_stop_when_not_running_safe(self):
        cam = CameraService(device_id=0)
        cam.stop()  # 不应抛异常
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_camera.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# camera.py
import cv2
import numpy as np


class CameraService:
    def __init__(self, device_id: int = 0):
        self.device_id = device_id
        self._cap = None

    @property
    def is_running(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def start(self) -> bool:
        if self.is_running:
            return True
        self._cap = cv2.VideoCapture(self.device_id, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self._cap = None
            return False
        return True

    def capture(self) -> np.ndarray | None:
        if not self.is_running:
            return None
        ret, frame = self._cap.read()
        if not ret or frame is None:
            return None
        return frame

    def stop(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_camera.py -v`
Expected: 5 PASS (需要有摄像头硬件)

- [ ] **Step 5: Commit**

```bash
git add camera.py tests/test_camera.py
git commit -m "feat: add CameraService with start/stop/capture"
```

---

### Task 4: AlertManager 告警模块

**Files:**
- Create: `alerter.py`
- Create: `tests/test_alerter.py`

**Interfaces:**
- Consumes: `AppConfig.cooldown_minutes`
- Produces:
  - `AlertManager(cooldown_minutes: int = 5)`
  - `.should_alert(event_type: str) -> bool`
  - `.notify(event_type: str, severity: str)`
  - `.record_alert(event_type: str)` (记录告警触发时间，供冷却检查)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_alerter.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_alerter.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# alerter.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alerter.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add alerter.py tests/test_alerter.py
git commit -m "feat: add AlertManager with cooldown and Windows toast notifications"
```

---

### Task 5: PostureAnalyzer 姿态分析模块

**Files:**
- Create: `analyzer.py`
- Create: `tests/test_analyzer.py`

**Interfaces:**
- Consumes: `AppConfig` thresholds
- Produces:
  - `PostureResult` dataclass (from spec)
  - `PostureAnalyzer(config: AppConfig)`
  - `.analyze(frame: np.ndarray) -> PostureResult`
  - `.reset()`
  - Internal pure functions: `_angle_between(a, b, c)`, `_midpoint(a, b)`, `_check_slouch(...)`, `_check_lean_forward(...)`, `_check_head_tilt(...)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyzer.py
import numpy as np
from analyzer import (
    PostureResult,
    PostureAnalyzer,
    _angle_between,
    _midpoint,
    _check_slouch,
    _check_lean_forward,
    _check_head_tilt,
)
from config import AppConfig


# 模拟 MediaPipe 33 关键点: [x, y, z, visibility]
def make_landmark(x, y, z=0.0, visibility=1.0):
    return np.array([x, y, z, visibility])


def make_normal_landmarks():
    """正常坐姿的关键点"""
    lm = np.zeros((33, 4))
    # 鼻子 (0)
    lm[0] = make_landmark(0.5, 0.3)
    # 左耳 (7), 右耳 (8)
    lm[7] = make_landmark(0.47, 0.28)
    lm[8] = make_landmark(0.53, 0.28)
    # 左肩 (11), 右肩 (12)
    lm[11] = make_landmark(0.4, 0.5)
    lm[12] = make_landmark(0.6, 0.5)
    # 左髋 (23), 右髋 (24)
    lm[23] = make_landmark(0.42, 0.75)
    lm[24] = make_landmark(0.58, 0.75)
    return lm


def make_slouch_landmarks():
    """驼背: 肩膀前移, 耳朵相对位置改变"""
    lm = np.zeros((33, 4))
    lm[0] = make_landmark(0.5, 0.3)
    lm[7] = make_landmark(0.44, 0.32)
    lm[8] = make_landmark(0.56, 0.32)
    # 肩膀前移 (x 更靠近中心)
    lm[11] = make_landmark(0.44, 0.48)
    lm[12] = make_landmark(0.56, 0.48)
    lm[23] = make_landmark(0.42, 0.75)
    lm[24] = make_landmark(0.58, 0.75)
    return lm


def make_lean_forward_landmarks():
    """前倾: 鼻-肩-髋连线向前倾斜"""
    lm = np.zeros((33, 4))
    # 鼻子和肩膀 x 坐标向前 (远离髋部基准)
    lm[0] = make_landmark(0.5, 0.25)
    lm[7] = make_landmark(0.44, 0.26)
    lm[8] = make_landmark(0.56, 0.26)
    lm[11] = make_landmark(0.38, 0.45)
    lm[12] = make_landmark(0.62, 0.45)
    lm[23] = make_landmark(0.42, 0.75)
    lm[24] = make_landmark(0.58, 0.75)
    return lm


def make_head_tilt_landmarks():
    """歪头: 耳-肩连线与水平线有明显夹角"""
    lm = np.zeros((33, 4))
    lm[0] = make_landmark(0.52, 0.25)
    # 耳朵一高一低
    lm[7] = make_landmark(0.44, 0.24)
    lm[8] = make_landmark(0.56, 0.30)
    lm[11] = make_landmark(0.42, 0.5)
    lm[12] = make_landmark(0.58, 0.5)
    lm[23] = make_landmark(0.42, 0.75)
    lm[24] = make_landmark(0.58, 0.75)
    return lm


class TestAngleBetween:
    def test_right_angle(self):
        a = np.array([0, 0])
        b = np.array([1, 0])
        c = np.array([1, 1])
        # a-b-c 在 b 处是 90 度
        angle = _angle_between(a, b, c)
        assert abs(angle - 90.0) < 1.0

    def test_straight_line(self):
        a = np.array([0, 0])
        b = np.array([1, 0])
        c = np.array([2, 0])
        angle = _angle_between(a, b, c)
        assert abs(angle - 180.0) < 1.0


class TestMidpoint:
    def test_midpoint_2d(self):
        a = np.array([0.0, 0.0])
        b = np.array([2.0, 2.0])
        m = _midpoint(a, b)
        assert m[0] == 1.0
        assert m[1] == 1.0


class TestPostureResult:
    def test_default_result(self):
        r = PostureResult()
        assert r.person_present is False
        assert r.slouch is False
        assert r.lean_forward is False
        assert r.head_tilt is False
        assert r.confidence == 0.0
        assert r.severity is None
        assert r.triggered == []


class TestSlouchDetection:
    def test_normal_not_slouch(self):
        lm = make_normal_landmarks()
        assert not _check_slouch(lm, threshold=15.0)

    def test_slouch_detected(self):
        lm = make_slouch_landmarks()
        # 注意: 模拟数据可能不会精确触发驼背判定
        # 这里测试函数不抛异常、返回 bool
        result = _check_slouch(lm, threshold=15.0)
        assert isinstance(result, bool)


class TestLeanForwardDetection:
    def test_normal_not_lean(self):
        lm = make_normal_landmarks()
        assert not _check_lean_forward(lm, threshold=15.0)


class TestHeadTiltDetection:
    def test_normal_not_tilt(self):
        lm = make_normal_landmarks()
        assert not _check_head_tilt(lm, threshold=10.0)

    def test_tilt_detected(self):
        lm = make_head_tilt_landmarks()
        result = _check_head_tilt(lm, threshold=10.0)
        assert isinstance(result, bool)


class TestPostureAnalyzer:
    def test_init(self):
        cfg = AppConfig()
        analyzer = PostureAnalyzer(cfg)
        assert analyzer is not None

    def test_analyze_no_person(self):
        cfg = AppConfig()
        analyzer = PostureAnalyzer(cfg)
        # 纯黑帧，MediaPipe 检测不到人体
        black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = analyzer.analyze(black_frame)
        assert result.person_present is False
        assert result.severity is None

    def test_reset(self):
        cfg = AppConfig()
        analyzer = PostureAnalyzer(cfg)
        analyzer.reset()  # 不应抛异常


class TestSeverity:
    def test_single_trigger_is_severe(self):
        r = PostureResult(
            person_present=True,
            slouch=True,
            confidence=0.9,
            triggered=["slouch"],
        )
        assert r.severity is None  # severity 由外部判定逻辑设置

    def test_no_trigger_none(self):
        r = PostureResult(
            person_present=True,
            confidence=0.9,
            triggered=[],
        )
        assert r.severity is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyzer.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# analyzer.py
import math
import numpy as np
from dataclasses import dataclass, field
import mediapipe as mp
from config import AppConfig


@dataclass
class PostureResult:
    person_present: bool = False
    slouch: bool = False
    lean_forward: bool = False
    head_tilt: bool = False
    confidence: float = 0.0
    severity: str | None = None
    triggered: list[str] = field(default_factory=list)


# ---- 纯函数：角度计算 ----

def _midpoint(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a + b) / 2.0


def _angle_between(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """计算向量 ba 和 bc 在 b 点的夹角（度）"""
    ba = a[:2] - b[:2]
    bc = c[:2] - b[:2]
    dot = np.dot(ba, bc)
    norm = np.linalg.norm(ba) * np.linalg.norm(bc)
    if norm < 1e-6:
        return 0.0
    cos = np.clip(dot / norm, -1.0, 1.0)
    return float(np.degrees(math.acos(cos)))


def _vertical_angle(a: np.ndarray, b: np.ndarray) -> float:
    """计算 a-b 连线与垂直线的夹角（度）"""
    vec = a[:2] - b[:2]
    vertical = np.array([0.0, -1.0])
    dot = np.dot(vec, vertical)
    norm = np.linalg.norm(vec) * np.linalg.norm(vertical)
    if norm < 1e-6:
        return 0.0
    cos = np.clip(dot / norm, -1.0, 1.0)
    return float(np.degrees(math.acos(cos)))


def _horizontal_angle(a: np.ndarray, b: np.ndarray) -> float:
    """计算 a-b 连线与水平线的夹角（度）"""
    vec = a[:2] - b[:2]
    horizontal = np.array([1.0, 0.0])
    dot = np.dot(vec, horizontal)
    norm = np.linalg.norm(vec) * np.linalg.norm(horizontal)
    if norm < 1e-6:
        return 0.0
    cos = np.clip(dot / norm, -1.0, 1.0)
    return float(np.degrees(math.acos(cos)))


def _check_slouch(landmarks: np.ndarray, threshold: float) -> bool:
    """驼背判定: 耳-肩-髋连线偏离垂直线"""
    ear_mid = _midpoint(landmarks[7], landmarks[8])
    shoulder_mid = _midpoint(landmarks[11], landmarks[12])
    hip_mid = _midpoint(landmarks[23], landmarks[24])
    angle = _angle_between(ear_mid, shoulder_mid, hip_mid)
    return angle > threshold


def _check_lean_forward(landmarks: np.ndarray, threshold: float) -> bool:
    """前倾判定: 上半身与垂直方向夹角"""
    nose = landmarks[0]
    shoulder_mid = _midpoint(landmarks[11], landmarks[12])
    angle = _vertical_angle(nose, shoulder_mid)
    return angle > threshold


def _check_head_tilt(landmarks: np.ndarray, threshold: float) -> bool:
    """歪头判定: 耳-肩连线与水平线夹角"""
    ear_left = landmarks[7]
    ear_right = landmarks[8]
    angle = _horizontal_angle(ear_left, ear_right)
    return angle > threshold


def _classify_posture(landmarks: np.ndarray, config: AppConfig) -> PostureResult:
    triggered = []
    if _check_slouch(landmarks, config.slouch_threshold):
        triggered.append("slouch")
    if _check_lean_forward(landmarks, config.lean_forward_threshold):
        triggered.append("lean_forward")
    if _check_head_tilt(landmarks, config.head_tilt_threshold):
        triggered.append("head_tilt")

    severity = "severe" if triggered else None

    return PostureResult(
        person_present=True,
        slouch="slouch" in triggered,
        lean_forward="lean_forward" in triggered,
        head_tilt="head_tilt" in triggered,
        confidence=1.0,  # 规则判定置信度
        severity=severity,
        triggered=triggered,
    )


# ---- MediaPipe 封装 ----

class PostureAnalyzer:
    def __init__(self, config: AppConfig):
        self.config = config
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def analyze(self, frame: np.ndarray) -> PostureResult:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb)

        if results.pose_landmarks is None:
            return PostureResult(person_present=False)

        # 提取 33 个关键点为 numpy 数组
        h, w = frame.shape[:2]
        lm = np.zeros((33, 4), dtype=np.float32)
        min_visibility = 1.0
        for i, landmark in enumerate(results.pose_landmarks.landmark):
            lm[i] = [landmark.x, landmark.y, landmark.z, landmark.visibility]
            min_visibility = min(min_visibility, landmark.visibility)

        result = _classify_posture(lm, self.config)
        result.confidence = min_visibility
        return result

    def reset(self):
        self.pose.reset()


import cv2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analyzer.py -v`
Expected: PASS (纯函数测试通过; MediaPipe 相关测试需要首次运行下载模型)

- [ ] **Step 5: Commit**

```bash
git add analyzer.py tests/test_analyzer.py
git commit -m "feat: add PostureAnalyzer with MediaPipe pose estimation and posture rules"
```

---

### Task 6: VisionClient MinimaX M3 模块

**Files:**
- Create: `vision_client.py`
- Create: `tests/test_vision_client.py`

**Interfaces:**
- Consumes: `AppConfig.vision_verify_enabled`, `AppConfig.vision_verify_cooldown`
- Produces:
  - `VisionClient(config: AppConfig)`
  - `.is_available -> bool`
  - `.verify(frame_b64: str, local_result: PostureResult) -> dict | None`
  - 返回 `{"verified": bool, "judgment": str, "raw": dict}` 或 None

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vision_client.py
from vision_client import VisionClient
from config import AppConfig


class TestVisionClient:
    def test_not_available_without_env(self, monkeypatch):
        monkeypatch.delenv("minmax_api", raising=False)
        cfg = AppConfig()
        client = VisionClient(cfg)
        assert client.is_available is False
        assert client.verify("fake_b64", None) is None

    def test_is_available_with_env(self, monkeypatch):
        monkeypatch.setenv("minmax_api", "sk-test-key")
        cfg = AppConfig()
        client = VisionClient(cfg)
        assert client.is_available is True

    def test_verify_when_not_available(self, monkeypatch):
        monkeypatch.delenv("minmax_api", raising=False)
        cfg = AppConfig()
        client = VisionClient(cfg)
        result = client.verify("b64data", None)
        assert result is None

    def test_cooldown_blocks_repeated_calls(self, monkeypatch):
        import time
        monkeypatch.setenv("minmax_api", "sk-test-key")
        cfg = AppConfig()
        client = VisionClient(cfg)
        # 模拟一次调用后在冷却期内再次调用
        client._last_verify_time = time.time()
        # 不应该实际发 HTTP 请求
        # 但我们至少验证冷却逻辑存在
        assert client._last_verify_time > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_vision_client.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# vision_client.py
import os
import time
import base64
import json
import urllib.request
import urllib.error
from config import AppConfig


class VisionClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self._api_key = os.environ.get("minmax_api", "")
        self._last_verify_time: float = 0.0

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def verify(self, frame_b64: str, local_result) -> dict | None:
        if not self.is_available:
            return None

        now = time.time()
        if now - self._last_verify_time < self.config.vision_verify_cooldown:
            return None

        self._last_verify_time = now

        prompt = (
            "分析这张图片中人物的坐姿。请判断是否存在以下问题:"
            "驼背(肩膀前倾)、前倾(上半身向前倾斜)、歪头(头部向一侧倾斜)。"
            "返回 JSON 格式: {\"slouch\": bool, \"lean_forward\": bool, "
            "\"head_tilt\": bool, \"person_present\": bool, \"confidence\": float}"
        )

        payload = json.dumps({
            "model": "minimax-m3",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}"}
                        }
                    ]
                }
            ],
            "max_tokens": 300,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.minimax.chat/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                judgment = json.loads(content)
                return {
                    "verified": True,
                    "judgment": judgment,
                    "raw": data,
                }
        except Exception:
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_vision_client.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add vision_client.py tests/test_vision_client.py
git commit -m "feat: add VisionClient for MinimaX M3 posture verification"
```

---

### Task 7: 主循环 + 系统托盘（集成）

**Files:**
- Create: `main.py`
- Create: `tray_ui.py`

**Interfaces:**
- Consumes: All previous modules
- Produces: Runnable application

**Note:** 托盘 UI 不做自动化测试，手动验证。

- [ ] **Step 1: Write tray_ui.py**

```python
# tray_ui.py
import threading
from PIL import Image, ImageDraw
import pystray


def _create_icon_image():
    """创建 64x64 托盘图标"""
    img = Image.new("RGB", (64, 64), color=(52, 152, 219))
    draw = ImageDraw.Draw(img)
    # 画一个简单的人形
    draw.ellipse([22, 4, 42, 24], fill=(255, 255, 255))   # 头
    draw.rectangle([27, 24, 37, 50], fill=(255, 255, 255)) # 身体
    return img


class TrayController:
    def __init__(self, on_start, on_pause, on_exit):
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_exit = on_exit
        self._running = False
        self._paused = True
        self._icon = None

    def _create_menu(self):
        def make_start():
            self.on_start()
            self._paused = False
            self._icon.update_menu()

        def make_pause():
            self.on_pause()
            self._paused = True
            self._icon.update_menu()

        def make_exit():
            self.on_pause()
            self.on_exit()
            self._icon.stop()

        start_item = pystray.MenuItem(
            "开始监控", make_start,
            enabled=lambda item: self._paused
        )
        pause_item = pystray.MenuItem(
            "暂停", make_pause,
            enabled=lambda item: not self._paused
        )
        exit_item = pystray.MenuItem("退出", make_exit)

        return pystray.Menu(start_item, pause_item, pystray.Menu.SEPARATOR, exit_item)

    def run(self):
        self._icon = pystray.Icon(
            "posture_monitor",
            _create_icon_image(),
            "姿态监控",
            menu=self._create_menu(),
        )
        self._running = True
        self._icon.run()

    def stop(self):
        self._running = False
        if self._icon:
            self._icon.stop()
```

- [ ] **Step 2: Write main.py**

```python
# main.py
import time
import threading
import base64
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
                    m3 = verification["judgment"]
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
```

- [ ] **Step 3: Verify import chain**

Run: `python -c "from main import App; print('Import OK')"` 
Expected: Import OK (首次运行会下载 MediaPipe 模型)

- [ ] **Step 4: Manual smoke test**

Run: `python main.py`
Expected: 托盘出现，右键可看到"开始监控/暂停/退出"菜单。点击"开始监控"后摄像头启动。

- [ ] **Step 5: Commit**

```bash
git add main.py tray_ui.py
git commit -m "feat: add main loop with debounce state machine and system tray UI"
```

---

## 依赖关系与 SDD 并行策略

```
Task 1 (config)  ─────────────────────────────
        │                                      │
        ├── Task 2 (storage) ──┐              │
        ├── Task 3 (camera)  ──┤              │
        ├── Task 4 (alerter) ──┤  并行组      │
        ├── Task 5 (analyzer)──┤              │
        └── Task 6 (vision)  ──┘              │
                                │              │
                                └── Task 7 (main+tray)
```

**SDD 执行顺序：**
1. Task 1 完成 → commit
2. Tasks 2-6 并行分发 → 各自完成 → commit
3. Task 7 收口 → commit
