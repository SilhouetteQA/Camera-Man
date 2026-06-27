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
        self.stop()  # 释放可能存在的旧句柄（如摄像头断开后的残留）
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
