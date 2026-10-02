"""Jointed, bedded rock: the medium scale (0.3-10 m) of solid rock faces, as a field offset (+ carves, - builds).

How rock breaks, and what read wrong before (renders r01-r03: courses of dressed rectangular stone, every block
outlined, near-uniform sizes, joints at right angles to the beds: a dry-stone wall):
- beds: uneven in thickness. Super-beds `super` m thick (a monotone warp of height, so they pinch and swell) are each
  split at 0-5 random cuts: many thin beds, few thick (an exponential-like spread, 0.1-6 m). Thin beds (< `thin`)
  are recessed as a package (they weather back); thick beds stand proud by thickness. Thin beds are below the meshing
  voxel: geometry recesses the package, the maps draw its laminae.
- minor joints: inside each bed only (they stop at its planes), spaced ~1.3 x the bed's thickness (thin beds: many
  small blocks; thick beds: few big ones), each bed's joints turned on their own (+-20 deg in plan, dipping 72-90 deg
  either way: traces lean a little on the face; all at right angles to the beds read as masonry, 60-90 deg as
  slumped), a large-scale density change and absent
  boundaries (blocks merge). Closed joints: a block's face tipped differently from its neighbour's and a small step,
  no dark line (`open` decides the few drawn ones).
- master joints: a few long open joints (segments 20-50 m up the face, en echelon, leaning +-25 deg, wavy), spaced
  ~25 m: a rounded groove, always dark. These dominate from 150 m.
- a family whose planes run along the face (|cos| to the face's normal > 0.93) fades out: it IS the face.

Continuity (a jump meshes as black shards): every piecewise-constant value is BOX-FILTERED over +-`ramp` m in its own
coordinate (beds along the bed coordinate, blocks along the joint coordinate, the filter's width carried through the
warp's slope): thick beds and wide blocks get linear ramps with creases at their ends; beds or blocks thinner than
the ramp are averaged, never stepped (a ramp per boundary jumped where two boundaries came closer than the ramp).
A tilt within a cell is linear, so its box-filtered value is its value at the overlap's centre.

`ids(p, B, fd)`: the structure for colour and the maps (bed, thickness, block, open cracks, master joints)."""
from __future__ import annotations

import math

import numpy as np

from . import fieldjit, noise

AZ = (37.0, 97.0, 157.0)     # joint families' plan normals (deg from +x), 60 deg apart: every face is crossed by one
SPACE = (1.0, 1.3, 1.7)      # minor joint spacing per family, x the bed's
LEVER = 3.0                  # a cell's tilt acts at most this far (m) from its middle
P_ABSENT = 0.35              # share of minor joint boundaries absent (never two in a row)
NCUT = 6                     # beds per super-bed: 1..NCUT
SLOTS = 3                    # minor blocks either side of a point's own block in the box filter
SOFT = 0.1                   # m: the filter's box is softened by this either side (creases rounded over 0.2 m)


def config(size, vox, scale=1.0):
    """Settings for a terrain: `size` the solid rock's facet size (m), vox the meshing voxel."""
    out = {"super": float(np.clip(0.5 * size, 2.5, 6.0)) * scale, "thin": 0.7 * scale,
            "joint": 1.3, "joint_min": 1.0 * scale, "joint_max": 5.0 * scale,
            "family": [1.0, 0.7, 0.5], "amp": 0.15 * scale, "tip": 0.1,
            "recess": 0.45 * scale, "p_recess": 0.015, "proud": 0.4 * scale, "p_proud": 0.04,
            "package": 0.22 * scale, "thick_proud": 0.5 * scale, "bed_amp": 0.12 * scale, "bed_tilt": 0.12,
            "open": 0.08,                                     # share of minor joints drawn as open cracks
            "master": {"spacing": float(np.clip(2.5 * size, 15.0, 25.0)) * scale, "p": 0.55, "seg": 35.0 * scale, "p_seg": 0.65,
                       "depth": 0.5 * scale, "half": max(0.6, 1.4 * vox), "taper": 6.0 * scale},
            "ramp": max(0.45, 1.0 * vox), "seed": 9100, "back": 0.3 * scale, "build": 0.12 * scale, "fallen": 1.0, "fall_min": max(0.6, 1.8 * vox), "chip": 0.35 * scale}
    # (the most the structure moves the surface, either way: the field's reach and the cliff overlay's push/shell
    # thickness. Measured: offsets -0.12..1.44 m over 400k random points; the sum of every term's maximum, 3 m,
    # thickened the cliff shell round caves by 3 m and a tile corner in pebble's karst passage decimated badly)
    out["relief"] = 1.6 * scale
    return out


# ---------------------------------------------------------------- leaves

