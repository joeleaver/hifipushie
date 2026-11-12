"""Applying paint: apply and its channels, bump, the view, a layer's mask and stack, blur, post, blend, the
generators; layers composited per point ahead of the node program. Part of paint (paint.py has the spec)."""
from __future__ import annotations

import numpy as np

from . import paint
from .noise import fbm
from .spec import SpecError
from .paint import _expanded, _ramp, colour, layers
from .paint_check import validate
from .paint_masks import _axis_mask, _near_mask, _outline_mask, _path_mask, element_random, painted_values
from .paint_patterns import (
    _along, _grain, _planar, _stretch, _tiles, _weave, cells, noise, resolve_spot, spot_mask, srgb_to_linear,
    tile_mask,
)

def apply(spec: dict, verts: np.ndarray, normals: np.ndarray, part: np.ndarray, part_names: list[str],
          base: np.ndarray, voxel: float, stats: dict | None = None, cache: dict | None = None,
          masks: dict | None = None) -> np.ndarray:
    """Painted sRGB colours (n, 3) for a built mesh, starting from `base` (each vertex's part clay colour).
    stats, if given, gets each layer's coverage: the fraction of its parts' vertices it paints at least half.
    cache: the vertices' field inputs (surface.Points), filled in as layers need them."""
    from .surface import Points
    pts = Points(spec, verts, normals, part, part_names, voxel, cache)
    return apply_channels(spec, pts, {"color": base[:, :3]}, stats, masks)["color"]


def bump(spec: dict, pts, eps: float, masks: dict | None = None):
    """Painted height (layers' "height" times their mask, summed; m) and the normals it tilts, or None when no
    layer has height. The slope comes from central differences `eps` apart across the surface (4 more
    evaluations of the height layers). masks: the layers' masks at pts, if apply_channels already made them."""
    from .surface import _frame, unit
    hl = {k: ly for k, ly in layers(spec).items() if ly.get("height")}
    if not hl:
        return None

    def height(p, given=None):
        h = np.zeros(len(p))
        for name, ly in hl.items():
            if given is not None and name in given:
                h += float(ly["height"]) * given[name]
                continue
            parts = ly.get("part", "body")
            parts = p.part_names if parts == "*" else ([parts] if isinstance(parts, str) else parts)
            idx = np.flatnonzero(np.isin(p.part, [p.part_names.index(q) for q in parts if q in p.part_names]))
            if len(idx):
                h[idx] += float(ly["height"]) * layer_mask(spec, name, ly, _View(p, idx))
        return h

    h0 = height(pts, masks)
    T, B = _frame(pts.normal)
    d = [height(pts.moved(pts.pos + s * eps * D, keep_inputs=True)) for D in (T, B) for s in (1, -1)]
    dT, dB = (d[0] - d[1]) / (2 * eps), (d[2] - d[3]) / (2 * eps)
    return h0, unit(pts.normal - dT[:, None] * T - dB[:, None] * B)


def part_defaults(spec: dict, part_names: list[str], part: np.ndarray) -> dict:
    """Every channel's starting value per point, from its part's definition."""
    from .store import part_colour
    defs = spec.get("parts") or {}
    col = np.array([part_colour(p, defs, i)[:3] for i, p in enumerate(part_names)])
    rough = np.array([float((defs.get(p) or {}).get("roughness", 0.6)) for p in part_names])
    metal = np.array([float((defs.get(p) or {}).get("metallic", 0.0)) for p in part_names])
    spec_ = np.array([float((defs.get(p) or {}).get("specular", 0.5)) for p in part_names])
    return {"color": col[part], "roughness": rough[part][:, None], "metallic": metal[part][:, None],
            "specular": spec_[part][:, None]}


