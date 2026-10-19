"""Diagnostic renders: construction shown in flat, high-contrast colour, so what is really happening on a garment (or any
mesh) is obvious to a vision model, not hidden in clay shading (Joe 2026-10-19: "contrast-color or something so that
what's really happening is super obvious to a vision model"; Marvelous Designer / CLO show pattern colours, seam lines
and strain maps for the same reason).

`diag_shading(objects, modes)` turns render objects into diagnostic ones; `cloth.render(..., diag=[...])` renders them
(EEVEE, emission only: unlit, no shadows, no cavity, so lighting can neither hide nor fake anything; the PNG pixel is
the declared sRGB colour) with a thin dark silhouette outline drawn in post so the shape still reads. The default clay
look is untouched: nothing changes unless `diag` is given.

An object is {"name", "V", "F", "color"?} as for cloth.render, plus for garments "mesh": the pattern mesh dict
(cloth / pattern_form: uv (flat pattern, m), piece (per vertex), names, sew (vertex pairs), sew_seam, folds) and
optionally "layer" (int, inner -> outer; default: the order garments are listed). Objects without "mesh" (the body)
are drawn flat in BODY.

Modes (combinable; a face's colour: strain > panels > layers > clay, then the overlays turned, backfaces, pierce):
- panels: each pattern piece a flat colour from PALETTE (pieces sewn to each other never share one; the least-used
  colour first), legend colour -> "garment:piece".
- seams: sewn seams as thick dark tubes on the surface (SEAM); fold lines (each fold's first row: a lapel's roll line,
  a collar's fold) as thick dashed bright tubes (FOLD).
- turned: the faces of a folded / turned flap (every fold with a turn) TURNED orange on the side that shows once the
  flap is turned over (the mesh back side), TURNED_UNDER (darker) on its other side: a flap left flat or turned the
  wrong way shows dark.
- backfaces: back faces RED (inside-out pieces, seeing through to the underside).
- strain: per-face stretch vs the flat pattern (the larger principal stretch of the face's map uv -> 3D, signed):
  blue compressed -> white 0 -> red stretched, +-STRAIN_SCALE full scale (printed by `strain_bar`).
- layers: each garment a LAYERS colour by layer; faces of an inner layer that cross the outer layer, or have the outer
  layer behind them (within PIERCE_REACH, toward the body), MAGENTA.
"""
from __future__ import annotations

import numpy as np

from . import validated

MODES = ("panels", "seams", "turned", "backfaces", "strain", "layers")

# sRGB hex (the PNG shows exactly these: emission, Standard view transform). Reserved colours are kept out of PALETTE.
PALETTE = ["#1f5fd6", "#2ca02c", "#17becf", "#7b3fc9", "#a6d854", "#8c564b", "#00796b", "#9ecae1", "#c7b6ff",
           "#003a70", "#556b2f", "#e5c494", "#4daf4a", "#5e3c99", "#80cdc1", "#b15928"]
RED, MAGENTA, TURNED, TURNED_UNDER = "#ff0000", "#ff00ff", "#ff8c00", "#8a3c00"
SEAM, FOLD = "#101010", "#ffee00"
CLAY, BODY, BG = "#a8a8a8", "#c4bcb4", "#3c3c3c"
LAYERS = ["#7fdbff", "#24408e", "#3d9970", "#b10dc9"]  # inner -> outer: shirt, jacket, (coat), ...
STRAIN_SCALE = 0.10  # full red / blue at +-10 %
PIERCE_REACH = 0.015  # m (as garment_game.PIERCE_REACH)
SEAM_R, FOLD_R, DASH = 0.0035, 0.003, (0.015, 0.010)  # m: tube radii, dash on / off


