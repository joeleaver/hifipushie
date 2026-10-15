"""The skin as a STACK OF LAYER MAPS decomposed from the de-lit reference atlas (projskin, Stage 1b; Joe: "we'd have to
build up a layer map from the reference texture as best we could"). The photograph's pixels do not ship; its
DECOMPOSITION does: each layer is one physical cause with its own map in the head's atlas (where, how much), smooth
at the scale that cause really has; the fine structure inside it stays our procedural generators'.

THE DECOMPOSITION. In optical density (D = -log albedo, per channel) skin colour is close to a base plus two
chromophores' amounts times their absorption colours: melanin and haemoglobin (Tsumura, Haneishi, Miyake 1999,
"Independent-component analysis of skin color image", JOSA A 16:2169; Tsumura et al. 2003, "Image-based skin color and
texture analysis / synthesis by extracting hemoglobin and melanin information in the skin", SIGGRAPH). They find the
two colour axes by ICA on the picture and keep shading on the (1, 1, 1) axis. WHAT IS IMPLEMENTED HERE: the two axes
are OUR pigment model's own (skin.tone_rgb's derivative in melanin and in blood at the model's tone: the same
colours every skin layer of ours is made of, so a map drives our generators directly and an edit is a pigment edit),
plus a NEUTRAL axis (1, 1, 1) for darkness that has no pigment colour (hair under the skin, shade of forms the head
lacks). Per texel D - D_tone = m v_mel + h v_hem + d v_neu is solved exactly (3 unknowns, 3 channels); `ica_check`
runs the paper's ICA in the shading-free plane and reports how far the data's own axes lie from ours.

THE STACK (in this order; each takes, from what the layers before left, its own axes, inside its own support, at its
own scale; what no layer takes is the RESIDUAL):
  pigment      melanin, everywhere, 4 mm            the base pigment field (tan, paler round the mouth)
  redness      haemoglobin, everywhere, 2.5 mm      cheeks, nose, lids, chin
  periorbital  melanin + haemoglobin + neutral, the orbit / lids / under-eye, 1.2 mm    dark circles, the lids' own colour
  brows        melanin + neutral, the brow regions, 0.7 mm          the brows' darkness as skin under our hair curves
  lips         all three, inside the vermilion (its edge from the picture's own colour edge), 0.8 mm
  beard        neutral + melanin, the beard zones, 2 mm              stubble shadow: density / colour (drives strands or paint)
  freckles     melanin's fine band (0.35-1.5 mm, positive), plain skin, as a DENSITY map (3 mm) for the generator;
               prominent marks are placed one by one (skin_project.marks)
  shade        neutral, everywhere, 3 mm            dark with no pigment colour and no layer of its own: mostly the
               shade of forms the head does not have (Stage 2 takes it back as form)
Each map is filled where no picture vouches for it: the mirror image first, then the layer's own neighbourhood inside
its support, then its mean; `provenance` marks every texel measured / mirrored / inferred.

  decompose(name)          -> the maps, the recomposition and its error, the per-layer text
  apply(name, out=None)    -> the maps stored as images, spec["skin"]["stack"] saved; skin layers "skin:stack_*"
  layers(spec, st, out, part)   (skin_features.build) the stack as paint layers: an opaque base + one multiply layer a map
  edit(spec, **kw)         -> a copy with layer strengths changed (blush, tan, older, no stubble): one map each
"""
from __future__ import annotations

import copy
import json

import numpy as np

from . import skin_project as sp

VERSION = 1
P0 = 0.8                 # a layer's default opacity: its stored multiplier is exact at P0 and leaves room to 1.0 (x 1.25)
LAYERS = (  # name, axes (m melanin, h haemoglobin, d neutral), support, scale mm
    ("pigment", "m", "all", 4.0),
    ("redness", "h", "all", 4.5),   # (2.5: cheek blush as round saturated patches; real flush is an even warmth)
    ("periorbital", "mh", "orbit", 1.2),   # (no neutral: the socket's own shading, under-lit by the de-lighting, read as a
                                           # purple-brown ring round the orbit, above the crease and under the eye)
    ("brows", "md", "brow", 0.7),
    ("lips", "mh", "lips", 0.3),     # (pigment only: its neutral darkness was the lower lip's own shading, a grey-brown lip)
    ("beard", "dm", "beard", 2.0),
    ("shade", "d", "all", 3.0),
)
SUPPORT = {"orbit": ("orbit", "under_eye"), "brow": ("brow",), "beard": ("upper_lip_skin", "lower_lip_skin", "chin", "jaw_side", "cheek")}
FRECKLE_BAND = (0.35, 1.5)   # mm: the fine melanin band that is freckles
BLEMISH_BAND = (0.4, 2.0)    # mm: the fine haemoglobin band that is blemishes (red papules / marks)
BLEMISH_REF = 0.05           # its 3 mm mean (blood x) that is a full blemish field (p99s measured 0.034 .. 0.050 on test heads)
BLEMISH_FLOOR = 0.03         # a p99 under this: no blemishes (an even skin's own grain)
FINE_FULL = 0.12         # rms log luminance under 1.2 mm that our fine generator gives at full strength (FINE_TINT, two scales)
FINE_TINT = (0.84, 0.77, 0.74)   # the fine generator's colour (a multiply: darker, a little redder: pores, mottle, fine vessels)
FINE_FLOOR = 0.35        # the fine generator's least strength on plain skin (see decompose)
FINE_SCALES = (0.0012,)   # m: (old) its noise scale
PORE_SCALE, PORE_TINT = 0.00045, (0.8, 0.68, 0.64)   # the pore grain's noise scale (m) and its multiply colour
MOTTLE_SCALE, MOTTLE_TINT = 0.004, (0.95, 0.86, 0.86)
FILL_REACH = (0.8, 2.0, 5.0, 15.0, 40.0)   # mm: unmeasured texels take each layer from measured skin within these, nearest first
CAVITY = (0.85, 0.45, 1.3, 0.5)   # unmeasured texels with ambient occlusion under the first: + neutral (up to the third) and
                                  # haemoglobin (up to the fourth) at occlusion first - second: nostrils, the lip seam, the
                                  # socket's edge read dark and warm, not as the lightest skin
LIP_REACH = 1.0          # mm: the lips layer's support reaches this far past GNM's lips (a Gaussian's sigma)
LIP_FADE = 0.12          # ... and is full where that blur is over this (about 3 mm out), fading to nothing beyond
OPACITY = {"brows": 0.4, "periorbital": 0.4}   # (periorbital: a bag's shadow the head has no form for was taken as pigment: a
                          # heavy orange-brown under an older eye and on the closed lid; Stage 2's bags take the rest as form)  # a layer's own default: the brows' map is the SKIN-LEVEL darkness under our brow hairs (at full
                          # strength map + hairs doubled: heavier brows than the photograph's)
FRECKLE_REF = 0.2        # the fine melanin band's 3 mm mean (melanin x) that is a full freckle field
OCC_AO_POW = 1.0          # the baked occlusion: ambient occlusion ^ this ...
OCC_CAV = 0.35            # ... x (1 - this x the cavity term: concave skin under 0.2 mm of the local mean surface)
OCC_CAV_MM = 0.2
BLINK_POSE = 0.0095        # base.head.pose lid_upper of a full blink (cu.py's closed-eye renders)
BLINK_MOVE_MM = 1.5       # skin moving this far in it carries no crease line / occlusion
CREASE_MM = 0.35          # the crease cavity line's softness (a Gaussian's sigma over the slit's vertices)
CREASE_DEPTH = 0.62       # the crease line's darkening at full strength, per channel x the skin's shadow weights
CREASE_STRENGTH = 0.5     # the crease line's default opacity (occfit measures it per head)
OCC_FLOOR = 0.55          # the bake never darker than this (a game AO map's usual floor; under it: cracks)
OCC_STRENGTH = 1.0        # the occlusion layer's default opacity (eyecmp / occfit measure it per head)
OCC_WEIGHTS = (0.5, 0.8, 1.0)   # per channel share of the occlusion's darkening (R, G, B) without an atlas: warm
OCC_WARMTH = 0.6          # how much of the measured shadow hue the occlusion keeps (1 = all of it)
OCC_SOFT_MM = 1.2         # the bake's softness (a Gaussian's sigma, mm)
ORBIT_SHADE_CUT = 0.7      # share of the shade layer kept off the orbit (see decompose)
COVER_SOFT_MM = 6.0        # the coverage fade's softness (mm)
COVER_EDGE_MM = 12.0       # the stack's coverage fades over this inside the head island's atlas border
LIPS_VENOUS = 0.5         # the lips' blood colour: share of the venous axis (the rest arterial)
BASE_MAX = 0.9            # linear: the lightest skin's brightest channel at most this (see decompose)
LOW_PCT = 3.0            # the maps' zero: this percentile of each amount over the measured plain skin (the lightest skin there is)
Y = sp.Y


