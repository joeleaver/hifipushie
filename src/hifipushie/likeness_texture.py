"""A reference picture as the head's ALBEDO (the projection test, kept): each fitted reference picture is projected
onto the model through its camera, de-lit roughly, and laid over the skin as an ordinary paint layer (an image decal,
"color": "image") with a confidence mask. General: any one-mesh model with fitted references (human_refs.json:
views + cameras, from human_reference).

What is the picture and what is ours, so nobody is fooled:
- the PICTURE gives the colour where its camera saw skin square-on: the face's zones, brows, stubble shadow, lips,
  lines, as the picture has them and at the picture's resolution (a face 110 px wide is 1.4 mm a pixel: no pores);
- OURS stays everywhere the picture is not trusted: skin turned away from its camera (facing below FACE[0]), hidden
  skin, the ears, the under-side of chin and nose, hair and whatever is not skin-coloured above the brows, the
  eyeballs (their own part), the neck and body; and ours are all the fine relief, roughness and scattering (the layer
  sets colour only), so the procedural pores, wrinkle relief and highlights still shape the surface;
- the light is taken out ROUGHLY: one fitted light (luminance = c0 + w . n on the model's own normals,
  likeness_shape.fit_light), the picture divided by it. Cast shadows, the dark under a brow, a painter's strokes
  and a lamp's colour stay in. A painting is a painting: its brushwork lands on the skin.

How it is laid, so it lands exactly: for each picture an ORTHOGRAPHIC image is made along that camera's axis: every
texel's surface point (the model's own depth) is projected through the fitted perspective camera to read the picture.
That image is a planar decal along the same axis (images.py), so no perspective is lost and the decal follows the
geometry it was made on. Re-make it after the head's shape changes (`stale` says so: the layer stores the head's key).

  make(name, ...)   -> the images + layers (nothing saved)
  apply(name, ...)  -> saved as spec["paint"]["ref_texture_<n>"] (remove=True takes them out)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

FACE = (0.3, 0.65)     # cos of the angle between skin normal and the direction to the picture's camera: no trust .. full
DOWN = (-0.6, -0.25)   # world z of the normal: skin facing down (under chin, under the nose) is not trusted
LIGHT_CLIP = (0.45, 1.8)   # the fitted shading's range (x its mean) the picture is divided by
SKIN_DE = 20.0         # Lab distance from the picture's own skin colour past which a pixel above the brows is hair
OFF_SKIN = 42.0        # ... past which a pixel anywhere off the features is not skin at all (backdrop, cloth)
JAW_CUT = (0.001, 0.008)   # m: the picture ends this far above the jaw's border, fading over this
EAR_REACH = 0.006      # m: no picture this near an ear vertex
FEATHER = 0.004        # m: the mask's soft edge
BLEND = 0.018         # m: inside the picture's OUTER edge its low frequencies are handed over to ours over this distance
BLEND_SIGMA = 0.006   # m: what "low frequencies" means there (a Gaussian's sigma)
EDGE_FADE = 0.010     # m: and its alpha fades over this (on top of FEATHER)
SHINE = (1.22, 0.35)  # a baked highlight: luminance over this x the local (1 cm) mean is compressed to this share
LAYER = "ref_texture"
ORTHO_D = 800.0        # m: the "orthographic" camera's distance


def _lab(rgb):
    rgb = np.asarray(rgb, float) / 255.0
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _sstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _to_lin(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _to_srgb8(lin):
    lin = np.clip(lin, 0, 1)
    return np.clip(np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055) * 255, 0, 255)


def head_key(base: dict) -> str:
    return hashlib.sha1(json.dumps(base.get("head"), sort_keys=True, default=str).encode()).hexdigest()[:12]


def ortho_camera(src_cam: dict, centre, half: float, px_per_m: float) -> dict:
    """A far camera on the picture camera's own axis through `centre`: orthographic for our purposes."""
    n = int(round(2 * half * px_per_m))
    return {"r": list(src_cam["r"]), "yaw": float(src_cam.get("yaw", 0.0)), "centre": [float(x) for x in centre],
            "t": [0.0, 0.0, ORTHO_D], "f": ORTHO_D * px_per_m, "size": [n, n]}


