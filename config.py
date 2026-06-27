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
