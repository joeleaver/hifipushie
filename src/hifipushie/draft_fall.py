"""Garment step 4's flat gate, the FALL's landing (C408): where a turn-down collar's outer edge lies, and how long it must be.

Why: shape_fall only had a floor (outer >= 1.012 x its stand seam, simon's shirt collar) against the first edge the fall was
sewn by. On a notch collar that edge is the gorge (68 mm, sewn to the facing), so trial s4-20's suit collar read "outer
558 / stand seam 68 = 8.230 PASS" while its outer edge was 23 % over its whole neck line (452 mm) and the sheet showed a
strong crescent. A turn-down collar drafted that curved stands off the garment (its fall flares); drafted too straight
it pulls and strangles the neck. A pattern maker decides it by where the fall's outer edge LANDS: it lies on the
garment (fall depth - stand height) below the neck seam, so it must be as long as the line on the garment at that
depth, over the stretch the collar covers, plus the cloth's lift (it lies on the shell, not in it).

The row (`row(B, decl, step1)`, id shape_fall_landing). Nothing here knows a garment:
  the collar = each fall (draft_shape.fall_pieces) with the stand / stiff / fall pieces sewn to it by edges that aren't
    neck edges (a top collar + its undercollar; a shirt collar + its band); layers are left out.
  the garment's neck line = the edges outside the collar it is sewn to by a seam with a neck edge (draft_shape.is_neck)
    on either side: the fronts' and backs' necks.
  the stretch the outer edge covers (N): a fall's own edges sewn to that neck line (an undercollar's neck edges: notch to
    notch on a notch collar), else its edges sewn to its stand (a shirt collar on its band: collar point to point).
  the depth d = fall - stand at CB, read off the drafted collar: with a roll fold on a fall, from the fold line's CB
    point (its middle; its end on the CB seam for a half collar) to the outline (stand: the nearest outline that isn't
    the outer edge; fall: the outer edge); with no roll fold, the stand piece's height at its middle (its edge sewn to
    the fall to its neck edge) and the fall's depth (outer edge to its edge sewn to the stand). No fold and no stand:
    INFO (declare the roll fold).
  the line: each neck edge offset d into its own flat piece (the pieces are the garment's surface unrolled: a pattern
    maker lays the collar on the bodice pattern, shoulders together, and walks the line at the fall's depth), its
    length over the neck line's length = the spread k. A front's neck edge (role front / facing: draft_shape.LAPEL_ROLES)
    is counted at its own length: in front the collar turns with the lapel about one roll line (a shirt's collar rides
    its band to the points), so its outer edge runs beside its neck edge; the fall lies DOWN on the garment only behind
    (the tailor's rule: the fall is set on the back neck). Offset in front too, simon's own shirt collar (1.024 x its
    stand seam) would read 5-8 % short and a notch collar's gorge corner would add an arc it never makes. Target = k N + 2 pi LIFT (N / neck line, at most 1): the fall
    goes round the neck lifted by the shell and its own cloth.
  FAIL: outer / target off by more than TOL; too long -> straighten the collar (less curve), too short -> spread it.
    A fall shallower than its stand (d <= 0) FAILs: it doesn't cover the neck seam.
Not known: the stand tapers to the collar's ends, so d held at its CB value overstates the line near the ends a little
(a notch collar's ends lie on the lapel); TOL holds that.
"""
from __future__ import annotations

import numpy as np

LIFT = 0.0015  # m: the fall's middle lies over the garment's middle by half of each: a suit's shell with its canvas
# (about 1.5 mm) and the fall's two layers (about 1.5 mm); a collar sewn round the whole neck line turns once round
TOL = 0.04  # outer / target: a wool fall's edge is shrunk or stretched with the iron by about 2 % (1 cm round a 45 cm
# collar: tailors do it); the line itself is placed to about 2 % (the CB depth held to the ends, offsets across seams)


def _ds():
    from . import draft_shape
    return draft_shape


def _piece(e: str) -> str:
    return e.split(":", 1)[0]


