"""Cards from the strands themselves: the strand grid, a clump, clump_cards, far flyaways, pooled singles. Part of hair cards (hair_cards.py has the overview)."""
from __future__ import annotations

import hashlib

import numpy as np

from . import hair_cards
from .hair_cards import _ss, _unit
from .hair_cards_mesh import spine

def strand_grid(D: dict, locks: list, n: int = hair_cards.GRID) -> dict:
    """The groom's lock strands (not the scalp layer) on a common grid: every strand resampled at `n` stations of
    its LOCK's parameter (NaN where the strand hasn't started or has ended: roots are staggered, tips ragged), so
    strands of one clump can be averaged station by station. {"A" (strands, n, 3), "lock", "sub", "rand", "free"}."""
    from scipy.spatial import cKDTree
    names = [str(x) for x in D["names"]]
    first = np.r_[0, np.cumsum(D["counts"])]
    U = np.linspace(0.0, 1.0, n)
    trees = {}
    A, LK, SUB, RND = [], [], [], []
    for j in range(len(D["counts"])):
        if names[int(D["obj"][j])] not in ("hair_guides", "hair_guides_free", "hair_guides_wisp") or D["counts"][j] < 2:
            continue
        li = int(D["lock"][j])
        if li >= len(locks):
            continue
        if li not in trees:
            P, *_ = spine(locks[li], 96)
            trees[li] = cKDTree(P)
        Q = D["pts"][first[j]:first[j + 1]].astype(float)
        _, k = trees[li].query(Q[[0, -1]])
        u0, u1 = k[0] / 95.0, k[1] / 95.0
        if u1 - u0 < 0.05:
            continue
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        t = (U - u0) / (u1 - u0)
        ok = (t >= 0) & (t <= 1)
        a = np.full((n, 3), np.nan)
        if ok.sum() < 2:
            continue
        a[ok] = np.stack([np.interp(t[ok] * s[-1], s, Q[:, c]) for c in range(3)], 1)
        A.append(a)
        LK.append(li)
        SUB.append(int(D["sub"][j]))
        RND.append(float(D["rand"][j]))
    return {"A": np.asarray(A), "lock": np.asarray(LK, int), "sub": np.asarray(SUB, int), "rand": np.asarray(RND),
            "u": U}


def _transport(v, t0, t1):
    """v (normal to t0) carried to t1 by the smallest rotation taking t0 onto t1."""
    c = float(t0 @ t1)
    ax = np.cross(t0, t1)
    sn = float(np.linalg.norm(ax))
    if sn < 1e-9:
        return v if c > 0 else v
    ax = ax / sn
    return v * c + np.cross(ax, v) * sn + ax * float(ax @ v) * (1 - c)


def _nan_smooth(x, k: int = 2):
    out = x.copy()
    for i in range(len(x)):
        out[i] = np.nanmean(x[max(0, i - k):i + k + 1])
    return out


def _medoid_line(A, P, w: float):
    """P moved (share `w`) onto one of its clump's own long strands, the one nearest the mean: hanging hair's mean over
    strands of other phases is straight (a wavy tail's cards hung as straight sheets, its bottom curl lost: b23 back
    edge -33 mm at 150-180 mm, review "straight stringy sheets"); a real strand keeps the wave and the curl. Before the
    strand starts and past its end the offset is held (the line stays continuous)."""
    from scipy.ndimage import gaussian_filter1d
    fin = np.isfinite(A[..., 0])
    n = fin.sum(1)
    if not n.max():
        return P
    long_ = n >= np.percentile(n, 75)
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        dist = np.nanmean(np.linalg.norm(A - P[None], axis=-1), 1)
    dist = np.where(long_ & np.isfinite(dist), dist, np.inf)
    j = int(np.argmin(dist))
    f = fin[j]
    k = np.nonzero(f)[0]
    if len(k) < 4:
        return P
    D = np.zeros_like(P)
    D[k] = A[j, k] - P[k]
    D[:k[0]] = D[k[0]]
    D[k[-1] + 1:] = D[k[-1]]
    D = gaussian_filter1d(D, 1.0, axis=0)
    return P + w * D


