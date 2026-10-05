"""Shaping and joining operations for pattern_draft: what a tailored garment needs beyond style lines and darts.
Registered into pattern_draft.OPS. Same contract as the others: named points, named edges kept, seams matched or
their ease declared.

  contour       shape an edge: moved into (or out of) its piece by an amount per level (a shaped centre-back seam, a
                side seam taken in at the waist and let out over the seat, a hem's spring).
  join          two pieces sewn together become one, the seam gone (a side panel with no side seam, a yoke cut on,
                a grown-on band); what the seam's curve shaped is reported as lost.
  round_corner  a corner of the outline rounded (a cut-away front hem, a patch pocket, a cuff, a collar point).
  fisheye       a double-pointed dart inside a piece that runs past the waist (run on to the hem as a closed cut:
                a cloth mesh can't hold a cut that doesn't reach its edge).
"""
from __future__ import annotations

import copy
import json
import math

import numpy as np

from . import pattern
from . import pattern_draft as pd
from .pattern_draft import DraftError, _insert, _remap, _rot, edge_length


def _unit(v):
    v = np.asarray(v, float)
    return v / max(np.linalg.norm(v), 1e-12)


def level(D: dict, pc: dict, lv) -> float:
    """A level as y (m): a number, or "top" / "hem" of the piece, "waist", "hips", "chest" (the piece's own line when
    it has one, else the block's)."""
    if isinstance(lv, (int, float)):
        return float(lv)
    if lv in ("top", "neck"):
        return float(pc["P"][:, 1].max())
    if lv in ("hem", "bottom"):
        return float(pc["P"][:, 1].min())
    if lv in (pc.get("lines") or {}):
        return float(np.mean(np.asarray(pc["lines"][lv], float)[:, 1]))
    m = D["meta"]
    if lv == "waist" and "waist_y" in m:
        return float(m["waist_y"])
    if lv in ("hips", "seat") and "hips_y" in m:
        return float(m["hips_y"])
    if lv == "chest" and "chest_y" in m:
        return float(m["chest_y"])
    raise DraftError(f"no level {lv!r} (a number in m, top, hem, waist, hips, chest, or a line of the piece)")


def op_contour(D: dict, edge, at: list, **o) -> None:
    """Shape an edge: moved INTO its piece by an amount at each level, eased between ("at": [[level, m], ...]; level =
    a y in m, "top", "chest", "waist", "hips", "hem"; negative = let out). A shaped centre-back seam is
    {"edge": "centre_back", "at": [["top", 0], ["chest", 0.005], ["waist", 0.02], ["hem", 0.012]]}; a side seam
    shaped on front and back alike keeps the two equal (edge may be a list of edges). Each point moves level, so
    the hem or neckline the edge meets gets that much shorter."""
    chain = []
    for e_ in ([edge] if isinstance(edge, str) else list(edge)):
        # (a style line's name = BOTH its edges: a panel seam shaped on one side only no longer matches)
        chain += list(D["lines"][e_]) if e_ in D["lines"] else list(D["edges"][e_]) if e_ in D["edges"] else [e_]
    did = []
    for spec in chain:
        pn, arc = spec.split(":", 1)
        pc = D["pieces"][pn]
        pd.densify_edge(pc, arc)
        ix = pattern.arc_indices(pc, arc)
        L = pc["P"][ix]
        # ("top" / "hem" are the EDGE's own ends: a centre back starts below the neck point)
        own = {"top": float(L[:, 1].max()), "neck": float(L[:, 1].max()), "hem": float(L[:, 1].min()),
               "bottom": float(L[:, 1].min())}
        lv = sorted((own[k] if k in own else level(D, pc, k), float(v)) for k, v in at)
        ys, am = np.array([q[0] for q in lv]), np.array([q[1] for q in lv])
        if len(ys) > 1:  # eased from each level to the next, held beyond the outer ones
            j = np.clip(np.searchsorted(ys, L[:, 1]) - 1, 0, len(ys) - 2)
            t = np.clip((L[:, 1] - ys[j]) / np.maximum(ys[j + 1] - ys[j], 1e-9), 0, 1)
            a = am[j] + (am[j + 1] - am[j]) * t * t * (3 - 2 * t)
        else:
            a = np.full(len(L), am[0])
        sgn = 1.0 if pc["P"][:, 0].mean() > L[:, 0].mean() else -1.0
        before = pattern.length(L)
        pc["P"][ix, 0] = L[:, 0] + sgn * a
        did.append(f"{spec} {before * 1000:.0f} -> {pattern.length(pc['P'][ix]) * 1000:.0f} mm")
    for e_ in ([edge] if isinstance(edge, str) else list(edge)):
        if e_ in D["lines"]:
            pd.press_note(D, e_)
    D["log"].append("contour " + (edge if isinstance(edge, str) else " + ".join(edge)) + ": " +
                    ", ".join(f"{k} {float(v) * 1000:+.0f} mm" for k, v in at) + " into the piece; " + "; ".join(did))


