"""Vegetation styles: the same grown plant dressed another way (spec `"style": "blobby"` or {"sheet": "blobby",
...overrides}).

A style never touches the growth: the skeleton, height, crown extent and lean are the realistic tree's. It is a SHEET
of ordinary numbers (vegetation_styles/<name>.json, every key overridable in the spec) over a few general operations:

- `wood`: which limbs are drawn (the stoutest `limbs`), how far along them (`reach`), how fat (`radius` x, never
  thinner than `taper_floor` x the limb's base), bends smoothed, ends rounded, bark one flat colour.
- `crown` kind "masses": the twigs' positions are clustered (k-means), each cluster becomes an ellipsoid (its
  principal axes x `spread` + `pad` twig lengths, no semi-axis under 0.75 x `min_feature`), the ellipsoids are joined by a
  smooth union (`blend` m) and meshed (marching cubes on the field, decimated to the budget, vertices put back on the
  field). Closed, no leaves, no alpha. How many masses: the fewest in `masses` [lo, hi] whose silhouette is within
  0.01 IoU of the best (measured against the realistic tree's own silhouette from three sides, at true scale).
- normals: the field's gradient (smooth over each mass and across the blends), mixed `normals` toward the direction
  out of the crown's middle.
- colour: one tone per mass, `tones` steps across the tree by the mass's height (top lighter, a little warmer), as
  COLOR_0 (a multiplier of the material's colour, so season variants only swap the material).
- wind: a mass moves as a whole with the limb it sits on (the limb's branch weight and phase).

What artists do (sources in vegetation_guide.md): blob / low-poly trees are a few smooth-shaded lumps on a trunk;
soft "Ghibli" foliage gets its shading from normals transferred off a rounded proxy hull. Here the proxy IS the
crown (blobby), and later styles put cards on it and take its normals.
"""

from __future__ import annotations

import colorsys
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from . import sdf, veg_leaf, veg_mesh, vegetation

STYLES = Path(__file__).with_name("vegetation_styles")
AZIMUTHS = (0, 60, 120)
AUTUMN = [0.78, 0.56, 0.16]
SEASONS = ("spring", "summer", "autumn", "winter", "snow")
_FIT: dict = {}


def names() -> list[str]:
    return ["realistic"] + sorted(p.stem for p in STYLES.glob("*.json"))


def sheet(spec: dict) -> dict | None:
    """The style's numbers for this spec (the sheet under the spec's own overrides), or None for realistic."""
    st = spec.get("style")
    if not st or st == "realistic":
        return None
    name, over = (st, {}) if isinstance(st, str) else (st.get("sheet", "realistic"), {k: v for k, v in st.items() if k != "sheet"})
    if name == "realistic":
        if over:
            raise ValueError('style overrides need a sheet: {"sheet": "blobby", ...}')
        return None
    p = STYLES / f"{name}.json"
    if not p.exists():
        raise ValueError(f"no vegetation style {name!r}; styles: {names()}")
    base = json.loads(p.read_text())
    for k, v in over.items():
        if k not in base:
            raise ValueError(f"style: unknown key {k!r}; the {name} sheet has {sorted(base)}")
        if isinstance(v, dict):
            bad = set(v) - set(base[k])
            if bad:
                raise ValueError(f"style.{k}: unknown keys {sorted(bad)}; it takes {sorted(base[k])}")
    out = vegetation._merge(base, over)
    out["name"] = name
    return out


def describe(name: str) -> dict:
    return json.loads((STYLES / f"{name}.json").read_text())


# ---------------------------------------------------------------- colour
def styled(rgb, sat: float = 1.0, val: float = 1.0) -> list:
    h, s, v = colorsys.rgb_to_hsv(*[float(c) for c in rgb])
    return [round(c, 4) for c in colorsys.hsv_to_rgb(h, min(s * sat, 1.0), min(v * val, 1.0))]


