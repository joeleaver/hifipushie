"""Caves as skeletons (like a creature's joints and bones): named nodes (entrances and chambers) joined by passages,
subtracted from the rock of the 3D terrain field (terrain_mesh). A cave's `kind` sets how it's built:

- "sea": carved by waves at the cliff foot. Floors at or just under the sea (the water runs in), wide low passages
  with flat floors, domed chambers. Entrances where the passage meets a cliff.
- "karst": dissolved along the rock's bedding. Keyhole passages (a round tube along a bedding plane with a slot cut
  down below it by the stream), floors that follow the beds and step between them, tall halls. Entrances are
  sinkholes (a shaft from the surface) or a hillside mouth.
- "lava": a tube left by a lava flow, a few metres under the ground it follows. Wide, round-roofed, flat floored;
  skylights where the roof fell in.

Spec (lengths in the terrain's units; "at" is any terrain address):
  "caves": {"name": {"kind": "sea" | "karst" | "lava", "width"?: m, "height"?: m,
      "entrances": {"door": {"at": address, "shaft"?: true}},
      "chambers": {"hall": {"at": address, "depth"?: m below the ground | "z"?: floor height, "size"?: m | [rx, rz]}},
      "passages": [["door", "hall"], {"from": "hall", "to": "top", "via"?: [[x, y], ...], "width"?, "height"?}]}}

Every node's floor is resolved first (entrances where the cave meets the open, chambers by depth or height), then
passages run floor to floor. `check(T, caves, field)` walks a person through every passage with the capsule rule of
measure.clearance (1.8 m tall, 0.25 m radius) and reports floor, headroom, width, steps and water.
"""

from __future__ import annotations

import math
import zlib

import numpy as np

from .terrain_mesh import Tube, _daylight, _downhill, _sea, smoothstep

KINDS = {
    "sea": {"width": 6.0, "height": 4.5, "chamber": 8.0, "depth": None, "rough": 0.4},
    "karst": {"width": 4.0, "height": 4.5, "chamber": 9.0, "depth": 14.0, "rough": 0.3},
    "lava": {"width": 7.0, "height": 4.5, "chamber": 9.0, "depth": 7.5, "rough": 0.25},
}


class Cave:
    def __init__(self, name, kind, nodes, edges, tubes, notes):
        self.name, self.kind, self.nodes, self.edges, self.tubes, self.notes = name, kind, nodes, edges, tubes, notes


def build(T, rock=None) -> list[Cave]:
    spec = T.spec.get("caves") or {}
    return [_cave(T, name, c, rock) for name, c in spec.items()]


def _xy(T, ref):
    xy, h, d = T.address(ref)
    return np.asarray(xy, float), float(h), (None if d is None else np.asarray(d, float)[:2])