def _clump(A, U, cen_of, min_share: float = 0.3, start_share: float = 0.04, end_share: float | None = None,
           medoid: float = 0.0, twist: float = 0.0, min_stations: int = 4):
    """A set of strands (m, n, 3 with NaN) as one clump: its centre line, frame and spread, over the stations where
    at least `min_share` of its strands run (`end_share`: on to the last station where that share still runs: hanging
    hair's ragged ends). None if too short."""
    with np.errstate(invalid="ignore"):
        cnt = np.isfinite(A[..., 0]).sum(0)
    ok = cnt >= max(1, int(np.ceil(min_share * len(A))))
    idx = np.nonzero(ok)[0]
    if len(idx) < min_stations:
        return None
    if end_share is not None:
        last = np.nonzero(cnt >= max(1, int(np.ceil(end_share * len(A)))))[0]
        if len(last) and last[-1] > idx[-1]:
            idx = np.r_[idx, np.arange(idx[-1] + 1, last[-1] + 1)]
    # a clump starts where its FIRST strands do (roots are staggered: the card's picture fades its root in; started
    # where a third of them run, the front row stood as a ledge 1.5 cm behind the hairline) and ends where few are left
    first = np.nonzero(cnt >= max(1, int(np.ceil(start_share * len(A)))))[0]
    idx = np.r_[first[0], idx] if first[0] < idx[0] else idx
    sl = slice(idx[0], idx[-1] + 1)
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        P = np.nanmean(A[:, sl], 0)
    if not np.isfinite(P).all():
        good = np.isfinite(P[:, 0])
        k = np.arange(len(P))
        P = np.stack([np.interp(k, k[good], P[good, c]) for c in range(3)], 1)
    # the mean jumps wherever a strand starts or ends: smoothed more where few strands run (a hanging tail's last 20%
    # kinked by 45-130 deg a station: crumpled paper ends, b12; head cards hooked at their staggered roots)
    from scipy.ndimage import gaussian_filter1d
    few = np.clip(1.0 - cnt[sl] / max(min_share * len(A), 1.0), 0.0, 1.0)[:, None]
    if len(P) > 4:
        # padded by carrying each end straight on (mode "nearest" squashed the last stations together: tiny segments,
        # random tangents at the ends)
        n_ = 12
        t0, t1 = P[0] - P[min(3, len(P) - 1)], P[-1] - P[-1 - min(3, len(P) - 1)]
        st_ = np.arange(1, n_ + 1)[:, None] / 3.0
        Pp = np.r_[P[0] + t0 * st_[::-1], P, P[-1] + t1 * st_]
        P = (gaussian_filter1d(Pp, 1.0, axis=0) * (1 - np.r_[few[:1].repeat(n_, 0), few, few[-1:].repeat(n_, 0)])
             + gaussian_filter1d(Pp, 4.0, axis=0) * np.r_[few[:1].repeat(n_, 0), few, few[-1:].repeat(n_, 0)])[n_:-n_]
    if medoid > 0 and len(A) > 1 and len(P) > 4:
        P = _medoid_line(A[:, sl], P, medoid)
    T = _unit(np.gradient(P, axis=0))
    cen = cen_of(P)
    out = _unit(P - cen)
    perp = out - (out * T).sum(-1, keepdims=True) * T
    # where the hair runs straight away from the head (into a tie, off a crown) "outward" says nothing about which
    # way a card faces: the frame is carried on from where it was sure (cards stood on edge round the tie as flaps)
    N = np.zeros_like(P)
    i0 = int(np.argmax(np.linalg.norm(perp, axis=1)))
    prev = _unit(perp[i0])
    for rng_ in (range(i0, len(P)), range(i0 - 1, -1, -1)):
        prev_ = prev
        j_ = i0
        for i in rng_:
            w = float(np.clip((np.linalg.norm(perp[i]) - 0.35) / 0.4, 0.0, 1.0))
            # carried by the turn of the flow (a rotation-minimising frame), not projected: where the hair rises
            # straight off the part T turns INTO the old normal and the projection was ~0, a random way: the cards
            # stood on edge over the part as planks
            pt = prev_ if j_ is None else _transport(prev_, T[j_], T[i])
            j_ = i
            v = w * _unit(perp[i]) + (1 - w) * _unit(pt)
            N[i] = v / max(np.linalg.norm(v), 1e-9)
            prev_ = N[i]
    if twist > 0 and hair_cards.PCA_FRAME > 0 and len(A) > 2:  # hanging cards: turn the frame so the card's WIDTH lies along the
        # clump's widest spread (its cross-section's major axis) where that section is clearly flat. "Outward" from the core
        # made the tail's edge clumps face sideways, so from the back (and front) they were seen edge-on as thin dark
        # ribbons arching off the tie (round 22, b29 g1backl cards 230 / 299 / 345), where the groom shows a broad mass
        X0 = _unit(np.cross(T, N))
        with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
            __import__("warnings").simplefilter("ignore")
            d_ = A[:, sl] - P[None]
            a_, b_ = (d_ * X0[None]).sum(-1), (d_ * N[None]).sum(-1)
            ok_ = np.isfinite(a_) & np.isfinite(b_)
            a_, b_ = np.where(ok_, a_, 0.0), np.where(ok_, b_, 0.0)
            n_ok = np.maximum(ok_.sum(0), 1)
            ma, mb = a_.sum(0) / n_ok, b_.sum(0) / n_ok
            caa = (a_ * a_).sum(0) / n_ok - ma * ma
            cbb = (b_ * b_).sum(0) / n_ok - mb * mb
            cab = (a_ * b_).sum(0) / n_ok - ma * mb
        tr_ = np.maximum(caa + cbb, 1e-12)
        an_ = np.sqrt((caa - cbb) ** 2 + 4 * cab ** 2) / tr_  # 0 round .. 1 flat
        w_ = np.clip((an_ - 0.3) / 0.4, 0.0, 1.0) * (ok_.sum(0) >= 3)
        c2, s2 = gaussian_filter1d((caa - cbb) / tr_ * w_, 2.0), gaussian_filter1d(2 * cab / tr_ * w_, 2.0)
        th = 0.5 * np.arctan2(s2, c2)  # the major axis' angle from X0 (axial, smoothed as a doubled angle)
        th = th * hair_cards.PCA_FRAME * np.clip(gaussian_filter1d(w_.astype(float), 2.0) / 0.5, 0.0, 1.0)
        th = np.clip(th, -np.radians(hair_cards.PCA_MAX), np.radians(hair_cards.PCA_MAX))
        Xn = X0 * np.cos(th)[:, None] + N * np.sin(th)[:, None]
        Nn = _unit(np.cross(Xn, T))
        Nn = np.where(((Nn * N).sum(-1) < 0)[:, None], -Nn, Nn)
        N = Nn
    if twist > 0:  # the frame turns about the hair by at most `twist` rad per station: hanging hair's "outward" swings
        # round where the line curls past its core, a 60 mm tail card twisted half a turn in ~30 mm (b24 / b25 hanging/L0
        # card 201: the "folded flap" at the tail's end, 10-11 folded triangle pairs, crownx.py)
        for rng_ in (range(i0 + 1, len(P)), range(i0 - 1, -1, -1)):
            for i in rng_:
                j = i - 1 if rng_.step == 1 else i + 1
                pt = _unit(_transport(N[j], T[j], T[i]))
                pt = _unit(pt - (pt @ T[i]) * T[i])
                a = float(np.arctan2(np.cross(pt, N[i]) @ T[i], pt @ N[i]))
                if abs(a) > twist:
                    b = np.sign(a) * twist
                    N[i] = pt * np.cos(b) + np.cross(T[i], pt) * np.sin(b)
    X = _unit(np.cross(T, N))
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        d = A[:, sl] - P[None]
        dx, dn = (d * X[None]).sum(-1), (d * N[None]).sum(-1)
        sx, sn = np.nanstd(dx, 0), np.nanstd(dn, 0)
        mx = np.nanmedian(dx, 1)  # each strand's side of the clump
    sx, sn = np.nan_to_num(sx), np.nan_to_num(sn)
    return {"P": P, "T": T, "N": N, "X": X, "sx": _nan_smooth(sx), "sn": _nan_smooth(sn), "u": U[sl], "mx": mx,
            "bend": out, "rad": np.linalg.norm(P - cen, axis=1), "share": cnt[sl] / max(len(A), 1), "i0": int(idx[0])}