def axes(tone: dict | None) -> np.ndarray:
    """(3, 3): the optical-density colour of one unit of melanin (x 2 the tone's own), of haemoglobin (x 2 its blood)
    and of neutral darkness (1 unit = e-fold), at this tone: rows v_mel, v_hem, v_neu."""
    from . import skin
    t0 = sp._lin(np.asarray(skin.tone_rgb(tone), float))
    vm = -np.log(sp._lin(np.asarray(skin.tone_rgb(tone, melanin=2.0), float)) / t0)
    vh = -np.log(sp._lin(np.asarray(skin.tone_rgb(tone, blood=2.0), float)) / t0)
    return np.stack([vm, vh, np.ones(3)])


def venous_axis(tone: dict | None) -> np.ndarray:
    """The optical density of one unit of DEOXYGENATED blood (x 2 its blood at oxygenation 0.35): the periorbital
    layer's redness. Thin lid skin over venous blood reads pink-violet; with the arterial axis the lids came out orange."""
    from . import skin
    t0 = sp._lin(np.asarray(skin.tone_rgb(tone, oxygenation=0.35), float))
    return -np.log(sp._lin(np.asarray(skin.tone_rgb(tone, blood=2.0, oxygenation=0.35), float)) / t0)


def ica_check(D: np.ndarray, V: np.ndarray) -> dict:
    """The paper's ICA on optical densities D (n, 3) of plain skin, in the plane across (1, 1, 1) (shading leaves it):
    whiten, then the rotation with the largest |excess kurtosis|. Returns the angles (deg, in that plane) between
    the data's two independent axes and our melanin / haemoglobin axes, and the two model axes' own angle."""
    e = np.ones(3) / np.sqrt(3)
    B = np.linalg.svd(np.eye(3) - np.outer(e, e))[0][:, :2]          # an orthonormal basis of the plane
    X = (D - D.mean(0)) @ B
    C = np.cov(X.T)
    w, U = np.linalg.eigh(C)
    Wh = U @ np.diag(1 / np.sqrt(np.maximum(w, 1e-12))) @ U.T
    Z = X @ Wh
    best, ang = -1.0, 0.0
    for a in np.linspace(0, np.pi / 2, 91):
        c, s = np.cos(a), np.sin(a)
        y1, y2 = Z @ [c, s], Z @ [-s, c]
        k = abs(np.mean(y1 ** 4) - 3) + abs(np.mean(y2 ** 4) - 3)
        if k > best:
            best, ang = k, a
    c, s = np.cos(ang), np.sin(ang)
    A = np.linalg.inv(Wh) @ np.array([[c, -s], [s, c]])               # the mixing matrix's columns: the data's axes in the plane
    A = A / np.linalg.norm(A, axis=0)
    M = (V[:2] @ B)
    M = M / np.linalg.norm(M, axis=1, keepdims=True)
    def angle(u, v):
        return float(np.degrees(np.arccos(np.clip(abs(u @ v), 0, 1))))
    d = [[angle(A[:, i], M[j]) for j in range(2)] for i in range(2)]
    pair = min((d[0][0] + d[1][1], (0, 1)), (d[0][1] + d[1][0], (1, 0)))[1]
    return {"melanin_deg": round(d[pair.index(0)][0], 1), "haemoglobin_deg": round(d[pair.index(1)][1], 1),
            "model_axes_deg": round(angle(M[0], M[1]), 1), "kurtosis": round(float(best), 2)}


def _atlas_of(spec: dict):
    from PIL import Image
    from . import images
    pj = (spec.get("skin") or {}).get("projection") or {}
    if not pj.get("albedo") or not pj.get("confidence") or not pj.get("delight", True):
        raise ValueError("skin_layers: the model has no de-lit skin projection (skin_project first)")
    at = sp.atlas(spec["base"])
    alb = sp._lin(np.asarray(Image.open(images.id_path(pj["albedo"])).convert("RGB"), float) / 255.0)[at["ii"], at["jj"]]
    cf = np.asarray(Image.open(images.id_path(pj["confidence"])).convert("RGB"), float)[..., 0][at["ii"], at["jj"]] / 255.0
    return at, alb, cf, pj


def _lip_mask(at, regs, hm, meas) -> np.ndarray:
    """The vermilion from the picture's own COLOUR EDGE: round GNM's lips (4 mm out), where the haemoglobin amount is
    over the midpoint between the lips' own median and the median of the skin round them."""
    near = sp._blur(at, regs["lips"].astype(float), None, 2.0) > 0.02
    inner = regs["lips"] & meas
    ring = near & ~regs["lips"] & meas
    if inner.sum() < 300 or ring.sum() < 300:
        return regs["lips"].astype(float)
    hi, lo = float(np.median(hm[inner])), float(np.median(hm[ring]))
    if hi - lo < 0.05:
        return regs["lips"].astype(float)
    hs = sp._blur(at, hm, meas.astype(float), 0.5)
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
    from . import blockin as bi, likeness as lk, skin_read as sr, store
    rj = bi._refs(name)
    vi = bi._front(rj)
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    P = bi.detect_view(img, v)
    if P is None or len(P) < 468:
        return None
    polys = sr.lip_polygons(P)
    ph = sp._lin(np.asarray(img, float) / 255.0)
    H, W = ph.shape[:2]
    mesh = bi._per_view(spec["base"], rj, [vi], lambda b: lk.model_mesh(b))[vi]
    smp = sp.sample_view(at, mesh, cam, np.asarray(img))
    cols, masks = {}, {}
    for key in ("lip_upper", "lip_lower"):
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).polygon([tuple(q) for q in polys[key]], fill=255)
        mm = np.asarray(m) > 0
        from scipy import ndimage
        core = ndimage.binary_erosion(mm, iterations=2)
        c = ph[core]
        y = c @ Y
        keep = (y <= np.percentile(y, 90)) & (y >= np.percentile(y, 45 if key == "lip_upper" else 25))   # (the upper lip's
        # lower half lies in the parting's shade: its median read dark)
        cols[key] = np.median(c[keep], 0)
        uv = smp["uv"]
        xi, yi = np.clip(uv[:, 0].round().astype(int), 0, W - 1), np.clip(uv[:, 1].round().astype(int), 0, H - 1)
        masks[key] = mm[yi, xi] & smp["vis"]
    plain = sp._plain(at) & smp["vis"] & (smp["facing"] > 0.6)
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
    dseam = cKDTree(pts).query(sp.interp(at, at["V"]))[0] * 1000.0
    g_ = at["groups"]
    mesh_in = {"lip_upper": (sp.interp(at, g_["upper_lip"]) > 0.5) & ((dseam < 2.5) | ~smp["vis"]),
               "lip_lower": (sp.interp(at, g_["lower_lip"]) > 0.5) & ((dseam < 2.5) | ~smp["vis"])}
    for key in ("lip_upper", "lip_lower"):
        masks[key] = masks[key] | mesh_in[key]
    for key in ("lip_upper", "lip_lower"):
        a = np.clip(cols[key] * gain, 1e-3, 1.0)
        # the lip AGAINST THE SKIN BESIDE IT in the same picture (a ratio: laid over whatever skin the head has; against the
        # stack's lightest-skin base it darkened twice over a darker procedural skin: dark mauve lips)
        rel = cols[key] / np.maximum(np.median(smp["rgb"][plain], 0), 1e-4)
        m = np.clip(sp._blur(at, masks[key].astype(float), None, EDGE_MM), 0, 1)
        m = sp._sstep((m - 0.15) / 0.7)
        od += m[:, None] * np.clip(-np.log(np.clip(rel, 1e-3, 1.0)), 0, None)[None]
        mask = np.maximum(mask, m)
        out[key.split("_")[1]] = [round(float(x), 3) for x in sp._srgb(a)]
    out.update(od=od, mask=mask)
    log(f"lips from indications: upper {out['upper']}, lower {out['lower']} (sRGB albedo; picture mid-lip x plain-skin gain {np.round(gain, 3).tolist()})")
    return out


