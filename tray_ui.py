# tray_ui.py
from PIL import Image, ImageDraw
import pystray


def _create_icon_image():
    """创建 64x64 托盘图标"""
    img = Image.new("RGB", (64, 64), color=(52, 152, 219))
    draw = ImageDraw.Draw(img)
    # 画一个简单的人形
    draw.ellipse([22, 4, 42, 24], fill=(255, 255, 255))   # 头
    draw.rectangle([27, 24, 37, 50], fill=(255, 255, 255)) # 身体
    return img


class TrayController:
    def __init__(self, on_start, on_pause, on_exit):
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_exit = on_exit
        self._running = False
        self._paused = True
        self._icon = None

    def _create_menu(self):
        def make_start():
            self.on_start()
            self._paused = False
            self._icon.update_menu()

        def make_pause():
            self.on_pause()
            self._paused = True
            self._icon.update_menu()

        def make_exit():
            self.on_pause()
            self.on_exit()
            self._icon.stop()

        start_item = pystray.MenuItem(
            "开始监控", make_start,
            enabled=lambda item: self._paused
        )
        pause_item = pystray.MenuItem(
            "暂停", make_pause,
            enabled=lambda item: not self._paused
        )
        exit_item = pystray.MenuItem("退出", make_exit)

        return pystray.Menu(start_item, pause_item, pystray.Menu.SEPARATOR, exit_item)

    def run(self):
        self._icon = pystray.Icon(
            "posture_monitor",
            _create_icon_image(),
            "姿态监控",
            menu=self._create_menu(),
        )
        self._running = True
        self._icon.run()

    def stop(self):
        self._running = False
        if self._icon:
            self._icon.stop()
