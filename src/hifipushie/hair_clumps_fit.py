"""A card fitted to a clump: `fit`, the envelope, the side weight, crown and grade fill, the root seat, offsets. Part of hair clumps (hair_clumps.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_clumps
from .hair_clumps import _ss, _unit, along_reference

def fit(Q: np.ndarray, cen_of, end_share: float = 0.2, max_hw: float = 0.03, start_share: float = 0.04,
        spread: float = 90.0, reference: bool = True, tip_taper=None, medoid: float = 0.0, per_strand: float = 0.0,
        min_stations: int | None = None, min_len: float | None = None) -> dict | None:
    """One card on a clump's strands Q (m, stations, 3, NaN past their ends), along its reference strand
    (along_reference): hair_cards_clumps._clump's centre line and frame, from where its first strands start to where only
    `end_share` of them still run (ragged ends are the picture's), its half width the strands' spread across it (90th
    percentile, capped)."""
    from .hair_cards_clumps import _clump
    # (`reference`: hair converging from many roots (into a tie) is aligned along its longest strand; hair hanging from
    # one place (a tail) by distance from the root: mapped to a wavy reference's nearest station, strands of another
    # phase folded back and forth and the picture smeared)
    A = along_reference(Q) if (reference and len(Q) > 1) else Q[:, :int(np.isfinite(Q[..., 0]).sum(1).max())].astype(float)
    U = np.arange(A.shape[1]) * hair_clumps.STEP
    c = _clump(A, U, cen_of, min_share=0.5, start_share=start_share, end_share=end_share, medoid=medoid,
               twist=0.0 if reference else np.radians(hair_clumps.TWIST_HANG),
               min_stations=hair_clumps.MIN_STATIONS if min_stations is None else int(min_stations))
    if c is None:
        return None
    sl = slice(c["i0"], c["i0"] + len(c["P"]))
    d = A[:, sl] - c["P"][None]
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        ax = np.nanpercentile(np.abs((d * c["X"][None]).sum(-1)), spread, axis=0)
        on = np.nanpercentile((d * c["N"][None]).sum(-1), hair_clumps.SIDE_OUT_PCT, axis=0)  # the clump's outer strands along N
    ax = np.nan_to_num(ax, nan=0.002)
    from scipy.ndimage import gaussian_filter1d
    c["out"] = np.clip(gaussian_filter1d(np.nan_to_num(on, nan=0.0), 2.0), 0.0, hair_clumps.SIDE_OUT_MAX)
    hw = np.clip(gaussian_filter1d(ax, 2.0) * 1.15 + 0.0015, 0.0015, max_hw)
    # narrower where few of its strands are left (a card as wide as its clump to the last strand's tip was a torn,
    # blocky end)
    hw = hw * np.clip(gaussian_filter1d(np.asarray(c["share"], float), 2.0) / 0.5, 0.35, 1.0)
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(c["P"], axis=0), axis=1))]
    if s[-1] < (hair_clumps.FIT_MIN_LEN if min_len is None else min_len):
        return None
    if per_strand > 0:  # (tail cards: HW_PER_STRAND) no wider than its running strands can fill (a few outer frizz strands as an 18 mm ribbon
        # wearing a dense tile: b24 review "wide separate ribbon strands flare off the ponytail")
        run = np.asarray(c["share"], float) * len(Q)
        hw = np.minimum(hw, np.maximum(0.0015, gaussian_filter1d(run, 2.0) * per_strand))
    if hair_clumps.BEND_HW > 0 and len(s) > 4:  # a card bent in its own plane tighter than its half width folds its inner edge
        # back over itself (b24: hanging/L0 card 201 at the tail's curl, 11 folded triangle pairs = the "folded flap
        # at the end"): half width <= BEND_HW x the bend radius there
        from scipy.ndimage import minimum_filter1d
        T_ = np.gradient(c["P"], s, axis=0)
        T_ = T_ / np.maximum(np.linalg.norm(T_, axis=1), 1e-9)[:, None]
        kx = np.abs((np.gradient(T_, s, axis=0) * c["X"]).sum(-1))
        lim = hair_clumps.BEND_HW / np.maximum(gaussian_filter1d(kx, 1.0), 1e-6)
        hw = np.minimum(hw, np.maximum(0.0015, minimum_filter1d(lim, 5)))
    # the card's GEOMETRY tapers to a point over its last TIP_TAPER: square-cut card ends read as a sawtooth comb at game
    # distance (g1_b15 review, 1 m: "blunt, comb-like" tail ends, "chunky blunt ends"); the picture's feathered tip alone
    # can't hide the quad's square end
    tt = hair_clumps.TIP_TAPER if tip_taper is None else tip_taper
    if tt > 0:
        u = (s[-1] - s) / max(tt * s[-1], 1e-6)
        hw = hw * (hair_clumps.TIP_FLOOR + (1 - hair_clumps.TIP_FLOOR) * _ss(np.clip(u, 0.0, 1.0)))
    return {**c, "hw": hw, "s": s}


def envelope(St: dict, C, deg: float = 3.0, pct: float = 97.0, grade: float = 0.0):
    """The head hair's outer surface seen from the head's centre: a function points -> the strands' `pct` radius in
    their (azimuth, elevation) bin (NaN where too few strands). `grade` (m / deg, GRADE_SLOPE): behind GRADE_AZ each
    bin is raised to max over the GRADE_BAND above it of (their radius - grade x the elevation between)."""
    C = np.asarray(C, float)
    Q = St["Q"][St["cls"] == "head"][:, ::2].reshape(-1, 3)
    Q = Q[np.isfinite(Q[:, 0])].astype(float)

    def key(P):
        v = np.asarray(P, float) - C
        r = np.linalg.norm(v, axis=1)
        az = np.degrees(np.arctan2(v[:, 0], -v[:, 1]))
        el = np.degrees(np.arcsin(np.clip(v[:, 2] / np.maximum(r, 1e-9), -1, 1)))
        return np.floor(az / deg).astype(np.int64) * 100000 + np.floor(el / deg).astype(np.int64), r
    kq, rq = key(Q)
    o = np.argsort(kq)
    u, st, cnt = np.unique(kq[o], return_index=True, return_counts=True)
    env = {int(k): (float(np.percentile(rq[o][a:a + c], pct)) if c >= 20 else np.nan) for k, a, c in zip(u, st, cnt)}
    if grade > 0:
        g_ = dict(env)
        for k, v in env.items():
            ia, ie = k // 100000, k % 100000
            if ie > 50000:  # (negative elevation bins: python floor division keeps ia, ie consistent; ie wraps)
                ia, ie = ia + 1, ie - 100000
            if abs((ia + 0.5) * deg) <= hair_clumps.GRADE_AZ:
                continue
            best = v if np.isfinite(v) else -np.inf
            for j in range(1, int(np.ceil(hair_clumps.GRADE_BAND / deg)) + 1):
                w_ = env.get(int(ia * 100000 + ie + j), np.nan)
                if np.isfinite(w_):
                    best = max(best, w_ - grade * j * deg)
            if np.isfinite(best):
                g_[k] = float(best)
        env = g_
    # fallback where an (azimuth, elevation) bin is empty or thin: near the pole those bins shrink to slivers (under 20
    # strand points), the envelope was NaN there and a card crossing the crown was never held under it (b24's crown
    # "plate": layer-1 card 133 arched front -> back over the top, 37% of its vertices on NaN bins, 1.5 cm2 standing
    # 3+ mm off, crownx.py). Uniform cells on the unit sphere (~6, then ~12 deg) have the same size everywhere.
    rad = np.maximum(np.linalg.norm(Q - C, axis=1), 1e-9)
    Uq = (Q - C) / rad[:, None]
    coarse = []
    for cells in (10.0, 5.0):
        kc = np.floor(Uq * cells).astype(np.int64) @ np.array([1, 1000, 1000000], np.int64)
        oc = np.argsort(kc)
        uc, sc_, cc = np.unique(kc[oc], return_index=True, return_counts=True)
        coarse.append((cells, {int(k): float(np.percentile(rad[oc][a:a + c], pct)) for k, a, c in zip(uc, sc_, cc) if c >= 20}))

    def f(P):
        k, r = key(P)
        e = np.array([env.get(int(x), np.nan) for x in k])
        bad = ~np.isfinite(e)
        if bad.any() and hair_clumps.ENV_FALLBACK:
            Pb = np.asarray(P, float)[bad] - C
            Ub = Pb / np.maximum(np.linalg.norm(Pb, axis=1), 1e-9)[:, None]
            eb = np.full(len(Ub), np.nan)
            for cells, tab in coarse:
                kb = np.floor(Ub * cells).astype(np.int64) @ np.array([1, 1000, 1000000], np.int64)
                eb = np.where(np.isfinite(eb), eb, np.array([tab.get(int(x), np.nan) for x in kb]))
            e[bad] = eb
        return e, r
    return f


def side_weight(P, C) -> np.ndarray:
    """1 on the head's sides (elevation over its centre under SIDE_EL[0]), 0 over the top (SIDE_EL[1]), smoothstep."""
    v = np.asarray(P, float) - np.asarray(C, float)
    el = np.degrees(np.arcsin(np.clip(v[:, 2] / np.maximum(np.linalg.norm(v, axis=1), 1e-9), -1, 1)))
    return _ss(np.clip((hair_clumps.SIDE_EL[1] - el) / (hair_clumps.SIDE_EL[1] - hair_clumps.SIDE_EL[0]), 0.0, 1.0))


def _under_envelope(c: dict, env, C, env_side=None) -> None:
    """Moves a head card's stations in toward the head's centre where it or its edges stand over the envelope (on the
    sides `env_side`, blended by side_weight)."""
    P, X, hw = c["P"], c["X"], np.asarray(c["hw"])
    over = np.zeros(len(P))
    for E in (P, P - X * hw[:, None], P + X * hw[:, None]):
        e, r = env(E)
        if env_side is not None:
            es, _ = env_side(E)
            w = side_weight(E, C)
            e = np.where(np.isfinite(es), (1 - w) * e + w * es, e)
        over = np.maximum(over, np.nan_to_num(r - (e - hair_clumps.ENV_UNDER), nan=0.0))
    if over.max() <= 0:
        return
    from scipy.ndimage import maximum_filter1d, gaussian_filter1d
    over = gaussian_filter1d(maximum_filter1d(over, 5), 1.5)
    c["P"] = P - _unit(P - np.asarray(C, float)) * over[:, None]


def crown_loops(St: dict, C) -> np.ndarray:
    """Strands rooted over the crown (FLY_CROWN over the head's centre) that loop: chord < CROWN_LOOP x length."""
    out = np.zeros(len(St["len"]), bool)
    if hair_clumps.CROWN_LOOP <= 0:
        return out
    for j in np.nonzero(St["root"][:, 2] > float(np.asarray(C)[2]) + hair_clumps.FLY_CROWN)[0]:
        q = St["Q"][j][np.isfinite(St["Q"][j][:, 0])]
        out[j] = len(q) >= 3 and np.linalg.norm(q[-1] - q[0]) < hair_clumps.CROWN_LOOP * St["len"][j]
    return out


def layer_offset(sn, la: int, cls: str) -> np.ndarray:
    """A card's offset along its normal from its clump's centre line (m), per station: coverage under, mid at the
    clump, top over it (by the clump's spread `sn` along its normal; a head clump's spread capped at HEAD_SN_MAX)."""
    sn = np.asarray(sn, float)
    if cls == "tail":
        return sn * (-0.6, 0.4, 1.0)[min(la, 2)] + 0.0004 * la
    return np.minimum(sn, hair_clumps.HEAD_SN_MAX) * (-0.6 + 0.6 * la) + 0.0004 * la + (hair_clumps.HEAD_LIFT if cls == "head" else 0.0)


def _crown_fill(P, la: int, n_layers: int, env, C, s=None) -> np.ndarray:
    """A head card raised toward the strands' envelope over the top of the head (see CROWN_FILL)."""
    P = np.asarray(P, float)
    d = P - np.asarray(C, float)
    r = np.linalg.norm(d, axis=1)
    e, _ = env(P)
    el = np.degrees(np.arcsin(np.clip(d[:, 2] / np.maximum(r, 1e-9), -1, 1)))
    w = hair_clumps.CROWN_FILL * _ss(np.clip((el - hair_clumps.CROWN_EL) / 25.0, 0.0, 1.0))
    if hair_clumps.CROWN_LAYERS and (n_layers - 1 - la) not in hair_clumps.CROWN_LAYERS:
        return P
    if hair_clumps.CROWN_END > 0 and s is not None and len(s):
        s = np.asarray(s, float)
        w = w * _ss(np.clip((s[-1] - s) / hair_clumps.CROWN_END, 0.0, 1.0))
    if hair_clumps.CROWN_SEAT > 0 and s is not None and len(s) and P[0, 1] < float(np.asarray(C)[1]) + hair_clumps.CROWN_SEAT_Y:
        w = w * _ss(np.clip(np.asarray(s, float) / hair_clumps.CROWN_SEAT, 0.0, 1.0))
    tgt = np.nan_to_num(np.asarray(e, float), nan=0.0) - hair_clumps.ENV_UNDER - hair_clumps.CROWN_GAP * (n_layers - 1 - la)
    from scipy.ndimage import gaussian_filter1d
    up = gaussian_filter1d(np.maximum(0.0, tgt - r) * w, 1.5)
    return np.asarray(C, float) + d * ((r + up) / np.maximum(r, 1e-9))[:, None]


def _grade_fill(P, la: int, n_layers: int, env, env_g, C, s=None) -> np.ndarray:
    """(c13) A head card raised (never lowered) onto the GRADED envelope (GRADE_SLOPE) where it stands over the plain
    one, less ENV_UNDER and CROWN_GAP per layer under the top, eased in from the root over GRADE_SEAT."""
    P = np.asarray(P, float)
    d = P - np.asarray(C, float)
    r = np.linalg.norm(d, axis=1)
    e, _ = env(P)
    eg, _ = env_g(P)
    add = np.nan_to_num(np.asarray(eg, float) - np.asarray(e, float), nan=0.0)
    if add.max() <= 5e-4:
        return P
    w = np.clip(add / 0.002, 0.0, 1.0)
    if hair_clumps.GRADE_SEAT > 0 and s is not None and len(s):
        w = w * _ss(np.clip(np.asarray(s, float) / hair_clumps.GRADE_SEAT, 0.0, 1.0))
    tgt = np.nan_to_num(np.asarray(eg, float), nan=0.0) - hair_clumps.ENV_UNDER - hair_clumps.CROWN_GAP * (n_layers - 1 - la)
    from scipy.ndimage import gaussian_filter1d
    up = gaussian_filter1d(np.maximum(0.0, tgt - r) * w, 1.5)
    return np.asarray(C, float) + d * ((r + up) / np.maximum(r, 1e-9))[:, None]


def _root_seat(P, s, roots, C) -> np.ndarray:
    """A head card's stations within ROOT_SEAT of its root moved in toward the head's centre, the root itself to
    ROOT_SEAT_GAP over the median radius of its strands' roots (only ever lowered)."""
    P = np.asarray(P, float).copy()
    d = P - np.asarray(C, float)
    r = np.linalg.norm(d, axis=1)
    r0 = float(np.median(np.linalg.norm(np.asarray(roots, float) - np.asarray(C, float), axis=1))) + hair_clumps.ROOT_SEAT_GAP
    w = 1.0 - _ss(np.clip(np.asarray(s, float) / hair_clumps.ROOT_SEAT, 0.0, 1.0))
    rn = r - w * np.maximum(0.0, r - r0)
    return np.asarray(C, float) + d * (rn / np.maximum(r, 1e-9))[:, None]


def card_offset(c: dict, la: int, n_layers: int, cls: str, C) -> np.ndarray:
    """layer_offset, and on the head's sides (side_weight) the head's layers moved out TOGETHER until the top one lies
    on the clump's outer strands (c["out"]: the top layer alone moved out stood off the one under it, crownprobe: rays
    with a gap > 4 mm 13.8 -> 15.3%, backdrop between cards at the silhouette; together 14.3%)."""
    yo = layer_offset(c["sn"], la, cls)
    if cls == "head" and hair_clumps.SIDE_OUT_PCT > 0 and "out" in c:
        top_ = layer_offset(c["sn"], n_layers - 1, cls)
        yo = yo + side_weight(c["P"], C) * np.maximum(0.0, np.asarray(c["out"], float) - top_)
    elif cls == "tail" and hair_clumps.TAIL_OUT > 0 and "out" in c:  # the tail's layers out together toward its outer strands
        top_ = layer_offset(c["sn"], n_layers - 1, cls)
        yo = yo + hair_clumps.TAIL_OUT * np.maximum(0.0, np.asarray(c["out"], float) - top_)
    return yo
