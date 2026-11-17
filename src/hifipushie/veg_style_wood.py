"""Wood: the limbs that are drawn, their tubes and field, meshing a field, capsules. Part of the plant styles (veg_style.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import veg_mesh
from . import veg_style
from . import sdf_shapes
from . import vegetation_kernels, vegetation_tree

# ---------------------------------------------------------------- wood: the limbs that are drawn
def wood(tree: dict, st: dict, inside=None, size: float = 0.0, feed=None) -> dict:
    """A small tree of the drawn wood only: the trunk's axis, the stoutest first-order limbs and, INSIDE the crown, a
    few branches off each (`stubs`: the stoutest forks, `stub_apart` m apart; each runs into the crown and ends in a
    mass like a limb: what is left standing when the plant is bare). Fattened, bends smoothed.
    The same keys veg_mesh.tubes and veg_export_parts.wind_nodes read; `src` = each node's node in the grown tree; `info` =
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
    allL = vegetation_tree.limbs(tree, 400, 0.0)
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
    tr = trad(rad[tn])
    zc = float(P[trunk[top_base], 2]) if kept else 0.35 * float(tree["height"])  # the crown's base on the trunk
    zt = max(float(tp[-1, 2]), 1e-3)
    if w.get("s_bend"):  # cartoon: one S along the bare trunk, `s_bend` x its height out and back (0 at the foot and the crown)
        ang = 2 * math.pi * float(vegetation_kernels._u(np.array([int(tree["spec"].get("seed", 1)) + 11], np.uint64), 99)[0])
        dvec = np.array([math.cos(ang), math.sin(ang), 0.0])
        zz = np.clip(tp[:, 2] / max(zc, 1e-3), 0, 1)
        tp = tp + (float(w["s_bend"]) * zc * np.sin(2 * math.pi * zz))[:, None] * dvec[None]
    tn_ = tn
    if w.get("taper") or w.get("flare"):  # cartoon: thick at the foot, thin at the top, a flared root foot
        # the flare: a concave root foot `flare_height` trunk diameters tall ((1 - s)^2.5: it rises steeply off the ground
        # and runs into the trunk; an exponential over 12% of the bole read as a mound). The trunk's first stretch is
        # resampled finely enough to carry the curve.
        fh = float(w.get("flare_height", 1.25)) * 2 * fat * r_ref  # (in trunk diameters: the bole's own girth, not the flared foot's)
        if w.get("flare") and fh > 0:
            seg = np.vstack([P[0], tp])
            zs_ = seg[:, 2]
            k_ = int(np.searchsorted(zs_, fh)) + 1
            new_p, new_n, new_r = [], [], []
            for j in range(1, len(seg)):
                a_, b_ = seg[j - 1], seg[j]
                if j <= k_:
                    m_ = int(max(1, math.ceil(np.linalg.norm(b_ - a_) / max(fh / 5, 0.05))))
                    for q in range(1, m_):
                        new_p.append(a_ + (b_ - a_) * q / m_); new_n.append(tn[j - 1]); new_r.append(float(tr[j - 1]))
                new_p.append(b_); new_n.append(tn[j - 1]); new_r.append(float(tr[j - 1]))
            tp, tn_, tr = np.array(new_p), np.array(new_n), np.array(new_r)
        z_ = np.clip(tp[:, 2], 0, None)
        if w.get("flare"):  # (the grown root swelling goes: the drawn flare replaces it)
            above = np.flatnonzero(z_ >= fh)
            if len(above):
                tr = np.where(z_ < fh, np.minimum(tr, tr[above[0]]), tr)
        tf_ = lambda zz: (1 + float(w.get("taper", 0.0)) * (1 - zz / zt)) * (1 + float(w.get("flare", 0.0)) * (1 - np.clip(zz / max(fh, 1e-3), 0, 1)) ** 2.5)
        tr = tr * tf_(z_)
    add(tn_, 0, tp, tr, 0, 0)
    if w.get("taper") or w.get("flare"):
        # the foot node goes UNDER the ground, as wide as the flare carried on down: a round cone ends in a sphere, and a
        # sphere centred on the ground reads as a bulb / mound; this way the flare meets the ground still widening
        dz = 0.3
        r1 = float(tr[0]) / float(tf_(np.array([max(float(tp[0, 2]), 1e-3)]))[0])
        slope = (float(tr[0]) - r1 * float(tf_(np.array([0.0]))[0])) / max(float(tp[0, 2]), 1e-3)
        r_g = r1 * float(tf_(np.array([0.0]))[0])
        pos[0] = P[0] - np.array([0, 0, dz])
        radius[0] = float(r_g + max(-slope, 0.0) * dz)
    drawn = [np.vstack([P[0], P[tn]])]
    n_ax, n_stub = 1, 0
    for L in kept:
        n0 = tree["axes"][L["axis"]]["node"]
        full = vegetation_tree.stout_path(tree, n0, kids)
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
            sn = within(vegetation_tree.stout_path(tree, c, kids), float(w.get("stub_reach", 0.6)), must=True,
                        keep=float(w.get("keep_in", 0.5)) + floor * sr0)  # (as a limb: on into the crown, ending in a mass)
            if len(sn) < 2 or length(sn)[-1] < float(w.get("stub_min", 1.0)):
                continue
            took.append(c)
            spts = smooth(np.vstack([pos[sroot], P[sn]]), floor * sr0)[1:]
            add(sn, sroot, spts, np.maximum(sr0 * rad[sn] / max(float(rad[c]), 1e-9), floor * sr0), n_ax, 2)
            n_ax += 1
            n_stub += 1
            drawn.append(np.vstack([pos[sroot], spts]))
    n_fed = 0
    if feed is not None and len(feed) and w.get("feed"):
        # every clump is carried: a clump with no drawn wood within `feed` x its radius gets the grown tree's own path
        # to it (from the nearest grown node in it back down to the drawn wood). Without it outer clumps floated.
        fr = float(w["feed"])
        for c, rc in feed:
            if np.linalg.norm(np.array(pos) - c, axis=1).min() <= fr * rc:
                continue
            near = np.flatnonzero(np.linalg.norm(P - c, axis=1) < 0.7 * rc)
            if not len(near):
                continue
            n = int(near[np.argmax(rad[near])])  # (its stoutest wood: the branch that carries it)
            path = []
            while n not in index and n > 0:
                path.append(n)
                n = int(par[n])
            if n not in index or not path:
                continue
            path = np.array(path[::-1])
            root = index[n]
            fr0 = min(max(fat * float(rad[path[0]]), float(w.get("feed_radius", 0.0)) * radius[root]), 0.8 * radius[root])
            fpts = smooth(np.vstack([pos[root], P[path]]))[1:]
            add(path, root, fpts, np.maximum(fr0 * rad[path] / max(float(rad[path[0]]), 1e-9), floor * fr0), n_ax, 2)
            n_ax += 1
            n_fed += 1
            drawn.append(np.vstack([pos[root], fpts]))
    src = np.array(src)
    drawn_len = float(sum(np.linalg.norm(np.diff(d_, axis=0), axis=1).sum() for d_ in drawn))
    total_len = float(np.linalg.norm(P - P[par], axis=1).sum())
    return {"pos": np.array(pos), "parent": np.array(parent), "radius": np.array(radius), "axis": np.array(axis),
            "order": np.array(order), "ends": np.zeros(len(pos), bool), "key": tree["key"][src], "height": tree["height"],
            "spec": tree["spec"], "dead": None, "src": src,
            "info": {"limbs_kept": len(kept), "limbs": len(allL), "axes": int(len(tree["axes"])), "axes_kept": n_ax, "stubs": n_stub, "fed": n_fed,
                     "wood_m": round(drawn_len, 1), "wood_m_grown": round(total_len, 1),
                     "limb_names": [L["name"] for L in kept]}}


