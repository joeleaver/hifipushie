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

from .terrain_mesh import Mound, Tube, _daylight, _downhill, _sea, smoothstep

KINDS = {
    "sea": {"width": 6.0, "height": 4.5, "chamber": 8.0, "depth": None, "rough": 0.4},
    "karst": {"width": 4.0, "height": 4.5, "chamber": 9.0, "depth": 18.0, "rough": 0.12, "doline": 18.0, "relief": 0.0,
              "rough_scale": 6.0},
    "lava": {"width": 7.0, "height": 4.5, "chamber": 9.0, "depth": 7.5, "rough": 0.25},
}


class Cave:
    def __init__(self, name, kind, nodes, edges, tubes, notes, dolines=()):
        self.name, self.kind, self.nodes, self.edges, self.tubes, self.notes = name, kind, nodes, edges, tubes, notes
        self.dolines = list(dolines)  # ground edits (terrain_mesh.dig_doline)


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
    notes_pre = []
    if kind == "lava" and c.get("flow") and not c.get("passages"):
        # a tube down a lava flow (terrain_volcano's line): from a collapse pit at `from` to another at `to` (shares
        # of the flow's length), following the flow's line
        fl_, f0, f1 = c["flow"], float(c.get("from", 0.25)), float(c.get("to", 0.85))
        if fl_ not in getattr(T, "lines", {}):
            raise ValueError(f"cave {name!r}: no lava flow {fl_!r} (flows: "
                             f"{sorted(k for k, v in getattr(T, 'lines', {}).items() if getattr(v, 'kind', '') == 'flow')})")
        # (the line's s is a fraction 0..1: read as metres it gave one via point, and the tube cut straight chords
        # across the flow's bends)
        L_ = _line_length(T.lines[fl_])
        n_ = max(2, int((f1 - f0) * L_ / 15))
        via = [f"{fl_}@{t:.4f}" for t in np.linspace(f0, f1, n_ + 1)[1:-1]]
        if c.get("grade") is not None:  # walkable: switchbacks across the flow (a tube follows its ground's grade)
            via, zz, land = _switchbacks(T, fl_, f0, f1, float(c["grade"]), float(c.get("swing", SWING)))
            notes_pre.append(f"cave {name} (lava): {zz}")
        c = {**c, "entrances": {**(c.get("entrances") or {}), "upper_pit": {"at": f"{fl_}@{f0:.4f}"},
                                "lower_pit": {"at": f"{fl_}@{f1:.4f}"}},
             "passages": [{"from": "upper_pit", "to": "lower_pit", "wander": 0, "via": via,
                           **({"grade": float(c["grade"]), "_land": land, "_turns": via}
                              if c.get("grade") is not None else {})}]}
    seed = zlib.crc32(name.encode()) % 10000
    rk = rock or {"bed": 3.0}
    bed = rk["bed"]
    nodes, notes = {}, list(notes_pre)

    def boff(xy):  # how far the beds are shifted at xy (the rock's own beds; level beds without it)
        xy = np.atleast_2d(xy)
        return rk["bed_offset"](xy) if rk.get("bed_offset") else np.zeros(len(xy))

    def snap(xy, z):  # karst floors lie on bedding planes (the same beds as the rock's character)
        off = float(boff(xy)[0])
        return math.floor((z + off) / bed) * bed - off

    # thin beds inside the rock's beds (~1.2-1.5 m: a passage shows a few), on the same planes
    sub = bed / max(1, round(bed / 1.3))
    beds = {"bed": sub, "amp": float(c.get("ledges", 0.45)), "off": rk.get("bed_offset"), "seed": seed}

    def sub_snap(xy, z):  # the nearest thin bedding plane (a flat roof)
        off = boff(xy)
        return np.round((np.asarray(z, float) + off) / sub) * sub - off

    for n, ch in (c.get("chambers") or {}).items():
        xy, g, d = _xy(T, ch["at"])
        if "in" in ch:  # metres into the rock along the address's own direction (e.g. from "cliff_foot:<address>")
            if d is None:
                raise ValueError(f"cave {name!r}: chamber {n!r}: \"in\" needs an address with a direction into the "
                                 f"rock, e.g. \"cliff_foot:<address>\" ({ch['at']!r} has none)")
            xy = xy + float(ch["in"]) * d / max(np.linalg.norm(d), 1e-9)
            g = float(T.height(xy))
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
        # a lava tube is entered where its roof fell in (a collapse pit), never through a hillside mouth
        nodes[n] = {"xy": xy, "z": None, "type": "entrance", "shaft": bool(en.get("shaft")) or kind == "lava",
                    "ground": g, "at": en["at"], "doline": en.get("doline", kind == "karst")}
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
    en_spec = c.get("entrances") or {}
    for n, nd in nodes.items():
        if nd["type"] != "entrance":
            continue
        other = next((nodes[e["to"] if e["from"] == n else e["from"]] for e in edges if n in (e["from"], e["to"])),
                     None)
        if other is None:
            raise ValueError(f"cave {name!r}: entrance {n!r} has no passage")
        if nd["shaft"]:
            if kind == "lava":  # the tube's own depth under the ground here
                nd["z"] = nd["ground"] - K["depth"]
            else:
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
        if kind != "sea":
            # the door's floor no higher than the ground it opens onto (where it ended up: pulled back to the rock's
            # edge and out into the open, the ground there is often lower than at the address: a geo's floor at a
            # cliff foot. Above it, the passage's floor stood over the open ground as a step)
            nd["z"] = min(nd["z"], float(T.height(nd["xy"])))
        if "z" in en_spec.get(n, {}):  # the designer's door floor
            nd["z"] = float(en_spec[n]["z"])
    tubes, rubble = [], []
    common = dict(op="subtract", blend=float(c.get("blend", 0.8)), rough=float(c.get("rough", K["rough"])),
                  rough_scale=float(c.get("rough_scale", K.get("rough_scale", 3.0))), relief=float(c.get("relief", K.get("relief", 1.0))))
    for i, e in enumerate(edges):
        a, b = nodes[e["from"]], nodes[e["to"]]
        w, h = float(e.get("width", K["width"])), float(e.get("height", K["height"]))
        pts = [a["xy"], *[_xy(T, v)[0] for v in e.get("via", [])], b["xy"]]
        xy, s = _resample(np.array(pts), 3.0 if e.get("grade") is None else 1.5)
        L = s[-1]
        # the floor: straight between the nodes' floors, or following the ground (lava), or the beds (karst)
        f = s / max(L, 1e-9)
        wander = float(e.get("wander", 0.06)) * L * math.sin(seed + i) * np.sin(np.pi * f)
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
            # (the flow's grade, not its surface: levees and pressure ridges put 1-3 m steps in a floor that followed
            # the ground itself)
            from scipy.ndimage import gaussian_filter1d
            roof = float(e.get("roof", K["depth"] - h))
            step = float(np.median(np.diff(s))) if len(s) > 1 else 3.0
            g = gaussian_filter1d(T.sample(xy), 12.0 / max(step, 1e-6), mode="nearest")
            fl = np.minimum(g - roof - h, fl + 0.0) if e.get("level") else g - roof - h
            if e.get("grade") is not None and len(fl) > 1:
                # a walkable tube: the highest floor no steeper than "grade" that is nowhere above its depth under the
                # ground (where the ground falls faster than the grade, the tube runs deeper: its pits get deeper).
                # (kept as near its depth from either end and met half way, it rode out of the ground wherever a
                # switchback left the flow's sheet: the cone's flank beside a 14 m flow is 14 m lower)
                gr = float(e["grade"])
                # (under the ground as sampled across the tube's width, not only its smoothed line: by a flow's
                # edge the smoothing stood metres over the flank and the roof broke out)
                tg = np.gradient(xy, axis=0)
                tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
                sd_ = np.c_[-tg[:, 1], tg[:, 0]]
                raw = np.min([T.sample(xy + o_ * sd_) for o_ in (-0.5 * w, 0.0, 0.5 * w)], axis=0)
                fl = np.minimum(fl, raw - roof - h)
                # (level through each turn's landing: the distance that counts for the grade leaves them out)
                run = np.r_[0.0, np.diff(s)]
                for tq in e.get("_turns") or []:
                    if isinstance(tq, (list, tuple)) and len(tq) == 2:
                        sc_ = s[int(np.argmin(np.linalg.norm(xy - np.asarray(tq, float), axis=1)))]
                        run[np.abs(s - sc_) < float(e.get("_land", 0.0))] = 0.0
                # (and level under each pit's pile of fallen roof: a tube falling away under it left the pile a
                # slope of blocks with 0.7 m steps)
                pit_r = 1.7 * (0.6 * K["width"] + 0.5) + 4.0  # (the pile, its blend and its rough toe)
                run[(s < pit_r) | (s > L - pit_r)] = 0.0
                se = np.cumsum(run)
                fl = np.min(fl[None, :] + gr * np.abs(se[:, None] - se[None, :]), axis=1)
            for nd_, k_ in ((a, 0), (b, -1)):  # a pit's floor is the tube's (a chamber keeps its own)
                if nd_["type"] == "entrance":
                    nd_["z"] = float(fl[k_])
            fl[0], fl[-1] = a["z"], b["z"]
        if kind == "karst":  # each end's floor carried along its own bedding plane (they dip), handing over between
            off = boff(xy)
            oa, ob = float(boff(a["xy"])[0]), float(boff(b["xy"])[0])
            lin = a["z"] * (1 - g_) + b["z"] * g_
            # (eased in from a hillside mouth over MOUTH_EASE m: the floor leaves the door on its plain grade, so
            # it meets the ground outside. Taken on at once, the beds' wander lifted kaze_cave's floor 1.5 m in the
            # first 6 m from its geo door and left a 0.7 m step where the passage left the open ground)
            ease = np.ones(len(s))
            for nd_, d_ in ((a, s), (b, L - s)):
                if nd_["type"] == "entrance" and not nd_["shaft"]:
                    u = np.clip(d_ / MOUTH_EASE, 0, 1)
                    ease *= u * u * (3 - 2 * u)
            # (and the beds' wander spread over BED_SPREAD m: by a cliff the beds' offset changes metres in a few
            # metres of plan, and a floor that took it at once climbed a staircase of 0.6 m steps (the slot's floor
            # is flat between its nodes, 3 m apart). The ends stay on their own beds)
            from scipy.ndimage import gaussian_filter1d
            D = (a["z"] + oa - off) * (1 - g_) + (b["z"] + ob - off) * g_ - lin
            if len(s) > 2:
                step = float(np.median(np.diff(s)))
                Ds = gaussian_filter1d(D, BED_SPREAD / max(step, 1e-6), mode="nearest")
                D = Ds - (Ds[0] - D[0]) * (1 - f) - (Ds[-1] - D[-1]) * f
            fl = lin + D * ease
        node_seed = zlib.crc32(f"{name}:{i}".encode()) % 10000
        if kind == "karst":
            # keyhole: the phreatic tube up top, spread wide along a bedding plane that is its flat roof, the vadose
            # slot cut down below it by the stream; thin beds stand out of the walls as ledges or are set back
            roof = sub_snap(xy, fl + h)
            top_h = 0.3 * w
            tubes.append(Tube(f"{name}:{i}", np.c_[xy, roof - 0.5 * top_h], 0.55 * w, top_h, None, seed=node_seed,
                              roof=roof, beds=beds, **common))
            tubes.append(Tube(f"{name}:{i}:slot", np.c_[xy, fl], 0.3 * w, roof - fl - 0.5 * top_h, fl,
                              seed=node_seed + 1, beds=beds, **common))
        elif kind == "lava":  # benches along the walls where the flow's level stood a while (lava shelves)
            tubes.append(Tube(f"{name}:{i}", np.c_[xy, fl], 0.5 * w, h, fl, seed=node_seed,
                              beds={"bed": 1.4, "amp": float(c.get("benches", 0.3)), "off": None, "seed": seed},
                              **common))
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
                    # the fallen roof: a low pile of breakdown on the floor under it
                    near_ = np.linalg.norm(xy - xy[j], axis=1) < 0.45 * w
                    base = float(fl[near_].min())
                    rubble.append(((*xy[j], base), 0.45 * w, 0.7 + fl[j] - base, node_seed + 8))
    dolines = []
    for n, nd in nodes.items():
        if nd["type"] == "chamber":
            kw = {}
            if kind == "karst":  # a hall under a bedding plane: a flat roof, bedded walls
                kw = {"roof": float(sub_snap(nd["xy"], nd["z"] + 0.8 * nd["rh"])[0]), "beds": beds}
            tubes.append(Tube(f"{name}:{n}", [[*nd["xy"], nd["z"]]], nd["rw"], nd["rh"], nd["z"],
                              seed=zlib.crc32(n.encode()) % 10000, **common, **kw))
        elif nd["shaft"]:  # a sinkhole: a round shaft from the passage's roof up through the ground, flared at the top
            r = (0.6 if kind == "lava" else 0.4) * K["width"] + 0.5  # (a collapse pit is as wide as the tube)
            g = nd["ground"]
            if nd.get("doline"):
                # a doline: a wide grassy funnel (tens of metres) dug into the ground, the shaft opening in its throat.
                # Deep enough to read, never so deep the shaft's rock over the passage goes (>= 2 m of it)
                dl = nd["doline"] if isinstance(nd["doline"], dict) else {}
                R = float(dl.get("radius", K["doline"]))
                roof = nd["z"] + float(max((e.get("height", K["height"]) for e in edges if n in (e["from"], e["to"])),
                                           default=K["height"]))
                # the bowl, then a rocky pit (a scarp round the throat) the shaft drops out of; >= 1.5 m of rock
                # left over the passage
                avail = g - roof - 1.5
                D = float(dl.get("depth", max(1.0, min(0.3 * R, 0.65 * avail))))
                scarp = float(dl.get("scarp", float(np.clip(avail - D, 0.0, 3.0))))
                throat = 1.6 * r
                dolines.append({"xy": nd["xy"].copy(), "radius": R, "depth": D, "throat": throat, "seed": seed})
                nd["doline"] = {"radius": R, "depth": D, "scarp": scarp}
                g = g - D
                if scarp > 0.3:
                    tubes.append(Tube(f"{name}:{n}:pit", [[*nd["xy"], g - scarp], [*nd["xy"], g + 3]],
                                      [throat, 1.5 * throat], [throat, 1.5 * throat], g - scarp,
                                      **{**common, "rough": 0.4, "relief": 1.0}))
            tubes.append(Tube(f"{name}:{n}", [[*nd["xy"], nd["z"]], [*nd["xy"], g - 1.5], [*nd["xy"], g + 3]],
                              [r, r, 2.2 * r], [r, r, 2.2 * r], nd["z"], **common))  # (flat-bottomed: no pit)
            if kind == "lava":  # a collapse pit: the roof that fell lies in it, a slope of blocks to climb down
                # standing on the lowest floor under it (the tube falls away from the pit: a mound set on the pit's
                # floor ran on down the tube as a long ramp, or overhung it)
                rr_ = 1.7 * r
                base = min([nd["z"]] + [float(np.min(e["_floor"][np.linalg.norm(e["_xy"] - nd["xy"], axis=1) < rr_]))
                                        for e in edges if n in (e["from"], e["to"]) and "_floor" in e])
                # (no taller than a third of the tube: under a deep pit (a graded tube's) the pile closed the passage)
                hp_ = max((float(e.get("height", K["height"])) for e in edges if n in (e["from"], e["to"])),
                          default=K["height"])
                rubble.append(((*nd["xy"], base), rr_, min(0.18 * (nd["ground"] - nd["z"]), 0.3 * hp_)
                               + (nd["z"] - base), zlib.crc32(n.encode()) % 10000))
    for k_, (at, rr, hh, sd) in enumerate(rubble):
        # a low cone of blocks (as an ellipsoid or a tube, its round ends made a step or a dome nobody could climb)
        tubes.append(Mound(f"{name}:rubble{k_}", at, rr, hh, seed=sd))
    for n, nd in nodes.items():
        over = nd["ground"] - nd["z"]
        notes.append(f"cave {name} ({kind}): {nd['type']} {n} at [{nd['xy'][0]:.0f}, {nd['xy'][1]:.0f}], floor "
                     f"{nd['z']:+.1f} m, {over:.0f} m under the ground" + (" (a shaft down to it)" if nd.get("shaft")
                                                                             else "")
                     + (f", in a doline {2 * nd['doline']['radius']:.0f} m across and {nd['doline']['depth']:.0f} m "
                        f"deep" if nd.get("shaft") and isinstance(nd.get("doline"), dict) else ""))
    return Cave(name, kind, nodes, edges, tubes, notes, dolines)


