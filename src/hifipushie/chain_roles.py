"""CHAIN ROLES (garment_steps T8, C289): the roles a chain build reads from ANY pattern, beyond a collared shirt.

Joe (2026-11-02): every garment is built by the same general chain build, from its pattern; nothing garment-specific.
A role comes from the pattern's construction (what is interfaced, what is sewn to what, which fold rolls, which closure
joins which pieces) plus the piece's declared role (draft_pattern's `role`, carried on the flat mesh as M["roles"];
else the role its name reads as, garment_design.role_of). Names never pick a stage on their own.

- FALL: a piece with a "roll" fold. BAND: the wholly interfaced piece the fall is sewn to (a shirt's collar band).
- STAND: a wholly interfaced piece sewn to the body cloth's neckline with nothing turned over it (role collar_stand /
  neckband, no fall): the BAND stage's ring of its own neckline length, resting on the high points, upright; its top is
  its own free edge (a band's top is its seam to the fall). Built by build_stand(), never as a ring round a limb. Its
  ends meet at CF where the front below them is closed edge to edge; its own closure open = the top ends left free.
  A stiff piece whose role reads "collar_fall" with no roll fold is refused by name (a fall needs its roll; a collar
  that stands needs role collar_stand): the stand mistaken for a fall was T5's hussar sheet.
- RINGS: other wholly interfaced pieces (cuffs, waistbands).
- TUBE: a soft piece sewn to itself, OR several soft pieces of a limb role (sleeve, leg) on one side sewn to each other
  (a two-piece sleeve: top sleeve + undersleeve). A group is started round the limb's axis piece after piece, each over
  its share of the girth at that height (tube_group_points); every later stage treats its pieces as tube cloth.
- PANELS: every other soft piece, wrapped round the torso; a back cut in halves (back.L / back.R from a CB seam) counts
  as the back (its x runs from CB). The hem is the pattern's own outline: a cutaway, tails or a straight hem are only
  lengths, nothing is special-cased.
- FRONT: a closure between two pieces. Buttons LAP (the over side a layer outside the under, tied a layer apart); a ZIP
  with no seam is EDGE TO EDGE: its pairs are made along the two declared edges (zip_pairs, written into the pattern's
  closure so the reads see them), tied ZIP_GAP apart, no layer offset.
"""
from __future__ import annotations

import time

import numpy as np
from scipy.spatial import cKDTree

STAND_ROLES = ("collar_stand", "neckband")
TUBE_ROLES = ("sleeve", "leg_front", "leg_back")
EDGE_TO_EDGE = ("zip",)
ZIP_GAP = 0.002  # m: an edge-to-edge closure's two edges this far apart (the teeth between them), side by side
UPRIGHT_LEAN = 30.0  # deg: a stand STANDS: each of its heights within this of vertical, its top above its bottom by
# its height x cos(this) (the solve holds it; its own edge links then read against their cut, chain_read)
EDGE_TOL = 0.0015  # m: a border vertex this near a closure's declared edge is on it


def piece_roles(net) -> dict:
    from . import garment_design
    decl = net.M.get("roles") or {}
    return {n: decl.get(n) or garment_design.role_of(n) for n in net.names}


def edge_to_edge(front: dict | None) -> bool:
    return bool(front) and front.get("kind") in EDGE_TO_EDGE


def tie_gap(front: dict | None, layer: float) -> float:
    """How far apart a fastened pair is held: a lap's layer, an edge-to-edge closure's teeth."""
    return ZIP_GAP if edge_to_edge(front) else layer


def _on_edge(net, piece: str, poly) -> tuple:
    """(vertices, param 0..1 along the polyline) of a piece's border vertices on a declared edge polyline (flat uv)."""
    P = np.asarray(poly, float).reshape(-1, 2)
    v = net.verts(piece)
    border = np.asarray(net.M.get("border"), bool) if net.M.get("border") is not None else np.ones(net.n, bool)
    v = v[border[v]]
    if len(P) < 2 or not len(v):
        return np.zeros(0, int), np.zeros(0)
    seg = np.diff(P, axis=0)
    sl = np.linalg.norm(seg, axis=1)
    s0 = np.r_[0, np.cumsum(sl)]
    q = net.uv[v][:, None, :] - P[None, :-1]
    t = np.clip((q * seg[None]).sum(-1) / np.maximum(sl ** 2, 1e-12), 0, 1)
    d = np.linalg.norm(q - t[..., None] * seg[None], axis=-1)
    k = np.argmin(d, axis=1)
    on = d[np.arange(len(v)), k] <= EDGE_TOL
    par = (s0[k] + t[np.arange(len(v)), k] * sl[k]) / max(s0[-1], 1e-9)
    return v[on], par[on]