def project(mesh: dict, src_cam: dict, photo: np.ndarray, px_per_m: float | None = None, delight: bool = True,
            skin_tone=None, match: str = "tone") -> dict:
    """One picture onto the head. Returns {"rgba": uint8 (n, n, 4) orthographic image along the camera's axis (alpha =
    confidence), "at", "dir", "up", "size", "light": (c0, w, rms) | None, "coverage": share of the head's texels that
    carry the picture, "px_per_m", "gain"}. skin_tone = sRGB 0..1 the confident skin's median is matched to (match
    "tone": per channel, the picture then gives only its variation about its own mean; "level": lightness only;
    None: as de-lit)."""
    from scipy import ndimage
    from scipy.spatial import cKDTree
    from . import humanfit, likeness as lk
    from . import likeness_shape as ls
    L = np.asarray(mesh["L"], float)
    centre = L[:68].mean(0)
    io = float(np.linalg.norm(L[36:42].mean(0) - L[42:48].mean(0)))
    half = 2.1 * io
    w, h = src_cam["size"]
    Rs = humanfit._cam_rot(src_cam)
    zc = float(((centre - np.asarray(src_cam["centre"], float)) @ Rs.T + np.asarray(src_cam["t"], float))[2])
    density = src_cam["f"] / zc                              # the picture's own pixels per metre at the head
    px_per_m = float(px_per_m or np.clip(2.0 * density, 800, 4000))
    cam = ortho_camera(src_cam, centre, half, px_per_m)
    n = cam["size"][0]
    box = (0.0, 0.0, float(n), float(n))
    _, k, ps = lk.render(mesh, cam, box, px=n, passes=True)
    zb, nrm, part = ps["zb"], ps["nrm"], ps["part"]
    on = np.isfinite(zb)
    ii, jj = np.nonzero(on)
    z = zb[ii, jj]
    u, v = (jj + 0.5) / k, (ii + 0.5) / k
    Xc = np.c_[(u - n / 2) / cam["f"] * z, (v - n / 2) / cam["f"] * z, z]
    Rc = humanfit._cam_rot(cam)
    X = (Xc - np.asarray(cam["t"], float)) @ Rc + np.asarray(cam["centre"], float)
    # seen by the picture's camera? (its own depth buffer, as project_reference)
    spx = int(min(max(w, h), 1600))
    _, ks, sp = lk.render(mesh, src_cam, (0.0, 0.0, float(w), float(h)), px=spx, passes=True)
    zs = sp["zb"]
    Xs = (X - np.asarray(src_cam["centre"], float)) @ Rs.T + np.asarray(src_cam["t"], float)
    us, vs = src_cam["f"] * Xs[:, 0] / Xs[:, 2] + w / 2, src_cam["f"] * Xs[:, 1] / Xs[:, 2] + h / 2
    a, b = np.round(vs * ks - 0.5).astype(int), np.round(us * ks - 0.5).astype(int)
    inside = (a >= 0) & (a < zs.shape[0]) & (b >= 0) & (b < zs.shape[1]) & (us >= 0) & (us < w - 1) & (vs >= 0) & (vs < h - 1)
    from .likeness_read import PROJECT_TOL
    vis = np.zeros(len(z), bool)
    vis[inside] = Xs[inside, 2] < zs[a[inside], b[inside]] + PROJECT_TOL
    nw = nrm[ii, jj] @ Rc                                    # normals in world axes
    to_src = -(Xs / np.linalg.norm(Xs, axis=1, keepdims=True)) @ Rs
    facing = (nw * to_src).sum(1)
    conf = vis * _sstep((facing - FACE[0]) / (FACE[1] - FACE[0])) * _sstep((nw[:, 2] - DOWN[0]) / (DOWN[1] - DOWN[0]))
    skin_px = part[ii, jj][:, 0] == 0 if part.ndim == 3 else part[ii, jj] == 0
    conf = conf * skin_px                                    # the eyeballs keep their own picture
    if mesh.get("ears") is not None and len(mesh["ears"]):
        de = cKDTree(np.asarray(mesh["V"])[mesh["ears"]]).query(X)[0]
        conf = conf * _sstep((de - EAR_REACH) / FEATHER)
    us_, vs_ = np.clip(us, 0, w - 1.001), np.clip(vs, 0, h - 1.001)
    x0, y0 = np.floor(us_).astype(int), np.floor(vs_).astype(int)
    fx, fy = (us_ - x0)[:, None], (vs_ - y0)[:, None]
    col = (photo[y0, x0] * (1 - fx) * (1 - fy) + photo[y0, x0 + 1] * fx * (1 - fy)
           + photo[y0 + 1, x0] * (1 - fx) * fy + photo[y0 + 1, x0 + 1] * fx * fy)
    # the picture's own skin colour: the confident texels between the brows' height and the mouth, off the nose's line
    lab = _lab(col)
    up_w = Rs.T @ np.array([0.0, -1.0, 0.0])
    hgt = (X - centre) @ up_w
    brow_h = float(np.mean((L[17:27] - centre) @ up_w))
    mouth_h = float(np.mean((L[48:55] - centre) @ up_w))
    core = (conf > 0.9) & (hgt < brow_h - 0.012) & (hgt > mouth_h + 0.01)
    if core.sum() < 50:
        core = conf > 0.9
    skin_lab = np.median(lab[core], 0) if core.any() else np.array([65.0, 12.0, 18.0])
    de_skin = np.linalg.norm((lab - skin_lab) * np.array([0.7, 1.0, 1.0]), axis=1)
    hairy = (hgt > brow_h + 0.012) & (de_skin > SKIN_DE)     # above the brows and not skin-coloured: hair
    img_mask = np.zeros((n, n), bool)
    img_mask[ii, jj] = hairy
    img_mask = ndimage.binary_opening(img_mask, iterations=1)
    # everything above the lowest hair in a column is hair too (the picture's fringe hides the skin behind it; image
    # rows run down the picture camera's up axis)
    img_mask = np.maximum.accumulate(img_mask[::-1], axis=0)[::-1]
    img_mask = ndimage.binary_dilation(img_mask, iterations=max(int(0.004 * px_per_m), 1))
    conf = conf * ~img_mask[ii, jj]
    # nothing under the jaw's border (neck, collar): the border's height at each distance from the mid-plane
    mx = float(L[27][0])
    J = L[0:17]
    o = np.argsort(np.abs(J[:, 0] - mx))
    jz = np.interp(np.abs(X[:, 0] - mx), np.abs(J[o, 0] - mx), J[o, 2])
    conf = conf * _sstep((X[:, 2] - jz + JAW_CUT[0]) / JAW_CUT[1])
    # and nothing that is plainly not skin (a backdrop at the silhouette, a collar) away from brows, eyes and mouth
    dfeat = cKDTree(L[17:68]).query(X)[0]
    conf = conf * np.where((dfeat > 0.02) & (de_skin > OFF_SKIN), 0.0, 1.0)
    light = None
    lin = _to_lin(col)
    if delight:
        Y = np.zeros((n, n))
        Y[ii, jj] = lin @ np.array([0.2126, 0.7152, 0.0722])
        Nimg = np.zeros((n, n, 3))
        Nimg[ii, jj] = nrm[ii, jj]
        m = np.zeros((n, n), bool)
        m[ii, jj] = (conf > 0.6) & (de_skin < SKIN_DE)
        c0, wv, rms = ls.fit_light(Y, Nimg, m)
        sh = c0 + nrm[ii, jj] @ wv
        mean = float(np.mean(sh[m[ii, jj]])) if m.any() else 1.0
        if mean > 1e-6 and np.isfinite(mean):
            lin = lin / np.clip(sh / mean, *LIGHT_CLIP)[:, None]
            light = (c0, [float(x) for x in wv], rms, mean)
    gain = [1.0, 1.0, 1.0]
    if match and skin_tone is not None and core.any():
        tgt = _to_lin(np.asarray(skin_tone, float) * 255.0)
        med = np.median(lin[core], 0)
        gain = (tgt / np.maximum(med, 1e-4)).tolist() if match == "tone" else [float((tgt @ [0.2126, 0.7152, 0.0722]) / max(med @ [0.2126, 0.7152, 0.0722], 1e-4))] * 3
        lin = lin * np.asarray(gain)
    if delight and SHINE:                                    # a highlight baked in the picture (forehead, nose): the
        Yl = np.zeros((n, n))                                # de-lighting only knows diffuse light
        Wl = np.zeros((n, n))
        yy = lin @ np.array([0.2126, 0.7152, 0.0722])
        ok = conf > 0.3
        Yl[ii[ok], jj[ok]] = yy[ok]
        Wl[ii[ok], jj[ok]] = 1.0
        sgl = 0.01 * px_per_m
        loc = (ndimage.gaussian_filter(Yl, sgl) / np.maximum(ndimage.gaussian_filter(Wl, sgl), 1e-3))[ii, jj]
        top = SHINE[0] * np.maximum(loc, 1e-4)
        over = np.maximum(yy - top, 0.0)
        lin = lin * ((np.minimum(yy, top) + SHINE[1] * over) / np.maximum(yy, 1e-5))[:, None]
    rgba = np.zeros((n, n, 4), np.uint8)
    A = np.zeros((n, n))
    A[ii, jj] = conf
    sg = max(FEATHER * px_per_m / 2, 0.8)
    A = np.minimum(A, ndimage.gaussian_filter(A, sg) * 1.0)   # soft edges that never exceed the confidence
    A = ndimage.gaussian_filter(np.where(A > 0.02, A, 0.0), sg / 2)
    C = np.zeros((n, n, 3))
    C[ii, jj] = _to_srgb8(lin)
    have = np.zeros((n, n), bool)
    have[ii, jj] = conf > 0.02
    if have.any() and not have.all():                        # colour bled outward under the soft edge
        idx = ndimage.distance_transform_edt(~have, return_distances=False, return_indices=True)
        C = C[idx[0], idx[1]]
    A[~on] = 0.0
    rgba[..., :3] = C.astype(np.uint8)
    rgba[..., 3] = np.clip(A * 255, 0, 255).astype(np.uint8)
    right = Rs.T @ np.array([1.0, 0.0, 0.0])
    d = -(Rs.T @ np.array([0.0, 0.0, 1.0]))                  # the way the printed skin faces: toward the camera
    head_px = on & (np.abs(np.arange(n)[:, None] - n / 2) < n)   # (all texels on the model)
    return {"rgba": rgba, "at": [round(float(x), 5) for x in centre], "dir": [round(float(x), 5) for x in d],
            "up": [round(float(x), 5) for x in up_w], "right": right.tolist(), "size": [round(2 * half, 5), round(2 * half, 5)],
            "light": light, "coverage": round(float((A[on] > 0.5).mean()) if on.any() else 0.0, 3), "px_per_m": px_per_m,
            "gain": [round(float(g), 3) for g in gain], "picture_px_per_m": round(float(density), 1),
            "skin_lab": [round(float(x), 1) for x in skin_lab], "head_texels": int(head_px.sum()), "cam": cam}


