"""Artist retopo: contact sheets (PIL): the ROM sheet, the close-ups, the final comparison, any grid of renders."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RED = (200, 0, 0)


def grid(out, paths, cols, tile=400, labels=None, quality=88):
    paths = [Path(p) for p in paths]
    rows = (len(paths) + cols - 1) // cols
    s = Image.new("RGB", (cols * tile, rows * tile), "white"); d = ImageDraw.Draw(s)
    for k, p in enumerate(paths):
        if p.exists():
            s.paste(Image.open(p).convert("RGB").resize((tile, tile)), ((k % cols) * tile, (k // cols) * tile))
        if labels:
            d.text(((k % cols) * tile + 6, (k // cols) * tile + 6), labels[k], fill=RED)
    s.save(out, quality=quality)
    return out


def rom_sheet(d: Path, names):
    """every pose, front + 3/4, 4 poses a row"""
    T = 260; rows = (len(names) + 3) // 4
    s = Image.new("RGB", (T * 8, T * rows), "white"); dr = ImageDraw.Draw(s)
    for k, n in enumerate(names):
        for j, v in enumerate(("front", "3q")):
            p = d / f"rom_{n}_{v}.png"
            if p.exists():
                s.paste(Image.open(p).convert("RGB").resize((T, T)), ((k % 4) * 2 * T + j * T, (k // 4) * T))
        dr.text(((k % 4) * 2 * T + 5, (k // 4) * T + 5), n, fill=RED)
    s.save(d / "rom_sheet.jpg", quality=85)


def close_sheet(d: Path):
    names = ["arms_side_80", "arms_up_150", "arms_forward_90", "elbows_120", "knee_up_100", "crouch"]
    grid(d / "close_rom.jpg", [d / f"close_{n}.png" for n in names], 3, 500, names)
    m = ["rest_mouth_front", "mouth_open_20_front", "mouth_open_20_3q"]
    if (d / "close_mouth_open_20_front.png").exists():
        grid(d / "close_mouth.jpg", [d / f"close_{n}.png" for n in m], 3, 400, m)


def final_cmp(d: Path):
    """the sculpt | the game mesh: whole figure front-3/4 and back on top, the head below"""
    rows = []
    for v in ("body", "head", "back"):
        r = Image.new("RGB", (1000, 500))
        for i, t in enumerate(("high", "final")):
            p = d / f"fin_{v}_{t}.png"
            if p.exists():
                r.paste(Image.open(p).convert("RGB").resize((500, 500)), (i * 500, 0))
        rows.append(r)
    s = Image.new("RGB", (1500, 1000))
    s.paste(rows[0].resize((750, 375)), (0, 0)); s.paste(rows[2].resize((750, 375)), (750, 0))
    s.paste(rows[1].resize((1250, 625)), (125, 375))
    s.save(d / "final_cmp.jpg", quality=90)
