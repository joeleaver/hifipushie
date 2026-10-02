"""Ground character for the 3D tiles' maps: what the ground looks like between the rock faces, per point (texel or
vertex), the same in every tile and LOD (pointwise on global grids and noise).

The whole-level round (2026-10-02; the user on pebble from 150 m: "WTF?", a cave "with a cover over it"): the ground
was one flat colour per cover layer (plaster), fairways flat light-green stickers, cliffs grey shells on a green
mound with turf rolling over every lip. Compared with photos of real coast (Pebble Beach's 7th, Cornish cliff tops,
Durdle Door), real ground varies at every scale and by its situation:
- the turf ends back from a cliff's lip along a ragged edge (bare rock and a dark undercut below the turf mat), and
  rock breaks through in patches near the edges and on thin-soiled knolls;
- the wave and splash zone is bare rock or sand: no grass within ~1.5 m of the sea;
- grass is drier and paler on convex ground, sun-facing slopes and the salt-burnt first tens of metres above the sea,
  lusher in hollows; patches at tens of metres, tussocks at a metre;
- cover kinds read differently: "mown" (fairways, greens, lawns: even, bright, striped by the mower, a first-cut ring
  at its edge), "rough" (long grass: olive, straw-tipped, tussocky), "scrub" (low bushes: dark grey-green clumps
  with dry gaps, on slopes and near cliffs). Plain "meadow"/"grass" covers are rough; they turn to scrub on
  steeper slopes.
Everything here is colour and layer weight only (Materials), never geometry."""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import noise


