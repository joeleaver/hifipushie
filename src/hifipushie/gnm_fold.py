"""The upper lid's FOLD in GNM's own parameters ("overhang" study, 2026-10-11; docs/notes/gnm_atlas.md "## overhang").

GNM's skin round each eye is closed quad rings: ring 0 = the lid margin, ring k = k edges out (rows 0.5-0.7 mm apart
at rings 3-6, where GNM's crease is). Every ring vertex is linear in the 170 identity comps (and the eye's 100
expression comps), so a wanted fold is a closed-form least squares, not a search:

  read(V)        overhang (mm of skin hanging in front of and below the skin under it, front view), the largest turn
                 of the section (deg) and the crease's height over the margin, on radial chains up the lid's middle
  hood_direction the ONE identity direction that makes an overhang at least cost. It is hooding: the brow and drape
                 coming down over a deeper-set eye (corr -0.95 with the brow's height). Not a local fold.
  design(V, ...) a designed folded lid as vertex targets: a platform on the ball up to the crease, a slit, a roll of
                 drape hanging `overhang` mm over the platform, merging into the head's own drape
  fold(c, ...)   the least-squares identity (optionally + eye expression) for that design with the rest of the head
                 held, optionally with the overhang as a hard constraint; returns the coefficients and a blunt report

What the study found (numbers in the notes): the basis SPANS a re-entrant lid (0.13 mm rms with nothing else asked,
at |dc| 460), but with the rest of the head held to 1 mm the lid's rows keep ~0.08 mm of freedom. fold() without
`overhang` gives a crisp fold at a chosen height (turn 45-65 deg raw; the population's largest at >= 4 mm is ~36) for
|dc| ~10-15; with `overhang` it buys the overhang by lowering the brow 4-5 mm (|dc| ~18-20). GNM frame, mm inside."""
from __future__ import annotations

import numpy as np

from . import gnm_controls as gc

NC = 170
NR = 12            # rings read out from the margin
MM_FREE = ("brow_hollow", "_platform_z")   # gnm_mm's measures a fold IS (the sulcus under the brow, the platform on the ball)
_C: dict = {}


def topo() -> dict:
    """{"ring": per GNM vertex ring index round the LEFT eye (0 = margin; 99 elsewhere; negative = the socket lining),
    "nb": neighbour lists over skin edges, "mir": the mirror vertex of each vertex}."""
    if "t" in _C:
        return _C["t"]
    from scipy.spatial import cKDTree
    g = gc.gnm()
    Q, gr, T = g["quads"], g["groups"], g["T"]
    n = len(T)
    skin, sock = gr["skin"], gr["eye_sockets"]
    E = np.concatenate([Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]])
    E = E[skin[E].all(1)]
    nb = [[] for _ in range(n)]
    for a, b in E:
        nb[a].append(int(b))
        nb[b].append(int(a))
    cl = g["J"][2]
    m = sock[E[:, 0]] != sock[E[:, 1]]
    r0 = np.unique(np.where(sock[E[m, 0]], E[m, 1], E[m, 0]))
    r0 = r0[np.linalg.norm(T[r0] - cl, axis=1) < 0.03]
    ring = np.full(n, 99)
    ring[r0] = 0
    for sgn, ok, lim in ((1, ~sock, NR + 6), (-1, sock, 5)):   # (+6: a fold traced far round the outer corner uses rings to 16)
        cur = list(r0)
        for k in range(1, lim + 1):
            nxt = []
            for a in cur:
                for b in nb[a]:
                    if ring[b] == 99 and ok[b]:
                        ring[b] = sgn * k
                        nxt.append(b)
            cur = nxt
    _C["t"] = {"ring": ring, "nb": nb, "mir": cKDTree(T).query(T * [-1, 1, 1])[1]}
    return _C["t"]