def clump_cards(D: dict, locks: list, C, S: dict, look: dict | None = None, seed: int = 0) -> list:
    """Cards cut from the groom's own STRANDS (what the card tools do: cluster strands into clumps, a few cards a
    clump, layered by opacity): each card's centre line is the mean of its clump's strands, so cards wave, part and
    end where the strands do, and its width is their spread. `S["group"]`: how big a clump is: "sub" (the groom's
    sub clumps: a hero), "pair" (two sub clumps), "lock" (a whole lock: fewer, wider cards), "free" (locks off the
    head only: the cap carries the rest). A clump wider than `card_width` is cut across into slices, each its own
    card on its own strands. Layers: 0 = coverage (dense tile, just under the clump's middle), 1 = medium over it,
    2+ = sparse break-up; a hero also gets single fly-away strands. Card dicts as _lock_cards'."""
    from .hair_strands import is_gather
    look = look or {}
    G = strand_grid(D, locks)
    if not len(G["A"]):
        return []
    rng = np.random.default_rng(seed + 3)
    group = str(S.get("group", "sub"))
    L = max(1, int(S["layers"]))
    cw = float(S["card_width"])
    vary = float(look.get("vary", 0.25))
    Rr = float(S["random"])
    C = np.asarray(C, float)
    out = []
    pool = [int(li) for li in np.unique(G["lock"]) if is_single(locks[int(li)])] if S.get("pool_singles", True) else []
    for li in np.unique(G["lock"]):
        lk = locks[int(li)]
        free = float(lk.get("free", 0.0)) > 0.5
        if group == "free" and not free:
            continue
        if int(li) in pool:
            continue
        if int(lk.get("hairs") or 0) > 0 and not lk.get("face") and not halo_card_ok(lk, C):
            continue  # (a few single hairs rooted in the mass over the crown (off_head): cut as wisps they stood 2-3 cm
            # over it at LOD1-3, round 29; the hero gives them no card either)
        sel = G["lock"] == li
        A, sub = G["A"][sel], G["sub"][sel]
        core = lk.get("core")
        if core is not None and len(core) >= 2:
            K = np.asarray(core, float)

            def cen_of(P, K=K):
                a, b = K[:-1], K[1:]
                ab = b - a
                tt = np.clip(((P[:, None] - a[None]) * ab[None]).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12)[None], 0, 1)
                near = a[None] + tt[..., None] * ab[None]
                return near[np.arange(len(P)), np.linalg.norm(P[:, None] - near, axis=-1).argmin(1)]
        else:
            def cen_of(P):
                return C[None]
        lrng = np.random.default_rng(int(hashlib.md5(lk["name"].encode()).hexdigest()[:8], 16))
        val = 1 + vary * 0.8 * (lrng.uniform() - 0.5)
        if group == "sub":
            keys = sub
        elif group == "pair":
            keys = sub // 2
        else:
            keys = np.zeros(len(sub), int)
        edge = bool(lk.get("at_hairline"))
        gather = is_gather(lk)
        fine = not free and float((lk.get("strands") or {}).get("fine", 0.0) or 0.0) >= hair_cards.FINE_SPARSE  # (hanging hair
        # drawn fine, a tail, still has a body to cover)
        for kk in np.unique(keys):
            Ag = A[keys == kk]
            c0 = _clump(Ag, G["u"], cen_of, end_share=hair_cards.FREE_END if free else None)
            if c0 is None:
                continue
            width = 2 * 1.7 * float(np.percentile(c0["sx"], 75))
            na = max(1, int(np.ceil(width / cw)))
            if free and hair_cards.TAIL_SPLIT_CW > 0 and cw > hair_cards.TAIL_SPLIT_MIN and float(lk["inputs"]["Width"]) >= 0.016:
                wo = 2 * hair_cards.FREE_SPREAD * float(np.percentile(c0["sx"], 75))  # (round 32) by its outline's width
                na = max(na, min(int(np.ceil(wo / (hair_cards.TAIL_SPLIT_CW * cw))), max(1, len(Ag) // 4)))
            order = np.argsort(c0["mx"])
            for j in range(na):
                part = Ag[order[j * len(order) // na:(j + 1) * len(order) // na]] if na > 1 else Ag
                if len(part) < 1:
                    continue
                c = _clump(part, G["u"], cen_of, end_share=hair_cards.FREE_END if free else None) if na > 1 else c0
                if c is None:
                    continue
                s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(c["P"], axis=0), axis=1))]
                if s[-1] < 0.01:
                    continue
                # (cards overlap their neighbours by a third: where they only met, every seam was a slit of shadow)
                # hanging hair is its OUTLINE: a tail's outer strands stand 3 sigma off the clump's mean (at 2.5 sigma,
                # clipped to 0.9 card widths, Tess's tail was 75 % of the strands' width)
                hw_full = np.clip((hair_cards.FREE_SPREAD if free else 2.5) * c["sx"], 0.003, (hair_cards.FREE_CLIP if free else 0.9) * cw)
                thin = free and float(lk["inputs"]["Width"]) < 0.016  # (a wisp: a lock of a few hairs off the head)
                # a wisp of 8+ hairs (Tess's face-framing locks: 9-16 hairs, 12-19 cm) reads as a light BUNDLE in the
                # strands: its first card wears the sparse tile (on the fly tile alone it was two or three grey wires)
                bundle = thin and int(lk.get("hairs") or 0) >= 8
                if thin:  # a wisp is a few hairs: a narrow card that runs out to a point (at full width an alpha
                    # test at any distance fills it: a brown slat down the cheek)
                    hw_full = (np.clip(1.4 * c["sx"], 0.002, 0.005) if bundle else np.clip(1.4 * c["sx"], 0.0012, 0.0025)) \
                        * (1 - 0.5 * _ss((s / s[-1] - 0.5) / 0.5))
                if free and not thin and hair_cards.TAIL_ROOT_HW > 0 and lk.get("tier") == "tie":  # (round 31) a tied tail's card
                    # leaves the band narrow: at full width (20-30 mm half widths at LOD1-3) its flat root corners stood
                    # 15-29 mm up off the round tie, thin spikes over it at 3/4 (LOD0's sub-clump cards are narrow there)
                    hw_full = hw_full - (hw_full - np.minimum(hw_full, hair_cards.TAIL_ROOT_HW)) * (1 - _ss(s / hair_cards.TAIL_ROOT_TAPER))
                if gather:  # into the tie a card runs out to nothing (its square end stood over the crown)
                    hw_full = hw_full * (1 - 0.5 * _ss((s / s[-1] - 0.8) / 0.2))  # (to nothing, 0.85, the tie's band
                    # showed between them: a black blob the strands hide)
                off_c = abs((j + 0.5) / na - 0.5) * 2 if na > 1 else 0.0
                nl = (3 if L > 2 else 2) if thin else L
                for la in range(nl):
                    if thin:  # a wisp: two or three thin cards of separate hairs side by side, never a filled
                        kind = "sparse" if (bundle and la == 0) else "fly"  # ribbon (under an alpha test: a dark slash)
                    elif fine:  # a lock the strands draw FINE (part rows, the rim: see-through hair): never the dense
                        kind = "sparse"  # tile (Tess's part rows rose off the part as opaque planks: the "fan" at the part)
                    elif la == 0:
                        kind = "hairline" if (edge and not free) else "dense"
                    else:
                        # hair lying on the head is a combed, closed surface: its second layer is dense too (over a
                        # medium one the layer under it showed through as dark chop), on the tile whose ROOTS come in
                        # one by one (the dense tile starts as a cut edge: under an alpha test every staggered card
                        # root drew a line across the flow, a brick pattern); loose hair opens up sooner
                        kind = ("hairline" if (la == 1 and not free and L > 2) else "medium") if (la <= 2 - int(free) and not thin) else "sparse"
                    yo = c["sn"] * (-0.3 + 0.4 * la) + (0.0003 * la)  # (layers lie close: lifted, each cast a shadow line)
                    xo = (rng.uniform(-0.35, 0.35) * hw_full if la > 0 else 0.0)
                    if thin:  # (a bundle's cards spread as its hairs do: at 0.9 card widths apart its 9-16 hairs,
                        # splayed over 2-3 cm, were three wires side by side)
                        xo = (la - (nl - 1) / 2) * (np.maximum(0.9 * hw_full, 1.3 * c["sx"]) if bundle else 0.9 * hw_full) \
                            + rng.uniform(-0.2, 0.2) * hw_full
                    hw = hw_full * (1.0 if la == 0 else 0.9)
                    u0 = 0.0 if la == 0 else Rr * rng.uniform(0.0, 0.25)
                    u1 = 1.0 if (la == 0 or gather) else 1.0 - float(S["tips"]) * Rr * rng.uniform(0.0, 0.2)
                    if edge and la > 0:
                        u0 = max(u0, min(0.3, 0.02 / max(s[-1], 1e-6)))
                    f = (s / s[-1])
                    keep = (f >= u0 - 1e-9) & (f <= u1 + 1e-9)
                    if keep.sum() < 3:
                        continue
                    P = c["P"] + c["X"] * (np.zeros(len(s)) + xo)[:, None] + c["N"] * yo[:, None]
                    out.append({"P": P[keep], "X": c["X"][keep], "N": c["N"][keep], "hw": hw[keep], "u": c["u"][keep],
                                "s": s[keep], "kind": kind, "layer": la,
                                "prio": (0.3 * la if bundle else la) + 0.3 * off_c + (0.25 if (thin and la > 0) else 0.0),
                                "cval": 1 + Rr * rng.uniform(-0.2, 0.2), "bend": c["bend"][keep], "T": c["T"][keep],
                                "lock": lk["name"], "value": val, "sn": np.asarray(c["sn"])[keep] if np.ndim(c["sn"]) else c["sn"],
                                "wisp": bool(bundle), "fine": bool(fine)})
            nf = int(S.get("fly", 0))
            if nf and not gather and len(Ag) >= 6:  # single strands that stand off the clump: a card each
                with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
                    __import__("warnings").simplefilter("ignore")
                    i0 = c0["i0"]
                    far = np.nanmax(np.linalg.norm(Ag[:, i0:i0 + len(c0["P"])] - c0["P"][None], axis=-1), 1)
                far = np.nan_to_num(far)
                lim = max(3.0 * float(np.median(c0["sx"])), 0.004)
                for i in np.argsort(-far)[:nf]:
                    if far[i] < lim:
                        break
                    Q = Ag[i]
                    okq = np.isfinite(Q[:, 0])
                    if okq.sum() < 5:
                        continue
                    Pq = Q[okq]
                    Tq = _unit(np.gradient(Pq, axis=0))
                    cq = cen_of(Pq)
                    oq = _unit(Pq - cq)
                    Nq = _unit(oq - (oq * Tq).sum(-1, keepdims=True) * Tq)
                    sq = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Pq, axis=0), axis=1))]
                    out.append({"P": Pq, "X": _unit(np.cross(Tq, Nq)), "N": Nq, "hw": np.full(len(Pq), 0.004),
                                "u": G["u"][okq], "s": sq, "kind": "fly", "layer": L, "prio": L + 1.0,
                                "cval": 1.0, "bend": oq, "T": Tq, "lock": lk["name"], "value": val})
    if pool:
        out += pooled_singles(G, locks, pool, C, L, rng)
    if hair_cards.FLY_FAR_TIERS and out:
        out = drop_far_fly(out, G, locks)
    return out