def near_camera(cam: dict, dist: float = 8.0) -> dict:
    """The orthographic camera brought to `dist` m on its axis (same picture to ~0.5 mm over a head): one a renderer's
    depth buffer can hold."""
    k = dist / cam["t"][2]
    return {**cam, "t": [0.0, 0.0, dist], "f": cam["f"] * k}


def frame_of(cam: dict, name: str = "ref") -> dict:
    """A humanfit-style camera (its whole picture) as a render frame (perspective)."""
    from . import humanfit
    R = humanfit._cam_rot(cam)
    eye = np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float)
    fwd, up = R.T @ np.array([0.0, 0.0, 1.0]), R.T @ np.array([0.0, -1.0, 0.0])
    w, h = cam["size"]
    return {"name": name, "eye": eye.tolist(), "dir": (-fwd).tolist(), "up": up.tolist(),
            "fov": float(np.degrees(2 * np.arctan(max(w, h) / 2 / cam["f"]))), "shift": [0.0, 0.0],
            "center": (eye + fwd).tolist(), "near": max(cam["t"][2] - 1.0, 0.01), "scale": None, "axes": None}


def scene_albedo(model: str, size: int = 768):
    """ours(cam) for `make`: the model's OWN painted skin, unlit, from its synced scene.blend (which must not hold
    reference-texture layers: sync before `apply`, or sync a copy), through the decal's camera."""
    def ours(cam):
        import tempfile
        from PIL import Image
        from . import scene
        with tempfile.TemporaryDirectory() as tmp:
            fr = {**frame_of(near_camera(cam)), "out": str(Path(tmp) / "o.png")}
            scene._blender({"blend": str(scene.blend_path(model)), "views": [fr], "size": size, "samples": 8, "hide": [],
                            "flat": True, "transparent": True, "mode": "render"}, 1200)
            im = Image.open(fr["out"]).convert("RGBA").resize(tuple(cam["size"]), Image.BILINEAR)
        a = np.asarray(im)
        return a[..., :3], a[..., 3] > 200
    return ours


