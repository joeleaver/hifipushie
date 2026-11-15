"""The bake: inner paint, the face's keep paint, the lip floor, and `bake`. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np

from . import asset
from .asset_budget import margin_px
from .asset_raster import (
    _across_seams, _corners, _dilate, _fill_missed_3d, _project, _srgb, _unit, rasterize, uv_islands,
)

def inner_paint(parts: dict, topo: dict, head: dict, log: list) -> None:
    """A GNM head's inner lip rolls (skin_features_mouth.inner_lip_values by GNM vertex) as each low-poly corner's
    "inner_paint" weight, which bake() lays over the scene's colour: the scene's surface has no rolls with the lips
    closed (the fill behind the seam), so what the bake found there was the skin beside the seam."""
    from . import skin_features_mouth
    val = skin_features_mouth.inner_lip_values(head)
    if val is None:
        return
    deep = skin_features_mouth.mouth_interior_values(head)
    if deep is None:
        deep = np.zeros(len(val))
    on_sock = deep > 0
    val = np.where(on_sock, 1.0, val)  # the sock is wet mucosa too: red at the rim, darkening inward
    for pn, (tp, _) in topo.items():
        z = np.load(tp)
        if pn not in parts or "gnm" not in z.files or len(z["verts"]) != len(parts[pn]["verts"]):
            continue
        gi = np.asarray(z["gnm"], int)
        v = np.where((gi >= 0) & (gi < len(val)), val[np.clip(gi, 0, len(val) - 1)], 0.0)
        dv = np.where((gi >= 0) & (gi < len(deep)), deep[np.clip(gi, 0, len(deep) - 1)], 0.0)
        parts[pn]["inner_paint"] = np.stack([v, dv], 1)[parts[pn]["corner_vert"]].astype(np.float32)
        log.append(f"{pn}: the lips' inner rolls painted on {int((v > 0.99).sum())} vertices (GNM's rings to the "
                   f"contact ring)")


def face_keep_paint(parts: dict, topo: dict, log: list) -> None:
    """(one mesh, retopo.FACE_KEEP) each low-poly corner's "keep" weight: 1 where the head's surface IS the approved GNM
    head (retopo_wrap.face_keep: eyes, mouth, nose), fading over its rings. bake() doesn't project those texels onto the field:
    the field is the smoothed copy of that head (the lips up to 6.6 mm off, game_ready.md r42), so projected, the lips'
    texels went astray (r41's lip gate 2.69 -> 4.27% with the lids kept) and their normals were the smoothed lips'."""
    from . import retopo
    from . import retopo_wrap
    if not retopo.FACE_KEEP:
        return
    for pn, (tp, _) in topo.items():
        z = np.load(tp)
        if pn not in parts or "gnm" not in z.files or len(z["verts"]) != len(parts[pn]["verts"]):
            continue
        L, S = np.asarray(z["loops"], int), np.asarray(z["sizes"], int)
        faces = np.split(L, np.cumsum(S)[:-1])
        w = retopo_wrap.face_keep(np.asarray(z["gnm"], int), faces)
        parts[pn]["keep"] = w[parts[pn]["corner_vert"]].astype(np.float32)[:, None]
        log.append(f"{pn}: {int((w > 0.999).sum())} vertices of the approved face kept, not projected in the bake")


def lip_floor_mask(spec: dict, X: np.ndarray, n: np.ndarray) -> np.ndarray:
    """0..1 per surface point (Blender coords, normals): the skin's lower-lip zone, where bake() floors the roughness at
    LIP_FLOOR_ROUGHNESS. Zeros without a skin or its lip landmarks."""
    from . import paint_apply
    from .surface import Points
    sk = spec.get("skin") or {}
    if not sk or not len(X):
        return np.zeros(len(X))
    try:
        pts = Points(spec, X, n, np.zeros(len(X), int), [sk.get("part", "body")], 0.001)
        pts.footprint = 0.0005
        from . import skin_zones
        ly = skin_zones.expand_zones(spec, {"mask": [asset.LIP_FLOOR_ZONE]}, "lip floor")
        return paint_apply.layer_mask(spec, "lip_floor", ly, paint_apply._View(pts, np.arange(len(X))))
    except (KeyError, ValueError):  # (no lip landmarks on this model: no floor)
        return np.zeros(len(X))


def lip_front_share(P: np.ndarray, bad: np.ndarray, lipw: np.ndarray) -> tuple[float | None, int]:
    """The share of the lips' FRONT band texels whose projection went astray (bake), and their count (None under
    50 texels). The band: in front of the inner rolls (lipw > 0.5: hidden in the closed seam, ~28% astray even when
    clean, so left out), within 1.2 half-widths across and 0.6 up / down of the rolls' centre (Blender axes, faces
    -y). Clean (retopo.SOCK_FALLOFF 0, v31/v37) 2.5%, x32's torn streaks (6) 6.5% (tests/test_lip_astray.py)."""
    rolls = lipw > 0.5
    if rolls.sum() < 50:
        return None, 0
    r = P[rolls]
    c = r.mean(0)
    hw = np.abs(r[:, 0] - c[0]).max()
    Q = P - c
    lips = (np.abs(Q[:, 0]) < 1.2 * hw) & (np.abs(Q[:, 2]) < 0.6 * hw) & (Q[:, 1] < 0) & ~rolls
    if lips.sum() < 50:
        return None, 0
    return float(bad[lips].mean()), int(lips.sum())


