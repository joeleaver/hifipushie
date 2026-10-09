"""A sward: plain grass as ground cover, built as a TILE of blades, not a tuft.

Why: tufts with seed heads scattered on a grid read as tufts on a grid over bare ground, not as a field of grass
(the user on the groundcover meadow: "what about just grass?"). What engines do for a field: blades, not clumps.
Ghost of Tsushima draws ~100k GPU-generated blades (a Bezier ribbon each, 15 vertices near, 7 far) in tiles round
the camera, thinned and widened with distance, and past the grass distance the TERRAIN's own grass texture takes
over in the same colour (Wohllaib, "Procedural Grass in Ghost of Tsushima", GDC 2021); BotW / Genshin instance single
blades the same way. Card patches (rows of alpha-tested quads with blades painted on) are the older way: cheap in
vertices, dear in overdraw and they shimmer or vanish through mipmaps (veg_groundcover's finding). Here, for an
engine that takes meshes: a tile `size` m square of opaque blade ribbons (no alpha, MSAA does the edges), LODs by
fewer / wider / simpler blades, and numbers for the fade into the terrain texture.

- Tileable: blade roots are jittered on a torus and every variation (height, lean direction, tone, clumping) is
  periodic noise over the tile, so tiles laid edge to edge (any 90 deg turn) show no seam and no grid. Blades lean
  out over the tile's edge into the neighbour (geometry needs no wrap; the neighbour's blades lean in the same way).
- A blade: a ribbon along a curve whose angle from the vertical grows from `lean` at the root by `bend` to the tip,
  `segs` quads tapering to a point (or a rounded end), width across the lean; normal = up mixed with the blade's own
  face (the ground's light: lit by their faces alone blades flicker), bent across the width by `round` (reads as a
  fat blade without geometry). COLOR_0 = root colour -> tip colour up the blade x a tone per blade (linear).
- LODs (`lods`: [share of the blades, width x, segments]): LOD k's blades are a subset of LOD k-1's (ranked by hash),
  wider so the covered ground stays about the same. Past `fade` [start, end] m the engine shrinks the blades into the
  ground (a vertex-shader line, recipe in the extras) over the terrain's grass texture; root colour = the terrain
  style's grass colour for the cover kind (mown / rough), so nothing steps where the grass ends.
- Variants (`variant`): mown (short, dense, upright), meadow (ankle to shin, leaning in drifts), rough (long, coarse,
  straw mixed in, tussocky). Styles: sheet block `sward` (blade width / density / height multipliers, tone steps,
  round tips, tufts of blades fanned from one root, colour through the sheet's `colour`).
- Wind: TEXCOORD_1 = (trunk, branch) = height up the blade (^1.5; branch scaled by the blade's length as small
  plants), TEXCOORD_2 = (phase from a slow noise over the tile so gusts run through it, flutter)."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

VERSION = 2
LOD_BAND = 0.25   # the share of the blades still drawn that are part-way into the ground (the per-blade dither's width)
# what a blade of each cover kind is (m, per m2, deg); colours sRGB: `ground` = the terrain's grass texture under it
VARIANTS = {
    "mown": {"height": [0.035, 0.06], "density": 1100, "width": 0.011, "lean": [0, 22], "bend": 25, "drift": 0.25, "clump": 0.15,
             "dry": 0.02, "ground": [0.20, 0.40, 0.13], "tip": [0.34, 0.56, 0.2], "fade": [18, 30],
             "lods": [[1.0, 1.0, 2], [0.4, 2.5, 1], [0.2, 5.0, 1], [0.05, 20.0, 1]], "rings": [5, 10, 18]},  # (short blades: two segments, tight rings)
    "meadow": {"height": [0.14, 0.3], "density": 520, "width": 0.012, "lean": [4, 30], "bend": 55, "drift": 0.6, "clump": 0.35,
               "dry": 0.06, "ground": [0.27, 0.42, 0.15], "tip": [0.47, 0.6, 0.24], "fade": [40, 60]},
    "rough": {"height": [0.22, 0.55], "density": 380, "width": 0.014, "lean": [6, 38], "bend": 75, "drift": 0.7, "clump": 0.6,
              "dry": 0.22, "ground": [0.30, 0.43, 0.17], "tip": [0.56, 0.6, 0.3], "fade": [50, 75]},
}
SWARD = {"variant": "meadow", "size": 2.0, "two_faces": True, "taper": 1.6, "tone": [0.82, 1.15], "tone_size": 0.5, "drift_size": 1.0, "clump_size": 0.4,
         "straw": [0.66, 0.6, 0.36], "up": 0.45, "round": 0.35, "root_dark": 0.8, "gradient": 1.2,
         "lods": [[1.0, 1.0, 3], [0.4, 2.5, 2], [0.2, 5.0, 1], [0.05, 20.0, 1]], "rings": [5, 12, 24], "roughness": 0.85}
# a style's way with blades (sheet block `sward`): multipliers on the realistic numbers + how a blade is drawn
STYLE = {"width": 1.0, "density": 1.0, "height": 1.0, "bend": 1.0, "tones": 0, "tip": "point", "tuft": 1, "tuft_fan": 20,
         "round": None, "dry": 1.0, "tip_light": 1.0, "taper": None, "drift": 1.0}
SEASONS = {"summer": [1.0, 1.0, 1.0], "spring": [0.9, 1.1, 0.75], "autumn": [1.25, 1.02, 0.7], "winter": [1.2, 0.92, 0.62],
           "snow": [1.75, 1.8, 2.1]}  # the foliage factor against summer (linear multipliers; snow toward white)
KEYS = set(SWARD) | set(VARIANTS["meadow"]) | {"rings"}


def params(spec: dict) -> dict:
    """The sward's numbers: defaults < variant < the spec's own `sward` keys, then the style's multipliers."""
    from . import veg_style
    own = dict(spec.get("sward") or {})
    bad = set(own) - KEYS
    if bad:
        raise ValueError(f"unknown sward keys {sorted(bad)}; known: {sorted(KEYS)}")
    var = own.get("variant", SWARD["variant"])
    if var not in VARIANTS:
        raise ValueError(f"sward variant {var!r}: one of {sorted(VARIANTS)}")
    p = {**SWARD, **VARIANTS[var], **own}
    st = veg_style.sheet(spec)
    sw = {**STYLE, **((st or {}).get("sward") or {})}
    bad = set(sw) - set(STYLE)
    if bad:
        raise ValueError(f"unknown style sward keys {sorted(bad)}; known: {sorted(STYLE)}")
    p["style"] = sw
    p["style_name"] = st["name"] if st else "realistic"
    co = (st or {}).get("colour") or {}
    for k in ("ground", "tip", "straw"):  # (the terrain's own style turns its grass colour by saturation / value too)
        p[k] = veg_style.styled(p[k], co.get("saturation", 1.0), co.get("value", 1.0)) if st else list(p[k])
    p["height"] = [h * sw["height"] for h in p["height"]]
    p["width"] = p["width"] * sw["width"]
    p["density"] = p["density"] * sw["density"]
    p["bend"] = p["bend"] * sw["bend"]
    p["dry"] = p["dry"] * sw["dry"]
    p["drift"] = p["drift"] * sw["drift"]
    if sw["round"] is not None:
        p["round"] = sw["round"]
    if sw["taper"] is not None:
        p["taper"] = sw["taper"]
    return p