def _ss(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


def _hex(c):
    return np.array([int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]) if isinstance(c, str) else np.asarray(c, float)


# what each cover type is, as ground character (types not listed: none of it)
KIND_OF = {"mown": "mown", "lawn": "mown", "fairway": "mown", "green": "mown", "grass": "rough", "meadow": "rough",
           "rough": "rough", "pasture": "rough", "scrub": "scrub", "heath": "scrub", "orchard": "rough"}

LOOK = {  # sRGB
    "straw": [0.66, 0.60, 0.38],        # dry grass, seed heads
    "lush": [0.25, 0.42, 0.14],         # damp hollows
    "salt": [0.58, 0.53, 0.37],         # salt-burnt turf near the sea
    "scrub": [0.25, 0.29, 0.19],        # coastal scrub clumps (grey-green)
    "scrub_gap": [0.48, 0.44, 0.31],    # dry ground between them
    "undercut": 0.55,                   # rock just under the turf's edge: shaded
}
LIP = {"band": 1.4, "patches": 7.0, "steep": 50.0}  # turf edge set back ~band m (wandering 0.3-2.4x); rock patches
# within `patches` m of a lip; a lip = ground steeper than `steep` deg below a top
SHORE = 1.6  # no grass within this many metres above the sea (wandering +-0.8)


class Ground:
    """Grids the ground's character needs (on the terrain grid, from the meshed ground `H`: the field's own copy, with
    arch necks and dolines dug in), and the per-point rules."""

    def __init__(self, T, H, sea_level=None):
        self.T = T
        self.sea = sea_level
        c = float(T.cell)
        gy, gx = np.gradient(H, c)
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))
        steep = slope > LIP["steep"]
        # tops: within a cliff's height of the highest ground near it (the foot is far below its neighbours' max)
        r = max(1, int(round(3.0 / c)))
        top = H >= ndimage.maximum_filter(H, size=2 * r + 1) - 1.5
        self.lip_d = np.where(steep.any(), ndimage.distance_transform_edt(~steep) * c, 1e3)
        self.top = ndimage.gaussian_filter(top.astype(float), 0.7)
        # moisture: hollows (positive Laplacian of the ground smoothed over ~6 m) wet, crests dry
        Hs = ndimage.gaussian_filter(H, max(1.0, 6.0 / c))
        lap = ndimage.laplace(Hs) / (c * c)
        self.wet = np.clip(lap / 0.02, -1, 1)
        # sun: a slope's share facing the noon sun (northern hemisphere: south), dry
        self.sunny = np.clip(-gy / np.maximum(np.hypot(gx, gy), 1e-6), -1, 1) * _ss(5, 25, slope)
        self.slope = slope
        sd = getattr(T, "sea", None)
        self.sea_d = np.asarray(sd["sd"], float) if sd is not None and "sd" in sd else None
        self._dir = {}

    # ---- grids at points (cubic B-spline on the grid: smooth, the same in every tile)
    def _at(self, mats, a, xy):
        return mats._grid(a, xy)

    def stripe_frame(self, name, mask):
        """The mowing frame of a mown cover: each piece of it (a fairway, a green) is mown in straight passes along
        its long axis (the principal axis of its cells), stripes counted across it from its centre. Grids per cell
        (nearest piece): the across direction (nx, ny) and the centre. A frame that turned with the zone put metres of
        phase into every degree (positions are hundreds of metres from the origin)."""
        if name not in self._dir:
            c = float(self.T.cell)
            m = np.asarray(mask, float) > 0.3
            lab, nl = ndimage.label(m)
            frame = np.zeros((nl + 1, 4))
            X, Y = self.T.X, self.T.Y
            for k in range(1, nl + 1):
                sel = lab == k
                xs, ys = X[sel], Y[sel]
                cx, cy = xs.mean(), ys.mean()
                if len(xs) < 3:
                    frame[k] = [1.0, 0.0, cx, cy]
                    continue
                cov = np.cov(np.c_[xs - cx, ys - cy].T)
                w, v = np.linalg.eigh(cov)
                frame[k] = [v[0, 0], v[1, 0], cx, cy]  # (the smaller axis: across the piece)
            if nl:
                _, (iy, ix) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
                near = lab[iy, ix]
            else:
                near = np.zeros(m.shape, int)
            self._dir[name] = frame[near]
        return self._dir[name]

    def stripes(self, P, name, mask):
        """-1..1 alternating 8 m bands across a mown piece (crisp-ish: a mower's pass, softened)."""
        F = self.stripe_frame(name, mask)
        T = self.T
        iy = np.clip(np.rint((P[:, 1] - T.ys[0]) / T.cell).astype(np.int64), 0, F.shape[0] - 1)
        ix = np.clip(np.rint((P[:, 0] - T.xs[0]) / T.cell).astype(np.int64), 0, F.shape[1] - 1)
        f = F[iy, ix]
        across = (P[:, 0] - f[:, 2]) * f[:, 0] + (P[:, 1] - f[:, 3]) * f[:, 1]
        return np.clip(1.6 * np.sin(np.pi * across / 8.0), -1, 1)

    def rock(self, mats, P, N):
        """Extra rock (0..1) on gentle ground: the bare band along a lip (a ragged turf edge), rock breaking through
        near edges, the wave/splash zone. Returns (rock, undercut darkening 0..1, shore share)."""
        xy = P[:, :2]
        d = self._at(mats, self.lip_d, xy)
        top = np.clip(self._at(mats, self.top, xy), 0, 1)
        # the turf's edge wanders 0.3-2.4 x the band (metre-scale bites and tongues, a crisp edge over ~0.12 m)
        Pf = P * np.array([1.0, 1.0, 0.0])
        wob = 0.15 + 2.5 * noise.fbm(Pf, 2.6, 4, seed=611) ** 1.3 + 0.35 * (noise.fbm(Pf, 0.7, 2, seed=614) - 0.5)
        edge = LIP["band"] * wob
        bare = _ss(edge + 0.12, edge - 0.12, d) * top
        # the rock right under the turf's lip is shaded (the mat overhangs it a little)
        under = _ss(edge - 0.45, edge - 0.05, d) * _ss(edge + 0.05, edge - 0.05, d) * top
        # patches breaking through: near lips, more of them closer, small (1-3 m) and ragged
        near = _ss(LIP["patches"], 1.0, d) * top
        pat = noise.fbm(P * np.array([1.0, 1.0, 0.0]), 2.2, 3, seed=612)
        patch = _ss(0.72 - 0.16 * near, 0.76 - 0.16 * near, pat) * near
        rock = np.maximum(bare, patch)
        # turf and thrift on the faces' ledges near the top: up-facing rock in patches keeps a skin of green
        ledge = _ss(0.72, 0.9, N[:, 2]) * _ss(LIP["patches"] + 6.0, 2.0, d) * _ss(0.5, 0.62, noise.fbm(P, 1.8, 3,
                                                                                                         seed=615)) \
            * (1 - top)  # (below the top: on the face)
        shore = np.zeros(len(P))
        if self.sea is not None:
            sh = SHORE + 1.6 * (noise.fbm(P * np.array([1.0, 1.0, 0.0]), 6.0, 2, seed=613) - 0.5)
            # (above the water: the seabed stays sand)
            shore = _ss(self.sea + sh + 0.4, self.sea + sh - 0.4, P[:, 2]) * _ss(self.sea - 0.4, self.sea - 0.1, P[:, 2])
            if self.sea_d is not None:  # (only by the sea, not a low inland hollow)
                shore = shore * _ss(40.0, 15.0, self._at(mats, self.sea_d, xy))
            rock = np.maximum(rock, shore)
        return np.clip(rock, 0, 1), under, shore, ledge

    def scrub(self, mats, P, scrub, natural):
        """(scrub share, clump 0..1): asked scrub, plus unkept grass turning to scrub on slopes past ~20 deg; the
        bushes' clumps (1-4 m) within it."""
        Pf = P * np.array([1.0, 1.0, 0.0])
        sl = self._at(mats, self.slope, P[:, :2])
        sc = np.clip(scrub + natural * _ss(20.0, 36.0, sl) * 0.8 * (0.4 + 0.6 * noise.fbm(Pf, 30.0, 2, seed=626)),
                     0, 1)
        # (patches of 3-8 m holding several bushes: one bush per 2 m noise blob read as rubble from 150 m)
        return sc, _ss(0.45, 0.56, noise.fbm(Pf, 5.0, 3, seed=627))

    def tint(self, mats, P, N, c, kinds, mown_dirs):
        """The ground colour c (sRGB, the cover's own) varied by situation and kind. kinds: {"mown"|"rough"|"scrub":
        weight per point}; mown_dirs: [(weight, stripes -1..1 per point)]."""
        xy = P[:, :2]
        n = len(P)
        Pf = P * np.array([1.0, 1.0, 0.0])
        lum = lambda col: col @ np.array([0.3, 0.59, 0.11])
        mown = np.clip(kinds.get("mown", np.zeros(n)), 0, 1)
        scrub = np.clip(kinds.get("scrub", np.zeros(n)), 0, 1)
        natural = np.clip(kinds.get("rough", np.zeros(n)) + scrub, 0, 1)  # (unmown grass; not sand, tracks, forest)
        # macro patches (60 m and 15 m): brightness +-9%, hue toward straw or lush
        m1 = noise.fbm(Pf, 60.0, 2, seed=621) - 0.5
        m2 = noise.fbm(Pf, 15.0, 2, seed=622) - 0.5
        wet = self._at(mats, self.wet, xy)
        sunny = self._at(mats, self.sunny, xy)
        dry = np.clip(0.5 * m1 + 0.35 * m2 - 0.45 * wet + 0.25 * sunny, -1, 1)
        out = c * (1 + 0.18 * m1 + 0.10 * m2)[:, None]
        tow = lambda col, a: out * (1 - a[:, None]) + np.asarray(col) * lum(out)[:, None] / lum(np.asarray(col)) * \
            a[:, None]
        # (tones carried at the ground's own brightness: a hue shift, not a paint-over)
        out = tow(LOOK["straw"], np.clip(dry, 0, 1) * 0.35 * natural + np.clip(dry, 0, 1) * 0.1 * mown)
        out = tow(LOOK["lush"], np.clip(-dry, 0, 1) * 0.45)
        # salt-burnt turf above the sea (unmown): patchy within ~30 m of the shore
        if self.sea_d is not None:
            sd = self._at(mats, self.sea_d, xy)
            salt = _ss(32.0, 6.0, sd) * natural * (0.25 + 0.55 * noise.fbm(Pf, 9.0, 2, seed=623))
            out = out * (1 - 0.4 * salt[:, None]) + np.asarray(LOOK["salt"]) * 0.4 * salt[:, None]
        # rough: tussocks (1 m) and straw tips (3 m)
        rough = np.clip(natural - scrub, 0, 1)
        t1 = noise.fbm(P, 0.9, 2, seed=624) - 0.5
        t2 = noise.fbm(Pf, 3.0, 2, seed=625) - 0.5
        out = out * (1 + rough * (0.22 * t1 + 0.12 * t2))[:, None]
        out = tow(LOOK["straw"], rough * np.clip(t2 * 1.4, 0, 1) * 0.5)
        # scrub on slopes (natural grass turns to scrub from ~22 deg) and where asked: clumps 1-4 m with dry gaps
        sc, clump = self.scrub(mats, P, scrub, natural)
        scol = np.asarray(LOOK["scrub"]) * (0.8 + 0.4 * noise.fbm(Pf, 1.1, 2, seed=628))[:, None]
        gap = np.asarray(LOOK["scrub_gap"])
        s_col = scol * clump[:, None] + gap * (1 - clump[:, None])
        out = out * (1 - sc[:, None]) + s_col * sc[:, None]
        # sand: wet and darker in the swash (up to ~0.9 m over the sea), a wrack line of weed and drift at the high
        # water mark, dry sand above with shell and pebble grit (a beach was one smooth cream ramp)
        sand = np.clip(kinds.get("sand", np.zeros(n)), 0, 1)
        if sand.any() and self.sea is not None:
            z = P[:, 2] - self.sea
            wv = 0.35 * (noise.fbm(Pf, 7.0, 2, seed=641) - 0.5)
            wet = _ss(1.0 + wv, 0.55 + wv, z)
            wrack = np.exp(-((z - 1.25 - 1.5 * wv) / 0.18) ** 2) * _ss(0.45, 0.7, noise.fbm(Pf, 1.6, 3, seed=642))
            grit = noise.fbm(P, 0.25, 2, seed=643) - 0.5
            f = (1 - 0.38 * wet) * (1 - 0.45 * wrack) * (1 + 0.10 * grit + 0.06 * (noise.fbm(Pf, 5.0, 2, seed=644) - 0.5))
            sc_ = np.c_[f, f * (1 - 0.03 * wet), f * (1 - 0.08 * wet - 0.1 * wrack)]
            out = out * (1 - sand[:, None]) + out * sc_ * sand[:, None]
        # mown: even and bright, striped along the cut (8 m bands, alternate stripes +-6%), a first cut at the edge
        if mown.any():
            st = np.zeros(n)
            wsum = np.zeros(n)
            for w, ph in mown_dirs:
                st += w * ph
                wsum += w
            st = st / np.maximum(wsum, 1e-9)
            core = _ss(0.55, 0.9, mown)
            out = out * (1 + 0.12 * st * core)[:, None]
            # first cut: between the mown core and the rough, a ring a shade darker and less even
            ring = _ss(0.15, 0.5, mown) * (1 - core)
            out = out * (1 - 0.08 * ring)[:, None]
        return np.clip(out, 0, 1)


