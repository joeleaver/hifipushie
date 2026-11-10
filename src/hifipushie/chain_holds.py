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
    layers: dict  # floating layer piece -> its host piece (a hostless seamless stiff piece is a part of its own)
    folds: list  # {name, piece, part, kind, fall}
    inside: dict = field(default_factory=dict)  # soft piece -> the larger soft piece it hangs inside (a facing in its front)

    def part_of(self, piece: str) -> Part | None:
        return next((p for p in self.parts if piece in p.pieces), None)

    def summary(self) -> dict:
        return {"parts": [{"name": p.name, "pieces": p.pieces, "outer": p.outer, "stiff": p.stiff, "rests_on": p.rests_on,
                           **({"stiffened_by": p.stiffened_by} if p.stiffened_by else {}),
                           **({"folds": p.folds} if p.folds else {})} for p in self.parts],
                "plies": self.plies, "layers": self.layers, "folds": self.folds,
                **({"inside": self.inside} if self.inside else {})}


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
    # (only with a host: a stiff piece with no seams and no soft piece sharing its place, or one a closure fastens, is a
    # part of its own: a belt sewn to nothing closes on its own buckle and is a RING, never a layer)
    closed = {c.get(k) for c in net.M.get("closures") or [] for k in ("over", "under")}
    floating = [i for i in range(n) if whole[i] and i not in seamed and names[i] not in closed]
    place = net.M.get("place") or {}
    layers: dict = {}
    for i in floating:
        pl, sd = place.get(names[i]), _side(names[i])
        cand = [j for j in range(n) if not whole[j] and j not in floating and len(groups[find(j)]) == 1 and pl
                and place.get(names[j]) == pl and _side(names[j]) == sd]
        if cand:
            layers[names[i]] = names[max(cand, key=lambda j: _area(net.uv, net.F[np.all(net.piece[net.F] == j, axis=1)]))]
    layer_ids = [i for i in floating if names[i] in layers]
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
    return Holds(stiff + soft, plies, layers, folds, inside_of(net, groups, find, whole, floating, pairs))


def inside_of(net, groups, find, whole, floating, pairs) -> dict:
    """Soft pieces that hang INSIDE a larger soft piece (a facing inside its front): worn at the same place and side,
    sewn to it only along its outline (an edge, never a patch on its face) in ONE run (a two-piece sleeve's halves are
    sewn in two runs: a tube, not a lining), and its flat lying in that piece's own flat (layer_frame: one design draws
    both in one frame). It starts a layer inside that piece, not as a panel of its own."""
    from .chain_net import boundary_edges
    names, n = net.names, len(net.names)
    place = net.M.get("place") or {}
    soft = [j for j in range(n) if not whole[j] and j not in floating and len(groups[find(j)]) == 1]
    area = {j: _area(net.uv, net.F[np.all(net.piece[net.F] == j, axis=1)]) for j in soft}
    out = {}
    for j in soft:
        pl = place.get(names[j])
        cand = [h for h in soft if h != j and pl and place.get(names[h]) == pl and _side(names[h]) == _side(names[j])
                and area[h] > area[j] and len(pairs.get((j, h), [])) >= 3]
        for h in sorted(cand, key=lambda h: -area[h]):
            Fh = net.F[np.all(net.piece[net.F] == h, axis=1)]
            edge = set(np.unique(boundary_edges(Fh)).tolist())
            if (all(c in edge for _, c in pairs[(j, h)]) and sewn_runs(net, j, {a for a, _ in pairs[(j, h)]}) == 1
                    and layer_frame(net, names[j], names[h])["own"]):
                out[names[j]] = names[h]
                break
    return out


# ---- the build: plies and floating layers follow their host
LAYER_TOL = 0.003  # m: a floating layer's flat point lies in its host's flat within this (the canvas: every point at 0)
LAYER_IN = 0.98  # of a floating layer's points that must lie in its host's flat for the host's frame to be its own


def _faces(net, piece: str):
    return net.F[np.all(net.piece[net.F] == net.pid(piece), axis=1)]


