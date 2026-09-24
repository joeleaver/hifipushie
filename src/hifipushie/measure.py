"""Cross-section measurements: slice the exact SDF with planes and report sizes as numbers.

Slices sample the analytic field (not the voxel grid), so numbers don't depend on build resolution.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from .sdf import field_at
from .spec import SpecError, bone_frame, compile_prims, expand_mirror, resolve_point

AXES = {"x": 0, "y": 1, "z": 2}
N = 161  # samples per side of a slice plane


def _plane(prims, centre, u, v, half):
    """Inside mask on a square plane spanned by unit vectors u, v; returns mask and 1-D coords."""
    s = np.linspace(-half, half, N)
    pts = centre + s[:, None, None] * u + s[None, :, None] * v
    return field_at(prims, pts) < 0, s


def _extent(mask, s):
    iu, iv = np.nonzero(mask)
    step = s[1] - s[0]
    return (s[iu.min()], s[iu.max()], s[iv.min()], s[iv.max()], len(iu) * step * step)


def _bone_slice(prims, centre, u, v, r0):
    """Section of the connected part that contains the bone axis, growing the plane until it fits."""
    half = 3.0 * r0
    for _ in range(6):
        mask, s = _plane(prims, centre, u, v, half)
        c = N // 2
        if not mask[c, c]:
            return None
        lab, _ = ndimage.label(mask)
        part = lab == lab[c, c]
        if not (part[0].any() or part[-1].any() or part[:, 0].any() or part[:, -1].any()):
            return _extent(part, s)
        half *= 2
    return _extent(part, s)


def _ray(prims, centre, d, reach):
    """Distance from centre along d to the first outside point (linearly refined), up to reach."""
    s = np.linspace(0, reach, 400)
    f = field_at(prims, centre + s[:, None] * d)
    out = np.nonzero(f >= 0)[0]
    if len(out) == 0:
        return reach
    i = out[0]
    if i == 0:
        return 0.0
    return float(s[i - 1] + (s[i] - s[i - 1]) * -f[i - 1] / (f[i] - f[i - 1]))


def _dirname(vec) -> str:
    """Nearest world axis as a label, e.g. '+X' or '~-Z' when not exact."""
    i = int(np.argmax(np.abs(vec)))
    label = ("+" if vec[i] > 0 else "-") + "XYZ"[i]
    return label if abs(vec[i]) > 0.99 else "~" + label


def along_bones(spec: dict, bones: list[str], samples: int) -> str:
    s = expand_mirror(spec)
    prims = compile_prims(spec)
    lines = []
    for name in bones:
        b = s["bones"].get(name)
        if b is None:
            raise SpecError(f"unknown bone {name!r}")
        a, bb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
        w, axis, h = bone_frame(a, bb, b.get("up"))
        ra = float(b.get("r_a") or s["joints"][b["a"]].get("r", 0.05))
        rb = float(b.get("r_b") or s["joints"][b["b"]].get("r", 0.05))
        r0 = max(ra, rb) * max(1.0, *(b.get("flat") or [1, 1]))
        lines.append(f"bone {name}: {b['a']} -> {b['b']}, len {np.linalg.norm(bb - a):.3f}; "
                     f"width axis {_dirname(w)}, height axis {_dirname(h)}")
        lines.append("   t    centre (x, y, z)          width  height    w-     w+     h-     h+    area")
        for t in np.linspace(0, 1, samples):
            c = a + (bb - a) * t
            pos = "(" + ", ".join(f"{x:6.3f}" for x in c) + ")"
            sec = _bone_slice(prims, c, w, h, r0)
            if sec is None:
                lines.append(f"  {t:4.2f}  {pos}   axis point is outside the surface")
                continue
            wm, wp, hm, hp = (_ray(prims, c, d, 8 * r0) for d in (-w, w, -h, h))
            lines.append(f"  {t:4.2f}  {pos}   {wm + wp:6.3f}  {hm + hp:6.3f}  "
                         f"{wm:5.3f}  {wp:5.3f}  {hm:5.3f}  {hp:5.3f}  {sec[4]:7.4f}")
    lines.append("w-/w+/h-/h+ = distance from the bone axis to the surface along each section axis "
                 "(width = w- + w+); area = the whole connected section, so it jumps where the bone "
                 "merges into the body.")
    return "\n".join(lines)


def along_axis(spec: dict, axis: str, samples: int, lo: float | None, hi: float | None,
               min_area: float = 1e-4) -> str:
    prims = compile_prims(spec)
    adds = [p for p in prims if p.op == "add"]
    blo = np.min([p.lo for p in adds], axis=0)
    bhi = np.max([p.hi for p in adds], axis=0)
    k = AXES[axis]
    i, j = [d for d in range(3) if d != k]
    ui, vj = np.eye(3)[i], np.eye(3)[j]
    mid = (blo + bhi) / 2
    half = float(max(bhi[i] - blo[i], bhi[j] - blo[j])) / 2 * 1.05
    lo = blo[k] if lo is None else lo
    hi = bhi[k] if hi is None else hi
    ni, nj = "XYZ"[i], "XYZ"[j]
    lines = [f"slices across {axis.upper()} from {lo:.3f} to {hi:.3f}; each part: "
             f"{ni} range, {nj} range, area (parts smaller than {min_area} m² omitted)"]
    for t in np.linspace(lo, hi, samples):
        c = mid.copy()
        c[k] = t
        mask, s = _plane(prims, c, ui, vj, half)
        lab, n = ndimage.label(mask)
        parts = []
        for m in range(1, n + 1):
            u0, u1, v0, v1, area = _extent(lab == m, s)
            if area >= min_area:
                parts.append((u0 + c[i], u1 + c[i], v0 + c[j], v1 + c[j], area))
        parts.sort(key=lambda p: p[0])
        head = f"  {axis}={t:+.3f}"
        if not parts:
            lines.append(f"{head}  empty")
            continue
        desc = "; ".join(f"{ni}[{p[0]:+.3f},{p[1]:+.3f}] {nj}[{p[2]:+.3f},{p[3]:+.3f}] a{p[4]:.4f}"
                         for p in parts)
        lines.append(f"{head}  {len(parts)} part{'s' * (len(parts) > 1)}: {desc}")
    return "\n".join(lines)


def measure(spec: dict, along, samples: int = 11, lo: float | None = None,
            hi: float | None = None) -> str:
    if isinstance(along, str) and along.lower() in AXES:
        return along_axis(spec, along.lower(), samples, lo, hi)
    bones = [along] if isinstance(along, str) else list(along)
    return along_bones(spec, bones, samples)


# --- walkability: floors, headroom and clear width, from vertical and horizontal rays through the exact field ---

DZ = 0.02  # vertical sampling step (m); crossings are refined linearly


def _bounds(prims):
    adds = [p for p in prims if p.op == "add"]
    return np.min([p.lo for p in adds], axis=0), np.max([p.hi for p in adds], axis=0)


def _column(prims, xy: np.ndarray, zlo: float, zhi: float):
    """Field along vertical lines at xy (n, 2) from zlo to zhi: (zs, f (n, len(zs)))."""
    zs = np.arange(zlo, zhi + DZ, DZ)
    pts = np.empty((len(xy), len(zs), 3))
    pts[..., :2] = xy[:, None, :]
    pts[..., 2] = zs[None, :]
    return zs, field_at(prims, pts)


def _crossings(zs, f):
    """Per column: tops (solid below, air above) and bottoms (air below, solid above), linearly refined."""
    tops, bottoms = [], []
    for fi in f:
        ii = fi < 0
        k = np.flatnonzero(ii[:-1] != ii[1:])
        z = zs[k] + (zs[k + 1] - zs[k]) * fi[k] / (fi[k] - fi[k + 1])
        tops.append(z[ii[k]])
        bottoms.append(z[~ii[k]])
    return tops, bottoms


def _stand(tops, bottoms, zhi, height):
    """Per column, the lowest top with `height` of air above it (or open up to zhi); nan where there's none."""
    out = np.full(len(tops), np.nan)
    for i, (t, b) in enumerate(zip(tops, bottoms)):
        for z in t:
            above = b[b > z]
            if (above[0] if len(above) else zhi) - z >= height:
                out[i] = z
                break
    return out


