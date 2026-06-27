# 姿态监控系统 MVP — 设计规格

> 2026-06-27 | 版本 v1.0 | 基于可行性方案报告 Phase 1

---

## 1. 需求摘要

| 目标 | 描述 |
|------|------|
| 坐姿检测 | 识别驼背、前倾、歪头 |
| 久坐提醒 | 累计坐姿满 60 分钟触发提醒 |
| 即时反馈 | Windows Toast 弹窗 + 系统默认提示音 |
| 托盘控制 | 系统托盘：启动/暂停/退出 |
| MinimaX 兜底 | 用户自行决定是否接入（环境变量 minmax_api） |

---

## 2. 关键决策

| 决策项 | 选择 |
|--------|------|
| 久坐阈值 | 60 分钟 |
| 提醒策略 | 智能模式：轻度只记录，严重才告警 |
| 严重判定 | 单指标超标即为严重（驼背/前倾 > 15°，歪头 > 10°） |
| 采样间隔 | 5 秒 |
| 提示音 | Windows 系统默认音 |
| 告警冷却 | 同类型 5 分钟 |
| 去抖帧数 | 连续 3 帧确认 |
| 摄像头控制 | 托盘按钮：启动时才开启，暂停时关闭 |

---

## 3. 模块架构

```
main.py                   # 主循环 + 生命周期
├── camera.py             # CameraService — 打开/关闭/抓帧
├── analyzer.py           # PostureAnalyzer — MediaPipe 推理 + 判定
├── vision_client.py      # MinimaX API 封装（可选，按需启用）
├── alerter.py            # AlertManager — 弹窗 + 声音 + 冷却
├── storage.py            # EventStore — SQLite 记录 + 统计
├── config.py             # AppConfig — dataclass 默认值
└── tray_ui.py            # TrayController — 托盘 UI
```

### 3.1 模块接口

```python
# camera.py
class CameraService:
    def start(device_id=0) -> bool
    def capture() -> np.ndarray | None
    def stop()
    @property is_running -> bool

# analyzer.py
class PostureAnalyzer:
    def __init__(config)         # 初始化 MediaPipe
    def analyze(frame) -> PostureResult
    def reset()

@dataclass
class PostureResult:
    person_present: bool
    slouch: bool
    lean_forward: bool
    head_tilt: bool
    confidence: float
    severity: Optional[str]     # "mild" | "severe" | None
    triggered: list[str]        # 触发的不良类型

# alerter.py
class AlertManager:
    def notify(posture_type, severity)        # 弹窗 + 声音
    def should_alert(posture_type) -> bool    # 冷却检查
    @property cooldowns: dict

# storage.py
class EventStore:
    def record(timestamp, event_type, severity, confidence, details)
    def record_sitting_minute()
    def get_stats_today() -> dict
    def get_recent_events(minutes=60) -> list

# config.py
@dataclass
class AppConfig:
    camera_device_id: int = 0
    sample_interval: float = 5.0
    slouch_threshold: float = 15.0      # 度
    lean_forward_threshold: float = 15.0
    head_tilt_threshold: float = 10.0
    sedentary_threshold: int = 60       # 分钟
    debounce_frames: int = 3
    cooldown_minutes: int = 5
    # MinimaX M3 二次验证（可选，用户自行决定是否接入）
    vision_verify_enabled: bool         # 由 minmax_api 环境变量决定
    vision_verify_cooldown: int = 30    # 秒

# tray_ui.py
class TrayController:
    def on_start()  -> 启动 camera + 主循环
    def on_pause()  -> 停止 camera，托盘保持
    def on_exit()   -> 停止 camera + 退出
```

### 3.2 生命周期

```
托盘启动 → camera 关闭（待命状态）
  ├─ "开始" → camera.start() → 主循环运行
  ├─ "暂停" → camera.stop() → 主循环停止
  └─ "退出" → camera.stop() → 退出进程
```

---

## 4. 判定引擎

### 4.1 检测规则

| 检测项 | 关键点 | 判定逻辑 | 阈值 |
|--------|--------|----------|------|
| 驼背 | 耳(7,8) + 肩(11,12) + 髋(23,24) | 耳-肩-髋连线偏离垂直线 | > 15° |
| 前倾 | 鼻(0) + 肩中点 + 髋中点 | 上半身与垂直方向夹角 | > 15° |
| 歪头 | 耳(7,8) + 肩(11,12) | 耳-肩连线与水平线夹角 | > 10° |
| 久坐 | 髋部(23,24) 可见 | 持续检测到人体累计计时 | > 60 min |

