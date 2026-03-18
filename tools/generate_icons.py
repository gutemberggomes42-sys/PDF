from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _load_font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except Exception:
            continue
    return ImageFont.load_default()


def _make_icon(size: int, main_text: str, sub_text: str | None = None, round_mask: bool = False) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = base.load()
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(102 + (118 - 102) * t)
        g = int(126 + (75 - 126) * t)
        b = int(234 + (162 - 234) * t)
        for x in range(size):
            px[x, y] = (r, g, b, 255)

    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    radius = int(size * 0.22)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img = Image.composite(base, img, mask)

    if round_mask:
        m2 = Image.new("L", (size, size), 0)
        d2 = ImageDraw.Draw(m2)
        pad = int(size * 0.06)
        d2.ellipse([pad, pad, size - pad - 1, size - pad - 1], fill=255)
        img = Image.composite(img, Image.new("RGBA", (size, size), (0, 0, 0, 0)), m2.point(lambda v: 255 - v))

    draw = ImageDraw.Draw(img)

    main_font = _load_font(int(size * 0.56))
    mw, mh = draw.textbbox((0, 0), main_text, font=main_font)[2:]
    y_main = int(size * (0.46 - (mh / (2 * size))))
    draw.text(((size - mw) / 2, y_main), main_text, font=main_font, fill=(255, 255, 255, 255))

    if sub_text:
        sub_font = _load_font(int(size * 0.16))
        sw, sh = draw.textbbox((0, 0), sub_text, font=sub_font)[2:]
        y_sub = int(size * 0.72)
        draw.text(((size - sw) / 2, y_sub), sub_text, font=sub_font, fill=(245, 245, 255, 235))

    return img


def _save_png(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path), format="PNG", optimize=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    static_icons = root / "static" / "icons"

    sizes = [72, 96, 128, 144, 152, 192, 384, 512]
    for s in sizes:
        icon = _make_icon(s, "R", None, round_mask=False)
        _save_png(icon, static_icons / f"icon-{s}x{s}.png")

    _save_png(_make_icon(192, "PDF", None, round_mask=False), static_icons / "pdf-icon.png")
    _save_png(_make_icon(192, "LIB", None, round_mask=False), static_icons / "library-icon.png")

    android_res = root / "android_app" / "app" / "src" / "main" / "res"
    mipmaps = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }
    for folder, s in mipmaps.items():
        base = _make_icon(s, "R", None, round_mask=False)
        rnd = _make_icon(s, "R", None, round_mask=True)
        _save_png(base, android_res / folder / "ic_launcher.png")
        _save_png(rnd, android_res / folder / "ic_launcher_round.png")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