def zip_pairs(net, front: dict) -> dict:
    """An edge-to-edge closure without fastening marks: one pair per vertex along the over edge, matched to the under
    edge at the same share of its length. Written into the pattern's closure (the reads take its pairs from there)."""
    ex = front.get("edge_xy") or {}
    if front.get("v") or ex.get("over") is None or ex.get("under") is None:
        return front
    vo, to = _on_edge(net, front["over"], ex["over"])
    vu, tu = _on_edge(net, front["under"], ex["under"])
    if not len(vo) or not len(vu):
        return front
    k = cKDTree(tu[:, None]).query(to[:, None])[1]
    pairs = sorted(([int(a), int(vu[j])] for a, j in zip(vo, k)), key=lambda p: -net.uv[p[0], 1])
    closed = [front.get("state", "closed") == "closed"] * len(pairs)
    for c in net.M.get("closures") or []:
        if c.get("name") == front.get("name"):
            c["v"], c["closed"] = pairs, closed
    return dict(front, v=pairs, closed=closed)


def _tube_groups(net, soft: list, role: dict, self_sewn: set, sewn: dict) -> dict:
    """{piece: [its tube's pieces]}: a self-sewn soft piece alone; limb-role soft pieces of one side sewn to each other."""
    from .chain_garment import hand_of
    out = {p: [p] for p in soft if p in self_sewn}
    limb = [p for p in soft if role[p] in TUBE_ROLES and p not in out]
    seen: set = set()
    for p in limb:
        if p in seen:
            continue
        grp, todo = [], [p]
        while todo:
            q = todo.pop()
            if q in seen:
                continue
            seen.add(q)
            grp.append(q)
            todo += [r for r in sewn[q] if r in limb and r not in seen and hand_of(r) == hand_of(p)]
        if len(grp) > 1:
            grp = sorted(grp, key=lambda q: -float(net.uv[net.verts(q), 1].max() - net.uv[net.verts(q), 1].min()))
            for q in grp:
                out[q] = grp
    return out


def read_roles(net):
    """The pattern's roles (module doc). Raises ChainRefused naming a role the core can't build."""
    from .chain_garment import ChainRefused, Roles
    names = net.names
    role = piece_roles(net)
    whole = {n: float(net.stiff[net.verts(n)].mean()) > 0.95 for n in names}
    sewn: dict = {n: set() for n in names}
    self_sewn = set()
    for a, b in net.sew:
        pa, pb = names[net.piece[a]], names[net.piece[b]]
        if pa == pb:
            self_sewn.add(pa)
        else:
            sewn[pa].add(pb)
            sewn[pb].add(pa)
    fold = next((f for f in net.M.get("folds") or [] if f.get("kind") == "roll"), None)
    fall = fold["piece"] if fold else None
    fall_fault = None
    band, stand = None, False
    if fall:
        cand = [p for p in sewn[fall] if whole[p]]
        if not cand:
            raise ChainRefused(f"{fall}: a roll piece sewn straight to the body cloth (no interfaced band): a chain build "
                               "needs the band it stands on. next: add a band to the pattern (design_garment)")
        band = cand[0]
    else:
        on_body = [p for p in names if whole[p] and any(not whole[q] for q in sewn[p])]
        falls = [p for p in names if whole[p] and role[p] == "collar_fall"]  # (F1: sewn to a stand too, not only the body)
        if falls:
            fall_fault = (f"{falls[0]}: a stiff collar read as a FALL (role collar_fall) with no roll fold: a fall needs "
                          "its roll line; a collar that stands up needs role collar_stand (declare the piece's role, "
                          "draft_pattern pieces.<name>.role, or its roll fold)")
        stands = [p for p in on_body if role[p] in STAND_ROLES]
        if stands:
            band, stand = stands[0], True
    faults = sided_faults(net, role, whole, self_sewn) + ([fall_fault] if fall_fault else [])
    if faults:
        raise ChainRefused("the pattern's pieces don't make a whole garment: " + "; ".join(faults) + ". next: draft_pattern "
                           "declarations: a piece worn on both sides is declared twice, NAME.L and NAME.R (the .R one "
                           "`mirror: true`, which only flips a piece, never makes its pair), or cut on the fold "
                           "(`fold: x0`); pattern_check, chain_garment again")
    closures = net.M.get("closures") or []
    band_cl = next((c for c in closures if band and c["over"] == band), None)
    front = next((c for c in closures if c["over"] != c["under"]), None)
    if edge_to_edge(front):
        front = zip_pairs(net, front)
    rings = [n for n in names if whole[n] and n not in (band, fall)]
    soft = [n for n in names if not whole[n]]
    groups = _tube_groups(net, soft, role, self_sewn, sewn)
    tubes = [n for n in soft if n in groups]
    panels = [n for n in soft if n not in groups]
    return Roles(band, fall, rings, tubes, panels, front, band_cl, fold, stand=stand,
                 tube_groups={k: v for k, v in groups.items() if len(v) > 1})