def _vn(q, a, b, seed):
    """Value noise (noise._value_noise, the same values) of a coordinate q with two more coordinates a, b (lattice
    units), and its derivative along q (analytic: finite differences cost three evaluations)."""
    p = np.c_[q, a, b]
    i = np.floor(p).astype(np.int64)
    f = p - i
    u = f * f * f * (f * (f * 6 - 15) + 10)
    du = 30 * f[:, 0] ** 2 * (f[:, 0] - 1) ** 2
    out = np.zeros(len(p))
    d = np.zeros(len(p))
    for dy in (0, 1):
        for dz in (0, 1):
            w = np.where(dy, u[:, 1], 1 - u[:, 1]) * np.where(dz, u[:, 2], 1 - u[:, 2])
            h0 = noise._hash(i[:, 0], i[:, 1] + dy, i[:, 2] + dz, seed)
            h1 = noise._hash(i[:, 0] + 1, i[:, 1] + dy, i[:, 2] + dz, seed)
            out += w * (h0 + u[:, 0] * (h1 - h0))
            d += w * du * (h1 - h0)
    return out, d


def _warp(x, sp, a, b, seed, big=0.25, jit=0.1):
    """x / sp warped, and its slope (per m): a large-scale density change (cells ~0.55-7 x sp, in regions ~4 sp
    across) plus a small jitter. Monotone: value noise's slope is at most ~1.7, so the slope stays
    (1 +- 2 x 0.25 x 1.7 +- 0.14) / sp > 0 (0.45 folded it: cells repeated)."""
    L = 4 * sp
    v1, d1 = _vn(x / L, a, b + 0.5, seed + 1)
    v2, d2 = _vn(0.8 * x / sp, a, b, seed)
    phi = (x + L * big * (2 * v1 - 1)) / sp + jit * v2
    dphi = (1 + 2 * big * d1) / sp + jit * 0.8 * d2 / sp
    return phi, np.maximum(dphi, 0.08 / sp)


def _win(lo, hi, c, a, e):
    """The weight of interval [lo, hi] under a window round c: a box of half-width a softened by e either side (a
    trapezoid of unit area): G(hi - c) - G(lo - c). The softening rounds the box filter's creases into C1 curves."""
    def R(x):  # integral of a ramp from 0 to 1 over [-e, e]
        return np.where(x < -e, 0.0, np.where(x > e, x, (x + e) ** 2 / (4 * e)))
    G = lambda t: (R(t + a) - R(t - a)) / (2 * a)
    return G(hi - c) - G(lo - c)


def _smin(a, b, k):
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * h * k / 6.0


def _h(i, j, s):
    return noise._hash(i, j, np.zeros_like(i), s)


def face_weight(n2, fd):
    """0..1 per point: how much planes with plan normal n2 (n, 2, unit) cross the face (fd: the ground's downhill
    gradient: the face's plan normal x its slope). Within ~20 deg of running along the face: none."""
    cs = np.abs((fd * n2).sum(1)) / np.sqrt((fd * fd).sum(1) + 0.04)
    x = np.clip((cs - 0.93) / (0.7 - 0.93), 0, 1)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- beds

def _cuts(K, B):
    """The bed boundaries of super-beds K (n,): (n, NCUT + 1) fractions in [0, 1], sorted, padded with 1 (the first
    is 0, the end is 1)."""
    s = B["seed"] + 20
    # beds in this super-bed: often one massive bed, sometimes a thinly bedded package (an even split everywhere read
    # as plywood from 150 m)
    nb = 1 + np.floor(_h(K, K * 0, s) ** 1.2 * NCUT).astype(np.int64)
    c = np.stack([_h(K, K * 0 + k, s + 1) for k in range(1, NCUT)], 1)
    c = np.where(np.arange(1, NCUT)[None] < nb[:, None], c, 1.0)
    c = np.sort(c, 1)
    return np.c_[np.zeros(len(K)), c, np.ones(len(K))]


def _bed_coord(p, B, zoff):
    """The super-bed coordinate Phi (super-bed K = floor(Phi)) and its slope up the face (per m); beds undulate ~0.15
    super over ~10 m."""
    S = B["super"]
    und = 0.3 * S * (noise._value_noise(np.c_[p[:, :2] / 10.0, np.full(len(p), 3.5)], B["seed"] + 2) - 0.5) + \
        0.5 * S * (noise._value_noise(np.c_[p[:, :2] / 28.0, np.full(len(p), 7.5)], B["seed"] + 3) - 0.5)
    # (the second octave: a ledge's shadow ran ruler-straight for 35-41 m in the 150 m view)
    # (and rough at the block scale, +-0.15 m over ~3 m: smooth bed edges read as sawn lumber at 40 m; over ~1 m the
    # creases wiggled within 2 voxels: black shards at tile borders, 0.09% of pebble's LOD 0. Slope < 0.3: the
    # coordinate stays monotone up the face)
    und = und + 0.3 * (noise._value_noise(p / 3.0, B["seed"] + 5) - 0.5)
    return _warp(p[:, 2] + zoff + und, S, p[:, 0] / 40.0, p[:, 1] / 40.0, B["seed"])