def validate(spec: dict):
    params(spec)


def _hash(a, salt: int) -> np.ndarray:
    x = (np.asarray(a, np.uint64) + np.uint64(salt * 0x9E3779B97F4A7C15 % (1 << 64))) * np.uint64(0xBF58476D1CE4E5B9)
    x ^= x >> np.uint64(31)
    x *= np.uint64(0x94D049BB133111EB)
    x ^= x >> np.uint64(29)
    return (x >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def tile_noise(xy: np.ndarray, size: float, cell: float, seed: int) -> np.ndarray:
    """Smooth value noise in 0..1, periodic over the tile (cells = a whole number across it)."""
    n = max(1, int(round(size / cell)))
    g = xy / size * n
    i = np.floor(g).astype(np.int64)
    f = g - i
    f = f * f * (3 - 2 * f)
    v = lambda dx, dy: _hash(((i[:, 0] + dx) % n) * 7919 + ((i[:, 1] + dy) % n) * 104729 + seed * 15485863, 3)
    return (v(0, 0) * (1 - f[:, 0]) + v(1, 0) * f[:, 0]) * (1 - f[:, 1]) + (v(0, 1) * (1 - f[:, 0]) + v(1, 1) * f[:, 0]) * f[:, 1]


def blades(spec: dict) -> dict:
    """Every blade of the tile (LOD 0's): root, height, width, yaw (the way it leans), lean, bend (rad), tone, dry,
    rank (0..1: LOD k keeps rank < its share), phase, tuft."""
    p = params(spec)
    seed = int(spec.get("seed", 1))
    S = float(p["size"])
    sw = p["style"]
    tuft = max(1, int(sw["tuft"]))
    n_root = max(1, int(round(p["density"] * S * S / tuft)))
    g = int(np.ceil(np.sqrt(n_root)))
    idx = np.arange(g * g)
    keep = np.argsort(_hash(idx + seed * 1000003, 1))[:n_root]  # (a jittered grid on the torus, thinned to the count)
    cx, cy = keep % g, keep // g
    root = np.c_[(cx + _hash(keep + seed * 31, 5)) / g, (cy + _hash(keep + seed * 31, 6)) / g] * S
    # clumping: roots drawn toward where a periodic noise is high (thin there, bare never: the ground shows through gaps)
    dens = tile_noise(root, S, p["clump_size"], seed + 11)
    live = _hash(keep + seed * 77, 9) < (1 - p["clump"]) + p["clump"] * np.clip(dens * 1.6, 0, 1)
    root, keep = root[live], keep[live]
    if tuft > 1:
        root = np.repeat(root, tuft, 0) + (np.c_[_hash(np.arange(len(root) * tuft) + seed, 21), _hash(np.arange(len(root) * tuft) + seed, 22)] - 0.5) * 0.012
        base = np.repeat(keep, tuft) * 16 + np.tile(np.arange(tuft), len(keep))
        fan = (np.tile(np.arange(tuft), len(keep)) - (tuft - 1) / 2) / max(tuft - 1, 1)
    else:
        base, fan = keep * 16, np.zeros(len(keep))
    n = len(root)
    u = lambda k: _hash(base + seed * 131, k)
    tall = 0.55 * tile_noise(root, S, p["clump_size"], seed + 12) + 0.45 * u(31)
    h = p["height"][0] + (p["height"][1] - p["height"][0]) * tall
    # the way blades lean drifts across the tile (wind-combed drifts), each blade off it by its own share
    da = tile_noise(root, S, p["drift_size"], seed + 13) * 4 * np.pi
    yaw = np.where(u(32) < p["drift"], da + (u(33) - 0.5) * 1.2, u(34) * 2 * np.pi) + np.radians(sw["tuft_fan"]) * fan * 2
    lean = np.radians(p["lean"][0] + (p["lean"][1] - p["lean"][0]) * u(35) ** 1.3) + np.abs(fan) * np.radians(sw["tuft_fan"])
    bend = np.radians(p["bend"]) * (0.5 + u(36)) * np.clip(h / max(p["height"][1], 1e-6), 0.4, 1.0)
    tone = p["tone"][0] + (p["tone"][1] - p["tone"][0]) * (0.6 * tile_noise(root, S, p["tone_size"], seed + 14) + 0.4 * u(37))
    return {"root": root, "h": h, "w": p["width"] * (0.75 + 0.5 * u(38)), "yaw": yaw, "lean": lean, "bend": bend, "tone": tone,
            "dry": u(39) < p["dry"], "rank": u(40) if tuft == 1 else np.repeat(_hash(keep + seed * 131, 40), tuft),
            "phase": tile_noise(root, S, 0.5 * S, seed + 15), "id": u(41), "p": p, "n": n}


def mesh(B: dict, share: float = 1.0, widen: float = 1.0, segs: int = 3) -> dict:
    """The tile's blades as one mesh: V (z up, the tile's corner at the origin), F, N, uv (across, along), col (linear
    rgb), grad (along 0..1, blade id), wind (trunk, branch, phase, flutter), across (the vertex's offset from its blade's
    centre line, plan x y, m), lodv (the blade's rank 0..1, this mesh's width multiple): what the LOD recipe reads."""
    from .veg_style import lin
    p = B["p"]
    sw = p["style"]
    sel = np.nonzero(B["rank"] < share)[0]
    n = len(sel)
    rnd = sw["tip"] == "round"
    rings = segs + (1 if rnd else 0)  # rings of two vertices; a pointed blade ends in one vertex, a round one in a short ring
    t = np.linspace(0, 1, segs + 1)
    h, w = B["h"][sel], B["w"][sel] * widen
    yaw, lean, bend = B["yaw"][sel], B["lean"][sel], B["bend"][sel]
    # the centre line: the angle from the vertical grows from lean by bend x t; integrated in `fine` steps
    fine = 12
    tf = (np.arange(fine * segs + 1)) / (fine * segs)
    ang = lean[:, None] + bend[:, None] * tf[None] ** 1.5
    ds = h[:, None] / (fine * segs)
    out = np.concatenate([np.zeros((n, 1)), np.cumsum(np.sin(ang[:, :-1]) * ds, 1)], 1)[:, ::fine]
    up = np.concatenate([np.zeros((n, 1)), np.cumsum(np.cos(ang[:, :-1]) * ds, 1)], 1)[:, ::fine]
    angk = ang[:, ::fine]
    d = np.c_[np.cos(yaw), np.sin(yaw)]          # the way it leans, in plan
    side = np.c_[-np.sin(yaw), np.cos(yaw)]      # across the blade
    if rnd:
        wt = np.sqrt(np.clip(1 - t ** 3.0, 0, 1))
        wt[-1] = 0.45
    else:
        wt = 1 - t ** p["taper"]
    wt = np.maximum(wt, 0.0)
    Vs, Ns, Us, Cs, Gs, Ws, Fn, As, Ls = [], [], [], [], [], [], [], [], []
    root3 = np.c_[B["root"][sel], np.zeros(n)]
    cg, ct, cs = np.array(lin(p["ground"])) * p["root_dark"], np.array(lin(p["tip"])) * sw["tip_light"], np.array(lin(p["straw"]))
    tones = int(sw["tones"])
    tone = B["tone"][sel]
    if tones:
        tone = p["tone"][0] + (p["tone"][1] - p["tone"][0]) * (np.floor((tone - p["tone"][0]) / max(p["tone"][1] - p["tone"][0], 1e-9) * tones).clip(0, tones - 1) + 0.5) / tones
    dry = B["dry"][sel]
    lenk = float(np.clip(np.median(h) / 1.2, 0.08, 1.0)) if n else 0.1
    for k in range(segs + 1):
        c3 = root3 + np.c_[d * out[:, k:k + 1], up[:, k]]
        # the blade's own face normal (square to its centre line, in the lean's plane, on its upper side)
        face = np.c_[-d * np.cos(angk[:, k:k + 1]), np.sin(angk[:, k])]
        g = t[k] ** p["gradient"]
        gq = (np.floor(g * tones).clip(0, tones - 1) + 0.5) / tones if tones else g
        col = (cg[None] * (1 - gq) + np.where(dry[:, None], cs[None], ct[None]) * gq) * tone[:, None]
        if k == segs and not rnd:
            pts = [(c3, 0.0, 0.5, np.zeros((n, 2)))]
        else:
            hw = 0.5 * w[:, None] * wt[k]
            pts = [(c3 - np.c_[side * hw, np.zeros(n)], -1.0, 0.0, -side * hw), (c3 + np.c_[side * hw, np.zeros(n)], 1.0, 1.0, side * hw)]
        for P, sgn, uu, acr in pts:
            N = p["up"] * np.array([0, 0, 1.0])[None] + (1 - p["up"]) * face + sgn * p["round"] * np.c_[side, np.zeros(n)]
            N /= np.linalg.norm(N, axis=1, keepdims=True)
            Vs.append(P)
            Ns.append(N)
            Fn.append(face)
            As.append(acr)
            Ls.append(np.c_[B["rank"][sel], np.full(n, widen)])
            Us.append(np.c_[np.full(n, uu), np.full(n, t[k])])
            Cs.append(col)
            Gs.append(np.c_[np.full(n, t[k]), B["id"][sel]])
            Ws.append(np.c_[np.full(n, t[k] ** 1.5 * np.clip(h / max(p["height"][1], 1e-6), 0.3, 1.0)), np.full(n, t[k] ** 1.5 * lenk) * (h / max(np.median(h), 1e-6)).clip(0.5, 1.6),
                            B["phase"][sel], np.full(n, 0.5 * t[k])])
    per = len(Vs)  # vertices a blade, laid ring by ring: vertex j of blade i = j * n + i
    F = []
    i = np.arange(n)
    for k in range(segs):
        a, b = (2 * k) * n + i, (2 * k + 1) * n + i
        if k == segs - 1 and not rnd:
            F.append(np.c_[a, (2 * segs) * n + i, b])  # (wound so the blade's UPPER face is the front)
        else:
            c, e = (2 * k + 2) * n + i, (2 * k + 3) * n + i
            F += [np.c_[a, e, b], np.c_[a, c, e]]
    V, F, N = np.vstack(Vs), (np.vstack(F) if n else np.zeros((0, 3), np.int64)), np.vstack(Ns)
    arr = [np.vstack(x_) for x_ in (Us, Cs, Gs, Ws, As, Ls)]
    if p["two_faces"]:  # the underside as triangles of its own with the SAME normals (single-sided material): a double-sided
        # material's back faces get their normal flipped by the engine (Godot does), and an up-leaning normal flipped is
        # black grass wherever a blade shows its underside
        F = np.vstack([F, F[:, ::-1] + len(V)])
        fn = np.vstack(Fn)
        Nb = N - 2 * (N * fn).sum(1, keepdims=True) * fn  # (the underside's normal: the upper side's mirrored through the blade)
        Nb[:, 2] = np.abs(Nb[:, 2])
        Nb /= np.linalg.norm(Nb, axis=1, keepdims=True)
        V, N = np.vstack([V, V]), np.vstack([N, Nb])
        arr = [np.vstack([x_, x_]) for x_ in arr]
    return {"V": V, "F": F, "N": N, "uv": arr[0], "col": arr[1], "grad": arr[2], "wind": arr[3], "across": arr[4], "lodv": arr[5],
            "blades": n, "verts_per_blade": per}


def build(spec: dict) -> dict:
    """{"p", "blades", "lods": [mesh per LOD], "info": [per LOD: blades, triangles, triangles_per_m2]}."""
    B = blades(spec)
    p = B["p"]
    lods, info = [], []
    for li, (share, widen, segs) in enumerate(p["lods"]):
        M = mesh(B, float(share), float(widen), int(segs))
        lods.append(M)
        info.append({"lod": li, "blades": int(M["blades"]), "triangles": int(len(M["F"])),
                     "triangles_per_m2": round(len(M["F"]) / p["size"] ** 2, 1), "width_x": widen, "segments": segs, "kind": "sward"})
    return {"p": p, "blades": B, "lods": lods, "info": info}


def grow(spec: dict) -> dict:
    """What vegetation.grow hands back for plant "sward": no skeleton, the built tile + numbers for the report."""
    b = build(spec)
    p = b["p"]
    H = float(max((M["V"][:, 2].max() if len(M["V"]) else 0.0) for M in b["lods"]))
    return {"sward": True, "spec": spec, "built": b, "height": H, "pos": np.zeros((2, 3)), "stats": {"nodes": int(b["info"][0]["blades"]), "height_m": round(H, 3), "blades": b["info"][0]["blades"]}}


FADE_RECIPE = ("past fade.start m from the camera shrink the blades into the ground and stop drawing the tile at fade.end: in the "
               "vertex shader, f = 1 - smoothstep(start, end, distance(camera, tile vertex)); VERTEX.y *= f (the tile's ground "
               "is y = 0 in its own space; do it before the wind). The LOOK goes to the ground's over a longer run, so no "
               "brightness step shows where the grass ends: g = 1 - smoothstep(fade.blend_from, end, distance); in the fragment "
               "shader albedo = mix(terrain grass colour, albedo, g), NORMAL = normalize(mix(the ground's normal, NORMAL, g)) and "
               "ROUGHNESS = mix(the ground's, roughness, g) (a blade lit by its own normal is lighter than flat ground of the "
               "same colour, and a style with specular shows the roughness as a sheen: both made an arc where the field "
               "ended). Under the tiles draw the terrain's grass "
               "texture; `ground_linear` is the colour the blades were made for (the terrain style's grass colour for this cover "
               "kind; a field of them averages to it): an engine may multiply COLOR_0 by (its terrain's grass colour there / "
               "ground_linear) so the sward follows the terrain's patches.")
PLACE_RECIPE = ("a TILE, not a clump: lay tiles edge to edge on a size_m grid (each turned by a random multiple of 90 deg about "
                "its middle: every variation is periodic over the tile); no random scale, no gaps. Mesh LOD k for a tile whose "
                "NEAREST point is at least lod.dist[k] m away (distance to its middle - 0.71 x tile_m), LOD 0 inside.")
LOD_RECIPE = ("the meshes only bound the vertex count; what is DRAWN thins per blade with distance, so no ring or tile edge shows. "
              "Per vertex: TEXCOORD_4 = across (its offset from the blade's centre line, model x, z, m), TEXCOORD_5 = (rank 0..1, "
              "width multiple of this mesh) (Godot: CUSTOM1.xy, CUSTOM1.zw). Vertex shader, d = distance(camera, vertex): "
              "S(d) = lod.share interpolated in log over lod.dist (share[0] up to dist[0], share[k] at dist[k], flat past the "
              "last); lo = S - max(1e-4, band * S * clamp((1 - S) * 8, 0, 1)); vis = 1 - smoothstep(lo, S, rank); "
              "VERTEX.xz += across * (vis / (S * width_multiple * (1 - 0.5 * (S - lo) / S)) - 1); VERTEX.y *= vis. A blade of "
              "rank r shrinks into the ground as S(d) passes r and the blades left widen (drawn share x width stays 1): LOD k's "
              "mesh at dist[k] draws exactly what LOD k - 1's draws there.")
RENDERER = ["1. Load <name>_LOD0..3.glb once; one MultiMesh (instanced draw) per LOD, no shadows cast (receive them).",
            "2. Grid: cells of tile_m on the terrain, anchored in the world (cell = floor(xz / tile_m)); a cell is grass where the "
            "terrain's cover says so (this sward's variant: mown / meadow / rough). Instance transform = the cell's middle on the "
            "ground, yaw = hash(cell) % 4 x 90 deg, scale 1. On a slope either tilt the tile to the ground's normal or sample the "
            "terrain height per vertex in the shader (VERTEX.y += height(world xz)): tiles are flat.",
            "3. Each time the camera has moved about a tile: for every grass cell within fade.end of the camera, near = max("
            "distance(camera, cell middle) - 0.71 x tile_m, 0); LOD k = the number of lod.dist[1..3] that near has reached "
            "(LOD 0 inside lod.dist[1]); skip cells outside the view frustum.",
            "4. Vertex shader, in this order: the per-blade LOD (lod.recipe), the fade (fade_recipe), the wind (wind).",
            "5. Fragment: albedo = baseColorFactor (the season's, from `seasons`) x COLOR_0 x color_gain, then the fade's mix to "
            "the terrain grass colour; opaque, cull back (undersides are their own triangles); no texture.",
            "6. Under and beyond the tiles the terrain draws its own grass texture; ground_linear is the colour these blades "
            "were made to stand on."]
WIND_NOTE = ("opaque geometry: no alpha, no texture, no mipmaps to set up (MSAA does the edges). Wind as every plant's recipe: "
             "TEXCOORD_1 = (trunk, branch) = height up the blade ^ 1.5, TEXCOORD_2 = (phase, flutter); the phase is a slow "
             "noise over the tile, so add a WORLD term to it (e.g. dot(world xz, wind direction) * 0.15 - time * speed) for "
             "gusts that run across tiles; apply after the LOD and fade lines.")


def write_glb(path: str, name: str, b: dict, seasons, which=None) -> dict:
    """A GLB of the tile's LODs (`which`; None = all, LOD 0 the scene + MSFT_lod): one mesh a LOD, slot `foliage`
    (opaque, double sided, no texture: albedo = baseColorFactor per season variant x COLOR_0)."""
    from . import veg_export, veg_style
    p = b["p"]
    which = list(range(len(b["lods"]))) if which is None else list(which)
    buf = bytearray()
    views, accessors, materials, meshes, nodes = [], [], [], [], []

    def acc(a, kind, comp, target, minmax=False):
        a = np.ascontiguousarray(a)
        while len(buf) % 4:
            buf.append(0)
        views.append({"buffer": 0, "byteOffset": len(buf), "byteLength": a.nbytes, "target": target})
        buf.extend(a.tobytes())
        d = {"bufferView": len(views) - 1, "componentType": comp, "count": int(len(a)), "type": kind}
        if minmax:
            d["min"], d["max"] = a.min(0).tolist(), a.max(0).tolist()
        accessors.append(d)
        return len(accessors) - 1

    seasons = list(seasons)
    gain = max(1.0, max(float(M["col"].max()) if len(M["col"]) else 1.0 for M in b["lods"]))  # (COLOR_0 must stay <= 1)
    var_mat = {}
    for se in seasons:
        f = np.array(SEASONS[se]) * gain
        ext = {"grade": "sward"}
        if f.max() > 1:  # (a factor over 1 is not glTF: the rest rides in the extras for engines that take it)
            ext["factor_over_one"] = [round(float(x), 4) for x in f]
        materials.append({"name": "foliage" if se == seasons[0] else f"foliage_{se}",
                          "pbrMetallicRoughness": {"baseColorFactor": [*np.clip(f / max(1.0, f.max()), 0, 1).tolist(), 1.0], "metallicFactor": 0.0,
                                                   "roughnessFactor": float(p["roughness"])},
                          "doubleSided": not p["two_faces"], "extras": ext})
        var_mat[se] = len(materials) - 1
    y = lambda v_: np.stack([v_[:, 0], v_[:, 2], -v_[:, 1]], 1)
    lod_nodes, lod_info = [], []
    S = p["size"]
    for li in which:
        M = b["lods"][li]
        V = M["V"] - np.array([S / 2, S / 2, 0.0])  # (the tile's middle at the origin)
        at = {"POSITION": acc(y(V).astype(np.float32), "VEC3", 5126, 34962, minmax=True),
              "NORMAL": acc(y(M["N"]).astype(np.float32), "VEC3", 5126, 34962),
              "TEXCOORD_0": acc(M["uv"].astype(np.float32), "VEC2", 5126, 34962),
              "TEXCOORD_1": acc(M["wind"][:, :2].astype(np.float32), "VEC2", 5126, 34962),
              "TEXCOORD_2": acc(M["wind"][:, 2:].astype(np.float32), "VEC2", 5126, 34962),
              "TEXCOORD_3": acc(M["grad"].astype(np.float32), "VEC2", 5126, 34962),
              "TEXCOORD_4": acc(np.c_[M["across"][:, 0], -M["across"][:, 1]].astype(np.float32), "VEC2", 5126, 34962),  # (glTF x, z)
              "TEXCOORD_5": acc(M["lodv"].astype(np.float32), "VEC2", 5126, 34962),
              "_WIND": acc(M["wind"].astype(np.float32), "VEC4", 5126, 34962),
              "COLOR_0": acc(np.c_[np.clip(M["col"] / gain, 0, 1), np.ones(len(M["col"]))].astype(np.float32), "VEC4", 5126, 34962)}
        pr = {"attributes": at, "indices": acc(M["F"].astype(np.uint32).ravel(), "SCALAR", 5125, 34963), "material": var_mat[seasons[0]],
              "extensions": {"KHR_materials_variants": {"mappings": [{"material": var_mat[se], "variants": [i]} for i, se in enumerate(seasons)]}}}
        pre = f"LOD{li}_" if len(which) > 1 else ""
        meshes.append({"name": pre + "foliage", "primitives": [pr]})
        nodes.append({"name": pre + "foliage", "mesh": len(meshes) - 1})
        if len(which) > 1:
            nodes.append({"name": f"{name}_LOD{li}", "children": [len(nodes) - 1]})
        lod_nodes.append(len(nodes) - 1)
        lod_info.append(b["info"][li])
    used = ["KHR_materials_variants"]
    if len(lod_nodes) > 1:
        used.append("MSFT_lod")
        nodes[lod_nodes[0]]["extensions"] = {"MSFT_lod": {"ids": lod_nodes[1:]}}
    while len(buf) % 4:
        buf.append(0)
    sward = {"tile_m": S, "variant": p["variant"], "fade": {"start": p["fade"][0], "end": p["fade"][1], "blend_from": float(p["rings"][-2])},
             "ground_srgb": p["ground"], "ground_linear": [round(c, 4) for c in veg_style.lin(p["ground"])],
             "root_linear": [round(c * p["root_dark"], 4) for c in veg_style.lin(p["ground"])],
             "tip_linear": [round(c, 4) for c in veg_style.lin(p["tip"])], "color_gain": round(gain, 4),
             "blades_per_m2": round(b["info"][0]["blades"] / S ** 2, 1), "lod_rings_m": list(p["rings"]),
             "lod": {"dist": [round(0.5 * p["rings"][0], 2), *[float(r) for r in p["rings"]]], "share": [float(l_[0]) for l_ in p["lods"]],
                     "band": LOD_BAND, "recipe": LOD_RECIPE},
             "fade_recipe": FADE_RECIPE, "place": PLACE_RECIPE, "wind": WIND_NOTE, "renderer": RENDERER,
             "ground_roughness": 1.0}
    gltf = {"asset": {"version": "2.0", "generator": "hifipushie vegetation (sward)"}, "scene": 0, "scenes": [{"nodes": [lod_nodes[0]]}],
            "nodes": nodes, "meshes": meshes, "materials": materials, "accessors": accessors, "bufferViews": views,
            "buffers": [{"byteLength": len(buf)}], "extensionsUsed": sorted(used),
            "extensions": {"KHR_materials_variants": {"variants": [{"name": v_} for v_ in seasons]}},
            "extras": {"hifipushie_plant": {"name": name, "species": "sward", "grade": "sward", "height_m": round(float(max(M["V"][:, 2].max() for M in b["lods"])), 3),
                                            "lods": lod_info, "wind": veg_export.WIND_RECIPE, "variants": seasons, "contract": veg_export.CONTRACT,
                                            "style": {"name": p["style_name"], "kind": "sward blades"}, "sward": sward,
                                            "snow_numbers": veg_export.snow_numbers({}, None)}}}
    js = json.dumps(gltf, separators=(",", ":"), default=float).encode()
    js += b" " * (-len(js) % 4)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(buf)))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(buf), b"BIN\0"))
        f.write(bytes(buf))
    return {"path": str(out), "bytes": out.stat().st_size, "lods": lod_info, "sward": sward}


