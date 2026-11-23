"""Hard surface from the point cloud: FRAME the fused sculpt before measuring anything.

A fused concept sculpt arrives in the generator's frame (y up, arbitrary yaw, unit-ish size). Square it up the way an
artist would on a turntable: stand it on the ground, turn it so its footprint lines up with the axes, centre it, scale
it to one dimension you know, and keep the transform (the colour bake projects the point-cloud renders and needs to get
back into their frame).

`square_up(mesh, up="y", contact_h=0.06, contacts=None, yaw="pca", pairs=None, scale=None, flip=False)`:
- `up`: the input's up axis ("y" for oxidegen's fused meshes, "z" if already Blender-up).
- ground footprint = the section `contact_h` above the lowest point: the regions there are the CONTACTS (wheels, feet,
  legs, a base). `contacts` keeps the N biggest (e.g. 4 for a four-wheeler, a table's legs) and drops the rest (a
  can lying on the ground behind a kart was a fifth contact: drop it by count, or by `exclude_centre` width).
- `yaw`: "pca" turns the footprint's long axis onto y; "pairs" squares up on left/right contact pairs (front pair and
  back pair side by side: the axle lines go along x); a number = degrees.
- `scale`: {"extent": "x"|"y"|"z", "value": m} (overall size) or {"pair_gap": m} (distance between the pairs' mid
  points along y: a wheelbase, a table's leg spacing) or None.
- `yaw0`: the first turn in degrees when the footprint is nearly square (track ~ wheelbase: PCA can't choose; warned).
- `shift` [dx, dy, dz]: after centring on the contacts, move so a known point sits where the reference says (axles at
  build.json's y, a door on a wall line).
- `flip`: turn 180 deg about z if the front came out at +y (the framed object faces -y).
Returns (framed Mesh, info) where info["framed_to_input"] (4x4) maps framed coords back to the input mesh's and
info["contacts"] lists each contact's centre and extent. `views_transform(...)` adds the input -> renders map.
Iterate: a second call on the framed mesh refines yaw (the first PCA can be biased by the body above the contacts)."""
from __future__ import annotations

import math

import numpy as np

from .artretopo_mesh import Mesh


def _Rz(a):
    c, s = math.cos(a), math.sin(a); return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def footprint(m: Mesh, contact_h=0.06, contacts=None, exclude_centre=None):
    """the regions of the section `contact_h` above the lowest point, biggest first"""
    z0 = m.V[:, 2].min()
    regs = m.section((0, 0, z0 + contact_h), (0, 0, 1), (1, 0, 0), (0, 1, 0))
    out = []
    for p in regs:
        e = p.exterior; lo, hi = e.min(0), e.max(0)
        c = (lo + hi) / 2
        if exclude_centre is not None and abs(c[0]) < exclude_centre: continue
        out.append(dict(c=c, lo=lo, hi=hi, area=p.area, pts=e))
    out.sort(key=lambda d: -d["area"])
    return out[:contacts] if contacts else out


def _pairs(C):
    """split contacts into a front and a back group by y, each sorted by x -> list of (left, right) pairs"""
    ys = np.array([c["c"][1] for c in C]); mid = np.median(ys)
    front = sorted([c for c in C if c["c"][1] < mid], key=lambda c: c["c"][0])
    back = sorted([c for c in C if c["c"][1] >= mid], key=lambda c: c["c"][0])
    return [g for g in (front, back) if len(g) >= 2]


