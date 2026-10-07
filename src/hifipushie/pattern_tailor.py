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


def op_pocket(D: dict, piece: str, type: str = "patch", at=None, width: float = 0.14, height: float = 0.15,
              name: str = "pocket", tack: float = 0.035, **o) -> None:
    """A pocket laid ON a piece (traced in its coordinates, placed on its outside face, tacked down by point stitches
    every `tack` m along the edges that are sewn):
      "patch"     a rectangle with its bottom corners cut, top edge open: at = [x, y] of the top edge's middle (m in
                  the piece's coordinates; default: below the waist, halfway to the side);
      "kangaroo"  across the centre front of a piece cut on the fold (a half is drawn, x = 0 on the fold): the top
                  and bottom edges sewn, the slanted sides open for the hands.
    Welt and in-seam pockets need a cut inside the piece / a split seam with bags behind: not drafted yet (the detail
    maps are where a welt shows)."""
    from . import pattern_blocks as pb
    if type == "in_seam":
        return _in_seam_pocket(D, piece, name=name, width=width, height=height, **o)
    pc = D["pieces"][piece]
    wy = D["meta"].get("waist_y", -0.45)
    P = pc["P"]
    if type == "kangaroo":
        if np.sum(np.abs(P[:, 0]) < 1e-6) < 2:
            raise DraftError("kangaroo pocket: the piece must be cut on the fold at centre front (block cf: fold)")
        w2, h = width / 2 if width > 0.2 else 0.16, height
        # (default: its top just above the waist, or as high as keeps its bottom 3 cm above the hem)
        top = float(at[1]) if at else max(wy + 0.02, float(P[:, 1].min()) + 0.03 + h)
        pts = [("topC", [0.0, top]), ("topS", [0.55 * w2, top]), ("openLow", [w2, top - 0.55 * h]),
               ("botS", [w2, top - h]), ("botC", [0.0, top - h])]
        sewn = [("topC", "topS"), ("openLow", "botS"), ("botS", "botC")]
        sym = "fold"
    elif type == "patch":
        if at is None:
            at = [0.5 * (0.0 + float(P[:, 0].max())), wy - 0.05]
        x0, top = float(at[0]) - width / 2, float(at[1])
        c = min(0.02, 0.2 * width)
        pts = [("topA", [x0, top]), ("topB", [x0 + width, top]), ("sideB", [x0 + width, top - height + c]),
               ("botB", [x0 + width - c, top - height]), ("botA", [x0 + c, top - height]), ("sideA", [x0, top - height + c])]
        sewn = [("topB", "sideB"), ("sideB", "botB"), ("botB", "botA"), ("botA", "sideA"), ("sideA", "topA")]
        sym = pc.get("sym", "pair")
    elif type in ("welt", "flap"):
        # what shows of a welt / flap pocket: a welt strip sewn down all round (the slot's lip), or a flap hanging
        # from its top edge. The slot itself is not cut and no bag hangs inside (a cloth mesh has no holes; the
        # bag never shows): the piece under it is whole
        if at is None:
            at = [0.5 * float(P[:, 0].max()), wy - 0.06]
        if type == "welt":
            height = min(height, 0.012) if height >= 0.05 else height
        else:
            height = 0.055 if height >= 0.1 else height
        x0, top = float(at[0]) - width / 2, float(at[1])
        c = 0.0 if type == "welt" else min(0.012, 0.2 * width)
        pts = [("topA", [x0, top]), ("topB", [x0 + width, top]), ("sideB", [x0 + width, top - height + c]),
               ("botB", [x0 + width - c, top - height]), ("botA", [x0 + c, top - height]), ("sideA", [x0, top - height + c])]
        if type == "welt":
            pts = [pts[0], pts[1], pts[3], pts[4]]
            sewn = [("topA", "topB"), ("topB", "botB"), ("botB", "botA"), ("botA", "topA")]
        else:
            sewn = [("topA", "topB")]
        sym = pc.get("sym", "pair")
    else:
        raise DraftError(f"pocket type {type!r}: patch, kangaroo, welt, flap or in_seam")
    from .cloth import _inside
    Q = np.array([q for _, q in pts], float)
    if not _inside(P, Q * 0.98 + 0.02 * Q.mean(0)).all():
        raise DraftError(f"pocket {name}: it doesn't lie inside {piece} (at {at}, {width * 1000:.0f} x {height * 1000:.0f} mm)")
    # the tack points: vertices of the pocket's sewn edges, each stitched to a mark of the piece under it
    ring, k = [], 0
    by = dict(pts)
    order = [nm_ for nm_, _ in pts]
    tacks = []
    for i, nm_ in enumerate(order):
        a_, b_ = np.asarray(by[nm_], float), np.asarray(by[order[(i + 1) % len(order)]], float)
        ring.append((nm_, a_))
        if (nm_, order[(i + 1) % len(order)]) in sewn:
            n_ = max(1, int(round(np.linalg.norm(b_ - a_) / tack)))
            for j in range(n_ + 1):
                q = a_ + (b_ - a_) * j / n_
                if abs(q[0]) < 1e-6 and sym == "fold" and j not in (0, n_):
                    continue
                tn = f"t{k}"
                k += 1
                if j == 0:
                    ring[-1] = (nm_, a_)
                    tacks.append((nm_, q))
                elif j == n_:
                    tacks.append((order[(i + 1) % len(order)], q))
                else:
                    ring.append((tn, q))
                    tacks.append((tn, q))
    if type in ("welt", "flap"):
        D["interfaced"].append(name)
    ppc = pb.make_piece(name, ring, "pocket", dict(pc.get("wrap") or {}), sym)
    ppc["wrap"].update({"lies_on": piece, "face": "out"})
    ppc["wrap"].pop("out", None)
    D["pieces"][name] = ppc
    if sym == "fold":
        D["centre"][name] = "fold"
    seen = set()
    for tn, q in tacks:
        if tn in seen:
            continue
        seen.add(tn)
        mk = f"{name}_{tn}"
        pc["marks"][mk] = np.asarray(q, float) + (np.array([0.0015, 0.0]) if abs(q[0]) < 1e-6 and sym == "fold" else 0.0)
        D.setdefault("sym_stitches", []).append([f"{name}:{tn}", f"{piece}:{mk}"])
    D["log"].append(f"{type} pocket {name} on {piece}: {np.ptp(Q[:, 0]) * (2 if sym == 'fold' else 1) * 1000:.0f} x "
                    f"{np.ptp(Q[:, 1]) * 1000:.0f} mm, laid on its outside, {len(seen)} tacks along its sewn edges "
                    f"({'top and bottom; the slanted sides open' if type == 'kangaroo' else 'sides and bottom; the top open'})")


