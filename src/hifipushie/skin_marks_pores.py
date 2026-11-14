"""The base skin: pore zones, the pore field, pixel points, the base map (pores, micro relief, fine colour). Part of the skin's drawn marks (skin_marks.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import skin_marks
from .skin_marks import _ramp
from .skin_marks_beard import _lips_path
from .skin_marks_map import _save, head_mesh, outward, pix, scatter, sphere

def base_zones(J: dict):
    """weights(P) -> {zone: 0..1} for the pore zones and the colour gains, from the face's landmarks."""
    from .skin_zones import interocular
    io = interocular(J)
    L = lambda n: np.asarray(J[n], float)  # noqa: E731
    nb, tip, nos, lid = L("lm_nose_bridge"), L("lm_nose_tip"), L("lm_nostril.L"), L("lm_lid_lower.L")
    lips = _lips_path(J)
    mc = L("lm_mouth_corner.L")[1] + 0.25 * io

    def g(q, c, r):
        return np.exp(-(((q - c) / (np.asarray(r) * io)) ** 2).sum(1))

    def w(P):
        q = P.copy()
        q[:, 0] = np.abs(q[:, 0])
        nose = np.maximum(g(q, tip + [0.0, 0.05 * io, 0.0], [0.22, 0.3, 0.3]), g(q, nos + [0.06 * io, 0.0, 0.04 * io], [0.16, 0.2, 0.14]))
        nose = np.maximum(nose, 0.7 * g(q, 0.5 * (nb + tip), [0.12, 0.3, 0.3]))
        return {"nose": nose,
                "cheek": g(q, lid + io * np.array([-0.02, 0.05, -0.45]), [0.32, 0.4, 0.32]),
                "forehead": g(q, np.array([0.0, nb[1] + 0.2 * io, nb[2] + 0.75 * io]), [0.9, 0.6, 0.45]),
                "chin": g(q, L("lm_chin") + np.array([0.0, 0.0, 0.25 * io]), [0.4, 0.35, 0.3]),
                "alae": g(q, nos + [0.12 * io, 0.0, 0.0], [0.16, 0.25, 0.16]),
                "lips": lips.contains_points(P[:, [0, 2]], radius=0.0005) & (P[:, 1] < mc),
                "front": g(q, np.array([0.0, nb[1] + 0.3 * io, 0.5 * (nb[2] + tip[2])]), [1.0, 1.2, 1.3]),
                "lids": g(q, L("lm_lid_upper.L") + np.array([0, 0.03 * io, -0.06 * io]), [0.3, 0.4, 0.2]),
                "mouth": np.maximum(g(q, np.array([0.0, mc - 0.25 * io, L("lm_lip_upper")[2] + 0.12 * io]), [0.45, 0.4, 0.2]),
                                    g(q, np.array([0.0, mc - 0.25 * io, L("lm_lip_lower")[2] - 0.15 * io]), [0.4, 0.4, 0.22]))}
    return w


def _pore_field(W: dict):
    """Per point: pores per m2 and the median pore radius (m), blended over the zones."""
    k = np.zeros_like(W["nose"])
    den = np.zeros_like(k)
    rad = np.zeros_like(k)
    for z in ("nose", "cheek", "forehead", "chin"):
        k = k + W[z]
        den = den + W[z] * skin_marks.PORE_ZONES[z][0]
        rad = rad + W[z] * skin_marks.PORE_ZONES[z][1]
    s = np.maximum(k, 1.0)
    f = np.clip(k, 0, 1)
    den = den / s + (1 - f) * skin_marks.PORE_ZONES["face"][0]
    rad = rad / s + (1 - f) * skin_marks.PORE_ZONES["face"][1]
    # (few that read off the face's front: a 6th-read "even dark speckle from the scalp to the chin" was dirt)
    off = np.clip(1 - W["lids"] * 0.8, 0, 1) * (~W["lips"]) * (0.15 + 0.85 * np.clip(W["front"] + k, 0, 1))
    return den * 1e4 * off, rad


