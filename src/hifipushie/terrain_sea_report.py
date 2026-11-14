"""After the cut: `recut`, the cliff's feet, `fill`, regions, the report, the seabed, a cove's shape. Part of the sea and its coast (terrain_sea.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import terrain_sea
from .terrain import smoothstep
from .terrain_sea import _cliff_face

def recut(T):
    """On a finer grid (terrain_detail): cut the cliffs again from their signed distance, so the face is a plane at the
    cliff's angle from its lip down to the water (resampled, it was the coarse grid's drape: a face 2 cells across
    became 4 soft ones) and the lip stands at its top. Stacks, foot beaches, routes and sites are left as they are."""
    S = getattr(T, "sea", None)
    if not S or not (S["wc"] > 0.5).any():
        return
    keep = np.zeros(T.X.shape, bool)
    for k in ("routes", "sites"):
        if k in T.masks:
            keep |= T.masks[k] > 0.05
    sd, level = S["sd"], S["level"]
    cliff = (S["wc"] > 0.5) & (S["foot"] < 0.5) & ~S["st_mask"] & ~keep
    face = (S["top"] - S["bev_h"]) - _cliff_face(T, sd, S["top"], level, T.spec["sea"].get("cliffs") or {})[0]
    H = T.H
    off = cliff & (sd < 0) & (face > level + 0.3)
    H = np.where(off, np.minimum(H, face), H)
    coarse = T.detail["cell"]
    lip = S["top"] - S["bev_h"] * smoothstep(S["bev_w"], 0, np.maximum(sd, 0)) ** 1.5
    on = cliff & (sd >= 0) & (sd < 1.5 * coarse)
    T.H = np.where(on, np.maximum(H, lip), H)


def cliff_feet(T, spacing=15.0):
    """Points along the foot of the sea cliffs, for placing things against the face (sea caves and notches as 3D
    volumes): [{"xy": foot [x, y], "z": the water level, "out": seaward unit [x, y], "height": cliff height m,
    "lip": [x, y] of the lip above}], every `spacing` metres along the cliff coast, stacks and talus left out."""
    S = getattr(T, "sea", None)
    if not S or not (S["wc"] > 0.5).any():
        return []
    sd, level = S["sd"], S["level"]
    land = sd > 0
    coast = land & ndimage.binary_dilation(~land) & (S["wc"] > 0.5) & (S["foot"] < 0.5)
    gy, gx = np.gradient(ndimage.gaussian_filter(sd, 2))
    ys, xs = np.nonzero(coast)
    out, taken = [], []
    order = np.lexsort((xs, ys))
    for j in order:
        y, x = ys[j], xs[j]
        p = np.array([T.X[y, x], T.Y[y, x]])
        if any(np.hypot(*(p - q)) < spacing for q in taken[-400:]):
            continue
        n = -np.array([gx[y, x], gy[y, x]])
        n /= np.linalg.norm(n) + 1e-9
        h = float(S["top"][y, x] - level)
        foot = p + n * float(S["run"][y, x]) if "run" in S else p + n * h / math.tan(terrain_sea.CLIFF)
        iy = int(np.clip(round((foot[1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1))
        ix = int(np.clip(round((foot[0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1))
        if S["st_mask"][iy, ix] or h < 2:
            continue
        taken.append(p)
        out.append({"xy": [round(float(foot[0]), 2), round(float(foot[1]), 2)], "z": level,
                    "out": [round(float(n[0]), 3), round(float(n[1]), 3)], "height": round(h, 1),
                    "lip": [round(float(p[0]), 2), round(float(p[1]), 2)]})
    return out


def fill(T, lk):
    """The sea's water: ground below its level connected to the sea side of the coast (never limited to a radius)."""
    below = T.H < lk["level"]
    lab, _ = ndimage.label(below)
    ids = np.unique(lab[~T.sea["land"] & below])
    return np.isin(lab, ids[ids > 0])


def regions(T, name):
    """The sea's zones for cover and routes: sea, beach, cliffs, coast."""
    S = T.sea
    if name == "sea":
        return (~np.isnan(T.water) & (T.lake_id == T.lakes["sea"]["id"])).astype(float)
    if name == "beach":
        graded = S["wb"] * smoothstep(S["beach_width"] * 1.6, S["beach_width"], S["sd"]) * (S["sd"] > -S["beach_width"])
        at_foot = (S["foot"] > 0.5) & (S["sd"] < 0) & (T.H < S["level"] + 2.5)  # sand below the cliffs
        return np.maximum(graded, at_foot) * np.isnan(T.water)
    if name == "cliffs":
        return S["wc"] * smoothstep(-4 * T.cell, 0, S["sd"]) * smoothstep(3 * T.cell, 0, S["sd"])
    if name == "coast":
        return smoothstep(6 * T.cell, 0, np.abs(S["sd"]))
    if name == "rocks":  # the low-rock strip's boulders (shore "rocks")
        return np.clip(S["rocks"] * 1.5, 0, 1)
    return None