SWING = 30.0  # m: how far a walkable lava tube's switchbacks reach either side of its flow's line


def _flow_profile(T, fl_, f0, f1):
    """A flow's line between shares f0..f1: points, arc length, the ground along it smoothed as a tube follows it."""
    from scipy.ndimage import gaussian_filter1d
    L = T.lines[fl_]
    n = _line_length(L)
    t = np.linspace(f0, f1, max(20, int((f1 - f0) * n / 2)))
    xy = np.array([L.at(float(x))[0] for x in t])
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    g = gaussian_filter1d(T.sample(xy), 12.0 / max(s[-1] / (len(t) - 1), 1e-6), mode="nearest")
    return t, xy, s, g


def _switchbacks(T, fl_, f0, f1, grade, swing):
    """Via points that zigzag a lava tube across its flow so it falls no faster than `grade`: legs across the flow
    (nearly along the slope's contours) from one side to the other, `swing` m either side at most, the tube still at
    its depth under the ground. (via points, a note)"""
    t, xy, s, g = _flow_profile(T, fl_, f0, f1)
    Lf, D = float(s[-1]), abs(float(g[-1] - g[0]))
    need = D / max(grade, 1e-3)
    if need <= 1.02 * Lf:
        k = max(2, int(Lf / 15))
        return ([f"{fl_}@{x:.4f}" for x in np.linspace(f0, f1, k + 1)[1:-1]],
                f"its flow falls {D:.0f} m in {Lf:.0f} m: no switchbacks needed for a grade of {100 * grade:.0f}%",
                0.0)
    # n corners, W m either side: legs of sqrt((Lf / n)^2 + (2 W)^2) m, each turn a level landing as long as the two
    # legs beside it still overlap (a walker there stood on the next leg's floor, a grade x that far lower: 2 m
    # steps at every hairpin). The fewest corners nearest the flow that give `need` m of sloping tube
    wd = KINDS["lava"]["width"] + 1.5

    def fit(W):
        for n in range(1, 120):
            a = Lf / n
            leg = math.hypot(a, 2 * W)
            land = wd / (2 * math.sin(math.atan2(a, 2 * W)))
            if leg - 2 * land <= 0:
                return None
            if n * (leg - 2 * land) >= need:
                return n, land
        return None
    W, got = None, None
    for W_ in np.arange(10.0, 400.0, 2.0):
        got = fit(float(W_))
        if got:
            W = float(W_)
            break
    if got is None:
        return ([f"{fl_}@{x:.4f}" for x in np.linspace(f0, f1, max(2, int(Lf / 15)) + 1)[1:-1]],
                f"its flow falls {D:.0f} m in {Lf:.0f} m: no switchbacks fit (a {100 * grade:.0f}% tube needs "
                f"{need:.0f} m): a gentler stretch (\"from\", \"to\")", 0.0)
    short = W > swing
    need_w = W
    if short:  # the most that fits within the swing: the report says the tube is still too steep and why
        W = swing
        n = max(1, math.ceil(math.sqrt(max(need ** 2 - Lf ** 2, 0.0)) / (2 * swing)))
        land = wd / (2 * math.sin(math.atan2(Lf / n, 2 * W)))
    else:
        n, land = got
    tang = np.gradient(xy, axis=0)
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
    side = np.c_[-tang[:, 1], tang[:, 0]]
    # (legs along the slope's own contour, from the ground's broad gradient (a flow is a ridge of its own, and its
    # line need not run straight down the cone): square across the line, the legs fell where the line ran aslant)
    r_ = max(swing, 20.0)
    ring = r_ * np.array([[math.cos(a), math.sin(a)] for a in np.linspace(0, 2 * np.pi, 12, endpoint=False)])
    hs = T.sample((xy[:, None, :] + ring[None]).reshape(-1, 2)).reshape(len(xy), -1)
    grad = (hs[:, :, None] * ring[None]).sum(1) / (0.5 * len(ring) * r_ ** 2)
    cont = np.c_[-grad[:, 1], grad[:, 0]]
    cont /= np.maximum(np.linalg.norm(cont, axis=1, keepdims=True), 1e-9)
    side = np.where((np.einsum("ij,ij->i", cont, side) < 0)[:, None], -cont, cont)
    via = []
    for k in range(n):  # a corner per leg, alternating sides, half a leg in from either end
        j = int(np.argmin(np.abs(s - (k + 0.5) / n * Lf)))
        p = xy[j] + (1 if k % 2 == 0 else -1) * W * side[j]
        via.append([float(p[0]), float(p[1])])
    note = (f"{n} switchbacks across its flow, {W:.0f} m either side of its line, a level landing {2 * land:.0f} m "
            f"long at each turn: {need:.0f} m of sloping tube for the flow's {D:.0f} m fall in {Lf:.0f} m (grade "
            f"{100 * grade:.0f}%)")
    if short:
        note += (f"; that needs switchbacks {need_w:.0f} m either side of the flow, more than its \"swing\" "
                 f"({swing:g}): with {swing:g} it stays too steep. Give it \"swing\": {need_w:.0f}, a higher "
                 f"\"grade\", or a gentler stretch (\"from\", \"to\")")
    return via, note, land


