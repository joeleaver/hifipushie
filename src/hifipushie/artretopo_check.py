"""Artist retopo: checks that refuse a bad input or a broken cage before any Blender step runs.

`check_input(mesh)`: what the fused sculpt must be (oxidegen make_point_cloud's `mesh_ply`): one watertight part,
outward normals (positive signed volume: a fused mesh once came inside out), z up (taller than wide or deep is not
required, but the ground is its lowest point), mirror-symmetric about x = 0 (the cage's .L / .R and the rig assume
it), the front facing -y (judged by eye on the study sheet: no number can say which side is the face).

`check_cage(V, F)`: the cage must be a closed 2-manifold of quads (every edge on exactly two faces, every face 4
distinct vertices), consistently wound, with no unused vertices; its signed volume (after orienting) and its genus are
reported (genus 0 for a body without handles). A hole left open (a skipped bridge cell with no limb out of it) is an
open boundary: named by its vertices' positions so the artist can find it."""
from __future__ import annotations

from collections import Counter

import numpy as np

from .artretopo_mesh import Mesh


def check_input(m: Mesh) -> dict:
    lo, hi = m.bounds(); size = hi - lo
    lab = m.components(); parts = Counter(lab.tolist())
    from scipy.spatial import cKDTree
    kd = cKDTree(m.V); mir = m.V * np.array([-1, 1, 1])
    d, _ = kd.query(mir[:: max(1, len(mir) // 20000)])
    out = {"vertices": len(m.V), "triangles": len(m.F), "bounds_min": lo.round(4).tolist(), "bounds_max": hi.round(4).tolist(),
           "height": round(float(size[2]), 4), "width_x": round(float(size[0]), 4), "depth_y": round(float(size[1]), 4),
           "signed_volume": round(m.signed_volume(), 6), "open_edges": m.edges_open(), "parts": len(parts),
           "mirror_error_p95": round(float(np.percentile(d, 95)), 4), "centre_x": round(float((lo[0] + hi[0]) / 2), 4)}
    faults = []
    if out["signed_volume"] <= 0:
        faults.append("the faces wind INWARD (negative signed volume): flip them before anything else")
    if out["open_edges"]:
        faults.append(f"{out['open_edges']} open edges: the sculpt isn't watertight (slices give open chains, dropped)")
    if len(parts) > 1:
        faults.append(f"{len(parts)} separate parts (the biggest has {max(parts.values())} triangles): slices pick "
                      "regions by a point, so loose bits are harmless, but say what they are")
    if out["mirror_error_p95"] > 0.02 * size[2]:
        faults.append(f"not mirror-symmetric about x = 0 (95% of mirrored vertices within {out['mirror_error_p95']}): "
                      "check the frame (z up, facing -y, centred on x = 0)")
    if abs(out["centre_x"]) > 0.02 * size[2]:
        faults.append(f"the bounding box is centred at x = {out['centre_x']}, not 0")
    out["faults"] = faults
    return out


def check_cage(V, F) -> dict:
    V = np.asarray(V, float)
    faults = []
    bad = [k for k, q in enumerate(F) if len(q) != 4 or len(set(q)) != len(q)]
    if bad:
        faults.append(f"{len(bad)} faces are not 4 distinct vertices (first: face {bad[0]} = {F[bad[0]]})")
    used = {i for q in F for i in q}
    if len(used) != len(V):
        faults.append(f"{len(V) - len(used)} vertices are on no face")
    E = Counter()
    directed = Counter()
    for q in F:
        for k in range(len(q)):
            a, b = q[k], q[(k + 1) % len(q)]
            E[(min(a, b), max(a, b))] += 1; directed[(a, b)] += 1
    open_ = [e for e, n in E.items() if n == 1]
    nonman = [e for e, n in E.items() if n > 2]
    if open_:
        P = np.unique(np.array([V[i] for e in open_ for i in e]).round(3), axis=0)
        faults.append(f"{len(open_)} open edges (a hole with nothing out of it, or a missing bridge); around "
                      f"{P[:6].tolist()}")
    if nonman:
        faults.append(f"{len(nonman)} edges on more than two faces (a loop bridged twice), first at {V[nonman[0][0]].round(3).tolist()}")
    notes = []
    flipped = sum(1 for n in directed.values() if n > 1)
    if flipped and not nonman:
        notes.append(f"{flipped} edges are wound the same way by both their faces: faces disagree on which side is "
                      "out (harmless: press re-winds the cage consistently, then outward by its signed volume)")
    nV, nE, nF = len(used), len(E), len(F)
    chi = nV - nE + nF
    tris = [(q[0], q[k], q[k + 1]) for q in F for k in range(1, len(q) - 1)]
    vol = float(sum(np.dot(V[a], np.cross(V[b], V[c])) for a, b, c in tris) / 6) if tris else 0.0
    # faces whose quad is badly non-planar or folded over (diagonals' normals disagree)
    twisted = 0
    for q in F:
        if len(q) == 4:
            a, b, c, d = (V[i] for i in q)
            n1 = np.cross(b - a, c - a); n2 = np.cross(c - a, d - a)
            if np.dot(n1, n2) < 0:
                twisted += 1; twisted_at = (a + b + c + d) / 4
    if twisted:
        notes.append(f"{twisted} quads are folded across a diagonal (a bow-tie, or a quad bent round a tip / narrow cap: "
                     f"look at them): first at {np.round(twisted_at, 3).tolist()}")
    return {"vertices": nV, "quads": nF, "edges": nE, "euler": chi, "genus": (2 - chi) / 2 if not open_ else None,
            "volume_as_wound": round(vol, 5), "faults": faults, "notes": notes}


def mirror_error(P, kd=None) -> float:
    """95th percentile distance from each point mirrored across x = 0 to the nearest point"""
    from scipy.spatial import cKDTree
    kd = kd or cKDTree(P)
    d, _ = kd.query(P * np.array([-1, 1, 1]))
    return float(np.percentile(d, 95))


def symmetry_yaw(V, n: int = 6000) -> tuple[float, float, float]:
    """the turn about z (degrees, within +-90 of the input's facing) and the x shift that put the sculpt's mirror
    plane on x = 0: (yaw_deg, x_shift, mirror error after). Mirror symmetry can't tell the face from the back: the
    nearest turn is taken (oxidegen turns the concept's view to -y, so the face is within 90 deg of it)."""
    P = np.asarray(V, float)[:: max(1, len(V) // n)]
    def err(a):
        r = np.radians(a); R = np.array([[np.cos(r), -np.sin(r), 0], [np.sin(r), np.cos(r), 0], [0, 0, 1]])
        Q = P @ R.T; Q[:, 0] -= Q[:, 0].mean()
        return mirror_error(Q), -float((P @ R.T)[:, 0].mean())
    coarse = min(np.arange(-90, 90, 2.0), key=lambda a: err(a)[0])
    best = min(np.arange(coarse - 2, coarse + 2.01, 0.25), key=lambda a: err(a)[0])
    e, dx = err(best)
    return float(best), dx, e


def align_yaw(m: Mesh, yaw_deg: float) -> Mesh:
    """turn about z by yaw_deg and put the mirror plane on x = 0 (the vertex mean's x); z untouched"""
    r = np.radians(yaw_deg); R = np.array([[np.cos(r), -np.sin(r), 0], [np.sin(r), np.cos(r), 0], [0, 0, 1]])
    V = m.V @ R.T; V[:, 0] -= V[:, 0].mean()
    return Mesh(V, m.F, m.C, weld=False)
