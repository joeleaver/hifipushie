"""Stands: a forest as a game builds one. A few grown trees per species and role (interior trees shaded on every side,
edge trees open to one), stood many times over a plot at a spacing, each at the level of detail its distance from
the eye allows (near: every twig; mid: a budget of a few thousand triangles with bough cards; far: a few hundred
triangles, the stand-in for an impostor), and a floor of scattered things (fallen branches, stumps, ferns) over
litter and moss. The spec:

    {"species": "norway_spruce" | [{"species", "share", "patch"?}, ...], "age": 55, "ages": 8, "spacing": 3.0,
     "size": [60, 60], "variants": 3, "edge": ["s"], "rows": false, "jitter": 0.3, "seed": 1,
     "scale": [0.9, 1.1], "clearings": [{"at": [x, y], "r": m}], "paths": [{"points": [[x, y]...], "width": m}],
     "floor": {"brash": per m2, "stumps": per m2, "ferns": per m2, "fern": preset, "moss": 0..1, "litter": 0..1},
     "lod": {"near": m, "mid": m, "budgets": [None, 10000, 1500]}, "haze": {"distance": m, "color"}}

`grow` makes the variants and the layout; `look` renders views (LODs by distance from the nearest eye); `report`
says what stands where and what a frame would draw; `layout_json` is what an engine's scatter needs."""
from __future__ import annotations

import copy
import math

import numpy as np

from . import vegetation, veg_leaf
from .vegetation import _child, _u

STAND = {"species": "norway_spruce", "age": 55, "ages": 8, "spacing": 3.0, "size": [60.0, 60.0], "variants": 3,
         "edge": [], "rows": False, "jitter": 0.3, "seed": 1, "scale": [0.9, 1.1], "clearings": [], "paths": [],
         "floor": {"brash": 0.12, "stumps": 0.004, "ferns": 0.0, "fern": "fern", "moss": 0.35, "litter": 0.6},
         "lod": {"near": 14.0, "mid": 45.0, "budgets": [None, 10000, 1500]},
         "haze": {"distance": 85.0, "color": [0.7, 0.75, 0.74], "strength": 0.8},
         "light": {"ambient": 1.1, "bounce": 0.5, "sun_energy": 4.5}}
SIDES = {"n": (0, 1), "s": (0, -1), "e": (1, 0), "w": (-1, 0)}
_CACHE: dict = {}


def resolve(stand: dict) -> dict:
    bad = set(stand) - set(STAND) - {"name", "about"}
    if bad:
        raise ValueError(f"stand: unknown keys {sorted(bad)}; it takes {sorted(STAND)}")
    s = vegetation._merge(STAND, stand)
    sp = s["species"]
    s["species"] = [{"species": sp, "share": 1.0}] if isinstance(sp, str) else [dict(x) for x in sp]
    for x in s["species"]:
        if x.get("species") not in vegetation.species():
            raise ValueError(f"stand species {x.get('species')!r}: presets are {vegetation.species()}")
        x.setdefault("share", 1.0)
    for e in s["edge"]:
        if e not in SIDES:
            raise ValueError(f"stand edge {e!r}: any of n, s, e, w (the sides open to the light)")
    if s["spacing"] < 0.8:
        raise ValueError("stand spacing under 0.8 m")
    n = (s["size"][0] / s["spacing"]) * (s["size"][1] / s["spacing"])
    if n > 4000:
        raise ValueError(f"about {int(n)} trees: over 4000 (a bigger forest is a terrain's scatter of this stand's kit, not one look)")
    return s