PARTING_MM = 0.6        # mm: the parting line's softness (a Gaussian's sigma)
PARTING_MAX = 1.2        # e-folds: at most this dark (the stomion of a photographed closed mouth reads 0.6-1.0)
EDGE_MM = 0.4            # mm: the indications route's vermilion edge softness


def _fill_soft(at: dict, vals: np.ndarray, w: np.ndarray, fallback: float, reaches=FILL_REACH) -> np.ndarray:
    """Values known where w > 0 carried over the unknown texels: the nearest measured skin first, BLENDED across reaches
    (from the widest in: each nearer reach takes over by a smoothstep of its own coverage), never a step. (Nearest-first
    by hard switches, each reach drew its own ring: a test head's hair-hidden temple and the skin by her ear showed
    concentric bands with edges in profile.)"""
    from scipy import ndimage
    out = np.full(len(vals), float(fallback))
    Wm = sp.image(at, w.astype(np.float32))
    Vm = sp.image(at, (vals * w).astype(np.float32))
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
    from . import likeness as lk
    b2 = copy.deepcopy(spec["base"])
    b2.setdefault("head", {})["pose"] = {**(b2["head"].get("pose") or {}), "lid_upper": BLINK_POSE}
    V0 = np.asarray(lk.model_mesh(spec["base"])["V"], float)
    V1 = np.asarray(lk.model_mesh(b2)["V"], float)
    d = np.linalg.norm(V1 - V0, axis=1) * 1000.0
    # (under 0.5 mm = still: a blink nudges the whole face a little, and the lid share took the ears' and nostrils'
    # occlusion into the exported blink map)
    return np.clip(1.0 - (d - 0.5) / (BLINK_MOVE_MM - 0.5), 0, 1)