def chains(umax: float = 7.0, k1: int = NR) -> np.ndarray:
    """Radial chains up the LEFT upper lid: from each margin vertex within umax mm of the eye's centre (across), follow
    the next ring's neighbour nearest in x. (n, k1 + 1) vertex ids; the right eye's are topo()["mir"][chains]."""
    key = ("ch", umax, k1)
    if key in _C:
        return _C[key]
    g, t = gc.gnm(), topo()
    T = g["T"] * 1000.0
    J = g["J"][2] * 1000.0
    r0 = np.flatnonzero(t["ring"] == 0)
    r0 = r0[(T[r0, 1] > J[1] + 0.5) & (np.abs(T[r0, 0] - J[0]) < umax)]
    out = []
    for v in r0[np.argsort(T[r0, 0])]:
        ch = [int(v)]
        while t["ring"][ch[-1]] < k1:
            up = [b for b in t["nb"][ch[-1]] if t["ring"][b] == t["ring"][ch[-1]] + 1]
            if not up:
                break
            ch.append(min(up, key=lambda b: abs(T[b, 0] - T[ch[-1], 0])))
        if len(ch) == k1 + 1:
            out.append(ch)
    _C[key] = np.array(out)
    return _C[key]


def vertices(c=None, e=None) -> np.ndarray:
    """GNM's head in mm (GNM frame) for identity c (<= 253) and expression e (383)."""
    return gc.vertices(c, e) * 1000.0


def read(V: np.ndarray, umax: float = 7.0) -> dict:
    """The fold on vertices V (mm), left eye, per radial chain and as means:
    hang   mm: the largest v[a] - v[b] over rings a < b <= a + 5 with ring b's skin FORWARD of ring a's: skin hanging in
           front of and below the skin under it (0 = no overhang anywhere); ka = that pair's lower ring (the crease)
    turn   deg: the largest turn between successive segments of the sagittal section at rings 2..9
    h      mm: the crease ring's height over the margin (the overhang's ring, else the turn's)."""
    ch = chains(umax)
    v, w = V[ch][..., 1], V[ch][..., 2]
    n, m = v.shape
    hang, ka = np.zeros(n), np.zeros(n, int)
    for a in range(1, m - 1):
        for b in range(a + 1, min(a + 6, m)):
            d = np.where(w[:, b] > w[:, a], v[:, a] - v[:, b], -np.inf)
            better = d > hang
            hang[better], ka[better] = d[better], a
    ang = np.unwrap(np.arctan2(np.diff(w, axis=1), np.diff(v, axis=1)), axis=1)
    tr = np.degrees(np.diff(ang, axis=1))[:, 1:9]
    kt = 2 + tr.argmax(1)
    hk = np.where(hang > 0, ka, kt)
    h = v[np.arange(n), hk] - v[:, 0]
    return {"hang": hang, "turn": tr.max(1), "h": h, "ring": hk, "hang_mean": float(hang.mean()), "hang_max": float(hang.max()),
            "turn_mean": float(tr.max(1).mean()), "h_mean": float(h.mean()), "ring_mode": int(np.bincount(hk).argmax()),
            "brow_h": float((v[:, NR] - v[:, 0]).mean())}


def read_text(q: dict) -> str:
    return (f"overhang {q['hang_mean']:.2f} mm (max {q['hang_max']:.2f}), turn {q['turn_mean']:.0f} deg, crease at ring {q['ring_mode']}, "
            f"{q['h_mean']:.1f} mm over the margin, brow ring {q['brow_h']:.1f} mm over the margin")


def _setup(ne: int = 0, umax: float = 10.0) -> dict:
    """B (170 + ne, V, 3) mm per unit of x = [identity, eye expression (left + its mirrored right as ONE coefficient)],
    the chains (left, right) and the column weights (full over the middle, tapering to the corners)."""
    key = ("S", ne, umax)
    if key in _C:
        return _C[key]
    g, t = gc.gnm(), topo()
    B = [g["IB"][:NC].astype(np.float64) * 1000.0]
    EL = [i for i, n in enumerate(g["ex_names"]) if n.startswith("left_eye")][:ne]
    ER = [i for i, n in enumerate(g["ex_names"]) if n.startswith("right_eye")][:ne]
    if ne:
        B.append((g["EB"][EL].astype(np.float64) + g["EB"][ER].astype(np.float64)) * 1000.0)
    ch = chains(umax)
    u = g["T"][ch[:, 0], 0] * 1000.0 - g["J"][2][0] * 1000.0
    wc = np.clip(1.5 - np.abs(u) / (umax / 1.5), 0.15, 1.0)
    _C[key] = {"B": np.concatenate(B), "ch": ch, "chR": t["mir"][ch], "wc": wc / wc.sum(), "EL": EL, "ER": ER}
    return _C[key]