def _cave(T, name, c, rock):
    kind = c.get("kind", "sea")
    if kind not in KINDS:
        raise ValueError(f"cave {name!r}: kind {kind!r}: use one of {sorted(KINDS)}")
    K = {**KINDS[kind], **{k: c[k] for k in ("width", "height") if k in c}}
    sea = _sea(T)
    seed = zlib.crc32(name.encode()) % 10000
    rk = rock or {"bed": 3.0}
    bed = rk["bed"]
    nodes, notes = {}, []

    def boff(xy):  # how far the beds are shifted at xy (the rock's own beds; level beds without it)
        xy = np.atleast_2d(xy)
        return rk["bed_offset"](xy) if rk.get("bed_offset") else np.zeros(len(xy))

    def snap(xy, z):  # karst floors lie on bedding planes (the same beds as the rock's character)
        off = float(boff(xy)[0])
        return math.floor((z + off) / bed) * bed - off

    for n, ch in (c.get("chambers") or {}).items():
        xy, g, _ = _xy(T, ch["at"])
        size = ch.get("size", K["chamber"])
        rw, rh = (float(size), 0.6 * float(size)) if np.isscalar(size) else map(float, size)
        if "z" in ch:
            z = float(ch["z"])
        elif "depth" in ch or K["depth"] is not None:  # depth: the chamber's floor below the ground over it
            z = g - float(ch.get("depth", K["depth"]))
        else:  # a sea cave's chamber: its floor at the water
            z = (sea if sea is not None else g) - 0.3
        if kind == "karst":
            z = snap(xy, z)
        nodes[n] = {"xy": xy, "z": z, "rw": rw, "rh": rh, "type": "chamber", "ground": g}
    for n, en in (c.get("entrances") or {}).items():
        xy, g, _ = _xy(T, en["at"])
        nodes[n] = {"xy": xy, "z": None, "type": "entrance", "shaft": bool(en.get("shaft")), "ground": g,
                    "at": en["at"]}
    edges = []
    for p in c.get("passages") or []:
        if isinstance(p, (list, tuple)):
            p = {"from": p[0], "to": p[1]}
        for e in (p["from"], p["to"]):
            if e not in nodes:
                raise ValueError(f"cave {name!r}: passage end {e!r} is neither an entrance nor a chamber")
        edges.append(p)
    # entrances: a shaft drops from the ground straight down to the passage it serves; a mouth is where that
    # passage, heading out of the rock, meets the open (the cliff foot, a hillside)
    for n, nd in nodes.items():
        if nd["type"] != "entrance":
            continue
        other = next((nodes[e["to"] if e["from"] == n else e["from"]] for e in edges if n in (e["from"], e["to"])),
                     None)
        if other is None:
            raise ValueError(f"cave {name!r}: entrance {n!r} has no passage")
        if nd["shaft"]:
            nd["z"] = other["z"] if other["z"] is not None else nd["ground"] - K["depth"]
            continue
        if kind == "sea":
            nd["z"] = (sea if sea is not None else nd["ground"]) - 0.5
        else:  # a hillside mouth: the floor where the ground is, the passage descending into the hill from there
            nd["z"] = nd["ground"] - 0.3
        t = other["xy"] - nd["xy"]
        t /= max(np.linalg.norm(t), 1e-9)
        # pulled back to where the rock begins along the way in, and a little beyond (into the open)
        if T.height(nd["xy"]) >= nd["z"] + 0.5 * K["height"]:
            back = _daylight(T, nd["xy"], -t, nd["z"] + 0.5 * K["height"], reach=150) or 0.0
            nd["xy"] = nd["xy"] - t * back
        nd["xy"] = nd["xy"] - t * 0.5 * K["width"]
    tubes = []
    common = dict(op="subtract", blend=float(c.get("blend", 0.8)), rough=float(c.get("rough", K["rough"])),
                  rough_scale=3.0)
    for i, e in enumerate(edges):
        a, b = nodes[e["from"]], nodes[e["to"]]
        w, h = float(e.get("width", K["width"])), float(e.get("height", K["height"]))
        pts = [a["xy"], *[_xy(T, v)[0] for v in e.get("via", [])], b["xy"]]
        xy, s = _resample(np.array(pts), 3.0)
        L = s[-1]
        # the floor: straight between the nodes' floors, or following the ground (lava), or the beds (karst)
        f = s / max(L, 1e-9)
        wander = 0.06 * L * math.sin(seed + i) * np.sin(np.pi * f)
        if len(xy) > 1:
            tang = np.gradient(xy, axis=0)
            tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
            xy = xy + wander[:, None] * np.c_[-tang[:, 1], tang[:, 0]]
        # level through the chambers at either end, sloping only between them (a passage leaving a hall part way up
        # its wall left a 2 m ledge)
        ra = a["rw"] if a["type"] == "chamber" else 0.0
        rb = b["rw"] if b["type"] == "chamber" else 0.0
        g_ = np.clip((s - ra) / max(L - (ra + rb), 1e-6), 0, 1)
        fl = a["z"] + (b["z"] - a["z"]) * g_
        if kind == "lava":  # a tube runs at a steady depth under the ground it follows
            roof = float(e.get("roof", K["depth"] - h))
            g = T.sample(xy)
            fl = np.minimum(g - roof - h, fl + 0.0) if e.get("level") else g - roof - h
            fl[0], fl[-1] = a["z"], b["z"]
        if kind == "karst":  # each end's floor carried along its own bedding plane (they dip), handing over between
            off = boff(xy)
            oa, ob = float(boff(a["xy"])[0]), float(boff(b["xy"])[0])
            fl = (a["z"] + oa - off) * (1 - g_) + (b["z"] + ob - off) * g_
        node_seed = zlib.crc32(f"{name}:{i}".encode()) % 10000
        if kind == "karst":
            # keyhole: the phreatic tube up top along the bed, the vadose slot cut down below it
            r = 0.5 * w
            tubes.append(Tube(f"{name}:{i}", np.c_[xy, fl + h - r], r, r, None, seed=node_seed, **common))
            tubes.append(Tube(f"{name}:{i}:slot", np.c_[xy, fl], 0.3 * w, h - r, fl, seed=node_seed + 1, **common))
        else:
            tubes.append(Tube(f"{name}:{i}", np.c_[xy, fl], 0.5 * w, h, fl, seed=node_seed, **common))
        e["_xy"], e["_floor"], e["_w"], e["_h"] = xy, fl, w, h
        if kind == "lava" and c.get("skylights", True):  # where the roof is thin, it fell in
            every = float(c.get("skylight_every", 60.0))
            g = T.sample(xy)
            for sk in np.arange(every / 2, L, every):
                j = int(np.argmin(np.abs(s - sk)))
                if g[j] - (fl[j] + h) < 5.0:
                    tubes.append(Tube(f"{name}:{i}:skylight{j}", [[*xy[j], fl[j] + h], [*xy[j], g[j] + 2]],
                                      0.35 * w, 0.35 * w, None, seed=node_seed + 7, **common))
    for n, nd in nodes.items():
        if nd["type"] == "chamber":
            tubes.append(Tube(f"{name}:{n}", [[*nd["xy"], nd["z"]]], nd["rw"], nd["rh"], nd["z"],
                              seed=zlib.crc32(n.encode()) % 10000, **common))
        elif nd["shaft"]:  # a sinkhole: a round shaft from the passage's roof up through the ground, flared at the top
            r = 0.4 * K["width"] + 0.5
            g = nd["ground"]
            tubes.append(Tube(f"{name}:{n}", [[*nd["xy"], nd["z"]], [*nd["xy"], g - 1.5], [*nd["xy"], g + 3]],
                              [r, r, 2.2 * r], [r, r, 2.2 * r], nd["z"], **common))  # (flat-bottomed: no pit)
    for n, nd in nodes.items():
        over = nd["ground"] - nd["z"]
        notes.append(f"cave {name} ({kind}): {nd['type']} {n} at [{nd['xy'][0]:.0f}, {nd['xy'][1]:.0f}], floor "
                     f"{nd['z']:+.1f} m, {over:.0f} m under the ground" + (" (a shaft down to it)" if nd.get("shaft")
                                                                             else ""))
    return Cave(name, kind, nodes, edges, tubes, notes)


