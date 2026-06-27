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