def _level(stand):
    """The most common standing height (2 cm bins): the floor, when the caller didn't give one."""
    ok = stand[~np.isnan(stand)]
    if not len(ok):
        return None
    vals, counts = np.unique(np.round(ok / 0.02).astype(int), return_counts=True)
    return float(vals[np.argmax(counts)] * 0.02)


def stand_height(spec: dict, x: float, y: float, height: float = 1.8) -> float | None:
    """The floor a person stands on at (x, y): the lowest surface with `height` of free space above it."""
    prims = compile_prims(spec)
    lo, hi = _bounds(prims)
    zs, f = _column(prims, np.array([[x, y]], float), float(lo[2]) - 0.05, float(hi[2]) + 0.05)
    z = _stand(*_crossings(zs, f), float(hi[2]) + 0.05, height)[0]
    return None if np.isnan(z) else float(z)


def stand_spot(spec: dict, x: float, y: float, height: float = 1.8, reach: float = 1.5):
    """Where a person asked to stand at (x, y) stands: (x, y, floor z, note). On the floor there, unless the spot
    is under something (a table: less than `height` above the floor) or on top of furniture (a counter, a bed:
    0.25-1.3 m above the floor around it): then the nearest spot within `reach` on the surrounding floor with
    the headroom, a hand's width clear, rather than on top of the furniture. "The floor around" is the lowest height a
    quarter of the spots within `reach` stand at. A loft or gallery (higher than
    that) is stood on. floor z is None when there is no floor at all."""
    prims = compile_prims(spec)
    lo, hi = _bounds(prims)
    zlo, zhi = float(lo[2]) - 0.05, float(hi[2]) + 0.05

    def floors(xy):  # per column: the lowest top with `height` of air above it (seams under 10 cm aren't air)
        zs, f = _column(prims, xy, zlo, zhi)
        out = []
        for t, b in zip(*_crossings(zs, f)):
            z = None
            for zt in t:
                ab = b[b > zt]
                gap = (ab[0] if len(ab) else zhi) - zt
                if gap >= height:
                    z = float(zt)
                    break
            out.append(z)
        return out

    here = floors(np.array([[x, y]], float))[0]
    rings = np.arange(0.1, reach + 1e-9, 0.1)
    ang = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    xy = np.array([[x + r * np.cos(a), y + r * np.sin(a)] for r in rings for a in ang])
    fl = floors(xy)
    rad = np.repeat(rings, len(ang))  # each ring sample stands for an area ~ its radius
    zs_ok = [z for z in fl if z is not None]
    w_ok = np.array([r for z, r in zip(fl, rad) if z is not None])
    if not zs_ok:
        return x, y, here, ""
    # the floor around: the lowest height (15 cm bins: a rug is floor) at least a quarter of the ring stands at;
    # not simply the lowest (the ground outside a raised floor), nor the most common (a big bed)
    zb = np.round(np.asarray(zs_ok) / 0.15).astype(int)
    vals = np.unique(zb)
    share = np.array([w_ok[zb == v].sum() for v in vals]) / rad.sum()
    low = float(np.min(np.asarray(zs_ok)[zb == vals[share >= 0.25].min()])) if (share >= 0.25).any() else min(zs_ok)
    if here is not None and (here - low < 0.25 or here - low > 1.3):
        return x, y, here, ""
    good = [i for i, z in enumerate(fl) if z is not None and z - low < 0.25]
    i = good[0]  # rings go outwards: the first good one is the nearest
    p, zf = xy[i], fl[i]
    d = p - [x, y]
    step = p + 0.15 * d / np.linalg.norm(d)  # a hand's width clear of the edge
    z3 = floors(step[None])[0]
    if z3 is not None and z3 - low < 0.25:
        p, zf = step, z3
    why = "on top of something" if here is not None else "under something"
    return (float(p[0]), float(p[1]), float(zf),
            f"({x:.2f}, {y:.2f}) is {why}" + (f" at z = {here:.2f}" if here is not None else "")
            + f": stepped {np.hypot(*(p - [x, y])):.2f} m to ({p[0]:.2f}, {p[1]:.2f})")


