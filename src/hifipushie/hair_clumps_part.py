"""The part: its roots, the cover over it, the crown's arch row, the part read from strands, where it shows. Part of hair clumps (hair_clumps.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_clumps
from .hair_clumps import _cen_of, _ss
from .hair_clumps_fit import envelope, fit

def _part_root(c: dict, side_of, C, gap: float | None = None) -> None:
    """A head card whose root lies within PART_ROOT_REACH of the part gets a lead-in: from the part's edge (PART_GAP
    off the line, at the root's height over the head) out sideways (away from the part), curving into the card's own
    start (Hermite). The per-station keys are extended with the root station's values."""
    P = np.asarray(c["P"], float)
    sd, dp = side_of(P[:1])
    sd, dp = float(sd[0]), float(dp[0])
    gap = hair_clumps.PART_GAP if gap is None else float(gap)
    if sd == 0 or not np.isfinite(dp) or dp > hair_clumps.PART_ROOT_REACH or dp < gap + 0.003:
        return
    C = np.asarray(C, float)
    r0 = P[0] - C
    rad = np.linalg.norm(r0)
    nr = r0 / max(rad, 1e-9)
    e = np.array([sd, 0.0, 0.0]) - nr * sd * nr[0]
    if np.linalg.norm(e) < 0.2:
        return
    e /= np.linalg.norm(e)
    R = P[0] - e * (dp - gap)
    R = C + (R - C) / np.linalg.norm(R - C) * rad
    L = float(np.linalg.norm(P[0] - R))
    m = int(np.ceil(L / hair_clumps.STEP))
    if m < 1:
        return
    T0 = np.asarray(c["T"], float)[0]
    t = np.arange(m)[:, None] / m
    h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
    Q = h00 * R + h10 * e * L + h01 * P[0] + h11 * T0 * L
    Pn = np.concatenate([Q, P])
    Tn = np.gradient(Pn, axis=0)
    Tn /= np.maximum(np.linalg.norm(Tn, axis=1, keepdims=True), 1e-12)
    N0 = np.asarray(c["N"], float)[0]
    X0 = np.asarray(c["X"], float)[0]
    Xq = np.cross(np.repeat(N0[None], m, 0), Tn[:m])
    Xq /= np.maximum(np.linalg.norm(Xq, axis=1, keepdims=True), 1e-12)
    Xq *= np.sign((Xq @ X0)[:, None] + 1e-12)
    n = len(P)
    for k_ in ("N", "bend", "hw", "sn", "u", "share", "out", "rad"):
        v = c.get(k_)
        if np.ndim(v) and len(v) == n:
            v = np.asarray(v)
            c[k_] = np.concatenate([np.repeat(v[:1], m, 0), v])
    c["P"], c["T"] = Pn, Tn
    c["X"] = np.concatenate([Xq, np.asarray(c["X"], float)])
    seg = np.linalg.norm(np.diff(Pn, axis=0), axis=1)
    c["s"] = np.concatenate([[0.0], np.cumsum(seg)])
    c["i0"] = max(0, int(c["i0"]) - m)
    c["part_root"] = m