def _in_seam_pocket(D: dict, piece: str, other: str | None = None, top: float | None = None, opening: float = 0.16,
                    width: float = 0.14, height: float = 0.24, name: str = "pocket", along: str | None = None, **o) -> None:
    """A pocket in the seam between `piece` (the front) and `other` (the back; default: the piece it shares a seam
    with, "along": a point on the seam meant): the seam is left unsewn over `opening` m from `top` (m below the
    seam's upper end; default 4 cm), and two bags (the same D shape, `width` deep into the front, `height` long) are
    sewn one to each lip of the opening and to each other. Both lie inside the front."""
    from . import pattern_blocks as pb
    flat = lambda side: [side] if isinstance(side, str) else list(side)
    one = lambda xs: xs[0] if len(xs) == 1 else xs
    seam = None
    for s in D["seams"]:
        for A, B in ((flat(s[0]), flat(s[1])), (flat(s[1]), flat(s[0]))):
            ia = [k for k, x in enumerate(A) if x.split(":")[0] == piece
                  and (not along or along in x.split(":", 1)[1].split(">"))]
            ib = [k for k, x in enumerate(B) if x.split(":")[0] != piece and (other is None or x.split(":")[0] == other)]
            if ia and ib and not any(x.split(":")[0] == piece for x in B):
                # (in a chain, the part of the other side that mates this one: the same place in the chain)
                seam, i, j = s, ia[0], (ia[0] if ia[0] in ib else ib[0])
                break
        if seam is not None:
            break
    if seam is None:
        raise DraftError(f"in-seam pocket: no seam between {piece} and {other or 'another piece'} (name it with \"other\" / \"along\")")
    ea, eb = A[i], B[j]
    other = eb.split(":")[0]
    note = D["notes"].pop(json.dumps(seam), None)
    top = 0.04 if top is None else float(top)
    ends = {}
    for tag, spec in (("F", ea), ("B", eb)):
        pn, arc = spec.split(":", 1)
        pcx = D["pieces"][pn]
        a0, b0 = arc.split(">")[0], arc.split(">")[-1]
        L = pb.edge_length(pcx, arc)
        if top + opening > L - 0.02:
            raise DraftError(f"in-seam pocket: the seam's part on {pn} is {L * 1000:.0f} mm, too short for an opening "
                             f"{opening * 1000:.0f} mm from {top * 1000:.0f} mm")
        pd._point(D, pcx, {"edge": arc, "dist": top}, f"{name}.top")
        pd._point(D, pcx, {"edge": arc, "dist": top + opening}, f"{name}.low")
        ends[tag] = (pn, a0, b0)
    (pf, fa, fb), (pk, ka, kb) = ends["F"], ends["B"]
    D["seams"] = [s for s in D["seams"] if s is not seam]
    up = [one(A[:i] + [f"{pf}:{fa}>{name}.top"]), one(B[:j] + [f"{pk}:{ka}>{name}.top"])]
    lo = [one([f"{pf}:{name}.low>{fb}"] + A[i + 1:]), one([f"{pk}:{name}.low>{kb}"] + B[j + 1:])]
    D["seams"] += [up, lo]
    if note:
        D["notes"][json.dumps(up)] = dict(note)
        D["notes"][json.dumps(lo)] = dict(note)
    # named edges that ran over the old seam (a side seam edge): unchanged specs still resolve (the points were added)
    f = D["pieces"][pf]
    ix = pattern.arc_indices(f, f"{name}.top>{name}.low")
    E = f["P"][ix]
    T, Lw = E[0], E[-1]
    d = (Lw - T) / np.linalg.norm(Lw - T)
    nin = np.array([-d[1], d[0]])
    if nin @ (f["P"].mean(0) - T) < 0:
        nin = -nin  # into the front
    # the bag: the opening's own line, then a D into the front, hanging below the opening
    low_end = T + d * height
    curve = pb.bez(Lw, Lw + d * 0.35 * (height - opening), low_end + nin * 0.25 * width, low_end + nin * 0.55 * width, 6)
    curve2 = pb.bez(low_end + nin * 0.55 * width, low_end + nin * width, T + nin * width + d * 0.25 * height, T + nin * width * 0.8, 8)
    pts = [("open.a", T)] + [(None, q) for q in E[1:-1]] + [("open.b", Lw)] + [(None, q) for q in curve[:-1]] + \
        [("bagLow", curve[-1])] + [(None, q) for q in curve2[:-1]] + [("bagTop", curve2[-1])]
    from .cloth import _inside
    Q = np.array([q for _, q in pts], float)
    if _inside(f["P"], Q * 0.97 + 0.03 * Q.mean(0)).mean() < 0.9:
        raise DraftError(f"in-seam pocket {name}: the bag ({width * 1000:.0f} x {height * 1000:.0f} mm) doesn't fit inside {pf}")
    for tag, depth in (("front", 1), ("back", 2)):
        b = pb.make_piece(f"{name}_{tag}", pts, "pocket", dict(f.get("wrap") or {}), f.get("sym", "pair"))
        b["wrap"].update({"lies_on": pf, "lies_depth": depth})
        b["wrap"].pop("out", None)
        b["traced"] = pf
        D["pieces"][f"{name}_{tag}"] = b
    s1 = [f"{name}_front:open.a>open.b", f"{pf}:{name}.top>{name}.low"]
    s2 = [f"{name}_back:open.a>open.b", f"{pk}:{name}.top>{name}.low"]
    s3 = [f"{name}_front:open.b>bagLow>bagTop", f"{name}_back:open.b>bagLow>bagTop"]
    s4 = [f"{name}_front:bagTop>open.a", f"{name}_back:bagTop>open.a"]
    D["seams"] += [s1, s2, s3, s4]
    e2 = pd.edge_length(D, s2[0]) / max(pd.edge_length(D, s2[1]), 1e-9) - 1
    D["notes"][json.dumps(s1)] = {"ease": [-0.004, 0.004], "why": f"{name}'s front bag is sewn to the opening's front lip"}
    D["notes"][json.dumps(s2)] = {"ease": [round(e2 - 0.01, 4), round(e2 + 0.01, 4)],
                                  "why": f"{name}'s back bag is sewn to the opening's back lip"}
    D["log"].append(f"in-seam pocket {name}: the seam {pf} / {pk} left open {opening * 1000:.0f} mm from {top * 1000:.0f} mm "
                    f"below its top; two bags {width * 1000:.0f} x {height * 1000:.0f} mm sewn to its lips and to each other, "
                    f"lying inside {pf}")