def _classify(prims, xy, level, height, radius, step, zhi, cols=None):
    """Per column near the floor level: floor z (nan if none), headroom (inf: open above), and a map character:
    '.' a person fits, ',' floor and headroom but within `radius` of something, 'h' headroom < height,
    '#' blocked (solid through the floor level, or less than half the height free), ' ' no floor there."""
    zs, f = cols or _column(prims, xy, level - step - 0.05, zhi)
    tops, bottoms = _crossings(zs, f)
    floor, head = np.full(len(xy), np.nan), np.full(len(xy), np.nan)
    ch = np.full(len(xy), " ")
    k_hi = min(int(np.searchsorted(zs, level + step)), len(zs) - 1)
    for i, (t, b) in enumerate(zip(tops, bottoms)):
        near = t[(t >= level - step) & (t <= level + step)]
        if not len(near):
            ch[i] = "#" if f[i, k_hi] < 0 else " "
            continue
        floor[i] = near.max()
        above = b[b > floor[i]]
        head[i] = (above[0] if len(above) else np.inf) - floor[i]
        ch[i] = "#" if head[i] < 0.5 * height else ("h" if head[i] < height else ".")
    # the body: a capsule from above step height to the top of the head, `radius` clear all round
    body = np.flatnonzero(ch == ".")
    if len(body):
        hz = np.linspace(step + radius, max(step + radius, height - radius), 6)
        pts = np.empty((len(body), len(hz), 3))
        pts[..., :2] = xy[body, None, :]
        pts[..., 2] = floor[body, None] + hz[None, :]
        ch[body[field_at(prims, pts).min(1) < radius]] = ","
    return floor, head, ch