def layout(stand: dict) -> dict:
    """Where the trees stand: a jittered grid (rows: straight planting rows along y; else every other row offset: no
    aisles), thinned by clearings and paths. Returns xy (n, 2) centred on the plot, edge (n: the open side's index into
    out, or -1), out (unit vectors per open side)."""
    s = resolve(stand)
    sp, (w, d) = float(s["spacing"]), s["size"]
    rng = np.random.default_rng(int(s["seed"]) * 7919 + 11)
    nx, ny = max(1, int(round(w / sp))), max(1, int(round(d / (sp if s["rows"] else sp * 0.87))))
    xs = (np.arange(nx) - (nx - 1) / 2) * sp
    ys = (np.arange(ny) - (ny - 1) / 2) * (d / ny)
    X, Y = np.meshgrid(xs, ys)
    if not s["rows"]:
        X = X + (np.arange(ny)[:, None] % 2) * 0.5 * sp
    xy = np.c_[X.ravel(), Y.ravel()]
    j = float(s["jitter"]) * sp
    xy = xy + rng.uniform(-j, j, xy.shape) * ([0.35, 1.0] if s["rows"] else [1.0, 1.0])
    keep = np.ones(len(xy), bool)
    for c in s["clearings"]:
        keep &= np.linalg.norm(xy - np.asarray(c["at"], float), axis=1) > float(c["r"])
    for p in s["paths"]:
        pts = np.asarray(p["points"], float)
        for a, b in zip(pts[:-1], pts[1:]):
            t = np.clip(((xy - a) @ (b - a)) / max(float((b - a) @ (b - a)), 1e-9), 0, 1)
            keep &= np.linalg.norm(xy - (a + t[:, None] * (b - a)), axis=1) > 0.5 * float(p.get("width", 2.5))
    xy = xy[keep]
    edge = -np.ones(len(xy), int)
    out = np.array([SIDES[e] for e in s["edge"]], float).reshape(-1, 2)
    half = np.array([w, d]) / 2
    for k, o in enumerate(out):  # the outermost rank on an open side
        dist = (half * np.abs(o)).sum() - xy @ o
        edge[(dist < 1.1 * sp) & (edge < 0)] = k
    return {"xy": xy, "edge": edge, "out": out, "rng": rng}


def _variant_specs(s: dict) -> list[dict]:
    out = []
    nv = int(s["variants"])
    for si, x in enumerate(s["species"]):
        for role in (["interior", "edge"] if s["edge"] else ["interior"]):
            for k in range(nv if role == "interior" else max(1, nv - 1)):
                u = (k + 0.5) / nv - 0.5
                env = {"setting": "forest", "spacing": float(s["spacing"])} if role == "interior" else \
                    {"setting": "edge", "spacing": float(s["spacing"]), "open_side": [-1, 0]}
                spec = vegetation._merge({"species": x["species"], "age": float(s["age"]) + 2 * u * float(s["ages"]),
                                          "seed": int(s["seed"]) * 100 + 17 * si + k + (50 if role == "edge" else 0), "environment": env},
                                         x.get("patch") or {})
                out.append({"name": f"{x['species']}_{role}{k + 1}", "species": si, "role": role, "spec": spec})
    return out


def grow(stand: dict, log=None) -> dict:
    """The stand: its variants grown ({"name", "role", "spec", "tree"}), and every tree's place (xy, yaw deg, variant,
    scale). The same spec gives the same stand."""
    s = resolve(stand)
    key = vegetation.json.dumps(s, sort_keys=True, default=float)
    if key in _CACHE:
        return _CACHE[key]
    vs = _variant_specs(s)
    for v in vs:
        v["tree"] = vegetation.grow(v["spec"])
        if log:
            log(f"{v['name']}: {v['tree']['height']:.1f} m, {v['tree']['stats']['nodes']} nodes")
    L = layout(s)
    rng = L["rng"]
    n = len(L["xy"])
    share = np.array([x["share"] for x in s["species"]], float)
    spi = rng.choice(len(share), n, p=share / share.sum())
    var = np.zeros(n, int)
    yaw = rng.uniform(0, 360, n)
    for i in range(n):
        role = "edge" if L["edge"][i] >= 0 else "interior"
        cand = [k for k, v in enumerate(vs) if v["species"] == spi[i] and v["role"] == role]
        var[i] = cand[int(rng.integers(len(cand)))]
        if role == "edge":  # the variant's open side (its own -x) turned to face out of the stand
            o = L["out"][L["edge"][i]]
            yaw[i] = math.degrees(math.atan2(o[1], o[0])) - 180.0 + float(rng.uniform(-25, 25))
    lo, hi = s["scale"]
    out = {"spec": s, "variants": vs, "xy": L["xy"], "yaw": yaw, "variant": var, "scale": rng.uniform(lo, hi, n),
           "edge": L["edge"]}
    out["floor"] = _floor(s, out, rng)
    if len(_CACHE) > 3:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = out
    return out


# ---------------------------------------------------------------- the floor

