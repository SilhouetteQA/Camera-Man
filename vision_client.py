import os
import time
import json
import urllib.request
from config import AppConfig


class VisionClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self._api_key = os.environ.get("minmax_api", "")
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

        prompt = (
            "分析这张图片中人物的坐姿。请判断是否存在以下问题:"
            "驼背(肩膀前倾)、前倾(上半身向前倾斜)、歪头(头部向一侧倾斜)。"
            "返回 JSON 格式: {\"slouch\": bool, \"lean_forward\": bool, "
            "\"head_tilt\": bool, \"person_present\": bool, \"confidence\": float}"
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