def _resample(P, step):
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    sc = np.r_[0, np.cumsum(seg)]
    s = np.linspace(0, sc[-1], max(2, int(math.ceil(sc[-1] / step)) + 1))
    return np.c_[np.interp(s, sc, P[:, 0]), np.interp(s, sc, P[:, 1])], s


# ---------------------------------------------------------------- walking through

def check(caves: list[Cave], field, height=1.8, radius=0.25, step=0.6, sea=None, paths=None) -> list[str]:
    """Walk a person through every passage (every 0.5 m along its line): the floor under them, headroom, the clear
    width at knee, waist and head height, and the body as a capsule (radius clear of rock from above a step to the top
    of the head, the rule measure.clearance uses in buildings). Steps up to `step` (a scramble in a cave). Water: the
    depth over the floor where it's under the sea (wading to 1 m, then swimming).
    `paths` (a list): each passage's walk appended as {cave, from, to, step_m, points: [[x, y, floor z | null], ...],
    width_m, headroom_m} (the tile manifest's `cave_paths`)."""
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
            bad_at = np.flatnonzero(~ok | (clear < radius) | (width < 2 * radius) | (head < height))
            if len(steps) and steps.max() > step:
                bad_at = np.r_[bad_at, np.flatnonzero(ok)[int(np.argmax(steps))]]
            stp = ""
            if len(steps) and steps.max() > step:  # (where the largest is: the advice depends on it)
                ks = np.flatnonzero(ok)[int(np.argmax(steps))]
                stp = f" ({steps.max():.2f} m at [{P[ks, 0]:.0f}, {P[ks, 1]:.0f}, {base[ks]:.1f}], {s[ks]:.0f} m along)"
            why = [w for w, bad in (("blocked", blocked), ("low headroom", low), ("too tight", tight),
                                    (f"a step over {step} m{stp}", len(steps) and steps.max() > step)) if bad]
            if paths is not None:  # (the walk as an engine can use it: navigation, lighting, its own walk test)
                r2 = lambda a: [None if not np.isfinite(x) else round(float(x), 2) for x in a]
                paths.append({"cave": cv.name, "from": e["from"], "to": e["to"], "step_m": 0.5,
                              "points": [[round(float(P[q, 0]), 2), round(float(P[q, 1]), 2),
                                          round(float(base[q]), 2) if ok[q] else None] for q in range(len(P))],
                              "width_m": r2(np.where(ok, width, np.nan)),
                              "headroom_m": r2(np.where(ok, np.minimum(head, 99.0), np.nan))})
            lines.append(
                f"{cv.name} {e['from']} -> {e['to']}: {s[-1]:.0f} m, floor {np.nanmin(base):+.1f}..{np.nanmax(base):+.1f}"
                f" m, headroom min {np.nanmin(head[ok]) if ok.any() else float('nan'):.1f} m, width min "
                f"{width[ok].min() if ok.any() else 0:.1f} m, largest step {steps.max() if len(steps) else 0:.2f} m"
                + (f", water up to {wet.max():.1f} m deep" + (f" (swim {swim * 0.5:.0f} m)" if swim else " (wading)")
                   if wet.max() > 0.05 else "")
                + (": a person PASSES" if passes else f": does NOT pass ({', '.join(why)}; first at "
                   f"[{P[bad_at[0], 0]:.0f}, {P[bad_at[0], 1]:.0f}, {base[bad_at[0]]:.1f}], {s[bad_at[0]]:.0f} m along)"))
    return lines


