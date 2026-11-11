"""The hair spec: validate, merge a patch, the groom from a spec, hierarchy, folds, root ends, fins. Part of hair
(hair.py has the overview)."""
from __future__ import annotations

import copy
import hashlib
import json

import numpy as np

from . import store
from . import hair, hair_head
from .hair import HairError, _ss, _unit, under
from .hair_groom import envelope, groom_params, hairline, head_ref, needs_body
from .hair_grow import grow
from .hair_head import Scalp

# ------------------------------------------------------------------------------------------------ spec I/O
def hair_of(spec: dict) -> dict:
    return spec.get("hair") or {}


def validate(spec: dict) -> None:
    h = hair_of(spec)
    if not h:
        return
    keys = {"groom", "locks", "look", "cap", "stage", "part", "filler", "removed", "export", "style", "strands", "head"}
    bad = set(h) - keys
    if bad:
        raise HairError(f"hair: unknown keys {sorted(bad)} (have {', '.join(sorted(keys))})")
    if h.get("stage", "locks") not in ("mass", "locks"):
        raise HairError('hair stage is "mass" (the groom\'s volume as one shell) or "locks"')
    bad = set(h.get("look") or {}) - set(hair.LOOK)
    if bad:
        raise HairError(f"hair look: unknown keys {sorted(bad)} (have {', '.join(sorted(hair.LOOK))})")
    groom_params(spec)
    if h.get("style", "locks") not in hair.STYLES:
        raise HairError(f'hair style is one of {", ".join(hair.STYLES)}')
    from . import hair_route
    hair_route.check_export(h)
    if h.get("strands") is not None:
        from . import hair_cards
        try:
            hair_cards.strands_of(spec)
        except ValueError as e:
            raise HairError(str(e)) from None
    for n, lk in (h.get("locks") or {}).items():
        bad = set(lk) - hair.LOCK_KEYS
        if bad:
            raise HairError(f"hair lock {n!r}: unknown keys {sorted(bad)} (have {', '.join(sorted(hair.LOCK_KEYS))})")
        pts = lk.get("pts") or []
        if len(pts) < 2 or any(len(p) != 3 for p in pts):
            raise HairError(f"hair lock {n!r}: pts is a list of at least 2 [az, el, h] points")
        for k in ("width", "thickness"):
            if not isinstance(lk.get(k), (int, float)) or lk[k] <= 0:
                raise HairError(f"hair lock {n!r}: {k} (m) must be > 0")


def merge_patch(a, b):
    """b merged into a key by key (objects merge, null deletes, anything else replaces). A list of named objects
    (the drawn clumps) patched with an object {name: patch | null} merges by name: one clump's numbers change, null
    drops it, a new name is appended (`"*"` / `"sweep*"` patterns patch every match)."""
    if isinstance(a, list) and isinstance(b, dict) and all(isinstance(x, dict) and x.get("name") for x in a):
        from fnmatch import fnmatch
        out = [copy.deepcopy(x) for x in a]
        for k, v in b.items():
            hit = [i for i, x in enumerate(out) if fnmatch(x["name"], k)]
            if v is None:
                out = [x for i, x in enumerate(out) if i not in hit]
            elif hit:
                for i in hit:
                    out[i] = merge_patch(out[i], v)
            elif not any(ch in k for ch in "*?["):
                out.append({"name": k, **copy.deepcopy(v)})
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            if v is None:
                out.pop(k, None)
            else:
                out[k] = merge_patch(a.get(k), v)
        return out
    return copy.deepcopy(b)