def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def srgb_to_linear(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _modes(diag) -> set:
    m = {diag} if isinstance(diag, str) else set(diag or ())
    bad = m - set(MODES)
    if bad:
        raise ValueError(f"diag: unknown mode(s) {sorted(bad)}; modes are {list(MODES)}")
    return m


# ---------------------------------------------------------------- per-face measures

def _selftest_face_strain():
    uv = np.array([[0, 0], [0.1, 0], [0, 0.1]], float)
    F = np.array([[0, 1, 2]])
    V = np.c_[uv, np.zeros(3)]
    assert abs(face_strain(V, F, uv)[0]) < 1e-12  # laid flat: 0
    assert abs(face_strain(V * [1.1, 1, 1], F, uv)[0] - 0.10) < 1e-9  # 10 % along u
    assert abs(face_strain(V * [0.9, 1.02, 1], F, uv)[0] + 0.10) < 1e-9  # the larger of -10 % / +2 % wins, signed
    R = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], float)  # rigid motion: 0
    assert abs(face_strain(V @ R.T + 3, F, uv)[0]) < 1e-12


@validated.known_answer(_selftest_face_strain)
def face_strain(V, F, uv) -> np.ndarray:
    """Per face: the principal stretch of the map flat pattern (uv, m) -> 3D with the larger |s - 1|, as s - 1 (0.1 =
    10 % stretched, -0.1 = 10 % compressed). Degenerate pattern faces read 0."""
    V, uv, F = np.asarray(V, float), np.asarray(uv, float), np.asarray(F)
    E = np.stack([V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]], 2)  # (n, 3, 2)
    e = np.stack([uv[F[:, 1]] - uv[F[:, 0]], uv[F[:, 2]] - uv[F[:, 0]]], 2)  # (n, 2, 2)
    det = e[:, 0, 0] * e[:, 1, 1] - e[:, 0, 1] * e[:, 1, 0]
    ok = np.abs(det) > 1e-14
    inv = np.zeros_like(e)
    d = np.where(ok, det, 1.0)
    inv[:, 0, 0], inv[:, 1, 1] = e[:, 1, 1] / d, e[:, 0, 0] / d
    inv[:, 0, 1], inv[:, 1, 0] = -e[:, 0, 1] / d, -e[:, 1, 0] / d
    G = E @ inv
    s = np.linalg.svd(G, compute_uv=False)  # (n, 2), descending
    hi, lo = s[:, 0] - 1, s[:, 1] - 1
    out = np.where(np.abs(hi) >= np.abs(lo), hi, lo)
    return np.where(ok, out, 0.0)


def strain_rgb(s, scale: float = STRAIN_SCALE) -> np.ndarray:
    """sRGB per value: blue (-scale) -> white (0) -> red (+scale)."""
    t = np.clip(np.asarray(s, float) / scale, -1, 1)[:, None]
    blue, red, white = hex_rgb("#1030ff"), hex_rgb(RED), np.ones(3)
    return np.where(t < 0, white + (-t) * (blue - white), white + t * (red - white))


def flap_faces(M: dict, per_fold: bool = False):
    """Face mask: faces of a turned fold's flap (folds._geom's flap0, every fold with a turn). per_fold: a list of
    (flap face mask, base triangles) per fold instead."""
    from . import folds as foldmod
    F = np.asarray(M["F"])
    out = np.zeros(len(F), bool)
    each = []
    for fd in M.get("folds") or []:
        if abs(float(fd.get("turn", 0.0))) < 1e-3 or not len(fd.get("rows") or []) or len(fd["rows"][0]) < 2:
            continue
        g = foldmod._geom(M, fd)
        fl = np.asarray(g["flap0"])
        onrow = np.zeros(len(fl), bool)
        onrow[np.asarray(fd["rows"][0])] = True
        # (the faces at the hinge, with a vertex on the row, are the flap's too)
        m = (fl | onrow)[F].all(1) & fl[F].any(1)
        out |= m
        each.append((m, np.asarray(g["base_tris"])))
    return each if per_fold else out


def outward_front(V, T, body) -> bool:
    """Do the triangles' FRONT sides (right-hand normals) face away from the body (majority, area-weighted)? True
    without a body."""
    if body is None or not len(T):
        return True
    from scipy.spatial import cKDTree
    V = np.asarray(V, float)
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    c = V[T].mean(1)
    _, i = cKDTree(np.asarray(body, float)).query(c)
    return float((n * (c - np.asarray(body, float)[i])).sum(1).sum()) >= 0


