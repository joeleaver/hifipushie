"""CHAIN ROLES (garment_steps T8, C289): the roles a chain build reads from ANY pattern, beyond a collared shirt.

Joe (2026-11-02): every garment is built by the same general chain build, from its pattern; nothing garment-specific.
A role comes from the pattern's construction (what is interfaced, what is sewn to what, which fold rolls, which closure
joins which pieces) plus the piece's declared role (draft_pattern's `role`, carried on the flat mesh as M["roles"];
else the role its name reads as, garment_design.role_of). Names never pick a stage on their own.

- WHAT HOLDS WHAT (R3b): chain_holds.read. Plies and floating layers get no role here (they follow their host:
  chain_holds.place_plies); a roll fold makes a FALL only on a stiff part (a soft piece's roll is its own fold, a lapel).
- FALL: a piece with a "roll" fold. BAND: the wholly interfaced piece the fall is sewn to (a shirt's collar band).
- STAND (R3c, C399): a wholly interfaced part resting on the body, sewn along the body cloth's NECKLINE (neck_part: its
  seam to the panels reaches within NECK_REACH of the high point, where the panels' own lengths put them), with nothing
  sewn on top of it: the BAND stage's ring of its own neckline length, resting on the high points, upright; its top is its
  own free edge (a band's top is its seam to the fall). Built by stand_ring(), never as a ring round a limb. Its neck
  ends meet at CF where the front's top pair is tied; its own closure untied = the top ends left free. Read from the
  construction only: a declared role or a name never makes a stand (it did: collar_stand / neckband; a stiff collar
  with no roll whose name read collar_fall was refused, the suit jacket's collar among them).
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


import numpy as np
from scipy.spatial import cKDTree

NECK_REACH = 0.10  # m: a stiff part's seam to the body cloth reaching this near the high point's height is on the neckline
# (a collar's seam starts at the hps; a waistband's is 0.4 m or more below it)
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
    from .chain_holds import read as read_holds  # (R3b: plies and floating layers have no role of their own)
    H = read_holds(net)
    carried = set(H.plies) | set(H.layers)
    names = [n for n in net.names if n not in carried]
    role = piece_roles(net)
    whole = {n: float(net.stiff[net.verts(n)].mean()) > 0.95 for n in net.names}
    sewn: dict = {n: set() for n in net.names}
    self_sewn = set()
    for a, b in net.sew:
        pa, pb = net.names[net.piece[a]], net.names[net.piece[b]]
        if pa == pb:
            self_sewn.add(pa)
        else:
            sewn[pa].add(pb)
            sewn[pb].add(pa)
    fold = next((f for f, h in zip(net.M.get("folds") or [], H.folds) if h["fall"]), None)  # (a FALL: a stiff part's roll)
    fall = fold["piece"] if fold else None
    band, stand = None, False
    if fall:
        cand = [p for p in sewn[fall] if whole[p] and p not in carried]
        if not cand:
            raise ChainRefused(f"{fall}: a roll piece sewn straight to the body cloth (no interfaced band): a chain build "
                               "needs the band it stands on. next: add a band to the pattern (design_garment)")
        band = cand[0]
    # (no fall: a stand on the neckline is read by the build, which knows the body: neck_part)
    faults = sided_faults(net, role, whole, self_sewn, carried)
    if faults:
        raise ChainRefused("the pattern's pieces don't make a whole garment: " + "; ".join(faults) + ". next: draft_pattern "
                           "declarations: a piece worn on both sides is cut 2 as a mirrored pair, pieces.NAME {\"pair\": true} "
                           "(NAME.L + NAME.R, seams per side; `mirror: true` only flips a piece, never makes its pair), "
                           "or cut on the fold (`fold: x0`); pattern_check, chain_garment again")
    closures = net.M.get("closures") or []
    band_cl = next((c for c in closures if band and c["over"] == band), None)
    front = next((c for c in closures if c["over"] != c["under"]), None)
    if edge_to_edge(front):
        front = zip_pairs(net, front)
    rings = [n for n in names if whole[n] and n not in (band, fall)]
    soft = [n for n in names if not whole[n]]
    from .piece_start import tube_groups as measured_tubes  # (F4: a tube by where its own girths were taken)
    groups = measured_tubes(net, soft, sewn, self_sewn)
    groups.update({k: v for k, v in _tube_groups(net, [n for n in soft if n not in groups], role, self_sewn, sewn).items()
                   if k not in groups})
    tubes = [n for n in soft if n in groups]
    panels = [n for n in soft if n not in groups]
    return Roles(band, fall, rings, tubes, panels, front, band_cl, fold, stand=stand,
                 tube_groups={k: v for k, v in groups.items() if len(v) > 1}, holds=H)


SIDE_TOL = 0.01  # m: a centre piece's flat is centred on x = 0 within this + 10 % of its width, else it is a half


def sided_faults(net, role: dict, whole: dict, self_sewn: set, skip=()) -> list:
    """(F1, t8) Pieces the body wears on both sides drafted once: a soft centre piece (no .L / .R) lying wholly on one
    side of the centre line is half of what the body wears (the t8 shirt's `front`, `mirror: true` taken for "cut
    two": its button lap crossed x = 0 by 18 mm, the t8 trousers' crotch by 60-120 mm); a limb piece (a tube, a limb role) with no side has no limb to go round. Each named; stiff pieces never
    (a band's ends are its own)."""
    from .chain_garment import hand_of
    out = []
    for n in net.names:
        if hand_of(n) != 0 or whole[n] or n in skip:
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
    from .chain_garment import hand_of
    net, R = b.net, b.roles
    uv = net.uv
    grp = R.tube_groups[t]
    side = hand_of(t)
    from .piece_start import axis_for
    ax = axis_for(b, t)
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


def _end_edges(net, piece, sb, st):
    """(F3) A stand's two END edges as chains [neck end, ..., top end]: the border vertices on neither the neck seam nor
    the top, each given to the end whose neck and top corners are nearer, ordered from the neck up (projection on the
    chord neck end -> top end). The cut lengths between them are the stand's own lengths (held_read reads them)."""
    v = net.verts(piece)
    border = np.asarray(net.M["border"], bool) if net.M.get("border") is not None else None
    arc = v[border[v]] if border is not None else np.asarray(net.loop(piece))
    arc = arc[~np.isin(arc, sb) & ~np.isin(arc, st)]
    uv = net.uv
    out = []
    for e, (nb_, nt_) in enumerate(((sb[0], st[0]), (sb[-1], st[-1]))):
        o = (sb[-1], st[-1]) if e == 0 else (sb[0], st[0])
        d_me = np.linalg.norm(uv[arc] - uv[nb_], axis=1) + np.linalg.norm(uv[arc] - uv[nt_], axis=1)
        d_ot = np.linalg.norm(uv[arc] - uv[o[0]], axis=1) + np.linalg.norm(uv[arc] - uv[o[1]], axis=1)
        mine = arc[d_me < d_ot]
        ch = uv[nt_] - uv[nb_]
        t = ((uv[mine] - uv[nb_]) @ ch) / max(float(ch @ ch), 1e-12)
        mine = mine[(t > 0) & (t < 1)]
        out.append(np.r_[nb_, mine[np.argsort(t[(t > 0) & (t < 1)])], nt_].astype(np.int64))
    return out


def neck_part(b) -> str | None:
    """The stiff part sewn along the body cloth's neckline (module doc, STAND): the band under a fall, else the first
    stiff ring-candidate resting on the body whose seam to the panels reaches within NECK_REACH of the high point (each
    panel where its own lengths start it, piece_start.panel_dz). That one becomes R.band (stand), out of R.rings, and its
    own closure is R.band_closure. Construction only: never a name or a declared role."""
    from .piece_start import panel_dz
    net, R = b.net, b.roles
    if R.band:
        return R.band
    hz = float(b.body.p("hps.L")[2])
    for part in b.holds.parts:
        p = part.outer
        if not part.stiff or part.rests_on != ["body"] or p not in R.rings:
            continue
        top = [hz + float(net.uv[list(sv), 1].max()) + panel_dz(b, q) for q in R.panels
               if (sv := b.sewn_with(q, p))]
        if top and max(top) >= hz - NECK_REACH:
            R.band, R.stand = p, True
            R.rings = [r for r in R.rings if r != p]
            R.band_closure = next((c for c in net.M.get("closures") or [] if c["over"] == p), None)
            b.reads["neck_part"] = {"part": p, "seam_top_below_hps_mm": round((hz - max(top)) * 1e3, 1)}
            return p
    return None


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
    # (F3) the END edges in the solve: chains neck end -> top end at their cut, started on the straight between their
    # corners (F1: left out, they were filled afterwards and the stand's border ran 39.8 % past its cut at a top corner)
    ends_v = _end_edges(net, R.band, sb, st)
    ends_c = []
    for E in ends_v:
        Le = np.linalg.norm(np.diff(uv[E], axis=0), axis=1)
        f_ = np.r_[0, np.cumsum(Le)] / max(float(Le.sum()), 1e-9)
        b.X[rs[E[1:-1]]] = (1 - f_[1:-1, None]) * b.X[rs[E[0]]] + f_[1:-1, None] * b.X[rs[E[-1]]]
        ends_c.append((rs[E], Le))
    free = np.unique(np.r_[nb, nt] if not ends_v else np.r_[nb, nt, np.concatenate([rs[E] for E in ends_v])])
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
    for (ne, Le), E in zip(ends_c, ends_v):
        S.add_links(ne[:-1], ne[1:], Le, np.ones(len(Le), bool))
        if len(E) > 2:
            S.add_bend(ne, cn.BEND_BASE * net.bend[E[1:-1]])
            S.add_contact(ne[1:-1], b.body.contact, GAP)
    S.add_contact(nt, b.body.contact, GAP)
    S.add_contact(nb, b.body.contact, GAP, rest=REST)
    rows = []
    from .chain_plan import top_tied
    front_shut = top_tied(R.front, uv)  # (C399: the front's TOP pair tied; was every pair, the pairs above dropped)
    ends = [(nb[0], nb[-1])] if front_shut else []  # the fronts below meet at CF: so do the stand's neck ends
    if getattr(b, "band_tied", False):  # (C399: as its tie says, chain_garment.Build.band_tied)
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
    b._end_links = (np.concatenate([ne[:-1] for ne, _ in ends_c]), np.concatenate([ne[1:] for ne, _ in ends_c]),
                    np.concatenate([Le for _, Le in ends_c])) if ends_c else None
    b.se = np.concatenate([E[1:-1] for E in ends_v]) if ends_v else np.zeros(0, np.int64)  # (fill_band keeps them)
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
                        "top_worst_link_pct": round(float(np.abs(lt / np.maximum(Lt, 1e-9) - 1).max() * 100), 1),
                        "end_edges_mm": [[round(float(np.linalg.norm(np.diff(b.X[ne], axis=0), axis=1).sum() * 1e3), 1),
                                          round(float(Le.sum() * 1e3), 1)] for ne, Le in ends_c],
                        "end_worst_link_pct": round(max([float(np.abs(np.linalg.norm(np.diff(b.X[ne], axis=0), axis=1)
                                                                     / np.maximum(Le, 1e-9) - 1).max() * 100)
                                                         for ne, Le in ends_c] or [0.0]), 1)}