def _seg_dist(Q: np.ndarray, E: np.ndarray) -> np.ndarray:
    """Each point of Q's distance to the polyline E."""
    A, Bb = E[:-1][None], E[1:][None]
    q = Q[:, None, :]
    ab = Bb - A
    t = np.clip(np.sum((q - A) * ab, axis=2) / np.maximum(np.sum(ab * ab, axis=2), 1e-18), 0, 1)
    return np.min(np.linalg.norm(q - (A + t[..., None] * ab), axis=2), axis=1)


def offset_length(E: np.ndarray, P: np.ndarray, d: float, step: float = 0.001) -> float:
    """The length of the line d into the piece (outline P) from its edge E: each segment's offset, round arcs where the
    edge turns away from the piece, the swallowtails where it turns in cut off (points nearer the edge than d), what
    lies outside the piece left out; flat ends (the offset stops square to the edge's ends)."""
    from . import pattern
    E = pattern._resampled(np.asarray(E, float), step)
    if len(E) < 2 or d <= 0:
        return pattern.length(E)
    t = np.diff(E, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-15
    n = np.c_[-t[:, 1], t[:, 0]]
    k = len(n) // 2
    mid = 0.5 * (E[k] + E[k + 1])
    if not pattern._poly_inside(P, (mid + 0.002 * n[k])[None])[0]:
        n = -n
    Q = [E[0] + d * n[0]]
    for i in range(1, len(E) - 1):
        a0, a1 = np.arctan2(n[i - 1, 1], n[i - 1, 0]), np.arctan2(n[i, 1], n[i, 0])
        da = (a1 - a0 + np.pi) % (2 * np.pi) - np.pi
        for s in np.linspace(0, 1, max(2, int(abs(da) / 0.05) + 2)):
            Q.append(E[i] + d * np.array([np.cos(a0 + s * da), np.sin(a0 + s * da)]))
    Q.append(E[-1] + d * n[-1])
    Q = np.asarray(Q)
    inside = pattern._poly_inside(P, Q)
    keep = inside & (_seg_dist(Q, E) >= d - 2e-4)
    L, last = 0.0, None
    for i in range(len(Q)):
        if not inside[i]:
            last = None
        elif keep[i]:
            if last is not None:
                L += float(np.linalg.norm(Q[i] - Q[last]))
            last = i
    return L


def _len(B: dict, edges) -> float:
    from . import pattern
    return float(sum(pattern.length(_ds()._pts(B, e)) for e in edges))


def units(B: dict, decl: dict, step1: dict) -> list:
    """[{"falls", "pieces", "neck": [(collar edge, garment edge)], "to_stand": [(fall edge, stand edge)]}]."""
    ds = _ds()
    falls = ds.fall_pieces(B, decl, step1)
    lay = ds.layers(B)
    stiff = set(decl.get("stiff") or [])
    join = lambda r: r in B["pieces"] and r not in lay and (r in falls or r in stiff or ds._role(r, decl, step1) in ds.STAND_ROLES)
    pairs = []
    for A, Bs in ds._seam_pairs(B):
        for mine, other in ((A, Bs), (Bs, A)):
            for e in mine:
                for f in other:
                    pairs.append((e, f, ds.is_neck(ds._edge_name(B, e)) or ds.is_neck(ds._edge_name(B, f))))
    out, seen = [], set()
    for p in sorted(falls):
        if p in seen or p in lay:
            continue
        U, todo = {p}, [p]
        while todo:
            q = todo.pop()
            for e, f, neck in pairs:
                r = _piece(f)
                if _piece(e) == q and r not in U and not neck and join(r):
                    U.add(r)
                    todo.append(r)
        seen |= U
        neck = [(e, f) for e, f, nk in pairs if nk and _piece(e) in U and _piece(f) not in U]
        to_stand = [(e, f) for e, f, nk in pairs if not nk and _piece(e) in U & falls and _piece(f) in U - falls]
        out.append({"falls": sorted(U & falls), "pieces": sorted(U), "neck": neck, "to_stand": to_stand})
    return out


def covered(B: dict, u: dict) -> tuple[float, str]:
    """(N, what): the stretch the outer edge covers."""
    best = max(((_len(B, sorted({e for e, _ in u["neck"] if _piece(e) == p})), p) for p in u["falls"]), default=(0.0, ""))
    if best[0] > 0:
        return best[0], f"{best[1]}'s neck edges"
    fs = sorted({e for e, _ in u["to_stand"]})
    return (_len(B, fs), "its seam to the stand") if fs else (0.0, "")


def _outer(B: dict, u: dict, decl: dict, step1: dict):
    """(piece, outline indices of its outer edge) on a fall: the one with a roll fold first."""
    from . import pattern
    ds = _ds()
    rolled = {f.get("piece") for f in B.get("folds") or [] if f.get("kind") == "roll"}
    for p in sorted(u["falls"], key=lambda q: q not in rolled):
        arcs = (B.get("edge_arcs") or {}).get(p, {})
        k = next((k for k in ds.OUTER_NAMES if k in arcs), None)
        if k:
            return p, pattern.arc_indices(B["pieces"][p], arcs[k])
    return None, None


def _mid(L: np.ndarray) -> np.ndarray:
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(L, axis=0), axis=1))]
    return np.array([np.interp(s[-1] / 2, s, L[:, k]) for k in range(2)])