# ---------------------------------------------------------------- the grass detail (a tiling swatch, like the rock's)

GRASS = {"size": 2.0, "res": 256, "blades": 26000, "length": (0.03, 0.09), "dry": 0.12}


def grass_swatch(size=None, res=None, seed=4243):
    """A tileable turf swatch (top view, periodic): blades as short strokes splatted on the torus (lit tips, dark
    gaps between them), clumps 0.1-0.4 m, dry blades straw-coloured. Returns {"albedo" (n, n, 3) multiplier, mean 1;
    "height" m; "normal" (n, n, 3) tangent space (+x east, +y north); "rough"; "size_m"; "texels_per_m"; "n"}. Below
    the ground maps' texel (4/m) the macro colour is mush at eye level; this is what an engine tiles over it."""
    from .terrain_swatch import spectral
    L = float(size or GRASS["size"])
    n = int(round(L * (res or GRASS["res"])))
    rng = np.random.default_rng(seed)
    nb = int(GRASS["blades"] * (L / 2.0) ** 2)
    clump = spectral(n, 2.2, seed + 1, lo=5)  # (-1..1, 0.1-0.4 m)
    # blades seeded more densely in the clumps
    px = rng.random((nb * 2, 2)) * n
    keep = rng.random(nb * 2) < 0.35 + 0.5 * (0.5 + 0.5 * clump[px[:, 1].astype(int) % n, px[:, 0].astype(int) % n])
    px = px[keep][:nb]
    nb = len(px)
    ang = rng.random(nb) * 2 * np.pi
    ln = rng.uniform(*GRASS["length"], nb) * n / L
    dry = rng.random(nb) < GRASS["dry"]
    hgt = np.zeros((n, n))
    tip = np.zeros((n, n))
    dryi = np.zeros((n, n))
    cnt = np.zeros((n, n))
    for t in np.linspace(0, 1, 9):
        q = px + (t * ln)[:, None] * np.c_[np.cos(ang), np.sin(ang)]
        ix, iy = q[:, 0].astype(int) % n, q[:, 1].astype(int) % n
        np.add.at(hgt, (iy, ix), 0.004 + 0.012 * t)
        np.add.at(tip, (iy, ix), t)
        np.add.at(dryi, (iy, ix), dry * 1.0)
        np.add.at(cnt, (iy, ix), 1.0)
    hgt = ndimage.gaussian_filter(hgt, 0.6, mode="wrap") + 0.012 * clump
    cover = 1 - np.exp(-cnt / 2.0)  # (how much of the texel blades cover; the rest is shadowed gap)
    tipm = tip / np.maximum(cnt, 1e-9)
    drym = np.clip(dryi / np.maximum(cnt, 1e-9), 0, 1)
    tone = (0.62 + 0.38 * cover) * (0.85 + 0.3 * tipm) * (1 + 0.12 * clump)
    tone = ndimage.gaussian_filter(tone, 0.5, mode="wrap")
    straw = np.array([1.45, 1.30, 0.75])  # (a dry blade against the green: warmer and paler)
    alb = tone[..., None] * (1 + drym[..., None] * (straw - 1))
    alb = alb / alb.reshape(-1, 3).mean(0)
    t = L / n
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * t)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * t)
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    rough = 1.0 + 0.1 * (1 - cover)
    return {"albedo": alb, "height": hgt - hgt.mean(), "normal": nrm, "rough": rough / rough.mean(), "size_m": L,
            "texels_per_m": n / L, "n": n}


