"""Drawn clumps: clumps under clumps, split tips, the drawn layout. Part of hair (hair.py has the overview)."""
from __future__ import annotations

import hashlib

import numpy as np

from . import store
from . import hair_head
from .hair import _ss, _unit, az_el, under
from .hair_groom import _line_at, _part_x, envelope, groom_params, hairline, inside
from .hair_grow import _grey, lie_cup, lie_tilt
from .hair_head import Scalp
from .hair_spec import _catmull, hair_of, lock_width

# ------------------------------------------------------------------------------------------------ drawn clumps
def top_to_azel(sc: Scalp, xy):
    """Points drawn on a top view of the head ([x, y] m from the head centre: x his left, y back) -> (az, el) of the
    scalp point under each, found along the vertical line (the highest scalp crossing)."""
    xy = np.asarray(xy, float)
    az0, el0 = az_el(np.stack([xy[:, 0], xy[:, 1], np.full(len(xy), 0.08)], 1))
    az, el = az0.copy(), el0.copy()
    for _ in range(12):  # solve for the scalp point whose x, y match (its radius varies with direction)
        P = sc.point(az, el, 0.0) - sc.C
        err = xy - P[:, :2]
        Q = P.copy()
        Q[:, :2] += err
        az, el = az_el(Q)
    return az, el


def _under_clumps(clumps: list, sc: Scalp | None = None, sink=True) -> list:
    """The layer under the drawn clumps, as an artist builds it: between each pair of neighbouring clumps of a row
    (consecutive, same name stem: top1, top2...) one more clump halfway between them, lying beneath both, so where
    their wedge tips part the gap shows hair, not the volume (the volume must never be a visible surface)."""
    import re

    def resample(xy, n=5):
        xy = np.asarray(xy, float)
        c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
        t = np.linspace(0, c[-1], n)
        return np.stack([np.interp(t, c, xy[:, k]) for k in range(2)], 1)
    out = []
    for c0, c1 in zip(clumps, clumps[1:]):
        n0, n1 = c0.get("name", ""), c1.get("name", "")
        stem = re.sub(r"\d+$", "", n0)
        if not n0 or stem != re.sub(r"\d+$", "", n1):
            continue
        sk = sink.get(stem, True) if isinstance(sink, dict) else sink  # per row: {stem: sink | false}
        if sk is False:
            continue
        sk = 0.35 if sk is True else float(sk)
        key = "azel" if ("azel" in c0 and "azel" in c1) else "top"
        if key not in c0 or key not in c1:
            if sc is None or not all(("azel" in c or "top" in c) for c in (c0, c1)):
                continue
            key = "azel"  # one drawn on the top view, one on the head: both as [az, el]

        def pts(c):
            if key == "azel" and "azel" not in c:
                a_, e_ = top_to_azel(sc, np.asarray(c["top"], float))
                q = np.stack([a_, e_], 1)
            else:
                q = np.asarray(c[key], float).copy()
            if key == "azel":
                q[:, 0] = (q[:, 0] + 180) % 360 - 180  # azimuths either side of the front average sensibly
                q[:, 0] = np.degrees(np.unwrap(np.radians(q[:, 0])))  # a clump crossing the back stays continuous
            return resample(q)
        p0, p1 = pts(c0), pts(c1)
        if key == "azel":  # neighbours either side of the back (175 and -170) average across it, not the front
            p1[:, 0] += 360.0 * np.round((p0[:, 0] - p1[:, 0]).mean() / 360.0)
        mid = 0.5 * (p0 + p1)
        out.append({"name": f"{n0}_{n1}_under", key: mid.round(4).tolist(),
                    "width": max(float(c0.get("width", 0.055)), float(c1.get("width", 0.055))),
                    "sink": sk, "edge": 1.2, "taper": 0.85,
                    **({"root": min(float(c0.get("root", 1.0)), float(c1.get("root", 1.0)))}
                       if ("root" in c0 or "root" in c1) else {})})  # (a narrow-rooted row's unders too; sink 1: under the
        # underlayer itself, so the volume still showed between the wedges)
    return out