def _bed_slots(Phi, dPhi, B, a):
    """The beds a box of half-width a (Phi units) round each point overlaps: per point up to 3 x (NCUT) slots of
    (super-bed K, bed index j, lo, hi (Phi), overlap length, overlap centre, nominal thickness m). Returned flattened
    with the point index of each slot whose overlap is > 0, plus the point's own bed."""
    K0 = np.floor(Phi).astype(np.int64)
    rows, Ks, js, los, his = [], [], [], [], []
    n = len(Phi)
    for dk in (-1, 0, 1):
        K = K0 + dk
        C = _cuts(K, B)
        lo = K[:, None] + C[:, :-1]
        hi = K[:, None] + C[:, 1:]
        rows.append(np.repeat(np.arange(n)[:, None], NCUT, 1))
        Ks.append(np.repeat(K[:, None], NCUT, 1))
        js.append(np.repeat(np.arange(NCUT)[None], n, 0))
        los.append(lo)
        his.append(hi)
    R, K, J = np.concatenate(rows, 1), np.concatenate(Ks, 1), np.concatenate(js, 1)
    lo, hi = np.concatenate(los, 1), np.concatenate(his, 1)
    a_ = a[:, None]
    e_ = np.maximum(SOFT * dPhi[:, None], 1e-9)
    # (each bed's weight under the softened box: zero where the window doesn't reach it)
    ol = _win(lo, hi, Phi[:, None], a_, np.minimum(e_, 0.9 * a_)) if np.all(a > 0) else np.zeros(lo.shape)
    own = (lo <= Phi[:, None]) & (Phi[:, None] < hi) & (hi > lo)
    sel = (ol > 0) & (hi > lo)
    oc = 0.5 * (np.minimum(hi, Phi[:, None] + a_) + np.maximum(lo, Phi[:, None] - a_))
    th = (hi - lo) * B["super"]  # (nominal m: one value per bed, so the thin/thick choice and the joint spacing never
    # change inside a bed; the metric thickness at the point, (hi - lo) / dPhi, varies with the warp)
    flat = lambda A: A[sel]
    o = np.argmax(own, 1)
    own_bed = {"K": K[np.arange(n), o], "j": J[np.arange(n), o], "lo": lo[np.arange(n), o], "hi": hi[np.arange(n), o],
               "thick": th[np.arange(n), o]}
    return {"row": flat(R), "K": flat(K), "j": flat(J), "lo": flat(lo), "hi": flat(hi), "ol": flat(ol),
            "oc": flat(oc), "thick": flat(th)}, own_bed


def _bed_value(K, j, thick, t_m, xy, B):
    """A bed's own offset: thin beds recessed as a package, thick beds proud by their thickness, a little random, and
    a tilt up the bed (t_m: m from the bed's middle). How far a bed stands out or sits back changes along the strike
    (~15 m, xy: plan position): the same recess along a whole cliff was a ruled black line (the pebble chasm, r07)."""
    s = B["seed"] + 30
    h1, h2 = _h(K, j, s), _h(K, j, s + 1)
    thin = thick < B["thin"]
    vn = noise._value_noise(np.c_[xy / 9.0, (K * 16 + j).astype(float)], s + 2)
    # (a thin package sits back only in stretches: set back wherever the noise allowed (~85%), it ran the whole pebble
    # chasm as one dark ruled line)
    along = np.where(thin, np.clip((vn - 0.4) / 0.25, 0, 1), np.clip(1.4 * vn - 0.25, 0, 1))
    v = along * np.where(thin, B["package"], -B["thick_proud"] * np.clip((thick - 1.2) / 2.5, 0, 1))
    # (and how deep it sits back wanders within a stretch: flush for a metre or two every few metres (weathered back
    # less, or choked with its own debris), lumpy over a metre. One depth along a stretch put the bed above's
    # underside, facing straight down, in the maps as one dark band along the pebble chasm, 0.2 m tall and 8 m long)
    kj = (K * 16 + j).astype(float)
    vd = noise._value_noise(np.c_[xy / 2.5, kj], s + 3)
    vr = noise._value_noise(np.c_[xy / 0.9, kj], s + 4)
    v = np.where(thin, v * (np.clip((vd - 0.35) / 0.4, 0, 1) * (0.55 + 0.45 * vr)), v)
    return v + B["bed_amp"] * (2 * h1 - 1) + B["bed_tilt"] * (2 * h2 - 1) * np.clip(t_m, -LEVER, LEVER)


