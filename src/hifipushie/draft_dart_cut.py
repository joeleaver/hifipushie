"""A DART INSIDE A PIECE (C415): a fish dart, or a dart ending in a pocket mouth, declared as drawn; the tool opens it.

Trial s4-23 (2026-11-11, the suit jacket): the forepart's fish dart (tip under the chest, widest at the waist, dying out
under the pocket mouth) is a closed path INSIDE the piece. A cloth mesh has no holes, and draft_own sewed only darts open
on the outline, so the agent cut a 1 mm slit from the dart's bottom to the hem by hand and declared slit + dart as the
two legs: a seam down the jacket front no tailor cuts, and a different hand-made workaround in every trial (s4-22 too).
A pattern maker draws the dart where it is and cuts it through where the cloth is cut anyway (a pocket mouth to the
nearest seam: the jacket's cut-through). So the declaration says just that, and the tool does the cutting:

  darts [{"piece", "inside": <the part's path of the dart: one closed path, two tips>, "release": [point, ..., outline
          point], "why"?}]
  inside: a path of the FreeSewing part (it may be hidden), drawn inside the piece, closed, its two tips the two points
     farthest apart (a fish dart's top and bottom; a dart ending in a pocket mouth: its tip and its bottom point in the
     mouth).
  release: where the dart is cut through to the outline: part points (inner points allowed: a pocket mouth's ends), the
     last a NAMED outline point where two declared edges meet (a side seam's point at pocket height, a hem point). It
     starts at the dart's tip nearest its first point. The cut is sewn shut with the dart, so it takes no cloth out and
     is no seam of the garment; on the cloth it is a line under the pocket flap at most.

The opening: the outline point is split in two (SPLIT apart along the outline), the release runs in on one side and out
on the other (SLIT apart), round the dart's two sides between them. The legs are `<piece>:<dart>.cut_a>...>.tip` and
`.cut_b>...>.tip` (from the outline to ONE tip, C361's form), sewn to each other: the dart row and the seam rows read
them as every other dart. A declared edge that ENDS at the outline point keeps its end on its own side; an edge running
PAST it is refused (end the edges there).
"""
from __future__ import annotations

import numpy as np

SLIT = 0.0008  # m between the two sides of the release cut (apart for Delaunay; under the darts row's 1 mm)
STEP = 0.003  # m: the release is sampled this fine
FORM = ('darts [{"piece", "inside": <path name of the part: the dart drawn closed inside the piece>, "release": [part '
        'point, ..., named outline point where two edges meet], "why"?}] (C415: a fish dart / a dart ending in a pocket '
        'mouth: the tool cuts it through along release and sews dart and cut shut)')


class Refused(ValueError):
    pass


def is_inside(dt: dict) -> bool:
    return isinstance(dt, dict) and "inside" in dt


def check(i: int, dt: dict, part: dict | None) -> list:
    """Declaration faults of one inside dart (validate)."""
    bad, w = [], f"darts[{i}] on {dt.get('piece')}"
    if "legs" in dt:
        bad.append(f"{w}: an inside dart has no legs (the tool makes them); legs are for a dart open on the outline")
    rel = dt.get("release")
    if not (isinstance(rel, list) and rel and all(isinstance(x, str) for x in rel)):
        bad.append(f"{w}: release = [part point, ..., named outline point]: where the dart is cut through to the "
                   f"outline (through a pocket mouth to the nearest seam, or straight to it). {FORM}")
    if part is not None:
        if dt.get("inside") not in (part.get("paths") or {}):
            bad.append(f"{w}: inside {dt.get('inside')!r} is not a path of the part (has "
                       f"{', '.join(k for k in part.get('paths') or {} if k not in ('seam', 'sa'))})")
        for p in rel if isinstance(rel, list) else []:
            if isinstance(p, str) and p not in (part.get("points") or {}):
                bad.append(f"{w}: release point {p!r} is not a point of the part")
    return bad


