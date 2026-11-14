"""The lips in the stack: the lip mask and lips read from the picture's indications. Part of the skin's layer stack (skin_layers.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_layers
from . import skin_project as sp
from . import skin_project_atlas, skin_project_detail, skin_project_sample

def _lip_mask(at, regs, hm, meas) -> np.ndarray:
    """The vermilion from the picture's own COLOUR EDGE: round GNM's lips (4 mm out), where the haemoglobin amount is
    over the midpoint between the lips' own median and the median of the skin round them."""
    near = skin_project_atlas._blur(at, regs["lips"].astype(float), None, 2.0) > 0.02
    inner = regs["lips"] & meas
    ring = near & ~regs["lips"] & meas
    if inner.sum() < 300 or ring.sum() < 300:
        return regs["lips"].astype(float)
    hi, lo = float(np.median(hm[inner])), float(np.median(hm[ring]))
    if hi - lo < 0.05:
        return regs["lips"].astype(float)
    hs = skin_project_atlas._blur(at, hm, meas.astype(float), 0.5)
    m = sp._sstep((hs - (lo + 0.35 * (hi - lo))) / (0.3 * (hi - lo))) * near
    return np.where(meas, m, regs["lips"].astype(float))


def lips_from_indications(name: str, spec: dict, at: dict, base: np.ndarray, log=print) -> dict | None:
    """The lips from INDICATIONS, not texels (for a head where projection fails: a phone photo grazing the lower lip,
    a lip form that differs from the photo's): the vermilion OUTLINE = the front picture's own lip contour (MediaPipe)
    mapped onto the atlas through the fitted camera (each texel's surface point projected: inside the polygon = lip),
    softened over EDGE_MM; the PIGMENT = the picture's mid-lip median (upper and lower separately; the brightest 15 %
    and darkest 25 % of each left out: highlights, the parting's shadow), brought to albedo by the plain skin's gain
    (atlas / picture). Returns {"od": (n, 3) optical density over the base, "upper", "lower" (sRGB albedo), "mask"}."""
    from PIL import Image, ImageDraw
    from . import store
    from . import likeness_render
    from . import blockin_clay, blockin_expression, blockin_models
    from . import skin_read_reads
    rj = blockin_models._refs(name)
    vi = blockin_clay._front(rj)
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    P = blockin_clay.detect_view(img, v)
    if P is None or len(P) < 468:
        return None
    polys = skin_read_reads.lip_polygons(P)
    ph = sp._lin(np.asarray(img, float) / 255.0)
    H, W = ph.shape[:2]
    mesh = blockin_expression._per_view(spec["base"], rj, [vi], lambda b: likeness_render.model_mesh(b))[vi]
    smp = skin_project_sample.sample_view(at, mesh, cam, np.asarray(img))
    cols, masks = {}, {}
    for key in ("lip_upper", "lip_lower"):
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).polygon([tuple(q) for q in polys[key]], fill=255)
        mm = np.asarray(m) > 0
        from scipy import ndimage
        core = ndimage.binary_erosion(mm, iterations=2)
        c = ph[core]
        y = c @ skin_layers.Y
        keep = (y <= np.percentile(y, 90)) & (y >= np.percentile(y, 45 if key == "lip_upper" else 25))   # (the upper lip's
        # lower half lies in the parting's shade: its median read dark)
        cols[key] = np.median(c[keep], 0)
        uv = smp["uv"]
        xi, yi = np.clip(uv[:, 0].round().astype(int), 0, W - 1), np.clip(uv[:, 1].round().astype(int), 0, H - 1)
        masks[key] = mm[yi, xi] & smp["vis"]
    plain = skin_project_detail._plain(at) & smp["vis"] & (smp["facing"] > 0.6)
    pj = spec["skin"]["projection"]
    from . import images
    alb = sp._lin(np.asarray(Image.open(images.id_path(pj["albedo"])).convert("RGB"), float) / 255.0)[at["ii"], at["jj"]]
    gain = np.median(alb[plain], 0) / np.maximum(np.median(smp["rgb"][plain], 0), 1e-4)
    od = np.zeros((len(alb), 3))
    mask = np.zeros(len(alb))
    out = {}
    # THE MESH decides "inside the lips": GNM's own lip vertex rows near the seam (the inner, wet faces the picture's contour
    # never reaches: no camera sees them, so they took the plain skin tone: a pale jagged line at the parting), unioned
    # with the picture's outline (the picture decides the outer border)
    from scipy.spatial import cKDTree
    Lm = np.asarray(at["state"]["L"], float)
    f_ = np.linspace(0, 1, 20)[:, None]
    line = np.r_[Lm[[48, 60, 61, 62, 63, 64, 54]], Lm[[54, 64, 65, 66, 67, 60, 48]]]
    pts = np.concatenate([a_[None] + (b_ - a_)[None] * f_ for a_, b_ in zip(line[:-1], line[1:])])
    dseam = cKDTree(pts).query(skin_project_atlas.interp(at, at["V"]))[0] * 1000.0
    g_ = at["groups"]
    mesh_in = {"lip_upper": (skin_project_atlas.interp(at, g_["upper_lip"]) > 0.5) & ((dseam < 2.5) | ~smp["vis"]),
               "lip_lower": (skin_project_atlas.interp(at, g_["lower_lip"]) > 0.5) & ((dseam < 2.5) | ~smp["vis"])}
    for key in ("lip_upper", "lip_lower"):
        masks[key] = masks[key] | mesh_in[key]
    for key in ("lip_upper", "lip_lower"):
        a = np.clip(cols[key] * gain, 1e-3, 1.0)
        # the lip AGAINST THE SKIN BESIDE IT in the same picture (a ratio: laid over whatever skin the head has; against the
        # stack's lightest-skin base it darkened twice over a darker procedural skin: dark mauve lips)
        rel = cols[key] / np.maximum(np.median(smp["rgb"][plain], 0), 1e-4)
        m = np.clip(skin_project_atlas._blur(at, masks[key].astype(float), None, skin_layers.EDGE_MM), 0, 1)
        m = sp._sstep((m - 0.15) / 0.7)
        od += m[:, None] * np.clip(-np.log(np.clip(rel, 1e-3, 1.0)), 0, None)[None]
        mask = np.maximum(mask, m)
        out[key.split("_")[1]] = [round(float(x), 3) for x in sp._srgb(a)]
    out.update(od=od, mask=mask)
    log(f"lips from indications: upper {out['upper']}, lower {out['lower']} (sRGB albedo; picture mid-lip x plain-skin gain {np.round(gain, 3).tolist()})")
    return out
