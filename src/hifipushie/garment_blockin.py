"""GARMENT BLOCK-IN (F9, C327-): the garment AS WORN, blocked in as an SDF at step 2, meshed, its seam lines on it.

Joe (2026-11-03): "what if, instead of going from measurement to mesh directly, we did all our block-ins with sdfs, then
meshed the result?" The block-in is the garment's TARGET and its START, never the garment: the pattern still gives the
seams, grain, lengths and UVs. Step 2 writes it (garment_plan "style", key `blockin`); step 4 maps each drafted piece onto
its region (blockin_map.check: the pattern vs the design, per region); step 5 starts the chains from that map
(blockin_map.start: every seam already closed, nothing inside the body).

THE FORMAT (data, like a spec; metres, Blender axes; a POINT is [x, y, z] or a body landmark name ("wrist.L"), a HEIGHT is
a number or a landmark ("waist_z", or a point landmark's z); every ".L" thing is mirrored to ".R" unless "mirror": false):
  blockin {
    ease    [{at: HEIGHT, mm}]  the stand-off from the body (a girth ease E reads E / 2 pi here), linear between knots
            in height, held past the ends: the body's own field offset outwards (`field`)
    shapes  [{kind: "cone", a: POINT, b: POINT, r_a, r_b (m)}]  unioned (smoothly, BLEND m) with the offset body: a
            straight leg, a flare, a collar's roll, a skirt's bell
    cuts    [PLANE]  the garment kept on each plane's BELOW side: hems, the waist, openings. PLANE = {x | y | z: HEIGHT or
            number, keep: "below" | "above"} (axis-aligned) or {point: POINT, normal: [3], keep}; "below" = n.(p - P) <= 0
    seams   [{name (step 1's seam, "front:side"), plane: PLANE, within: [PLANE] (the seam plane only acts where these all
            keep; none = everywhere)}]  each seam LINE is where its plane meets the block-in's surface
    regions [{piece (step 4's piece name), seed: POINT}]  the surface cut along every seam line falls into cells; a
            piece's region is the cell holding its seed (".L" seeds mirrored for ".R")
    voxel_mm (default VOXEL_MM), source }
Nothing here names a garment: a shirt is the torso + arms offset, cut at the neck / hem / wrists, its seams the side,
shoulder, armhole planes.

`build(bi, body)` -> BlockIn: the field on a grid, the mesh (marching cubes), the mesh cut exactly along each seam plane,
each face's region, each seam line as polylines. `outline_rows(blk, plan, at)` is T15's outline check on the block-in's
silhouette (structure_outline.placement + compare): run BEFORE any drafting; a FAIL backs to step 2 (the block-in).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dfield

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

VOXEL_MM = 6.0
BLEND = 0.02      # m: the smooth union of a shape with the offset body (smin k)
NEAR = 0.06       # m: the body's distance is read exactly within this; beyond, inside / outside by flood fill
PAD = 0.03        # m: the grid past the kept body + the largest stand-off


def _mirror_name(n: str) -> str:
    return n[:-2] + ".R" if n.endswith(".L") else n


def point(at: dict, P, mirror: bool = False) -> np.ndarray:
    """A POINT: [x, y, z] or a landmark name (".R" mirrors ".L")."""
    if isinstance(P, str):
        side = P.endswith(".R")
        q = np.asarray(at[P[:-2] + ".L"] if side else at[P], float).ravel()
        if q.size == 1:
            raise ValueError(f"landmark {P} is a height, not a point")
        q = q.copy()
        if side:
            q[0] = -q[0]
    else:
        q = np.asarray(P, float).ravel()
        if q.size != 3:
            raise ValueError(f"a point is [x, y, z] or a landmark: {P}")
        q = q.copy()
    if mirror:
        q[0] = -q[0]
    return q


def height(at: dict, h) -> float:
    if isinstance(h, str):
        return float(np.asarray(at[h], float).ravel()[-1])
    return float(h)


def plane(at: dict, d: dict, mirror: bool = False) -> tuple:
    """(P, n): kept where n.(p - P) <= 0."""
    keep = d.get("keep", "below")
    if keep not in ("below", "above"):
        raise ValueError(f"keep is 'below' or 'above': {keep}")
    sg = 1.0 if keep == "below" else -1.0
    for i, ax in enumerate("xyz"):
        if ax in d:
            P, n = np.zeros(3), np.zeros(3)
            P[i] = height(at, d[ax]) + float(d.get("d" + ax, 0.0))
            n[i] = sg
            break
    else:
        P, n = point(at, d["point"]), np.asarray(d["normal"], float)
        n = sg * n / max(np.linalg.norm(n), 1e-12)
    if mirror:
        P, n = P * [-1, 1, 1], n * [-1, 1, 1]
    return P, n


def validate(bi: dict, at: dict | None = None) -> list:
    """Problems with a block-in (strings; empty = fine)."""
    bad = []
    if not isinstance(bi, dict):
        return ["blockin is a dict (garment_blockin's docstring)"]
    for k in bi:
        if k not in ("ease", "shapes", "cuts", "seams", "regions", "voxel_mm", "source"):
            bad.append(f"blockin: unknown key {k}")
    if not bi.get("ease"):
        bad.append("blockin.ease: at least one {at, mm} (the stand-off from the body)")
    if not bi.get("regions"):
        bad.append("blockin.regions: one {piece, seed} per piece to map")
    for s in bi.get("seams") or []:
        if not s.get("name") or "plane" not in s:
            bad.append(f"blockin.seams: each needs name + plane: {s}")
    for s in bi.get("shapes") or []:
        if s.get("kind", "cone") != "cone":
            bad.append(f"blockin.shapes: kind 'cone' only: {s}")
    if at is not None and not bad:
        try:
            for e in bi["ease"]:
                height(at, e["at"])
            for s in bi.get("shapes") or []:
                point(at, s["a"]), point(at, s["b"])
            for c in list(bi.get("cuts") or []) + [s["plane"] for s in bi.get("seams") or []]:
                plane(at, c)
            for r in bi["regions"]:
                point(at, r["seed"])
        except (KeyError, ValueError, TypeError) as e:
            bad.append(f"blockin: {type(e).__name__} {e} (a landmark name or a malformed entry)")
    return bad


def _ease(at: dict, ease: list, z: np.ndarray) -> np.ndarray:
    k = sorted((height(at, e["at"]), float(e["mm"]) / 1000) for e in ease)
    return np.interp(z, [a for a, _ in k], [b for _, b in k])


def _cone(p, a, b, ra, rb):
    ab = b - a
    L2 = max(float(ab @ ab), 1e-12)
    t = np.clip(((p - a) @ ab) / L2, 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1) - (ra + (rb - ra) * t)


def _smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


@dataclass
class BlockIn:
    V: np.ndarray
    F: np.ndarray
    region: np.ndarray            # per face: index into names (-1: no piece)
    names: list
    seams: dict                   # (piece a, piece b) -> [polyline (k, 3)] (each a connected line, ordered)
    seam_of: dict                 # (piece a, piece b) -> [step-1 seam name per polyline]
    reads: dict = dfield(default_factory=dict)


def shapes_of(bi: dict, at: dict) -> list:
    out = []
    for s in bi.get("shapes") or []:
        a, b = point(at, s["a"]), point(at, s["b"])
        out.append((a, b, float(s["r_a"]), float(s["r_b"])))
        if s.get("mirror", True) and (abs(a[0]) > 1e-6 or abs(b[0]) > 1e-6):
            out.append((a * [-1, 1, 1], b * [-1, 1, 1], float(s["r_a"]), float(s["r_b"])))
    return out


def cuts_of(bi: dict, at: dict) -> list:
    out = []
    for c in bi.get("cuts") or []:
        P, n = plane(at, c)
        out.append((P, n))
        if c.get("mirror", True) and abs(n[0]) > 1e-9:
            out.append(plane(at, c, mirror=True))
    return out


def field(bi: dict, body, P: np.ndarray, d_body: np.ndarray) -> np.ndarray:
    """The block-in's field at P given the body's signed distance there."""
    at = body.at
    f = d_body - _ease(at, bi["ease"], P[:, 2])
    for a, b, ra, rb in shapes_of(bi, at):
        f = _smin(f, _cone(P, a, b, ra, rb), BLEND)
    for Q, n in cuts_of(bi, at):
        f = np.maximum(f, (P - Q) @ n)
    return f


def body_distance(body, P: np.ndarray, shape: tuple) -> np.ndarray:
    """Signed distance to the body mesh on a grid (exact within NEAR; beyond it, inside / outside by flood fill)."""
    dv, _ = cKDTree(np.asarray(body.V, float)).query(P, distance_upper_bound=NEAR)
    near = np.isfinite(dv)
    d = np.full(len(P), NEAR)
    if near.any():
        d[near] = body.contact.query(P[near])[0]
    far = (~near).reshape(shape)
    lab, n = ndimage.label(far)
    inside = np.zeros(shape, bool)
    flat = lab.ravel()
    rng = np.random.default_rng(0)
    for c in range(1, n + 1):  # (each far region inside or out by the body's own sign at a few of its points: the grid's
        # faces may slice the body, so touching the border says nothing)
        idx = np.where(flat == c)[0]
        pick = idx[rng.choice(len(idx), min(9, len(idx)), replace=False)]
        if (body.contact.query(P[pick])[0] < 0).mean() > 0.5:
            inside |= lab == c
    d = d.reshape(shape)
    d[inside] = -NEAR
    return d.ravel()


def _split(V, F, Q, n, active, snap: float = 1e-4):
    """Cut the mesh exactly along the plane n.(p - Q) = 0 where `active` (per face); points within `snap` of the plane
    are moved onto it first; new points shared between faces."""
    V = np.array(V, float)
    s = (V - Q) @ n
    near = np.abs(s) < snap
    inF = np.zeros(len(V), bool)
    inF[np.unique(F[active])] = True
    V[near & inF] -= s[near & inF, None] * n
    s = np.where(near & inF, 0.0, s)
    sg = np.sign(s).astype(int)
    V = [v for v in V]
    cache = {}

    def cut(i, j):
        k = (min(i, j), max(i, j))
        if k not in cache:
            t = s[i] / (s[i] - s[j])
            V.append(V[i] + t * (V[j] - V[i]))
            cache[k] = len(V) - 1
        return cache[k]

    out = []
    for fi, tri in enumerate(F):
        g = sg[tri]
        if not active[fi] or not ((g > 0).any() and (g < 0).any()):
            out.append(tuple(tri))
            continue
        if (g == 0).any():  # (through a vertex: two triangles)
            z = int(np.where(g == 0)[0][0])
            p, q, r = tri[z], tri[(z + 1) % 3], tri[(z + 2) % 3]
            m = cut(q, r)
            out += [(p, q, m), (p, m, r)]
            continue
        lone = int(np.where(g > 0)[0][0]) if (g > 0).sum() == 1 else int(np.where(g < 0)[0][0])
        p, q, r = tri[lone], tri[(lone + 1) % 3], tri[(lone + 2) % 3]
        m1, m2 = cut(p, q), cut(r, p)
        out += [(p, m1, m2), (m1, q, r), (m1, r, m2)]
    return np.asarray(V), np.asarray(out, np.int64)


def _components(F, ok, blocked=None):
    """Face components (sharing an edge not in `blocked`, a set of sorted vertex pairs) among faces with ok."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    idx = np.where(ok)[0]
    E = np.r_[F[idx][:, [0, 1]], F[idx][:, [1, 2]], F[idx][:, [2, 0]]]
    E = np.sort(E, axis=1)
    fid = np.r_[idx, idx, idx]
    o = np.lexsort((E[:, 1], E[:, 0]))
    E, fid = E[o], fid[o]
    same = np.all(E[1:] == E[:-1], axis=1)
    if blocked:
        same &= ~np.array([(int(x), int(y)) in blocked for x, y in E[:-1]])
    a, b = fid[:-1][same], fid[1:][same]
    G = coo_matrix((np.ones(len(a)), (a, b)), shape=(len(F), len(F)))
    _, lab = connected_components(G, directed=False)
    return lab