def depth(B: dict, u: dict, outer: tuple) -> dict:
    """{"stand", "fall", "d", "from"} at CB (m), or {"why"}."""
    from . import pattern
    ds = _ds()
    p, oix = outer
    for f in B.get("folds") or []:
        if f.get("kind") != "roll" or f.get("piece") not in u["falls"]:
            continue
        q = f["piece"]
        pc = B["pieces"][q]
        try:
            L = pattern.fold_line(B["pieces"], f)
        except (KeyError, ValueError, TypeError, IndexError):
            continue
        hs = ds._half_seam(B, q)
        if hs:  # (a half collar: its CB is the fold line's end on the seam to its other half)
            C = pc["P"][pattern.arc_indices(pc, hs[1])]
            r = min((L[0], L[-1]), key=lambda x: float(_seg_dist(x[None], C)[0]))
        else:
            r = _mid(L)
        arcs = (B.get("edge_arcs") or {}).get(q, {})
        k = next((k for k in ds.OUTER_NAMES if k in arcs), None)
        if q != p and not k:
            continue
        qix = oix if q == p else pattern.arc_indices(pc, arcs[k])
        O = pc["P"][qix]
        rest = np.ones(len(pc["P"]), bool)
        rest[qix] = False
        R = np.r_[pc["P"], pc["P"][:1]]
        segs = [R[i:i + 2] for i in range(len(pc["P"])) if rest[i] and rest[(i + 1) % len(pc["P"])]]
        st = min(float(_seg_dist(r[None], S)[0]) for S in segs) if segs else 0.0
        fa = float(_seg_dist(r[None], O)[0])
        return {"stand": st, "fall": fa, "d": fa - st, "from": f"{q}'s roll fold {f.get('name', '')!r} at CB"}
    if u["to_stand"]:
        s_edges = sorted({f for _, f in u["to_stand"]})
        sp = _piece(s_edges[0])
        nk = [e for e, _ in u["neck"] if _piece(e) == sp]
        if nk:
            st = float(_seg_dist(_mid(ds._pts(B, s_edges[0]))[None], np.concatenate([ds._pts(B, e) for e in nk]))[0])
            O = B["pieces"][p]["P"][oix]
            fe = [e for e, _ in u["to_stand"] if _piece(e) == p]
            if fe:
                fa = float(_seg_dist(_mid(O)[None], np.concatenate([ds._pts(B, e) for e in fe]))[0])
                return {"stand": st, "fall": fa, "d": fa - st, "from": f"{sp}'s height and {p}'s depth at their middles"}
    return {"why": "no roll fold on the fall and no stand under it: declare the collar's roll fold (folds: kind "
                   "\"roll\" on the fall piece, along its roll line) so its stand and fall can be read"}