def _auto_level(prims, xy, lo, zhi, height):
    """The floor level and the columns it was found from (reused to classify)."""
    zs, f = _column(prims, xy, float(lo[2]) - 0.05, zhi)
    return _level(_stand(*_crossings(zs, f), zhi, height)), (zs, f)


def clearance(spec: dict, region=None, path=None, floor: float | None = None, height: float = 1.8,
              radius: float = 0.25, step: float = 0.2, spacing: float | None = None) -> str:
    """Walkability over a floor region (a character map + numbers) or along a path (floor, headroom and clear
    width per sample, the bottleneck, and whether a person passes). See server.clearance."""
    prims = compile_prims(spec)
    lo, hi = _bounds(prims)
    zhi = float(hi[2]) + 0.05
    if (region is None) == (path is None):
        raise ValueError("give either region [[x0, y0], [x1, y1]] or path [[x, y], ...]")
    if path is not None:
        return _walk(prims, np.asarray(path, float)[:, :2], floor, height, radius, step, lo, zhi)
    (x0, y0), (x1, y1) = np.sort(np.asarray(region, float)[:, :2], axis=0)
    spacing = float(spacing or max(0.05, round(max(x1 - x0, y1 - y0) / 60, 3)))
    xs, ys = np.arange(x0, x1 + 1e-9, spacing), np.arange(y1, y0 - 1e-9, -spacing)  # rows from +Y down
    gx, gy = np.meshgrid(xs, ys)
    xy = np.stack([gx.ravel(), gy.ravel()], 1)
    how, cols = "given", None
    if floor is None:
        floor, cols = _auto_level(prims, xy, lo, zhi, height)
        if floor is None:
            return f"no floor anywhere in the region with {height} m of headroom"
        how = "the most common standing height in the region"
    fz, head, ch = _classify(prims, xy, floor, height, radius, step, zhi, cols)
    grid = ch.reshape(gx.shape)
    walk = ch == "."
    lines = [f"clearance over x {x0:.2f}..{x1:.2f}, y {y0:.2f}..{y1:.2f} every {spacing:.3f} m; floor level "
             f"{floor:.3f} ({how}); person {height} m tall, {radius} m radius, steps up to {step} m",
             f"walkable {walk.sum() * spacing ** 2:.2f} m² ({walk.mean():.0%} of cells); tight (within {radius} m of "
             f"something) {(ch == ',').mean():.0%}; low headroom {(ch == 'h').mean():.0%}; blocked "
             f"{(ch == '#').mean():.0%}; no floor at that level {(ch == ' ').mean():.0%}"]
    if walk.any():
        fw = fz[walk]
        g = fz.reshape(gx.shape)
        pairs = [(np.abs(np.diff(g, axis=a)), (np.diff(grid == ".", axis=a) == 0) &
                  (grid[1:, :] == "." if a == 0 else grid[:, 1:] == ".")) for a in (0, 1)]
        worst = max((d[o].max() for d, o in pairs if o.any()), default=0.0)
        hw = head[walk].min()
        lines.append(f"walkable floor z {fw.min():.3f}..{fw.max():.3f} (spread {np.ptp(fw) * 1000:.0f} mm, sd "
                     f"{fw.std() * 1000:.0f} mm); largest step between neighbouring walkable cells "
                     f"{worst * 1000:.0f} mm; least headroom over it {'open' if np.isinf(hw) else f'{hw:.2f} m'}")
    low = np.flatnonzero(ch == "h")
    if len(low):
        i = low[np.argmin(head[low])]
        lines.append(f"lowest headroom {head[i]:.2f} m at ({xy[i, 0]:.2f}, {xy[i, 1]:.2f})")
    ticks = "".join("|" if np.floor(x / 0.5 + 1e-9) != np.floor((x - spacing) / 0.5 + 1e-9) else " " for x in xs)
    lines += ["map, top view (+Y up, +X right): '.' walkable, ',' tight, 'h' headroom < height, '#' blocked, "
              f"' ' no floor; '|' marks every 0.5 m of x (first column x = {xs[0]:.2f})",
              "        " + ticks]
    lines += [f"{y:+7.2f} " + "".join(grid[r]) for r, y in enumerate(ys)]
    return "\n".join(lines)