def brash_mesh(variant: int = 0, length: float = 1.8) -> dict:
    """A fallen dead branch lying on the ground: a dead twig's tangle at a branch's size, pressed flat."""
    m = veg_leaf.dead_twig_mesh({"twig": {"length": length, "radius": 0.012 + 0.004 * (variant % 3), "droop": 0.0, "forks": 3.5,
                                          "depth": 3, "crook": 0.3, "broken": 0.35, "flat": 0.12, "lichen": 0.0}}, 40 + variant)
    V = m["V"].copy()
    V[:, 2] = np.abs(V[:, 2]) * 0.6 + 0.012
    return {"V": V, "F": m["F"], "mat": np.zeros(len(m["F"]), int)}


def stump_mesh(variant: int = 0) -> dict:
    """A cut stump: a flared frustum with a pale cut face (material 1), a little out of round."""
    k = _child(np.uint64(733), variant)
    r0 = 0.16 + 0.12 * float(_u(k, 1))
    h = 0.25 + 0.2 * float(_u(k, 2))
    n = 14
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    wob = 1 + 0.12 * np.sin(3 * a + 6 * float(_u(k, 3))) + 0.08 * np.sin(5 * a + 6 * float(_u(k, 4)))
    rings = [(1.5, 0.0), (1.15, 0.12 * h), (1.0, 0.5 * h), (0.98, h)]
    V = [np.c_[r0 * f * wob * np.cos(a), r0 * f * wob * np.sin(a), np.full(n, z)] for f, z in rings]
    V.append(np.array([[0, 0, h + 0.01]]))
    V = np.vstack(V)
    F, M = [], []
    for j in range(len(rings) - 1):
        for i in range(n):
            a0, a1, b0, b1 = j * n + i, j * n + (i + 1) % n, (j + 1) * n + i, (j + 1) * n + (i + 1) % n
            F += [[a0, a1, b1], [a0, b1, b0]]
            M += [0, 0]
    top = (len(rings) - 1) * n
    for i in range(n):
        F.append([top + i, top + (i + 1) % n, len(V) - 1])
        M.append(1)
    return {"V": V, "F": np.array(F), "mat": np.array(M)}


def _floor(s: dict, st: dict, rng) -> dict:
    """What lies and grows on the stand's floor: {"brash": {"xy", "yaw", "scale", "variant"}, "stumps": ..., "ferns": ...}.
    Brash lies thickest by the stems (where the dead branches fall); ferns stand where light reaches (clearings,
    paths, open edges); stumps anywhere a tree might have stood."""
    fl = s["floor"]
    w, d = s["size"]
    area = w * d
    xy_t = st["xy"]

    def uniform(n):
        return np.c_[rng.uniform(-w / 2, w / 2, n), rng.uniform(-d / 2, d / 2, n)]

    out = {}
    n = int(fl.get("brash", 0) * area)
    if n and len(xy_t):
        base = xy_t[rng.integers(len(xy_t), size=n)]
        p = base + rng.normal(0, 0.9, (n, 2))
        out["brash"] = {"xy": p, "yaw": rng.uniform(0, 360, n), "scale": rng.uniform(0.5, 1.3, n), "variant": rng.integers(0, 4, n)}
    n = int(fl.get("stumps", 0) * area)
    if n:
        p = uniform(n)
        if len(xy_t):  # (not inside a standing tree)
            from scipy.spatial import cKDTree
            p = p[cKDTree(xy_t).query(p)[0] > 0.9]
        out["stumps"] = {"xy": p, "yaw": rng.uniform(0, 360, len(p)), "scale": rng.uniform(0.8, 1.3, len(p)), "variant": rng.integers(0, 2, len(p))}
    n = int(fl.get("ferns", 0) * area)
    if n:
        p = uniform(n * 3)
        light = np.zeros(len(p))  # where the canopy is open
        for c in s["clearings"]:
            light = np.maximum(light, np.clip(1.4 - np.linalg.norm(p - np.asarray(c["at"], float), axis=1) / max(float(c["r"]), 1e-6), 0, 1))
        for pt in s["paths"]:
            pts = np.asarray(pt["points"], float)
            for a, b in zip(pts[:-1], pts[1:]):
                t = np.clip(((p - a) @ (b - a)) / max(float((b - a) @ (b - a)), 1e-9), 0, 1)
                light = np.maximum(light, np.clip(1.6 - np.linalg.norm(p - (a + t[:, None] * (b - a)), axis=1) / max(float(pt.get("width", 2.5)), 1e-6), 0, 1))
        for e in s["edge"]:
            o = np.asarray(SIDES[e], float)
            light = np.maximum(light, np.clip(1 - ((np.array([w, d]) / 2 * np.abs(o)).sum() - p @ o) / 6.0, 0, 1))
        patch = (np.sin(p[:, 0] * 0.35 + 1.3) * np.cos(p[:, 1] * 0.29 + 0.4) + rng.normal(0, 0.35, len(p)) > 0.25).astype(float)
        pr = np.clip(0.12 * patch + light, 0, 1)
        p = p[rng.random(len(p)) < pr][:n]
        if len(xy_t) and len(p):
            from scipy.spatial import cKDTree
            p = p[cKDTree(xy_t).query(p)[0] > 0.5]
        out["ferns"] = {"xy": p, "yaw": rng.uniform(0, 360, len(p)), "scale": rng.uniform(0.7, 1.25, len(p)), "variant": np.zeros(len(p), int)}
    return out