def report(T):
    S = T.sea
    if not S:
        return []
    lk = T.lakes["sea"]
    wet = T.lake_id == lk["id"]
    coast = S["land"] & ndimage.binary_dilation(~S["land"])
    length = coast.sum() * T.cell
    out = [f"sea: level {S['level']:.0f} m, {_area(wet.sum() * T.cell ** 2)} of water, {length / 1000:.1f} km of coast; "
           f"deepest {float((S['level'] - T.H[wet]).max()) if wet.any() else 0:.0f} m in the frame"]
    # cliffs as built: at each coast point with a cliff, the drop from the land's top just inland to the water
    by, bx = np.nonzero(coast & (S["wc"] > 0.5))
    if len(by):
        ring = 3
        tops = np.array([T.H[max(y - ring, 0):y + ring + 1, max(x - ring, 0):x + ring + 1].max() for y, x in zip(by, bx)])
        h = tops - S["level"]
        want = S["want"][by, bx] - S["level"]
        slope = T._slope()
        steep = np.array([slope[max(y - ring, 0):y + ring + 1, max(x - ring, 0):x + ring + 1].max() for y, x in zip(by, bx)])
        # judged against what was asked for each stretch (cliffs.heights), not the coast-wide range
        lo, hi = float(np.percentile(want, 5)), float(np.percentile(want, 95))
        tall = h > 1.3 * want + 5
        ok = (h >= 0.8 * want) & (steep >= 55) & ~tall
        out.append(f"sea cliffs (measured): {len(by) * T.cell / 1000:.1f} km of cliff coast, {np.percentile(h, 10):.0f}-"
                   f"{np.percentile(h, 90):.0f} m high (asked {lo:.0f}" + (f"-{hi:.0f}" if hi - lo > 1 else "")
                   + (" over the stretches" if (T.spec.get("sea") or {}).get("cliffs", {}).get("heights") else "")
                   + f"), steepest median {np.median(steep):.0f} deg; {100 * ok.mean():.0f}% as asked")
        if tall.mean() > 0.2:
            ty, tx = by[tall], bx[tall]
            T.warnings.append(f"sea cliffs: {100 * tall.mean():.0f}% of the cliff coast stands over 1.3x its asked height "
                              f"(up to {h.max():.0f} m, around [{T.X[ty, tx].mean():.0f}, {T.Y[ty, tx].mean():.0f}]): the "
                              f"land is that high where it meets the sea (a peak's flanks reaching past the coast). Widen the "
                              f"land, give that stretch its height (cliffs.heights), or let the peak's flanks come lower; the "
                              f"tool won't cut the land down under what you placed")
    for gname, g in S.get("geos", {}).items():  # does the sea run up it: the floor at its mouth and its head, as built
        p, inl = np.array(g["xy"]), np.array(g["inland"])
        pts_ = p + inl[None] * np.linspace(0, 0.9 * g["length"], 10)[:, None]
        fl = T.sample(pts_)
        gwet = T.sample(pts_, (~np.isnan(T.water)).astype(float)) > 0.5
        out.append(f"geo {gname}: {g['length']:.0f} m long, {g['width']:.0f} m wide; floor {fl[0] - S['level']:+.1f} m at the "
                   f"mouth, {fl[-1] - S['level']:+.1f} m at its head; the sea runs {100 * gwet.mean():.0f}% of the way up")
        if gwet.mean() < 0.7:
            T.warnings.append(f"geo {gname!r}: the sea reaches only {100 * gwet.mean():.0f}% of the way up it (its floor stands "
                              f"{fl.max() - S['level']:+.1f} m): move it onto a cliff stretch, or shorten it")
    bc = coast & ((S["wb"] > 0.5) | (S["foot"] > 0.5))
    if bc.any():
        # dry ground within 2.5 m of the water, next to the beach coast: its area over the beach's length is its width
        low = (np.isnan(T.water) & (T.H - S["level"] < 2.5) & ((S["wb"] > 0.5) | (S["foot"] > 0.5))
               & (S["sd"] < 6 * S["beach_width"]))
        lab, _ = ndimage.label(low)
        ids = np.unique(lab[ndimage.binary_dilation(bc, iterations=int(4 + 60 / T.cell)) & low])
        sand = np.isin(lab, ids[ids > 0]).sum() * T.cell ** 2
        length = bc.sum() * T.cell
        out.append(f"beaches (measured): {length:.0f} m of beach coast; the dry sand within 2.5 m of the water averages "
                   f"{sand / max(length, 1):.0f} m wide")
    if S.get("stacks"):
        hs = []
        for st in S["stacks"]:
            c = np.array(st["xy"])
            near = np.hypot(T.X - c[0], T.Y - c[1]) < st["radius"]
            hs.append(float(T.H[near].max() - S["level"]) if near.any() else 0.0)
        up = [h for h in hs if h >= 2.0]
        if up:
            out.append(f"sea stacks: {len(up)} standing {min(up):.0f}-{max(up):.0f} m out of the water off the cliffs")
        if len(up) < len(hs):
            out.append(f"  ({len(hs) - len(up)} placed stack(s) don't stand out of the water: the ground there was cut "
                       f"away after them (a cove, a geo) or they fell in deep water; move the string (`stacks.at`)")
    for name, cv in S["coves"].items():
        m = cv["mask"] & wet
        out.append(f"cove {name}: {_area(m.sum() * T.cell ** 2)} of water, {cv['depth']:.0f} m deep into the "
                   f"land, mouth at [{cv['mouth'][0]:.0f}, {cv['mouth'][1]:.0f}]" + _cove_shape(T, cv, wet))
    sb = seabed(T)
    if sb["line"]:
        out.append(sb["line"])
    for w in sb["warnings"]:
        if w not in T.warnings:
            T.warnings.append(w)
    return out