def row(B: dict, decl: dict, step1: dict) -> dict:
    from . import pattern
    vals, why, info, detail = [], [], [], []
    for u in units(B, decl, step1):
        name = "+".join(u["pieces"])
        if not u["neck"]:
            info.append(f"{name}: sewn to no neck edge")
            continue
        p, oix = _outer(B, u, decl, step1)
        if p is None:
            info.append(f"{name}: no outer edge (name the fall's free edge outer / fall / edge)")
            continue
        D = depth(B, u, (p, oix))
        if "why" in D:
            info.append(f"{name}: {D['why']}")
            continue
        O = pattern.length(B["pieces"][p]["P"][oix])
        N, what = covered(B, u)
        G = sorted({f for _, f in u["neck"]})
        GL = _len(B, G)
        if D["d"] <= 0:
            why.append(f"{name}: its fall ({1000 * D['fall']:.0f} mm) is no deeper than its stand ({1000 * D['stand']:.0f} "
                       "mm) at CB: it can't cover the neck seam. change: deepen the fall (move the outer edge out)")
            vals.append(f"{name}: fall {1000 * D['fall']:.0f} <= stand {1000 * D['stand']:.0f} mm")
            continue
        fronts = [f for f in G if _ds()._role(_piece(f), decl, step1) in _ds().LAPEL_ROLES]
        line = sum(pattern.length(_ds()._pts(B, f)) if f in fronts else
                   offset_length(_ds()._pts(B, f), B["pieces"][_piece(f)]["P"], D["d"]) for f in G)
        k = line / GL if GL else 1.0
        T = k * N + 2 * np.pi * LIFT * min(1.0, N / GL if GL else 1.0)
        s = O / T
        vals.append(f"{name}: {p}'s outer edge {1000 * O:.0f} mm against the line it lands on {1000 * T:.0f} mm = {s:.3f} "
                    f"(depth {1000 * D['d']:.0f} mm = fall {1000 * D['fall']:.0f} - stand {1000 * D['stand']:.0f} at CB, "
                    f"{D['from']}; the garment's neck line {1000 * GL:.0f} mm is {1000 * line:.0f} mm at that depth, "
                    f"x{k:.3f} (spread on {len(G) - len(fronts)} of {len(G)} neck edges, the fronts' along their roll), over {what} {1000 * N:.0f} mm, + {1000 * 2 * np.pi * LIFT * min(1.0, N / GL):.0f} mm lift)")
        detail.append({"collar": name, "outer": O, "target": T, "ratio": s, "d": D["d"], "line": line, "neck": GL, "N": N})
        mm = abs(O - T) * 1000
        if s > 1 + TOL:
            why.append(f"{name}: {p}'s outer edge is {mm:.0f} mm ({100 * (s - 1):.0f} %) longer than the line it lands on: "
                       "the fall flares and stands off the garment. change: straighten the collar (less curve: a flatter "
                       f"neck edge, its outer edge in by ~{mm:.0f} mm), or deepen the stand")
        elif s < 1 - TOL:
            why.append(f"{name}: {p}'s outer edge is {mm:.0f} mm ({100 * (1 - s):.0f} %) shorter than the line it lands "
                       "on: the fall pulls and the collar strangles the neck. change: spread the collar (more curve: "
                       f"slash and spread the outer edge by ~{mm:.0f} mm), or shallow the fall")
    return {"id": "shape_fall_landing", "status": ("FAIL" if why else "PASS") if vals else "INFO",
            "value": "; ".join(vals) if vals else ("; ".join(info) or "no fall"), "why": "; ".join(why),
            "info": "; ".join(info) if vals else "", "detail": detail,
            "target": f"outer edge within {100 * TOL:.0f} % of the line at (fall - stand) below the neck seam, + lift",
            "change": "; ".join(w.split("change: ", 1)[-1] for w in why), "back_to": "4"}