def apply_channels(spec: dict, pts, base: dict, stats: dict | None = None, masks: dict | None = None) -> dict:
    """Paint every channel in `base` ({"color": (n, 3), "roughness": (n, 1), ...}) at arbitrary surface points
    (a surface.Points: mesh vertices, or texels of a baked texture). masks, if given, gets each layer's mask
    over all points (0 off its parts)."""
    out = {c: np.array(v, float) for c, v in base.items()}
    if not (spec.get("paint") or spec.get("skin")):
        return out
    validate(spec)
    for name, ly in layers(spec).items():
        parts = ly.get("part", "body")
        parts = pts.part_names if parts == "*" else ([parts] if isinstance(parts, str) else parts)
        idx = np.flatnonzero(np.isin(pts.part, [pts.part_names.index(p) for p in parts if p in pts.part_names]))
        if not len(idx):
            if stats is not None:
                stats[ly.get("_of") or name] = None
            continue  # e.g. a close-up that doesn't reach that part
        m = layer_mask(spec, name, ly, _View(pts, idx))
        of = ly.get("_of")
        if stats is not None and (of is None or of not in stats):  # a material reports its first sub-layer
            seen = pts.get("hidden")[idx] < 0.5  # skin under clothes or in an eye socket doesn't count
            stats[of or name] = float((m[seen] >= 0.5).mean()) if seen.any() else 0.0
        if masks is not None:
            masks[name] = np.zeros(len(pts))
            masks[name][idx] = m
        a = (float(ly.get("opacity", 1.0)) * m)[:, None]
        for c, arr in out.items():
            if c in ly:
                if c == "color" and ly[c] == "image":  # the picture's own colours (sRGB, as every colour here)
                    from . import images_frame, images_project
                    view = _View(pts, idx)
                    fr = images_frame.frame(spec, ly["image"], _expanded(spec), what=f"paint {name!r} image",
                                       parts=ly.get("part", "body"))
                    _, val = images_project.evaluate(fr, view.v, view.n)
                    arr[idx] += a * (val - arr[idx])
                    continue
                val = colour(ly[c]) if c == "color" else np.array([float(ly[c])])
                arr[idx] += a * (val[None] - arr[idx])
    return out


class _View:
    """Some of a Points set (idx), possibly mirrored across X: positions and normals as a mask sees them.
    Field inputs (ao, curvature, thickness) are always the point's own, mirrored or not."""

    def __init__(self, pts, idx: np.ndarray, mirror: bool = False):
        self.pts, self.idx, self.mirror = pts, idx, mirror
        self.v = pts.pos[idx] * paint.MIRROR if mirror else pts.pos[idx]
        self.n = pts.normal[idx] * paint.MIRROR if mirror else pts.normal[idx]

    def __len__(self):
        return len(self.idx)

    def get(self, key: str) -> np.ndarray:
        return self.pts.get(key)[self.idx]

    def mirrored(self) -> "_View":
        return _View(self.pts, self.idx, not self.mirror)

    def jittered(self, radius: float, k: int = 12):
        """k copies of these points moved across the surface (a Vogel disc of `radius`, Gaussian weights)."""
        from .surface import _frame
        P, N = self.pts.pos[self.idx], self.pts.normal[self.idx]
        U, V = _frame(N)
        i = np.arange(k) + 0.5
        r = radius * np.sqrt(i / k)
        a = i * 2.39996323  # golden angle
        w = np.exp(-2 * (r / radius) ** 2)
        views = []
        for rr, aa in zip(r, a):
            here = self.pts.__class__(self.pts.spec, P, N, self.pts.part[self.idx], self.pts.part_names,
                                      self.pts.voxel, streams=self.pts._streams)
            here.footprint = self.pts.footprint
            moved = here.moved(P + rr * (np.cos(aa) * U + np.sin(aa) * V))
            moved.footprint = self.pts.footprint
            views.append(_View(moved, np.arange(len(P)), self.mirror))
        return views, w / w.sum()


def _tag(name: str, i) -> str:
    """A stack entry's own name (paths seat as strokes named after it), keeping a ".L" suffix at the end."""
    if i is None:
        return name
    stem, sfx = (name[:-2], name[-2:]) if name.endswith((".L", ".R")) else (name, "")
    return f"{stem}~{i}{sfx}"