def _ring(part: dict, path: str) -> np.ndarray:
    from . import pattern
    D = np.asarray(pattern.from_freesewing({"paths": {"seam": part["paths"][path]}, "points": {}}, "_")["P"])
    if len(D) > 2 and np.linalg.norm(D[0] - D[-1]) < 1e-6:
        D = D[:-1]
    return D


def _xy(part: dict, name: str) -> np.ndarray:
    from . import pattern
    return np.asarray(pattern._fs_xy(part["points"][name]), float)


def _dense(Q: np.ndarray) -> np.ndarray:
    out = [Q[0]]
    for a, b in zip(Q[:-1], Q[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / STEP)))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return np.asarray(out)


def _simple(P: np.ndarray) -> bool:
    """No two non-adjacent segments of the closed polygon cross."""
    A, B = P, np.roll(P, -1, axis=0)
    n = len(P)
    d1 = B - A
    cr = lambda u, v: u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]
    a, b = A[:, None], A[None, :]
    da, db = d1[:, None], d1[None, :]
    den = cr(da, db)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = cr(b - a, db) / den
        u = cr(b - a, da) / den
    hit = (np.abs(den) > 1e-15) & (t > 1e-9) & (t < 1 - 1e-9) & (u > 1e-9) & (u < 1 - 1e-9)
    i, j = np.indices((n, n))
    near = (np.abs(i - j) <= 1) | (np.abs(i - j) == n - 1)
    return not np.any(hit & ~near)