def occlusion(spec: dict, at: dict, part: str | None = None) -> np.ndarray:
    """THE BAKED OCCLUSION (per texel, (n, 3) multiplier 0..1) from the head's FINAL geometry (forms first: lid fold, crease
    tail, bags, nasolabial; nostrils, ears): per-vertex ambient occlusion (likeness.ambient_occlusion: cosine-weighted sky
    visibility) x a cavity term (skin concave against its neighbours' mean), a little warmer where darker. The atlas was
    de-lit WITH this occlusion in its shading model (skin_project's per-texel visibility), so it does not carry the
    crease's darkness; this map puts it back for renderers that don't (EEVEE's GI loses a lid fold's occlusion; a game's
    real-time light), as a multiply layer whose strength is measured against the photo (eyecmp)."""
    from scipy import sparse
    from . import likeness as lk
    mesh = lk.model_mesh(spec["base"])
    # WITHOUT the eyeballs as occluders: the lid margins against the ball read near black (a dark ring round each
    # opening, "raccoon" eyes on an older test head's first bake); the eyes' own occlusion paint (skin.eyes.occlusion) is the margin's
    mesh = {k: v for k, v in mesh.items() if not k.startswith("_")}
    mesh["eyes"] = []
    V, F = np.asarray(mesh["V"], float), np.asarray(mesh["F"])
    ao = np.clip(lk.ambient_occlusion(mesh), 0, 1)
    n = len(V)
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    A = sparse.coo_matrix((np.ones(len(E) * 2), (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    deg = np.asarray(A.sum(1)).ravel()
    mean = (A @ V) / np.maximum(deg, 1)[:, None]
    vn = lk._vertex_normals(V, F)
    conc = np.clip(((mean - V) * vn).sum(1) * 1000.0, 0, None)              # mm the skin sits below its neighbours
    conc = (A @ conc + conc) / (deg + 1)                                       # one smoothing step (vertex noise)
    cav = np.clip(conc / OCC_CAV_MM, 0, 1)
    m = np.clip(ao ** OCC_AO_POW * (1 - OCC_CAV * cav), OCC_FLOOR, 1)
    if part is not None:   # split by the blink: "still" = what stays on the skin a blink leaves put, "lid" = the rest
        still = blink_still(spec)
        m = 1 - (1 - m) * (still if part == "still" else 1 - still)
    # softened over OCC_SOFT_MM (a soft hollow, not a ring with edges; 0.4 mm drew the tail's jagged path as a black line)
    mt = sp._blur(at, sp.interp(at, m), None, OCC_SOFT_MM)
    # WARM, never grey: skin in shadow goes darker AND redder (light scattered under it comes out red); grey occlusion read
    # as soot round Tess's eyes, greyed her lips and the whole face. Each channel darkens by its own weight, the skin's
    # own shadow hue (shadow_weights: the atlas' darkest plain skin against its lightest)
    w = shadow_weights(spec, at)
    return np.clip(1 - (1 - mt)[:, None] * w[None, :], 0, 1)


def crease_tint(spec: dict, at: dict) -> np.ndarray:
    """The crease line's multiply colour: the skin's own shadow hue (shadow_weights) at CREASE_DEPTH: warm, not grey."""
    return np.clip(1 - CREASE_DEPTH * shadow_weights(spec, at), 0, 1)


def shadow_weights(spec: dict, at: dict) -> np.ndarray:
    """(3,) per channel 0..1: how much each channel darkens in the skin's own shadow, from the de-lit atlas (its 3rd
    percentile plain skin against its 97th: log ratio per channel, the largest = 1): blue most, red least on any skin.
    Falls back to OCC_WEIGHTS without an atlas."""
    try:
        _, alb, cf, _ = _atlas_of(spec)
    except Exception:  # noqa: BLE001
        return np.asarray(OCC_WEIGHTS, float)
    q = sp._plain(at) & (cf > 0.6)
    if q.sum() < 500:
        return np.asarray(OCC_WEIGHTS, float)
    Y_ = alb[q] @ sp.Y
    lo, hi = alb[q][Y_ <= np.percentile(Y_, 3)].mean(0), alb[q][Y_ >= np.percentile(Y_, 97)].mean(0)
    d = np.log(np.maximum(hi, 1e-4) / np.maximum(lo, 1e-4))
    if not np.all(d > 0):
        return np.asarray(OCC_WEIGHTS, float)
    w = d / d.max()
    w = np.clip(np.minimum(w, np.asarray(OCC_WEIGHTS, float) + 0.15), 0.3, 1.0)
    # (part way to neutral: at the full measured hue the shadow under an older test head's hood read orange-red)
    return OCC_WARMTH * w + (1 - OCC_WARMTH) * 1.0


def crease_map(spec: dict, at: dict) -> np.ndarray:
    """(n,) 0..1 per texel: the lid fold's slit (gnm_fold.slit_ids: the crease line and its tail) as a soft line ~0.6 mm
    wide, for a crease-only cavity layer (darker only in the fold, its strength measured against the photo by occfit:
    the broad occlusion bake alone left an older test head's crease line at 0.09-0.25 against his photo's 0.30-0.49)."""
    from . import gnm_fold, likeness as lk, onemesh
    lf = ((spec.get("base") or {}).get("head") or {}).get("lid_fold")
    if not lf:
        return np.zeros(len(at["ii"]))
    ids = gnm_fold.slit_ids(lf)
    mesh = lk.model_mesh(spec["base"])
    tpl = mesh["state"]["tpl"]
    fid = np.asarray(tpl["fid"])
    gidall = np.asarray(onemesh.asset()["gnm_id"])
    gid = np.where(fid < len(gidall), gidall[np.clip(fid, 0, len(gidall) - 1)], -1)
    w = np.array([ids.get(int(g_), 0.0) for g_ in gid])
    m = sp._blur(at, sp.interp(at, w), None, CREASE_MM)
    return np.clip(m / max(float(np.percentile(m[m > 0.01], 95)) if (m > 0.01).any() else 1.0, 1e-6), 0, 1)


def decompose(name: str, spec: dict | None = None, log=print, lips: str = "texels") -> dict:
    """The stack of a model with a de-lit atlas: {"base" (3,) linear (the lightest skin: every map is >= 0 over it),
    "layers": {name: {"amount": {axis: (n,) map}, "od": (n, 3) its optical density, "meas"/"mirror" shares}},
    "freckles": (n,) density map 0..1, "provenance" (n,) uint8 (255 measured, 170 mirrored, 85 inferred), "recomposed"
    (n, 3) linear, "residual": {...by region and band}, "ica", "axes", "at", "text"}."""
    from scipy.spatial import cKDTree
    from . import skin, store
    spec = spec or store.load(name)
    at, alb, cf, pj = _atlas_of(spec)
    n = len(alb)
    tone = skin.params(spec)["tone"]
    V = axes(tone)
    Vi = np.linalg.inv(V)                                     # amounts = D @ Vi
    meas = cf > 0.6
    regs = sp.region_masks(at)
    plain = sp._plain(at) & meas
    c_tone = np.median(alb[plain], 0)
    D = -np.log(np.maximum(alb, 1e-4) / c_tone)
    A = D @ Vi                                                # (n, 3): m, h, d
    wm = meas.astype(float)
    zero = np.array([np.percentile(sp._blur(at, A[:, k], wm, 4.0)[plain], LOW_PCT) for k in range(3)])
    A = A - zero                                              # over the lightest skin
    base = c_tone * np.exp(-(zero @ V))
    # an albedo over 1 cannot be laid: the stored base (sRGB) clipped its red channel at 1 and every colour over it lost
    # red (a test head's forms-first stack read grey: base [1.0, 0.93, 0.91], the photo's cheek r/g 1.42, ours 1.27). The
    # whole stack darkened instead (the lightness is the model's guess anyway: tone "picture" keeps only the hue)
    if float(base.max()) > BASE_MAX:
        base = base * (BASE_MAX / float(base.max()))
    ica = ica_check(D[plain][:: max(int(plain.sum() // 60000), 1)], V)
    sup = {"all": np.ones(n)}
    for k, names in SUPPORT.items():
        sup[k] = np.clip(sp._blur(at, np.max([regs[r] for r in names if r in regs], 0).astype(float), None, 1.5), 0, 1)
    # THE LIPS' SUPPORT IS WIDE AND SOFT (GNM's lips + LIP_REACH, fading over LIP_FADE): inside it the lips layer takes
    # everything the broad layers left at its own 0.8 mm, so the vermilion border's PROFILE is the atlas' own (soft on
    # the lower lip and at the corners, sharpest at the cupid's bow), not a mask's edge. (First version: a thresholded
    # vermilion mask multiplied the layer and cut the broad layers out: one hard colour line all round. Joe: "the lip
    # color lines are a little hard".) `vermilion` (the colour edge) is kept for the report only.
    vermilion = _lip_mask(at, regs, A[:, 1], meas)
    sup["lips"] = sp._sstep(sp._blur(at, regs["lips"].astype(float), None, LIP_REACH) / LIP_FADE)
    lips_core = np.clip(sp._blur(at, regs["lips"].astype(float), None, 0.4) * 2.0, 0, 1)
    # the mirror image of every unmeasured texel
    Xn = sp.interp(at, at["neutral"])
    have, need = np.flatnonzero(meas), np.flatnonzero(~meas)
    msrc = np.full(n, -1)
    if len(have) > 1000 and len(need):
        d_, j = cKDTree(Xn[have]).query(Xn[need] * [-1.0, 1.0, 1.0], distance_upper_bound=0.0008)
        g = np.isfinite(d_)
        msrc[need[g]] = have[j[g]]
    prov = np.where(meas, 255, np.where(msrc >= 0, 170, 85)).astype(np.uint8)
    known = meas | (msrc >= 0)
    R = A.copy()
    R[msrc >= 0] = A[msrc[msrc >= 0]]                          # mirrored amounts (INFERRED: the face taken as symmetric)
    out_l = {}
    ax = {"m": 0, "h": 1, "d": 2}
    sk_ = spec.get("skin") or {}
    beard_on = float(sk_.get("sex", 0.5) if sk_.get("sex") is not None else 0.5) >= 0.5 or bool((sk_.get("hair") or {}).get("stubble"))
    for lname, axs, sname, mm in LAYERS:
        S = sup[sname]
        if lname == "beard" and not beard_on:   # no beard: the darkness there is shading under the nose (philtrum), left to
            continue                            # the shade layer (on a woman the beard layer drew a fuzzy moustache)
        # redness / shade UNDER THE LIPS: the skin's own level carried in from round the mouth (measured outside the
        # vermilion core, filled across it); the lips layer takes only the lip's excess over it. (Cut to zero there, the
        # lightest-skin base showed wherever GNM's lip region is wider than the person's lips: a pale rim round the
        # lips and a pale lower-lip band on the test heads' full stacks; the indications route's lips are a ratio to
        # the skin beside them, so they need the skin under them too.)
        hole = (lips_core > 0.2) if lname in ("redness", "shade") else None
        if lname == "shade":   # the socket's neutral darkness is the form's (the fold, the bag, the baked occlusion make it):
            S = S * (1 - ORBIT_SHADE_CUT * sup["orbit"])   # laid as paint too it doubled into a dark ring round the eye
        amt = {}
        od = np.zeros((n, 3))
        for a in axs:
            k = ax[a]
            Sa = S
            if lname == "lips" and a == "d":   # the neutral darkness only ON the lips: round them it is the shadow of a form
                Sa = np.clip(sp._blur(at, regs["lips"].astype(float), None, 0.4) * 2.0, 0, 1)   # (the lower lip's): a dark ring
            w = known.astype(float) * (Sa > 0.05)
            if hole is not None:
                w = w * ~hole
            v = np.clip(sp._blur(at, R[:, k], w, mm), 0, None) * Sa
            if hole is not None and hole.any():
                v = np.where(hole, _fill_soft(at, v, w, float(np.median(v[w > 0])) if (w > 0).any() else 0.0) * Sa, v)
            # where nothing is known: the layer's own neighbourhood inside its support, then its mean there
            if (~known & (Sa > 0.05)).any():
                mean = float(np.median(v[known & (Sa > 0.5)])) if (known & (Sa > 0.5)).any() else 0.0
                # the NEAREST measured skin first (a lid margin, a lip border, a nostril rim continue the colour next to
                # them): a 6 mm first reach averaged in the lighter cheek and the near-base colour showed as a pale ring
                fill_ = _fill_soft(at, v, w, mean) * Sa
                if lname in ("pigment", "redness", "shade", "periorbital"):   # measured skin eased into the fill over
                    # ~2 mm inside its edge (edge texels are the least trustworthy: the hair line's, the lid band's): no
                    # seam where it stops (a thin dark line ran down from Tess's outer eye corner along the lid band's edge)
                    kb = sp._blur(at, known.astype(float), None, 2.0)
                    tk = np.clip((kb - 0.5) / 0.5, 0, 1)
                    tk = tk * tk * (3 - 2 * tk)
                    v = np.where(known, tk * v + (1 - tk) * fill_, fill_)
                else:
                    v = np.where(known, v, fill_)
            if lname in ("pigment", "redness"):   # the orbit no warmer than the face round it: the lids' and sockets'
                # de-lit colour carries the shading residue as warmth (an orange-peach band across the upper lids that read
                # as eyeshadow, on every head); capped at the plain skin's 75th percentile there
                cap_ = float(np.percentile(v[plain], 75)) if plain.any() else float(np.median(v))
                ow = np.clip(sup["orbit"], 0, 1)
                v = v * (1 - ow) + np.minimum(v, cap_) * ow
            amt[a] = v
            if lname in ("periorbital", "lips") and a == "h":   # (lips: mucosa over venous-rich blood reads pink, the arterial axis orange)   # the lids' redness laid with venous blood's colour (pink-violet, not orange)
                od += v[:, None] * venous_axis(tone) * (float(np.linalg.norm(V[k])) / max(float(np.linalg.norm(venous_axis(tone))), 1e-9))
            else:
                od += v[:, None] * V[k]
            R[:, k] = R[:, k] - v
        if lname == "lips":   # the lips' PIGMENT is the lip body's: the parting's shadow and the lower lip's grazing underside
            # (de-lighting leaves them dark) are not painted (a dark-red smear with a hard edge on a phone photo's lower lip)
            g_ = at["groups"]
            ul, ll = sp.interp(at, g_["upper_lip"]), sp.interp(at, g_["lower_lip"])
            seam = np.clip(sp._blur(at, (ul > 0.5).astype(float), None, 1.0) * sp._blur(at, (ll > 0.5).astype(float), None, 1.0) * 8.0, 0, 1)
            body = regs["lips"] & meas & (seam < 0.2)
            if body.sum() > 200:
                od = np.zeros((n, 3))
                for a in axs:
                    cap = float(np.percentile(amt[a][body], 60))
                    amt[a] = np.minimum(amt[a], cap)
                    # (the lips' blood half venous, half arterial: all venous read mauve-grey to a blind review, all
                    # arterial read orange)
                    vax = venous_axis(tone) * (float(np.linalg.norm(V[1])) / max(float(np.linalg.norm(venous_axis(tone))), 1e-9))
                    od += amt[a][:, None] * ((LIPS_VENOUS * vax + (1 - LIPS_VENOUS) * V[1]) if a == "h" else V[ax[a]])
        out_l[lname] = {"amount": amt, "od": od, "support": sname, "mm": mm}
    # THE PARTING: where the closed lips meet, a photograph shows a soft dark line ~1 mm wide (the stomion's shadow and wet
    # inner lip); the mesh's seam alone is a hairline, jagged at any voxel. A soft neutral line along GNM's own seam, as dark
    # as the atlas' parting band against the lip body beside it (measured; at most PARTING_MAX)
    # (the seam = the 68 landmarks' inner lip line 60-64-67, densely resampled; GNM's lip groups meet INSIDE the mouth)
    from scipy.spatial import cKDTree
    Lm = np.asarray(at["state"]["L"], float)
    line = np.r_[Lm[[48, 60, 61, 62, 63, 64, 54]], Lm[[54, 64, 65, 66, 67, 60, 48]]]
    f_ = np.linspace(0, 1, 20)[:, None]
    pts = np.concatenate([a_[None] + (b_ - a_)[None] * f_ for a_, b_ in zip(line[:-1], line[1:])])
    Xs = sp.interp(at, at["V"])
    dmm = cKDTree(pts).query(Xs)[0] * 1000.0
    seam = np.exp(-0.5 * (dmm / max(PARTING_MM * 1.5, 1e-6)) ** 2) * (regs["lips"] | (dmm < 1.0))
    band = regs["lips"] & meas & (seam > 0.6)
    body = regs["lips"] & meas & (seam < 0.15)
    dpart = float(np.clip(np.median((A[:, 2] + A[:, 0] * 0.3)[band]) - np.median((A[:, 2] + A[:, 0] * 0.3)[body]), 0.35, PARTING_MAX)) if band.sum() > 50 and body.sum() > 200 else 0.4
    out_l["parting"] = {"amount": {"d": dpart * seam}, "od": (dpart * seam)[:, None] * V[2], "support": "lips", "mm": PARTING_MM}
    if lips == "indications":   # the lips layer replaced by the picture's outline + mid-lip colour
        li = lips_from_indications(name, spec, at, base, log=log)
        if li is not None:
            out_l["lips"] = {"amount": {"m": li["mask"]}, "od": li["od"], "support": "lips", "mm": EDGE_MM, "indications": li}
    # surfaces no picture saw that sit in occlusion (nostril interior, the inner lip at the seam, the lid's tuck): dark
    # and warm by their own ambient occlusion (INFERRED), on the shade (neutral) and redness (haemoglobin) layers
    from . import likeness as lk
    ao = np.clip(sp.interp(at, lk.ambient_occlusion(lk.model_mesh(spec["base"]))), 0, 1)
    cav = np.where(~meas, np.clip((CAVITY[0] - ao) / CAVITY[1], 0, 1), 0.0)
    # only inside an unmeasured REGION (a nostril, the seam's inner faces), never along a sliver of unmeasured texels (a
    # UV seam or a thin gap between views on open skin drew a thin dark scratch on a jaw)
    cav = cav * np.clip((sp._blur(at, (~meas).astype(float), None, 1.0) - 0.6) / 0.3, 0, 1)
    # never on the lids: the skin tucked under a fold is occluded at rest but a blink shows it (a dark patch on a closed
    # lid); only surfaces that stay hidden (nostril interiors, the lip seam) take the dark-warm term
    X_ = sp.interp(at, at["V"])
    for Ve, _, _ in lk.model_mesh(spec["base"])["eyes"]:
        c_ = Ve.mean(0)
        cav = cav * sp._sstep((np.linalg.norm(X_ - c_, axis=1) - float(np.linalg.norm(Ve - c_, axis=1).max()) - 0.008) / 0.004)
    cav = sp._blur(at, cav, None, 1.0)      # (0.3 mm: a hard-edged pale crescent where it stopped, under the outer corner)
    if cav.any():
        out_l["shade"]["amount"]["d"] = out_l["shade"]["amount"]["d"] + CAVITY[2] * cav
        out_l["shade"]["od"] = out_l["shade"]["od"] + (CAVITY[2] * cav)[:, None] * V[2]
        out_l["redness"]["amount"]["h"] = out_l["redness"]["amount"]["h"] + CAVITY[3] * cav
        out_l["redness"]["od"] = out_l["redness"]["od"] + (CAVITY[3] * cav)[:, None] * V[1]
    # freckles: the fine melanin band's positive part as a density (the generator draws the dots)
    fb = sp._blur(at, A[:, 0], wm, FRECKLE_BAND[0]) - sp._blur(at, A[:, 0], wm, FRECKLE_BAND[1])
    # freckles are DARK spots on lighter skin: the band's dark excess over its light excess (symmetric noise, a soft or
    # compressed photo's grain, cancels: the positive part alone gave smooth phone photos 5-6 % "freckled" skin)
    fpos = np.clip(fb, 0, None) * sp._plain(at)
    fneg = np.clip(-fb, 0, None) * sp._plain(at)
    fden = np.clip(sp._blur(at, fpos, wm, 3.0) - sp._blur(at, fneg, wm, 3.0), 0, None)
    ref = float(np.percentile(fden[plain], 99)) if plain.any() else 0.0
    fr = np.clip(fden / FRECKLE_REF, 0, 1)                    # ABSOLUTE: an even skin has no freckle map (its own p99 as 1 made noise a map)
    if (msrc >= 0).any():
        fr[msrc >= 0] = fr[msrc[msrc >= 0]]
    fr = np.where(known, fr, float(np.median(fr[plain])) if plain.any() else 0.0)
    # BLEMISHES: small red spots (papules, marks) = the fine HAEMOGLOBIN band's dark excess over its light excess (as the
    # freckles' melanin), a density for our blemish generator (the dots are ours; where and how many is the picture's)
    hb_ = sp._blur(at, A[:, 1], wm, BLEMISH_BAND[0]) - sp._blur(at, A[:, 1], wm, BLEMISH_BAND[1])
    bden = np.clip(sp._blur(at, np.clip(hb_, 0, None) * sp._plain(at), wm, 3.0) - sp._blur(at, np.clip(-hb_, 0, None) * sp._plain(at), wm, 3.0), 0, None)
    bref = float(np.percentile(bden[plain], 99)) if plain.any() else 0.0
    bl = np.clip(bden / BLEMISH_REF, 0, 1)
    if (msrc >= 0).any():
        bl[msrc >= 0] = bl[msrc[msrc >= 0]]
    bl = np.where(known, bl, 0.0)
    rec = base * np.exp(-np.sum([l["od"] for l in out_l.values()], 0))
    res = _error(at, rec, alb, meas, regs)
    # FINE TEXTURE STRENGTH (no photo pixels): how much fine-band (< 1.2 mm) contrast the atlas has that the maps do
    # not carry, as a smooth map (4 mm): it sets the strength of OUR fine generator there (the stack alone read porcelain)
    la_, lr_ = np.log(np.maximum(alb, 1e-4)) @ Y, np.log(np.maximum(rec, 1e-4)) @ Y
    fa, frc = la_ - sp._blur(at, la_, wm, 1.2), lr_ - sp._blur(at, lr_, wm, 1.2)
    need = np.sqrt(np.clip(sp._blur(at, fa ** 2, wm, 4.0) - sp._blur(at, frc ** 2, wm, 4.0), 0, None))
    # (never near a feature edge: there the "fine band the maps miss" is the edge's own contrast (the vermilion border, a
    # nostril, a lid margin), and the fine generator laid its stipple as a grey band all along the upper lip: Tess's
    # "moustache", found by switching layers off one at a time)
    edge = np.clip(sp._blur(at, (regs["lips"] | regs["orbit"]).astype(float), None, 5.0) * 6.0, 0, 1)   # (3 mm: a faint band above the lip in the 3/4 view)
    # (a FLOOR on plain skin: a picture at 0.2-0.3 mm a pixel resolves little under 1.2 mm, so the measured band is a
    # lower bound; at the measure alone every head under the stack read smoother than its photograph)
    fine = np.clip(np.maximum(need / FINE_FULL, FINE_FLOOR * sp._plain(at)), 0, 0.8) * (1 - np.clip(sup["lips"] + sup["brow"], 0, 1)) * (1 - edge)
    if (msrc >= 0).any():
        fine[msrc >= 0] = fine[msrc[msrc >= 0]]
    fine = np.where(known, fine, float(np.median(fine[plain])) if plain.any() else 0.0)
    fine_by = {k: round(float(need[m & meas].mean()), 4) for k, m in regs.items() if (m & meas).sum() > 300}
    L = [f"skin layers {name}: the de-lit atlas as a stack ({int(meas.sum())} measured texels, {int((msrc >= 0).sum())} mirrored, {int((~known).sum())} inferred)",
         f"  axes (optical density per unit, r g b): melanin {np.round(V[0], 3).tolist()}, haemoglobin {np.round(V[1], 3).tolist()}, neutral 1 1 1; "
         f"the data's own independent axes (ICA in the shading-free plane, Tsumura 1999) lie {ica['melanin_deg']} deg / {ica['haemoglobin_deg']} deg from them "
         f"(ours are {ica['model_axes_deg']} deg apart)",
         f"  base (the lightest skin, sRGB) {np.round(sp._srgb(base), 3).tolist()}",
         "  layer: mean / p95 amount on its own support (m melanin x, h blood x, d neutral e-folds), its mean darkening there (L*)"]
    for lname, l in out_l.items():
        S = sup[l["support"]] > 0.5
        q = S & meas
        if not q.any():
            continue
        dl = sp.lab(base[None] * np.ones((int(q.sum()), 1)))[:, 0] - sp.lab(base * np.exp(-l["od"][q]))[:, 0]
        L.append(f"    {lname:12s} " + "  ".join(f"{a} {float(v[q].mean()):.3f} / {float(np.percentile(v[q], 95)):.3f}" for a, v in l["amount"].items()) + f"   -{float(dl.mean()):.1f} L")
    L.append(f"    freckles     density map: p99 of the fine melanin band {ref:.4f} ({FRECKLE_REF} = 1 on the map); share of plain skin over 0.5: {float((fr[plain] > 0.5).mean()):.2f}")
    L.append(f"    blemishes    density map: p99 of the fine haemoglobin band {bref:.4f} ({BLEMISH_REF} = 1 on the map); share of plain skin over 0.5: {float((bl[plain] > 0.5).mean()):.3f}")
    L.append("  RECOMPOSED against the atlas (measured texels): broad colour dE / mid band (1.2-6 mm) rms log luminance / what the stack leaves of the fine band:")
    L += [f"    {k:16s} dE {r['dE']:5.2f}  dL {r['dL']:+5.1f}   mid {r['mid']:.3f} of {r['mid_atlas']:.3f}   fine kept x {r['fine']:.2f}" for k, r in res.items()]
    # the vermilion border's WIDTH per segment (10-90 % of the haemoglobin step, measured across the border in the
    # atlas): what the lips layer now carries at 0.3 mm (Joe: at 0.8 mm the border went from a cut-out line to blurry)
    try:
        hs = sp._blur(at, A[:, 1], wm, 0.25)
        lipc = X0 = sp.interp(at, at["V"])
        lc = X0[regs["lips"] & meas].mean(0)
        inner, ring = regs["lips"] & meas, (sp._blur(at, regs["lips"].astype(float), None, 1.5) > 0.03) & ~regs["lips"] & meas
        hi_, lo_ = float(np.percentile(hs[inner], 60)), float(np.percentile(hs[ring], 40))
        img = sp.image(at, hs.astype(np.float32))
        gy, gx = np.gradient(img)
        gm = np.hypot(gx, gy)[at["ii"], at["jj"]] / at["mm"]          # per mm
        edge = (np.abs(hs - 0.5 * (hi_ + lo_)) < 0.15 * (hi_ - lo_)) & (sp._blur(at, regs["lips"].astype(float), None, 1.0) > 0.02) & meas
        segs = {}
        for name_, cond in (("cupid's bow (upper middle)", (X0[:, 2] > lc[2]) & (np.abs(X0[:, 0] - lc[0]) < 0.007)),
                            ("upper sides", (X0[:, 2] > lc[2]) & (np.abs(X0[:, 0] - lc[0]) >= 0.007) & (np.abs(X0[:, 0] - lc[0]) < 0.019)),
                            ("lower", (X0[:, 2] <= lc[2]) & (np.abs(X0[:, 0] - lc[0]) < 0.019)),
                            ("corners", np.abs(X0[:, 0] - lc[0]) >= 0.019)):
            q = edge & cond
            if q.sum() > 30:
                segs[name_] = round(float(0.8 * (hi_ - lo_) / max(np.median(gm[q]), 1e-6)), 2)
        L.append("  vermilion border width, 10-90 % (mm, measured in the atlas): " + ", ".join(f"{k} {v}" for k, v in segs.items()))
    except Exception as e_:  # noqa: BLE001
        L.append(f"  vermilion border width NOT MEASURED ({str(e_)[:80]})")
    L.append("  fine texture the maps do not carry (rms log luminance under 1.2 mm, by zone; " + f"{FINE_FULL} = our fine generator at full strength): " +
             ", ".join(f"{k} {v:.3f}" for k, v in fine_by.items()))
    return {"base": base, "layers": out_l, "freckles": fr, "blemishes": bl, "blemish_p99": bref, "fine": fine, "fine_by": fine_by, "provenance": prov, "recomposed": rec, "residual": res, "ica": ica, "axes": V,
            "at": at, "atlas": alb, "meas": meas, "support": sup, "zero": zero, "vermilion": vermilion, "text": "\n".join(L)}


def _error(at, rec, alb, meas, regs) -> dict:
    w = meas.astype(float)
    la, lr = np.log(np.maximum(alb, 1e-4)), np.log(np.maximum(rec, 1e-4))
    A_low, R_low = np.exp(sp._blur(at, la, w, 6.0)), np.exp(sp._blur(at, lr, w, 6.0))
    a_mid = sp._blur(at, la @ Y, w, 1.2) - sp._blur(at, la @ Y, w, 6.0)
    r_mid = sp._blur(at, lr @ Y, w, 1.2) - sp._blur(at, lr @ Y, w, 6.0)
    a_fine, r_fine = la @ Y - sp._blur(at, la @ Y, w, 1.2), lr @ Y - sp._blur(at, lr @ Y, w, 1.2)
    dlab = sp.lab(R_low) - sp.lab(A_low)
    out = {}
    for k, m in {"ALL": np.ones(len(meas), bool), **regs}.items():
        q = m & meas
        if q.sum() < 300:
            continue
        out[k] = {"dE": round(float(np.linalg.norm(dlab[q], axis=1).mean()), 2), "dL": round(float(dlab[q, 0].mean()), 2),
                  "mid": round(float(np.sqrt(np.mean((r_mid[q] - a_mid[q]) ** 2))), 4), "mid_atlas": round(float(a_mid[q].std()), 4),
                  "fine": round(float(r_fine[q].std() / max(a_fine[q].std(), 1e-6)), 2)}
    return out


def _multiplier(od: np.ndarray) -> np.ndarray:
    """A layer's stored colour: the multiplier that, mixed in at P0, gives exp(-od) (so opacity 1 is 1.25 x the layer)."""
    c = np.exp(-od)
    return np.clip(1 - (1 - c) / P0, 0.0, 1.0)


def apply(name: str, out: str | None = None, note: str = "", freckles: bool = True, log=print, lips: str = "texels") -> dict:
    """decompose() + each map stored as an image + spec["skin"]["stack"] saved (on `out`, a copy with the references,
    or on `name`). The stack then IS the head's skin colour (skin layers "skin:stack_*"): the procedural zones and lip
    colours under it are covered on the head, the fine generators (pores, freckle dots, hairs, the lid rims) lie over
    it. The files (one PNG a layer, the provenance, the recomposition, report) go to <model>/skin_layers/."""
    from pathlib import Path
    from PIL import Image
    from . import blockin as bi, images, likeness_texture as lt, store
    spec = copy.deepcopy(store.load(name))
    r = decompose(name, spec, log=log, lips=lips)
    at = r["at"]
    dst = out or name
    d = store._dir(dst) / "skin_layers"
    d.mkdir(parents=True, exist_ok=True)
    H, W = at["shape"]
    valid = sp.image(at, np.ones(len(at["ii"]), bool), False)
    fade = np.clip(sp.interp(at, at["fade"]), 0, 1)
    # every map fades out toward the head island's own border in the atlas (where the body's mesh takes over): at the raw
    # fade the stack stopped on the island's ragged edge, a soft band and a jagged line across the neck
    from scipy import ndimage as _nd
    dist_mm = _nd.distance_transform_edt(valid)[at["ii"], at["jj"]] * at["mm"]
    edge = np.clip(dist_mm / COVER_EDGE_MM, 0, 1)
    fade = fade * edge * edge * (3 - 2 * edge)
    # ... and the fade itself softened: per vertex it stepped ring by ring (a ragged colour edge across the neck)
    fade = np.clip(sp._blur(at, fade, None, COVER_SOFT_MM), 0, 1)

    def save_rgb(lin_or_mult, fname, alpha=None, srgb=True):
        a = np.zeros((H, W, 4), np.uint8)
        v = sp._srgb(lin_or_mult) if srgb else lin_or_mult
        a[..., :3] = sp._bleed(sp.image(at, (np.clip(v, 0, 1) * 255 + 0.5).astype(np.uint8)), valid)
        a[..., 3] = sp._bleed(sp.image(at, ((fade if alpha is None else alpha) * 255).astype(np.uint8)), valid)
        Image.fromarray(a, "RGBA").save(d / fname)
        return images.ingest(d / fname)
    layers_ = []
    for lname, l in r["layers"].items():
        if float(np.abs(l["od"]).max()) < 0.01:
            continue
        iid = save_rgb(_multiplier(l["od"]), f"{lname}.png")
        layers_.append({"name": lname, "image": iid, "opacity": OPACITY.get(lname, P0)})
    cov = save_rgb(np.ones((len(fade), 3)), "coverage.png")
    Image.fromarray(sp.image(at, r["provenance"])).save(d / "provenance.png")
    save_rgb(r["recomposed"], "recomposed.png")
    fr_id = save_rgb(np.repeat(r["freckles"][:, None], 3, 1), "freckles.png", alpha=np.ones(len(fade)), srgb=False)
    fine_id = save_rgb(np.repeat(r["fine"][:, None], 3, 1), "fine.png", alpha=np.ones(len(fade)), srgb=False)
    (d / "report.txt").write_text(r["text"])
    (d / "report.json").write_text(json.dumps({"residual": r["residual"], "ica": r["ica"], "axes": r["axes"].tolist(),
                                               "base": r["base"].tolist()}, indent=1))
    box = [round(float(x), 6) for x in at["box"]]
    occ_id = save_rgb(occlusion(spec, at, "still"), "occlusion.png", alpha=np.ones(len(fade)))
    occ_lid_id = save_rgb(occlusion(spec, at, "lid"), "occlusion_lid.png", alpha=np.ones(len(fade)))
    cm = crease_map(spec, at)
    cr_id = save_rgb(np.tile(crease_tint(spec, at), (len(cm), 1)), "crease.png", alpha=cm) if cm.max() > 0 else None
    spec["skin"]["stack"] = {"box": box, "base": [round(float(x), 4) for x in sp._srgb(r["base"])], "coverage": cov, "layers": layers_,
                             "freckles": fr_id, "fine": fine_id, "occlusion": occ_id, "occlusion_lid": occ_lid_id, "occlusion_strength": OCC_STRENGTH,
                             **({"crease": cr_id, "crease_strength": CREASE_STRENGTH} if cr_id else {}),
                             "head": lt.head_key(spec["base"]), "version": VERSION}
    notes = []
    sk = spec["skin"]
    if freckles:   # the freckle GENERATOR confined to the density map (dots are ours; where and how many is the picture's)
        ft = dict(sk.get("features") or {})
        dens = float(np.mean(r["freckles"][sp._plain(at) & r["meas"]] > 0.5))
        if dens > 0.03:
            ft["freckles"] = {"amount": round(min(0.3 + 2.0 * dens, 1.2), 3), "mask": [{"image": {"id": fr_id, "wrap": "uv", "box": box, "channel": "luma"}}]}
            notes.append(f"  features.freckles: amount {ft['freckles']['amount']} inside the density map ({100 * dens:.0f} % of the plain skin over half density)")
        else:
            ft.pop("freckles", None)
            notes.append("  features.freckles: none (the fine melanin band is even)")
        sk["features"] = ft
    if freckles:   # blemishes the same way: our generator, inside the picture's own density map, as strong as its p99
        ft = dict(sk.get("features") or {})
        ab = float(np.clip((r["blemish_p99"] - BLEMISH_FLOOR) / (2 * BLEMISH_REF - 2 * BLEMISH_FLOOR + 1e-9) * 1.5, 0, 1))
        if ab > 0.1:
            bl_id = save_rgb(np.repeat(r["blemishes"][:, None], 3, 1), "blemishes.png", alpha=np.ones(len(fade)), srgb=False)
            ft["blemishes"] = {"amount": round(0.6 * ab, 3), "size": 0.0012, "mask": [{"image": {"id": bl_id, "wrap": "uv", "box": box, "channel": "luma"}}]}
            notes.append(f"  features.blemishes: amount {ft['blemishes']['amount']} inside the density map (p99 {r['blemish_p99']:.4f})")
        else:
            ft.pop("blemishes", None)
        sk["features"] = ft
    h = dict(sk.get("hair") or {})
    bd = r["layers"].get("beard")
    if bd is not None and not h.get("stubble"):   # a measured beard SHADOW without hairs read as a blue-grey smear (the
        # older test head man's stubble): our stubble's hairs where the beard layer is, its own shadow off (the layer is it)
        sup_ = bd["amount"]["d"] > 0.05
        md = float(np.mean(bd["amount"]["d"][sup_])) if sup_.any() else 0.0
        if md > 0.12:
            h["stubble"] = {"amount": round(float(np.clip(md / 0.35, 0.3, 1.0)), 2), "style": "short"}
            notes.append(f"  hair.stubble: amount {h['stubble']['amount']} (the beard layer's mean {md:.2f} e-folds: hairs over its shadow)")
    if h.get("stubble"):   # one, not both: the beard layer is the shadow; our stubble keeps its hairs, not its shadow
        st = h["stubble"] if isinstance(h["stubble"], dict) else {"amount": float(h["stubble"])}
        h["stubble"] = {**st, "shadow": 0.0}
        sk["hair"] = h
        notes.append("  hair.stubble.shadow -> 0: the beard LAYER is the shadow now (our stubble keeps its hair dots)")
    if dst != name:
        rj = copy.deepcopy(bi._refs(name))
        if rj.get("blockin"):
            rj["blockin"] = {**rj["blockin"], "root": dst}
        bi._save(dst, spec, note or f"skin layer stack from {name}'s atlas", rj)
    else:
        store.save(dst, spec, note or "skin layer stack from the atlas", checked=False)
    r["text"] += "\n" + "\n".join([f"  saved: {dst} skin.stack ({len(layers_)} layers; files in {d})"] + notes)
    r["dir"] = str(d)
    return r


def check(st) -> dict | None:
    from .spec import SpecError
    if st in (None, False, {}):
        return None
    if not isinstance(st, dict) or set(st) - {"box", "base", "coverage", "layers", "freckles", "fine", "fine_strength", "head", "version", "opacity", "base_opacity", "occlusion", "occlusion_lid", "occlusion_strength", "crease", "crease_strength"} or not isinstance(st.get("layers"), list):
        raise SpecError("skin stack: {box, base, coverage, layers: [{name, image, opacity}]} (made by skin_layers.apply / skin_from_reference)")
    return st


def layers(spec: dict, st: dict, out: dict, part: str) -> None:
    """spec["skin"]["stack"] as paint layers (skin_features.build calls it FIRST: over the skin's broad colour layers,
    under every fine generator): the base colour over the head, then one multiply layer a map."""
    if not st or not st.get("layers"):
        return
    box = [float(x) for x in st["box"]]
    k = float(st.get("opacity", 1.0))
    if k <= 0:
        return
    img = lambda iid: {"id": iid, "wrap": "uv", "box": box, "channel": "alpha"}  # noqa: E731
    if float(st.get("base_opacity", 1.0)) > 0:
        out["skin:stack_base"] = {"part": part, "color": [float(x) for x in st["base"]], "opacity": round(k * float(st.get("base_opacity", 1.0)), 4), "image": img(st["coverage"])}
    for l in st["layers"]:
        op = float(l.get("opacity", P0)) * k
        if op > 0:
            out[f"skin:stack_{l['name']}"] = {"part": part, "color": "image", "mix": "multiply", "opacity": round(min(op, 1.0), 4), "image": img(l["image"])}
    if any(l["name"] == "parting" and float(l.get("opacity", P0)) > 0 for l in st["layers"]):
        # the seam's own surfaces (the lips' inner faces in a hairline gap, outside the head's atlas, so no stack layer
        # reaches them): dark in world space, a thin deep band along the closed lips' line (a pale jagged line showed
        # through a hand-edited mouth's seam)
        out["skin:stack_seam"] = {"part": part, "color": [0.22, 0.12, 0.12], "opacity": round(0.85 * k, 4),
                                  "mask": [{"spot": {"at": ["lm_mouth_corner.R", "lm_lip_seam", "lm_mouth_corner.L"],
                                                     "radius": [0.0016, 0.006, 0.0018], "soft": 0.6, "line": True}},
                                           # only the seam's own faces (they face up or down into the gap), never the lips'
                                           # front (a wide dark smudge on the lower lip)
                                           {"facing": [0, -1, 0], "range": [0.55, 0.25], "blend": "multiply"}]}
    # the pose's own lid close (base.head.pose lid_upper; a full blink = BLINK_POSE): the crease line and the lid's
    # occlusion fade with it (open = full, closed = clean); "_blink" lets the export bake them as their own map
    pose = (((spec.get("base") or {}).get("head") or {}).get("pose") or {})
    wb = float(np.clip(float(pose.get("lid_upper", 0.0) or 0.0) / BLINK_POSE, 0.0, 1.0))
    oc = float(st.get("occlusion_strength", OCC_STRENGTH)) * k
    if st.get("occlusion") and oc > 0:   # the baked occlusion (skin_layers.occlusion): linear multiplier in the image
        out["skin:stack_occlusion"] = {"part": part, "color": "image", "mix": "multiply", "opacity": round(min(oc, 1.0), 4),
                                       "image": img(st["occlusion"])}
    if st.get("occlusion_lid") and oc * (1 - wb) > 0:
        out["skin:stack_occlusion_lid"] = {"part": part, "color": "image", "mix": "multiply", "_blink": True,
                                           "opacity": round(min(oc, 1.0) * (1 - wb), 4), "image": img(st["occlusion_lid"])}
    cs = float(st.get("crease_strength", CREASE_STRENGTH)) * k
    if st.get("crease") and cs * (1 - wb) > 0:   # the fold's crease line (skin_layers.crease_map): its own strength
        out["skin:stack_crease"] = {"part": part, "color": "image", "mix": "multiply", "_blink": True,
                                    "opacity": round(min(cs, 1.0) * (1 - wb), 4), "image": img(st["crease"])}
    fs = float(st.get("fine_strength", 1.0)) * k
    if st.get("fine") and fs > 0:   # OUR fine texture (noise at two scales), as strong as the reference's fine band is there
        # PORE GRAIN: small dark speckles at the scale a photograph resolves pores (~0.4-0.5 mm, a few pixels at a face
        # close-up; the swatch pores are ~0.15 mm, sub-pixel there: a blind review read the stacked face as wax), and a
        # broad soft warm mottle; both as strong as the reference's fine band (the map) allows
        fm = {"image": {"id": st["fine"], "wrap": "uv", "box": box, "channel": "luma"}, "blend": "multiply"}
        out["skin:stack_fine0"] = {"part": part, "color": list(PORE_TINT), "mix": "multiply", "opacity": round(min(0.22 * fs, 1.0), 4),
                                   "mask": [{"noise": {"scale": PORE_SCALE, "range": [0.63, 0.72], "seed": 31}}]}   # (everywhere: the map kept it off the cheeks)
        out["skin:stack_fine1"] = {"part": part, "color": list(MOTTLE_TINT), "mix": "multiply", "opacity": round(min(0.6 * fs, 1.0), 4),
                                   "mask": [{"noise": {"scale": MOTTLE_SCALE, "range": [0.35, 0.85], "seed": 32}}, fm]}


# named edits: {layer: strength}, strength in units of the layer as measured (1 = as it is, 2 = twice the pigment, 0 = off)
def only(spec: dict, names=("lips",)) -> dict:
    """A copy whose stack lays ONLY these layers over the model's own skin (no stack base, no fine layer), and whose own
    description's groups that the layers replace are off (lips: our painted vermilion). A one-cause change."""
    from . import skin
    s = copy.deepcopy(spec)
    st = s["skin"]["stack"]
    st["base_opacity"] = 0.0
    st["fine_strength"] = 0.0
    for l in st["layers"]:
        if l["name"].rstrip("+") not in names and not (l["name"] == "parting" and "lips" in names):
            l["opacity"] = 0.0
    if "lips" in names:
        s["skin"]["only"] = [g for g in skin.GROUPS if g != "lips"]
    return s


EDITS = {"older": {"periorbital": 1.6, "shade": 1.7, "pigment": 1.15}, "blush": {"redness": 2.2}, "pale": {"redness": 0.4},
         "tan": {"pigment": 1.7}, "no_stubble": {"beard": 0.0}, "rested": {"periorbital": 0.5}, "tired": {"periorbital": 1.8}}


def edit(spec: dict, *names, **strengths) -> dict:
    """A copy of the spec with layer STRENGTHS changed: named edits (EDITS: blush, pale, tan, older, no_stubble, rested,
    tired) and / or layer=strength (1 = as measured). One map each: the others are untouched. A strength over 1.25 lays
    the same map a second time (a layer's stored multiplier is exact at opacity P0 and tops out at 1.25 x)."""
    s = copy.deepcopy(spec)
    want = {}
    for nm in names:
        want.update(EDITS[nm])
    want.update(strengths)
    new = []
    for l in s["skin"]["stack"]["layers"]:
        if l["name"].endswith("+"):
            continue                                  # (an earlier edit's second pass)
        k = float(want.get(l["name"], 1.0))
        base_op = float(OPACITY.get(l["name"], P0))
        op = base_op * k
        new.append({**l, "opacity": round(min(op, 1.0), 4)})
        if op > 1.0:
            new.append({**l, "name": l["name"] + "+", "opacity": round(min(op - 1.0, 1.0), 4)})
    s["skin"]["stack"]["layers"] = new
    if "older" in names:   # ten years in the skin only: the description's own age cues (spots, thinner drier skin, lines) + the maps above
        s["skin"]["age"] = float(s["skin"].get("age", 30)) + 10.0
        ft = dict(s["skin"].get("features") or {})
        ft["age_spots"] = max(float(ft.get("age_spots", 0.0)) if isinstance(ft.get("age_spots", 0.0), (int, float)) else 0.0, 0.5)
        s["skin"]["features"] = ft
    return s
