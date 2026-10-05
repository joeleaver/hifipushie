"""The flat pattern as a pattern maker lays it out on the table: every piece at one scale, named, with its role, size,
grain arrow, notches, buttons/buttonholes, internal lines, fold lines (dashed blue, with angle and kind),
interfacing (hatched), and every seam in its own colour with its number on both sides (S3a / S3b), so a seam's
two edges can be matched by eye. A 10 cm scale bar; the seam list underneath. Stage 2 of the clothing workflow
(look_pattern)."""
from __future__ import annotations

import colorsys
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import garment_design, pattern

ROLE_TINT = {"front": (232, 240, 250), "back": (236, 244, 236), "yoke": (244, 238, 228), "sleeve": (248, 236, 240),
             "cuff": (250, 244, 220), "collar_stand": (250, 230, 220), "collar_fall": (252, 222, 210),
             "waistband": (250, 244, 220), "skirt_front": (232, 240, 250), "skirt_back": (236, 244, 236)}


def _font(px: int):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def _seam_colour(i: int, n: int) -> tuple:
    r, g, b = colorsys.hsv_to_rgb((i * 0.61803) % 1.0, 0.85, 0.85)
    return int(r * 255), int(g * 255), int(b * 255)


def _dashed(d: ImageDraw.ImageDraw, pts, fill, width=2, dash=10, gap=6):
    pts = [np.asarray(p, float) for p in pts]
    acc, on = 0.0, True
    for a, b in zip(pts[:-1], pts[1:]):
        L = float(np.linalg.norm(b - a))
        if L < 1e-9:
            continue
        t = 0.0
        while t < L:
            seg = (dash if on else gap) - acc
            t1 = min(L, t + seg)
            if on:
                d.line([tuple(a + (b - a) * t / L), tuple(a + (b - a) * t1 / L)], fill=fill, width=width)
            acc += t1 - t
            if acc >= (dash if on else gap) - 1e-9:
                acc, on = 0.0, not on
            t = t1


def _layout(pcs: dict, width_m: float, margin: float = 0.04):
    """Shelf packing, tallest first: {name: (dx, dy)} offsets (pattern -> sheet metres) and the sheet's size."""
    boxes = []
    for nm, pc in pcs.items():
        P = pc["P"]
        boxes.append((nm, P.min(0), np.ptp(P, 0)))
    boxes.sort(key=lambda b: -b[2][1])
    x = y = margin
    row_h = 0.0
    off = {}
    W = max(width_m, max(b[2][0] for b in boxes) + 2 * margin)
    for nm, lo, sz in boxes:
        if x + sz[0] + margin > W and x > margin:
            x = margin
            y += row_h + margin + 0.03
            row_h = 0.0
        off[nm] = (x - lo[0], y - lo[1], sz)
        x += sz[0] + margin
        row_h = max(row_h, sz[1])
    return off, W, y + row_h + margin + 0.03