def harmonise(r: dict, ours_rgb: np.ndarray, ours_ok: np.ndarray) -> dict:
    """The picture handed over to OUR skin at its outer edge, so no seam shows when the head turns: within BLEND of
    the edge the picture's low frequencies (BLEND_SIGMA) become ours (its fine detail stays), and its alpha fades over
    EDGE_FADE. Holes inside the picture (the eyes) are not edges. ours_rgb: our unlit skin through r["cam"]."""
    from scipy import ndimage
    rgba = r["rgba"].astype(float)
    ppm = r["px_per_m"]
    A = rgba[..., 3] / 255.0
    inside = ndimage.binary_fill_holes(A > 0.05)
    dist = ndimage.distance_transform_edt(inside) / ppm
    w = _sstep(dist / BLEND)
    sg = BLEND_SIGMA * ppm
    P, O = _to_lin(rgba[..., :3]), _to_lin(ours_rgb)
    # one colour for both first: the picture's confident skin takes OUR painted skin's median there (zones and all,
    # not the bare tone: matched to the tone alone, a picture whose trusted skin is mostly cheek came out pale)
    both = (A > 0.9) & ours_ok
    gain = [1.0, 1.0, 1.0]
    if both.sum() > 200:
        gain = (np.median(O[both], 0) / np.maximum(np.median(P[both], 0), 1e-4)).tolist()
        P = P * np.asarray(gain)
    mp = (A > 0.3).astype(float)
    mo = (ours_ok & inside).astype(float)
    Pl = ndimage.gaussian_filter(P * mp[..., None], (sg, sg, 0)) / np.maximum(ndimage.gaussian_filter(mp, sg), 1e-3)[..., None]
    Ol = ndimage.gaussian_filter(O * mo[..., None], (sg, sg, 0)) / np.maximum(ndimage.gaussian_filter(mo, sg), 1e-3)[..., None]
    have = (ndimage.gaussian_filter(mo, sg) > 0.2) & (ndimage.gaussian_filter(mp, sg) > 0.2)
    ratio = np.where(have[..., None], np.clip(Ol / np.maximum(Pl, 1e-4), 0.5, 2.0), 1.0)
    out = P * ratio ** (1.0 - w)[..., None]
    rgba[..., :3] = _to_srgb8(out)
    rgba[..., 3] = 255.0 * A * _sstep(dist / EDGE_FADE)
    seam = float(np.sqrt(np.mean((np.log(np.maximum(Ol, 1e-4) / np.maximum(Pl, 1e-4))[have & (dist < 0.004) & inside]) ** 2))) if (have & (dist < 0.004) & inside).any() else 0.0
    return {**r, "rgba": np.clip(rgba, 0, 255).astype(np.uint8), "seam_before": round(seam, 3),
            "gain_to_ours": [round(float(g), 3) for g in gain]}


