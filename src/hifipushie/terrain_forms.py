"""Forms cut into or stood on the ground: canyons (into a plateau, through horizontal strata), mesas, river water and
fords. A canyon kind needs these: ridges raised out of low ground made V-trenches with a hump for a rim.

canyons: {name: {"river": river, "rim": m, "width": m rim to rim, "floor": m,
                 "strata": {"bands": 3, "cliff": deg, "talus": m}}}
  The river gives the path and the floor's heights; the plateau stands at "rim" (default world.base). The walls climb
  through horizontal strata: each band a cliff (hard rock, stands) over a ledge (soft rock, lies back), with talus at
  the foot. Band elevations are the same all along the canyon, as in real ones; the ledges' slope is solved so the
  walls reach the rim at the asked width.
mesas: {name: {"at", "top": m, "radius": m, "cliff": deg, "talus": share of the height}}
fords: {name: {"on": "river@0.5", "width": m, "depth": m}}: a shallow, wide crossing routes may use.
Rivers carry water ("water": width m, default from the floor) that routes cross only at fords (or say they'd need a
bridge).
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import noise
from .terrain import smoothstep

TALUS = math.radians(34)


def canyon_rivers(spec) -> set:
    return {c["river"] for c in (spec.get("canyons") or {}).values()}


def carve(T):
    T.canyons = {}
    for name, c in (T.spec.get("canyons") or {}).items():
        _canyon(T, name, c)
    for name, m in (T.spec.get("mesas") or {}).items():
        _mesa(T, name, m)


def _strata(T, lo, rim, st, width_half, floor_half):
    """Absolute-elevation strata between lo and rim: (z grid, cot of the slope at each z), talus height, and the
    ledge slope solved so the widest (deepest) section reaches the rim at width_half."""
    n = int(st.get("bands", 3))
    cliff = math.radians(st.get("cliff", 78))
    depth = max(rim - lo, 1.0)
    talus_h = float(st.get("talus", 0.15 * depth))
    z = np.linspace(lo, rim, 1024)
    u = (z - (lo + talus_h)) / max(depth - talus_h, 1e-6)
    frac = (u * n) % 1.0
    is_cliff = (frac > 0.25) & (u >= 0)  # the upper three quarters of each band is cliff, the lower quarter ledge
    hc = 0.75 * (depth - talus_h)
    hl = 0.25 * (depth - talus_h)
    run = width_half - floor_half - talus_h / math.tan(TALUS) - hc / math.tan(cliff)
    ledge = math.atan(hl / run) if run > hl / math.tan(math.radians(60)) else math.radians(60)
    cot = np.where(is_cliff, 1 / math.tan(cliff), 1 / math.tan(ledge))
    cot[u < 0] = 1 / math.tan(TALUS)
    return z, cot, talus_h, math.degrees(ledge), run > 0


def _canyon(T, name, c):
    L = T.lines[c["river"]]
    rim = float(c.get("rim", T.world["base"]))
    half = float(c.get("width", 800)) / 2
    fh = float(c.get("floor", 60)) / 2
    lo = float(L.h.min())
    z, cot, talus_h, ledge_deg, fits = _strata(T, lo, rim, c.get("strata") or {}, half, fh)
    if not fits:
        T.warnings.append(f"canyon {name!r}: {rim - lo:.0f} m deep won't fit {2 * half:.0f} m rim to rim with its "
                          f"cliffs; the ledges stand at 60 deg and it comes out narrower. Widen it or make it shallower")
    C = np.r_[0, np.cumsum((cot[1:] + cot[:-1]) / 2 * np.diff(z))]  # horizontal run to climb from lo to each z
    d, i = cKDTree(L.xy).query(T.P, distance_upper_bound=half * 1.6 + 5 * T.cell)
    d, i = d.reshape(T.X.shape), np.minimum(i, len(L.xy) - 1).reshape(T.X.shape)
    near = np.isfinite(d)
    # the rim's plan wanders: alcoves and buttresses, a few hundred metres apart
    pts = np.c_[T.P, np.zeros(len(T.P))]
    wob = (noise.fbm(pts, 0.35 * half, 3, seed=81).reshape(T.X.shape) - 0.5) * 0.5 * half
    dd = np.where(near, np.maximum(d + wob, 0), np.inf) - fh
    hf = L.h[i]  # this section's floor
    # the run from this floor: talus first (from the local floor, whatever stratum it's in), then the strata above
    top_talus = hf + talus_h
    Ct = np.interp(top_talus, z, C)
    run_t = talus_h / math.tan(TALUS)
    zz = np.where(dd <= 0, hf,
                  np.where(dd <= run_t, hf + dd * math.tan(TALUS), np.interp(Ct + (dd - run_t), C, z)))
    zz = np.minimum(zz, rim)
    cut = near & (zz < T.H)
    T.H = np.where(cut, zz, T.H)
    wall = cut & (dd > 0)
    steep = np.interp(zz, z, cot) < 0.5  # cliff strata (cot < 0.5: steeper than ~63 deg) stand as hard rock
    cliffs = wall & steep & (dd > run_t)
    T.hard = T.hard | cliffs
    T.hardness = np.where(cliffs, 0.03, T.hardness)  # canyon cliffs stand: strong rock, not soil
    T.canyons[name] = {"river": L.name, "rim": rim, "half": half, "floor": 2 * fh, "ledge": ledge_deg,
                       "depth": rim - lo}


def _mesa(T, name, m):
    xy = T.address(m["at"])[0]
    r = float(m.get("radius", 150))
    ground = T.height(xy)
    top = float(m.get("top", ground + 0.15 * T.world["relief"]))
    hgt = top - ground
    if hgt <= 0:
        T.warnings.append(f"mesa {name!r}: its top {top:.0f} m isn't above the ground ({ground:.0f} m)")
        return
    cliff = math.radians(m.get("cliff", 80))
    talus = float(m.get("talus", 0.4)) * hgt
    pts = np.c_[T.P, np.full(len(T.P), 3.0)]
    d = np.hypot(T.X - xy[0], T.Y - xy[1])
    d = d * (1 + 0.18 * (noise.fbm(pts, 0.8 * r, 2, seed=91).reshape(T.X.shape) - 0.5) * 2)  # not a drum
    run_c = (hgt - talus) / math.tan(cliff)
    zz = np.where(d <= r, top, np.where(d <= r + run_c, top - (d - r) * math.tan(cliff),
                                        top - (hgt - talus) - (d - r - run_c) * math.tan(TALUS)))
    T.H = np.maximum(T.H, zz)
    ring = (d > r) & (d <= r + run_c)
    T.hard = T.hard | ring
    T.hardness = np.where(ring, 0.03, T.hardness)
    T.mesas = getattr(T, "mesas", {}) | {name: {"xy": xy.tolist(), "top": top, "radius": r}}


def rim_address(T, ref):
    """"<canyon>.<side>_rim@s": on the plateau at the canyon's lip, s along its river; side = west/east/north/south
    or left/right (looking downstream). Returns (xy, h, direction into the canyon)."""
    head, _, s = ref.partition("@")
    cname, side = head.rsplit(".", 1)
    side = side[:-len("_rim")]
    cy = T.canyons[cname]
    L = T.lines[cy["river"]]
    xy, h, tan = L.at(float(s) if s else 0.5)
    nrm = np.array([-tan[1], tan[0]])  # left bank
    want = {"west": (-1, 0), "east": (1, 0), "north": (0, 1), "south": (0, -1)}
    if side in want:
        sgn = 1 if nrm @ np.array(want[side]) >= 0 else -1
    else:
        sgn = 1 if side == "left" else -1
    # the lip along this line (the rim's plan wanders): scanning in from well outside, the last point before the
    # ground falls away below the plateau
    ds = np.arange(1.7 * cy["half"], 0, -T.cell / 2)
    line = xy + sgn * nrm * ds[:, None]
    hs = T.sample(line)
    plateau = np.median(hs[:5])
    falls = np.nonzero(hs < plateau - max(3.0, 0.03 * cy["depth"]))[0]
    k = max(int(falls[0]) - 1, 0) if len(falls) else len(ds) - 1
    out = line[k]
    return out, T.height(out), -sgn * nrm


def water(T):
    """Rivers carry water (a channel a metre or so deep) except where they're dry; fords are wide and shallow."""
    fords = []
    for name, f in (T.spec.get("fords") or {}).items():
        xy, _, _ = T.address(f["on"])
        fords.append((name, xy, float(f.get("width", 15)), float(f.get("depth", 0.3))))
    T.fords = {n: {"xy": xy.tolist(), "width": w} for n, xy, w, _ in fords}
    T.river_water = np.zeros(T.X.shape, bool)
    T.ford_mask = np.zeros(T.X.shape, bool)
    for L in (L for L in T.lines.values() if L.kind == "river"):
        r = (T.spec.get("rivers") or {}).get(L.name, {})
        wd = r.get("water", max(3.0, min(L.props["floor"] / 3, 25.0)))
        if not wd:
            continue
        d, i = cKDTree(L.xy).query(T.P, distance_upper_bound=wd)
        d, i = d.reshape(T.X.shape), np.minimum(i, len(L.xy) - 1).reshape(T.X.shape)
        wet = np.isfinite(d) & np.isnan(T.water)
        level = L.h[i] + 0.2
        depth = 1.0
        for _, fxy, fw, fd in fords:
            nearf = np.hypot(T.X - fxy[0], T.Y - fxy[1]) < fw
            T.ford_mask |= nearf & wet
            depth = np.where(nearf, fd, depth)
        bed = level - depth * (1 - (d / wd) ** 2)
        T.H = np.where(wet, np.minimum(T.H, bed), T.H)
        T.water = np.where(wet, level, T.water)
        T.river_water |= wet
