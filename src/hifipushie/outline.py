"""Extruded outlines and lettering: signs, logos, cut-out letters, cookie-cutter shapes.

A blob `{"shape": "outline", "loops": [[[x, z], ...], ...], "depth": d, "bevel": b, "round": r}` is a flat
outline in its local XZ plane (its front faces -Y, like a prefab), pushed back `depth` along Y (centred on its
`at`). Loops are closed polygons in metres; holes are loops inside loops (nonzero winding, as fonts draw them).
`bevel` cuts a 45-degree chamfer round the front and back edges (a sign's bevel), `round` rounds every edge
(the front and back edges and the outline's convex corners) by that radius. `grow` moves the outline out (or in, < 0)
by that much all round: a trim or a shadow behind a letter is the same letter grown, set back. The distance is exact, so a
bevelled letter meshes with crisp, even edges at any voxel finer than the bevel.

A blob `{"shape": "text", "text": "BRAYNARD", "font": "lilita-one", "height": 0.3, ...}` is set into one
"outline" blob per glyph (`<name>/B#0`, `<name>/R#1`, ...) by `expand_text`, so each letter culls and
re-evaluates on its own. `height` is the cap height in metres; `tracking` adds space between letters (a share of
the height); `align` is "centre" (default), "left" or "right" about `at`; `italic` slants the letters (a shear,
dx per unit of height: 0.15 leans them forward); `arc` lifts the middle letters that much above the end ones
(each letter whole, along a parabola: a gently arched title); `depth`, `bevel`, `round`, `rot`, `op`, `layer`, `part`, `tags`
and any other keys pass to every letter. `font` names a font in fonts/ (FONTS) or is a path to a .ttf / .otf.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

FONT_DIR = Path(__file__).parent / "fonts"
FONTS = {"lilita-one": "LilitaOne-Regular.ttf"}  # SIL Open Font License: fonts/OFL.txt
CURVE_STEP = 0.008  # flattening: a curve is cut into segments about this long, as a share of the cap height
PASS = ("depth", "bevel", "round", "rot", "op", "layer", "part", "tags", "blend", "group", "join", "instance")


# ---------------------------------------------------------------- distance

def _sd2(q: np.ndarray, seg: np.ndarray) -> np.ndarray:
    """Signed distance from points q (m, 2) to the outline made of segments seg (S, 2, 2); < 0 inside."""
    a, d = seg[:, 0], seg[:, 1] - seg[:, 0]
    out = np.empty(len(q))
    step = max(1, 2_000_000 // max(len(seg), 1))
    for s in range(0, len(q), step):
        x = q[s:s + step, None, :] - a[None]                                   # (m, S, 2)
        t = np.clip((x * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-18), 0.0, 1.0)
        dist = np.sqrt(((x - t[..., None] * d) ** 2).sum(-1).min(axis=1))
        cross = d[None, :, 0] * x[..., 1] - d[None, :, 1] * x[..., 0]
        y, ya, yb = q[s:s + step, None, 1], a[None, :, 1], seg[None, :, 1, 1]
        wind = (((ya <= y) & (yb > y) & (cross > 0)).sum(1) - ((yb <= y) & (ya > y) & (cross < 0)).sum(1))
        out[s:s + step] = np.where(wind != 0, -dist, dist)
    return out


def _profile(u: np.ndarray, v: np.ndarray, bevel: float) -> np.ndarray:
    """Exact 2D distance in (u, v) = (outline distance, depth distance) to the quadrant u, v <= 0 with its
    corner cut by the chamfer u + v <= -bevel."""
    if bevel <= 0:
        return np.hypot(np.maximum(u, 0), np.maximum(v, 0)) + np.minimum(np.maximum(u, v), 0)
    inside = np.maximum(np.maximum(u, v), (u + v + bevel) / math.sqrt(2))
    # outside: the nearest of the side face (u = 0, v <= -b), the chamfer (-b, 0)-(0, -b), the front (v = 0, u <= -b)
    side = np.hypot(np.maximum(u, 0), np.maximum(v + bevel, 0))
    front = np.hypot(np.maximum(u + bevel, 0), np.maximum(v, 0))
    t = np.clip((u - v + bevel) / (2 * bevel), 0, 1)                         # along (-b, 0) -> (0, -b)
    cham = np.hypot(u - (-bevel + t * bevel), v - (-t * bevel))
    out = np.minimum(np.minimum(side, front), cham)
    return np.where(inside <= 0, inside, out)


def sd_outline(p: np.ndarray, pr: dict) -> np.ndarray:
    q = (p.reshape(-1, 3) - pr["c"]) @ pr["rot"]
    r = pr["round"]
    u = _sd2(q[:, [0, 2]], pr["segs"]) - pr["grow"] + r
    v = np.abs(q[:, 1]) - pr["depth"] / 2 + r
    return (_profile(u, v, max(pr["bevel"] - r * (2 - math.sqrt(2)), 0.0)) - r).reshape(p.shape[:-1])


# ---------------------------------------------------------------- compile

def segments(loops) -> np.ndarray:
    segs = []
    for loop in loops:
        P = np.asarray(loop, float)
        if P.ndim != 2 or P.shape[1] != 2 or len(P) < 3:
            raise ValueError("each loop is a list of at least 3 [x, z] points")
        segs.append(np.stack([P, np.roll(P, -1, axis=0)], axis=1))
    return np.concatenate(segs)


def outline_params(name: str, bl: dict, c: np.ndarray, rot: np.ndarray, err):
    try:
        segs = segments(bl.get("loops") or [])
    except ValueError as e:
        raise err(f"blob {name!r}: {e}") from None
    depth = float(bl.get("depth", 0.02))
    bevel, rnd = float(bl.get("bevel", 0.0)), float(bl.get("round", 0.0))
    if depth <= 0 or bevel < 0 or rnd < 0 or 2 * max(bevel, rnd) > depth:
        raise err(f"blob {name!r}: an outline needs depth > 0 and bevel, round >= 0, each under half the depth")
    grow = float(bl.get("grow", 0.0))
    pts = segs[:, 0]
    lo2, hi2 = pts.min(0) - max(grow, 0), pts.max(0) + max(grow, 0)
    local = np.array([[x, y, z] for x in (lo2[0], hi2[0]) for y in (-depth / 2, depth / 2) for z in (lo2[1], hi2[1])])
    world = c + local @ rot.T
    pr = {"c": c, "rot": rot, "segs": segs, "depth": depth, "bevel": bevel, "round": rnd, "grow": grow}
    return pr, world.min(0), world.max(0)


# ---------------------------------------------------------------- lettering

def font_path(font: str) -> Path:
    if font in FONTS:
        return FONT_DIR / FONTS[font]
    p = Path(font).expanduser()
    if p.suffix.lower() in (".ttf", ".otf") and p.is_file():
        return p
    raise ValueError(f"no font {font!r} (have {', '.join(FONTS)}, or a path to a .ttf / .otf)")


class _Flatten:
    """A fontTools pen that records each contour as a polyline (curves cut at about `step` font units)."""

    def __init__(self, step: float):
        self.step, self.loops, self.cur = step, [], []

    def moveTo(self, p):
        self.cur = [tuple(p)]

    def lineTo(self, p):
        self.cur.append(tuple(p))

    def _bez(self, ctrl):
        P = np.array([self.cur[-1], *ctrl], float)
        n = max(2, int(np.linalg.norm(np.diff(P, axis=0), axis=1).sum() / self.step))
        t = np.linspace(0, 1, n + 1)[1:, None]
        k = len(P) - 1
        pts = sum(math.comb(k, i) * (1 - t) ** (k - i) * t ** i * P[i] for i in range(k + 1))
        self.cur.extend(map(tuple, pts))

    def qCurveTo(self, *pts):
        if pts[-1] is None:  # a contour of only off-curve points (TrueType): close it on its own midpoints
            pts = pts[:-1]
            pts = (*pts, ((pts[-1][0] + pts[0][0]) / 2, (pts[-1][1] + pts[0][1]) / 2))
            self.cur = [pts[-1]]
        for i in range(len(pts) - 1):  # implied on-curve points between consecutive off-curve ones
            end = pts[i + 1] if i == len(pts) - 2 else ((pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2)
            self._bez([pts[i], end])

    def curveTo(self, *pts):
        for i in range(0, len(pts) - 2, 3):
            self._bez(pts[i:i + 3])

    def closePath(self):
        if len(self.cur) > 1 and np.allclose(self.cur[0], self.cur[-1]):
            self.cur.pop()
        if len(self.cur) >= 3:
            self.loops.append(self.cur)
        self.cur = []

    endPath = closePath

    def addComponent(self, glyph, transform):
        raise NotImplementedError  # glyphs are drawn through a DecomposingPen (text_glyphs)


def text_glyphs(text: str, font: str = "lilita-one", height: float = 0.1, tracking: float = 0.0,
                align: str = "centre", italic: float = 0.0, arc: float = 0.0) -> list[tuple[str, list]]:
    """Each visible character of `text` as (character, loops in metres), laid out on a baseline at z = 0 with cap
    height `height`, aligned about x = 0."""
    from fontTools.pens.basePen import BasePen
    from fontTools.ttLib import TTFont

    f = TTFont(str(font_path(font)))
    gs, cmap = f.getGlyphSet(), f.getBestCmap()
    os2 = f["OS/2"]
    cap = getattr(os2, "sCapHeight", 0) or f["head"].unitsPerEm * 0.7
    s = height / cap
    flat_step = CURVE_STEP * cap

    class Pen(BasePen):
        def __init__(self, glyphset, inner):
            super().__init__(glyphset)
            self.inner = inner

        def _moveTo(self, p):
            self.inner.moveTo(p)

        def _lineTo(self, p):
            self.inner.lineTo(p)

        def _curveToOne(self, a, b, c):
            self.inner.curveTo(a, b, c)

        def _qCurveToOne(self, a, b):
            self.inner.qCurveTo(a, b)

        def _closePath(self):
            self.inner.closePath()

        def _endPath(self):
            self.inner.closePath()

    out, x = [], 0.0
    for ch in text:
        gname = cmap.get(ord(ch))
        if gname is None:
            raise ValueError(f"the font {font!r} has no {ch!r}")
        g = gs[gname]
        rec = _Flatten(flat_step)
        g.draw(Pen(gs, rec))
        if rec.loops:
            loops = [[((px + x) * s + italic * py * s, py * s) for px, py in lp] for lp in rec.loops]
            out.append((ch, loops))
        x += g.width + tracking * cap
    width = (x - tracking * cap) * s
    shift = {"centre": -width / 2, "center": -width / 2, "left": 0.0, "right": -width}.get(align)
    if shift is None:
        raise ValueError(f"align is centre, left or right, not {align!r}")
    half = width / 2

    def lift(loops):
        xs = [px for lp in loops for px, _ in lp]
        xc = (min(xs) + max(xs)) / 2 + shift
        return arc * (1 - (xc / half) ** 2) if half > 0 else 0.0

    return [(ch, [[(px + shift, pz + dz) for px, pz in lp] for lp in loops])
            for ch, loops in out for dz in [lift(loops)]]


def expand_text(s: dict) -> None:
    """Set every "text" blob of spec s into one "outline" blob per glyph, in place (named <name>/<char>#<i>)."""
    blobs = s.get("blobs") or {}
    if not any(b.get("shape") == "text" for b in blobs.values()):
        return
    from .spec import SpecError
    new = {}
    for name, bl in blobs.items():
        if bl.get("shape") != "text":
            new[name] = bl
            continue
        try:
            glyphs = text_glyphs(str(bl.get("text", "")), bl.get("font", "lilita-one"), float(bl.get("height", 0.1)),
                                 float(bl.get("tracking", 0.0)), bl.get("align", "centre"), float(bl.get("italic", 0.0)), float(bl.get("arc", 0.0)))
        except (ValueError, ImportError) as e:
            raise SpecError(f"blob {name!r}: {e}") from None
        if not glyphs:
            raise SpecError(f"blob {name!r}: no visible characters in {bl.get('text')!r}")
        keep = {k: v for k, v in bl.items() if k in PASS or k not in ("shape", "text", "font", "height", "tracking",
                                                                       "align", "italic", "arc", "loops")}
        for i, (ch, loops) in enumerate(glyphs):
            label = ch if ch.isalnum() else f"u{ord(ch):04x}"
            new[f"{name}/{label}#{i}"] = {**keep, "shape": "outline",
                                          "loops": [[[round(px, 6), round(pz, 6)] for px, pz in lp] for lp in loops]}
    s["blobs"] = new
