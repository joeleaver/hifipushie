"""Garment step 4's flat gate, row `shape_stand` (T5c, C300): a stand's curve and heights DECIDED BY THE REFERENCE.

Why (Joe, on the T5b hussar stand: "it looks like it got the collar curves the wrong direction again"): T5b required
every stand's neck edge to rise towards its front ends (jaeger.collarStand). That is ONE style, the HUGGING stand
(mandarin, a shirt band): sewn on, it leans in and its top follows the neckline down at CF. A stand whose top line stays
LEVEL all round over a neckline that drops at the front stands AWAY from the neck and is TALLER at its front ends; its
neck edge is straight or curves the other way. A collar style isn't a law: the step-2 traces (structure_outline.py:
`collar_top`, `collar_front`, placed on the body by `body_marks`) say which one this garment is.

DERIVATION (the stand as a band whose neck edge is the drafted neckline and whose free edge is the trace). Heights in the
view are vertical, in mm, the body the ruler (structure_outline.placement). Let D = the neckline's front drop SEEN (vertical,
HPS -> CF; below), D_b = the back's (CB -> HPS). The trace gives:
  h_side = the top line's highest point above the side neck points (hps marks' height on the body),
  T      = how far the top line drops from that point to its front ends (each end: the last point where the trace still
           runs within TOP_DEG of level; past it the trace turns down a rounded corner / the front edge), mean of both.
  f = T / D (clipped 0..1): the share of the neckline's drop the top follows.
The stand's height anywhere = its top - the neckline there, so:
  front ends: h_front = h_side + D - T  (= h_side + D (1 - f)),   centre back: h_back = h_side + D_b (1 - f).
The curve: a stand of constant height whose top follows the whole drop (f = 1) is jaeger's: neck edge rising ~ JAEGER x D
(the flat drop) at its ends (the top concentric and shorter: it leans in). A level top (f = 0) on an UPRIGHT stand is a
vertical band: developed flat its free edge is ~straight and its neck edge FALLS at the front ends by the height it gains
there, D - D_b seen (r-hussar: T5c's straight neck edge built a stand tilted with the neckline's plane, 31 deg up, CB
lying flat). Between, blended: rise target = f x JAEGER x D_flat - (1 - f)(D - D_b), within the heights' tol.
Heights are the nearest distance free edge -> neck edge (square to the neck edge): a steeply falling end reads a little
short of its vertical (cos of the slope; 4 % at the hussar's 16 deg).
  lean (free / neck edge <= STAND_LEAN) only when the top follows (f >= FOLLOW): a level stand standing away needs no lean.
Heights within tol = 2 x TRACE_PX x mm/px (two traced places per height) + the marks' residual. Approximations, said:
an upright stand (a stand leaning 20 deg reads 6 % short in the view).
D AND D_b ARE SEEN, NOT FLAT (r-hussar; T5c took them from the flat, 75 mm, and asked for fronts 30-60 mm too tall: build
c1's collar collapsed): a jacket front tilts over the chest, so its 75 mm flat drop is ~16-39 mm of height. D = the
collar_front traces' bottom ends below the hps marks (the reference's own neckline at CF), else the body's hps - cf_neck;
D_b = the body's hps - cb_neck; the flat's only when neither is known (said in the row). The RISE stays a flat quantity
(jaeger's rise x the flat front drop): f decides the style, the flat drop scales the curve.
Every FAIL says which way to curve and how much taller / lower, at the ends or the back.
WITHOUT a collar_top trace the row is INFO: the stand's curve (rising: hugs / straight / falling: stands away) and its
heights are reported, no style assumed. A BAND under a fall is INFO too (the fall's trace doesn't show the band).
"""
from __future__ import annotations

import numpy as np