# ---------------------------------------------------------------- LODs, numbers

def lods(st: dict, eyes) -> np.ndarray:
    """Each tree's level of detail (0 near, 1 mid, 2 far) by its distance to the nearest eye."""
    lod = st["spec"]["lod"]
    e = np.asarray(eyes, float).reshape(-1, 3)[:, :2]
    d = np.min(np.linalg.norm(st["xy"][:, None, :] - e[None], axis=2), axis=1) if len(e) else np.zeros(len(st["xy"]))
    return np.where(d < lod["near"], 0, np.where(d < lod["mid"], 1, 2))


def measures(st: dict) -> dict:
    """The stand as a forester counts it: stems / ha, mean height (m), mean dbh (cm), basal area (m2 / ha), mean live
    crown ratio, canopy cover (crown discs over the plot, capped at 1)."""
    s = st["spec"]
    area = s["size"][0] * s["size"][1]
    cm = [vegetation.crown_measures(v["tree"]) for v in st["variants"]]
    k, sc = st["variant"], st["scale"]
    h = np.array([cm[i]["height"] for i in k]) * sc
    dbh = np.array([cm[i]["dbh_cm"] for i in k]) * sc
    cw = np.array([cm[i]["width_over_height"] * cm[i]["height"] for i in k]) * sc
    return {"trees": int(len(k)), "stems_per_ha": round(len(k) / area * 1e4), "height_m": round(float(h.mean()), 1) if len(k) else 0,
            "dbh_cm": round(float(dbh.mean()), 1) if len(k) else 0,
            "basal_area_m2_ha": round(float((math.pi * (dbh / 200) ** 2).sum() / area * 1e4), 1),
            "crown_ratio": round(float(np.mean([cm[i]["crown_ratio"] for i in k])), 2) if len(k) else 0,
            "canopy_cover": round(float(min(1.0, (math.pi * (cw / 2) ** 2).sum() / area)), 2),
            "variants": {v["name"]: {**{q: cm[i][q] for q in ("height", "dbh_cm", "crown_ratio", "width_over_height", "nodes")},
                                     "count": int((k == i).sum())} for i, v in enumerate(st["variants"])}}


def report(st: dict, eyes=None) -> str:
    s, m = st["spec"], measures(st)
    L = [f"stand: {m['trees']} trees on {s['size'][0]:g} x {s['size'][1]:g} m at {s['spacing']:g} m ({m['stems_per_ha']} stems / ha), "
         f"mean height {m['height_m']} m, dbh {m['dbh_cm']} cm, basal area {m['basal_area_m2_ha']} m2 / ha, live crown {m['crown_ratio']:.0%} of the height, "
         f"canopy cover {m['canopy_cover']:.0%}"]
    for nm, v in m["variants"].items():
        L.append(f"  {nm}: x{v['count']}, {v['height']} m, dbh {v['dbh_cm']} cm, live crown {v['crown_ratio']:.0%}, crown width {v['width_over_height'] * v['height']:.1f} m, {v['nodes']} nodes")
    fl = st["floor"]
    L.append("floor: " + ", ".join(f"{len(v['xy'])} {k}" for k, v in fl.items()) + f"; moss {s['floor'].get('moss', 0):g}, litter {s['floor'].get('litter', 0):g}")
    if eyes is not None:
        lod = lods(st, eyes)
        b = s["lod"]["budgets"]
        L.append(f"levels of detail from the eye(s): {int((lod == 0).sum())} near (< {s['lod']['near']:g} m, full detail), "
                 f"{int((lod == 1).sum())} mid (< {s['lod']['mid']:g} m, {b[1]} triangles), {int((lod == 2).sum())} far ({b[2]} triangles)")
    if m["basal_area_m2_ha"] > 70:
        L.append(f"WARNING: basal area {m['basal_area_m2_ha']} m2 / ha is more than a closed stand carries (30-60): the trees are too stout for this spacing, or the spacing too tight for their age")
    if m["canopy_cover"] < 0.6 and not s["clearings"]:
        L.append(f"WARNING: canopy cover {m['canopy_cover']:.0%}: the crowns don't close; from inside this reads as scattered trees, not a forest (closer spacing or older trees)")
    return "\n".join(L)