def _rows(S: dict, ka: int, kb: int) -> dict:
    """Linear rows (and template values) of: hang = v[ka] - v[kb]; H = v[ka] - v[0]; gap = w[kb] - w[ka]; brow =
    v[NR] - v[0]: weighted means over the columns, both eyes."""
    B, ch, chR, wc = S["B"], S["ch"], S["chR"], S["wc"]
    T = gc.gnm()["T"] * 1000.0

    def lin(k, ax):
        return 0.5 * (np.tensordot(B[:, ch[:, k], ax], wc, 1) + np.tensordot(B[:, chR[:, k], ax], wc, 1))

    def tem(k, ax):
        return float(0.5 * (T[ch[:, k], ax] @ wc + T[chR[:, k], ax] @ wc))
    return {"hang": lin(ka, 1) - lin(kb, 1), "hang0": tem(ka, 1) - tem(kb, 1), "H": lin(ka, 1) - lin(0, 1), "H0": tem(ka, 1) - tem(0, 1),
            "gap": lin(kb, 2) - lin(ka, 2), "gap0": tem(kb, 2) - tem(ka, 2), "brow": lin(NR, 1) - lin(0, 1), "brow0": tem(NR, 1) - tem(0, 1)}


def hood_direction(ka: int = 5) -> dict:
    """The identity direction of least |c| per mm of overhang at rings ka -> ka + 2 (margins free): {"dc": unit (170),
    "per_unit": mm of overhang per unit, "sd_to_overhang": how many units from GNM's template to zero spacing,
    "brow": mm the brow ring moves over the margin per unit, "crease": mm the crease moves per unit, "corr_brow"}."""
    R = _rows(_setup(0), ka, ka + 2)
    g = R["hang"]
    n = float(np.linalg.norm(g))
    return {"dc": g / n, "per_unit": n, "sd_to_overhang": -R["hang0"] / n, "brow": float(R["brow"] @ g / n),
            "crease": float(R["H"] @ g / n), "corr_brow": float(R["brow"] @ g / n / np.linalg.norm(R["brow"]))}


def _ball(V, grp):
    g = gc.gnm()
    P = V[g["groups"][grp] & g["groups"]["scleras"]]
    A = np.c_[2 * P, np.ones(len(P))]
    sol = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
    return sol[:3], float(np.sqrt(sol[3] + sol[:3] @ sol[:3]))


