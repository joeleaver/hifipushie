"""River-corridor heightmaps (pushieworld note 118: gdamp's nested 0.25 m water solve). Along every river's water path,
round every lake's shore and every fall's plunge pool, buffered `buffer` m, rectangles of at most `size` m (axis
aligned, overlapping where they meet) sampled every `spacing` m from the export's own field: the TOP surface as the
tiles build it (the ground tiles' heightmap, i.e. the ground with its stream beds, banks and fall faces, and over it
the cliff meshes' rock where they stand higher), no clutter. Not a resample of the 1 m grid: the bed's pools and
riffles, a fall's face (a step between texels) and the rock at a lip are the field's own.

Opt-in: export.tiles "corridors": true | {"spacing", "buffer", "size"}. Files corridors/corridor_<n>.npy, float32,
row 0 north, column 0 west; manifest "corridors" lists each rect (file, extent [[x0, y0], [x1, y1]] east / north m of
the outer samples, cols, rows, spacing, what it follows)."""
from __future__ import annotations

import math

import numpy as np

SPACING = 0.25
BUFFER = 15.0  # m each side of the water's edge
SIZE = 128.0  # m: a rect's longest side at most
SCAN_UP = 10.0  # m over the ground a cliff mesh's top is looked for (a lip's rock, relief built out)
SCAN_RISE = 20  # times SCAN_UP more where that is still rock (a stack, rock built out over a sunk ground)
SCAN_DOWN = 6.0  # m under it (a sunk front: the ground is on top there anyway)
SCAN_STEP_MAX = 0.5  # m: the longest step down (a thin lip of rock is never stepped over)
SCAN_MIN = 0.02
CHUNK = 200_000  # points per field call


def config(cfg) -> dict | None:
    c = cfg.get("corridors")
    if not c:
        return None
    c = c if isinstance(c, dict) else {}
    return {"spacing": float(c.get("spacing", SPACING)), "buffer": float(c.get("buffer", BUFFER)),
            "size": float(c.get("size", SIZE))}


def _chunks(xy, pad, size, what):
    """Axis-aligned boxes covering a polyline buffered by pad (per point), each side <= size: a new box starts (at the
    last point, so they overlap) when the next point would make the box too big."""
    out = []
    pad = np.broadcast_to(np.asarray(pad, float), (len(xy),))
    i = 0
    while i < len(xy):
        lo, hi = xy[i] - pad[i], xy[i] + pad[i]
        j = i + 1
        while j < len(xy):
            l2, h2 = np.minimum(lo, xy[j] - pad[j]), np.maximum(hi, xy[j] + pad[j])
            if np.any(h2 - l2 > size):
                break
            lo, hi = l2, h2
            j += 1
        out.append({"lo": lo, "hi": hi, "what": what})
        if j >= len(xy):
            break
        i = max(j - 1, i + 1)
    return out


def rects(T, c, box=None) -> list[dict]:
    """The corridors' rects (lo, hi, what), snapped out to the spacing's lattice, inside the terrain (and `box`)."""
    from .terrain_mesh import lake_outlines
    buf, size, sp = c["buffer"], c["size"], c["spacing"]
    out = []
    for name, w in (getattr(T, "river_water_lines", None) or {}).items():
        xy = np.asarray(w["xy"], float)[:, :2]
        hw = 0.5 * np.asarray(w.get("width", 0.0), float)
        hw = np.broadcast_to(np.nan_to_num(hw), (len(xy),))
        pad = np.minimum(hw + buf, 0.5 * size)
        out += _chunks(xy, pad, size, f"river {name}")
    for name, lk in lake_outlines(T).items():
        for ring in lk["outline"]:
            out += _chunks(np.asarray(ring, float), buf, size, f"lake {name} shore")
    for f in getattr(T, "falls", None) or []:
        pool = f.get("pool") or {}
        if not pool.get("xyz"):
            continue
        r = min(float(pool.get("radius", 0.0)) + buf, 0.5 * size)
        xy = np.asarray(pool["xyz"][:2], float)
        out.append({"lo": xy - r, "hi": xy + r, "what": f"fall pool ({f.get('river', '')})".replace(" ()", "")})
    ext_lo = np.array([T.xs[0], T.ys[0]], float)
    ext_hi = np.array([T.xs[-1], T.ys[-1]], float)
    if box is not None:
        ext_lo, ext_hi = np.maximum(ext_lo, box[0]), np.minimum(ext_hi, box[1])
    keep = []
    for r in out:
        lo = np.floor(np.maximum(r["lo"], ext_lo) / sp) * sp
        hi = np.ceil(np.minimum(r["hi"], ext_hi) / sp) * sp
        hi = np.minimum(hi, lo + math.floor(size / sp) * sp)
        if np.all(hi - lo >= 4 * sp):
            keep.append({**r, "lo": lo, "hi": hi})
    # (a fall's pool inside a river's rect already: not twice)
    inside = lambda a, b: np.all(a["lo"] >= b["lo"] - 1e-9) and np.all(a["hi"] <= b["hi"] + 1e-9)
    return [r for r in keep if not r["what"].startswith("fall pool")
            or not any(inside(r, o) for o in keep if not o["what"].startswith("fall pool"))]