### 4.2 智能模式分级

- 任一指标超标 → severity = "severe" → 告警
- 零指标超标 → severity = None → 不告警
- "mild" 保留给 Phase 2 扩展（叠加判定场景）

### 4.3 去抖与冷却

```
逐帧判定：
  triggered → bad_frames += 1, good_frames = 0
  not triggered → good_frames += 1, bad_frames = 0

连续 bad_frames >= 3 → 确认不良状态
确认后查询冷却表：
  - 未冷却 → 弹窗 + 记录 DB
  - 冷却中 → 仅记录 DB，不弹窗

冷却窗口：5 分钟（同类型告警）

连续 good_frames >= 3 → 确认恢复

person_present=False 连续 3 帧：
  → 暂停所有告警、重置久坐计时
```

### 4.4 双路径判定（MinimaX M3 二次验证，可选）

```
frame → MediaPipe Pose → 33 关键点 + 规则判定 → PostureResult(local)

  minmax_api 存在?
    ├─ 是 → frame b64 → MinimaX M3 多模态模型
    │         → 对比 MediaPipe 结果与 M3 判断是否一致
    │         → PostureResult(verified=True/False, m3_judgment=...)
    └─ 否 → PostureResult(verified=None)  纯本地判定
```

- MinimaX M3 仅在用户设置 `minmax_api` 环境变量时启用
- 单次调用超时 5 秒，失败不影响本地结果
- 验证冷却：30 秒内不重复调用
- 用途：二次验证 MediaPipe 判定是否正确，降低误报

---

## 5. 数据存储

### 5.1 表结构

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,       -- 'slouch'|'lean_forward'|'head_tilt'|'sedentary'
    severity TEXT NOT NULL,         -- 'mild'|'severe'
    confidence REAL,
    details TEXT
);

CREATE TABLE daily_stats (
    date TEXT PRIMARY KEY,
    total_sitting_minutes INTEGER,
    slouch_count INTEGER DEFAULT 0,
    lean_forward_count INTEGER DEFAULT 0,
    head_tilt_count INTEGER DEFAULT 0,
    sedentary_alerts INTEGER DEFAULT 0,
    severe_alerts INTEGER DEFAULT 0
);
```

### 5.2 设计决策

- 直接用 sqlite3 标准库，不引入 ORM
- 数据库文件 `data/posture.db`，首次运行自动创建
- daily_stats 通过 UPSERT 更新
- Phase 1 不暴露数据查询 UI

---

## 6. 主循环

```python
while tray_running:
    if not camera.is_running:
        sleep(0.5)
        continue

    frame = camera.capture()
    if frame is None:
        continue

    result = analyzer.analyze(frame)
    state_machine.update(result)

    for event in state_machine.pending_events():
        if alerter.should_alert(event.type):
            alerter.notify(event.type, event.severity)
        storage.record(event)

    sleep(5)  # 采样间隔
```

---

## 7. 测试策略

| 模块 | 测试内容 | 方式 |
|------|----------|------|
| camera.py | 启动/停止/抓帧 | 有摄像头实测 |
| analyzer.py | 给定关键点 → 正确判定 | 离线（静态图片或模拟关键点） |
| alerter.py | 冷却 + 去抖 + 分级 | 纯逻辑，无外部依赖 |
| storage.py | CRUD + 统计 | 内存 SQLite |
| config.py | 默认值完整性 | 纯逻辑 |
| tray_ui.py | 手动验证 | Phase 1 不自动化 |

### 关键测试用例

```
test_person_present              # 人体可见
test_no_person                   # 空画面
test_slouch_detection            # 驼背关键点 → True
test_lean_forward_detection      # 前倾关键点 → True
test_head_tilt_detection         # 歪头关键点 → True
test_normal_posture              # 正常坐姿 → 全部 False
test_severity_single_trigger     # 单指标超标 → severe
test_debounce_3_frames           # 连续 3 帧确认
test_cooldown_5min               # 冷却期间不重复告警
test_person_absent_silence       # 离开后暂停
test_sedentary_60min_trigger     # 60 分钟久坐触发
```

---

## 8. 非目标（Phase 1 明确不做）

- 手机使用检测（Phase 2）
- 配置文件持久化（Phase 2）
- 开机自启动（Phase 2）
- 云端多模态自动调用（用户手动决定是否用 MinimaX）
- 多摄像头支持（Phase 3）
- Android App（Phase 3）
- 每日/每周报告 UI（Phase 3）
