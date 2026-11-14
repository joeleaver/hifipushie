"""Mass under the cards: tail cores and their mesh, the mass shell, the shadow proxy. Part of hair cards (hair_cards.py has the overview)."""
from __future__ import annotations

import json

import numpy as np

from . import hair_cards
from .hair_cards import _unit
from .hair_cards_clumps import strand_grid

def tail_cores(D: dict, locks: list, sides: int = 10, stations: int = 28, fill: float = 0.8) -> dict | None:
    """A solid surface inside each bundle of hair that hangs round a `core` line (a tied tail): the shape the tail's
    own strands make, a little inside them (`fill` of their radius per direction), so cards over it never show air
    between them and a far tier's tail is this shape alone. It follows the strands station by station (a tail that
    swings to one side swings the core with it). A mesh like hair_cards_mesh.mesh's (uv: u round the tail in dense tiles
    is set by the caller: "around" 0..1, "along" 0..1)."""
    G = strand_grid(D, locks, n=stations)
    if not len(G["A"]):
        return None
    groups: dict = {}
    for li in np.unique(G["lock"]):
        lk = locks[int(li)]
        core = lk.get("core")
        if core is None or len(core) < 2 or float(lk.get("free", 0.0)) <= 0.5:
            continue
        groups.setdefault(json.dumps(np.round(np.asarray(core, float), 4).tolist()), []).append(int(li))
    V, F, AR, AL, NR, TN = [], [], [], [], [], []
    off = 0
    for key_, lis in groups.items():
        if len(lis) < 3:
            continue
        A = G["A"][np.isin(G["lock"], lis)]
        with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
            __import__("warnings").simplefilter("ignore")
            cnt = np.isfinite(A[..., 0]).sum(0)
            Pm = np.nanmean(A, 0)
        ok = np.nonzero(cnt >= max(3, hair_cards.CORE_SHARE * len(A)))[0]
        if len(ok) < 4:
            continue
        sl = slice(ok[0], ok[-1] + 1)
        Pm, A = Pm[sl], A[:, sl]
        T = _unit(np.gradient(Pm, axis=0))
        e1 = np.zeros_like(Pm)
        v = np.cross(T[0], [0.0, 0.0, 1.0])
        v = v if np.linalg.norm(v) > 1e-3 else np.cross(T[0], [1.0, 0.0, 0.0])
        for i in range(len(Pm)):  # parallel transport
            v = v - (v @ T[i]) * T[i]
            v = v / max(np.linalg.norm(v), 1e-9)
            e1[i] = v
        e2 = np.cross(T, e1)
        ang = np.linspace(0, 2 * np.pi, sides, endpoint=False)
        Rr = np.zeros((len(Pm), sides))
        with np.errstate(invalid="ignore"):
            d = A - Pm[None]
            x, y = (d * e1[None]).sum(-1), (d * e2[None]).sum(-1)
            th, rr = np.arctan2(y, x), np.hypot(x, y)
        for i in range(len(Pm)):
            good = np.isfinite(rr[:, i])
            if good.sum() < 3:
                continue
            base = float(np.percentile(rr[good, i], 60))
            for a_i, a in enumerate(ang):
                w = good & (np.abs(((th[:, i] - a + np.pi) % (2 * np.pi)) - np.pi) < 2 * np.pi / sides * 1.2)
                Rr[i, a_i] = float(np.percentile(rr[w, i], 75)) if w.sum() >= 3 else base
        for _ in range(2):  # smooth round and along
            Rr = (np.roll(Rr, 1, 1) + 2 * Rr + np.roll(Rr, -1, 1)) / 4
            Rr[1:-1] = (Rr[:-2] + 2 * Rr[1:-1] + Rr[2:]) / 4
        Rr = np.maximum(Rr * fill, 0.002)
        if hair_cards.CORE_TAPER > 0:  # the core closes over its last CORE_TAPER (a tube cut square was a dark ragged block showing
            # through the thinning tail cards: b21 review "dark crunchy patch mid-tail", traced by flat passes per range)
            sa = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Pm, axis=0), axis=1))]
            uu = np.clip((sa[-1] - sa) / max(hair_cards.CORE_TAPER * sa[-1], 1e-6), 0.0, 1.0)
            Rr = np.maximum(Rr * (uu * uu * (3 - 2 * uu))[:, None], 0.0005)
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Pm, axis=0), axis=1))]
        ns = len(Pm)
        ring = (np.cos(ang)[None, :, None] * e1[:, None] + np.sin(ang)[None, :, None] * e2[:, None])  # (ns, sides, 3)
        Vr = Pm[:, None] + ring * Rr[..., None]
        # a seam column (u = 1) so the tiles wrap
        Vr = np.concatenate([Vr, Vr[:, :1]], 1)
        nr = np.concatenate([ring, ring[:, :1]], 1)
        V.append(Vr.reshape(-1, 3))
        NR.append(nr.reshape(-1, 3))
        TN.append(np.repeat(T, sides + 1, 0))
        AR.append(np.tile(np.arange(sides + 1) / sides, ns))
        AL.append(np.repeat(s / max(s[-1], 1e-9), sides + 1))
        i, j = np.meshgrid(np.arange(ns - 1), np.arange(sides), indexing="ij")
        a = (i * (sides + 1) + j).ravel() + off
        b, c, d_ = a + 1, a + sides + 2, a + sides + 1
        F.append(np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d_], 1)]))
        off += ns * (sides + 1)
    if not V:
        return None
    return {"verts": np.concatenate(V).astype(np.float32), "tris": np.concatenate(F).astype(np.int32),
            "normal": np.concatenate(NR).astype(np.float32), "tangent": np.concatenate(TN).astype(np.float32),
            "around": np.concatenate(AR).astype(np.float32), "along": np.concatenate(AL).astype(np.float32)}