# ---------------------------------------------------------------- the early check (set_terrain / check_terrain)

GRADE_WALK = 0.25  # the steepest a cave floor stays a walk (sustained, over GRADE_RUN m): ~14 deg
GRADE_RUN = 10.0
ROOF_MIN = 1.0  # m of rock over a passage's roof away from its entrances (less: it opens to the sky)
BED_SPREAD = 12.0  # m (Gaussian sigma) over which a karst floor's climb onto its beds is spread
MOUTH_EASE = 20.0  # m from a hillside mouth over which a karst floor takes on its bedding planes' wander
MOUTH = 15.0  # m from an entrance where the roof may thin out (a mouth daylights by design)


def _line_length(L) -> float:
    n = (getattr(L, "props", None) or {}).get("length")
    if n:
        return float(n)
    return float(np.linalg.norm(np.diff(np.asarray(L.xy, float), axis=0), axis=1).sum())


def light_field(T):
    """The caves and a field to walk them in, cheaply: the height field with the volumes and caves cut out, no rock
    character (relief, beds, blocks) and no sea stacks. Seconds, where the tile export's field takes minutes."""
    from . import terrain_mesh as tm
    karst = any((c or {}).get("kind") == "karst" for c in (T.spec.get("caves") or {}).values())
    rock = tm.rock_config(T, dict(tm.DEFAULTS)) if karst else None  # (karst floors lie on the rock's beds)
    caves = build(T, rock)
    vols, _ = tm.volumes(T)
    field = tm.Field(T, vols + [tb for cv in caves for tb in cv.tubes], None,
                     dolines=[d for cv in caves for d in cv.dolines],
                     cuts=[v.cut for v in vols if getattr(v, "cut", None)])
    return caves, field