def split_tips(sc: Scalp, g: dict, line, name: str, lk: dict, n: int = 2, at: float = 0.6, fan: float = 0.5,
               keep: float = 0.2) -> dict:
    """A clump whose end breaks into n smaller locks, the way an artist splits a big shape's tip in twos and threes
    (negative space between the tips, not one blunt point): the clump itself is cut off `keep` past `at` (0..1 along
    it) so its end tucks under the children; each child starts at `at`, lies on top of it (its tips over the layer
    below), is ~1.3/n of its width, and they fan apart across the lock by `fan` x the clump's width at the tips.
    Lengths differ a little (equal tips read as a comb). Returns the children ({name}_t1...); lk is shortened in place."""
    pts = np.asarray(lk["pts"], float)
    P = _catmull(sc.point(pts[:, 0], pts[:, 1], pts[:, 2]), 48)
    c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    u = c / max(c[-1], 1e-9)
    w, T = float(lk["width"]), float(lk["thickness"])
    tg = _unit(np.gradient(P, axis=0))
    nrm = _unit(P - sc.C)
    side = _unit(np.cross(nrm, tg))  # across the clump, in the head's tangent plane

    def resample(Q, lo, hi, k):
        t = np.linspace(lo, hi, k)
        return np.stack([np.interp(t, u, Q[:, q]) for q in range(3)], 1), t
    # the parent ends a little past the split, its tip under the children
    end = min(1.0, at + keep)
    k0 = max(3, len(pts) - 1)
    Pp, _ = resample(P, 0.0, end, k0)
    a, e, h = sc.coords(Pp)
    lk["pts"] = [[round(float(a[j]), 2), round(float(e[j]), 2), round(float(h[j]), 4)] for j in range(k0)]
    if lk.get("tilt"):
        lk["tilt"] = [round(float(v), 3) for v in lie_tilt(sc, g, line, _catmull(Pp, 4 * k0)[::4])]
    lk.pop("radius", None)
    lk.pop("handles", None)
    lk["taper"] = 1.0  # its cut end comes to a point under the children (a blunt end read as a block on top)
    out = {}
    rng = np.random.default_rng(int(hashlib.md5(name.encode()).hexdigest()[:6], 16))
    for i in range(n):
        o = (i - (n - 1) / 2) / max(n - 1, 1)  # -0.5 .. 0.5 across
        length = 1.0 - 0.12 * rng.uniform(0, 1) if n > 1 else 1.0
        Q, t = resample(P, at - 0.04, at + (1.0 - at) * length, 5)
        s_ = np.clip((t - at) / max(1.0 - at, 1e-9), 0, 1)
        j = np.clip(np.searchsorted(u, t), 0, len(u) - 1)
        off = (o * w * 0.55 * (1 - s_) + o * w * (0.55 + fan) * s_)[:, None] * side[j]  # start side by side, fan out
        # a child never strays further out of the hairline than the clump's own spine there (a split fringe
        # dropped one tip onto the forehead)
        a0, e0, _ = sc.coords(Q)
        lim = np.minimum(inside(sc, line, a0, e0), 0.004)
        for f in np.linspace(1.0, 0.0, 11):
            a1, e1, _ = sc.coords(Q + f * off)
            ok = inside(sc, line, a1, e1) >= lim - 1e-4
            if ok.all() or f == 0.0:
                break
        Q = Q + f * off + nrm[j] * (0.55 * T * np.sin(np.pi * np.clip(s_ * 1.4, 0, 1)) + 0.15 * T)[:, None]
        a, e, h = sc.coords(Q)
        cw = round(w * 1.3 / n * (1 + 0.15 * rng.uniform(-1, 1)), 4)
        out[f"{name}_t{i + 1}"] = {
            "tier": lk.get("tier", "drawn"), "pts": [[round(float(a[q]), 2), round(float(e[q]), 2),
                                                      round(float(h[q]), 4)] for q in range(len(Q))],
            "tilt": [round(float(v), 3) for v in lie_tilt(sc, g, line, Q)], "width": cw,
            "thickness": round(T * 0.8, 4), "cup": round(lie_cup(sc, cw, Q), 4), "taper": 1.0, "belly": 0.25,
            "root": 0.35, "twist": 0.0, "edge": lk.get("edge", 1.6), **({"grey": lk["grey"]} if "grey" in lk else {})}
    return out


ROOT_TILT = 0.5  # the climbing root's tilt, x the lie's tilt behind it (1: nape rows folded at their roots)