# seabed(): a plateau = sea floor flatter than `flat` (m / m) over `area` m2, above the sea's own depth; a step = cells
# offshore whose floor falls more than `step` x the cell to a neighbour; ruled = a run of them over `run` m long lying
# within `straight` cells of one line
def seabed(T) -> dict:
    """The sea floor as built: flat plateaus above the sea's own depth and long straight steps offshore (a shore
    form's profile held at a floor, or its share cut off along a line, show in any depth-coloured water as a pale
    rectangle: pushieworld note 107). {"line", "warnings", "plateaus": [...], "steps": [...]}."""
    S = T.sea
    level, c = S["level"], T.cell
    depth = float((T.spec.get("sea") or {}).get("depth", 0) or 0)
    sd = S["sd"]
    off = (sd < -4 * c) & (T.H < level - 1.5)
    out = {"line": "", "warnings": [], "plateaus": [], "steps": []}
    if not off.any():
        return out
    gy, gx = np.gradient(T.H, c)
    g = np.hypot(gx, gy)
    deep = level - depth + 1.0 if depth else -np.inf
    flat = off & (g < terrain_sea.SHELF["flat"]) & (T.H > deep)
    flat = ndimage.binary_opening(flat, iterations=2)
    lab, n = ndimage.label(flat)
    if n:
        sizes = ndimage.sum(flat, lab, np.arange(1, n + 1)) * c * c
        for i in np.argsort(-sizes)[:3]:
            if sizes[i] < terrain_sea.SHELF["area"]:
                break
            m = lab == i + 1
            out["plateaus"].append({"area_m2": float(sizes[i]), "z": float(np.median(T.H[m])),
                                    "at": [float(T.X[m].mean()), float(T.Y[m].mean())]})
    # steps: away from the coast's own forms (cliff feet, stacks stand within a few cells of the coast line)
    far = sd < -max(12 * c, 30.0)
    step = far & (g > terrain_sea.SHELF["step"]) & (T.H < level - 3.0)
    lab, n = ndimage.label(step, structure=np.ones((3, 3)))
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() * c < terrain_sea.SHELF["run"]:
            continue
        P = np.c_[T.X[m], T.Y[m]]
        q = P - P.mean(0)
        _, sv, vt = np.linalg.svd(q, full_matrices=False)
        along, across = q @ vt[0], q @ vt[1]
        length = float(np.ptp(along))
        if length >= terrain_sea.SHELF["run"] and float(np.sqrt((across ** 2).mean())) <= terrain_sea.SHELF["straight"] * c:
            H0 = T.H[m]
            out["steps"].append({"length_m": length, "at": [float(P[:, 0].mean()), float(P[:, 1].mean())],
                                 "bearing": float(np.degrees(np.arctan2(vt[0][0], vt[0][1])) % 180),
                                 "z": [float(H0.min()), float(H0.max())]})
    out["steps"].sort(key=lambda s_: -s_["length_m"])
    out["line"] = (f"sea floor (measured): {len(out['plateaus'])} flat shelves over {terrain_sea.SHELF['area'] / 1e4:.1f} ha above the "
                   f"sea's depth, {len(out['steps'])} straight steps over {terrain_sea.SHELF['run']:.0f} m offshore")
    for p_ in out["plateaus"]:
        out["warnings"].append(f"sea floor: a dead-flat shelf of {p_['area_m2'] / 1e4:.1f} ha at {p_['z']:.1f} m around "
                               f"[{p_['at'][0]:.0f}, {p_['at'][1]:.0f}] (the sea is {depth:.0f} m deep): depth-coloured water "
                               f"shows it as a pale patch")
    for s_ in out["steps"][:3]:
        out["warnings"].append(f"sea floor: a ruler-straight step {s_['length_m']:.0f} m long ({s_['z'][1]:.0f} to "
                               f"{s_['z'][0]:.0f} m) around [{s_['at'][0]:.0f}, {s_['at'][1]:.0f}], bearing "
                               f"{s_['bearing']:.0f} deg")
    return out


