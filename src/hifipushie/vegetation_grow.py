"""`grow`: a tree from its resolved style. Part of vegetation (vegetation.py has the overview)."""
from __future__ import annotations

import math
import time

import numpy as np

from .vegetation import resolve
from .vegetation_kernels import _child, _mix, _u
from .vegetation_tree import _Nodes, _compass, _norm, _path, steps_of
from .vegetation_grow_seasons import _seasons
from .vegetation_grow_wood import _dead_wood, _finish, _wood

class Growth:
    """What one plant's growth carries from stage to stage: the arguments of `grow`, then what each stage sets for
    the ones after it. A stage reads and writes it as `gx.<name>`; what a stage only uses itself is a local there.
    grow itself sets, before the first stage:
      s, h, t0
    _setting sets:
      unit, steps, yps, seed, sa, sb, sd, env, tilt, wind, wdir, wstr, g0u, gvu, clear_u, forces, stand, dead_log_,
      prunes, cuts, cut_log, bolls, envl
    _guides sets:
      guides, replaced
    _seedling sets:
      T, axes
    _seasons sets:
      ring_l, step, n, closed, m_
    _wood sets:
      out
    _dead_wood sets:
      subset
    """

    def __init__(self, **arguments):
        self.__dict__.update(arguments)


def grow(spec: dict, unit_scale: float | None = None, log=None) -> dict:
    """Grow the tree. Returns arrays in metres (pos, parent, radius, order, born, axis, key, tip, leafy), axes, and
    stats. With `height`, an unedited run is grown first and its height sets the unit, so edits stay in metres."""
    s = resolve(spec)
    if s.get("plant") == "sward":  # a tile of blades, not a plant with a skeleton
        from . import veg_sward
        return veg_sward.grow(s)
    if s.get("plant") == "clump":  # assembled, not grown
        from . import veg_small
        return veg_small.grow(s)
    h = s["habit"]
    t0 = time.perf_counter()
    if s.get("height") and unit_scale is None:
        bare = {k: v for k, v in spec.items() if k not in ("guides", "prune", "envelope", "forces", "height", "cuts", "dead")}
        ref = grow(bare, unit_scale=1.0)
        k = float(s["height"]) / max(ref["height"], 1e-6)
        if abs(k - 1) > 0.02:
            out = grow(spec, unit_scale=k)
            out["stats"]["unit_scale"] = round(k, 3)
            out["stats"]["grow_s"] = round(time.perf_counter() - t0, 3)
            return out
        unit_scale = 1.0
    gx = Growth(spec=spec, unit_scale=unit_scale, log=log, s=s, h=h, t0=t0)
    _setting(gx)
    _guides(gx)
    _seedling(gx)
    _seasons(gx)
    _wood(gx)
    _dead_wood(gx)
    return _finish(gx)


def _setting(gx):
    """What the growth is given: the unit, the steps and the seed, the shadow's numbers, the light, wind, ground and stand
    of its environment, the forces, the steps each cut is made at."""
    gx.unit = gx.h["unit"] * (gx.unit_scale or 1.0)
    gx.steps = steps_of(gx.s)
    gx.yps = gx.h["years_per_step"]
    gx.seed = np.uint64(int(gx.s["seed"]) * 2654435761 % (1 << 62) + 12345)
    gx.sa, gx.sb, gx.sd = gx.h["shadow"]
    gx.sd = int(gx.sd)
    gx.env = gx.s.get("environment") or {}
    light = _norm(np.asarray(gx.env.get("light", [0, 0, 1]), float))
    gx.tilt = (-light[0] / max(light[2], 0.3), -light[1] / max(light[2], 0.3))  # shadows fall away from the light
    gx.wind = gx.env.get("wind")
    gx.wdir = _compass(gx.wind["from"]) * -1 if gx.wind else None  # the way it blows
    gx.wstr = float(gx.wind.get("strength", 0.5)) if gx.wind else 0.0
    g_ = gx.env.get("ground") or {}  # the ground in growth units: z = g0u + [x, y] . gvu
    gx.g0u = float(g_.get("level", 0.0)) / gx.unit
    gx.gvu = np.zeros(2)
    if g_.get("slope"):
        t_ = np.asarray(g_.get("toward", [1, 0]), float)
        gx.gvu = -math.tan(math.radians(float(g_["slope"]))) * t_ / max(np.linalg.norm(t_), 1e-9)
    gx.clear_u = float(gx.h["ground_clear"]) / gx.unit
    gx.forces = [(np.asarray(f["dir"], float) * float(f.get("strength", 1.0)), f.get("orders")) for f in gx.s.get("forces") or []]
    gx.stand = gx.env.get("stand") if gx.env.get("setting") in ("forest", "stand", "edge") or gx.env.get("stand") else None
    if gx.env.get("setting") in ("forest", "edge") and gx.stand is None:
        gx.stand = {}
    if gx.env.get("setting") == "edge":  # a stand's edge: closed behind, open to one side (foliage down that side only)
        gx.stand = {**gx.stand, "open_side": gx.env.get("open_side", gx.stand.get("open_side", [1, 0]))}
    gx.dead_log_ = []  # limbs the shade killed: (the trunk node's key, direction, girth, step)
    gx.prunes = gx.s.get("prune") or []
    gx.cuts = []
    for c in gx.s.get("cuts") or []:  # the steps each cut is made at
        y, last_y = float(c["year"]), float(c.get("until_year", gx.s["age"]))
        ys = [y]
        while c.get("every") and ys[-1] + float(c["every"]) <= last_y:
            ys.append(ys[-1] + float(c["every"]))
        gx.cuts.append(({int(round(q / gx.yps)) for q in ys}, c))
    gx.cut_log = []
    gx.bolls = {}  # node key -> swelling: where a pollard is cut again and again the wood heals into a knuckled head
    gx.envl = gx.s.get("envelope")