SIDE_TOL = 0.01  # m: a centre piece's flat is centred on x = 0 within this + 10 % of its width, else it is a half


def sided_faults(net, role: dict, whole: dict, self_sewn: set) -> list:
    """(F1, t8) Pieces the body wears on both sides drafted once: a soft centre piece (no .L / .R) lying wholly on one
    side of the centre line is half of what the body wears (the t8 shirt's `front`, `mirror: true` taken for "cut
    two": its button lap crossed x = 0 by 18 mm, the t8 trousers' crotch by 60-120 mm); a limb piece (a tube, a limb role) with no side has no limb to go round. Each named; stiff pieces never
    (a band's ends are its own)."""
    from .chain_garment import hand_of
    out = []
    for n in net.names:
        if hand_of(n) != 0 or whole[n]:
            continue
        if n in self_sewn or role[n] in TUBE_ROLES:
            out.append(f"{n}: a limb piece with no side (.L / .R)")
            continue
        x = net.uv[net.verts(n), 0]
        if abs(x.min() + x.max()) / 2 > 0.1 * float(np.ptp(x)) + SIDE_TOL:  # (off centre: a lap or a crotch crosses x = 0)
            out.append(f"{n}: half a garment (its flat lies off the centre line, x {x.min() * 1e3:.0f} to "
                       f"{x.max() * 1e3:.0f} mm) with no other half")
    return out


# ---- a tube of several pieces
def _rows(xa, ya):
    """Per 10 mm height bin: (x low, x high) of a piece."""
    bins = np.round(ya / 0.01).astype(int)
    return {int(k): (float(xa[bins == k].min()), float(xa[bins == k].max())) for k in np.unique(bins)}


def _sides(b, p, q):
    """Which x-side of piece p (-1 low, +1 high) is sewn to piece q, and which side of q it meets."""
    uv = b.net.uv
    s = b.sewn_with(p, q)
    if not s:
        return None
    cp, cq = np.median(uv[b.net.verts(p), 0]), np.median(uv[b.net.verts(q), 0])
    a = np.array(list(s.keys()))
    c = np.array(list(s.values()))
    return float(np.sign(np.mean(uv[a, 0]) - cp)), float(np.sign(np.mean(uv[c, 0]) - cq))


def _loop(b, grp):
    """The group's pieces round the limb: [(piece, direction)], direction +1 = low x -> high x."""
    order = [(grp[0], 1.0)]
    while len(order) < len(grp):
        p, d = order[-1]
        nxt = None
        for q in grp:
            if q in [o[0] for o in order]:
                continue
            for sp, sq in ([_sides(b, p, q)] if _sides(b, p, q) else []):
                if sp == d:  # p's exit side (its high side going +1) meets q: q enters from that side
                    nxt = (q, -sq)
            if nxt:
                break
        if nxt is None:
            nxt = next((q, 1.0) for q in grp if q not in [o[0] for o in order])
        order.append(nxt)
    return order