def drop_far_fly(cards: list, G: dict, locks: list) -> list:
    """Fly cards (not face-framing) whose centre line stands further than hair_clumps.FLY_FAR off the strands of the
    locks that aren't few single hairs (the hero's rule for its single hairs: hair_clumps FLY_FAR)."""
    from scipy.spatial import cKDTree
    from .hair_clumps import FLY_FAR
    few = np.array([int(lk.get("hairs") or 0) > 0 and not lk.get("face") for lk in locks] + [False])
    rest = ~few[np.clip(np.asarray(G["lock"]).astype(int), 0, len(few) - 1)]
    Q = np.asarray(G["A"], float)[rest].reshape(-1, 3)
    Q = Q[np.isfinite(Q[:, 0])]
    if not len(Q):
        return cards
    tr = cKDTree(Q[:: max(1, len(Q) // 200000)])
    face = {lk["name"] for lk in locks if lk.get("face")}
    return [c for c in cards if c["kind"] != "fly" or c.get("lock") in face
            or float(tr.query(np.asarray(c["P"], float))[0].max()) <= FLY_FAR]


def is_single(lk: dict) -> bool:
    """A lock of a few single hairs lying on the head hair (a halo, escaped hairs): not face-framing, not a tail's."""
    return int(lk.get("hairs") or 0) > 0 and not lk.get("face") and not lk.get("off_head")


def halo_card_ok(lk: dict, C) -> bool:
    """The hero's rules for which single hairs get a card (hair_clumps FLY_CROWN / FLY_CROWN_FREE / FLY_STRAIGHT), for
    every tier: none rooted over the crown (a few single hairs there stood 1-3 cm over it as dark strokes on LOD1-3
    only, round 29: the hero leaves them to the strands' look), none that loop (cards read them as stiff arcs)."""
    from .hair_clumps import FLY_CROWN, FLY_CROWN_FREE, FLY_STRAIGHT
    P = np.asarray(lk["pts"], float)
    if len(P) < 2 or P[0, 2] > float(np.asarray(C)[2]) + (FLY_CROWN_FREE if lk.get("off_head") else FLY_CROWN):
        return False
    L = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
    return L > 0 and float(np.linalg.norm(P[-1] - P[0])) >= FLY_STRAIGHT * L


def pooled_singles(G: dict, locks: list, pool: list, C, L: int, rng) -> list:
    """Single-hair locks clustered by where they run (root, middle, end), SINGLES_PER_CARD a cluster, each cluster ONE
    fly card along its hairs' mean path: the halo as a few cards standing where the hairs stand."""
    from scipy.cluster.vq import kmeans2
    C = np.asarray(C, float)
    pool = [li for li in pool if halo_card_ok(locks[li], C)]
    if not pool:
        return []
    feats = []
    for li in pool:
        P = np.asarray(locks[li]["pts"], float)
        feats.append(np.r_[P[0], P[len(P) // 2], P[-1]])
    feats = np.asarray(feats)
    k = max(1, int(np.ceil(len(pool) / hair_cards.SINGLES_PER_CARD)))
    if k < len(pool):
        _, lab = kmeans2(feats, k, minit="++", seed=int(rng.integers(1 << 30)))
    else:
        lab = np.arange(len(pool))
    out = []
    for g in np.unique(lab):
        lis = [pool[i] for i in np.nonzero(lab == g)[0]]
        A = G["A"][np.isin(G["lock"], lis)]
        if len(A) < 1:
            continue
        c = _clump(A, G["u"], lambda P: C[None], min_share=0.25)
        if c is None:
            continue
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(c["P"], axis=0), axis=1))]
        if s[-1] < 0.01:
            continue
        # narrow: the fly tile's hairs are a share of the card's width (FLY_HAIR), at 10 mm cards they were 0.7 mm
        # wide, a halo of brown leaves over the crown
        hw = np.clip(1.2 * c["sx"], 0.0012, 0.002) * (1 - 0.4 * _ss((s / s[-1] - 0.6) / 0.4))
        out.append({"P": c["P"], "X": c["X"], "N": c["N"], "hw": hw, "u": c["u"], "s": s, "kind": "fly", "layer": L,
                    "prio": L + 1.0, "cval": 1.0, "bend": c["bend"], "T": c["T"], "lock": locks[lis[0]]["name"],
                    "value": 1.0, "sn": c["sn"], "pooled": True})
    return out