def _chains(segs: np.ndarray, V: np.ndarray) -> list:
    """Edge list -> ordered vertex chains (each a polyline of vertex ids)."""
    from collections import defaultdict
    adj = defaultdict(list)
    for a, b in segs:
        adj[a].append(b)
        adj[b].append(a)
    seen, out = set(), []
    ends = [v for v in adj if len(adj[v]) == 1] + list(adj)
    for s in ends:
        if s in seen:
            continue
        ch, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nxt = [w for w in adj[cur] if w != prev and w not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            ch.append(cur)
        if len(ch) > 1:
            out.append(ch)
    return out


def _join(polys: list, tol: float = 1e-6) -> list:
    """Polylines whose ends meet (a vertex on a seam plane splits a line in two) joined into one."""
    polys = [np.asarray(p) for p in polys]
    done = False
    while not done:
        done = True
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                a, b = polys[i], polys[j]
                for A, B in ((a, b), (a, b[::-1]), (a[::-1], b), (a[::-1], b[::-1])):
                    if np.linalg.norm(A[-1] - B[0]) < tol:
                        polys[i] = np.r_[A, B[1:]]
                        del polys[j]
                        done = False
                        break
                if not done:
                    break
            if not done:
                break
    return polys


def build(bi: dict, body, log=lambda *_: None) -> BlockIn:
    """Field -> mesh -> cut along the seams -> regions + seam lines."""
    from skimage import measure
    at = body.at
    vox = float(bi.get("voxel_mm", VOXEL_MM)) / 1000
    BV = np.asarray(body.V, float)
    keep = np.ones(len(BV), bool)
    for Q, n in cuts_of(bi, at):
        keep &= (BV - Q) @ n <= 0
    pts = [BV[keep]] + [np.r_[[a], [b]] for a, b, _, _ in shapes_of(bi, at)]
    E = max(float(e["mm"]) for e in bi["ease"]) / 1000
    R = max([0.0] + [max(ra, rb) for _, _, ra, rb in shapes_of(bi, at)])
    lo = np.min(np.concatenate(pts), 0) - PAD - E - R
    hi = np.max(np.concatenate(pts), 0) + PAD + E + R
    shape = tuple(np.ceil((hi - lo) / vox).astype(int) + 1)
    g = [lo[i] + vox * np.arange(shape[i]) for i in range(3)]
    P = np.stack(np.meshgrid(*g, indexing="ij"), -1).reshape(-1, 3)
    d = body_distance(body, P, shape)
    f = field(bi, body, P, d).reshape(shape)
    V, F, _, _ = measure.marching_cubes(f, 0.0, spacing=(vox,) * 3)
    V = V + lo
    F = F[:, ::-1].astype(np.int64)
    from .sdf import taubin
    V = taubin(V, F, iterations=6)  # (the voxel steps out: a seam line's length is read on this surface)  # (outward normals, the repo's winding)
    # the cuts are OPENINGS (a hem, the waist): their caps are not cloth
    T_ = V[F]
    N_ = np.cross(T_[:, 1] - T_[:, 0], T_[:, 2] - T_[:, 0])
    N_ /= np.maximum(np.linalg.norm(N_, axis=1, keepdims=True), 1e-12)
    cap = np.zeros(len(F), bool)
    for Q, n in cuts_of(bi, at):
        cap |= (np.abs((T_.mean(1) - Q) @ n) < 0.75 * vox) & (np.abs(N_ @ n) > 0.9)
    F = F[~cap]
    comp = _components(F, np.ones(len(F), bool))  # (one garment surface: cavities inside the body's field are not cloth)
    big = np.bincount(comp).argmax()
    F = F[comp == big]
    used = np.unique(F)
    remap = np.full(len(V), -1)
    remap[used] = np.arange(len(used))
    V, F = V[used], remap[F]
    log(f"blockin: grid {shape}, mesh {len(V)} v ({int(cap.sum())} cap faces dropped)")
    # seams: exact cuts
    planes = []
    for s in bi.get("seams") or []:
        Q, n = plane(at, s["plane"])
        W = [plane(at, w) for w in s.get("within") or []]
        planes.append((s["name"], Q, n, W))
        if s.get("mirror", True):
            Qm, nm_ = plane(at, s["plane"], True)
            Wm = [plane(at, w, True) for w in s.get("within") or []]
            same_ = lambda A, B: abs(abs(A[1] @ B[1]) - 1) < 1e-9 and abs((A[0] - B[0]) @ B[1]) < 1e-9
            if not (same_((Qm, nm_), (Q, n)) and len(W) == len(Wm) and all(any(same_(a, b) and a[1] @ b[1] > 0 for b in W) for a in Wm)):
                planes.append((s["name"], Qm, nm_, Wm))
    for _, Q, n, W in planes:
        C = V[F].mean(1)
        act = np.ones(len(F), bool)
        for Qw, nw in W:
            act &= (C - Qw) @ nw <= 0.5 * vox
        V, F = _split(V, F, Q, n, act)
    # cells: faces joined across every edge that is not on an (active) seam line
    Es_all = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1), axis=0)
    blocked = set()
    for _, Q, n, W in planes:
        on = np.abs((V - Q) @ n) < 1e-9
        k = on[Es_all[:, 0]] & on[Es_all[:, 1]]
        M_ = V[Es_all[k]].mean(1)
        ok = np.ones(len(M_), bool)
        for Qw, nw in W:
            ok &= (M_ - Qw) @ nw <= 1e-6
        blocked |= {(int(a), int(b)) for a, b in Es_all[k][ok]}
    C = V[F].mean(1)
    lab = _components(F, np.ones(len(F), bool), blocked)
    regs = []
    for r in bi["regions"]:
        regs.append((r["piece"], point(at, r["seed"])))
        if r.get("mirror", True) and r["piece"].endswith(".L"):
            regs.append((_mirror_name(r["piece"]), point(at, r["seed"], mirror=True)))
    names = [p for p, _ in regs]
    region = np.full(len(F), -1)
    kd = cKDTree(C)
    for i, (p, s) in enumerate(regs):
        cell = lab[kd.query(s)[1]]
        if (region[lab == cell] >= 0).any():
            raise ValueError(f"blockin: regions {p} and {names[region[lab == cell][0]]} fall in one cell: a seam missing between them")
        region[lab == cell] = i
    # seam lines: edges between faces of two regions
    Ed = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    fid = np.tile(np.arange(len(F)), 3)
    Es = np.sort(Ed, axis=1)
    o = np.lexsort((Es[:, 1], Es[:, 0]))
    Es, fid = Es[o], fid[o]
    same = np.all(Es[1:] == Es[:-1], axis=1)
    ia, ib = fid[:-1][same], fid[1:][same]
    ra, rb = region[ia], region[ib]
    diff = (ra != rb) & (ra >= 0) & (rb >= 0)
    seams, seam_of = {}, {}
    for a, b in {tuple(sorted(x)) for x in zip(ra[diff], rb[diff])}:
        k = diff & (np.minimum(ra, rb) == a) & (np.maximum(ra, rb) == b)
        chains = _chains(Es[:-1][same][k], V)
        polys = _join([V[c] for c in chains if len(c) > 1])
        polys = [q for q in polys if len(q) > 2]
        key_ = (names[a], names[b])
        seams[key_] = polys
        nm = []
        for pl in polys:  # (which step-1 seam: the plane it lies on, inside its within)
            m_ = pl.mean(0)
            dist = [np.abs((pl - Q) @ n).mean() + sum(max(0.0, float((m_ - Qw) @ nw)) for Qw, nw in W)
                    for _, Q, n, W in planes]
            nm.append(planes[int(np.argmin(dist))][0] if planes else "?")
        seam_of[key_] = nm
    blk = BlockIn(V, F, region, names, seams, seam_of)
    blk.reads = {"grid": [int(x) for x in shape], "voxel_mm": vox * 1000, "verts": len(V), "faces": len(F),
                 "unassigned_area_pct": round(100 * _area(V, F[region < 0]) / max(_area(V, F), 1e-12), 1),
                 "regions": {n: round(_area(V, F[region == i]) * 1e4, 1) for i, n in enumerate(names)},
                 "seams": {f"{a}~{b}": [f"{nm} {_plen(pl) * 1e3:.0f} mm" for nm, pl in zip(seam_of[(a, b)], seams[(a, b)])]
                           for (a, b) in seams}}
    return blk