JAEGER_RISE = 31.0 / 65.4  # jaeger.collarStand: rise / front drop (the hugging stand; T5b's measure on wf_simon)
STAND_RISE = 0.5 * JAEGER_RISE  # the rise's tolerance either way, x D (T5b's halving)
STAND_LEAN = 1 - 0.5 * (1 - 0.978)  # jaeger.collarStand free / neck edge: a hugging stand leans in
FOLLOW = 0.5  # the top follows >= half the neckline's drop: the hugging stand; less: level, standing away
TOP_DEG = 60.0  # the top line, seen: within this of level (steeper: a rounded corner or the front edge going down)
END_SHARE = 0.25
TRACE_CUT_MM = 10.0  # the collar_top trace runs on this far down past its corner: it traces a cut-away front end
# the curve's why is REPORTED, not failed (r-hussar): builds r1 / r2 with the neck edge +9 and -13 mm both built the stand
# 31 deg up (the build lays it out whatever the curve), so no build backs the rise target yet; the heights are (c1 too
# tall -> collar_height FAIL; r1 / r2 on target -> PASS; T8 short -> collar_front's top corners low)
CURVE_ONLY = "(curve: reported, not failed) "  # a front end's height: the tallest place on the free edge within this share of its arc from the end


def _curve_word(r: float, D: float) -> str:
    """The neck edge's curve in words: past half jaeger's rise either way (the row's own tolerance) it reads as a style."""
    return ("rising (hugs)" if r >= STAND_RISE * D else "falling (stands away)" if r <= -STAND_RISE * D
            else "near straight (upright)")


def reference(plan: dict | None, at: dict | None) -> dict | None:
    """{h_side, T, tol, fronts, how} mm from step 2's first collar_top trace, or None (no trace) / {why} (unplaced)."""
    from . import structure_outline as so
    style = (plan or {}).get("style") or {}
    tops = [t for t in style.get("traces") or [] if t.get("what") == "collar_top"]
    if not tops:
        return None
    t = tops[0]
    vi = t.get("view", 0)
    try:
        v = so._view_of(plan, vi)
        pl = so.placement(v, so._marks(style, vi), at or {})
        b_hps = -float(np.asarray(at["hps.L"]).ravel()[-1]) * 1000
    except (ValueError, KeyError, IndexError, TypeError, np.linalg.LinAlgError) as e:
        return {"why": f"{t.get('id')}: the body marks don't place view {vi}: {e}"}
    P = so.to_mm(t["points"], pl)  # (a right, b down) mm
    top = float(P[:, 1].min())
    ti = int(np.argmin(P[:, 1]))
    cs = [int(c) for c in t.get("corners") or [] if isinstance(c, int) and 0 < c < len(P) - 1]
    ends, cut = [], []
    for side, Q in ((-1, P), (1, P[::-1])):
        # the trace's own corners end the top (C377, t s4-7: the hussar's front ends slant down at 45 deg to the CF neck;
        # read by TOP_DEG alone, the slant was taken for a top following the neckline); else the first level stretch
        near = [c for c in cs if (c < ti if side < 0 else c > ti)]
        if near:
            c = max(near) if side < 0 else min(near)
            k = c if side < 0 else len(P) - 1 - c
            cut.append(float(Q[0, 1]) - float(Q[k, 1]) > TRACE_CUT_MM)  # (the trace runs on, DOWN a front edge, past it)
        else:
            k = next((i for i in range(len(Q) - 1)
                      if np.degrees(np.arctan2(abs(Q[i + 1, 1] - Q[i, 1]), abs(Q[i + 1, 0] - Q[i, 0]) + 1e-12)) < TOP_DEG), 0)
            cut.append(False)
        ends.append(float(Q[k, 1]) - top)
    cf = [so.to_mm(f["points"], pl) for f in style.get("traces") or []
          if f.get("what") == "collar_front" and f.get("view", 0) == vi]
    fronts = {f["id"]: round(float(np.sum(np.linalg.norm(np.diff(so.to_mm(f["points"], pl), axis=0), axis=1))), 1)
              for f in style.get("traces") or [] if f.get("what") == "collar_front" and f.get("view", 0) == vi}
    z = lambda k: float(np.asarray(at[k]).ravel()[-1]) * 1000 if k in at else None
    if cf:  # the neckline at CF, seen: the collar_front traces' bottom ends below the side neck
        D, D_how = float(np.mean([Q[:, 1].max() for Q in cf])) - b_hps, "the collar_front traces' bottoms below the hps marks"
    elif z("cf_neck") is not None:
        D, D_how = z("hps.L") - z("cf_neck"), "the body's hps - cf_neck height"
    else:
        D, D_how = None, "the flat pattern's (no collar_front trace, no cf_neck landmark)"
    D_b = z("hps.L") - z("cb_neck") if z("cb_neck") is not None else None
    return dict(h_side=b_hps - top, T=float(np.mean(ends)), T_ends=ends, cut_away=any(cut), tol=2 * so.TRACE_PX * pl["s"] + pl["residual_mm"],
                fronts=fronts, D=D, D_back=D_b, D_how=D_how,
                how=f"trace {t.get('id')} on view {vi} ({pl['how']}; residual {pl['residual_mm']} mm)")