def design(V: np.ndarray, crease=4.7, overhang: float = 1.0, thick: float = 0.9, standoff: float = 1.3,
           ka: int = 5, kt: int = 10, umax: float = 12.0, taper: float = 3.0) -> dict:
    """{vertex id: target xyz (mm)} for both upper lids, rings 1..kt-1, on the head V (mm): per radial chain
    rings 1..ka   the platform: heights spread (as the template's rows) up to `crease` mm over the margin at ring ka
                  (a number, or a function of u = mm across from the eye's centre, + = outer: the picture's fold line),
                  `standoff` mm off GNM's eyeball (1.3: clear of OUR smaller, differently seated ball; 0.8 touches it)
    ring ka+1     the top of the slit (0.35 mm up, 0.45 mm further out)
    ring ka+2     the fold's lower edge: `overhang` mm BELOW the crease in a front view, `thick` mm in front of the platform
    ring ka+3     the roll's front; rings ka+4..kt-1 on the line to the head's own ring kt (its drape)
    fading into the head's own lid over `taper` mm at the corners."""
    t = topo()
    T = gc.gnm()["T"] * 1000.0
    J = gc.gnm()["J"][2] * 1000.0
    ch = chains(umax)
    out = {}
    for side, grp in ((1, "left_eye"), (-1, "right_eye")):
        ids = ch if side == 1 else t["mir"][ch]
        ctr, r = _ball(V, grp)
        P = V[ids] - ctr
        Tm = T[ch]
        hv = Tm[:, :, 1] - Tm[:, :1, 1]
        uu = T[ch[:, 0], 0] - J[0]
        wt = np.clip((umax - np.abs(uu)) / taper, 0.0, 1.0)
        cr = np.asarray(crease(uu), float) if callable(crease) else np.full(len(ch), float(crease))
        for j in range(len(ch)):
            crease_j = float(cr[j])
            x, v0 = P[j, :, 0], P[j, 0, 1]
            s0 = np.linalg.norm(P[j, 0]) - r
            tg = {}
            for k in range(1, ka + 1):
                h = crease_j * hv[j, k] / hv[j, ka]
                tg[k] = (h, standoff + (s0 - standoff) * np.exp(-h))
            tg[ka + 1] = (crease_j + 0.35, standoff + 0.45)
            tg[ka + 2] = (crease_j - overhang, standoff + thick)
            tg[ka + 3] = (crease_j - overhang + 0.8, standoff + thick + 0.9)
            pts = {k: np.array([x[k], v0 + h, np.sqrt(max((r + s) ** 2 - x[k] ** 2 - (v0 + h) ** 2, 0.0))]) for k, (h, s) in tg.items()}
            a, b = pts[ka + 3], P[j, kt]
            cum = np.cumsum(np.linalg.norm(np.diff(Tm[j, ka + 3:kt + 1], axis=0), axis=1))
            for i, k in enumerate(range(ka + 4, kt)):
                q = a + (b - a) * (cum[i] / cum[-1])
                pts[k] = np.array([x[k], q[1], q[2]])
            for k, p in pts.items():
                out[int(ids[j, k])] = wt[j] * p + (1 - wt[j]) * P[j, k] + ctr
    return out


