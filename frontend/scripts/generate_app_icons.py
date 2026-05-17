#!/usr/bin/env python3
"""生成 Safari / PWA 主屏幕图标（PNG）。"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent / "public"
SIZES = (180, 192, 512)


def _blend(c1: str, c2: str, t: float) -> tuple:
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return (
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def draw_icon(size: int) -> Image.Image:
    scale = size / 36
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)

    for y in range(size):
        t = y / max(size - 1, 1)
        draw.line([(0, y), (size, y)], fill=_blend("#fffbeb", "#fde68a", t))

    cx = cy = size / 2
    r = 15.5 * scale
    stroke = max(2, int(2 * scale))
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill="#fffbeb",
        outline="#d97706",
        width=stroke,
    )

    # 水面
    water = [
        (cx, 10 * scale),
        (4 * scale, 28 * scale),
        (cx, 24 * scale),
        (32 * scale, 28 * scale),
    ]
    draw.polygon(water, fill="#fde68a")

    # 牛身
    body = [
        14 * scale,
        13 * scale,
        (14 + 8) * scale,
        (13 + 14) * scale,
    ]
    draw.rounded_rectangle(body, radius=int(2 * scale), fill="#d97706")

    # 牛角区域
    horn = [
        (11 * scale, 13 * scale),
        (25 * scale, 13 * scale),
        (23 * scale, 7 * scale),
        (13 * scale, 7 * scale),
    ]
    draw.polygon(horn, fill="#f59e0b")

    # 顶部高光
    hr = 3.5 * scale
    draw.ellipse(
        [cx - hr, 10 * scale - hr, cx + hr, 10 * scale + hr],
        fill="#ffffff",
    )
    draw.ellipse(
        [cx - 2 * scale, 10 * scale - 2 * scale, cx + 2 * scale, 10 * scale + 2 * scale],
        fill="#f59e0b",
    )

    return img


def main():
    icons_dir = ROOT / "icons"
    icons_dir.mkdir(exist_ok=True)

    for size in SIZES:
        icon = draw_icon(size)
        if size == 180:
            icon.save(ROOT / "apple-touch-icon.png", "PNG", optimize=True)
        icon.save(icons_dir / f"icon-{size}.png", "PNG", optimize=True)
        print(f"wrote icon-{size}.png")

    print("done")


if __name__ == "__main__":
    main()
