"""Shading the stack removes: soft fill, the blink still, occlusion, the crease's tint and map, shadow weights. Part of the skin's layer stack (skin_layers.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_layers
from . import skin_project as sp
from . import skin_project_atlas, skin_project_detail
from .skin_layers import _atlas_of

def _fill_soft(at: dict, vals: np.ndarray, w: np.ndarray, fallback: float, reaches=skin_layers.FILL_REACH) -> np.ndarray:
    """Values known where w > 0 carried over the unknown texels: the nearest measured skin first, BLENDED across reaches
    (from the widest in: each nearer reach takes over by a smoothstep of its own coverage), never a step. (Nearest-first
    by hard switches, each reach drew its own ring: a test head's hair-hidden temple and the skin by her ear showed
    concentric bands with edges in profile.)"""
    from scipy import ndimage
    out = np.full(len(vals), float(fallback))
    Wm = skin_project_atlas.image(at, w.astype(np.float32))
    Vm = skin_project_atlas.image(at, (vals * w).astype(np.float32))
    for mm in reversed(reaches):
        sg = mm / at["mm"]
        den = ndimage.gaussian_filter(Wm, sg, truncate=3.0)[at["ii"], at["jj"]]
        num = ndimage.gaussian_filter(Vm, sg, truncate=3.0)[at["ii"], at["jj"]]
        f = num / np.maximum(den, 1e-6)
        a = np.clip(den / 0.35, 0, 1)
        a = a * a * (3 - 2 * a)
        out = np.where(den > 1e-4, a * f + (1 - a) * out, out)
    return out


def blink_still(spec: dict) -> np.ndarray:
    """Per vertex of the model mesh 0..1: 1 where the skin stays put in a blink, 0 where it moves 1.5 mm or more (the
    upper lid). Paint is fixed on the skin, so the crease line and the occlusion laid on the lid came down over the closed
    eye as a dark gash (an older head). Used to SPLIT the occlusion (the lid's part is faded by the blink with the crease
    line: looks by the pose's own lid weight, the export as its own map the engine multiplies by 1 - eyeBlink); masking
    them off the lid outright cost the open eye its crease (the open eye is what is seen)."""
    import copy
    from . import likeness_render
    b2 = copy.deepcopy(spec["base"])
    b2.setdefault("head", {})["pose"] = {**(b2["head"].get("pose") or {}), "lid_upper": skin_layers.BLINK_POSE}
    V0 = np.asarray(likeness_render.model_mesh(spec["base"])["V"], float)
    V1 = np.asarray(likeness_render.model_mesh(b2)["V"], float)
    d = np.linalg.norm(V1 - V0, axis=1) * 1000.0
    # (under 0.5 mm = still: a blink nudges the whole face a little, and the lid share took the ears' and nostrils'
    # occlusion into the exported blink map)
    return np.clip(1.0 - (d - 0.5) / (skin_layers.BLINK_MOVE_MM - 0.5), 0, 1)


def occlusion(spec: dict, at: dict, part: str | None = None) -> np.ndarray:
    """THE BAKED OCCLUSION (per texel, (n, 3) multiplier 0..1) from the head's FINAL geometry (forms first: lid fold, crease
    tail, bags, nasolabial; nostrils, ears): per-vertex ambient occlusion (likeness_render.ambient_occlusion: cosine-weighted sky
    visibility) x a cavity term (skin concave against its neighbours' mean), a little warmer where darker. The atlas was
    de-lit WITH this occlusion in its shading model (skin_project's per-texel visibility), so it does not carry the
    crease's darkness; this map puts it back for renderers that don't (EEVEE's GI loses a lid fold's occlusion; a game's
    real-time light), as a multiply layer whose strength is measured against the photo (eyecmp)."""
    from scipy import sparse
    from . import likeness_render
    mesh = likeness_render.model_mesh(spec["base"])
    # WITHOUT the eyeballs as occluders: the lid margins against the ball read near black (a dark ring round each
    # opening, "raccoon" eyes on an older test head's first bake); the eyes' own occlusion paint (skin.eyes.occlusion) is the margin's
    mesh = {k: v for k, v in mesh.items() if not k.startswith("_")}
    mesh["eyes"] = []
    V, F = np.asarray(mesh["V"], float), np.asarray(mesh["F"])
    ao = np.clip(likeness_render.ambient_occlusion(mesh), 0, 1)
    n = len(V)
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    A = sparse.coo_matrix((np.ones(len(E) * 2), (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    deg = np.asarray(A.sum(1)).ravel()
    mean = (A @ V) / np.maximum(deg, 1)[:, None]
    vn = likeness_render._vertex_normals(V, F)
    conc = np.clip(((mean - V) * vn).sum(1) * 1000.0, 0, None)              # mm the skin sits below its neighbours
    conc = (A @ conc + conc) / (deg + 1)                                       # one smoothing step (vertex noise)
    cav = np.clip(conc / skin_layers.OCC_CAV_MM, 0, 1)
    m = np.clip(ao ** skin_layers.OCC_AO_POW * (1 - skin_layers.OCC_CAV * cav), skin_layers.OCC_FLOOR, 1)
    if part is not None:   # split by the blink: "still" = what stays on the skin a blink leaves put, "lid" = the rest
        still = blink_still(spec)
        m = 1 - (1 - m) * (still if part == "still" else 1 - still)
    # softened over OCC_SOFT_MM (a soft hollow, not a ring with edges; 0.4 mm drew the tail's jagged path as a black line)
    mt = skin_project_atlas._blur(at, skin_project_atlas.interp(at, m), None, skin_layers.OCC_SOFT_MM)
    # WARM, never grey: skin in shadow goes darker AND redder (light scattered under it comes out red); grey occlusion read
    # as soot round Tess's eyes, greyed her lips and the whole face. Each channel darkens by its own weight, the skin's
    # own shadow hue (shadow_weights: the atlas' darkest plain skin against its lightest)
    w = shadow_weights(spec, at)
    return np.clip(1 - (1 - mt)[:, None] * w[None, :], 0, 1)


def crease_tint(spec: dict, at: dict) -> np.ndarray:
    """The crease line's multiply colour: the skin's own shadow hue (shadow_weights) at CREASE_DEPTH: warm, not grey."""
    return np.clip(1 - skin_layers.CREASE_DEPTH * shadow_weights(spec, at), 0, 1)


def shadow_weights(spec: dict, at: dict) -> np.ndarray:
    """(3,) per channel 0..1: how much each channel darkens in the skin's own shadow, from the de-lit atlas (its 3rd
    percentile plain skin against its 97th: log ratio per channel, the largest = 1): blue most, red least on any skin.
    Falls back to OCC_WEIGHTS without an atlas."""
    try:
        _, alb, cf, _ = _atlas_of(spec)
    except Exception:  # noqa: BLE001
        return np.asarray(skin_layers.OCC_WEIGHTS, float)
    q = skin_project_detail._plain(at) & (cf > 0.6)
    if q.sum() < 500:
        return np.asarray(skin_layers.OCC_WEIGHTS, float)
    Y_ = alb[q] @ sp.Y
    lo, hi = alb[q][Y_ <= np.percentile(Y_, 3)].mean(0), alb[q][Y_ >= np.percentile(Y_, 97)].mean(0)
    d = np.log(np.maximum(hi, 1e-4) / np.maximum(lo, 1e-4))
    if not np.all(d > 0):
        return np.asarray(skin_layers.OCC_WEIGHTS, float)
    w = d / d.max()
    w = np.clip(np.minimum(w, np.asarray(skin_layers.OCC_WEIGHTS, float) + 0.15), 0.3, 1.0)
    # (part way to neutral: at the full measured hue the shadow under an older test head's hood read orange-red)
    return skin_layers.OCC_WARMTH * w + (1 - skin_layers.OCC_WARMTH) * 1.0


def crease_map(spec: dict, at: dict) -> np.ndarray:
    """(n,) 0..1 per texel: the lid fold's slit (gnm_fold_mesh.slit_ids: the crease line and its tail) as a soft line ~0.6 mm
    wide, for a crease-only cavity layer (darker only in the fold, its strength measured against the photo by occfit:
    the broad occlusion bake alone left an older test head's crease line at 0.09-0.25 against his photo's 0.30-0.49)."""
    from . import onemesh
    from . import gnm_fold_mesh
    from . import likeness_render
    lf = ((spec.get("base") or {}).get("head") or {}).get("lid_fold")
    if not lf:
        return np.zeros(len(at["ii"]))
    ids = gnm_fold_mesh.slit_ids(lf)
    mesh = likeness_render.model_mesh(spec["base"])
    tpl = mesh["state"]["tpl"]
    fid = np.asarray(tpl["fid"])
    gidall = np.asarray(onemesh.asset()["gnm_id"])
    gid = np.where(fid < len(gidall), gidall[np.clip(fid, 0, len(gidall) - 1)], -1)
    w = np.array([ids.get(int(g_), 0.0) for g_ in gid])
    m = skin_project_atlas._blur(at, skin_project_atlas.interp(at, w), None, skin_layers.CREASE_MM)
    return np.clip(m / max(float(np.percentile(m[m > 0.01], 95)) if (m > 0.01).any() else 1.0, 1e-6), 0, 1)
