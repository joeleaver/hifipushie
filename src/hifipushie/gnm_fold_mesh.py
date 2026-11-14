"""The fold in MESH space: rings filled, the blink's gain, the tail, smoothing along rings and crease rows, the slit,
`mesh_delta`; the wrap: the crease smoothed and its roughness measured, `chains_wrap`, `design_wrap`. Part of the upper lid's fold on GNM (gnm_fold.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import gnm_fold
from . import gnm_controls as gc
from .gnm_fold import chains, topo
from .gnm_fold_design import _ball, design

def _along(x, default: float):
    """A number, or [inner, middle, outer] (at CREASE_KNOTS), or [[u mm, value], ...] -> a function of u (mm across
    from the eye's centre, + = outer)."""
    if x is None:
        return lambda u: np.full(np.shape(u), float(default))
    if isinstance(x, (int, float)):
        return lambda u: np.full(np.shape(u), float(x))
    a = np.asarray(x, float)
    if a.ndim == 1:
        k = np.linspace(gnm_fold.CREASE_KNOTS[0], gnm_fold.CREASE_KNOTS[-1], len(a))
        return lambda u: np.interp(u, k, a)
    o = np.argsort(a[:, 0])
    return lambda u: np.interp(u, a[o, 0], a[o, 1])


def check_fold(cfg) -> dict | None:
    if cfg in (None, False, {}):
        return None
    if not isinstance(cfg, dict) or set(cfg) - gnm_fold.FOLD_KEYS:
        raise ValueError(f"base.head.lid_fold: keys {sorted(gnm_fold.FOLD_KEYS)} (crease / overhang in mm: a number, [inner, middle, outer] or "
                         "[[u mm, value], ...]; L / R: one side's own values)")
    return cfg


def _fill_rings(out: np.ndarray, side: int, last: int, t: dict, T: np.ndarray, Jl: np.ndarray) -> None:
    """The fold's displacement on EVERY vertex of each lid ring, not only on the radial chains' vertices (a ring has more
    vertices than there are chains: the ones between were left unmoved, a comb of moved / unmoved vertices: the crease
    "doesn't blend at the edges"), interpolated by angle round the eye; faded to nothing FADE_DEG past the span the chains
    cover and over FADE_RINGS rings beyond the last one moved. In place, mm."""
    ring = t["ring"] if side == 1 else t["ring"][t["mir"]]
    cx, cy = (Jl[0] if side == 1 else -Jl[0]), Jl[1]
    on_side = (T[:, 0] > 0) == (side == 1)
    ang_all = np.degrees(np.arctan2(side * (T[:, 0] - cx), T[:, 1] - cy))     # 0 = up, + = outer
    prev = None
    for k in range(1, last + len(gnm_fold.FADE_RINGS)):
        ids = np.flatnonzero((ring == k) & on_side)
        if not len(ids):
            continue
        a = ang_all[ids]
        if k < last:
            have = ids[np.linalg.norm(out[ids], axis=1) > 0]
            if len(have) < 2:
                continue
            ah = ang_all[have]
            o = np.argsort(ah)
            ah, dh = ah[o], out[have][o]
            d = np.stack([np.interp(a, ah, dh[:, c]) for c in range(3)], 1)
            lo, hi = ah[0], ah[-1]
            w = np.clip(1 - np.maximum(lo - a, 0) / gnm_fold.FADE_DEG, 0, 1) * np.clip(1 - np.maximum(a - hi, 0) / gnm_fold.FADE_DEG, 0, 1)
            out[ids] = d * (w * w * (3 - 2 * w))[:, None]
            prev = (a, out[ids].copy())
        elif prev is not None:      # past the last ring: the last ring's displacement, faded
            f = gnm_fold.FADE_RINGS[k - last]
            pa, pd = prev
            o = np.argsort(pa)
            out[ids] = np.stack([np.interp(a, pa[o], pd[o][:, c]) for c in range(3)], 1) * f


def _blink_gain(Vm, En, ch, uu, side, t, T, Jl) -> float:
    """1 with the eye open .. 0 when the upper margin has come down BLINK_FULL of the open aperture (smoothstep)."""
    r0 = np.flatnonzero(t["ring"] == 0)
    low = r0[(T[r0, 1] < Jl[1] - 0.5) & (np.abs(T[r0, 0] - Jl[0]) < 5.0)]
    up = ch[np.abs(uu) < 5.0, 0]
    if side == -1:
        low, up = t["mir"][low], t["mir"][up]
    ap = float(Vm[up, 1].mean() - Vm[low, 1].mean())
    drop = -float(np.asarray(En)[up, 1].mean()) * 1000.0
    x = float(np.clip(drop / max(gnm_fold.BLINK_FULL * ap, 1e-6), 0.0, 1.0))
    return 1.0 - x * x * (3 - 2 * x)


def _vnormals(Vm: np.ndarray) -> np.ndarray:
    Q = gc.gnm()["quads"]
    n = np.cross(Vm[Q[:, 2]] - Vm[Q[:, 0]], Vm[Q[:, 3]] - Vm[Q[:, 1]])
    N = np.zeros_like(Vm)
    for i in range(4):
        np.add.at(N, Q[:, i], n)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def _tail(Vm: np.ndarray, tail: dict, side: int) -> np.ndarray:
    """The crease's TAIL past the outer canthus (mm displacement): a groove along a path of GNM vertices traced in the
    front picture (the hood's crease running on laterally, 4-11 mm past the corner, where the lid rings' radial chains
    do not reach), the skin above it standing a little proud (the drape's lower edge), faded in over its first fifth and
    out over its last 40 % (no step where it starts or ends). tail = {"path": [GNM vertex ids, this side's own, outward],
    "depth": mm (0.5), "width": mm (0.9)}. Only skin outside the lid margin moves."""
    from scipy.spatial import cKDTree
    path = np.asarray(tail.get("path") or [], int)
    out = np.zeros_like(Vm)
    if len(path) < 3:
        return out
    dep, wd = float(tail.get("depth", gnm_fold.TAIL_DEPTH)), float(tail.get("width", gnm_fold.TAIL_WIDTH))
    P = Vm[path]
    seg = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    if seg[-1] < 1.0:
        return out
    f = np.linspace(0, seg[-1], max(int(seg[-1] / 0.1), 4))
    Pd = np.stack([np.interp(f, seg, P[:, i]) for i in range(3)], 1)
    for _ in range(3):     # a smooth line (vertex to vertex the path zigzags)
        Pd[1:-1] = 0.25 * Pd[:-2] + 0.5 * Pd[1:-1] + 0.25 * Pd[2:]
    g, t = gc.gnm(), topo()
    ring = t["ring"] if side == 1 else t["ring"][t["mir"]]
    skin = np.asarray(g["groups"]["skin"]) > 0.5
    cand = np.flatnonzero(skin & (ring >= 1) & (np.linalg.norm(Vm - Pd.mean(0), axis=1) < seg[-1] + 6 * wd))
    d, j = cKDTree(Pd).query(Vm[cand])
    u = j / (len(Pd) - 1)
    taper = np.clip(u / 0.2, 0, 1) * np.clip((1 - u) / 0.4, 0, 1)
    taper = taper * taper * (3 - 2 * taper)
    N = _vnormals(Vm)[cand]
    above = np.clip((Vm[cand, 1] - Pd[j, 1]) / wd, -1, 1)              # GNM frame: y up
    prof = -dep * np.exp(-(d / wd) ** 2) + 0.45 * dep * np.exp(-((d - 1.8 * wd) / (1.4 * wd)) ** 2) * np.clip(above, 0, 1)
    out[cand] = (prof * taper)[:, None] * N
    return out


def _smooth_along_rings(out: np.ndarray, side: int, t: dict, passes: int) -> None:
    """The fold's displacement averaged with each vertex's neighbours ON ITS OWN RING (a ring = one height in the section),
    `passes` times, in place, this side only. Neighbouring radial chains round the outer corner point very differently
    (GNM's rings fan out there), so their designed sections disagree: a rippled, pale "crust" along the outer third of
    the fold under raking or GI light (found by switching paint layers off: it stayed in every toggle and vanished
    unlit = geometry). Along the ring only, so the crease's own section (platform, slit, roll) is kept."""
    if passes <= 0:
        return
    ring = t["ring"] if side == 1 else t["ring"][t["mir"]]
    T = gc.gnm()["T"] * 1000.0
    J = gc.gnm()["J"][2] * 1000.0
    up = (T[:, 1] > J[1] - 1.0) | (np.abs(T[:, 0]) - abs(J[0]) > 3.0)     # the upper lid and round the outer corner only:
    mv = np.flatnonzero((np.abs(out).sum(1) > 0) & up)                    # never carried round the ring under the eye
    mv = mv[ring[mv] >= 1]
    nbr = [[b for b in t["nb"][v] if ring[b] == ring[v] and up[b]] for v in mv]
    for _ in range(passes):
        new = out[mv].copy()
        for i, (v, nb) in enumerate(zip(mv, nbr)):
            if nb:
                new[i] = 0.5 * out[v] + 0.5 * out[nb].mean(0)
        out[mv] = new


def slit_ids(cfg: dict) -> dict:
    """{GNM vertex id: weight 0..1} of the fold's SLIT (the crease line: rings ring+1 and ring+2 of the chains up to the
    outer corner's horizontal, tapered over the inner and outer quarter) and of each side's crease tail (the path and its
    neighbours, fading to its end): where a crease cavity term darkens the skin. (The wrap's chains past 90 deg run DOWN
    round the corner: a downward stub with a gap before the tail.)"""
    cfg = check_fold(cfg) or {}
    t = topo()
    out: dict = {}
    def put(v, w):
        out[int(v)] = max(out.get(int(v), 0.0), float(w))
    for side, key in ((1, "L"), (-1, "R")):
        c = {**{k: v for k, v in cfg.items() if k not in ("L", "R")}, **(cfg.get(key) or {})}
        if float(c.get("amount", 1.0)) <= 0:
            continue
        ka, kt = int(c.get("ring", 5)), int(c.get("last", 10))
        ch, ang = chains_wrap(float(c.get("reach", 15.5)), kt + 2, _wrap(c))
        keep = np.flatnonzero(ang <= 90.0)
        ids = ch if side == 1 else t["mir"][ch]
        a0, a1 = float(ang[keep].min()), float(ang[keep].max())
        tail = [int(v) for v in ((c.get("tail") or {}).get("path") or [])]
        for j in keep:
            u = (ang[j] - a0) / max(a1 - a0, 1e-6)
            w = min(np.clip(u / 0.15, 0, 1), 1.0 if tail else np.clip((1 - u) / 0.15, 0, 1))
            w = w * w * (3 - 2 * w)
            # (the slit itself hides under the roll in a front view: the dark the picture shows is the shadow the hood
            # casts on the platform under it, and the roll's lower edge; with the slit rings alone an older test head's crease read
            # 0.13-0.27 against his 0.30-0.49 at full strength)
            for k, wk in ((ka - 1, 0.6), (ka, 1.0), (ka + 1, 1.0), (ka + 2, 0.8)):
                put(ids[j, k], w * wk)
        for i, v in enumerate(tail):
            w = float(np.clip((len(tail) - 1 - i) / max(0.4 * len(tail), 1), 0, 1))
            put(v, w)
            for b in t["nb"][v]:
                put(b, 0.6 * w)
    return out


def _smooth_crease_rows(out: np.ndarray, Vm: np.ndarray, side: int, t: dict, ka: int) -> None:
    """The crease's own rows (rings ka-1 .. ka+3: platform edge, slit, roll edge) made smooth curves: each moved vertex's
    final position averaged with its ring neighbours', only ALONG the ring (the component across it, i.e. the section,
    kept). GNM's ring rows are not smooth curves at the fold's heights and the vertices between the chains took
    interpolated displacements: the crease line wobbled and kinked above the pupil. In place, mm, this side only."""
    ring = t["ring"] if side == 1 else t["ring"][t["mir"]]
    T = gc.gnm()["T"] * 1000.0
    J = gc.gnm()["J"][2] * 1000.0
    up = (T[:, 1] > J[1] - 1.0) | (np.abs(T[:, 0]) - abs(J[0]) > 3.0)
    on = (T[:, 0] > 0) == (side == 1)
    for _ in range(gnm_fold.CREASE_ROW_PASSES):
        X = Vm + out
        for k in range(max(ka - 1, 1), ka + 4):
            mv = np.flatnonzero((ring == k) & up & on & (np.abs(out).sum(1) > 0))
            for v in mv:
                nb = [b for b in t["nb"][v] if ring[b] == k and up[b] and on[b]]
                if len(nb) != 2:
                    continue
                tng = X[nb[1]] - X[nb[0]]
                tng /= max(np.linalg.norm(tng), 1e-9)
                mid = 0.5 * (X[nb[0]] + X[nb[1]])
                d = mid - X[v]
                d_perp = d - (d @ tng) * tng            # toward the neighbours' chord, across the tangent only
                out[v] += 0.5 * d_perp


def mesh_delta(V0: np.ndarray, En: np.ndarray | None, cfg: dict) -> np.ndarray:
    """The upper lids' fold as a displacement of GNM's OWN vertices (m, GNM frame; added to the head as built):
    base.head.lid_fold = {"crease": mm over the margin where the fold's slit sits (6.5), "overhang": mm of drape
    hanging over the platform in a front view (0.6; 0 = a crisp crease, 2+ = hooded: the visible platform is crease -
    overhang), "thick": the roll's thickness mm (0.9), "standoff": the platform's distance off the eyeball mm (1.3),
    "ring": the crease's ring (5), "last": the first ring left as it is (10), "reach": mm either side of the eye's
    centre the fold runs (15.5: to the canthi), "taper": mm over which it fades into the head's own lid toward the
    corners (0.45 x reach: at 12 / 3 mm the fold stopped in a visible step short of the outer corner), "amount":
    0..1, "L" / "R": one side's own values}. crease / overhang: a number, [inner, middle, outer] or [[u, value], ...].
    LOCAL BY CONSTRUCTION: only the upper lid's rings 1 .. last - 1 on the radial chains within `reach` move (the
    margin, the brow, the lower lid, the eyeball and every landmark are bit-identical); GNM's own soft groove is
    REPLACED by the designed section (platform, slit, roll), not overlaid.
    V0: the head WITHOUT its expression (m); En: the expression's displacement (m) or None: the fold fades as the upper
    margin comes down (a blink unfolds it: gone at BLINK_FULL of the open aperture) and rides the lid otherwise."""
    cfg = check_fold(cfg) or {}
    Vm = np.asarray(V0, float) * 1000.0
    t = topo()
    T = gc.gnm()["T"] * 1000.0
    Jl = gc.gnm()["J"][2] * 1000.0
    out = np.zeros_like(Vm)
    for side, key in ((1, "L"), (-1, "R")):
        c = {**{k: v for k, v in cfg.items() if k not in ("L", "R")}, **(cfg.get(key) or {})}
        amount = float(c.get("amount", 1.0))
        if amount <= 0:
            continue
        reach = float(c.get("reach", 15.5))
        cr, ov = _along(c.get("crease"), 6.5), _along(c.get("overhang"), 0.6)
        ka, kt = int(c.get("ring", 5)), int(c.get("last", 10))
        # (design() takes ONE overhang: lay it per chain by designing at the knots' values and blending along u)
        ch = chains(reach)
        uu = T[ch[:, 0], 0] - Jl[0]
        ovs = ov(uu)
        wrap = _wrap(c)
        if wrap > 0:   # the fold follows its ring round the outer corner (design_wrap); crease / overhang by the chain's
            # angle: the [inner, middle, outer] lists at -60 / 0 / 90 deg, the last held round the wrap
            def by_ang(x, dflt):
                f = _along(x, dflt)
                return lambda a: f(np.interp(a, [-60.0, 0.0, 90.0], [-9.0, 0.0, 9.0]))
            crf = by_ang(c.get("crease"), 6.5)
            if c.get("crease_by_angle"):   # [[deg, mm], ...]: the crease's height along each chain, traced in a picture
                crf = smooth_crease(c["crease_by_angle"])
            tgw = design_wrap(Vm, crf, by_ang(c.get("overhang"), 0.6), traced=bool(c.get("crease_by_angle")), thick=float(c.get("thick", 0.9)),
                              standoff=float(c.get("standoff", 1.3)), ka=ka, kt=kt, umax=reach, wrap_deg=wrap,
                              depth=float(c.get("depth", 1.0)))
            Tm = gc.gnm()["T"] * 1000.0
            gain = _blink_gain(Vm, En, ch, uu, side, t, Tm, Jl) if En is not None else 1.0
            for v, p in tgw.items():
                if (Tm[v, 0] > 0) == (side == 1):          # this side's own vertices (design_wrap makes both)
                    out[v] = (p - Vm[v]) * amount * gain
            _fill_rings(out, side, kt, t, Tm, Jl)
            if c.get("tail"):
                out += _tail(Vm, c["tail"], side) * amount * gain
            _smooth_along_rings(out, side, t, int(c.get("smooth", gnm_fold.RING_SMOOTH)))
            _smooth_crease_rows(out, Vm, side, t, ka)
            continue
        levels = np.unique(np.round(ovs, 2))
        tg_by = {float(o): design(Vm, crease=cr, overhang=float(o), thick=float(c.get("thick", 0.9)), standoff=float(c.get("standoff", 1.3)),
                                  ka=ka, kt=kt, umax=reach, taper=float(c.get("taper", 0.45 * reach))) for o in levels}
        ids = ch if side == 1 else t["mir"][ch]
        gain = _blink_gain(Vm, En, ch, uu, side, t, T, Jl) if En is not None else 1.0
        for j in range(len(ch)):
            tg = tg_by[float(np.round(ovs[j], 2))]
            for k in range(1, kt):
                v = int(ids[j, k])
                if v in tg:
                    out[v] = (tg[v] - Vm[v]) * amount * gain
    return out / 1000.0


                    # upper and lower lids share their rings, so a chain based past ~10 deg below the horizontal sits on the LOWER
                    # lid's margin: re-sectioning it against its unmoved neighbours folded the lower lid (r12, folded exterior
                    # edges on the built heads, assembly mask: Garrett 0 without the fold -> 109 at wrap 35.2 (down to 9.5 mm
                    # below the eye centre), 50 at 10 (upper lid only, the slit's own undercut rings ka+1 / ka+2); Tess 0 -> 105
                    # (to 14.4 mm below) / 37 at 10)

def _wrap(c: dict) -> float:
    return min(float(c.get("wrap", gnm_fold.WRAP_DEG)), gnm_fold.WRAP_MAX)


def smooth_crease(cba) -> callable:
    """[[deg, mm], ...] (traced / read, noisy) -> a smooth height function of the chain angle: a least-squares
    polynomial of CREASE_DEG (a quadratic has one extremum: a real crease is one smooth arc between the canthi), held flat
    past the data's ends. Interpolating the points themselves seated their noise: a wobbly, kinked crease."""
    a = np.asarray(cba, float)
    a = a[np.argsort(a[:, 0])]
    if len(a) < gnm_fold.CREASE_DEG + 2:
        return lambda x, a=a: np.interp(x, a[:, 0], a[:, 1])
    k = np.polyfit(a[:, 0], a[:, 1], gnm_fold.CREASE_DEG)
    lo, hi = float(a[0, 0]), float(a[-1, 0])
    return lambda x, k=k, lo=lo, hi=hi: np.polyval(k, np.clip(x, lo, hi))


def crease_roughness(heights: np.ndarray) -> dict:
    """A crease line's smoothness, heights (mm) sampled evenly along the arc: the rms second difference (mm) and how
    often the curvature changes sign (a smooth arc: 0)."""
    h = np.asarray(heights, float)
    d2 = np.diff(h, 2)
    sg = np.sign(d2[np.abs(d2) > 0.02])
    return {"d2_rms": round(float(np.sqrt(np.mean(d2 ** 2))) if len(d2) else 0.0, 3),
            "sign_changes": int((np.diff(sg) != 0).sum()) if len(sg) > 1 else 0}


def seated_roughness(V0: np.ndarray, cfg: dict) -> dict:
    """The SEATED crease line's smoothness per side (GNM frame, m in): the slit ring's vertices (ring + 1) on the upper lid,
    ordered round the eye, their distance from the eye's centre in the front plane resampled every 3 deg and taken
    through crease_roughness. The gate for a wobbly crease (a curve's parameters, not its vertices)."""
    t = topo()
    T = gc.gnm()["T"] * 1000.0
    J = gc.gnm()["J"][2] * 1000.0
    X = (np.asarray(V0, float) + mesh_delta(V0, None, cfg)) * 1000.0
    out = {}
    for side, key in ((1, "L"), (-1, "R")):
        c = {**{k: v for k, v in (cfg or {}).items() if k not in ("L", "R")}, **((cfg or {}).get(key) or {})}
        ka = int(c.get("ring", 5))
        ring = t["ring"] if side == 1 else t["ring"][t["mir"]]
        cx = J[0] if side == 1 else -J[0]
        on = ((T[:, 0] > 0) == (side == 1)) & (ring == ka + 1)
        ids = np.flatnonzero(on)
        dx, dy = (X[ids, 0] - cx) * side, X[ids, 1] - J[1]
        ang = np.degrees(np.arctan2(dx, dy))
        sel = (ang > -60) & (ang < 75)
        if sel.sum() < 6:
            continue
        o = np.argsort(ang[sel])
        P = np.c_[dx[sel][o], dy[sel][o]]
        # the polyline's TURNING per vertex (deg): a smooth arc turns the same way everywhere, a wobble flips
        e = np.diff(P, axis=0)
        th = np.degrees(np.unwrap(np.arctan2(e[:, 1], e[:, 0])))
        turn = np.diff(th)
        sg = np.sign(turn[np.abs(turn) > 2.0])
        out[key] = {"turn_rms_deg": round(float(np.sqrt(np.mean((turn - turn.mean()) ** 2))), 2),
                    "sign_changes": int((np.diff(sg) != 0).sum()) if len(sg) > 1 else 0, "n": int(len(P))}
    return out


def chains_wrap(umax: float = 15.5, k1: int = gnm_fold.NR, wrap_deg: float = gnm_fold.WRAP_DEG) -> tuple:
    """Radial chains of the LEFT eye's lid rings for a fold that wraps the outer corner: every margin vertex of the upper
    lid within umax mm across, plus the margin round the OUTER corner down to wrap_deg below the eye's horizontal; each
    chain followed outward along its own radial direction (from the eye's centre in the front plane). Returns
    (chains (n, k1 + 1), angle per chain: deg from the upward vertical, + toward the outer side)."""
    key = ("chw", umax, k1, wrap_deg)
    if key in gnm_fold._C:
        return gnm_fold._C[key]
    g, t = gc.gnm(), topo()
    T = g["T"] * 1000.0
    J = g["J"][2] * 1000.0
    r0 = np.flatnonzero(t["ring"] == 0)
    dx, dy = T[r0, 0] - J[0], T[r0, 1] - J[1]
    ang = np.degrees(np.arctan2(dx, dy))                 # 0 = straight up, + = outer (+x for the left eye)
    upper = (dy > 0.5) & (np.abs(dx) < umax)
    outer = (dx > 0) & (ang <= 90.0 + wrap_deg) & (ang > 0)
    r0, ang = r0[upper | outer], ang[upper | outer]
    o = np.argsort(ang)
    out, aout = [], []
    for v, a_ in zip(r0[o], ang[o]):
        ch = [int(v)]
        while t["ring"][ch[-1]] < k1:
            up = [b for b in t["nb"][ch[-1]] if t["ring"][b] == t["ring"][ch[-1]] + 1]
            if not up:
                break
            rad = T[ch[-1], :2] - J[:2]
            rad = rad / max(np.linalg.norm(rad), 1e-9)
            ch.append(max(up, key=lambda b: float((T[b, :2] - T[ch[-1], :2]) @ rad)))
        if len(ch) == k1 + 1:
            out.append(ch)
            aout.append(float(a_))
    gnm_fold._C[key] = (np.array(out), np.array(aout))
    return gnm_fold._C[key]


def design_wrap(V: np.ndarray, crease, overhang, thick: float = 0.9, standoff: float = 1.3, ka: int = 5, kt: int = 10,
                umax: float = 15.5, wrap_deg: float = gnm_fold.WRAP_DEG, fade_deg: float = 30.0, traced: bool = False, depth: float = 1.0) -> dict:
    """design() along each chain's OWN outward direction (not the vertical), so the fold follows its ring round the
    outer corner and down (a hood wrapping the corner, continuing toward the lower lid's fold). crease / overhang:
    functions of the chain's angle (deg from the upward vertical, + outer). The fold fades to nothing over the last
    fade_deg of the wrap and over the inner end (by the across distance)."""
    wrap_deg = min(float(wrap_deg), gnm_fold.WRAP_MAX)   # (never onto the lower lid: WRAP_MAX)
    t = topo()
    T = gc.gnm()["T"] * 1000.0
    ch, ang = chains_wrap(umax, kt + 2, wrap_deg)
    out = {}
    for side, grp in ((1, "left_eye"), (-1, "right_eye")):
        ids = ch if side == 1 else t["mir"][ch]
        ctr, r = _ball(V, grp)
        uu = T[ch[:, 0], 0] - gc.gnm()["J"][2][0] * 1000.0
        w_in = np.clip((umax + uu) / (0.45 * umax), 0, 1)                         # the inner end (uu < 0 inner)
        w_out = np.clip((90.0 + wrap_deg - ang) / fade_deg, 0, 1)                  # the wrap's end
        wt = np.minimum(w_in, w_out)
        wt = wt * wt * (3 - 2 * wt)
        cr = np.asarray(crease(ang), float)
        ov = np.asarray(overhang(ang), float)
        # the crease follows its RING round the corners: each chain's height scaled by its own ring-ka distance against
        # the upper lid's (forcing the full crease height onto corner chains, whose ring ka lies ~2 mm out, dragged a
        # 5 mm lump under the outer lower lid)
        Pall = V[ids] - ctr
        dka = np.array([float(np.linalg.norm(Pall[j, ka, :2] - Pall[j, 0, :2])) for j in range(len(ch))])
        top = np.abs(ang) < 40.0
        dref = float(np.median(dka[top])) if top.any() else float(np.median(dka))
        sc = np.clip(dka / max(dref, 1e-6), 0.35, 1.0)
        if not traced:   # (a crease TRACED per chain angle already follows the picture round the corner: not scaled down)
            cr = cr * sc
        ov = ov * sc
        for j in range(len(ch)):
            P = V[ids[j]] - ctr
            if wt[j] <= 0:
                continue
            rad = P[1:kt + 1, :2].mean(0) - P[0, :2]
            rad = rad / max(np.linalg.norm(rad), 1e-9)
            base = P[0, :2]
            d = (P[:, :2] - base) @ rad                                              # the head's own spacing out along the chain
            nz = np.cross(np.r_[rad, 0.0], [0.0, 0.0, 1.0])                           # (the chain's sideways axis, front plane)
            dmax = float(d[kt]) - 1.0
            # depths relative to the head's OWN surface at that distance along the chain (the ball's sphere does not
            # describe the skin lateral to the eye: seated on it the wrap ran 10 mm off): the platform on the surface,
            # the slit in, the roll's lower edge and front out
            def surf(h):
                return float(np.interp(h, d, P[:, 2]))
            tg = {}
            for k in range(1, ka + 1):
                tg[k] = (min(cr[j] * d[k] / max(d[ka], 1e-6), dmax), -0.15 * (k / ka))
            # the slit only as deep as there is drape over it: with little overhang (a young lid, the wrap's fading end) a
            # full slit showed as a dark CRACK at Tess's outer corner
            tg[ka + 1] = (min(cr[j] + 0.35, dmax), -0.7 * depth * float(np.clip(ov[j] / 1.0, 0.25, 1.0)))
            # the roll only as proud as the drape it is: a young lid with little overhang has a soft crease, not a ridge
            # (at full height a pale ridge and a dark line, "hard" on a young face's crease)
            rk = float(np.clip(ov[j] / 1.0, 0.4, 1.0))
            tg[ka + 2] = (min(cr[j] - ov[j], dmax), (0.4 + 0.6 * thick) * rk)
            tg[ka + 3] = (min(cr[j] - ov[j] + 0.8, dmax), (0.5 + thick) * rk)
            pts = {}
            for k, (h, dz) in tg.items():
                q2 = base + rad * h
                pts[k] = np.array([q2[0], q2[1], surf(h) + dz]) + nz * float((P[k, :2] - base) @ nz[:2])
            a, b = pts[ka + 3], P[kt]
            cum = np.cumsum(np.linalg.norm(np.diff(P[ka + 3:kt + 1], axis=0), axis=1))
            for i, k in enumerate(range(ka + 4, kt)):
                pts[k] = a + (b - a) * (cum[i] / cum[-1])
            for k, p in pts.items():
                vid = int(ids[j, k])
                tgt = wt[j] * p + (1 - wt[j]) * P[k] + ctr
                out[vid] = tgt if vid not in out else 0.5 * (out[vid] + tgt)
    return out