def make(name: str, base: dict | None = None, views=None, opacity: float = 0.9, delight: bool = True,
         match: str | None = "tone", out_dir: str | None = None, spec: dict | None = None, ours=None) -> dict:
    """The reference textures of a model: {"layers": {layer name: paint layer}, "views": [per view: file, coverage,
    light, picture density...], "text"}. views = indices into human_refs' views (default: every view with an image and
    a camera, the front first so later views only fill where it is transparent... each layer lies OVER the ones before:
    list the most trusted LAST)."""
    from PIL import Image
    from . import likeness as lk, store
    spec = spec or store.load(name)
    base = base or spec["base"]
    refs = lk._refs(name)
    mesh = lk.model_mesh(base)
    tone = None
    if match and spec.get("skin"):
        from . import skin
        try:
            tone = skin.tone_rgb(skin.params(spec)["tone"])
        except Exception:  # noqa: BLE001
            tone = None
    part = (spec.get("skin") or {}).get("part", "body")
    out_dir = Path(out_dir) if out_dir else store.HOME / name
    idx = list(range(len(refs["views"]))) if views is None else list(views)
    key = head_key(base)
    layers, info = {}, []
    for i in idx:
        v, cam = refs["views"][i], refs["cameras"][i]
        if not v.get("image") or cam is None:
            continue
        photo = np.asarray(Image.open(v["image"]).convert("RGB"), float)
        r = project(mesh, cam, photo, delight=delight, skin_tone=tone, match=match)
        if ours is not None:      # ours(cam) -> (our unlit skin, sRGB uint8 (n, n, 3), valid (n, n)): `scene_albedo`
            r = harmonise(r, *ours(r["cam"]))
        f = out_dir / f"{LAYER}_{i}_{key}{'h' if ours is not None else ''}.png"
        Image.fromarray(r["rgba"], "RGBA").save(f)
        layers[f"{LAYER}_{i}"] = {"color": "image", "opacity": float(opacity), "part": part,
                                  "image": {"file": str(f), "at": r["at"], "dir": r["dir"], "up": r["up"], "size": r["size"],
                                            "depth": 0.2, "facing": 0.05, "channel": "alpha"}}
        info.append({"view": i, "image": v["image"], "file": str(f), "coverage": r["coverage"], "light": r["light"],
                     "picture_mm_per_px": round(1000.0 / r["picture_px_per_m"], 2), "texture_mm_per_px": round(1000.0 / r["px_per_m"], 2),
                     "gain": r["gain"], "seam_before": r.get("seam_before"), "gain_to_ours": r.get("gain_to_ours")})
    lines = [f"reference texture for {name} (head {key}):"]
    for x in info:
        lt = x["light"]
        lines.append(f"  view {x['view']} ({Path(x['image']).name}): the picture on {int(100 * x['coverage'])}% of the head's texels seen along "
                     f"its camera; the picture has {x['picture_mm_per_px']} mm a pixel there (no detail finer than that is the "
                     f"picture's); " + (f"light taken out (fit rms {lt[2]:.3f}, direction share {np.linalg.norm(lt[1]) / max(lt[3], 1e-6):.2f} of the mean)"
                                         if lt else "not de-lit") + f"; colour gain {x['gain']}")
        if x.get("seam_before") is not None:
            lines.append(f"    handed over to our skin at its outer edge (colour x {x.get('gain_to_ours')} onto our painted skin's median; then rms log colour step {x['seam_before']} at the edge before the hand-over)")
    lines.append("  the PICTURE: colour where its camera saw skin square-on. OURS: ears, under chin and nose, hair, eyeballs, skin "
                 "turned away, neck and body; all relief, roughness and scattering.")
    return {"layers": layers, "views": info, "text": "\n".join(lines), "head_key": key}


