"""CHAIN SOLVE PLIES (N2 of docs/proposals/step5_rewrite.md): plies and floating layers follow their host as a TERM in
chain_solve's one solve, never as copied or held positions.

What follows what is chain_holds' reading of the pattern (read): a PLY lies on its part's outer piece (an undercollar's
top collar), a floating LAYER inside the soft piece worn at its place (a chest canvas in its front), an INSIDE piece
inside the larger soft piece it is sewn round (a facing in its front). Each follower point is bound to the place its flat
point has in its host's flat (chain_holds.flat_locate: a host triangle and barycentric weights; a ply's flat mapped
through the affine fit of its sewn pairs, a layer's and an inside piece's flat in the host's own draft frame) and to an
OFFSET d along that host triangle's normal (F's winding): k LAYERs on the host's inner side (k: 1 for a layer or the
first ply, 1 + the host's layers for an inside piece, so interfacing lies next to the outer cloth).

THE TERM, per bound point p on host triangle (a, b, c) with weights w: p - (w_a x_a + w_b x_b + w_c x_c) = d n, n the
host's normal there over a RING of faces (the area-weighted vertex normals of a, b, c summed). A triangle's own normal
let the term flip a host corner's triangles towards its follower (the synthetic facing: 7 mm off, a corner inverted).
- PD: the row S = e_p - sum w e_h is linear; its local target d n is re-read from the host's current triangle each pass.
- LM: the same residual (per REF, weight W_PLY), its Jacobian with the normal held at the current pass (a lagged normal:
  exact at the solution, where the residual is d n, and cheap; its full derivative was tried and did not help).
Because the offset is along the host's OWN normal, a follower stays on the same face of its host through any bend: a
facing on its front stays on the front's inner face where the lapel turns over, never crosses it.
A follower point that IS one of its host triangle's nodes (sewn to the host: one node) gets no row.

report: per follower, the residual |p - q - d n| (max / mean mm) and CROSSED: points on the wrong face of their host
((p - q) . n has the other sign from d, past half a LAYER).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

W_PLY = 30.0  # weight of a bound point's offset error (rows / REF): a follower is cloth sewn to its host, so near hard
SAME_FRAME = 0.003  # m: a follower whose sewn points lie on their host partners' flat within this is in the host's frame
SPAN = 0.1  # sewn pairs on a line (second spread under this share of the first) give no affine map (a facing's front edge)
CROSS_TOL = 0.5  # of d: a point this far past its host's face on the other side is crossed


def bind(net, host_of: dict, k_of: dict, sign_of: dict, affine: bool = True) -> list:
    """Bindings for chain_solve(plies=...): host_of {follower piece: host piece}, k_of {follower: layers in}, sign_of
    {host: +1 when its F normals point AWAY from the body (so inside is -n)}. Each {ids, tri (m, 3), w (m, 3), d (m,), name}.
    affine: a follower's flat is mapped onto its host's through its sewn pairs when it has 3 or more (a ply cut mirrored)."""
    from .chain_core import LAYER
    from .chain_holds import flat_locate
    out = []
    for p, h in host_of.items():
        v = net.verts(p)
        hv = net.verts(h)
        Fh = net.F[np.isin(net.F, hv).all(1)]
        q = net.uv[v]
        if affine:
            A = _sewn_affine(net, v, hv)
            if A is not None:
                q = np.c_[q, np.ones(len(q))] @ A
        f, w, _ = flat_locate(net.uv, Fh, q)
        d = np.full(len(v), -float(sign_of.get(h, 1.0)) * k_of.get(p, 1) * LAYER)
        out.append({"ids": v, "tri": Fh[f], "w": w, "d": d, "hostF": Fh, "name": f"{p} on {h}"})
    return out


def _sewn_affine(net, v, hv):
    """(3, 2) least-squares affine map of the follower's uv onto the host's through their sewn pairs; None (its own uv)
    under 3 pairs, when already in the host's frame, or when the pairs lie on one line."""
    sv, sh = set(v.tolist()), set(hv.tolist())
    pr = [(a, b) for a, b in net.sew if a in sv and b in sh] + [(b, a) for a, b in net.sew if b in sv and a in sh]
    if len(pr) < 3:
        return None
    a, b = np.array(pr).T
    if np.abs(net.uv[a] - net.uv[b]).max() <= SAME_FRAME:  # (drawn in its host's own frame: no map)
        return None
    sv_ = np.linalg.svd(net.uv[a] - net.uv[a].mean(0), compute_uv=False)
    if sv_[1] < SPAN * sv_[0]:  # (sewn along one line: an affine fit from it collapses the piece onto that line)
        return None
    P = np.c_[net.uv[a], np.ones(len(a))]
    A, *_ = np.linalg.lstsq(P, net.uv[b], rcond=None)
    return A


