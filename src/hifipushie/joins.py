"""How a part joins the body: along its base, or out of a stalk? Measured, not judged by eye.

- SEAM: points on the part's own skin where the rest of the model's surface is within 1.5 mm (the line where
  they meet). Its length along its main axis is the JOIN.
- FOOTPRINT: the part's skin within 2.5 cm of the rest of the model, along the same axis: how wide the part is
  where it comes off the body. JOIN / FOOTPRINT near 1 = joined along its base; about 0.5 = a stalk or neck.
  Under WARN (0.75) a save says so.
- SECTIONS: two cuts through the seam's centre, along and across it, drawn flat: the rest grey, the part red, a
  1 cm grid, up = out of the body. A stalk shows as a waist between them.

Why: a silhouette can't show a stalk (it sits inside the outline) and a shaded render hides it under the overhang.
(Baynard Racing, Puddles' ears, 2026-11: three rounds of "both edges meet" about an ear standing on a stalk;
v83's ear measured 0.58.)

A part is named by element (prim) name, its part name, or a base name with `side` (".L" by default), e.g.
"ear" -> ear.L; "ear,earroot" measures the two as one piece. Everything else, except the part's mirror twin, is "the rest".
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from . import sdf, store

WARN = 0.75
SEAM, FOOT = 0.0015, 0.025
MAX_POINTS = 3_000_000


def _split(prims, part: str, side: str):
    cands = {c for n in part.split(",") for c in (n.strip(), f"{n.strip()}.{side}")}  # "ear,earroot": one piece
    sel = [p for p in prims if p.name in cands or p.part in cands]
    if not sel:
        names = sorted({p.name for p in prims} | {p.part for p in prims})
        raise ValueError(f"no element or part named {part!r} (or {part}.{side}); have e.g. {names[:30]}")
    keys = {p.name for p in sel}
    twin = {k[:-2] + (".R" if k.endswith(".L") else ".L") for k in keys if k.endswith((".L", ".R"))}
    rest = [p for p in prims if p.name not in keys and p.name not in twin]
    return sel, rest


def measure(name: str, part: str, side: str = "L", sections: bool = False) -> dict:
    """The join report of one part (module docstring). sections=True adds "image": the two sections."""
    from .spec import compile_prims
    prims = compile_prims(store.load(name))
    sel, rest = _split(prims, part, side)
    lo = np.min([p.lo for p in sel], 0) - 0.03
    hi = np.max([p.hi for p in sel], 0) + 0.03
    h = max(0.0012, float(np.prod(hi - lo) / MAX_POINTS) ** (1 / 3))
    g = np.stack(np.meshgrid(*[np.arange(lo[i], hi[i], h) for i in range(3)], indexing="ij"), -1).reshape(-1, 3)
    fp = sdf.field_at(sel, g, clip=False)
    skin = g[np.abs(fp) < 0.7 * h]
    if not len(skin):
        raise ValueError(f"{part}: no surface found at {1000 * h:.1f} mm")
    fo = sdf.field_at(rest, skin, clip=False) if rest else np.full(len(skin), np.inf)
    seam = skin[np.abs(fo) < max(SEAM, 0.7 * h)]
    foot = skin[(fo > -0.002) & (fo < FOOT)]
    out = {"part": part, "elements": sorted(p.name for p in sel), "voxel_mm": round(1000 * h, 2)}
    if len(seam) < 10:
        out.update(ratio=0.0, joined=False, closest_mm=round(1000 * float(np.abs(fo).min()), 1))
        return out
    c = seam.mean(0)
    _, _, vt = np.linalg.svd(seam - c, full_matrices=False)
    ax1, ax3 = vt[0], vt[2]
    if (skin.mean(0) - c) @ ax3 < 0:  # up = out of the body, toward the part
        ax3 = -ax3
    ax2 = np.cross(ax3, ax1)

    def ext(pts, a):
        q = (pts - c) @ a
        return float(np.percentile(q, 98) - np.percentile(q, 2))
    j1, f1, j2, f2 = ext(seam, ax1), ext(foot, ax1), ext(seam, ax2), ext(foot, ax2)
    out.update(joined=True, centre=np.round(c, 3).tolist(), along=np.round(ax1, 2).tolist(),
               join_mm=round(1000 * j1), footprint_mm=round(1000 * f1), ratio=round(j1 / max(f1, 1e-9), 2),
               join_across_mm=round(1000 * j2), footprint_across_mm=round(1000 * f2),
               ratio_across=round(j2 / max(f2, 1e-9), 2))
    if sections:
        out["image"] = _sections(sel, rest, c, ax1, ax2, ax3)
    return out


def _sections(sel, rest, c, ax1, ax2, ax3, S: int = 300, R: float = 0.09) -> Image.Image:
    tiles = []
    for a in (ax1, ax2):
        u = np.linspace(-R, R, S)
        U, Wv = np.meshgrid(u, u[::-1])
        pts = (c + U[..., None] * a + Wv[..., None] * ax3).reshape(-1, 3)
        fpa = sdf.field_at(sel, pts, clip=False).reshape(S, S)
        foa = sdf.field_at(rest, pts, clip=False).reshape(S, S) if rest else np.ones((S, S))
        img = np.full((S, S, 3), 250, np.uint8)
        img[foa < 0] = (170, 170, 178)
        img[fpa < 0] = (225, 80, 70)
        img[(fpa < 0) & (foa < 0)] = (150, 60, 60)
        im = Image.fromarray(img).resize((2 * S, 2 * S), Image.NEAREST)
        d = ImageDraw.Draw(im)
        for k in range(-int(R * 100), int(R * 100) + 1):  # 1 cm grid
            q = (k * 0.01 + R) / (2 * R) * 2 * S
            d.line([(q, 0), (q, 2 * S)], fill=(205, 205, 215))
            d.line([(0, q), (2 * S, q)], fill=(205, 205, 215))
        tiles.append(im)
    sheet = Image.new("RGB", (4 * S + 10, 2 * S), "white")
    sheet.paste(tiles[0], (0, 0))
    sheet.paste(tiles[1], (2 * S + 10, 0))
    return sheet


def line(r: dict) -> str:
    """One report line; a WARNING when the part stands on a stalk or doesn't touch at all."""
    if not r["joined"]:
        return f"WARNING: join {r['part']}: not joined to the rest (closest {r['closest_mm']} mm)"
    s = (f"join {r['part']}: seam {r['join_mm']} mm of a {r['footprint_mm']} mm base = {r['ratio']:.2f} "
         f"(across {r['ratio_across']:.2f})")
    if r["ratio"] < WARN:
        s = (f"WARNING: {s}: joined along only part of its base, a stalk or neck (want >= {WARN}); "
             "join_report(sections=True) shows the cut")
    return s


def report(name: str, parts, side: str = "L") -> str:
    """Lines for several parts (a failure on one part is its line, never the save's)."""
    out = []
    for p in parts:
        try:
            out.append(line(measure(name, p, side)))
        except ValueError as e:
            out.append(f"join {p}: {e}")
    return "\n".join(out)