def core_mesh(core: dict, tiles: list, reps: int = 4) -> dict:
    """tail_cores' surface wearing the dense tile round it (mirrored every other repeat, so it has no seam), root at
    the tie, the tile's ragged end at the tail's end."""
    t = next(t for t in tiles if t["kind"] == "dense")
    tri = np.abs(((core["around"] * reps) % 2.0) - 1.0)
    n = len(core["verts"])
    return {"verts": core["verts"], "tris": core["tris"],
            "uv": np.stack([t["u0"] + (t["u1"] - t["u0"]) * tri, 1 - core["along"]], 1).astype(np.float32),
            "normal": core["normal"], "tangent": core["tangent"], "col": np.full((n, 3), 0.8, np.float32),
            "along": core["along"], "layer": np.full(n, -1.0, np.float32), "card": np.zeros(n, np.int32)}


def mass_shell(D: dict, locks: list, C, tiles: list, col=None, triangles: int = 3000, tier: str = "loose",
               level: float = 0.3, reps: int = 10) -> dict | None:
    """A solid surface INSIDE a loose mass of hair (what tail_cores is for a tied tail): the strands of the `tier`
    locks counted on a voxel grid, smoothed, meshed where the hair is `level` x as dense as its typical inside, cut
    down to `triangles`. Cards over it never show air or skin between them, and a far tier is little more than
    this. Faces turned toward the body close to it are dropped (nobody sees the inside of a head of hair). It
    wears the dense tile: v = how far along its strands the hair there is (root .. tip, so the tile's ragged end
    lies at the hair's ends), u round the head. `col`: hair_loose_body.Collider (the body)."""
    from scipy import ndimage
    from skimage import measure
    names = [str(n) for n in D["names"]]
    if "hair_guides_free" not in names:
        return None
    want = np.array([lk.get("tier") == tier for lk in locks] + [False])
    lock = np.asarray(D["lock"]).astype(int)
    sel = (np.asarray(D["obj"]) == names.index("hair_guides_free")) & want[np.clip(lock, 0, len(want) - 1)]
    if sel.sum() < 50:
        return None
    cnt = np.asarray(D["counts"])
    first = np.r_[0, np.cumsum(cnt)]
    idx = np.concatenate([np.arange(first[j], first[j + 1]) for j in np.nonzero(sel)[0]])
    u = np.concatenate([np.linspace(0, 1, cnt[j]) for j in np.nonzero(sel)[0]])
    P = np.asarray(D["pts"], float)[idx]
    T = np.gradient(np.asarray(D["pts"], float), axis=0)[idx]
    h = hair_cards.MASS_CELL
    lo = P.min(0) - 4 * h
    n = np.ceil((P.max(0) - lo) / h).astype(int) + 5
    ijk = np.floor((P - lo) / h).astype(int)
    flat = np.ravel_multi_index(ijk.T, n)
    size = int(np.prod(n))
    den = np.bincount(flat, minlength=size).astype(float).reshape(n)
    uu = np.bincount(flat, weights=u, minlength=size).reshape(n)
    tt = np.stack([np.bincount(flat, weights=T[:, k], minlength=size).reshape(n) for k in range(3)], -1)
    dn = ndimage.gaussian_filter(den, 1.0)
    us = ndimage.gaussian_filter(uu, 1.5) / np.maximum(ndimage.gaussian_filter(den, 1.5), 1e-9)
    ts = np.stack([ndimage.gaussian_filter(tt[..., k], 1.5) for k in range(3)], -1)
    ref = float(np.percentile(dn[den > 0], 60))
    if not (dn.max() > level * ref > 0):
        return None
    V, F, Nn, _ = measure.marching_cubes(dn, level * ref, spacing=(h, h, h))
    V = V + lo + 0.5 * h
    Nn = -_unit(Nn)  # (the gradient points into the hair: density rises inward)
    fn = _unit(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]))
    if (fn * Nn[F].mean(1)).sum(-1).mean() < 0:
        F, fn = F[:, ::-1], -fn
    if col is not None:  # the faces toward the body, near it
        fc = V[F].mean(1)
        ph = col.at(fc)
        F = F[~((ph < 0.03) & ((fn * col.grad(fc)).sum(-1) < -0.2)) & (ph > -0.002)]
    if len(F) > triangles:
        import pyfqmr
        used = np.unique(F)
        re_ = -np.ones(len(V), int)
        re_[used] = np.arange(len(used))
        sm = pyfqmr.Simplify()
        sm.setMesh(V[used], re_[F])
        sm.simplify_mesh(target_count=int(triangles), aggressiveness=5, preserve_border=False, verbose=False)
        V, F, _ = sm.getMesh()
        V, F = np.asarray(V, float), np.asarray(F, int)
    if len(F) < 8:
        return None
    used = np.unique(F)
    re_ = -np.ones(len(V), int)
    re_[used] = np.arange(len(used))
    V, F = V[used], re_[F]
    q = ((V - lo - 0.5 * h) / h).T
    grad = np.stack([ndimage.map_coordinates(g_, q, order=1, mode="nearest") for g_ in np.gradient(dn)], -1)
    Nn = -_unit(grad)
    tan = _unit(np.stack([ndimage.map_coordinates(ts[..., k], q, order=1, mode="nearest") for k in range(3)], -1))
    tan = _unit(tan - (tan * Nn).sum(-1, keepdims=True) * Nn)
    along = np.clip(ndimage.map_coordinates(us, q, order=1, mode="nearest"), 0.02, 0.98)
    az = np.arctan2(V[:, 0] - C[0], -(V[:, 1] - C[1])) / (2 * np.pi) + 0.5
    t = next(t for t in tiles if t["kind"] == "dense")
    tri = np.abs(((az * reps) % 2.0) - 1.0)
    m = len(V)
    return {"verts": V.astype(np.float32), "tris": F.astype(np.int32),
            "uv": np.stack([t["u0"] + (t["u1"] - t["u0"]) * tri, 1 - 0.85 * along], 1).astype(np.float32),
            "normal": Nn.astype(np.float32), "tangent": tan.astype(np.float32), "col": np.full((m, 3), 0.8, np.float32),
            "along": along.astype(np.float32), "layer": np.full(m, -1.0, np.float32), "card": np.zeros(m, np.int32)}