def pierce_faces(under_V, under_F, cover_V, cover_F, body=None, reach: float = PIERCE_REACH) -> np.ndarray:
    """Face mask of the inner layer: faces that cross the cover (garment_game.crossing_faces) or have a vertex with
    the cover BEHIND it (toward the body, within reach: poked through, garment_game.pierce_count's test)."""
    from . import garment_game as gg
    uV, uF = np.asarray(under_V, float), np.asarray(under_F)
    cV, cF = np.asarray(cover_V, float), np.asarray(cover_F)
    m = gg.crossing_faces(uV, uF, cV, cF)
    used = np.unique(uF)
    N = gg.normals(uV, uF)
    if body is not None:
        N = gg.outward(uV, N, np.asarray(body, float))
    t = gg.ray_hits(uV[used], -N[used], cV, cF, reach)
    poked = np.zeros(len(uV), bool)
    poked[used[np.isfinite(t)]] = True
    return m | poked[uF].any(1)


def _piece_colours(garments: list) -> dict:
    """{(garment, piece index): hex}: sewn pieces never share a colour; the least-used colour first."""
    keys, adj = [], {}
    for g in garments:
        M = g["mesh"]
        for k in range(len(M["names"])):
            keys.append((g["name"], k))
            adj[(g["name"], k)] = set()
        pid = np.asarray(M["piece"])
        for a, b in np.asarray(M.get("sew", np.zeros((0, 2), int))).reshape(-1, 2):
            pa, pb = (g["name"], int(pid[a])), (g["name"], int(pid[b]))
            if pa != pb:
                adj[pa].add(pb)
                adj[pb].add(pa)
    col, used = {}, {c: 0 for c in PALETTE}
    for k in keys:
        taken = {col[n] for n in adj[k] if n in col}
        free = [c for c in PALETTE if c not in taken] or PALETTE
        c = min(free, key=lambda c: (used[c], PALETTE.index(c)))
        col[k] = c
        used[c] += 1
    return col


# ---------------------------------------------------------------- lines as tubes

def tubes(P0, P1, r: float, sides: int = 6):
    """Open prisms of radius r along segments P0 -> P1 (each lengthened by r at both ends so a polyline's joints
    close). Returns (V, F)."""
    P0, P1 = np.asarray(P0, float), np.asarray(P1, float)
    if not len(P0):
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    t = P1 - P0
    L = np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    t = t / L
    P0, P1 = P0 - t * r, P1 + t * r
    a = np.where(np.abs(t[:, [0]]) < 0.9, [[1.0, 0, 0]], [[0, 1.0, 0]])
    u = np.cross(t, a)
    u /= np.linalg.norm(u, axis=1, keepdims=True)
    v = np.cross(t, u)
    ang = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    ring = (np.cos(ang)[None, :, None] * u[:, None] + np.sin(ang)[None, :, None] * v[:, None]) * r  # (n, s, 3)
    V = np.concatenate([P0[:, None] + ring, P1[:, None] + ring], 1).reshape(-1, 3)
    n = len(P0)
    base = (np.arange(n) * 2 * sides)[:, None]
    i = np.arange(sides)[None]
    j = (i + 1) % sides
    a0, a1, b0, b1 = base + i, base + j, base + sides + i, base + sides + j
    F = np.concatenate([np.stack([a0, a1, b1], -1), np.stack([a0, b1, b0], -1)], 1).reshape(-1, 3)
    return V, F


def seam_edges(M: dict) -> np.ndarray:
    """Boundary edges whose two ends are sewn on the same seam (M["sew"], M["sew_seam"])."""
    F = np.asarray(M["F"])
    sew = np.asarray(M.get("sew", np.zeros((0, 2), int))).reshape(-1, 2)
    if not len(sew):
        return np.zeros((0, 2), int)
    sid = np.asarray(M.get("sew_seam", np.zeros(len(sew), int)))
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    u, c = np.unique(E, axis=0, return_counts=True)
    bnd = u[c == 1]
    vs = {}
    for (a, b), s in zip(sew, sid):
        vs.setdefault(int(a), set()).add(int(s))
        vs.setdefault(int(b), set()).add(int(s))
    keep = [i for i, (a, b) in enumerate(bnd) if vs.get(int(a), set()) & vs.get(int(b), set())]
    return bnd[keep]


