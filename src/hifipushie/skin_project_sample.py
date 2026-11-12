"""One picture onto the atlas, and what in it is not this skin (wisps, strands, the exclusion mask). Part of the skin projection (skin_project.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_project
from .skin_project import _lin, _sstep, lab
from .skin_project_atlas import interp

# ---------------------------------------------------------------- one picture onto the atlas
def sample_view(at: dict, mesh: dict, cam: dict, photo: np.ndarray, maps: dict | None = None) -> dict:
    """One picture at the atlas' texels through its fitted camera. mesh: likeness_render.model_mesh of the view's own base
    (its expression). photo: (h, w, 3) sRGB 0..255. maps: {name: (h, w) picture-pixel maps} sampled the same way.
    Returns {"rgb" (n, 3) linear, "vis" (seen by the camera), "facing" (cos), "X", "N" (world), "uv" (picture px),
    "mm" (the picture's mm per pixel at the head), "maps": {name: (n,)}, "clip" (a channel clipped)}."""
    from . import humanfit
    from . import likeness_render
    from .likeness_read import PROJECT_TOL
    V = np.asarray(mesh["V"], float)
    X = interp(at, V)
    N = interp(at, likeness_render._vertex_normals(V, np.asarray(mesh["F"])))
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    w, h = cam["size"]
    R = humanfit._cam_rot(cam)
    Xc = (X - np.asarray(cam["centre"], float)) @ R.T + np.asarray(cam["t"], float)
    us, vs = cam["f"] * Xc[:, 0] / Xc[:, 2] + w / 2, cam["f"] * Xc[:, 1] / Xc[:, 2] + h / 2
    spx = int(min(max(w, h), 2000))
    _, ks, sp = likeness_render.render(mesh, cam, (0.0, 0.0, float(w), float(h)), px=spx, brows=False, passes=True)
    zs = sp["zb"]
    a, b = np.round(vs * ks - 0.5).astype(int), np.round(us * ks - 0.5).astype(int)
    inside = (a >= 0) & (a < zs.shape[0]) & (b >= 0) & (b < zs.shape[1]) & (us >= 0.5) & (us < w - 1.5) & (vs >= 0.5) & (vs < h - 1.5) & (Xc[:, 2] > 0.01)
    vis = np.zeros(len(X), bool)
    vis[inside] = Xc[inside, 2] < zs[a[inside], b[inside]] + min(PROJECT_TOL, skin_project.DEPTH_TOL)
    to_cam = -(Xc / np.linalg.norm(Xc, axis=1, keepdims=True)) @ R
    facing = (N * to_cam).sum(1)
    vis &= facing > 0.02

    def bil(img):
        img = np.asarray(img)
        u_, v_ = np.clip(us, 0, w - 1.001), np.clip(vs, 0, h - 1.001)
        x0, y0 = np.floor(u_).astype(int), np.floor(v_).astype(int)
        fx, fy = u_ - x0, v_ - y0
        if img.ndim == 3:
            fx, fy = fx[:, None], fy[:, None]
        return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) + img[y0 + 1, x0] * (1 - fx) * fy
                + img[y0 + 1, x0 + 1] * fx * fy)
    ph = np.asarray(photo, float)
    col = bil(ph)
    zc = float(np.median(Xc[vis, 2])) if vis.any() else float(cam["t"][2])
    return {"rgb": _lin(col / 255.0).astype(np.float32), "vis": vis, "facing": facing.astype(np.float32), "X": X.astype(np.float32),
            "N": N.astype(np.float32), "uv": np.c_[us, vs].astype(np.float32),
            "mm": 1000.0 * zc / cam["f"], "maps": {k: bil(m).astype(np.float32) for k, m in (maps or {}).items()},
            "clip": (col.max(1) > 250) | (col.max(1) < 6), "zb": zs, "ks": ks}


# ---------------------------------------------------------------- what is not this skin
def _picture_maps(img, cam, mesh, parse: str | None) -> dict:
    """The picture's own parse as picture-pixel probability maps {"skin", "hair", "cloth", "figure"} ({} without a
    parser). parse: "mediapipe" (Apache 2.0: the default, its masks decide what ships) | "bisenet" (trained on
    CelebAMask-HQ, non-commercial data: a MEASURING tool, for comparison only) | None (the colour rule)."""
    if not parse:
        return {}
    from . import faceparse
    try:
        if not faceparse.available():
            return {}
        g = faceparse.masks(img, cam, mesh, model=parse)[2]
    except Exception:  # noqa: BLE001
        return {}
    return {k: np.asarray(g[k], np.float32) for k in ("skin", "hair", "cloth", "figure", "ears") if k in g}