NEAR_DZ, NECK_TAPER = 100.0, 0.85  # mm; with no girth at the top's height, one this near bounds it: no neck narrows
# to under 0.85 of itself over 100 mm (C381, t s4-11: a stand's top 194 mm round over a 406 mm neck passed, only said)
GIRTH_DZ = 20.0  # mm: a step-3 girth whose loop sits this close to the traced top's height is the girth there


def girth_at(step3: dict, at: dict, h_side: float) -> dict:
    """The step-3 girth taken at the traced top's height (hps + h_side), or the nearest one said (C380, t s4-10: a stand
    whose top edge is 0.86 x its neck edge may grip the neck, and no row compared the top with the body there)."""
    z0 = float(np.asarray(at["hps.L"]).ravel()[-1]) * 1000 + h_side
    best = None
    for m in (step3 or {}).get("measurements") or []:
        L = np.asarray(m.get("loop") or [], float)
        if L.ndim != 2 or L.shape[1] != 3 or "mm" not in m:
            continue
        dz = float(L[:, 2].mean()) * 1000 - z0
        if best is None or abs(dz) < abs(best["dz"]):
            best = {"name": m["name"], "mm": float(m["mm"]), "dz": dz}
    return {"z": z0, "at": best if best and abs(best["dz"]) <= GIRTH_DZ else None, "nearest": best}


def _rest(pc: dict, idx: list) -> np.ndarray:
    """The outline from the neck edge's last point round to its first (the end edges and the free edge), in order."""
    n = len(pc["P"])
    inner = set(idx[1:-1])
    for step in (1, -1):
        out, i = [idx[-1]], idx[-1]
        while True:
            i = (i + step) % n
            out.append(i)
            if i == idx[0] or i in inner:
                break
        if i == idx[0]:
            return pc["P"][out]
    return pc["P"][[idx[-1], idx[0]]]


