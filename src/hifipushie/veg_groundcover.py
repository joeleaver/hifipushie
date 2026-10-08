"""Groundcover grade: a small plant (a clump: grass, daisy, clover, fern...) as a few alpha cards for scatter.

Why: a game scatters thousands of clumps round the player (pushieworld: a 0.9 m grid within 32 m, note 102). The
full small plant costs 270-4,750 triangles at LOD 0 (pixar grass is lush thin blades), so a meadow was 6.5 M
triangles, or thinned until it looked sparse. What game artists do for scatter: the clump is built (or sculpted,
or scanned) once at full detail and BAKED into an atlas, then drawn as a handful of cards (SpeedTree's and
Megascans' grass "billboard" LODs; Ghost of Tsushima / Horizon's grass blades are GPU geometry, but their small
plants and flowers are cards). Here the bake is the plant exactly as the full export draws it, in its style, per
season, so every style reads as itself.

How (one tier per LOD, `TIERS`): `planes` vertical cards through the clump's foot at equal angles (a star). Card k
shows only what stands in its own double wedge round the vertical axis (azimuth within 90 / planes deg of the card's
line: blender_vegetation's `sector` cut on the pass materials), seen square on, so every blade is drawn ONCE, on the
card nearest to where it really is (crossed cards that each show the whole clump draw it `planes` times: too dense,
and every blade doubled where the cards cross). Each card is cut to what it draws (alpha bounding box, the union over
seasons) and split into `cols` x `rows` quads so wind bends it.

Front and back of a card are triangles of their own, single sided: NORMAL leans up and out from the clump's middle
(the ground's light: a grass card lit by its own face flickers as it turns) and a little toward its own face (FACE:
straight up, a card seen from the side caught the styles' rim light: pale distant clumps), so the two faces' normals
are mirror images through the card; TANGENT w is +1 on the front, -1 on the back, so the one tangent-space normal map
(baked from the front: the blades' own normals, mirrored through the card when they faced away) reads mirrored from
behind. Double-sided materials would flip an up-leaning normal to point down on the back (Godot does: dark backs).

Maps per season: albedo (sRGB, the shade of the clump over each point baked in as the impostors do, alpha = what is
drawn, colour bled under it) + the normal map, one atlas for all tiers. Seasons are material variants of the one
`foliage` slot (winter = the plant regrown lying; snow = the winter plant under snow), every picture fitted inside the
same cards (their extent is the union over seasons). Wind: TEXCOORD_1 = (trunk, branch), TEXCOORD_2 = (phase,
flutter), _WIND, as every plant (veg_export.WIND_RECIPE): a card bends from its foot, each card its own phase.

Files (a folder an engine loads like any plant): <stem>_LOD0..2.glb (one tier each), <stem>.glb (all, MSFT_lod),
<stem>_seasons.json (contract, slots, per-season textures)."""

from __future__ import annotations

import json
import struct
import tempfile
from pathlib import Path

import numpy as np

from . import vegetation

GRADE = "groundcover"
# per LOD: cards through the foot, quads across x up each card, the bake's pixels along the frame's longer side
TIERS = ({"planes": 8, "cols": 3, "rows": 5, "px": 448, "heads": 12},
         {"planes": 5, "cols": 2, "rows": 4, "px": 128, "heads": 6},
         {"planes": 3, "cols": 1, "rows": 3, "px": 64, "heads": 3})
HEAD_SPAN = 1.25  # a head card's side, x the head's diameter
LEAN = 0.6        # card normals: up + LEAN x (where on the card, -1..1) along the card (a dome over the clump) ...
FACE = 0.7        # ... + FACE x the face's own side (front +, back -): mirror images through the card
SHADE = 0.45      # how much of the baked shade (sky reaching the point from above) goes into the albedo
SHADE_BRIGHT = 0.7
ALPHA_CUT = 0.5
MARGIN_PX = 2
ATLAS_W = 1024
PAD = 6           # px between pictures in the atlas
FLAT = 1.15       # a plant lower than FLAT x its radius gets a card lying flat (TOP_AT x its height up), baked from above
TOP_AT = 0.45
TOP_PX = 1.0      # (its picture's side, x the tier's px)
SUPER = 2         # the bake renders SUPER x the pictures' pixels and averages them down: what share of a pixel a blade
COVER = 0.55      # covers is its alpha; a pixel covered over COVER/2 is drawn (alpha / COVER: pixar's 2-4 mm blades at
                  # 3 mm a pixel fell under the cut and the lush clump read as a few thick blades)