def op_join(D: dict, a: str, b: str, name: str | None = None, **o) -> None:
    """Join piece `b` onto piece `a` along the seam between them: one piece, the seam gone. `b` is laid against `a`
    with the seam's ends together (turned over when the two were mirror pieces, as a front and a back are at the side
    seam). What the seam's curve shaped is LOST (the two edges only meet at their ends): the log says how much; take
    it in a seam nearby instead. The piece keeps `a`'s name (or `name`) and placement; `b`'s point names that clash
    with `a`'s become "<name>@<b>"."""
    pa, pb_ = D["pieces"][a], D["pieces"][b]
    seam = None
    for s in D["seams"]:
        if all(isinstance(x, str) for x in s) and {x.split(":")[0] for x in s} == {a, b} and \
                (not o.get("along") or any(o["along"] in x.split(":", 1)[1].split(">") for x in s)):
            seam = s  # ("along": a point name on the seam meant, when the two share more than one)
            break
    if seam is None:
        raise DraftError(f"join: no single seam between {a} and {b}")
    ea, eb = (seam[0], seam[1]) if seam[0].startswith(a + ":") else (seam[1], seam[0])
    ia = pattern.arc_indices(pa, ea.split(":", 1)[1])
    ib = pattern.arc_indices(pb_, eb.split(":", 1)[1])
    A0, A1 = pa["P"][ia[0]], pa["P"][ia[-1]]

    def lay(P, flip):
        m = np.array([-1.0, 1.0]) if flip else np.array([1.0, 1.0])
        Q = np.asarray(P, float).reshape(-1, 2) * m
        B0, B1 = pb_["P"][ib[0]] * m, pb_["P"][ib[-1]] * m
        ang = math.atan2(*(A1 - A0)[::-1]) - math.atan2(*(B1 - B0)[::-1])
        return _rot(Q, B0, ang) - B0 + A0
    # which way up: b's cloth must lie on the other side of the seam from a's
    nrm = _unit(np.array([-(A1 - A0)[1], (A1 - A0)[0]]))
    side_a = 1.0 if float((pa["P"].mean(0) - A0) @ nrm) > 0 else -1.0
    flip = float((lay(pb_["P"], False).mean(0) - A0) @ nrm) * side_a > 0
    Pb = lay(pb_["P"], flip)
    # what the seam's curves shaped: how far the two edges stand apart (+) or overlap (-) laid end to end
    da = side_a * ((pa["P"][ia] - A0) @ nrm)  # + = a's edge bows into a (a hollow)
    db = -side_a * ((Pb[ib] - A0) @ nrm)
    lost = float(np.max(da) + np.max(db)) if (np.max(da) + np.max(db)) > -(np.min(da) + np.min(db)) else float(np.min(da) + np.min(db))
    na, nb = len(pa["P"]), len(pb_["P"])
    step_a = 1 if (len(ia) < 2 or (ia[0] + 1) % na == ia[1]) else -1
    ring_a, k = [], ia[-1]  # a's ring from the seam's far end round (away from the seam) to its near end
    while True:
        ring_a.append(k)
        if k == ia[0]:
            break
        k = (k + step_a) % na
    step_b = -1 if (len(ib) < 2 or (ib[0] + 1) % nb == ib[1]) else 1  # b's ring away from the seam, from its start
    ring_b, k = [], (ib[0] + step_b) % nb
    while k != ib[-1]:
        ring_b.append(k)
        k = (k + step_b) % nb
    P = np.r_[pa["P"][ring_a], Pb[ring_b]] if ring_b else pa["P"][ring_a].copy()
    pos_a = {w: j for j, w in enumerate(ring_a)}
    pos_b = {w: len(ring_a) + j for j, w in enumerate(ring_b)}
    pos_b[ib[0]], pos_b[ib[-1]] = pos_a[ia[0]], pos_a[ia[-1]]
    names = {k_: pos_a[v] for k_, v in pa["names"].items() if v in pos_a}
    ren = {}
    for k_, v in pb_["names"].items():
        if v not in pos_b:
            continue
        ren[k_] = k_ if k_ not in names else f"{k_}@{b}"
        names.setdefault(ren[k_], pos_b[v])
    other = lambda d, k_: k_ if k_ not in (d or {}) else f"{k_}@{b}"
    new = dict(pa, P=P, names=names)
    new["marks"] = dict(pa.get("marks") or {}, **{other(pa.get("marks"), k_): lay(v, flip)[0]
                                                  for k_, v in (pb_.get("marks") or {}).items()})
    new["lines"] = dict(pa.get("lines") or {}, **{other(pa.get("lines"), k_): lay(v, flip)
                                                  for k_, v in (pb_.get("lines") or {}).items()})
    new["darts"] = dict(pa.get("darts") or {}, **{other(pa.get("darts"), k_): tuple(ren.get(p, p) for p in v)
                                                  for k_, v in (pb_.get("darts") or {}).items()
                                                  if all(p in ren for p in v)})
    D["seams"] = [s for s in D["seams"] if s is not seam]
    D["notes"].pop(json.dumps(seam), None)
    old_a, old_b = copy.deepcopy(pa), copy.deepcopy(pb_)
    nm = name or a
    new["name"] = nm
    order = [nm if k_ == a else k_ for k_ in D["pieces"] if k_ != b]
    pcs = {k_: v for k_, v in D["pieces"].items() if k_ not in (a, b)}
    pcs[nm] = new
    D["pieces"] = {k_: pcs[k_] for k_ in order}
    _remap(D, a, old_a, {w: [(nm, j)] for w, j in pos_a.items()}, {nm: new})
    _remap(D, b, old_b, {w: [(nm, j)] for w, j in pos_b.items()}, {nm: new})
    def moved(spec):  # a style line's own edge specs (take_in reads them) on the joined piece
        p_, arc = spec.split(":", 1)
        if p_ == a:
            return f"{nm}:{arc}"
        if p_ == b:
            return f"{nm}:" + ">".join(ren.get(x, x) for x in arc.split(">"))
        return spec
    D["lines"] = {k_: tuple(moved(x) for x in v) for k_, v in D["lines"].items()}
    if a in D["centre"] and nm != a:
        D["centre"][nm] = D["centre"].pop(a)
    D["centre"].pop(b, None)
    D["interfaced"] = [nm if e_ == a else e_ for e_ in D["interfaced"] if e_ != b]
    for f in D["folds"]:
        if f.get("piece") == a:
            f["piece"] = nm
    D["log"].append(f"join {b} onto {a}{' (turned over)' if flip else ''} along {pattern.length(pa['P'][ia]) * 1000:.0f} mm: "
                    f"one piece \"{nm}\", the seam gone; " +
                    (f"the seam's shaping is lost ({abs(lost) * 1000:.0f} mm {'of cloth added' if lost > 0 else 'overlapped'} "
                     "at its widest: take it in a seam nearby)" if abs(lost) > 0.002 else "the two edges were one line"))
    D["meta"].setdefault("joined", {})[nm] = {"lost": lost}