def layer_mask(spec: dict, name: str, ly: dict, view: _View) -> np.ndarray:
    """A layer's mask: its flat keys (each a generator, multiplied), then its "mask" stack, 0..1. A ".L" layer
    takes the stronger of the mask at the point and at its mirror image."""
    stack = [{g: ly[g], **{k: ly[k] for k in paint.PARAMS.get(g, ()) if k in ly}} for g in paint.GENERATORS
             if g in ly and g != "mask"]
    tags = [None] * len(stack)
    if "mask" in ly:
        stack += ly["mask"]
        tags += list(range(len(ly["mask"])))
    m = _stack(spec, name, stack, tags, view)
    if name.endswith(".L"):
        m = np.maximum(m, _stack(spec, name, stack, tags, view.mirrored()))
    return np.clip(m, 0, 1)


def _stack(spec: dict, name: str, stack: list, tags: list, view: _View) -> np.ndarray:
    m = None
    for j, (e, tag) in enumerate(zip(stack, tags)):
        gen = next((g for g in paint.GENERATORS if g in e), None)
        if gen is None:  # an op on the mask so far
            if m is None:
                m = np.ones(len(view))
            if "blur" in e:
                m = _blurred(lambda v: _stack(spec, name, stack[:j], tags[:j], v), view, float(e["blur"]), m)
            m = _post(m, e, view)
            continue
        g = _generate(spec, name, gen, e, _tag(name, tag), view)
        if "blur" in e:
            g = _blurred(lambda v: _generate(spec, name, gen, e, _tag(name, tag), v), view, float(e["blur"]), g)
        g = _post(g, e, view)
        mode = e.get("blend", "multiply")
        if m is None:
            m = g  # the first generator starts the mask
            continue
        b = _blend(mode, m, g)
        wgt = float(e.get("weight", 1.0))
        m = np.clip(m + wgt * (b - m), 0, 1)
    return np.ones(len(view)) if m is None else m


def _blurred(fn, view: _View, radius: float, m0: np.ndarray) -> np.ndarray:
    """fn (a mask at a view's points) averaged over a disc of `radius` across the surface. m0 is fn unblurred:
    only points whose neighbourhood isn't constant in it get sampled (a cell grid of size radius finds them)."""
    if radius <= 0 or not len(view):
        return m0
    cell = np.floor(view.v / radius).astype(np.int64)
    keys, inv = np.unique(cell, axis=0, return_inverse=True)
    inv = inv.ravel()
    lo = np.full(len(keys), np.inf)
    hi = np.full(len(keys), -np.inf)
    np.minimum.at(lo, inv, m0)
    np.maximum.at(hi, inv, m0)
    code = lambda c: (c[:, 0] * 2_000_003 + c[:, 1]) * 2_000_029 + c[:, 2]  # noqa: E731
    kc = code(keys)
    order = np.argsort(kc)
    nlo, nhi = lo.copy(), hi.copy()
    for off in np.array(np.meshgrid([-1, 0, 1], [-1, 0, 1], [-1, 0, 1])).reshape(3, -1).T:
        q = code(keys + off)
        at = np.clip(np.searchsorted(kc, q, sorter=order), 0, len(kc) - 1)
        hit = kc[order[at]] == q
        nlo[hit] = np.minimum(nlo[hit], lo[order[at[hit]]])
        nhi[hit] = np.maximum(nhi[hit], hi[order[at[hit]]])
    varying = np.flatnonzero((nhi - nlo)[inv] > 1e-4)
    out = m0.copy()
    if len(varying):
        sub = _View(view.pts, view.idx[varying], view.mirror)
        views, w = sub.jittered(radius)
        out[varying] = sum(wi * fn(v) for v, wi in zip(views, w))
    return out


