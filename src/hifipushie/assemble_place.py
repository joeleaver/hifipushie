"""Placing on things: footprints, scatter, heights, clearance, supports, the top of what is below. Part of assemble (assemble.py has the spec)."""
from __future__ import annotations

import numpy as np

from . import assemble
from .spec import SpecError
from .assemble import select
from .assemble_arrays import _arrays, _place
from .assemble_shapes import _deformed

def footprint(pf: dict) -> float:
    """A prefab's rough radius across the floor (m): how far its pieces reach from its origin, sideways."""
    r = 0.02
    for b in (pf.get("blobs") or {}).values():
        if b.get("op", "add") != "add" or not isinstance(b.get("at"), list):
            continue
        size = np.asarray(b.get("size", [0.05] * 3), float)
        reach = float(np.hypot(*b["at"][:2])) + float(max(size[:2]))
        for st in (b["array"] if isinstance(b.get("array"), list) else [b["array"]] if b.get("array") else []):
            reach += float(np.hypot(*np.asarray(st.get("offset", [0, 0, 0]), float)[:2])) * (int(st.get("count", 1)) - 1)
        r = max(r, reach)
    for j in (pf.get("joints") or {}).values():
        if isinstance(j.get("pos"), list):
            r = max(r, float(np.hypot(*j["pos"][:2])) + float(j.get("r", 0.02)))
    return r


def _scatter(s: dict, insts: dict) -> dict:
    """spec["scatter"]: {name: {"use": prefab | [prefabs] | {prefab: weight}, "on": support, "count": n,
    "area": [[x0, y0], [x1, y1]] (default: the support's extent), "spacing": m (clear gap between pieces, 0.01),
    "rot": [lo, hi] deg about Z (0..360), "scale": [lo, hi], "seed", "tags", "part"}} -> instances "<name>#i", each
    set down "on" the support where all of its footprint is over it (nothing hangs off an edge), apart from each
    other and from what already stands there. Fewer than `count` if they don't fit (the log says so)."""
    out = {}
    for name in sorted(s.get("scatter") or {}):
        sc = s["scatter"][name]
        where = f"scatter {name!r}"
        bad = set(sc) - assemble.SCATTER_KEYS
        if bad:
            raise SpecError(f"{where}: unknown keys {sorted(bad)} (allowed: {sorted(assemble.SCATTER_KEYS)})")
        use = sc.get("use")
        if isinstance(use, str):
            use = {use: 1.0}
        elif isinstance(use, list):
            use = {u: 1.0 for u in use}
        if not use or not isinstance(use, dict):
            raise SpecError(f"{where}: use is a prefab, a list of prefabs or {{prefab: weight}}")
        pfs = s.get("prefabs") or {}
        missing = [u for u in use if u not in pfs]
        if missing:
            raise SpecError(f"{where}: no prefab {missing}")
        if "on" not in sc:
            raise SpecError(f"{where}: needs \"on\" (a support: an element, tag or instance)")
        names = [sc["on"]] if isinstance(sc["on"], str) else list(sc["on"])
        rng = np.random.default_rng(int(sc.get("seed", 0)) + 7919)
        kinds, weights = list(use), np.asarray([float(w) for w in use.values()])
        weights = weights / weights.sum()
        rad = {u: footprint(pfs[u]) for u in kinds}
        lo_s, hi_s = sc.get("scale", [1.0, 1.0])
        r0, r1 = sc.get("rot", [0.0, 360.0])
        gap = float(sc.get("spacing", 0.01))
        if sc.get("area"):
            (x0, y0), (x1, y1) = np.sort(np.asarray(sc["area"], float)[:, :2], axis=0)
        else:
            els = {**s.get("bones", {}), **s.get("blobs", {})}
            members = [m for n in names for m in ([n] if n in els else select(s, [n])) if m in els]
            if not members:
                raise SpecError(f"{where}: \"on\" {names} names nothing")
            box = _support_box(s, members)
            (x0, y0), (x1, y1) = box[0][:2], box[1][:2]
        # what already stands on this support
        taken = []
        for d in insts.values():
            if d.get("on") == sc["on"] and isinstance(d.get("at"), list):
                taken.append((float(d["at"][0]), float(d["at"][1]), rad.get(d.get("use"), footprint(pfs.get(d.get("use"), {})))))
        clear = _Clearance(s, names, (x0, y0), (x1, y1))
        n, tries = int(sc.get("count", 1)), 0
        made = 0
        while made < n and tries < 60 * n:
            tries += 1
            u = kinds[int(rng.choice(len(kinds), p=weights))]
            k = float(rng.uniform(lo_s, hi_s))
            r = rad[u] * k
            x, y = float(rng.uniform(x0 + r, x1 - r)) if x1 - x0 > 2 * r else (x0 + x1) / 2, \
                float(rng.uniform(y0 + r, y1 - r)) if y1 - y0 > 2 * r else (y0 + y1) / 2
            if any(np.hypot(x - tx, y - ty) < r + tr + gap for tx, ty, tr in taken):
                continue
            try:  # over the support at its centre and all round its footprint, at one height (not across a step)
                zs = [top_of(s, names, x + dx, y + dy, where, bent=False) for dx, dy in
                      [(0, 0)] + [(0.8 * r * np.cos(a), 0.8 * r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 6, endpoint=False)]]
            except SpecError:
                continue
            if max(zs) - min(zs) > 0.02:
                continue
            if not clear.free(x, y, zs[0], r, height(pfs[u]) * k):  # a plate rack, a lamp, the wall behind
                continue
            taken.append((x, y, r))
            d = {"use": u, "at": [round(x, 4), round(y, 4)], "rot": [0, 0, round(float(rng.uniform(r0, r1)), 2)],
                 "on": sc["on"], "tags": [name, *sc.get("tags", [])]}
            if k != 1.0:
                d["scale"] = round(k, 4)
            if sc.get("part"):
                d["part"] = sc["part"]
            out[f"{name}#{made}"] = d
            made += 1
        if made < n:
            s.setdefault("_notes", []).append(f"{where}: {made} of {n} fitted on {names}")
    return out