def op_round_corner(D: dict, piece: str, corner: str, radius: float = 0.06, **o) -> None:
    """A corner of the outline rounded: the outline leaves each edge `radius` from the corner (or "along": [m on the
    edge before it, m on the edge after]) on a curve. The corner's name stays on the curve's middle, so edges named
    to the corner still run. Do it BEFORE facings and bands are traced from those edges."""
    pc = D["pieces"][piece]
    if corner not in pc["names"]:
        raise DraftError(f"{piece}: no point {corner!r}")
    ra, rb = o.get("along") or (radius, radius)
    for sgn, r, tag in ((-1, float(ra), "_rc0"), (1, float(rb), "_rc1")):
        n = len(pc["P"])
        i = pc["names"][corner]
        acc, k = 0.0, i
        while True:
            j = (k + sgn) % n
            seg = float(np.linalg.norm(pc["P"][j] - pc["P"][k]))
            if acc + seg >= r - 1e-9:
                q = pc["P"][k] + (pc["P"][j] - pc["P"][k]) * (r - acc) / max(seg, 1e-12)
                if np.linalg.norm(q - pc["P"][j]) < 1e-6:
                    pc["names"][tag] = j
                else:
                    _insert(pc, k if sgn > 0 else j, q, tag)
                break
            acc += seg
            k = j
            if k == i:
                raise DraftError(f"round_corner: {r * 1000:.0f} mm is longer than the outline")
    n = len(pc["P"])
    i0, i1, ic = pc["names"]["_rc0"], pc["names"]["_rc1"], pc["names"][corner]
    A, C, B = pc["P"][i0].copy(), pc["P"][ic].copy(), pc["P"][i1].copy()
    drop, k = [], (i0 + 1) % n
    while k != i1:
        drop.append(k)
        k = (k + 1) % n
    t = np.linspace(0, 1, 13)[1:-1, None]
    arc = (1 - t) ** 2 * A + 2 * (1 - t) * t * C + t ** 2 * B
    keep = [k for k in range(n) if k not in drop]
    at = keep.index(i0)
    P = np.r_[pc["P"][keep[:at + 1]], arc, pc["P"][keep[at + 1:]]]
    pos = {w: (j if j <= at else j + len(arc)) for j, w in enumerate(keep)}
    names = {}
    for k_, v in pc["names"].items():
        if k_ in ("_rc0", "_rc1"):
            continue
        if v in pos:
            names[k_] = pos[v]
        elif v == ic:
            names[k_] = at + 1 + len(arc) // 2
        else:  # a point on the part cut off: to the nearer end of the curve
            names[k_] = pos[i0] if np.linalg.norm(pc["P"][v] - A) <= np.linalg.norm(pc["P"][v] - B) else pos[i1]
    names[f"{corner}.r0"], names[f"{corner}.r1"] = pos[i0], pos[i1]
    pc["P"], pc["names"] = P, names
    D["edges"][f"{corner}_round"] = [f"{piece}:{corner}.r0>{corner}>{corner}.r1"]
    D["log"].append(f"round corner {corner} of {piece}: {float(ra) * 1000:.0f} / {float(rb) * 1000:.0f} mm along its two "
                    f"edges, the curve {pattern.length(np.r_[[A], arc, [B]]) * 1000:.0f} mm")