def stale(spec: dict) -> list:
    """Reference-texture layers made on another head shape than the spec's (the head's key is in the image's name)."""
    key = head_key(spec.get("base") or {})
    out = []
    for k, v in (spec.get("paint") or {}).items():
        im = v.get("image") or {}
        nm = str(im.get("name") or im.get("file") or "")
        if k.startswith(LAYER) and LAYER in nm and key not in nm:
            out.append(k)
    return out


def apply(name: str, views=None, opacity: float = 0.9, delight: bool = True, match: str | None = "tone",
          remove: bool = False, note: str = "", ours=None) -> dict:
    """Make the reference textures and save them as paint layers (spec["paint"]["ref_texture_<view>"]); remove=True
    takes them out. Returns make()'s dict."""
    from . import store
    spec = store.load(name)
    paint = {k: v for k, v in (spec.get("paint") or {}).items() if not k.startswith(LAYER)}
    if remove:
        store.save(name, {**spec, "paint": paint}, note or "reference textures removed")
        return {"layers": {}, "views": [], "text": f"{name}: reference textures removed"}
    r = make(name, views=views, opacity=opacity, delight=delight, match=match, spec=spec, ours=ours)
    paint.update(r["layers"])
    store.save(name, {**spec, "paint": paint}, note or "reference textures: the fitted pictures projected as albedo")
    return r
