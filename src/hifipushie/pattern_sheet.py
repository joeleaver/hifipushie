"""The flat pattern as a pattern maker lays it out on the table, drawn for SHAPE (C288: pictures are for shape, text is
for numbers). Every piece at one scale: its outline, grain arrow, notches, buttons/buttonholes, internal lines, fold
lines (dashed blue), interfacing (hatched), ONE large piece name inside the piece (sized down to fit, or left off and
said so in `img.info["names_off"]`), every seam pair in one colour on both its edges, a 10 cm scale bar and a big
legend mapping each colour to its seam's name. No numbers on the image: sizes, cut counts, lengths and ease are in
`text_lines` (every caller puts them in its text answer). Stage 2 of the clothing workflow (look_pattern)."""
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


def offset_outline(P: np.ndarray, dist: float) -> np.ndarray:
    """A closed outline moved `dist` outward (miter joins, clamped at 3x): the cutting line a seam allowance away
    from the sewing line."""
    P = np.asarray(P, float)
    area = 0.5 * float(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))
    s = 1.0 if area > 0 else -1.0  # (counter-clockwise: outward is the edge direction turned clockwise)
    e_in = P - np.roll(P, 1, axis=0)
    e_out = np.roll(P, -1, axis=0) - P

    def nrm(e):
        n = np.c_[e[:, 1], -e[:, 0]] * s
        return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)
    n = nrm(e_in) + nrm(e_out)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    c = np.clip(np.sum(n * nrm(e_out), axis=1), 1.0 / 3.0, 1.0)
    return P + n * (dist / c)[:, None]


NAME_PX = (44, 18)  # a piece name's largest and smallest size (px); smaller than 18 is left off and reported
LEGEND_PX = 24


def _side_name(s) -> str:
    return s if isinstance(s, str) else " + ".join(s)


def seam_names(Bp: dict) -> list:
    """One name per seam (its two sides' edges), the legend's and text_lines' wording."""
    return [f"{_side_name(A)} = {_side_name(B)}" for A, B in Bp.get("seams") or []]


def _role_text(nm: str, pc: dict, d: dict) -> str:
    """The role as the shape rows read it (C379, t s4-9: a stand named "collar" was listed collar_fall while the gate
    checked it as a stand): a name that doesn't say stand or fall, with no role declared, is decided by its seams."""
    from . import draft_shape as ds
    base = nm.rsplit(".", 1)[0] if nm.endswith((".L", ".R")) else nm
    if not (d.get("role") or pc.get("role")) and base.lower() in ds.AMBIGUOUS_NAMES:
        return "stand or fall: its seams decide (the shape rows say which)"
    return garment_design.role_of(nm, pc)


def text_lines(Bp: dict, seam_rows=None, names: list | None = None, decl: dict | None = None) -> list:
    """The sheet's numbers as text (the image carries none): every piece (name, size, cut count, stiff, grain, role)
    and every seam pair (both edges, both lengths, the ease, PASS/FAIL): failing pairs first with their kind and band,
    then each passing pair on one compact line. names: the seams' names (default
    seam_names); decl: draft_pattern's declarations (cut counts, folds)."""
    pcs, stiff = Bp.get("pieces") or {}, {e if isinstance(e, str) else e.get("piece") for e in Bp.get("interfaced") or []}
    dp = (decl or {}).get("pieces") or {}
    out = [f"pieces ({len(pcs)}; sizes are the piece's width x height on the sheet, mm):"]
    for nm, pc in pcs.items():
        sz = np.ptp(np.asarray(pc["P"], float), 0) * 1000
        cut = int(dp.get(nm, {}).get("cut", pc.get("cut", 1)))
        fold = " on fold" if dp.get(nm, {}).get("fold") else ""
        out.append(f"  {nm}: {sz[0]:.0f} x {sz[1]:.0f} mm, cut {cut}{fold}{', stiff' if nm in stiff else ''}, "
                   f"grain {float(pc.get('grain', 90)):.0f} deg, role {_role_text(nm, pc, dp.get(nm, {}))}")
    names = names or seam_names(Bp)
    rows = list(seam_rows or [])
    fail, ok_lines, bare = [], [], []
    for i, nm in enumerate(names):
        r = rows[i] if i < len(rows) else None
        if r is None:
            bare.append(f"  S{i + 1} {nm}")
            continue
        band = r.get("band")
        a, b, e = float(r["len_a_mm"]), float(r["len_b_mm"]), float(r["ease"]) * 100
        if r.get("ok", True) and not r.get("notches_off"):  # (a passing pair: one compact line)
            ok_lines.append(f"  S{i + 1} PASS {nm}: {a:.0f} / {b:.0f} mm, ease {e:+.1f} %")
            continue
        fail.append(f"  S{i + 1} FAIL {nm}: {a:.0f} / {b:.0f} mm, ease {e:+.1f} % ({r.get('kind', '')}"
                    + (f", band {band[0] * 100:+.1f}..{band[1] * 100:+.1f} %" if band else "") + ")"
                    + (f", notches off {r['notches_off']}" if r.get("notches_off") else ""))
    # failing pairs first, with their numbers (Joe, T8): what to fix is at the top
    out.append(f"seams ({len(names)}; S<n> is the n-th colour in the sheet's legend; lengths a / b mm; "
               f"{len(fail)} failing first):")
    return out + fail + ok_lines + bare