def op_fisheye(D: dict, piece: str, x: float | None = None, width: float | None = None, up: float = 0.14,
               down: float = 0.11, at="waist", name: str = "waistDart", gap: float = 0.003, **o) -> None:
    """A fish-eye (double-pointed) dart: `width` taken out at the level `at` (the waist) at x, tapering to nothing
    `up` above and `down` below. Below its lower point the dart runs on to the hem as a closed cut `gap` wide (sewn
    shut like the dart: its seam pressed on to the hem). Defaults: the block's own waist dart (bodice option
    "darts") under the bust point / the middle of the back."""
    pc = D["pieces"][piece]
    wy = level(D, pc, at)
    if width is None:
        width = float(D["meta"].get("waist_dart", 0.0)) or 0.02
    if x is None:
        bust = D["meta"].get("bust")
        x = float(bust[0]) if (pc.get("role") == "front" and bust) else 0.5 * float(D["meta"].get("waist_quarter", 0.2))
    hits = [h for h in pd._line_hits(pc, np.array([x, wy]), np.array([0.0, -1.0])) if h[0] > 1e-6]
    if not hits:
        raise DraftError(f"fisheye: nothing of {piece} below x {x}, y {wy}")
    _, i_h, q_h = hits[0]
    ih = i_h if q_h is None else _insert(pc, i_h, q_h)
    work = copy.deepcopy(pc)
    n = len(work["P"])
    H = work["P"][ih].copy()
    ed = _unit(work["P"][(ih + 1) % n] - work["P"][(ih - 1) % n])  # the outline's direction through H
    s1 = -1.0 if ed[0] > 0 else 1.0  # the lip met first lies on the side the outline comes from
    slope = ed[1] / ed[0] if abs(ed[0]) > 1e-9 else 0.0
    top, lowp = wy + up, max(wy - down, H[1] + 0.01)

    def half(y):
        c = np.clip((top - y) / up, 0, 1) if y >= wy else np.clip((y - lowp) / max(wy - lowp, 1e-9), 0, 1)
        return max(0.5 * width * c * c * (3 - 2 * c), 0.5 * gap)
    ys = np.r_[np.linspace(H[1], lowp, max(2, int((lowp - H[1]) / 0.03) + 1))[:-1], np.linspace(lowp, wy, 6)[:-1],
               np.linspace(wy, top - 0.006, 8)]
    lip1 = [np.array([x + s1 * half(y), y]) for y in ys]
    lip2 = [np.array([x - s1 * half(y), y]) for y in ys[::-1]]
    for q in (lip1[0], lip2[-1]):  # the lips' feet on the hem's own line
        q[1] = H[1] + slope * (q[0] - H[0])
    iw = int(np.argmin(np.abs(ys - wy)))
    ins = lip1 + [np.array([x, top])] + lip2
    P = np.r_[work["P"][:ih], ins, work["P"][ih + 1:]]
    sh = len(ins) - 1
    names = {k_: (v if v <= ih else v + sh) for k_, v in work["names"].items()}  # (a name on H: the first lip's foot)
    a_n, t_n, b_n = f"{name}A", f"{name}Tip", f"{name}B"
    names[a_n], names[f"{name}Am"], names[t_n] = ih, ih + iw, ih + len(lip1)
    names[f"{name}Bm"], names[b_n] = ih + len(lip1) + (len(lip2) - iw), ih + len(ins) - 1
    new = dict(work, P=P, names=names)
    imap = {w: [(piece, w if w < ih else w + sh)] for w in range(n) if w != ih}
    imap[ih] = [(piece, ih), (piece, ih + len(ins) - 1)]
    D["pieces"][piece] = new
    _remap(D, piece, work, imap, {piece: new})
    s = [f"{piece}:{a_n}>{name}Am>{t_n}", f"{piece}:{b_n}>{name}Bm>{t_n}"]
    D["seams"].append(s)
    new.setdefault("fisheyes", {})[name] = (a_n, t_n, b_n)
    D["log"].append(f"fish-eye dart {name} on {piece}: {width * 1000:.0f} mm at {at} (x {x * 1000:.0f} mm), {up * 1000:.0f} mm "
                    f"up and {(wy - lowp) * 1000:.0f} mm down, run on to the hem as a closed cut; legs "
                    f"{edge_length(D, s[0]) * 1000:.0f} / {edge_length(D, s[1]) * 1000:.0f} mm")


pd.OPS.update({"contour": op_contour, "join": op_join, "round_corner": op_round_corner, "fisheye": op_fisheye})
