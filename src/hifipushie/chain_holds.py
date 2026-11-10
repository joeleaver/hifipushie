"""CHAIN HOLDS (R3b of docs/proposals/step5_one_build.md): WHAT HOLDS WHAT, read from how the pattern is constructed.

Trial s5-1 (2026-11-10) found the chain build reading structure from shirt vocabulary. The first "roll" fold made its
piece a collar FALL, so the suit jacket's lapel roll, a roll fold on the soft front, read as a collar. The hussar's collar
canvas (the stand's interfacing) read as a FALL with no roll and was refused. This module reads the structure from the
pattern alone: the pieces, the sewing (net.sew), the folds, the interfacing (net.stiff), the declared roles and where each
piece is worn (M["place"], the draft's `place` {to, side}). Nothing in it names a garment, a piece or a limb.
Step 1's layer numbers are not on the flat mesh, so they are not read.

PARTS. Pieces joined as PLIES are one part. A ply LIES ON its host, cut to the same outline and sewn round it. A
collar's canvas is sewn to the collar on all four edges. Its facing is sewn on top and end, with the neck edges left
free inside. A jacket's top collar and undercollar are sewn along the fall and both ends. Three tests, all needed:
- CONGRUENT. The sewn pairs' flat positions map onto the host's by a rigid motion, within PLY_RMS. Every ply measured
  0.0 mm. Two-piece sleeves measured 23-25 mm (a top sleeve is wider than its undersleeve, sewn round a tube), and a
  shirt collar on its band measured 20.6 mm (its neck edge curves the other way to the band's top). The fit allows a
  reflection, because plies are often cut face to face (an undercollar cut mirrored to its top collar).
- AROUND AN AREA. The sewn outline's hull covers at least PLY_AREA of the piece's flat area. Any single line, straight or
  curved, maps rigidly onto its partner. A front + facing (the front edge only) is 0.0 mm, and so are a yoke on a back
  and a shoulder seam. Their areas are 0.00-0.09 against 0.41-1.08 for the plies (canvas 1.08, collar facing 0.58,
  collar / undercollar 0.41).
- IN ONE RUN. The sewn stretch of each outline is one run (a pocket: the canvas all round, the facing's end-top-end,
  the collar's end-fall-end). Two halves of a tube sewn along both sides, congruent when cut alike (a synthetic trouser
  leg's front and back), make two runs, and its two ends stay open.
A share of the sewn LENGTH does not separate these cases (measured 2026-11-10). The undercollar is 0.47 of its outline on
the collar and a shirt band 0.45 on its collar, while two-piece sleeves are 0.62-0.79 on each other.
The OUTER ply is the one with the most sewn length to cloth outside the part (the body cloth or a facing). It is the
piece the stages build; the others follow its surface (place_plies). A part is stiff when any of its pieces is wholly
interfaced.

LAYERS. A wholly interfaced piece with no seams at all (a jacket's chest canvas) floats inside the soft piece worn at the
same place (to, side) on the same side (.L / .R). It stiffens that host and is not built on its own. When several soft
pieces share the place, the host is the largest: the body cloth, where a facing is a strip along its edge.

ORDER. Stiff parts come first. A stiff part sewn only to soft cloth (a band, a stand, a cuff) rests on the "body". A
stiff part sewn to a stiff part (a fall on its band) rests on that part, so it comes after it. Soft parts hang from the
stiff parts they are sewn to (else from the "body"). This is data, a list of parts each with `rests_on`, not stages.

FOLDS. Each fold is listed on its part and piece with its kind. A roll fold is a collar's FALL only on a STIFF part. On a
soft piece it is that piece's own fold (a lapel), kept for R3d's crease turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

PLY_RMS = 0.001  # m: a ply's sewn outline maps rigidly onto its host's within this (plies 0.0 mm; sleeves, a band 20+ mm)
PLY_AREA = 0.25  # of the piece's flat area closed round by its sewn outline (plies 0.41-1.08; one seam line 0.00-0.09)
PLY_GAP = 0.01  # m: unsewn stretches of an outline shorter than this (a seam's corner) don't split its sewn run
WHOLE = 0.95  # a piece is stiff when this share of its vertices is interfaced (chain_roles' rule)


@dataclass
class Part:
    name: str  # its outer ply's name
    pieces: list
    outer: str
    stiff: bool
    folds: list = field(default_factory=list)
    rests_on: list = field(default_factory=list)  # "body" or the stiff parts it is sewn to
    stiffened_by: list = field(default_factory=list)  # floating layers inside it


@dataclass
class Holds:
    parts: list  # in ORDER: stiff parts (resting first), then soft
    plies: dict  # ply piece -> its part's outer piece
    layers: dict  # floating layer piece -> its host piece (None when no piece shares its place)
    folds: list  # {name, piece, part, kind, fall}

    def part_of(self, piece: str) -> Part | None:
        return next((p for p in self.parts if piece in p.pieces), None)

    def summary(self) -> dict:
        return {"parts": [{"name": p.name, "pieces": p.pieces, "outer": p.outer, "stiff": p.stiff, "rests_on": p.rests_on,
                           **({"stiffened_by": p.stiffened_by} if p.stiffened_by else {}),
                           **({"folds": p.folds} if p.folds else {})} for p in self.parts],
                "plies": self.plies, "layers": self.layers, "folds": self.folds}


def _side(name: str) -> str:
    return name[-2:] if name.endswith((".L", ".R")) else ""


def _area(uv, F) -> float:
    e1, e2 = uv[F[:, 1]] - uv[F[:, 0]], uv[F[:, 2]] - uv[F[:, 0]]
    return 0.5 * float(np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum())


def rigid_rms(A, B) -> float:
    """RMS after the best rigid motion of A onto B, a reflection allowed (Kabsch, both orientations, the better kept)."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    a, b = A - A.mean(0), B - B.mean(0)
    U, _, Vt = np.linalg.svd(a.T @ b)
    best = np.inf
    for s in (1.0, -1.0):
        D = np.eye(A.shape[1])
        D[-1, -1] = s
        R = U @ D @ Vt
        best = min(best, float(np.sqrt(((a @ R - b) ** 2).sum(1).mean())))
    return best