def blocks(plies, nid, nn) -> list:
    """Node-level bindings: rows whose follower node is one of its host triangle's nodes are dropped."""
    out = []
    for b in plies:
        p = nid[np.asarray(b["ids"], np.int64)]
        tri = nid[np.asarray(b["tri"], np.int64)]
        keep = ~(tri == p[:, None]).any(1)
        if not keep.any():
            continue
        p, tri = p[keep], tri[keep]
        w, d = np.asarray(b["w"], float)[keep], np.asarray(b["d"], float)[keep]
        m = len(p)
        r = np.repeat(np.arange(m), 4)
        c = np.c_[p, tri].ravel()
        val = np.c_[np.ones(m), -w].ravel()
        S = sp.coo_matrix((val, (r, c)), shape=(m, nn)).tocsr()
        S.sum_duplicates()
        hF = nid[np.asarray(b["hostF"], np.int64)] if "hostF" in b else tri
        out.append({"p": p, "tri": tri, "w": w, "d": d, "S": S, "hF": hF, "name": b.get("name", "ply"),
                    "weight": float(b.get("weight", 1.0))})
    return out


def normals(Xn, tri, hF=None):
    """Unit normals at host triangles: with hF (the host's faces), the sum of the area-weighted vertex normals of the
    triangle's three nodes (a ring of faces: one crumpled triangle can't turn it); else the triangle's own."""
    if hF is None:
        n = np.cross(Xn[tri[:, 1]] - Xn[tri[:, 0]], Xn[tri[:, 2]] - Xn[tri[:, 0]])
    else:
        c = np.cross(Xn[hF[:, 1]] - Xn[hF[:, 0]], Xn[hF[:, 2]] - Xn[hF[:, 0]])
        vn = np.zeros_like(Xn)
        for j in range(3):
            np.add.at(vn, hF[:, j], c)
        n = vn[tri].sum(1)
    return n / np.maximum(np.linalg.norm(n, axis=1), 1e-15)[:, None]


def target(Xn, b):
    """PD's local step: the offset along the host's current normal there."""
    return b["d"][:, None] * normals(Xn, b["tri"], b["hF"])


def residual_rows(Xn, b, w_ply, ref, m, R, C, V, jac):
    """LM rows (3 per bound point): sqrt(W) / REF (p - q - d n), n lagged. Returns (residuals, rows used)."""
    s = np.sqrt(w_ply * b["weight"]) / ref
    tri, dd = b["tri"], b["d"]
    q = (b["w"][:, :, None] * Xn[tri]).sum(1)
    r = s * (Xn[b["p"]] - q - dd[:, None] * normals(Xn, tri, b["hF"]))
    k = len(b["p"])
    if jac:  # (the ring normal held at this pass: exact at the solution, where it is d n)
        rows = m + 3 * np.arange(k)
        for d in range(3):
            R.append(rows + d)
            C.append(3 * b["p"] + d)
            V.append(np.full(k, s))
            for j in range(3):
                R.append(rows + d)
                C.append(3 * tri[:, j] + d)
                V.append(-s * b["w"][:, j])
    return r.ravel(), 3 * k


def report(Xn, blocks_) -> dict:
    out = {}
    for b in blocks_:
        n = normals(Xn, b["tri"], b["hF"])
        q = (b["w"][:, :, None] * Xn[b["tri"]]).sum(1)
        e = Xn[b["p"]] - q
        res = np.linalg.norm(e - b["d"][:, None] * n, axis=1)
        side = (e * n).sum(1) * np.sign(b["d"])
        crossed = int((side < -CROSS_TOL * np.abs(b["d"])).sum())
        out[b["name"]] = {"points": int(len(b["p"])), "max_mm": round(float(res.max()) * 1e3, 2),
                          "mean_mm": round(float(res.mean()) * 1e3, 2), "crossed": crossed}
    return out