def op_lining(D: dict, pieces: list | None = None, attach: list | None = None, suffix: str = "_lining", **o) -> None:
    """A lining derived from its shell: every body piece (or `pieces`) traced as "<piece>_lining" (the same outline:
    a tailor then adds a centre-back pleat and trims the fronts to the facing, not done here), the seams between
    lined pieces repeated between their linings, each lining laid inside its shell, and the lining sewn to the shell
    along the named edges in `attach` (default: the hems, the sleeve hems and the back neck: a bagged lining). Do it
    last, after the shell's shaping, collar and sleeves, before unfold."""
    body = pieces or [n for n, pc in D["pieces"].items() if pc.get("role") in ("front", "back", "sleeve")
                      and not pc.get("traced")]
    if not body:
        raise DraftError("lining: no body pieces to line")
    ren = lambda e: e.split(":", 1)[0] + suffix + ":" + e.split(":", 1)[1]
    for n in body:
        c = copy.deepcopy(D["pieces"][n])
        c.update(name=n + suffix, role="lining", traced=n, darts={})
        c["wrap"] = dict(c.get("wrap") or {}, lies_on=n)
        c["wrap"].pop("out", None)
        D["pieces"][n + suffix] = c
        if n in D["centre"]:
            D["centre"][n + suffix] = D["centre"][n]
            if D["centre"][n] == "seam":  # its own centre seam, as its shell's
                key = "centre_front" if str(D["pieces"][n].get("role") or "").endswith("front") else "centre_back"
                D.setdefault("pair_seams", []).extend(ren(e) for e in D["edges"].get(key, []) if e.split(":")[0] == n)
    flat = lambda side: [side] if isinstance(side, str) else list(side)
    one = lambda xs: xs[0] if len(xs) == 1 else xs
    n_in = 0
    for s in list(D["seams"]):
        if all(e.split(":")[0] in body for side in s for e in flat(side)):
            ns = [one([ren(e) for e in flat(s[0])]), one([ren(e) for e in flat(s[1])])]
            D["seams"].append(ns)
            n_in += 1
            if json.dumps(s) in D["notes"]:
                D["notes"][json.dumps(ns)] = dict(D["notes"][json.dumps(s)])
    for e in D.get("pair_seams") or []:
        if e.split(":")[0] in body:
            D["pair_seams"].append(ren(e))
    did = []
    for key in (attach if attach is not None else ["hem_back", "hem_front", "sleeve_hem", "neck_back"]):
        chain = [e for e in D["edges"].get(key, []) if e.split(":")[0] in body]
        if not chain:
            continue
        seam = [one([ren(e) for e in chain]), one(list(chain))]
        D["seams"].append(seam)
        D["notes"][json.dumps(seam)] = {"ease": [-0.004, 0.004], "turned": "under",
                                        "why": f"the lining is sewn to the shell along {key} (the same edge) and turned in"}
        did.append(key)
    D["log"].append(f"lining: {len(body)} pieces traced from their shells ({', '.join(body)}), {n_in} seams repeated "
                    f"between them, sewn to the shell along {', '.join(did) or 'nothing'}; each lies inside its shell")


