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
        assert cfg.phone_use_threshold == 20
        assert cfg.debounce_frames == 3
        assert cfg.cooldown_minutes == 5
        assert cfg.vision_verify_enabled is False
        assert cfg.vision_verify_cooldown == 30

    def test_vision_verify_disabled_by_default(self):
        cfg = AppConfig()
        assert cfg.vision_verify_enabled is False

    def test_vision_verify_can_be_toggled(self):
        cfg = AppConfig()
        cfg.vision_verify_enabled = True
        assert cfg.vision_verify_enabled is True
        cfg.vision_verify_enabled = False
        assert cfg.vision_verify_enabled is False

    def test_minmax_api_available_with_env(self, monkeypatch):
        monkeypatch.setenv("minimax_api", "sk-test-123")
        cfg = AppConfig()
        assert cfg.minmax_api_available is True

    def test_minmax_api_not_available_without_env(self, monkeypatch):
        monkeypatch.delenv("minimax_api", raising=False)
        cfg = AppConfig()
        assert cfg.minmax_api_available is False

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
