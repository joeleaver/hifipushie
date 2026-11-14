"""The early check (set_terrain / check_terrain): the collision floor and steps, light, the survey, the fixes it names. Part of the caves (terrain_caves.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import terrain_caves
from .terrain_volumes import _sea
from .terrain_caves import Cave, _line_length
from .terrain_caves_build import build
from .terrain_caves_walk import check

def collision_floor(xy, z, P, F, cell=4.0):
    """Per point (xy, the walk's floor z): the highest collision-mesh surface under z + STEP_PROBE and over z - 3,
    (vertical rays against the triangles), NaN where there's none."""
    out = np.full(len(xy), np.nan)
    if not len(F):
        return out
    A, B, C = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    lo = np.minimum(np.minimum(A, B), C)[:, :2]
    hi = np.maximum(np.maximum(A, B), C)[:, :2]
    grid = {}
    for t, (l, h) in enumerate(zip(np.floor(lo / cell).astype(int), np.floor(hi / cell).astype(int))):
        for gx in range(l[0], h[0] + 1):
            for gy in range(l[1], h[1] + 1):
                grid.setdefault((gx, gy), []).append(t)
    for q, (p, zz) in enumerate(zip(xy, z)):
        if not np.isfinite(zz):
            continue
        ts = np.array(grid.get(tuple(np.floor(p / cell).astype(int)), []), np.int64)
        if not len(ts):
            continue
        a, b, c = A[ts], B[ts], C[ts]
        v0, v1 = b[:, :2] - a[:, :2], c[:, :2] - a[:, :2]
        w = p - a[:, :2]
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        ok = np.abs(den) > 1e-12
        u = np.where(ok, (w[:, 0] * v1[:, 1] - v1[:, 0] * w[:, 1]) / np.where(ok, den, 1), -1)
        v = np.where(ok, (v0[:, 0] * w[:, 1] - w[:, 0] * v0[:, 1]) / np.where(ok, den, 1), -1)
        inside = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
        if not inside.any():
            continue
        zt = (a[:, 2] + u * (b[:, 2] - a[:, 2]) + v * (c[:, 2] - a[:, 2]))[inside]
        zt = zt[(zt <= zz + terrain_caves.STEP_PROBE) & (zt >= zz - 3.0)]
        if len(zt):
            out[q] = float(zt.max())
    return out


def collision_steps(paths, out, tiles, lod) -> list[str]:
    """Each cave_paths passage walked again on the collision meshes (what an engine's character stands on): the floor
    under each point (`collision_floor`, written into the path as "collision_floor") and the largest step between
    half-metre points, beside the field's ("largest_step_m", "largest_step_collision_m"). Report lines."""
    from pathlib import Path
    from . import terrain_gltf
    out = Path(out)
    if not paths:
        return []
    Ps, Fs, n = [], [], 0
    have = {(e["i"], e["j"]): e for e in tiles if e.get("collision")}
    pts = np.array([q[:2] for pth in paths for q in pth["points"]], float)
    near = set()
    for e in have.values():
        lo, hi = np.asarray(e["min"], float)[:2], np.asarray(e["max"], float)[:2]
        if ((pts >= lo - 1) & (pts <= hi + 1)).all(1).any():
            near.add((e["i"], e["j"]))
    for ij in sorted(near):
        tr, prims = terrain_gltf.read_glb(out / have[ij]["collision"])
        o = terrain_gltf._from_gltf(tr[None])[0]
        for p in prims:
            P = terrain_gltf._from_gltf(p["POSITION"].astype(np.float64)) + o
            Ps.append(P)
            Fs.append(p["indices"].astype(np.int64) + n)
            n += len(P)
    if not Ps:
        return []
    P, F = np.vstack(Ps), np.vstack(Fs)
    lines = []
    for pth in paths:
        xy = np.array([q[:2] for q in pth["points"]], float)
        z = np.array([np.nan if q[2] is None else q[2] for q in pth["points"]], float)
        cz = collision_floor(xy, z, P, F)
        pth["collision_floor"] = [None if not np.isfinite(v) else round(float(v), 2) for v in cz]
        st = np.abs(np.diff(z))
        st = st[np.isfinite(st)]
        sc = np.abs(np.diff(cz))
        good = np.isfinite(sc)
        pth["largest_step_m"] = round(float(st.max()), 2) if len(st) else None
        pth["largest_step_collision_m"] = round(float(sc[good].max()), 2) if good.any() else None
        # risers: runs of the collision floor steeper than RISER_DEG at 0.1 m spacing (a character controller's wall,
        # unless it steps up): the tallest, and where (crown_tube's lower pile: a 0.2 m lip at 60 deg where the
        # pile meets the tube's floor, which the half-metre steps don't show)
        s0 = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
        sf = np.arange(0, s0[-1], terrain_caves.RISER_STEP)
        xf = np.c_[np.interp(sf, s0, xy[:, 0]), np.interp(sf, s0, xy[:, 1])]
        zf = np.interp(sf, s0, np.where(np.isfinite(z), z, -1e9))
        zf[zf < -1e8] = np.nan
        cf = collision_floor(xf, zf, P, F)
        d = np.diff(cf)
        steep = np.isfinite(d) & (np.abs(d) > terrain_caves.RISER_STEP * math.tan(math.radians(terrain_caves.RISER_DEG)))
        best_r, at_r = 0.0, None
        q = 0
        while q < len(d):
            if steep[q]:
                j = q
                while j + 1 < len(d) and steep[j + 1] and np.sign(d[j + 1]) == np.sign(d[q]):
                    j += 1
                h = abs(float(d[q:j + 1].sum()))
                if h > best_r:
                    best_r, at_r = h, (xf[q], cf[q], sf[q])
                q = j + 1
            else:
                q += 1
        pth["tallest_riser_collision_m"] = round(best_r, 2)
        if at_r is not None:
            pth["tallest_riser_at"] = [round(float(at_r[0][0]), 1), round(float(at_r[0][1]), 1), round(float(at_r[1]), 1)]
        if good.any():
            k = int(np.flatnonzero(good)[np.argmax(sc[good])])
            miss = int((~np.isfinite(cz) & np.isfinite(z)).sum())
            lines.append(f"{pth['cave']} {pth['from']} -> {pth['to']}: largest step {pth['largest_step_m']} m on the "
                         f"field, {pth['largest_step_collision_m']} m on the LOD {lod} collision mesh (at "
                         f"[{xy[k, 0]:.0f}, {xy[k, 1]:.0f}, {cz[k]:.1f}], {0.5 * k:.0f} m along); the tallest riser "
                         f"steeper than {terrain_caves.RISER_DEG:g} deg {pth['tallest_riser_collision_m']} m"
                         + (f" at {pth['tallest_riser_at']}" if pth.get("tallest_riser_at") else "")
                         + ": your character must step at least that high (a capsule character meets any riser "
                           "over ~0.1 m steeper than its floor angle, so it needs a step-up; Godot's "
                           "CharacterBody3D reads such a riser as a wall)"
                         + (f"; {miss} of {len(z)} points have no collision floor under them (the heightmap's, or "
                            f"open)" if miss else ""))
    return lines


def light_field(T):
    """The caves and a field to walk them in, cheaply: the height field with the volumes and caves cut out, no rock
    character (relief, beds, blocks) and no sea stacks. Seconds, where the tile export's field takes minutes."""
    from . import terrain_mesh as tm
    from . import terrain_field, terrain_relief, terrain_volumes
    karst = any((c or {}).get("kind") == "karst" for c in (T.spec.get("caves") or {}).values())
    rock = terrain_relief.rock_config(T, dict(tm.DEFAULTS)) if karst else None  # (karst floors lie on the rock's beds)
    caves = build(T, rock)
    vols, _ = terrain_volumes.volumes(T)
    field = terrain_field.Field(T, vols + [tb for cv in caves for tb in cv.tubes], None,
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
                n = max(1, int(round(min(terrain_caves.GRADE_RUN, L) / 1.0)))
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
                away &= s > terrain_caves.MOUTH + (0.0 if not a.get("shaft") else w)
            if b["type"] == "entrance":
                away &= s < L - terrain_caves.MOUTH - (0.0 if not b.get("shaft") else w)
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
    room = terrain_caves.GRADE_WALK * sv["run"]
    need = abs(sv["rise"]) / terrain_caves.GRADE_WALK + (sv["length"] - sv["run"])
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
            if nd["type"] == "entrance" and not nd.get("shaft") and d_ <= terrain_caves.MOUTH:
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
    k = max(1, int(round(terrain_caves.GRADE_RUN / ds)))
    gr = np.r_[np.abs(g[k:] - g[:-k]) / (k * ds), np.zeros(k)]
    ok = gr <= terrain_caves.GRADE_WALK
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
    walk = (f"set \"grade\": {terrain_caves.GRADE_WALK - 0.05:.2f} on the cave (the tube then switchbacks across the flow, up to "
            f"\"swing\" m either side of it, default {terrain_caves.SWING:.0f}, falling no faster than that)")
    if c.get("grade") is not None:
        walk = (f"its \"grade\" ({c['grade']}) is followed by switchbacks, but the ground along them still falls "
                f"faster: a lower \"grade\", more \"swing\" (now {c.get('swing', terrain_caves.SWING)}), or a gentler stretch "
                f"(\"from\", \"to\")")
    if (i1 - i0) * ds < 30:
        return (f"the flow \"{c['flow']}\" falls {100 * mean:.0f}% on average and has no stretch of 30 m gentler than "
                f"{100 * terrain_caves.GRADE_WALK:.0f}% (a tube follows its flow's grade): {walk}")
    return (f"{walk}; or run it on the flow's gentle stretch: \"from\": {t[i0]:.2f}, \"to\": "
            f"{t[min(i1, len(t) - 1)]:.2f} ({(i1 - i0) * ds:.0f} m under {100 * terrain_caves.GRADE_WALK:.0f}%)")


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
    from .terrain_volumes import _sea
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
             f"({100 * p['grade']:.0f}%), steepest {terrain_caves.GRADE_RUN:.0f} m {100 * p['steep']:.0f}% at "
             f"[{p['steep_at'][0]:.0f}, {p['steep_at'][1]:.0f}]")
        if p["roof"] is not None:
            g += f"; rock over the roof {p['roof'][0]:.1f} m at its thinnest"
        lines.append(g)
        head = f"cave {p['cave']}: {p['from']} -> {p['to']}"
        if p["grade"] > terrain_caves.GRADE_WALK or p["steep"] > 2 * terrain_caves.GRADE_WALK:
            what = (f"{'climbs' if p['rise'] > 0 else 'falls'} {abs(p['rise']):.0f} m in {p['length']:.0f} m "
                    f"({100 * p['grade']:.0f}%)" if p["grade"] > terrain_caves.GRADE_WALK else
                    f"has a stretch of {100 * p['steep']:.0f}% at [{p['steep_at'][0]:.0f}, {p['steep_at'][1]:.0f}]")
            warns.append(f"{head} {what}: too steep to walk (a cave floor walks up to {100 * terrain_caves.GRADE_WALK:.0f}%); "
                         + _fix(T, spec.get(p["cave"], {}), cv, p, cv.nodes))
        if p["roof"] is not None and p["roof"][0] < (0.5 if p["kind"] == "lava" else terrain_caves.ROOF_MIN):
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
            if cover < terrain_caves.ROOF_MIN:
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