def tube_group_points(b, t, v):
    """Vertices v of piece t (one piece of a several-piece tube) at their start: round the limb's axis, each piece over
    its share of the girth at that height (heights from the wrist end up), the top piece's middle on the limb's outer
    side, turning so the cloth sewn to the front panel faces front."""
    from .chain_garment import LimbAxis, hand_of
    net, R = b.net, b.roles
    uv = net.uv
    grp = R.tube_groups[t]
    side = hand_of(t)
    ax = b.axes.setdefault(side, LimbAxis(b.body, side)) if hasattr(b, "axes") else LimbAxis(b.body, side)
    info = {}
    for p in grp:
        pv = net.verts(p)
        xa, ya = uv[pv, 0], uv[pv, 1]
        y0 = float(ya.min())
        rows = _rows(xa, ya - y0)
        wk = {k: max(hi - lo, 0.03) for k, (lo, hi) in rows.items()}
        kw = max(wk, key=wk.get)
        info[p] = dict(y0=y0, rows=rows, w=wk, kw=kw, wide=wk[kw], top=int(max(rows)))
    H = max((float(uv[net.verts(p), 1].max()) - info[p]["y0"]) for p in grp)

    def width(p, k):
        f = info[p]
        if k >= f["kw"]:
            return f["wide"]  # the cap (rows above the widest): whole width, so its edge rings the armhole
        k = min(max(k, min(f["w"])), f["top"])
        while k not in f["w"]:
            k += 1
        return f["w"][k]

    def lohi(p, k):
        f = info[p]
        k = min(max(k, min(f["rows"])), f["top"])
        while k not in f["rows"]:
            k += 1
        lo, hi = f["rows"][k]
        return lo, max(hi, lo + 1e-3)

    order = _loop(b, grp)

    def phase(p, x, y):
        h = y - info[p]["y0"]
        k = np.round(h / 0.01).astype(int)
        out = np.zeros(len(x))
        for i, (xx, kk) in enumerate(zip(x, k)):
            W = sum(width(q, kk) for q, _ in order)
            off = 0.0
            for q, d in order:
                if q == p:
                    lo, hi = lohi(q, kk)
                    fr = (xx - lo) / (hi - lo)
                    fr = fr if d > 0 else 1 - fr
                    out[i] = 2 * np.pi * (off + np.clip(fr, 0, 1) * width(q, kk)) / W
                    break
                off += width(q, kk)
        return out

    top = grp[0]  # the longest piece: the top sleeve, its middle on the outer side
    tv = net.verts(top)
    mid_y = float(uv[tv, 1].max()) - 0.05
    mid = phase(top, np.array([float(np.median(uv[tv, 0]))]), np.array([mid_y]))[0]
    fp = [(q, pp) for q in grp for pp in R.panels if b.sewn_with(q, pp) and R.front and pp in (R.front["over"], R.front["under"])]
    sf = 1.0
    if fp:
        q, pp = fp[0]
        a = np.array(list(b.sewn_with(q, pp).keys()))
        ph = np.angle(np.exp(1j * (phase(q, uv[a, 0], uv[a, 1]) - mid)))
        sf = float(np.sign(np.mean(ph))) or 1.0
    s_end = H
    x, y = uv[v, 0], uv[v, 1]
    ph = (phase(t, x, y) - mid) * sf
    s = (H - (y - info[t]["y0"])) * s_end / H
    Wv = np.array([sum(width(q, int(round((yy - info[t]["y0"]) / 0.01))) for q, _ in order) for yy in y])
    Cc, o, f, d = ax.at(s)
    return Cc + (np.cos(ph)[:, None] * o + np.sin(ph)[:, None] * f) * (Wv / (2 * np.pi))[:, None]


