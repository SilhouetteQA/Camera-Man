import math
import os
import urllib.request
import cv2
import numpy as np
from dataclasses import dataclass, field
import mediapipe as mp
from mediapipe.tasks.python.vision import PoseLandmarker
from config import AppConfig


# 姿势检测模型下载地址（lite 版本）
_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"


def _get_model_path() -> str:
    """获取模型文件路径，首次运行时自动下载"""
    cache_dir = os.path.join(os.path.dirname(__file__), ".mediapipe_models")
    model_path = os.path.join(cache_dir, "pose_landmarker_lite.task")
    if not os.path.exists(model_path):
        os.makedirs(cache_dir, exist_ok=True)
        urllib.request.urlretrieve(_MODEL_URL, model_path)
    return model_path


@dataclass
class PostureResult:
    person_present: bool = False
    slouch: bool = False
    lean_forward: bool = False
    head_tilt: bool = False
    phone_use: bool = False
    confidence: float = 0.0
    severity: str | None = None
    triggered: list[str] = field(default_factory=list)


# ---- 纯函数：角度计算 ----

def _midpoint(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a + b) / 2.0


def _angle_between(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """计算向量 ba 和 bc 在 b 点的夹角（度）"""
    ba = a[:2] - b[:2]
    bc = c[:2] - b[:2]
    dot = np.dot(ba, bc)
    norm = np.linalg.norm(ba) * np.linalg.norm(bc)
    if norm < 1e-6:
        return 0.0
    cos = np.clip(dot / norm, -1.0, 1.0)
    return float(np.degrees(math.acos(cos)))


def _vertical_angle(a: np.ndarray, b: np.ndarray) -> float:
    """计算 a-b 连线与垂直线的夹角（度）"""
    vec = a[:2] - b[:2]
    vertical = np.array([0.0, -1.0])
    dot = np.dot(vec, vertical)
    norm = np.linalg.norm(vec) * np.linalg.norm(vertical)
    if norm < 1e-6:
        return 0.0
    cos = np.clip(dot / norm, -1.0, 1.0)
    return float(np.degrees(math.acos(cos)))


def _horizontal_angle(a: np.ndarray, b: np.ndarray) -> float:
    """计算 a-b 连线与水平线的夹角（度）"""
    vec = a[:2] - b[:2]
    horizontal = np.array([1.0, 0.0])
    dot = np.dot(vec, horizontal)
    norm = np.linalg.norm(vec) * np.linalg.norm(horizontal)
    if norm < 1e-6:
        return 0.0
    cos = np.clip(dot / norm, -1.0, 1.0)
    return float(np.degrees(math.acos(cos)))


def _check_slouch(landmarks: np.ndarray, threshold: float) -> bool:
    """驼背判定: 耳-肩-髋连线偏离垂直线"""
    ear_mid = _midpoint(landmarks[7], landmarks[8])
    shoulder_mid = _midpoint(landmarks[11], landmarks[12])
    hip_mid = _midpoint(landmarks[23], landmarks[24])
    # 计算三点连线的夹角，正常直立时接近 180 度
    angle = _angle_between(ear_mid, shoulder_mid, hip_mid)
    deviation = abs(180.0 - angle)
    return deviation > threshold


def _check_lean_forward(landmarks: np.ndarray, threshold: float) -> bool:
    """前倾判定: 上半身与垂直方向夹角"""
    nose = landmarks[0]
    shoulder_mid = _midpoint(landmarks[11], landmarks[12])
    angle = _vertical_angle(nose, shoulder_mid)
    return angle > threshold


def _check_head_tilt(landmarks: np.ndarray, threshold: float) -> bool:
    """歪头判定: 两耳连线与水平线夹角"""
    ear_left = landmarks[7]
    ear_right = landmarks[8]
    angle = _horizontal_angle(ear_left, ear_right)
    # 归一化到 [0, 90] 范围，表示与水平线的偏离程度
    if angle > 90.0:
        angle = 180.0 - angle
    return angle > threshold


def _check_phone_use(landmarks: np.ndarray) -> bool:
    """手机使用判定: 头部明显下倾，鼻子大幅偏离正常位置靠近肩膀"""
    nose = landmarks[0]
    shoulder_mid = _midpoint(landmarks[11], landmarks[12])

    # 鼻子与肩膀的垂直距离: 正常看屏幕时约 0.30，低头看手机时明显缩小
    nose_to_shoulder = shoulder_mid[1] - nose[1]
    return nose_to_shoulder < 0.22


def _classify_posture(landmarks: np.ndarray, config: AppConfig) -> PostureResult:
    triggered = []
    if _check_slouch(landmarks, config.slouch_threshold):
        triggered.append("slouch")
    if _check_lean_forward(landmarks, config.lean_forward_threshold):
        triggered.append("lean_forward")
    if _check_head_tilt(landmarks, config.head_tilt_threshold):
        triggered.append("head_tilt")
    if _check_phone_use(landmarks):
        triggered.append("phone_use")

    severity = "severe" if triggered else None

    return PostureResult(
        person_present=True,
        slouch="slouch" in triggered,
        lean_forward="lean_forward" in triggered,
        head_tilt="head_tilt" in triggered,
        phone_use="phone_use" in triggered,
        confidence=1.0,  # 规则判定置信度
        severity=severity,
        triggered=triggered,
    )


# ---- MediaPipe 封装 ----

class PostureAnalyzer:
    def __init__(self, config: AppConfig):
        self.config = config
        model_path = _get_model_path()
        self.detector = PoseLandmarker.create_from_model_path(model_path)

    def analyze(self, frame: np.ndarray) -> PostureResult:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = self.detector.detect(mp_image)

        if not results.pose_landmarks:
            return PostureResult(person_present=False)

        # 提取 33 个关键点为 numpy 数组
        lm = np.zeros((33, 4), dtype=np.float32)
        min_visibility = 1.0
        for i, landmark in enumerate(results.pose_landmarks[0]):
            lm[i] = [landmark.x, landmark.y, landmark.z, landmark.visibility]
            min_visibility = min(min_visibility, landmark.visibility)

        result = _classify_posture(lm, self.config)
        result.confidence = min_visibility
        return result

    def reset(self):
        # PoseLandmarker 使用 IMAGE 模式，无状态，无需重置
        pass