def _dashes(P: np.ndarray, on: float, off: float):
    """Segments of the dashes along polyline P."""
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.r_[0, np.cumsum(seg)]
    if s[-1] <= 0:
        return np.zeros((0, 3)), np.zeros((0, 3))
    a0, a1 = [], []
    x = 0.0
    while x < s[-1]:
        lo, hi = x, min(x + on, s[-1])
        grid = np.r_[lo, s[(s > lo) & (s < hi)], hi]
        pts = np.stack([np.interp(grid, s, P[:, k]) for k in range(3)], 1)
        a0.append(pts[:-1])
        a1.append(pts[1:])
        x += on + off
    return np.concatenate(a0), np.concatenate(a1)


# ---------------------------------------------------------------- the shading

def diag_shading(objects: list, diag, body=None, strain_scale: float = STRAIN_SCALE,
                 piece_colours: dict | None = None) -> tuple[list, list]:
    """Render objects -> (diagnostic objects for cloth.render: per-corner sRGB "CC" front / "CB" back colours, plus
    seam / fold tube objects, legend [(label, hex)]). `body`: vertices for orienting the pierce test (default: the
    first object without "mesh")."""
    modes = _modes(diag)
    garments = [o for o in objects if o.get("mesh") is not None]
    others = [o for o in objects if o.get("mesh") is None]
    if body is None and others:
        body = others[0]["V"]
    out, legend = [], []
    for o in others:
        out.append({"name": o["name"], "V": o["V"], "F": o["F"], "color": BODY})
    pcol = (piece_colours or _piece_colours(garments)) if "panels" in modes else {}
    lay = {id(g): g.get("layer", i) for i, g in enumerate(garments)}
    order = sorted(garments, key=lambda g: lay[id(g)])
    pierce = {}
    if "layers" in modes:
        for i, g in enumerate(order):
            m = np.zeros(len(g["F"]), bool)
            for h in order[i + 1:]:
                m |= pierce_faces(g["V"], g["F"], h["V"], h["F"], body)
            pierce[g["name"]] = m
    seg0, seg1, fol0, fol1 = [], [], [], []
    stats = {}
    for g in garments:
        M, V, F = g["mesh"], np.asarray(g["V"], float), np.asarray(g["F"])
        nf = len(F)
        front = np.tile(hex_rgb(CLAY), (nf, 1))
        if "layers" in modes:
            front[:] = hex_rgb(LAYERS[order.index(g) % len(LAYERS)])
            legend.append((f"layer {order.index(g)}: {g['name']}", LAYERS[order.index(g) % len(LAYERS)]))
        if "panels" in modes:
            pid = np.asarray(M["piece"])[F[:, 0]]
            for k, nm in enumerate(M["names"]):
                c = pcol[(g["name"], k)]
                front[pid == k] = hex_rgb(c)
                if (pid == k).any():
                    legend.append((f"{g['name']}:{nm}", c))
        if "strain" in modes:
            s = face_strain(V, F, M["uv"])
            front = strain_rgb(s, strain_scale)
            stats[g["name"]] = {"strain_p50": float(np.median(np.abs(s))), "strain_p99": float(np.percentile(np.abs(s), 99))}
        back = front.copy()
        if "backfaces" in modes:
            back[:] = hex_rgb(RED)
        if "turned" in modes:
            # the side that shows once a flap is turned over is the side its base wears INWARD: base fronts out (the
            # usual winding) -> the flap's back side shows; a piece wound the other way swaps
            nfl = 0
            for fl, bt in flap_faces(M, per_fold=True):
                out_front = outward_front(V, bt, body)
                shown, other = (back, front) if out_front else (front, back)
                shown[fl], other[fl] = hex_rgb(TURNED), hex_rgb(TURNED_UNDER)
                nfl += int(fl.sum())
            stats.setdefault(g["name"], {})["flap_faces"] = nfl
        if g["name"] in pierce:
            pm = pierce[g["name"]]
            front[pm] = back[pm] = hex_rgb(MAGENTA)
            stats.setdefault(g["name"], {})["pierce_faces"] = int(pm.sum())
        if "seams" in modes:
            E = seam_edges(M)
            seg0.append(V[E[:, 0]])
            seg1.append(V[E[:, 1]])
            for fd in M.get("folds") or []:
                if len(fd.get("rows") or []) and len(fd["rows"][0]) >= 2:
                    a, b = _dashes(V[np.asarray(fd["rows"][0])], *DASH)
                    fol0.append(a)
                    fol1.append(b)
        out.append({"name": g["name"], "V": V, "F": F, "CC": np.repeat(front, 3, 0), "CB": np.repeat(back, 3, 0)})
    if "seams" in modes:
        if seg0:
            tv, tf = tubes(np.concatenate(seg0), np.concatenate(seg1), SEAM_R)
            if len(tf):
                out.append({"name": "diag_seams", "V": tv, "F": tf, "color": SEAM})
        if fol0:
            tv, tf = tubes(np.concatenate(fol0), np.concatenate(fol1), FOLD_R)
            if len(tf):
                out.append({"name": "diag_folds", "V": tv, "F": tf, "color": FOLD})
        legend += [("sewn seam", SEAM), ("fold line (dashed)", FOLD)]
    if "turned" in modes:
        legend += [("turned flap, shown side", TURNED), ("turned flap, other side", TURNED_UNDER)]
    if "backfaces" in modes:
        legend.append(("back face", RED))
    if "layers" in modes:
        legend.append(("inner layer through outer", MAGENTA))
    diag_shading.stats = stats
    return out, legend