def fold(c0, crease=4.7, overhang: float | None = None, hold: float = 1.0, brow: float | None = None,
         standoff: float = 1.3, expression: int = 0, lam: float = 1.0, ka: int = 5, sig: float | None = None,
         design_overhang: float = 1.0, margins: float = 0.05, free: bool = False, clear_rounds: int = 4,
         hold_mm: float | None = None, hold_far: float | None = None, far: tuple = (25.0, 45.0)) -> dict:
    """Form the upper-lid fold on identity c0 (170) with GNM's parameters alone.
    crease     mm over the lid margin (raw GNM mm; a model's world mm / ~0.99): a number, or a function of u (mm
               across from the eye's centre, + = outer) for a fold line that is not level
    hold_far   mm: the skin beyond far[1] mm of both eyes' centres held this tightly instead of `hold` (eased in from
               far[0]): the fold is paid for round the orbit, not with the jaw and mouth
    hold_mm    mm: gnm_mm's measures (the orbit and everything else the block-in measured) held this tightly too
    overhang   None: fit the designed fold softly (a crisp fold; the overhang itself does not survive the hold);
               mm: ALSO require that much skin hanging over the platform (hard). This lowers the brow: see the report.
    hold       mm: every other skin vertex and the eyeballs (inside skin 3x looser); margins: the lid margins (mm)
    brow       mm: the brow regions held this tightly instead (raises the cost steeply with an overhang)
    expression n > 0 adds the eye's first n expression comps (both eyes alike) at unit prior: GNM's expressions do
               not form folds; here for completeness
    free       True: no hold and no prior (the pure projection: the span test)
    Returns {"c", "e" (383 or None), "dc", "e_norm", "residual" (mm rms to the design), "held_rms", "held_max", "worst"
    (regions that moved most, mm), "before" / "after" (read()), "brow_drop" (mm), "measures" (gnm_mm rows that moved
    most)}."""
    g, t = gc.gnm(), topo()
    c0 = np.asarray(c0, float)[:NC]
    V0 = vertices(c0)
    tgt = design(V0, crease, design_overhang, standoff=standoff, ka=ka)
    ids = np.array(sorted(tgt))
    P = np.array([tgt[i] for i in ids])
    S = _setup(expression)
    B = S["B"]
    nx = len(B)
    sig = (0.3 if overhang is not None else 0.1) if sig is None else sig
    hm = np.zeros(len(V0), bool)
    Qh = 1e-6 * np.eye(nx)
    if not free:
        ext = g["groups"]["skin_exterior"] | g["groups"]["eyes"]
        hm = (g["groups"]["skin"] | g["groups"]["eyes"]).copy()
        hm[ids] = False
        rr = np.minimum(np.abs(t["ring"]), np.abs(t["ring"][t["mir"]]))
        hv = np.full(len(V0), float(hold))
        if hold_far:
            T = g["T"] * 1000.0
            de = np.minimum(np.linalg.norm(T - g["J"][2] * 1000.0, axis=1), np.linalg.norm(T - g["J"][3] * 1000.0, axis=1))
            f = np.clip((de - far[0]) / (far[1] - far[0]), 0.0, 1.0)
            hv = hold * (hold_far / hold) ** (f * f * (3 - 2 * f))
        w = np.where(rr == 0, 1.0 / margins, np.where(ext, 1.0 / hv, 1.0 / (3.0 * hv)))
        if brow is not None:
            bm = g["groups"]["left_brow_region"] | g["groups"]["right_brow_region"] | g["groups"]["middle_brow_region"]
            w = np.where(bm, np.maximum(w, 1.0 / brow), w)
        Ah = (B[:, hm] * w[hm][None, :, None]).reshape(nx, -1)
        Qh = Ah @ Ah.T + lam * np.eye(nx)
        if hold_mm:
            from . import gnm_mm
            keep = [i for i, n in enumerate(gnm_mm.HELD) if n not in MM_FREE]
            Jm = np.zeros((len(keep), nx))
            Jm[:, :NC] = gnm_mm.jacobian()[keep] / hold_mm
            Qh += Jm.T @ Jm
    R = _rows(S, ka, ka + 2)
    x0 = np.zeros(nx)
    x0[:NC] = c0
    # the platform must stay clear of the eyeball: a vertex the solve leaves closer than `standoff` - 0.2 mm to GNM's
    # ball gets its target pushed out by the shortfall and 3x the weight, a few rounds (our own ball is smaller but
    # seated by 6 landmarks: a platform under ~1.1 mm let it show through the lid as a brown patch)
    left = g["T"][ids, 0] > 0
    rk = np.where(left, t["ring"][ids], t["ring"][t["mir"]][ids])
    plat = rk <= ka + 1
    wv = np.ones(len(ids))
    for _ in range(clear_rounds + 1):
        At = (B[:, ids] * (wv / sig)[None, :, None]).reshape(nx, -1).T
        D0 = ((P - V0[ids]) * (wv / sig)[:, None]).ravel()
        Q, rhs = At.T @ At + Qh, At.T @ D0
        if overhang is None:
            dx = np.linalg.solve(Q, rhs)
        else:
            A = np.array([R["hang"], R["gap"]])
            b = np.array([overhang - (R["hang0"] + R["hang"] @ x0), 0.6 - (R["gap0"] + R["gap"] @ x0)])
            dx = np.linalg.solve(np.block([[Q, A.T], [A, np.zeros((2, 2))]]), np.r_[rhs, b])[:nx]
        V1 = V0 + np.tensordot(dx, B, 1)
        so = np.empty(len(ids))
        push = []
        for m_, grp in ((left, "left_eye"), (~left, "right_eye")):
            ctr, r_ = _ball(V1, grp)
            so[m_] = np.linalg.norm(V1[ids][m_] - ctr, axis=1) - r_
            bad = m_ & plat & (np.where(m_, so, np.inf) < standoff - 0.2)
            push.append((bad, ctr))
        if free or not any(bad.any() for bad, _ in push):
            break
        for bad, ctr in push:
            if bad.any():
                nrm = V1[ids][bad] - ctr
                nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
                P[bad] += nrm * (standoff - so[bad])[:, None]
                wv[bad] *= 3.0
    res = (P - V1[ids])
    c1 = c0 + dx[:NC]
    e1 = None
    if expression:
        e1 = np.zeros(len(g["ex_names"]))
        e1[S["EL"]] = dx[NC:]
        e1[S["ER"]] = dx[NC:]
    V1 = vertices(c1, e1)
    mv = np.linalg.norm(V1 - V0, axis=1)
    worst = {}
    if hm.any():
        for nm, m in g["groups"].items():
            if (nm.endswith("_region") or nm in ("ears", "eyes")) and (m & hm).any():
                worst[nm] = float(mv[m & hm].max())
        worst = dict(sorted(worst.items(), key=lambda kv: -kv[1])[:5])
    q0, q1 = read(V0), read(V1)
    meas = []
    try:
        from . import gnm_mm
        meas = [(r["measure"], round(r["gap"], 2)) for r in gnm_mm.gaps(V0 / 1000.0, vertices(c1) / 1000.0)[:6]]
    except Exception:  # noqa: BLE001  (the measures are a report, not the solve)
        pass
    return {"c": c1, "e": e1, "dc": float(np.linalg.norm(dx[:NC])), "e_norm": float(np.linalg.norm(dx[NC:])),
            "residual": float(np.sqrt((res ** 2).sum(1).mean())), "held_rms": float(np.sqrt((mv[hm] ** 2).mean())) if hm.any() else 0.0,
            "held_max": float(mv[hm].max()) if hm.any() else 0.0, "worst": worst, "before": q0, "after": q1,
            "brow_drop": float(q0["brow_h"] - q1["brow_h"]), "measures": meas, "min_standoff": float(so[plat].min())}