def op_crease(D: dict, pieces: list | None = None, angle: float = 205.0, strength: float = 0.6, **o) -> None:
    """A pressed crease down a piece's `crease` line (a trouser leg's grain line: through the middle of knee and hem,
    front and back), as a press fold from hem to waist: a ridge standing OUT (angle > 180 on the outside; 205 = 25
    deg of turn left in the cloth), laid by the wrap (nothing is turned at placement), held by the fold row's rest
    angle and bending. Tailors press the front crease up to the waistband (or into the first pleat) and the back
    crease up to the seat; a fold line here must cross its piece, so the back's runs to the waist too (the seat
    stretches it flat there)."""
    names = pieces or [n for n, pc in D["pieces"].items() if "crease" in (pc.get("lines") or {})]
    if not names:
        raise DraftError("crease: no piece has a crease line (a trouser block's front / back)")
    for nm in names:
        pc = D["pieces"][nm]
        if "crease" not in (pc.get("lines") or {}):
            raise DraftError(f"crease: {nm} has no crease line (has {', '.join(sorted(pc.get('lines') or {})) or 'no lines'})")
        L = np.asarray(pc["lines"]["crease"], float)
        D["folds"].append({"piece": nm, "line": L.tolist(), "angle": float(angle), "kind": "press", "strength": float(strength),
                           "name": f"crease {nm}", "in_wrap": True, "reach": 0.05})
    D["log"].append(f"crease pressed on {', '.join(names)}: a ridge of {angle - 180:.0f} deg down the grain line "
                    f"(strength {strength:g})")


