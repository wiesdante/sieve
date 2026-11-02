"""Regenerate ``assets/icon.png`` and ``assets/icon.ico``.

Usage: python scripts/generate_icon.py   (requires Pillow)
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SIZE = 1024
TOP = (124, 108, 242)
BOTTOM = (64, 196, 214)


def _gradient(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            pixels[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM, strict=True))
    return image


def build() -> Image.Image:
    scale = 4  # draw large, downsample for smooth edges
    big = SIZE * scale // 4
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=255)
    canvas.paste(_gradient(big), (0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    cx = cy = big / 2
    radius = big * 0.30
    rim = big * 0.045
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline="white", width=round(rim))

    # Mesh of dots inside the rim.
    inner = radius - rim * 2.2
    step = big * 0.075
    dot = big * 0.018
    count = math.ceil(inner / step)
    for i in range(-count, count + 1):
        for j in range(-count, count + 1):
            x, y = cx + i * step, cy + j * step
            if math.hypot(x - cx, y - cy) <= inner:
                draw.ellipse((x - dot, y - dot, x + dot, y + dot), fill=(255, 255, 255, 235))

    # Handle.
    angle = math.radians(45)
    start = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
    end = (cx + radius * 1.45 * math.cos(angle), cy + radius * 1.45 * math.sin(angle))
    draw.line((start, end), fill="white", width=round(rim * 1.2))
    draw.ellipse(
        (end[0] - rim * 0.6, end[1] - rim * 0.6, end[0] + rim * 0.6, end[1] + rim * 0.6),
        fill="white",
    )
    return canvas.resize((256, 256), Image.Resampling.LANCZOS)


def main() -> None:
    icon = build()
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    icon.save(assets / "icon.png")
    icon.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Wrote icons to {assets}")


if __name__ == "__main__":
    main()