# ---- the stand
def _top_edge(net, piece, sb):
    """A stand's free top edge, in outline order and the neck chain's direction: the outline arc off the neck seam less
    its two END edges. An end edge rises from an end of the neck edge: each of its points lies nearest that END (its foot
    on the neck polyline clamps to the end vertex); a top point's foot is inside; the top is ordered by its feet. Border
    vertices from the mesh's border mask, not loop(): its walk stopped at the first end corner. (F1: "farthest from the neck seam"
    kept only the tallest ear of a stand taller at its ends than at CB: 13 of its top vertices, 20 mm of 470, and the
    rest of the stand stood on nothing and fell.)"""
    v = net.verts(piece)
    border = np.asarray(net.M["border"], bool) if net.M.get("border") is not None else None
    arc = v[border[v]] if border is not None else np.asarray(net.loop(piece))
    arc = arc[~np.isin(arc, sb)]
    P = net.uv[sb]
    seg = np.diff(P, axis=0)
    sl = np.sqrt(np.maximum((seg ** 2).sum(1), 1e-12))
    q = net.uv[arc][:, None, :] - P[None, :-1]
    t = (q * seg[None]).sum(-1) / sl ** 2
    tc = np.clip(t, 0, 1)
    d = np.linalg.norm(q - tc[..., None] * seg[None], axis=-1)
    j = np.argmin(d, axis=1)
    tj = t[np.arange(len(arc)), j]
    end = ((j == 0) & (tj <= 0)) | ((j == len(seg) - 1) & (tj >= 1))
    s0 = np.r_[0, np.cumsum(sl)]
    foot = s0[j] + np.clip(tj, 0, 1) * sl[j]  # (where along the neck edge each point stands: the top's order)
    top = arc[~end][np.argsort(foot[~end])] if (~end).sum() >= 2 else arc[np.argsort(foot)]
    # (a top far shorter than the neck edge is no top: read it whole and let the lengths speak)
    return top[::-1] if net.uv[top[0], 0] > net.uv[top[-1], 0] else top


