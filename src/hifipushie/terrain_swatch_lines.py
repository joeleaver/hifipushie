"""The structure's lines (a macro map): joint openness, drawn beds and joints, `structure_lines`. Part of the terrain's material swatches (terrain_swatch.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import terrain_swatch
from . import noise
from .terrain_swatch import smoothstep

# m: the openness field's scales (across a family's joints, along their strike, up the face) and its 0..1 ramp
def joint_openness(X, m, B):
    """How open family m's joints are at points X (0..1): smooth value noise elongated along the family's strike and
    up the face, so a fracture corridor opens a few neighbouring joints together, the crack runs on through the beds
    above and below (stepping where each bed's set turns) and its strength wanders and tapers along it."""
    from .terrain_blocks import AZ
    a = math.radians(AZ[m])
    d = np.array([math.cos(a), math.sin(a)])
    J = terrain_swatch.JOINT_OPEN
    q = np.c_[X[:, :2] @ d / J["across"], X[:, :2] @ np.array([-d[1], d[0]]) / J["along"], X[:, 2] / J["up"]]
    v = noise._value_noise(np.ascontiguousarray(q), int(B["seed"]) + 700 + 11 * m)
    return smoothstep(J["lo"], J["hi"], v)


def _drawn_beds(p, Phi, dPhi, B, texel):
    """The nearest DRAWN bed plane at points: (signed distance m, + above it; its crack strength; the distance to the
    next drawn plane). Drawn planes are the open ones (terrain_blocks.ids' bed_crack: the same hash and stretches)
    beside a bed thicker than ~3 texels. Measured to the nearest plane of the point's own bed, the distance was noise
    inside a thin package (a plane every few cm), and the line's strength, gated to a texel round it so that noise
    stayed dark, stepped from texel row to texel row along it: the sawteeth."""
    from .terrain_blocks import _cuts, _h, NCUT
    n = len(Phi)
    S = B["super"]
    K0 = np.floor(Phi).astype(np.int64)
    Cs = {dk: _cuts(K0 + dk, B) for dk in (-2, -1, 0, 1)}
    best = np.full(n, np.inf)
    s_best = np.full(n, terrain_swatch.LINE_D)
    a_best = np.zeros(n)
    second = np.full(n, np.inf)
    for dk in (-1, 0, 1):
        K = K0 + dk
        C, Cb = Cs[dk], Cs[dk - 1]
        last_lo = np.max(np.where(Cb[:, :NCUT] < 1.0, Cb[:, :NCUT], 0.0), 1)  # (the top bed of the super-bed below)
        for i in range(NCUT):
            lo = K + C[:, i]
            valid = (C[:, i + 1] > C[:, i]) & ((i == 0) | (C[:, i] < 1.0))
            above = (C[:, i + 1] - C[:, i]) * S
            below = ((C[:, i] - C[:, i - 1]) if i else (1.0 - last_lo)) * S
            d = (Phi - lo) / dPhi
            pc = _h(K, np.full(n, i, np.int64), B["seed"] + 90)
            cand = valid & (pc > 0.75) & (np.abs(d) < terrain_swatch.LINE_D) & (np.maximum(above, below) > 2.8 * texel)
            if not cand.any():
                continue
            k = np.flatnonzero(cand)
            vn = noise._value_noise(np.c_[p[k, :2] / 8.0, (i + 16 * K[k]).astype(float)], B["seed"] + 92)
            cr = np.clip((pc[k] - 0.75) / 0.25, 0, 1) * np.clip((vn - 0.52) / 0.18, 0, 1)
            k, cr = k[cr > 0], cr[cr > 0]
            # (how open the crack is wanders along it over a metre or two, now and then closing: one strength over a
            # whole 8 m stretch drew a ruled ink line across the 10 m view once the line was clean)
            key = (i + 16 * K[k]).astype(float) + 0.5
            ow = noise._value_noise(np.c_[p[k, :2] / 1.7, key], B["seed"] + 93)
            gap = noise._value_noise(np.c_[p[k, :2] / 4.5, key], B["seed"] + 94)
            cr = cr * (0.3 + 0.7 * smoothstep(0.2, 0.7, ow)) * smoothstep(0.25, 0.4, gap)
            ad = np.abs(d[k])
            nearer = ad < best[k]
            second[k] = np.where(nearer, best[k], np.minimum(second[k], ad))
            kk = k[nearer]
            best[kk], s_best[kk], a_best[kk] = ad[nearer], d[kk], cr[nearer]
    return s_best, a_best, second


def _drawn_joints(p, I, B, fd, texel, n):
    """Per joint family the nearest present boundary of the point's own bed's set (terrain_blocks: absent boundaries
    merge blocks): (signed distance m along the joint's normal, the family's weight x joint_openness there, the
    distance to the next boundary, the joint's 3D normal)."""
    from .terrain_blocks import _joint_coord, _joint_frame, _absent, face_weight
    K, j, th = I["K"][:n], I["j"][:n], I["thick"][:n]
    out = []
    for m in range(len(I["edges"])):
        phi, dphi, n2 = _joint_coord(p, K, j, m, th, B)
        nrm, _ = _joint_frame(K, j, m, B)
        jj = (K * 16 + j) * 5 + m
        i0 = np.floor(phi).astype(np.int64)
        best = np.full(n, np.inf)
        sd = np.full(n, terrain_swatch.LINE_D)
        second = np.full(n, np.inf)
        for db in (-1, 0, 1, 2):
            b = i0 + db
            ok = ~_absent(b, jj, B["seed"] + 80 + 9)  # (every present boundary: which are drawn is joint_openness's)
            d = (phi - b) / dphi
            ad = np.where(ok, np.abs(d), np.inf)
            nearer = ad < best
            second = np.where(nearer, best, np.minimum(second, ad))
            sd = np.where(nearer, d, sd)
            best = np.where(nearer, ad, best)
        w = B["family"][m] * face_weight(n2, fd) * (th >= B["thin"])
        out.append((np.where(np.isfinite(best), sd, terrain_swatch.LINE_D), w * joint_openness(p, m, B), second, nrm))
    return out


def structure_lines(field, X, texel=0.25, N=None):
    """The rock structure's drawn lines at texels, as SIGNED distances (m, across the surface) and strengths, for the
    lines map: (s_bed, a_bed, s_joint, a_joint). At a few texels per metre a crack 3-5 cm wide can't be baked into
    colour (it blurs into a 0.5 m smudge), but a signed distance interpolates linearly across the line, so the shader
    cuts it crisp at any width (as a font's distance field does).
    X: the texels' points on the low poly (measured at the point projected onto the exact rock, every texel of a
    triangle bridging a ledge landed on its crease, on the bed plane: filled triangles); N: the low poly's smooth
    (interpolated) normal there. Every value is a smooth function of position within a line's reach (2026-10-01: the
    lines followed the 0.5 m mesh's zigzag as thorns at 40 m and sawteeth on bed lines at 10 m; the cause was the
    distance and the gating, not where it was measured: moving the points level onto the exact rock first changed
    nothing measurable):
    - the distance is to the nearest DRAWN plane (`_drawn_beds`) or joint (`_drawn_joints`), so it is a clean
      ramp across the line, and the strength is wide (LINE_GATE_TX texels) and constant across it: the shader's crisp
      cut follows the distance's zero, not the texel grid. Half-way to the next drawn line the distance flips sign (a
      false zero after interpolation): the strength is 0 there (it fades within 2 texels of that point);
    - distances are taken across the surface, not through space (/ the sine between the surface and the plane, from
      the low poly's smooth normal): on a tread lying near a bed plane the vertical distance stayed under the line's
      width over whole triangles. Where the surface runs within ~20 deg of a plane (a tread, a block's side) the line
      fades out on the same smooth normal (the old gate on the triangle's own normal switched it triangle by triangle:
      thorns; ungated, the mesh's wobble about the plane drew wavy false lines beside a crack)."""
    from . import terrain_blocks
    r = field.rock
    n = len(X)
    z = np.zeros(n)
    if not r or not r.get("blocks") or not n:
        return z, z, z, z
    B = r["blocks"]
    fd = field.face_dir(X[:, 0], X[:, 1])
    zoff = r["bed_offset"](X[:, :2]) if r.get("bed_offset") else 0.0
    pre = terrain_blocks._pre(X, B, fd, zoff)
    I = terrain_blocks.ids(X, B, fd, zoff, pre=pre)
    Phi, dPhi = pre[0], pre[1]
    g0, g1 = terrain_swatch.LINE_GATE_TX[0] * texel, terrain_swatch.LINE_GATE_TX[1] * texel
    gate = lambda s: 1.0 - smoothstep(g0, g1, np.abs(s))
    guard = lambda s, d2: smoothstep(0.0, 2.0 * texel, d2 - np.abs(s))
    s_b, a_b, d2b = _drawn_beds(X, Phi, dPhi, B, texel)
    if N is not None:
        sin_b = np.sqrt(np.maximum(1.0 - N[:, 2] ** 2, 0.02))
        s_b, d2b = s_b / sin_b, d2b / sin_b
        a_b = a_b * smoothstep(0.2, 0.4, sin_b)
    a_b = a_b * gate(s_b) * guard(s_b, d2b)
    fam = _drawn_joints(X, I, B, fd, texel, n)
    # (a bed crack breaks where a joint crosses it: the joint's block corners are knocked off there, not cut through)
    cross = np.zeros(n)
    for sd, w, d2, nrm in fam:
        cross = np.maximum(cross, np.clip(w, 0, 1) * (1 - smoothstep(0.08, 0.3, np.abs(sd))))
    a_b = a_b * (1 - 0.85 * cross)
    best = np.full(n, -1.0)
    runner = np.zeros(n)
    s_j, a_j = np.full(n, terrain_swatch.LINE_D), np.zeros(n)
    for sd, w, d2, nrm in fam:
        if N is not None:
            sn = np.sqrt(np.maximum(1.0 - ((N * nrm).sum(1)) ** 2, 0.02))
            sd, d2 = sd / sn, d2 / sn
            w = w * smoothstep(0.2, 0.4, sn)
        a = np.clip(w, 0, 1) * gate(sd) * guard(sd, d2)
        # (the family drawn at a point is the one whose line there is strongest: the family with the NEAREST boundary,
        # however faint, broke a strong crack into pieces wherever its own boundary came closer)
        take = a > best
        runner = np.where(take, np.maximum(best, 0.0), np.maximum(runner, a))
        best = np.where(take, a, best)
        s_j, a_j = np.where(take, sd, s_j), np.where(take, a, a_j)
    # (a joint stops at its bed's planes: faded out within ~1.5 texels of them; and only in beds thick enough for a
    # crack with some length (in a 0.7-1.4 m bed every open joint was a short dash of one width, the "pen ticks" of m02)
    # (where two families are nearly as strong, the drawn one can switch between neighbouring texels, and two distances
    # of either sign interpolate to a false zero: faded where the runner-up is close)
    a_j = a_j * smoothstep(0.0, 0.35, (best - runner) / np.maximum(best, 1e-9))
    th = terrain_swatch.JOINT_OPEN["thick"]
    a_j = a_j * smoothstep(0.6 * texel, 1.6 * texel, I["bed_edge"]) * smoothstep(th[0], th[1], I["thick"])
    return np.clip(s_b, -terrain_swatch.LINE_D, terrain_swatch.LINE_D), a_b, np.clip(s_j, -terrain_swatch.LINE_D, terrain_swatch.LINE_D), a_j