def wood_tubes(mini: dict, st: dict, f: float = 1.0) -> dict:
    """The drawn wood as plain tubes (quick: what the fit's silhouettes use)."""
    lo, hi = st["wood"].get("sides", [6, 12])
    sides = (max(3, int(round(lo * f))), max(4, int(round(hi * f))))
    return veg_mesh.tubes(mini, sides=sides, simplify=0.25 / max(f, 0.2), tip=1.0, tile=(0.5, 1.0))


def _segments(mini: dict, orders=(0, 1, 2)) -> list:
    """Per axis of those orders: (a, b, ra, rb, node of b) for its segments, with the foot run 0.3 m into the ground;
    with order 0, the spec's root buttresses (_roots: a 6th number, their join)."""
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
    if 0 in orders:
        out += _roots(mini)
    return out


def _roots(mini: dict) -> list:
    """The spec's `roots` ({count, spread, height}) on the drawn trunk: one root buttress per root, each its own axis (so
    the union fillets it into the trunk): it leaves the trunk at `height` m, runs out and down, meets the ground at
    the flared foot's radius + (`spread` - 1) x the bole's (the grown tree's root flares reach `spread` x its radius)
    and runs on into the ground. Directions and strengths as the realistic tree's (veg_mesh.tubes: the same seed)."""
    ro = (mini.get("spec") or {}).get("roots")
    if not ro or float(ro.get("spread", 2.0)) <= 1.0 or int(ro.get("count", 5)) < 1:
        return []
    tn = np.flatnonzero(mini["axis"] == mini["axis"][1])
    tn = tn[tn >= 1]
    zs, rs = mini["pos"][tn, 2], mini["radius"][tn]
    o = np.argsort(zs)
    zs, rs = zs[o], rs[o]
    h = max(float(ro.get("height", 0.8)), 0.05)
    r_b = float(np.interp(max(h, float(zs[0])), zs, rs))  # the bole over the roots
    r_g = max(float(np.interp(0.0, zs, rs)), float(mini["radius"][0]) if mini["pos"][0, 2] < 0 else 0.0, r_b)  # the foot at the ground
    foot = mini["pos"][0].copy()
    foot[2] = 0.0
    cnt = int(ro.get("count", 5))
    rng = np.random.default_rng(int((mini.get("spec") or {}).get("seed", 1)) + 77)
    th = (np.arange(cnt) + rng.uniform(-0.3, 0.3, cnt)) * (2 * math.pi / cnt) + rng.uniform(0, 6.28)
    st = rng.uniform(0.6, 1.0, cnt)
    node = np.array([int(tn[0])])
    out = []
    for t_, s_ in zip(th, st):
        d = np.array([math.cos(t_), math.sin(t_), 0.0])
        R = r_g + (float(ro["spread"]) - 1.0) * r_b * s_
        hh = h * (0.6 + 0.4 * s_)
        # (axis points: on the trunk's axis, a third of the way out, at the ground, in it; radii a fin's: thick at the trunk)
        # (thin tubes read as spider legs: a buttress is a fat lobe, its far end sunk into the ground)
        P = np.array([foot + [0, 0, hh], foot + d * 0.5 * R + [0, 0, 0.35 * hh], foot + d * R - [0, 0, 0.05 * r_b], foot + d * (R + 0.6 * r_b) - [0, 0, 0.4]])
        rr = r_b * np.array([0.65, 0.58, 0.42, 0.25]) * (0.8 + 0.2 * s_)
        out.append((P[:-1], P[1:], rr[:-1], rr[1:], np.repeat(node, 3), veg_style.ROOT_JOIN))
    return out


