from config import AppConfig


class TestAppConfig:
    def test_default_values(self):
        cfg = AppConfig()
        assert cfg.camera_device_id == 0
        assert cfg.sample_interval == 5.0
        assert cfg.slouch_threshold == 4.0
        assert cfg.lean_forward_threshold == 15.0
        assert cfg.head_tilt_threshold == 6.0
        assert cfg.sedentary_threshold == 60
        assert cfg.phone_use_threshold == 10
        assert cfg.debounce_frames == 3
        assert cfg.cooldown_minutes == 5
        assert cfg.frames_per_minute == 12
        assert cfg.phone_nose_threshold == 0.39
        assert cfg.phone_grace_minutes == 2
        assert cfg.pause_join_timeout == 1.0

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
        assert cfg.head_tilt_threshold == 6.0