def write_grass(out_dir):
    """The grass swatch's images in out_dir/materials (rows top = north), as terrain_swatch.write lays the rock's:
    grass_detail_albedo (linear, x 2 = the multiplier), _normal (tangent: +x east, +y north), _height (16-bit). Returns
    the manifest entry."""
    from PIL import Image
    from .terrain_swatch import tileability
    S = grass_swatch()
    d = out_dir / "materials"
    d.mkdir(exist_ok=True)
    q8 = lambda a: np.round(np.clip(a, 0, 1) * 255).astype(np.uint8)
    hr = float(max(np.abs(S["height"]).max(), 1e-4))
    imgs = {"albedo": q8(0.5 * S["albedo"]), "normal": q8(S["normal"] * 0.5 + 0.5),
            "height": np.round((S["height"] / hr * 0.5 + 0.5) * 65535).astype(np.uint16)}
    files, seams = {}, {}
    for k, a in imgs.items():
        fn = f"materials/grass_detail_{k}.png"
        Image.fromarray(np.ascontiguousarray(a[::-1]), "I;16" if a.dtype == np.uint16 else None).save(out_dir / fn)
        files[k] = fn
        seams[k] = tileability(a)
    return {"layers": ["grass", "scrub"], **files, "size_m": S["size_m"], "texels_per_m": S["texels_per_m"],
            "height_m": round(hr, 5), "wrap_seam": seams, "projection": "top: uv = world (x, y) / size_m",
            "fade_m": list(GRASS_FADE),
            "recipe": "Where the grass/scrub layers weigh w (_WEIGHTS / the weights map), on ground and cliff tiles: "
                      "uv = worldpos.xy / size_m, and a second sampling at uv / 1.618 + (0.37, 0.71), mixed 50/50 to "
                      "break the repeat; albedo: macro x (1 + w f (2 albedo - 1)); normal: the detail normal (+x east, "
                      "+y north) RNM-combined onto the macro normal by w f; f = 1 - smoothstep(fade_m[0], fade_m[1], "
                      "view distance)."}