def _wisps(photo: np.ndarray, hair: np.ndarray, mpp: float, skin: np.ndarray | None = None) -> np.ndarray:
    """Loose hairs over skin in a picture ((h, w) 0..1): thin dark lines within WISP_NEAR of the parser's hair, grown
    by a millimetre. (The parser's hair mask ends where the hair is solid: Tess's temple and nape wisps went on as skin.)"""
    from scipy import ndimage
    lum = np.log(np.maximum(_lin(np.asarray(photo, float) / 255.0) @ skin_project.Y, 1e-3)).astype(np.float32)
    s = max(skin_project.WISP_MM / 1000.0 / mpp, 0.8)
    hxx = ndimage.gaussian_filter(lum, s, order=(0, 2)) * s * s
    hyy = ndimage.gaussian_filter(lum, s, order=(2, 0)) * s * s
    hxy = ndimage.gaussian_filter(lum, s, order=(1, 1)) * s * s
    tr, df = hxx + hyy, np.sqrt((hxx - hyy) ** 2 + 4 * hxy ** 2)
    line = np.clip(0.5 * (tr + df) - np.abs(0.5 * (tr - df)), 0, None)
    near = ndimage.maximum_filter(hair, 2 * max(int(skin_project.WISP_NEAR / mpp / 4), 1) + 1)
    near = ndimage.zoom(ndimage.maximum_filter(near[::4, ::4], 9), 4, order=1)[:hair.shape[0], :hair.shape[1]] if min(hair.shape) > 64 else near
    if near.shape != hair.shape:
        near = np.pad(near, ((0, hair.shape[0] - near.shape[0]), (0, hair.shape[1] - near.shape[1])), mode="edge")
    w = _sstep((line - 0.5 * skin_project.WISP_DARK) / skin_project.WISP_DARK) * (near > 0.3)
    k = max(int(round(0.001 / mpp)), 1)
    w = ndimage.gaussian_filter(ndimage.maximum_filter(w, 2 * k + 1), k * 0.5)
    # a veil of hair or its shadow: skin within VEIL_NEAR of the hair much darker than the picture's skin away from it
    kv = max(int(round(skin_project.VEIL_NEAR / mpp / 4)), 1)
    nv = ndimage.maximum_filter(hair[::4, ::4], 2 * kv + 1)
    nv = np.kron(nv, np.ones((4, 4), np.float32))[:hair.shape[0], :hair.shape[1]]
    if nv.shape != hair.shape:
        nv = np.pad(nv, ((0, hair.shape[0] - nv.shape[0]), (0, hair.shape[1] - nv.shape[1])), mode="edge")
    if skin is not None and ((skin > 0.7) & (nv < 0.1)).sum() > 500:
        ref = float(np.median(lum[(skin > 0.7) & (nv < 0.1)]))
        lo = ndimage.gaussian_filter(lum, 0.0015 / mpp)
        w = np.maximum(w, _sstep((ref - lo - 0.6 * skin_project.VEIL_DARK) / (0.8 * skin_project.VEIL_DARK)) * (nv > 0.3))
    return w.astype(np.float32)


