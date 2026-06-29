from dataclasses import dataclass

# 姿态检测类型 (不含 phone_use, 因为手机使用走独立的累计计时)
BODY_POSTURE_TYPES = ("slouch", "lean_forward", "head_tilt")

# 所有事件类型 (含 phone_use, 供去抖状态机使用)
ALL_EVENT_TYPES = ("slouch", "lean_forward", "head_tilt", "phone_use")


@dataclass
class AppConfig:
    camera_device_id: int = 0
    sample_interval: float = 5.0
    slouch_threshold: float = 4.0
    lean_forward_threshold: float = 15.0
    head_tilt_threshold: float = 6.0
    sedentary_threshold: int = 60
    phone_use_threshold: int = 10
    debounce_frames: int = 3
    cooldown_minutes: int = 5

    # 魔法数字 → 命名常量, 提升可读性
    frames_per_minute: int = 12       # 12 帧 × 5 秒采样 = 60 秒
    phone_nose_threshold: float = 0.39  # 鼻子-肩膀垂直距离的手机使用判定阈值
    phone_grace_minutes: int = 2        # 手机计时器容差期: 连续离开超过此时间才重置
    pause_join_timeout: float = 1.0     # 暂停时等待 daemon 线程退出的超时秒数
