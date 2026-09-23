"""Paint: colour laid on the built surface, one vertex colour per mesh vertex.

spec["paint"] = {name: layer, ...}: layers apply in order, each over the colour so far (every part starts
from its clay colour, spec["parts"][p]["color"]). Paint never changes geometry, so repainting doesn't rebuild.

layer = {"color": [r, g, b] (0..1, sRGB, as you'd pick it) | "#rrggbb", "roughness", "metallic", "specular": 0..1,
         (any of these channels; a layer changes only the ones it gives), "opacity": 0..1 (1),
         "part": name | [names] | "*" (default "body"), plus any of the masks below, multiplied together.
         No mask = the whole part.}
Each part starts from spec["parts"][p]: "color" (clay palette), "roughness" (0.6), "metallic" (0), "specular"
(0.5 = the usual 4% reflectance of skin, cloth, plastic). These show in exported game assets (export_asset), not
in the clay views: wet lips roughness 0.2, skin 0.5-0.6, cloth 0.8-0.9 with specular 0.3, metal buckles
metallic 1 with roughness 0.3, eyes roughness 0.05 with specular 0.7.

Masks (each 0..1 per vertex):
  path:    surface addresses exactly as for strokes ({"bone", "t", "side", "around"} or {"at", "offset", "dir"},
           later points inheriting), with "width" (half-width, m; a number or one per control point) and
           "profile": "flat" (default: solid with a soft rim) | "soft" | "round" | "sharp". One point = a spot.
           "repeat" and "scatter" work as for strokes (spots, stripes, freckles). Paint doesn't print through
           to the far side of a thin part (it only covers skin facing the way the path's skin faces).
  near:    [element names] (bones, blobs, kit output such as "face_eye.L", "hand_f2_3.L", or a kit's name for
           all it generates, e.g. "hand.L"): skin within "within"
           (m, default 0) of those primitives' own surfaces, fading over "soft" (m, 0.01) beyond. A primitive's
           own surface is inside the blended skin, so "within" ~ the blend radius covers its whole footprint.
  facing:  [x, y, z]: by how much the skin faces that way (normal . dir), ramping from "range"[0] to "range"[1]
           (default [0, 0.7]). [0, 0, 1] with a dark colour darkens the back; [0, 0, -1] lightens the belly
           (countershading).
  axis:    {"dir": [x, y, z], "from": a, "to": b} ramps 0 -> 1 as position . dir goes from a to b (world metres),
           or {"bone": name, "from": t0, "to": t1} along a bone (0 at its start joint, 1 at its end; outside the
           range it clamps): tail tips, gloved hands, socks, fading limbs. It ramps across the whole part (the
           feet lie past a forearm's end too): confine it with "near", e.g. {"near": ["forearm.L", "hand.L"],
           "within": 0.02, "axis": {"bone": "forearm.L", "from": 0.7, "to": 1}} for a glove.
  cavity:  "concave" | "convex", "radius": [r0, r1] (m, default [0.03, 0.006]): zero where the surface is
           curved gentler than radius r0 (mean curvature), full where tighter than r1. Dirt in creases,
           light on ridges and knuckles. Depends a little on the build resolution.
  noise:   {"scale": m (feature size, 0.03), "range": [lo, hi] (0.45, 0.6), "octaves": 3, "seed": 0}: fractal
           noise thresholded softly between lo and hi. Mottling, blotches, patches; narrow ranges give crisp
           patches, wide ones soft variation. Combine with other masks to confine it.

Symmetry: a layer named ".L" is mirrored (its masks, noise included, evaluated at the vertex and at its mirror
image, whichever is stronger); a centre-named layer isn't, so asymmetric markings are plain names.

Colour detail can't be finer than the mesh: about one voxel (see look's info line). Judge colour with
look(shading="flat") (unlit colour) as well as the clay views.
"""

from __future__ import annotations

import copy
import hashlib
import json

import numpy as np

from .spec import SpecError

MIRROR = np.array([-1.0, 1.0, 1.0])
CHANNELS = ("color", "roughness", "metallic", "specular")
VERSION = 1  # bump when painting output changes, so cached painted meshes are redone