def shadow_proxy(V, T, voxel: float | None = None, close: int | None = None, inset: float | None = None,
                 smooth: float | None = None, step: int | None = None) -> dict:
    """An opaque, smooth, low-poly hull of the cards' volume that casts the hair's shadow in place of the cards (a
    shadow-only mesh: invisible to the camera). The card triangles are sampled into a `voxel` grid, closed (dilate
    `close` voxels, fill holes, erode back), shrunk by `inset` (the outer cards stay lit, the hull sits under them),
    blurred (`smooth` voxels: a soft round body, not a voxel staircase) and meshed with marching cubes at `step` voxels.
    Returns {"verts", "tris", "voxel", "inset"}."""
    from scipy import ndimage
    from skimage import measure
    o = {**hair_cards.SHADOW_PROXY, **{k: v for k, v in dict(voxel=voxel, close=close, inset=inset, smooth=smooth, step=step).items()
                            if v is not None}}
    h = float(o["voxel"])
    V = np.asarray(V, np.float64)
    T = np.asarray(T, np.int64)
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    L = np.maximum(np.maximum(np.linalg.norm(B - A, axis=1), np.linalg.norm(C - A, axis=1)), np.linalg.norm(C - B, axis=1))
    k = np.clip(np.ceil(L / (0.5 * h)).astype(int), 1, 64)  # samples per edge: every voxel a triangle crosses is hit
    pts = []
    for kk in np.unique(k):
        sel = k == kk
        u, v = np.meshgrid(np.arange(kk + 1), np.arange(kk + 1), indexing="ij")
        m = (u + v) <= kk
        u, v = u[m] / kk, v[m] / kk
        a, b, c = A[sel], B[sel], C[sel]
        pts.append((a[:, None] + u[None, :, None] * (b - a)[:, None] + v[None, :, None] * (c - a)[:, None]).reshape(-1, 3))
    P = np.concatenate(pts)
    pad = int(o["close"]) + 4
    lo = P.min(0) - pad * h
    n = np.ceil((P.max(0) + pad * h - lo) / h).astype(int) + 1
    g = np.zeros(n, bool)
    ij = np.floor((P - lo) / h).astype(int)
    g[ij[:, 0], ij[:, 1], ij[:, 2]] = True
    ball = ndimage.generate_binary_structure(3, 1)
    c = int(o["close"])
    g = ndimage.binary_dilation(g, ball, iterations=c)
    g = ndimage.binary_fill_holes(g)
    g = ndimage.binary_erosion(g, ball, iterations=c + int(round(float(o["inset"]) / h)))
    f = ndimage.gaussian_filter(g.astype(np.float32), float(o["smooth"]))
    if f.max() < 0.5:
        return {"verts": np.zeros((0, 3), np.float32), "tris": np.zeros((0, 3), np.int64), "voxel": h, "inset": o["inset"]}
    try:
        vv, ff, _, _ = measure.marching_cubes(f, 0.5, step_size=int(o["step"]), allow_degenerate=False)
    except RuntimeError:  # (sh6) a sliver over 0.5 that the coarse step skips: no surface (Garrett's far tier, cap only)
        return {"verts": np.zeros((0, 3), np.float32), "tris": np.zeros((0, 3), np.int64), "voxel": h, "inset": o["inset"]}
    return {"verts": (vv * h + lo).astype(np.float32), "tris": ff.astype(np.int64), "voxel": h, "inset": float(o["inset"])}


def write_obj(path, verts, tris, name: str = "hair_shadow", yup: bool = True) -> None:
    """A plain OBJ (positions + faces): what every engine and DCC imports. yup: Blender's Z-up written Y-up (as the
    GLB beside it, and as OBJ importers expect: x, z, -y)."""
    V = np.asarray(verts, np.float64)
    if yup:
        V = np.stack([V[:, 0], V[:, 2], -V[:, 1]], 1)
    with open(path, "w") as fh:
        fh.write(f"o {name}\n")
        np.savetxt(fh, V, fmt="v %.5f %.5f %.5f")
        np.savetxt(fh, np.asarray(tris) + 1, fmt="f %d %d %d")