def export(T: dict, out_dir: str, stem: str, seasons=("summer", "spring", "autumn", "winter", "snow")) -> dict:
    """<stem>.glb (all LODs), <stem>_LOD<k>.glb, <stem>_seasons.json (+ the `sward` numbers in it)."""
    from . import veg_export
    b = T["built"]
    out = Path(out_dir)
    full = write_glb(str(out / f"{stem}.glb"), stem, b, seasons)
    files = [full["path"]]
    for li in range(len(b["lods"])):
        files.append(write_glb(str(out / f"{stem}_LOD{li}.glb"), stem, b, seasons, which=[li])["path"])
    sj = veg_export.seasons_json(full["path"])
    if sj:
        d = json.loads(Path(sj["path"]).read_text())
        d["sward"] = full["sward"]
        Path(sj["path"]).write_text(json.dumps(d, indent=1))
        files.append(sj["path"])
    return {"path": full["path"], "files": files, "lods": full["lods"], "sward": full["sward"], "bytes": full["bytes"],
            "seasons_file": sj["path"] if sj else None}


def report(name: str, T: dict) -> str:
    b = T["built"]
    p = b["p"]
    out = [f"plant {name}: a sward (plain grass as a {p['size']:g} m tile of blades), variant {p['variant']}, style {p['style_name']}",
           f"blades: {b['info'][0]['blades']} ({b['info'][0]['blades'] / p['size'] ** 2:.0f} per m2), {p['height'][0] * 100:.0f}-{p['height'][1] * 100:.0f} cm tall, "
           f"{p['width'] * 1000:.0f} mm wide, lean {p['lean'][0]}-{p['lean'][1]} deg, bend {p['bend']:.0f} deg; tallest point {T['height']:.2f} m"]
    for i in b["info"]:
        out.append(f"LOD {i['lod']}: {i['blades']} blades x {i['segments']} segments, width x{i['width_x']:g}: {i['triangles']} triangles "
                   f"({i['triangles_per_m2']:.0f} per m2)")
    out.append(f"fade into the terrain's grass texture {p['fade'][0]}-{p['fade'][1]} m; root colour = the terrain grass {p['ground']} (sRGB), tip {p['tip']}")
    out.append("place: tiles edge to edge on a grid, random quarter turns; judge in an engine (spikes/godot_veg/sward.gd), not as one tile")
    return "\n".join(out)