def flat_locate(uv, F, q, k: int = 8) -> tuple:
    """(face index into F, barycentric weights clipped onto it, flat distance from q to it) of flat points q in the
    triangles F over uv (the nearest of the k faces by centroid with the largest least weight)."""
    from scipy.spatial import cKDTree
    q = np.asarray(q, float).reshape(-1, 2)
    k = min(k, len(F))
    J = np.asarray(cKDTree(uv[F].mean(1)).query(q, k=k)[1]).reshape(len(q), k)
    t = uv[F[J]]  # (n, k, 3, 2)
    e1, e2, d = t[:, :, 1] - t[:, :, 0], t[:, :, 2] - t[:, :, 0], q[:, None] - t[:, :, 0]
    det = e1[..., 0] * e2[..., 1] - e1[..., 1] * e2[..., 0]
    det = np.where(np.abs(det) < 1e-18, 1e-18, det)
    l1 = (d[..., 0] * e2[..., 1] - d[..., 1] * e2[..., 0]) / det
    l2 = (e1[..., 0] * d[..., 1] - e1[..., 1] * d[..., 0]) / det
    W = np.stack([1 - l1 - l2, l1, l2], -1)
    best = np.argmax(W.min(-1), 1)
    r = np.arange(len(q))
    w = np.clip(W[r, best], 0, None)
    w /= np.maximum(w.sum(1, keepdims=True), 1e-12)
    f = J[r, best]
    dist = np.linalg.norm((w[:, :, None] * uv[F[f]]).sum(1) - q, axis=1)
    return f, w, dist


def _outward(b, X, F):
    """Unit face normals of F at X, turned to the body's outward side (the outer side of cloth on it)."""
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    out = b.body.contact.query(X[F].mean(1))[1]
    fn = np.where(((fn * out).sum(1) < 0)[:, None], -fn, fn)
    return fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)


def _put(X, rs, v, P):
    """Vertices v at P, through their nodes: every vertex sewn to them follows (one node, one position)."""
    X[rs[v]] = P
    m = np.isin(rs, rs[v])
    X[m] = X[rs[m]]


def layer_frame(net, layer: str, host: str) -> dict:
    """Does the floating layer's flat lie in its host's flat (both drawn by one design, in one draft frame)? The share
    of its points inside the host's triangles within LAYER_TOL; the frame is the host's own when LAYER_IN of them are."""
    v = net.verts(layer)
    _, _, dist = flat_locate(net.uv, _faces(net, host), net.uv[v])
    share = float((dist <= LAYER_TOL).mean())
    return {"inside": round(share, 4), "worst_mm": round(float(dist.max()) * 1e3, 2), "own": share >= LAYER_IN}


def place_layers(b, X=None) -> dict:
    """Each floating layer on a placed host: its flat point (in the host's own draft frame, layer_frame) onto the host's
    surface there, a LAYER inside it, through its nodes; the host's vertices it covers take its stiffness (net.bend and
    b.layer_stiff, the hang's stiff weight), once. A layer whose flat doesn't lie in its host's is refused by name: no
    frame, no honest place. X: the positions to place on (default b.X), changed in place and returned."""
    from .chain_core import LAYER, ChainRefused
    H = getattr(b, "holds", None)
    X = b.X if X is None else X
    if H is None or not H.layers:
        return {}
    net, rs = b.net, b.net.root
    rep = {}
    for lay, host in H.layers.items():
        hv = net.verts(host)
        if not np.abs(X[hv]).sum():
            continue  # (the host isn't built yet)
        fr = layer_frame(net, lay, host)
        if not fr["own"]:
            raise ChainRefused(f"the floating layer {lay} doesn't lie in its host {host}'s flat ({fr['inside']:.0%} of its "
                               f"points inside, worst {fr['worst_mm']} mm out): it has no place there. next: draft it "
                               f"from {host}'s own points (draft_pattern), or sew it to {host} (a ply)")
        Fh, v = _faces(net, host), net.verts(lay)
        f, w, _ = flat_locate(net.uv, Fh, net.uv[v])
        P = (w[:, :, None] * X[Fh[f]]).sum(1) - LAYER * _outward(b, X, Fh)[f]
        _put(X, rs, v, P)
        r = {"stiffens": host, "built": True, "frame": f"{host}'s own flat ({fr['inside']:.0%} of its points inside)",
             "placed": int(len(v)), "inside_mm": round(LAYER * 1e3, 1)}
        done = getattr(b, "layer_done", None) or {}
        if lay not in done:  # (its stiffness onto the host where it lies: the host's points inside the layer's flat)
            fl, wl, dl = flat_locate(net.uv, _faces(net, lay), net.uv[hv])
            cov = dl <= LAYER_TOL
            Fl = _faces(net, lay)
            bend = (wl * net.bend[Fl[fl]]).sum(1)
            stf = (wl * net.stiff[Fl[fl]]).sum(1)
            net.bend[hv[cov]] = np.maximum(net.bend[hv[cov]], bend[cov])
            if getattr(b, "layer_stiff", None) is None:
                b.layer_stiff = np.zeros(net.n)
            b.layer_stiff[hv[cov]] = np.maximum(b.layer_stiff[hv[cov]], stf[cov])
            done[lay] = {"covers": int(cov.sum()), "of_host": round(float(cov.mean()), 3),
                         "bend": round(float(bend[cov].mean()), 3) if cov.any() else 0.0,
                         "stiff": round(float(stf[cov].mean()), 3) if cov.any() else 0.0}
            b.layer_done = done
        r.update(done[lay])
        rep[lay] = r
    b.reads.setdefault("layers", {}).update(rep)
    return rep