def render(Bp: dict, title: str = "", px_per_m: float = 900.0, width_m: float = 1.9, seam_rows=None,
           notes: list | None = None) -> Image.Image:
    """The pattern sheet. seam_rows: cloth_check rows (ease, flags) to print in the seam list."""
    pcs = Bp["pieces"]
    off, W, H = _layout(pcs, width_m)
    list_h = 22 * (len(Bp["seams"]) + 3 + len(notes or [])) + 40
    S = px_per_m
    img = Image.new("RGB", (int(W * S), int(H * S) + list_h + 40), (255, 255, 255))
    d = ImageDraw.Draw(img, "RGBA")
    f_big, f_mid, f_small = _font(18), _font(14), _font(12)
    Hpx = int(H * S) + 40

    def tp(nm, q):  # pattern point of a piece -> image px (y flipped: pattern y up)
        dx, dy, sz = off[nm]
        q = np.asarray(q, float)
        x = (q[..., 0] + dx) * S
        y = Hpx - (q[..., 1] + dy) * S
        return np.stack([x, y], -1)

    d.text((10, 8), title, fill=(0, 0, 0), font=f_big)
    # pieces: fill, interfacing hatch, outline
    inter = {}
    for e in Bp["interfaced"]:
        inter.setdefault(e if isinstance(e, str) else e["piece"], []).append(e)
    for nm, pc in pcs.items():
        role = garment_design.role_of(nm, pc)
        poly = [tuple(p) for p in tp(nm, pc["P"])]
        d.polygon(poly, fill=ROLE_TINT.get(role, (242, 242, 242)))
        for e in inter.get(nm, []):  # hatch: diagonal lines inside the piece (whole) or near a line (band)
            P = pc["P"]
            lo, hi = P.min(0), P.max(0)
            step = 0.012
            from .cloth import _inside, _seg_dist
            ref = None
            if not isinstance(e, str):
                r_ = e["near"]
                if isinstance(r_, str) and r_ not in (pc.get("lines") or {}):
                    ref = np.asarray([pc["P"][pattern.index_of(pc, r_)] if r_ in pc["names"] else pc["marks"][r_]], float)
                else:
                    ref = np.asarray(pattern._line(pc, r_), float)
            for c0 in np.arange(lo[0] - (hi[1] - lo[1]), hi[0], step):
                t = np.linspace(0, 1, 120)[:, None]
                Q = np.c_[c0 + t[:, 0] * (hi[1] - lo[1]), lo[1] + t[:, 0] * (hi[1] - lo[1])]
                ok = _inside(P, Q)
                if ref is not None:
                    w = float(e.get("within", 0.02))
                    dd = np.linalg.norm(Q - ref[0], axis=1) if len(ref) == 1 else _seg_dist(Q, ref, closed=False)
                    ok &= dd < w
                if ok.sum() < 2:
                    continue
                # draw the inside runs
                run = []
                for q, k in zip(Q, ok):
                    if k:
                        run.append(q)
                    elif len(run) > 1:
                        d.line([tuple(p) for p in tp(nm, np.array(run))], fill=(150, 120, 60, 110), width=1)
                        run = []
                    else:
                        run = []
                if len(run) > 1:
                    d.line([tuple(p) for p in tp(nm, np.array(run))], fill=(150, 120, 60, 110), width=1)
        for k, L in (pc.get("lines") or {}).items():  # the draft's internal lines (chest, waist, placket folds...)
            _dashed(d, tp(nm, np.asarray(L)), fill=(170, 170, 170), width=1, dash=4, gap=4)
        d.line(poly + [poly[0]], fill=(30, 30, 30), width=2)
    # seams: each its colour, label at the middle of each side's edges
    for si, (A, B) in enumerate(Bp["seams"]):
        col = _seam_colour(si, len(Bp["seams"]))
        for lab, side in (("a", A), ("b", B)):
            for e in ([side] if isinstance(side, str) else side):
                nm, arc = e.split(":", 1)
                if nm not in pcs:
                    continue
                L = pcs[nm]["P"][pattern.arc_indices(pcs[nm], arc)]
                pts = tp(nm, L)
                d.line([tuple(p) for p in pts], fill=col + (230,), width=5)
                m = pts[len(pts) // 2]
                c = tp(nm, pcs[nm]["P"].mean(0))
                v = c - m
                v = v / (np.linalg.norm(v) + 1e-9) * 16
                d.text(tuple(m + v - [10, 7]), f"S{si + 1}{lab}", fill=col, font=f_small)
    # fold lines
    for f in Bp.get("folds") or []:
        try:
            Q = garment_design.fold_polyline(pcs, f)
        except Exception as ex:  # drawn as a note: the sheet must still render
            d.text((10, 30), f"fold {f} unresolved: {ex}", fill=(200, 0, 0), font=f_small)
            continue
        pts = tp(f["piece"], Q)
        _dashed(d, pts, fill=(20, 60, 220), width=3, dash=12, gap=5)
        d.text(tuple(pts[0] + [4, -16]), f"fold {f.get('angle')}° {f.get('kind', 'press')}", fill=(20, 60, 220), font=f_small)
    for nm, pc in pcs.items():  # the old placement fold (wrap.fold: rise, layer): where the U starts
        w = pc.get("wrap") or {}
        if w.get("fold") and not any(f.get("piece") == nm for f in Bp.get("folds") or []):
            from .cloth import _fold_line
            # the sewn edge offset by the rise: drawn from _fold_line's first row (it needs the seams only)
            try:
                FL = _fold_line(Bp, nm, 0.01)
                if FL is not None:
                    n3 = len(FL) // 3
                    _dashed(d, tp(nm, FL[:n3]), fill=(20, 60, 220), width=2, dash=4, gap=4)
                    d.text(tuple(tp(nm, FL[0]) + [4, -16]), f"placed fold (U {w['fold']})", fill=(20, 60, 220), font=f_small)
            except Exception:
                pass
    # marks: notches (ticks), buttons (circles), buttonholes (slots)
    for nm, pc in pcs.items():
        for k, v in pc["marks"].items():
            v = np.asarray(v, float)
            if len(v) != 2:
                continue
            p = tp(nm, v)
            kl = k.lower()
            if "notch" in kl:
                d.line([tuple(p - [0, 6]), tuple(p + [0, 6])], fill=(220, 0, 0), width=2)
                d.line([tuple(p - [6, 0]), tuple(p + [6, 0])], fill=(220, 0, 0), width=2)
            elif "buttonhole" in kl:
                d.rectangle([tuple(p - [3, 8]), tuple(p + [3, 8])], outline=(60, 60, 60), width=2)
            elif "button" in kl:
                d.ellipse([tuple(p - 6), tuple(p + 6)], outline=(60, 60, 60), width=2)
    # per piece: name, role, size, grain, where it goes
    for nm, pc in pcs.items():
        P = pc["P"]
        c = tp(nm, 0.5 * (P.min(0) + P.max(0)))
        sz = np.ptp(P, 0) * 1000
        role = garment_design.role_of(nm, pc)
        w = pc.get("wrap") or {}
        g = math.radians(float(pc.get("grain", 90)))
        L = min(0.35 * min(np.ptp(P, 0).max(), 0.3), 0.12) * S
        u = np.array([math.cos(g), -math.sin(g)]) * L / 2
        d.line([tuple(c - u), tuple(c + u)], fill=(90, 90, 90), width=2)
        for s in (-1, 1):  # arrow heads
            tip = c + s * u
            perp = np.array([-u[1], u[0]]) / (np.linalg.norm(u) + 1e-9) * 6
            d.line([tuple(tip), tuple(tip - s * u / np.linalg.norm(u) * 10 + perp)], fill=(90, 90, 90), width=2)
            d.line([tuple(tip), tuple(tip - s * u / np.linalg.norm(u) * 10 - perp)], fill=(90, 90, 90), width=2)
        txt = f"{nm}  [{role}]\n{sz[0]:.0f} x {sz[1]:.0f} mm\n-> {w.get('to', 'torso')}" + (
            f" {w.get('side')}" if w.get("side") else "") + (f" @{w['level']}" if w.get("level") else "") + (
            f" out {w['out'] * 1000:.0f}mm" if w.get("out") else "")
        d.multiline_text(tuple(c + [8, 6]), txt, fill=(0, 0, 0), font=f_mid, spacing=2)
    # scale bar
    y0 = Hpx - 18
    d.line([(20, y0), (20 + 0.1 * S, y0)], fill=(0, 0, 0), width=3)
    d.text((24 + 0.1 * S, y0 - 9), "10 cm", fill=(0, 0, 0), font=f_small)
    # seam list
    y = Hpx + 6
    d.text((10, y), "seams (both sides sewn by fraction of their length: ease spreads evenly; '!!' outside its band)",
           fill=(0, 0, 0), font=f_mid)
    y += 22
    rows = {i: r for i, r in enumerate(seam_rows or [])}
    for si, (A, B) in enumerate(Bp["seams"]):
        col = _seam_colour(si, len(Bp["seams"]))
        nm_ = lambda s: s if isinstance(s, str) else " + ".join(s)
        r = rows.get(si)
        extra = ""
        if r is not None:
            extra = f"  {'!! ' if not r['ok'] or r['notches_off'] else ''}{r['kind']} {r['len_a_mm']:.0f}/{r['len_b_mm']:.0f} mm " \
                    f"ease {r['ease'] * 100:+.1f}%"
        d.text((10, y), f"S{si + 1}: {nm_(A)}  ||  {nm_(B)}{extra}", fill=col, font=f_small)
        y += 18
    for ln in notes or []:
        d.text((10, y), ln, fill=(0, 0, 0), font=f_small)
        y += 18
    return img