def stand_ring(b):
    """The STAND: the band stage's ring with its own top edge (module doc). Sets b.sb / b.st / b._band_lines like
    band_closed, so fill_band, stiff_last and the soft network hold it as they hold a band."""
    import math
    from . import chain_net as cn
    from .chain_garment import GAP, REST, ChainRefused, hand_of
    from .chain_net import BendSolve
    from .chain_rest import rest_ring
    net, R = b.net, b.roles
    uv, rs = net.uv, net.root
    soft_sewn = set()
    for p in R.panels:
        soft_sewn |= set(b.sewn_with(R.band, p))
    if len(soft_sewn) < 4:
        raise ChainRefused(f"{R.band}: a stand not sewn to the body cloth's neckline. next: sew its neck edge (draft_pattern)")
    sb = b.order_x(soft_sewn)
    st = _top_edge(net, R.band, sb)
    LB = np.linalg.norm(np.diff(uv[sb], axis=0), axis=1)
    sB = np.r_[0, np.cumsum(LB)]
    C = float(sB[-1])
    mid = int(np.argmin(np.abs(sB - C / 2)))
    left = [p for p in R.panels if hand_of(p) > 0 and b.sewn_with(R.band, p)]
    su = float(np.sign(np.mean([uv[q, 0] for q in b.sewn_with(R.band, left[0])]) - uv[sb[mid], 0])) if left else 1.0
    a, bb_, yc, zc, dz = b._neck_ring(C)
    th = (sB - sB[mid]) / C * 2 * np.pi * su
    hz = b.body.p("hps.L")[2]
    B = np.c_[a * np.sin(th), yc + bb_ * np.cos(th), zc + dz * np.cos(th) + (hz - zc) * np.sin(th) ** 2]
    sidep = B[np.argmax(B[:, 0])]
    B, b.reads["band_rest"] = rest_ring(B, b.body.contact, GAP, np.array([0.0, sidep[1], sidep[2]]))
    kb = cKDTree(uv[sb])
    cross = np.array([(j, int(kb.query(uv[v])[1])) for j, v in enumerate(st)])
    hgt = np.linalg.norm(uv[st] - uv[sb[cross[:, 1]]], axis=1)
    for phi in np.radians(np.arange(0, 41, 2.5)):  # it leans with the neck: the least tilt forward that clears it
        T = B[cross[:, 1]] + np.array([0.0, -math.sin(phi), math.cos(phi)]) * hgt[:, None]
        if b.body.contact.query(T)[0].min() >= GAP:
            break
    b.X[rs[sb]] = B
    b.X[rs[st]] = T
    nb, nt = rs[sb], rs[st]
    cbn = rs[sb[mid]]
    free = np.unique(np.r_[nb, nt])
    free = free[free != cbn]
    S = BendSolve(b.X, free)
    Lt = np.linalg.norm(np.diff(uv[st], axis=0), axis=1)
    S.add_links(nb[:-1], nb[1:], LB, np.ones(len(LB), bool))
    S.add_links(nt[:-1], nt[1:], Lt, np.ones(len(st) - 1, bool))
    ev = cross[np.unique(np.r_[np.arange(0, len(cross), 4), len(cross) - 1])]  # (the end corners too: free, the stand's
    # end edges ran 41 % past their cut)
    S.add_links(nt[ev[:, 0]], nb[ev[:, 1]], hgt[ev[:, 0]], np.ones(len(ev), bool))
    S.add_bend(nb, cn.BEND_BASE * net.bend[sb[1:-1]])
    S.add_bend(nt, cn.BEND_BASE * net.bend[st[1:-1]])
    S.add_contact(nt, b.body.contact, GAP)
    S.add_contact(nb, b.body.contact, GAP, rest=REST)
    rows = []
    front_shut = bool(R.front) and all(R.front.get("closed") or [False])
    ends = [(nb[0], nb[-1])] if front_shut else []  # the fronts below meet at CF: so do the stand's neck ends
    if R.band_closure and all(R.band_closure.get("closed") or [False]):
        ends.append((nt[0], nt[-1]))  # its own closure done: the top ends meet too
    for p0, p1 in ends:
        rows += [([p0], [1.0], 0, 0.0, cn.HARD), ([p1], [1.0], 0, 0.0, cn.HARD),
                 ([p0, p1], [1.0, -1.0], 1, 0.0, cn.HARD), ([p0, p1], [1.0, -1.0], 2, 0.0, cn.HARD)]
    sT = np.r_[0, np.cumsum(Lt)]
    for chain, s, m in ((nb, sB, mid), (nt, sT, int(np.argmin(np.abs(cross[:, 1] - mid))))):  # worn straight: mirror
        mj = np.searchsorted(s, 2 * s[m] - s).clip(0, len(s) - 1)
        for q in range(len(chain)):
            if q < m and mj[q] > m:
                rows += [([chain[q], chain[mj[q]]], [1.0, 1.0], 0, 0.0, 1.0),
                         ([chain[q], chain[mj[q]]], [1.0, -1.0], 1, 0.0, 1.0),
                         ([chain[q], chain[mj[q]]], [1.0, -1.0], 2, 0.0, 1.0)]
    S.add_linear(rows)

    hz_ = hgt[ev[:, 0]] * np.cos(np.radians(UPRIGHT_LEAN))

    def upright(Y):  # it stands: its top above its bottom by its own height (within UPRIGHT_LEAN of vertical; F1: a
        # flat 12 mm let an 80 mm stand lie out at 30 deg)
        d = Y[nt[ev[:, 0]], 2] - Y[nb[ev[:, 1]], 2] - hz_
        bad = d < 0
        m = len(ev)
        g = np.zeros((m, 3))
        g[:, 2] = 10.0 * bad
        k = np.arange(m)
        return 10 * np.where(bad, d, 0.0), np.r_[k, k], np.r_[nt[ev[:, 0]], nb[ev[:, 1]]], np.r_[g, -g]
    S.add_fn(upright)
    b.X = S.solve(60)
    b.sb, b.st = sb, st
    b._band_lines = (nb, nt, ev, hgt, LB)
    b._band_project(held=np.isin(np.arange(net.n), [cbn]))
    b.reads["band"] = b._band_read()
    up = b.X[nt[ev[:, 0]]] - b.X[nb[ev[:, 1]]]
    rise = np.degrees(np.arctan2(up[:, 2], np.linalg.norm(up[:, :2], axis=1)))
    cbk = int(np.argmin(np.abs(ev[:, 1] - mid)))
    lt = np.linalg.norm(np.diff(b.X[nt], axis=0), axis=1)
    b.reads["stand"] = {"rise_deg_median": round(float(np.median(rise)), 1), "rise_deg_min": round(float(rise.min()), 1),
                        "rise_deg_cb": round(float(rise[cbk]), 1), "ends_meet": [bool(e) for e in (front_shut,)],
                        "top_mm": [round(float(lt.sum() * 1e3), 1), round(float(Lt.sum() * 1e3), 1)],
                        "neck_mm": round(float(LB.sum() * 1e3), 1),
                        "top_worst_link_pct": round(float(np.abs(lt / np.maximum(Lt, 1e-9) - 1).max() * 100), 1)}