def pushed_grid(region, xs, ys):
    """`region.height` on the grid xs (west to east) x ys (north to south) at once: its push ball's offsets (-push,
    -push + 0.25, ...) step 0.25 m, so with a 0.25 m spacing every offset point is a point of one grid (the samples'
    grid moved by -push) evaluated once, and the ball's minimum is taken over shifted views of it (961 column calls a
    point before: 25 s for a fall's 40 k samples). Equal to `region.height` but for float rounding. None if the
    spacing isn't 0.25 m."""
    from scipy import ndimage
    if len(xs) < 2 or len(ys) < 2 or abs(float(xs[1] - xs[0]) - 0.25) > 1e-9 or abs(float(ys[1] - ys[0]) + 0.25) > 1e-9:
        return None
    off = np.arange(-region.push, region.push + 1e-9, 0.25)  # (exactly `height`'s offsets)
    no = len(off)
    xe = xs[0] + off[0] + 0.25 * np.arange(len(xs) + no - 1)  # x_c + off[k] = xe[c + k]
    ye = ys[0] + off[-1] - 0.25 * np.arange(len(ys) + no - 1)  # y_r + off[l] = ye[r + no - 1 - l]
    Xe, Ye = np.meshgrid(xe, ye)
    He = np.asarray(region.base.column(Xe.ravel(), Ye.ravel())[0], float).reshape(Xe.shape)
    X, Y = np.meshgrid(xs, ys)
    h = np.asarray(region.base.column(X.ravel(), Y.ravel())[0], float).reshape(X.shape)
    Rr = ndimage.map_coordinates(region.Rg, [(X - region.G.origin[0]) / region.d, (Y - region.G.origin[1]) / region.d],
                                 order=1, mode="nearest")
    act = Rr > 1e-3
    if not act.any():
        return h
    best = h.copy()
    for k in range(no):
        for l in range(no):
            r = math.hypot(off[k], off[l])
            if r > region.push + 1e-9:
                continue
            ok = act & (r < Rr)
            if not ok.any():
                continue
            hh = He[no - 1 - l:no - 1 - l + len(ys), k:k + len(xs)]
            best = np.where(ok, np.minimum(best, hh - np.sqrt(np.maximum(Rr * Rr - r * r, 0.0))), best)
    return np.where(act, np.minimum(h, best), h)