def _cove_shape(T, cv, wet):
    """As built: the bay's widest water across, the mouth's narrowest gap between the land either side, each headland's
    top (m above the sea) and the shore height round the rest of the bay."""
    from scipy.spatial import cKDTree
    p, inl = np.array(cv["mouth"]), np.array(cv["inland"])
    left = np.array([-inl[1], inl[0]])
    rel = T.P - p
    u, sa = rel @ inl, rel @ left
    w, dp = cv["width"], cv["depth"]
    # water across the bay's axis, section by section from outside the mouth to the head: the run of water through the
    # bay's own axis (stacks count as water: they stand in the mouth, they don't close it)
    wetx = (T.sea["sd"] <= 0) | wet  # (the coastline itself: rocks awash and stacks in the mouth don't close it)
    axis_s = float(((np.array(cv["xy"]) - p) @ left))
    txt = ""
    widths = []
    for uu in np.arange(-0.3 * dp, dp, max(T.cell, dp / 40)):
        ss = np.arange(axis_s - 1.5 * w, axis_s + 1.5 * w, T.cell)
        pts = p + inl * uu + left * ss[:, None]
        wv = T.sample(pts, wetx.astype(float)) > 0.5
        k = int(np.argmin(np.abs(ss - axis_s)))
        if not wv[k]:
            widths.append((uu, 0.0))
            continue
        i0, i1 = k, k
        while i0 > 0 and wv[i0 - 1]:
            i0 -= 1
        while i1 < len(wv) - 1 and wv[i1 + 1]:
            i1 += 1
        open_ = i0 == 0 or i1 == len(wv) - 1
        widths.append((uu, np.inf if open_ else (i1 - i0 + 1) * T.cell))
    inner = [wd for uu, wd in widths if uu > 0.25 * dp and np.isfinite(wd)]
    bay_w = max(inner) if inner else 0.0
    u_b = next((uu for uu, wd in widths if wd == bay_w), dp / 2)
    mouth = [wd for uu, wd in widths if uu <= u_b and wd > 0]
    mouth_w = min(mouth) if mouth else 0.0
    if bay_w:
        txt += f"; the bay {bay_w:.0f} m across at its widest"
    if np.isfinite(mouth_w) and mouth_w > 0:
        txt += f", the mouth {mouth_w:.0f} m" + (" (sheltered)" if mouth_w < 0.8 * bay_w else
                                                  " (as wide as the bay: open, not sheltered)")
    else:
        txt += ", the mouth opens straight onto the sea (no narrowing: not sheltered)"
    lvl = T.sea["level"]
    for h in cv.get("headlands", []):
        b0, tip = np.array(h["base"]), np.array(h["tip"])
        seg = tip - b0
        t = np.clip(((T.P - b0) @ seg) / (seg @ seg), 0, 1)
        near = np.linalg.norm(T.P - (b0 + t[:, None] * seg), axis=1) < 0.25 * w
        top = float(T.H.ravel()[near & ~wet.ravel()].max() - lvl) if (near & ~wet.ravel()).any() else 0.0
        v = left * h["side"]
        side = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][
            int(round(math.degrees(math.atan2(v[0], v[1])) / 45)) % 8]
        kind = "headland" if h.get("height") is not None else "low point"
        txt += f"; {kind} on its {side} side tops {top:.0f} m"
    return txt


def _area(a):
    from .terrain import _area as f
    return f(a)