def square_up(mesh, up="y", contact_h=0.06, contacts=None, exclude_centre=None, yaw="pca", scale=None, flip=False,
              iterations=2, yaw0=None, shift=None):
    m = mesh if isinstance(mesh, Mesh) else Mesh.load(mesh)
    M = np.eye(4); square = False
    if up == "y": M[:3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]          # y-up -> z-up
    V = m.V @ M[:3, :3].T
    for it in range(iterations):
        mm = Mesh(V, m.F, m.C, weld=False)
        C = footprint(mm, contact_h, contacts, exclude_centre if it else None)
        if not C: raise ValueError("no footprint: raise contact_h")
        P = np.vstack([c["pts"] for c in C])
        if isinstance(yaw, (int, float)) and not isinstance(yaw, bool):
            a = math.radians(yaw) if it == 0 else 0.0
        elif yaw == "pairs" and it > 0 and len(_pairs(C)) >= 1:
            v = sum((g[-1]["c"] - g[0]["c"]) for g in _pairs(C)); a = -math.atan2(v[1], v[0])
        elif it == 0 and yaw0 is not None:
            a = math.radians(yaw0)
        else:
            c0 = P.mean(0); w, E = np.linalg.eigh(np.cov((P - c0).T)); ax = E[:, 1]; a = math.atan2(ax[0], ax[1])
            if it == 0 and w[1] < 1.3 * w[0]:
                square = True                                                 # PCA can't tell the long axis
            if it > 0 and abs(a) > math.pi / 4: a = 0.0                     # refine only, never swap axes
        R = _Rz(a); c = np.r_[np.mean([d["c"] for d in C], 0), V[:, 2].min()]
        T = np.eye(4); T[:3, :3] = R; T[:3, 3] = -(R @ c)
        V = V @ R.T + T[:3, 3]; M = T @ M
    if flip:
        F_ = np.eye(4); F_[:3, :3] = _Rz(math.pi); V = V @ F_[:3, :3].T; M = F_ @ M
    mm = Mesh(V, m.F, m.C, weld=False); C = footprint(mm, contact_h, contacts, exclude_centre)
    s = 1.0
    if scale:
        if "extent" in scale:
            i = "xyz".index(scale["extent"]); s = scale["value"] / float(np.ptp(V[:, i]))
        elif "pair_gap" in scale:
            g = _pairs(C)
            if len(g) < 2: raise ValueError("pair_gap needs a front and a back pair of contacts")
            s = scale["pair_gap"] / float(abs(np.mean([c["c"][1] for c in g[1]]) - np.mean([c["c"][1] for c in g[0]])))
    S_ = np.eye(4); S_[:3, :3] *= s; V = V * s; M = S_ @ M
    # centre x on the contacts (the mirror plane of most hard-surface objects), y on the contacts, ground at 0
    cc = np.mean([d["c"] for d in footprint(Mesh(V, m.F, m.C, weld=False), contact_h * s, contacts, exclude_centre)], 0)
    T = np.eye(4); T[:3, 3] = [-cc[0], -cc[1], -V[:, 2].min()]
    if shift is not None: T[:3, 3] += np.asarray(shift, float)          # a known point where the reference puts it
    V = V + T[:3, 3]; M = T @ M
    out = Mesh(V, m.F, m.C, weld=False)
    C = footprint(out, contact_h * s, contacts, exclude_centre)
    info = {"framed_to_input": np.linalg.inv(M).tolist(), "input_to_framed": M.tolist(), "scale": s,
            "yaw_deg": round(math.degrees(math.atan2(M[1, 0], M[0, 0])), 2),
            "contacts": [{"centre": [round(float(x), 4) for x in d["c"]], "size": [round(float(x), 4) for x in d["hi"] - d["lo"]]} for d in C],
            "bounds": [out.bounds()[0].round(4).tolist(), out.bounds()[1].round(4).tolist()]}
    if square:
        info["warning"] = ("the footprint is nearly square: PCA can't tell its long axis. Look at the framed views and "
                           "pass yaw0 (degrees) for the first turn; check the front is at -y (flip)")
    return out, info


def fuse_views_transform(views_npz) -> np.ndarray:
    """input (a fused mesh from oxidegen's fuse: (render + centre) * (1, -1, -1)) -> the renders' frame, as 4x4"""
    z = np.load(views_npz); c = np.asarray(z["centre"], float)
    T = np.diag([1.0, -1.0, -1.0, 1.0]); T[:3, 3] = -c
    return T


def views_transform(info: dict, input_to_views: np.ndarray) -> np.ndarray:
    """framed -> renders (what blender_hardsurf_bake projects with)"""
    return np.asarray(input_to_views) @ np.asarray(info["framed_to_input"])