def _inside(P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    from . import cloth
    return cloth._inside(P, Q)


def _hit(R: np.ndarray, D: np.ndarray):
    """The first crossing of polyline R (from the outline inward) with the closed ring D: (k on R, j on D, point)."""
    m = len(D)
    cr = lambda u, v: u[0] * v[1] - u[1] * v[0]
    for k in range(len(R) - 1):
        a, da = R[k], R[k + 1] - R[k]
        best = None
        for j in range(m):
            b, db = D[j], D[(j + 1) % m] - D[j]
            den = cr(da, db)
            if abs(den) < 1e-15:
                continue
            t, u = cr(b - a, db) / den, cr(b - a, da) / den
            if 0 <= t <= 1 and 0 <= u < 1 and (best is None or t < best[0]):
                best = (t, j, a + t * da)
        if best:
            return k, best[1], best[2]
    return None


def _len(Q):
    return float(np.sum(np.linalg.norm(np.diff(np.asarray(Q), axis=0), axis=1))) if len(Q) > 1 else 0.0


def open_inside(pc: dict, part: dict, dt: dict, edges: dict) -> dict:
    """Cut the inside dart `dt` open in piece `pc` (in place), rewrite `edges` (this piece's declared edge strings) whose
    end is the release's outline point, and return {"pairs": [[edge, edge], ...] (each sewn to the other), "release_mm"}.

    The release runs in from the outline point S along its points and stops where it first meets the dart (X): at a
    tip, or on a side (a pocket mouth crossing it). Sewn: the cut's two sides to each other; the dart's sides to each
    other tip to tip (a side the cut meets in two parts, the other side split at the matching length: X')."""
    from . import pattern
    nm, path, rel = pc["name"], dt["inside"], list(dt["release"])
    tag = path
    P = np.asarray(pc["P"], float)
    D = _ring(part, path)
    if len(D) < 3:
        raise Refused(f"{nm}: dart {path!r} has {len(D)} points: draw it closed (a fish dart's two sides)")
    if not _inside(P, D).all():
        raise Refused(f"{nm}: dart {path!r} is not inside the piece: a dart open on the outline is declared with legs "
                      "[edge, edge], each 'outline point>tip' (C361)")
    S = rel[-1]
    if S not in pc["names"]:
        named = sorted(pc["names"], key=lambda k: np.linalg.norm(P[pc["names"][k]] - D.mean(0)))
        raise Refused(f"{nm}: dart {path!r}: release ends at {S!r}, not a named outline point; the nearest are "
                      f"{', '.join(named[:6])} (the cut runs to a point where two declared edges meet)")
    s = int(pc["names"][S])
    inner = [_xy(part, q) for q in rel[:-1]]
    if inner and not _inside(P, np.asarray(inner)).all():
        raise Refused(f"{nm}: dart {path!r}: a release point lies off the piece")
    far = np.linalg.norm(D[:, None] - D[None], axis=2)
    tips = list(np.unravel_index(int(np.argmax(far)), far.shape))
    R0 = np.array([P[s]] + inner[::-1])
    h = _hit(R0, D) if len(R0) > 1 else None
    if h is None:  # (the cut stops short of the dart: on to its nearest point)
        j = int(np.argmin(np.linalg.norm(D - R0[-1], axis=1)))
        R0, X = np.r_[R0, D[j][None]], j
    else:
        k, j, q = h
        R0 = np.r_[R0[:k + 1], q[None]]
        D = np.r_[D[:j + 1], q[None], D[j + 1:]]
        tips = [t + 1 if t > j else t for t in tips]
        X = j + 1
    for t in tips:  # (meeting the dart within 3 mm of a tip is meeting the tip)
        if np.linalg.norm(D[t] - D[X]) < 0.003:
            X = t
    keep = [i for i in range(len(D)) if i == X or i in tips or np.linalg.norm(D[i] - D[X]) > SLIT]
    tips, X, D = [keep.index(t) for t in tips], keep.index(X), D[keep]  # (no ring point inside the cut's mouth)
    m = len(D)
    R = _dense(R0)
    R[-1] = D[X]
    # edges ending at S: which side of it they leave on (in the uncut outline)
    n0 = len(P)
    side = {}
    for ed, how in edges.items():
        if not isinstance(how, str) or S not in how.split(">"):
            continue
        ix = pattern.arc_indices(pc, how)
        if s in ix[1:-1]:
            raise Refused(f"{nm}: edge {ed!r} ({how}) runs past {S!r}, where dart {path!r} is cut through: end the "
                          f"edges at {S!r} (two edges, sewn as one chain [a, b] in their seam; the joint needs no notch)")
        nb = ix[1] if ix[0] == s else ix[-2]
        side[ed] = "b" if nb == (s + 1) % n0 else "a"
    t_out = P[(s + 1) % n0] - P[s - 1]
    t_out /= np.linalg.norm(t_out)

    def off(Q, sgn):
        T = np.gradient(Q, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
        return Q + sgn * 0.5 * SLIT * np.c_[-T[:, 1], T[:, 0]]
    best = None
    for rev in (False, True):
        order = [(X + (-k if rev else k)) % m for k in range(m + 1)]  # X round the dart back to X
        ring = [D[i] for i in order]
        for sg in (1.0, -1.0):
            Ra, Rb = off(R, sg), off(R, -sg)
            Ra[0], Rb[0] = P[s] - 0.5 * SLIT * t_out, P[s] + 0.5 * SLIT * t_out
            for Rx, nb in ((Ra, ring[1]), (Rb, ring[-2])):  # (the cut's inner ends on the dart, either side of X)
                u = nb - D[X]
                Rx[-1] = D[X] + 0.5 * SLIT * u / max(np.linalg.norm(u), 1e-12)
            loop = list(Ra) + ring[1:-1] + list(Rb[::-1])
            Q = np.r_[P[:s], np.asarray(loop), P[s + 1:]]
            if _simple(Q):
                best = (Q, loop, Ra, order)
                break
        if best:
            break
    if best is None:
        raise Refused(f"{nm}: dart {path!r} can't be cut through to {S!r} without crossing itself or the outline: "
                      "choose release points that run clear of the dart's sides")
    Q, loop, Ra, order = best
    r, k = len(Ra), len(loop) - 1
    at = lambda pos: s + r - 1 + pos  # Q index of ring position pos (0 = X on side a, m = X on side b)
    names = {key: (i if i < s else (i + k if i > s else s)) for key, i in pc["names"].items()}
    names.update({f"{tag}.cut_a": s, f"{tag}.cut_b": s + k, f"{tag}.x_a": at(0), f"{tag}.x_b": at(m)})
    pos = sorted(order.index(t) for t in tips)  # tip positions along the ring from X
    p1, p2 = pos
    pairs = [[f"{tag}.cut_a>{tag}.x_a", f"{tag}.cut_b>{tag}.x_b"]]  # the cut, sewn shut
    if p1 == 0:  # X is a tip: the dart's two sides, from the cut to the far tip
        names[f"{tag}.tip"] = at(p2)
        pairs.append([f"{tag}.x_a>{tag}.tip", f"{tag}.x_b>{tag}.tip"])
    else:  # X on a side: T1..X and X..T2 against the other side split at the matching length (X')
        ringQ = [Q[at(i)] for i in range(m + 1)]
        l0, l2, s1 = _len(ringQ[:p1 + 1]), _len(ringQ[p2:]), ringQ[p1:p2 + 1]
        want = l0 / (l0 + l2) * _len(s1)
        cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.asarray(s1), axis=0), axis=1))]
        ip = int(np.clip(np.searchsorted(cum, want), 1, len(s1) - 1))
        f = (want - cum[ip - 1]) / max(cum[ip] - cum[ip - 1], 1e-12)
        xp = s1[ip - 1] + f * (s1[ip] - s1[ip - 1])
        ins = at(p1) + ip  # insert X' before Q index ins
        Q = np.r_[Q[:ins], xp[None], Q[ins:]]
        names = {key: (i + 1 if i >= ins else i) for key, i in names.items()}
        names.update({f"{tag}.t1": at(p1), f"{tag}.t2": at(p2) + 1, f"{tag}.xp": ins})
        pairs += [[f"{tag}.x_a>{tag}.t1", f"{tag}.xp>{tag}.t1"], [f"{tag}.x_b>{tag}.t2", f"{tag}.xp>{tag}.t2"]]
    lo, hi = s, s + k + (0 if p1 == 0 else 1)  # (the part's own points on the cut outline keep their names: dartTop)
    for key, v in (part.get("points") or {}).items():
        if v and key not in names and not key.startswith("__"):
            dd = np.linalg.norm(Q[lo:hi + 1] - _xy(part, key), axis=1)
            if dd.min() < 5e-5:
                names[key] = lo + int(np.argmin(dd))
    pc["P"], pc["names"] = Q, names
    for ed, sd in side.items():
        if sd == "b":
            edges[ed] = ">".join(f"{tag}.cut_b" if q == S else q for q in edges[ed].split(">"))
    return {"pairs": pairs, "release_mm": round(1000 * _len(R), 1)}