def hull_share(P, area: float) -> float:
    from scipy.spatial import ConvexHull, QhullError
    if len(P) < 3 or area <= 0:
        return 0.0
    try:
        return float(ConvexHull(P).volume) / area
    except QhullError:  # (collinear: a straight seam closes round nothing)
        return 0.0


def _sewn(net) -> tuple:
    """{(p, q): [(vertex of p, vertex of q)]} for pieces p != q sewn directly, and the self-sewn pieces."""
    pairs: dict = {}
    selfs = set()
    for a, b in net.sew:
        pa, pb = int(net.piece[a]), int(net.piece[b])
        if pa == pb:
            selfs.add(pa)
            continue
        pairs.setdefault((pa, pb), []).append((int(a), int(b)))
        pairs.setdefault((pb, pa), []).append((int(b), int(a)))
    return pairs, selfs


def _sewn_length(net, p: int, verts: set) -> float:
    """Length of piece p's outline with both ends among `verts`."""
    from .chain_net import boundary_edges
    Fp = net.F[np.all(net.piece[net.F] == p, axis=1)]
    be = boundary_edges(Fp)
    on = np.array([int(a) in verts and int(b) in verts for a, b in be], bool) if len(be) else np.zeros(0, bool)
    return float(np.linalg.norm(net.uv[be[on, 0]] - net.uv[be[on, 1]], axis=1).sum()) if on.any() else 0.0


def sewn_runs(net, p: int, verts: set) -> int:
    """How many separate stretches of piece p's outline are sewn (both ends in `verts`), round its loop."""
    lp = net.loop(net.names[p])
    if len(lp) < 3:
        return 0
    on = np.array([int(a) in verts and int(b) in verts for a, b in zip(lp, np.roll(lp, -1))], bool)
    if on.all():
        return 1
    L = np.linalg.norm(net.uv[lp] - net.uv[np.roll(lp, -1)], axis=1)
    k = int(np.argmax(~on))  # (start in a gap: every run then ends inside the loop)
    on, L = np.roll(on, -k), np.roll(L, -k)
    runs, gap = 0, np.inf
    for o, l in zip(on, L):
        if o:
            if gap >= PLY_GAP:
                runs += 1
            gap = 0.0
        else:
            gap += l
    lead = float(L[:int(np.argmax(on))].sum())  # (the gap before the first run joins the one after the last)
    return runs - 1 if runs > 1 and lead + gap < PLY_GAP else runs