def layout_json(st: dict) -> dict:
    """What an engine's scatter needs: per variant its name, per tree x, y, yaw (deg), scale, variant; the floor's
    instances; the LOD distances and budgets."""
    s = st["spec"]
    return {"spacing": s["spacing"], "size": s["size"], "lod": s["lod"], "haze": s["haze"],
            "variants": [{"name": v["name"], "role": v["role"], "height": round(float(v["tree"]["height"]), 2)} for v in st["variants"]],
            "trees": [{"x": round(float(p[0]), 3), "y": round(float(p[1]), 3), "yaw": round(float(y), 1), "scale": round(float(c), 3), "variant": int(k)}
                      for p, y, c, k in zip(st["xy"], st["yaw"], st["scale"], st["variant"])],
            "floor": {k: [{"x": round(float(p[0]), 3), "y": round(float(p[1]), 3), "yaw": round(float(y), 1), "scale": round(float(c), 3), "variant": int(q)}
                          for p, y, c, q in zip(v["xy"], v["yaw"], v["scale"], v["variant"])] for k, v in st["floor"].items()}}


# ---------------------------------------------------------------- looks

VIEWS = ("inside", "aisle", "edge", "above", "canopy")


def view_jobs(st: dict, views, size: int = 720) -> list[dict]:
    """Named views of a stand as camera jobs: "inside" (eye 1.7 m in the stand's middle, looking along it), "aisle"
    (the same, down a row), "edge" (from outside an open side, or the south side, toward the stand), "above" (a high
    oblique), "canopy" (from the floor, up); or a camera {"eye", "look", "fov"}."""
    s = st["spec"]
    w, d = s["size"]
    H = max(v["tree"]["height"] for v in st["variants"])
    xy = st["xy"]

    def free(p, r=1.2):  # the nearest spot with no stem within r
        p = np.asarray(p, float)
        best = p
        for k in range(60):
            q = p + (0.25 * k) * np.array([math.cos(2.4 * k), math.sin(2.4 * k)])
            if not len(xy) or np.linalg.norm(xy - q, axis=1).min() > r:
                best = q
                break
        return best

    jobs = []
    for i, v in enumerate(views):
        nm = v if isinstance(v, str) else v.get("name", f"camera{i + 1}")
        j = {"name": nm, "size": [int(size * 1.5), size], "sun": [205, 52]}
        if isinstance(v, dict):
            j.update(eye=list(v["eye"]), look=list(v["look"]), fov=v.get("fov", 60))
            if v.get("sun"):
                j["sun"] = v["sun"]
        elif v == "inside":
            e = free([0.4, -0.25 * d])
            j.update(eye=[e[0], e[1], 1.7], look=[e[0] + 2.0, e[1] + 14.0, 3.6], fov=62)
        elif v == "aisle":
            e = free([0.5 * s["spacing"], -0.3 * d])
            j.update(eye=[e[0], e[1], 1.7], look=[e[0], e[1] + 20.0, 2.6], fov=58)
        elif v == "edge":
            o = np.asarray(SIDES[s["edge"][0]] if s["edge"] else (0, -1), float)
            dist = (np.array([w, d]) / 2 * np.abs(o)).sum() + 1.3 * H
            side = np.array([-o[1], o[0]])
            e = o * dist + side * 0.25 * dist
            j.update(eye=[e[0], e[1], 1.7], look=[o[0] * 0.3 * dist, o[1] * 0.3 * dist, 0.45 * H], fov=46)
        elif v == "above":
            j.update(eye=[0.9 * w, -1.1 * d, 1.6 * H + 0.3 * max(w, d)], look=[0, 0, 0.5 * H], fov=40)
        elif v == "canopy":
            e = free([0, 0])
            j.update(eye=[e[0], e[1], 1.5], look=[e[0] + 0.5, e[1] + 2.0, H], fov=80)
        else:
            raise ValueError(f"stand view {v!r}: {list(VIEWS)} or a camera {{'eye', 'look', 'fov'}}")
        jobs.append(j)
    return jobs