def wood_field(segs: list, p: np.ndarray, blend: float, node: bool = False):
    """The drawn wood as one field: each axis a chain of round cones (hard union along it: a smooth one bulged at every
    joint), the axes joined by a smooth union of `blend` x the branch's girth: forks are fillets, ends are round.
    node=True also returns the nearest segment's end node per point."""
    d = np.full(len(p), 1e3)
    nn = np.zeros(len(p), np.int64)
    for sg in segs:
        a, b, ra, rb, nodes = sg[:5]
        k = blend * float(rb[0]) * (sg[5] if len(sg) > 5 else 1.0)  # (a root's own wider fillet: its 6th number)
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
        d[m] = sdf_shapes.smin(d[m], da, k)
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
    rmin = float(min(sg[3].min() for sg in segs))
    voxel = float(st["wood"].get("voxel") or np.clip(0.4 * rmin, 0.05, 0.12))
    r = float(mini["radius"].max())
    lo = np.minimum(mini["pos"].min(0) - r - 0.4, np.min([np.minimum(sg[0], sg[1]).min(0) - sg[2].max() for sg in segs], 0) - 0.2)
    hi = np.maximum(mini["pos"].max(0) + r + 0.2, np.max([np.maximum(sg[0], sg[1]).max(0) + sg[2].max() for sg in segs], 0) + 0.2)
    V, F = mesh_field(fn, lo, hi, voxel)
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