def _resample(P, step):
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    sc = np.r_[0, np.cumsum(seg)]
    s = np.linspace(0, sc[-1], max(2, int(math.ceil(sc[-1] / step)) + 1))
    return np.c_[np.interp(s, sc, P[:, 0]), np.interp(s, sc, P[:, 1])], s


# ---------------------------------------------------------------- walking through

def check(caves: list[Cave], field, height=1.8, radius=0.25, step=0.6, sea=None) -> list[str]:
    """Walk a person through every passage (every 0.5 m along its line): the floor under them, headroom, the clear
    width at knee, waist and head height, and the body as a capsule (radius clear of rock from above a step to the top
    of the head, the rule measure.clearance uses in buildings). Steps up to `step` (a scramble in a cave). Water: the
    depth over the floor where it's under the sea (wading to 1 m, then swimming)."""
    lines = []
    for cv in caves:
        for i, e in enumerate(cv.edges):
            xy, fl0 = e["_xy"], e["_floor"]
            seg = np.linalg.norm(np.diff(xy, axis=0), axis=1)
            sc = np.r_[0, np.cumsum(seg)]
            s = np.arange(0, sc[-1] + 1e-9, 0.5)
            P = np.c_[np.interp(s, sc, xy[:, 0]), np.interp(s, sc, xy[:, 1])]
            f0 = np.interp(s, sc, fl0)
            tang = np.gradient(P, axis=0)
            tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
            side = np.c_[-tang[:, 1], tang[:, 0]]
            # floor and roof along vertical lines through the passage's middle
            zs = np.arange(-3.0, e["_h"] + 6.0, 0.05)
            col = np.empty((len(P), len(zs), 3))
            col[..., :2] = P[:, None, :]
            col[..., 2] = f0[:, None] + zs[None, :]
            F = field.value(col.reshape(-1, 3)).reshape(len(P), len(zs))
            mid = int(np.searchsorted(zs, 0.5 * e["_h"]))
            floor = np.full(len(P), np.nan)
            head = np.full(len(P), np.nan)
            for j in range(len(P)):
                air = F[j] > 0
                if not air[mid]:
                    continue
                below = np.flatnonzero(~air[:mid])
                above = np.flatnonzero(~air[mid:])
                floor[j] = f0[j] + zs[below[-1] + 1] if len(below) else np.nan
                head[j] = (f0[j] + zs[mid + above[0]] if len(above) else np.inf) - floor[j]
            if sea is not None:  # standing in water: the floor is under the sea
                wet = np.nan_to_num(sea - floor, nan=0.0).clip(0)
            else:
                wet = np.zeros(len(P))
            ok = ~np.isnan(floor)
            base = np.where(ok, floor, f0)
            widths = []
            rs = np.arange(0, 6.0, 0.05)
            for hz in (0.5, 1.0, 1.6):
                both = np.zeros(len(P))
                for sg in (1, -1):
                    pts = P[:, None, :] + sg * side[:, None, :] * rs[None, :, None]
                    q = np.c_[pts.reshape(-1, 2), np.repeat(base + hz, len(rs))]
                    solid = field.value(q).reshape(len(P), len(rs)) < 0
                    both += np.where(solid.any(1), rs[solid.argmax(1)], rs[-1])
                widths.append(both)
            width = np.min(widths, 0)
            # the body as a capsule, at the line or stepped up to 0.8 m aside (a person picks their way through): the
            # best of those offsets that has a floor near this one
            # (tested by sign on a ring `radius` round each point of the body's axis, not by the field's value: with
            # rock relief and blended passages the field is no distance, and read 0.2 in a 1.3 m gap)
            hz = np.linspace(min(step, 0.3) + radius, height - radius, 6)
            ring = np.array([[math.cos(a), math.sin(a)] for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)])
            fits = np.zeros(len(P), bool)
            for off in (0.0, 0.4, -0.4, 0.8, -0.8):
                Q = P + off * side
                pts = (Q[:, None, None, :] + radius * ring[None, None, :, :]) * np.ones((1, len(hz), 1, 1))
                zz = np.broadcast_to((base[:, None] + hz[None, :])[:, :, None], pts.shape[:3])
                q = np.c_[pts.reshape(-1, 2), zz.reshape(-1)]
                ok_ = (field.value(q) > 0).reshape(len(P), -1).all(1)
                under = field.value(np.c_[Q, base - 0.15]) < 0  # standing on rock there, not over a hole
                fits |= ok_ & (under | (off == 0.0))
            clear = np.where(fits, radius, 0.0)
            steps = np.abs(np.diff(base[ok])) if ok.sum() > 1 else np.zeros(1)
            blocked = int((~ok).sum())
            low = int((ok & (head < height)).sum())
            tight = int((ok & ((clear < radius) | (width < 2 * radius))).sum())
            swim = int((wet > 1.0).sum())
            passes = not blocked and not low and not tight and (steps.max() if len(steps) else 0) <= step
            bad_at = np.flatnonzero(ok & ((clear < radius) | (width < 2 * radius) | (head < height)))
            if len(steps) and steps.max() > step:
                bad_at = np.r_[bad_at, np.flatnonzero(ok)[int(np.argmax(steps))]]
            why = [w for w, bad in (("blocked", blocked), ("low headroom", low), ("too tight", tight),
                                    (f"a step over {step} m", len(steps) and steps.max() > step)) if bad]
            lines.append(
                f"{cv.name} {e['from']} -> {e['to']}: {s[-1]:.0f} m, floor {np.nanmin(base):+.1f}..{np.nanmax(base):+.1f}"
                f" m, headroom min {np.nanmin(head[ok]) if ok.any() else float('nan'):.1f} m, width min "
                f"{width[ok].min() if ok.any() else 0:.1f} m, largest step {steps.max() if len(steps) else 0:.2f} m"
                + (f", water up to {wet.max():.1f} m deep" + (f" (swim {swim * 0.5:.0f} m)" if swim else " (wading)")
                   if wet.max() > 0.05 else "")
                + (": a person PASSES" if passes else f": does NOT pass ({', '.join(why)}; first at "
                   f"[{P[bad_at[0], 0]:.0f}, {P[bad_at[0], 1]:.0f}, {base[bad_at[0]]:.1f}], {s[bad_at[0]]:.0f} m along)"))
    return lines


def node_xyz(caves: list[Cave], ref: str, lift=1.7):
    """"cave.node" -> a point `lift` above that node's floor (an eye inside a cave)."""
    cn, n = ref.split(".", 1)
    for cv in caves:
        if cv.name == cn and n in cv.nodes:
            nd = cv.nodes[n]
            return [float(nd["xy"][0]), float(nd["xy"][1]), float(nd["z"] + lift)]
    raise ValueError(f"no cave node {ref!r}")
