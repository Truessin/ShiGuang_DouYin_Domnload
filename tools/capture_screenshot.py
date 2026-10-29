r"""Render the README screenshot with demo data. No network access.

Usage:
    .\.venv\Scripts\python.exe tools\capture_screenshot.py
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6 import QtGui, QtWidgets  # noqa: E402

import app  # noqa: E402
from core import Asset, Post  # noqa: E402


def load_fonts():
    for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf"):
        path = Path(r"C:\Windows\Fonts") / name
        if path.is_file():
            QtGui.QFontDatabase.addApplicationFont(str(path))


def main():
    qt = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    load_fonts()
    qt.setStyle("Fusion")
    window = app.Window()
    window.resize(1020, 820)

    demo_folder = r"D:\Downloads\拾光"
    window.destination = Path(demo_folder)
    window.folder.setText(demo_folder)
    window.text.setPlainText(
        "3.28 复制打开抖音，看看【示例作者】的作品 https://v.douyin.com/EXAMPLE/ "
        "复制此链接，打开抖音搜索，直接观看视频！"
    )

    post = Post(
        "7000000000000000000",
        "海边落日 · 胶片练习",
        "示例作者",
        "图集",
        [Asset(i, "image", ["https://example.invalid/demo"], 2660, 2160, label=f"图片 {i:03d}") for i in range(1, 9)],
        page_url="https://www.douyin.com/note/7000000000000000000",
    )
    window.on_message({"kind": "post", "key": 0, "post": post})

    window.log.appendPlainText("读取分享链接…")
    window.log.appendPlainText("作品完成：8 个文件，保存至 7000000000000000000_海边落日 · 胶片练习")

    for i in range(1, 9):
        window.on_message(
            {
                "kind": "progress",
                "key": 0,
                "index": i,
                "received": 58000 if i <= 6 else 21000,
                "total": 58000,
                "overall": 1000,
            }
        )

    for i in range(1, 7):
        window.on_message(
            {"kind": "file", "key": 0, "index": i, "state": "done", "path": rf"{demo_folder}\7000000000000000000_海边落日 · 胶片练习\{i:03d}.webp"}
        )
    window.on_message({"kind": "progress", "key": 0, "index": 7, "received": 21000, "total": 58000, "overall": 860})
    window.on_message({"kind": "file", "key": 0, "index": 7, "state": "downloading", "path": ""})
    window.on_message({"kind": "file", "key": 0, "index": 8, "state": "downloading", "path": ""})

    window.progress.setValue(860)
    window.status.setText("图集 · 8 个文件 · 海边落日 · 胶片练习（示例数据，未联网）")

    qt.processEvents()

    target = ROOT / "docs" / "images" / "main-window.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(target))
    print(f"saved {target} ({target.stat().st_size} bytes)")
    window.close()


if __name__ == "__main__":
    main()