def heights(N: np.ndarray, R: np.ndarray) -> dict:
    """The drafted stand's heights (m): at its front ends (the tallest free-edge place near each end: a rounded corner
    is passed over), at its middle (CB), and the free edge between the two front places (for the lean)."""
    Nd = N[::max(1, len(N) // 400)]
    d = np.min(np.linalg.norm(R[:, None, :] - Nd[None], axis=2), axis=1)
    L = np.r_[0, np.cumsum(np.linalg.norm(np.diff(R, axis=0), axis=1))]
    a = np.where(L <= END_SHARE * L[-1])[0]
    b = np.where(L >= (1 - END_SHARE) * L[-1])[0]
    i, j = int(a[np.argmax(d[a])]), int(b[np.argmax(d[b])])
    mid = int(np.argmin(np.abs(L - L[-1] / 2)))
    return dict(front=(float(d[i]), float(d[j])), back=float(d[mid]), top=R[i:j + 1], mid=R[mid])


def whole(N: np.ndarray, R: np.ndarray, top: np.ndarray | None, C: np.ndarray):
    """A half stand (its neck edge N, the rest of its outline R from N's last point round to its first, its free edge
    top) mirrored across its end edge C (sewn to its mirror half) into the whole stand the checks read: the neck edge
    from one front end through CB to the other, the rest from that end round the free edge back (C381, t s4-11: each
    half was read as a whole stand, its "CB" the half's middle and its rise the half's sagitta, about a third of the
    front end's)."""
    a, b = C[0], C[-1]
    u = (b - a) / (np.linalg.norm(b - a) or 1.0)
    M = lambda X: 2 * (a + np.outer((X - a) @ u, u)) - X
    near = lambda X, q: float(min(np.linalg.norm(X[0] - q), np.linalg.norm(X[-1] - q)))
    ends = (C[0], C[-1])
    if min(np.linalg.norm(N[0] - e) for e in ends) < min(np.linalg.norm(N[-1] - e) for e in ends):
        N, R = N[::-1], R[::-1]  # (the CB end last)
    far = C[-1] if np.linalg.norm(C[0] - N[-1]) < np.linalg.norm(C[-1] - N[-1]) else C[0]
    k = int(np.argmin(np.linalg.norm(R - far, axis=1)))
    Nw = np.r_[N, M(N[::-1])[1:]]
    Rk = R[k:]
    Rw = np.r_[M(Rk)[::-1], Rk[1:]]
    Tw = None
    if top is not None:
        T = top if np.linalg.norm(top[-1] - far) <= np.linalg.norm(top[0] - far) else top[::-1]
        Tw = np.r_[T, M(T[::-1])[1:]] if near(T, far) < 1e-3 else T
    return Nw, Rw, Tw


def check(p: str, kind: str, N: np.ndarray, R: np.ndarray, top: np.ndarray | None, D: float, D_b: float,
          ref: dict | None, whole: bool = False) -> tuple[str, list]:
    """(value, why[]) for one stand / band (m in, mm out). whole: N / R / top are already the whole stand (two halves
    mirrored: `whole`), so the top's round isn't doubled."""
    from . import draft_shape as ds, pattern
    H = heights(N, R)
    T_ = H["top"] if top is None else top
    r = ds.rise(N, H["mid"])
    lean = pattern.length(T_) / pattern.length(N)
    mm = lambda x: 1000 * x
    hf = mm(float(np.mean(H["front"])))
    val = (f"{p} ({kind}): neck edge {_curve_word(r, D)} {mm(r):+.1f} mm = {r / D:+.2f} x front drop {mm(D):.0f} mm; "
           f"free/neck {lean:.3f}; heights front {mm(H['front'][0]):.0f} / {mm(H['front'][1]):.0f}, back {mm(H['back']):.0f} mm")
    if kind == "band":
        return val + " (a band under a fall: reported, the fall's trace doesn't show it)", []
    if ref is None:
        return val + " (no collar_top trace at step 2: reported, no style assumed)", []
    if "why" in ref:
        return val + f" (trace not placed: {ref['why']})", []
    tol = ref["tol"]  # the neckline's drops in the VIEW (r-hussar): a front tilts over the chest, its flat drop isn't seen
    Dm = ref["D"] if ref.get("D") is not None else mm(D)
    Dbm = ref["D_back"] if ref.get("D_back") is not None else mm(D_b)
    f = float(np.clip(ref["T"] / Dm, 0, 1)) if Dm > 0 else 1.0
    style = "follows the neckline (hugging)" if f >= FOLLOW else "level (standing away)"
    # the rise (r-hussar, build r1: a near-straight neck edge on the tilted neckline built a stand rising 31 deg, not
    # upright): an UPRIGHT stand is a vertical band; developed flat its free edge is straight where the top is level, so
    # its neck edge falls at the front ends by the height it gains there, (1 - f)(D - D_b) seen; a top that follows (f = 1)
    # is jaeger's cone, rising f x JAEGER x the flat drop. Between, the two blended; tol: the heights' own.
    r_exp, r_tol = f * JAEGER_RISE * mm(D) - (1 - f) * (Dm - Dbm), tol
    hf_exp = ref["h_side"] + Dm * (1 - f)
    hb_exp = ref["h_side"] + Dbm * (1 - f)
    val += (f"; traced top ({ref['how']}): {ref['h_side']:.0f} mm above the side neck, drops {ref['T']:.0f} mm to its "
            f"front ends = {f:.2f} x D {Dm:.0f} mm (seen: {ref.get('D_how', 'flat')}; CB {Dbm:.0f}): {style}"
            + (f"; collar_front traced {', '.join(f'{k} {v:.0f}' for k, v in ref['fronts'].items())} mm" if ref["fronts"] else ""))
    why = []
    if abs(mm(r) - r_exp) > r_tol:
        way = "flatter / down (the ends away from the free edge)" if mm(r) > r_exp else "up (the ends towards the free edge)"
        why.append(f"{CURVE_ONLY}{p}: neck edge {_curve_word(r, D)} {mm(r):+.0f} mm at its front ends; a top that {style.split(' (')[0]} "
                   f"({f:.2f} x D) wants {r_exp:+.0f} +- {r_tol:.0f} mm (f x {JAEGER_RISE:.2f} x the flat drop - (1 - f)(D - D_back) "
                   f"seen). change: curve the neck "
                   f"edge's ends {way} by {abs(mm(r) - r_exp) - r_tol:.0f}-{abs(mm(r) - r_exp):.0f} mm (the free edge follows)")
    if ref.get("cut_away"):  # (C377: the front end edge is traced down to the neck; h_front's vertical end isn't this style)
        val += "; front ends cut away (the trace runs down past its corner): their height isn't checked, the back's is"
    elif abs(hf - hf_exp) > tol:
        why.append(f"{p}: front ends {hf:.0f} mm tall; the trace wants h_side + D - T = {ref['h_side']:.0f} + {Dm:.0f} - "
                   f"{ref['T']:.0f} = {hf_exp:.0f} +- {tol:.0f} mm. change: make the stand {abs(hf_exp - hf):.0f} mm "
                   f"{'taller' if hf_exp > hf else 'lower'} at its front ends (the top line drawn {'level' if f < FOLLOW else 'down'} to them)")
    if abs(mm(H["back"]) - hb_exp) > tol:
        why.append(f"{p}: {mm(H['back']):.0f} mm tall at CB; the trace wants h_side + D_back (1 - f) = {hb_exp:.0f} +- "
                   f"{tol:.0f} mm. change: make it {abs(hb_exp - mm(H['back'])):.0f} mm {'taller' if hb_exp > mm(H['back']) else 'lower'} at the back")
    tg = ref.get("top_girth")
    if tg:  # the free edge round against the body's girth at the top's height (C380)
        rnd = 2 * mm(pattern.length(T_)) if p.endswith((".L", ".R")) and not whole else mm(pattern.length(T_))
        g = tg.get("at")
        nb = tg.get("nearest")
        if g is None and nb and abs(nb["dz"]) <= NEAR_DZ and rnd < NECK_TAPER * nb["mm"]:
            why.append(f"{p}: its top edge goes round {rnd:.0f} mm, under {NECK_TAPER:.0%} of the body's {nb['name']} "
                       f"{nb['mm']:.0f} mm taken {abs(nb['dz']):.0f} mm {'below' if nb['dz'] < 0 else 'above'} the top: "
                       f"no neck narrows that much, so it grips. change: lengthen the free edge by "
                       f"{NECK_TAPER * nb['mm'] - rnd:.0f} mm or more (less lean / curve), or take a girth at the top's "
                       f"height (hps + {ref['h_side']:.0f} mm, body_tape add=true) to check it closer (C381)")
        elif g is None:
            val += (f"; top edge round {rnd:.0f} mm: step 3 took no girth at the top's height (hps + {ref['h_side']:.0f} mm)"
                    + (f"; nearest {nb['name']} {nb['mm']:.0f} mm, {nb['dz']:+.0f} mm from it" if nb else "")
                    + ": take one there (body_tape) to check the top doesn't grip")
        elif ref.get("cut_away"):
            val += (f"; top edge round {rnd:.0f} mm vs {g['name']} {g['mm']:.0f} mm at its height: the ends must sit "
                    f">= {max(0.0, g['mm'] - rnd):.0f} mm apart at the top when worn")
        elif rnd < g["mm"] * (1 - 0.01):
            why.append(f"{p}: its top edge goes round {rnd:.0f} mm, under the body's {g['name']} {g['mm']:.0f} mm at that "
                       f"height: it grips the neck. change: lengthen the free edge (less lean / curve) by "
                       f"{g['mm'] - rnd:.0f} mm or more")
        else:
            val += f"; top edge round {rnd:.0f} mm >= {g['name']} {g['mm']:.0f} mm at its height"
    if f >= FOLLOW and lean > STAND_LEAN + 1e-9:
        why.append(f"{p}: free edge {lean:.3f} x its neck edge (a hugging stand <= {STAND_LEAN:.3f}: it must lean in). "
                   "change: shorten the free edge (curve it with the neck edge)")
    return val, why
