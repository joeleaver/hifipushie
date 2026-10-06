"""Principle-based pattern drafting: a garment that doesn't exist yet = a block + a list of operations.

A draft D = {"pieces": {name: half piece}, "seams": [[side, side]], "edges": {name: [edge specs]}, "centre":
{piece: "fold" | "seam" | "open"}, "meta", "log": [what each step did, with its numbers], "notes": {seam key:
{"ease": [lo, hi], "why"}}, "folds", "interfaced", "stitches", "generate"}. Pieces are HALVES until `unfold`.

Two things make operations composable:
  * every construction point is NAMED and operations address points, edges ("a>b", "a>via>b") and darts by name;
  * NAMED EDGES SURVIVE OPERATIONS. D["edges"] (armhole_front, armhole_back, neck_front, neck_back, hem_front, ...)
    and the seam table are rewritten by every operation that cuts or re-shapes an outline (`_remap`): an edge that is
    cut by a style line becomes a chain over the new pieces, a dart moved onto an edge splits it. So a sleeve can be
    drafted into "the armhole" and a collar onto "the neckline" whatever was done to the bodice before.
Mating edges stay matched by construction (a cut makes two identical edges; a take-in shaves both alike; a moved dart
only rotates part of the outline rigidly) or the operation DECLARES the ease it made (D["notes"]): `consistency`
measures every seam and names any that are neither.

Operations (`OPS`; each is {"op": name, ...}):
  style_line   cut a piece in two along a line between two outline points (through optional interior points); the two
               new edges are sewn (a panel seam, a yoke). "take_in": shave both edges at a level (contouring: the
               waist suppression a dart would take, moved into the seam).
  dart         move a dart to another edge point (pivot about its tip or an apex): the outline between the old dart
               and the new position turns rigidly, the old dart closes, the new opens. Seam lengths don't change.
  dart_to_ease close a dart by straightening its edge: the intake becomes ease (or gathers) declared on that seam.
  (not yet: darts_to_seam, joining two darts into a panel seam on a darted block; on a dartless block a style_line
               with take_in does the same job)
  flare        slash from an edge to a hinge point and spread (added fullness: an A-line, a flared hem); or close
               (negative amount: tapering). The hinge edge keeps its length.
  lengthen     lengthen / shorten below a level on every piece named (the side seams stay matched when both sides
               are named: say so, or `consistency` will).
  extend       push an edge outward by an amount (a button stand, a wrap overlap, a vent extension).
  reshape      move a named point (a neckline lowered, a hem curved), neighbours eased along.
  facing       a new piece traced from a piece along edges, `width` deep (a facing, a hem facing); sewn to the edges
               it was traced from, turned under by a fold.
  collar       a collar drafted from the neckline as it is now: "band" (a stand: the neckline's length, slightly
               curved), "flat" (traced from the neckline: lies flat), "roll" (between: less curve = more stand).
  sleeve       draft the sleeve into the armhole as it is now (pattern_blocks.sleeve); "two_piece" splits it.
  unfold       halves -> the garment's pieces (left/right pairs, pieces cut on the fold, sleeve copies) and the seams
               mirrored. Runs last by itself; operations after an explicit unfold address the whole pieces
               (asymmetric designs).
"""
from __future__ import annotations

import copy
import json
import math

import numpy as np

from . import pattern, pattern_blocks as pb


class DraftError(ValueError):
    pass


# ---------------------------------------------------------------- outline helpers


def _counter(D: dict) -> int:
    D["_n"] = D.get("_n", 0) + 1
    return D["_n"]


def _names_at(pc: dict, i: int) -> list:
    return sorted((k for k, v in pc["names"].items() if v == i), key=lambda k: (k.startswith("_"), len(k)))


def _name_for(D: dict, pc: dict, i: int) -> str:
    nm = _names_at(pc, i)
    if nm:
        return nm[0]
    k = f"_p{_counter(D)}"
    pc["names"][k] = i
    return k


def _insert(pc: dict, after: int, q, name: str | None = None) -> int:
    """A new outline vertex after index `after`; names shift. Returns its index."""
    i = after + 1
    pc["P"] = np.insert(pc["P"], i, np.asarray(q, float), axis=0)
    pc["names"] = {k: (v + 1 if v >= i else v) for k, v in pc["names"].items()}
    if name:
        pc["names"][name] = i
    return i


