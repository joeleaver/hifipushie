"""Sites: a site's ground, earthworks, the shore pad. Part of the terrain design layer (terrain_design.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from .terrain import smoothstep
from .terrain_design_sight import lake_seen, sight

def _site(T, name, s):
    """A flat pad. An address on a lake shore puts the pad inland of that point, clear of the water."""
    ref = s["at"]
    xy, _, d = T.address(ref)
    r = float(s.get("radius", 60))
    shore_lake = None
    sea = getattr(T, "sea", None)
    if isinstance(ref, str) and sea and ref in sea["coves"]:  # in a cove: at its head, just inland of its beach
        cv = sea["coves"][ref]
        xy = np.array(cv["head"]) + np.array(cv["inland"]) * (r + s.get("setback", 5))
        shore_lake, d = "sea", np.array(cv["inland"])
    elif isinstance(ref, str) and ref.endswith("_shore"):
        shore_lake = ref.rsplit(".", 1)[0]
        xy = _shore_pad(T, name, shore_lake, xy, d, r + s.get("setback", 5), r + max(20.0, 0.5 * r))
    rim = isinstance(ref, str) and "_rim" in ref.split("@")[0]
    if rim:  # d points into the canyon: back from the lip, on the plateau, looking in ("lip": its edge at the lip)
        xy = xy - d * ((0.35 * r if s.get("lip") else r) + s.get("setback", 0 if s.get("lip") else 3))
        s = {**s, "level": s.get("level", T.height(xy + -d * r))}
    dist = np.hypot(T.X - xy[0], T.Y - xy[1])
    inside = dist <= r
    # the water that could reach the pad: what's beside it, not a river's level 200 m upstream (that put a lakeside
    # village 198 m up on a mound)
    # (out to where the report judges "the water beside it" (edge within max(60, r)): a village 56 m from the vale river
    # was set from no water at all and stood 4 m under the river's level, above_water: 3 ignored; pushieworld 67, 116)
    wet = ~np.isnan(T.water) & (dist < r + max(60.0, r))
    if "level" in s:
        level = float(s["level"])
    elif shore_lake is not None:  # a lakeside pad: just above its lake, cut into the bank behind
        level = T.lakes[shore_lake]["level"] + s.get("above_water", 3.0)
    else:  # a little below the middle: cut into the slope more than built out (fill stands as a mound)
        level = float(np.percentile(T.H[inside], 40))
    floor_w = -np.inf
    if wet.any():  # above the water nearest the pad (a steep river beside it is higher upstream, lower downstream)
        k = np.argmin(np.where(wet, dist, np.inf))
        floor_w = float(T.water.ravel()[k]) + s.get("above_water", 2.0)
        level = max(level, floor_w)
    # a big pad (a village, a farmyard) keeps some of the ground's own lie: levelled halfway, not a dead-flat plate
    # (every village stood on a mound or in a dug box); small pads (a tee, a camp) are flat. "flat": 0..1
    flat = float(s.get("flat", 1.0 if r <= 40 else 0.5))
    lie = ndimage.gaussian_filter(T.H, max(1.0, 0.35 * r / T.cell))
    river = getattr(T, "river_water", np.zeros(T.X.shape, bool)) & inside
    if isinstance(ref, str) and ref.rsplit(".", 1)[-1] in ("source", "mouth"):  # a spring or a river's end: on purpose
        river[:] = False
    if river.any():
        T.warnings.append(f"site {name!r}: a river runs through the pad (at [{T.X[river].mean():.0f}, "
                          f"{T.Y[river].mean():.0f}]): move it, or it will be built over the water")
    shoulder = s.get("shoulder", max(20.0, 0.5 * r))
    # banks sized to how far the ground is from the pad (35 deg), at least `shoulder`
    bank = np.clip(np.abs(T.H - level) / math.tan(math.radians(35)), shoulder, shoulder + r)  # capped: beyond, a cliff
    w = smoothstep(r + bank, r, dist)
    before = T.H.copy()
    if rim:  # a lookout on a rim: cut to the plateau, never fill out over the lip (the fill mound hid the view)
        w = np.where(T.H >= level, w, 0)

    def surface(fall, dvec):  # a pad that falls gently toward dvec (real yards drain; a dead-level one blinds its middle)
        plane = level - fall * ((T.X - xy[0]) * dvec[0] + (T.Y - xy[1]) * dvec[1])
        if flat >= 1:
            return plane
        # the ground's lie relative to its own mean over the pad, added back in part (kept above the water)
        rel = lie - float(np.mean(lie[inside]))
        return np.maximum(plane + (1 - flat) * rel, floor_w)

    fall, dvec, note = float(s.get("fall", 0.0)), np.array([0.0, 0.0]), ""
    if s.get("toward"):
        tw = s["toward"]
        dvec = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}.get(tw) if isinstance(tw, str) else None
        dvec = np.array(dvec, float) if dvec is not None else T.address(tw)[0] - xy
        dvec = dvec / (np.linalg.norm(dvec) + 1e-12)
        fall = fall or 0.02
    if s.get("overlooks"):  # choose the gentlest fall toward the target that lets most of the pad see it
        tgt = s["overlooks"]
        dvec = T.address(tgt)[0] - xy
        dvec = dvec / (np.linalg.norm(dvec) + 1e-12)
        spots = [xy] + [xy + 0.7 * r * np.array([math.sin(a), math.cos(a)]) for a in np.radians(np.arange(0, 360, 45))]
        best = None
        keep_h = T.H
        asked = float(s.get("fall", 0.0))  # a fall the designer gave is the least it gets
        for f in [asked] + [f for f in (0.02, 0.04, 0.06, 0.08, 0.1) if f > asked]:
            T.H = keep_h * (1 - w) + surface(f, dvec) * w
            named = isinstance(tgt, str)  # (an [x, y] target is neither a cove nor a lake: it crashed the lookup)
            cove = named and getattr(T, "sea", None) and tgt in T.sea["coves"]
            seen = sum((lake_seen(T, p_.tolist(), "sea", mask=T.sea["coves"][tgt]["mask"]) > 0) if cove else
                       (lake_seen(T, p_.tolist(), tgt) > 0) if named and tgt in T.lakes else
                       (sight(T, p_.tolist(), tgt)["visible"] > 0) for p_ in spots)
            if best is None or seen > best[1]:
                best = (f, seen)
            if seen >= 6:
                break
        T.H = keep_h
        fall = best[0]
        note = f"; falls {100 * fall:.0f}% toward {tgt} so {best[1]} of 9 spots across it see it" + (
            f" (asked {100 * asked:.0f}%)" if abs(fall - asked) > 1e-6 and asked else "")
        if best[1] < 6:
            T.warnings.append(f"site {name!r} overlooks {tgt!r} from only {best[1]} of 9 spots even falling "
                              f"{100 * fall:.0f}%: raise it, move it nearer the edge, or move the target")
    if fall and not note:
        note = f"; falls {100 * fall:.0f}% toward " + (s["toward"] if isinstance(s.get("toward"), str) else "its low side")
    T.H = T.H * (1 - w) + surface(fall, dvec) * w
    _earthworks(T, w)
    T.sites[name] = {"xy": xy.tolist(), "level": level, "radius": r, "cut": float((before - T.H).max()),
                     "fill": float((T.H - before).max()), "note": note, "fall": fall, "toward": dvec.tolist(),
                     "shore": shore_lake, "above": s.get("above_water", 3.0), "above_asked": s.get("above_water")}
    if s.get("prop"):  # a prop the engine drops here (a basket, a bench): its name; which way it faces is resolved
        T.sites[name]["prop"] = {"name": s["prop"], "yaw": 0.0, "facing": s.get("facing")}  # once every site stands
    if max(T.sites[name]["cut"], T.sites[name]["fill"]) > 25:
        T.warnings.append(f"site {name!r} is dug {T.sites[name]['cut']:.0f} m into / built {T.sites[name]['fill']:.0f} m "
                          f"out of the slope: it stands against a cliff or on a mound; move it or give it a level")
    T.masks.setdefault("sites", np.zeros(T.X.shape))
    T.masks["sites"] = np.maximum(T.masks["sites"], smoothstep(r + 8, r, dist))
    T.pads = np.maximum(getattr(T, "pads", np.zeros(T.X.shape)), smoothstep(r, r - 2 * T.cell, dist))


def _earthworks(T, w):
    """Banks cut or built for a pad or a road: erosion leaves them alone (gullies cut into a fill slope read as a
    sawtooth along its edge)."""
    T.masks["earthworks"] = np.maximum(T.masks.get("earthworks", np.zeros(T.X.shape)), w)


def _shore_pad(T, name, lake, xy, d, back, clearance=None):
    """Where a pad `back` metres inland of a lake's shore goes: at the asked side's shore point unless a river runs
    there, else the nearest shore point toward that side whose pad is clear of rivers (said in the report)."""
    rw = getattr(T, "river_water", None)
    want = xy + d * back
    if rw is None or not rw.any():
        return want

    def clear(p):
        return not (rw & (np.hypot(T.X - p[0], T.Y - p[1]) < (clearance or back))).any()

    if clear(want):
        return want
    wet = ~np.isnan(T.water) & (T.lake_id == T.lakes[lake]["id"])
    edge = wet & ~ndimage.binary_erosion(wet)
    pts = np.stack([T.X[edge], T.Y[edge]], 1)
    c = np.array([T.X[wet].mean(), T.Y[wet].mean()])
    out = pts - c
    out /= np.linalg.norm(out, axis=1, keepdims=True) + 1e-9
    for k in np.argsort(-(out @ d)):
        if out[k] @ d < 0:
            break
        p = pts[k] + out[k] * back
        if clear(p):
            T.warnings.append(f"site {name!r}: a river reaches {lake!r}'s shore where asked, so the pad moved along the "
                              f"shore to [{p[0]:.0f}, {p[1]:.0f}]")
            return p
    T.warnings.append(f"site {name!r}: every shore point on that side of {lake!r} has a river beside it")
    return want