def lin(c) -> list:
    return [float(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c]


def evergreen(spec: dict) -> bool:
    lf = spec["leaves"]
    return bool(lf.get("evergreen", str(lf.get("shape", "")).startswith("needle")))


def season_color(spec: dict, season: str, st: dict | None = None):
    """The foliage's one colour in a season (sRGB), or None when the plant is bare then. With a style sheet the colour
    goes through its `colour` (saturation, value). spring = `leaves.spring`, else the summer colour mixed toward a
    fresh yellow-green; snow = mixed toward white; autumn = `leaves.autumn` (an evergreen keeps its colour)."""
    lf = spec["leaves"]
    eg = evergreen(spec)
    ss = (st or {}).get("seasons") or {}
    mix = lambda a, b, t: [a[i] * (1 - t) + b[i] * t for i in range(3)]
    base = list(lf.get("color", [0.16, 0.3, 0.08]))
    if season in ("winter", "bare", "dead") and (not eg or season == "dead"):
        return None
    c = base
    if season == "autumn" and not eg:
        c = list(lf.get("autumn", AUTUMN))
    elif season == "spring":
        sp = ss.get("spring") or {"mix": [0.55, 0.78, 0.25], "amount": 0.45}
        c = list(lf["spring"]) if isinstance(lf.get("spring"), (list, tuple)) else mix(base, sp["mix"], sp["amount"] * (0.4 if eg else 1.0))
    if st:
        co = st.get("colour") or {}
        c = styled(c, co.get("saturation", 1.0), co.get("value", 1.0))
    if season == "snow":
        sn = ss.get("snow") or {"mix": [0.93, 0.95, 0.98], "amount": 0.7}
        c = mix(c, sn["mix"], sn["amount"])
    return [round(float(x), 4) for x in c]


def bark_color(spec: dict, st: dict) -> list:
    co = st.get("colour") or {}
    return styled((spec.get("bark") or {}).get("color", [0.5, 0.45, 0.4]), co.get("bark_saturation", 1.0), co.get("bark_value", 1.0))


# ---------------------------------------------------------------- wood: the limbs that are drawn
def wood(tree: dict, st: dict, inside=None) -> dict:
    """A small tree of the drawn wood only: the trunk's axis and the stoutest first-order limbs, each to `reach` of its
    length along its stoutest wood, fattened, bends smoothed, ends rounded. The same keys veg_mesh.tubes and
    veg_export.wind_nodes read; `src` = each node's node in the grown tree; `info` = what was left out.
    inside: points -> depth inside the crown (m, positive inside): a limb then ends `bury` m inside the first mass it
    enters (no later than `reach`), so no limb ends in the air or pokes out the far side."""
    w = st["wood"]
    P, par, rad, ax = tree["pos"], tree["parent"], tree["radius"], tree["axis"]
    kids: dict = {}
    for i in range(1, len(par)):
        kids.setdefault(int(par[i]), []).append(i)
    trunk = np.flatnonzero(ax == ax[1])
    trunk = trunk[trunk >= 1]
    tpos = {int(n): i for i, n in enumerate(trunk)}
    lo, hi = (w["limbs"], w["limbs"]) if isinstance(w["limbs"], int) else w["limbs"]
    allL = vegetation.limbs(tree, 400, 0.0)
    cand = sorted([L for L in allL if int(par[tree["axes"][L["axis"]]["node"]]) in tpos], key=lambda L: -L["diameter"])
    n_keep = 0
    if cand:
        n_keep = int(np.clip(sum(L["diameter"] >= 0.4 * cand[0]["diameter"] for L in cand), lo, hi))
    kept = cand[:n_keep]
    fat, floor = float(w.get("radius", 1.0)), float(w.get("taper_floor", 0.0))

    def cut(nodes, share, least=0):
        pts = np.vstack([P[par[nodes[0]]], P[nodes]])
        cum = np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))
        k = int(np.searchsorted(cum, share * cum[-1])) + 1
        return nodes[: max(min(k, len(nodes)), least, 2)]

    top_base = max([tpos[int(par[tree["axes"][L["axis"]]["node"]])] for L in kept], default=0)
    tn = cut(trunk, float(w.get("trunk_reach", 1.0)), top_base + 2)
    r_ref = float(rad[tn[min(len(tn) - 1, max(1, len(tn) // 5))]])
    pos, parent, radius, axis, order, src = [P[0]], [0], [fat * max(float(rad[0]), floor * r_ref)], [0], [0], [0]
    index = {}

    def smooth(pts):
        pts = pts.copy()
        for _ in range(int(w.get("smooth", 0))):
            pts[1:-1] = 0.5 * pts[1:-1] + 0.25 * (pts[:-2] + pts[2:])
        return pts

    def add(nodes, root, pts, rr, ai, od):
        prev = root
        first = len(pos)
        for n, p_, r_ in zip(nodes, pts, rr):
            index[int(n)] = len(pos)
            pos.append(p_)
            parent.append(prev)
            radius.append(float(r_))
            axis.append(ai)
            order.append(od)
            src.append(int(n))
            prev = len(pos) - 1
        if w.get("round_ends", True) and len(pts) > 1:  # a hemisphere: rings at 35, 62 and 82 deg round the end
            d = pts[-1] - pts[-2]
            d = d / max(float(np.linalg.norm(d)), 1e-9)
            for th in (35, 62, 82):
                pos.append(pts[-1] + d * rr[-1] * math.sin(math.radians(th)))
                parent.append(prev)
                radius.append(float(rr[-1] * math.cos(math.radians(th))))
                axis.append(ai)
                order.append(od)
                src.append(int(nodes[-1]))
                prev = len(pos) - 1
        return first

    tp = smooth(np.vstack([P[0], P[tn]]))[1:]
    add(tn, 0, tp, fat * np.maximum(rad[tn], floor * r_ref), 0, 0)
    drawn_len = float(np.linalg.norm(np.diff(np.vstack([P[0], P[tn]]), axis=0), axis=1).sum())
    for j, L in enumerate(kept):
        n0 = tree["axes"][L["axis"]]["node"]
        full = vegetation.stout_path(tree, n0, kids)
        nodes = cut(full, float(w.get("reach", 1.0)))
        if inside is not None:
            dep = inside(P[full])
            deep = np.flatnonzero(dep >= float(w.get("bury", 0.8)))
            nodes = full[: max(int(deep[0]) + 1, 2)] if len(deep) else full[: max(int(np.argmax(dep)) + 1, 2)]
        root = index[int(par[n0])]
        pts = smooth(np.vstack([pos[root], P[nodes]]))[1:]
        r0 = max(fat * float(rad[n0]), float(w.get("limb_min", 0.0)) * fat * r_ref)
        rr = np.minimum(np.maximum(fat * rad[nodes], floor * r0), 0.8 * radius[root])
        add(nodes, root, pts, rr, j + 1, 1)
        drawn_len += float(np.linalg.norm(np.diff(np.vstack([pos[root], pts]), axis=0), axis=1).sum())
    src = np.array(src)
    n = len(pos)
    total_len = float(np.linalg.norm(P - P[par], axis=1).sum())
    return {"pos": np.array(pos), "parent": np.array(parent), "radius": np.array(radius), "axis": np.array(axis),
            "order": np.array(order), "ends": np.zeros(n, bool), "key": tree["key"][src], "height": tree["height"],
            "spec": tree["spec"], "dead": None, "src": src,
            "info": {"limbs_kept": len(kept), "limbs": len(allL), "axes": int(len(tree["axes"])), "axes_kept": 1 + len(kept),
                     "wood_m": round(drawn_len, 1), "wood_m_grown": round(total_len, 1),
                     "limb_names": [L["name"] for L in kept]}}


def wood_mesh(mini: dict, st: dict, f: float = 1.0) -> dict:
    """The drawn wood as tubes; f < 1 = a lower LOD (fewer sides and rings)."""
    lo, hi = st["wood"].get("sides", [6, 12])
    sides = (max(3, int(round(lo * f))), max(4, int(round(hi * f))))
    return veg_mesh.tubes(mini, sides=sides, simplify=0.25 / max(f, 0.2), tip=1.0, tile=(0.5, 1.0))


def capsules(mini: dict, limit: int = 24) -> list[dict]:
    """Collision for the wood that is drawn: straight pieces along the trunk and each limb."""
    caps = []
    for ai in np.unique(mini["axis"]):
        nodes = np.flatnonzero(mini["axis"] == ai)
        nodes = nodes[nodes >= 1]
        pts = np.vstack([mini["pos"][mini["parent"][nodes[0]]], mini["pos"][nodes]])
        rr = np.r_[mini["radius"][nodes[0]], mini["radius"][nodes]]
        keep = veg_mesh._rdp(pts, np.maximum(rr, 0.02) * 0.6, rr * 0 + 1)
        for i0, i1 in zip(keep[:-1], keep[1:]):
            if rr[i1] < 0.3 * rr[i0] and np.linalg.norm(pts[i1] - pts[i0]) < rr[i0]:
                continue  # (the rounded end's rings)
            caps.append({"a": pts[i0].round(3).tolist(), "b": pts[i1].round(3).tolist(), "ra": round(float(rr[i0]), 3), "rb": round(float(rr[i1]), 3)})
    return caps[:limit]


# ---------------------------------------------------------------- crown masses
def leaf_points(tree: dict) -> tuple[np.ndarray, float]:
    """Where the foliage is: the middle of every living twig, and the twig's length (m)."""
    tw = veg_leaf.place_live(tree)
    tl = float({**veg_leaf.TWIG, **(tree["spec"]["leaves"].get("twig") or {})}["length"])
    if not len(tw["pos"]):
        return np.zeros((0, 3)), tl
    return tw["pos"] + tw["frame"][:, :, 1] * (0.5 * tl * tw["scale"])[:, None], tl


def _kmeans(X: np.ndarray, k: int, iters: int = 30) -> np.ndarray:
    """Labels of a k-means from a farthest-point start (no randomness: the same tree gives the same masses)."""
    C = [X[np.argmin(np.linalg.norm(X - X.mean(0), axis=1))]]
    d = np.linalg.norm(X - C[0], axis=1)
    for _ in range(1, k):
        C.append(X[int(np.argmax(d))])
        d = np.minimum(d, np.linalg.norm(X - C[-1], axis=1))
    C = np.array(C)
    lab = np.zeros(len(X), int)
    for _ in range(iters):
        D = ((X[:, None, :] - C[None]) ** 2).sum(-1)
        new = D.argmin(1)
        if (new == lab).all() and _:
            break
        lab = new
        for j in range(k):
            if (lab == j).any():
                C[j] = X[lab == j].mean(0)
    return lab


def masses(X: np.ndarray, k: int, st: dict, twig: float) -> list[dict]:
    """k ellipsoids over the foliage points: [{"c", "R" (rows = axes), "r" (semi-axes), "n" points}], lowest first."""
    cr = st["crown"]
    ztop = float(X[:, 2].max()) + 0.5 * twig
    if len(X) > 6000:  # (a cluster's shape doesn't need every twig)
        X = X[np.argsort(vegetation._u(np.arange(len(X)).astype(np.uint64), 3))[:6000]]
    lab = _kmeans(X, k)
    out = []
    for j in range(k):
        Q = X[lab == j]
        if len(Q) < max(4, 0.01 * len(X)):
            continue
        c = Q.mean(0)
        ev, U = np.linalg.eigh(np.cov((Q - c).T) + np.eye(3) * 1e-6)
        r = float(cr.get("spread", 1.75)) * np.sqrt(np.maximum(ev, 0)) + float(cr.get("pad", 0.5)) * twig
        r = np.maximum(r, 0.75 * float(cr.get("min_feature", 0.6)))
        r = np.maximum(r, float(cr.get("roundness", 0.0)) * r.max())  # (a flat cluster as a disc read as a lily pad, not a lump)
        ez = math.sqrt(float(((U.T[:, 2] * r) ** 2).sum()))  # its vertical half extent
        c[2] -= max(0.0, c[2] + ez - ztop)  # never taller than the tree: a rounded-up top mass sinks to the tree's own height
        out.append({"c": c, "R": U.T.copy(), "r": r, "n": int(len(Q))})
    out.sort(key=lambda e: float(e["c"][2]))
    return out


def field(ells: list[dict], p: np.ndarray, blend: float, each: bool = False, floor: float | None = None):
    """The crown's field at points (negative inside): the ellipsoids' (approximate) distances under a smooth union.
    each=True also returns the (n, k) distances. floor: nothing under this height."""
    D = np.empty((len(p), len(ells)))
    for j, e in enumerate(ells):
        q = (p - e["c"]) @ e["R"].T
        k0 = np.linalg.norm(q / e["r"], axis=1)
        k1 = np.linalg.norm(q / (e["r"] ** 2), axis=1)
        D[:, j] = np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -float(e["r"].min()))
    d = D[:, 0].copy()
    for j in range(1, len(ells)):
        d = sdf.smin(d, D[:, j], blend)
    if floor is not None:
        d = np.maximum(d, floor - p[:, 2])
    return (d, D) if each else d


def _gradient(ells, p, blend, floor, h=0.02):
    g = np.empty_like(p)
    for a in range(3):
        e = np.zeros(3)
        e[a] = h
        g[:, a] = field(ells, p + e, blend, floor=floor) - field(ells, p - e, blend, floor=floor)
    return g / (2 * h)


def crown_mesh(ells: list[dict], st: dict, voxel: float | None = None, floor: float | None = None) -> dict:
    """The masses as one closed surface: marching cubes of the field ({"V", "F"}, outward)."""
    from skimage import measure
    cr = st["crown"]
    blend = float(cr.get("blend", 0.5))
    lo = np.min([e["c"] - e["r"].max() for e in ells], axis=0) - blend
    hi = np.max([e["c"] + e["r"].max() for e in ells], axis=0) + blend
    voxel = voxel or float(cr.get("voxel") or 0) or float(np.clip((hi - lo).max() / 80, 0.06, 0.3))
    ax = [np.arange(lo[i] - voxel, hi[i] + 2 * voxel, voxel) for i in range(3)]
    G = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    vol = np.concatenate([field(ells, G[i: i + 200000], blend, floor=floor) for i in range(0, len(G), 200000)])
    vol = vol.reshape(len(ax[0]), len(ax[1]), len(ax[2]))
    V, F, _, _ = measure.marching_cubes(vol, 0.0, spacing=(voxel,) * 3)
    V = V + [ax[0][0], ax[1][0], ax[2][0]]
    pick = np.arange(0, len(F), max(1, len(F) // 500))
    fn = np.cross(V[F[pick, 1]] - V[F[pick, 0]], V[F[pick, 2]] - V[F[pick, 0]])
    if (np.einsum("ij,ij->i", fn, _gradient(ells, V[F[pick]].mean(1), blend, floor)) < 0).mean() > 0.5:
        F = F[:, ::-1]
    return {"V": V, "F": np.ascontiguousarray(F), "voxel": voxel}


def color_gain(st: dict) -> float:
    """What the crown material's colour is multiplied by (COLOR_0 holds each mass's tone divided by it)."""
    cr = st.get("crown") or {}
    return float(max(cr.get("tone", [0.85, 1.15])) * (1 + abs(float(cr.get("warm_top", 0.0)))))


def _decimate(V, F, target: int):
    if len(F) <= target:
        return V, F
    import pyfqmr
    s = pyfqmr.Simplify()
    s.setMesh(np.ascontiguousarray(V, np.float64), np.ascontiguousarray(F, np.int32))
    s.simplify_mesh(target_count=int(target), aggressiveness=5, preserve_border=True, verbose=False)
    V2, F2, _ = s.getMesh()
    return np.asarray(V2, float), np.asarray(F2, np.int64)


# ---------------------------------------------------------------- silhouettes: is it still the same tree?
def _fill(mask):
    any_, left, right = vegetation._rows(mask)
    f = np.zeros_like(mask)
    for i in np.flatnonzero(any_):
        f[i, left[i]: right[i] + 1] = True
    return f


def mesh_mask(meshes: list, azimuth: float, x0: float, z1: float, px: float, shape) -> np.ndarray:
    """Triangle meshes [(V, F)] seen from the side, in a given frame (as vegetation.silhouette's)."""
    from PIL import Image, ImageDraw
    im = Image.new("L", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(im)
    c, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    for V, F in meshes:
        X = (V[:, 0] * c + V[:, 1] * s_ - x0) * px
        Y = (z1 - V[:, 2]) * px
        T = np.stack([X[F], Y[F]], -1).reshape(len(F), 6)
        for t in T.tolist():
            d.polygon(t, fill=255)
    return np.asarray(im) > 0


def reference(tree: dict, azimuths=AZIMUTHS, px: float = 10.0) -> list:
    """The realistic tree's silhouettes in leaf (mask, frame) per azimuth: what every style is held against."""
    return [vegetation.silhouette(tree, az, px, leaves=True, pad=3.0) for az in azimuths]


def compare(tree: dict, meshes: list, azimuths=AZIMUTHS, px: float = 10.0, refs: list | None = None) -> dict:
    """The styled meshes against the realistic tree in leaf, from the side at true scale (same frame, feet together):
    IoU of the row-filled outlines per azimuth, and both heights and crown widths (m)."""
    ious, wr, ws = [], [], []
    refs = refs or reference(tree, azimuths, px)
    for az, (A, fr) in zip(azimuths, refs):
        B = mesh_mask(meshes, az, fr["x0"], fr["z1"], px, A.shape)
        A, B = _fill(A), _fill(B)
        ious.append(float((A & B).sum() / max((A | B).sum(), 1)))
        wr.append(float(A.sum(1).max() / px))
        ws.append(float(B.sum(1).max() / px))
    top = max(float(V[:, 2].max()) for V, _ in meshes)
    return {"iou": round(float(np.mean(ious)), 3), "iou_by_azimuth": [round(v, 3) for v in ious], "azimuths": list(azimuths),
            "height_m": [round(float(tree["height"]), 2), round(top, 2)],
            "width_m": [round(float(np.mean(wr)), 2), round(float(np.mean(ws)), 2)]}


# ---------------------------------------------------------------- the fit (once per tree and sheet) and the dress (per LOD)
def fit(tree: dict, st: dict) -> dict:
    """The styled plant's parts before any budget: {"mini": the drawn wood, "ells": the crown's masses (or []),
    "dense": the crown at full resolution, "match": compare()'s numbers, "tried": IoU per number of masses}."""
    key = hashlib.sha1(json.dumps(st, sort_keys=True).encode()).hexdigest()
    hit = _FIT.get(id(tree))
    if hit is not None and hit[0] is tree and hit[1] == key:
        return hit[2]
    mini = wood(tree, st)
    Wm = wood_mesh(mini, st)
    wm = (Wm["V"], Wm["F"])
    X, tl = leaf_points(tree)
    out = {"mini": mini, "ells": [], "dense": None, "tried": {}, "twigs": int(len(X))}
    floor = float(tree["spec"]["leaves"].get("clear", 0.03)) + 0.02
    refs = reference(tree)
    cr = st.get("crown") or {}
    if len(X) >= 8 and cr.get("kind", "masses") == "masses":
        lo, hi = (cr["masses"], cr["masses"]) if isinstance(cr["masses"], int) else cr["masses"]
        cands = {}
        for k in range(int(lo), int(hi) + 1):
            ells = masses(X, k, st, tl)
            if not ells or len(ells) in cands:
                continue
            cm = crown_mesh(ells, st, voxel=None if lo == hi else 0.3, floor=floor)
            cands[len(ells)] = (ells, compare(tree, [wm, (cm["V"], cm["F"])], refs=refs)["iou"])
        best = max(v[1] for v in cands.values())
        k = min(k_ for k_, v in cands.items() if v[1] >= best - 0.01)
        out["tried"] = {k_: v[1] for k_, v in cands.items()}
        out["ells"] = cands[k][0]
        out["dense"] = crown_mesh(out["ells"], st, floor=floor)
        out["floor"] = floor
        mini = out["mini"] = wood(tree, st, lambda q: -field(out["ells"], q, float(cr.get("blend", 0.5)), floor=floor))
        Wm = wood_mesh(mini, st)
        wm = (Wm["V"], Wm["F"])
    out["match"] = compare(tree, [wm] + ([(out["dense"]["V"], out["dense"]["F"])] if out["dense"] else []), refs=refs)
    if len(_FIT) > 6:
        _FIT.clear()
    _FIT[id(tree)] = (tree, key, out)
    return out


def dress(tree: dict, st: dict, triangles: int | None = None, season: str = "summer") -> dict:
    """The plant in its style within a triangle count (default the sheet's `budget`): {"wood": tubes, "wood_wind":
    (trunk, branch, phase, flutter) per wood vertex, "crown": None | {"V", "F", "N", "uv", "col" (n, 3 multiplier),
    "wind", "mass"}, "mini", "info"}. A lower count takes sides and rings off the wood and triangles off the same
    crown: the masses themselves never change with the LOD."""
    from . import veg_export
    ft = fit(tree, st)
    full = int(st.get("budget", 5000))
    triangles = int(triangles or full)
    f = float(np.clip(math.sqrt(triangles / full), 0.3, 1.4))
    mini = ft["mini"]
    share = float(st["wood"].get("share", 0.25))
    W = wood_mesh(mini, st, f)
    while len(W["F"]) > max(share * triangles, 60) * (1.0 if ft["ells"] else 4.0) and f > 0.2:
        f *= 0.85
        W = wood_mesh(mini, st, f)
    wn = veg_export.wind_nodes(mini)
    nd = W["node"]
    out = {"wood": W, "wood_wind": (wn["trunk"][nd], wn["branch"][nd], wn["phase"][nd], np.zeros(len(nd))), "crown": None, "mini": mini}
    info = {"style": st["name"], **mini["info"], "masses": len(ft["ells"]), "twigs": ft["twigs"], "match": ft["match"],
            "masses_tried": ft["tried"], "wood_triangles": int(len(W["F"])), "crown_triangles": 0, "budget": triangles}
    if ft["ells"] and season_color(tree["spec"], season, st) is not None:
        cr, ells = st["crown"], ft["ells"]
        blend = float(cr.get("blend", 0.5))
        V, F = _decimate(ft["dense"]["V"], ft["dense"]["F"], max(triangles - len(W["F"]), 40 * len(ells)))
        for _ in range(2):  # back onto the field (decimation pulls a rounded surface in)
            d = field(ells, V, blend, floor=ft["floor"])
            g = _gradient(ells, V, blend, ft["floor"])
            V = V - g * (d / np.maximum((g * g).sum(1), 1e-9))[:, None]
        d, D = field(ells, V, blend, each=True, floor=ft["floor"])
        g = _gradient(ells, V, blend, ft["floor"])
        N = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
        cen = np.average([e["c"] for e in ells], axis=0, weights=[e["n"] for e in ells])
        o = V - cen
        o /= np.maximum(np.linalg.norm(o, axis=1, keepdims=True), 1e-9)
        wN = float(cr.get("normals", 0.0))
        N = (1 - wN) * N + wN * o
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        mass = D.argmin(1)
        k = len(ells)
        # one tone per mass, in steps by the mass's height
        cz = np.array([e["c"][2] for e in ells])
        tones = int(max(1, cr.get("tones", 3)))
        t = (cz - cz.min()) / max(float(np.ptp(cz)), 1e-6)
        ti = np.minimum((t * tones).astype(int), tones - 1) if k > 1 else np.zeros(k, int)
        tf = ti / max(tones - 1, 1)
        t0, t1 = cr.get("tone", [0.85, 1.15])
        warm = float(cr.get("warm_top", 0.0))
        mcol = np.stack([(t0 + (t1 - t0) * tf) * (1 + warm * (tf - 0.5) * 2), t0 + (t1 - t0) * tf, (t0 + (t1 - t0) * tf) * (1 - warm * (tf - 0.5) * 2)], 1)
        gain = float(max(t0, t1) * (1 + abs(warm)))  # COLOR_0 must stay within 0..1 (glTF): the material's colour carries the rest
        mcol = mcol / gain
        ez = np.array([math.sqrt(float(((e["R"][:, 2] * e["r"]) ** 2).sum())) for e in ells])
        u = np.clip((V[:, 2] - (cz[mass] - ez[mass])) / (2 * ez[mass]), 0, 1)
        uv = np.stack([u, (mass + 0.5) / k], 1)
        # wind: a mass goes with the wood it sits on, as a whole; soft between masses so nothing tears
        wd = st.get("wind") or {}
        mp = mini["pos"]
        anchor = np.array([int(np.argmin(np.linalg.norm(mp - e["c"], axis=1))) for e in ells])
        b_m = np.maximum(wn["branch"][anchor], float(wd.get("mass", 0.3)))
        ph_m = np.where(mini["order"][anchor] > 0, wn["phase"][anchor], vegetation._u(np.arange(k).astype(np.uint64) + np.uint64(int(tree["spec"].get("seed", 1))), 57))
        sw = np.exp(-(D - D.min(1, keepdims=True)) / max(0.5 * blend, 1e-3))
        sw /= sw.sum(1, keepdims=True)
        trunk_w = np.clip(V[:, 2] / max(tree["height"], 1e-6), 0, 1) ** 1.5
        branch_w = sw @ b_m + float(wd.get("squash", 0.0)) * (u - 0.5)
        out["crown"] = {"V": V, "F": F, "N": N, "uv": uv, "col": mcol[mass], "gain": gain, "mass": mass, "tone": ti,
                        "wind": (trunk_w, np.clip(branch_w, 0, 1), sw @ ph_m, np.full(len(V), float(wd.get("flutter", 0.0))))}
        info["crown_triangles"] = int(len(F))
        info["tones"] = int(len(np.unique(ti)))
        info["mass_list"] = [{"center": e["c"].round(2).tolist(), "radii": np.sort(e["r"])[::-1].round(2).tolist(), "tone": int(ti[j])}
                             for j, e in enumerate(ells)]
    info["triangles"] = info["wood_triangles"] + info["crown_triangles"]
    out["info"] = info
    return out


def lines(info: dict) -> list[str]:
    """What the style did to this plant, in words (the report, the export's reply, GLB extras)."""
    m = info["match"]
    out = [f"style {info['style']}: {info['limbs_kept']} limbs kept of {info['limbs']} first-order ({info['axes_kept']} of "
           f"{info['axes']} axes drawn, {info['wood_m']} of {info['wood_m_grown']} m of wood; no twigs)"
           + (f"; {info['masses']} crown masses for {info['twigs']} twigs" if info["masses"] else "; no crown masses")
           + (f", {info.get('tones', 0)} tones" if info.get("tones") else "")]
    out.append(f"same individual: outline IoU {m['iou']} against the realistic tree in leaf (true scale, feet together; azimuths "
               f"{'/'.join(str(a) for a in m['azimuths'])}: {'/'.join(f'{v:.2f}' for v in m['iou_by_azimuth'])}); height "
               f"{m['height_m'][1]} m (realistic {m['height_m'][0]}), crown width {m['width_m'][1]} m (realistic {m['width_m'][0]})")
    if info.get("masses_tried"):
        out.append("masses tried (count: IoU at a coarse voxel): " + ", ".join(f"{k}: {v:.3f}" for k, v in sorted(info["masses_tried"].items())))
    return out


def warnings(info: dict) -> list[str]:
    m = info["match"]
    w = []
    if m["iou"] < 0.8:
        w.append(f"WARNING: the {info['style']} tree's outline is only {m['iou']} IoU of the realistic one: at a distance it is not "
                 f"the same tree (style.crown.spread / pad / masses)")
    if abs(m["height_m"][1] - m["height_m"][0]) > 0.06 * m["height_m"][0]:
        w.append(f"WARNING: the styled tree is {m['height_m'][1]} m tall, the realistic one {m['height_m'][0]} m")
    return w
