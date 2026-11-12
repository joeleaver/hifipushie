"""The water as built (wet runs, the wet design, the flow report), and the cobble and silt swatches. Part of terrain streams (terrain_stream.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import terrain_stream
from .terrain_stream import _ss, config
from .terrain_stream_streams import Streams

def _wet_run(wet, step, start):
    """Per row of `wet` (samples out from a centre, `step` apart, the first at `step`): how far the water reaches,
    contiguous from the centre (the first `start` m always counted), dry runs shorter than WET_GAP bridged; and whether
    a rim ended it (False: wet to the row's end, ground falling away that holds no standing water at that level)."""
    n = wet.shape[1]
    o = (np.arange(n) + 1) * step
    w = wet | (o[None] <= start[:, None])
    gap = max(1, int(round(terrain_stream.WET_GAP / step)))
    dry = (~w).astype(np.int32)
    cs = np.cumsum(np.c_[np.zeros(len(w), np.int32), dry], 1)
    ends = (cs[:, gap:] - cs[:, :-gap]) == gap  # (a dry run `gap` long starts here)
    rim = ends.any(1)
    first = np.where(rim, ends.argmax(1), n)
    idx = np.where(w & (np.arange(n)[None] < first[:, None]), np.arange(n)[None], -1).max(1)
    return np.where(idx >= 0, o[np.maximum(idx, 0)], 0.0), rim


def wet_design(T, streams=None):
    """The water as the built ground holds it, for the designs a game trims its water to (pushieworld note 126: meta's
    widths were river_water_lines' HALF widths, and the cut banks drop ground beside the channel under the water).
    Per river, per water-line sample: the full width that covers the water across it, 2 x the farther side where a
    bank closes it (ground falling away holds no standing water), never under 2 x the design's half width; samples
    over a fall's lip band and pool keep the design (the pool says it). Per fall: the pool's wet radius at its level
    where its basin closes on every side but downstream, else its radius (None in the sea). Ground = the terrain grid
    as the field reads it (cubic B-spline) plus the stream beds' shape (Streams.dz). Cached on T."""
    got = getattr(T, "_wet_design", None)
    if got is not None:
        return got
    lines = getattr(T, "river_water_lines", None) or {}
    if streams is None and lines:
        cfg = config(T)
        streams = Streams(T, cfg) if cfg is not None else None
    streams = streams if streams is not None and streams.any else None
    H = np.ascontiguousarray(T.H, float)
    x0, y0, c = float(T.xs[0]), float(T.ys[0]), float(T.cell)

    def ground(P):
        h = ndimage.map_coordinates(H, [(P[:, 1] - y0) / c, (P[:, 0] - x0) / c], order=3, prefilter=False,
                                    mode="nearest")
        if streams is not None:
            h = h + streams.dz(P[:, 0], P[:, 1], h)
        return h

    o = np.arange(1, int(terrain_stream.WET_REACH / terrain_stream.WET_STEP) + 1) * terrain_stream.WET_STEP
    pools = []
    for f in getattr(T, "falls", None) or []:
        pl = f.get("pool") or {}
        if not pl.get("xyz") or pl.get("depth") is None:  # (the sea)
            pools.append(None)
            continue
        pc, lev, r0 = np.array(pl["xyz"][:2], float), float(pl["xyz"][2]), float(pl.get("radius") or 0.0)
        # rays out from the centre at its level, up the river and to the sides (downstream the river runs on at its
        # own, lower level), each as far as the ground stays under the level. Where the ground falls away on some
        # side (a pool perched on a hillside) the water runs off there, it doesn't stand at the pool's level
        ang = np.linspace(0, 2 * np.pi, 72, endpoint=False)
        d = np.c_[np.cos(ang), np.sin(ang)]
        up = d @ (np.asarray(f["flow"], float) / max(np.linalg.norm(f["flow"]), 1e-9)) < 0.5
        P = pc[None, None] + o[None, :, None] * d[up][:, None, :]
        g = ground(P.reshape(-1, 2)).reshape(int(up.sum()), len(o))
        r, rim = _wet_run(g < lev - terrain_stream.WET_DEEP, terrain_stream.WET_STEP, np.full(int(up.sum()), r0))
        # (a basin only if every side closes: an open side drains it to the outlet's level, the pool's own radius)
        pools.append(round(float(max(r0, r.max()) if rim.all() else r0), 2))
    rivers, flow = {}, {}
    for nm, rw in lines.items():
        xy = np.asarray(rw["xy"], float)
        lv = np.asarray(rw["level"], float)
        wd = np.asarray(rw["width"], float)
        out = 2 * wd
        flow[nm] = np.full(len(xy), np.nan)
        live = wd > 0
        for f, wr in zip(getattr(T, "falls", None) or [], pools):  # (a fall's lip and pool: the pool's wet radius
            if f["river"] != nm:  # says it; across the lip band and the amphitheatre a cross-section is meaningless)
                continue
            lc = np.mean(np.array(f["lip"], float)[:, :2], 0)
            tf = np.asarray(f["flow"], float) / max(np.linalg.norm(f["flow"]), 1e-9)
            pl = (f.get("pool") or {}).get("xyz")
            reach = (float((np.array(pl[:2]) - lc) @ tf) + (wr or 0.0)) if pl else 0.0
            reach = max(reach, 2.0)
            u = (xy - lc) @ tf
            live &= ~((u > -terrain_stream.FALL_HOLD) & (u < reach) & (np.hypot(*(xy - lc).T) < reach + terrain_stream.FALL_HOLD))
        k = np.flatnonzero(live)
        if len(k) and len(xy) > 1:
            t = np.gradient(xy, axis=0)
            t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
            n = np.c_[-t[:, 1], t[:, 0]]
            far = np.zeros(len(k))
            area, perim = np.zeros(len(k)), np.zeros(len(k))
            g0 = ground(xy[k])
            for side in (1.0, -1.0):
                for a in range(0, len(k), 1000):
                    kk = k[a:a + 1000]
                    P = xy[kk, None, :] + side * o[None, :, None] * n[kk, None, :]
                    g = ground(P.reshape(-1, 2)).reshape(len(kk), len(o))
                    r, rim = _wet_run(g < lv[kk, None] - terrain_stream.WET_DEEP, terrain_stream.WET_STEP, wd[kk])
                    far[a:a + len(kk)] = np.maximum(far[a:a + len(kk)], np.where(rim, r, 0.0))
                    # the cross-section's wet area and wetted perimeter out to where the water ends on this side
                    inside = o[None] <= r[:, None] + 1e-9
                    dep = np.clip(lv[kk, None] - g, 0, None) * inside
                    area[a:a + len(kk)] += dep.sum(1) * terrain_stream.WET_STEP
                    gg = np.c_[g0[a:a + len(kk)], g]
                    seg = np.hypot(terrain_stream.WET_STEP, np.diff(gg, axis=1)) * (np.c_[inside[:, :1], inside[:, 1:]] & (
                        np.minimum(gg[:, 1:], gg[:, :-1]) < lv[kk, None]))
                    perim[a:a + len(kk)] += seg.sum(1)
            out[k] = 2 * np.maximum(wd[k], far)
            # the flow the channel carries at its design level (Manning: Q = A R^(2/3) S^(1/2) / n), the water's own
            # grade (steps at falls left out), n from gravel (0.035) to a boulder torrent (0.07) with the grade
            s_ = np.r_[np.linalg.norm(np.diff(xy, axis=0), axis=1), 1.0]
            dl = np.r_[np.clip(-np.diff(lv), 0, None), 0.0] / np.maximum(s_, 1e-6)
            dl = np.where(dl > 0.6, np.nan, dl)  # (a fall's step)
            win = max(3, int(30.0 / max(float(np.median(s_)), 1e-3)))
            num = ndimage.uniform_filter1d(np.nan_to_num(dl), win, mode="nearest")
            den = ndimage.uniform_filter1d(np.isfinite(dl).astype(float), win, mode="nearest")
            S = np.clip(num / np.maximum(den, 1e-6), terrain_stream.MIN_GRADE, None)[k]
            man = 0.035 + 0.035 * np.clip(S / 0.2, 0, 1)
            R = area / np.maximum(perim, 1e-6)
            Q = np.full(len(xy), np.nan)
            Q[k] = area * R ** (2.0 / 3.0) * np.sqrt(S) / man
            flow[nm] = Q
        rivers[nm] = out
    T._wet_design = {"rivers": rivers, "pools": pools, "flow": flow}
    return T._wet_design


def report_flow(T):
    """Per river: the flow its channel carries at its design level, as built (wet_design's Manning figure), and the
    reach that carries least (pushieworld note 121: a game fed every river 8 m3/s, ten times what its becks hold)."""
    if not getattr(T, "river_water_lines", None):
        return []
    D = wet_design(T)
    out = []
    for nm, q in D.get("flow", {}).items():
        q = np.asarray(q, float)
        ok = np.isfinite(q)
        if not ok.any():
            continue
        xy = np.asarray(T.river_water_lines[nm]["xy"], float)
        i = int(np.flatnonzero(ok)[np.argmin(q[ok])])
        line = (f"river {nm}: its channel carries {np.nanpercentile(q, 10):.2g} m3/s at its design level "
                f"(10th percentile; median {np.nanmedian(q):.2g}, least {q[i]:.2g} at "
                f"[{xy[i, 0]:.0f}, {xy[i, 1]:.0f}]): meta.json rivers.{nm}.design_flow_m3s; more spills over the "
                f"banks (a wider `water` or a deeper valley holds more)")
        dry = np.flatnonzero(ok & (q < 0.01))
        if len(dry):
            st = np.r_[np.linalg.norm(np.diff(xy, axis=0), axis=1), 0.0]
            line += (f". Its bed stands at or over its water's level for {st[dry].sum():.0f} m (from "
                     f"[{xy[dry[0], 0]:.0f}, {xy[dry[0], 1]:.0f}]): a water simulation runs a film over the ground there")
        out.append(line)
    return out


# ---------------------------------------------------------------------------------------------- swatches
def cobble_swatch(size=2.0, res=256, seed=4251):
    """A tileable bed swatch (top view, periodic): rounded cobbles and pebbles packed on gravel, 3-22 cm (a few big,
    many small: no two rows alike), each its own tone (grey, buff, a few dark or pale), dark wet gaps between, grit on
    the stones. Returns what terrain_ground.grass_swatch returns."""
    from .terrain_swatch import spectral
    L = float(size)
    n = int(round(L * res))
    rng = np.random.default_rng(seed)
    t = L / n
    hgt = 0.004 * spectral(n, 1.2, seed + 1, lo=10)
    tone = 0.62 + 0.10 * spectral(n, 0.8, seed + 2, lo=12)  # (the gravel between: darker)
    tint = np.zeros((n, n, 3))
    ns = int(1150 * (L / 2.0) ** 2)  # (gravel shows between: wall-to-wall domes read as bubble wrap)
    rad = np.clip(0.028 * np.exp(0.55 * rng.standard_normal(ns)), 0.012, 0.11)
    order = np.argsort(rad)  # (small first: the big stones lie on top)
    cen = rng.random((ns, 2)) * n
    # stones gather: patches of plain gravel between drifts of cobbles (evenly spread domes of one height were the
    # "bubble wrap"); the big ones stand anywhere
    drift = spectral(n, 3.0, seed + 5, lo=2)
    drift = (drift - drift.min()) / max(float(np.ptp(drift)), 1e-9)
    for q in order:
        r = rad[q] / t
        cx, cy = cen[q]
        if rad[q] < 0.06 and rng.random() > _ss(0.3, 0.6, float(drift[int(cy) % n, int(cx) % n])) + 0.12:
            continue
        el = rng.uniform(0.45, 1.0)
        a = rng.uniform(0, np.pi)
        ri = int(r + 2)
        ii, jj = np.mgrid[int(cy) - ri:int(cy) + ri + 1, int(cx) - ri:int(cx) + ri + 1]
        dx, dy = jj - cx, ii - cy
        ca, sa = np.cos(a), np.sin(a)
        d2 = ((dx * ca + dy * sa) / r) ** 2 + ((-dx * sa + dy * ca) / (r * el)) ** 2
        # (flattish water-worn tops, each stone sunk to its own depth and lying at its own tilt)
        sunk, tl, ta = rng.uniform(0.2, 0.55), rng.uniform(0.0, 0.45), rng.uniform(0, 2 * np.pi)
        dome = rad[q] * sunk * np.sqrt(np.clip(1 - d2, 0, 1)) ** 0.6 * \
            (1 + tl * (dx * np.cos(ta) + dy * np.sin(ta)) / r)
        sl = (ii % n, jj % n)
        m = (d2 < 1) & (dome + 0.2 * rad[q] > hgt[sl])
        if not m.any():
            continue
        u = rng.random()
        tn = rng.uniform(0.85, 1.2) if u < 0.75 else (rng.uniform(0.55, 0.75) if u < 0.9 else rng.uniform(1.3, 1.5))
        hv, tv, cv = hgt[sl], tone[sl], tint[sl]
        hv[m] = np.maximum(hv[m], dome[m])
        tv[m] = tn * (0.86 + 0.14 * np.sqrt(np.clip(1 - d2[m], 0, 1)))  # (a little darker toward each stone's foot)
        cv[m] = rng.normal(0, 0.035) * np.array([1.0, 0.2, -1.0])
        hgt[sl], tone[sl], tint[sl] = hv, tv, cv
    grit = spectral(n, 0.5, seed + 3, lo=30)
    tone = tone * (1 + 0.06 * grit)
    # the gaps between stones are deep and dark (shadowed, wet)
    low = ndimage.gaussian_filter(hgt, 2.0, mode="wrap")
    tone = tone * (0.8 + 0.2 * _ss(-0.006, 0.004, hgt - low))
    alb = tone[..., None] * (1 + tint)
    alb = alb / alb.reshape(-1, 3).mean(0)
    hgt = ndimage.gaussian_filter(hgt, 0.6, mode="wrap")
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * t)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * t)
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    return {"albedo": alb, "height": hgt - hgt.mean(), "normal": nrm, "rough": np.ones((n, n)), "size_m": L,
            "texels_per_m": n / L, "n": n}


