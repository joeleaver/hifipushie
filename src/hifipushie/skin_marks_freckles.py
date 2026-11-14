"""Freckles: their density and their map. Part of the skin's drawn marks (skin_marks.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import skin_marks
from .skin_marks import _ramp, _unit
from .skin_marks_beard import _lips_path
from .skin_marks_map import _px_m, _save, draw, frames, head_mesh, jacobians, outward, scatter, sphere

# ---- freckles --------------------------------------------------------------------------------------------------------
def freckle_density(J: dict, o: dict):
    """Where freckles gather: what faces the sun (above and in front) on the nose, the malar cheeks, the forehead,
    less on the upper lip and chin; clusters from a low noise."""
    from .skin_zones import interocular
    from .paint_patterns import noise
    io = interocular(J)
    L = lambda n: np.asarray(J[n], float)  # noqa: E731
    sun = _unit(np.array([0.0, -0.55, 0.83]))
    nb, br, lid = L("lm_nose_bridge"), L("lm_nose_base"), L("lm_lid_lower.L")
    zones = o["zones"]
    seed = int(o.get("seed", 0))
    clump = float(o["clump"])

    def g(P, c, r):
        return np.exp(-(((P - c) / r) ** 2).sum(1))

    def dens(P, Nrm):
        q = P.copy()
        q[:, 0] = np.abs(q[:, 0])
        face = g(q, np.array([0.0, nb[1] + 0.4 * io, 0.5 * (nb[2] + br[2])]), np.array([1.25, 1.2, 1.25]) * io)
        w = zones["face"] * face
        w = np.maximum(w, zones["nose"] * g(q, np.array([0.0, nb[1] - 0.15 * io, 0.5 * (nb[2] + br[2]) + 0.05 * io]), np.array([0.28, 0.4, 0.5]) * io))
        w = np.maximum(w, zones["cheeks"] * g(q, lid + io * np.array([0.12, 0.05, -0.36]), np.array([0.6, 0.5, 0.36]) * io))
        w = np.maximum(w, zones["forehead"] * g(q, np.array([0.0, nb[1] + 0.2 * io, nb[2] + 0.75 * io]), np.array([0.9, 0.6, 0.45]) * io))
        w = np.maximum(w, zones["upper_lip"] * g(q, np.array([0.0, br[1] + 0.05 * io, br[2] - 0.2 * io]), np.array([0.4, 0.4, 0.15]) * io))
        w = np.maximum(w, zones["chin"] * g(q, L("lm_chin") + np.array([0.0, 0.0, 0.25 * io]), np.array([0.35, 0.35, 0.3]) * io))
        # (what faces the sun: the side of the cheek and the temple keep some, fading; a cut at N.sun = 0.05 left none
        # past the cheek's front, skin3 measured 0.01-0.04 of the peak there against 0.1-0.9 on ref_02 / 09 / 40-42)
        lit = _ramp(Nrm @ sun, -0.3, 0.55)
        nz = noise(P, {"scale": 0.018, "octaves": 2, "seed": 500 + seed})
        cl = (1 - clump) + clump * _ramp(nz, 0.3, 0.75) ** 1.5
        lips = _lips_path(J)
        inl = lips.contains_points(P[:, [0, 2]], radius=0.001) & (P[:, 1] < L("lm_mouth_corner.L")[1] + 0.25 * io)
        d = np.clip(w * lit * cl, 0, 1)
        d[inl] = 0
        # not on the lids' margins and eyes (the eye area keeps a few)
        eye = np.maximum(g(q, L("lm_lid_upper.L") + np.array([0, 0.03 * io, -0.02 * io]), np.array([0.28, 0.4, 0.13]) * io), 0)
        top = _ramp(q[:, 2], L("lm_brow_mid.L")[2] + 0.85 * io, L("lm_brow_mid.L")[2] + 0.45 * io)   # none up into the hairline
        return d * (1 - 0.85 * eye) * top
    return dens


def freckle_map(spec: dict, part: str, J: dict, o: dict) -> tuple[str, dict, dict]:
    """The freckle map's file, placement and stats. o: amount (density), size (median diameter m), clump, dark (share
    of darker ones), moles (count on the face), zones, seed."""
    from . import store
    sp = sphere(J, (-62.0, 72.0), 220.0, 0.00007)
    V, N, F = head_mesh(spec, part, J)
    key = hashlib.sha1(json.dumps([o, np.asarray(V[:50]).round(5).tolist(), len(V), sp["img"], skin_marks.VERSION],
                                  sort_keys=True, default=str).encode()).hexdigest()[:16]
    path = store.HOME / "_images" / f"mk_freckles_{key}.png"
    stats_f = path.with_suffix(".json")
    if path.exists() and stats_f.exists():
        return str(path), sp["img"], json.loads(stats_f.read_text())
    rng = np.random.default_rng(1300 + int(o.get("seed", 0)))
    W, H = sp["W"], sp["H"]
    R = np.zeros((H, W), np.float32)
    G = np.zeros((H, W), np.float32)
    B = np.zeros((H, W), np.float32)
    per_m2 = 1.2e6 * float(o["amount"])          # ~120 / cm2 where densest at amount 1: dense freckling is a field of specks (blind read: "10x the count, 3-5x smaller")
    dens = freckle_density(J, o)
    P, Nrm, d = scatter(V, N, F, dens, per_m2, rng)
    keep = outward(sp, P, Nrm, V)
    P, Nrm, d = P[keep], Nrm[keep], d[keep]
    n = len(P)
    if n:
        t1, t2 = frames(Nrm, np.tile([1.0, 0, 0], (n, 1)))
        x0, A = jacobians(sp, P, t1, t2)
        pxm = _px_m(A)
        big = rng.random(n) < 0.05          # a few larger ones among the specks (more read as splats)
        rad = 0.5 * float(o["size"]) * rng.lognormal(0, 0.35, n) * np.where(big, rng.uniform(1.5, 2.5, n), 1.0) * (0.75 + 0.4 * d)
        rad = np.clip(rad, 0.00012, 0.002)
        soft = rng.uniform(0.3, 0.9, n)
        lobes = rng.normal(0, 1, (n, 4)) * np.array([0.0, 0.08, 0.05, 0.03])   # nearly round
        ph = rng.uniform(0, 2 * np.pi, (n, 4))
        aspect = rng.uniform(0.75, 1.0, n)
        rot = rng.uniform(0, np.pi, n)
        inten = np.clip(rng.uniform(0.15, 1.0, n) * (0.7 + 0.5 * d), 0, 1)   # a wide range: light tan to deep brown
        dark = rng.random(n) < float(o["dark"])

        def shape(i, s, t):
            c, sn = np.cos(rot[i]), np.sin(rot[i])
            a = c * s + sn * t
            b = (-sn * s + c * t) / aspect[i]
            r = np.hypot(a, b)
            th = np.arctan2(b, a)
            edge = rad[i] * (1 + sum(lobes[i, k] * np.cos((k + 1) * th + ph[i, k]) for k in range(1, 4)))
            aa = pxm[i]
            return _ramp(r, edge * (1 + 0.5 * soft[i]) + aa, edge * (1 - soft[i]))
        reach = rad * 1.9 + 2 * pxm
        inten = np.where(dark, rng.uniform(0.8, 1.0, n), inten)
        draw(R, x0, A, reach, shape, inten)                  # every freckle, its darkness in its value
        draw(G, x0, A, reach, shape, np.where(dark, 1.0, 0.0))  # the darker ones alone
    # moles: a few, anywhere on the face, rounder, sharper, darker
    nm = int(o["moles"])
    if nm:
        fd = freckle_density(J, {**o, "zones": {k: 1.0 for k in skin_marks.FRECKLE_ZONES}, "clump": 0.0})
        Pm, Nm, _ = scatter(V, N, F, lambda P_, N_: np.clip(fd(P_, N_) * 3, 0, 1), 4e4, np.random.default_rng(1700 + int(o.get("seed", 0))))
        if len(Pm):
            pick = np.random.default_rng(1800 + int(o.get("seed", 0))).choice(len(Pm), min(nm, len(Pm)), replace=False)
            Pm, Nm = Pm[pick], Nm[pick]
            t1, t2 = frames(Nm, np.tile([1.0, 0, 0], (len(Pm), 1)))
            x0, A = jacobians(sp, Pm, t1, t2)
            pxm = _px_m(A)
            radm = np.random.default_rng(1900).uniform(0.0007, 0.0018, len(Pm))

            def mshape(i, s, t):
                return _ramp(np.hypot(s, t), radm[i] + pxm[i], radm[i] * 0.75)
            draw(B, x0, A, radm + 2 * pxm, mshape, np.ones(len(Pm)))
    _save(path, np.dstack([R, G, B]))
    stats = {"freckles": int(n), "moles": nm, "size": [W, H]}
    stats_f.write_text(json.dumps(stats))
    return str(path), sp["img"], stats
