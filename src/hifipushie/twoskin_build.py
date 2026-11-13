"""Build one continuous surface of a creature straight from what its pictures show, as a solid of two skins
(twoskin.py): the front picture's surface and the back picture's, joined at the outline.

A `group` is the masses that make ONE surface as the front and back pictures show it (a head with its eyes and
ears): no borders are cut between them, so none can tear. A mass that stands in front with air behind it (a can in
the mouth), or that runs away from the viewer (a horn curling back: neither picture shows its length), is left
out and built on its own; where it hides the group, the skin is carried through smoothly underneath.

Both skins are solved on the FRONT picture's grid (its outline is the solid's; the back picture's read is laid
onto it mirrored, world place for world place). Each is the read's slopes (surfaceread.py) added up over the
group's whole outline, held in three ways, which also give the read its true depth (its gain):
  the outline       where it is the figure's own, both skins to ONE depth, the block-in clay's mid-depth there:
                    front and back meet in an edge, as a closed surface does where it turns away
  the middle line   to the profile the side view shows of the group's middle mass (`main`), gently, over a band
  seated parts      (`seat`: ears, whatever stands off to one side) softly to the block-in clay's own surface: the
                    marks in the other views say where such a part sits in depth and how thick it is
The block-in under the group is then taken out of the clay: it was scaffolding. The side picture's detail is
pressed on afterwards (relief_press.py).
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

from . import featuremap, featuresee, relief_press as rp, surfaceread, twoskin
from .spec import compile_prims

OUTLINE_W = 1.0    # how hard both skins are held to the one depth at the figure's outline
MIDDLE = 0.006     # m: the middle line is held over a band this wide either side
MIDDLE_W = 0.05    # how hard, per pixel of the band
SEAT_W = 0.02      # how hard a seated part is held to the block-in's surface
THIN = 0.004       # m: the two skins are never closer than this inside the outline


def _stands_on(fm: dict, f: str, group) -> bool:
    seen = set()
    f = fm["features"][f].get("on")
    while f and f in fm["features"] and f not in seen:
        if f in group:
            return True
        seen.add(f)
        f = fm["features"][f].get("on")
    return False


def footprint(name: str, fm: dict, group, view: str):
    """(the group's whole outline in the view, what the view shows of it): view-pixel masks. The second leaves out
    every mass that stands on the group without being of it."""
    feats = fm["features"]
    marks = [featuremap.mask(name, g, view) for g in group if view in feats[g]["marks"]]
    if not marks:
        raise ValueError(f"none of {list(group)} is marked in {view!r}")
    foot = np.any(marks, 0)
    for f, c in feats.items():
        if c.get("kind") == "form" and view in c["marks"] and featuresee._mass_of(fm, f) in group:
            foot |= featuremap.mask(name, f, view)
    data = foot.copy()
    for f, c in feats.items():
        if c.get("kind") == "mass" and f not in group and view in c["marks"] and _stands_on(fm, f, group):
            data &= ~featuremap.mask(name, f, view)
    return foot, data


def _read(name: str, fm: dict, group, main: str, view: str, seat=()) -> dict:
    """A view's read of the group on that view's own grid: normals, masks, and the grid's place in the world."""
    rec = fm["views"][view]
    foot_v, data_v = footprint(name, fm, group, view)
    img, box, zoom = rp.closeup(rec, foot_v)
    n = surfaceread.normals([img])[0]
    h, w = n.shape[:2]
    S = rp.SUB
    H2, W2 = h // S, w // S

    def pooled(a, how, soft=True):
        a = np.asarray(Image.fromarray(a[box[1]:box[3], box[0]:box[2]].astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 127
        a = getattr(a[:H2 * S, :W2 * S].reshape(H2, S, W2, S), how)((1, 3))
        return ndimage.gaussian_filter(a.astype(float), 1.5) > 0.5 if soft else a

    full = pooled(foot_v, "all")
    nm = n[:H2 * S, :W2 * S].reshape(H2, S, W2, S, 3).mean((1, 3))
    nm /= np.maximum(np.linalg.norm(nm, axis=-1, keepdims=True), 1e-6)
    k = rec["m_per_px"]
    za, zb = rp._zfit(name, fm, main, view)
    F, U = (np.array(v) for v in rp.FRAMES[rec["kind"]])
    into = np.zeros(full.shape, bool)       # what the group stands on: where the two meet, the surface runs on
    up, seen_up = fm["features"][main].get("on"), set()
    while up and up in fm["features"] and up not in seen_up:
        if view in fm["features"][up]["marks"]:
            into |= pooled(featuremap.mask(name, up, view), "any", soft=False)
        seen_up.add(up)
        up = fm["features"][up].get("on")
    seats = np.zeros(full.shape, bool)
    for f in seat:
        if f in fm["features"] and view in fm["features"][f]["marks"]:
            seats |= pooled(featuremap.mask(name, f, view), "all")
    return {"normals": nm, "full": full, "seen": pooled(data_v, "all") & full, "seats": seats & full, "into": into & ~full,
            "fig": pooled(np.asarray(Image.open(rec["image"]).convert("RGBA").getchannel("A")) > 127, "any", soft=False),
            "px": k * S / zoom, "za": za, "z0": za * (rec["ground_px"] - box[1]) * k + zb,
            "u0": (box[0] - rec["centre_px"]) * k, "U": U, "F": F, "rec": rec, "box": box, "zoom": zoom}


def _onto(b: dict, f: dict) -> dict:
    """The back view's read laid onto the front's grid, mirrored: the same place in the world, pixel for pixel."""
    H, W = f["full"].shape
    zf = f["z0"] - np.arange(H) * f["px"] * f["za"]
    xf = f["u0"] + np.arange(W) * f["px"]                                  # world x (the front's U is +x)
    rb = (b["z0"] - zf) / (b["px"] * b["za"])
    cb = (-xf - b["u0"]) / b["px"]                                          # the back's U runs along -x
    at = np.meshgrid(rb, cb, indexing="ij")
    ok = (at[0] >= 0) & (at[0] <= b["full"].shape[0] - 1) & (at[1] >= 0) & (at[1] <= b["full"].shape[1] - 1)
    nm = np.stack([ndimage.map_coordinates(b["normals"][..., i], at, order=1, mode="nearest") for i in range(3)], -1)
    nm[..., 0] *= -1.0                                                      # its right is the front's left
    nm /= np.maximum(np.linalg.norm(nm, axis=-1, keepdims=True), 1e-6)
    pick = lambda m: (ndimage.map_coordinates(m.astype(np.float32), at, order=0, mode="constant") > 0.5) & ok
    return {"normals": nm, "seen": pick(b["seen"]) & f["full"], "seats": pick(b["seats"]) & f["full"]}


def _band(zrow: np.ndarray, prof, rec_other: dict, c0: float, px: float, full: np.ndarray):
    """Pins along the middle line: the profile, smoothed past its own pixel steps, over a band of columns."""
    pin, pw = np.full(full.shape, np.nan), np.zeros(full.shape)
    if prof is None:
        return pin, pw, 0
    step = 1.5 * rec_other["m_per_px"]
    seen = np.abs(zrow[:, None] - prof[0][None, :]).min(1) < step           # heights the outline really covers
    e_t = ndimage.gaussian_filter1d(np.interp(zrow, prof[0], prof[1]), max(1.0, 0.004 / px), mode="nearest")
    half = max(1, round(MIDDLE / px))
    n = 0
    for v in np.flatnonzero(seen):
        for c in range(int(round(c0)) - half, int(round(c0)) + half + 1):
            if 0 <= c < full.shape[1] and full[v, c]:
                pin[v, c], pw[v, c] = e_t[v], MIDDLE_W
                n += 1
    return pin, pw, n


def build(name: str, spec: dict, fm: dict, group, main: str | None = None, seat=(), front: str | None = None,
          back: str | None = None) -> tuple[dict, dict]:
    """The spec with the group built as one two-skin solid in place of its block-in clay, and what was done."""
    group = list(group)
    main = main or group[0]
    views = {r.get("kind"): v for v, r in fm["views"].items()}
    front, back = front or views.get("front"), back or views.get("back")
    if not front or not back:
        raise ValueError("a two-skin solid needs a front and a back view of the reference")
    f = _read(name, fm, group, main, front, seat)
    b = _onto(_read(name, fm, group, main, back, seat), f)
    full, px, za = f["full"], f["px"], f["za"]
    H, W = full.shape
    Ff, U, V = f["F"], f["U"], np.array([0.0, 0.0, -1.0])
    o = U * f["u0"] + np.array([0.0, 0.0, f["z0"]])
    zrow = f["z0"] - np.arange(H) * px * za
    # the block-in clay along the grid's rays, from the front and from the back: where each part sits in depth
    prims = compile_prims(spec)
    adds = [p for p in prims if p.op == "add"]
    ys = sorted(float(c @ Ff) for c in (np.min([p.lo for p in adds], 0), np.max([p.hi for p in adds], 0)))
    st = 3
    rr, cc = np.mgrid[0:H:st, 0:W:st]
    P0 = o[None] + cc.reshape(-1, 1) * px * U[None] + rr.reshape(-1, 1) * px * za * V[None]
    zf = (H / rr.shape[0], W / rr.shape[1])

    def up(a):
        return ndimage.zoom(rp._fill(a.reshape(rr.shape)), zf, order=1, mode="nearest")[:H, :W]

    near_f, far_f = rp._hits(prims, P0, Ff, ys[1] + 0.02, ys[0] - 0.02)     # heights t towards the front viewer
    near_b, _ = rp._hits(prims, P0, -Ff, -ys[0] + 0.02, -ys[1] - 0.02)      # heights -t towards the back viewer
    hit = ndimage.zoom((~np.isnan(near_f)).reshape(rr.shape).astype(np.float32), zf, order=1, mode="nearest")[:H, :W] > 0.5
    Bf, Bb, mid = up(near_f), up(near_b), 0.5 * (up(near_f) + up(far_f))
    # Where the group's outline is an edge of the solid (the figure's own outline, or a part standing on the group
    # hides it: the surface still ends there), both skins are held to ONE depth: the clay's mid-depth, carried
    # along the outline where no clay stood and eased along it. Where the group runs on into what it stands on
    # (a head into its neck), the outline is left open.
    rim = full & (ndimage.distance_transform_edt(full) * px < rp.RIM) & ~ndimage.binary_dilation(f["into"], iterations=max(2, round(2 * rp.RIM / px)))
    edge = np.where(rim & hit, mid, np.nan)
    if np.isfinite(edge).any():
        i = ndimage.distance_transform_edt(~np.isfinite(edge), return_distances=False, return_indices=True)
        edge = np.where(rim, edge[tuple(i)], 0.0)
        sg = 0.012 / px
        edge = ndimage.gaussian_filter(edge, sg) / np.maximum(ndimage.gaussian_filter(rim.astype(float), sg), 1e-6)
        edge = np.where(rim, edge, np.nan)
    c0 = (f["rec"]["centre_px"] - f["box"][0]) * f["zoom"] / rp.SUB
    out, abouts = {}, {}
    for key, nm, seen, seats, B, sign, view in (("front", f["normals"], f["seen"], f["seats"], Bf, 1.0, front),
                                               ("back", b["normals"], b["seen"], b["seats"], Bb, -1.0, back)):
        prof = rp.profile(name, fm, main, view)
        pin, pw, n_mid = _band(zrow, prof, fm["views"][prof[2]] if prof else {}, c0, px, full)
        m = seats & seen & hit & ~rim
        pin[m], pw[m] = B[m], SEAT_W
        pin[rim], pw[rim] = sign * edge[rim], OUTLINE_W
        pw[~np.isfinite(pin)] = 0.0
        T, gain = surfaceread.height(nm, full, px, pin=pin, pin_w=pw, data=seen, gain=rp.GAIN)
        out[key] = rp._fill(np.where(full, T.astype(np.float64), np.nan))
        abouts[key] = {"view": view, "gain": round(float(gain), 2),
                       "held": {"outline": int(rim.sum()), "middle_line": n_mid, "seated": int(m.sum())},
                       "hidden": round(float((full & ~seen).sum() / max(full.sum(), 1)), 2)}
    Tf, Tb = out["front"], out["back"]
    inner = ndimage.distance_transform_edt(full) * px
    short = np.clip(np.minimum(THIN, inner) - (Tf + Tb), 0, None) / 2       # the skins may not cross inside
    Tf, Tb = Tf + short, Tb + short

    def cos(t):
        gy, gx = np.gradient(t, px * za, px)
        return np.clip(1.0 / np.sqrt(1.0 + gx ** 2 + gy ** 2), 0.25, 1.0)

    foot = (ndimage.distance_transform_edt(~full) - ndimage.distance_transform_edt(full)) * px
    sha = twoskin.put({"o": o, "U": U, "V": V / za, "F": Ff, "px": px},
                      {"front": Tf, "back": Tb, "foot": foot, "cf": cos(Tf), "cb": cos(Tb)})
    # the block-in under the group was scaffolding: out of the clay (its joints stay: other parts hang on them)
    gone = {e for g in group for e in (fm["features"][g].get("built") or [])}
    gone |= {featuremap.twin(e) for e in list(gone) if featuremap.twin(e)}
    new = {**spec, "bones": {k: v for k, v in spec.get("bones", {}).items() if k not in gone},
           "blobs": {k: v for k, v in spec.get("blobs", {}).items() if k not in gone}}
    bname = f"{main}_skins"
    new["blobs"][bname] = {"shape": "twoskin", "skins": sha}
    thick = (Tf + Tb)[full]
    about = {"blob": bname, "skins": sha, "group": group, "map": [int(W), int(H)], "px_mm": round(px * 1e3, 2),
             "front": abouts["front"], "back": abouts["back"],
             "thick_mm": [round(float(np.percentile(thick, q)) * 1e3, 1) for q in (2, 50, 98)],
             "taken_out": sorted(e for e in gone if e in spec.get("bones", {}) or e in spec.get("blobs", {}))}
    return new, {"about": about, "front": {"normals": f["normals"], "full": full, "T": Tf},
                 "back": {"normals": b["normals"], "full": full, "T": Tb}}