# ---------------------------------------------------------------- minor joints

def _joint_frame(K, j, m, B):
    """Bed (K, j)'s family-m joint normal (n, 3): the family's plan direction turned +-20 deg, dipping 72-90 deg
    either way."""
    s = B["seed"] + 40 + 7 * m
    az = np.radians(AZ[m] + 20.0 * (2 * _h(K, j, s) - 1))
    dip = np.radians(72.0 + 18.0 * _h(K, j, s + 1)) * np.where(_h(K, j, s + 2) < 0.5, 1, -1)
    sd, cd = np.sin(np.abs(dip)), np.cos(dip)
    return np.stack([np.cos(az) * sd, np.sin(az) * sd, cd], 1), np.stack([np.cos(az), np.sin(az)], 1)


def _absent(i, j, s):
    return (_h(i, j, s) < P_ABSENT) & ~(_h(i - 1, j, s) < P_ABSENT)


def _joint_coord(p, K, j, m, thick, B):
    """Bed (K, j)'s family-m block coordinate at points: phi (block = floor), its slope (per m), the plan normal."""
    nrm, n2 = _joint_frame(K, j, m, B)
    sp = np.clip(B["joint"] * thick, B["joint_min"], B["joint_max"]) * SPACE[m]
    s = B["seed"] + 60 + m
    bid = (K * 16 + j).astype(float)
    wav = 0.25 * sp * (noise._value_noise(np.c_[p[:, 2] / (1.5 * sp), bid, np.full(len(p), m + 0.5)], s + 7) - 0.5)
    x = (p * nrm).sum(1) + wav + 0.4 * (noise._value_noise(p / 3.0, s + 9) - 0.5)  # (rough edges, +-0.2 m / 3 m)
    phi, dphi = _warp(x, sp, bid, np.full(len(p), float(m)), s)
    return phi, dphi, n2


def _joint_value(i, jj, t_m, B, half=None, z_m=None, zh=None):
    """Minor block i (merged across absent boundaries) of joint set jj: mostly nearly flush (+-amp), a few missing
    (recess) or standing out (proud), each face tipped on its own (t_m: m from the block's middle). With the block's
    half-width `half`, the point's height from its bed's middle `z_m` and the bed's half-thickness `zh` (m): one or two
    corners knocked off (a diagonal plane carving up to `chip` m into the corner): straight joints between level beds
    outlined every block as a rectangle (stacked lumber, masonry)."""
    s = B["seed"] + 80
    g = i - _absent(i, jj, s + 9)
    h1, h2, h3 = _h(g, jj, s), _h(g, jj, s + 1), _h(g, jj, s + 2)
    v = B["amp"] * (2 * h1 - 1)
    v = np.where(h2 < B["p_recess"], B["recess"] * (0.6 + 0.8 * h1), v)
    v = np.where(h2 > 1 - B["p_proud"], -B["proud"] * (0.6 + 0.8 * h1), v)
    v = v + B["tip"] * (2 * h3 - 1) * np.clip(t_m, -LEVER, LEVER)
    if half is not None and B.get("chip", 0) > 0:
        a = t_m / np.maximum(half, 0.2)
        b = z_m / np.maximum(zh, 0.2)
        for c in range(2):
            hc = _h(g, jj, s + 3 + c)
            st = np.where(_h(g, jj, s + 5 + 2 * c) < 0.5, 1.0, -1.0)
            sz = np.where(_h(g, jj, s + 6 + 2 * c) < 0.5, 1.0, -1.0)
            u = st * a + sz * b  # (2 at the corner)
            on = hc < (0.6 if c == 0 else 0.3)
            x = np.clip((u - 0.6) / 1.0, 0, 1)  # (smooth: a C0 crease inside a face is a sub-voxel edge to mesh)
            v = v + on * B["chip"] * (0.5 + 0.5 * hc) * x * x * (3 - 2 * x)
    return v


def _block_mid(i, jj, s):
    """A block's group middle (phi units): merged with the one below if its lower boundary is absent, with the one
    above if the next boundary is absent."""
    return i + 0.5 + 0.5 * _absent(i + 1, jj, s) - 0.5 * _absent(i, jj, s)