def _pixel_points(sp: dict, V, N, step: int = 4):
    """The head's surface point under each map pixel: the outermost skin along the wrap's ray (R interpolated over
    the mesh's outward vertices on a grid `step` px apart). Returns rows(y0, y1) -> (P (n, 3), on the head (n,), facing
    (n,): the surface normal . the wrap's ray, ~0 where the ray grazes it (the nose's sides: one pixel spans a long
    strip of skin there, and anything evaluated per pixel streaks)."""
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
    from scipy.ndimage import zoom
    fr = sp["fr"]
    o = np.asarray(fr["o"], float)
    V = np.asarray(V, float)
    keep = outward(sp, V, np.asarray(N, float), V)
    xv = pix(sp, V[keep])
    Rv = np.linalg.norm(V[keep] - o, axis=1)
    fv = (np.asarray(N, float)[keep] * (V[keep] - o)).sum(1) / np.maximum(Rv, 1e-9)
    W, H = sp["W"], sp["H"]
    gx, gy = np.meshgrid(np.arange(0, W + step, step, dtype=float), np.arange(0, H + step, step, dtype=float))
    R, fc = LinearNDInterpolator(xv, np.stack([Rv, fv], 1))(gx, gy).transpose(2, 0, 1)
    ok = np.isfinite(R)
    R[~ok] = NearestNDInterpolator(xv, Rv)(gx[~ok], gy[~ok])
    fc[~ok] = 0.0
    Rf = zoom(R, step, order=1)[:H, :W]
    ff = zoom(fc, step, order=1)[:H, :W]
    okf = zoom(ok.astype(np.float32), step, order=1)[:H, :W] > 0.5
    k, e1, e2 = (np.asarray(fr[x], float) for x in ("k", "dir", "right"))
    th = ((np.arange(W) + 0.5) / W - 0.5) * fr["su"] + fr["dc"] + fr["seam"]

    def rows(y0, y1):
        v = 1 - (np.arange(y0, y1) + 0.5) / H
        ph = (v - 0.5) * fr["sv"] + fr["phic"]
        cp, sph = np.cos(ph)[:, None, None], np.sin(ph)[:, None, None]
        d = cp * (np.cos(th)[None, :, None] * e1 + np.sin(th)[None, :, None] * e2) + sph * k
        return (o + Rf[y0:y1, :, None] * d).reshape(-1, 3), okf[y0:y1].ravel(), ff[y0:y1].ravel()
    return rows


