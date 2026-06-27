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
        # 冷却期内调用 verify 应返回 None
        result = client.verify("fake_b64", None)
        assert result is None