ROOT_CLIMB = 0.012  # m: the shortest run over which a drawn clump's root rises from under the layer to lie on it


TILT_MAX = 1.3  # rad: the most a drawn clump's flat side turns off facing away from the head centre


BEND_EASE = 0.7  # drawn clumps are eased until their spine's in-plane bend x half width is under this


def bend_ratio(sc: Scalp, Q, half):
    """Per point of a dense path on the head: how tightly it turns along the head's surface x the half width there
    (>= 1: a lock that wide folds its inner edge)."""
    d = np.gradient(Q, axis=0)
    ds = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    tg = d / ds[:, None]
    nr = _unit(Q - sc.C)
    b = _unit(np.cross(nr, tg))
    r = np.abs((np.gradient(tg, axis=0) / ds[:, None] * b).sum(1)) * half
    r[[0, -1]] = 0.0
    return r


def ease_bends(sc: Scalp, Q, half, limit: float = BEND_EASE, rounds: int = 200):
    """A dense path on the head smoothed (ends held, kept on the scalp's rays) where it turns tighter than `limit` x
    half width allows: a wide clump drawn round a sharp corner sweeps a wide curve instead."""
    Q = np.asarray(Q, float).copy()
    for _ in range(rounds):
        r = bend_ratio(sc, Q, half)
        if r.max() < limit:
            break
        wgt = np.clip((r - 0.8 * limit) / (0.2 * limit), 0, 1)
        wgt = np.convolve(wgt, np.ones(5) / 5, mode="same")  # ease the neighbourhood, not one point
        wgt[[0, -1]] = 0.0
        L = np.zeros_like(Q)
        L[1:-1] = 0.5 * (Q[:-2] + Q[2:]) - Q[1:-1]
        Q = Q + 0.5 * wgt[:, None] * L
        a, e = az_el(Q - sc.C)
        Q = sc.point(a, e, 0.0)
    return Q


def _to_hairline(sc: Scalp, line, Q, half, inset: float, rounds: int = 6, reach: float | None = None):
    """A dense path on the head moved across itself so the lock's edge facing the hairline (half width `half` per
    point) runs `inset` m inside the hairline (negative: tucked into the skin): the spine lies `half + inset` from the
    line. The edge of the front lock then IS the hairline, one designed sweep, instead of the volume's rim showing
    between it and the skin. `reach` (m): only where the edge already comes within this of that line (fully within
    half of it), so a lock that runs off the hairline keeps its drawn path there."""
    from scipy.ndimage import gaussian_filter1d
    Q = np.asarray(Q, float).copy()
    target = np.asarray(half, float) + inset
    eps = 0.4
    wgt = np.ones(len(Q))
    if reach is not None:
        a, e = az_el(Q - sc.C)
        gap = inside(sc, line, a, e) - target
        wgt = 1 - _ss((gap - 0.5 * reach) / (0.5 * reach))
        wgt = np.clip(gaussian_filter1d(wgt, 3.0, mode="nearest"), 0, 1)
        if wgt.max() < 0.02:
            return Q
    for _ in range(rounds):
        a, e = az_el(Q - sc.C)
        d = inside(sc, line, a, e)
        Pa = sc.point(a + eps, e, 0.0) - sc.point(a - eps, e, 0.0)
        Pe = sc.point(a, e + eps, 0.0) - sc.point(a, e - eps, 0.0)
        da = inside(sc, line, a + eps, e) - inside(sc, line, a - eps, e)
        de = inside(sc, line, a, e + eps) - inside(sc, line, a, e - eps)
        # the gradient of d on the scalp: v in span(Pa, Pe) with Pa.v = da, Pe.v = de
        M = np.stack([Pa, Pe], 1)  # (n, 2, 3)
        G = M @ np.transpose(M, (0, 2, 1))
        lam = np.linalg.solve(G + 1e-12 * np.eye(2), np.stack([da, de], 1)[..., None])[..., 0]
        v = (lam[:, :, None] * M).sum(1)
        step = -(wgt * (d - target) / np.maximum((v * v).sum(1), 1e-12))[:, None] * v
        Q = Q + step
        a, e = az_el(Q - sc.C)
        Q = sc.point(a, e, 0.0)
        if (wgt * np.abs(d - target)).max() < 0.0005:
            break
    return Q


