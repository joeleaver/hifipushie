"""Erosion for terrain: fastscapelib's stream power + hillslope diffusion (drainage networks: valleys and spurs that
all lead somewhere), our own strata (hard beds erode slower: cliff bands and ledges) and thermal slumping (ground
steeper than its talus angle sheds material downhill: scree aprons).

It runs after the design is applied: sites, routes and pass corridors don't erode, lakes are base level, and the
authored large-scale heights are restored afterwards (the erosion's detail is kept, its overall lowering is not), so
the designer's numbers still hold. Strength is scale-free: erosion runs until the ground has lowered by a set share of
the relief, whatever the frame's size.

Spec: "erosion": {"strength": 1.0, "strata": {"spacing": m, "hard": 0..1, "dip": deg, "dip_toward": deg},
                  "talus": deg, "keep_heights": true}   ({"strength": 0} turns it off; "dissection" is the old name)
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from .terrain import smoothstep


def protected(T) -> np.ndarray:
    keep = np.zeros(T.X.shape, bool)
    for m in T.masks.values():
        keep |= m > 0.05
    for p in T.passes.values():
        keep |= p["corridor"]
    return ndimage.binary_dilation(keep, iterations=2)


def strata_factor(T, H, cfg) -> np.ndarray:
    """Erodibility multiplier from bedding: every `spacing` metres (measured across tilted beds) a hard bed resists."""
    if not cfg:
        return np.ones(H.shape)
    spacing = float(cfg.get("spacing", 0.04 * max(np.ptp(H), 1)))
    hard = float(cfg.get("hard", 0.7))
    dip = math.radians(cfg.get("dip", 0))
    az = math.radians(cfg.get("dip_toward", 0))  # compass bearing the beds dip toward
    z = H + math.tan(dip) * (T.X * math.sin(az) + T.Y * math.cos(az))
    phase = (z / spacing) % 1.0
    bed = smoothstep(0.55, 0.65, phase) * smoothstep(0.95, 0.85, phase)  # the upper part of each layer is hard
    return 1 - hard * bed


def thermal(H, cell, talus_deg, keep, iters=20, rate=0.25):
    """Material above the talus angle slides to lower neighbours until slopes relax toward it."""
    t = math.tan(math.radians(talus_deg))
    H = H.copy()

    offs = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2))]
    free = ~keep
    for _ in range(iters):
        pad = np.pad(H, 1, mode="edge")
        excess = []
        for dy, dx, d in offs:
            nb = pad[1 + dy:1 + dy + H.shape[0], 1 + dx:1 + dx + H.shape[1]]
            excess.append(np.clip(H - nb - t * d * cell, 0, None))
        excess = np.stack(excess)
        total = excess.sum(0)
        move = rate * np.max(excess, axis=0) * free  # what leaves each cell, shared by how much each neighbour is below
        share = np.where(total > 0, excess / np.maximum(total, 1e-9), 0) * move
        H -= move
        for k, (dy, dx, _) in enumerate(offs):  # deposit on the neighbours it went to
            dep = np.zeros_like(H)
            src = share[k]
            ys, yd = (slice(0, H.shape[0] - dy), slice(dy, None)) if dy >= 0 else (slice(-dy, None), slice(0, H.shape[0] + dy))
            xs, xd = (slice(0, H.shape[1] - dx), slice(dx, None)) if dx >= 0 else (slice(-dx, None), slice(0, H.shape[1] + dx))
            dep[yd, xd] = src[ys, xs]
            H += dep * free  # protected cells take no deposit (what reaches them is lost at their edge)
    return H


def erode(T):
    import fastscapelib as fs
    cfg = T.spec.get("erosion", T.spec.get("dissection"))
    cfg = {} if cfg is None else cfg  # (an empty dict means the defaults, not "off")
    strength = float(cfg.get("strength", 1.0))
    if not strength:
        return
    H0 = T.H.copy()
    ny, nx = H0.shape
    keep = protected(T)
    wet = ~np.isnan(T.water)
    base = ndimage.binary_erosion(wet, iterations=2) | (T._fixed_river & ~keep)  # water ends in lakes and rivers
    status = {(int(i), int(j)): fs.NodeStatus.FIXED_VALUE for i, j in zip(*np.nonzero(base))}
    grid = fs.RasterGrid([ny, nx], [T.cell, T.cell], fs.NodeStatus.FIXED_VALUE, status)
    graph = fs.FlowGraph(grid, [fs.SingleFlowRouter(), fs.MSTSinkResolver(), fs.MultiFlowRouter(1.1)])
    # K scales with the frame (drainage area grows with its square) so a tile erodes like a valley does
    k0 = 5e-5 * (4000.0 / T.size) ** 0.9
    relief = float(np.percentile(H0, 98) - np.percentile(H0, 2))
    # mean lowering to reach, then stop. Capped in metres: in a game level (compressed geometry) erosion scaled to the
    # implied geology cut 20-30 m flutes, trenches across the player's space. "detail" scales the cap.
    target = strength * min(0.035 * relief, T.world["gully"] * float(cfg.get("detail", 1.0)))
    # soil creeps, rock cliffs (the hard bands) do not
    D = float(cfg.get("soften", 0.1)) * T.k ** 2
    diff = fs.DiffusionADIEroder(grid, np.where(keep, 0.0, np.where(T.hard, 0.2 * D, D)))  # rock creeps slower
    area = np.empty_like(H0)
    E = H0.copy()
    talus = float(cfg.get("talus", 38))
    steps = 0
    # multiple-flow routing divides by slope: on dead-flat ground (pads, plains) 0/0 turned every cell into NaN
    jitter = np.random.default_rng(3).random(H0.shape) * 1e-3
    for steps in range(1, 80):
        K = np.where(keep, 0.0, k0 * strata_factor(T, E, cfg.get("strata")) * np.where(T.hard, 0.2, 1.0))
        spl = fs.SPLEroder(graph, K, 0.45, 1.0)
        graph.update_routes(E + jitter)
        graph.accumulate(area, 1.0)
        e1 = spl.erode(E, area, 1000.0)
        E = E - e1 - diff.erode(E - e1, 1000.0)
        if not np.isfinite(E).all():
            T.warnings.append("erosion went numerically wrong and was skipped (please report the spec)")
            return
        if steps % 2 == 0:  # gully sides relax as they're cut (only hard rock, the cliff bands, stands steeper)
            E = thermal(E, T.cell, talus, keep | base | T.hard, iters=6)
        if np.mean(H0 - E) >= target:
            break
    E = thermal(E, T.cell, talus, keep | base | T.hard, iters=25)
    lowered = float(np.mean(H0 - E))
    if cfg.get("keep_heights", True):  # restore the designed large-scale heights; keep the erosion's detail
        lp = 0.06 * T.size / T.cell
        E = E + ndimage.gaussian_filter(H0 - E, lp)
    # designed places exactly as designed; lakes and their shores too (restoring heights raised the shores and
    # shrank the lakes away from the sites placed on them)
    margin = max(3, int(round(0.03 * T.size / T.cell)))
    shores = ndimage.binary_dilation(wet, iterations=margin) if wet.any() else wet
    w = ndimage.gaussian_filter((keep | shores).astype(float), 1.5)
    T.H = E * (1 - w) + H0 * w
    T.erosion = {"steps": steps, "lowered": lowered, "k": k0}
