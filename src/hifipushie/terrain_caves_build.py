"""Building caves: `build`, one cave's passage, its flow profile, switchbacks. Part of the caves (terrain_caves.py has the overview)."""
from __future__ import annotations

import math
import zlib

import numpy as np

from . import terrain_caves
from .terrain_volumes import Mound, Tube, _daylight, _sea
from .terrain_caves import Cave, _line_length

def build(T, rock=None) -> list[Cave]:
    spec = T.spec.get("caves") or {}
    return [_cave(T, name, c, rock) for name, c in spec.items()]


def _xy(T, ref):
    xy, h, d = T.address(ref)
    return np.asarray(xy, float), float(h), (None if d is None else np.asarray(d, float)[:2])


def _cave(T, name, c, rock):
    kind = c.get("kind", "sea")
    if kind not in terrain_caves.KINDS:
        raise ValueError(f"cave {name!r}: kind {kind!r}: use one of {sorted(terrain_caves.KINDS)}")
    K = {**terrain_caves.KINDS[kind], **{k: c[k] for k in ("width", "height") if k in c}}
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
            via, zz, land = _switchbacks(T, fl_, f0, f1, float(c["grade"]), float(c.get("swing", terrain_caves.SWING)))
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
                    u = np.clip(d_ / terrain_caves.MOUTH_EASE, 0, 1)
                    ease *= u * u * (3 - 2 * u)
            # (and the beds' wander spread over BED_SPREAD m: by a cliff the beds' offset changes metres in a few
            # metres of plan, and a floor that took it at once climbed a staircase of 0.6 m steps (the slot's floor
            # is flat between its nodes, 3 m apart). The ends stay on their own beds)
            from scipy.ndimage import gaussian_filter1d
            D = (a["z"] + oa - off) * (1 - g_) + (b["z"] + ob - off) * g_ - lin
            if len(s) > 2:
                step = float(np.median(np.diff(s)))
                Ds = gaussian_filter1d(D, terrain_caves.BED_SPREAD / max(step, 1e-6), mode="nearest")
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
    wd = terrain_caves.KINDS["lava"]["width"] + 1.5

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
