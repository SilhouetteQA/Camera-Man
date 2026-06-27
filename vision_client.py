import os
import time
import json
import urllib.request
from config import AppConfig


class VisionClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self._api_key = os.environ.get("minimax_api", "")
        self._last_verify_time: float = 0.0

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def verify(self, frame_b64: str, local_result) -> dict | None:
        if not self.config.vision_verify_enabled:
            return None

        if not self.is_available:
            return None

        now = time.time()
        if now - self._last_verify_time < self.config.vision_verify_cooldown:
            return None

        self._last_verify_time = now

        # 将本地判定结果传给 M3，让它做二次确认
        local_info = ""
        if local_result is not None and local_result.person_present:
            parts = []
            if local_result.slouch:
                parts.append("驼背=是")
            if local_result.lean_forward:
                parts.append("前倾=是")
            if local_result.head_tilt:
                parts.append("歪头=是")
            if parts:
                local_info = f"本地算法判定: {', '.join(parts)}。"
            else:
                local_info = "本地算法判定: 坐姿正常。"

        prompt = (
            f"你是一个坐姿检测助手。请仔细观察图片中人物的坐姿。{local_info}"
            "请根据你的观察独立判断，确认或纠正本地算法的判定。参考标准:"
            "驼背 = 肩膀明显前移、上背部弯曲呈弧形、头部前伸;"
            "前倾 = 整个上半身向前大幅倾斜;"
            "歪头 = 头部向一侧明显歪斜。"
            "返回 JSON 格式: {\"slouch\": bool, \"lean_forward\": bool, "
            "\"head_tilt\": bool, \"person_present\": bool}"
        )

        payload = json.dumps({
            "model": "minimax-m3",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}"}
                        }
                    ]
                }
            ],
            "max_tokens": 300,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.minimax.chat/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                return {
                    "verified": True,
                    "judgment": content,
                    "raw": data,
                }
        except Exception:
            return None