def build_stand(b, t0: float) -> None:
    """A garment whose collar is a STAND: the stand's ring, its surface and edges, rings, then the soft cloth under it
    (closed front: fastened edge to edge or lapped as its closure says)."""
    stand_ring(b)
    b.fill_band()
    b.stiff_last()
    b.rings()
    b.reads["stiff_stand_s"] = round(time.time() - t0, 1)
    b.soft_net()


# ---- held lengths (F1)
def held_read(b, X, both, e, over) -> dict:
    """Links with both ends held to stiff parts, read against their cut (F1: a stand's own edges read 237-278 % over and
    went uncounted because both ends were held): a STIFF piece's own edge / fold link is a length (exact either way);
    a soft link gathered into a stiff part may be shorter, never longer. Worst of either, by piece and line."""
    net, R = b.net, b.roles
    stiff = [net.pid(p) for p in [R.band, R.fall] + list(R.rings) if p]
    pi, pj = net.piece[net.link_i], net.piece[net.link_j]
    own = both & (pi == pj) & np.isin(pi, stiff)
    gath = both & ~own
    err = np.where(own, e, np.where(gath, np.maximum(over, 0.0), 0.0))
    if not (own | gath).any() or err.max() <= 0:
        return {"held_worst_pct": 0.0, "held_worst_line": ""}
    k = int(np.argmax(err))
    c = int(np.where(net.link_of_chain == k)[0][0])
    nm = net.names[net.chain_piece[c]]
    line = (f"{nm} {'fold line' if net.chain_kind[c] else 'edge'} at flat ({net.uv[net.link_i[k], 0]:.3f}, "
            f"{net.uv[net.link_i[k], 1]:.3f}){b._near_point(int(net.link_i[k]), nm)}"
            + (" (a stiff piece's own length)" if own[k] else " (gathered into a stiff part: longer than its cut)"))
    return {"held_worst_pct": round(float(err[k]), 3), "held_worst_line": line,
            "stiff_own_worst_pct": round(float(e[own].max()), 3) if own.any() else 0.0}


# ---- a stiff band on a body loop (F1)
def torso_hull(body, z: float, dz: float = 0.012):
    """The torso's convex section at height z (arms left out as TorsoRings does), or None."""
    from scipy.spatial import ConvexHull
    V = body.V
    sx = abs(float(body.p("shoulder.L")[0]))
    pit = float(body.at["armpit_z"])
    lim = sx if z >= pit + 0.03 else min(0.83 * sx + max(pit - 0.03 - z, 0.0) * 0.4, 1.25 * sx)
    s = V[(np.abs(V[:, 2] - z) < dz) & (np.abs(V[:, 0]) < lim), :2]
    if len(s) < 6:
        return None
    s = np.r_[s, s * [-1, 1]]
    return s[ConvexHull(s).vertices]


def _perim(h) -> float:
    return float(np.linalg.norm(np.diff(np.r_[h, h[:1]], axis=0), axis=1).sum())


def _loop_at(h, C: float, frac):
    """Points at fractions `frac` (0 = centre front, going +X) round hull h offset outward until its length is C."""
    from .chain_garment import unit
    t = (C - _perim(h)) / (2 * np.pi)
    e = np.diff(np.r_[h[-1:], h, h[:1]], axis=0)
    nn = unit(np.c_[e[:, 1], -e[:, 0]])
    Q = h + unit(nn[:-1] + nn[1:]) * t
    k = int(np.argmin(np.abs(Q[:, 0]) + 10 * (Q[:, 1] > Q[:, 1].mean())))  # (centre front: x ~ 0, the -Y side)
    Q = np.roll(Q, -k, axis=0)
    Q = np.r_[Q, Q[:1]]
    sa = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    sq = (np.asarray(frac) % 1.0) * sa[-1]
    return np.c_[np.interp(sq, sa, Q[:, 0]), np.interp(sq, sa, Q[:, 1])]  # (a hull runs CCW from above: +X after CF)