def _joints_in_bed(p, K, j, thick, fd, B, ramp, sharp=None, z_m=None, zh=None):
    """The minor joints' offset inside bed (K, j) at points p: per family, box-filtered over +-ramp along the joint
    coordinate, weighted by how much the family crosses the face. With `sharp` (a narrower ramp, m) also the same
    filtered over +-sharp (the maps' crisp edges), from the same blocks: (wide, sharp)."""
    out = np.zeros(len(p))
    out2 = np.zeros(len(p)) if sharp is not None else None
    s = B["seed"] + 80 + 9
    for m in range(len(AZ)):
        phi, dphi, n2 = _joint_coord(p, K, j, m, thick, B)
        w = B["family"][m] * face_weight(n2, fd) * (thick >= B["thin"])  # (no geometric joints in thin beds)
        k = np.flatnonzero(w > 0)
        if not len(k):
            continue
        ph, dp = phi[k], dphi[k]
        a = ramp * dp
        jj = (K[k] * 16 + j[k]) * 5 + m
        i0 = np.floor(ph).astype(np.int64)
        acc = np.zeros(len(k))
        acc2 = np.zeros(len(k))
        e = np.minimum(SOFT * dp, 0.9 * a)
        if sharp is not None:
            a2 = sharp * dp
            e2 = np.minimum(np.minimum(SOFT, 0.5 * sharp) * dp, 0.9 * a2)
        for di in range(-SLOTS, SLOTS + 1):
            i = i0 + di
            ol = _win(i, i + 1, ph, a, e)
            kk = np.flatnonzero((ol > 0) | ((_win(i, i + 1, ph, a2, e2) > 0) if sharp is not None else False))
            if not len(kk):
                continue
            oc = 0.5 * (np.minimum(i[kk] + 1, ph[kk] + a[kk]) + np.maximum(i[kk], ph[kk] - a[kk]))
            t_m = (oc - _block_mid(i[kk], jj[kk], s)) / dp[kk]
            if z_m is None:
                v = _joint_value(i[kk], jj[kk], t_m, B)
            else:  # (the block's half-width: its group's extent, 1-3 blocks)
                ext = 1 + _absent(i[kk], jj[kk], s) + _absent(i[kk] + 1, jj[kk], s)
                v = _joint_value(i[kk], jj[kk], t_m, B, 0.5 * ext / dp[kk], z_m[k][kk], zh[k][kk])
            acc[kk] += ol[kk] * v
            if sharp is not None:  # (the slots either window reaches)
                acc2[kk] += _win(i[kk], i[kk] + 1, ph[kk], a2[kk], e2[kk]) * v
        out[k] += w[k] * acc
        if sharp is not None:
            out2[k] += w[k] * acc2
    return out if sharp is None else (out, out2)


# ---------------------------------------------------------------- master joints

def _masters(p, fd, B):
    """The few long open joints: per family, planes ~`spacing` apart (each present or not, its own offset and a lean
    of +-15 deg), open in segments `seg` m tall with gaps between (en echelon), wavy at two scales (~1.2 m over ~14 m,
    ~0.3 m over ~4 m: a 60 m dead-straight groove read as a ruler from 150 m). Returns (groove depth 0..1 per point,
    distance to the nearest master joint (m))."""
    M = B["master"]
    depth = np.zeros(len(p))
    near = np.full(len(p), np.inf)
    s0 = B["seed"] + 200
    for m in range(len(AZ)):
        az = math.radians(AZ[m])
        n2 = np.array([math.cos(az), math.sin(az)])
        w = face_weight(np.tile(n2, (len(p), 1)), fd)
        k = np.flatnonzero(w > 0)
        if not len(k):
            continue
        q = p[k]
        s = s0 + 11 * m
        sp = M["spacing"] * SPACE[m]
        # (the wander belongs to the point, not the plane: one noise per family instead of one per candidate)
        t2 = np.c_[-n2[1], n2[0]]
        u = q[:, :2] @ t2[0]
        wav = 2.4 * (noise._value_noise(np.c_[q[:, 2] / 14.0, u / 14.0, np.full(len(q), m + 0.5)], s + 6) - 0.5) + \
            0.6 * (noise._value_noise(np.c_[q[:, 2] / 4.0, u / 4.0, np.full(len(q), m + 7.5)], s + 8) - 0.5)
        x = q[:, :2] @ n2 + wav
        zq = q[:, 2]
        i0 = np.floor(x / sp).astype(np.int64)
        zs = np.floor(zq / M["seg"]).astype(np.int64)
        best = np.zeros(len(k))
        dmin = np.full(len(k), np.inf)
        for di in (-1, 0, 1):
            i = i0 + di
            ok = _h(i, i * 0 + m, s) < M["p"]
            if not ok.any():
                continue
            x0 = (i + 0.5 + 0.35 * (2 * _h(i, i * 0 + m, s + 5) - 1)) * sp
            lean = math.tan(math.radians(15.0)) * (2 * _h(i, i * 0 + m, s + 4) - 1)
            op = 0.4 + 0.6 * _h(i, i * 0 + m, s + 7)
            g = np.zeros(len(k))
            for dz in (-1, 0, 1):  # the segments it's open in: each its own height range, en echelon (stepped aside)
                zk = zs + dz
                on = ok & (_h(i, zk, s + 1) < M["p_seg"])
                zc = (zk + 0.5 + 0.3 * (2 * _h(i, zk, s + 2) - 1)) * M["seg"]
                half = 0.5 * M["seg"] * (0.5 + 0.6 * _h(i, zk, s + 3))
                ends = on * np.clip((half - np.abs(zq - zc)) / M["taper"], 0, 1)
                # (leaning about the segment's own middle; one far origin would shift it by hundreds of metres)
                d = np.abs(x - (x0 + 1.5 * (2 * _h(i, zk, s + 9) - 1) + lean * (zq - zc)))
                v = np.clip(1 - d / M["half"], 0, 1)
                g = np.maximum(g, op * ends * v * v * (3 - 2 * v))  # (a rounded groove: smooth floor and lips)
                dmin = np.where(ends > 0, np.minimum(dmin, d), dmin)
            best = np.maximum(best, g)
        depth[k] = np.maximum(depth[k], w[k] * best)
        near[k] = np.minimum(near[k], np.where(w[k] > 0.3, dmin, np.inf))
    return depth, near