def _edge_cup(sc: Scalp, g: dict, line, P, tilt, half, T) -> float:
    """The cup that brings a lock's edge facing the hairline down onto the underlayer there (a lock laid along a
    rolled front lies on the roll's tangent at its spine; its front edge stood off the roll and the dark rim of the
    volume showed under it). Near the most any control point needs (80th percentile: the roll at the quiff is where
    the rim showed), never less than the head's own sag."""
    P = np.asarray(P, float)
    tg = _unit(np.gradient(P, axis=0))
    n0 = _unit(P - sc.C)
    n0 = _unit(n0 - (n0 * tg).sum(1, keepdims=True) * tg)
    t = np.asarray(tilt, float)[:, None]
    nr = n0 * np.cos(t) + np.cross(tg, n0) * np.sin(t)
    b = _unit(np.cross(nr, tg))
    drops = []
    for sgn in (1.0, -1.0):
        E = P + sgn * np.asarray(half)[:, None] * b
        a, e, hE = sc.coords(E)
        drops.append((a, e, hE))
    # the side nearer the hairline
    (a1, e1, h1), (a2, e2, h2) = drops
    d1, d2 = inside(sc, line, a1, e1), inside(sc, line, a2, e2)
    pick = d1 < d2
    a, e, hE = np.where(pick, a1, a2), np.where(pick, e1, e2), np.where(pick, h1, h2)
    H, d_in = envelope(sc, g, line, a, e)
    want = under(g, H, a, e, d_in) + 0.35 * T
    need = (hE + 0.5 * T) - want  # the lens's outer face at the edge vs lying on the layer under it
    return float(np.clip(np.percentile(need[1:], 80), lie_cup(sc, 2 * float(np.max(half)), P), 0.03))