def fold_text(r: dict) -> str:
    return "\n".join([
        "before: " + read_text(r["before"]),
        "after:  " + read_text(r["after"]),
        f"cost: |dc| {r['dc']:.1f}" + (f", |e| {r['e_norm']:.1f} per eye" if r["e"] is not None else "") + f"; the design missed by {r['residual']:.2f} mm rms; "
        f"held skin moved {r['held_rms']:.2f} mm rms, max {r['held_max']:.1f}; brow ring {r['brow_drop']:+.1f} mm DOWN over the margin; "
        f"platform's least stand-off from GNM's ball {r['min_standoff']:.2f} mm",
        "moved most: " + ", ".join(f"{k} {v:.1f} mm" for k, v in r["worst"].items()),
        "measures (mm): " + ", ".join(f"{k} {v:+.1f}" for k, v in r["measures"])])


# ---------------------------------------------------------------- the fold in MESH space (projskin, 2026-10-13)

FOLD_KEYS = {"crease", "overhang", "thick", "standoff", "amount", "ring", "last", "L", "R", "reach", "taper", "wrap", "crease_by_angle", "tail", "depth", "smooth"}
CREASE_KNOTS = (-9.0, 0.0, 9.0)     # mm across from the eye's centre (inner, middle, outer) where "crease" / "overhang" lists sit
BLINK_FULL = 0.75                   # the fold is gone when the upper margin has come down this share of the open aperture


def _along(x, default: float):
    """A number, or [inner, middle, outer] (at CREASE_KNOTS), or [[u mm, value], ...] -> a function of u (mm across
    from the eye's centre, + = outer)."""
    if x is None:
        return lambda u: np.full(np.shape(u), float(default))
    if isinstance(x, (int, float)):
        return lambda u: np.full(np.shape(u), float(x))
    a = np.asarray(x, float)
    if a.ndim == 1:
        k = np.linspace(CREASE_KNOTS[0], CREASE_KNOTS[-1], len(a))
        return lambda u: np.interp(u, k, a)
    o = np.argsort(a[:, 0])
    return lambda u: np.interp(u, a[o, 0], a[o, 1])


def check_fold(cfg) -> dict | None:
    if cfg in (None, False, {}):
        return None
    if not isinstance(cfg, dict) or set(cfg) - FOLD_KEYS:
        raise ValueError(f"base.head.lid_fold: keys {sorted(FOLD_KEYS)} (crease / overhang in mm: a number, [inner, middle, outer] or "
                         "[[u mm, value], ...]; L / R: one side's own values)")
    return cfg