def base_map(spec: dict, part: str, J: dict, o: dict) -> tuple[str, dict, dict]:
    """The base skin's unique map (file, placement, stats): what a character texture artist paints (or projects from a
    scan) into every face before any feature. r = relief, depth 0..1 (pores as pits sized by zone, the skin-line
    net's furrows, a 0.5-2 mm undulation; the layer makes it height, so the export bakes it into the normal map, and
    a little cavity tint); g = blood, 0.5 even (up: capillary redness in 1-3 mm blotches and threads beside the nose's
    wings; down: paler); b = melanin, 0.5 even (up: uneven pigment in 1-4 mm patches). o: pore_size (x the zones'
    radii), seed."""
    from . import store
    from .noise import fbm
    from .paint_patterns import cells
    from scipy.spatial import cKDTree
    sp = sphere(J, (-62.0, 72.0), 220.0, skin_marks.BASE_PX)
    V, N, F = head_mesh(spec, part, J)
    seed = int(o.get("seed", 0))
    size = float(o.get("pore_size", 1.0))
    key = hashlib.sha1(json.dumps([o, np.asarray(V[:50]).round(5).tolist(), len(V), sp["img"], skin_marks.VERSION, skin_marks.BASE_VERSION, skin_marks.PORE_ZONES],
                                  sort_keys=True, default=str).encode()).hexdigest()[:16]
    path = store.HOME / "_images" / f"mk_base_{key}.png"
    stats_f = path.with_suffix(".json")
    if path.exists() and stats_f.exists():
        return str(path), sp["img"], json.loads(stats_f.read_text())
    zones = base_zones(J)
    rng = np.random.default_rng(2100 + seed)
    # pores: scattered on the mesh by the zones' density, each a soft pit of its own size and depth
    top = max(z[0] for z in skin_marks.PORE_ZONES.values()) * 1e4
    P, Nrm, _ = scatter(V, N, F, lambda P_, N_: _pore_field(zones(P_))[0] / top, top, rng)
    P = P[outward(sp, P, Nrm, V)] if len(P) else P
    n = len(P)
    rad = _pore_field(zones(P))[1] * size * rng.lognormal(0, 0.3, n) if n else np.zeros(0)
    dep = rng.uniform(0.45, 1.0, n)
    tree = cKDTree(P) if n else None
    rmax = float(rad.max()) if n else 0.0
    W, H = sp["W"], sp["H"]
    out = np.zeros((H, W, 3), np.float32)
    rows = _pixel_points(sp, V, N)
    chunk = max(1, 400000 // W)
    for y0 in range(0, H, chunk):
        y1 = min(H, y0 + chunk)
        Q, ok, fac = rows(y0, y1)
        # (fades to even skin where the wrap grazes the surface, and toward the map's edges: no seam where it ends)
        ev = _ramp(np.minimum(np.arange(y0, y1) + 0.5, H - np.arange(y0, y1) - 0.5) / H, 0.0, 0.08)
        eu = _ramp(np.minimum(np.arange(W) + 0.5, W - np.arange(W) - 0.5) / W, 0.0, 0.05)
        edge = (ev[:, None] * eu[None, :]).ravel()
        keep = _ramp(fac, 0.05, 0.5) * edge   # relief: streaks where the ray grazes
        # colour only half fades there (its 1-2.5 mm blotches barely streak): faded to even, the nose's side read as a
        # pale band beside its wing (skin4's blind read)
        keep_c = (0.5 + 0.5 * _ramp(fac, 0.05, 0.5)) * edge
        wz = zones(Q)
        lip = wz["lips"]
        # relief: an undulation (0.5-2 mm), the polygonal net of skin lines (cells ~0.8 mm, furrows ~0.1 mm wide)
        peel = fbm(Q, 0.0012, 3, seed + 31) - 0.5 + 0.3 * (fbm(Q, 0.0006, 2, seed + 34) - 0.5)
        lines = _ramp(cells(Q, 0.0008, "edges", 0.9, seed + 32), 0.2, 0.0) * (0.6 + 0.8 * (fbm(Q, 0.006, 2, seed + 33) - 0.5))
        pit = np.zeros(len(Q))
        if n:
            d, i = tree.query(Q, k=3, distance_upper_bound=2.2 * rmax, workers=4)
            for j in range(3):
                ii = np.minimum(i[:, j], n - 1)
                t = np.where(np.isfinite(d[:, j]), d[:, j] / rad[ii], 9.0)
                pit = np.maximum(pit, dep[ii] * np.clip(1 - t * t, 0, 1) ** 2)
        rel = 0.3 * edge + keep * (0.3 * peel + 0.1 * lines * (~lip) + 0.4 * pit)
        # blood: blotches (2.5 mm and, stronger, 1.3 / 0.8 mm: big blotches read as a rash) stronger mid-face, threads beside the nose's wings
        # (round the mouth even: the blotches there read as a beard's shadow on a woman)
        calm = 1 - 0.6 * wz["mouth"]
        gr = (0.65 + 0.35 * np.clip(wz["cheek"] + wz["nose"] + 0.6 * wz["chin"], 0, 1) - 0.25 * wz["forehead"]) * calm
        blood = (0.2 * (fbm(Q, 0.0025, 3, seed + 41) - 0.5) + 0.42 * (fbm(Q, 0.0013, 2, seed + 45) - 0.5)
                 + 0.28 * (fbm(Q, 0.0008, 2, seed + 42) - 0.5))
        rid = 1 - np.abs(2 * fbm(Q, 0.004, 2, seed + 43) - 1)
        thread = _ramp(rid, 0.9, 0.985) * np.clip(1.5 * np.maximum(wz["alae"], 0.5 * wz["cheek"]), 0, 1)
        g = 0.5 + keep_c * (2.8 * gr * blood + 0.45 * thread)
        # melanin: uneven patches (3.5, 1.4 mm; a 0.7 mm grain read as dirt), more where the sun falls (forehead, cheeks, nose)
        gp = (0.6 + 0.4 * np.clip(wz["cheek"] + wz["nose"] + wz["forehead"], 0, 1)) * calm
        b = 0.5 + keep_c * 2.2 * gp * (0.3 * (fbm(Q, 0.0035, 3, seed + 51) - 0.5) + 0.55 * (fbm(Q, 0.0014, 2, seed + 52) - 0.5))
        for c, val in enumerate((rel, g, b)):
            val = np.where((ok & ~lip) if c else ok, val, 0.3 if c == 0 else 0.5)
            out[y0:y1, :, c] = np.clip(val, 0, 1).reshape(y1 - y0, W)
    _save(path, out)
    stats = {"pores": int(n), "size": [W, H], "px_m": skin_marks.BASE_PX}
    stats_f.write_text(json.dumps(stats))
    return str(path), sp["img"], stats