def op_fly(D: dict, piece: str = "front", length: float = 0.18, width: float = 0.035, state="closed", name: str = "fly",
           **o) -> None:
    """A fly: the centre front seam from the waist down `length` m is an OPENING closed by a zip (a closure, kind
    zip: sewn when worn closed, left over right; `state` "open" leaves it unsewn), the seam below it stays a seam.
    `width` = the fly facing's width (where the J of topstitching runs on the over side: detail maps)."""
    pc = D["pieces"][piece]
    ce = [e for e in D["edges"].get("centre_front") or [] if e.split(":")[0] == piece]
    if not ce or D["centre"].get(piece) != "seam":
        raise DraftError(f"fly: {piece} has no centre front seam (a trouser block's front; a skirt takes a cb_zip)")
    arc = ce[0].split(":", 1)[1]
    pts = arc.split(">")
    full = pb_edge_length(pc, arc)
    seat = pb_edge_length(pc, ">".join(pts[:2])) if len(pts) > 2 else full
    length = float(min(length, 0.92 * seat))  # it ends on the straight part, above where the crotch curve turns
    pd._point(D, pc, {"edge": ">".join(pts[:2]), "dist": length}, f"{name}End")
    D["edges"]["centre_front"] = [f"{piece}:{name}End>" + ">".join(pts[1:])] + [e for e in D["edges"]["centre_front"] if e != ce[0]]
    D["edges"][name] = [f"{piece}:{pts[0]}>{name}End"]
    pc["lines"][f"{name}_stitch"] = _fly_j(pc, pts[0], f"{name}End", width)
    D.setdefault("pair_closures", []).append({"name": name, "kind": "zip", "piece": piece, "arc": f"{pts[0]}>{name}End",
                                              "state": state, "width": float(width)})
    D["log"].append(f"fly on {piece}: {length * 1000:.0f} mm from the waist, a zip closure (left over right), facing "
                    f"{width * 1000:.0f} mm; the centre seam runs on from its end to the fork")


def _fly_j(pc: dict, top: str, end: str, width: float) -> np.ndarray:
    """The fly's topstitching: down from the waist `width` in from the centre edge, curving in to the edge at the
    fly's end (a J)."""
    A, B = pc["P"][pc["names"][top]], pc["P"][pc["names"][end]]
    d = (B - A) / (np.linalg.norm(B - A) + 1e-12)
    n = np.array([-d[1], d[0]])
    if pattern._poly_inside(pc["P"], (0.5 * (A + B) + 0.004 * n)[None]).mean() < 0.5:
        n = -n
    Ln = float(np.linalg.norm(B - A))
    r = min(width, 0.45 * Ln)
    th = np.linspace(0, np.pi / 2, 9)
    arc = np.array([A + d * (Ln + 0.012 - r + r * np.sin(t)) + n * (width - r + r * np.cos(t)) for t in th])
    return np.r_[(A + n * width)[None], arc]


def pb_edge_length(pc: dict, arc: str) -> float:
    return pattern.length(pc["P"][pattern.arc_indices(pc, arc)])


pd.OPS.update({"crease": op_crease, "fly": op_fly, "lining": op_lining, "pocket": op_pocket, "contour": op_contour, "join": op_join, "round_corner": op_round_corner, "fisheye": op_fisheye})