def _area(V, F) -> float:
    if not len(F):
        return 0.0
    T = V[F]
    return float(0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1).sum())


def _plen(P) -> float:
    return float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())


# ---------------------------------------------------------------- the outline check (T15) on the block-in
def silhouette(V, F, view: str, px_mm: float = 2.0) -> list:
    """The block-in's outline in a view (structure_outline.project mm), as closed polylines."""
    from PIL import Image, ImageDraw
    from skimage import measure
    from .structure_outline import project
    P = project(V, view)
    lo = P.min(0) - 10
    Q = (P - lo) / px_mm
    W, H = (np.ceil(Q.max(0)) + 10).astype(int)
    im = Image.new("L", (int(W), int(H)), 0)
    dr = ImageDraw.Draw(im)
    for t in Q[F]:
        dr.polygon([tuple(x) for x in t], fill=255)
    A = np.asarray(im) > 0
    return [c[:, ::-1] * px_mm + lo for c in measure.find_contours(A.astype(float), 0.5) if len(c) > 20]


def outline_rows(blk: BlockIn, plan: dict, at: dict) -> list:
    """T15's outline rows ("outline:<trace id>") on the block-in's silhouette: placed by the body marks, compared in mm.
    A FAIL backs to step 2 (the block-in: its ease, shapes or cuts)."""
    from . import structure_outline as so
    style = plan.get("style") or {}
    out = []
    for t in style.get("traces") or []:
        vi = t.get("view", 0)
        v = so._view_of(plan, vi)
        row = dict(id=f"outline:{t['id']}", stage=2, measure="garment_blockin (the block-in's silhouette)")
        try:
            pl = so.placement(v, so._marks(style, vi), at)
        except (ValueError, KeyError, np.linalg.LinAlgError) as e:
            out.append({**row, "status": "UNMEASURED", "why": f"the body marks don't place the view: {e}", "back_to": "2"})
            continue
        arcs = silhouette(blk.V, blk.F, v["view"])
        Tm = so.to_mm(t["points"], pl)
        r = so.compare(Tm, arcs, 2.0, pl["s"], t.get("corners") or [], pl["residual_mm"])
        row.update(status=r["status"], ours={k: r.get(k) for k in ("p95_mm", "max_mm", "placed_p95_mm", "shift_mm") if k in r},
                   ref=f"shape p95 <= {r.get('tol_mm')} mm; placed: {pl['how']} (residual {pl['residual_mm']} mm)")
        if r["status"] == "FAIL":
            row.update(why="; ".join(r.get("fails") or []), back_to="2",
                       change=f"the block-in's ease / shapes / cuts where the outline is off: worst {r.get('max_mm')} mm "
                              f"at {r.get('worst_along', 0):.0%} along {t['id']} (shift {r.get('shift_mm')} mm)")
        out.append(row)
    return out