# ---------------------------------------------------------------- the field and the structure

def structure(p, B, fd, zoff=0.0, want_ids=False, sharp=None):
    """offsets(...) and, with want_ids, ids(...) at the same points, sharing the bed coordinate and the master joints
    (the bake asks for both at every field point). With `sharp` (m), ids["sharp"] = the offsets filtered over
    +-sharp instead of +-ramp, minus the offsets: what the maps add for crisp block edges (the mesh can't hold an
    edge narrower than ~2 voxels; the maps can, down to ~2 texels)."""
    if not len(p):
        I = ids(p, B, fd, zoff) if want_ids else None
        if I is not None and sharp is not None:
            I["sharp"] = np.zeros(0)
        return np.zeros(0), I
    pre = _pre(p, B, fd, zoff)
    if sharp is None:
        return offsets(p, B, fd, zoff, pre), (ids(p, B, fd, zoff, pre) if want_ids else None)
    o, o2 = offsets(p, B, fd, zoff, pre, sharp)
    I = ids(p, B, fd, zoff, pre) if want_ids else {}
    I["sharp"] = o2 - o
    return o, I


def offsets(p, B, fd, zoff=0.0, pre=None, sharp=None):
    """The rock structure's field offset at points p (n, 3); fd the face's gradient per point (n, 2); zoff the big
    beds' wander (m). With `sharp` (m): (offsets, the same filtered over +-sharp: crisper than the mesh's ramp at a
    fine texel, softer at a coarse one, where the ramp's edges would alias)."""
    n = len(p)
    if not n:
        return np.zeros(0) if sharp is None else (np.zeros(0), np.zeros(0))
    ramp = B["ramp"]
    Phi, dPhi, mast = pre if pre is not None else _pre(p, B, fd, zoff)
    if fieldjit.ON:  # (the compiled sums, bit-identical)
        o, o2 = fieldjit.blocks_offsets(p, B, fd, Phi, dPhi, sharp, _cuts, _joint_frame, NCUT)
        md = B["master"]["depth"] * mast[0]
        if sharp is None:
            return _carve(o, B) + md
        return _carve(o, B) + md, _carve(o2, B) + md
    a = ramp * dPhi
    # (the beds either window reaches: a coarse LOD's bake asks for a sharp window WIDER than the ramp)
    S, _ = _bed_slots(Phi, dPhi, B, max(ramp, sharp or 0.0) * dPhi)
    r = S["row"]
    if sharp is not None and sharp > ramp:
        S["ol"] = _win(S["lo"], S["hi"], Phi[r], a[r], np.minimum(SOFT * dPhi[r], 0.9 * a[r]))
        S["oc"] = 0.5 * (np.minimum(S["hi"], Phi[r] + a[r]) + np.maximum(S["lo"], Phi[r] - a[r]))
    mid = 0.5 * (S["lo"] + S["hi"])
    v = _bed_value(S["K"], S["j"], S["thick"], (S["oc"] - mid) / dPhi[r], p[r, :2], B)
    J = _joints_in_bed(p[r], S["K"], S["j"], S["thick"], fd[r], B, ramp, sharp,
                       (S["oc"] - mid) / dPhi[r], 0.5 * (S["hi"] - S["lo"]) / dPhi[r])
    md = B["master"]["depth"] * mast[0]
    if sharp is None:
        return _carve(np.bincount(r, S["ol"] * (v + J), minlength=n), B) + md
    a2 = sharp * dPhi[r]
    e2 = np.minimum(np.minimum(SOFT, 0.5 * sharp) * dPhi[r], 0.9 * a2)
    ol2 = _win(S["lo"], S["hi"], Phi[r], a2, e2)
    return (_carve(np.bincount(r, S["ol"] * (v + J[0]), minlength=n), B) + md,
            _carve(np.bincount(r, ol2 * (v + J[1]), minlength=n), B) + md)