def height(pf: dict) -> float:
    """A prefab's rough height above its origin (m)."""
    h = 0.02
    for b in (pf.get("blobs") or {}).values():
        if b.get("op", "add") == "add" and isinstance(b.get("at"), list):
            h = max(h, float(b["at"][2]) + float(np.asarray(b.get("size", [0.05] * 3), float)[2]))
    for j in (pf.get("joints") or {}).values():
        if isinstance(j.get("pos"), list):
            h = max(h, float(j["pos"][2]) + float(j.get("r", 0.02)))
    return h


class _Clearance:
    """Is the room above a spot on a support free (nothing else there: the rest of a dresser, a wall, a
    lamp)? The elements around the support's area, compiled once per scatter entry."""

    def __init__(self, s: dict, names: list, lo, hi, pad: float = 0.6):
        from .spec import compile_prims
        els = {**s.get("bones", {}), **s.get("blobs", {})}
        support = {m for n in names for m in ([n] if n in els else select(s, [n])) if m in els}
        joints = s.get("joints", {})

        def xy(el):
            if isinstance(el.get("at"), list):
                return [el["at"][:2]]
            if "a" in el:
                return [joints[j]["pos"][:2] for j in (el["a"], el["b"]) if isinstance(joints.get(j, {}).get("pos"), list)]
            return []
        near = {k: el for k, el in els.items() if k not in support and el.get("op", "add") == "add"
                and any(lo[0] - pad - 3 <= p[0] <= hi[0] + pad + 3 and lo[1] - pad - 3 <= p[1] <= hi[1] + pad + 3
                        for p in xy(el))}
        mini = {"joints": joints, "parts": s.get("parts") or {}, "symmetry": False, "blend": s.get("blend", 0.03),
                "bones": {k: {kk: v for kk, v in el.items() if kk != "targets"} for k, el in near.items() if "a" in el},
                "blobs": {k: {kk: v for kk, v in el.items() if kk != "targets"} for k, el in near.items() if "a" not in el}}
        self.prims = [p for p in compile_prims(mini) if p.op == "add"] if near else []

    def free(self, x: float, y: float, z: float, r: float, h: float) -> bool:
        if not self.prims:
            return True
        from .sdf import field_at
        ring = [(0.0, 0.0)] + [(0.85 * r * np.cos(a), 0.85 * r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
        pts = np.array([[x + dx, y + dy, z + dz] for dx, dy in ring for dz in np.linspace(0.015, max(h, 0.03), 4)])
        return bool(field_at(self.prims, pts).min() > 0.004)


def _support_box(s: dict, members: list) -> tuple:
    from .spec import compile_prims
    mini = {"joints": s.get("joints", {}), "bones": {m: s["bones"][m] for m in members if m in s.get("bones", {})},
            "blobs": {m: {k: v for k, v in s["blobs"][m].items() if k != "targets"} for m in members if m in s.get("blobs", {})},
            "parts": s.get("parts") or {}, "symmetry": False, "blend": s.get("blend", 0.03)}
    ps = [p for p in compile_prims(mini) if p.op == "add"]
    return np.min([p.lo for p in ps], 0), np.max([p.hi for p in ps], 0)


def _place_on(s: dict, todo: dict, insts: dict | None = None) -> dict:
    """Place instances given "on": set down on the top of the named elements (or tags, instances) at their x, y,
    in dependency order (a cup on a table that is itself an instance), after everything else and arrays.
    Returns {instance: its origin in the world (after any style deformation)}.
    Under a style deformation a prop on an instance rides with it as one rigid piece (the plates carried with the
    dresser), and a prop on the building (a shelf, the counter, the ground) lands where the bend puts it."""
    placed = {}
    insts = insts or {}
    bent = bool(((s.get("style") or {}).get("shape") or {}).get("deform"))
    while todo:
        ready = [i for i, d in todo.items() if not any(
            n in todo or n.split("/")[0] in todo for n in ([d["on"]] if isinstance(d["on"], str) else d["on"]))]
        if not ready:
            raise SpecError(f"instances {sorted(todo)}: \"on\" goes round in a circle")
        for inst in ready:
            d = dict(todo.pop(inst))
            at = [float(v) for v in d.get("at", [0, 0, 0])]
            lift = float(d.get("lift", 0.0))
            who = f"instance {inst!r}"
            names = [d["on"]] if isinstance(d["on"], str) else list(d["on"])
            els = {**s.get("bones", {}), **s.get("blobs", {})}  # props placed this pass (a bowl for its apples) too
            members = [m for n in names for m in ([n] if n in els else select(s, [n])) if m in els]
            carriers = {els[m].get("instance") for m in members}
            if bent and len(carriers) == 1 and None not in carriers:
                sup = carriers.pop()  # carried by an instance: its displacement, rigidly
                if sup in placed:
                    src = insts.get(sup, {}).get("at", [0, 0, 0])
                    carry = np.asarray(placed[sup], float) - _pad3(src)
                else:
                    src = _pad3(insts.get(sup, {}).get("at", [0, 0, 0]))
                    carry = _deformed(s, src) - src
                wx, wy = at[0] + carry[0], at[1] + carry[1]
                world = [wx, wy, top_of(s, names, wx, wy, who) + lift]
            elif bent:
                zu = _solve_on(s, names, at[0], at[1], lift, who)
                world = _deformed(s, [at[0], at[1], zu]).tolist()
            else:
                world = [at[0], at[1], top_of(s, names, at[0], at[1], who) + lift]
            d["at"] = [float(v) for v in world]
            d["_world"] = True  # already where it stands: no further deformation
            placed[inst] = d["at"]
            _place(s, inst, d)
        _arrays(s)
    return placed


def _pad3(at) -> np.ndarray:
    a = [float(v) for v in at]
    return np.asarray(a + [0.0] * (3 - len(a)))


def _solve_on(s: dict, names, x: float, y: float, lift: float, who: str) -> float:
    """The (undeformed) height of a prop set down on `names` at x, y. Under a style deformation the prop lands
    where its origin is bent to, and the support is bent too (or, an instance, carried rigidly): look where it
    lands and solve for the height that bends onto the top found, from a few starting heights (the lookup must
    hit a narrow shelf, whose bent position depends on its height)."""
    if not ((s.get("style") or {}).get("shape") or {}).get("deform"):
        return top_of(s, names, x, y, who) + lift
    err = None
    for z0 in (None, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5):
        try:
            zu = (top_of(s, names, x, y, who, bent=False) + lift) if z0 is None else z0
            for _ in range(4):
                pd = _deformed(s, [x, y, zu])
                zu = top_of(s, names, float(pd[0]), float(pd[1]), who) + lift - (float(pd[2]) - zu)
            return zu
        except SpecError as e:
            err = e
    raise err


def top_of(s: dict, names, x: float, y: float, who: str = "", bent: bool = True) -> float:
    """The top surface of the named elements (tags, instances) at (x, y), cuts into them included: the highest
    point where a vertical line there leaves them. s: a spec with instances placed and arrays expanded."""
    from .sdf import field_at
    from .spec import compile_prims
    names = [names] if isinstance(names, str) else list(names)
    els = {**s.get("bones", {}), **s.get("blobs", {})}
    # an element's own name means that element (an array's copy 0 is named like the array, whose name also tags
    # every copy: "shelf" is the first shelf, not all of them); anything else is a tag or an instance
    members = [m for n in names for m in ([n] if n in els else select(s, [n])) if m in els]
    if not members:
        raise SpecError(f"{who}: \"on\" {names} names no element, tag or instance")
    mset = set(members)
    mini = {"joints": s.get("joints", {}), "bones": {}, "blobs": {}, "parts": s.get("parts") or {},
            "symmetry": False, "blend": s.get("blend", 0.03)}
    dfm = ((s.get("style") or {}).get("shape") or {}).get("deform")
    if dfm and bent:  # the support as it stands, bent (its elements' own style changes are already applied)
        mini["style"] = {"shape": {"deform": dfm}}
    for kind in ("bones", "blobs"):
        for n, el in (s.get(kind) or {}).items():
            cuts_it = el.get("targets") and mset & set(select(s, el["targets"]))
            if n in mset or cuts_it:
                mini[kind][n] = {k: v for k, v in el.items() if k not in ("array",)}
                if cuts_it:  # only what it cuts among the support (the rest isn't in this small spec)
                    mini[kind][n]["targets"] = sorted(cuts_it)
                at = el.get("at")
                if isinstance(at, dict) and at.get("bone") in s.get("bones", {}):
                    mini["bones"].setdefault(at["bone"], s["bones"][at["bone"]])
    prims = [p for p in compile_prims(mini) if p.name in mset]
    lo = np.min([p.lo for p in prims], 0)
    hi = np.max([p.hi for p in prims], 0)
    zs = np.arange(hi[2] + 0.02, lo[2] - 0.02, -0.002)
    f = field_at(prims, np.stack([np.full_like(zs, x), np.full_like(zs, y), zs], 1))
    inside = np.flatnonzero(f < 0)
    if not len(inside):
        raise SpecError(f"{who}: ({x:.3f}, {y:.3f}) isn't over {names} (they span x {lo[0]:.2f}..{hi[0]:.2f}, "
                        f"y {lo[1]:.2f}..{hi[1]:.2f})")
    k = inside[0]  # first sample inside, coming down: refine between it and the one above
    if k == 0:
        return float(zs[0])
    return float(zs[k - 1] + (zs[k] - zs[k - 1]) * f[k - 1] / (f[k - 1] - f[k]))