# Alpha through the engine's mipmaps (measured in Godot, pixar grass LOD 0 at 2-12 m): box-filtered mips average a thin
# blade with the air beside it and an alpha test drops it (covered area 0.50 -> 0.07 of the full plant's by 12 m). A halo
# (alpha just under the cut round every shape) kept blades but filled the gaps between close ones (a fan of thin blades
# read as one broad leaf at 2 m); no static picture holds from mip 0 to 3. So: each tier's pictures are baked at the
# size they are seen at (px), and the engine either imports them without mipmaps or scales alpha by the mip level
# (MIP_ALPHA_RECIPE: 0.76-0.98 of the full plant's area from 2 to 12 m). HALO stays as a per-tier option, off.
HALO = (0.0, 0.0, 0.0)  # per tier, 0..0.49: alpha kept just under the cut round every shape, fading over HALO_PX
HALO_PX = 8.0
SEASONS = ("summer", "spring", "autumn", "winter", "snow")
MIP_ALPHA_RECIPE = ("alpha-tested cards through mipmaps (Ben Golus, 'Anti-aliased Alpha Test: The Esoteric Alpha To Coverage'): "
                    "after reading the albedo, alpha *= 1 + max(0, mip) * 0.25 with mip = 0.5 * log2(max(dot(dx, dx), dot(dy, dy))), "
                    "dx = dFdx(uv * textureSize), dy = dFdy(uv * textureSize); then the alpha test at the material's alphaCutoff. "
                    "Godot: in fragment(), vec2 t = UV * vec2(textureSize(albedo_tex, 0)); vec2 x = dFdx(t), y = dFdy(t); "
                    "ALPHA *= 1.0 + max(0.0, 0.5 * log2(max(dot(x, x), dot(y, y)))) * 0.25;")


def season_tree(T: dict, season: str) -> dict:
    """The clump in a season: regrown (a small plant's winter lies down: veg_small.SEASONS), snow = winter under snow."""
    s = T["spec"]
    se = "winter" if season == "snow" else season
    if se == s.get("season", "summer") and season != "snow":
        return T
    t = vegetation.grow({**s, "season": se})
    if season == "snow":
        t = {**t, "spec": {**t["spec"], "snow": 0.8}}
    return t


def drawn_points(T: dict) -> np.ndarray:
    """Every vertex the full export draws (styled: wood, crown, heads; realistic: stalks + cards), plant axes (z up)."""
    from . import veg_export, veg_leaf, veg_mesh, veg_style
    s = T["spec"]
    st = veg_style.sheet(s)
    P = [np.asarray(T["pos"], float)]
    if st:
        D = veg_style.dress(T, st, None, s.get("season", "summer"))
        for k in ("wood", "crown", "heads", "forks", "cards"):
            if D.get(k) is not None and len(D[k]["V"]):
                P.append(np.asarray(D[k]["V"], float))
    else:
        if len(veg_leaf.place(T)["pos"]):
            at = veg_leaf.atlas(s["leaves"], (s.get("bark") or {}).get("twig_color") or [0.45, 0.4, 0.35])
            L = veg_export.foliage_mesh(T, at)
            if len(L["V"]):
                P.append(L["V"])
        try:
            W = veg_mesh.tubes(T)
            P.append(W["V"])
        except Exception:
            pass
    return np.vstack(P)


def heads(trees: list) -> list:
    """[(centre xyz, radius)] of the flower / seed heads (veg_look.parts on the solid mesh as a look builds it), from the
    season showing the most of them."""
    from . import veg_look, veg_style
    best = []
    for t in trees:
        s = t["spec"]
        st = veg_style.sheet(s)
        if not st:
            continue  # (a realistic plant's flowers are on its card pictures)
        D = veg_style.dress(t, st, None, s.get("season", "summer"))
        Vs, Fs, n = [], [], 0
        C = D.get("crown")
        if C is None:
            continue
        for k, keep in (("crown", True), ("heads", D.get("heads") is not None and s.get("season", "summer") in D["heads"]["seasons"]), ("cards", True)):
            if keep and D.get(k) is not None and len(D[k]["V"]):
                Vs.append(D[k]["V"])
                Fs.append(np.asarray(D[k]["F"]) + n)
                n += len(D[k]["V"])
        W = D["wood"]
        Hp = float(max(np.vstack(Vs)[:, 2].max(), W["V"][:, 2].max() if len(W["V"]) else 0.0))
        P = veg_look.parts(np.vstack(Vs), np.vstack(Fs), Hp)
        hs = clusters(P["centre"][P["head"]], P["radius"][P["head"]])
        if len(hs) > len(best):
            best = hs
    return best


def clusters(C: np.ndarray, r: np.ndarray) -> list:
    """Head parts (petals, dabs, a ball) gathered into heads: parts closer than 1.5 x the sum of their radii are one
    head (single linkage). [(centre xyz, radius round it, rho = how far a part's middle may be from it and belong)]."""
    from scipy.sparse.csgraph import connected_components
    if not len(C):
        return []
    D = np.linalg.norm(C[:, None] - C[None], axis=2)
    _, lab = connected_components(D < 1.5 * (r[:, None] + r[None]), directed=False)
    out = []
    for k in range(lab.max() + 1):
        m = lab == k
        c = C[m].mean(0)
        d = np.linalg.norm(C[m] - c, axis=1)
        out.append((c.tolist(), float((d + r[m]).max()), float(d.max() + 0.5 * r[m].mean())))
    return out