SLIT_MM = 3.0  # an open dart narrower than this where it meets the outline is a hand-cut slit


def row(B: dict) -> dict:
    """The flat gate's `darts` row: each dart's two legs run from the outline to ONE tip (C361), and an open dart is a
    dart, not a slit cut by hand to open one drawn inside the piece (C415)."""
    from . import pattern

    def arc(e):
        p, a = e.split(":", 1)
        pc = B["pieces"][p]
        return pc["P"][pattern.arc_indices(pc, a)]
    far = []
    for dt in B["darts"]:
        A, C = (arc(e) for e in dt["legs"])
        gap = float(np.linalg.norm(A[-1] - C[-1])) * 1000
        if gap > 1.0:
            far.append(f"{dt['piece']}: its legs end {gap:.1f} mm apart")
        mouth = float(np.linalg.norm(A[0] - C[0])) * 1000
        if not dt.get("inside") and mouth < SLIT_MM:  # (t s4-22 / s4-23: a 1 mm slit cut to the hem by hand)
            far.append(f"{dt['piece']}: its legs open {mouth:.1f} mm apart on the outline: a slit cut by hand to open a "
                       "dart drawn inside the piece. Draw the dart as it is and declare it " + FORM)
    return {"id": "darts", "status": "FAIL" if far else "PASS", "value": f"{len(B['darts'])} darts",
            "target": "each dart's two legs run from the outline to ONE tip (declare both toward the tip); a dart inside "
                      "the piece declared inside, never slit open by hand",
            "why": "; ".join(far), "fix": "declare each leg 'outline point>tip'", "back_to": "4"}
