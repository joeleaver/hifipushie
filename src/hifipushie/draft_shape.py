"""Garment step 4's flat gate, SHAPE rows (T5b, C295): a pattern piece's curves, per role, against FreeSewing's own drafts.

Why: the flat gate checked lengths only, so a stand drafted as a straight trapezoid (the hussar) and a shirt band drafted
as a rectangle passed it; built, a straight stand follows a front-dropping neckline down into a V and flares like a
funnel (Joe: "Why would it build curved pieces as straight lines?"). Nothing here knows a garment: each row reads a role
off the declarations (role, stiff, folds, seams, place) and compares a shape measure with the same measure taken on a
FreeSewing design's own part (4.10.2, measured on wf_simon's step-3 measurements; /mnt/data/hifipushie/t5b/scripts/
ref_measure.py). Every FAIL names what to change in the design (`change`) and goes back to step 4.

Rows (`rows(B, decl, step1)`; B = draft_own.block + cloth.pieces, its pieces in FreeSewing's frame, y = the grain):
  shape_stand: a STAND / BAND (role collar_stand / collar_band / neckband, or a stiff piece sewn to edges named "neck"):
    rise = how far its neck edge's ENDS sit towards its free edge from the chord through them, vs the neckline's front
    drop D (the largest grain-wise drop of the neck edges it is sewn to). Source: jaeger.collarStand rises 31.0 mm on a
    65.4 mm front drop (0.47 D): a stand alone needs >= half that (STAND_RISE). A band under a fall (simon's place):
    simon.collarStand at its default options DROPS 7.9 mm (0.12 D) and at its own most-rising options (collarStandBend
    0, collarStandCurve 5) rises; a band needs a rise > 0 (BAND_RISE: a straight band is 0, the shirt's T5 rectangle).
    lean = free edge / neck edge: jaeger 0.978 -> a stand <= 0.989 (half its shortfall); a band <= 1.0.
  shape_fall: a FALL (role collar_fall, or a piece with a "roll" fold): its outer line (an edge named outer / fall /
    edge, else its fold line) over its stand seam: simon.collar 1.024, jaeger.collar 1.038 -> >= 1.012 (half simon's).
  shape_cap: a SLEEVE cap (a seam joining pieces placed on an arm to pieces on the torso): cap height (grain-wise span
    of the cap edges; a two-piece sleeve's parts share FreeSewing's frame) over the armhole depth (the deepest body
    piece's armhole span): brian 0.52 (a shirt block), bent 0.72 (a two-piece jacket sleeve) -> [0.47, 0.79].
  shape_seam_curve: a seam whose one side is curved (sagitta / chord > CURVED: simon's stand neck edge, the least
    curved neck edge in the pack, is 0.021) and the other straight (< STRAIGHT: a FreeSewing `line`, 0) fails, naming
    the straight edge (a curved neckline sewn to a straight edge). Known false alarm: a straight waistband on a skirt.
"""
from __future__ import annotations

import numpy as np

STAND_RISE = 0.5 * 31.0 / 65.4  # jaeger.collarStand: rise / front drop, halved
BAND_RISE = 0.0  # a band under a fall: rises at all (simon's options allow it; straight = 0)
STAND_LEAN = 1 - 0.5 * (1 - 0.978)  # jaeger.collarStand free / neck edge
BAND_LEAN = 1.0
FALL_SPREAD = 1 + 0.5 * 0.024  # simon.collar outer / stand seam, halved excess
CAP = (0.9 * 0.521, 1.1 * 0.715)  # brian.sleeve, bent's top + under sleeve: cap height / armhole depth
CURVED, STRAIGHT = 0.02, 0.005  # sagitta / chord
STAND_ROLES = ("collar_stand", "collar_band", "neckband")
FALL_ROLES = ("collar_fall",)
FREE_NAMES = ("top", "free", "outer", "edge")
OUTER_NAMES = ("outer", "fall", "edge")


def _pts(B: dict, e: str) -> np.ndarray:
    from . import pattern
    p, arc = e.split(":", 1)
    pc = B["pieces"][p]
    return pc["P"][pattern.arc_indices(pc, arc)]


def _sides(s) -> list:
    return [s] if isinstance(s, str) else list(s)