def extent(trees: list) -> tuple[float, float]:
    """(R, H): the radius round the foot (x = y = 0) and the height every season's plant fits in, m."""
    P = np.vstack([drawn_points(t) for t in trees])
    R = float(np.max(np.linalg.norm(P[:, :2], axis=1)))
    H = float(P[:, 2].max())
    return R * 1.04 + 0.01, H * 1.03 + 0.01


def plane_frames(R: float, H: float, heads: list | None = None) -> list:
    """Every card's view: [{tier, k, top, theta (rad, the card's line in plan from +x), half (wedge, rad), px [w, h],
    span_w, span_h, pc (the card's middle), right, up (the picture's), back (toward its camera), Blender axes}].
    A low wide plant (H < FLAT x R: clover, a fern's rosette) also gets a card lying flat at TOP_AT x H in every tier,
    baked from straight above with the whole plant: what a standing player mostly sees of it.
    Flower / seed heads (`heads`: [(centre xyz, radius, rho)], heads()) get two small crossed cards of their own
    through their middle in every tier that can afford them (TIERS heads): on a wedge card a round head seen along the
    card is a sliver. A tier with more heads than that leaves them on the wedge cards (`heads_on_wedges`)."""
    heads = heads or []
    out = []
    z0 = -0.02 * H
    sw, sh = 2 * R, H - z0
    z, flat = np.array([0, 0, 1.0]), H < FLAT * R
    for ti, tr in enumerate(TIERS):
        n = tr["planes"]
        big = max(sw, sh)
        w, h = int(round(tr["px"] * sw / big)), int(round(tr["px"] * sh / big))
        for k in range(n):
            th = np.pi * k / n + (0.5 * np.pi / n if ti % 2 else 0.0)  # (tiers turned against each other: a switch doesn't line up cards)
            r = np.array([np.cos(th), np.sin(th), 0.0])
            out.append({"tier": ti, "k": k, "top": False, "theta": float(th), "half": float(np.pi / (2 * n)), "px": [w, h],
                        "span_w": sw, "span_h": sh, "pc": np.array([0, 0, z0 + sh / 2]), "right": r, "up": z, "back": np.cross(r, z),
                        "heads_on_wedges": len(heads) > tr["heads"]})
        if 0 < len(heads) <= tr["heads"]:
            C = np.array([h_[0] for h_ in heads], float)
            for hi, (c, rh, rho) in enumerate(heads):
                c = np.asarray(c, float)
                phi = float(np.arctan2(c[1], c[0])) if np.hypot(c[0], c[1]) > 1e-4 else 0.0
                k_ph = int(np.argmin([abs(((phi - (np.pi * k / n + (0.5 * np.pi / n if ti % 2 else 0.0)) + np.pi / 2) % np.pi) - np.pi / 2) for k in range(n)]))
                span = 2 * rh * HEAD_SPAN
                p_ = int(np.clip(round(tr["px"] * span / big * 2), 24, 128))
                for j, a_ in enumerate((phi, phi + np.pi / 2)):
                    r = np.array([np.cos(a_), np.sin(a_), 0.0])
                    out.append({"tier": ti, "k": 100 + 2 * hi + j, "k_ph": k_ph, "top": False, "head": [float(c[0]), float(c[1]), float(rho)],
                                "theta": 0.0, "half": 10.0, "px": [p_, p_], "span_w": span, "span_h": span, "pc": c, "right": r, "up": z,
                                "back": np.cross(r, z)})
        if flat:
            p_ = int(round(tr["px"] * TOP_PX))
            out.append({"tier": ti, "k": n, "top": True, "theta": 0.0, "half": 10.0, "px": [p_, p_], "span_w": sw, "span_h": sw,
                        "pc": np.array([0, 0, TOP_AT * H]), "right": np.array([1.0, 0, 0]), "up": np.array([0, 1.0, 0]), "back": z})
    return out


def views(frames: list, tmp: str, tag: str) -> list:
    """Blender jobs: albedo, normal, shade per card, orthographic, cut to its wedge."""
    out = []
    for fi, f in enumerate(frames):
        w, h = f["px"]
        cen = [float(x_) for x_ in f["pc"]] if not f["top"] else [0.0, 0.0, 0.0]
        sec = ({"centre": [0.0, 0.0], "head": f["head"]} if f.get("head") else
               {"centre": [0.0, 0.0], "theta": f["theta"], "half": f["half"], "heads": bool(f["top"] or f.get("heads_on_wedges"))})
        for kind in ("albedo", "normal", "shade"):
            out.append({"out": f"{tmp}/{tag}_{kind}_{fi:02d}.png", "size": [SUPER * w, SUPER * h], "azimuth": 0, "elevation": 0, "focus": cen,
                        "span": min(f["span_w"], f["span_h"]), "leaves": True, "transparent": True, "no_ground": True, "pass": kind,
                        "samples": 8, "sector": sec,
                        "basis": {"centre": cen, "right": f["right"].tolist(), "up": f["up"].tolist(), "back": f["back"].tolist(),
                                  "dist": 4.0 * max(f["span_w"], f["span_h"]) + 1.0}})
    return out