FADE_RINGS = (0.55, 0.25, 0.08)   # the displacement handed on to the rings past the fold's last one (no hard patch edge)
FADE_DEG = 20.0                    # deg: the displacement fades to nothing this far past the angular span the chains cover


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
    for k in range(1, last + len(FADE_RINGS)):
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
            w = np.clip(1 - np.maximum(lo - a, 0) / FADE_DEG, 0, 1) * np.clip(1 - np.maximum(a - hi, 0) / FADE_DEG, 0, 1)
            out[ids] = d * (w * w * (3 - 2 * w))[:, None]
            prev = (a, out[ids].copy())
        elif prev is not None:      # past the last ring: the last ring's displacement, faded
            f = FADE_RINGS[k - last]
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
    x = float(np.clip(drop / max(BLINK_FULL * ap, 1e-6), 0.0, 1.0))
    return 1.0 - x * x * (3 - 2 * x)


TAIL_WIDTH = 0.9     # mm: the crease tail's groove half-width (a Gaussian's)
TAIL_DEPTH = 0.5     # mm


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
    dep, wd = float(tail.get("depth", TAIL_DEPTH)), float(tail.get("width", TAIL_WIDTH))
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


RING_SMOOTH = 0     # passes of smoothing the fold's displacement along each lid ring (OFF: GNM's BFS rings are not the design's rows; 6 passes flattened the hood to nothing)


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
        ch, ang = chains_wrap(float(c.get("reach", 15.5)), kt + 2, float(c.get("wrap", WRAP_DEG)))
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


CREASE_ROW_PASSES = 3   # passes of smoothing the crease rows' FINAL positions along their rings


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
    for _ in range(CREASE_ROW_PASSES):
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
        wrap = float(c.get("wrap", WRAP_DEG))
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
            _smooth_along_rings(out, side, t, int(c.get("smooth", RING_SMOOTH)))
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


WRAP_DEG = 25.0     # deg below the eye's horizontal the fold's chains reach round the OUTER corner (the hood wraps it). At
                    # 70 the crease turned straight down at the corner and ran back under the eye (a roll under the lower
                    # lid; the photos' creases run on 4-11 mm LATERALLY past the canthus and drop only 0-5 mm)


CREASE_DEG = 2   # the crease's height along the lid: a polynomial of this degree in the chain angle (one maximum at most)


def smooth_crease(cba) -> callable:
    """[[deg, mm], ...] (traced / read, noisy) -> a smooth height function of the chain angle: a least-squares
    polynomial of CREASE_DEG (a quadratic has one extremum: a real crease is one smooth arc between the canthi), held flat
    past the data's ends. Interpolating the points themselves seated their noise: a wobbly, kinked crease."""
    a = np.asarray(cba, float)
    a = a[np.argsort(a[:, 0])]
    if len(a) < CREASE_DEG + 2:
        return lambda x, a=a: np.interp(x, a[:, 0], a[:, 1])
    k = np.polyfit(a[:, 0], a[:, 1], CREASE_DEG)
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


def chains_wrap(umax: float = 15.5, k1: int = NR, wrap_deg: float = WRAP_DEG) -> tuple:
    """Radial chains of the LEFT eye's lid rings for a fold that wraps the outer corner: every margin vertex of the upper
    lid within umax mm across, plus the margin round the OUTER corner down to wrap_deg below the eye's horizontal; each
    chain followed outward along its own radial direction (from the eye's centre in the front plane). Returns
    (chains (n, k1 + 1), angle per chain: deg from the upward vertical, + toward the outer side)."""
    key = ("chw", umax, k1, wrap_deg)
    if key in _C:
        return _C[key]
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
    _C[key] = (np.array(out), np.array(aout))
    return _C[key]


def design_wrap(V: np.ndarray, crease, overhang, thick: float = 0.9, standoff: float = 1.3, ka: int = 5, kt: int = 10,
                umax: float = 15.5, wrap_deg: float = WRAP_DEG, fade_deg: float = 30.0, traced: bool = False, depth: float = 1.0) -> dict:
    """design() along each chain's OWN outward direction (not the vertical), so the fold follows its ring round the
    outer corner and down (a hood wrapping the corner, continuing toward the lower lid's fold). crease / overhang:
    functions of the chain's angle (deg from the upward vertical, + outer). The fold fades to nothing over the last
    fade_deg of the wrap and over the inner end (by the across distance)."""
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