def drawn(sc: Scalp, g: dict, clumps: list) -> dict:
    """Clumps drawn on the top view: [{"name"?, "top": [[x, y], ...] (root first), "width", "thickness"?, "lie"?}]
    -> locks. Heights come from the volume: the root dives under whatever it grows from, the body lies with its back
    at the volume (the underlayer is sunk under it), the tip tucks onto the clump below (lifted `lie` x thickness,
    default 0.1); past the hairline (a fringe) it lies on the skin."""
    line = hairline(sc, g)
    out = {}
    clumps = list(clumps) + (_under_clumps(clumps, sc, g["drawn_under"]) if g.get("drawn_under", True) is not False else [])
    for i, c in enumerate(clumps):
        w = float(c.get("width", 0.055))
        # the drawing smoothed and resampled (6 points), with one more just past the root: the root grows from the
        # scalp and the clump is up at the volume a short way on (with the rise spread over the whole first segment
        # most of a short clump lay under the volume, which then showed as a smooth patch)
        if c.get("azel"):  # drawn on the head itself ([az, el] from the root)
            q = np.asarray(c["azel"], float)
            Q = _catmull(sc.point(q[:, 0], q[:, 1], 0.0), 40)
        else:  # drawn on the top view
            xy = _catmull(np.c_[np.asarray(c["top"], float), np.zeros(len(c["top"]))], 40)[:, :2]
            qa, qe = top_to_azel(sc, xy)
            Q = sc.point(qa, qe, 0.0)
        # a clump can't turn within its own width: eased where the drawing bends tighter (it folded into flakes)
        Q = ease_bends(sc, Q, 0.5 * w * lock_width({"Root": float(c.get("root", 1.0)),
                                                       "Belly": float(c.get("belly", 0.06)),
                                                       "Taper": float(c.get("taper", 1.0))}, np.linspace(0, 1, len(Q))))
        # the clump's outer edge laid on the hairline: one clean designed sweep. Per clump "to_hairline": inset m
        # (all along it) or {"inset", "reach"}; groom "hairline_edge": {"inset", "reach"} for every drawn clump whose
        # edge comes within reach of the hairline (the volume's rim showed between the clumps' edges and the skin)
        th = c.get("to_hairline", g.get("hairline_edge") if not c.get("name", "").endswith("_under") else None)
        if th is False:
            th = None
        laid = False
        if th is not None:
            thd = th if isinstance(th, dict) else {"inset": th}
            Q0 = Q
            Q = _to_hairline(sc, line, Q, 0.5 * w * lock_width({"Root": float(c.get("root", 1.0)),
                                                                "Belly": float(c.get("belly", 0.06)),
                                                                "Taper": float(c.get("taper", 1.0))},
                                                               np.linspace(0, 1, len(Q))), float(thd.get("inset", 0.0)),
                             reach=float(thd["reach"]) if thd.get("reach") is not None else None)
            laid = thd.get("reach") is None or float(np.abs(Q - Q0).max()) > 1e-4
            if laid:  # a hairline that turns (a temple corner) bent the path tighter than the lock's width allows
                Q = ease_bends(sc, Q, 0.5 * w * lock_width({"Root": float(c.get("root", 1.0)),
                                                               "Belly": float(c.get("belly", 0.06)),
                                                               "Taper": float(c.get("taper", 1.0))},
                                                              np.linspace(0, 1, len(Q))))
        cq =np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        # (the root's climb out of the layer takes at least ROOT_CLIMB m: over 8% of a short nape lock it rose ~7 mm
        # in 5 mm, and the tilted lens folded there)
        # "climb" (m): how long the root takes to rise onto the layer; long, a narrow root (root 0.05-0.1) grows out
        # of the layer and the lock's body forms further back, with no blunt root end showing
        t1 = min(max(0.08, float(c.get("climb", ROOT_CLIMB)) / max(cq[-1], 1e-9)), 0.4)
        tt = np.r_[0.0, t1, np.linspace(max(0.25, t1 + 0.12), 1.0, 4)] * cq[-1]
        Q = np.stack([np.interp(tt, cq, Q[:, k]) for k in range(3)], 1)
        a, e = az_el(Q - sc.C)
        T = float(c.get("thickness", 0.0055 * w / 0.055))
        H, d_in = envelope(sc, g, line, a, e)
        U = under(g, H, a, e, d_in)
        u = tt / max(tt[-1], 1e-9)
        h = U + 0.35 * T
        # the root dives just under the underlayer where it grows (at the part the underlayer dips to the scalp):
        # sent down to the scalp under a full volume, a root climbed ~2 cm in its first centimetre and the wide lens
        # folded through itself there (flakes along the part)
        h[0] = max(min(U[0] - 0.5 * T, U[1] - T), 0.2 * T)
        h[-1] = U[-1] + float(c.get("lie", 0.1)) * T
        h = h - float(c.get("sink", 0.0)) * T * _ss(u / 0.2)  # an under clump lies beneath its neighbours
        h = np.where(d_in < 0, np.maximum(h, 0.55 * T), h)  # a fringe lies on the forehead
        if d_in[0] < 0:  # a root drawn on or past the hairline grows out of the skin there: its end is buried in
            # the skin (left lying on the forehead, a row of front roots read as rounded scales along the hairline)
            h[0] = -0.6 * T
        P = sc.point(a, e, h)
        tilt = lie_tilt(sc, g, line, _catmull(P, 4 * len(P))[::4])
        # the root takes the next point's tilt: there the spine climbs out of the scalp and the volume's normal turns
        # sideways at a parting, so its own tilt came out ~100 deg off the next one's: the lens twisted through
        # itself at the root (the flakes along the part); and no point lies more than TILT_MAX off the head's own
        tilt[0] = tilt[1]
        tilt = np.clip(tilt, -TILT_MAX, TILT_MAX)
        # where the root climbs out of the layer the spine bends up: a lens turned on its side there bends within its
        # own plane and folds (the nape rows' flags), so the climb faces out (ROOT_TILT of the lie's tilt)
        tilt[:2] = ROOT_TILT * tilt[2]
        cup = lie_cup(sc, w, P)
        if laid:  # its hairline edge brought down onto the layer under it
            cup = _edge_cup(sc, g, line, P, tilt, 0.5 * w * lock_width(
                {"Root": float(c.get("root", 1.0)), "Belly": float(c.get("belly", 0.06)),
                 "Taper": float(c.get("taper", 1.0))}, u), T)
        cup = float(c.get("cup", cup))
        name = c.get("name") or f"k{i:02d}"
        out[name] = {"tier": "drawn", "pts": [[round(float(a[k]), 2), round(float(e[k]), 2), round(float(h[k]), 4)]
                                              for k in range(len(a))],
                     "tilt": [round(float(v), 3) for v in tilt], "width": round(w, 4), "thickness": round(T, 4),
                     "cup": round(cup, 4), "taper": float(c.get("taper", 1.0)),  # wedges: widest
                     "belly": float(c.get("belly", 0.06)), "root": float(c.get("root", 1.0)), "twist": 0.0,  # at
                     "edge": float(c.get("edge", 1.6))}  # the root, to a thin sharp tip; a flat back with crisp edges
        gr = _grey(g, float(a[0]), float(e[0]), line)
        if gr > 0.01:
            out[name]["grey"] = round(gr, 3)
        if c.get("split"):  # breakup: the tip splits into smaller locks
            sp = c["split"] if isinstance(c["split"], dict) else {"n": int(c["split"])}
            out.update(split_tips(sc, g, line, name, out[name], int(sp.get("n", 2)), float(sp.get("at", 0.6)),
                                  float(sp.get("fan", 0.5)), float(sp.get("keep", 0.2))))
    return out