def _card_frame(f: dict, s: np.ndarray, t: np.ndarray, R: float, side: float = 1.0):
    """Per point at (s, t) on the card (m along its right / up from its middle): N (up + LEAN x out from the foot, a
    dome over the clump), T (along the card's right, square to N), B = cross(N, T) (the front's bitangent); Blender axes."""
    P = f["pc"][None] + s[:, None] * f["right"][None] + t[:, None] * f["up"][None]
    hz = np.c_[P[:, :2], np.zeros(len(P))] / R
    N = np.array([0, 0, 1.0])[None] + LEAN * np.clip(hz, -1, 1)
    if not f["top"]:  # (each face leans toward its own side: a normal straight up is seen edge-on from the side, a pale rim)
        N = N + side * FACE * f["back"][None]
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    r = f["right"]
    T = r[None] - (N @ r)[:, None] * N
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    return N, T, np.cross(N, T)


def compose(f: dict, albedo: np.ndarray, normal: np.ndarray, shade: np.ndarray, R: float) -> dict:
    """One card's maps from its passes (h, w, 4 floats 0..1): albedo sRGB with the shade baked in + alpha, and the
    tangent-space normal map in the card's own frame (_card_frame)."""
    from scipy import ndimage
    from .veg_export import _bleed
    k = albedo.shape[1] // max(f["px"][0], 1)
    if k > 1:  # (rendered SUPER x: coverage-weighted means down to the picture's pixels)
        h_, w_ = f["px"][1], f["px"][0]
        blk = lambda x_: x_[:h_ * k, :w_ * k].reshape(h_, k, w_, k, -1).mean((1, 3))
        al_ = albedo[..., 3:4]
        cov = blk(al_)
        albedo = np.concatenate([blk(albedo[..., :3] * al_) / np.maximum(cov, 1e-6), cov], -1)
        nw_ = normal[..., 3:4]
        normal = np.concatenate([blk(normal[..., :3] * nw_) / np.maximum(blk(nw_), 1e-6), blk(nw_)], -1)
        shade = blk(shade)
    a = albedo.copy()
    a[..., 3] = np.clip(a[..., 3] / COVER, 0, 1)
    solid = a[..., 3] > 0.5
    got = shade[..., 3] > 0.05
    s_ = ndimage.gaussian_filter(_bleed(np.where(got, shade[..., 0], 1.0), got), 1.0) if got.any() else np.ones(a.shape[:2])
    val = np.clip((a[..., :3].max(-1) - 0.35) / 0.5, 0, 1)
    kk = SHADE * (1 - SHADE_BRIGHT * val * val * (3 - 2 * val))
    lin = np.where(a[..., :3] <= 0.04045, a[..., :3] / 12.92, ((a[..., :3] + 0.055) / 1.055) ** 2.4) * (1 - kk + kk * s_)[..., None]
    rgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.maximum(lin, 0) ** (1 / 2.4) - 0.055)
    h, w = a.shape[:2]
    S, Tt = np.meshgrid((np.arange(w) + 0.5) / w * f["span_w"] - f["span_w"] / 2, f["span_h"] / 2 - (np.arange(h) + 0.5) / h * f["span_h"])
    N, T, B = (x_.reshape(h, w, 3) for x_ in _card_frame(f, S.ravel(), Tt.ravel(), R))
    nb = normal[..., :3] * 2 - 1
    nb /= np.maximum(np.linalg.norm(nb, axis=-1, keepdims=True), 1e-6)
    b = f["back"]
    d = nb @ b
    nb = nb - 2 * np.minimum(d, 0)[..., None] * b  # (facing away from the card's front: mirrored through it)
    loc = np.stack([(nb * T).sum(-1), (nb * B).sum(-1), (nb * N).sum(-1)], -1)
    loc[..., 2] = np.maximum(loc[..., 2], 0.05)
    loc /= np.linalg.norm(loc, axis=-1, keepdims=True)
    loc = np.where(solid[..., None] | (a[..., 3] > 0.02)[..., None], loc, np.array([0, 0, 1.0]))
    has = a[..., 3] > 0.02
    rgb = _bleed(rgb, has) if has.any() else rgb
    return {"rgb": np.clip(rgb, 0, 1), "alpha": a[..., 3], "nrm": loc}