def survey(T, caves) -> list[dict]:
    """Per passage, from the skeleton and the height field: length, rise, mean grade over the sloping part, the
    steepest GRADE_RUN m, and the rock over the roof (least, away from entrances)."""
    out = []
    for cv in caves:
        for e in cv.edges:
            xy, fl, w, h = e["_xy"], np.asarray(e["_floor"], float), e["_w"], e["_h"]
            s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
            L = float(s[-1])
            a, b = cv.nodes[e["from"]], cv.nodes[e["to"]]
            ra = a["rw"] if a["type"] == "chamber" else 0.0
            rb = b["rw"] if b["type"] == "chamber" else 0.0
            run = max(L - ra - rb, 1e-6)  # (level through the chambers at either end)
            rise = float(fl[-1] - fl[0])
            # steepest sustained grade: over GRADE_RUN m windows
            steep, at = 0.0, xy[0]
            if L > 1:
                ss = np.arange(0, L + 1e-9, 1.0)
                f1 = np.interp(ss, s, fl)
                n = max(1, int(round(min(GRADE_RUN, L) / 1.0)))
                if len(ss) > n:
                    g = np.abs(f1[n:] - f1[:-n]) / (ss[n:] - ss[:-n])
                    k = int(np.argmax(g))
                    steep = float(g[k])
                    m = 0.5 * (ss[k] + ss[k + n])
                    at = np.array([np.interp(m, s, xy[:, 0]), np.interp(m, s, xy[:, 1])])
            # rock over the roof, away from the entrances
            ground = T.sample(xy)
            cover = ground - (fl + h)
            away = (s >= ra) & (s <= L - rb)  # (a chamber's own dome is judged on its own)
            if a["type"] == "entrance":
                away &= s > MOUTH + (0.0 if not a.get("shaft") else w)
            if b["type"] == "entrance":
                away &= s < L - MOUTH - (0.0 if not b.get("shaft") else w)
            roof = (float(cover[away].min()), xy[away][int(np.argmin(cover[away]))]) if away.any() else None
            out.append({"cave": cv.name, "kind": cv.kind, "from": e["from"], "to": e["to"], "length": L, "run": run,
                        "rise": rise, "grade": abs(rise) / run, "steep": steep, "steep_at": at, "roof": roof,
                        "edge": e})
    return out