def look(st: dict, views=("inside",), out_stem: str = "stand", size: int = 720, floor_radius: float = 30.0,
         max_full: int = 40) -> dict:
    """Render views of the stand. Each tree is drawn at the level of detail its distance from the nearest eye gives
    (`lod`; at most `max_full` trees at full detail: the nearest), every variant x level meshed once and instanced.
    The floor's scatter is drawn within `floor_radius` m of an eye. Returns {"files": [(view, path)], counts}."""
    from . import veg_look
    s = st["spec"]
    jobs = view_jobs(st, views, size)
    for j in jobs:
        j["out"] = f"{out_stem}_{j['name']}.png"
    eyes = np.array([j["eye"] for j in jobs], float)
    lod = lods(st, eyes)
    dist = np.min(np.linalg.norm(st["xy"][:, None, :] - eyes[None, :, :2], axis=2), axis=1)
    near = np.flatnonzero(lod == 0)
    if len(near) > max_full:  # (the GPU: a few dozen trees with every twig is what a look can hold)
        lod[near[np.argsort(dist[near])[max_full:]]] = 1
    b = s["lod"]["budgets"]
    order = np.argsort(dist)
    items = [(st["variants"][st["variant"][i]]["tree"], st["xy"][i].tolist(), float(st["yaw"][i]), b[lod[i]], float(st["scale"][i])) for i in order]
    fl = st["floor"]

    def close(v):
        return np.min(np.linalg.norm(v["xy"][:, None, :] - eyes[None, :, :2], axis=2), axis=1) < floor_radius if len(v["xy"]) else np.zeros(0, bool)

    scatter = []
    if "brash" in fl:
        m_ = close(fl["brash"])
        for k in range(4):
            q = m_ & (fl["brash"]["variant"] == k)
            if q.any():
                bm = brash_mesh(k)
                scatter.append({**bm, "colors": [[0.36, 0.33, 0.29]], "pos": np.c_[fl["brash"]["xy"][q], np.zeros(q.sum())],
                                "yaw": fl["brash"]["yaw"][q], "scale": fl["brash"]["scale"][q]})
    if "stumps" in fl:
        m_ = close(fl["stumps"]) | True
        for k in range(2):
            q = fl["stumps"]["variant"] == k
            if q.any():
                scatter.append({**stump_mesh(k), "colors": [[0.3, 0.26, 0.22], [0.62, 0.52, 0.38]], "pos": np.c_[fl["stumps"]["xy"][q], np.zeros(q.sum())],
                                "yaw": fl["stumps"]["yaw"][q], "scale": fl["stumps"]["scale"][q]})
    if "ferns" in fl and len(fl["ferns"]["xy"]):
        fern = _fern(s["floor"].get("fern", "fern"))
        m_ = close(fl["ferns"])
        items += [(fern, p.tolist(), float(y), None, float(c)) for p, y, c in zip(fl["ferns"]["xy"][m_], fl["ferns"]["yaw"][m_], fl["ferns"]["scale"][m_])]
    first, rest = items[0], items[1:]
    job = {"haze": s["haze"], **s["light"], "ground": {"moss": {"amount": s["floor"].get("moss", 0.0), "color": [0.25, 0.33, 0.13], "size": 1.8} if s["floor"].get("moss") else None,
                                         "litter": s["floor"].get("litter", 0.0)}, "ruler": 0}
    r = veg_look.render(first[0], jobs, others=rest, at=first[1], yaw=first[2], triangles=first[3], scale=first[4], scatter=scatter, job=job,
                        timeout=1800)
    return {"files": [(j["name"], j["out"]) for j in jobs], "trees": int(len(order)), "near": int((lod == 0).sum()), "mid": int((lod == 1).sum()),
            "far": int((lod == 2).sum()), "meshed": r.get("meshed"), "triangles_instanced": r.get("others_triangles"),
            "floor": {k: int(len(v["xy"])) for k, v in fl.items()}, "mesh_s": r["mesh_s"], "blender_s": r["blender_s"]}


def _fern(name: str) -> dict:
    k = ("fern", name)
    if k not in _CACHE:
        _CACHE[k] = vegetation.grow({"species": name})
    return _CACHE[k]