def _pre(p, B, fd, zoff):
    """The bed coordinate, its slope and the master joints at points: what offsets and ids share."""
    if fieldjit.ON and len(p):
        return fieldjit.blocks_pre(p, B, fd, zoff, AZ)
    return (*_bed_coord(p, B, zoff), _masters(p, fd, B))


def _carve(o, B):
    """The structure set back `back` m and its building side softly capped at -`build` m (a smooth, monotone clamp):
    proud beds and blocks standing out over a cliff's lip built slabs in the air (a 42-triangle piece floating 27 m over
    pebble's heightmap). Mostly the structure carves, as weathering does."""
    x = o + B["back"] + B["build"]
    k = 0.15
    return -B["build"] + k * np.logaddexp(0.0, x / k)


def ids(p, B, fd, zoff=0.0, pre=None):
    """Structure at points for colour and the maps: the bed (K, j), its thickness and whether it's thin, the distance
    (m) to the nearest bed plane and that plane's crack strength (0..1: drawn only where > 0), per family the block
    id, the family's weight and its distance to an open joint (inf where the nearest boundary is closed), and the
    master joints (groove 0..1, distance m)."""
    Phi, dPhi, mast = pre if pre is not None else _pre(p, B, fd, zoff)
    if fieldjit.ON and len(p):
        K, j, fo, blocks, fam = fieldjit.blocks_ids(p, B, fd, Phi, dPhi, _cuts, _joint_frame, NCUT)
        out = {"K": K, "j": j, "thick": fo[:, 0], "thin": fo[:, 4] > 0, "bed_edge": fo[:, 1], "below_top": fo[:, 2],
               "bed_crack": fo[:, 3], "blocks": list(blocks), "weights": [fam[m, :, 0] for m in range(len(AZ))],
               "edges": [fam[m, :, 1] for m in range(len(AZ))], "open": [fam[m, :, 2] for m in range(len(AZ))]}
        out["master"], out["master_d"] = mast
        return out
    _, own = _bed_slots(Phi, dPhi, B, np.zeros(len(p)))
    K, j, th = own["K"], own["j"], own["thick"]
    d_lo, d_hi = (Phi - own["lo"]) / dPhi, (own["hi"] - Phi) / dPhi
    # a bed plane is drawn (open) where the beds either side differ much in how they stand (a ledge), by chance
    plane_hi = d_hi < d_lo
    # (the plane's key, the same from both sides: the top of super-bed K is bed 0 of K + 1)
    top = own["hi"] >= K + 1 - 1e-9
    Kp = np.where(plane_hi & top, K + 1, K)
    jp = np.where(plane_hi, np.where(top, 0, j + 1), j)
    pc = _h(Kp, jp, B["seed"] + 90)
    out = {"K": K, "j": j, "thick": th, "thin": th < B["thin"], "bed_edge": np.minimum(d_lo, d_hi),
           "below_top": (K + 1 - Phi) / dPhi,  # (m under the top of the point's super-bed: where stains start)
           # (open in stretches along the strike, ~8 m, about a third of it: ~15 m stretches over 85% of the plane still
           # drew a ruled line across the pebble chasm)
           "bed_crack": np.clip((pc - 0.75) / 0.25, 0, 1) * np.clip((noise._value_noise(
               np.c_[p[:, :2] / 8.0, (jp + 16 * Kp).astype(float)], B["seed"] + 92) - 0.52)
               / 0.18, 0, 1), "blocks": [], "weights": [], "edges": [], "open": []}
    s = B["seed"] + 80 + 9
    for m in range(len(AZ)):
        phi, dphi, n2 = _joint_coord(p, K, j, m, th, B)
        jj = (K * 16 + j) * 5 + m
        i = np.floor(phi).astype(np.int64)
        u = phi - i
        g = i - _absent(i, jj, s)
        out["blocks"].append(g)
        out["weights"].append(B["family"][m] * face_weight(n2, fd) * (th >= B["thin"]))
        # the nearest present boundary below / above, and whether it's open
        lo_b = i - _absent(i, jj, s)
        hi_b = i + 1 + _absent(i + 1, jj, s)
        dl, dh = (phi - lo_b) / dphi, (hi_b - phi) / dphi
        out["edges"].append(np.minimum(dl, dh))
        b = np.where(dl < dh, lo_b, hi_b)
        is_open = _h(b, jj, B["seed"] + 91) < B["open"]
        out["open"].append(np.where(is_open, np.minimum(dl, dh), np.inf))
    out["master"], out["master_d"] = mast
    return out


