"""Rock relief for the terrain field: strata, joints, facets, bed planes, the rock configuration, digs, local
thickness and the rivers' hold. Part of the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import fieldjit, noise, profiling
from .profiling import span as _span
from .terrain_mesh import DEFAULTS, _f64, smoothstep

# ---------------------------------------------------------------- the field
def rock_relief(p, r, g=None, jw=None, fd=None, u=None, blk=None, thin=None):
    """Solid rock character as a field offset (+ carves, - builds): planar facets meeting in crisp creases, and bedding
    (a V notch at each bedding plane, each bed standing proud or set back on its own, stepping over at its edge).
    Continuous everywhere with C0 creases, never jumps: a jump (the nearest cell's plane alone) meshed as steps whose
    normals pointed sideways (black shards), and blending the cells smoothly read as mush. The mesh shows the creases
    with split normals (`split_normals`). The heightfield's own rock (terrain_rock) moves the ground in plan only;
    this can overhang. fd: the ground's gradient per point (the face's orientation: facets on irregular triangles laid
    on the face, `facet`); u: 0..1 how much of the point's relief comes from a volume (a cave's walls and roof, which
    the ground's gradient says nothing about: facets in 3D there); thin: 0..1 per point, thin rock (Field.thin_at),
    where the soft beds are picked out (`strata`: fins and stacks are where the sea does that)."""
    fac = lambda size, seed: facet(p, size, seed, fd, u)
    uvol = u  # (the volumes' share; `u` is reused below)
    profiling.count("facets pts", len(p))
    if g is None:
        out = r["facets"] * (fac(r["size"], r["seed"]) + 0.4 * fac(0.43 * r["size"], r["seed"] + 5))
    else:
        # facet size follows the face's structure (g: 0 on buttresses and open faces, 1 in gullies and near the
        # top): big planes where the rock stands out, small broken facets where it's cut up; one facet size
        # everywhere read as evenly crumpled paper (the alps walls)
        out = np.zeros(len(p))
        kc, kf = np.flatnonzero(g < 1), np.flatnonzero(g > 0)
        # (with jointed blocks the finer facet octaves go: the blocks are the medium scale, and facets inside blocks
        # read as crumpled soft slabs)
        # (on volumes' walls (u) as before: the blocks don't go there)
        fine = np.ones(len(p)) if not r.get("blocks") else (np.zeros(len(p)) if u is None else np.asarray(u, float))
        if len(kc):
            sub = lambda size, seed: facet(p[kc], size, seed, None if fd is None else fd[kc], None if u is None else u[kc])
            big = sub(1.5 * r["size"], r["seed"])
            fk = fine[kc]
            sm = np.flatnonzero(fk > 0)
            add = np.zeros(len(kc))
            if len(sm):
                add[sm] = fk[sm] * 0.3 * facet(p[kc][sm], 0.6 * r["size"], r["seed"] + 5,
                                               None if fd is None else fd[kc][sm], None if u is None else u[kc][sm])
            out[kc] += (1 - g[kc]) * 1.1 * (big + add)
        if len(kf):
            sub = lambda size, seed: facet(p[kf], size, seed, None if fd is None else fd[kf], None if u is None else u[kf])
            mid = 0.55 * sub(0.45 * r["size"], r["seed"] + 11)
            fk = fine[kf]
            sm = np.flatnonzero(fk > 0)
            add = np.zeros(len(kf))
            if len(sm):
                add[sm] = fk[sm] * 0.35 * facet(p[kf][sm], 0.2 * r["size"], r["seed"] + 12,
                                                None if fd is None else fd[kf][sm], None if u is None else u[kf][sm])
            out[kf] += g[kf] * ((1.3 - 0.3 * fk) * mid + add)
        out = r["facets"] * out
    if r["bedding"] > 0:
        B = bed_planes(p, r, g)
        kb, f, lower, xy = B["kb"], B["f"], B["lower"], p[:, :2]
        edge = np.minimum(f, 1 - f)
        # each bed stands proud or set back, by an amount that changes along the strike (one offset per bed made the
        # step a ruler-straight line across the whole wall: "reads like a seam"), stepping over to the next in a
        # straight ramp either side of the bedding plane (creases at both ends: a crisp step, no jump). Where the plane
        # is absent (`pres` low: patches along the strike, gullies) the ramp widens to metres: the beds merge
        off = lambda k, i=slice(None): 2 * _bed_noise(xy[i], k, 28.0, r["seed"] + 20) - 1
        nb = np.where(lower, kb - 1, kb + 1)
        be = B["width"]
        u = np.clip((np.where(lower, f, f - 1) + be) / (2 * be), 0, 1)  # 0..1 from the lower bed to the upper
        t = np.where(lower, 1 - u, u)  # the neighbouring bed's share
        o = off(kb)
        i = np.flatnonzero(t > 0)
        o[i] += t[i] * (off(nb[i], i) - o[i])
        # (with jointed blocks the big beds step less: their planes ran the whole cliff as ruled ledges)
        # (in full on the volumes' walls: karst passages' ledges are these beds)
        bf = 1.0 if not r.get("blocks") else (0.4 if uvol is None else 0.4 + 0.6 * uvol)
        out = out + r["bedding"] * bf * (
            0.3 * B["pres"] * np.clip(1 - edge / B["sharp"], 0, 1) + 0.3 * o)
    if r.get("blocks"):
        # jointed blocks (terrain_blocks): courses and joint families bound blocks 1-10 m that stand proud or sit back
        # (a few missing): the medium scale. Not on volumes' walls (u) nor deep in the rock (jw)
        from . import terrain_blocks
        # ((1 - u)^3: at a cave mouth, half volume and half face, the face's blocks stepped the cave's walls and roof)
        wb = (1.0 if jw is None else jw) * (1.0 if uvol is None else (1.0 - uvol) ** 3)
        kb = np.flatnonzero(np.asarray(wb) * np.ones(len(p)) > 1e-3)
        if len(kb) and fd is not None:
            with _span("field.blocks", leaf=True):
                if blk is None:  # (blk: the offsets at every point, computed by the caller with the maps' ids)
                    zoff = r["bed_offset"](p[kb, :2]) if r.get("bed_offset") else 0.0
                    ob = terrain_blocks.offsets(p[kb], r["blocks"], fd[kb], zoff)
                else:
                    ob = blk[kb]
                out = out + 0.0
                out[kb] += (np.ones(len(p)) * wb)[kb] * ob
    if thin is not None and THIN_STRATA["depth"] > 0:
        kt = np.flatnonzero(np.asarray(thin, float) > 1e-3)
        if len(kt):
            out = out + 0.0
            zoff = r["bed_offset"](p[kt, :2]) if r.get("bed_offset") else 0.0
            # (sqrt: a fin's faces are only partly "thin" by the grid's measure, and the beds should run on across it;
            # not on the volumes' walls)
            wv = 1.0 if uvol is None else (1.0 - np.asarray(uvol, float)[kt]) ** 2
            # (eased to 0 at the cut: sqrt(1e-3) is 0.03, a step of 3% of the strata's offset where thin rock begins)
            tk = np.asarray(thin, float)[kt]
            out[kt] += np.sqrt(tk) * smoothstep(1e-3, 0.02, tk) * wv * strata(p[kt], zoff, r["seed"])
    if r.get("joints") and r["joints"]["depth"] > 0:
        # (jw: 1 at the open ground, 0 a few metres in: joints on cave walls deep in the rock made black shards)
        with _span("field.joints", leaf=True):
            out = out + _joints(p, r, fd) * (1.0 if jw is None else jw)
    return out


def _bed_hash(k, seed):
    """0..1 per integer bed index (and seed)."""
    x = np.sin(np.asarray(k, float) * 12.9898 + seed * 78.233) * 43758.5453
    return x - np.floor(x)


def strata(p, zoff, seed, tone=False):
    """Thin rock's strata (+ carves): beds 1-3 m thick (THIN_STRATA spacing x (1 +- 2 jitter)) in the bed coordinate
    z + zoff, each with its own hardness: soft beds sit back up to `depth`, hard ones stand flush, how far changing
    along the strike (~12 m, the bed index a noise coordinate) so no bed is a ruled line. Beds hand over across +-ramp
    (>= 2 voxels in all: finer meshed as sawtooth). Durdle Door's fin reads by these, not by its facets.
    tone=True: each point's bed softness instead (0..1, eased across the planes the same way: the colour's banding)."""
    S, J, ramp, depth = (THIN_STRATA[k] for k in ("spacing", "jitter", "ramp", "depth"))
    zb = p[:, 2] + zoff
    i0 = np.floor(zb / S).astype(np.int64)
    bnd = lambda i: (i + J * (2 * _bed_hash(i, seed + 31) - 1)) * S  # (bed i spans bnd(i) .. bnd(i + 1))
    k = np.where(zb < bnd(i0), i0 - 1, np.where(zb >= bnd(i0 + 1), i0 + 1, i0))
    xy = p[:, :2]

    def rec(i, q):  # how far bed i sits back at points q: soft beds the most, wandering along the strike
        # (interbedded: about half the beds soft, 0.55-1, the rest hard and flush, as limestone and shale)
        hsh = _bed_hash(i, seed + 37)
        soft = np.where(hsh < 0.5, 0.55 + 0.9 * hsh, 0.0)
        if tone:
            return soft
        along = noise.fbm(np.c_[q, i * 13.7], 12.0, 2, seed=seed + 41)
        return depth * soft * np.clip(0.2 + 1.4 * along, 0, 1)
    v0 = rec(k, xy)
    v = v0.copy()
    # (each plane: half way between the two beds' values on it, eased over +-ramp; beds are >= 2 ramps thick)
    for side, d in ((-1, zb - bnd(k)), (1, bnd(k + 1) - zb)):
        t = smoothstep(ramp, -ramp, d)
        j = np.flatnonzero(t > 0)
        if len(j):
            v[j] += t[j] * (rec(k[j] + side, xy[j]) - v0[j])
    return v


def _joints(p, r, fd=None):
    """Joint sets: a few families of long, straight, vertical fracture planes (2-3 directions), irregularly spaced
    (each candidate plane on a fine spacing is present or not, jittered: many small blocks and a few big ones), strong
    in some bands of the face and absent in others. Each joint is a V groove between flat faces (a smooth profile
    pillowed every block: from 150 m the face read as hammered metal). ~2 voxels wide: geometry carries the medium
    structure, the maps the fine grain.
    fd: the face's horizontal normal per point (plan; its length the slope). A family whose planes run nearly along the face shows no
    groove there (a cliff breaks off along such a joint: it IS the face); crossing the face it cuts steep traces.
    Every family everywhere crossed as a lattice of long diagonal grooves: from 150 m a crosshatch of diamonds."""
    J = r["joints"]
    ed = J["edge"]
    out = np.zeros(len(p))
    h = lambda k, m, c: noise._hash(k, k * 0 + m, k * 0 + c, r["seed"] + 60)
    for m, d in enumerate(J["dirs"]):
        sp = J["spacing"][m]
        q = (p[:, :2] @ np.asarray(d)) / sp
        k0 = np.floor(q).astype(np.int64)
        best = np.zeros(len(p))
        for dk in (-1, 0, 1):
            k = k0 + dk
            pos = k + 0.8 * (h(k, m, 1) - 0.5)
            amp = (h(k, m, 2) < J["prob"][m]) * (0.6 + 0.4 * h(k, m, 3))
            t = np.clip(1 - np.abs(q - pos) * sp / ed, 0, 1)
            # (crisp shoulders, a rounded floor: a V-bottom crease on cave walls shaded as black shards)
            best = np.maximum(best, amp * t * (2 - t))
        if fd is not None:  # (|cos| of the joint plane's normal with the face's: 1 = the plane lies along the face;
            # the slope in the denominator keeps it continuous where the ground flattens and the direction is lost)
            cs = np.abs(fd @ np.asarray(d)) / np.sqrt((fd * fd).sum(1) + 0.04)
            best = best * smoothstep(0.8, 0.45, cs)
        # (the bands' noise only where there's a groove to scale: it was a sixth of every bake's time)
        kb = np.flatnonzero(best > 0)
        if len(kb):
            band = smoothstep(0.35, 0.6, noise.fbm(p[kb] * np.array([1.0, 1.0, 0.5]), J["band"], 2,
                                                   seed=r["seed"] + 70 + m))
            out[kb] = out[kb] + J["depth"] * best[kb] * band
    return out


# a fixed rotation for the facet lattice, so its creases don't line up with the world's axes
_ROT = np.linalg.qr(np.array([[0.62, -0.51, 0.33], [0.27, 0.71, 0.58], [-0.49, -0.12, 0.74]]))[0]


# a second rotation, for the lattice that warps the facet lattice (see _pl_facets)
_ROT_W = np.linalg.qr(np.array([[0.3, 0.8, -0.2], [-0.7, 0.1, 0.6], [0.5, -0.4, 0.7]]))[0]


def _hash3(ix, iy, iz, seed):
    """Three pseudo-random values -1..1 per lattice point from one 64-bit hash (16 bits each)."""
    h = ((ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)).astype(np.uint64)
    for m in (np.uint64(0xBF58476D1CE4E5B9), np.uint64(0x94D049BB133111EB)):  # (splitmix64's finaliser)
        h ^= h >> np.uint64(31)
        h *= m
    h ^= h >> np.uint64(29)
    return np.stack([((h >> np.uint64(16 * c)) & np.uint64(0xFFFF)).astype(np.float64) / 32767.5 - 1.0
                     for c in range(3)], 1)


def _pl_walk(q, seed, vec=False):
    """Random values (-1..1) at the corners of the unit cubic lattice, interpolated linearly over each cube's six
    tetrahedra (the Freudenthal split: consistent across faces). (n,), or (n, 3) with vec."""
    if fieldjit.ON:
        r = fieldjit.pl_walk(np.ascontiguousarray(q, dtype=np.float64), int(seed), bool(vec))
        return r if vec else r[:, 0]
    b = np.floor(q).astype(np.int64)
    f = q - b
    order = np.argsort(-f, axis=1)  # the tetrahedron: walk the axes from the largest fraction down
    fs = np.take_along_axis(f, order, 1)
    w = np.stack([1 - fs[:, 0], fs[:, 0] - fs[:, 1], fs[:, 1] - fs[:, 2], fs[:, 2]], 1)
    val = (lambda v: _hash3(v[:, 0], v[:, 1], v[:, 2], seed)) if vec else \
        (lambda v: 2 * noise._hash(v[:, 0], v[:, 1], v[:, 2], seed) - 1)
    v = b.copy()
    out = (w[:, :1] if vec else w[:, 0]) * val(v)
    rows = np.arange(len(q))
    for k in range(3):
        v[rows, order[:, k]] += 1
        out = out + (w[:, k + 1:k + 2] if vec else w[:, k + 1]) * val(v)
    return out


def _pl_facets(p, size, seed, warp=0.45):
    """A continuous, piecewise-planar field (-1..1): random heights at the corners of a rotated cubic lattice,
    interpolated linearly over each cube's six tetrahedra. Offsetting a surface by it breaks the surface into planar
    facets with crisp creases.
    The lattice is warped by a second piecewise-linear field on another rotated lattice 1.7x coarser (a composition of
    piecewise-linear maps is still piecewise linear: facets stay planar, creases stay C0). Unwarped, every crease lay
    on the lattice's planes and diagonals: a face showed a few fixed crease directions at a fixed spacing, a quilt of
    rhombs and rectangles (the user's "squares in the rocks")."""
    q = (p @ _ROT.T) / size
    if warp:
        q = q + warp * _pl_walk((p @ _ROT_W.T) / (1.7 * size), seed + 1001, vec=True)
    return _pl_walk(q, seed)


def facet(p, size, seed, fd=None, u=None):
    """Planar facets about `size` across (-1..1): on irregular triangles laid on the face where the ground's gradient
    fd says which way it faces (terrain_facets), on the warped lattice (`_pl_facets`) where a volume shapes the rock
    (share u) or no gradient is given."""
    if fd is None:
        return _pl_facets(p, size, seed)
    from . import terrain_facets
    with _span("field.facets", leaf=True):
        return _facet(p, size, seed, fd, u, terrain_facets)


def _facet(p, size, seed, fd, u, terrain_facets):
    u = np.zeros(len(p)) if u is None else u
    out = np.zeros(len(p))
    a, b = np.flatnonzero(u < 0.999), np.flatnonzero(u > 1e-3)
    if len(a):
        out[a] += (1 - u[a]) * terrain_facets.facets(p[a], size, seed, fd[a])
    if len(b):
        out[b] += u[b] * _pl_facets(p[b], size, seed)
    return out


def bed_level(p, r):
    """Which bed a point is in, as a real number (bed k spans k..k+1): the heightfield rock's own beds
    (terrain_rock.bed_step / bed_offset, so sills on the heightfield's faces and the solid rock's beds line up) when
    it has them, else level beds `bed` thick."""
    off = r["bed_offset"](p[:, :2]) if r.get("bed_offset") else 0.0
    return (p[:, 2] + off) / r["bed"]


def _bed_noise(xy, k, scale, seed, octaves=2):
    """0..1 per point, smooth along the strike (plan position, features ~`scale` m), independent per bed k (the bed
    index is the lattice's third coordinate, sampled on its nodes). Two octaves on rotated lattices."""
    k = np.asarray(k, float) * np.ones(len(xy))
    out = np.zeros(len(xy))
    for o, (a, w) in enumerate(((0.61, 0.65), (2.13, 0.35))[:octaves]):
        c, s, m = math.cos(a), math.sin(a), (2 ** o) / scale
        q = np.c_[(xy[:, 0] * c - xy[:, 1] * s) * m, (xy[:, 0] * s + xy[:, 1] * c) * m, k]
        out += w * noise._value_noise(q, seed + 101 * o)
    out = out / (0.65 if octaves == 1 else 1.0)
    return np.clip(0.5 + (out - 0.5) * (1.6 if octaves > 1 else 1.0), 0, 1)


def bed_planes(p, r, g=None):
    """The beds at points: bed level z (bed k spans k..k+1), kb, f, lower (nearer the plane under than over), and for
    the nearest bedding plane: `pres` 0..1 (how much the plane shows: it comes and goes along the strike in patches of
    ~20 m and breaks in gullies, g), `sharp` (its crisp half-width in bed units, varying along the strike: 1-2.5x
    `bed_edge`) and `width` (the step's ramp: sharp where present, metres wide where absent, so the beds merge).
    One offset, one sharpness and one tone per bed, uniform along the whole wall, read as a ruler line: a seam."""
    z = bed_level(p, r)
    kb = np.floor(z).astype(np.int64)
    f = z - kb
    lower = f < 0.5
    m = np.where(lower, kb, kb + 1)  # the nearest plane: between beds m - 1 and m
    be = r.get("bed_edge", 0.08)
    wide = min(0.42, 6.0 / r["bed"])
    pres, sharp = np.ones(len(z)), np.full(len(z), min(be, 0.45))
    # (only points near a plane need them: the step, the notch and the tone's ease reach at most `reach` from it)
    reach = max(wide, min(0.45, 4.2 / r["bed"]), 2.5 * be)
    k = np.flatnonzero(np.minimum(f, 1 - f) < reach)
    if len(k):
        xy = p[k, :2]
        pres[k] = smoothstep(0.3, 0.62, _bed_noise(xy, m[k], 22.0, r["seed"] + 23))
        if g is not None:
            pres[k] *= 1 - 0.8 * np.clip(g[k], 0, 1)
        sharp[k] = np.minimum(0.45, be * (1 + 1.5 * _bed_noise(xy, m[k], 15.0, r["seed"] + 24, octaves=1)))
    width = sharp + (1 - pres) * np.maximum(0.0, wide - sharp)
    return {"z": z, "kb": kb, "f": f, "lower": lower, "m": m, "pres": pres, "sharp": sharp, "width": width}


def rock_config(T, cfg):
    """The solid rock character's settings: spec "rock" (false turns it off; "facets", "bedding" 0..1 as for the
    heightfield; "facet_size", "bed" m) and export.tiles "rock" (a multiplier, 0 = none). Beds are the heightfield
    rock's own where terrain_rock exposes them."""
    from . import terrain_rock
    rc = T.spec.get("rock", {})
    mult = float(cfg.get("rock", 1.0))
    if rc is False or mult <= 0:
        return None
    rc = rc if isinstance(rc, dict) else {}
    # few large facets with crisp joints (5 m cells and 1.8 m beds at 1 m voxels read as crumpled paper); the
    # heightfield's own facets are larger (1.2 x crag): these sit inside them, the finer size
    size = float(rc.get("facet_size", np.clip(float(T.world.get("crag", 12.0)) / 2.5, 4.0, 10.0)))
    fac = mult * float(rc.get("facets", 1.0)) * 0.18 * size
    bd = mult * float(rc.get("bedding", 1.0))
    bed, base = float(rc.get("bed", 3.0)), None
    if hasattr(terrain_rock, "bed_step") and hasattr(terrain_rock, "bed_offset") and "bed" not in rc:
        bed = float(terrain_rock.bed_step(T))
        base = lambda xy, T=T: terrain_rock.bed_offset(T, xy)
    # the beds wander in height along the strike, ~0.5 m over ~25 m and ~0.15 m over ~7 m (terrain_rock's offset alone
    # changes over hundreds of metres: every bed was a level ruler line across the wall)
    wa = min(1.0, 0.12 * bed)
    wander = lambda xy: wa * 3 * (noise.fbm(np.c_[xy, np.full(len(xy), 17.0)], 24.0, 2, seed=4242 + 25) - 0.5) + \
        0.3 * wa * 3 * (noise.fbm(np.c_[xy, np.full(len(xy), 5.0)], 7.0, 1, seed=4242 + 26) - 0.5)
    off = _gridded(lambda xy: wander(xy) + (base(xy) if base else 0.0), T)
    # bed steps ramp over 2 voxels either side of their plane (0.8 voxel meshed as a sawtooth that cast jagged
    # shadows); the crisp notch at the bedding plane is in the maps (terrain_bake.micro_relief)
    vox = float(cfg.get("voxel", DEFAULTS["voxel"]))
    out = {"size": size, "facets": fac, "bedding": bd, "bed": bed, "bed_offset": off, "seed": 4242,
           "reach": 1.4 * fac + 0.7 * bd + 1.0, "bed_edge": max(0.05, 2.0 * vox / bed)}
    bk = float(rc.get("blocks", 1.0)) * mult
    if bk > 0:  # jointed blocks (terrain_blocks); the big facets calmer on them: block faces are flat-ish
        from . import terrain_blocks
        out["blocks"] = terrain_blocks.config(size, vox, bk)
        b = out["blocks"]
        out["reach"] += b["relief"]
        # (the cliff overlay's push/shell keep main's sizes: the blocks mostly carve, within the old push's margin.
        # Thickening the shell by the blocks' relief re-cut the shells round pebble's karst passage and notch: a face
        # in a tile border plane, a non-manifold sliver, a 4-triangle piece floating 2 m over the heightmap)
    jt = float(rc.get("joints", 1.0)) * mult * (bk <= 0)
    if bd > 0 and jt > 0:  # joint sets: three families of vertical planes, candidate spacing ~a fifth of a facet
        sp = float(np.clip(0.2 * size, 1.2, 2.5))
        dirs = [math.radians(a) for a in (37.0, 107.0, 162.0)]
        out["joints"] = {"dirs": [[math.cos(a), math.sin(a)] for a in dirs], "spacing": [sp, 1.4 * sp, 2.0 * sp],
                         "prob": [0.4, 0.3, 0.2], "band": max(12.0, 3.0 * size), "edge": max(0.6, 1.5 * vox),
                         "depth": 0.22 * jt * bd}  # (0.3 m folded the 800-triangle LOD 2: 0.6% shards)
        out["reach"] += 0.35 * jt * bd
    return out


def _gridded(fn, T, spacing=2.0):
    """A smooth function of plan position (the beds' wander: fbm over ~150 m) read from a cubic spline on a grid over
    the frame instead of evaluated per point: it was a quarter of every field evaluation, and the bake evaluates the
    field tens of times per texel. Identical for meshing and baking (both use this)."""
    (x0, y0), (x1, y1) = T.spec["extent"]
    m = 4 * spacing
    xs = np.arange(x0 - m, x1 + m + spacing, spacing)
    ys = np.arange(y0 - m, y1 + m + spacing, spacing)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    coef = ndimage.spline_filter(fn(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape), order=3)

    def f(xy):
        xy = np.atleast_2d(np.asarray(xy, float))
        if fieldjit.ON:
            return fieldjit.grid_at(coef, _f64(xy[:, 1]), _f64(xy[:, 0]), ys[0], xs[0], spacing)
        return ndimage.map_coordinates(coef, [(xy[:, 0] - xs[0]) / spacing, (xy[:, 1] - ys[0]) / spacing], order=3,
                                       prefilter=False, mode="nearest")
    from .terrain_incremental import Frame
    f.grid, f.frame = coef, Frame("gridded", coef.shape, "xy", xs[0], ys[0], spacing)  # (incremental export: per tile)
    return f


def _structure_grain(T, H, c):
    """0..1 per terrain cell: how cut up the rock is. Concave ground at the faces' own structure scale (gullies,
    couloirs), terrain_rock's gullies, and the top quarter of each face (the lip breaks up) score high; convex
    buttresses and open faces low. Smooth (a few cells): facet sizes change gradually."""
    rk = getattr(T, "rock", None) if isinstance(getattr(T, "rock", None), dict) else {}
    fh = float(rk.get("face_height", 20.0) or 20.0)
    sig = max(1.0, 0.25 * fh / c)
    Hs = ndimage.gaussian_filter(H, sig)
    lap = ndimage.laplace(Hs) / (c * c)
    gy, gx = np.gradient(H, c)
    steep = np.hypot(gx, gy) > 0.8
    ref = np.percentile(np.abs(lap[steep]), 85) if steep.sum() > 50 else np.abs(lap).max() + 1e-9
    conc = np.clip(lap / max(ref, 1e-9), 0, 1)
    w = max(3, int(round(fh / c)) | 1)
    lo, hi = ndimage.minimum_filter(Hs, w), ndimage.maximum_filter(Hs, w)
    top = smoothstep(0.7, 0.95, (Hs - lo) / np.maximum(hi - lo, 1e-6)) * steep
    g = np.maximum(conc, 0.8 * top)
    gul = rk.get("gullies")
    if gul is not None and np.shape(gul) == H.shape:
        g = np.maximum(g, np.clip(ndimage.gaussian_filter(np.asarray(gul, float), 2.0) * 3, 0, 1))
    return ndimage.gaussian_filter(g, 2.0)


def dig_bunker(T, H, m, depth):
    """A sand trap dug into the ground grid where its cover mask m (0..1) is: `depth` m down with a steep cut edge
    (most of the drop within ~1 m of the edge), the turf lip round it raised a little (0.15 x depth) as mown up to the
    edge; a flat-ish sand floor following the ground's own lie."""
    c = float(T.cell)
    m = ndimage.gaussian_filter(np.clip(np.asarray(m, float), 0, 1), 0.6 / c)
    inside = smoothstep(0.25, 0.65, m)
    ring = smoothstep(0.02, 0.2, ndimage.maximum_filter(m, size=3)) * (1 - inside)
    return H - depth * inside + 0.15 * depth * ring


def dig_doline(T, H, d):
    """A doline (a karst sinkhole) dug into the ground grid: a bowl `radius` m round and `depth` m deep relative to the
    ground around it (so on a hillside it's a hollow in the slope), gentle at the lip and steepest (2 x depth / run)
    at its throat, a flat floor `throat` m round where a shaft drops to the cave."""
    dx, dy = T.X - d["xy"][0], T.Y - d["xy"][1]
    r = np.hypot(dx, dy)
    # an uneven rim: the radius wanders +-20% round the bowl (a perfect circle read as a dish)
    u = np.c_[(dx / np.maximum(r, 1e-9)).ravel(), (dy / np.maximum(r, 1e-9)).ravel(), np.zeros(r.size)]
    wob = 1 + 0.4 * (noise.fbm(u * 3.0, 1.0, 2, seed=int(d.get("seed", 0))).reshape(r.shape) - 0.5)
    R = d["throat"] + (d["radius"] - d["throat"]) * wob
    s = np.clip((r - d["throat"]) / np.maximum(R - d["throat"], 1e-6), 0, 1)
    return H - d["depth"] * (1 - s) ** 2


THIN_LEVELS = 48  # at most this many height levels per thin piece (_local_thickness)


def _local_thickness(H, c, r_open, thin):
    """Where the ground is thin (`thin` > 0: fins, stacks, narrow headlands), the rock's local half-thickness per
    height level: at each level z, the radius of the largest disc inside {H > z} that covers the cell (the
    Hildebrand-Ruegsegger local thickness, in whole cells up to r_open), carried 2 cells out into the air and smoothed.
    Returns (labels, comps): labels (the grid, 0 = not thin) and per piece (j0, i0, z0, dz, hw (nz, ny, nx) m,
    tw (nz, ny, nx): how much the cap applies, 0 where the rock is r_open thick)."""
    m = thin > 0.02
    if not m.any():
        return None
    lab, n = ndimage.label(ndimage.binary_dilation(m, iterations=2))
    pad = 2 * r_open + 3
    big = r_open * c
    comps = []
    for li, sl in enumerate(ndimage.find_objects(lab), 1):
        j0, j1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, H.shape[0])
        i0, i1 = max(sl[1].start - pad, 0), min(sl[1].stop + pad, H.shape[1])
        Hs, own = H[j0:j1, i0:i1], lab[j0:j1, i0:i1] == li
        th = thin[j0:j1, i0:i1]
        zlo = float(Hs[own].min()) - 1.0
        zhi = float(Hs[own].max()) + 1.0
        nz = int(min(THIN_LEVELS, max(2, math.ceil((zhi - zlo) / c) + 1)))
        dz = (zhi - zlo) / (nz - 1)
        hw = np.zeros((nz,) + Hs.shape)
        for iz in range(nz):
            M = Hs > zlo + iz * dz
            if not M.any():
                continue
            edt = ndimage.distance_transform_edt(M)
            h = np.where(M, 0.5, 0.0)
            for R in range(1, r_open + 1):
                core = edt >= R
                if not core.any():
                    break
                # (the cells within R of a core cell: an EDT, not a disc dilation, which cost R^2 per cell)
                h[(ndimage.distance_transform_edt(~core) <= R) & M] = R
            # (into the air a little: the surface lies between cells, and carving reaches out to it)
            h = ndimage.grey_dilation(h, size=(5, 5))
            hw[iz] = ndimage.gaussian_filter(h, 0.8) * c
        tw = th[None] * (1.0 - smoothstep(0.6 * big, big, hw))
        comps.append((j0, i0, zlo, dz, hw, tw))
    return lab, comps


