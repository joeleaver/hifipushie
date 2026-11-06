"""Garment step 4's flat gate, SHAPE rows (T5b, C295): a pattern piece's curves, per role, against FreeSewing's own drafts.

Why: the flat gate checked lengths only, so a stand drafted as a straight trapezoid (the hussar) and a shirt band drafted
as a rectangle passed it; built, a straight stand follows a front-dropping neckline down into a V and flares like a
funnel (Joe: "Why would it build curved pieces as straight lines?"). Nothing here knows a garment: each row reads a role
off the declarations (role, stiff, folds, seams, place) and compares a shape measure with the same measure taken on a
FreeSewing design's own part (4.10.2, measured on wf_simon's step-3 measurements; /mnt/data/hifipushie/t5b/scripts/
ref_measure.py). Every FAIL names what to change in the design (`change`) and goes back to step 4.

Rows (`rows(B, decl, step1)`; B = draft_own.block + cloth.pieces, its pieces in FreeSewing's frame, y = the grain):
  shape_stand: a STAND / BAND (role collar_stand / collar_band / neckband, or a stiff piece sewn to edges named neck*):
    its curve and heights DECIDED BY THE REFERENCE (T5c, C300; draft_stand.py, its docstring the derivation): step 2's
    collar_top trace says whether the top follows the neckline down (the hugging stand: neck edge rising, jaeger) or
    stays level (standing away: taller at its front ends, neck edge straight or falling). No trace: INFO (no style is a
    law). T5b's universal "the ends rise" rule was one style taken for all (Joe: "the collar curves the wrong direction").
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

FALL_SPREAD = 1 + 0.5 * 0.024  # simon.collar outer / stand seam, halved excess
CAP = (0.9 * 0.521, 1.1 * 0.715)  # brian.sleeve, bent's top + under sleeve: cap height / armhole depth
CURVED, STRAIGHT = 0.02, 0.005  # sagitta / chord
STAND_ROLES = ("collar_stand", "collar_band", "neckband")
LAPEL_ROLES = ("front", "facing")  # (t s4-5: a lapel's roll line made the front and facing read as a collar's fall)
AMBIGUOUS_NAMES = ("collar",)  # (a name that doesn't say stand or fall: the seams decide, not the name: C363)
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


def _role(nm: str, decl: dict, step1: dict) -> str:
    """The declared role (draft, then step 1), else the role its NAME gives (garment_design.role_of: C363, t s4-3: an
    undercollar with no declared role was judged as a shirt's stand, so C361's name fix never reached this gate)."""
    from .garment_design import role_of
    r = (decl.get("pieces") or {}).get(nm, {}).get("role") or (step1.get("pieces") or {}).get(nm, {}).get("role")
    if r:
        return str(r)
    base = nm.rsplit(".", 1)[0] if nm.endswith((".L", ".R")) else nm
    if base.lower() in AMBIGUOUS_NAMES:  # ("collar" alone: a shirt's band or a fall: its structure decides, t8)
        return ""
    from .garment_design import kb
    r = role_of(nm)  # (it returns the name itself when no alias matched; "front" IS a role: C366)
    return r if r != base or r in kb()["roles"] else ""


def is_neck(name: str) -> bool:
    """An edge on the neck line: "neck", "neckline", "neck_front", "neck_back" (C377, t s4-7: only "neck" counted, so a
    stand sewn by its neck_front / neck_back to the body's necklines was no stand and its canvas read as a fall)."""
    return str(name).lower().startswith("neck")


def layers(B: dict) -> dict:
    """{layer: host}: a piece whose every seam joins one of its edges to the SAME-NAMED edge of one other piece (a canvas,
    facing or lining cut to that piece: top to top, end to end). Its shape is its host's, so no shape row judges it
    (C377, t s4-7: a stand collar's canvas and inner collar, sewn top to top, were judged as falls sewn on the stand).
    A fall is sewn by a different edge (its stand seam to the stand's top), so it is never a layer."""
    seen = {}
    for A, Bs in _seam_pairs(B):
        for mine, other in ((A, Bs), (Bs, A)):
            for e in mine:
                p = e.split(":", 1)[0]
                ok = len(mine) == 1 and len(other) == 1 and other[0].split(":", 1)[0] != p and \
                    _edge_name(B, e) == _edge_name(B, other[0])
                seen.setdefault(p, []).append(other[0].split(":", 1)[0] if ok else None)
    out = {p: hs[0] for p, hs in seen.items() if hs and None not in hs and len(set(hs)) == 1}
    return {p: h for p, h in out.items() if out.get(h) != p}  # (two pieces sewn only to each other: neither)


def _mirror_sewn(B: dict, p: str) -> bool:
    """p (a sided piece) is sewn to its mirror by a same-named edge (back.L:cb = back.R:cb)."""
    return bool(p[-2:] in (".L", ".R") and _half_seam(B, p))


def _half_seam(B: dict, p: str):
    """(mirror piece, p's arc, edge name) when p (X.L / X.R) is sewn to its mirror X.R / X.L by the same-named edge;
    else None."""
    if p[-2:] not in (".L", ".R"):
        return None
    q = p[:-2] + {".L": ".R", ".R": ".L"}[p[-2:]]
    for A, Bs in _seam_pairs(B):
        for mine, other in ((A, Bs), (Bs, A)):
            if len(mine) == len(other) == 1 and mine[0].split(":", 1)[0] == p and other[0].split(":", 1)[0] == q \
                    and _edge_name(B, mine[0]) == _edge_name(B, other[0]):
                return q, mine[0].split(":", 1)[1], _edge_name(B, mine[0])
    return None


def _seam_pairs(B: dict):
    for s in B.get("seams") or []:
        yield _sides(s[0]), _sides(s[1])


def _edge_name(B: dict, e: str) -> str:
    p, arc = e.split(":", 1)
    return next((k for k, v in (B.get("edge_arcs") or {}).get(p, {}).items() if v == arc), arc)


def full_arc(pc: dict, arcs: list) -> str:
    """ONE arc for a piece's edges sewn to one line (F2, t8: a stand sewn to front:neck AND back:neck as two edges, each
    half read alone, came out "near straight" at +0.9 mm while its front ends rose 18 mm, and as two stands). The arcs
    chain end to end; a chain from a point on the mirror line (no "<name>.m") to one with a mirror ("fe" / "fe.m": the
    half of a piece cut on the fold) is the whole edge "fe.m>cb>fe"."""
    names = pc.get("names") or {}
    ends = [(a.split(">")[0], a.split(">")[-1]) for a in arcs]
    cnt = {}
    for e in ends:
        for k in e:
            cnt[k] = cnt.get(k, 0) + 1
    tips = [k for k, c in cnt.items() if c == 1] or [ends[0][0], ends[-1][-1]]
    shared = [k for k, c in cnt.items() if c > 1]
    a, b = (tips + tips)[:2]
    if len(tips) == 2 and (f"{a}.m" in names) != (f"{b}.m" in names):
        edge, axis = (a, b) if f"{a}.m" in names else (b, a)
        return f"{edge}.m>{axis}>{edge}"
    if len(arcs) == 1:
        return arcs[0]
    return f"{a}>{shared[0]}>{b}" if shared else arcs[0]


def stand_rows(B: dict, decl: dict, step1: dict, ref: dict | None = None) -> dict:
    """shape_stand: each stand / band's curve and heights against step 2's collar traces (draft_stand.py, its docstring
    the derivation); `ref` = draft_stand.reference(plan, at). No trace: INFO, the curve reported, no style assumed.
    ONE row per piece: all its edges sewn to a neck line read as one neck edge (full_arc), its free edge likewise."""
    from . import draft_stand as dst, pattern
    stiff = set(decl.get("stiff") or [])
    falls = fall_pieces(B, decl, step1)
    lay = layers(B)
    out, why, vals = [], [], []
    cand = {}  # piece -> ([its neck-sewn arcs], [the neck edges they're sewn to])
    for A, Bs in _seam_pairs(B):
        for mine, other in ((A, Bs), (Bs, A)):
            if len(mine) != 1:
                continue
            p = mine[0].split(":", 1)[0]
            if p in lay:
                continue
            role = _role(p, decl, step1)
            on_neck = all(is_neck(_edge_name(B, e)) and e.split(":", 1)[0] not in stiff for e in other)
            if p in falls or not (role in STAND_ROLES or (p in stiff and on_neck)) or not on_neck:
                continue
            c = cand.setdefault(p, ([], []))
            c[0].append(mine[0].split(":", 1)[1])
            c[1].extend(other)
    for p, (arcs, other) in cand.items():
        pc = B["pieces"][p]
        idx = pattern.arc_indices(pc, full_arc(pc, arcs))
        N = pc["P"][idx]
        top = None
        for X, Y in _seam_pairs(B):  # a fall sewn to this piece: that edge is the free edge
            for a, b in ((X, Y), (Y, X)):
                if len(a) == 1 and a[0].split(":", 1)[0] == p and a[0].split(":", 1)[1] not in arcs and all(
                        e.split(":", 1)[0] in falls for e in b):
                    top = pc["P"][pattern.arc_indices(pc, full_arc(pc, [a[0].split(":", 1)[1]]))]
        band = top is not None
        for k in FREE_NAMES:
            arc = (B.get("edge_arcs") or {}).get(p, {}).get(k)
            if top is None and arc:
                top = pc["P"][pattern.arc_indices(pc, full_arc(pc, [arc]))]
        drops = sorted(float(np.ptp(_pts(B, e)[:, 1])) for e in other)
        R = dst._rest(pc, idx)
        half = _half_seam(B, p)
        if half and half[0] in out:  # (its mirror half already judged the whole)
            continue
        if half:  # (C381: a half sewn to its mirror at an end edge is judged whole)
            N, R, top = dst.whole(N, R, top, pc["P"][pattern.arc_indices(pc, half[1])])
        v, w = dst.check(p, "band" if band else "stand", N, R, top, drops[-1],
                         drops[0] if len(drops) > 1 else 0.0, ref, whole=bool(half))
        if half:
            v = v.replace(f"{p} ({'band' if band else 'stand'})", f"{p} + {half[0]} (whole: mirrored at {p}:{half[2]})", 1)
        elif p[-2:] in (".L", ".R") and p[:-2] + {".L": ".R", ".R": ".L"}[p[-2:]] in B["pieces"] and any(
                _mirror_sewn(B, e.split(":", 1)[0]) for e in other):
            w.append(f"{p}: half a stand, not joined to {p[:-2] + {'.L': '.R', '.R': '.L'}[p[-2:]]} though the body it is "
                     "sewn to joins its own halves: sew the two halves' end edges (a seam P.L:cb = P.R:cb) or cut it as "
                     "one piece on the fold (pieces.P {part, fold: \"x0\"}) (C381)")
        vals.append(v)
        why += w
        out.append(p)
    judged = bool(out) and ref is not None and "why" not in ref
    # A VERDICT again on the heights (r-hussar): D is the neckline's drop SEEN, and three builds back the heights (c1's
    # fronts 108 mm, the flat D's ask, built lying out and too tall: collar_height FAIL; r1 / r2's 82 / 48 mm: PASS; T8's
    # 46 mm fronts: collar_front's top corners low). The curve's why stays report-only (draft_stand.CURVE_ONLY).
    hard = [w for w in why if not w.startswith(dst.CURVE_ONLY)]
    status = ("FAIL" if hard else "INFO (curve would FAIL)" if why else "PASS" if judged else "INFO") if out else "INFO"
    return {"id": "shape_stand", "status": status,
            "value": "; ".join(vals) if vals else "no stand / band",
            "target": ("step 2's collar_top trace decides (draft_stand.py): rise = f x %.2f x D +- %.2f D (f = the share of "
                       "the neckline's drop D the top follows), front height = h_side + D - T, CB = h_side + D_back (1 - f), "
                       "lean <= %.3f when f >= %.1f" % (dst.JAEGER_RISE, dst.STAND_RISE, dst.STAND_LEAN, dst.FOLLOW)),
            "why": "; ".join(why), "change": "; ".join(x.split("change: ", 1)[-1] for x in why), "back_to": "4"}


def fall_pieces(B: dict, decl: dict, step1: dict) -> set:
    """Falls: role collar_fall, a roll fold, or (F2, t8) a piece sewn ONLY to a stand-role / stiff piece's edges other
    than its neck edge, itself on no neck: a fall sewn on a band's top (it was read as nothing, the band as two stands)."""
    roll = {f.get("piece") for f in B.get("folds") or [] if f.get("kind") == "roll"
            and _role(f.get("piece"), decl, step1) not in LAPEL_ROLES}  # (a front's roll fold is its lapel: C366)
    lay = layers(B)
    falls = {p for p in B["pieces"] if p not in lay and (p in roll or _role(p, decl, step1) in FALL_ROLES)}
    stiff = set(decl.get("stiff") or [])
    standish = {p for p in B["pieces"] if _role(p, decl, step1) in STAND_ROLES or p in stiff}
    to, necked = {}, set()
    for A, Bs in _seam_pairs(B):
        for mine, other in ((A, Bs), (Bs, A)):
            for e in mine:
                to.setdefault(e.split(":", 1)[0], []).extend(other)
                if is_neck(_edge_name(B, e)):
                    necked.add(e.split(":", 1)[0])
    for p, other in to.items():
        if p in falls or p in lay or p in necked or _role(p, decl, step1) in STAND_ROLES or not other:
            continue
        if all(e.split(":", 1)[0] in standish and e.split(":", 1)[0] != p and not is_neck(_edge_name(B, e)) for e in other):
            falls.add(p)
    return falls


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
    """shape_cap, ONE row per sleeve (C361): the arm pieces sewn to each other are one sleeve (a two-piece sleeve's top +
    under), its cap = every edge of them sewn to the torso, its height over the deepest of their torso partners' armhole
    spans (t s4-1: each of three cap edges was judged alone against its own panel)."""
    vals, why = [], []
    on = lambda e, w: str((B["pieces"][e.split(":", 1)[0]].get("wrap") or {}).get("to", "")).startswith(w)
    pc = lambda e: e.split(":", 1)[0]
    caps, arm_links = [], []
    for A, Bs in _seam_pairs(B):
        for cap, body in ((A, Bs), (Bs, A)):
            if all(on(e, "arm") for e in cap) and all(on(e, "torso") for e in body):
                caps.append((cap, body))
        if all(on(e, "arm") for e in A + Bs):
            arm_links.append({pc(e) for e in A + Bs})
    groups: list = []  # (arm pieces joined by seams: one sleeve)
    for cap, _ in caps:
        groups.append({pc(e) for e in cap})
    for link in arm_links:
        groups.append(set(link))
    merged = []
    for g in groups:
        for m in [m for m in merged if m & g]:
            g |= m
            merged.remove(m)
        merged.append(g)
    for g in merged:
        mine = [(c, b) for c, b in caps if {pc(e) for e in c} <= g]
        if not mine:
            continue
        ce = [e for c, _ in mine for e in c]
        be = [e for _, b in mine for e in b]
        h = float(np.ptp(np.concatenate([_pts(B, e) for e in ce])[:, 1]))
        dep = max(float(np.ptp(np.concatenate([_pts(B, e) for e in be if pc(e) == q])[:, 1])) for q in {pc(e) for e in be})
        r = h / dep
        nm = "+".join(sorted(g))
        vals.append(f"{nm}: cap {1000 * h:.0f} / armhole depth {1000 * dep:.0f} mm = {r:.2f}")
        if not CAP[0] <= r <= CAP[1]:
            why.append(f"{nm}: cap height {r:.2f} x the armhole depth (target [{CAP[0]:.2f}, {CAP[1]:.2f}]). change: "
                       f"{'raise' if r < CAP[0] else 'lower'} the cap (extend brian's sleeve / bent's two-piece sleeve "
                       "and set its sleevecapHeight-type option)")
    return {"id": "shape_cap", "status": ("FAIL" if why else "PASS") if vals else "INFO",
            "value": "; ".join(vals) if vals else "no set-in sleeve",
            "target": f"cap height / armhole depth in [{CAP[0]:.2f}, {CAP[1]:.2f}] (brian 0.52, bent 0.72)",
            "why": "; ".join(why), "change": "; ".join(x.split("change: ", 1)[-1] for x in why), "back_to": "4"}


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


def rows(B: dict, decl: dict, step1: dict, stand_ref: dict | None = None) -> list:
    out = []
    for f in (stand_rows, fall_rows, cap_rows, seam_curve_rows):
        try:
            out.append(f(B, decl, step1, stand_ref) if f is stand_rows else f(B, decl, step1))
        except (KeyError, ValueError, IndexError, TypeError) as x:
            out.append({"id": "shape_" + f.__name__.replace("_rows", ""), "status": "INFO",
                        "value": "n/a", "why": f"{type(x).__name__}: {str(x)[:160]}"})
    return out