def ply_pairs(net) -> list:
    """[(p, q, rms, share)] for every piece pair that passes both ply tests (module doc)."""
    pairs, _ = _sewn(net)
    out = []
    for (p, q), ab in pairs.items():
        if p > q or len(ab) < 3:
            continue
        ab = np.asarray(ab)
        rms = rigid_rms(net.uv[ab[:, 0]], net.uv[ab[:, 1]])
        if rms > PLY_RMS:
            continue
        sh = []
        for k, piece in ((0, p), (1, q)):
            Fp = net.F[np.all(net.piece[net.F] == piece, axis=1)]
            sh.append(hull_share(net.uv[np.unique(ab[:, k])], _area(net.uv, Fp)))
        if min(sh) >= PLY_AREA and max(sewn_runs(net, piece, set(ab[:, k].tolist())) for k, piece in ((0, p), (1, q))) <= 1:
            out.append((p, q, rms, min(sh)))
    return out


def read(net) -> Holds:
    """The pattern's construction (module doc)."""
    names, n = net.names, len(net.names)
    whole = [float(net.stiff[net.verts(nm)].mean()) > WHOLE for nm in names]
    pairs, selfs = _sewn(net)
    # parts: union of ply pairs
    up = list(range(n))

    def find(a):
        while up[a] != a:
            up[a] = up[up[a]]
            a = up[a]
        return a
    for p, q, _, _ in ply_pairs(net):
        up[find(p)] = find(q)
    groups: dict = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    # floating layers: stiff, no seams at all
    seamed = {p for p, _ in pairs} | selfs
    layer_ids = [i for i in range(n) if whole[i] and i not in seamed]
    place = net.M.get("place") or {}
    layers: dict = {}
    for i in layer_ids:
        pl, sd = place.get(names[i]), _side(names[i])
        cand = [j for j in range(n) if not whole[j] and j not in layer_ids and len(groups[find(j)]) == 1 and pl
                and place.get(names[j]) == pl and _side(names[j]) == sd]
        layers[names[i]] = names[max(cand, key=lambda j: _area(net.uv, net.F[np.all(net.piece[net.F] == j, axis=1)]))] \
            if cand else None
    parts, plies, of = [], {}, {}
    for g in groups.values():
        if g[0] in layer_ids:
            continue
        gs = set(g)
        if len(g) > 1:
            outside = {j: set(v for q in range(n) if q not in gs for v, _ in pairs.get((j, q), [])) for j in g}
            outer = max(g, key=lambda j: (_sewn_length(net, j, outside[j]), whole[j], -j))
        else:
            outer = g[0]
        pt = Part(names[outer], [names[outer]] + [names[j] for j in g if j != outer], names[outer], any(whole[j] for j in g))
        for j in g:
            of[j] = pt
            if j != outer:
                plies[names[j]] = names[outer]
        parts.append(pt)
    for lay, host in layers.items():
        if host:
            of[names.index(host)].stiffened_by.append(lay)
    # what each part is sewn to (outside itself): a stiff part sewn to any soft cloth rests on the body (a band, a stand,
    # a cuff, even with a fall sewn on top); one sewn to stiff parts only rests on them (a fall on its band)
    byname = {p.name: p for p in parts}
    for pt in parts:
        ids = {names.index(x) for x in pt.pieces}
        nb = sorted({of[q].name for p in ids for (a, q) in pairs if a == p and q not in ids and q in of},
                    key=lambda x: names.index(x))
        stiff_nb = [x for x in nb if byname[x].stiff]
        if pt.stiff:
            pt.rests_on = ["body"] if len(stiff_nb) < len(nb) or not nb else stiff_nb
        else:
            pt.rests_on = stiff_nb or ["body"]
    depth: dict = {}

    def dep(pt, seen=()):
        if pt.name not in depth:
            below = [byname[x] for x in pt.rests_on if x in byname and x not in seen]
            depth[pt.name] = 1 + max(dep(p, seen + (pt.name,)) for p in below) if below else 0
        return depth[pt.name]
    stiff = [p for p in parts if p.stiff]
    stiff.sort(key=lambda p: (dep(p), names.index(p.outer)))
    soft = [p for p in parts if not p.stiff]
    folds = []
    for f in net.M.get("folds") or []:
        pc = f.get("piece")
        pt = of.get(names.index(pc)) if pc in names else None
        rec = {"name": f.get("name"), "piece": pc, "part": pt.name if pt else None, "kind": f.get("kind"),
               "fall": bool(pt and pt.stiff and f.get("kind") == "roll")}
        folds.append(rec)
        if pt:
            pt.folds.append(rec["name"])
    return Holds(stiff + soft, plies, layers, folds)


