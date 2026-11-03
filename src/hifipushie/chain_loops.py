"""CHAIN LOOPS (F1, after blind trial t8): what the chain build reads beyond a collar band.

- body_ring: a wholly stiff CENTRE piece closed on its own closure (a waistband, a belt) is a band round a body loop:
  at its seam's height when sewn to the body cloth, else where the torso takes its closed length nearest the waist;
  refused by name when it has no closure or is shorter than the body there. (t8: the build only knew rings on a limb.)
- held_read: links held at both ends are lengths too: a stiff piece's own edge links exact, a soft link gathered into a
  stiff part never longer than its cut (t8 / r-hussar: a stand's edges read 237-278 % over, uncounted).
"""
from __future__ import annotations

import numpy as np

# ---- held lengths (F1)
def held_read(b, X, both, e, over) -> dict:
    """Links with both ends held to stiff parts, read against their cut (F1: a stand's own edges read 237-278 % over and
    went uncounted because both ends were held): a STIFF piece's own edge / fold link is a length (exact either way);
    a soft link gathered into a stiff part may be shorter, never longer. Worst of either, by piece and line."""
    net, R = b.net, b.roles
    stiff = [net.pid(p) for p in [R.band, R.fall] + list(R.rings) if p]
    lp = np.full(len(net.link_i), -1)
    lp[net.link_of_chain] = net.chain_piece  # (each link's own piece: its ends may be roots on a sewn partner)
    own = both & np.isin(lp, stiff)
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


def _sewn_start_z(b, ring: str, hz: float) -> float:
    """The mean start height of the body cloth the ring is sewn to, as soft_start will place it (F4: a tube round its
    own measurements, a panel between its tapes; no measurements: hung from the hps)."""
    from .piece_start import panel_dz
    net, R = b.net, b.roles
    zs = []
    for p in R.panels + list(R.tubes):
        vv = np.array(list(b.sewn_with(ring, p).values()), int)
        if not len(vv):
            continue
        if p in R.tubes:
            zs += b._tube_points(p, vv)[:, 2].tolist()
        else:
            zs += (hz + net.uv[vv, 1] + panel_dz(b, p)).tolist()
    return float(np.mean(zs))


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
        z0 = _sewn_start_z(b, ring, hz)
        vs = float(np.mean(uv[sv, 1]))
        free_up = float(np.mean(v)) >= vs  # (the band's cloth off its seam goes up the body: the panels hang below)
        z = z0 + (v - vs) * (1.0 if free_up else -1.0)
        how = "its seam's height"
    else:
        wz = float(b.body.at["waist_z"])
        zs = np.arange(float(b.body.at["crotch_z"]) + 0.03, float(b.body.at["armpit_z"]) - 0.03, 0.005)
        per = {zz: _perim(h) for zz in zs if (h := torso_hull(b.body, zz)) is not None}
        ok = [zz for zz, pp in per.items() if pp + 2 * np.pi * RING_GAP <= C]
        if not ok:
            zm = min(per, key=per.get)
            raise ChainRefused(f"{ring}: closed length {C * 1e3:.0f} mm is shorter than the torso at every height between "
                               f"the crotch and the armpits (narrowest {per[zm] * 1e3:.0f} mm at z {zm:.3f} m, + "
                               f"{2 * np.pi * RING_GAP * 1e3:.0f} mm for its gap off the body). next: lengthen it by at "
                               f"least {(per[zm] + 2 * np.pi * RING_GAP - C) * 1e3:.0f} mm in the pattern (draft_pattern), "
                               "or close it on a later hole; pattern_check, chain_garment again")
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
