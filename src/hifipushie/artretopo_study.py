"""Artist retopo: studying the sculpt before drawing a loop (what an artist does with the model on a turntable and a
ruler): gridded orthographic views and slices with numbers.

- `views(name, mesh, views, centre, scale, step, style, over)`: front / left / top (... ) renders of one mesh, a
  coordinate grid every `step` (labelled: x / y / z in the sculpt's frame) drawn over each, as one sheet. Read rings'
  heights, a limb's centre, an eye's centre straight off it.
- `slices(name, axis, at, mesh)`: cut the sculpt with planes (axis "z": horizontal at each height; "x" / "y":
  vertical), every region listed with its centroid, extent and area, and drawn on one gridded sheet. A ring's `pick`
  is a centroid from here; a limb is the small region beside the torso; where two regions merge (an arm fused to the
  body) the slice says so.
Pictures carry the shape; the text answer carries every number."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .artretopo_run import folder, need
from .artretopo_sculpt import Sculpt

AXES = {"front": (0, 2, 1, False), "back": (0, 2, -1, True), "side_r": (1, 2, 1, True), "side": (1, 2, 1, False),
        "top": (0, 1, 1, False)}       # view: (horizontal axis, vertical axis, -, horizontal flipped?)
MESHES = {"high": "high.ply", "body": "high_body.ply", "cage": "cage.ply", "low": "low.ply", "lod1": "lod1.ply",
          "final": "final.glb", "rigged": "rigged.glb", "lod1_rigged": "lod1_rigged.glb"}


def _mesh_path(d: Path, mesh: str) -> Path:
    f = MESHES.get(mesh, mesh); need(d, f); return d / f


def views(name: str, mesh: str = "high", views=("front", "side", "top"), centre=None, scale=None, step: float = 0.05,
          style: str = "colour", over: str | None = None, res: int = 768, folds: bool = False) -> tuple[Path, str]:
    from .artretopo_steps import GB, blender, framing
    d = folder(name); src = _mesh_path(d, mesh)
    fr = framing(d)
    centre = list(centre) if centre is not None else fr["centre"]; scale = float(scale or fr["scale"])
    out = d / "study" / f"{mesh}_{style}"; out.parent.mkdir(exist_ok=True)
    job = {"mesh": str(src), "style": style, "views": list(views), "centre": centre, "scale": scale, "res": res,
           "out": str(out)}
    if over:
        job["over"] = str(_mesh_path(d, over))
    if folds:
        if mesh != "low" or style not in ("clay", "wire"):
            raise ValueError("folds: only on mesh low, style clay or wire (the press's folded faces)")
        need(d, "low_folded.json"); job["red"] = json.loads((d / "low_folded.json").read_text())
    blender("look", job, GB["look"])
    tiles = []
    for v in views:
        im = Image.open(f"{out}_{v}.png").convert("RGB")
        if v in AXES:
            _grid(im, v, centre, scale, step)
        ImageDraw.Draw(im).text((6, res - 16), v, fill=(0, 0, 0))
        tiles.append(im)
    sheet = Image.new("RGB", (res * len(tiles), res), "white")
    for k, im in enumerate(tiles):
        sheet.paste(im, (k * res, 0))
    p = d / "study" / f"{mesh}_{style}_{'_'.join(views)}.jpg"; sheet.save(p, quality=88)
    return p, (f"{mesh} ({src.name}) {style}: centre {centre}, view width {scale}; grid every {step} "
               f"(blue: horizontal axis, orange: vertical; labels are coordinates in the sculpt's frame)")


def _grid(im, view, centre, scale, step):
    h, v, _, flip = AXES[view]; res = im.size[0]; S = res / scale; d = ImageDraw.Draw(im)
    n = "xyz"
    lo_h, hi_h = centre[h] - scale / 2, centre[h] + scale / 2
    for val in np.arange(np.floor(lo_h / step) * step, hi_h + 1e-9, step):
        X = res / 2 + (-1 if flip else 1) * (val - centre[h]) * S
        d.line([(X, 0), (X, res)], fill=(0, 120, 255)); d.text((X + 2, 2), f"{n[h]}{val:+.2f}", fill=(0, 90, 200))
    lo_v, hi_v = centre[v] - scale / 2, centre[v] + scale / 2
    for val in np.arange(np.floor(lo_v / step) * step, hi_v + 1e-9, step):
        Y = res / 2 - (val - centre[v]) * S
        d.line([(0, Y), (res, Y)], fill=(255, 80, 0)); d.text((2, Y + 2), f"{n[v]}{val:+.2f}", fill=(200, 60, 0))


PLANES = {"z": ((0, 0, 1), (1, 0, 0), (0, 1, 0), "x", "y"), "x": ((1, 0, 0), (0, 1, 0), (0, 0, 1), "y", "z"),
          "y": ((0, 1, 0), (1, 0, 0), (0, 0, 1), "x", "z")}


def slices(name: str, axis: str = "z", at=(0.0,), mesh: str = "high", step: float = 0.05, res: int = 700) -> tuple[Path, str]:
    d = folder(name); S_ = Sculpt(_mesh_path(d, mesh))
    nrm, u, v, un, vn = PLANES[axis]
    k = "xyz".index(axis)
    rows, polys = [], []
    for a in at:
        o = [0.0, 0.0, 0.0]; o[k] = float(a)
        ps = sorted(S_.slice(o, nrm, u, v), key=lambda p: -p.area)
        for p in ps:
            c = p.centroid; e = p.exterior
            rows.append({axis: a, "centroid": [round(float(c[0]), 4), round(float(c[1]), 4)],
                         f"{un}_range": [round(float(e[:, 0].min()), 4), round(float(e[:, 0].max()), 4)],
                         f"{vn}_range": [round(float(e[:, 1].min()), 4), round(float(e[:, 1].max()), 4)],
                         "area_cm2": round(p.area * 1e4, 1), "holes": len(p.holes)})
        polys.append((a, ps))
    allp = np.vstack([p.exterior for _, ps in polys for p in ps]) if rows else np.zeros((1, 2))
    lo, hi = allp.min(0), allp.max(0); span = float(max(hi - lo)) * 1.15 + 1e-6; cen = (lo + hi) / 2
    im = Image.new("RGB", (res, res), "white"); dr = ImageDraw.Draw(im); Sx = res / span
    tx = lambda q: (res / 2 + (q[0] - cen[0]) * Sx, res / 2 - (q[1] - cen[1]) * Sx)
    for val in np.arange(np.floor((cen[0] - span / 2) / step) * step, cen[0] + span / 2, step):
        X = tx((val, 0))[0]; dr.line([(X, 0), (X, res)], fill=(200, 220, 255)); dr.text((X + 2, 2), f"{un}{val:+.2f}", fill=(0, 90, 200))
    for val in np.arange(np.floor((cen[1] - span / 2) / step) * step, cen[1] + span / 2, step):
        Y = tx((0, val))[1]; dr.line([(0, Y), (res, Y)], fill=(255, 225, 200)); dr.text((2, Y + 2), f"{vn}{val:+.2f}", fill=(200, 60, 0))
    cols = [(200, 30, 30), (30, 120, 30), (30, 30, 200), (160, 90, 0), (120, 0, 160), (0, 130, 130)]
    for n, (a, ps) in enumerate(polys):
        col = cols[n % len(cols)]
        for p in ps:
            for loop in [p.exterior] + p.holes:
                pts = [tx(q) for q in loop] + [tx(loop[0])]
                dr.line(pts, fill=col, width=2)
            dr.text(tx(p.centroid), f"{a:+.2f}", fill=col)
    p = d / "study" / f"slices_{mesh}_{axis}.png"; p.parent.mkdir(exist_ok=True); im.save(p)
    head = f"slices of {mesh} by planes {axis} = {list(at)} (in the plane: {un} across, {vn} up); regions largest first:"
    return p, head + "\n" + "\n".join(json.dumps(r) for r in rows)