def _point(D: dict, pc: dict, ps, name: str | None = None) -> int:
    """An outline index for a point spec: a name; {"edge": "a>b", "t": 0..1 along it | "dist": m from a | "y": level};
    inserted as a vertex when it isn't one."""
    if isinstance(ps, str):
        if ps not in pc["names"]:
            raise DraftError(f"{pc['name']}: no point {ps!r} (has {', '.join(sorted(k for k in pc['names'] if not k.startswith('_')))})")
        if name:
            pc["names"][name] = pc["names"][ps]
        return pc["names"][ps]
    ix = pattern.arc_indices(pc, ps["edge"])
    L = pc["P"][ix]
    seg = np.linalg.norm(np.diff(L, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    if "y" in ps:
        # (a level by name: "waist", "hips", "chest": the block's own line)
        if isinstance(ps["y"], str) and f"{ps['y']}_y" not in D["meta"]:
            raise DraftError(f"{pc['name']}: no level {ps['y']!r} in this block (a y in m, or waist / hips / chest)")
        y = float(D["meta"][f"{ps['y']}_y"]) if isinstance(ps["y"], str) else float(ps["y"])
        hit = [k for k in range(len(L) - 1) if (L[k, 1] - y) * (L[k + 1, 1] - y) <= 0 and L[k, 1] != L[k + 1, 1]]
        if not hit:
            raise DraftError(f"{pc['name']}: edge {ps['edge']} doesn't cross y = {y}")
        k = hit[0]
        s = cum[k] + seg[k] * (y - L[k, 1]) / (L[k + 1, 1] - L[k, 1])
    elif "dist" in ps:
        s = float(ps["dist"])
    else:
        s = float(ps.get("t", 0.5)) * cum[-1]
    s = float(np.clip(s, 0, cum[-1]))
    k = int(np.clip(np.searchsorted(cum, s, side="right") - 1, 0, len(seg) - 1))
    if abs(s - cum[k]) < 1e-5:
        i = ix[k]
    elif abs(s - cum[k + 1]) < 1e-5:
        i = ix[k + 1]
    else:
        q = L[k] + (L[k + 1] - L[k]) * (s - cum[k]) / seg[k]
        a, b = ix[k], ix[k + 1]
        n = len(pc["P"])
        after = a if (a + 1) % n == b else b  # the arc may run backwards round the outline
        i = _insert(pc, after, q)
    if name:
        pc["names"][name] = i
    return i


def _spec_of(D: dict, pname: str, pc: dict, run: list) -> str:
    """An edge spec for a run of consecutive outline indices (with a via point when it has an inside)."""
    a, b = _name_for(D, pc, run[0]), _name_for(D, pc, run[-1])
    if len(run) >= 3:
        return f"{pname}:{a}>{_name_for(D, pc, run[len(run) // 2])}>{b}"
    return f"{pname}:{a}>{b}"


def _flat(side) -> list:
    return [side] if isinstance(side, str) else list(side)


def _remap(D: dict, old_name: str, old: dict, imap: dict, new: dict) -> None:
    """Rewrite every seam and named edge that ran on `old` (a piece replaced by the pieces in `new`):
    imap {old outline index: [(new piece name, new index), ...]}. An old edge becomes the chain of new edges that
    cover it; where two consecutive old vertices aren't neighbours on any new piece (the cut went between them, a
    dart opened) the chain breaks there."""
    def runs(spec):
        nm, arc = spec.split(":", 1)
        if nm != old_name:
            return [spec]
        ix = pattern.arc_indices(old, arc)
        out, cur = [], None  # cur = (piece, [indices])
        for u, v in zip(ix[:-1], ix[1:]):
            found = None
            for pu, iu in imap.get(u, []):
                for pv, iv in imap.get(v, []):
                    n = len(new[pu]["P"])
                    if pu == pv and ((iu + 1) % n == iv or (iv + 1) % n == iu):
                        found = (pu, iu, iv)
                        break
                if found:
                    break
            if not found:
                if cur:
                    out.append(cur)
                cur = None
                continue
            if cur and cur[0] == found[0] and cur[1][-1] == found[1]:
                cur[1].append(found[2])
            else:
                if cur:
                    out.append(cur)
                cur = (found[0], [found[1], found[2]])
        if cur:
            out.append(cur)
        return [_spec_of(D, p, new[p], r) for p, r in out]

    seams = []
    for A, B in D["seams"]:
        key = json.dumps([A, B])
        a2 = [s for e in _flat(A) for s in runs(e)]
        b2 = [s for e in _flat(B) for s in runs(e)]
        if not a2 or not b2:
            D["log"].append(f"  seam dropped (its edge is gone): {A} || {B}")
            continue
        nA, nB = (a2[0] if len(a2) == 1 else a2), (b2[0] if len(b2) == 1 else b2)
        if key in D["notes"]:
            D["notes"][json.dumps([nA, nB])] = D["notes"].pop(key)
        seams.append([nA, nB])
    D["seams"] = seams
    for k, chain in list(D["edges"].items()):
        D["edges"][k] = [s for e in chain for s in runs(e)]


def _replace(D: dict, old_name: str, new: dict) -> None:
    order = []
    for k in D["pieces"]:
        order += list(new) if k == old_name else [k]
    pcs = dict(D["pieces"], **new)
    D["pieces"] = {k: pcs[k] for k in order}
    for k in ("centre",):
        if old_name in D[k]:
            v = D[k][old_name] if old_name in new else D[k].pop(old_name)
            # the centre edge goes with every piece that holds the centre line (x = 0): a cut across the piece (a
            # yoke) leaves both parts on it (the yoke of a back with a centre seam had none: its halves weren't sewn)
            for nm, pc in new.items():
                if np.sum(np.abs(pc["P"][:, 0]) < 1e-6) >= 2:
                    D[k][nm] = v
                elif nm == old_name:
                    D[k].pop(nm, None)


def edge_points(D: dict, chain) -> np.ndarray:
    P = [D["pieces"][e.split(":")[0]]["P"][pattern.arc_indices(D["pieces"][e.split(":")[0]], e.split(":", 1)[1])]
         for e in _flat(chain)]
    return P


def edge_length(D: dict, chain) -> float:
    return float(sum(pattern.length(p) for p in edge_points(D, chain)))


# ---------------------------------------------------------------- operations


def op_style_line(D: dict, piece: str, **o) -> None:
    """Cut `piece` from point "from" to point "to" (outline points), through "via" [[x, y] | mark name ...]."""
    pc = D["pieces"][piece]
    old = copy.deepcopy(pc)
    name = o.get("name", f"line{_counter(D)}")
    work = copy.deepcopy(pc)
    ia = _point(D, work, o["from"], f"{name}.a")
    ib = _point(D, work, o["to"], f"{name}.b")
    ia = work["names"][f"{name}.a"]  # (the second insert may have shifted the first)
    n = len(work["P"])
    via = []
    for v in o.get("via") or []:
        via.append(np.asarray(work["marks"][v] if isinstance(v, str) else v, float))
    if o.get("curve", True) and via:  # a smooth line through the points
        ctl = [work["P"][ia]] + via + [work["P"][ib]]
        dense = []
        for k in range(len(ctl) - 1):
            p0 = ctl[max(k - 1, 0)]
            p1, p2 = ctl[k], ctl[k + 1]
            p3 = ctl[min(k + 2, len(ctl) - 1)]
            for t in np.linspace(0, 1, 9)[1:]:
                dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                                    + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
        via = dense[:-1]
    fwd = [(ia + k) % n for k in range((ib - ia) % n + 1)]  # a .. b
    bwd = [(ib + k) % n for k in range((ia - ib) % n + 1)]  # b .. a
    Pv = np.asarray(via).reshape(-1, 2)
    new, imap = {}, {}
    # the old piece's indices -> work indices (points inserted for the cut ends shift them): match by coordinates
    w_of = {i: i for i in range(len(work["P"]))}  # (arcs are resolved on `work`: the piece with the cut ends in)
    halves = [(fwd, Pv[::-1]), (bwd, Pv)]
    names = o.get("names")
    built = []
    for run, inner in halves:
        P = np.r_[work["P"][run], inner] if len(inner) else work["P"][run]
        h = {"P": P, "names": {}, "marks": {}, "lines": {}, "grain": work["grain"], "role": work.get("role"),
             "wrap": dict(work.get("wrap") or {}), "sym": work.get("sym", "pair"), "darts": {}}
        pos = {w: k for k, w in enumerate(run)}
        for k_, w in work["names"].items():
            if w in pos:
                h["names"][k_] = pos[w]
        for j in range(len(inner)):
            h["names"][f"{name}.{j + 1}" if run is bwd else f"{name}.{len(inner) - j}"] = len(run) + j
        from .cloth import _inside
        for k_, v in work["marks"].items():
            if _inside(P, np.asarray(v, float)[None])[0]:
                h["marks"][k_] = v
        for k_, Ln in work["lines"].items():
            if _inside(P, np.asarray(Ln, float).mean(0)[None])[0]:
                h["lines"][k_] = Ln
        for dn, pts in (work.get("darts") or {}).items():
            if all(p in h["names"] for p in pts):
                h["darts"][dn] = pts
        built.append((h, pos))
    # which half holds the centre line: it is named first
    cx = [float(np.abs(h["P"][:, 0]).min()) + 1e-3 * float(h["P"][:, 0].mean()) for h, _ in built]
    order = [0, 1] if cx[0] <= cx[1] else [1, 0]
    if all(np.sum(np.abs(h["P"][:, 0]) < 1e-6) >= 2 for h, _ in built):
        # a cut ACROSS the piece (a yoke): both parts hold the centre line; the upper one is named first
        order = [0, 1] if built[0][0]["P"][:, 1].mean() >= built[1][0]["P"][:, 1].mean() else [1, 0]
    names = names or [f"{piece}_centre", f"{piece}_side"]
    if o.get("apart", True):
        # the two parts start a little apart (their cut edges are the same line: laid edge on edge, a contact solver
        # sees them through each other): the part away from the centre moves off along the cut's normal
        c0, c1 = built[order[0]][0]["P"].mean(0), built[order[1]][0]["P"].mean(0)
        dv = work["P"][ib] - work["P"][ia]
        nv = np.array([-dv[1], dv[0]]) / max(np.linalg.norm(dv), 1e-12)
        nv = nv if nv @ (c1 - c0) > 0 else -nv
        sh0 = np.asarray(built[order[1]][0]["wrap"].get("shift", [0.0, 0.0]), float)
        # (a cut ACROSS the piece, a yoke: 6 mm, its corners at the side seams overlapped at 2, and at 4 once an
        # in-seam pocket put more vertices on the side seam)
        across_ = all(np.sum(np.abs(h_["P"][:, 0]) < 1e-6) >= 2 for h_, _ in built)
        built[order[1]][0]["wrap"]["shift"] = (sh0 + (0.006 if across_ else 0.002) * nv).round(5).tolist()
        if across_:
            # ... and the lower part a layer further out: once it is flared (pivoted at the seam) its top corner at
            # the side seam rises past the yoke's (12 mm on the skirt), on the same surface: read as a crossing
            built[order[1]][0]["wrap"]["out"] = round(float(built[order[1]][0]["wrap"].get("out", 0.0)) + 0.003, 5)
    for nm, k in zip(names, order):
        h, pos = built[k]
        h["name"] = nm
        new[nm] = h
        for i, w in w_of.items():
            if w in pos:
                imap.setdefault(i, []).append((nm, pos[w]))
    _replace(D, piece, new)
    _remap(D, piece, work, imap, new)
    a, b = names[order[0]], names[order[1]]
    mid = [f"{name}.{j + 1}" for j in range(len(Pv))]
    sa = f"{a}:{name}.a>" + (mid[len(mid) // 2] + ">" if mid else "") + f"{name}.b"
    sb = f"{b}:{name}.a>" + (mid[len(mid) // 2] + ">" if mid else "") + f"{name}.b"
    D["seams"].append([sa, sb])
    D["edges"][name] = [sa]
    D["lines"][name] = (sa, sb)
    D["log"].append(f"style line {name}: {piece} cut into {a} + {b} along {edge_length(D, sa) * 1000:.0f} mm; the two "
                    "edges are the same line (sewn 1:1)")
    if o.get("take_in"):
        op_take_in(D, line=name, **(o["take_in"] if isinstance(o["take_in"], dict) else {"amount": o["take_in"]}))


def op_take_in(D: dict, line: str, amount: float, y: float | None = None, length: float = 0.22, share: float = 0.65,
               **_) -> None:
    """Contour a panel seam: `amount` taken out at level y (default: the waist), fading out over `length` above and
    below (a fish-eye dart moved into the seam). The SIDE panel's edge takes `share` of it and the centre panel's the
    rest: the centre panel stays nearly straight on grain and the side panel carries the curve, as a tailor cuts it."""
    sa, sb = D["lines"][line]
    y = D["meta"].get("waist_y", 0.0) if y is None else float(y)
    cen = [float(np.abs(D["pieces"][x.split(":")[0]]["P"][:, 0]).min()) for x in (sa, sb)]
    shares = (1 - share, share) if cen[0] <= cen[1] else (share, 1 - share)
    for spec, part in zip((sa, sb), shares):
        nm, arc = spec.split(":", 1)
        pc = D["pieces"][nm]
        densify_edge(pc, arc)  # (a straight cut has only its two ends: nothing to carry the curve, nothing was taken in)
        ix = pattern.arc_indices(pc, arc)
        L = pc["P"][ix]
        t = np.gradient(L, axis=0)
        nrm = np.c_[-t[:, 1], t[:, 0]]
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
        if np.mean(np.sum((pc["P"].mean(0) - L) * nrm, 1)) < 0:
            nrm = -nrm  # into the piece
        w = np.clip(1 - np.abs(L[:, 1] - y) / length, 0, 1)
        w = w * w * (3 - 2 * w)
        mv = nrm * (amount * part * w)[:, None]
        # an end the shaping hasn't faded out at (a cropped hem inside the taper) slides along its own edge: level
        # (held, the points next to it moved and left a hook at the hem)
        for k in (0, -1):
            mv[k] = [np.sign(nrm[k, 0]) * amount * part * w[k], 0.0]
        pc["P"][ix] = L + mv
    la, lb = edge_length(D, sa), edge_length(D, sb)
    press_note(D, line)
    D["log"].append(f"take in {line}: {amount * 1000:.0f} mm at y {y * 1000:.0f} mm, {share * 100:.0f}% from the side "
                    f"panel ({la * 1000:.1f} / {lb * 1000:.1f} mm)")


def press_note(D: dict, line: str) -> None:
    """A shaped panel seam's two edges differ a little in length (the more hollowed one is the longer): a tailor
    stretches the straighter one onto it with the iron, or eases the hollow in. Under 2% that is declared on the
    seam; more is left for `consistency` to name (the shares are wrong)."""
    sa, sb = D["lines"][line]
    for s in D["seams"]:
        if s == [sa, sb] or s == [sb, sa]:
            la, lb = edge_length(D, s[0]), edge_length(D, s[1])
            e_s = la / max(lb, 1e-9) - 1
            key = json.dumps(s)
            if 0.003 < abs(e_s) <= 0.02:
                D["notes"][key] = {"ease": [round(e_s - 0.004, 4), round(e_s + 0.004, 4)],
                                   "why": f"panel seam {line}: one edge is {abs(la - lb) * 1000:.0f} mm longer after "
                                          "shaping, pressed / eased on"}
            elif abs(e_s) <= 0.003:
                D["notes"].pop(key, None)


def densify_edge(pc: dict, arc: str, step: float = 0.03) -> None:
    """Vertices added along an edge until none of its segments is longer than `step` (an edge about to be shaped)."""
    for _ in range(300):
        ix = pattern.arc_indices(pc, arc)
        seg = np.linalg.norm(np.diff(pc["P"][ix], axis=0), axis=1)
        k = int(np.argmax(seg))
        if seg[k] <= step:
            return
        a, b = ix[k], ix[k + 1]
        _insert(pc, a if (a + 1) % len(pc["P"]) == b else b, 0.5 * (pc["P"][a] + pc["P"][b]))


def _rot(P, c, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    R = np.array([[ca, -sa], [sa, ca]])
    return (np.asarray(P, float) - c) @ R.T + c


def op_dart(D: dict, piece: str, dart: str, to, apex=None, **o) -> None:
    """Move a dart: slash from the new position `to` (an outline point spec) to the pivot (the dart's tip, or `apex`:
    a mark / [x, y]), close the old dart by turning the outline between it and the slash."""
    pc = D["pieces"][piece]
    if dart not in pc.get("darts", {}):
        raise DraftError(f"{piece}: no dart {dart!r} (has {', '.join(pc.get('darts', {})) or 'none'})")
    old = copy.deepcopy(pc)
    work = copy.deepcopy(pc)
    a_n, t_n, b_n = work["darts"][dart]
    it = _point(D, work, to, "_to")
    ia, itp, ib = (work["names"][k] for k in (a_n, t_n, b_n))
    it = work["names"]["_to"]
    n = len(work["P"])
    if it in (ia, itp, ib):
        raise DraftError(f"{piece}: the dart is already at {to!r}")
    piv = work["P"][itp].copy() if apex is None else np.asarray(work["marks"][apex] if isinstance(apex, str) else apex, float)
    A, B = work["P"][ia], work["P"][ib]
    # the pivot must be as far from one leg end as from the other, or the dart can't close by turning: an apex off
    # the dart's centre line is taken onto it (the dart is "trued" to the apex)
    mid_, d_ = 0.5 * (A + B), (B - A) / max(np.linalg.norm(B - A), 1e-12)
    off_ = float((piv - mid_) @ d_)
    if abs(off_) > 1e-6:
        piv = piv - off_ * d_
        if abs(off_) > 0.002:
            D["log"].append(f"  (the pivot was {abs(off_) * 1000:.0f} mm off the dart's centre line: moved onto it)")
    ang_a = math.atan2(*(A - piv)[::-1])
    ang_b = math.atan2(*(B - piv)[::-1])
    # the outline runs a -> tip -> b (or b -> tip -> a); the section from the dart's far leg to `to` turns
    step = 1 if (ia + 1) % n == itp else -1
    # two ways to do it: turn the outline from the dart's b leg on to `to`, or from its a leg back to `to`. The
    # section that holds the centre line (x = 0) must stay where it is; otherwise the shorter one turns
    def section(start, stp):
        k, out = start, []
        while True:
            out.append(k)
            if k == it:
                return out
            k = (k + stp) % n
            if k in (ia, ib, itp):
                return None
    cands = []
    for leg, other, stp, sgn in ((ib, ia, step, ang_a - ang_b), (ia, ib, -step, ang_b - ang_a)):
        sec = section(leg, stp)
        if sec is not None:
            cen = int(np.sum(np.abs(work["P"][sec, 0]) < 1e-6))
            cands.append((cen, len(sec), sec, sgn, other, leg))
    if not cands:
        raise DraftError(f"{piece}: can't reach {to!r} from dart {dart}")
    cands.sort(key=lambda c: (c[0], c[1]))
    _, _, moving, ang, stay_leg, move_leg = cands[0]
    ang = (ang + math.pi) % (2 * math.pi) - math.pi
    Pn = work["P"].copy()
    Pn[moving] = _rot(work["P"][moving], piv, ang)
    T_old = work["P"][it].copy()
    T_new = Pn[it].copy()
    u_ = 0.5 * (T_old + T_new) - piv
    tip_new = piv + u_ / max(np.linalg.norm(u_), 1e-9) * float(o.get("back_off", 0.0))  # the tip set back from the pivot
    # the new outline: walk the old ring; drop the old tip and the moving leg (it now lies on the staying leg);
    # at `to` put  T_new, tip, T_old  in walking order (moving side first when we arrive from the moving side)
    ring, tag = [], []
    for k in range(n):
        if k == itp or k == move_leg:
            continue
        if k == it:
            prev_moving = ((k - 1) % n) in moving
            trio = [(T_new, "new"), (tip_new, "tip"), (T_old, "old")] if prev_moving else \
                [(T_old, "old"), (tip_new, "tip"), (T_new, "new")]
            for q, tg in trio:
                ring.append(q)
                tag.append((k, tg))
            continue
        ring.append(Pn[k])
        tag.append((k, "v"))
    newp = dict(work, P=np.asarray(ring))
    names = {}
    pos = {}
    for j, (k, tg) in enumerate(tag):
        pos.setdefault(k, {})[tg] = j
    for nm_, k in work["names"].items():
        if nm_ in (a_n, t_n, b_n, "_to"):
            continue
        if k == move_leg:
            k = stay_leg
        if k == itp:
            continue
        if k == it:
            names[nm_] = pos[k]["old"]
        elif k in pos:
            names[nm_] = pos[k]["v"]
    moving_first = tag[pos[it]["new"]][1] == "new" and pos[it]["new"] < pos[it]["old"]
    # the dart keeps its point names: A / B in outline order
    first, second = (pos[it]["new"], pos[it]["old"]) if pos[it]["new"] < pos[it]["old"] else (pos[it]["old"], pos[it]["new"])
    names[a_n], names[t_n], names[b_n] = first, pos[it]["tip"], second
    names[f"{dart}.was"] = pos[stay_leg]["v"]
    newp["names"] = names
    # marks and lines on the turned side turn with it (side = which side of the slash a point lies, by angle)
    def turned(q):
        from .cloth import _inside
        poly = np.r_[work["P"][moving], [piv]]
        return bool(_inside(poly, np.asarray(q, float)[None])[0])
    newp["marks"] = {k_: (_rot(v, piv, ang) if turned(v) else v) for k_, v in work["marks"].items()}
    newp["lines"] = {k_: v for k_, v in work["lines"].items()}
    newp["darts"] = dict(work["darts"])
    # old indices -> new: `old` is the piece before the point at `to` was inserted
    imap = {}
    for w in range(n):
        i = w
        if w == itp:
            continue
        w2 = stay_leg if w == move_leg else w
        if w2 == it:
            imap[i] = [(piece, pos[it]["old"]), (piece, pos[it]["new"])]
        else:
            imap[i] = [(piece, pos[w2]["v"])]
    D["pieces"][piece] = newp
    dart_seam = None
    for s in D["seams"]:
        if all(isinstance(x, str) for x in s) and {x.split(":", 1)[1] for x in s} == {f"{a_n}>{t_n}", f"{b_n}>{t_n}"}:
            dart_seam = s
    D["seams"] = [s for s in D["seams"] if s is not dart_seam]
    work["names"].pop("_to", None)
    _remap(D, piece, work, imap, {piece: newp})
    D["seams"].append([f"{piece}:{a_n}>{t_n}", f"{piece}:{b_n}>{t_n}"])
    la, lb = edge_length(D, f"{piece}:{a_n}>{t_n}"), edge_length(D, f"{piece}:{b_n}>{t_n}")
    D["log"].append(f"dart {dart} on {piece} moved to {to if isinstance(to, str) else json.dumps(to)}: turned "
                    f"{abs(math.degrees(ang)):.1f} deg about the {'apex' if apex is not None else 'tip'}; new legs "
                    f"{la * 1000:.1f} / {lb * 1000:.1f} mm, intake {np.linalg.norm(T_old - T_new) * 1000:.0f} mm")


def op_dart_to_ease(D: dict, piece: str, dart: str, **o) -> None:
    """Close a dart by leaving its edge straight: the intake stays in the edge as ease (or gathers)."""
    pc = D["pieces"][piece]
    old = copy.deepcopy(pc)
    a_n, t_n, b_n = pc["darts"].pop(dart)
    ia, itp, ib = (pc["names"][k] for k in (a_n, t_n, b_n))
    intake = float(np.linalg.norm(pc["P"][ia] - pc["P"][ib]))
    keep = [k for k in range(len(pc["P"])) if k != itp]
    pos = {k: j for j, k in enumerate(keep)}
    new = dict(pc, P=pc["P"][keep], names={k_: pos[v] for k_, v in pc["names"].items() if v in pos})
    imap = {k: [(piece, pos[k])] for k in keep}
    D["seams"] = [s for s in D["seams"] if not (all(isinstance(x, str) for x in s) and
                  {x.split(":", 1)[1] for x in s} == {f"{a_n}>{t_n}", f"{b_n}>{t_n}"})]
    before = {json.dumps(s): s for s in D["seams"]}
    D["pieces"][piece] = new
    _remap(D, piece, old, imap, {piece: new})

    # an edge that skipped the dart now runs straight over it: the gap between the old leg ends joins the chain
    def bridge(chain):
        out = []
        for e in chain:
            if out and out[-1].startswith(piece + ":") and e.startswith(piece + ":"):
                p_end, n_start = out[-1].split(">")[-1], e.split(":", 1)[1].split(">")[0]
                if {p_end, n_start} == {a_n, b_n}:
                    out.append(f"{piece}:{p_end}>{n_start}")
            out.append(e)
        return out
    for k_ in D["edges"]:
        D["edges"][k_] = bridge(D["edges"][k_])
    for s in D["seams"]:
        for j in (0, 1):
            if not isinstance(s[j], str):
                key = json.dumps(s)
                s[j] = bridge(s[j])
                if key in D["notes"]:
                    D["notes"][json.dumps(s)] = D["notes"].pop(key)
    # the seam that ran over the dart now carries its intake as ease
    for s in D["seams"]:
        for side in s:
            fl = _flat(side)
            if any(e.startswith(piece + ":") and (a_n in e.split(":", 1)[1].split(">") or b_n in e.split(":", 1)[1].split(">"))
                   for e in fl):
                la, lb = edge_length(D, s[0]), edge_length(D, s[1])
                e = max(la, lb) / max(min(la, lb), 1e-9) - 1
                D["notes"][json.dumps(s)] = {"ease": [round(e - 0.01, 4), round(e + 0.01, 4)],
                                             "why": f"{dart} of {piece} converted to {o.get('as', 'ease')}: "
                                                    f"{intake * 1000:.0f} mm held into the seam"}
    D["log"].append(f"dart {dart} on {piece} closed into its edge: {intake * 1000:.0f} mm becomes {o.get('as', 'ease')}")


def _true_edge(pc: dict, edge: str, keep: tuple = ()) -> None:
    """True an edge after slashing: its inside vertices are moved onto a smooth curve through them (a pattern maker
    redraws a slashed hem with a curve), its ends stay."""
    ix = pattern.arc_indices(pc, edge)
    if len(ix) < 4:
        return
    L = pc["P"][ix]
    s_ = np.r_[0, np.cumsum(np.linalg.norm(np.diff(L, axis=0), axis=1))]
    t = s_ / s_[-1]
    deg = min(3, len(ix) - 1)
    out = L.copy()
    for c in range(2):
        # a cubic through the ends (least squares inside): no kinks, the ends unmoved
        base = L[0, c] + (L[-1, c] - L[0, c]) * t
        A = np.stack([t * (1 - t), t * (1 - t) * (2 * t - 1)], 1)[:, :deg - 1]
        co, *_ = np.linalg.lstsq(A, L[:, c] - base, rcond=None)
        out[:, c] = base + A @ co
    pc["P"][ix[1:-1]] = out[1:-1]


def op_flare(D: dict, piece: str, amount: float, edge: str, hinge, n: int = 1, **o) -> None:
    """Slash from points along `edge` (e.g. the hem) to the hinge point(s) and spread each by `amount` (m): added
    fullness. Negative closes (tapering). The part holding the centre line stays where it is; the slashed edge is
    trued to a smooth curve afterwards."""
    pc = D["pieces"][piece]
    hinges = hinge if isinstance(hinge, list) else [hinge]
    e_a, e_b = edge.split(">")[0], edge.split(">")[-1]
    L0 = pb.edge_length(pc, edge)
    for k in range(n):
        h = hinges[min(k, len(hinges) - 1)]
        _point(D, pc, h, "_hinge")
        _point(D, pc, {"edge": edge, "t": (k + 1) / (n + 1)}, "_slash")
        a_, b_ = pc["P"][pc["names"]["_hinge"]].copy(), pc["P"][pc["names"]["_slash"]].copy()
        before = pc["P"].copy()
        d_ = b_ - a_
        nrm = np.array([-d_[1], d_[0]])
        left = (before - a_) @ nrm > 1e-9
        centre = np.abs(before[:, 0]) < 1e-6
        if centre.any() and left[centre].mean() > 0.5:  # the centre is on the side that would turn: turn the other
            new = pattern.slash_spread(pc, np.array([b_, a_]), float(amount), "b")
        else:
            new = pattern.slash_spread(pc, np.array([a_, b_]), float(amount), "a")
        i_s = pc["names"]["_slash"]
        moved = np.linalg.norm(new["P"] - before, axis=1) > 1e-12
        pc["P"], pc["marks"], pc["lines"] = new["P"], new["marks"], new["lines"]
        nb_ = [(i_s - 1) % len(before), (i_s + 1) % len(before)]
        turned_nb = [j for j in nb_ if moved[j]]
        if turned_nb and not moved[i_s]:  # the slash point becomes two: the turned side's copy opens the edge
            j = turned_nb[0]
            # the turn that carried the neighbour: the same rigid motion applied to the slash point
            v0, v1 = before[j] - a_, pc["P"][j] - a_
            ang = math.atan2(v1[1], v1[0]) - math.atan2(v0[1], v0[0])
            q = _rot(before[i_s], a_, ang)
            after = i_s if j == (i_s + 1) % len(before) else (i_s - 1) % len(before)
            _insert(pc, after, q)
        for k_ in ("_hinge", "_slash"):
            pc["names"].pop(k_, None)
    if o.get("true", True):
        _true_edge(pc, edge)
    L1 = pb.edge_length(pc, edge)
    D["log"].append(f"flare {piece}: {n} slash(es) from {edge} to {hinges}, {amount * 1000:+.0f} mm each; {edge} "
                    f"{L0 * 1000:.0f} -> {L1 * 1000:.0f} mm (trued to a curve), the hinge edge keeps its length")


def op_lengthen(D: dict, pieces, amount: float, y: float | None = None, **o) -> None:
    """Every vertex below level y (default: just above the lowest edge) moves down by amount (negative: shorten)."""
    for nm in ([pieces] if isinstance(pieces, str) else pieces):
        pc = D["pieces"][nm]
        yy = (pc["P"][:, 1].min() + 1e-4) if y is None else float(y)
        sel = pc["P"][:, 1] <= yy + 1e-9
        pc["P"][sel, 1] -= amount
        for k_, v in pc["marks"].items():
            if v[1] <= yy:
                v[1] -= amount
    D["log"].append(f"lengthen {pieces}: {amount * 1000:+.0f} mm below y {('the hem' if y is None else f'{y * 1000:.0f} mm')}")


def op_extend(D: dict, piece: str, edge: str, amount, name: str = "ext", **o) -> None:
    """Push an edge outward by `amount` (m, or a list of amounts along it): a button stand, a wrap overlap, a vent
    extension. The old edge stays as the line "<name>.line" (the centre front, a fold line); the pushed edge's ends are
    the points "<name>.a" / "<name>.b" (in the edge's own direction)."""
    pc = D["pieces"][piece]
    ix = pattern.arc_indices(pc, edge)
    P = pc["P"]
    L = P[ix].copy()
    t = np.gradient(L, axis=0)
    nrm = np.c_[-t[:, 1], t[:, 0]]
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    if np.mean(np.sum((P.mean(0) - L) * nrm, 1)) > 0:
        nrm = -nrm  # outward
    amt = np.interp(np.linspace(0, 1, len(L)), np.linspace(0, 1, len(amount)), amount) \
        if isinstance(amount, (list, tuple)) else np.full(len(L), float(amount))
    pushed = L + nrm * amt[:, None]
    n = len(P)
    fwd = (ix[0] + 1) % n == ix[1]
    seq = ix if fwd else ix[::-1]
    push_ring = pushed if fwd else pushed[::-1]
    inner = set(seq[1:-1])
    by_idx = {}
    for k_, v in pc["names"].items():
        by_idx.setdefault(v, []).append(k_)
    ring, names = [], {}
    first = last = None
    for k in range(n):
        if k in inner:
            continue
        ring.append(P[k])
        for k_ in by_idx.get(k, []):
            names[k_] = len(ring) - 1
        if k == seq[0]:
            for j, q in enumerate(push_ring):
                ring.append(q)
                if j == 0:
                    first = len(ring) - 1
                if j == len(push_ring) - 1:
                    last = len(ring) - 1
    names[f"{name}.a"], names[f"{name}.b"] = (first, last) if fwd else (last, first)
    pc["P"], pc["names"] = np.asarray(ring), names
    pc["lines"][f"{name}.line"] = L
    D["edges"][name] = [f"{piece}:{name}.a>{name}.b"]
    D["log"].append(f"extend {piece} {edge} by {np.max(amt) * 1000:.0f} mm ({name}): the old edge stays as the line "
                    f"{name}.line")


def op_reshape(D: dict, piece: str, point: str, by, falloff: float = 0.06, **o) -> None:
    pc = D["pieces"][piece]
    new = pattern.move_point(pc, point, by, falloff)
    pc["P"] = new["P"]
    D["log"].append(f"reshape {piece}: {point} moved by {[round(v * 1000) for v in by]} mm (falloff {falloff * 1000:.0f} mm)")


def op_facing(D: dict, piece: str, edges, width: float = 0.06, name: str | None = None, **o) -> None:
    """A facing traced from `piece` along `edges` (a chain of its edges, or a named edge of the draft), `width` deep:
    its outer edge is the same line (sewn 1:1), turned under."""
    name = name or f"{piece}_facing"
    chain = []
    for e_ in ([edges] if isinstance(edges, str) else list(edges)):  # named edges of the draft, or edge specs
        chain += list(D["edges"][e_]) if e_ in D["edges"] else [e_]
    chain = [e if ":" in e else f"{piece}:{e}" for e in chain]
    chain = [e for e in chain if e.split(":")[0] == piece]
    if not chain:
        raise DraftError(f"facing: no edge of {piece} in {edges}")
    pc = D["pieces"][piece]
    segs = [pc["P"][pattern.arc_indices(pc, e.split(":", 1)[1])] for e in chain]
    # in a row, end to start (each next edge turned to continue the line)
    for k in range(1, len(segs)):
        if k == 1 and min(np.linalg.norm(segs[0][0] - segs[1][0]), np.linalg.norm(segs[0][0] - segs[1][-1])) < \
                min(np.linalg.norm(segs[0][-1] - segs[1][0]), np.linalg.norm(segs[0][-1] - segs[1][-1])):
            segs[0] = segs[0][::-1]
            chain[0] = _rev(chain[0])
        if np.linalg.norm(segs[k][-1] - segs[k - 1][-1]) < np.linalg.norm(segs[k][0] - segs[k - 1][-1]):
            segs[k] = segs[k][::-1]
            chain[k] = _rev(chain[k])
    L = np.concatenate(segs)
    keep = np.r_[True, np.linalg.norm(np.diff(L, axis=0), axis=1) > 1e-7]
    L = L[keep]
    if len(L) < 5:  # a straight edge: a few points along it (the facing needs a middle point to be addressed by)
        cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(L, axis=0), axis=1))]
        s_ = np.unique(np.r_[cum, np.linspace(0, cum[-1], 5)])
        L = np.c_[np.interp(s_, cum, L[:, 0]), np.interp(s_, cum, L[:, 1])]
    # the facing is the part of the piece within `width` of the edge: past the edge's two ends it follows the
    # piece's own outline until that is `width` away, and its inner edge is the line `width` from the edge (round
    # the ends too). A plain offset of the edge alone made beaks at corners and a square end across the piece.
    from .cloth import _inside, _seg_dist
    P = pc["P"]
    n_ = len(P)

    def nearest(q):
        return int(np.argmin(np.linalg.norm(P - q, axis=1)))

    ia, ib = nearest(L[0]), nearest(L[-1])
    on = set(int(np.argmin(np.linalg.norm(P - q, axis=1))) for q in L)

    def run_on(i0):  # along the outline away from the edge until `width` from it
        step = 1 if (i0 + 1) % n_ not in on else -1
        out, prev, dprev = [], P[i0], 0.0
        for k in range(1, n_):
            q = P[(i0 + step * k) % n_]
            if (i0 + step * k) % n_ in on:
                break
            sub = np.linspace(0, 1, max(2, int(np.linalg.norm(q - prev) / 0.004) + 1))[1:]
            for u_ in sub:
                x = prev + (q - prev) * u_
                d = float(_seg_dist(x[None], L, closed=False)[0])
                if d >= width:
                    w_ = (width - dprev) / max(d - dprev, 1e-9)
                    out.append(out[-1] + (x - out[-1]) * w_ if out else x)
                    return out
                out.append(x)
                dprev = d
            prev = q
        return out

    tail_b, tail_a = run_on(ib), run_on(ia)
    t = np.gradient(L, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    nrm = np.c_[-t[:, 1], t[:, 0]]
    if np.mean(np.sum((P.mean(0) - L) * nrm, 1)) < 0:
        nrm = -nrm
    arc = np.linspace(0, math.pi / 2, 9)[:-1]
    cap_b = [L[-1] + width * (math.cos(a_) * t[-1] + math.sin(a_) * nrm[-1]) for a_ in arc]
    cap_a = [L[0] + width * (-math.cos(a_) * t[0] + math.sin(a_) * nrm[0]) for a_ in arc[::-1]]
    inner = np.array(cap_b + list((L + nrm * width)[::-1]) + cap_a)
    ok = (_seg_dist(inner, L, closed=False) > width * 0.98) & _inside(P, inner)
    inner = inner[ok]
    for _ in range(4):  # the joins of the offset line and the round ends: eased (a pattern maker draws one curve)
        if len(inner) > 4:
            inner[1:-1] = 0.25 * inner[:-2] + 0.5 * inner[1:-1] + 0.25 * inner[2:]
    # thin the tails' points that sit on the piece's straight runs; keep corners
    ring = [q for q in tail_b] + [q for q in inner] + [q for q in tail_a[::-1]]
    keep_r = [ring[0]] if ring else []
    for q in ring[1:]:
        if np.linalg.norm(q - keep_r[-1]) > 0.002:
            keep_r.append(q)
    while keep_r and np.linalg.norm(keep_r[-1] - L[0]) < 0.002:
        keep_r.pop()
    pts = [("edge.a", L[0])] + [(None, q) for q in L[1:-1]] + [("edge.b", L[-1])] + [(None, q) for q in keep_r]
    mid = len(L) // 2
    pts[mid] = ("edge.m", L[mid])
    fpc = pb.make_piece(name, pts, "facing", dict(pc.get("wrap") or {}), pc.get("sym", "pair"))
    fpc["wrap"]["out"] = -0.003  # inside the piece it faces
    fpc["wrap"]["lies_on"] = piece  # placed as that piece's own surface, a layer inside it (cloth.place)
    fpc["traced"] = piece
    # a facing is FUSED to its piece: one cloth for the sim (cloth.pieces sets it aside as Bp["fused"]). As a
    # separate interfaced piece it was held as made: a rigid plank 16-64 mm off its front, its seams never closed
    # ("separate": true keeps it a piece of its own)
    if not o.get("separate"):
        fpc["wrap"]["fused"] = piece
    D["pieces"][name] = fpc
    seam = [f"{name}:edge.a>edge.m>edge.b", chain[0] if len(chain) == 1 else chain]
    D["seams"].append(seam)
    D["notes"][json.dumps(seam)] = {"ease": [-0.004, 0.004], "turned": "under",
                                    "why": f"{name} is sewn to the edge it was traced from and turned in"}
    D["interfaced"].append(name)
    D["log"].append(f"facing {name}: traced from {piece} along {len(chain)} edge(s), {pattern.length(L) * 1000:.0f} mm "
                    f"long, {width * 1000:.0f} mm deep; sewn 1:1 and turned in")


def op_collar(D: dict, type: str = "band", height: float = 0.035, name: str = "collar", **o) -> None:
    """A collar drafted from the neckline as it is now (edges neck_back + neck_front), as a half cut on the fold at
    centre back. "band": a stand: a strip the neckline's length, its sewn edge slightly convex (it then leans in to
    the neck); "flat": the sewn edge is the neckline's own curve (shoulder seams laid together): it lies flat on
    the shoulders with no stand; "roll": between the two (`stand` 0..1: 1 = band, 0 = flat).
    "tailored": a jacket's collar in one piece, stand + fall with a roll line between: `stand_height` (0.03) up the
    neck, `fall` (0.045) back down over it, ending at the lapel's gorge (`stop`). Its back part is an annular sector
    (the shawl collar's lesson: a strip run straight can't turn down round a neck): the outer edge is longer than
    the neck edge by `spring` (default (fall - stand_height + 8 mm) x pi / 2: what the fall's edge needs to lie on
    the shoulders a fall's overhang outside the neck seam); the front part runs on straight to the gorge.
    `point` (0.0) moves the end's outer corner along the collar (the notch's shape). Points cbNeck, cbRoll,
    cbOuter, endNeck, endRoll, endOuter; a roll fold `stand_height` from the neck edge."""
    nb, nf = D["edges"].get("neck_back"), D["edges"].get("neck_front")
    if not nb or not nf:
        raise DraftError("collar: the draft has no neckline edges (neck_back / neck_front)")
    lb, lf = edge_length(D, nb), edge_length(D, nf)
    ext = float(o.get("extend", 0.0))  # past centre front (onto a button stand)
    stop = float(o.get("stop", 0.0))  # the collar ends this far short of the neckline's front end (the gorge notch)
    if stop > 0:
        if len(nf) != 1:
            raise DraftError("collar stop: the front neckline is cut by a style line; stop it at that line instead")
        fpn, farc = nf[0].split(":", 1)
        fpc = D["pieces"][fpn]
        _point(D, fpc, {"edge": farc, "dist": max(lf - stop, 0.01)}, "gorgeNotch")
        nf = [f"{fpn}:{farc.split('>')[0]}>gorgeNotch"]
        lf = edge_length(D, nf)
    ratio = float(o.get("ratio", 1.0))  # a rib band is cut shorter than the neckline and stretched on (0.85)
    Ln = (lb + lf + ext) * ratio
    stand = {"band": 1.0, "flat": 0.0, "roll": 0.5}.get(type, 1.0) if "stand" not in o else float(o["stand"])
    # the neckline's own curve: back neck from cb to hps, then the front (turned to continue it) from hps to cf
    Pb = np.concatenate(edge_points(D, nb))
    Pf = np.concatenate(edge_points(D, nf))
    if np.linalg.norm(Pb[0] - Pb[-1]) > 0 and abs(Pb[0][0]) > abs(Pb[-1][0]):
        Pb = Pb[::-1]  # from the centre back out to the hps
    if np.linalg.norm(Pf[0] - Pb[-1]) > np.linalg.norm(Pf[-1] - Pb[-1]):
        Pf = Pf[::-1]  # from the hps to the centre front
    # lay the front against the back at the shoulder: mirror the front about the shoulder line is the true method;
    # here the front's curve simply continues from the hps turned 180 deg about it (shoulder seams together)
    hps = Pb[-1]
    Pf2 = hps - (Pf - Pf[0]) * np.array([1, 1])
    Pf2 = hps + (Pf - Pf[0]) * np.array([1.0, -1.0])  # the front neck swings up past the shoulder line
    flat_curve = np.r_[Pb, Pf2[1:]]
    seg = np.linalg.norm(np.diff(flat_curve, axis=0), axis=1)
    s = np.r_[0, np.cumsum(seg)]
    # turning angle along the flat curve; the collar's sewn edge keeps (1 - stand) of it, minus a little rise for a band
    ang = np.unwrap(np.arctan2(np.gradient(flat_curve[:, 1]), np.gradient(flat_curve[:, 0])))
    n = 40
    si = np.linspace(0, s[-1], n)
    a_i = np.interp(si, s, ang - ang[0]) * (1 - stand) + (-0.12 * stand) * (si / s[-1]) ** 2
    tailored = type == "tailored"
    if tailored:
        sh_, fl_ = float(o.get("stand_height", 0.03)), float(o.get("fall", 0.045))
        stand = 0.5  # (its role: a collar that turns)
        height = sh_ + fl_
        spring = float(o.get("spring", (fl_ - sh_ + 0.008) * math.pi / 2))
        R0 = lb * height / max(spring, 1e-4)
        a_i = np.minimum(si * ratio, lb) / R0  # turns (outer edge on the outside) over the back neck, then straight
    ds = (Ln) / (n - 1)
    edge = [np.zeros(2)]
    for k in range(1, n):
        edge.append(edge[-1] + ds * np.array([math.cos(a_i[k - 1]), math.sin(a_i[k - 1])]))
    edge = np.asarray(edge)
    t = np.gradient(edge, axis=0)
    nrm = np.c_[-t[:, 1], t[:, 0]]
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    hgt = np.interp(si / s[-1], [0, 1], [height, float(o.get("height_front", height))])
    # the collar's body lies AWAY from the neck hole (the hole is on the left of cb -> hps -> cf): a flat collar's
    # outer edge is then longer than its neck edge, a band's top edge a little shorter (it leans in to the neck)
    outer = edge - nrm * hgt[:, None]
    if tailored and o.get("point"):
        outer[-1] = outer[-1] + t[-1] / np.linalg.norm(t[-1]) * float(o["point"])
    k_sh = int(np.argmin(np.abs(si - lb)))
    k_cf = int(np.argmin(np.abs(si - (lb + lf))))
    pts = [("cb", edge[0])] + [(("shoulderNotch" if k == k_sh else "cf" if (k == k_cf and ext > 0) else None), edge[k])
                               for k in range(1, n - 1)] + [("front" if ext > 0 else "cf", edge[-1])]
    if tailored:  # the roll line's ends are outline points (the end edge, the centre back fold)
        pts += [("endRoll", edge[-1] + (outer[-1] - edge[-1]) * (sh_ / height))]
    pts += [("frontTop", outer[-1])] + [(None, q) for q in outer[-2:0:-1]] + [("cbTop", outer[0])]
    if tailored:
        pts += [("cbRoll", edge[0] + (outer[0] - edge[0]) * (sh_ / height))]
    # the half must have its centre back on x = 0: turn it so cb -> cbTop is the y axis
    role = o.get("role") or ("collar_stand" if stand >= 0.75 else "collar_fall")
    pc = pb.make_piece(name, pts, role, {"to": "neck", "edge": "cb"}, "fold")
    v = pc["P"][pc["names"]["cbTop"]] - pc["P"][pc["names"]["cb"]]
    pc["P"] = _rot(pc["P"], pc["P"][pc["names"]["cb"]], math.pi / 2 - math.atan2(v[1], v[0]))
    pc["P"] -= pc["P"][pc["names"]["cb"]]
    if pc["P"][:, 0].mean() < 0:
        pc["P"][:, 0] *= -1
        pc["P"] = pc["P"][::-1]
        m = len(pc["P"]) - 1
        pc["names"] = {k_: m - i for k_, i in pc["names"].items()}
    if tailored:
        for alias, src in (("cbNeck", "cb"), ("cbOuter", "cbTop"), ("endNeck", "cf"), ("endOuter", "frontTop")):
            pc["names"][alias] = pc["names"][src]
        D["edges"][f"{name}_neck"] = [f"{name}:cb>shoulderNotch>cf"]
        D["edges"][f"{name}_outer"] = [f"{name}:frontTop>cbTop"]
        D["edges"][f"{name}_end"] = [f"{name}:cf>endRoll>frontTop"]
    D["pieces"][name] = pc
    D["centre"][name] = "fold"
    seam_edge = f"{name}:cb>shoulderNotch>{'cf' if True else 'front'}" if ext == 0 else f"{name}:cb>shoulderNotch>cf"
    D["seams"].append([seam_edge, list(nb) + list(nf)])
    if abs(ratio - 1) > 1e-6:
        D["notes"][json.dumps(D["seams"][-1])] = {
            "ease": [ratio - 1 - 0.01, ratio - 1 + 0.01],
            "why": f"{name} is cut {ratio:.2f} x the neckline and stretched on (a rib band hugs the neck)"}
    D["interfaced"].append(name)
    if tailored:
        D["folds"].append({"piece": name, "line": {"edge": seam_edge, "offset": sh_}, "angle": 15,
                           "kind": "roll", "radius": 0.004, "name": f"{name} roll"})
        D["log"].append(f"collar {name} (tailored): stand {sh_ * 1000:.0f} + fall {fl_ * 1000:.0f} mm, spring "
                        f"{spring * 1000:.0f} mm: outer edge {edge_length(D, D['edges'][name + '_outer']) * 1000:.0f} mm for a "
                        f"neck edge of {edge_length(D, seam_edge) * 1000:.0f} (half)")
    elif stand < 0.75 and not tailored:
        D["folds"].append({"piece": name, "line": {"edge": seam_edge, "offset": 0.004 + 0.02 * stand}, "angle": 15,
                           "kind": "roll", "radius": 0.003, "name": f"{name} roll"})
    D["log"].append(f"collar {name} ({type}, stand {stand:.2f}): sewn edge {edge_length(D, seam_edge) * 1000:.0f} mm for a "
                    f"neckline of back {lb * 1000:.0f} + front {lf * 1000:.0f} mm, {height * 1000:.0f} mm high; "
                    f"{'stands' if stand >= 0.75 else 'rolls' if stand > 0.2 else 'lies flat'}")


def op_sleeve(D: dict, **o) -> None:
    """Draft the sleeve into the armhole as it is now."""
    af, ab = edge_length(D, D["edges"]["armhole_front"]), edge_length(D, D["edges"]["armhole_back"])
    opts = dict({"biceps_ease": D["meta"].get("biceps_ease", 0.15)}, **o)
    if D["meta"].get("knit"):
        opts.setdefault("cap_ease", 0.0)
    mate = list(D["edges"]["armhole_front"]) + [_rev(e) for e in reversed(D["edges"]["armhole_back"])]
    S = pb.sleeve(D["meta"]["measurements"], {"meta": D["meta"]}, opts, armhole=(af, ab), mate=mate)
    D["pieces"].update(S["pieces"])
    D["seams"] += S["seams"]
    D["meta"]["sleeve"] = S["meta"]
    D["edges"]["sleeve_hem"] = ["sleeve:wristB>wristF"]
    D["edges"]["cap"] = ["sleeve:underarmF>capTop>underarmB"]
    D["log"] += S["log"]
    e = S["meta"]["cap_ease"]
    D["notes"][json.dumps(S["seams"][0])] = {"ease": [e - 0.012, e + 0.012], "why": f"sleeve cap ease {e * 100:.1f}% (designed)"}


def _rev(spec: str) -> str:
    nm, arc = spec.split(":", 1)
    return nm + ":" + ">".join(reversed(arc.split(">")))


def op_two_piece(D: dict, shift: float = 0.02, **o) -> None:
    """A two-piece sleeve from the one-piece: the sleeve is folded edge to centre (the fold lines a quarter in from
    each side), the folds become seams moved `shift` under the arm so they are hidden: a top sleeve (the middle) and
    an under sleeve (the two outer strips joined along the old underarm seam; its top edge is the hollow of the two
    underarm curves). "shift_back": the hindarm seam's own shift (default 0.25 x shift: it runs over the elbow, near the back pitch).
    Then the sleeve is BENT as a tailor cuts it: below the elbow line each piece swings toward its forearm seam by
    "elbow" (m the wrist comes forward; 0 = straight), about the forearm seam's elbow point: the forearm seams stay
    equal and hollow, the hindarm seams open over the elbow, the top sleeve's a little more than the under's (elbow
    ease, declared), the hem ends up square to the forearm."""
    if "sleeve" not in D["pieces"]:
        raise DraftError("two_piece: draft the sleeve first")
    pc = D["pieces"]["sleeve"]
    old = copy.deepcopy(pc)
    W = D["meta"]["sleeve"]["width"]
    hw = D["meta"]["sleeve"]["hem_width"]
    lo = pc["P"][:, 1].min()
    # the seam lines: a quarter in from each side at the biceps and at the hem (they follow the taper), `shift` under
    lf = (np.array([W / 4 + shift, 0.0]), np.array([hw / 4 + shift, lo]))
    sb_ = float(o.get("shift_back", 0.25 * shift))  # (the hindarm seam sits near the back pitch: high on the cap)
    lb = (np.array([-(W / 4 + sb_), 0.0]), np.array([-(hw / 4 + sb_), lo]))
    work = copy.deepcopy(pc)
    # cut points on the cap and on the hem at the two seam lines

    def at_line(edge, ln, name):
        p1, p2 = ln
        d = p2 - p1
        nrm = np.array([-d[1], d[0]])
        ix = pattern.arc_indices(work, edge)
        L = work["P"][ix]
        sd = (L - p1) @ nrm
        for k in range(len(L) - 1):
            if sd[k] * sd[k + 1] <= 0 and sd[k] != sd[k + 1]:
                q = L[k] + (L[k + 1] - L[k]) * sd[k] / (sd[k] - sd[k + 1])
                a_, b_ = ix[k], ix[k + 1]
                n_ = len(work["P"])
                return _insert(work, a_ if (a_ + 1) % n_ == b_ else b_, q, name)
        raise DraftError(f"two_piece: a seam line misses {edge}")
    at_line("capTop>underarmF", lf, "tsF")
    at_line("capTop>underarmB", lb, "tsB")
    at_line("wristF>wristB", lf, "tsHemF")
    at_line("wristF>wristB", lb, "tsHemB")
    n = len(work["P"])
    i = {k: work["names"][k] for k in ("tsF", "tsB", "tsHemF", "tsHemB", "underarmF", "underarmB", "wristF", "wristB", "capTop")}
    step = 1 if pattern.arc_indices(work, "underarmB>capTop")[1] == (i["underarmB"] + 1) % n else -1

    def walk(a, b):
        out, k = [a], a
        while k != b:
            k = (k + step) % n
            out.append(k)
        return out
    top_cap = walk(i["tsB"], i["tsF"])  # over the cap's top
    top = top_cap + walk(i["tsHemF"], i["tsHemB"])  # down the front seam line, along the hem, up the back
    front_strip = walk(i["tsF"], i["tsHemF"])  # tsF .. underarmF .. wristF .. tsHemF
    back_strip = walk(i["tsHemB"], i["tsB"])  # tsHemB .. wristB .. underarmB .. tsB
    def mir(P, ln):
        p1, p2 = ln
        d = (p2 - p1) / np.linalg.norm(p2 - p1)
        v = P - p1
        return p1 + 2 * np.outer(v @ d, d) - v
    Fm = mir(work["P"][front_strip], lf)  # folded in about the front seam line
    Bm = mir(work["P"][back_strip], lb)
    # the two folded strips meet along the old underarm seam: slide each sideways so their underarm edges coincide
    # at every height (the seam is closed: its two edges are the same length by the block)
    def edge_x(P, idx_a, idx_b, y):
        seg = P[idx_a:idx_b + 1]
        o_ = np.argsort(seg[:, 1])
        return np.interp(y, seg[o_, 1], seg[o_, 0])
    fa, fb = front_strip.index(i["underarmF"]), front_strip.index(i["wristF"])
    ba, bb = back_strip.index(i["wristB"]), back_strip.index(i["underarmB"])
    ys = np.linspace(lo, 0, 12)
    gap = np.array([edge_x(Fm, fa, fb, y) - edge_x(Bm, ba, bb, y) for y in ys])  # front's edge minus the back's
    # under sleeve outline: the back strip's seam line (x = xs_b), its cap part, [the underarm seam vanishes], the
    # front strip's cap part and seam line. Each strip is shifted by half the gap at its height (a shear in x)
    sh = lambda P, sgn: np.c_[P[:, 0] + sgn * 0.5 * np.interp(P[:, 1], ys, gap), P[:, 1]]
    Fs, Bs = sh(Fm, -1.0), sh(Bm, +1.0)
    # walking order of the under sleeve (anticlockwise not required): front seam line top -> front cap part ->
    # underarm (merged) -> back cap part -> back seam top -> down the back seam line -> hem -> up the front seam
    f_cap = Fs[:fa + 1]  # tsF .. underarmF
    b_cap = Bs[bb:]  # underarmB .. tsB
    f_hem = Fs[fb:]  # wristF .. tsHemF
    b_hem = Bs[:ba + 1]  # tsHemB .. wristB
    under_pts = [("usF", f_cap[0])] + [(None, q) for q in f_cap[1:-1]] + [("underarm", 0.5 * (f_cap[-1] + b_cap[0]))]
    under_pts += [(None, q) for q in b_cap[1:-1]] + [("usB", b_cap[-1]), ("usHemB", b_hem[0])]
    under_pts += [("usHemMid", 0.5 * (b_hem[0] + f_hem[-1])), ("usHemF", f_hem[-1])]  # the under hem: one straight line
    under = pb.make_piece("under", under_pts, "sleeve", {"to": "arm.L", "front": 1, "turn": 180,
                                                         "align": ["usF", "top", "tsF"]}, "copy")
    # the strips were folded in: the piece as built is seen from its wrong side. Turned over (mirrored), so its
    # pattern face is its outside like every other piece, and laid under the arm its forearm edge meets the top's
    # (unmirrored it went round the arm the other way: both sleeve seams started ~15 cm apart and the sewing
    # twisted the sleeve into a knot at the shoulder)
    under["P"] = (under["P"] * [-1.0, 1.0])[::-1]
    under["names"] = {k_: len(under["P"]) - 1 - i_ for k_, i_ in under["names"].items()}
    tpts = [(("tsB" if k == i["tsB"] else "tsF" if k == i["tsF"] else "tsHemF" if k == i["tsHemF"] else
              "tsHemB" if k == i["tsHemB"] else "capTop" if k == i["capTop"] else None), work["P"][k]) for k in top]
    topp = pb.make_piece("top", tpts, "sleeve", {"to": "arm.L", "front": 1}, "copy",
                         lines={k_: v for k_, v in work["lines"].items()})
    # the elbow: a tailored sleeve follows the arm's bend. Both pieces are sheared alike about the elbow line (the
    # forearm seam hollows, the hindarm seam bows out over the elbow point), so the mating seams stay the same curves;
    # and the under sleeve's hindarm is hollowed a little more than the top's bows (the cloth cups over the elbow)
    elbow = float(o.get("elbow", 0.035))
    ey = float(np.mean(pc["lines"]["elbow"][:, 1])) if "elbow" in (pc.get("lines") or {}) else 0.45 * lo
    theta = elbow / max(ey - lo, 1e-6)
    if elbow > 0:
        for pcx, edge, sgn in ((topp, "tsF>tsHemF", 1.0), (under, "usF>usHemF", -1.0)):
            for yy in np.linspace(ey + 0.07, ey - 0.07, 9):  # both seam edges need points to carry the curve
                try:
                    _point(D, pcx, {"edge": edge, "y": float(yy)})
                except DraftError:
                    pass
            ix = pattern.arc_indices(pcx, edge)
            E = pcx["P"][ix]
            o_ = np.argsort(E[:, 1])
            piv = np.array([float(np.interp(ey, E[o_, 1], E[o_, 0])), ey])
            other = "tsB>tsHemB" if pcx is topp else "usB>usHemB"
            for yy in np.linspace(ey + 0.07, ey - 0.07, 9):
                try:
                    _point(D, pcx, {"edge": other, "y": float(yy)})
                except DraftError:
                    pass
            bd = {"pivot": piv.round(5).tolist(), "angle": round(sgn * theta, 5), "y": round(ey, 5), "band": 0.05}
            pcx["P"] = pattern.bend(pcx["P"], **bd)
            for k_ in list(pcx["lines"]):
                pcx["lines"][k_] = pattern.bend(np.asarray(pcx["lines"][k_], float), **bd)
            pcx["wrap"]["bend"] = bd  # (cloth.place lays the straight sleeve: the bend is undone for the start)
    del D["pieces"]["sleeve"]
    D["pieces"]["top"], D["pieces"]["under"] = topp, under
    # seams: the cap (top's part + the under's two parts) into the armhole; the two sleeve seams
    cap_seam = next(s for s in D["seams"] if any(e.startswith("sleeve:underarmF") for e in _flat(s[0])))
    note = D["notes"].pop(json.dumps(cap_seam), None)
    D["seams"] = [s for s in D["seams"] if not any(e.startswith("sleeve:") for side in s for e in _flat(side))]
    new_cap = [["under:underarm>usF", "top:tsF>capTop>tsB", "under:usB>underarm"], cap_seam[1]]
    D["seams"] += [new_cap, ["top:tsF>tsHemF", "under:usF>usHemF"], ["top:tsB>tsHemB", "under:usB>usHemB"]]
    if note:
        D["notes"][json.dumps(new_cap)] = note
    if elbow > 0:
        hb = (edge_length(D, "top:tsB>tsHemB"), edge_length(D, "under:usB>usHemB"))
        e_ = hb[0] / hb[1] - 1
        D["notes"][json.dumps(D["seams"][-1])] = {
            "ease": [round(e_ - 0.004, 4), round(e_ + 0.004, 4)],
            "why": f"elbow ease: the top sleeve's hindarm is {(hb[0] - hb[1]) * 1000:.0f} mm longer, eased in over the elbow"}
        fa = (edge_length(D, "top:tsF>tsHemF"), edge_length(D, "under:usF>usHemF"))
        if abs(fa[0] - fa[1]) > 0.001:
            D["notes"][json.dumps(D["seams"][-2])] = {
                "ease": [round(fa[0] / fa[1] - 1 - 0.003, 4), round(fa[0] / fa[1] - 1 + 0.003, 4)],
                "why": "the forearm seams bent about their own elbow points"}
    D["edges"]["sleeve_hem"] = ["top:tsHemB>tsHemF", "under:usHemF>usHemMid>usHemB"]
    D["meta"]["sleeve"]["two_piece"] = True
    D["edges"]["cap"] = new_cap[0]
    lf = (edge_length(D, "top:tsF>tsHemF"), edge_length(D, "under:usF>usHemF"))
    lb = (edge_length(D, "top:tsB>tsHemB"), edge_length(D, "under:usB>usHemB"))
    D["log"].append(f"two-piece sleeve: seams {shift * 1000:.0f} mm under the quarter lines; front seam top/under "
                    f"{lf[0] * 1000:.0f}/{lf[1] * 1000:.0f} mm, back {lb[0] * 1000:.0f}/{lb[1] * 1000:.0f} mm; bent "
                    f"{math.degrees(theta):.1f} deg at the elbow (the wrist {elbow * 1000:.0f} mm forward: forearm seam "
                    "hollowed, hindarm seam opened over the elbow, the top's more: elbow ease)")


def op_waistband(D: dict, height: float = 0.04, overlap: float = 0.035, ratio: float = 1.0, **o) -> None:
    """A straight waistband generated from the waist edges as they are at the end (after darts, pleats, yokes): a
    strip their length x ratio (+ the overlap, buttoned at the centre back), sewn round the waist in order, held at
    the body's waist. ratio < 1: cut shorter and the waist eased onto it (an elasticated or gathered waist)."""
    if "waist_front" not in D["edges"]:
        raise DraftError("waistband: needs a block with waist edges (trouser, skirt)")
    D["waistband"] = dict(o, height=height, overlap=overlap, ratio=ratio)
    D["log"].append(f"waistband: {height * 1000:.0f} mm high, {overlap * 1000:.0f} mm overlap, x{ratio:.2f} the waist edge "
                    "(generated at unfold from the waist edges as they are then)")


OPS = {"waistband": op_waistband, "style_line": op_style_line, "take_in": op_take_in, "dart": op_dart, "dart_to_ease": op_dart_to_ease,
       "flare": op_flare, "lengthen": op_lengthen, "extend": op_extend, "reshape": op_reshape, "facing": op_facing,
       "collar": op_collar, "sleeve": op_sleeve, "two_piece": op_two_piece}


# ---------------------------------------------------------------- the draft


def start(block: str, meas_mm: dict, opts: dict | None = None) -> dict:
    if block in ("bodice", "knit"):
        B = pb.bodice(meas_mm, opts, knit=block == "knit")
        low = B["meta"]["low"]
        edges = {"armhole_front": ["front:armhole>armholePitch>shoulder"],
                 "armhole_back": ["back:armhole>armholePitch>shoulder"],
                 "neck_front": ["front:hps>cfNeck"], "neck_back": ["back:cbNeck>hps"],
                 "shoulder_front": ["front:hps>shoulder"], "shoulder_back": ["back:hps>shoulder"],
                 "centre_front": [f"front:cfNeck>{'cfHem' if low == 'hem' else 'cfWaist'}"],
                 "centre_back": [f"back:cbNeck>{'cbHem' if low == 'hem' else 'cbWaist'}"],
                 "hem_front": [f"front:{low}>{'cfHem' if low == 'hem' else 'cfWaist'}"],
                 "hem_back": [f"back:{low}>{'cbHem' if low == 'hem' else 'cbWaist'}"]}
        if "waistDartA" in B["pieces"]["front"]["names"]:  # the waist edge skips its dart
            edges["hem_front"] = ["front:waist>waistDartB", "front:waistDartA>cfWaist"]
            edges["hem_back"] = ["back:waist>waistDartB", "back:waistDartA>cbWaist"]
    elif block == "trouser":
        B = pb.trouser(meas_mm, opts)
        edges = {"waist_front": ["front:cWaist>sideWaist"], "hem_front": ["front:sideHem>inHem"],
                 "hem_back": ["back:sideHem>inHem"], "centre_front": ["front:cWaist>cSeat>fork"],
                 "centre_back": ["back:cWaist>cSeat>fork"],
                 "waist_back": ["back:cWaist>dartA", "back:dartB>sideWaist"] if "dartA" in B["pieces"]["back"]["names"]
                 else ["back:cWaist>sideWaist"]}
    elif block == "skirt":
        B = pb.skirt(meas_mm, opts)
        dart = "dartA" in B["pieces"]["front"]["names"]
        edges = {"hem_front": ["front:hem>cHem"], "hem_back": ["back:hem>cHem"],
                 "centre_front": ["front:cWaist>cHem"], "centre_back": ["back:cWaist>cHem"],
                 "side_front": ["front:sideWaist>sideSeat>hem"], "side_back": ["back:sideWaist>sideSeat>hem"],
                 "waist_front": ["front:cWaist>dartA", "front:dartB>sideWaist"] if dart else ["front:cWaist>sideWaist"],
                 "waist_back": ["back:cWaist>dartA", "back:dartB>sideWaist"] if dart else ["back:cWaist>sideWaist"]}
    else:
        raise DraftError(f"no block {block!r} (have bodice, knit, trouser, skirt)")
    D = {"pieces": B["pieces"], "seams": B["seams"], "edges": edges, "centre": dict(B["centre"]), "meta": B["meta"],
         "log": [f"block {block}:"] + ["  " + x for x in B["log"]], "notes": dict(B.get("notes") or {}), "folds": [],
         "interfaced": [],
         "stitches": [], "generate": [], "lines": {}, "block": block}
    D["meta"]["measurements"] = dict(meas_mm)
    if block in ("bodice", "knit") and D["meta"].get("waist_dart", 0) > 0 and D["meta"]["low"] == "hem":
        # a fitted block past the waist: its waist darts are fish-eye darts (at the waist edge of a block that ends
        # there they are ordinary darts)
        for which in ("front", "back"):
            OPS["fisheye"](D, which)
    return D


def apply(D: dict, ops: list) -> dict:
    for k, op in enumerate(ops or []):
        o = dict(op)
        kind = o.pop("op")
        if kind == "unfold":
            unfold(D)
            continue
        if kind not in OPS:
            raise DraftError(f"op {k + 1}: unknown operation {kind!r} (have {', '.join(OPS)}, unfold)")
        try:
            OPS[kind](D, **o)
        except (KeyError, TypeError) as e:
            raise DraftError(f"op {k + 1} ({kind}): {type(e).__name__}: {e}")
    return D


def consistency(D: dict, tol: float = 0.004) -> list:
    """[(ok, text)] per seam: the two sides' lengths agree (within tol as a fraction, or 1 mm), or the seam's
    declared ease says why not."""
    out = []
    for s in D["seams"]:
        la, lb = edge_length(D, s[0]), edge_length(D, s[1])
        e = la / max(lb, 1e-9) - 1
        note = D["notes"].get(json.dumps(s))
        nm = lambda x: x if isinstance(x, str) else " + ".join(x)
        if note:
            ok = note["ease"][0] - 1e-6 <= abs(e) <= note["ease"][1] + 1e-6 or note["ease"][0] - 1e-6 <= e <= note["ease"][1] + 1e-6
            out.append((ok, f"{la * 1000:.1f} vs {lb * 1000:.1f} mm ({e * 100:+.1f}%, declared: {note['why']}): {nm(s[0])} || {nm(s[1])}"))
        else:
            ok = abs(e) <= tol or abs(la - lb) <= 0.001
            out.append((ok, f"{la * 1000:.1f} vs {lb * 1000:.1f} mm ({e * 100:+.2f}%): {nm(s[0])} || {nm(s[1])}"))
    return out


# ---------------------------------------------------------------- hinges (one cloth, two placements)


def _rename_piece(D: dict, old: str, new: str) -> None:
    """A piece renamed everywhere the draft names it."""
    if old == new:
        return
    ren = lambda e: new + e[len(old):] if isinstance(e, str) and e.startswith(old + ":") else e
    side = lambda s: ren(s) if isinstance(s, str) else [ren(e) for e in s]
    D["pieces"] = {(new if k == old else k): v for k, v in D["pieces"].items()}
    D["pieces"][new]["name"] = new
    seams, notes = [], {}
    for s in D["seams"]:
        ns = [side(s[0]), side(s[1])]
        if json.dumps(s) in D["notes"]:
            notes[json.dumps(ns)] = D["notes"][json.dumps(s)]
        seams.append(ns)
    D["seams"], D["notes"] = seams, notes
    D["edges"] = {k: [ren(e) for e in v] for k, v in D["edges"].items()}
    D["lines"] = {k: tuple(ren(e) for e in v) for k, v in D["lines"].items()}
    for key in ("pair_seams", "pair_stitches"):
        if key in D:
            D[key] = [ren(e) for e in D[key]]
    D["stitches"] = [[ren(a), ren(b)] for a, b in D["stitches"]]
    D["interfaced"] = [new if e == old else e for e in D["interfaced"]]
    if old in D["centre"]:
        D["centre"][new] = D["centre"].pop(old)
    for f in D["folds"]:
        if f.get("piece") == old:
            f["piece"] = new
    for pc in D["pieces"].values():
        w = pc.get("wrap") or {}
        if w.get("lies_on") == old:
            w["lies_on"] = new
        if pc.get("traced") == old:
            pc["traced"] = new


def _line_hits(pc: dict, a: np.ndarray, d: np.ndarray) -> list:
    """Where the line a + t d crosses the outline: [(t, outline index before it, point or None when it is that
    vertex)] by t."""
    P = pc["P"]
    n = len(P)
    sd = (P - a) @ np.array([-d[1], d[0]])
    out = []
    for i in range(n):
        j = (i + 1) % n
        if abs(sd[i]) < 1e-9:
            out.append((float((P[i] - a) @ d), i, None))
        elif sd[i] * sd[j] < 0 and abs(sd[j]) >= 1e-9:
            q = P[i] + (P[j] - P[i]) * sd[i] / (sd[i] - sd[j])
            out.append((float((q - a) @ d), i, q))
    return sorted(out, key=lambda h: h[0])


def _split_fold(f: dict, a: np.ndarray, u: np.ndarray):
    """A fold whose line is a list of points, cut where it crosses the line through `a` square to `u`: (the part on
    the side u points away from, the part on u's side), either None."""
    if not isinstance(f.get("line"), list) or not f["line"] or not isinstance(f["line"][0], (list, tuple)):
        return f, None
    L = np.asarray(f["line"], float)
    s = (L - a) @ u
    if (s <= 1e-9).all():
        return f, None
    if (s >= -1e-9).all():
        return None, f
    lo, hi = [], []
    for k in range(len(L)):
        (hi if s[k] > 0 else lo).append(L[k])
        if k + 1 < len(L) and s[k] * s[k + 1] < 0:
            q = L[k] + (L[k + 1] - L[k]) * s[k] / (s[k] - s[k + 1])
            lo.append(q)
            hi.append(q)
    return dict(f, line=[q.tolist() for q in lo]), dict(f, line=[q.tolist() for q in hi])


def apply_hinges(D: dict) -> None:
    """D["hinges"]: a piece that is ONE cloth but lies on two parts of the body (a shawl collar cut on with the front:
    the front on the torso, the collar round the back of the neck; a cut-on stand; a grown-on hood). The piece is
    cut along the hinge line for PLACEMENT only: the part past the line becomes "<piece>_<part>" in its own frame
    (origin and x axis given by the hinge) with its own wrap, joined to the rest by a seam noted "virtual" (sewn 1:1,
    no allowance, no groove in the maps). Pieces traced from it (facings) are cut the same way. Fold lines that cross
    the hinge are cut with it. Runs once, before unfold."""
    for hg in D.get("hinges") or []:
        a, dirn = np.asarray(hg["at"], float), np.asarray(hg["dir"], float)
        dirn = dirn / np.linalg.norm(dirn)
        mid = np.asarray(hg["mid"], float)
        o, ex = np.asarray(hg["origin"], float), np.asarray(hg["x"], float)
        ex = ex / np.linalg.norm(ex)
        ey = np.array([-ex[1], ex[0]])
        u = np.array([dirn[1], -dirn[0]])
        if u @ ex < 0:
            u = -u  # the far side (the part that takes the other placement) is the side the frame's x points to
        part = hg.get("part", "neck")
        group = [hg["piece"]] + [n for n, pc in D["pieces"].items() if pc.get("traced") == hg["piece"]]
        for nm in group:
            if nm not in D["pieces"]:
                continue
            pc = D["pieces"][nm]
            hits = _line_hits(pc, a, dirn)
            tm = float((mid - a) @ dirn)
            lo = [h for h in hits if h[0] <= tm]
            hi = [h for h in hits if h[0] > tm]
            from .cloth import _inside
            if not lo or not hi or not _inside(pc["P"], mid[None])[0]:
                continue  # the hinge doesn't cross this piece
            h1, h2 = lo[-1], hi[0]
            centre = D["centre"].get(nm)
            for tag, h in sorted((("_hb", h2), ("_ha", h1)), key=lambda x: -x[1][1]):  # the higher index first
                if h[2] is None:
                    pc["names"][tag] = h[1]
                else:
                    _insert(pc, h[1], h[2], tag)
            hn = f"{hg.get('name', 'hinge')}_{nm}"
            # where the piece's fold lines cross the hinge, both parts get a vertex (the folds' rows end on it: a
            # facing's rows then end where its front's do)
            via = []
            for f in D["folds"]:
                if f.get("piece") == nm and isinstance(f.get("line"), list) and not isinstance(f["line"][0], str):
                    Lf = np.asarray(f["line"], float)
                    sf = (Lf - a) @ u
                    for k in range(len(Lf) - 1):
                        if (sf[k] < -1e-9) != (sf[k + 1] < -1e-9):  # (a point ON the hinge counts as across)
                            q = Lf[k] + (Lf[k + 1] - Lf[k]) * sf[k] / (sf[k] - sf[k + 1])
                            # (and a few beside it, 4 mm apart: a roll's other rows end on the hinge too, and a
                            # row end snapped to a far vertex bends the row: its flap was stretched 150% there)
                            for kk in range(-3, 4):
                                qk = q + dirn * 0.004 * kk
                                if h1[0] + 0.004 < (qk - a) @ dirn < h2[0] - 0.004:
                                    via.append(qk)
            via.sort(key=lambda q: float((q - a) @ dirn))
            op_style_line(D, nm, name=hn, names=[f"{nm}__a", f"{nm}__b"], curve=False, apart=False, via=via,
                          **{"from": "_ha", "to": "_hb"})
            pa, pb_ = D["pieces"][f"{nm}__a"], D["pieces"][f"{nm}__b"]
            if hg.get("far") is not None:  # the part that holds (is nearest) this point takes the other placement
                fq = np.asarray(hg["far"], float)
                far, base = (pa, pb_) if np.linalg.norm(pa["P"] - fq, axis=1).min() < np.linalg.norm(pb_["P"] - fq, axis=1).min() \
                    else (pb_, pa)
            else:
                far, base = (pa, pb_) if (pa["P"].mean(0) - a) @ u > (pb_["P"].mean(0) - a) @ u else (pb_, pa)
            seam = D["seams"][-1]
            D["notes"][json.dumps(seam)] = {"ease": [-0.004, 0.004], "virtual": True,
                                            "why": f"{nm} and its {part} are one cloth: cut here only to place them"}
            fname = f"{nm}_{part}"
            hinge_len = edge_length(D, seam[0])
            _rename_piece(D, base["name"], nm)
            _rename_piece(D, far["name"], fname)
            D["centre"].pop(fname, None)
            if centre is not None:
                D["centre"][nm] = centre
            # stitches at marks, pair lists: to the part that holds the point now
            def owner(e):
                p_, x_ = e.split(":", 1)
                if p_ != nm:
                    return e
                first = x_.split(">")[0]
                if first in D["pieces"][nm]["names"] or first in D["pieces"][nm]["marks"]:
                    return e
                return f"{fname}:{x_}"
            for key in ("pair_seams", "pair_stitches"):
                D[key] = [owner(e) for e in D.get(key) or []]
            D["stitches"] = [[owner(x), owner(y)] for x, y in D["stitches"]]
            if nm in D["interfaced"]:
                D["interfaced"].append(fname)
            # the far part in its own frame
            far = D["pieces"][fname]
            tr = lambda Q: np.c_[(np.asarray(Q, float).reshape(-1, 2) - o) @ ex, (np.asarray(Q, float).reshape(-1, 2) - o) @ ey]
            if hg.get("matrix") is not None:  # any rigid map (a reflection too): far = M (p - origin) + offset
                Mh, th = np.asarray(hg["matrix"], float), np.asarray(hg.get("offset", [0.0, 0.0]), float)
                tr = lambda Q: (np.asarray(Q, float).reshape(-1, 2) - o) @ Mh.T + th
                if np.linalg.det(Mh) < 0:  # turned over: the outline runs the other way round
                    n_far = len(far["P"])
                    far["P"] = far["P"][::-1]
                    far["names"] = {k_: n_far - 1 - i_ for k_, i_ in far["names"].items()}
            far["P"] = tr(far["P"])
            far["marks"] = {k: tr(v)[0] for k, v in far["marks"].items()}
            far["lines"] = {k: tr(v) for k, v in far["lines"].items()}
            w_old = dict(far.get("wrap") or {})
            far["wrap"] = dict(hg["wrap"])
            if w_old.get("lies_on"):
                far["wrap"]["lies_on"] = f"{w_old['lies_on']}_{part}"
            if w_old.get("fused"):
                far["wrap"]["fused"] = f"{w_old['fused']}_{part}"
            far["of"] = nm
            en = far["wrap"].get("edge")
            if en and en not in far["names"]:  # (a traced piece's part: the frame's origin end of it)
                far["names"][en] = int(np.argmin(np.linalg.norm(far["P"], axis=1)))
            if hg.get("role") and not far.get("traced"):
                far["role"] = hg["role"]
            far["sym"] = "pair"
            folds = []
            for f in D["folds"]:
                if f.get("piece") != nm:
                    folds.append(f)
                    continue
                f_lo, f_hi = _split_fold(f, a, u)
                if f_lo is not None:
                    folds.append(f_lo)
                if f_hi is not None and f_hi is not f:
                    g = dict(f_hi, piece=fname, line=tr(f_hi["line"]).tolist(), name=f"{f.get('name', 'fold')} ({part})")
                    g.pop("flap", None)
                    for k_ in ("flap", "angle", "radius", "strength", "kind"):
                        if k_ in (hg.get("fold") or {}):
                            g[k_] = hg["fold"][k_]
                    fl, sp = g.get("flap"), D["pieces"].get(f"{hg['piece']}_{part}")
                    if fl and fl not in far["names"] and fl not in far["marks"] and sp is not None:
                        far["marks"][fl] = np.array(sp["marks"][fl] if fl in sp["marks"] else sp["P"][sp["names"][fl]], float)
                    folds.append(g)
            D["folds"] = folds
            D["log"].append(f"hinge {hn}: {nm} is placed in two parts ({nm} + {fname} -> {hg['wrap'].get('to')}), one "
                            f"cloth, joined along {hinge_len * 1000:.0f} mm")
    D["hinges"] = []


# ---------------------------------------------------------------- unfold


def _on_fold(pc: dict, name: str) -> bool:
    return abs(pc["P"][pc["names"][name], 0]) < 1e-6


def unfold(D: dict) -> dict:
    """Halves -> the garment's pieces; seams mirrored. Idempotent."""
    if D.get("unfolded"):
        return D
    # a piece traced from another (a facing) takes that piece's fold lines where they cross it: it is laid on the
    # piece and turns with it (and its mesh gets the same rows, so it can follow the crease)
    from .cloth import _inside
    for nm, pc in D["pieces"].items():
        src = pc.get("traced")
        for f in list(D["folds"]) if src else []:
            if f.get("piece") != src or not isinstance(f.get("line"), list) or isinstance(f["line"][0], str):
                continue
            L = np.asarray(f["line"], float)
            Q = np.concatenate([L[k] + (L[k + 1] - L[k]) * np.linspace(0, 1, 12)[:, None] for k in range(len(L) - 1)])
            if _inside(pc["P"], Q).mean() > 0.3 and not any(g.get("piece") == nm and g.get("name") == f.get("name") for g in D["folds"]):
                D["folds"].append(dict(copy.deepcopy(f), piece=nm))
                fl, sp = f.get("flap"), D["pieces"].get(src)
                if fl and sp is not None and fl not in pc["names"] and fl not in pc["marks"]:
                    pc["marks"][fl] = np.array(sp["marks"][fl] if fl in sp["marks"] else sp["P"][sp["names"][fl]], float)
    apply_hinges(D)
    halves = D["pieces"]
    out, kind = {}, {}
    for nm, pc in halves.items():
        sym = pc.get("sym", "pair")
        if sym == "fold" and D["centre"].get(nm, "fold") != "fold":
            sym = "pair"
        if sym == "fold" and np.sum(np.abs(pc["P"][:, 0]) < 1e-6) < 2:
            sym = "pair"  # the centre edge was cut away or extended: two pieces
        kind[nm] = sym
        base = {k: v for k, v in pc.items() if k not in ("sym", "darts")}
        if sym == "fold":
            whole = pattern.mirror_fold(dict(base, name=nm))
            mirp = lambda pl: dict(pl, a=[-pl["a"][0], pl["a"][1]], b=[-pl["b"][0], pl["b"][1]], sign=-pl["sign"])
            if (whole.get("wrap") or {}).get("pleats"):  # a pleat on each half
                whole["wrap"] = dict(whole["wrap"], pleats=whole["wrap"]["pleats"] + [mirp(p_) for p_ in whole["wrap"]["pleats"]])
            out[nm] = whole
        elif sym == "copy":
            for S in ("L", "R"):
                c = copy.deepcopy(base)
                c["name"] = f"{nm}.{S}"
                w = dict(c.get("wrap") or {})
                if str(w.get("to", "")).startswith("arm."):
                    w["to"] = f"arm.{S}"
                if "align" in w:
                    w["align"] = [w["align"][0], f"{w['align'][1]}.{S}", w["align"][2]]
                if "lies_on" in w:
                    w["lies_on"] = f"{w['lies_on']}.{S}"
                if "fused" in w:
                    w["fused"] = f"{w['fused']}.{S}"
                c["wrap"] = w
                out[f"{nm}.{S}"] = c
        else:
            L = copy.deepcopy(base)
            L["name"] = f"{nm}.L"
            R = pattern.mirror_x(copy.deepcopy(base))
            R["name"] = f"{nm}.R"
            R["wrap"] = dict(base.get("wrap") or {})
            if R["wrap"].get("pleats"):
                R["wrap"]["pleats"] = [dict(pl, a=[-pl["a"][0], pl["a"][1]], b=[-pl["b"][0], pl["b"][1]], sign=-pl["sign"])
                                       for pl in R["wrap"]["pleats"]]
            if "shift" in R["wrap"]:
                R["wrap"]["shift"] = [-R["wrap"]["shift"][0], R["wrap"]["shift"][1]]
            if D["centre"].get(nm) == "open" and L["wrap"].get("to") == "torso":
                # the left front laps over: a layer out, and a layer more for what lies between the two fronts (the
                # right front's lapel turned back onto it, a facing inside the left)
                # (as little as holds the layers apart: 20 mm stood the whole left front off the body and left its
                # panel seam 8 mm open after the settle)
                lap = 0.004 + 0.010 * any(f.get("piece") == nm for f in D["folds"]) + \
                    0.004 * any((p_.get("wrap") or {}).get("lies_on") == nm and not (p_.get("wrap") or {}).get("fused")
                                for p_ in halves.values())
                L["wrap"]["out"] = max(float(L["wrap"].get("out", 0)), lap)
            if D["centre"].get(nm) == "seam" and L["wrap"].get("to", "torso") == "torso":
                # the two halves of a centre seam start 2 mm apart: edge on edge, a contact solver drops the seam's
                # zero-length stitches (ZOZO: the jacket's centre back stayed open from the neck down)
                for c_, sg_ in ((L, 1.0), (R, -1.0)):
                    sh_ = c_["wrap"].get("shift", [0.0, 0.0])
                    c_["wrap"]["shift"] = [round(float(sh_[0]) + sg_ * 0.001, 5), float(sh_[1])]
            for S, c in (("L", L), ("R", R)):
                c["wrap"]["half"] = 1 if S == "L" else -1  # which side of x = 0 (its centre line) the piece is on
                if "lies_on" in c["wrap"]:
                    c["wrap"]["lies_on"] = f"{c['wrap']['lies_on']}.{S}"
                if "fused" in c["wrap"]:
                    c["wrap"]["fused"] = f"{c['wrap']['fused']}.{S}"
                if str(c["wrap"].get("to", "")).startswith("leg."):
                    c["wrap"]["to"] = f"leg.{S}"
                if str(c["wrap"].get("to", "")).startswith("arm."):  # a pair piece on an arm (a kimono sleeve's half):
                    c["wrap"]["to"] = f"arm.{S}"  # the mirrored one goes round its arm the other way
                    if S == "R":
                        c["wrap"]["front"] = -float(c["wrap"].get("front", 1))
                        if "cx" in c["wrap"]:
                            c["wrap"]["cx"] = -float(c["wrap"]["cx"])
            out[f"{nm}.L"], out[f"{nm}.R"] = L, R

    for c_ in out.values():  # (a pair piece lying on a piece cut on the fold: that piece has no .L / .R)
        lo_ = (c_.get("wrap") or {}).get("lies_on")
        if lo_ and lo_ not in out and lo_[:-2] in out:
            c_["wrap"]["lies_on"] = lo_[:-2]

    def side_spec(spec, S):
        nm, arc = spec.split(":", 1)
        k = kind[nm]
        if k == "fold":
            if S == "L":
                return f"{nm}:{arc}"
            return nm + ":" + ">".join(p if _on_fold(halves[nm], p) else p + ".m" for p in arc.split(">"))
        return f"{nm}.{S}:{arc}"

    def side_of(side, S):
        fl = [side_spec(e, S) for e in _flat(side)]
        return fl[0] if len(fl) == 1 else fl
    seams, notes = [], {}
    for s in D["seams"]:
        note = D["notes"].get(json.dumps(s))
        for S in ("L", "R"):
            ns = [side_of(s[0], S), side_of(s[1], S)]
            if ns in seams:
                continue
            seams.append(ns)
            if note:
                notes[json.dumps(ns)] = note
    for nm, c in D["centre"].items():  # a centre seam joins the two halves of a pair
        if c == "seam" and kind.get(nm) == "pair":
            ce = D["edges"].get("centre_front" if str(halves[nm].get("role") or "").endswith("front") else "centre_back")
            ce = [e for e in (ce or []) if e.split(":")[0] == nm]
            if ce:
                seams.append([side_of(ce, "L"), side_of(ce, "R")])
    for e in D.get("pair_seams") or []:  # an edge of a pair piece sewn to its own mirror (a collar's CB seam, a hood)
        if kind.get(e.split(":")[0]) == "pair":
            seams.append([side_spec(e, "L"), side_spec(e, "R")])
    stitches = list(D["stitches"])
    for e in D.get("pair_stitches") or []:  # buttons: the right front's mark to the left front's
        if kind.get(e.split(":")[0]) == "pair":
            stitches.append([side_spec(e, "R"), side_spec(e, "L")])
    def side_pt(e, S):  # a point or mark of a half piece, on side S of the garment
        nm, pt = e.split(":", 1)
        k = kind[nm]
        if k == "fold":
            h = halves[nm]
            x = h["P"][h["names"][pt], 0] if pt in h["names"] else float(np.asarray(h["marks"][pt])[0])
            return e if (S == "L" or abs(x) < 1e-6) else f"{nm}:{pt}.m"
        return f"{nm}.{S}:{pt}"
    for a_, b_ in D.get("sym_stitches") or []:  # tacks drawn on the half: on both sides of the garment
        for S in ("L", "R"):
            st = [side_pt(a_, S), side_pt(b_, S)]
            if st not in stitches:
                stitches.append(st)
    D["stitches"] = stitches
    edges = {}
    for k_, chain in D["edges"].items():
        for S in ("L", "R"):
            edges[f"{k_}.{S}"] = [side_spec(e, S) for e in chain if e.split(":")[0] in kind]
    folds, inter = [], []
    for f in D["folds"]:
        for S in ("L", "R"):
            k = kind.get(f["piece"])
            if k is None:
                continue
            g = copy.deepcopy(f)
            g["piece"] = f["piece"] if k == "fold" else f"{f['piece']}.{S}"
            if isinstance(g.get("line"), dict) and "edge" in g["line"]:
                g["line"]["edge"] = side_spec(g["line"]["edge"], S)
            elif isinstance(g.get("line"), list) and S == "R" and k != "fold":
                g["line"] = [[-float(q[0]), float(q[1])] for q in g["line"]]  # points: mirrored with the piece
            if k == "fold" and S == "R":
                # one fold line runs across the whole piece (declared on the left half's edge); a line given by
                # points that stays off the centre (a pleat on each side) is mirrored to the other half
                Lp = g.get("line")
                if isinstance(Lp, list) and Lp and not isinstance(Lp[0], str) and min(abs(float(q[0])) for q in Lp) > 1e-4:
                    g["line"] = [[-float(q[0]), float(q[1])] for q in Lp]
                    g["name"] = f"{g.get('name', 'fold')} (R)"
                    if isinstance(g.get("flap"), str):
                        g["flap"] = g["flap"] + ".m"
                    folds.append(g)
                continue
            folds.append(g)
    for nm in D["interfaced"]:
        k = kind.get(nm)
        inter += [nm] if k == "fold" else [f"{nm}.L", f"{nm}.R"]
    wb = D.get("waistband")
    if wb:
        # the waistband's chain round the waist from the centre back: the right back out to the side, the right front
        # in to the centre, the left front out, the left back in (each half's waist edges run centre -> side)
        rv = lambda ch: [_rev(e) for e in reversed(ch)]
        chain = list(edges.get("waist_back.R", [])) + rv(edges.get("waist_front.R", [])) + \
            list(edges.get("waist_front.L", [])) + rv(edges.get("waist_back.L", []))
        if not chain:
            raise DraftError("waistband: the draft has no waist edges (waist_front / waist_back: a trouser or skirt block)")
        D["generate"].append({"band": wb.get("name", "waistband"), "role": "waistband", "along": chain,
                              "ratio": float(wb.get("ratio", 1.0)), "height": float(wb.get("height", 0.04)),
                              "overlap": float(wb.get("overlap", 0.035)), "interfaced": True,
                              "wrap": {"to": "torso", "side": "front", "level": "waist", "out": 0.004}})
    D.update(pieces=out, seams=seams, notes=notes, edges=edges, folds=folds, interfaced=inter, unfolded=True)
    D["log"].append(f"unfold: {', '.join(out)}")
    return D


# ---------------------------------------------------------------- entry for cloth.pieces


def build(meas_mm: dict, pat: dict) -> dict:
    """pattern {"from": "draft", "block": ..., "block_options": {...}, "ops": [...]} -> what cloth.pieces takes."""
    D = start(pat.get("block", "bodice"), meas_mm, pat.get("block_options"))
    apply(D, pat.get("ops"))
    unfold(D)
    for nm, pc in D["pieces"].items():
        pc.setdefault("wrap", {})
    return {"pieces": D["pieces"], "seams": D["seams"], "stitches": D["stitches"], "interfaced": D["interfaced"],
            "folds": D["folds"], "generate": D["generate"], "seam_notes": D["notes"],
            "draft": {"design": "draft", "block": D["block"], "options": pat.get("block_options") or {},
                      "measurements": dict(meas_mm), "log": D["log"], "meta": {k: v for k, v in D["meta"].items()
                                                                               if k != "measurements"}},
            "_D": D}



from . import pattern_tailor  # noqa: E402,F401  (registers contour, join, round_corner, fisheye)
from . import pattern_styles  # noqa: E402,F401  (registers shawl, lapel, cut_away, darts_to_seam, raglan, kimono, hood, pleat...)