def body_ring(b, ring: str) -> None:
    """A wholly stiff CENTRE piece closed on its own closure (a waistband, a belt): a band round the torso's loop.
    Its height: where its seam to the body cloth starts (hps z + the panels' flat y, as soft_start places them); sewn
    to nothing (a belt), where the torso's loop first takes its closed length, nearest the waist. Its closed length
    (between its closure's marks) round the torso's convex section over its height, offset out to that length; the
    marks at centre front, the part past them lapped a layer over. Refused by name: no closure; shorter than the body."""
    from .chain_garment import ChainRefused, GAP, LAYER, RING_GAP, hand_of, unit
    net, R = b.net, b.roles
    uv = net.uv
    cl = next((c for c in net.M.get("closures") or [] if c["over"] == ring), None)
    if cl is None or not cl.get("v"):
        raise ChainRefused(f"{ring}: a band round the body with no closure of its own: it can't close. next: add its "
                           "fastening to the pattern (draft_pattern closures)")
    rv = net.verts(ring)
    a, c_ = cl["v"][0]
    ua, ub = sorted((float(uv[a, 0]), float(uv[c_, 0])))
    C = ub - ua
    hz = float(b.body.p("hps.L")[2])
    sewn = {}
    for p in R.panels + list(R.tubes):
        sewn.update({v: q for v, q in b.sewn_with(ring, p).items()})
    u, v = uv[rv, 0], uv[rv, 1]
    if sewn:
        sv = np.array(list(sewn.keys()))
        z0 = hz + float(np.mean(uv[list(sewn.values()), 1]))
        vs = float(np.mean(uv[sv, 1]))
        free_up = float(np.mean(v)) >= vs  # (the band's cloth off its seam goes up the body: the panels hang below)
        z = z0 + (v - vs) * (1.0 if free_up else -1.0)
        how = "its seam's height"
    else:
        wz = float(b.body.at["waist_z"])
        zs = np.arange(float(b.body.at["crotch_z"]) + 0.03, float(b.body.at["armpit_z"]) - 0.03, 0.005)
        ok = [zz for zz in zs if (h := torso_hull(b.body, zz)) is not None and _perim(h) + 2 * np.pi * RING_GAP <= C]
        if not ok:
            raise ChainRefused(f"{ring}: closed length {C * 1e3:.0f} mm is shorter than the torso at every height between "
                               "the crotch and the armpits. next: lengthen it in the pattern (draft_pattern), or close it "
                               "on a later hole")
        z0 = min(ok, key=lambda zz: abs(zz - wz))
        z = z0 + (v - float(np.mean(v)))
        how = "where the torso takes its closed length, nearest the waist"
    hs = [h for zz in np.linspace(z.min(), z.max(), 5) if (h := torso_hull(b.body, float(zz))) is not None]
    if not hs:
        raise ChainRefused(f"{ring}: no torso at its height ({z0:.3f} m). next: check its placement (draft_pattern place)")
    from scipy.spatial import ConvexHull
    allp = np.concatenate(hs)
    h = allp[ConvexHull(allp).vertices]
    need = _perim(h) + 2 * np.pi * RING_GAP
    if C < need:
        raise ChainRefused(f"{ring}: closed length {C * 1e3:.0f} mm is shorter than the body's loop at its height "
                           f"({need * 1e3:.0f} mm with its gap): it can't close round the body. next: lengthen it in the "
                           "pattern (draft_pattern), pattern_check, chain_garment again")
    left = [p for p in R.panels if hand_of(p) > 0 and b.sewn_with(ring, p)]
    su = 1.0
    if left:
        lv = np.array(list(b.sewn_with(ring, left[0]).keys()))
        su = float(np.sign(np.mean(uv[lv, 0]) - 0.5 * (ua + ub))) or 1.0
    frac = su * (u - ub) / C  # (0 at a mark: centre front; the part past the other mark laps over)
    P = _loop_at(h, C, frac)
    lap = LAYER * ((u < ua - 1e-6) | (u > ub + 1e-6))
    cen = P.mean(0)
    P = P + unit(P - cen) * lap[:, None]
    X3 = np.c_[P, z]
    b.X[rv] = X3
    b.X[net.root[rv]] = X3
    gap = float(b.body.contact.query(X3)[0].min())
    b.reads.setdefault("rings", {})[ring] = {"body_loop": how, "z_mm": round(z0 * 1e3, 1), "closed_mm": round(C * 1e3, 1),
                                             "loop_mm": round(_perim(h) * 1e3, 1), "min_gap_mm": round(gap * 1e3, 2)}
    if gap < min(GAP, RING_GAP) * 0.5:
        raise ChainRefused(f"{ring}: built {gap * 1e3:.1f} mm off the body (inside it) at its height: its section can't "
                           "take the band's shape. next: tell the coordinator (body_ring); don't fit it another way")