def _strands(photo: np.ndarray, hair: np.ndarray, mpp: float) -> np.ndarray:
    """Long strands of hair lying across the face ((h, w) 0..1): connected thin dark lines that TOUCH the parser's hair
    (grown 3 mm) and run on at least STRAND_MM, followed however far they run, grown by a millimetre. Unlike _wisps, no
    region keeps them (a strand down a test head's cheek beside her nose crossed the orbital and nose regions, where wisps
    are kept for the lids' and nostrils' own lines, and went on as a dark streak in her skin)."""
    from scipy import ndimage
    lum = np.log(np.maximum(_lin(np.asarray(photo, float) / 255.0) @ skin_project.Y, 1e-3)).astype(np.float32)
    s = max(skin_project.WISP_MM / 1000.0 / mpp, 0.8)
    hxx = ndimage.gaussian_filter(lum, s, order=(0, 2)) * s * s
    hyy = ndimage.gaussian_filter(lum, s, order=(2, 0)) * s * s
    hxy = ndimage.gaussian_filter(lum, s, order=(1, 1)) * s * s
    tr, df = hxx + hyy, np.sqrt((hxx - hyy) ** 2 + 4 * hxy ** 2)
    line = np.clip(0.5 * (tr + df) - np.abs(0.5 * (tr - df)), 0, None) > skin_project.WISP_DARK
    lab, nl = ndimage.label(line, structure=np.ones((3, 3)))
    if nl == 0:
        return np.zeros(hair.shape, np.float32)
    g3 = max(int(round(0.003 / mpp)), 1)
    near = ndimage.maximum_filter((hair > 0.5).astype(np.uint8), 2 * g3 + 1) > 0
    touch = np.zeros(nl + 1, bool)
    touch[np.unique(lab[near & line])] = True
    sl = ndimage.find_objects(lab)
    keep = np.zeros(nl + 1, bool)
    for i, b in enumerate(sl, start=1):
        if b is None or not touch[i]:
            continue
        ext = float(np.hypot(b[0].stop - b[0].start, b[1].stop - b[1].start)) * mpp * 1000.0
        keep[i] = ext >= skin_project.STRAND_MM
    keep[0] = False
    m = keep[lab] & ~(hair > 0.5)
    k = max(int(round(0.001 / mpp)), 1)
    return ndimage.gaussian_filter(ndimage.maximum_filter(m.astype(np.float32), 2 * k + 1), k * 0.5).astype(np.float32)


