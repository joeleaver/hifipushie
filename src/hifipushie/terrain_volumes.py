"""Terrain volumes: the solid shapes a world adds to or cuts from its ground (tubes, stacks, mounds), built from the
world's features, and the view through them. Part of the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import math
import zlib

import numpy as np

from . import noise
from .terrain_mesh import DEFAULTS, smax, smoothstep

# ---------------------------------------------------------------- volumes
NORMAL_H = 0.125  # the normals' stencil, voxels: exact on each side of a crease (split_normals splits at creases)


NEAR = 2.5  # how far from a volume's surface the rock character reaches (m)


# the rock relief is evaluated only where its weight is over RELIEF_CUT (a cost cull), and eased in from there to
# RELIEF_FADE, so the field stays continuous where the cull starts (Field._solid)
RELIEF_CUT = 0.01


RELIEF_FADE = 0.1


JUMP_LIMIT = 3  # sampled texels with a step under them (terrain_bake.bake_texels) a tile LOD may have (seam_check)


BURIED_DEEP = 0.1  # a face is buried when its centre is deeper in the rock than this x sqrt(its area) (and > the LOD threshold)


FLOAT_PIECE = 50.0  # m2: closed cliff pieces off the tile border that never reach the ground, under this: dropped, logged


FLOAT_TOL = 0.15  # m over the pushed heightmap that still counts as reaching the ground (terrain_cliffs.floating's tol)


EXPOSED_OFF = 0.5  # m out along a face's normal: rock there = behind the visible surface (terrain_cliffs.EXPOSED_OFF)


BURIED_SHADE = 0.6  # the buried back's material: the rock's mean colour under it x this (never white)


FALL_SEAT = 0.5  # fallen blocks seat this share of the rock relief's reach (x its weight) under the column's ground


class Tube:
    """A passage along a polyline of nodes: an elliptical cross-section (half width rw across, rh up) that varies
    node to node, rounded ends, optionally cut flat below `floor` (per node). One node is an ellipsoid (a chamber).
    Arches, sea caves and notches are all tubes; a cave engine would be a graph of them."""

    def __init__(self, name, nodes, rw, rh, floor=None, op="subtract", blend=1.0, rough=0.4, rough_scale=3.0, seed=0,
                 roof=None, beds=None, relief=1.0):
        self.name, self.op, self.blend = name, op, float(blend)
        self.nodes = np.atleast_2d(np.asarray(nodes, float))
        n = len(self.nodes)
        self.rw = np.broadcast_to(np.asarray(rw, float), (n,)).copy()
        self.rh = np.broadcast_to(np.asarray(rh, float), (n,)).copy()
        self.floor = None if floor is None else np.broadcast_to(np.asarray(floor, float), (n,)).copy()
        # a flat roof (per node: a bedding plane the passage spread along) and beds in the walls: {"bed": m thick,
        # "amp": m each bed stands out or back, "off": xy -> the beds' shift in height (the rock's own beds)}
        self.roof = None if roof is None else np.broadcast_to(np.asarray(roof, float), (n,)).copy()
        self.beds = beds
        self.relief = float(relief)  # how much of the rock character (facets) its walls take
        self.rough, self.rough_scale, self.seed = float(rough), float(rough_scale), int(seed)
        rough = self.rough + (1.6 * beds["amp"] if beds else 0.0)
        # the box reaches past everything the tube does to the field (its blend, and the rock character's reach,
        # NEAR): cut off inside that reach, the field jumped at the box's edge (shards). The ellipse's distance
        # under-reads along its long axis by the aspect ratio, hence the factor.
        aspect = float(np.max(np.maximum(self.rw / self.rh, self.rh / self.rw)))
        r = np.maximum(self.rw, self.rh).max() + (self.blend + rough + NEAR + 0.5) * aspect
        self.reach = float(r)
        self.lo, self.hi = self.nodes.min(0) - r, self.nodes.max(0) + r
        if self.floor is not None:
            self.lo[2] = max(self.lo[2], float(self.floor.min()) - self.blend - rough - 0.5)

    def sd(self, p, detail=False):
        """Signed distance (roughly: the ellipse's is a bound). With detail: also each point's height above the floor
        of the nearest segment (inf with no floor) and that segment's smaller radius (for how much rock relief
        a passage's walls take)."""
        best = np.full(len(p), np.inf)
        above = np.full(len(p), np.inf)
        size = np.zeros(len(p))
        rough = self.rough * (2 * noise.fbm(p, self.rough_scale, 3, seed=self.seed) - 1) if self.rough > 0 else 0.0
        if self.beds:
            rough = rough + wall_beds(p, self.beds)
        segs = [(0, 0)] if len(self.nodes) == 1 else [(i, i + 1) for i in range(len(self.nodes) - 1)]
        # (segments in runs of TUBE_RUN, each run only at the points within its reach: every point against every
        # segment made a 1,088 m switchback lava tube (725 segments) cost 1,500 s of marching cubes a tile. Past the
        # reach (the box's margin) nothing reads the tube's value but the box test, which is the same)
        reach = self.reach
        # (the ellipse's distance under-reads by its aspect: a value under `reach` can lie this far in space)
        rmax = float(np.maximum(self.rw, self.rh).max())
        aspect = float(np.max(np.maximum(self.rw / self.rh, self.rh / self.rw)))
        span = (reach + abs(self.rough) + (1.6 * self.beds["amp"] if self.beds else 0.0)) * aspect + rmax
        full = np.arange(len(p))
        for r0 in range(0, len(segs), TUBE_RUN):
            run = segs[r0:r0 + TUBE_RUN]
            ns = self.nodes[[run[0][0]] + [j for _, j in run]]
            lo_, hi_ = ns.min(0) - span, ns.max(0) + span
            if len(segs) > TUBE_RUN:
                sel = np.flatnonzero(np.all((p >= lo_) & (p <= hi_), axis=1))
                if not len(sel):
                    continue
            else:
                sel = full
            ps = p[sel]
            rgh = rough[sel] if np.ndim(rough) else rough
            b_, a_, z_ = best[sel], above[sel], size[sel]
            for i, j in run:
                b_, a_, z_ = self._seg(ps, i, j, rgh, b_, a_, z_)
            best[sel], above[sel], size[sel] = b_, a_, z_
        if len(segs) > TUBE_RUN:  # (points no run reaches: past the reach, a bound)
            far = ~np.isfinite(best)
            best[far] = reach
        return (best, above, size) if detail else best

    def _seg(self, p, i, j, rough, best, above, size):
        if True:
            a, b = self.nodes[i], self.nodes[j]
            d = b - a
            L = float(np.linalg.norm(d))
            t = d / L if L > 1e-9 else np.array([1.0, 0.0, 0.0])
            s = np.clip(((p - a) @ t) / L, 0, 1) if L > 1e-9 else np.zeros(len(p))
            q = p - (a + s[:, None] * d)
            eu = np.cross(t, [0, 0, 1.0])
            eu = eu / np.linalg.norm(eu) if np.linalg.norm(eu) > 1e-6 else np.array([1.0, 0, 0])
            ev = np.cross(eu, t)
            u, v, w = q @ eu, q @ ev, q @ t
            rw = self.rw[i] + s * (self.rw[j] - self.rw[i])
            rh = self.rh[i] + s * (self.rh[j] - self.rh[i])
            # walls and roof rough, the floor flat (rough floors made a cave's floor a scramble of 1 m steps)
            dd = (np.sqrt((u / rw) ** 2 + (v / rh) ** 2 + (w / rw) ** 2) - 1) * np.minimum(rw, rh) + rough
            if self.roof is not None:  # flat along the bedding plane, rounding into the walls over ~a voxel
                rf = self.roof[i] + s * (self.roof[j] - self.roof[i])
                dd = smax(dd, p[:, 2] - rf, np.minimum(0.6, 0.3 * rh))
            ab = np.full(len(p), np.inf)
            if self.floor is not None:
                fl = self.floor[i] + s * (self.floor[j] - self.floor[i])
                # the floor meets the walls in a fillet about a voxel round, not a hard crease: a vertex on a
                # crease takes one side's normal from the field and the faces on the other side shade black
                dd = smax(dd, fl - p[:, 2], np.minimum(0.6, 0.3 * rh))
                ab = p[:, 2] - fl
            m = dd < best
            best = np.where(m, dd, best)
            above = np.where(m, ab, above)
            size = np.where(m, np.minimum(rw, rh), size)
        return best, above, size

    def touches(self, lo, hi):
        return bool(np.all(self.hi >= lo) and np.all(self.lo <= hi))


TUBE_RUN = 16  # segments a tube evaluates together, at the points in their run's reach (Tube.sd)


STACK ={"radius": 0.75}


STACK_BUILD = 0.05  # m: the most rock relief may build out from a stack


STACK_CARVE = 0.3  # m: ... and carve into it (cartoon facets 1.4 x cut a fin of a stack loose 5 m up: the stack's own


# form carries its shape, the relief is texture on it)
# a solid sea stack's radius x the sea's stack radius; its form is terrain_stack.FORM (a jointed column), a style's
# sheet may override it (rock.stack)
class Stack:
    """A sea stack as solid rock (op "add" over the heightfield's own stack): a jointed column (terrain_stack.Column:
    a plan of joint faces, near-vertical walls stepping back at a few levels, a flat dipping top or a spire, a
    waterline notch, fallen blocks at the foot). The heightfield can't hold a 70-90 deg side on 1-2 m cells (its
    stacks came out as rounded loaves); the lobed, bedded prism that stood here before read as a pile of tyres."""

    def __init__(self, name, xy, base, top, r, seed, blend=0.4, clip=None, sea=None, over=None, stage="auto",
                 foot=None):
        from .terrain_stack import Column
        self.name, self.op, self.blend, self.relief = name, "add", float(blend), 1.0
        self.build = STACK_BUILD  # (its rock relief carves; see Field._solid)
        # the heightfield's own stack (a slim core) taken away within `clip` m of the centre above the plinth, so the
        # solid stack alone is the form: two steep surfaces crossing inside its notch meshed as shards
        self.clip = None if clip is None else (float(clip), float(base) + 0.5)
        self.xy, self.base, self.top, self.r, self.seed = np.asarray(xy, float), float(base), float(top), float(r), \
            int(seed)
        self.col = Column(self.xy, self.base, self.top, self.r, self.seed,
                          sea=(self.base + 2.0) if sea is None else sea, stage=stage, over=over, foot=foot)
        m = max(self.col.reach, self.clip[0] if self.clip else 0.0) + self.blend + NEAR + 1.0
        self.lo = np.r_[self.xy - m, self.col.foot - NEAR]
        self.hi = np.r_[self.xy + m, self.top + 1.0 + NEAR]

    def sd(self, p, detail=False):
        f = self.col.sd(p)
        if detail:
            return f, np.full(len(p), np.inf), np.full(len(p), self.r)
        return f

    def touches(self, lo, hi):
        return bool(np.all(self.hi >= lo) and np.all(self.lo <= hi))


def stacks(T):
    """The sea's stacks (terrain_sea) as solid prisms for the 3D tiles, and a note. Off with export.tiles "stacks":
    false."""
    st = (getattr(T, "sea", None) or {}).get("stacks") or []
    sea = _sea(T)
    out = []
    for i, a in enumerate(st):
        xy = np.asarray(a["xy"], float)
        top = sea + float(a["height"])
        from .terrain_sea import STACK_CORE
        rc = STACK_CORE * float(a["radius"]) + 0.11 * float(a["height"]) + 0.8  # (the core, spread at 84 deg, + margin)
        from .terrain_style import stack_form
        # its rock runs down into the sea floor round it (the lowest ground within twice its radius, 1.5 m in)
        r2 = 2.0 * STACK["radius"] * float(a["radius"]) + 2.0 * T.cell
        near = np.hypot(T.X - xy[0], T.Y - xy[1]) < r2
        foot = float(T.H[near].min()) - 1.5 if near.any() else sea - 3.0
        out.append(Stack(f"stack{i}", xy, sea - 2.0, top, STACK["radius"] * float(a["radius"]), 3000 + i, clip=rc,
                         sea=sea, over=stack_form(T, xy), foot=foot))
    stages = ", ".join(sorted({s.col.stage for s in out}))
    note = (f"stacks: {len(out)} as jointed rock columns ({stages}: joint faces, steps at a few levels, notch, "
            f"fallen blocks), "
            f"{min(a['height'] for a in st):.0f}-{max(a['height'] for a in st):.0f} m out of the water") if out else None
    return out, note


class Mound:
    """A low cone of fallen blocks standing on a floor (breakdown under a skylight or in a collapse pit): `radius` at
    its foot, `height` at its top, rough. Added to the rock (op "add")."""

    def __init__(self, name, at, radius, height, blend=0.6, rough=0.25, rough_scale=1.5, seed=0):
        self.name, self.op, self.blend, self.relief = name, "add", float(blend), 0.0
        self.at, self.r, self.h = np.asarray(at, float), float(radius), float(height)
        self.rough, self.rough_scale, self.seed = float(rough), float(rough_scale), int(seed)
        m = self.r + self.blend + self.rough + NEAR + 1.0
        self.lo = self.at - np.array([m, m, 1.5 + self.blend + self.rough])
        self.hi = self.at + np.array([m, m, self.h + m])

    def sd(self, p, detail=False):
        q = p - self.at
        rxy = np.hypot(q[:, 0], q[:, 1])
        L = math.hypot(self.r, self.h)
        side = (rxy * self.h + q[:, 2] * self.r - self.h * self.r) / L  # the cone's flank
        d = smax(side, -q[:, 2] - 0.3, 0.3)  # (its foot sunk a little into the floor)
        if self.rough > 0:
            d = d + self.rough * (2 * noise.fbm(p, self.rough_scale, 3, seed=self.seed) - 1)
        if detail:
            return d, np.full(len(p), np.inf), np.full(len(p), self.r)
        return d

    def touches(self, lo, hi):
        return bool(np.all(self.hi >= lo) and np.all(self.lo <= hi))


def wall_beds(p, b):
    """Beds in a passage's walls, as an offset to its distance (+ rock stands out: a ledge; - it's set back): each
    bed `amp` proud or recessed on its own, a notch along every bedding plane. Continuous: each bed hands over to the
    next over >= 0.45 m either side (a step in the field meshed as shards, a sharper one as teeth)."""
    off = b["off"](p[:, :2]) if b.get("off") else 0.0
    z = (p[:, 2] + off) / b["bed"]
    kb = np.floor(z).astype(np.int64)
    f = z - kb
    edge = np.minimum(f, 1 - f)
    be = max(0.12, 0.45 / b["bed"])
    o = lambda k: 2 * noise._hash(k, k * 0 + 11, k * 0, int(b.get("seed", 0))) - 1
    lower = f < 0.5
    nb = np.where(lower, kb - 1, kb + 1)
    u = smoothstep(-be, be, np.where(lower, f, f - 1))
    stand = np.where(lower, o(nb) * (1 - u) + o(kb) * u, o(kb) * (1 - u) + o(nb) * u)
    return b["amp"] * (stand - 0.6 * (1 - smoothstep(0.0, 2 * be, edge)))


def _bearing(T, v, at_xy):
    """A direction in plan: a compass bearing (0 north, 90 east) or an address to head for."""
    if isinstance(v, (int, float)):
        b = math.radians(float(v))
        return np.array([math.sin(b), math.cos(b)])
    xy = T.address(v)[0]
    d = np.asarray(xy, float) - at_xy
    return d / max(np.linalg.norm(d), 1e-9)


def _daylight(T, xy, t, below, reach=300.0, start=0.0):
    """Distance along t from xy to the first ground lower than `below` (where a passage comes out into the open)."""
    s = np.arange(start, reach, T.cell / 2)
    h = T.sample(xy + s[:, None] * t)
    k = np.flatnonzero(h < below)
    return float(s[k[0]]) if len(k) else None


def _daylight_back(T, xy, t, above, reach):
    """Distance along t from xy to the first ground higher than `above` (land standing in a line of sight), or None."""
    st = np.arange(0.0, reach, T.cell / 2)
    k = np.flatnonzero(T.sample(xy + st[:, None] * t) > above)
    return float(st[k[0]]) if len(k) else None


def _sea(T):
    return float(T.sea["level"]) if getattr(T, "sea", None) else None


def volumes(T) -> tuple[list[Tube], list[str]]:
    """The spec's volumes as tubes, and notes on what was chosen or doesn't fit (for the report)."""
    out, notes = [], []
    spec = T.spec.get("volumes") or {}
    if isinstance(spec, list):
        spec = {v.get("name", f"volume_{i}"): v for i, v in enumerate(spec, 1)}
    for k, (name, v) in enumerate(spec.items()):
        kind = v.get("type")
        seed = zlib.crc32(name.encode()) % 10000
        common = dict(op=v.get("op", "subtract"), blend=v.get("blend", DEFAULTS["blend"]), rough=v.get("rough", 0.4),
                      rough_scale=v.get("rough_scale", 3.0), seed=seed)
        at, _, adir = T.address(v["at"])  # an address's own direction (e.g. "cliff_foot:<address>": into the rock)
        at = np.asarray(at, float)
        adir = None if adir is None else np.asarray(adir, float)[:2] / max(np.linalg.norm(np.asarray(adir)[:2]), 1e-9)
        sea = _sea(T)
        if kind == "arch":
            floor = float(v.get("floor", (sea - 1.0) if sea is not None else T.height(at) - 6))
            roof_min = float(v.get("roof", 2.0))
            # where along the land near `at` the arch is shortest: real sea arches go through a thin neck, short and
            # tall (a fixed spot put a 38 m tunnel through a 30 m point)
            R = float(v.get("search", 30.0))
            g = np.arange(-R, R + 0.1, 3.0)
            cands = [at] + [at + np.array([dx, dy]) for dx in g for dy in g if 0 < dx * dx + dy * dy <= R * R]
            best = None
            for c in cands:
                top = T.height(c)
                height, w, roof = _arch_size(v, top - floor, roof_min)
                if height is None:
                    continue
                ts = [_bearing(T, v["toward"], c)] if "toward" in v else [
                    np.array([math.sin(math.radians(b_)), math.cos(math.radians(b_))]) for b_ in range(0, 180, 10)]
                for t in ts:
                    s1 = _daylight(T, c, t, floor + 0.5 * height, reach=80)
                    s2 = _daylight(T, c, -t, floor + 0.5 * height, reach=80)
                    if s1 is None or s2 is None:
                        continue
                    # short for its height (length over height), near `at`, and daylight through it: land standing
                    # in its line just past a mouth fills the opening with rock (pebble's first neck framed a rock
                    # 9 m off)
                    zc = floor + 0.75 * height  # (rocks awash in front of a mouth don't close it)
                    blocked = sum(_daylight_back(T, c + t * sg * (s_ + 2.0), t * sg, zc, 60.0) is not None
                                  for sg, s_ in ((1, s1), (-1, s2)))
                    # (and big enough to read: 6 m / height; daylight through it weighs more than its length, since
                    # the neck cut makes a long one a fin anyway)
                    score = (s1 + s2) / height + 0.01 * float(np.linalg.norm(c - at)) + 3.0 * blocked + 6.0 / height
                    if best is None or score < best[0]:
                        best = (score, c, t, s1, s2, top, height, w)
            if best is None:
                raise ValueError(f"volume {name!r}: no place within {R:.0f} m of {v['at']!r} where an arch fits (land "
                                 f"that comes out into the open both ways, {roof_min:g} m of roof over it, at least "
                                 f"half its span)")
            _, c, t, s1, s2, top, height, w = best
            # irregular: mouths flared and taller than the middle, the line bending a little
            side = np.array([-t[1], t[0]])
            u = np.linspace(-1, 1, 5)
            along = np.where(u < 0, u * (s2 + 0.5 * w), u * (s1 + 0.5 * w))
            bend = 0.12 * w * math.sin(seed) * (1 - u * u)
            xy = c + along[:, None] * t + bend[:, None] * side
            flare = 1 + 0.3 * u * u
            common["rough"] = v.get("rough", 0.25)
            tube = Tube(name, np.c_[xy, np.full(5, floor)], w / 2 * flare, height * (1 + 0.12 * u * u), floor,
                        **common)
            # the neck: a sea arch goes through a fin of rock about as thick as the arch is tall (Durdle Door, the
            # Green Bridge of Wales). Through a wider headland the arch read as a tunnel with a turf lid ("a cave with
            # a cover over it", the user on pebble's 38 m arch): the sea's bays cut in on both sides until the rock
            # left round the arch is `through` metres thick, over `neck` metres either side of it
            through = float(v.get("through", max(4.0, 0.9 * height)))
            land = s1 + s2
            tube.kind = "arch"
            tube.arch = {"c": c, "t": t, "s1": s1, "s2": s2, "w": w, "height": height, "floor": floor,
                         "bend": 0.12 * w * math.sin(seed), "through": min(through, land)}
            if land > 1.25 * through:
                neck = float(v.get("neck", max(6.0, 1.2 * w)))
                tube.cut = {"kind": "neck", "c": c.tolist(), "t": t.tolist(), "a1": s1 + 0.5 * w, "a2": s2 + 0.5 * w,
                            "hw": 0.5 * w, "neck": neck, "through": through, "floor": floor,
                            "bend": 0.12 * w * math.sin(seed)}
            out.append(tube)
            shape = (f"through a neck {through:.0f} m thick (bays cut in from {land:.0f} m of land)"
                     if land > 1.25 * through else f"{land:.0f} m through the rock")
            notes.append(f"{name}: arch at [{c[0]:.0f}, {c[1]:.0f}] heading {math.degrees(math.atan2(t[0], t[1])) % 180:.0f}"
                         f" deg, {w:.1f} m wide, {height:.1f} m high over a floor at {floor:+.1f} m, {shape}, roof "
                         f"{top - floor - height:.1f} m thick at its middle")
        elif kind in ("cave", "tunnel"):
            t = _bearing(T, v["toward"], at) if "toward" in v else adir if adir is not None else -_downhill(T, at)
            floor0 = float(v.get("floor", (sea - 0.5) if sea is not None else T.height(at)))
            w, h = float(v.get("width", 4.5)), float(v.get("height", 6.0))  # (taller than wide: sea caves follow joints)
            L = float(v.get("length", 30.0))
            rise = float(v.get("rise", 0.0))
            narrow = float(v.get("narrow", 0.7))
            # the mouth: where the rock starts along the way in (a cave addressed in the water or on the cliff top both
            # open at the cliff)
            if T.height(at) < floor0 + 0.5 * h:  # out in the open: ahead to the rock
                s = np.arange(0, 300, T.cell / 2)
                k = np.flatnonzero(T.sample(at + s[:, None] * t) >= floor0 + 0.5 * h)
                if not len(k):
                    raise ValueError(f"volume {name!r}: no rock ahead of {v['at']!r} to cut a cave into")
                mouth = at + t * s[k[0]]
            else:  # in the rock: back to where it comes out
                mouth = at - t * (_daylight(T, at, -t, floor0 + 0.5 * h, reach=200) or 0.0)
            start = mouth - t * 0.5 * w
            n = max(3, int(L / 6))
            s = np.linspace(0, L + 0.5 * w, n + 1)
            wander = float(v.get("wander", 0.08)) * L
            side = np.array([-t[1], t[0]])
            lat = wander * np.sin(np.pi * s / (L + 0.5 * w)) * math.sin(seed)  # one gentle bend
            xy = start + s[:, None] * t + lat[:, None] * side
            fl = floor0 + rise * np.clip(s / max(L, 1e-6), 0, 1)
            f = np.clip(s / (L + 0.5 * w), 0, 1)
            rw = w / 2 * (1 - (1 - narrow) * f)
            rh = h * (1 - (1 - narrow) * f)
            # a roof of at least ROOF_SPAN x the span (and 1.5 m) over every node under the ground: the passage
            # lowers where the rock over it thins, and ends where even a 1.8 m passage wouldn't keep it (a 0.7 m roof
            # broke through; a turf skin over a hole read as a lid)
            ground = T.sample(xy)
            rmin = np.maximum(1.5, ROOF_SPAN * 2 * rw)
            room = ground - fl - rmin
            under = ground > fl + 0.5 * rh  # (the part out in the open has no roof)
            fix = []
            if v.get("roof_rule", True):
                lowered = under & (room < rh)
                keep = ~(under & (room < 1.8))
                stop = int(np.argmin(keep)) if not keep.all() else len(keep)
                if stop < len(keep):
                    fix.append(f"ends after {s[max(stop - 1, 0)]:.0f} m (the rock over it thins under "
                               f"{float(rmin[stop]) + 1.8:.1f} m)")
                    xy, fl, rw, rh, ground, rmin, under = (a[:max(stop, 2)] for a in (xy, fl, rw, rh, ground, rmin,
                                                                                       under))
                lowered = lowered[:len(rh)]
                if lowered.any():
                    rh = np.where(lowered, np.maximum(1.8, np.minimum(rh, ground - fl - rmin)), rh)
                    fix.append(f"lowered to {float(rh[lowered].min()):.1f} m where the rock thins")
            out.append(Tube(name, np.c_[xy, fl], rw, rh, fl, **common))
            ch = float(v.get("chamber", 0.0))
            if ch > 0 and len(xy) == n + 1:  # a domed chamber at the end, on the passage's floor
                g_end = float(T.sample(xy[-1:])[0])
                ch_fit = min(ch, (g_end - fl[-1]) / (0.8 + 2 * ROOF_SPAN), (g_end - fl[-1] - 1.5) / 0.8) \
                    if v.get("roof_rule", True) else ch
                if ch_fit < ch:
                    fix.append(f"chamber r {ch:.0f} -> {max(ch_fit, 0):.1f} m (its roof)")
                    ch = ch_fit
                if ch >= 1.5:
                    out.append(Tube(name + ":chamber", [[*xy[-1], fl[-1]]], ch, 0.8 * ch, fl[-1], **common))
            inside = ground > fl + rh
            roof = float(np.min((ground - (fl + rh))[inside])) if inside.any() else float("nan")
            shape = " (wider than tall: sea caves follow joints, mostly taller than wide)" if w > 1.15 * h else ""
            notes.append(f"{name}: cave {w:g} x {h:g} m{shape}, mouth at [{mouth[0]:.0f}, {mouth[1]:.0f}] floor "
                         f"{floor0:+.1f} m, {L:.0f} m in" + (f", chamber r {ch:.0f} m" if ch else "")
                         + f"; thinnest roof {roof:.1f} m" + (" (it breaks through)" if roof < 1 else "")
                         + ("; " + ", ".join(fix) if fix else ""))
        elif kind == "overhang":  # a wave-cut notch along a cliff foot: the lip above overhangs it
            # a flat floor in the water, the roof high enough to see from a boat, the back cut deep under the lip
            depth, h = float(v.get("depth", 5.0)), float(v.get("height", 3.5))
            L = float(v.get("length", 30.0))
            floor = float(v.get("floor", (sea - 0.5) if sea is not None else T.height(at)))
            # along the face: across the address's own direction into the rock (cliff_foot:<address>), else the slope
            inward = adir if adir is not None else -_downhill(T, at)
            along = _bearing(T, v["along"], at) if "along" in v else np.array([-inward[1], inward[0]])
            pts = []
            for s_ in np.linspace(-L / 2, L / 2, max(3, int(L / 5) + 1)):
                face = _face(T, at + s_ * along, floor + h / 2)
                if face is not None:
                    pts.append(face)
            if len(pts) < 2:
                raise ValueError(f"volume {name!r}: no cliff face near {v['at']!r} to undercut")
            pts = np.array(pts)
            f = np.abs(np.linspace(-1, 1, len(pts)))
            ease = 1 - 0.75 * f ** 3  # full depth along most of it, easing out at the ends
            common["rough"] = v.get("rough", 0.3)
            # the rock over the notch: where the ground behind the face is too low to roof it (1.5 m and ROOF_SPAN x
            # its height), the notch is shallower there (it broke through behind a low stretch of cliff)
            hh = h * (0.6 + 0.4 * ease)
            if v.get("roof_rule", True):
                for i, p_ in enumerate(pts):
                    dn = _downhill(T, p_)
                    for fr in (1.0, 0.8, 0.6, 0.45, 0.3, 0.2):
                        if T.height(p_ - dn * depth * ease[i] * fr) - floor - hh[i] >= max(1.5, ROOF_SPAN * hh[i]):
                            break
                    else:  # (a low stretch of cliff: the notch dies out to a nick)
                        fr = 0.15
                        hh[i] = max(0.5, min(hh[i], T.height(p_) - floor - 1.5))
                    ease[i] *= fr
            out.append(Tube(name, np.c_[pts, np.full(len(pts), floor)], depth * ease, hh, floor, **common))
            lip = np.array([float(T.height(p_ - _downhill(T, p_) * depth * e_)) for p_, e_ in zip(pts, ease)]) \
                - floor - hh
            notes.append(f"{name}: overhang notch {depth:.1f} m deep, {h:.1f} m high over a floor at {floor:+.1f} m, "
                         f"{L:.0f} m along the cliff; {lip.min():.1f}-{lip.max():.1f} m of rock over it")
        else:
            raise ValueError(f"volume {name!r}: type {kind!r}: use arch, cave or overhang")
        if common["op"] not in ("subtract", "add"):
            raise ValueError(f"volume {name!r}: op {common['op']!r}: use subtract or add")
    return out, notes


ROOF_SPAN = 0.5  # the rock over an opening: at least this share of its span (thinner read as a lid on a hole)


def _arch_size(v, avail, roof_min):
    """An arch's height, span and roof from the rock standing over its floor (avail): 0.65 of it high unless given,
    0.8 of that wide (capped at 8 m; arches are taller than wide), and a roof of at least `roof_min` and ROOF_SPAN x
    the span. (None, ...) where it doesn't fit."""
    h = float(v.get("height", 0.65 * avail))
    w = float(v.get("width", min(8.0, 0.8 * h)))
    for _ in range(4):
        roof = max(roof_min, ROOF_SPAN * w)
        if avail - h >= roof - 1e-6:
            break
        h = avail - roof
        if "width" not in v:
            w = min(8.0, 0.8 * h)
    roof = max(roof_min, ROOF_SPAN * w)
    if h < 2 or avail - h < roof - 1e-6:
        return None, None, None
    return h, w, roof


def cut_neck(T, H, c):
    """A sea arch's neck dug into the ground grid: on each side of the arch the ground down to its floor where the
    land along the arch's line is more than `through`/2 from its middle, over `hw` + `neck` metres across (the
    bays narrowing to nothing at the neck's ends), so the rock round the arch is a fin `through` m thick."""
    t = np.asarray(c["t"], float)
    n = np.array([-t[1], t[0]])
    dx, dy = T.X - c["c"][0], T.Y - c["c"][1]
    a = dx * t[0] + dy * t[1]
    A = np.where(a >= 0, c["a1"], c["a2"])
    u = np.clip(np.where(a >= 0, a / c["a1"], a / c["a2"]), -1, 1)
    b = dx * n[0] + dy * n[1] - c["bend"] * (1 - u * u)
    hw, B, th = c["hw"], c["neck"], 0.5 * c["through"]
    # the neck's half thickness: `through`/2 at the arch, opening out to the whole land at the bays' far sides
    half = th + (A - th) * smoothstep(hw, hw + B, np.abs(b))
    wgt = smoothstep(half, half + 1.0, np.abs(a)) * smoothstep(A + c["hw"] + 4.0, A + c["hw"], np.abs(a)) \
        * smoothstep(hw + B + 1.0, hw + B, np.abs(b))
    return H - wgt * np.maximum(H - c["floor"], 0.0)


def through_view(field, tube, reach=300.0):
    """Does an arch show daylight? Rays parallel to its line through a grid over its opening (above the water), marched
    through the rock: the share that come out the far side clear is the see-through share. Beyond each mouth the
    centre ray runs on `reach` m: what it meets (sea/sky, or land at what distance) is what the opening frames."""
    A = tube.arch
    t = np.r_[np.asarray(A["t"], float), 0.0]
    n = np.array([-t[1], t[0], 0.0])
    c = np.r_[np.asarray(A["c"], float), 0.0]
    sea = A["floor"] + 1.0
    lo = max(A["floor"], sea) + 0.3
    hw = 0.5 * A["w"]
    us = np.linspace(-0.9, 0.9, 9) * hw
    zs = np.linspace(lo, A["floor"] + 0.95 * A["height"], 7)
    U, Z = np.meshgrid(us, zs)
    inside = (U / hw) ** 2 + ((Z - A["floor"]) / A["height"]) ** 2 <= 1.0  # (the ellipse over its floor)
    U, Z = U[inside], Z[inside]
    s = np.arange(-(A["s2"] + hw + 2.0), A["s1"] + hw + 2.0, 0.25)
    P = (c + U[:, None, None] * n + Z[:, None, None] * np.array([0, 0, 1.0]) + s[None, :, None] * t
         ).reshape(-1, 3)
    P[:, :2] += 0  # (the bend: under 1 m, inside the 0.9 x half width margin)
    F = field.value(P).reshape(len(U), len(s))
    clear = float((F > 0).all(1).mean()) if len(U) else 0.0
    zc = A["floor"] + 0.75 * A["height"]  # (land standing over most of the opening; rocks awash don't count)
    beyond = {}
    for sign, key in ((1, "ahead"), (-1, "behind")):
        d = np.arange(0, reach, 1.0)
        start = c + t * sign * ((A["s1"] if sign > 0 else A["s2"]) + 2.0)
        Q = start[None] + sign * d[:, None] * t
        h, _ = field.column(Q[:, 0], Q[:, 1])
        k = np.flatnonzero(h > zc)
        beyond[key] = None if not len(k) else float(d[k[0]])
    b = math.degrees(math.atan2(t[0], t[1])) % 360
    say = lambda d, bb: (f"open sea/sky toward {bb:.0f} deg" if d is None else f"land {d:.0f} m off toward {bb:.0f} deg")
    note = (f"{tube.name}: see-through {100 * clear:.0f}% of the opening (rays along it, above the water); beyond: "
            f"{say(beyond['ahead'], b)}, {say(beyond['behind'], (b + 180) % 360)}"
            + (" -- WARNING: the arch barely shows daylight" if clear < 0.5 else ""))
    return {"clear": round(clear, 3), "ahead_land_m": beyond["ahead"], "behind_land_m": beyond["behind"], "note": note}


def _downhill(T, xy):
    """Unit direction downhill at xy, the slope smoothed over a few cells."""
    e = 3 * T.cell
    gx = T.height(xy + [e, 0]) - T.height(xy - np.array([e, 0]))
    gy = T.height(xy + [0, e]) - T.height(xy - np.array([0, e]))
    g = -np.array([gx, gy])
    return g / max(np.linalg.norm(g), 1e-9)


def _narrowest(T, at):
    """The bearing along which the land at `at` is thinnest (an arch goes through a neck)."""
    best = None
    for b in range(0, 180, 5):
        t = np.array([math.sin(math.radians(b)), math.cos(math.radians(b))])
        s1 = _daylight(T, at, t, T.height(at) - 3)
        s2 = _daylight(T, at, -t, T.height(at) - 3)
        if s1 is not None and s2 is not None and (best is None or s1 + s2 < best[0]):
            best = (s1 + s2, t)
    if best is None:
        raise ValueError("an arch needs land that comes out into the open both ways")
    return best[1]


def _face(T, p, z):
    """Where the ground crosses height z nearest p, along the local slope (a cliff face's position)."""
    d = _downhill(T, p)
    s = np.arange(-40, 40, T.cell / 4)
    pts = p + s[:, None] * d
    h = T.sample(pts) - z
    k = np.flatnonzero(np.sign(h[:-1]) != np.sign(h[1:]))
    if not len(k):
        return None
    k = k[np.argmin(np.abs(s[k]))]
    f = h[k] / (h[k] - h[k + 1])
    return pts[k] + f * (pts[k + 1] - pts[k])