def look(blk: BlockIn, plan: dict, at: dict, path: str, vi: int = 0) -> str:
    """The reference view with the step-2 traces (red) and the block-in's silhouette (blue) placed by the body marks,
    its seam lines (yellow) projected: shape only, numbers are in the rows (C288)."""
    from PIL import Image, ImageDraw
    from . import structure_outline as so
    style = plan.get("style") or {}
    v = so._view_of(plan, vi)
    im = Image.open(v["image"]).convert("RGB")
    dr = ImageDraw.Draw(im)
    pl = so.placement(v, so._marks(style, vi), at)
    for a in silhouette(blk.V, blk.F, v["view"]):
        dr.line([tuple(p) for p in so.to_px(a, pl)], fill=(40, 90, 255), width=3)
    for polys in blk.seams.values():
        for P in polys:
            dr.line([tuple(p) for p in so.to_px(so.project(P, v["view"]), pl)], fill=(255, 210, 0), width=2)
    for t in style.get("traces") or []:
        if t.get("view", 0) == vi:
            dr.line([tuple(p) for p in t["points"]], fill=(230, 30, 30), width=3)
    for k, uv in so._marks(style, vi).items():
        if uv[1] is None:
            dr.line([(uv[0], 0), (uv[0], im.size[1])], fill=(0, 200, 0), width=1)
        else:
            dr.ellipse([uv[0] - 6, uv[1] - 6, uv[0] + 6, uv[1] + 6], outline=(0, 200, 0), width=3)
    im.save(path)
    return path