def _guides(gx):
    """The guides: each path in metres made growth units, with the step it starts at; the shoots a guide replaces."""

    # guides: paths in metres -> units; each starts at a step
    gx.guides = []
    for name, g in (gx.s.get("guides") or {}).items():
        pts, cum = _path(np.asarray(g["path"], float) / gx.unit, smooth=not g.get("straight"))
        st = int(round(g.get("from_year", 0) / gx.yps))
        until = g.get("until_year")
        en = int(round(until / gx.yps)) if until is not None else None
        gx.guides.append({"name": name, "pts": pts, "cum": cum, "start": st, "end": en, "s": 0.0, "node": -1,
                       "vigour": float(g.get("vigour", 1.0)), "done": False, "free": bool(g.get("free", False)),
                       "on": g.get("on"), "bare": float(g.get("bare", 0.0))})
    gx.guides.sort(key=lambda g: (g["start"], g["name"]))
    # a limb taken over as a guide: the shoot it was grown from is not made again (its lineage key)
    gx.replaced = np.array([int(k) for g in (gx.s.get("guides") or {}).values() for k in (g.get("replaces") or [])], np.uint64)


def _seedling(gx):
    """The foot and the first internode of each stem (straight up, more stems leaning out round it), or a drawn trunk
    as the seedling."""

    gx.T = _Nodes()
    gx.T.add(1, key=_mix(gx.seed), tip=False, guide=-1, R=np.eye(3))
    gx.axes = [{"order": 0, "node": 1, "guide": None}]
    trunk = next((g for g in gx.guides if g["start"] == 0 and np.linalg.norm(g["pts"][0]) < 1.5), None)
    if trunk is None:  # the first internode: straight up
        gx.T.add(1, pos=[0, 0, 1.0], off=[0, 0, 1.0], parent=0, main=True, key=_child(_mix(gx.seed), 0), tip=True,
              nb=0, guide=-1, R=np.eye(3), vig=1.0)
        for si_ in range(1, int(gx.h["stems"])):  # more stems from the same foot, leaning out round it
            a_ = 2.399963 * si_ + 6.283 * float(_u(_child(_mix(gx.seed), 300), 1))
            t_ = math.radians(float(gx.h["stem_angle"]) * (0.6 + 0.8 * float(_u(_child(_mix(gx.seed), 300 + si_), 2))))
            d_ = [math.sin(t_) * math.cos(a_), math.sin(t_) * math.sin(a_), math.cos(t_)]
            gx.axes.append({"order": 0, "node": gx.T.n, "guide": None, "born": 0})
            gx.T.add(1, pos=d_, off=d_, parent=0, main=True, key=_child(_mix(gx.seed), 300 + si_), tip=True,
                  nb=0, guide=-1, R=np.eye(3), vig=1.0, axis=len(gx.axes) - 1)
    else:  # a drawn trunk: its path is the seedling
        trunk.update(node=0, axis=0)
        gx.axes[0]["guide"] = trunk["name"]