def groom(name: str, replace: bool = False, note: str = "", patch: dict | None = None,
          stage: str | None = None) -> dict:
    """Grow the first pass of locks from spec["hair"]["groom"] and save them. Locks a person or an edit changed
    (their names not starting with the tier letters b/f/e + digits) and hand-shaped locks (`"hand": true`: every lock
    edited or added in Blender comes back with it from scene.pull) are kept unless replace; locks deleted in Blender
    (`hair.removed`) aren't grown again."""
    spec = store.load(name)
    from . import hair_route
    h = spec.setdefault("hair", {})
    if patch:
        h["groom"] = merge_patch(h.get("groom") or {}, patch)
    if stage is not None:
        h["stage"] = stage
    hair_route.default_style(spec)
    validate(spec)
    sc = hair_head.scalp(name, spec)
    g = groom_params(spec)
    col = None
    if g.get("loose") or needs_body(g):
        from . import hair_loose
        col = hair_loose.collider(name, spec, sc)
    new = grow(sc, g, col)
    old = h.get("locks") or {}
    if replace:
        h.pop("removed", None)
    else:
        new = {n: lk for n, lk in new.items() if n not in set(h.get("removed") or [])}
    keep = {} if replace else {n: lk for n, lk in old.items()
                               if lk.get("hand") or (not (n[:1] in "bcfesghk" and n[1:].rstrip("abcdefgh").isdigit())
                                                     and lk.get("tier") not in ("drawn", "tie", "loose"))}
    h["locks"] = {**new, **keep}
    if h.get("groom") is not None and not h["groom"].get("fit"):
        h["groom"]["fit"] = head_ref(sc)  # the head these locks were grown on: the groom carries to other heads (carry)
    h["head"] = hair_route.head_key(sc)  # (look / export warn when the head changes under the groom)
    v = store.save(name, spec, note or f"hair: grew {len(new)} locks from the groom")
    tiers: dict = {}
    for n, lk in new.items():
        if n not in keep:  # (a kept lock of the same name wins)
            tiers[lk["tier"]] = tiers.get(lk["tier"], 0) + 1
    return {"version": v, "locks": len(h["locks"]), "grown": tiers, "kept": sorted(keep),
            "not_regrown": sorted(set(h.get("removed") or []))}


def hierarchy(spec: dict, sc: Scalp) -> dict:
    """The groom's size hierarchy, the artists' 6-3-1 (big shapes ~60% of the area, medium ~30%, small ~10%): each
    lock's area (width x length x 0.65, lens and taper) by its width against the widest locks (90th percentile):
    big >= 0.7, medium 0.4-0.7, small < 0.4. Under-layer locks ("_under") don't count (they're hidden). Also how far
    widths spread (coefficient of variation: ~0 = every lock the same, the "uniform locks" look)."""
    locks = {n: lk for n, lk in (hair_of(spec).get("locks") or {}).items() if not n.endswith("_under")}
    if not locks:
        return {}
    W, A = [], []
    for lk in locks.values():
        P = lock_world(sc, lk, lk["pts"])
        L = float(np.linalg.norm(np.diff(_catmull(P, 24), axis=0), axis=1).sum())
        W.append(float(lk["width"]))
        A.append(float(lk["width"]) * L * 0.65)
    W, A = np.array(W), np.array(A)
    ref = np.percentile(W, 90)
    r = W / max(ref, 1e-9)
    tot = max(A.sum(), 1e-12)
    big, med = A[r >= 0.7].sum() / tot, A[(r >= 0.4) & (r < 0.7)].sum() / tot
    return {"big": round(float(big), 2), "medium": round(float(med), 2), "small": round(max(0.0, float(1 - big - med)), 2),
            "width_cv": round(float(W.std() / max(W.mean(), 1e-9)), 2), "locks": len(W),
            "widest_mm": round(float(ref * 1000), 1)}


def lock_hash(lk: dict, sc: Scalp) -> str:
    return hashlib.sha1(json.dumps([lk, sc.C.tolist(), float(sc.R.sum())], sort_keys=True,
                                   default=float).encode()).hexdigest()[:12]


def lock_world(sc: Scalp, lk: dict, pts):
    """A lock's points (its own space: [az, el, h] on the head, or "space": "xyz" metres from the head centre) in
    world metres."""
    pts = np.asarray(pts, float).reshape(-1, 3)
    if lk.get("space") == "xyz":
        return sc.C + pts
    return sc.point(pts[:, 0], pts[:, 1], pts[:, 2])