def _post(g: np.ndarray, e: dict, view: _View) -> np.ndarray:
    if "breakup" in e:  # noise shifts the threshold: edges chip, grime gathers in blotches
        b = e["breakup"]
        b = {"amount": float(b)} if isinstance(b, (int, float)) else b
        n = fbm(view.v, float(b.get("scale", 0.03)), int(b.get("octaves", 3)), int(b.get("seed", 0)))
        s = 0.5 * (1 - min(max(float(b.get("sharpness", 0.5)), 0.0), 0.98))
        g = _ramp(g + float(b.get("amount", 0.5)) * (2 * n - 1), 0.5 - s, 0.5 + s)
    if "levels" in e:
        lv = e["levels"]
        lo, hi = float(lv[0]), float(lv[1])
        g = np.clip((g - lo) / (hi - lo if hi != lo else 1e-9), 0, 1) ** (1 / float(lv[2]) if len(lv) > 2 else 1)
    if e.get("invert"):
        g = 1 - g
    return g


def _blend(mode: str, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if mode == "multiply":
        return a * b
    if mode == "add":
        return a + b
    if mode == "subtract":
        return a - b
    if mode == "min":
        return np.minimum(a, b)
    if mode == "max":
        return np.maximum(a, b)
    if mode == "screen":
        return 1 - (1 - a) * (1 - b)
    if mode == "overlay":
        return np.where(a < 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))
    return b  # replace


def _generate(spec: dict, name: str, gen: str, e: dict, tag: str, view: _View) -> np.ndarray:
    """One generator's 0..1 value at the view's points."""
    v, n = view.v, view.n
    if gen == "path":  # seated on the part these points are on (the layer's, even from inside a mask stack)
        counts = np.bincount(view.pts.part[view.idx], minlength=len(view.pts.part_names))
        return _path_mask(spec, tag, {**e, "part": view.pts.part_names[int(np.argmax(counts))]}, v, n)
    if gen == "near":
        return _near_mask(spec, name, e, v)
    if gen == "facing":  # a direction, or one of the story's named directions ("weather", "sun"), or "element"
        from .realism import direction
        lo, hi = e.get("range", [0.0, 0.7])
        if e["facing"] == "element":
            return _ramp(np.abs((n * _grain(view)[0]).sum(1)), lo, hi)
        return _ramp(n @ direction(spec, e["facing"], f"paint {name!r}"), lo, hi)
    if gen == "axis":
        return _axis_mask(spec, name, e["axis"], v)
    if gen == "noise":
        nz = e["noise"]
        lo, hi = nz.get("range", [0.45, 0.6])
        return _ramp(noise(v, nz, _grain(view) if _along(nz) else None), lo, hi)
    if gen == "cells":
        c = e["cells"]
        mode = c.get("mode", "edges")
        val = cells(_stretch(v, c, _grain(view) if _along(c) else None), float(c.get("scale", 0.03)), mode, float(c.get("jitter", 1.0)), int(c.get("seed", 0)))
        lo, hi = c.get("range", {"edges": [0.15, 0.0], "distance": [0.35, 0.1], "id": [0.0, 1.0]}[mode])
        return _ramp(val, lo, hi)
    if gen == "cavity":
        r0, r1 = e.get("radius", [0.03, 0.006])
        curv = view.get("curvature")
        return _ramp(-curv if e["cavity"] == "concave" else curv, 1 / r0, 1 / r1)
    if gen == "tiles":
        t = e["tiles"]
        return _planar(lambda u, w: _tiles(u, w, t), v, n, t.get("dir"))
    if gen == "weave":
        w = e["weave"]
        sc = float(w.get("scale", 0.0025))
        val = _planar(lambda a, b: _weave(a, b, sc), v, n, w.get("dir"))
        # threads under ~3 points across can't be resolved: fade to the average instead of aliasing (like a mip)
        k = float(np.clip((sc / max(view.pts.footprint, 1e-9) - 2.0) / 2.0, 0, 1))
        return 0.55 + k * (val - 0.55)
    if gen in ("ao", "thickness", "sky"):
        a, b = e[gen]
        return _ramp(view.get(gen), float(a), float(b))
    if gen == "rings":
        r = e["rings"]
        sp = float(r.get("spacing", 0.006))
        rad = np.linalg.norm(view.get("radial"), axis=1)
        seed = view.get("grain_seed")
        wob = float(r.get("warp", 0.5)) * sp * (2 * noise(v, {"scale": 8 * sp, "octaves": 2, "seed": int(r.get("seed", 0))}) - 1)
        ph = (rad + seed * 7.31 * sp + wob) / sp
        lo, hi = r.get("range", [0.75, 0.9])
        return _ramp(0.5 + 0.5 * np.cos(2 * np.pi * ph), float(lo), float(hi))
    if gen == "random":
        r = e["random"]
        lo, hi = r.get("range", [0.0, 1.0])
        return _ramp(element_random(view.get("grain_seed"), int(r.get("seed", 0))), float(lo), float(hi))
    if gen == "painted":
        return painted_values(e["painted"], v, n)
    if gen == "outline":
        return _outline_mask(spec, name, e["outline"], v, n)
    if gen == "image":  # a mirrored view (a ".L" layer) sees the picture unmirrored on the other side
        from . import images_frame, images_project
        on = sorted({view.pts.part_names[i] for i in np.unique(view.pts.part[view.idx])}) if len(view) else None
        fr = images_frame.frame(spec, e["image"], _expanded(spec), what=f"paint {name!r} image", parts=on)
        if view.mirror:
            fr = {**fr, "flip": not fr["flip"]}
        return images_project.evaluate(fr, v, n)[0]
    if gen == "spot":
        return spot_mask(resolve_spot(spec, e["spot"], f"paint {name!r}"), v)
    if gen == "tile":
        return tile_mask(e["tile"], v, n)
    if gen == "mask":
        sub = e["mask"]
        return _stack(spec, tag, sub, list(range(len(sub))), view)
    raise SpecError(f"paint {name!r}: unknown generator {gen!r}")