def sagitta(P: np.ndarray) -> float:
    """Max distance of the polyline from its chord, over the chord (0 = straight)."""
    a, b = P[0], P[-1]
    c = np.linalg.norm(b - a)
    if c < 1e-9:
        return 0.0
    t = (b - a) / c
    d = P - a
    return float(np.max(np.abs(d[:, 0] * t[1] - d[:, 1] * t[0])) / c)


def rise(N: np.ndarray, toward: np.ndarray) -> float:
    """How far the ends of edge N sit towards `toward` (a point on the free side) from the edge's middle (m)."""
    L = np.r_[0, np.cumsum(np.linalg.norm(np.diff(N, axis=0), axis=1))]
    m = np.array([np.interp(L[-1] / 2, L, N[:, k]) for k in range(2)])
    c = (N[0] + N[-1]) / 2
    n = toward - c
    n = n / (np.linalg.norm(n) or 1.0)
    return float(np.dot(c - m, n))


def _free_edge(pc: dict, N: np.ndarray) -> np.ndarray:
    """The outline points far from the neck edge (>= 0.9 of the farthest): a stand's free edge without its ends."""
    P = pc["P"]
    d = np.min(np.linalg.norm(P[:, None, :] - N[None, ::max(1, len(N) // 200), :], axis=2), axis=1)
    far = np.where(d >= 0.9 * d.max())[0]
    # the longest run of consecutive outline indices
    runs, cur = [], [far[0]]
    for i in far[1:]:
        if i == cur[-1] + 1:
            cur.append(i)
        else:
            runs.append(cur)
            cur = [i]
    runs.append(cur)
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == len(P) - 1:
        runs[0] = runs.pop() + runs[0]
    return P[max(runs, key=len)]


def _role(nm: str, decl: dict, step1: dict) -> str:
    return str((decl.get("pieces") or {}).get(nm, {}).get("role") or (step1.get("pieces") or {}).get(nm, {}).get("role") or "")


def _seam_pairs(B: dict):
    for s in B.get("seams") or []:
        yield _sides(s[0]), _sides(s[1])


def _edge_name(B: dict, e: str) -> str:
    p, arc = e.split(":", 1)
    return next((k for k, v in (B.get("edge_arcs") or {}).get(p, {}).items() if v == arc), arc)


def _drop(B: dict, edges: list) -> float:
    return max(float(np.ptp(_pts(B, e)[:, 1])) for e in edges)


def stand_rows(B: dict, decl: dict, step1: dict) -> dict:
    from . import pattern
    stiff = set(decl.get("stiff") or [])
    falls = fall_pieces(B, decl, step1)
    out, why, vals = [], [], []
    for A, Bs in _seam_pairs(B):
        for mine, other in ((A, Bs), (Bs, A)):
            if len(mine) != 1:
                continue
            p = mine[0].split(":", 1)[0]
            role = _role(p, decl, step1)
            on_neck = all(_edge_name(B, e) == "neck" and e.split(":", 1)[0] not in stiff for e in other)
            if p in falls or not (role in STAND_ROLES or (p in stiff and on_neck)) or not on_neck:
                continue
            pc = B["pieces"][p]
            N = _pts(B, mine[0])
            top = None
            for X, Y in _seam_pairs(B):  # a fall sewn to this piece: that edge is the free edge
                for a, b in ((X, Y), (Y, X)):
                    if len(a) == 1 and a[0].split(":", 1)[0] == p and a[0] != mine[0] and all(
                            e.split(":", 1)[0] in falls for e in b):
                        top = _pts(B, a[0])
            for k in FREE_NAMES:
                arc = (B.get("edge_arcs") or {}).get(p, {}).get(k)
                if top is None and arc:
                    top = pc["P"][pattern.arc_indices(pc, arc)]
            band = top is not None and any(f for f in falls)
            if top is None:
                top = _free_edge(pc, N)
            D = _drop(B, other)
            r = rise(N, top.mean(0))
            lean = pattern.length(top) / pattern.length(N)
            rmin, lmax = (BAND_RISE, BAND_LEAN) if band else (STAND_RISE, STAND_LEAN)
            kind = "band" if band else "stand"
            vals.append(f"{p} ({kind}): rise {1000 * r:+.1f} mm = {r / D:+.2f} x front drop {1000 * D:.0f} mm; "
                        f"free/neck {lean:.3f}")
            if r / D <= rmin + 1e-9 if band else r / D < rmin:
                why.append(f"{p}: its neck edge {'drops' if r < 0 else 'is straight' if abs(r) < 1e-3 else 'rises too little'} "
                           f"at its front ends ({1000 * r:+.1f} mm; target {'> 0' if band else f'>= {rmin:.2f} x {1000 * D:.0f} = {1000 * rmin * D:.0f} mm'}). "
                           f"change: curve the neck edge so its front ends rise towards the free edge (the free edge follows), "
                           f"e.g. extend a FreeSewing stand ({'simon.collarStand: collarStandBend 0, collarStandCurve up' if band else 'jaeger.collarStand'})")
            if lean > lmax + 1e-9:
                why.append(f"{p}: free edge {lean:.3f} x its neck edge (target <= {lmax:.3f}: it must lean in). change: "
                           "shorten the free edge (bring its ends in / curve it with the neck edge)")
            out.append(p)
    return {"id": "shape_stand", "status": ("FAIL" if why else "PASS") if out else "INFO",
            "value": "; ".join(vals) if vals else "no stand / band",
            "target": f"stand rise >= {STAND_RISE:.2f} x front drop (jaeger.collarStand / 2), free/neck <= {STAND_LEAN:.3f}; "
                      f"band (under a fall) rise > 0 (simon.collarStand's rising options), free/neck <= {BAND_LEAN:.2f}",
            "why": "; ".join(why), "change": "; ".join(w.split("change: ", 1)[-1] for w in why), "back_to": "4"}


def fall_pieces(B: dict, decl: dict, step1: dict) -> set:
    roll = {f.get("piece") for f in B.get("folds") or [] if f.get("kind") == "roll"}
    return {p for p in B["pieces"] if p in roll or _role(p, decl, step1) in FALL_ROLES}


def _line(B: dict, p: str, ln):
    from . import pattern
    pc = B["pieces"][p]
    if isinstance(ln, dict) and isinstance(ln.get("edge"), str) and not ln.get("offset"):
        return pc["P"][pattern.arc_indices(pc, ln["edge"])]
    if isinstance(ln, str):
        return pc["P"][pattern.arc_indices(pc, (B.get("edge_arcs") or {}).get(p, {}).get(ln, ln))]
    if isinstance(ln, list) and all(isinstance(x, str) and x in pc["names"] for x in ln):
        return pc["P"][[pc["names"][x] for x in ln]]
    return None


def fall_rows(B: dict, decl: dict, step1: dict) -> dict:
    from . import pattern
    vals, why = [], []
    for p in sorted(fall_pieces(B, decl, step1)):
        seam = next((a[0] for A, Bs in _seam_pairs(B) for a, b in ((A, Bs), (Bs, A))
                     if len(a) == 1 and a[0].split(":", 1)[0] == p and all(e.split(":", 1)[0] != p for e in b)), None)
        if seam is None:
            vals.append(f"{p}: no stand seam")
            continue
        S = _pts(B, seam)
        arcs = (B.get("edge_arcs") or {}).get(p, {})
        out = next((B["pieces"][p]["P"][pattern.arc_indices(B["pieces"][p], arcs[k])] for k in OUTER_NAMES if k in arcs), None)
        src = "outer edge"
        if out is None:
            out = next((x for f in B.get("folds") or [] if f.get("piece") == p and (x := _line(B, p, f.get("line"))) is not None), None)
            src = "fold line"
        if out is None:
            vals.append(f"{p}: no outer edge or fold line to measure")
            continue
        s = pattern.length(out) / pattern.length(S)
        vals.append(f"{p}: {src} {1000 * pattern.length(out):.0f} / stand seam {1000 * pattern.length(S):.0f} mm = {s:.3f}")
        if s < FALL_SPREAD:
            why.append(f"{p}: its {src} is {s:.3f} x its stand seam (target >= {FALL_SPREAD:.3f}): it can't turn down and "
                       "spread over the stand. change: lengthen the outer edge (curve the stand seam's ends up / spread "
                       "the fall), e.g. extend simon.collar (collarBend, collarFlare)")
    return {"id": "shape_fall", "status": ("FAIL" if why else "PASS") if vals else "INFO",
            "value": "; ".join(vals) if vals else "no fall", "why": "; ".join(why),
            "target": f"outer / stand seam >= {FALL_SPREAD:.3f} (simon.collar 1.024, jaeger.collar 1.038)",
            "change": "; ".join(w.split("change: ", 1)[-1] for w in why), "back_to": "4"}


def cap_rows(B: dict, decl: dict, step1: dict) -> dict:
    vals, why = [], []
    on = lambda e, w: str((B["pieces"][e.split(":", 1)[0]].get("wrap") or {}).get("to", "")).startswith(w)
    for A, Bs in _seam_pairs(B):
        for cap, arm in ((A, Bs), (Bs, A)):
            if not (all(on(e, "arm") for e in cap) and all(on(e, "torso") for e in arm)):
                continue
            h = float(np.ptp(np.concatenate([_pts(B, e) for e in cap])[:, 1]))
            pcs = {e.split(":", 1)[0] for e in arm}
            dep = max(float(np.ptp(np.concatenate([_pts(B, e) for e in arm if e.startswith(q + ":")])[:, 1])) for q in pcs)
            r = h / dep
            nm = "+".join(sorted({e.split(":", 1)[0] for e in cap}))
            vals.append(f"{nm}: cap {1000 * h:.0f} / armhole depth {1000 * dep:.0f} mm = {r:.2f}")
            if not CAP[0] <= r <= CAP[1]:
                why.append(f"{nm}: cap height {r:.2f} x the armhole depth (target [{CAP[0]:.2f}, {CAP[1]:.2f}]). change: "
                           f"{'raise' if r < CAP[0] else 'lower'} the cap (extend brian's sleeve / bent's two-piece sleeve "
                           "and set its sleevecapHeight-type option)")
    return {"id": "shape_cap", "status": ("FAIL" if why else "PASS") if vals else "INFO",
            "value": "; ".join(vals) if vals else "no set-in sleeve", "why": "; ".join(why),
            "target": f"cap height / armhole depth in [{CAP[0]:.2f}, {CAP[1]:.2f}] (brian 0.52, bent 0.72)",
            "change": "; ".join(w.split("change: ", 1)[-1] for w in why), "back_to": "4"}


def seam_curve_rows(B: dict, decl: dict, step1: dict) -> dict:
    from . import pattern
    why, n = [], 0
    for A, Bs in _seam_pairs(B):
        n += 1
        k = []
        for side in (A, Bs):
            P = [_pts(B, e) for e in side]
            w = np.array([pattern.length(x) for x in P])
            k.append(float(np.dot([sagitta(x) for x in P], w) / (w.sum() or 1)))
        for i in (0, 1):
            if k[i] < STRAIGHT and k[1 - i] > CURVED:
                st = [_label(B, e) for e in (A, Bs)[i]]
                why.append(f"{' + '.join(st)} is straight (sagitta {k[i]:.3f}) but is sewn to a curved edge "
                           f"({' + '.join(_label(B, e) for e in (A, Bs)[1 - i])}: {k[1 - i]:.3f}). change: draw "
                           f"{' + '.join(st)} curved to match (extend the FreeSewing part that has it)")
    return {"id": "shape_seam_curve", "status": "FAIL" if why else "PASS",
            "value": f"{n} seams, {len(why)} straight-to-curved", "why": "; ".join(why[:6]),
            "target": f"no seam straight (sagitta/chord < {STRAIGHT}) on one side and curved (> {CURVED}) on the other",
            "change": "; ".join(w.split("change: ", 1)[-1] for w in why[:6]), "back_to": "4"}


def _label(B: dict, e: str) -> str:
    return f"{e.split(':', 1)[0]}:{_edge_name(B, e)}"


def rows(B: dict, decl: dict, step1: dict) -> list:
    out = []
    for f in (stand_rows, fall_rows, cap_rows, seam_curve_rows):
        try:
            out.append(f(B, decl, step1))
        except (KeyError, ValueError, IndexError, TypeError) as x:
            out.append({"id": "shape_" + f.__name__.replace("_rows", ""), "status": "INFO",
                        "value": "n/a", "why": f"{type(x).__name__}: {str(x)[:160]}"})
    return out