def _walk(prims, P, floor, height, radius, step, lo, zhi):
    """Along a path: floor, headroom and clear width every 5 cm; the bottleneck and whether a person passes."""
    if len(P) < 2:
        raise ValueError("a path needs at least two points")
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    sc = np.concatenate([[0], np.cumsum(seg)])
    s = np.arange(0, sc[-1] + 1e-9, 0.05)
    xy = np.stack([np.interp(s, sc, P[:, 0]), np.interp(s, sc, P[:, 1])], 1)
    k = np.clip(np.searchsorted(sc, s, side="right") - 1, 0, len(seg) - 1)
    fwd = (P[k + 1] - P[k]) / np.maximum(seg[k], 1e-9)[:, None]
    left = np.stack([-fwd[:, 1], fwd[:, 0]], 1)
    cols = None
    if floor is None:
        floor, cols = _auto_level(prims, xy, lo, zhi, height)
        if floor is None:
            return f"no floor along the path with {height} m of headroom"
    fz, head, ch = _classify(prims, xy, floor, height, radius, step, zhi, cols)
    hz = np.linspace(step + 0.05, height - 0.05, 5)  # heights above the floor for the width rays
    rs = np.arange(0.0, 2.0 + 1e-9, 0.01)
    base = np.where(np.isnan(fz), floor, fz)
    reach = {}
    for sgn in (1, -1):
        pts = np.empty((len(xy), len(hz), len(rs), 3))
        pts[..., :2] = xy[:, None, None, :] + sgn * left[:, None, None, :] * rs[None, None, :, None]
        pts[..., 2] = base[:, None, None] + hz[None, :, None]
        inside = field_at(prims, pts) < 0
        reach[sgn] = np.where(inside.any(-1), rs[inside.argmax(-1)], rs[-1])  # (n, heights)
    both = reach[1] + reach[-1]
    width = both.min(1)
    worst = int(np.argmin(width))
    lines = [f"walk along {len(P)} points, {sc[-1]:.2f} m; floor level {floor:.3f}; person {height} m tall, "
             f"{radius} m radius, steps up to {step} m. width = clear distance left + right of the path at "
             f"{', '.join(f'{h:.2f}' for h in hz)} m above the floor (the least; each side capped at 2 m)",
             "      s       x       y    floor  headroom  width   left  right"]
    for i in range(len(xy)):
        if i % 5 and i not in (worst, len(xy) - 1) and ch[i] == ch[i - 1]:  # every 25 cm, and where it changes
            continue
        hd = "open" if np.isinf(head[i]) else ("-" if np.isnan(head[i]) else f"{head[i]:.2f}")
        fl = "-" if np.isnan(fz[i]) else f"{fz[i]:.3f}"
        j = int(np.argmin(both[i]))
        note = {"#": "BLOCKED", "h": "LOW", ",": "tight", " ": "NO FLOOR"}.get(str(ch[i]), "")
        lines.append(f"  {s[i]:5.2f}  {xy[i, 0]:+6.2f}  {xy[i, 1]:+6.2f}  {fl:>7}  {hd:>7}  {width[i]:5.2f}  "
                     f"{reach[1][i, j]:5.2f}  {reach[-1][i, j]:5.2f}  {note}{'  <- narrowest' if i == worst else ''}")
    ok = ~np.isnan(fz)
    stepmax = float(np.abs(np.diff(fz[ok])).max()) if ok.sum() > 1 else 0.0
    headmin = float(np.nanmin(head)) if ok.any() else float("nan")
    passes = (not np.isin(ch, ["#", "h", " "]).any()) and width.min() >= 2 * radius and stepmax <= step
    lines.append(f"narrowest {width[worst]:.2f} m at s = {s[worst]:.2f} ({xy[worst, 0]:+.2f}, {xy[worst, 1]:+.2f}); "
                 f"lowest headroom {'open' if np.isinf(headmin) else f'{headmin:.2f} m'}; largest step "
                 f"{stepmax * 1000:.0f} mm; samples blocked {(ch == '#').sum()}, low {(ch == 'h').sum()}, "
                 f"no floor {(ch == ' ').sum()} of {len(ch)}")
    why = [w for w, bad in (("blocked", (ch == "#").any()), ("low headroom", (ch == "h").any()),
                            ("no floor", (ch == " ").any()), ("too narrow", width.min() < 2 * radius),
                            (f"a step over {step} m", stepmax > step)) if bad]
    lines.append(f"a person {height} m tall and {2 * radius:.2f} m wide "
                 + ("PASSES" if passes else f"does NOT pass ({', '.join(why)})"))
    return "\n".join(lines)