def colour(c, what: str = "color") -> np.ndarray:
    """sRGB 0..1 triple from [r, g, b] or "#rrggbb"."""
    if isinstance(c, str):
        s = c.lstrip("#")
        if len(s) != 6:
            raise SpecError(f"{what}: {c!r} isn't #rrggbb")
        return np.array([int(s[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    v = np.asarray(c, float)
    if v.shape[-1] < 3 or np.any(v[:3] < 0) or np.any(v[:3] > 1):
        raise SpecError(f"{what}: {c!r} isn't [r, g, b] in 0..1")
    return v[:3]


def validate(spec: dict) -> None:
    for name, ly in (spec.get("paint") or {}).items():
        if not any(c in ly for c in CHANNELS):
            raise SpecError(f"paint {name!r}: needs at least one of {', '.join(CHANNELS)}")
        if "color" in ly:
            colour(ly["color"], f"paint {name!r}")
        for c in ("roughness", "metallic", "specular"):
            if c in ly and not 0 <= float(ly[c]) <= 1:
                raise SpecError(f"paint {name!r}: {c} is 0..1")
        unknown = set(ly) - {*CHANNELS, "opacity", "part", "path", "width", "profile", "repeat", "scatter", "near",
                             "within", "soft", "facing", "range", "axis", "cavity", "radius", "noise"}
        if unknown:
            raise SpecError(f"paint {name!r}: unknown keys {sorted(unknown)}")
        if "cavity" in ly and ly["cavity"] not in ("concave", "convex"):
            raise SpecError(f"paint {name!r}: cavity is \"concave\" or \"convex\"")


def key(spec: dict) -> str:
    """What painted colours depend on besides the mesh."""
    return hashlib.sha1(json.dumps([spec.get("paint"), spec.get("parts")], sort_keys=True,
                                   default=float).encode()).hexdigest()[:12]


def apply(spec: dict, verts: np.ndarray, normals: np.ndarray, part: np.ndarray, part_names: list[str],
          base: np.ndarray, voxel: float, stats: dict | None = None) -> np.ndarray:
    """Painted sRGB colours (n, 3) for a built mesh, starting from `base` (each vertex's part clay colour).
    stats, if given, gets each layer's coverage: the fraction of its parts' vertices it paints at least half."""
    return apply_channels(spec, verts, normals, part, part_names, {"color": base[:, :3]}, voxel, stats)["color"]


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


def apply_channels(spec: dict, verts: np.ndarray, normals: np.ndarray, part: np.ndarray, part_names: list[str],
                   base: dict, voxel: float, stats: dict | None = None) -> dict:
    """Paint every channel in `base` ({"color": (n, 3), "roughness": (n, 1), ...}) at arbitrary surface points
    (verts with their normals and part index): mesh vertices, or texels of a baked texture."""
    from . import sdf
    from .spec import compile_prims
    layers = spec.get("paint") or {}
    out = {c: np.array(v, float) for c, v in base.items()}
    if not layers:
        return out
    validate(spec)
    verts = verts.astype(np.float64)
    normals = normals.astype(np.float64)
    lap_cache: dict[int, np.ndarray] = {}
    streams = None
    for name, ly in layers.items():
        parts = ly.get("part", "body")
        parts = part_names if parts == "*" else ([parts] if isinstance(parts, str) else parts)
        idx = np.flatnonzero(np.isin(part, [part_names.index(p) for p in parts if p in part_names]))
        if not len(idx):
            if stats is not None:
                stats[name] = None
            continue  # e.g. a close-up that doesn't reach that part
        v, n = verts[idx], normals[idx]
        m = _masks(spec, name, ly, v, n)
        if name.endswith(".L"):
            m = np.maximum(m, _masks(spec, name, ly, v * MIRROR, n * MIRROR))
        if "cavity" in ly:
            if streams is None:
                streams = {ps[0].part: ps for ps in sdf.streams(compile_prims(spec))}
            lap = np.zeros(len(idx))
            for pi in np.unique(part[idx]):
                sel = part[idx] == pi
                k = int(pi)
                if k not in lap_cache:
                    whole = np.flatnonzero(part == pi)
                    lap_cache[k] = np.zeros(len(verts))
                    lap_cache[k][whole] = laplacian(streams[part_names[k]], verts[whole], voxel)
                lap[sel] = lap_cache[k][idx[sel]]
            r0, r1 = ly.get("radius", [0.03, 0.006])
            curv = (-lap if ly["cavity"] == "concave" else lap) / 2  # 1/r on a sphere of radius r
            m = m * _ramp(curv, 1 / r0, 1 / r1)
        m = np.clip(m, 0, 1)
        if stats is not None:
            stats[name] = float((m >= 0.5).mean())
        a = (float(ly.get("opacity", 1.0)) * m)[:, None]
        for c, arr in out.items():
            if c in ly:
                val = colour(ly[c]) if c == "color" else np.array([float(ly[c])])
                arr[idx] += a * (val[None] - arr[idx])
    return out


def laplacian(prims, pts: np.ndarray, voxel: float) -> np.ndarray:
    """Laplacian of the exact field at pts (= 2/r on a sphere of radius r), one 7-point stencil evaluation."""
    from . import sdf
    h = 0.75 * voxel
    st = np.array([[0, 0, 0], [h, 0, 0], [-h, 0, 0], [0, h, 0], [0, -h, 0], [0, 0, h], [0, 0, -h]])
    f = sdf.field_at(prims, pts[:, None, :] + st[None])
    return (f[:, 1:].sum(1) - 6 * f[:, 0]) / (h * h)


def _ramp(x, a, b):
    """0 at a, 1 at b (either order), smooth in between."""
    d = np.asarray(b - a, float)
    t = np.clip((x - a) / np.where(d == 0, 1e-12, d), 0, 1)
    return t * t * (3 - 2 * t)


def _masks(spec: dict, name: str, ly: dict, v: np.ndarray, n: np.ndarray) -> np.ndarray:
    m = np.ones(len(v))
    if "path" in ly:
        m *= _path_mask(spec, name, ly, v, n)
    if "near" in ly:
        m *= _near_mask(spec, name, ly, v)
    if "facing" in ly:
        d = np.asarray(ly["facing"], float)
        lo, hi = ly.get("range", [0.0, 0.7])
        m *= _ramp(n @ (d / np.linalg.norm(d)), lo, hi)
    if "axis" in ly:
        m *= _axis_mask(spec, name, ly["axis"], v)
    if "noise" in ly:
        nz = ly["noise"]
        lo, hi = nz.get("range", [0.45, 0.6])
        m *= _ramp(fbm(v, float(nz.get("scale", 0.03)), int(nz.get("octaves", 3)), int(nz.get("seed", 0))), lo, hi)
    return m


def _axis_mask(spec: dict, name: str, ax: dict, v: np.ndarray) -> np.ndarray:
    if "bone" in ax:
        from .spec import expand_mirror, resolve_point
        s = expand_mirror(spec)
        b = s["bones"].get(ax["bone"])
        if b is None:
            raise SpecError(f"paint {name!r}: unknown bone {ax['bone']!r}")
        a, bb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
        d = bb - a
        t = (v - a) @ d / (d @ d)
        return _ramp(t, float(ax.get("from", 0.0)), float(ax.get("to", 1.0)))
    d = np.asarray(ax.get("dir", [0, 0, 1]), float)
    d = d / np.linalg.norm(d)
    return _ramp(v @ d, float(ax["from"]), float(ax["to"]))


def _near_mask(spec: dict, name: str, ly: dict, v: np.ndarray) -> np.ndarray:
    from . import sdf
    from .spec import compile_prims
    want = [ly["near"]] if isinstance(ly["near"], str) else list(ly["near"])
    prims = {p.name: p for p in compile_prims(spec)}
    for w in list(want):  # a kit name stands for everything it generates (hand.L -> hand_*.L)
        if w in (spec.get("kits") or {}) and w not in prims:
            stem, sfx = (w[:-2], w[-2:]) if w.endswith((".L", ".R")) else (w, "")
            want.remove(w)
            want += [n for n, p in prims.items() if n.startswith(stem + "_") and n.endswith(sfx) and p.kind in sdf.SDF
                     and p.kind != "shell" and p.op == "add"]
    missing = [w for w in want if w not in prims]
    if missing:
        raise SpecError(f"paint {name!r}: no bone or blob {missing} (kit output names are listed by get_model)")
    d = np.full(len(v), np.inf)
    for w in want:
        p = prims[w]
        if p.kind not in sdf.SDF or p.kind == "shell":
            raise SpecError(f"paint {name!r}: {w!r} is a {p.kind}, not a shape")
        d = np.minimum(d, sdf.SDF[p.kind](v, p.params))
    within, soft = float(ly.get("within", 0.0)), float(ly.get("soft", 0.01))
    return 1 - _ramp(d, within, within + max(soft, 1e-6))


def _seated_paths(spec: dict, name: str, ly: dict) -> list[dict]:
    """The layer's path seated on the surface, as stroke samples (pts, nrm, width per sample), one per copy."""
    from . import kits, strokes
    from .spec import geometry
    base = strokes.seat_joints(kits.expand(geometry(spec)))
    base = copy.copy(base)
    base.pop("strokes", None)
    st = {"op": "clay", "path": ly["path"], "width": ly.get("width", 0.01), "depth": 0.001}
    for k in ("repeat", "scatter"):
        if k in ly:
            st[k] = ly[k]
    part = ly.get("part", "body")
    if isinstance(part, str) and part != "*" and part != "body":
        st["part"] = part
    return list(strokes._generate(base, {f"paint:{name}": st})["blobs"].values())


def _path_mask(spec: dict, name: str, ly: dict, v: np.ndarray, n: np.ndarray) -> np.ndarray:
    from scipy.spatial import cKDTree
    from .sdf import PROFILES
    from .spec import _profile_norm
    prof_name = ly.get("profile", "flat")
    if prof_name not in PROFILES:
        raise SpecError(f"paint {name!r}: unknown profile {prof_name!r} (have {', '.join(PROFILES)})")
    prof = PROFILES[prof_name][0]
    out = np.zeros(len(v))
    for bl in _seated_paths(spec, name, ly):
        P, N, W = (np.asarray(bl[k], float) for k in ("pts", "nrm", "width"))
        N = N / np.linalg.norm(N, axis=1, keepdims=True)
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1) if len(P) > 1 else np.zeros(0)
        ds = np.concatenate([seg, [0.0]]) / 2 + np.concatenate([[0.0], seg]) / 2
        gain = ds / (W * _profile_norm(prof_name)) if len(P) > 1 else np.ones(1)
        reach = np.maximum(W, 0.02)  # along the normal: covers what strokes pushed in or out
        R = float(np.hypot(W.max(), 2 * reach.max()))
        step = float(ds[ds > 0].min()) if (ds > 0).any() else 1.0
        K = int(min(len(P), 2 * W.max() / step + 4))
        box = np.all((v >= P.min(0) - R) & (v <= P.max(0) + R), axis=1)
        sel = np.flatnonzero(box)
        if not len(sel):
            continue
        q = v[sel]
        dist, idx = cKDTree(P).query(q, k=K, distance_upper_bound=R)
        idx = idx.reshape(len(q), K)
        ok = idx < len(P)
        j = np.where(ok, idx, 0)
        r = q[:, None, :] - P[j]
        h = (r * N[j]).sum(-1)
        lat = np.sqrt(np.maximum((r * r).sum(-1) - h * h, 0.0)) / W[j]
        k = np.where(ok & (lat < 1.0), prof(np.minimum(lat, 1.0)), 0.0)
        k *= 1 - _ramp(np.abs(h), reach[j], 2 * reach[j])
        k *= _ramp((n[sel][:, None, :] * N[j]).sum(-1), 0.0, 0.3)  # skin facing the path's way: no print-through
        out[sel] = np.maximum(out[sel], np.clip((k * gain[j]).sum(1), 0, 1))
    return out


def _hash(ix, iy, iz, seed: int) -> np.ndarray:
    """Pseudo-random 0..1 per integer lattice point."""
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h = h.astype(np.uint64)
    h ^= h >> np.uint64(13)
    h *= np.uint64(0x5bd1e995)
    h ^= h >> np.uint64(15)
    return (h & np.uint64(0xFFFFFF)).astype(np.float64) / float(0xFFFFFF)


def _value_noise(p: np.ndarray, seed: int) -> np.ndarray:
    i = np.floor(p).astype(np.int64)
    f = p - i
    u = f * f * f * (f * (f * 6 - 15) + 10)  # quintic fade: no creases at lattice planes
    out = np.zeros(len(p))
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (np.where(dx, u[:, 0], 1 - u[:, 0]) * np.where(dy, u[:, 1], 1 - u[:, 1])
                     * np.where(dz, u[:, 2], 1 - u[:, 2]))
                out += w * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
    return out


def _rotations(n: int) -> list[np.ndarray]:
    rng = np.random.default_rng(7)
    out = []
    for _ in range(n):
        q, r = np.linalg.qr(rng.normal(size=(3, 3)))
        out.append(q * np.sign(np.diag(r)))
    return out


_ROT = _rotations(8)


def fbm(p: np.ndarray, scale: float, octaves: int = 3, seed: int = 0) -> np.ndarray:
    """Fractal value noise in 0..1 (mean ~0.5) with features about `scale` across."""
    out, amp, total = np.zeros(len(p)), 1.0, 0.0
    q = p / scale
    for o in range(max(1, octaves)):  # each octave on its own rotated lattice: no axis-aligned blocks
        out += amp * _value_noise(q @ _ROT[o % len(_ROT)] * (2 ** o), seed + 101 * o)
        total += amp
        amp *= 0.5
    # summed octaves bunch up around 0.5; stretch back to roughly 0..1
    return np.clip(0.5 + (out / total - 0.5) * (1.0 + 0.6 * (octaves - 1)), 0, 1)


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