# ---- layers composited per point ahead of the node program ------------------------------------------------------
def pre_layers(spec: dict) -> dict:
    """The layers marked "_pre" (the skin's broad colour layers): composited here per vertex into one base the
    scene's material starts from, instead of each being a branch of its node program (a renderer's shader has
    room for a few dozen layers: Cycles' stack ran out near 45, EEVEE compiled 100 for minutes)."""
    return {n: ly for n, ly in layers(spec).items() if ly.get("_pre")}


def precomposite(spec: dict, view, base: dict, pre: dict) -> np.ndarray:
    """(n, 5): linear r, g, b, roughness, specular at the view's points after the pre layers, from the part's base
    channels (sRGB colour). Mixed in linear colour, as the node program mixes."""
    col = np.tile(srgb_to_linear(np.asarray(base["color"], float)[:3]), (len(view), 1))
    rough = np.full(len(view), float(base.get("roughness", 0.6)))
    spc = np.full(len(view), float(base.get("specular", 0.5)))
    for name, ly in pre.items():
        a = np.clip(float(ly.get("opacity", 1.0)) * layer_mask(spec, name, ly, view), 0, 1)
        if "color" in ly:
            c = srgb_to_linear(colour(ly["color"]))
            mode = ly.get("mix", "mix")
            if mode == "multiply":
                col = col * (1 - a[:, None] + a[:, None] * c)
            elif mode == "screen":
                col = col + a[:, None] * ((1 - (1 - col) * (1 - c)) - col)
            else:
                col = col + a[:, None] * (c - col)
        if "roughness" in ly:
            rough = rough + a * (float(ly["roughness"]) - rough)
        if "specular" in ly:
            spc = spc + a * (float(ly["specular"]) - spc)
    return np.column_stack([col, rough, spc])