def doorways(spec: dict, min_height: float = 1.6) -> list[dict]:
    """Door openings: box cuts with targets (subtract), taller than `min_height`, whose bottom is within 0.3 m of
    the floor through them. [{"name", "at" (floor centre), "across" (unit, horizontal, through the wall), "width",
    "height"}]."""
    from .assemble import expand
    from .spec import euler_matrix
    s = expand_mirror(expand(spec))
    out = []
    for n, b in (s.get("blobs") or {}).items():
        if b.get("op") != "subtract" or not b.get("targets") or b.get("shape", "ellipsoid") != "box":
            continue
        sz = np.asarray(b["size"], float)
        R = euler_matrix(b.get("rot", [0, 0, 0]))
        if abs(R[2, 2]) < 0.99 or 2 * sz[2] < min_height:  # tilted: a roof cut, not a door
            continue
        c = resolve_point(s, b["at"]) + np.asarray(b.get("offset", [0, 0, 0]), float)
        ax = 0 if sz[0] < sz[1] else 1  # the thin horizontal axis runs through the wall
        across = R[:, ax] * np.array([1, 1, 0])
        across /= np.linalg.norm(across)
        x, y, z, _ = stand_spot(spec, float(c[0]), float(c[1]), height=min_height)
        bottom = c[2] - sz[2]
        if z is None or bottom - z > 0.3:
            continue
        out.append({"name": n, "at": [float(c[0]), float(c[1]), float(z)], "across": across.tolist(),
                    "width": float(2 * sz[1 - ax]), "height": float(c[2] + sz[2] - z)})
    return out