def exclude(at: dict, s: dict, mesh: dict, cam: dict, img, view: dict, parse: str | None = "mediapipe", ears: bool = False) -> tuple:
    """(ok (n,) 0..1: this texel's picture pixel IS this skin, notes). s: sample_view's (with the parse maps)."""
    from scipy import ndimage
    from scipy.spatial import cKDTree
    from . import humanfit
    n = len(s["vis"])
    seen = s["vis"] & (s["facing"] > skin_project.FACE[0])
    ok = np.ones(n)
    notes: dict = {"parser": parse if s["maps"] else None}
    L = np.asarray(mesh["L"], float)
    if s["maps"]:
        mp = s["maps"]
        not_skin = 1 - _sstep((mp["skin"] - 0.35) / 0.3)
        hair = _sstep((mp.get("hair_grown", mp["hair"]) - 0.25) / 0.4)
        if "wisp" in mp:   # loose hairs the parser calls skin: dark thin lines near its hair; never on brows, lids, lips
            g = at["groups"]
            keep = np.max([interp(at, g[k]) for k in ("left_brow_region", "right_brow_region", "middle_brow_region", "upper_lip", "lower_lip",
                                                    "left_orbital_region", "right_orbital_region", "nose_region")], 0) > 0.2
            hair = np.maximum(hair, np.where(keep, 0.0, _sstep((mp["wisp"] - 0.3) / 0.4)))
        if "strand" in mp:   # long strands connected to the hair: excluded wherever they run (but the brows: bangs
            g = at["groups"]   # touching a brow would take the brow's hairs with them)
            kb = np.max([interp(at, g[k]) for k in ("left_brow_region", "right_brow_region", "middle_brow_region")], 0) > 0.2
            hair = np.maximum(hair, np.where(kb, 0.0, _sstep((mp["strand"] - 0.3) / 0.4)))
        cloth = _sstep((mp["cloth"] - 0.3) / 0.4) if "cloth" in mp else np.zeros(n)
        bg = _sstep((0.6 - mp["figure"]) / 0.3)
        ok *= (1 - not_skin) * (1 - hair) * (1 - cloth) * (1 - bg)
        tot = max(int(seen.sum()), 1)
        notes["rejected"] = {"hair": round(float((seen & (hair > 0.5)).sum() / tot), 3),
                             "clothing": round(float((seen & (cloth > 0.5) & (hair <= 0.5)).sum() / tot), 3),
                             "backdrop": round(float((seen & (bg > 0.5) & (hair <= 0.5) & (cloth <= 0.5)).sum() / tot), 3),
                             "other": round(float((seen & (not_skin > 0.5) & (hair <= 0.5) & (cloth <= 0.5) & (bg <= 0.5)).sum() / tot), 3)}
    else:  # no parser: the picture's own skin colour (likeness_texture's rule)
        lb = lab(s["rgb"])
        core = seen & (s["facing"] > 0.8) & (interp(at, at["groups"]["hockey_mask"]) > 0.5)
        skin_lab = np.median(lb[core], 0) if core.sum() > 50 else np.array([65.0, 12.0, 18.0])
        de = np.linalg.norm((lb - skin_lab) * np.array([0.7, 1.0, 1.0]), axis=1)
        brow_z = float(L[17:27, 2].mean())
        hairy = (s["X"][:, 2] > brow_z + 0.012) & (de > skin_project.SKIN_DE)
        dfeat = cKDTree(L[17:68]).query(s["X"])[0]
        ok *= ~hairy & ~((dfeat > 0.02) & (de > skin_project.OFF_SKIN))
        notes["rejected"] = {"by colour": round(float((seen & (ok < 0.5)).sum() / max(int(seen.sum()), 1)), 3)}
    # the lid margins: nothing within a band of the eyeball (the picture's lashes, wet line, a lid that sits elsewhere)
    band = skin_project.LID_BAND
    try:
        from . import blockin_clay
        P = blockin_clay.detect_view(img, view)
        if P is not None:
            Pm = humanfit.project(cam, L[:68])
            from . import likeness as lk
            P = np.asarray(P, float)
            P = P[np.asarray(lk.MP68)] if len(P) > 68 else P
            res = np.linalg.norm(P[36:48, :2] - Pm[36:48], axis=1)
            mis = float(np.sqrt(np.mean(res ** 2))) * s["mm"] / 1000.0
            notes["lid_misfit_mm"] = round(1000 * mis, 2)
            band = float(np.clip(1.2 * mis, skin_project.LID_BAND, 0.004))
    except Exception:  # noqa: BLE001
        pass
    notes["lid_band_mm"] = round(1000 * band, 2)
    for Ve, _, _ in mesh["eyes"]:
        c = Ve.mean(0)
        r = float(np.linalg.norm(Ve - c, axis=1).max())
        d = np.linalg.norm(s["X"] - c, axis=1) - r
        ok *= _sstep((d - band) / band)
    # the ears: only when asked for, and only when the picture's ear lands on the model's
    ear = interp(at, at["groups"]["ears"]) > 0.35
    ev = np.flatnonzero((at["groups"]["ears"] > 0.5) & at["head"])
    near_ear = cKDTree(np.asarray(mesh["V"])[ev]).query(s["X"])[0] if len(ev) else np.full(n, 1.0)
    keep_ear = False
    if ears and (seen & ear).sum() > 200 and s["maps"]:
        inside = float((s["maps"]["skin"][seen & ear] > 0.5).mean())
        zb, ks = s["zb"], s["ks"]
        m = np.zeros(zb.shape, bool)
        q = seen & ear
        a_, b_ = np.round(s["uv"][q, 1] * ks - 0.5).astype(int), np.round(s["uv"][q, 0] * ks - 0.5).astype(int)
        m[np.clip(a_, 0, zb.shape[0] - 1), np.clip(b_, 0, zb.shape[1] - 1)] = True
        ring = ndimage.binary_dilation(m, iterations=max(int(0.010 / (s["mm"] / 1000.0) * ks), 2)) & ~np.isfinite(zb)
        from PIL import Image
        sk = np.asarray(Image.fromarray((np.clip(s["_skin_map"], 0, 1) * 255).astype(np.uint8)).resize((zb.shape[1], zb.shape[0]), Image.BILINEAR)) > 127
        beside = float(sk[ring].mean()) if ring.sum() > 50 else 0.0
        keep_ear = inside >= skin_project.EAR_INSIDE and beside <= skin_project.EAR_BESIDE
        notes["ear"] = {"inside": round(inside, 2), "beside": round(beside, 2), "projected": bool(keep_ear)}
    elif (seen & ear).sum() > 200:
        notes["ear"] = {"projected": False, "why": "ears are left to the procedural skin unless asked for (ears=True)"}
    if not keep_ear:
        ok *= _sstep((near_ear - 0.002) / 0.006)
    return ok, notes