def lock_address(sc: Scalp, lk: dict, P) -> list:
    """World points as the lock stores them."""
    P = np.asarray(P, float).reshape(-1, 3)
    if lk.get("space") == "xyz":
        return [[round(float(v), 4) for v in q] for q in P - sc.C]
    a, e, hh = sc.coords(P)
    return [[round(float(a[i]), 2), round(float(e[i]), 2), round(float(hh[i]), 4)] for i in range(len(P))]


def resolve(spec: dict, sc: Scalp) -> list:
    """The locks as Blender wants them: world control points, handles, radius, tilt and modifier inputs."""
    out = []
    for n, lk in sorted((hair_of(spec).get("locks") or {}).items()):
        W = lock_world(sc, lk, lk["pts"])
        H = None
        if lk.get("handles"):
            H = []
            for hd in lk["handles"]:
                if hd:
                    a, b = lock_world(sc, lk, [hd[:3], hd[3:]])
                    H.append([float(v) for v in list(a) + list(b)])
                else:
                    H.append(None)
        inputs = {hair.MOD[k]: float(lk.get(k, hair.LOCK_DEFAULTS.get(k, 0.0))) for k in hair.MOD}
        inputs["Seed"] = (int(hashlib.md5(n.encode()).hexdigest()[:6], 16) % 1000) / 1000.0
        inputs["Centre"] = [float(v) for v in sc.C]
        out.append({"name": n, "pts": W.tolist(), "handles": H, "radius": lk.get("radius"), "tilt": lk.get("tilt"),
                    "inputs": inputs, "hash": lock_hash(lk, sc), "free": float(lk.get("free", 0.0)),
                    "strands": lk.get("strands"), "tier": lk.get("tier"), "swoop": float(lk.get("swoop", 0.0)),
                    "hairs": int(lk.get("hairs") or 0),
                    "core": lock_world(sc, lk, lk["core"]).tolist() if lk.get("core") else None})
    return out


def _catmull(P, n):
    """A Catmull-Rom curve through P (close to Blender's auto handles), n points evenly in parameter."""
    P = np.asarray(P, float)
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    t = np.linspace(0, len(P) - 1, n)
    k = np.minimum(np.floor(t).astype(int), len(P) - 2)
    u = (t - k)[:, None]
    p0, p1, p2, p3 = Q[k], Q[k + 1], Q[k + 2], Q[k + 3]
    return 0.5 * (2 * p1 + (p2 - p0) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u ** 2 + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3)


def lock_width(inp: dict, u):
    """The lock's width factor along it (0 root .. 1 tip), as blender_hair's node group makes it."""
    root, belly, taper = inp.get("Root", 0.6), max(inp.get("Belly", 0.3), 0.02), inp.get("Taper", 1.0)
    rise = root + (1 - root) * _ss(u / belly)
    fall = _ss((u - belly) / max(1 - belly, 1e-6))
    return rise * (1 - taper * fall ** 0.8)


def folds(sc: Scalp, locks: list, n: int = 80) -> dict:
    """Locks that fold over themselves: where the spine turns within the lock's flat side tighter than its half width
    (in-plane curvature x half width >= 1), the inner edge runs backwards and the lens crumples into overlapping
    flakes. {lock: [ratio, u]} for the worst point of every lock over FOLD_LIMIT (u = 0 root .. 1 tip)."""
    out = {}
    for lk in locks:
        S = _catmull(lk["pts"], n)
        d = np.gradient(S, axis=0)
        ds = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
        tg = d / ds[:, None]
        nr = _unit(S - sc.C)
        nr = _unit(nr - (nr * tg).sum(1, keepdims=True) * tg)
        u = np.linspace(0, 1, n)
        if lk.get("tilt"):
            ti = np.interp(u, np.linspace(0, 1, len(lk["tilt"])), lk["tilt"])[:, None]
            nr = nr * np.cos(ti) + np.cross(tg, nr) * np.sin(ti)
        b = _unit(np.cross(nr, tg))
        k = (np.gradient(tg, axis=0) / ds[:, None] * b).sum(1)  # in-plane curvature (1/m)
        inp = lk["inputs"]
        half = 0.5 * inp["Width"] * lock_width(inp, u)
        r = np.abs(k) * half
        r[[0, -1]] = 0.0  # the ends' one-sided differences
        i = int(np.argmax(r))
        if r[i] >= hair.FOLD_LIMIT:
            out[lk["name"]] = [round(float(r[i]), 2), round(float(u[i]), 2)]
    return out