def silt_swatch(size=2.0, res=256, seed=4253):
    """A tileable silt / damp earth swatch: smooth fine sediment with faint current ripples in patches, a scatter of
    small pebbles half sunk, dark leaf and twig flecks."""
    from .terrain_swatch import spectral
    L = float(size)
    n = int(round(L * res))
    rng = np.random.default_rng(seed)
    t = L / n
    yy, xx = np.mgrid[0:n, 0:n] * t
    mx, my = int(round(0.3 * L / 0.06)), int(round(0.95 * L / 0.06))
    warp = spectral(n, 2.4, seed + 1, lo=3) * 1.3
    ph = 2 * np.pi * (mx * xx + my * yy) / L + warp * 2 * np.pi
    patch = np.clip(0.3 + 1.6 * spectral(n, 2.0, seed + 2, lo=4), 0, 1)
    hgt = 0.002 * np.sin(ph) * patch + 0.003 * spectral(n, 1.5, seed + 4, lo=6)
    alb = 1 + 0.07 * spectral(n, 1.0, seed + 3, lo=6) + 0.03 * np.sin(ph) * patch
    for kind, cnt in (("pebble", int(90 * (L / 2.0) ** 2)), ("fleck", int(160 * (L / 2.0) ** 2))):
        c = rng.random((cnt, 2)) * n
        for cx, cy in c:
            if kind == "pebble":
                r, el, tn = rng.uniform(0.006, 0.022) / t, rng.uniform(0.6, 1.0), rng.uniform(0.75, 1.3)
            else:
                r, el, tn = rng.uniform(0.01, 0.03) / t, rng.uniform(0.15, 0.4), rng.uniform(0.45, 0.7)
            a = rng.uniform(0, np.pi)
            ri = int(r + 2)
            ii, jj = np.mgrid[int(cy) - ri:int(cy) + ri + 1, int(cx) - ri:int(cx) + ri + 1]
            dx, dy = jj - cx, ii - cy
            ca, sa = np.cos(a), np.sin(a)
            d = np.sqrt(((dx * ca + dy * sa) / r) ** 2 + ((-dx * sa + dy * ca) / (r * el)) ** 2)
            m = np.clip((1.15 - d) * 3, 0, 1)
            sl = (ii % n, jj % n)
            alb[sl] = alb[sl] * (1 - m) + tn * m
            if kind == "pebble":
                hgt[sl] = np.maximum(hgt[sl], 0.5 * r * t * np.sqrt(np.clip(1 - d * d, 0, 1)))
    alb = np.repeat(alb[..., None], 3, -1) * np.array([1.0, 0.98, 0.95])
    alb = alb / alb.reshape(-1, 3).mean(0)
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * t)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * t)
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    return {"albedo": alb, "height": hgt - hgt.mean(), "normal": nrm, "rough": np.ones((n, n)), "size_m": L,
            "texels_per_m": n / L, "n": n}