def bake(parts: dict, size: int, ctx: dict, log: list, atlas: int | None, given: dict) -> dict:
    """Every map of one atlas (None: all parts) as float arrays (size, size, k), plus the height range. Each
    texel is projected onto its export part's own field (normal, height); given: the maps Cycles baked from the
    scene (`scene_maps`: color linear, rms, ao, height; rows top first) for paint, AO and painted relief."""
    t0 = time.time()
    names = list(parts)
    # the islands' own texels plus a ring past their edges (half the gap between islands): extrapolated, so
    # bilinear filtering at a chart's edge reads the surface beyond it on both sides of a seam
    (ys, xs), tri, bary, tpart, inside, drawn = rasterize(parts, size, atlas, ring=max(1, margin_px(size) // 2))
    log.append(f"rasterized {drawn.sum()} texels ({drawn.sum() / size ** 2:.0%} of the atlas) + {(~drawn).sum()} "
               f"past the islands' edges in {time.time() - t0:.1f}s")

    def interp(key):
        return np.einsum("nk,nkc->nc", bary, _corners(parts, key)[tri])

    P, Nl, T = interp("pos"), _unit(interp("normal")), interp("tangent")
    sgn = np.sign(interp("sign")[:, 0])
    sgn[sgn == 0] = 1
    T = _unit(T - Nl * (T * Nl).sum(1, keepdims=True))
    B = sgn[:, None] * np.cross(Nl, T)
    part = tpart[tri]

    # project onto the exact surface of the texel's own part
    X, G = P.copy(), Nl.copy()
    lip_astray = {}
    t1 = time.time()
    island = uv_islands(parts)[tri]
    # the lips' texels (inner_paint's roll weight > 0: GNM's rings from the sock to past the contact ring), so a
    # projection that goes astray there is named on its own: a whole-part share hid x32's torn lip streaks
    # (3.75 -> 4.89% of the head, ~all of the rise in the lips' band; game_ready.md r20/r21)
    lipw = None
    if any("inner_paint" in p for p in parts.values()):
        # (column 1 = the mouth sock's depth: the sock takes column 0 = 1 too, but lies hidden behind the closed
        # lips, where a projection astray is expected; only the lips' own rolls count)
        lc = np.concatenate([(np.where(p["inner_paint"][:, 1] > 0, 0.0, p["inner_paint"][:, 0]) if "inner_paint" in p
                              else np.zeros(len(p["corner_vert"]))).reshape(-1, 3) for p in parts.values()]).astype(np.float64)
        lipw = (bary * lc[tri]).sum(1)
    kw = None
    if any("keep" in p for p in parts.values()):  # (face_keep_paint: the approved face is the low poly itself)
        for p_ in parts.values():
            p_.setdefault("keep", np.zeros((len(p_["corner_vert"]), 1), np.float32))
        kw = np.clip(interp("keep")[:, 0], 0, 1)
    for pi, pn in enumerate(names):
        sel = np.flatnonzero(part == pi)
        if not len(sel):
            continue
        vx = ctx["frames"][pn][1]
        x, g = _project(ctx["streams"][pn], X[sel], ys[sel], xs[sel], island[sel], vx)
        if kw is not None:  # kept: the low poly's own position / normal (fading out over the keep's rings)
            k_ = kw[sel][:, None]
            x = P[sel] + (1 - k_) * (x - P[sel])
            g = _unit(k_ * Nl[sel] + (1 - k_) * _unit(g))
        # a texel that wandered off (onto the far side of a thin sheet, or out of a thin gap) keeps the low-poly
        # surface. Steep but outward normals (a shingle's butt end, a board's edge) are real detail: keep those.
        bad = (np.linalg.norm(x - P[sel], axis=1) > 6 * vx) | ((_unit(g) * Nl[sel]).sum(1) < -0.2)
        x[bad], g[bad] = P[sel][bad], Nl[sel][bad]
        X[sel], G[sel] = x, _unit(g)
        if bad.any():
            log.append(f"  {pn}: {bad.mean():.2%} of texels kept the low-poly surface (projection went astray)"
                       + (": WARNING, the low poly is too far from thin geometry: raise its triangle_weight "
                          "(or min_triangles)" if bad.mean() > 0.2 else ""))
        if os.environ.get("HP_ASTRAY_DUMP"):  # (debug: where the astray texels are, to compare two exports)
            np.savez(Path(os.environ["HP_ASTRAY_DUMP"]) / f"astray_{pn}_{atlas}.npz", P=P[sel], bad=bad,
                     lipw=lipw[sel] if lipw is not None else np.zeros(len(sel)))
        share, nl = lip_front_share(P[sel], bad, lipw[sel]) if lipw is not None else (None, 0)
        if share is not None:
            lip_astray[pn] = share
            log.append(f"  {pn}: {share:.2%} of the lips' {nl} front texels kept the low-poly surface"
                       + (f": WARNING, the lips' texels projected astray (over {asset.LIP_ASTRAY_WARN:.1%}): torn streaks "
                          f"bake into the lips (the mouth sock moved onto their exact surface? retopo.SOCK_FALLOFF)"
                          if share > asset.LIP_ASTRAY_WARN else ""))
    log.append(f"projected onto the exact surface in {time.time() - t1:.1f}s")
    # texels whose ray found no scene mesh (alpha 0) take their nearest baked neighbour
    share = given["color"][..., 3].astype(np.float64)  # (supersampled: the share of the texel's points baked)
    baked = share > 0
    miss = ~baked[ys, xs] & drawn
    if miss.any():
        log.append(f"  {miss.sum() / drawn.sum():.2%} of texels found no scene mesh along their ray: filled from neighbours")
        log.append(f"    {(miss & ~inside).sum() / miss.sum():.0%} of them are edge texels (centre outside its triangle)")
        for pi, pn in enumerate(names):
            m = (miss & inside)[(part == pi) & drawn]
            if m.size and m.mean() > 0.005:
                log.append(f"    {pn}: {m.mean():.1%} of its texels missed inside their triangle")
        given = {k: _dilate(v, baked) for k, v in given.items()}
        if asset.MISS_FILL_3D:
            given = _fill_missed_3d(given, baked, miss & inside, ys, xs, P, part, log)
        if os.environ.get("HP_BAKE_DUMP"):  # (debug, r66: where the missed texels are, to mark them on a crop)
            np.savez(Path(os.environ["HP_BAKE_DUMP"]) / f"miss_{atlas}.npz", P=P[miss], inside=inside[miss],
                     part=part[miss], names=np.array(names), ys=ys[miss], xs=xs[miss], size=size)

    c = _corners(parts, "pos")[np.unique(tri)]  # the atlas's triangles: surface per texel
    area = np.linalg.norm(np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1).sum() / 2
    texel = np.sqrt(area / max(int(drawn.sum()), 1))
    fill = share[ys, xs] < 0.999  # past the islands' edges, edge texels part-baked or missed
    given, baked, n_across = _across_seams(parts, given, baked, share, ys, xs, tri, P, fill, tpart, texel)
    if fill.any():
        log.append(f"  {n_across / fill.sum():.0%} of the texels past the islands' edges (or missed at them) filled "
                   f"across their seam; the rest (open edges) from the nearest texel")
    if "height" in given:
        # painted height baked by Cycles (0.5 + h x 25); its slope across the texture tilts the normal: u runs
        # along the tangent, v (up the texture, rows down) along the bitangent, a texel is `texel` metres
        hi = (given["height"][..., 0].astype(np.float64) - 0.5) / 25.0
        if np.abs(hi[ys, xs]).max() > 1e-6:
            hp = np.pad(hi, 1, mode="edge")
            du = (hp[1:-1, 2:] - hp[1:-1, :-2]) / (2 * texel)
            dv = -(hp[2:, 1:-1] - hp[:-2, 1:-1]) / (2 * texel)
            h0 = hi[ys, xs]
            X = X + h0[:, None] * G  # the height map measures to the painted surface
            G = _unit(G - du[ys, xs][:, None] * T - dv[ys, xs][:, None] * B)  # B is signed: +v
            log.append(f"painted height from the scene's bake (texel {texel * 1000:.2f} mm)")

    if any(parts[pn].get("designed") is not None for pn in names):  # (one mesh, own quads) GNM's interior
        # surfaces (sock, lip rolls, lid insides) are its own, not the field's: projected, the sock's texels read
        # heights of 25 mm and set the whole atlas's height range
        td = np.concatenate([np.asarray(parts[pn]["designed"], bool)[parts[pn]["corner_vert"].reshape(-1, 3)].all(1)
                             if parts[pn].get("designed") is not None else
                             np.zeros(len(parts[pn]["corner_vert"]) // 3, bool) for pn in names])
        dm = td[tri]
        X[dm], G[dm] = P[dm], Nl[dm]
    height = ((X - P) * Nl).sum(1)
    tn = np.stack([(G * T).sum(1), (G * B).sum(1), (G * Nl).sum(1)], -1)
    # a normal map can't point below its surface: detail steeper than 90 deg is bent to the horizon
    tn[:, 2] = np.maximum(tn[:, 2], 0.02)
    tn = _unit(tn)
    filled = np.zeros((size, size), bool)
    filled[ys, xs] = True
    hr = float(max(np.abs(height).max(), 1e-4))
    maps = {}

    def put(name, vals, fill):
        img = np.full((size, size, vals.shape[1]), fill, np.float64)
        img[ys, xs] = vals
        maps[name] = _dilate(img, filled)
    # Cycles' channels keep their own texels past the islands' edges too (the bake's margin, filled across each
    # seam from the adjacent faces): only what lies beyond them is filled from the nearest texel
    own = baked.copy()
    own[ys[drawn], xs[drawn]] = True

    def put_given(name, img):
        maps[name] = _dilate(img.astype(np.float64), own)
    lin = given["color"][..., :3].astype(np.float64)
    if any("inner_paint" in p for p in parts.values()):  # (inner_paint: the lips' rolls, hidden in the scene)
        from . import skin_features as sfe
        for pn_, p_ in parts.items():
            p_.setdefault("inner_paint", np.zeros((len(p_["corner_vert"]), 2), np.float32))
        ip_ = interp("inner_paint")
        w_ = np.zeros(lin.shape[:2] + (2,))
        w_[ys, xs] = np.clip(ip_[:, :2], 0, 1)
        w_ = _dilate(w_, own)
        d_ = w_[..., 1:2]
        w_ = w_[..., 0]
        inner_c = (1 - d_) * np.asarray(sfe.INNER_LIP_COLOR, float) + d_ * np.asarray(sfe.MOUTH_DEEP_COLOR, float)
        lin = lin * (1 - w_[..., None]) + inner_c * w_[..., None]
        if os.environ.get("HP_BAKE_DUMP"):  # (debug, r70: Tess's ala patch is this overlay at w = 1, deep = 1 exactly,
            # on texels whose GLB triangles carry no paint: which bake-time triangle / uv put it there)
            np.savez(Path(os.environ["HP_BAKE_DUMP"]) / f"inner_{atlas}.npz", ys=ys, xs=xs, tri=tri, part=part,
                     drawn=drawn, ip=ip_[:, :2].astype(np.float32), P=P.astype(np.float32), names=np.array(names),
                     raw=given["color"].astype(np.float16), own=own, w=w_.astype(np.float16), d=d_[..., 0].astype(np.float16),
                     **{f"uv_{pn_}": p_["uv"] for pn_, p_ in parts.items()},
                     **{f"cv_{pn_}": p_["corner_vert"] for pn_, p_ in parts.items()},
                     **{f"v_{pn_}": p_["verts"] for pn_, p_ in parts.items()})
        rms = given["rms"].astype(np.float64).copy()
        rms[..., 0] = rms[..., 0] * (1 - w_) + asset.INNER_PAINT_ROUGHNESS * w_
        given = {**given, "rms": rms}
    lf = ctx.get("lip_floor")  # (r66) the lower lip never glossier than LIP_FLOOR_ROUGHNESS (skin's lower-lip zone)
    if lf is not None and lf[1] in names and asset.LIP_FLOOR_ROUGHNESS > 0:
        sel = np.flatnonzero(part == names.index(lf[1]))
        mk = lip_floor_mask(lf[0], P[sel], Nl[sel]) if len(sel) else np.zeros(0)
        if (mk > 0).any():
            rms = given["rms"].astype(np.float64).copy()
            r_ = rms[ys[sel], xs[sel], 0]
            rms[ys[sel], xs[sel], 0] = r_ + mk * np.maximum(asset.LIP_FLOOR_ROUGHNESS - r_, 0)
            given = {**given, "rms": rms}
            on = mk > 0.5
            log.append(f"lip floor: {int(on.sum())} lower-lip texels, roughness mean {r_[on].mean():.3f} -> "
                       f"{rms[ys[sel][on], xs[sel][on], 0].mean():.3f} (floor {asset.LIP_FLOOR_ROUGHNESS})" if on.any() else
                       "lip floor: no texel over half in the lower-lip zone")
    sf = ctx.get("skin_fade")  # (sh8) the short hair's edge fade (hair_fade) baked into the head's base colour: any
    # engine shows it with no extra maps or formula (the look lays the same map on in blender_cards.skin_fade)
    if sf is not None and sf["part"] in names:
        from . import hair_fade
        sel = np.flatnonzero(part == names.index(sf["part"]))
        if len(sel):
            lin = lin.copy()
            new_, a_ = hair_fade.bake_into(lin[ys[sel], xs[sel]], X[sel], sf["map"])
            lin[ys[sel], xs[sel]] = new_
            log.append(f"hair fade: baked into {sf['part']}'s base colour: {int((a_ > 0.05).sum())} texels "
                       f"(alpha mean {float(a_[a_ > 0.05].mean()) if (a_ > 0.05).any() else 0:.2f}); roughness unchanged")
    rc = ctx.get("recolour")  # (export_asset recolour_masks) neutral base + channel masks over the masked parts
    channels = None
    if rc is not None and rc["atlas"] == atlas:
        from . import asset_recolour
        # (filled out first: the masks reach past the islands, so the neutral base must too)
        lin, masks_, channels = asset_recolour.apply(_dilate(lin, own), rc, names, ys, xs, part, drawn, baked, filled, log)
        for k_, m_ in enumerate(masks_):
            maps[f"mask{k_}"] = m_
    if channels is None:
        put_given("basecolor", _srgb(lin))
    else:  # (already filled past the islands, then neutral by the masks' own labels: a second fill would undo it there)
        maps["basecolor"] = _srgb(lin)
    put_given("roughness", given["rms"][..., :1])
    put_given("metallic", given["rms"][..., 1:2])
    put_given("specular", given["rms"][..., 2:3])
    ao_ = given["ao"][..., :1].astype(np.float64)
    off_ = [names.index(pn_) for pn_ in (ctx.get("ao_off") or ()) if pn_ in names]
    if off_ and asset.EYES_AO_OFF:  # (the eyeball: its baked AO is the lids' shadow in the rest pose, wrong once a lid moves)
        m_ = np.isin(tpart[tri], off_)  # (tpart is per triangle)
        ao_ = ao_.copy()
        ao_[ys[m_], xs[m_]] = 1.0
        log.append(f"ao: {', '.join(names[i] for i in off_)} left unoccluded ({int(m_.sum())} texels): the lids move")
    put_given("ao", ao_)
    if "blink" in given:   # (skin) the crease line and the lid's occlusion as their own multiplier map, out of basecolor
        # (sRGB-encoded like basecolor: the notes declare it sRGB, as engines sample colour maps. Written as the raw
        # linear ratio it was decoded to ~ratio^2.2: the lids' crease and occlusion twice as dark and orange, expr_r15)
        put_given("blink", _srgb(given["blink"][..., :3]))
    put("normal", tn * 0.5 + 0.5, 0.5)
    put("height", (height / hr * 0.5 + 0.5)[:, None], 0.5)
    maps["orm"] = np.concatenate([maps["ao"], maps["roughness"], maps["metallic"]], -1)
    return {"maps": maps, "height_range": hr, "coverage": float(drawn.sum()) / size ** 2, "lip_astray": lip_astray,
            **({"recolour": channels} if channels is not None else {})}
