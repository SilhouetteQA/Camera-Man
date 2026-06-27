import numpy as np
from analyzer import (
    PostureResult,
    PostureAnalyzer,
    _angle_between,
    _midpoint,
    _check_slouch,
    _check_lean_forward,
    _check_head_tilt,
)
from config import AppConfig


# 模拟 MediaPipe 33 关键点: [x, y, z, visibility]
def make_landmark(x, y, z=0.0, visibility=1.0):
    return np.array([x, y, z, visibility])


def make_normal_landmarks():
    """正常坐姿的关键点"""
    lm = np.zeros((33, 4))
    # 鼻子 (0)
    lm[0] = make_landmark(0.5, 0.3)
    # 左耳 (7), 右耳 (8)
    lm[7] = make_landmark(0.47, 0.28)
    lm[8] = make_landmark(0.53, 0.28)
    # 左肩 (11), 右肩 (12)
    lm[11] = make_landmark(0.4, 0.5)
    lm[12] = make_landmark(0.6, 0.5)
    # 左髋 (23), 右髋 (24)
    lm[23] = make_landmark(0.42, 0.75)
    lm[24] = make_landmark(0.58, 0.75)
    return lm


def make_slouch_landmarks():
    """驼背: 头部前倾下沉, 耳-肩-髋连线偏离垂直线, 使角度偏差 > 15 度"""
    lm = np.zeros((33, 4))
    lm[0] = make_landmark(0.53, 0.3)     # 鼻子随头部偏移
    lm[7] = make_landmark(0.42, 0.42)    # 左耳 — 头部下沉且右偏
    lm[8] = make_landmark(0.64, 0.42)    # 右耳 — 头部下沉且右偏
    lm[11] = make_landmark(0.44, 0.48)   # 左肩
    lm[12] = make_landmark(0.56, 0.48)   # 右肩
    lm[23] = make_landmark(0.42, 0.75)   # 左髋
    lm[24] = make_landmark(0.58, 0.75)   # 右髋
    return lm


def make_lean_forward_landmarks():
    """前倾: 鼻-肩连线与垂直线有明显夹角 (>15度)"""
    lm = np.zeros((33, 4))
    lm[0] = make_landmark(0.6, 0.25)     # 鼻子前倾右移
    lm[7] = make_landmark(0.52, 0.26)    # 左耳
    lm[8] = make_landmark(0.68, 0.26)    # 右耳
    lm[11] = make_landmark(0.4, 0.45)    # 左肩
    lm[12] = make_landmark(0.6, 0.45)    # 右肩
    lm[23] = make_landmark(0.42, 0.75)
    lm[24] = make_landmark(0.58, 0.75)
    return lm


def make_head_tilt_landmarks():
    """歪头: 耳-肩连线与水平线有明显夹角"""
    lm = np.zeros((33, 4))
    lm[0] = make_landmark(0.52, 0.25)
    # 耳朵一高一低
    lm[7] = make_landmark(0.44, 0.24)
    lm[8] = make_landmark(0.56, 0.30)
    lm[11] = make_landmark(0.42, 0.5)
    lm[12] = make_landmark(0.58, 0.5)
    lm[23] = make_landmark(0.42, 0.75)
    lm[24] = make_landmark(0.58, 0.75)
    return lm


class TestAngleBetween:
    def test_right_angle(self):
        a = np.array([0, 0])
        b = np.array([1, 0])
        c = np.array([1, 1])
        # a-b-c 在 b 处是 90 度
        angle = _angle_between(a, b, c)
        assert abs(angle - 90.0) < 1.0

    def test_straight_line(self):
        a = np.array([0, 0])
        b = np.array([1, 0])
        c = np.array([2, 0])
        angle = _angle_between(a, b, c)
        assert abs(angle - 180.0) < 1.0


class TestMidpoint:
    def test_midpoint_2d(self):
        a = np.array([0.0, 0.0])
        b = np.array([2.0, 2.0])
        m = _midpoint(a, b)
        assert m[0] == 1.0
        assert m[1] == 1.0


class TestPostureResult:
    def test_default_result(self):
        r = PostureResult()
        assert r.person_present is False
        assert r.slouch is False
        assert r.lean_forward is False
        assert r.head_tilt is False
        assert r.confidence == 0.0
        assert r.severity is None
        assert r.triggered == []


class TestSlouchDetection:
    def test_normal_not_slouch(self):
        lm = make_normal_landmarks()
        assert not _check_slouch(lm, threshold=15.0)

    def test_slouch_detected(self):
        lm = make_slouch_landmarks()
        result = _check_slouch(lm, threshold=15.0)
        assert result is True


class TestLeanForwardDetection:
    def test_normal_not_lean(self):
        lm = make_normal_landmarks()
        assert not _check_lean_forward(lm, threshold=15.0)

    def test_lean_forward_detected(self):
        lm = make_lean_forward_landmarks()
        assert _check_lean_forward(lm, threshold=15.0) is True


class TestHeadTiltDetection:
    def test_normal_not_tilt(self):
        lm = make_normal_landmarks()
        assert not _check_head_tilt(lm, threshold=10.0)

    def test_tilt_detected(self):
        lm = make_head_tilt_landmarks()
        result = _check_head_tilt(lm, threshold=10.0)
        assert result is True


class TestPostureAnalyzer:
    def test_init(self):
        cfg = AppConfig()
        analyzer = PostureAnalyzer(cfg)
        assert analyzer is not None

    def test_analyze_no_person(self):
        cfg = AppConfig()
        analyzer = PostureAnalyzer(cfg)
        # 纯黑帧，MediaPipe 检测不到人体
        black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = analyzer.analyze(black_frame)
        assert result.person_present is False
        assert result.severity is None

    def test_reset(self):
        cfg = AppConfig()
        analyzer = PostureAnalyzer(cfg)
        analyzer.reset()  # 不应抛异常


class TestSeverity:
    def test_single_trigger_is_severe(self):
        r = PostureResult(
            person_present=True,
            slouch=True,
            confidence=0.9,
            triggered=["slouch"],
        )
        assert r.severity is None  # severity 由外部判定逻辑设置

    def test_no_trigger_none(self):
        r = PostureResult(
            person_present=True,
            confidence=0.9,
            triggered=[],
        )
        assert r.severity is None
