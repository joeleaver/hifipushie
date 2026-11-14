"""The designed fold: its rows, the hood's direction, `design`, `fold` and the fold's text. Part of the upper lid's fold on GNM (gnm_fold.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import gnm_fold
from . import gnm_controls as gc
from .gnm_fold import chains, read, read_text, topo, vertices

def _setup(ne: int = 0, umax: float = 10.0) -> dict:
    """B (170 + ne, V, 3) mm per unit of x = [identity, eye expression (left + its mirrored right as ONE coefficient)],
    the chains (left, right) and the column weights (full over the middle, tapering to the corners)."""
    key = ("S", ne, umax)
    if key in gnm_fold._C:
        return gnm_fold._C[key]
    g, t = gc.gnm(), topo()
    B = [g["IB"][:gnm_fold.NC].astype(np.float64) * 1000.0]
    EL = [i for i, n in enumerate(g["ex_names"]) if n.startswith("left_eye")][:ne]
    ER = [i for i, n in enumerate(g["ex_names"]) if n.startswith("right_eye")][:ne]
    if ne:
        B.append((g["EB"][EL].astype(np.float64) + g["EB"][ER].astype(np.float64)) * 1000.0)
    ch = chains(umax)
    u = g["T"][ch[:, 0], 0] * 1000.0 - g["J"][2][0] * 1000.0
    wc = np.clip(1.5 - np.abs(u) / (umax / 1.5), 0.15, 1.0)
    gnm_fold._C[key] = {"B": np.concatenate(B), "ch": ch, "chR": t["mir"][ch], "wc": wc / wc.sum(), "EL": EL, "ER": ER}
    return gnm_fold._C[key]


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
            "gap": lin(kb, 2) - lin(ka, 2), "gap0": tem(kb, 2) - tem(ka, 2), "brow": lin(gnm_fold.NR, 1) - lin(0, 1), "brow0": tem(gnm_fold.NR, 1) - tem(0, 1)}


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
    c0 = np.asarray(c0, float)[:gnm_fold.NC]
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
            keep = [i for i, n in enumerate(gnm_mm.HELD) if n not in gnm_fold.MM_FREE]
            Jm = np.zeros((len(keep), nx))
            Jm[:, :gnm_fold.NC] = gnm_mm.jacobian()[keep] / hold_mm
            Qh += Jm.T @ Jm
    R = _rows(S, ka, ka + 2)
    x0 = np.zeros(nx)
    x0[:gnm_fold.NC] = c0
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
    c1 = c0 + dx[:gnm_fold.NC]
    e1 = None
    if expression:
        e1 = np.zeros(len(g["ex_names"]))
        e1[S["EL"]] = dx[gnm_fold.NC:]
        e1[S["ER"]] = dx[gnm_fold.NC:]
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
    return {"c": c1, "e": e1, "dc": float(np.linalg.norm(dx[:gnm_fold.NC])), "e_norm": float(np.linalg.norm(dx[gnm_fold.NC:])),
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