def bake(trees: dict, R: float, H: float, frames: list, timeout: float = 1800) -> dict:
    """{season: [per frame {"albedo", "normal", "shade"} (h, w, 4) uint8]}: every season's plant rendered through every
    card's view (Blender, one job a season); compose() makes the maps from them."""
    from PIL import Image
    from . import veg_look
    out = {}
    with tempfile.TemporaryDirectory(prefix="hifipushie-ground-") as tmp:
        for se, t in trees.items():
            vs = views(frames, tmp, se)
            veg_look.render(t, vs, timeout=timeout)
            rd = lambda kind, fi: np.asarray(Image.open(f"{tmp}/{se}_{kind}_{fi:02d}.png").convert("RGBA"), np.uint8)
            out[se] = [{k_: rd(k_, fi) for k_ in ("albedo", "normal", "shade")} for fi in range(len(frames))]
    return out


def crops(baked: dict, frames: list) -> list:
    """Per frame the pixel box [x0, x1, y0, y1) every season draws inside (+ MARGIN_PX), or None (draws nothing)."""
    out = []
    for fi, f in enumerate(frames):
        A = np.max([baked[se][fi]["alpha"] for se in baked], axis=0) > 0.02
        if not A.any():
            out.append(None)
            continue
        ys, xs = np.nonzero(A)
        h, w = A.shape
        out.append([max(int(xs.min()) - MARGIN_PX, 0), min(int(xs.max()) + 1 + MARGIN_PX, w),
                    max(int(ys.min()) - MARGIN_PX, 0), min(int(ys.max()) + 1 + MARGIN_PX, h)])
    return out


def pack(sizes: list, width: int = ATLAS_W, pad: int = 2) -> tuple[list, int, int]:
    """Shelf packing: per (w, h) its [x, y] (None for None), and the atlas (W, H) (H a multiple of 4)."""
    order = sorted([i for i, s in enumerate(sizes) if s], key=lambda i: -sizes[i][1])
    W = width
    while any(s and s[0] + 2 * pad > W for s in sizes):
        W *= 2
    at = [None] * len(sizes)
    x = y = shelf = 0
    for i in order:
        w, h = sizes[i]
        if x + w + 2 * pad > W:
            x, y, shelf = 0, y + shelf, 0
        at[i] = [x + pad, y + pad]
        x += w + 2 * pad
        shelf = max(shelf, h + 2 * pad)
    Ht = y + shelf
    Ht += -Ht % 4
    return at, W, max(Ht, 4)


def atlases(baked: dict, frames: list, box: list) -> tuple[dict, list, int, int]:
    """{season: (rgba uint8, normal uint8)} and per frame its [x, y] in them."""
    from .veg_export import _bleed
    from scipy import ndimage
    sizes = [None if b is None else (b[1] - b[0], b[3] - b[2]) for b in box]
    at, W, Ht = pack(sizes, pad=PAD)
    out = {}
    for se, fr in baked.items():
        rgb = np.zeros((Ht, W, 3), np.float32)
        al = np.zeros((Ht, W), np.float32)
        nr = np.zeros((Ht, W, 3), np.float32)
        nr[..., 2] = 1.0
        hal = np.zeros((Ht, W), np.float32)
        for fi, b in enumerate(box):
            if b is None:
                continue
            x, y = at[fi]
            hal[max(y - PAD, 0):y + (b[3] - b[2]) + PAD, max(x - PAD, 0):x + (b[1] - b[0]) + PAD] = HALO[frames[fi]["tier"]]
            c = fr[fi]
            sl = (slice(b[2], b[3]), slice(b[0], b[1]))
            hh, ww = b[3] - b[2], b[1] - b[0]
            rgb[y:y + hh, x:x + ww] = c["rgb"][sl]
            al[y:y + hh, x:x + ww] = c["alpha"][sl]
            nr[y:y + hh, x:x + ww] = c["nrm"][sl]
        has = al > 0.02
        if has.any():
            rgb = _bleed(rgb, has)
            inside = al >= ALPHA_CUT
            d = ndimage.distance_transform_edt(~inside)
            al = np.where(inside, al, np.maximum(al * (al < ALPHA_CUT), np.minimum(hal * np.exp(-d / HALO_PX), ALPHA_CUT - 0.01)))
        A = (np.dstack([rgb, al]) * 255 + 0.5).clip(0, 255).astype(np.uint8)
        N = ((nr * 0.5 + 0.5) * 255 + 0.5).clip(0, 255).astype(np.uint8)
        out[se] = (A, N)
    return out, at, W, Ht