def _fix(T, cv_spec, cave, sv, nodes) -> str:
    """What to change, in the designer's terms, for a passage too steep to walk."""
    a, b = nodes[sv["from"]], nodes[sv["to"]]
    lo_n, hi_n = (sv["from"], sv["to"]) if sv["rise"] > 0 else (sv["to"], sv["from"])
    lo, hi = nodes[lo_n], nodes[hi_n]
    room = GRADE_WALK * sv["run"]
    need = abs(sv["rise"]) / GRADE_WALK + (sv["length"] - sv["run"])
    ways = []
    if cave.kind == "lava" and cv_spec.get("flow"):
        return _flow_fix(T, cv_spec)
    if hi["type"] == "chamber":
        z = lo["z"] + room
        ways.append(f"put {hi_n} lower (its floor at z ~ {z:.0f}: \"z\": {z:.0f}" + _depth(hi, z) + ")")
    elif hi.get("shaft"):
        ways.append(f"{hi_n} is a shaft down to the passage: put the chamber it serves lower")
    if lo["type"] == "chamber":
        z = hi["z"] - room
        ways.append(f"put {lo_n} higher (its floor at z ~ {z:.0f}: \"z\": {z:.0f}" + _depth(lo, z) + ")")
    elif lo["type"] == "entrance" and not lo.get("shaft") and (_sea(T) is None or lo["z"] > _sea(T) + 1.0):
        ways.append(f"move {lo_n} up the hillside (a mouth's floor is where the ground is there)")
    ways.append(f"make the passage longer (at least {need:.0f} m: route it round with \"via\" points)")
    return "; or ".join(ways)