def check_doorways(spec: dict, height: float = 1.8, radius: float = 0.25) -> list[str]:
    """Walk a person through every doorway (1 m either side of the wall): one line each, and for a blocked one the
    element in the way (a door swung across it, furniture)."""
    prims = compile_prims(spec)
    lo, hi = _bounds(prims)
    lines = []
    for d in doorways(spec):
        c, a = np.asarray(d["at"]), np.asarray(d["across"])
        note = ""
        for reach in (1.0, 0.5):  # no floor at the ends only: the ground outside isn't modelled; walk just through
            path = np.stack([c[:2] - reach * a[:2], c[:2] + reach * a[:2]])
            rep = _walk(prims, path, None, height, radius, 0.2, lo, float(hi[2]) + 0.05)
            verdict = rep.splitlines()[-1]
            if "PASSES" in verdict or verdict.rstrip(")").split("(")[-1] != "no floor":
                break
            note = f" (no floor {reach:.1f} m out on one side: the ground there isn't modelled; walked {0.5:.1f} m either side)"
        narrow = next(l for l in rep.splitlines() if l.startswith("narrowest"))
        ok = "PASSES" in verdict
        line = f"{d['name']} ({d['width']:.2f} x {d['height']:.2f} m opening at ({c[0]:.2f}, {c[1]:.2f})): " + (
            "passes, " + narrow.split(";")[0] + (note if "PASSES" in verdict and note else "") if ok
            else verdict.split("does NOT pass")[1].strip() + "; " + narrow)
        if not ok and "no floor" != verdict.rstrip(")").split("(")[-1]:  # name what's in the way
            ts = np.linspace(0, 1, 21)
            pts = np.array([[*(path[0] + t * (path[1] - path[0])), c[2] + h] for t in ts for h in (0.4, 0.9, 1.4)])
            best = None
            for p in prims:
                if p.op != "add" or p.part in ("floor",):
                    continue
                if np.any(p.hi < pts.min(0) - radius) or np.any(p.lo > pts.max(0) + radius):
                    continue
                from .sdf import SDF
                if p.kind not in SDF:
                    continue
                dmin = float(SDF[p.kind](pts, p.params).min())
                if best is None or dmin < best[0]:
                    best = (dmin, p.name)
            if best and best[0] < radius:
                who = best[1].split("/")[0] if "/" in best[1] else best[1]
                line += f"; in the way: {who} ({best[1]}, {max(best[0], 0) * 100:.0f} cm from the path)"
        lines.append(("ok       " if ok else "BLOCKED  ") + line)
    return lines