HOLD_REACH = 30.0  # m from a river's water line where the 3D field's ground keeps the banks the terrain grid has


HOLD_FREEBOARD = 0.3  # m over the water the banks are kept (forms.water grades banks from level + 0.3)


def hold_rivers(T, H, ref):
    """H (the field's ground grid after its own edits: facets taken out, styles softened) kept from dropping below a
    river's banks: within HOLD_REACH of a water line, wherever `ref` (the terrain's ground) stands at least
    HOLD_FREEBOARD over the nearest water-line sample's level, H stays at least there. The channel, and ground the
    terrain already had under the water (fall amphitheatres, pools), are left as they are."""
    lines = getattr(T, "river_water_lines", None) or {}
    if not lines:
        return H
    from scipy.spatial import cKDTree
    xs, ys = np.asarray(T.xs, float), np.asarray(T.ys, float)
    guard = np.full(H.shape, np.inf)
    for rw in lines.values():
        xy, lv, wd = np.asarray(rw["xy"], float), np.asarray(rw["level"], float), np.asarray(rw["width"], float)
        live = wd > 0
        if not live.any():
            continue
        lo, hi = xy[live].min(0) - HOLD_REACH, xy[live].max(0) + HOLD_REACH
        ix = np.flatnonzero((xs >= lo[0]) & (xs <= hi[0]))
        iy = np.flatnonzero((ys >= lo[1]) & (ys <= hi[1]))
        if not len(ix) or not len(iy):
            continue
        X, Y = np.meshgrid(xs[ix], ys[iy])
        d, i = cKDTree(xy[live]).query(np.c_[X.ravel(), Y.ravel()], distance_upper_bound=HOLD_REACH)
        g = np.where(np.isfinite(d), lv[live][np.minimum(i, live.sum() - 1)] + HOLD_FREEBOARD, np.inf).reshape(X.shape)
        sub = guard[iy[0]:iy[-1] + 1, ix[0]:ix[-1] + 1]
        np.minimum(sub, g, out=sub)
    hold = np.isfinite(guard) & (ref >= guard) & (H < guard)
    if not hold.any():
        return H
    return np.where(hold, guard, H)


THIN_STRATA = {"spacing": 1.7, "jitter": 0.2, "ramp": 0.5, "depth": 1.0, "tone": 1.0}  # thin rock's strata