def cards(frames: list, box: list, at: list, W: int, Ht: int, R: float, H: float, tier: int) -> dict:
    """One tier's cards: V (plant axes), F, uv (glTF: v down), N, TAN (xyz + w), wind (trunk, branch, phase, flutter)."""
    tr = TIERS[tier]
    Vs, Fs, Us, Ns, Ts, Ws = [], [], [], [], [], []
    base = 0
    for fi, f in enumerate(frames):
        if f["tier"] != tier or box[fi] is None:
            continue
        b, (x, y) = box[fi], at[fi]
        w, h = f["px"]
        mpx_w, mpx_h = f["span_w"] / w, f["span_h"] / h
        s0, s1 = -f["span_w"] / 2 + b[0] * mpx_w, -f["span_w"] / 2 + b[1] * mpx_w
        t1, t0 = f["span_h"] / 2 - b[2] * mpx_h, f["span_h"] / 2 - b[3] * mpx_h
        nc, nr_ = (1, 1) if f.get("head") else (tr["cols"], (tr["cols"] if f["top"] else tr["rows"]))
        S, Tt = np.meshgrid(np.linspace(s0, s1, nc + 1), np.linspace(t0, t1, nr_ + 1), indexing="xy")  # (rows + 1, cols + 1)
        S, Tt = S.ravel(), Tt.ravel()
        P = f["pc"][None] + S[:, None] * f["right"][None] + Tt[:, None] * f["up"][None]
        u = (x + (S - s0) / (s1 - s0) * (b[1] - b[0])) / W
        v = (y + (t1 - Tt) / (t1 - t0) * (b[3] - b[2])) / Ht
        q = np.arange((nr_ + 1) * (nc + 1)).reshape(nr_ + 1, nc + 1)
        a_, b_, c_, d_ = q[:-1, :-1].ravel(), q[:-1, 1:].ravel(), q[1:, 1:].ravel(), q[1:, :-1].ravel()
        front = np.r_[np.c_[a_, b_, c_], np.c_[a_, c_, d_]]  # (right, up, seen from `back`: counter-clockwise)
        n_v = len(S)
        # wind: a card bends from its foot; a flat card by how far out from the foot (its leaves' tips)
        hz = np.clip(P[:, 2] / max(H, 1e-6), 0, 1) if not f["top"] else np.clip(np.linalg.norm(P[:, :2], axis=1) / R, 0, 1) * TOP_AT
        ph = float(vegetation._u(np.array([1000 * tier + f.get("k_ph", f["k"]) + 1], np.uint64), 57)[0])  # (a head card sways with its stalk's)
        bend = hz ** 1.5 * float(np.clip(H / 1.2, 0.08, 1.0))
        wind = np.c_[hz ** 1.5, bend, np.full(n_v, ph), 0.5 * hz]
        for side in ((1.0,) if f["top"] else (1.0, -1.0)):  # front, then back (its own vertices: TANGENT w = -1); a flat card: its top
            N, T, _ = _card_frame(f, S, Tt, R, side)
            Vs.append(P)
            Us.append(np.c_[u, v])
            Ns.append(N)
            Ts.append(np.c_[T, np.full(n_v, side)])
            Ws.append(wind)
            Fs.append((front if side > 0 else front[:, ::-1]) + base)
            base += n_v
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "uv": np.vstack(Us), "N": np.vstack(Ns), "TAN": np.vstack(Ts),
            "wind": np.vstack(Ws), "cards": sum(1 for fi, f in enumerate(frames) if f["tier"] == tier and box[fi] is not None),
            "flat": any(f["top"] for f in frames if f["tier"] == tier)}


def _png(a: np.ndarray) -> bytes:
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(a).save(b, format="PNG", optimize=True)
    return b.getvalue()