def layout(name: str, save: str | None = None, size: int = 520, spec: dict | None = None):
    """The groom seen from above as a designer's sketch: the hairline, the parting, every lock's spine (drawn clumps
    thick and labelled, with their width; grown locks thin, by tier), roots dotted, arrows at the tips. x his left
    to the right of the image? No: drawn as seen from above with the face at the bottom, his left on the image's
    right (so it matches the top view render)."""
    from PIL import Image, ImageDraw
    spec = store.load(name) if spec is None else spec
    sc = hair_head.scalp(name, spec)
    g = groom_params(spec)
    line = hairline(sc, g)
    s = size / 0.24

    def px(P):
        Q = np.asarray(P, float) - sc.C
        return np.stack([size / 2 + Q[..., 0] * s, size / 2 - Q[..., 1] * s], -1)
    im = Image.new("RGB", (size, size), (246, 244, 240))
    dr = ImageDraw.Draw(im)
    a = np.arange(0.0, 360.0, 2.0)
    HL = px(sc.point(a, _line_at(line, a), 0.0))
    dr.line([tuple(p) for p in np.vstack([HL, HL[:1]])], fill=(150, 110, 90), width=2)
    xp = _part_x(g)
    if xp is not None:
        L = float(g["parting"].get("length", 0.1))
        y0 = sc.point(0.0, float(_line_at(line, 0.0)), 0.0)[1]
        dr.line([tuple(px([xp, y0, 0])), tuple(px([xp, y0 + L, 0]))], fill=(200, 60, 60), width=2)
    colours = {"drawn": (40, 40, 40), "strip": (120, 150, 190), "gap": (170, 170, 120), "fill": (170, 170, 120),
               "big": (60, 90, 60), "crown": (90, 120, 60)}
    for n, lk in sorted((hair_of(spec).get("locks") or {}).items(), key=lambda kv: kv[1].get("tier") == "drawn"):
        pts = np.asarray(lk["pts"], float)
        P = _catmull(sc.point(pts[:, 0], pts[:, 1], pts[:, 2]), 24)
        Pp = px(P)
        tier = lk.get("tier", "")
        col = colours.get(tier, (140, 140, 140))
        wpx = max(1, int(lk["width"] * s * 0.2))
        dr.line([tuple(p) for p in Pp], fill=col, width=wpx if tier == "drawn" else 1)
        r0 = Pp[0]
        dr.ellipse([r0[0] - 3, r0[1] - 3, r0[0] + 3, r0[1] + 3], outline=col)
        d = Pp[-1] - Pp[-3]
        d = d / max(np.linalg.norm(d), 1e-9)
        nrm = np.array([-d[1], d[0]])
        tip = Pp[-1]
        dr.polygon([tuple(tip + d * 7), tuple(tip - d * 3 + nrm * 5), tuple(tip - d * 3 - nrm * 5)], fill=col)
        if tier == "drawn":
            dr.text(tuple(r0 + np.array([4, -12])), n, fill=(20, 20, 20))
    dr.text((6, 6), f"{name}: from above, face at the bottom, his left on the right", fill=(60, 60, 60))
    dr.text((6, size - 16), "drawn clumps black (thickness = a fifth of the width); strips blue, gap locks olive; red = part",
            fill=(60, 60, 60))
    if save:
        im.save(save)
    return im