def top(field, region, x, y, g=None):
    """The top surface as the tiles build it at columns: the ground tiles' heightmap (`region.height`: the ground with
    its edits, pushed under the cliffs) or the column's ground (full mode), and over it the meshed field's topmost
    crossing (the cliff meshes) where that stands higher. (The pushed heightmap is never above the ground's column, so
    where the cliff mesh's top is at or over the column the heightmap isn't needed: its push ball was 90% of the
    time on a fall's rect.)"""
    x, y = np.asarray(x, float), np.asarray(y, float)
    h0 = np.asarray(field.column(x, y)[0], float)
    if region is not None:
        cand = region.s(x, y) > 0
        for lo, hi in field._boxes():
            cand |= (x >= lo[0]) & (x <= hi[0]) & (y >= lo[1]) & (y <= hi[1])
        k = np.flatnonzero(cand)
    else:
        v0 = field.value(np.c_[x, y, h0])
        k = np.flatnonzero(np.abs(v0) > 0.005)
    zc = np.full(len(x), -np.inf)
    # down from SCAN_UP over the ground, each step half the field's value (a distance, about: rock relief makes it a
    # little steeper than 1) and at most SCAN_STEP_MAX, until it reads rock; then bisection between the last air and
    # that. (Every 0.25 m from 10 m over to 6 m under took 65 calls a point: 5 of the island's 5.5 minutes)
    for a in range(0, len(k), CHUNK):
        kk = k[a:a + CHUNK]
        # the scan starts in the air: SCAN_UP over the ground, or higher where that is still rock (a sea cliff's rock
        # built out over a sunk ground, a stack: the first point read rock and the column fell back to the heightmap,
        # under the mesh by metres)
        z0 = h0[kk] + SCAN_UP
        up = np.flatnonzero(field.value(np.c_[x[kk], y[kk], z0]) <= 0)
        for _ in range(SCAN_RISE):
            if not len(up):
                break
            z0[up] += SCAN_UP
            up = up[field.value(np.c_[x[kk[up]], y[kk[up]], z0[up]]) <= 0]
        z = z0.copy()
        za = z.copy()
        live = np.setdiff1d(np.arange(len(kk)), up)  # (still rock SCAN_RISE x SCAN_UP up: left to the heightmap)
        hitz = np.full(len(kk), np.nan)
        for _ in range(int((z0.max() - (h0[kk] - SCAN_DOWN).min()) / SCAN_MIN) + 1 if len(kk) else 0):
            if not len(live):
                break
            v = field.value(np.c_[x[kk[live]], y[kk[live]], z[live]])
            rock = v <= 0
            hitz[live[rock]] = z[live[rock]]
            go = ~rock
            za[live[go]] = z[live[go]]
            z[live[go]] -= np.clip(0.5 * v[go], SCAN_MIN, SCAN_STEP_MAX)
            live = live[go]
            live = live[z[live] >= h0[kk[live]] - SCAN_DOWN]
        hit = np.flatnonzero(np.isfinite(hitz) & (hitz < z0))  # (rock at the first point: none found)
        if not len(hit):
            continue
        q = kk[hit]
        lo_, hi_ = hitz[hit], za[hit]  # (rock, air)
        for _ in range(9):
            zm = 0.5 * (lo_ + hi_)
            air = field.value(np.c_[x[q], y[q], zm]) > 0
            hi_, lo_ = np.where(air, zm, hi_), np.where(air, lo_, zm)
        zc[q] = 0.5 * (lo_ + hi_)
    if region is None:
        return np.where(np.isfinite(zc), zc, h0)
    out = zc.copy()
    need = np.flatnonzero(zc < h0 - 1e-6)  # (the ground tile may be on top: its pushed heightmap)
    for a in range(0, len(need), CHUNK):
        q = need[a:a + CHUNK]
        out[q] = np.maximum(zc[q], g[q] if g is not None else np.asarray(region.height(x[q], y[q]), float))
    return out


def write(T, field, region, out, cfg, box=None, log=print) -> dict | None:
    """Every corridor rect sampled and written (corridors/corridor_<n>.npy); the manifest's "corridors" entry."""
    import time
    c = config(cfg)
    if c is None:
        return None
    t0 = time.time()
    sp = c["spacing"]
    (out / "corridors").mkdir(exist_ok=True)
    entries, n_pts = [], 0
    for n, r in enumerate(rects(T, c, box)):
        (x0, y0), (x1, y1) = r["lo"], r["hi"]
        cols, rows = int(round((x1 - x0) / sp)) + 1, int(round((y1 - y0) / sp)) + 1
        xs = x0 + sp * np.arange(cols)
        ys = y1 - sp * np.arange(rows)  # (row 0 north)
        X, Y = np.meshgrid(xs, ys)
        g = pushed_grid(region, xs, ys) if region is not None else None
        h = top(field, region, X.ravel(), Y.ravel(), None if g is None else g.ravel()).reshape(rows, cols)
        h = h.astype(np.float32)
        fn = f"corridors/corridor_{n}.npy"
        np.save(out / fn, np.ascontiguousarray(h))
        n_pts += h.size
        entries.append({"file": fn, "extent": [[round(float(x0), 3), round(float(y0), 3)],
                                               [round(float(x1), 3), round(float(y1), 3)]],
                        "cols": cols, "rows": rows, "spacing": sp, "follows": r["what"]})
    took = time.time() - t0
    mb = 4 * n_pts / 2 ** 20
    log(f"corridors: {len(entries)} rects at {sp:g} m ({n_pts / 1e6:.1f} M samples, {mb:.0f} MB) in {took:.0f} s")
    return {"rects": entries, "spacing": sp, "buffer_m": c["buffer"], "max_side_m": c["size"],
            "format": "float32 .npy absolute metres, row 0 north (the extent's y1), column 0 west (x0); extent = the "
                      "outer samples' centres",
            "what": "the top surface as the tiles build it (ground with its stream beds, banks and fall faces; the "
                    "cliff meshes' rock where it stands higher), sampled from the export's field, no clutter",
            "seconds": round(took, 1), "megabytes": round(mb, 1)}