def write_glb(path: str, name: str, tiers: list, maps: dict, seasons: list, info: dict, which=None) -> dict:
    """A GLB of the given tiers' card meshes (`which` = tier indices; None = all, LOD 0 the scene, the others hung on
    it by MSFT_lod), one `foliage` material per season variant (KHR_materials_variants)."""
    from . import veg_export
    which = list(range(len(tiers))) if which is None else list(which)
    buf = bytearray()
    views_, accessors, images, textures, materials, meshes, nodes = [], [], [], [], [], [], []

    def view(data: bytes, target=None):
        while len(buf) % 4:
            buf.append(0)
        views_.append({"buffer": 0, "byteOffset": len(buf), "byteLength": len(data), **({"target": target} if target else {})})
        buf.extend(data)
        return len(views_) - 1

    def acc(a, kind, comp, target, minmax=False):
        a = np.ascontiguousarray(a)
        d = {"bufferView": view(a.tobytes(), target), "componentType": comp, "count": int(len(a)), "type": kind}
        if minmax:
            d["min"], d["max"] = a.min(0).tolist(), a.max(0).tolist()
        accessors.append(d)
        return len(accessors) - 1

    seen = {}

    def tex(png: bytes):
        k_ = (hash(png), len(png))
        if k_ not in seen:
            images.append({"bufferView": view(png), "mimeType": "image/png"})
            textures.append({"source": len(images) - 1, "sampler": 0})
            seen[k_] = len(textures) - 1
        return seen[k_]

    se0 = seasons[0]
    var_mat = {}
    for se in seasons:
        A, Nm = maps[se]
        materials.append({"name": "foliage" if se == se0 else f"foliage_{se}",
                          "pbrMetallicRoughness": {"baseColorTexture": {"index": tex(_png(A))}, "metallicFactor": 0.0,
                                                   "roughnessFactor": float(info.get("roughness", 0.85))},
                          "normalTexture": {"index": tex(_png(Nm))},
                          "alphaMode": "MASK", "alphaCutoff": ALPHA_CUT, "doubleSided": False,
                          "extras": {"grade": GRADE, "alpha_mips": "import WITHOUT mipmaps, or WITH them and this in the shader: " + MIP_ALPHA_RECIPE,
                                     "faces": "front and back are their own single-sided triangles: NORMALs mirror "
                                                              "images through the card, TANGENT w +1 / -1 (the normal map reads mirrored from behind)"}})
        var_mat[se] = len(materials) - 1
    variants = list(seasons)  # (one season too: the seasons json is how an engine maps slots)
    ext = {"KHR_materials_variants"} if variants else set()
    lod_nodes, lod_info = [], []
    for li in which:
        C = tiers[li]
        y = lambda v_: np.stack([v_[:, 0], v_[:, 2], -v_[:, 1]], 1)
        at_ = {"POSITION": acc(y(C["V"]).astype(np.float32), "VEC3", 5126, 34962, minmax=True),
               "NORMAL": acc(y(C["N"]).astype(np.float32), "VEC3", 5126, 34962),
               "TANGENT": acc(np.c_[y(C["TAN"][:, :3]), C["TAN"][:, 3]].astype(np.float32), "VEC4", 5126, 34962),
               "TEXCOORD_0": acc(C["uv"].astype(np.float32), "VEC2", 5126, 34962),
               "TEXCOORD_1": acc(C["wind"][:, :2].astype(np.float32), "VEC2", 5126, 34962),
               "TEXCOORD_2": acc(C["wind"][:, 2:].astype(np.float32), "VEC2", 5126, 34962),
               "_WIND": acc(C["wind"].astype(np.float32), "VEC4", 5126, 34962)}
        p_ = {"attributes": at_, "indices": acc(C["F"].astype(np.uint32).ravel(), "SCALAR", 5125, 34963), "material": var_mat[se0]}
        if variants:
            p_["extensions"] = {"KHR_materials_variants": {"mappings": [{"material": var_mat[se], "variants": [i]} for i, se in enumerate(variants)]}}
        pre = f"LOD{li}_" if len(which) > 1 else ""
        meshes.append({"name": pre + "foliage", "primitives": [p_]})
        nodes.append({"name": pre + "foliage", "mesh": len(meshes) - 1})
        if len(which) > 1:
            nodes.append({"name": f"{name}_LOD{li}", "children": [len(nodes) - 1]})
        lod_nodes.append(len(nodes) - 1)
        tr = TIERS[li]
        lod_info.append({"lod": li, "triangles": int(len(C["F"])), "cards": int(C["cards"]), "flat_card": bool(C["flat"]),
                         "planes": tr["planes"], "grid": [tr["cols"], tr["rows"]], "grade": GRADE})
    if len(lod_nodes) > 1:
        ext.add("MSFT_lod")
        nodes[lod_nodes[0]]["extensions"] = {"MSFT_lod": {"ids": lod_nodes[1:]}}
        nodes[lod_nodes[0]]["extras"] = {"MSFT_screencoverage": [0.2, 0.06, 0.0][:len(lod_nodes)]}
    while len(buf) % 4:
        buf.append(0)
    gltf = {"asset": {"version": "2.0", "generator": "hifipushie vegetation (groundcover)"},
            "scene": 0, "scenes": [{"nodes": [lod_nodes[0]]}], "nodes": nodes, "meshes": meshes, "materials": materials,
            "textures": textures, "images": images,
            "samplers": [{"wrapS": 33071, "wrapT": 33071, "magFilter": 9729, "minFilter": 9987}],
            "accessors": accessors, "bufferViews": views_, "buffers": [{"byteLength": len(buf)}],
            "extras": {"hifipushie_plant": {**info, "grade": GRADE, "lods": lod_info, "wind": veg_export.WIND_RECIPE, "variants": variants,
                                            "contract": veg_export.CONTRACT}}}
    if variants:
        gltf["extensions"] = {"KHR_materials_variants": {"variants": [{"name": v_} for v_ in variants]}}
    if ext:
        gltf["extensionsUsed"] = sorted(ext)
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
    return {"path": str(out), "bytes": out.stat().st_size, "lods": lod_info}