def place_inside(b, X) -> dict:
    """(the start) Each soft piece that hangs inside another (Holds.inside, a facing in its front): its flat point onto
    its host's start there, inside it by a LAYER per floating layer the host carries plus one (interfacing lies next to
    the outer cloth). Only its points that no host point and no held point already place (its sewn edge stays the
    host's; its seam to a stiff part stays there). X changed in place."""
    from .chain_core import LAYER
    H = getattr(b, "holds", None)
    if H is None or not H.inside:
        return {}
    net, rs = b.net, b.net.root
    held = np.zeros(net.n, bool)
    held[rs[b._stiff_mask()]] = True
    rep = {}
    for p, host in H.inside.items():
        hv = net.verts(host)
        if not np.abs(X[hv]).sum():
            continue
        held_h = held.copy()
        held_h[rs[hv]] = True
        v = net.verts(p)
        free = v[~held_h[rs[v]]]
        Fh = _faces(net, host)
        f, w, _ = flat_locate(net.uv, Fh, net.uv[free])
        k = 1 + sum(1 for h in H.layers.values() if h == host)
        _put(X, rs, free, (w[:, :, None] * X[Fh[f]]).sum(1) - k * LAYER * _outward(b, X, Fh)[f])
        rep[p] = {"inside": host, "placed": int(len(free)), "on_its_seams": int(len(v) - len(free)), "inside_mm": round(k * LAYER * 1e3, 1)}
    b.reads.setdefault("inside", {}).update(rep)
    return rep


def place_plies(b, hosts=None, X=None) -> dict:
    """Each ply of a placed host follows it. A ply point sewn to the host is already the host's (one node). EVERY other
    point (unsewn, or sewn only to a third piece: a collar ply's gorge sewn to a facing) goes through the flat map that
    the ply's sewn pairs with its part give (affine least squares, ply uv -> host uv), onto the host's surface at that
    flat point, then a LAYER inside it per ply (stiff plies next to the outer, as interfacing lies), through its node, so
    the third piece's points sewn there start on it. `hosts`: only these outer pieces (default: every host with a placed
    vertex). X: the positions to place on (default b.X), changed in place."""
    from .chain_core import LAYER
    H = getattr(b, "holds", None)
    if H is None or not H.plies:
        return {}
    own = X is None
    net, X, rs = b.net, (b.X if X is None else X), b.net.root
    pairs, _ = _sewn(net)
    rep = {}
    for pt in H.parts:
        if len(pt.pieces) < 2 or (hosts is not None and pt.outer not in hosts):
            continue
        hv = net.verts(pt.outer)
        if not np.abs(X[hv]).sum():
            continue  # (the host isn't built yet)
        Fh = _faces(net, pt.outer)
        fn = _outward(b, X, Fh)
        on_host = np.zeros(net.n, bool)
        on_host[rs[hv]] = True  # (nodes the host's own points hold)
        plies = sorted(pt.pieces[1:], key=lambda x: -float(net.stiff[net.verts(x)].mean()))
        for k, ply in enumerate(plies, 1):
            pp = net.pid(ply)
            ab = np.asarray([(a, c) for q in [net.pid(x) for x in pt.pieces] for a, c in pairs.get((pp, q), [])])
            T = np.linalg.lstsq(np.c_[net.uv[ab[:, 0]], np.ones(len(ab))], net.uv[ab[:, 1]], rcond=None)[0]
            v = net.verts(ply)
            free = v[~on_host[rs[v]]]
            q = np.c_[net.uv[free], np.ones(len(free))] @ T
            f, w, _ = flat_locate(net.uv, Fh, q)
            _put(X, rs, free, (w[:, :, None] * X[Fh[f]]).sum(1) - k * LAYER * fn[f])
            rep[ply] = {"on": pt.outer, "placed": int(len(free)), "sewn": int(len(v) - len(free)), "inside_mm": k * LAYER * 1e3}
    if own:
        b.X = X
    b.reads.setdefault("plies", {}).update(rep)
    return rep