def root_ends(sc: Scalp, g: dict, locks: list, n: int = 80) -> dict:
    """How blunt each lock's root end is where it comes out of the layer: the lens's width (mm) x the steepness of its
    rise (rise over run, at most 1) at the first point
    along it whose back stands ROOT_RISE above the underlayer there. A wide end standing up shows its cut: a crescent
    fin from the side where rows start at a parting, a row of scales along a hairline. {lock: mm} over ROOT_END_MM,
    widest first (lower `root` and raise `climb` on those clumps: a narrow root grows out of the layer)."""
    line = hairline(sc, g)
    out = {}
    for lk in locks:
        if lk["name"].endswith("_under"):
            continue
        S = _catmull(lk["pts"], n)
        u = np.linspace(0, 1, n)
        a, e, h = sc.coords(S)
        H, d_in = envelope(sc, g, line, a, e)
        U = under(g, H, a, e, d_in)
        inp = lk["inputs"]
        f = lock_width(inp, u)
        top = h + 0.5 * inp["Thickness"] * f
        up = np.nonzero((top - U > hair.ROOT_RISE) & (u < 0.5))[0]
        if not len(up):
            continue
        k = up[0]
        below = np.nonzero(top[:k] - U[:k] <= 0)[0]  # where its back was last under the layer
        j = below[-1] if len(below) else 0
        run = float(np.linalg.norm(np.diff(S[j:k + 1], axis=0), axis=1).sum()) if k > j else 0.0
        steep = min(1.0, (top[k] - U[k]) / max(run, 1e-6))  # 1: a wall; a long low ramp shows no cut
        w = 1000 * inp["Width"] * f[k] * steep
        if w > hair.ROOT_END_MM:
            out[lk["name"]] = round(float(w), 1)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def fins(sc: Scalp, g: dict, locks: list, n: int = 60) -> dict:
    """Lock edges standing up off the hair under them: for each lock, the highest of its two lens edges (with the
    tilt and cup) over the underlayer there, less the lock's own thickness (a lock lying on another one stands about
    a thickness up), over u 0.1-0.95. {lock: [mm over, u]} above FIN_MM, worst first. A wide flat lock whose path
    crosses the volume's curve, or stacked on rows that lie high, stands on one edge (the top rows' fins in the side
    view): narrow it, lower its `lie`, or move it onto the curve."""
    line = hairline(sc, g)
    out = {}
    for lk in locks:
        S = _catmull(lk["pts"], n)
        u = np.linspace(0, 1, n)
        tg = _unit(np.gradient(S, axis=0))
        nr = _unit(S - sc.C)
        nr = _unit(nr - (nr * tg).sum(1, keepdims=True) * tg)
        if lk.get("tilt"):
            ti = np.interp(u, np.linspace(0, 1, len(lk["tilt"])), lk["tilt"])[:, None]
            nr = nr * np.cos(ti) + np.cross(tg, nr) * np.sin(ti)
        b = _unit(np.cross(nr, tg))
        inp = lk["inputs"]
        f = lock_width(inp, u)
        best = np.full(n, -np.inf)
        for c in (-1.0, 1.0):
            E = S + (f * c * 0.5 * inp["Width"])[:, None] * b - (f * inp["Cup"])[:, None] * nr
            a, e, h = sc.coords(E)
            H, d = envelope(sc, g, line, a, e)
            best = np.maximum(best, h - under(g, H, a, e, d))
        x = (best - inp["Thickness"]) * 1000
        x[(u < 0.1) | (u > 0.95)] = -np.inf
        k = int(np.argmax(x))
        if x[k] > hair.FIN_MM:
            out[lk["name"]] = [round(float(x[k]), 1), round(float(u[k]), 2)]
    return dict(sorted(out.items(), key=lambda kv: -kv[1][0]))