def part_cover(St: dict, C, side_of, env, idx, seed: int = 0) -> list:
    """The part's cover row (see PART_COVER): per side, the head strands `idx` rooted within COVER_REACH of the part
    (over PART_EL) split into PART_COVER runs along it (by root y, front to back); each run is one card fitted to its
    strands, cut to COVER_LEN, led in from COVER_OVER past the part line (_part_root), raised from its root to the
    strands' envelope less COVER_UNDER, tapered (COVER_TAPER). Cards are head cards of the top layer with "cover"."""
    if not hair_clumps.PART_COVER or side_of is None or not len(idx):
        return []
    from scipy.ndimage import gaussian_filter1d
    C = np.asarray(C, float)
    if hair_clumps.COVER_PCT != hair_clumps.ENV_PCT:
        env = envelope(St, C, pct=hair_clumps.COVER_PCT)
    root = St["root"][idx]
    sd, dp = side_of(root)
    v = root - C
    el = np.degrees(np.arcsin(np.clip(v[:, 2] / np.maximum(np.linalg.norm(v, axis=1), 1e-9), -1, 1)))
    ok = (sd != 0) & np.isfinite(dp) & (dp < hair_clumps.COVER_REACH) & (el > hair_clumps.PART_EL)
    top = len(hair_clumps.LAYERS["head"]) - 1
    rng = np.random.default_rng(seed + 53)
    out = []
    for s_ in (-1.0, 1.0):
        mem_all = idx[ok & (sd == s_)]
        if len(mem_all) < hair_clumps.MIN_STRANDS * 2:
            continue
        n_ = max(1, min(int(hair_clumps.PART_COVER), len(mem_all) // hair_clumps.MIN_STRANDS))
        y = St["root"][mem_all][:, 1]
        q = np.quantile(y, np.linspace(0, 1, n_ + 1))
        for b in range(n_):
            mem = mem_all[(y >= q[b]) & ((y < q[b + 1]) if b < n_ - 1 else (y <= q[b + 1]))]
            if len(mem) < hair_clumps.MIN_STRANDS:
                continue
            c = fit(St["Q"][mem], _cen_of(C, None), end_share=0.35, max_hw=hair_clumps.COVER_HW, spread=90.0, reference=True,
                    tip_taper=0.0)
            if c is None:
                continue
            n = len(c["P"])
            k1 = int(np.searchsorted(np.asarray(c["s"], float), hair_clumps.COVER_LEN)) + 1
            if k1 < n:
                for k_ in ("P", "T", "N", "X", "bend", "hw", "sn", "u", "share", "out", "rad", "s"):
                    if np.ndim(c.get(k_)) and len(c[k_]) == n:
                        c[k_] = np.asarray(c[k_])[:k1]
            if len(c["P"]) < 4:
                continue
            _part_root(c, side_of, C, gap=-hair_clumps.COVER_OVER)
            P = np.asarray(c["P"], float)
            P_fit = P  # (round 35) its picture baked on the fitted line, its share over its own length (r34's arch fix:
            # a 7 cm card over 30 cm strands drew no strand, an EMPTY tile)
            s = np.asarray(c["s"], float)
            d = P - C
            r = np.linalg.norm(d, axis=1)
            e, _ = env(P)
            tgt = np.nan_to_num(np.asarray(e, float), nan=0.0) - hair_clumps.COVER_UNDER
            w = _ss(np.clip(s / hair_clumps.COVER_SEAT, 0.0, 1.0))
            up = gaussian_filter1d(np.maximum(0.0, tgt - r), 1.5) * w
            P = C + d * ((r + up) / np.maximum(r, 1e-9))[:, None]
            X, N = np.asarray(c["X"], float), np.asarray(c["N"], float)
            if hair_clumps.COVER_TILT:  # (see COVER_TILT) the across direction turned toward the outward radial
                Tn = np.asarray(c["T"], float)
                Ru = P - C
                Ru = Ru - (Ru * Tn).sum(1, keepdims=True) * Tn
                Ru /= np.maximum(np.linalg.norm(Ru, axis=1, keepdims=True), 1e-12)
                Xp = X - (X * Ru).sum(1, keepdims=True) * Ru
                Xp /= np.maximum(np.linalg.norm(Xp, axis=1, keepdims=True), 1e-12)
                ta = np.radians(hair_clumps.COVER_TILT)
                X = np.cos(ta) * Xp + np.sin(ta) * Ru
                Nn = np.cross(Tn, X)
                N = Nn * np.sign((Nn * N).sum(1, keepdims=True) + 1e-12)
                P = P - Ru * (hair_clumps.COVER_SINK * np.sin(ta) * np.asarray(c["hw"], float))[:, None]
            L = max(float(s[-1]), 1e-6)
            f = np.clip((s / L - (1.0 - hair_clumps.COVER_TAPER)) / hair_clumps.COVER_TAPER, 0.0, 1.0)
            hw = np.asarray(c["hw"], float) * (1.0 - (1.0 - hair_clumps.TIP_FLOOR) * _ss(f))
            lk_ = int(np.bincount(St["lock"][mem]).argmax())
            u = (c["i0"] * hair_clumps.STEP + s) / max(float(np.percentile(St["len"][mem], 95)), 0.02)
            out.append({"P": P, "X": X, "N": N, "T": c["T"], "bend": c["bend"], "hw": hw,
                        "rad": np.asarray(c["rad"], float) + up, "u": u, "s": s, "kind": "baked", "layer": top,
                        "cls": "head", "prio": top + 0.5 + 0.1 * rng.uniform(), "cval": 1.0, "value": 1.0,
                        "lock": lk_, "sn": c["sn"], "strands": mem, "draw": hair_clumps.COVER_DRAW, "s0": c["i0"] * hair_clumps.STEP,
                        "wisp": False, "edge": False, "cover": True, "P_fit": P_fit})
    return out


def arch_row(St: dict, C, idx, seed: int = 0, side_of=None) -> list:
    """The crown arch row (see ARCH): head strands `idx` rooted over ARCH_EL within ARCH_X of the centre line, split by
    root y into ARCH_ROWS rows and each by root x into ARCH runs; each run one card fitted to its strands, from
    ARCH_START to ARCH_LEN from their roots, raised to the strands' ARCH_PCT envelope less
    ARCH_UNDER (eased in over ARCH_SEAT), tapered (COVER_TAPER) and faded (COVER_FADE, "cover")."""
    if not hair_clumps.ARCH or not len(idx):
        return []
    from scipy.ndimage import gaussian_filter1d
    C = np.asarray(C, float)
    env = envelope(St, C, pct=hair_clumps.ARCH_PCT)
    R = St["root"][idx].astype(float) - C
    el = np.degrees(np.arcsin(np.clip(R[:, 2] / np.maximum(np.linalg.norm(R, axis=1), 1e-9), -1, 1)))
    ok = (el >= hair_clumps.ARCH_EL) & (np.abs(R[:, 0]) <= hair_clumps.ARCH_X)
    mem_all = idx[ok]
    if len(mem_all) < hair_clumps.MIN_STRANDS * 2:
        print(f"arch row: {len(mem_all)} strands in the strip: none", flush=True)
        return []
    yr, xr = R[ok, 1], R[ok, 0]
    # (r34 a4: a run by root x mixed strands sweeping +x and -x off the part: the card followed one, its picture's
    # strands lay 3-4 cm across it, an EMPTY tile) the way each strand leaves its root: +x, -x or back
    Qm = St["Q"][mem_all].astype(float)
    kk = min(Qm.shape[1] - 1, int(round(0.025 / hair_clumps.STEP)))
    dv = Qm[:, kk] - Qm[:, 0]
    dv = np.where(np.isfinite(dv), dv, 0.0)
    sx = dv[:, 0] / np.maximum(np.linalg.norm(dv, axis=1), 1e-9)
    way = np.where(sx > 0.5, 1, np.where(sx < -0.5, -1, 0))
    if side_of is not None:  # (round 36) part-safe: the centre strip is used as one only behind the part's back end
        # (side_of's distance inf: no strand there shows a part); in front of it a run takes one side's strands, kept
        # PART_GAP off the part and not sweeping across it (a run over the part line spanned it: test_no_card_spans_the_part)
        sd_, dp_ = side_of(St["root"][mem_all])
        fr_ = np.isfinite(dp_)
        keep_ = ~fr_ | ((sd_ != 0) & (sx * sd_ > -0.5) & (dp_ >= hair_clumps.ARCH_PART_KEEP * hair_clumps.PART_GAP))
        way = np.where(fr_, 3 * np.asarray(sd_, int) + way, way)  # a run per side AND sweep (back-running
        # strands by the part get their own run on each side: r36e grouped by side alone and the cards bent away, a V notch)
        print(f"arch row: {int(fr_.sum())} strands in front of the part's back end ({int((fr_ & ~keep_).sum())} at or "
              f"across the part dropped)", flush=True)
        mem_all, yr, xr, way = mem_all[keep_], yr[keep_], xr[keep_], way[keep_]
        if len(mem_all) < hair_clumps.MIN_STRANDS * 2:
            return []
    way_of = dict(zip(mem_all.tolist(), way.tolist()))
    way_of = np.array([way_of.get(i, 0) for i in range(int(mem_all.max()) + 1)]) if len(mem_all) else np.zeros(1, int)
    nr = max(1, int(hair_clumps.ARCH_ROWS))
    qy = np.quantile(yr, np.linspace(0, 1, nr + 1))
    groups = []
    for a_ in range(nr):
        iy = (yr >= qy[a_]) & ((yr < qy[a_ + 1]) if a_ < nr - 1 else (yr <= qy[a_ + 1]))
        for w_ in range(-4, 5):
            iw = iy & (way == w_)
            if iw.sum() < hair_clumps.MIN_STRANDS * 2:
                continue
            n_ = max(1, min(int(hair_clumps.ARCH), int(iw.sum()) // (hair_clumps.MIN_STRANDS * 4)))
            qx = np.quantile(xr[iw], np.linspace(0, 1, n_ + 1))
            for b in range(n_):
                groups.append((a_, mem_all[iw & (xr >= qx[b]) & ((xr < qx[b + 1]) if b < n_ - 1 else (xr <= qx[b + 1]))]))
    top = len(hair_clumps.LAYERS["head"]) - 1
    rng = np.random.default_rng(seed + 59)
    out = []
    for row_, mem in groups:
        if len(mem) < hair_clumps.MIN_STRANDS:
            continue
        c = fit(St["Q"][mem], _cen_of(C, None), end_share=0.35, max_hw=hair_clumps.ARCH_HW, spread=90.0, reference=True,
                tip_taper=0.0)
        if c is None:
            continue
        P = np.asarray(c["P"], float)
        s = np.asarray(c["s"], float)
        st0 = c["i0"] * hair_clumps.STEP
        k0 = int(np.searchsorted(s + st0, hair_clumps.ARCH_START))
        if side_of is not None and abs(int(np.median(way_of[mem]))) >= 2:  # (round 36) in front of the part's back
            # end: the card starts PART_GAP off the part (its strands' roots by the part line are cut, as head cards')
            _, dc_ = side_of(P)
            ok_ = np.nonzero(dc_ >= (hair_clumps.ARCH_PART_GAP if hair_clumps.ARCH_PART_GAP > 0 else hair_clumps.PART_GAP))[0]
            k0 = max(k0, int(ok_[0]) if len(ok_) else len(P))
        k1 = int(np.searchsorted(s + st0, hair_clumps.ARCH_LEN)) + 1
        if k1 - k0 < 6:
            continue
        n = len(P)
        for k_ in ("P", "T", "N", "X", "bend", "hw", "sn", "u", "share", "out", "rad"):
            if np.ndim(c.get(k_)) and len(c[k_]) == n:
                c[k_] = np.asarray(c[k_])[k0:k1]
        c["i0"] += k0
        s = s[k0:k1] - s[k0]
        P = np.asarray(c["P"], float)
        d = P - C
        r_ = np.linalg.norm(d, axis=1)
        e, _ = env(P)
        tgt = np.nan_to_num(np.asarray(e, float), nan=0.0) - hair_clumps.ARCH_UNDER
        seat_ = hair_clumps.ARCH_SEAT_FRONT if (hair_clumps.ARCH_FILL and row_ == 0) else hair_clumps.ARCH_SEAT
        w = _ss(np.clip(s / seat_, 0.0, 1.0))
        up = gaussian_filter1d(np.maximum(0.0, tgt - r_), 1.5) * w
        P_fit = P
        P = C + d * ((r_ + up) / np.maximum(r_, 1e-9))[:, None]
        L = max(float(s[-1]), 1e-6)
        f = np.clip((s / L - (1.0 - hair_clumps.COVER_TAPER)) / hair_clumps.COVER_TAPER, 0.0, 1.0)
        hw = np.asarray(c["hw"], float) * (1.0 - (1.0 - hair_clumps.TIP_FLOOR) * _ss(f))
        if hair_clumps.ARCH_ROOT_TAPER > 0 and row_ == 0:  # (round 36) the front row's root end narrowed to a point over its first
            # ARCH_ROOT_TAPER: its square root ends, seen end-on at 3/4, were a blocky ridged lump at the crown's front (f1)
            hw = hw * (hair_clumps.TIP_FLOOR + (1.0 - hair_clumps.TIP_FLOOR) * _ss(np.clip(s / hair_clumps.ARCH_ROOT_TAPER, 0.0, 1.0)))
        lk_ = int(np.bincount(St["lock"][mem]).argmax())
        u = (c["i0"] * hair_clumps.STEP + s) / max(float(np.percentile(St["len"][mem], 95)), 0.02)
        out.append({"P": P, "X": c["X"], "N": c["N"], "T": c["T"], "bend": c["bend"], "hw": hw,
                    "rad": np.asarray(c["rad"], float) + up, "u": u, "s": s, "kind": "baked", "layer": top,
                    "cls": "head", "prio": top + 0.6 + 0.1 * rng.uniform(), "cval": 1.0, "value": 1.0,
                    "lock": lk_, "sn": c["sn"], "strands": mem, "draw": hair_clumps.COVER_DRAW, "s0": c["i0"] * hair_clumps.STEP,
                    "wisp": False, "edge": False, "cover": True, "arch": True, "P_fit": P_fit, "row": row_})
    print(f"arch row: {len(mem_all)} strands in the strip -> {len(out)} cards", flush=True)
    return out


def strand_part(St: dict, C):
    """The parting as the strands show it: head strands rooted over the top whose first PART_REACH runs sideways (x
    share >= PART_SIDEWAYS) vote their side (sign of x); a function points -> (side, distance m to the part) like
    hair.part_side_of: side = the nearest voting roots' majority, distance = half the gap between the nearest root of
    the other side and the nearest of its own; points far from every voting root get side 0, distance inf."""
    from scipy.spatial import cKDTree
    C = np.asarray(C, float)
    head = np.nonzero(St["cls"] == "head")[0]
    Q = St["Q"][head].astype(float)
    k = max(1, int(round(hair_clumps.PART_REACH / hair_clumps.STEP)))
    p0 = Q[:, 0]
    fin = np.isfinite(Q[..., 0])
    last = np.minimum(k, fin.sum(1) - 1)
    pk = Q[np.arange(len(Q)), np.maximum(last, 0)]
    d = pk - p0
    v = p0 - C
    el = np.degrees(np.arcsin(np.clip(v[:, 2] / np.maximum(np.linalg.norm(v, axis=1), 1e-9), -1, 1)))
    xs = d[:, 0] / np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    ok = np.isfinite(xs) & (el > hair_clumps.PART_EL) & (np.abs(xs) >= hair_clumps.PART_SIDEWAYS) & (last > 0)
    if ok.sum() < 20 or (xs[ok] > 0).sum() < 10 or (xs[ok] < 0).sum() < 10:
        return None
    R, sd = p0[ok], np.sign(xs[ok])
    tp, tn = cKDTree(R[sd > 0]), cKDTree(R[sd < 0])
    print(f"strand part: {int((sd > 0).sum())} roots sweep +x, {int((sd < 0).sum())} -x (of {len(head)} head strands)",
          flush=True)

    def f(P):
        P = np.asarray(P, float)
        dp, _ = tp.query(P)
        dn, _ = tn.query(P)
        side = np.where(dp < dn, 1.0, -1.0)
        dist = np.abs(dn - dp) / 2
        far = np.minimum(dp, dn) > 0.02
        return np.where(far, 0.0, side), np.where(far, np.inf, dist)
    return f


def part_visible(St: dict, C, side_of):
    """`side_of` limited to where the groom SHOWS its part: points -> (side, distance), the distance inf where the
    groom's outline seen ALONG the part (one view: up = the mean radial direction over the part-line roots, across = x
    in that plane; the highest head strand point in each PART_DIP_R band across) has no notch PART_DIP at the part line
    against PART_DIP_W either side. An empty band over the part line with hair either side is a gap: shown. Where
    nothing can be measured the part counts. `f.dip(points)` -> the notch m at the part-line points nearest them (inf =
    gap, NaN = off the part)."""
    C = np.asarray(C, float)
    Q = St["Q"][St["cls"] == "head"][:, ::2].reshape(-1, 3)
    Q = Q[np.isfinite(Q[:, 0])].astype(float) - C
    sd0, d0 = side_of(St["root"][St["cls"] == "head"])
    R0 = St["root"][St["cls"] == "head"][np.isfinite(d0) & (np.asarray(d0) < hair_clumps.PART_GAP)].astype(float) - C
    up = R0.mean(0) if len(R0) else np.array([0.0, 0.0, 1.0])
    up /= max(float(np.linalg.norm(up)), 1e-9)
    xt = np.array([1.0, 0.0, 0.0]) - up[0] * up
    xt /= max(float(np.linalg.norm(xt)), 1e-9)
    a, h = Q @ xt, Q @ up
    lo = float(a.min()) if len(a) else 0.0
    nb = int((float(a.max()) - lo) / hair_clumps.PART_DIP_R) + 1 if len(a) else 1
    top = np.full(nb, -np.inf)
    if len(a):
        np.maximum.at(top, ((a - lo) / hair_clumps.PART_DIP_R).astype(int), h)
    top[~np.isfinite(top)] = np.nan

    def outline(x):
        k = np.floor((np.asarray(x, float) - lo) / hair_clumps.PART_DIP_R).astype(int)
        return np.where((k >= 0) & (k < nb), top[np.clip(k, 0, nb - 1)], np.nan)

    def notch_at(ap):
        hc, ha, hb = outline(ap), outline(ap + hair_clumps.PART_DIP_W), outline(ap - hair_clumps.PART_DIP_W)
        hs = np.where(np.isfinite(ha) & np.isfinite(hb), 0.5 * (ha + hb), np.where(np.isfinite(ha), ha, hb))
        return np.where(np.isfinite(hc), hs - hc, np.where(np.isfinite(hs), np.inf, np.nan))
    tree, notch0 = None, None
    if len(R0):
        from scipy.spatial import cKDTree
        on0 = np.isfinite(d0) & (np.asarray(d0) < hair_clumps.PART_GAP)
        notch0 = notch_at(R0 @ xt - np.asarray(sd0, float)[on0] * np.asarray(d0, float)[on0])
        if hair_clumps.PART_DIP_WHOLE and (~np.isnan(notch0)).any():
            # (round 38) ONE notch for the whole part: the outline is a single view along it, so roots differ only by
            # where the part line sits across it (a few mm), and per root the notch was noise around the threshold
            # (Tess: p50 1-2 mm; >= 3 mm at 114 / 0 / 389 of 1129 roots for strand points every 2nd / 4th / 8th:
            # t38/np3.py). The median over the part-line roots is stable (1.8 / 1.2 / 2.3 mm).
            m_ = notch0[~np.isnan(notch0)]
            notch0 = np.full(len(notch0), float(np.median(m_)))
        tree = cKDTree(R0)

    def dip(P, sd=None, dist=None):
        P = np.asarray(P, float)
        if sd is None:
            sd, dist = side_of(P)
        sd, dist = np.asarray(sd, float), np.asarray(dist, float)
        out = np.full(len(P), np.nan)
        fin = np.isfinite(dist) & (dist <= hair_clumps.PART_DIP_REACH)
        if not fin.any():
            return out
        if tree is not None:  # the notch at the nearest part-line root (side_of's distance is half a gap between
            # roots, not a length to step across: stepped from roots 2-3 cm off, r37a read notches beside the part)
            out[fin] = notch0[tree.query(P[fin] - C)[1]]
        else:
            out[fin] = notch_at((P[fin] - C) @ xt - sd[fin] * dist[fin])
        return out

    def f(P):
        P = np.asarray(P, float)
        sd, dist = side_of(P)
        dp = dip(P, sd, dist)
        shown = ~(np.isfinite(dp) & (dp < hair_clumps.PART_DIP))  # unmeasured (bare both sides, off the reach) counts as shown
        return sd, np.where(shown, dist, np.inf)
    f.dip = dip
    f.view = (up, xt)
    return f