GRASS_FADE = (20.0, 70.0)  # m: the grass detail fades out with the view distance (its 2 m repeat shows beyond)


# ---------------------------------------------------------------- ground clutter (placeholder instances)

CLUTTER = {  # kind: (grid spacing m, what decides it) -- jittered grid samples kept by probability
    "bush": 1.3,      # coastal scrub / heath clumps, 0.5-1.4 m: in scrub, on its clumps (the maps' dark clumps)
    "tussock": 0.7,   # long-grass tussocks, 0.3-0.6 m: in rough grass, off scrub
    "boulder": 1.6,   # rocks 0.3-1.5 m: along the shore's splash zone and where rock breaks through near a lip
}


def clutter(T, mats, field, kinds=("bush", "boulder"), box=None, near=None, seed=7):
    """Ground clutter as instances [[x, y, z, kind index, scale, yaw]] (kind index into `kinds`), from the same
    masks the maps paint: bushes on the scrub's clumps, tussocks in rough grass, boulders in the splash zone and the
    rock breaking through near lips. Engines would scatter these from the layer weights with their own detail system;
    this is the placement and the reference density. box: [[x0, y0], [x1, y1]]; near: (points (n, 2), radius) keeps
    only samples within radius of any point (render views). Steep ground, water, routes and sites are left bare."""
    if mats.ground is None:
        return np.zeros((0, 6))
    (x0, y0), (x1, y1) = box or T.spec["extent"]
    out = []
    for ki, kind in enumerate(kinds):
        sp = CLUTTER[kind]
        ys = np.arange(y0, y1, sp)
        rows = max(1, int(1_000_000 // max(1, len(np.arange(x0, x1, sp)))))  # (in strips: a big map is 10^7 samples)
        for r0 in range(0, len(ys), rows):
            C = _clutter_strip(T, mats, field, kind, ki, np.arange(x0, x1, sp), ys[r0:r0 + rows], sp, near,
                               np.random.default_rng([seed, ki, r0]))
            if len(C):
                out.append(C)
    return np.concatenate(out) if out else np.zeros((0, 6))


def _clutter_strip(T, mats, field, kind, ki, xs, ys, sp, near, rng):
    out = []
    if True:
        gx, gy = np.meshgrid(xs, ys)
        xy = np.c_[gx.ravel(), gy.ravel()]
        xy = xy + rng.uniform(-0.45, 0.45, xy.shape) * sp
        if near is not None:
            from scipy.spatial import cKDTree
            d, _ = cKDTree(np.asarray(near[0], float)[:, :2]).query(xy)
            xy = xy[d < near[1]]
        if not len(xy):
            return np.zeros((0, 6))
        h, cs = field.column(xy[:, 0], xy[:, 1])
        P = np.c_[xy, h]
        ok = cs > 0.82  # (under ~35 deg)
        if mats.sea is not None:
            ok &= h > mats.sea - 0.2
        if not np.isnan(T.water).all():
            wet = mats._grid((~np.isnan(T.water)).astype(float), xy) > 0.3
            if mats.sea is None:
                ok &= ~wet
        for m in ("routes", "sites"):
            if m in T.masks:
                ok &= mats._grid(np.asarray(T.masks[m], float), xy) < 0.2
        P = P[ok]
        if not len(P):
            return np.zeros((0, 6))
        N = np.tile([0.0, 0.0, 1.0], (len(P), 1))
        kd = mats.kinds(P)
        u = rng.random(len(P))
        if kind == "bush":
            sc, clump = mats.ground.scrub(mats, P, kd.get("scrub", 0.0), np.clip(kd.get("rough", 0.0) +
                                                                                 kd.get("scrub", 0.0), 0, 1))
            p = sc * clump * 0.9
        elif kind == "tussock":
            sc, _ = mats.ground.scrub(mats, P, kd.get("scrub", 0.0), kd.get("rough", 0.0))
            p = np.clip(kd.get("rough", 0.0), 0, 1) * (1 - sc) * 0.6
        else:  # (on the ground the maps make rock: never on a beach's sand)
            rock, _, shore, _ = mats.ground.rock(mats, P, N)
            Wl, _ = mats.weights(P, N)
            wr = sum(Wl[:, mats.layers.index(k)] for k in ("rock", "wet_rock") if k in mats.layers)
            p = np.clip(wr, 0, 1) * (shore * 0.35 + np.clip(rock - shore, 0, 1) * 0.12)
        keep = u < p
        n = int(keep.sum())
        if n:
            out.append(np.c_[P[keep], np.full(n, ki), rng.uniform(0.6, 1.4, n), rng.uniform(0, 360, n)])
    return np.concatenate(out) if out else np.zeros((0, 6))
