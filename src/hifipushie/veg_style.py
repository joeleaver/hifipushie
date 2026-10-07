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
    con = out.pop("conifer", None)
    if con and conifer(spec):  # the sheet's own numbers for needle trees (tiers, a bare pole), under the spec's overrides
        out = vegetation._merge(vegetation._merge(out, con), {k: v for k, v in over.items() if k != "conifer"})
        out = vegetation._merge(out, over.get("conifer") or {})
    out["name"] = name
    return out


def conifer(spec: dict) -> bool:
    return str((spec.get("leaves") or {}).get("shape", "")).startswith("needle")


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


def material_color(rgb, st: dict) -> list:
    """The crown material's LINEAR colour factor: the season's colour x the tones' gain, scaled back as a whole when a
    channel would pass 1 (clipped per channel, autumn's orange lost its tone steps and its hue)."""
    c = np.array(lin(rgb)) * color_gain(st)
    return (c / max(1.0, float(c.max()))).tolist()


def bark_color(spec: dict, st: dict) -> list:
    co = st.get("colour") or {}
    return styled((spec.get("bark") or {}).get("color", [0.5, 0.45, 0.4]), co.get("bark_saturation", 1.0), co.get("bark_value", 1.0))


# ---------------------------------------------------------------- wood: the limbs that are drawn
def wood(tree: dict, st: dict, inside=None, size: float = 0.0) -> dict:
    """A small tree of the drawn wood only: the trunk's axis, the stoutest first-order limbs and, INSIDE the crown, a
    few branches off each (`stubs`: the stoutest forks, `stub_apart` m apart; each runs into the crown and ends in a
    mass like a limb: what is left standing when the plant is bare). Fattened, bends smoothed.
    The same keys veg_mesh.tubes and veg_export.wind_nodes read; `src` = each node's node in the grown tree; `info` =
    what was left out.
    inside: points -> depth inside the crown (m, positive inside): a limb runs on inside the crown while it stays
    `keep_in` m deep (to `reach_in` of its length), so it ends in a mass, never in the air or out the far side; one
    that never gets `bury` m deep ends where it is deepest. size: the crown masses' mean radius (m): a limb's base
    is at least `limb_mass` x it (toy proportions: a limb as fat as what it carries, not as the pipe model says)."""
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

    def length(nodes):
        return np.cumsum(np.linalg.norm(np.diff(np.vstack([P[par[nodes[0]]], P[nodes]]), axis=0), axis=1))

    def cut(nodes, share, least=0):
        cum = length(nodes)
        k = int(np.searchsorted(cum, share * cum[-1])) + 1
        return nodes[: max(min(k, len(nodes)), least, 2)]

    def within(full, share, entered=False, keep=None, must=False):
        """The part of a path drawn: to where it leaves the crown again after entering it."""
        if inside is None:
            return cut(full, float(w.get("reach", 1.0)))
        dep = inside(P[full])
        cum = length(full)
        ins = np.flatnonzero(dep > 0)
        if len(ins) and not entered:  # it stops for good where it first comes out of the crown again (a limb that
            out_ = np.flatnonzero(dep[ins[0]:] < 0)  # crossed a shallow lobe and went on showed as a stick in the air between two masses)
            if len(out_):
                full, dep, cum = full[: ins[0] + out_[0]], dep[: ins[0] + out_[0]], cum[: ins[0] + out_[0]]
        deep = np.flatnonzero(dep >= float(w.get("bury", 0.8)))
        if not len(deep) and not entered:
            if must and float(dep.max()) < float(w.get("keep_in", 0.5)):
                return full[:0]  # (a fork that never gets into the crown is not drawn: its end would stand in the air)
            return full[: max(int(np.argmax(dep)) + 1, 2)]
        i = 0 if entered else int(deep[0])
        end = i
        while end + 1 < len(full) and dep[end + 1] >= (float(w.get("keep_in", 0.5)) if keep is None else keep) and cum[end + 1] <= share * cum[-1]:
            end += 1
        return full[: max(end + 1, 2)]

    top_base = max([tpos[int(par[tree["axes"][L["axis"]]["node"]])] for L in kept], default=0)
    tn = cut(trunk, float(w.get("trunk_reach", 1.0)), top_base + 2)
    r_ref = float(rad[tn[min(len(tn) - 1, max(1, len(tn) // 5))]])
    r_ref = max(r_ref, float(w.get("trunk_mass", 0.0)) * size / fat)  # (a trunk as stout as the crown it carries)
    tfloor = float(w.get("trunk_floor", floor))
    foot = float(w.get("foot", 1.25))  # the root flare, at most this x the trunk (the grown flare made the trunk a cone)
    trad = lambda r_: fat * np.clip(r_, tfloor * r_ref, foot * r_ref)
    pos, parent, radius, axis, order, src = [P[0]], [0], [float(trad(rad[0]))], [0], [0], [0]
    index = {}

    def smooth(pts, r_end=0.0):
        pts = pts.copy()
        for _ in range(int(w.get("smooth", 0))):
            pts[1:-1] = 0.5 * pts[1:-1] + 0.25 * (pts[:-2] + pts[2:])
        if inside is not None and r_end and len(pts) > 2:
            # the end goes under the crown's surface by its own girth: one that lay shallower (a limb running along
            # under a mass, entering only at its tip) showed past the crown from the side. The last 40% bends with it.
            e = pts[-1].copy()
            need = r_end + float(w.get("keep_in", 0.5))
            for _ in range(6):
                dep = float(inside(e[None])[0])
                if dep >= need:
                    break
                g = grad(inside, e[None])[0]
                e = e + g / max(float(np.linalg.norm(g)), 1e-9) * min(need - dep, 1.0)
            t = np.clip((np.linspace(0, 1, len(pts)) - 0.6) / 0.4, 0, 1)
            pts = pts + (t * t * (3 - 2 * t))[:, None] * (e - pts[-1])
        return pts

    def add(nodes, root, pts, rr, ai, od):
        prev = root
        for n, p_, r_ in zip(nodes, pts, rr):
            index[int(n)] = len(pos)
            pos.append(p_)
            parent.append(prev)
            radius.append(float(r_))
            axis.append(ai)
            order.append(od)
            src.append(int(n))
            prev = len(pos) - 1

    tp = smooth(np.vstack([P[0], P[tn]]))[1:]
    add(tn, 0, tp, trad(rad[tn]), 0, 0)
    drawn = [np.vstack([P[0], P[tn]])]
    n_ax, n_stub = 1, 0
    for L in kept:
        n0 = tree["axes"][L["axis"]]["node"]
        full = vegetation.stout_path(tree, n0, kids)
        root = index[int(par[n0])]
        r0 = max(fat * float(rad[n0]), float(w.get("limb_min", 0.0)) * fat * r_ref, float(w.get("limb_mass", 0.0)) * size)
        r0 = min(r0, 0.8 * radius[root])
        # (inside the crown its axis stays its own girth + keep_in under the surface: 0.5 m down, a 0.5 m limb showed through)
        nodes = within(full, float(w.get("reach_in", 0.9)), keep=float(w.get("keep_in", 0.5)) + floor * r0)
        pts = smooth(np.vstack([pos[root], P[nodes]]), floor * r0)[1:]
        rr = np.maximum(r0 * rad[nodes] / max(float(rad[n0]), 1e-9), floor * r0)
        add(nodes, root, pts, rr, n_ax, 1)
        n_ax += 1
        drawn.append(np.vstack([pos[root], pts]))
        if inside is None or not w.get("stubs"):
            continue
        # stubby branches off this limb, inside the crown: the stoutest side branches whose foot is in a mass
        on = set(int(q) for q in nodes)
        sides = []
        for q in nodes[1:]:
            for c in kids.get(int(q), ()):
                if c not in on and rad[c] >= 0.15 * rad[q]:
                    sides.append((float(rad[c]), int(c)))
        sides.sort(reverse=True)
        took = []
        for _, c in sides:
            if len(took) >= int(w["stubs"]):
                break
            if any(np.linalg.norm(P[c] - P[t_]) < float(w.get("stub_apart", 1.5)) for t_ in took):
                continue
            sroot = index[int(par[c])]
            sr0 = min(max(fat * float(rad[c]), float(w.get("stub_radius", 0.6)) * radius[sroot]), 0.8 * radius[sroot])
            sn = within(vegetation.stout_path(tree, c, kids), float(w.get("stub_reach", 0.6)), must=True,
                        keep=float(w.get("keep_in", 0.5)) + floor * sr0)  # (as a limb: on into the crown, ending in a mass)
            if len(sn) < 2 or length(sn)[-1] < float(w.get("stub_min", 1.0)):
                continue
            took.append(c)
            spts = smooth(np.vstack([pos[sroot], P[sn]]), floor * sr0)[1:]
            add(sn, sroot, spts, np.maximum(sr0 * rad[sn] / max(float(rad[c]), 1e-9), floor * sr0), n_ax, 2)
            n_ax += 1
            n_stub += 1
            drawn.append(np.vstack([pos[sroot], spts]))
    src = np.array(src)
    drawn_len = float(sum(np.linalg.norm(np.diff(d_, axis=0), axis=1).sum() for d_ in drawn))
    total_len = float(np.linalg.norm(P - P[par], axis=1).sum())
    return {"pos": np.array(pos), "parent": np.array(parent), "radius": np.array(radius), "axis": np.array(axis),
            "order": np.array(order), "ends": np.zeros(len(pos), bool), "key": tree["key"][src], "height": tree["height"],
            "spec": tree["spec"], "dead": None, "src": src,
            "info": {"limbs_kept": len(kept), "limbs": len(allL), "axes": int(len(tree["axes"])), "axes_kept": n_ax, "stubs": n_stub,
                     "wood_m": round(drawn_len, 1), "wood_m_grown": round(total_len, 1),
                     "limb_names": [L["name"] for L in kept]}}


def wood_tubes(mini: dict, st: dict, f: float = 1.0) -> dict:
    """The drawn wood as plain tubes (quick: what the fit's silhouettes use)."""
    lo, hi = st["wood"].get("sides", [6, 12])
    sides = (max(3, int(round(lo * f))), max(4, int(round(hi * f))))
    return veg_mesh.tubes(mini, sides=sides, simplify=0.25 / max(f, 0.2), tip=1.0, tile=(0.5, 1.0))


def _segments(mini: dict, orders=(0, 1, 2)) -> list:
    """Per axis of those orders: (a, b, ra, rb, node of b) for its segments, with the foot run 0.3 m into the ground."""
    out = []
    for ai in np.unique(mini["axis"]):
        if mini["order"][np.flatnonzero(mini["axis"] == ai)[-1]] not in orders:
            continue
        nodes = np.flatnonzero(mini["axis"] == ai)
        nodes = nodes[nodes >= 1]
        par = mini["parent"][nodes]
        a, b = mini["pos"][par].copy(), mini["pos"][nodes]
        ra, rb = mini["radius"][par].copy(), mini["radius"][nodes]
        if ai != mini["axis"][1]:
            ra[0] = rb[0]  # (a branch starts at its own girth, on its parent's axis: the union makes the fork)
        else:
            a[0] = a[0] - [0, 0, 0.3]
        out.append((a, b, ra, rb, nodes))
    return out


def wood_field(segs: list, p: np.ndarray, blend: float, node: bool = False):
    """The drawn wood as one field: each axis a chain of round cones (hard union along it: a smooth one bulged at every
    joint), the axes joined by a smooth union of `blend` x the branch's girth: forks are fillets, ends are round.
    node=True also returns the nearest segment's end node per point."""
    d = np.full(len(p), 1e3)
    nn = np.zeros(len(p), np.int64)
    for a, b, ra, rb, nodes in segs:
        k = blend * float(rb[0])
        lo, hi = np.minimum(a, b).min(0) - ra.max() - k - 0.3, np.maximum(a, b).max(0) + ra.max() + k + 0.3
        m = np.flatnonzero(((p >= lo) & (p <= hi)).all(1))
        if not len(m):
            continue
        da = np.full(len(m), 1e3)
        na = np.zeros(len(m), np.int64)
        for i in range(len(a)):
            ab = b[i] - a[i]
            t = np.clip((p[m] - a[i]) @ ab / max(float(ab @ ab), 1e-12), 0, 1)
            di = np.linalg.norm(p[m] - (a[i] + t[:, None] * ab), axis=1) - (ra[i] + t * (rb[i] - ra[i]))
            better = di < da
            da = np.where(better, di, da)
            na = np.where(better, nodes[i], na)
        nn[m] = np.where(da < d[m], na, nn[m])
        d[m] = sdf.smin(d[m], da, k)
    return (d, nn) if node else d


def mesh_field(fn, lo, hi, voxel: float) -> tuple:
    """Marching cubes of a field over a box: (V, F) with faces outward (the field is negative inside)."""
    from skimage import measure
    C = 4  # a coarse pass first: the field is only evaluated exactly in coarse cells the surface can reach
    nc = [int(np.ceil((hi[i] - lo[i] + 3 * voxel) / (C * voxel))) + 1 for i in range(3)]
    cax = [lo[i] - voxel + (np.arange(nc[i]) + 0.5) * C * voxel - 0.5 * voxel for i in range(3)]
    Gc = np.stack(np.meshgrid(*cax, indexing="ij"), -1).reshape(-1, 3)
    vc = np.concatenate([fn(Gc[i: i + 400000]) for i in range(0, len(Gc), 400000)]).reshape(nc)
    vol = np.repeat(np.repeat(np.repeat(vc, C, 0), C, 1), C, 2)
    ax = [lo[i] - voxel + np.arange(nc[i] * C) * voxel for i in range(3)]
    near = np.argwhere(np.abs(vol) < 1.6 * C * voxel)  # (fields here are steeper than a distance by at most ~1.3)
    Gn = np.stack([ax[i][near[:, i]] for i in range(3)], 1)
    vol[near[:, 0], near[:, 1], near[:, 2]] = np.concatenate([fn(Gn[i: i + 400000]) for i in range(0, len(Gn), 400000)]) if len(Gn) else []
    V, F, _, _ = measure.marching_cubes(vol, 0.0, spacing=(voxel,) * 3)
    V = V + [ax[0][0], ax[1][0], ax[2][0]]
    pick = np.arange(0, len(F), max(1, len(F) // 500))
    fn_ = np.cross(V[F[pick, 1]] - V[F[pick, 0]], V[F[pick, 2]] - V[F[pick, 0]])
    if (np.einsum("ij,ij->i", fn_, grad(fn, V[F[pick]].mean(1))) < 0).mean() > 0.5:
        F = F[:, ::-1]
    return V, np.ascontiguousarray(F)


def grad(fn, p, h=0.02):
    g = np.empty_like(p)
    for a in range(3):
        e = np.zeros(3)
        e[a] = h
        g[:, a] = fn(p + e) - fn(p - e)
    return g / (2 * h)


def onto(fn, V, steps: int = 2):
    """Vertices back onto a field's surface (decimation pulls a rounded surface in), and its normals there."""
    for _ in range(steps):
        g = grad(fn, V)
        V = V - g * (fn(V) / np.maximum((g * g).sum(1), 1e-9))[:, None]
    g = grad(fn, V)
    return V, g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)


def wood_dense(mini: dict, st: dict, orders=(0, 1)) -> dict | None:
    """The drawn wood of those orders meshed from its field, at full resolution. Trunk and limbs are one mesh; the forks
    (order 2: drawn only when the plant is bare) another, each fork starting inside its limb."""
    segs = _segments(mini, orders)
    if not segs:
        return None
    blend = float(st["wood"].get("blend", 0.6))
    fn = lambda q: np.maximum(wood_field(segs, q, blend), -0.3 - q[:, 2])  # (cut flat 0.3 m under the foot)
    rmin = float(min(rb.min() for _, _, _, rb, _ in segs))
    voxel = float(st["wood"].get("voxel") or np.clip(0.4 * rmin, 0.05, 0.12))
    r = float(mini["radius"].max())
    V, F = mesh_field(fn, mini["pos"].min(0) - r - 0.4, mini["pos"].max(0) + r + 0.2, voxel)
    return {"V": V, "F": F, "segs": segs, "blend": blend, "voxel": voxel, "axes": len(segs)}


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
def in_leaf(tree: dict) -> dict:
    """The same tree in summer: a style is fitted to the plant in leaf whatever season it is shown in (a winter tree
    has no twigs to fit masses to, and its limbs must still be the summer tree's)."""
    if tree["spec"].get("season", "summer") == "summer":
        return tree
    return {**tree, "spec": {**tree["spec"], "season": "summer"}}


def leaf_points(tree: dict) -> tuple[np.ndarray, float]:
    """Where the foliage is: the middle of every living twig, and the twig's length (m)."""
    tree = in_leaf(tree)
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


def masses(X: np.ndarray, k: int, st: dict, twig: float, seed: int = 0) -> list[dict]:
    """k ellipsoids over the foliage points: [{"c", "R" (rows = axes), "r" (semi-axes), "n" points}], lowest first."""
    cr = st["crown"]
    ztop = float(X[:, 2].max()) + 0.5 * twig
    if cr.get("kind") == "tiers":
        # stacked dumplings: one upright egg per height band (round above its widest level, flat below it: `tier_under`
        # x the band), seated low in its band, so each overhangs the narrower top of the one below with an undercut.
        # `trunk_show` m of trunk stay bare under the lowest; bands differ in height by `tier_uneven` (the seed's own
        # numbers); the top one is a cap no slimmer than `tier_cap` x its height.
        show = float(cr.get("trunk_show", 0.0))
        z0, z1 = max(float(np.percentile(X[:, 2], 1)), show), float(X[:, 2].max())
        un = float(cr.get("tier_uneven", 0.0))
        jit = (vegetation._u(np.arange(3 * k + 3).astype(np.uint64) + np.uint64(1000 * (seed + 1)), 91) - 0.5) * 2 if un else np.zeros(3 * k + 3)
        frac = (np.arange(k + 1) / k) ** float(cr.get("tier_power", 1.0))
        frac[1:-1] += 0.5 * un * jit[1:k] * np.diff(frac).min()
        edges = z0 + (z1 - z0) * frac
        out = []
        for j in range(k):
            hgt = edges[j + 1] - edges[j]
            Q = X[(X[:, 2] >= edges[j] - 1e-9) & (X[:, 2] <= edges[j] + 0.6 * hgt)]  # (its width is its lower part's: the band's top is the next one's business)
            if len(Q) < 4:
                Q = X[(X[:, 2] >= edges[j] - 1e-9) & (X[:, 2] <= edges[j + 1] + 1e-9)]
            if len(Q) < 4:
                continue
            c = np.array([Q[:, 0].mean(), Q[:, 1].mean(), edges[j] + float(cr.get("tier_seat", 0.4)) * hgt])
            wj = 1.0 + 0.35 * un * jit[k + 1 + j]
            rx, ry = [wj * float(cr.get("spread", 1.75)) * float(Q[:, i].std()) + float(cr.get("pad", 0.5)) * twig for i in (0, 1)]
            rz = max(float(cr.get("tier_height", 0.75)) * hgt, float(cr.get("roundness", 0.0)) * max(rx, ry) * 0.5)
            if j == k - 1:
                rz = max(ztop - c[2], 0.3 * hgt)
                rx, ry = [max(v, float(cr.get("tier_cap", 0.0)) * rz) for v in (rx, ry)]
            r = np.maximum(np.array([rx, ry, rz]), 0.75 * float(cr.get("min_feature", 0.6)))
            c[2] -= max(0.0, c[2] + r[2] - ztop)
            e = {"c": c, "R": np.eye(3), "r": r, "n": int(len(Q))}
            if cr.get("tier_under") is not None:
                e["down"] = float(np.clip(float(cr["tier_under"]) * hgt, 0.3 * float(cr.get("min_feature", 0.6)), max(c[2] - show, 0.05) if j == 0 else 1e9))
            out.append(e)
        return out
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
    if cr.get("core") and len(out) > 1:  # the foliage is a shell: a mass in its hollow makes the crown one body with lobes
        c = X.mean(0)
        ev, U = np.linalg.eigh(np.cov((X - c).T) + np.eye(3) * 1e-6)
        r = float(cr["core"]) * np.sqrt(np.maximum(ev, 0))
        r = np.maximum(r, float(cr.get("roundness", 0.0)) * r.max())
        ez = math.sqrt(float(((U.T[:, 2] * r) ** 2).sum()))
        c[2] -= max(0.0, c[2] + ez - ztop)
        out.append({"c": c, "R": U.T.copy(), "r": r, "n": 0, "core": True})
    return out


def blend_of(ells: list[dict], st: dict) -> float:
    """The crown union's smoothing radius (m): `blend`, or `blend_share` x the masses' mean radius when that is more
    (a fixed 1 m between 5 m masses left eight balloons)."""
    cr = st["crown"]
    size = float(np.mean([e["r"].mean() for e in ells if not e.get("core")])) if ells else 0.0
    return max(float(cr.get("blend", 0.5)), float(cr.get("blend_share", 0.0)) * size)


def field(ells: list[dict], p: np.ndarray, blend: float, each: bool = False, floor: float | None = None):
    """The crown's field at points (negative inside): the ellipsoids' (approximate) distances under a smooth union.
    each=True also returns the (n, k) distances. floor: nothing under this height."""
    D = np.empty((len(p), len(ells)))
    for j, e in enumerate(ells):
        q = (p - e["c"]) @ e["R"].T
        r_ = e["r"]
        if e.get("down") is not None:  # an egg: its own (shorter) semi-axis below the middle
            r_ = np.tile(e["r"], (len(q), 1))
            r_[q[:, 2] < 0, 2] = e["down"]
        k0 = np.linalg.norm(q / r_, axis=1)
        k1 = np.linalg.norm(q / (r_ ** 2), axis=1)
        D[:, j] = np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -float(e["r"].min()))
    d = D[:, 0].copy()
    for j in range(1, len(ells)):
        d = sdf.smin(d, D[:, j], blend)
    if floor is not None:
        d = np.maximum(d, floor - p[:, 2])
    return (d, D) if each else d


def _gradient_old(ells, p, blend, floor, h=0.02):
    g = np.empty_like(p)
    for a in range(3):
        e = np.zeros(3)
        e[a] = h
        g[:, a] = field(ells, p + e, blend, floor=floor) - field(ells, p - e, blend, floor=floor)
    return g / (2 * h)


def crown_mesh(ells: list[dict], st: dict, voxel: float | None = None, floor: float | None = None) -> dict:
    """The masses as one closed surface: marching cubes of the field ({"V", "F"}, outward)."""
    cr = st["crown"]
    blend = blend_of(ells, st)
    lo = np.min([e["c"] - e["r"].max() for e in ells], axis=0) - blend
    hi = np.max([e["c"] + e["r"].max() for e in ells], axis=0) + blend
    voxel = voxel or float(cr.get("voxel") or 0) or float(np.clip((hi - lo).max() / 80, 0.06, 0.3))
    V, F = mesh_field(lambda q: field(ells, q, blend, floor=floor), lo, hi, voxel)
    return {"V": V, "F": F, "voxel": voxel, "blend": blend}


def color_gain(st: dict) -> float:
    """What the crown material's colour is multiplied by (COLOR_0 holds each mass's tone divided by it)."""
    cr = st.get("crown") or {}
    return float(max(cr.get("tone", [0.85, 1.15])) * (1 + abs(float(cr.get("warm_top", 0.0)))))


def _decimate(V, F, target: int):
    if len(F) <= target:
        return V, F
    import pyfqmr
    for agg in (5, 7, 9):  # (at 5 a long smooth pole stalled at 2.4x its target)
        s = pyfqmr.Simplify()
        s.setMesh(np.ascontiguousarray(V, np.float64), np.ascontiguousarray(F, np.int32))
        s.simplify_mesh(target_count=int(target), aggressiveness=agg, preserve_border=True, verbose=False)
        V2, F2, _ = s.getMesh()
        V, F = np.asarray(V2, float), np.asarray(F2, np.int64)
        if len(F) <= 1.08 * target:
            break
    return V, F


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
    return [vegetation.silhouette(in_leaf(tree), az, px, leaves=True, pad=3.0) for az in azimuths]


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
    """The styled plant's parts before any budget: {"mini": the drawn wood, "wood": its dense mesh, "ells": the
    crown's masses (or []), "dense": the crown at full resolution, "match": compare()'s numbers, "tried": IoU per
    number of masses}."""
    key = hashlib.sha1(json.dumps(st, sort_keys=True).encode()).hexdigest()
    hit = _FIT.get(id(tree))
    if hit is not None and hit[0] is tree and hit[1] == key:
        return hit[2]
    mini = wood(tree, st)
    Wm = wood_tubes(mini, st)
    wm = (Wm["V"], Wm["F"])
    X, tl = leaf_points(tree)
    out = {"mini": mini, "ells": [], "dense": None, "tried": {}, "twigs": int(len(X)), "blend": 0.0}
    floor = float(tree["spec"]["leaves"].get("clear", 0.03)) + 0.02
    refs = reference(tree)
    cr = st.get("crown") or {}
    if cr.get("kind") == "tiers" and cr.get("trunk_show"):
        floor = max(floor, 0.6 * float(cr["trunk_show"]))  # (the union's blend may sag under the lowest tier: never to the ground)
    if len(X) >= 8 and cr.get("kind", "masses") in ("masses", "tiers"):
        lo, hi = (cr["masses"], cr["masses"]) if isinstance(cr["masses"], int) else cr["masses"]
        cands = {}
        for k in range(int(lo), int(hi) + 1):
            ells = masses(X, k, st, tl, int(tree["spec"].get("seed", 1)))
            n_ = sum(not e.get("core") for e in ells)
            if not ells or n_ in cands:
                continue
            cm = crown_mesh(ells, st, voxel=None if lo == hi else 0.3, floor=floor)
            cands[n_] = (ells, compare(tree, [wm, (cm["V"], cm["F"])], refs=refs)["iou"])
        best = max(v[1] for v in cands.values())
        k = min(k_ for k_, v in cands.items() if v[1] >= best - 0.01)
        out["tried"] = {k_: v[1] for k_, v in cands.items()}
        ells = out["ells"] = cands[k][0]
        out["dense"] = crown_mesh(ells, st, floor=floor)
        out["floor"] = floor
        out["blend"] = bl = out["dense"]["blend"]
        size = float(np.mean([e["r"].mean() for e in ells if not e.get("core")]))
        mini = out["mini"] = wood(tree, st, lambda q: -field(ells, q, bl, floor=floor), size)
    out["wood"] = wood_dense(mini, st)
    out["forks"] = wood_dense(mini, st, (2,))
    out["match"] = compare(tree, [(out["wood"]["V"], out["wood"]["F"])] + ([(out["dense"]["V"], out["dense"]["F"])] if out["dense"] else []), refs=refs)
    if len(_FIT) > 6:
        _FIT.clear()
    _FIT[id(tree)] = (tree, key, out)
    return out


def dress(tree: dict, st: dict, triangles: int | None = None, season: str = "summer") -> dict:
    """The plant in its style within a triangle count (default the sheet's `budget`): {"wood": {"V", "F", "N", "uv",
    "node"...}, "wood_wind": (trunk, branch, phase, flutter) per wood vertex, "crown": None | {"V", "F", "N", "uv",
    "col" (n, 3 multiplier), "wind", "mass"}, "mini", "info"}. A lower count takes triangles off the same two
    surfaces: the masses and the limbs themselves never change with the LOD."""
    from . import veg_export
    ft = fit(tree, st)
    full = int(st.get("budget", 5000))
    triangles = int(triangles or full)
    mini = ft["mini"]
    share = float(st["wood"].get("share", 0.25)) if ft["ells"] else 1.0
    wd_ = ft["wood"]
    wfn = lambda q: np.maximum(wood_field(wd_["segs"], q, wd_["blend"]), -0.3 - q[:, 2])
    wn = veg_export.wind_nodes(mini)

    def surface(dn, target):
        fn_ = wfn if dn is wd_ else (lambda q: wood_field(dn["segs"], q, dn["blend"]))
        V_, F_ = _decimate(dn["V"], dn["F"], max(int(target), 12 * dn["axes"]))
        V_, N_ = onto(fn_, V_)
        nd_ = wood_field(dn["segs"], V_, dn["blend"], node=True)[1]
        z_ = np.zeros(len(V_))
        return {"V": V_, "F": F_, "N": N_, "uv": np.zeros((len(V_), 2)), "node": nd_, "tan": np.tile([0, 0, 1.0], (len(V_), 1)),
                "radius": mini["radius"][nd_], "dead": z_,
                "wind": (np.clip(V_[:, 2] / max(tree["height"], 1e-6), 0, 1) ** 1.5, wn["branch"][nd_], wn["phase"][nd_], z_)}

    W = surface(wd_, share * triangles)
    Vw, Fw = W["V"], W["F"]
    out = {"wood": W, "wood_wind": W["wind"], "crown": None, "mini": mini, "forks": None}
    if ft.get("forks") is not None and not evergreen(tree["spec"]):
        # the limbs' forks: drawn only when the plant is bare (in leaf they cluttered the crown's underside), within
        # what the hidden crown's triangles would have cost
        out["forks"] = surface(ft["forks"], float(st["wood"].get("forks_share", 0.3)) * triangles)
    info = {"style": st["name"], **mini["info"], "masses": sum(not e.get("core") for e in ft["ells"]), "core": any(e.get("core") for e in ft["ells"]),
            "blend_m": round(ft["blend"], 2), "twigs": ft["twigs"], "match": ft["match"],
            "masses_tried": ft["tried"], "wood_triangles": int(len(Fw)), "crown_triangles": 0, "budget": triangles,
            "forks_triangles": int(len(out["forks"]["F"])) if out["forks"] else 0, "kind": (st.get("crown") or {}).get("kind", "masses")}
    if ft["ells"] and season_color(tree["spec"], season, st) is not None:
        cr, ells = st["crown"], ft["ells"]
        blend = ft["blend"]
        cfn = lambda q: field(ells, q, blend, floor=ft["floor"])
        V, F = _decimate(ft["dense"]["V"], ft["dense"]["F"], max(triangles - len(Fw), 16 * len(ells)))
        V, N = onto(cfn, V)
        d, D = field(ells, V, blend, each=True, floor=ft["floor"])
        cen = np.mean([e["c"] for e in ells], axis=0)
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
        ed = np.array([e["down"] if e.get("down") is not None else ez[j] for j, e in enumerate(ells)])
        u = np.clip((V[:, 2] - (cz[mass] - ed[mass])) / (ez[mass] + ed[mass]), 0, 1)
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
        info["mass_list"] = [{"center": e["c"].round(2).tolist(), "radii": np.sort(e["r"])[::-1].round(2).tolist(), "tone": int(ti[j]),
                              **({"core": True} if e.get("core") else {})} for j, e in enumerate(ells)]
    info["triangles"] = info["wood_triangles"] + info["crown_triangles"]
    out["info"] = info
    return out


def lines(info: dict) -> list[str]:
    """What the style did to this plant, in words (the report, the export's reply, GLB extras)."""
    m = info["match"]
    out = [f"style {info['style']}: {info['limbs_kept']} limbs kept of {info['limbs']} first-order + {info.get('stubs', 0)} of their forks (shown only when bare: {info.get('forks_triangles', 0)} triangles) "
           f"({info['axes_kept']} of {info['axes']} axes drawn, {info['wood_m']} of {info['wood_m_grown']} m of wood; no twigs)"
           + (f"; {info['masses']} crown {'tiers' if info.get('kind') == 'tiers' else 'masses'}" + (" + a core" if info.get("core") else "") + f" joined over {info.get('blend_m', 0)} m, for {info['twigs']} twigs"
              if info["masses"] else "; no crown masses")
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
