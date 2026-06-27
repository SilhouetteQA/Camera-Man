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
