"""Generate the Ally Optimizer app icon (ROG red/black).

Draws a dark rounded-square badge with a bold ROG-red power/optimise bolt and
an angular accent slash, then writes a multi-size .ico (for the Windows exe and
tray) plus a .png preview. Run: ``python tools/make_icon.py``.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

BG_TOP = (24, 24, 28)
BG_BOTTOM = (8, 8, 10)
RED = (255, 20, 33)
RED_DARK = (180, 10, 22)
EDGE = (44, 44, 52)


def _rounded_mask(size: int, radius_frac: float = 0.22) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    r = int(size * radius_frac)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    return mask


def _vertical_gradient(size: int, top, bottom) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        grad.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return grad.resize((size, size))


def _bolt_points(size: int):
    """A bold lightning bolt, coordinates scaled to the icon size."""
    s = size
    return [
        (0.56 * s, 0.12 * s),
        (0.30 * s, 0.56 * s),
        (0.47 * s, 0.56 * s),
        (0.42 * s, 0.88 * s),
        (0.70 * s, 0.42 * s),
        (0.52 * s, 0.42 * s),
    ]


def render(size: int) -> Image.Image:
    base = _vertical_gradient(size, BG_TOP, BG_BOTTOM).convert("RGBA")
    draw = ImageDraw.Draw(base)

    # Angular ROG-style accent slash in the lower-right.
    draw.polygon(
        [(0.62 * size, size), (0.78 * size, size),
         (size, 0.78 * size), (size, 0.62 * size)],
        fill=RED_DARK + (90,),
    )

    # Bolt with a subtle dark drop for depth.
    off = max(1, size // 64)
    draw.polygon([(x + off, y + off) for x, y in _bolt_points(size)], fill=(0, 0, 0, 160))
    draw.polygon(_bolt_points(size), fill=RED)

    # Inner edge highlight.
    r = int(size * 0.22)
    draw.rounded_rectangle([1, 1, size - 2, size - 2], radius=r, outline=EDGE, width=max(1, size // 64))

    base.putalpha(_rounded_mask(size))
    return base


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [render(s) for s in sizes]
    ico_path = os.path.join(OUT_DIR, "allyoptimizer.ico")
    imgs[-1].save(ico_path, format="ICO",
                  sizes=[(s, s) for s in sizes])
    png_path = os.path.join(OUT_DIR, "allyoptimizer.png")
    render(256).save(png_path, format="PNG")
    print(f"wrote {ico_path}\nwrote {png_path}")


if __name__ == "__main__":
    main()