# ---- the build: plies follow their host
def place_plies(b, hosts=None) -> dict:
    """Each ply of a placed host follows it. Sewn points are already the host's (one node). Every other point goes
    through the flat map that the shared outline's sewn pairs give (affine least squares, ply uv -> host uv), onto
    the host's surface at that flat point, then a LAYER inside it per ply (stiff plies next to the outer, as
    interfacing lies). `hosts`: only these outer pieces (default: every host with a placed vertex)."""
    from scipy.spatial import cKDTree
    from .chain_core import LAYER
    H = getattr(b, "holds", None)
    if H is None or not H.plies:
        return {}
    net, X, rs = b.net, b.X, b.net.root
    pairs, _ = _sewn(net)
    rep = {}
    for pt in H.parts:
        if len(pt.pieces) < 2 or (hosts is not None and pt.outer not in hosts):
            continue
        ho = net.pid(pt.outer)
        hv = net.verts(pt.outer)
        if not np.abs(X[hv]).sum():
            continue  # (the host isn't built yet)
        Fh = net.F[np.all(net.piece[net.F] == ho, axis=1)]
        fn = np.cross(X[Fh[:, 1]] - X[Fh[:, 0]], X[Fh[:, 2]] - X[Fh[:, 0]])
        cen = X[Fh].mean(1)
        out = b.body.contact.query(cen)[1]  # (the body's outward normal there: the outer side)
        fn = np.where(((fn * out).sum(1) < 0)[:, None], -fn, fn)
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
        kd = cKDTree(net.uv[Fh].mean(1))
        plies = sorted(pt.pieces[1:], key=lambda x: -float(net.stiff[net.verts(x)].mean()))
        for k, ply in enumerate(plies, 1):
            pp = net.pid(ply)
            ab = [(a, c) for q in [net.pid(x) for x in pt.pieces] for a, c in pairs.get((pp, q), [])]
            ab = np.asarray(ab)
            A = np.c_[net.uv[ab[:, 0]], np.ones(len(ab))]
            T = np.linalg.lstsq(A, net.uv[ab[:, 1]], rcond=None)[0]
            v = net.verts(ply)
            free = v[np.bincount(rs, minlength=net.n)[rs[v]] == 1]  # (not sewn: its own node)
            q = np.c_[net.uv[free], np.ones(len(free))] @ T
            _, J = kd.query(q, k=min(8, len(Fh)))
            J = np.asarray(J).reshape(len(free), -1)
            P = np.zeros((len(free), 3))
            for i in range(len(free)):
                best, bw, bj = -np.inf, None, None
                for j in J[i]:
                    t = net.uv[Fh[j]]
                    M2 = np.c_[t[1] - t[0], t[2] - t[0]]
                    try:
                        l1, l2 = np.linalg.solve(M2, q[i] - t[0])
                    except np.linalg.LinAlgError:
                        continue
                    w = np.array([1 - l1 - l2, l1, l2])
                    if w.min() > best:
                        best, bw, bj = w.min(), w, j
                bw = np.clip(bw, 0, None) / max(np.clip(bw, 0, None).sum(), 1e-12)
                P[i] = bw @ X[Fh[bj]] - k * LAYER * fn[bj]
            X[free] = P
            rep[ply] = {"on": pt.outer, "placed": int(len(free)), "sewn": int(len(v) - len(free)), "inside_mm": k * LAYER * 1e3}
    b.X = X
    b.reads.setdefault("plies", {}).update(rep)
    return rep
