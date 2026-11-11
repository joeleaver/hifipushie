"""`build`: one variant from its style (field, mesh, LODs, bake), and the tone range. Part of clutter (clutter.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import clutter
from .clutter import resolve
from .clutter_bake import bake_variant
from .clutter_mesh import _hull, _mesh, _onto, _volume, cluster_lod, lod_mesh, mesh_check, silhouette_iou, wood_lod
from .clutter_solid import Solid, bush_cards, spray_tile

# -------------------------------------------------------------------------------------------------------- building
def build(spec: dict, progress=None) -> dict:
    """Make the asset: every variant's LODs + collision hull and the shared atlas. Returns {"cfg", "variants": [{"name",
    "lods": [mesh...], "collision": (V, F) | None, "size", "height", "sink"}], "albedo", "normal", "orm"} (pictures
    0..1 floats; meshes Z up in metres, pivot on the ground line)."""
    cfg = resolve(spec)
    if cfg["shape"] == "bush" and cfg["form"].get("open", True):
        from . import clutter_bush
        return clutter_bush.build(spec, progress)
    nv = cfg["variants"]
    bush = cfg["shape"] == "bush"
    grid = 3 if bush else 1 if nv == 1 else 2 if nv <= 4 else 3
    base = cfg["atlas"]
    cell = base // grid
    albs = {se: np.zeros((base, base, 4)) for se in cfg["seasons"]}
    for a_ in albs.values():
        a_[..., :3] = cfg["color"]
        a_[..., 3] = 1.0
    if bush:  # a bark patch for stems: the last cell
        bk = np.clip(np.asarray(cfg["color"]) * [1.15, 0.8, 0.65] * 0.5, 0, 1)
        for a_ in albs.values():
            a_[2 * cell: 3 * cell, 2 * cell: 3 * cell, :3] = bk
    tiles = []
    if bush and cfg["form"]["cards"][1] > 0:  # the sprays' pictures: the cells after the variants'
        for t in range(grid * grid - nv - 1):
            c = nv + t
            x0, y0 = (c % grid) * cell, (c // grid) * cell
            tiles.append((x0, y0, cell))
            for se, sv in cfg["seasons"].items():
                rgb, al = spray_tile(cell, cfg["paint"], cfg["color"], sv, cfg["seed"] * 100 + t)
                albs[se][y0: y0 + cell, x0: x0 + cell, :3] = rgb
                albs[se][y0: y0 + cell, x0: x0 + cell, 3] = al
    nrm = np.zeros((base, base, 3))
    nrm[..., 2] = 1
    orm = np.ones((base, base, 3))
    orm[..., 2] = 0
    out = []
    for k in range(nv):
        solid = Solid(cfg, k)
        vol, ax, vox = _volume(solid, 96 if solid.cluster or solid.wood else 80)
        V, F = _mesh(vol, ax, vox)
        V = _onto(solid.sd, V, vox * 0.5, 1)
        solid.lo, solid.hi = V.min(0) - vox, V.max(0) + vox  # (the charts' frame: tight round the form)
        # normalise: largest plan dimension 1 m, centred in plan, the ground line `sink` of the height above the bottom
        lo, hi = V.min(0), V.max(0)
        plan = float(max(hi[0] - lo[0], hi[1] - lo[1]))
        height = float(hi[2] - lo[2])
        sink = cfg["form"]["sink"] * height
        if bush:
            sink = float(solid.parts[0].ground_z - lo[2])
            height = float(hi[2] - solid.parts[0].ground_z)
        scale = 1.0 / plan
        shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -(lo[2] + sink)])
        origin = np.array([(k % grid) * cell, (k // grid) * cell], float)
        seed = cfg["seed"] * 1000 + k
        lods, ious = [], []
        for j, tgt in enumerate(cfg["lods"]):
            tgt = int(round(tgt * solid.lods_x))
            single = cfg["shape"] in ("rock", "bush") and not solid.cluster
            hull = single and tgt <= 40  # (a near-convex stone's last LOD: its hull, never a folded sliver)
            pre = None
            if solid.wood and (j or len(solid.parts) > 1):  # built tubes: LOD 1 five sides, LOD 2 three; a jam always
                sides, rings = ((7, 6) if j == 0 else (5, 5) if j == 1 else (3, 4))
                stubs = j < 2
                while True:
                    pre = wood_lod(solid, sides, rings, stubs=stubs)
                    if len(pre[1]) <= 1.1 * tgt or (sides == 3 and rings == 2 and not stubs):
                        break
                    if sides == 3 and rings == 2:  # still over with every stub and root as a tube: the stems alone
                        stubs, sides, rings = False, 5, 5
                        continue
                    sides, rings = (sides - 1, rings) if sides > 3 else (sides, rings - 1)
            elif solid.cluster and cfg["shape"] != "wood" and (len(solid.parts) > 2 or getattr(solid, "lumpy", False)):  # a patch of stones / a bush's lumps: a hull each
                pre = cluster_lod(V, F, tgt)
            L = lod_mesh(solid, V, F, tgt, cfg, cell, origin, base, vox * 0.5, hull=hull, pre=pre)
            bad = False
            if pre is None and not hull:
                chk = mesh_check(L["V"], L["F"])
                bad = L["triangles"] > 1.3 * tgt or chk["open_edges"] > 0 or chk["nonmanifold_edges"] > 0
            if bad and cfg["shape"] in ("rock", "bush") and not (solid.cluster and len(solid.parts) > 2):  # stalled or torn: its hull
                L = lod_mesh(solid, V, F, tgt, cfg, cell, origin, base, vox * 0.5, hull=True)
            if bad and solid.wood:  # built tubes
                sides, rings = 8, 6
                while True:
                    pre = wood_lod(solid, sides, rings, True)
                    if len(pre[1]) <= 1.1 * tgt or sides == 3:
                        break
                    sides -= 1
                L = lod_mesh(solid, V, F, tgt, cfg, cell, origin, base, vox * 0.5, pre=pre)
            iou = float(np.mean(silhouette_iou((lods[0]["V"], lods[0]["F"]), (L["V"], L["F"])))) if j else 1.0
            if j and pre is None and cfg["shape"] == "rock" and not hull and iou < clutter.LOD_IOU and not (solid.cluster and len(solid.parts) > 2):  # the decimation changed the outline: the hull keeps it
                L2 = lod_mesh(solid, V, F, tgt, cfg, cell, origin, base, vox * 0.5, hull=True)
                i2 = float(np.mean(silhouette_iou((lods[0]["V"], lods[0]["F"]), (L2["V"], L2["F"]))))
                if i2 > iou:
                    L, iou = L2, i2
            L["iou"] = round(iou, 3)
            lods.append(L)
        a_, n_, o_, fill_ = bake_variant(cfg, solid, vol, ax, vox, cell, seed, low=(lods[0], lods[0]["UV"] * base - origin), ground=float(lo[2] + sink))
        if cfg["material"] == "rock" and cfg["paint"].get("tone_range"):
            a_ = tone_range(a_, fill_, cfg["color"], cfg["paint"]["tone_range"])
        sl = (slice(int(origin[1]), int(origin[1]) + cell), slice(int(origin[0]), int(origin[0]) + cell))
        nrm[sl], orm[sl] = n_, o_
        for se in albs:
            albs[se][sl][..., :3] = a_[se]
        for j, L in enumerate(lods):
            if bush:  # wind channels; the sprays joined on
                Bz = solid.parts[0].H
                tr = np.clip(L["V"][:, 2] / Bz, 0, 1.3) ** 1.5
                L["wind"] = np.c_[tr, 0.2 * tr, np.full(len(tr), 0.37 * k % 1.0), np.zeros(len(tr))]
                sh = cfg["form"]["cards_lod"]
                C = bush_cards(solid, cfg, k, sh[min(j, len(sh) - 1)], 1.0 + 0.25 * j, tiles, base)
                if C is not None:
                    o = len(L["V"])
                    for key in ("V", "N", "UV", "T", "wind"):
                        L[key] = np.r_[L[key], C[key]]
                    L["F"] = np.r_[L["F"], C["F"] + o]
                    L["triangles"] = int(len(L["F"]))
                    L["cards"] = int(len(C["F"]) // 4)
                if solid.parts[0].stems:  # the lumps' stems: 3-sided tubes, their colour a bark patch in the atlas's last cell
                    from .clutter_bush import _tube
                    for pts, rr in solid.parts[0].stems:
                        Vs, Ns, Fs = _tube(pts, rr, 3, 3 if j < 2 else 2)
                        o = len(L["V"])
                        ts = np.clip(Vs[:, 2] / Bz, 0, 1.3) ** 1.5
                        L["V"] = np.r_[L["V"], Vs]
                        L["N"] = np.r_[L["N"], Ns]
                        L["UV"] = np.r_[L["UV"], np.tile([(2.5 * cell) / base, (2.5 * cell) / base], (len(Vs), 1))]
                        L["T"] = np.r_[L["T"], np.tile([1.0, 0, 0, 1.0], (len(Vs), 1))]
                        L["wind"] = np.r_[L["wind"], np.c_[ts, 0.2 * ts, np.full(len(ts), 0.37 * k % 1.0), np.zeros(len(ts))]]
                        L["F"] = np.r_[L["F"], Fs + o]
                    L["triangles"] = int(len(L["F"]))
            L["V"] = (L["V"] + shift) * scale
        col = None
        if cfg["collision"] == "convex":
            col = _hull((lods[min(1, len(lods) - 1)]["V"]), 24)
        out.append({"name": f"v{k}", "lods": lods, "collision": col, "height": round(height * scale, 4),
                    "sink": round(max(sink, 0.0) * scale, 4), "bounds": [((lo + shift) * scale).round(4).tolist(), ((hi + shift) * scale).round(4).tolist()]})
        if progress:
            progress(f"{cfg['kind']} {cfg['style']} variant {k}: " + " / ".join(str(L["triangles"]) for L in lods) + " triangles")
    return {"cfg": cfg, "variants": out, "albedo": albs, "normal": nrm * 0.5 + 0.5, "orm": orm}


def tone_range(albs: dict, filled, color, rng) -> dict:
    """A rock variant's pictures brought into the tone RANGE of a cliff of the same rock. The painted shading (gradient,
    top light, cavity, face tones, ink) spread the albedo's linear luminance over 0.15 .. 2.9 of its mean (cartoon) where
    the terrain's rock texture holds 0.9 .. 1.1, and its mean sat 40% under the colour the json states: tinted by
    mean colour alone a boulder was charcoal with chalk tops beside a tan cliff. Here the luminance over its mean is
    raised to the power that brings p5 .. p95 inside `rng` (never widened), and the picture's mean luminance is set to
    the stated colour's, so `color_linear` in the json is what the pictures hold. Hue is kept (lichen, minerals).
    The power and the scale come from the summer picture and are used for every season. sRGB in, sRGB out."""
    from .terrain_style import _srgb_lin as lin
    w = np.array([0.2126, 0.7152, 0.0722])
    ref = albs.get("summer", next(iter(albs.values())))
    m = filled if filled is not None and filled.any() else np.ones(ref.shape[:2], bool)
    L = np.maximum(lin(ref) @ w, 1e-5)
    mu = float(L[m].mean())
    p5, p95 = np.percentile(L[m] / mu, [5, 95])
    g = min(1.0, math.log(rng[1] / rng[0]) / max(math.log(max(p95, 1e-4) / max(p5, 1e-4)), 1e-6))
    target = float(np.asarray(lin(np.asarray(color, float))) @ w)
    k = target / float((((L[m] / mu) ** g)).mean())
    out = {}
    for se, a in albs.items():
        al = lin(a)
        Ls = np.maximum(al @ w, 1e-5)
        al = al * (k * (Ls / mu) ** g / Ls)[..., None]
        al = np.clip(al, 0, 1)
        out[se] = np.where(al <= 0.0031308, al * 12.92, 1.055 * al ** (1 / 2.4) - 0.055)
    return out