def build(T: dict, seasons=SEASONS, baked: dict | None = None) -> dict:
    """Bake the clump and make every tier's cards: {"R", "H", "frames", "box", "maps" {season: (A, N)}, "tiers": [cards],
    "baked"}. `baked` = an earlier build's (the Blender renders: the maps and cards are made again from them)."""
    if not T.get("clump"):
        raise ValueError("groundcover grade is for small plants (a clump: grass, daisy, clover, fern...); trees have impostors")
    ck = _cache_path(T["spec"], seasons) if baked is None else None
    if ck is not None and ck.exists():
        import pickle
        try:
            baked = pickle.loads(ck.read_bytes())
        except Exception:
            baked = None
    if baked is None:
        trees = {se: season_tree(T, se) for se in seasons}
        R, H = extent(list({id(t): t for t in trees.values()}.values()))
        frames = plane_frames(R, H, heads(list(trees.values())))
        baked = {"R": R, "H": H, "frames": frames, "renders": bake(trees, R, H, frames)}
        if ck is not None:
            import pickle
            ck.parent.mkdir(parents=True, exist_ok=True)
            ck.write_bytes(pickle.dumps(baked))
            for old_ in sorted(ck.parent.glob("*.pkl"), key=lambda q: q.stat().st_mtime)[:-40]:
                old_.unlink(missing_ok=True)
    R, H, frames = baked["R"], baked["H"], baked["frames"]
    seasons = list(baked["renders"])
    return {**_finish(baked["renders"], frames, R, H), "R": R, "H": H, "frames": frames, "seasons": seasons, "baked": baked}


def _cache_path(spec: dict, seasons) -> Path:
    """Where a bake is kept: by the plant's spec, the seasons, the growth and style code and the bake's own settings
    ($HIFIPUSHIE_VEG_CACHE/groundcover, else ~/.cache/hifipushie/groundcover; the 40 most recent kept)."""
    import hashlib
    import os
    code = b"".join((Path(__file__).with_name(f).read_bytes() for f in
                     ("veg_groundcover.py", "veg_style.py", "veg_small.py", "veg_leaf.py", "blender_vegetation.py", "veg_look.py")))
    key = hashlib.sha1(json.dumps([spec, list(seasons), vegetation.VERSION, TIERS], sort_keys=True, default=str).encode() + code).hexdigest()[:20]
    root = Path(os.environ.get("HIFIPUSHIE_VEG_CACHE") or Path.home() / ".cache" / "hifipushie")
    return root / "groundcover" / f"{key}.pkl"


def _finish(renders: dict, frames: list, R: float, H: float) -> dict:
    f32 = lambda a_: np.asarray(a_, np.float32) / 255
    baked = {se: [compose(f, f32(r_["albedo"]), f32(r_["normal"]), f32(r_["shade"]), R) for f, r_ in zip(frames, fr)]
             for se, fr in renders.items()}
    box = crops(baked, frames)
    maps, at, W, Ht = atlases(baked, frames, box)
    tiers = [cards(frames, box, at, W, Ht, R, H, ti) for ti in range(len(TIERS))]
    return {"box": box, "maps": maps, "tiers": tiers, "atlas": [W, Ht], "at": at}


def export(T: dict, out_dir: str, stem: str, seasons=SEASONS, built: dict | None = None) -> dict:
    """The groundcover files in out_dir (see the module's docstring); returns counts."""
    from . import veg_export, veg_style
    s = T["spec"]
    st = veg_style.sheet(s)
    B = built or build(T, seasons)
    info = {"name": stem, "species": s.get("species"), "height_m": round(B["H"], 3), "radius_m": round(B["R"], 3),
            "atlas_px": B["atlas"], "style": {"name": st["name"] if st else "realistic", "kind": "groundcover cards"},
            "snow_numbers": veg_export.snow_numbers(s, st), "roughness": float((st or {}).get("crown", {}).get("roughness", 0.85)) if st else 0.85,
            "groundcover": "each card shows the slice of the clump in its own wedge round the foot (azimuth within 90 / planes deg of "
                           "its line), baked square on from the full plant in its style and season: albedo (sRGB, shade of the clump "
                           "above baked in) + tangent-space normal map; NORMAL leans up and out (the ground's light)"}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    seasons = list(B["seasons"])
    full = write_glb(str(out / f"{stem}.glb"), stem, B["tiers"], B["maps"], seasons, info)
    files = [full["path"]]
    for li in range(len(B["tiers"])):
        files.append(write_glb(str(out / f"{stem}_LOD{li}.glb"), stem, B["tiers"], B["maps"], seasons, info, which=[li])["path"])
    sj = veg_export.seasons_json(full["path"])
    if sj:
        files.append(sj["path"])
    return {"path": full["path"], "files": files, "lods": full["lods"], "R": B["R"], "H": B["H"], "atlas": B["atlas"],
            "seasons_file": sj["path"] if sj else None}