def render(Bp: dict, title: str = "", px_per_m: float = 900.0, width_m: float = 1.9, seam_rows=None,
           grid: bool = False, sa: float = 0.0, points=(), names: list | None = None) -> Image.Image:
    """The pattern sheet, shape only. grid: a light 1 cm grid (10 cm lines darker) under the pieces, true scale,
    unnumbered; sa: a seam allowance (m) drawn as the cutting line outside each piece's sewing line (thin dashed);
    points [(piece, name, label)]: named pattern points marked (a dot; the names belong in the text answer);
    names: the seams' names for the legend (default seam_names). seam_rows is accepted for the callers' symmetry and
    not drawn: its numbers go in text_lines. img.info["names_off"]: pieces whose name did not fit inside them."""
    pcs = Bp["pieces"]
    off, W, H = _layout(pcs, width_m)
    names = names or seam_names(Bp)
    f_leg = _font(LEGEND_PX)
    S = px_per_m
    leg_h = (LEGEND_PX + 12) * (len(Bp["seams"]) + 2) + 40
    img = Image.new("RGB", (int(W * S), int(H * S) + 60 + leg_h), (255, 255, 255))
    d = ImageDraw.Draw(img, "RGBA")
    Hpx = int(H * S) + 60
    if grid:  # true scale: 1 cm cells, every 10 cm darker (no numbers: the scale bar gives the scale)
        for i in range(int(W * 100) + 1):
            x = i * S / 100.0
            d.line([(x, 60), (x, Hpx)], fill=(214, 222, 238) if i % 10 == 0 else (242, 245, 250), width=1)
        for j in range(int(H * 100) + 1):
            y = Hpx - j * S / 100.0
            d.line([(0, y), (W * S, y)], fill=(214, 222, 238) if j % 10 == 0 else (242, 245, 250), width=1)

    def tp(nm, q):  # pattern point of a piece -> image px (y flipped: pattern y up)
        dx, dy, sz = off[nm]
        q = np.asarray(q, float)
        x = (q[..., 0] + dx) * S
        y = Hpx - (q[..., 1] + dy) * S
        return np.stack([x, y], -1)

    def pt(nm, px):  # image px -> the piece's pattern point
        dx, dy, sz = off[nm]
        px = np.asarray(px, float)
        return np.stack([px[..., 0] / S - dx, (Hpx - px[..., 1]) / S - dy], -1)

    from .cloth import _inside

    def inside(nm, box, pad=6):  # an image-px box (x0, y0, x1, y1) wholly inside the piece
        x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
        xs, ys = np.linspace(x0, x1, 7), np.linspace(y0, y1, 5)
        Q = np.array([(x, y) for x in xs for y in ys])
        return bool(_inside(np.asarray(pcs[nm]["P"], float), pt(nm, Q)).all())

    d.text((10, 10), title, fill=(0, 0, 0), font=_font(30))
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
            from .cloth import _seg_dist
            ref = None
            if not isinstance(e, str) and "edge" in e:  # (a fused facing's band: along an outline arc)
                ref = np.asarray(pc["P"], float)[pattern.arc_indices(pc, e["edge"])]
            elif not isinstance(e, str):
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
                run = []  # draw the inside runs
                for q, k in zip(Q, ok):
                    if k:
                        run.append(q)
                    elif len(run) > 1:
                        d.line([tuple(p) for p in tp(nm, np.array(run))], fill=(150, 120, 60, 90), width=1)
                        run = []
                    else:
                        run = []
                if len(run) > 1:
                    d.line([tuple(p) for p in tp(nm, np.array(run))], fill=(150, 120, 60, 90), width=1)
        for k, L in (pc.get("lines") or {}).items():  # the draft's internal lines (chest, waist, placket folds...)
            if str(k).startswith("detail:"):  # (a detail's strip as step 7 will place it: draft_marks, C380)
                d.line([tuple(q) for q in tp(nm, np.asarray(L))], fill=(200, 120, 0), width=3)
                continue
            _dashed(d, tp(nm, np.asarray(L)), fill=(170, 170, 170), width=1, dash=4, gap=4)
        d.line(poly + [poly[0]], fill=(30, 30, 30), width=2)
        if sa > 0:  # the cutting line, a seam allowance outside the sewing line
            C = tp(nm, offset_outline(pc["P"], sa))
            _dashed(d, list(C) + [C[0]], fill=(90, 90, 90), width=1, dash=6, gap=4)
    # seams: both edges of a pair in the pair's colour, thick (matched by colour, never by a printed code)
    for si, (A, B) in enumerate(Bp["seams"]):
        col = _seam_colour(si, len(Bp["seams"]))
        for side in (A, B):
            for e in ([side] if isinstance(side, str) else side):
                nm, arc = e.split(":", 1)
                if nm not in pcs:
                    continue
                pts = tp(nm, pcs[nm]["P"][pattern.arc_indices(pcs[nm], arc)])
                d.line([tuple(p) for p in pts], fill=col + (240,), width=8, joint="curve")
    # fold lines (dashed blue; their angle and kind are in the text)
    for f in Bp.get("folds") or []:
        try:
            Q = garment_design.fold_polyline(pcs, f)
        except Exception:  # the sheet must still render (callers report the fold)
            continue
        _dashed(d, tp(f["piece"], Q), fill=(20, 60, 220), width=4, dash=14, gap=6)
    for nm, pc in pcs.items():  # the old placement fold (wrap.fold: rise, layer): where the U starts
        w = pc.get("wrap") or {}
        if w.get("fold") and not any(f.get("piece") == nm for f in Bp.get("folds") or []):
            from .cloth import _fold_line
            try:
                FL = _fold_line(Bp, nm, 0.01)
                if FL is not None:
                    _dashed(d, tp(nm, FL[:len(FL) // 3]), fill=(20, 60, 220), width=3, dash=6, gap=5)
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
                d.line([tuple(p - [0, 8]), tuple(p + [0, 8])], fill=(220, 0, 0), width=3)
                d.line([tuple(p - [8, 0]), tuple(p + [8, 0])], fill=(220, 0, 0), width=3)
            elif "buttonhole" in kl:
                d.rectangle([tuple(p - [4, 10]), tuple(p + [4, 10])], outline=(60, 60, 60), width=2)
            elif kl.startswith("detail:"):  # (a detail's point as step 7 will place it: draft_marks, C380)
                d.ellipse([tuple(p - 5), tuple(p + 5)], fill=(200, 120, 0))
            elif "button" in kl:
                d.ellipse([tuple(p - 7), tuple(p + 7)], outline=(60, 60, 60), width=3)
    for nm, pn, lab in points:  # named pattern points: a dot (the name is the caller's text)
        if nm in pcs and pn in pcs[nm]["names"]:
            p = tp(nm, pcs[nm]["P"][pcs[nm]["names"][pn]])
            d.ellipse([tuple(p - 7), tuple(p + 7)], fill=(200, 40, 140))
    # per piece: ONE large name inside the piece, and the grain arrow beside it
    names_off = []
    for nm, pc in pcs.items():
        P = np.asarray(pc["P"], float)
        c = tp(nm, 0.5 * (P.min(0) + P.max(0)))
        placed = None
        for px in range(NAME_PX[0], NAME_PX[1] - 1, -2):
            f = _font(px)
            x0, y0, x1, y1 = d.textbbox((0, 0), nm, font=f)
            for rot in (False, True) if np.ptp(P[:, 1]) > np.ptp(P[:, 0]) else (False,):  # (a tall piece: upright)
                tw, th = (y1 - y0, x1 - x0) if rot else (x1 - x0, y1 - y0)
                for dy in (0.0, -0.25, 0.25, -0.4, 0.4):
                    cy = c[1] + dy * np.ptp(P[:, 1]) * S
                    box = (c[0] - tw / 2, cy - th / 2, c[0] + tw / 2, cy + th / 2)
                    if inside(nm, box):
                        placed = (box, f, x0, y0, rot)
                        break
                if placed:
                    break
            if placed:
                break
        g = math.radians(float(pc.get("grain", 90)))
        u1 = np.array([math.cos(g), -math.sin(g)])
        ext = float(np.ptp(P @ np.array([math.cos(g), math.sin(g)]))) * S
        u = u1 * min(0.12 * S, 0.35 * min(np.ptp(P, 0).max(), 0.3) * S, 0.7 * ext) / 2
        spots = [c]
        if placed:
            bx = placed[0]
            mid = np.array([0.5 * (bx[0] + bx[2]), 0.5 * (bx[1] + bx[3])])
            spots = [mid - [0.5 * (bx[2] - bx[0]) + 28, 0], mid + [0.5 * (bx[2] - bx[0]) + 28, 0],
                     mid + [0, 0.5 * (bx[3] - bx[1]) + abs(u[1]) + 14], mid - [0, 0.5 * (bx[3] - bx[1]) + abs(u[1]) + 14], c]
        a0 = next((s for s in spots if inside(nm, (min(s[0] - u[0], s[0] + u[0]), min(s[1] - u[1], s[1] + u[1]),
                                                    max(s[0] - u[0], s[0] + u[0]), max(s[1] - u[1], s[1] + u[1])), pad=2)),
                  spots[-1])
        d.line([tuple(a0 - u), tuple(a0 + u)], fill=(70, 70, 70), width=3)
        for s in (-1, 1):  # arrow heads
            tip = a0 + s * u
            n_ = u / (np.linalg.norm(u) + 1e-9)
            perp = np.array([-n_[1], n_[0]]) * 7
            d.line([tuple(tip), tuple(tip - s * n_ * 12 + perp)], fill=(70, 70, 70), width=3)
            d.line([tuple(tip), tuple(tip - s * n_ * 12 - perp)], fill=(70, 70, 70), width=3)
        if placed:
            box, f, x0, y0, rot = placed
            if rot:  # written bottom to top
                m = Image.new("L", (int(box[3] - box[1]) + 2, int(box[2] - box[0]) + 2), 0)
                ImageDraw.Draw(m).text((-x0, -y0), nm, fill=255, font=f)
                m = m.rotate(90, expand=True)
                img.paste((0, 0, 0), (int(box[0]), int(box[1])), m)
            else:
                d.text((box[0] - x0, box[1] - y0), nm, fill=(0, 0, 0), font=f)
        else:
            names_off.append(nm)
    # scale bar (under the pieces, above the legend)
    y0 = Hpx + 26
    d.line([(20, y0), (20 + 0.1 * S, y0)], fill=(0, 0, 0), width=5)
    for x in (20, 20 + 0.1 * S):
        d.line([(x, y0 - 8), (x, y0 + 8)], fill=(0, 0, 0), width=3)
    d.text((30 + 0.1 * S, y0 - 14), "10 cm", fill=(0, 0, 0), font=_font(LEGEND_PX))
    # legend: colour -> seam name (big; no numbers: lengths and ease are in the text answer)
    y = Hpx + 12 + LEGEND_PX + 20
    for si, nm in enumerate(names):
        col = _seam_colour(si, len(Bp["seams"]))
        d.rectangle([(14, y + 4), (64, y + LEGEND_PX)], fill=col)
        t, room = f"S{si + 1}  {nm}", img.width - 90
        while d.textlength(t, font=f_leg) > room and len(t) > 8:  # (cut to the sheet: the full name is in the text)
            t = t[:-4] + "..."
        d.text((76, y), t, fill=(0, 0, 0), font=f_leg)
        y += LEGEND_PX + 12
    img.info["names_off"] = names_off
    return img
