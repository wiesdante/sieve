"""Regenerate ``assets/icon.png`` and ``assets/icon.ico``.

Usage: python scripts/generate_icon.py   (requires Pillow)

Design: a black rounded tile with a phosphor-green sieve ring, a square mesh
inside it and a diagonal handle, with a soft green glow.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SIZE = 1024
TILE_TOP = (10, 22, 10)
TILE_BOTTOM = (2, 6, 2)
RING = (57, 255, 20, 255)
MESH = (190, 255, 180, 235)
GLOW = (57, 255, 20)
ICO_SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]


def _gradient(size: int) -> Image.Image:
    column = Image.new("RGB", (1, 2 * size))
    for y in range(2 * size):
        t = y / (2 * size - 1)
        column.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(TILE_TOP, TILE_BOTTOM, strict=True)))
    # A vertical ramp rotated 45 degrees gives a diagonal gradient.
    ramp = column.resize((2 * size, 2 * size)).rotate(45, resample=Image.Resampling.BICUBIC)
    offset = size // 2
    return ramp.crop((offset, offset, offset + size, offset + size))


def _tile() -> Image.Image:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=int(SIZE * 0.225), fill=255)
    canvas.paste(_gradient(SIZE), (0, 0), mask)
    return canvas


def _glyph() -> Image.Image:
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx = cy = SIZE * 0.45
    radius = SIZE * 0.27
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=RING, width=46)

    inner = radius - 58
    step = 62
    for i in range(-6, 7):
        for j in range(-6, 7):
            x, y = cx + i * step, cy + j * step
            if math.hypot(x - cx, y - cy) <= inner:
                draw.rounded_rectangle((x - 17, y - 17, x + 17, y + 17), radius=6, fill=MESH)

    angle = math.radians(45)
    start = (cx + (radius + 10) * math.cos(angle), cy + (radius + 10) * math.sin(angle))
    end = (cx + (radius + 210) * math.cos(angle), cy + (radius + 210) * math.sin(angle))
    draw.line((start, end), fill=RING, width=58)
    draw.ellipse((end[0] - 29, end[1] - 29, end[0] + 29, end[1] + 29), fill=RING)
    return layer


def _with_shadow(layer: Image.Image) -> Image.Image:
    shadow = Image.new("RGBA", layer.size, (*GLOW, 0))
    shadow.putalpha(layer.split()[3].point(lambda v: min(v, 150)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(30))
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(shadow)
    out.alpha_composite(layer)
    return out


def build() -> Image.Image:
    icon = _tile()
    icon.alpha_composite(_with_shadow(_glyph()))
    return icon


def main() -> None:
    icon = build()
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(assets / "icon.png")
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(assets / "icon.ico", sizes=ICO_SIZES)
    print(f"Wrote icons to {assets}")


if __name__ == "__main__":
    main()
