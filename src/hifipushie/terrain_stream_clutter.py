"""Stream clutter: where it lies, all of it, counts, summary, the manifest. Part of terrain streams (terrain_stream.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from . import terrain_stream
from . import noise
from .terrain_stream import _shore, _snags, _ss, config, pad

# ---------------------------------------------------------------------------------------------- clutter
def clutter(T, mats, field, box=None, seed=11):
    """Stream clutter as rows [x, y, z, kind index (into KINDS), scale, yaw deg, squash, place index (PLACES), river
    index, water (m: the water's surface minus z; > 0 standing in that much water, < 0 above it), sink (m the piece's
    pivot goes below z: half-buried stones)]: rounded boulders in the channel (more and bigger with the stream's energy, in clusters and in rows across
    the steps; the bigger ones stand proud of the water) and on the banks, cobble patches on bars, riffles and
    margins, slabs along steep margins, driftwood caught on boulders and stranded on outer bends and bar heads, reeds
    along slow margins, litter in the slack. Deterministic; nothing on fords, routes or sites. box: [[x0, y0],
    [x1, y1]]."""
    S = getattr(mats, "streams", None)
    empty = np.zeros((0, terrain_stream.COLS))
    if S is None or not S.any or S.cfg["clutter"] <= 0:
        return empty
    dens = float(S.cfg["clutter"])
    kinds = list(terrain_stream.KINDS)
    iy, ix = np.nonzero(S.zone)
    zx0, zx1 = S.x0 + ix.min() * S.c - S.c, S.x0 + ix.max() * S.c + S.c
    zy0, zy1 = S.y0 + iy.min() * S.c - S.c, S.y0 + iy.max() * S.c + S.c
    if box is not None:
        (bx0, by0), (bx1, by1) = box
        zx0, zx1, zy0, zy1 = max(zx0, bx0), min(zx1, bx1), max(zy0, by0), min(zy1, by1)
    if zx1 <= zx0 or zy1 <= zy0:
        return empty
    out = []
    rocks = None
    for ki, kind in enumerate(kinds):
        if kind not in terrain_stream.SPACING:  # (the sea beach kinds: terrain_shore.beach_clutter)
            continue
        sp = terrain_stream.SPACING[kind]
        # (the lattice is anchored at the world's origin, so a block's rows are the whole level's rows)
        xs = np.arange(np.floor(zx0 / sp) - 1, np.ceil(zx1 / sp) + 2) * sp  # (a cell past the box: jitter crosses it)
        ys = np.arange(np.floor(zy0 / sp) - 1, np.ceil(zy1 / sp) + 2) * sp
        gx, gy = np.meshgrid(xs, ys)
        xy = np.c_[gx.ravel(), gy.ravel()]
        h3 = lambda a, b: noise._hash(np.rint(xy[:, 0] / sp).astype(np.int64), np.rint(xy[:, 1] / sp).astype(np.int64),
                                      np.full(len(xy), a, np.int64), seed + b)
        xy = xy + (np.c_[h3(1, ki), h3(2, ki)] - 0.5) * 0.9 * sp
        u_keep, u_a, u_b, u_c, u_s = h3(3, ki), h3(4, ki), h3(5, ki), h3(6, ki), h3(9, ki)
        k = S.in_zone(xy[:, 0], xy[:, 1])
        k = k[(xy[k, 0] >= zx0) & (xy[k, 0] < zx1) & (xy[k, 1] >= zy0) & (xy[k, 1] < zy1)]
        if not len(k):
            continue
        xy, u_keep, u_a, u_b, u_c, u_s = xy[k], u_keep[k], u_a[k], u_b[k], u_c[k], u_s[k]
        h, cs = field.column(xy[:, 0], xy[:, 1])
        g = S.sample(xy)
        ok = (cs > 0.75) & (g["ford"] < 0.25) & (g["sd"] < S.cfg["reach"])
        if mats.sea is not None:
            ok &= h > mats.sea + 0.1
        xy, h, u_keep, u_a, u_b, u_c, u_s = xy[ok], h[ok], u_keep[ok], u_a[ok], u_b[ok], u_c[ok], u_s[ok]
        g = {a: b[ok] for a, b in g.items()}
        n = len(xy)
        if not n:
            continue
        Pf = np.c_[xy, np.zeros(n)]
        dep = g["level"] - h
        e, sd, u = g["energy"], g["sd"], g["u"]
        pool, riffle, bar = S.forms(xy, g)
        inwater = (dep > 0.04) & (sd < 0.5)
        flow = np.degrees(np.arctan2(g["t"][:, 1], g["t"][:, 0]))
        lo, hi = terrain_stream.KINDS[kind]["scale"]
        sq0, sq1 = terrain_stream.KINDS[kind]["squash"]
        squash = sq0 + (sq1 - sq0) * u_c
        yaw = 360.0 * u_b
        place = np.zeros(n, int)
        z = h.copy()
        sink = np.zeros(n)
        if kind == "river_rock":
            clus = 0.25 + 1.5 * _ss(0.42, 0.68, noise.fbm(Pf, 4.0, 2, seed=741))
            rows = _ss(0.7, 0.95, -np.sin(2 * np.pi * g["phi"])) * _ss(0.3, 0.7, e)  # (the steps of a step-pool reach)
            edge = _ss(0.45, 0.9, u)
            p_w = (0.03 + 0.42 * e ** 1.5) * clus * (edge + (1 - edge) * (0.4 + 0.6 * _ss(0.1, 0.5, e))) + 0.5 * rows
            p_w = p_w * (1 + 0.8 * riffle)
            p_w = p_w * (1 - 0.7 * pool * (1 - rows))
            p_w = p_w * (1 - g["still"] * (1 - _ss(-5.0, -1.5, sd)))  # (a lake: stones along its shore only)
            hb = -dep
            p_b = (0.012 + 0.12 * e) * clus * _ss(5.0, 1.0, sd) * (hb < 1.6) * (0.6 + 0.8 * _ss(0.1, 0.6, -g["bend"]))
            # (steep reaches: fewer round boulders, more angular slabs; see "slab")
            p = np.where(inwater, p_w * (1 - 0.35 * _ss(0.6, 0.95, e)), np.where(sd > -0.5, p_b, 0.0))
            # a waterfall's plunge pool: big boulders round its rim (thrown out by the fall), few in the pool itself
            ring = 4 * g["plunge"] * (1 - g["plunge"])
            p = np.maximum(p, 0.55 * ring)
            # sorted along the channel: the big ones on riffles and steps, small ones in the pools
            med = (0.42 + 0.55 * e + 0.25 * rows) * (1 + 0.35 * riffle - 0.4 * pool * (1 - rows)) * (1 + 0.9 * ring)
            scale = np.clip(med * np.exp(0.5 * _normal(u_a)), lo, np.minimum(hi, np.maximum(0.5, 1.3 * g["w"])))
            squash = np.where(scale > 1.0, sq0 + (1.0 - sq0) * u_c, squash)  # (big ones sit lower: slabby)
            place = np.where(inwater, 1, np.where(-dep < 0.3, 2, 3))
            # a third lie half buried in the bed (0.2-0.45 of their height; height ~0.55 x scale x squash), the rest
            # bedded a little: stones set ON the gravel read as garden stones
            ht = terrain_stream.FOOTPRINT["river_rock"]["height"] * scale * squash
            sink = np.where(u_s < 0.33, 0.2 + 0.75 * u_s, 0.04 + 0.08 * u_s) * ht
        elif kind == "cobbles":
            margin = _ss(-1.4, -0.3, sd) * _ss(1.2, 0.2, sd)
            shallow = _ss(0.55, 0.15, dep)
            st = S.shares(np.c_[xy, h])
            silt = np.zeros(n)
            if st is not None:
                silt[st["k"]] = st["silt"]
            p = np.maximum(np.maximum(0.8 * bar, 0.3 * riffle * (0.4 + 0.6 * shallow)), 0.4 * margin) * (1 - silt) * \
                (0.35 + 0.65 * _ss(0.05, 0.4, e)) * (0.5 + _ss(0.4, 0.6, noise.fbm(Pf, 2.5, 2, seed=742)))
            p = p * ((dep > -0.3) & (sd < 1.5))
            scale = lo + (hi - lo) * u_a ** 1.5
            place = np.where(bar > 0.4, 4, np.where(dep > 0.03, 1, 2))
        elif kind == "slab":
            p = 0.22 * _ss(0.35, 0.75, e) * _ss(-1.2, -0.2, sd) * _ss(2.0, 0.6, sd) * \
                _ss(0.45, 0.65, noise.fbm(Pf, 5.0, 2, seed=743))
            # (and a few big flat slabs out in the channel on any reach: on the riffles, awash)
            p = np.maximum(p, 0.035 * (0.4 + riffle) * inwater * _ss(0.6, 0.72, noise.fbm(Pf, 6.0, 2, seed=747)))
            # (and on steep reaches broken slabs and blocks in the channel itself)
            p = np.maximum(p, 0.16 * _ss(0.55, 0.9, e) * inwater * (0.5 + riffle) *
                           _ss(0.4, 0.6, noise.fbm(Pf, 3.0, 2, seed=753)))
            p = p * (1 - g["still"])
            p = np.maximum(p, 0.45 * g["foot"])  # (blocks fallen from a waterfall's face, at its foot)
            scale = lo + (hi - lo) * u_a ** (1.3 - 0.8 * g["foot"])
            sink = (0.1 + 0.15 * u_s) * terrain_stream.FOOTPRINT["slab"]["height"] * scale * squash
            yaw = flow + 40 * (u_b - 0.5)
            place = np.where(dep > 0.03, 1, 2)
        elif kind == "driftwood":
            margin = _ss(-1.5, -0.2, sd) * _ss(1.5, 0.3, sd)
            p = margin * (0.02 + 0.16 * _ss(0.2, 0.7, -g["bend"])) + 0.12 * bar * _ss(0.4, 0.0, dep) * (sd < 0.5)
            p = p * (0.4 + 1.2 * _ss(0.5, 0.7, noise.fbm(Pf, 12.0, 2, seed=744)))  # (in drifts, bare stretches between)
            scale = np.clip(1.6 * np.exp(0.55 * _normal(u_a)), lo, np.minimum(hi, 2.5 * g["w"] + 1.5))
            yaw = flow + 50 * (u_b - 0.5)  # (stranded along the flow)
            place = np.where(bar > 0.4, 4, 2)
        elif kind == "reeds":
            slow = _ss(0.45, 0.15, e)
            st = S.shares(np.c_[xy, h])
            rk = np.zeros(n)
            if st is not None:
                rk[st["k"]] = st["rock"]
            p = 0.6 * slow * (np.abs(sd) < 1.2) * _ss(-0.3, -0.1, dep) * _ss(0.35, 0.2, dep) * \
                _ss(0.5, 0.62, noise.fbm(Pf, 7.0, 2, seed=745)) * (1 - 0.6 * bar) * (1 - rk) * \
                (1 - 0.7 * _ss(0.2, 0.6, -g["bend"]))  # (the outer bank is cut, not reedy)
            scale = lo + (hi - lo) * u_a
            place = np.full(n, 2)
        elif kind == "sedge":  # tussocks along the wet margin and up the bank's foot: denser on the slow inner side,
            # thin on a cut bank (its turf ends at the edge); in rows of clumps, with gaps
            outer, hc, inner, _ = S.cut(xy, g)
            hb = -dep
            p = 0.55 * _ss(-0.08, 0.05, hb) * _ss(1.1, 0.5, hb) * (sd < 4.0) * (0.3 + 0.6 * inner) * (1 - 0.75 * outer) * \
                (0.25 + 0.75 * _ss(0.4, 0.6, noise.fbm(Pf, 4.0, 2, seed=748))) * (1 - 0.6 * _ss(0.5, 0.9, e))
            p = p + 0.5 * outer * np.exp(-((hb - hc - 0.15) / 0.12) ** 2)  # (the turf's fringe along a cut bank's top)
            scale = lo + (hi - lo) * u_a
            place = np.where(hb < 0.2, 2, 3)
        elif kind == "bush":  # scrub on the bank top in clumps (a willow or alder line), fewer on fast reaches
            hb = -dep
            p = 0.3 * _ss(0.25, 0.5, hb) * _ss(2.6, 1.8, hb) * (sd < 6.5) * (sd > 1.2) * \
                _ss(0.56, 0.7, noise.fbm(Pf, 11.0, 2, seed=749)) * (1 - 0.5 * e)
            scale = lo + (hi - lo) * u_a
            squash = 0.8 + 0.3 * u_c
            place = np.full(n, 3)
        else:  # litter: leaf and twig drifts in the slack of pools and on the bank's foot
            p = 0.22 * pool * (np.abs(sd) < 1.0) * _ss(0.6, 0.2, e) + 0.05 * (sd > 0.4) * (sd < 4.0) * (-dep < 1.0)
            p = p * _ss(0.4, 0.6, noise.fbm(Pf, 6.0, 2, seed=746))
            scale = lo + (hi - lo) * u_a
            place = np.where(sd > 0.4, 3, 2)
        if kind == "driftwood":  # (a log lies at the water's surface or on the ground, never sunk on the bed)
            z = np.maximum(z, g["level"] - 0.06)
        keep = u_keep < np.clip(p * dens, 0, 1)
        if not keep.any():
            continue
        R = np.c_[xy, z, np.full(n, ki), scale, np.mod(yaw, 360.0), squash, place, S.river_of(xy), g["level"] - z,
                  sink][keep]
        if kind == "river_rock":
            R = _thin(R, 0.42)
            rocks = (R, g["t"][keep], g["w"][keep])
        elif kind == "slab":
            R = _thin(R, 0.5)
        elif kind == "driftwood":
            R = _thin(R, 0.6)
            # logs caught on the upstream side of the big boulders standing in the water, lying across the flow
            if rocks is not None and len(rocks[0]):
                Rr = rocks[0]
                tdir = _dirs(S, Rr[:, :2])
                hh = noise._hash(np.rint(Rr[:, 0] * 10).astype(np.int64), np.rint(Rr[:, 1] * 10).astype(np.int64),
                                 np.full(len(Rr), 7, np.int64), seed + 91)
                h2 = noise._hash(np.rint(Rr[:, 0] * 10).astype(np.int64), np.rint(Rr[:, 1] * 10).astype(np.int64),
                                 np.full(len(Rr), 8, np.int64), seed + 92)
                sel = (Rr[:, 7] == 1) & (Rr[:, 4] > 0.85) & (hh < 0.3 * dens)
                if sel.any():
                    q = Rr[sel]
                    td = tdir[sel]
                    pos = q[:, :2] - td * (0.45 * q[:, 4:5] + 0.15)
                    hz, _ = field.column(pos[:, 0], pos[:, 1])
                    wq = S.sample(pos)["w"]
                    ln = np.clip(1.2 + 2.2 * h2[sel], lo, np.minimum(hi, 2.2 * wq + 1.0))
                    yw = np.degrees(np.arctan2(td[:, 1], td[:, 0])) + 90 + 70 * (hh[sel] / (0.3 * dens) - 0.5)
                    lvq = S.sample(pos)["level"]
                    hz = np.maximum(hz, lvq - 0.06)  # (afloat against the rock, not on the bed)
                    R = np.concatenate([R, np.c_[pos, hz, np.full(len(q), ki), ln, np.mod(yw, 360.0),
                                                 0.9 + 0.5 * h2[sel], np.ones(len(q)), q[:, 8], lvq - hz,
                                                 np.zeros(len(q))]])
        out.append(pad(R))
    # snags and limbs (terrain_snags): resting on the bed, banks and the boulders just placed, never through them
    trees_xy = getattr(T, "_snag_trees", None)
    if trees_xy is None:
        from . import terrain_design_cover
        tr = terrain_design_cover.trees(T) if getattr(T, "cover", None) else []
        trees_xy = np.asarray(tr, float)[:, :2] if len(tr) else np.zeros((0, 2))
        T._snag_trees = trees_xy
    SR, SCp = _snags.snags(S, field, rocks[0] if rocks is not None else None, trees_xy, (zx0, zx1, zy0, zy1),
                           dens=dens)
    if len(SR):
        out.append(np.c_[SR, SCp])
    return np.concatenate(out) if out else empty


def _normal(u):
    """A standard normal from a uniform (an approximation good to ~3 sigma)."""
    u = np.clip(u, 1e-4, 1 - 1e-4)
    return 4.91 * (u ** 0.14 - (1 - u) ** 0.14)


def _dirs(S, xy):
    return S.sample(xy)["t"]


def _thin(R, share):
    """Greedy thinning: a piece closer to a bigger one than `share` x the sum of their sizes goes (stones don't
    stand inside each other; spacing follows size, not a grid)."""
    if len(R) < 2:
        return R
    order = np.argsort(-R[:, 4], kind="stable")
    R = R[order]
    tree = cKDTree(R[:, :2])
    alive = np.ones(len(R), bool)
    rmax = float(R[:, 4].max())
    for i in range(len(R)):
        if not alive[i]:
            continue
        for j in tree.query_ball_point(R[i, :2], share * (R[i, 4] + rmax)):
            if j > i and alive[j] and np.hypot(*(R[j, :2] - R[i, :2])) < share * (R[i, 4] + R[j, 4]):
                alive[j] = False
    R = R[alive]
    return R[np.lexsort((R[:, 0], R[:, 1]))]


def all_clutter(T, mats, field, box=None):
    """Stream and lake clutter (when the terrain has running or still water) and the sea beaches' (terrain_shore), as
    one array of `clutter` rows; river index -1 = a sea beach."""
    S = getattr(mats, "streams", None)
    dens = float(S.cfg["clutter"]) if S is not None else float((config(T) or {"clutter": 0.0})["clutter"])
    parts = [clutter(T, mats, field, box)]
    if dens > 0:
        parts.append(pad(_shore.beach_clutter(T, mats, field, list(terrain_stream.KINDS), box, density=dens)))
    return np.concatenate([p for p in parts if len(p)]) if any(len(p) for p in parts) else np.zeros((0, terrain_stream.COLS))


def counts(S, C):
    """{river: {kind: n}} and per river the share of in-water river rocks standing proud of the water is not known
    here (it needs the water's depth): see `summary`."""
    out = {}
    kinds = list(terrain_stream.KINDS)
    for r, name in [(-1, "sea beaches")] + list(enumerate(S.names if S is not None else [])):
        sel = C[C[:, 8] == r] if len(C) else C
        if r >= 0 or len(sel):
            out[name] = {k: int((sel[:, 3] == i).sum()) for i, k in enumerate(kinds)}
    return out


def summary(S, C, box=None):
    """Report lines: the clutter per river (and how many of the rocks in the water stand proud of it), a WARNING for
    a river with none."""
    lines = []
    kinds = list(terrain_stream.KINDS)
    sb = C[C[:, 8] == -1] if len(C) else np.zeros((0, terrain_stream.COLS))
    if len(sb):
        lines.append("shore clutter (sea beaches): " + ", ".join(
            f"{int((sb[:, 3] == i).sum())} {k}" for i, k in enumerate(kinds) if (sb[:, 3] == i).any()))
    for r, name in enumerate(S.names if S is not None else []):
        sel = C[C[:, 8] == r] if len(C) else np.zeros((0, terrain_stream.COLS))
        if not len(sel):
            if box is None:
                lines.append(f"WARNING stream clutter {name}: none placed (the channel has no rocks, wood or reeds; is "
                             f"\"streams\".clutter 0, or the river all ford / route?)")
            continue
        n = {k: int((sel[:, 3] == i).sum()) for i, k in enumerate(kinds)}
        rk = sel[(sel[:, 3] == kinds.index("river_rock")) & (sel[:, 7] == 1)]
        proud = ""
        if len(rk):
            dep = S.sample(rk[:, :2])["level"] - rk[:, 2]
            top = terrain_stream.FOOTPRINT["river_rock"]["height"] * rk[:, 4] * rk[:, 6] - rk[:, 10]
            proud = f" ({int((top > dep).sum())} of {len(rk)} rocks in the water stand proud of it)"
        lines.append(f"stream clutter {name}: " + ", ".join(f"{v} {k}" for k, v in n.items() if v) + proud)
    return lines


def manifest(S, C):
    """The export manifest's "clutter" section for the stream kinds."""
    return {"kinds": {k: {"scale_m": v["scale"], "squash": v["squash"], "what": v["what"], "z": "surface",
                          **({"footprint": terrain_stream.FOOTPRINT[k]} if k in terrain_stream.FOOTPRINT else {})}
                      for k, v in terrain_stream.KINDS.items() if k != "bush" and k not in _snags.KINDS}  # (bush: the older kind's
                     | _snags.manifest_kinds(),  # entry stands; snags and limbs: capsules)
            "places": {"water": "in the channel, its base on the bed under the water", "margin": "at the water line",
                       "bank": "on the bank beside the water", "bar": "on a gravel bar inside a bend",
                       "shore": "on a sea beach above the water",
                       "": "dry ground (the older kinds)"},
            "columns": terrain_stream.CSV_COLUMNS, "csv_version": terrain_stream.CSV_VERSION,
            "how": "clutter.csv rows x,y,z,kind,scale,yaw,squash,place,water,sink: scale = the piece's largest plan dimension in "
                   "metres, squash = its height relative to the asset's own proportions (instance scale (s, s, s x "
                   "squash) on an asset 1 m across), yaw degrees about up (driftwood: its long axis, 0 = along +x), z "
                   "= the ground or bed under its pivot (kinds with \"z\": \"surface\"; the asset's pivot sinks it). "
                   "Two more columns after place: water = the water surface's height minus z at the row, in metres (> "
                   "0: the piece stands in that much water; < 0: that far above it; empty: no water near), and sink "
                   "= metres the pivot goes below z on top of the asset's own sink (half-buried stones; empty = 0). "
                   "footprint (per kind) is what a water or flow simulation stamps for a row, at its own resolution: "
                   "the upper half of an ellipsoid with plan axes scale x plan (the long one along yaw) and height "
                   "scale x squash x height over (z - sink); the tile heightmaps hold none of these pieces (they "
                   "are 1 m cells; the pieces are their own meshes and colliders). csv_version 3 adds seven columns "
                   "at the END (a v2 reader that indexes by header keeps working): x0,y0,z0,x1,y1,z1,diameter, "
                   "filled only for the kinds whose footprint is a \"capsule\" (snag, limb; empty for the rest): "
                   "the capsule's axis end points (m; end 0 the lower) and its diameter (m). Each end rests on what "
                   "holds it (the axis end a radius over the bed, a bank or a boulder); nothing of it is inside the "
                   "ground, rock or a boulder row's footprint. Stamp it as that capsule; the asset is a stem 1 m "
                   "along +x at scale 1 (scale = the length), turned by yaw (from end 0 to end 1 in plan) and "
                   "pitched to the ends' heights.",
            "rivers": counts(S, C)}