# ---------------------------------------------------------------- render + post

def outline(path, width: int = 1, bg: str = BG) -> None:
    """A thin dark line on the inside of the silhouette (pixels that differ from the background), in place."""
    from PIL import Image
    im = np.asarray(Image.open(path).convert("RGB")).astype(int)
    fg = np.abs(im - (hex_rgb(bg) * 255).round()).max(2) > 10
    er = fg.copy()
    for _ in range(width):
        e = er.copy()
        e[1:] &= er[:-1]; e[:-1] &= er[1:]; e[:, 1:] &= er[:, :-1]; e[:, :-1] &= er[:, 1:]
        er = e
    im[fg & ~er] = (10, 10, 10)
    Image.fromarray(im.astype(np.uint8)).save(path)


def legend_strip(legend: list, width: int, strain: bool = False, scale: float = STRAIN_SCALE):
    """A PIL image: colour swatches with labels (and the strain colour bar when strain) across `width` px."""
    from PIL import Image, ImageDraw
    cell, rowh = 230, 22
    per = max(1, width // cell)
    rows = (len(legend) + per - 1) // per + (2 if strain else 0)
    im = Image.new("RGB", (width, rows * rowh + 8), (30, 30, 30))
    d = ImageDraw.Draw(im)
    for i, (lab, c) in enumerate(legend):
        x, y = (i % per) * cell + 6, (i // per) * rowh + 4
        d.rectangle([x, y + 2, x + 16, y + 16], fill=tuple(int(v * 255) for v in hex_rgb(c)), outline=(200, 200, 200))
        d.text((x + 22, y + 4), lab[:30], fill=(240, 240, 240))
    if strain:
        y = (len(legend) + per - 1) // per * rowh + 6
        w = min(width - 120, 600)
        vals = np.linspace(-scale, scale, w)
        bar = (strain_rgb(vals, scale) * 255).astype(np.uint8)
        for x in range(w):
            d.line([(60 + x, y), (60 + x, y + 14)], fill=tuple(int(c) for c in bar[x]))
        d.text((6, y + 2), "strain", fill=(240, 240, 240))
        for f, t in ((0, f"-{scale * 100:.0f}%"), (0.5, "0"), (1, f"+{scale * 100:.0f}%")):
            d.text((60 + int(f * (w - 1)) - 10, y + 18), t, fill=(240, 240, 240))
        d.text((60 + w + 8, y + 2), "blue compressed / red stretched vs flat pattern", fill=(240, 240, 240))
    return im


def render(objects: list, prefix: str, diag, views=("front", "side", "back"), resolution: int = 700, box=None,
           aspect: float = 0.62, body=None, strain_scale: float = STRAIN_SCALE,
           piece_colours: dict | None = None) -> tuple[list, list]:
    """Diagnostic render: diag_shading + the flat EEVEE pass (blender_cloth.render job "diag") + outline. Returns
    (PNG paths, legend). Takes the GPU: run under bin/capped with resources.heavy."""
    from . import cloth
    objs, legend = diag_shading(objects, diag, body=body, strain_scale=strain_scale, piece_colours=piece_colours)
    paths = cloth._render_job(objs, prefix, views=views, resolution=resolution, box=box, aspect=aspect,
                              extra={"diag": True, "bg": BG})
    for p in paths:
        outline(p)
    return paths, legend


def sheet(rows: list, out, diag, views=("front", "three", "side", "back", "top"), resolution: int = 560, box=None,
          aspect: float = 0.8, title: str = "", strain_scale: float = STRAIN_SCALE, singles: bool = True):
    """rows: [(label, objects)] or [(label, objects, {"diag": modes, "box": box})] (a row's own modes / framing) -> one
    PNG: per row the views side by side, labelled, legend (+ strain bar) at the bottom. The caller holds
    resources.heavy (GPU). singles (default): each view is also kept as its own PNG, <out stem>_r<row>_<view>.png
    (plus <out stem>_legend.png): reviewers see ONE view per turn (a single reference | result crop of one region from
    one camera), never the contact sheet; the sheet is for Joe and the coordinator."""
    from pathlib import Path
    from PIL import Image, ImageDraw
    VIEW = {"three": {"name": "three", "dir": [-0.65, -0.72, 0.15]}, "top": {"name": "top", "dir": [0.0, -0.05, 1.0]}}
    vs = [VIEW.get(v, v) if isinstance(v, str) else v for v in views]
    names = [v if isinstance(v, str) else v["name"] for v in vs]
    out = Path(out)
    strips, legend = [], []
    anystrain = False
    seen = {}  # (one panel colouring over every row: a piece keeps its colour from row to row)
    for row in rows:
        for o in row[1]:
            if o.get("mesh") is not None:
                seen.setdefault(o["name"], o)
    pc = _piece_colours(list(seen.values()))
    for k, row in enumerate(rows):
        lab, objs = row[0], row[1]
        opt = row[2] if len(row) > 2 else {}
        dg = opt.get("diag", diag)
        anystrain |= "strain" in _modes(dg)
        paths, lg = render(objs, str(out.with_suffix("")) + f"_r{k}", dg, views=vs, resolution=resolution,
                           box=opt.get("box", box), aspect=aspect, strain_scale=strain_scale, piece_colours=pc)
        legend += [x for x in lg if x not in legend]
        ims = [Image.open(p).convert("RGB") for p in paths]
        h = ims[0].height
        st = Image.new("RGB", (sum(i.width for i in ims), h + 24), (30, 30, 30))
        d = ImageDraw.Draw(st)
        x = 0
        for im, v in zip(ims, names):
            st.paste(im, (x, 24))
            d.text((x + 6, 6), f"{v}  {lab}  [diag: {', '.join(sorted(_modes(dg)))}] {title}", fill=(255, 255, 255))
            x += im.width
        strips.append(st)
        if not singles:
            for p in paths:
                Path(p).unlink(missing_ok=True)
    W = max(s.width for s in strips)
    lg = legend_strip(legend, W, strain=anystrain, scale=strain_scale)
    if singles:
        legend_strip(legend, 900, strain=anystrain, scale=strain_scale).save(str(out.with_suffix("")) + "_legend.png")
    full = Image.new("RGB", (W, sum(s.height for s in strips) + lg.height), (30, 30, 30))
    y = 0
    for s in strips + [lg]:
        full.paste(s, (0, y))
        y += s.height
    full.save(out)
    return out


def pattern_sheet_diag(res: dict, prefix, diag, views=("front", "three", "side", "back", "top"),
                       resolution: int = 700):
    """cloth_check.pattern_sheet's layout (the assembled pre-sim garment on the body, framed ~1 m) in diagnostic
    colour -> <prefix>.png. A wrapper: pattern_sheet itself (clay) is unchanged. Under bin/capped."""
    import os
    from pathlib import Path
    from . import resources
    if not os.environ.get("HIFIPUSHIE_CAPPED"):
        raise RuntimeError("pattern_sheet_diag renders: run it under /mnt/data/hifipushie/bin/capped")
    M, B = res["mesh"], res["body"]
    X = np.asarray(res.get("A", res["X0"]), float)
    lo, hi = X.min(0) - 0.08, X.max(0) + 0.08
    c, half = (lo + hi) / 2, np.maximum((hi - lo) / 2, 0.5)
    objs = [{"name": "body", "V": B.V, "F": B.T}, {"name": "garment", "V": X, "F": M["F"], "mesh": M}]
    p = Path(prefix).with_suffix(".png")
    with resources.heavy(f"diag sheet {p.name}", gb=4, gpu=True):
        return sheet([("garment", objs)], p, diag, views=views, resolution=resolution, box=(c - half, c + half),
                     aspect=0.62)


LOOK_DIAG = (("construction", ("panels", "seams", "turned")), ("strain", ("strain", "layers")))


def look_pairs(ref: list, ours: list, out_dir, views=("front", "three", "side", "back"), resolution: int = 640,
               box=None, aspect: float = 0.8, diag=LOOK_DIAG, gap: int = 8) -> dict:
    """Reviewer pairs, reference | ours, ONE view per PNG, clay AND diagnostic by default (coordinator 2026-10-19, after
    Joe asked why the debug colours weren't used): per view <out_dir>/pair_clay_<view>.png and, for each (label, modes)
    in `diag` (default: construction = panels + seams + turned, strain = strain + layers), pair_<label>_<view>.png, plus
    legend_<label>.png. diag=() is clay only and has to be asked for. ref / ours: cloth.render objects (the diag modes
    need "mesh" for strain / panels, "layer" for layers). Returns {"clay": [paths], label: [paths], "legend": {label:
    path}}. The caller holds resources.heavy (GPU) under bin/capped."""
    import os
    from PIL import Image
    from . import cloth
    os.makedirs(out_dir, exist_ok=True)
    VIEW = {"three": {"name": "three", "dir": [-0.65, -0.72, 0.15]}, "top": {"name": "top", "dir": [0.0, -0.05, 1.0]}}
    vs = [VIEW.get(v, v) if isinstance(v, str) else v for v in views]
    names = [v if isinstance(v, str) else v["name"] for v in vs]

    def pair(a, b, out):
        A, B = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
        im = Image.new("RGB", (A.width + B.width + gap, max(A.height, B.height)), (255, 255, 255))
        im.paste(A, (0, 0))
        im.paste(B, (A.width + gap, 0))
        im.save(out)
        return str(out)

    res = {"legend": {}}
    a = cloth.render(ref, f"{out_dir}/ref_clay", views=vs, resolution=resolution, box=box, aspect=aspect)
    b = cloth.render(ours, f"{out_dir}/ours_clay", views=vs, resolution=resolution, box=box, aspect=aspect)
    res["clay"] = [pair(x, y, f"{out_dir}/pair_clay_{n}.png") for x, y, n in zip(a, b, names)]
    for label, modes in diag or ():
        a, leg = render(ref, f"{out_dir}/ref_{label}", list(modes), views=vs, resolution=resolution, box=box,
                        aspect=aspect)
        b, leg2 = render(ours, f"{out_dir}/ours_{label}", list(modes), views=vs, resolution=resolution, box=box,
                         aspect=aspect)
        res[label] = [pair(x, y, f"{out_dir}/pair_{label}_{n}.png") for x, y, n in zip(a, b, names)]
        lg = list(leg) + [e for e in leg2 if e not in leg]
        legend_strip(lg, 2 * Image.open(a[0]).width + gap, strain="strain" in modes).save(f"{out_dir}/legend_{label}.png")
        res["legend"][label] = f"{out_dir}/legend_{label}.png"
    return res