def _walk_fix(T, cv, p, why) -> str:
    """What to change for a passage the walk stops, by what stops it: a step by a mouth is where the passage's floor
    meets the ground outside (its entrance's floor: "z"), a step further in is the floor climbing too fast onto its
    beds, too tight / low is the passage's size."""
    import re
    out = []
    m = re.search(r"a step over [\d.]+ m \(([\d.]+) m at \[(-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\], (\d+) m along\)", why)
    if m:
        along = float(m[5])
        at_mouth = False
        for n_, d_ in ((p["from"], along), (p["to"], p["length"] - along)):
            nd = cv.nodes[n_]
            if nd["type"] == "entrance" and not nd.get("shaft") and d_ <= MOUTH:
                g = float(T.height(nd["xy"]))
                out.append(f"the step is {d_:.0f} m from the mouth {n_}, where the passage's floor (its door at "
                           f"{nd['z']:+.1f} m) meets the open ground ({g:+.1f} m at the door): set the door's floor "
                           f"on the entrance (\"z\": {g:.1f}) or move its \"at\" to where the ground outside is level "
                           f"with the passage; its width and height don't change a step")
                at_mouth = True
                break
        if not at_mouth:
            out.append(f"the step ({m[1]} m, {along:.0f} m along) is the floor rising faster than it runs there: make "
                       f"the passage longer (\"via\" points) or its ends' floors closer (a chamber's \"z\")"
                       + ("; a lava tube: a lower \"grade\"" if cv.kind == "lava" else "")
                       + "; width and height don't change a step")
    if any(w in why for w in ("blocked", "too tight", "low headroom")):
        out.append("where it is blocked, tight or low: widen or heighten it (\"width\", \"height\" on the passage) or "
                   "move it clear of the rock in the way")
    return "; ".join(out) or "move it clear of the rock in the way"


def _depth(nd, z):
    d = nd["ground"] - z
    return f" or \"depth\": {d:.0f}" if d > 2 else " (above the ground there: under higher ground too)"


def _flow_fix(T, c) -> str:
    """A lava tube down a flow: the stretch of the flow gentle enough to walk (its tube follows the ground's grade)."""
    from scipy.ndimage import gaussian_filter1d
    L = T.lines.get(c["flow"])
    if L is None:
        return "use a gentler flow"
    n = _line_length(L)
    t = np.linspace(0, 1, max(20, int(n / 2)))
    xy = np.array([L.at(float(x))[0] for x in t])
    g = gaussian_filter1d(T.sample(xy), 12.0 / max(n / len(t), 1e-6), mode="nearest")
    ds = n / (len(t) - 1)
    k = max(1, int(round(GRADE_RUN / ds)))
    gr = np.r_[np.abs(g[k:] - g[:-k]) / (k * ds), np.zeros(k)]
    ok = gr <= GRADE_WALK
    best, cur, start = (0, 0), 0, 0
    for i, v in enumerate(ok):
        if v:
            if cur == 0:
                start = i
            cur += 1
            if cur > best[1] - best[0]:
                best = (start, i + 1)
        else:
            cur = 0
    i0, i1 = best
    mean = abs(float(g[-1] - g[0])) / n
    walk = (f"set \"grade\": {GRADE_WALK - 0.05:.2f} on the cave (the tube then switchbacks across the flow, up to "
            f"\"swing\" m either side of it, default {SWING:.0f}, falling no faster than that)")
    if c.get("grade") is not None:
        walk = (f"its \"grade\" ({c['grade']}) is followed by switchbacks, but the ground along them still falls "
                f"faster: a lower \"grade\", more \"swing\" (now {c.get('swing', SWING)}), or a gentler stretch "
                f"(\"from\", \"to\")")
    if (i1 - i0) * ds < 30:
        return (f"the flow \"{c['flow']}\" falls {100 * mean:.0f}% on average and has no stretch of 30 m gentler than "
                f"{100 * GRADE_WALK:.0f}% (a tube follows its flow's grade): {walk}")
    return (f"{walk}; or run it on the flow's gentle stretch: \"from\": {t[i0]:.2f}, \"to\": "
            f"{t[min(i1, len(t) - 1)]:.2f} ({(i1 - i0) * ds:.0f} m under {100 * GRADE_WALK:.0f}%)")