# ---------------------------------------------------------------- fallen blocks

FALL_CELL = 2.2   # m: one candidate block per cell of this plan grid (jittered)


def fall_zone(H, c, steep, reach=None):
    """0..1 per terrain cell: where blocks that fell off a face come to rest: gentler ground (< 40 deg) below a steep
    face, within `reach` m of it (fading out; default max(8 m, 3 cells): on 5 m cells a 6 m band vanished in the
    smoothing), more right at the foot."""
    from scipy import ndimage
    reach = max(8.0, 3.0 * c) if reach is None else reach
    st = steep > 0.5
    if not st.any():
        return np.zeros(H.shape)
    dist, (iy, ix) = ndimage.distance_transform_edt(~st, sampling=c, return_indices=True)
    gy, gx = np.gradient(H, c)
    gentle = np.hypot(gx, gy) < math.tan(math.radians(40.0))
    below = H < H[iy, ix] - 0.5
    z = np.clip(1 - dist / reach, 0, 1) * gentle * below * ~st
    return ndimage.gaussian_filter(z.astype(float), 0.7)


def fallen_sd(p, ground, zone, B):
    """Signed distance to the fallen blocks at points p: rounded, chipped boxes `fall_min`-(+1.1) m, sunk a third into
    the ground, many small and few big (size ~ u^2), one candidate per FALL_CELL cell (present by the zone's density),
    each turned and tipped its own way. ground(xy) -> heights; zone(xy) -> 0..1. inf where none is near."""
    out = np.full(len(p), np.inf)
    if not len(p):
        return out
    s = B["seed"] + 300
    ci = np.floor(p[:, 0] / FALL_CELL).astype(np.int64)
    cj = np.floor(p[:, 1] / FALL_CELL).astype(np.int64)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            i, j = ci + di, cj + dj
            cx = (i + 0.2 + 0.6 * _h(i, j, s)) * FALL_CELL
            cy = (j + 0.2 + 0.6 * _h(i, j, s + 1)) * FALL_CELL
            dens = zone(np.c_[cx, cy])
            # (only where the zone is dense enough that the cliff overlay holds the ground unsunk: Region takes 4 x the
            # zone; a block on sunk ground was a piece floating over the heightmap)
            x = np.clip((dens - 0.3) / 0.3, 0, 1)
            on = _h(i, j, s + 2) < 0.75 * x * x * (3 - 2 * x)
            if not on.any():
                continue
            k = np.flatnonzero(on)
            # (never under ~2 voxels across: 0.3 m blocks meshed as slivers, a non-manifold edge at a tile border)
            size = B["fall_min"] + 1.1 * _h(i[k], j[k], s + 3) ** 2
            bx = size * (0.8 + 0.4 * _h(i[k], j[k], s + 4))
            by = size * (0.65 + 0.35 * _h(i[k], j[k], s + 5))
            bz = size * (0.55 + 0.3 * _h(i[k], j[k], s + 6))
            yaw = 2 * math.pi * _h(i[k], j[k], s + 7)
            tilt = math.radians(25.0) * (2 * _h(i[k], j[k], s + 8) - 1)
            cz = ground(np.c_[cx[k], cy[k]]) + 0.35 * bz
            q = p[k] - np.c_[cx[k], cy[k], cz]
            c_, s_ = np.cos(yaw), np.sin(yaw)
            x1, y1 = c_ * q[:, 0] + s_ * q[:, 1], -s_ * q[:, 0] + c_ * q[:, 1]
            ct, st = np.cos(tilt), np.sin(tilt)
            y2, z2 = ct * y1 + st * q[:, 2], -st * y1 + ct * q[:, 2]
            rr = np.maximum(0.25 * size, 0.2)  # (edges rounded over ~half a voxel at least: sharper made shards)
            d = np.abs(np.c_[x1, y2, z2]) - np.c_[bx, by, bz] + rr[:, None]
            sd = np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(d.max(1), 0) - rr
            # two corners knocked off by planes of their own (a rounded box alone read as a crate)
            for c in range(2):
                u = np.c_[2 * _h(i[k], j[k], s + 10 + 3 * c) - 1, 2 * _h(i[k], j[k], s + 11 + 3 * c) - 1,
                          0.3 + 0.7 * _h(i[k], j[k], s + 12 + 3 * c)]
                u /= np.linalg.norm(u, axis=1, keepdims=True)
                reach = (np.abs(u) * np.c_[bx, by, bz]).sum(1)  # (the box's extent along u)
                sd = -_smin(-sd, -((np.c_[x1, y2, z2] * u).sum(1) - 0.7 * reach), 0.25)
            out[k] = np.minimum(out[k], sd)
    return out
