import os
from dataclasses import dataclass


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
    vision_verify_enabled: bool = False  # 托盘菜单手动开关
    vision_verify_cooldown: int = 30

    @property
    def minmax_api_available(self) -> bool:
        """环境变量中是否有 API Key（仅表示可用，不表示启用）"""
        return "minimax_api" in os.environ