def early(T) -> tuple[list[str], list[str]]:
    """The caves checked before any export (set_terrain / check_terrain's report): every passage walked by
    `check` through `light_field` (the same rule as the tile export's walk, without the rock's relief), plus the
    skeleton's grades and roof cover, each problem with a fix in the spec's terms. (report lines, warnings)."""
    spec = T.spec.get("caves") or {}
    if not spec:
        return [], []
    import json
    key = json.dumps([spec, T.spec.get("volumes") or {}], sort_keys=True, default=str)
    got = getattr(T, "_cave_early", None)
    if got and got[0] == key:
        return got[1], got[2]
    import time
    t0 = time.time()
    try:
        caves, field = light_field(T)
    except ValueError as e:
        lines, warns = [f"caves: can't build: {e}"], [f"caves: {e}"]
        T._cave_early = (key, lines, warns)
        return lines, warns
    from .terrain_mesh import _sea
    walk = check(caves, field, sea=_sea(T))
    sv = survey(T, caves)
    lines = [f"caves (walked now through the height field with the caves cut out, no rock relief: "
             f"{time.time() - t0:.0f} s; the tile export walks them again in the finished rock):"]
    warns = []
    for cv in caves:  # what the build chose for a walkable lava tube (switchbacks)
        lines += ["  " + nt for nt in cv.notes if "switchback" in nt
                  or (cv.kind == "lava" and "entrance" in nt and any("switchback" in x for x in cv.notes))]
    for wl, p in zip(walk, sv):
        cv = next(c for c in caves if c.name == p["cave"])
        lines.append("  " + wl)
        g = (f"    {'climbs' if p['rise'] > 0 else 'falls'} {abs(p['rise']):.0f} m over {p['run']:.0f} m of slope "
             f"({100 * p['grade']:.0f}%), steepest {GRADE_RUN:.0f} m {100 * p['steep']:.0f}% at "
             f"[{p['steep_at'][0]:.0f}, {p['steep_at'][1]:.0f}]")
        if p["roof"] is not None:
            g += f"; rock over the roof {p['roof'][0]:.1f} m at its thinnest"
        lines.append(g)
        head = f"cave {p['cave']}: {p['from']} -> {p['to']}"
        if p["grade"] > GRADE_WALK or p["steep"] > 2 * GRADE_WALK:
            what = (f"{'climbs' if p['rise'] > 0 else 'falls'} {abs(p['rise']):.0f} m in {p['length']:.0f} m "
                    f"({100 * p['grade']:.0f}%)" if p["grade"] > GRADE_WALK else
                    f"has a stretch of {100 * p['steep']:.0f}% at [{p['steep_at'][0]:.0f}, {p['steep_at'][1]:.0f}]")
            warns.append(f"{head} {what}: too steep to walk (a cave floor walks up to {100 * GRADE_WALK:.0f}%); "
                         + _fix(T, spec.get(p["cave"], {}), cv, p, cv.nodes))
        if p["roof"] is not None and p["roof"][0] < (0.5 if p["kind"] == "lava" else ROOF_MIN):
            r, at = p["roof"]
            warns.append(f"{head}: only {max(r, 0):.1f} m of rock over the roof at [{at[0]:.0f}, {at[1]:.0f}]"
                         + (" (it breaks out to the sky)" if r < 0 else "")
                         + ": put it deeper (the chambers' \"depth\" or \"z\"), or route it under higher ground")
        if "does NOT pass" in wl:
            why = wl.split("does NOT pass (", 1)[1].rstrip(")")
            mine = [i for i, w in enumerate(warns) if w.startswith(head + " ") or w.startswith(head + ":")]
            if mine:
                warns[mine[0]] += f" (the walk: {why})"
            else:
                warns.append(f"{head} does not pass the walk: {why}; " + _walk_fix(T, cv, p, why))
    for cv in caves:  # a chamber under too little rock: its dome opens to the sky
        for n, nd in cv.nodes.items():
            if nd["type"] != "chamber":
                continue
            a = np.linspace(0, 2 * np.pi, 16, endpoint=False)
            ring = np.concatenate([nd["xy"][None]] + [nd["xy"] + f * nd["rw"] * np.c_[np.cos(a), np.sin(a)]
                                                      for f in (0.4, 0.7)])
            g = T.sample(ring)
            # (the dome's top over its middle, lower toward its rim: an ellipsoid of rw across, rh up)
            top = nd["z"] + nd["rh"] * np.sqrt(np.clip(1 - (np.linalg.norm(ring - nd["xy"], axis=1) / nd["rw"]) ** 2,
                                                       0, 1))
            k = int(np.argmin(g - top))
            cover = float(g[k] - top[k])
            lines.append(f"  {cv.name} chamber {n}: floor {nd['z']:+.1f} m, rock over its dome {cover:.1f} m at its "
                         f"thinnest")
            if cover < ROOF_MIN:
                warns.append(f"cave {cv.name}: chamber {n} has only {max(cover, 0):.1f} m of rock over it at "
                             f"[{ring[k, 0]:.0f}, {ring[k, 1]:.0f}]" + (" (its dome breaks out to the sky)" if cover < 0
                                                                         else "")
                             + (": move it under higher ground (\"at\", \"in\")" if cv.kind == "sea" else
                                ": put it deeper (\"depth\" or \"z\") or under higher ground")
                             + f", or make it smaller (\"size\": [{nd['rw']:.0f}, {nd['rh']:.0f}] now)")
    T._cave_early = (key, lines, warns)
    return lines, warns


def node_xyz(caves: list[Cave], ref: str, lift=1.7):
    """"cave.node" -> a point `lift` above that node's floor (an eye inside a cave)."""
    cn, n = ref.split(".", 1)
    for cv in caves:
        if cv.name == cn and n in cv.nodes:
            nd = cv.nodes[n]
            return [float(nd["xy"][0]), float(nd["xy"][1]), float(nd["z"] + lift)]
    raise ValueError(f"no cave node {ref!r}")
