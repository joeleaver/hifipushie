"""The read's context: the anchor (sclera, white patch, backdrop), the tone, the shade's colour and the regions. Part of the skin read (skin_read.py has the overview)."""
from __future__ import annotations

import json

import numpy as np

from .skin_read import CLIP, STAGE, _lin, _srgb, lab
from .skin_read_frames import Albedo, WHITE_PX, atlas_frames, atlas_source, capture, stage_spec, trust, white_patch

# ---------------------------------------------------------------- the read
ZONES = ("forehead", "temple", "glabella", "nose_bridge", "nose_tip", "nose_wing", "cheek", "cheekbone", "cheek_side",
         "under_eye", "eyelid", "upper_lip", "philtrum", "mouth_corner", "soul_patch", "chin", "jaw", "jowl")
PLAIN = ("forehead", "cheek", "cheekbone", "nose_bridge", "chin")   # the face's plain skin: the double differences' zero
RHO_BLUR = 1.0          # px: picture and render are blurred this much before their ratio (sub-pixel misregistration)
RHO_CLIP = 4.0          # a pixel whose ratio is this far (x) from the view's median is not skin as we model it
MIN_PX = 40             # a region with fewer trusted pixels (weight sum) is NOT READ
SCLERA_PX = 60          # the sclera anchor needs this many pixels in a view
LIGHT_WHITE = np.array([1.0, 0.976, 0.953])   # our stage light's colour (key and fill), for the backdrop anchor
NEUTRAL = 7.0           # a backdrop within this Lab chroma of grey counts as neutral
LIGHT_SPREAD = 0.06     # a view whose picture / render ratio changes colour across the face by this much (rms of log
                        # chroma along the normal) counts half: coloured or mixed light, a painter's palette

def _wmedian(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    if x.ndim == 2:
        return np.array([_wmedian(x[:, c], w) for c in range(x.shape[1])])
    o = np.argsort(x)
    c = np.cumsum(w[o])
    return float(x[o][min(np.searchsorted(c, 0.5 * c[-1]), len(x) - 1)])


def _eye_classes(f: dict, mesh: dict, spec: dict) -> tuple:
    """(sclera, iris) pixel masks of a frame, from the eyeballs' own geometry (the angle off the gaze)."""
    ht = mesh["state"]["head"]
    fwd = np.asarray(ht.get("forward", [0, -1, 0]), float)
    fwd = fwd / np.linalg.norm(fwd)
    r = float(ht.get("eye_r", 0.012))
    from . import base_implied
    ir = base_implied.drawn_iris(spec, 0.012, legacy=0.0059 / 0.012)   # skin.eyes.iris_size, GNM's limbus, else 11.8 mm
    a_iris = np.arcsin(min(ir / r, 0.99))
    scl, iris = np.zeros(f["eye"].shape, bool), np.zeros(f["eye"].shape, bool)
    X = f["X"][f["eye"]]
    if not len(X):
        return scl, iris
    ang = np.full(len(X), np.pi)
    for c in ht["eyes"]:
        d = X - np.asarray(c, float)
        dn = np.linalg.norm(d, axis=1)
        a = np.arccos(np.clip((d @ fwd) / np.maximum(dn, 1e-9), -1, 1))
        ang = np.where(np.abs(dn - r) < 0.004, np.minimum(ang, a), ang)
    scl[f["eye"]] = ang > 1.3 * a_iris
    iris[f["eye"]] = (ang > 0.5 * a_iris) & (ang < 0.88 * a_iris)
    return scl, iris


WHITE_ALBEDO = 0.8      # a white shirt / collar / paper: what the lightness anchor takes its albedo to be


WHITE_CHROMA = 9.0      # ... within this Lab chroma of grey (after the backdrop's white balance, when there is one)
TONE_BOUND = 3.0        # L*: how far the plain skin's albedo may move from the PRIOR tone's without an exposure anchor
TONE_BOUND_WHITE = 8.0  # ... and with a known white in the picture (its albedo and its light are INFERRED: 0.8, lit as the face)
TONE_CHROMA = 5.0       # Lab a*b*: how far the plain skin's COLOUR may move from the prior's on a backdrop's white balance (a
                        # backdrop "neutral within 7" may be 7 of real colour: Garrett's painted one read his skin +9 b*, and
                        # exposed like the picture the head came out 5 b* too yellow: "orange")

TONE_CHROMA_WHITE = 10.0
TONE_SIGMA = 1.0        # L*: the solve's hold on the prior's lightness (the bound is checked after it)
TONE_SIGMA_WHITE = 12.0   # (the white leads, the bound holds: at 4 the prior took two thirds of what the white said)
WHITE_SIGMA = 0.15      # log: what a white's exposure is worth


WHITE_BACKDROP = 0.8    # a "white" darker than this x a neutral backdrop in the same picture is a pale grey thing, not a white
WHITE_OVER_SKIN = 1.1   # ... and it is brighter than the lit skin by this (albedo 0.8 against at most ~0.65)


def _white(f: dict, wb=None, backdrop_Y: float | None = None, declared: dict | None = None) -> tuple:
    """(white | None, why): a view's KNOWN WHITE (the lightness anchor: skin albedo = its albedo x skin / white, the
    white taken to be lit as the face is: INFERRED). Found (white_patch: clothing under the face) it must be NEUTRAL
    (Lab chroma < WHITE_CHROMA after the backdrop's white balance `wb`), bright (L* > 62), brighter than the lit skin
    and no darker than WHITE_BACKDROP x a neutral backdrop (a pale grey shirt is not a white: Garrett's lilac-grey one
    reads half his backdrop). declared: {"box": [x0, y0, x1, y1] picture px, "albedo": 0.8}: the caller says this
    patch is white (paper, a shirt, a wall): taken at its word."""
    Yv = np.array([0.2126, 0.7152, 0.0722])
    if declared is not None:
        from PIL import Image
        img = _lin(np.asarray(Image.open(f["image"]).convert("RGB"), float) / 255.0)
        q = white_patch(img, {}, 0.0, box=declared["box"])
        if q is None:
            return None, f"the declared white {declared['box']} is clipped or too small ({WHITE_PX} px needed)"
        q["albedo"] = float(declared.get("albedo", WHITE_ALBEDO))
        q["lab"] = [round(float(x), 1) for x in lab(q["rgb"])]
        return q, "declared"
    q = f.get("white_patch")
    if q is None:
        return None, "no clothing under the face that is bright and unclipped"
    q = dict(q)
    rgb = np.asarray(q["rgb"], float) / (np.asarray(wb, float) / max(float(np.asarray(wb, float) @ Yv), 1e-9) if wb is not None else 1.0)
    L = lab(rgb * (q["Y"] / max(float(rgb @ Yv), 1e-9)))
    q["lab"] = [round(float(x), 1) for x in L]
    q["albedo"] = WHITE_ALBEDO
    if np.hypot(L[1], L[2]) > WHITE_CHROMA:
        return None, f"the clothing under the face is coloured (Lab {q['lab']}): not a white"
    if L[0] < 62:
        return None, f"the clothing under the face is not bright (L* {L[0]:.0f}): not a white"
    if backdrop_Y is not None and q["Y"] < WHITE_BACKDROP * backdrop_Y:
        return None, (f"the pale clothing under the face (L* {L[0]:.0f}) reads {q['Y'] / backdrop_Y:.2f} x the neutral backdrop: a grey "
                      "thing, not a known white")
    sk = f["P"][trust(f) > 0.5] @ Yv if "P" in f else np.zeros(0)
    if len(sk) > 200 and q["Y"] < WHITE_OVER_SKIN * float(np.percentile(sk, 75)):
        return None, f"the pale clothing under the face (L* {L[0]:.0f}) is no brighter than the lit skin: not a known white"
    return q, "found"


def _anchor(frames: list, mesh: dict, spec: dict, mode: str = "auto") -> dict:
    """The picture's exposure and white balance against our render's: {"kind": "sclera" | "backdrop" | "none",
    "gain": per view [r, g, b] the ratio P / R is divided by, "note"}. sclera: ours through the same camera (both
    exposure and white balance); backdrop: a plain neutral backdrop gives the light's colour (lightness kept)."""
    from scipy import ndimage
    Y = np.array([0.2126, 0.7152, 0.0722])
    sc, bd, bdY = {}, {}, {}
    for f in frames:
        scl, _ = _eye_classes(f, mesh, spec)
        ok = scl & (f["alpha"] > 0.98) & (_srgb(f["P"]).max(-1) < CLIP[1]) & (_srgb(f["R"]).max(-1) < CLIP[1])
        if ok.sum() >= SCLERA_PX:
            p, r = f["P"][ok], f["R"][ok]
            pb, rb = p[p @ Y >= np.median(p @ Y)], r[r @ Y >= np.median(r @ Y)]   # the lit half of each: lashes and
            sc[f["view"]] = (np.median(pb, 0) / np.maximum(np.median(rb, 0), 1e-4), int(ok.sum()))  # lid shadows differ
        if f["parse"]:
            bg = ndimage.binary_erosion((f["parse"]["figure"] < 0.3) & (f["alpha"] < 0.02), iterations=4)
            if bg.sum() > 400:
                c = f["P"][bg]
                L = lab(c)
                med = np.median(L, 0)
                m = np.median(c, 0)
                # neutral in Lab AND in its channels' ratio (a dark blue wall has little Lab chroma), and lit
                if (np.hypot(med[1], med[2]) < NEUTRAL and np.percentile(np.abs(L[:, 0] - med[0]), 80) < 8 and med[0] > 40
                        and m.max() / max(m.min(), 1e-4) < 1.3):
                    bd[f["view"]] = (m / (m @ Y)) / (LIGHT_WHITE / (LIGHT_WHITE @ Y))
                    bdY[f["view"]] = float(m @ Y)
    if mode == "sclera" and sc:   # (not in "auto": on photographs the sclera reads 0.5-0.6 x ours against the skin and its
        # colour differs view to view; it failed as an anchor, see docs/notes/skin.md "## skinread")
        g = np.median([v[0] for v in sc.values()], 0)   # one camera set-up for a reference set: one gain
        return {"kind": "sclera", "gain": {f["view"]: (sc[f["view"]][0] if f["view"] in sc else g) for f in frames},
                "note": f"sclera through the same camera in view(s) {sorted(sc)} ({', '.join(str(v[1]) for v in sc.values())} px): "
                        "exposure and white balance; the tone's lightness rests on the sclera being lit as ours is (INFERRED)"}
    if mode in ("auto", "backdrop") and bd:
        return {"kind": "backdrop", "gain": {f["view"]: bd.get(f["view"]) for f in frames}, "level": True, "backdrop_Y": bdY,
                "note": f"plain neutral backdrop in view(s) {sorted(bd)}: white balance only (the exposure stays free)" +
                        ("" if len(bd) == len(frames) else "; the other view(s) have their own light and no anchor: their plain skin "
                         "is set to the anchored views' (they give zones, lips and folds, not the tone)")}
    return {"kind": "none", "gain": {f["view"]: None for f in frames},
            "note": "no anchor (no readable sclera, no plain neutral backdrop): the base tone is NOT READ; zones, lips and "
                    "marks are read against the face's own plain skin"}


class Context:
    """The pooled trusted pixels of every view with the picture's albedo there, and the forward model to fit to."""


def context(name: str, spec: dict | None = None, frames: list | None = None, anchor: str = "auto", log=print, white=None) -> Context:
    from scipy import ndimage
    from . import store
    from . import likeness_render
    spec = spec or store.load(name)
    src = atlas_source(spec) if frames is None else None
    if src is not None:       # the de-lit atlas is the picture (no stage, no render): docs/notes/skin.md "## projskin"
        frames = atlas_frames(spec, capture(name, spec, log=log, render=False), src, log=log)
    frames = frames or capture(name, spec, log=log)
    mesh = likeness_render.model_mesh(spec["base"])
    an = _anchor([{**f, "P": f.get("P_photo", f["P"])} for f in frames], mesh, spec, anchor if anchor not in ("prior", "white") else "auto")
    wh, wh_why = {}, {}
    decl = {int(d_["view"]): d_ for d_ in (white or [])}
    if anchor != "prior":
        for f in frames:
            q, why = _white(f, an["gain"].get(f["view"]) if an["kind"] == "backdrop" else None, (an.get("backdrop_Y") or {}).get(f["view"]),
                            decl.get(f["view"]))
            wh_why[f["view"]] = why
            if q is not None:
                wh[f["view"]] = q
    if an["kind"] == "none" and wh:      # no backdrop: the white gives the light's colour too
        Y_ = np.array([0.2126, 0.7152, 0.0722])
        an = {"kind": "white", "level": True,
              "gain": {f["view"]: ((wh[f["view"]]["rgb"] / (wh[f["view"]]["rgb"] @ Y_)) / (LIGHT_WHITE / (LIGHT_WHITE @ Y_)) if f["view"] in wh else None)
                       for f in frames},
              "note": f"a white (shirt / collar) in view(s) {sorted(wh)}: white balance from it"}
    X, n, w, vw, rho, pix = [], [], [], [], [], []
    views = []
    src_lc = {}
    if frames and frames[0].get("atlas"):
        src_lc = (atlas_source(spec) or {}).get("light_colour", {})
        an["note"] = ("SOURCE: the de-lit projection atlas (skin_project): one albedo for every view, light and shading already out; "
                      "ours = our albedo evaluated at the same surface points (no render). " + an["note"])
    for f in frames:
        t = trust(f)
        sel = t > 0.3
        pb = np.stack([ndimage.gaussian_filter(f["P"][..., c], RHO_BLUR) for c in range(3)], -1)
        rb = np.stack([ndimage.gaussian_filter(f["R"][..., c], RHO_BLUR) for c in range(3)], -1)
        r = pb[sel] / np.maximum(rb[sel], 1e-4)
        X.append(f["X"][sel]); n.append(f["n"][sel]); w.append(t[sel]); rho.append(r)
        vw.append(np.full(sel.sum(), f["view"])); pix.append(np.flatnonzero(sel.ravel()))
        views.append({"view": f["view"], "image": f["image"], "mm_per_px": round(f.get("mm_native", f["mm"]), 3), "trusted_px": int(sel.sum())})
    c = Context()
    c.name, c.spec, c.frames, c.anchor, c.mesh = name, spec, frames, an, mesh
    c.X, c.n, c.w, c.view, c.rho, c.pix = (np.concatenate(a) for a in (X, n, w, vw, rho, pix))
    c.st = stage_spec(spec)
    c.alb = Albedo(c.st, c.X, c.n, log=log)
    c.A0 = c.alb()
    plain = np.max([c.alb.zone(z) for z in PLAIN], 0)
    c.plain = plain
    Yv = np.array([0.2126, 0.7152, 0.0722])
    carried = []           # the anchored views' plain skin, picture over ours (per channel): what an unanchored view is set to
    for v in sorted(views, key=lambda v_: an["gain"][v_["view"]] is None):
        m = c.view == v["view"]
        g = an["gain"][v["view"]]
        pm = m & (plain > 0.5)
        if pm.sum() < MIN_PX:
            pm = m
        med = _wmedian(c.rho[pm], c.w[pm])
        f_ = next(q_ for q_ in frames if q_["view"] == v["view"])
        if f_.get("atlas"):
            # the atlas' plain skin has the tone skin_project fitted its lights with (the model's own): its HUE is free
            # only where something else says what colour the light was. A neutral backdrop does: the fitted light's
            # colour over the backdrop's = how far the skin's colour is from the model's tone. One correction for the
            # whole atlas (the median over the anchored views), then the lightness levelled as ever.
            cors = []
            for q_ in frames:
                bd_, lc_ = an["gain"].get(q_["view"]) if an["kind"] == "backdrop" else None, src_lc.get(q_["view"])
                if bd_ is not None and lc_ is not None:
                    true = np.asarray(bd_, float) * LIGHT_WHITE
                    cr = np.asarray(lc_, float) / (true / (true @ Yv))
                    cors.append(cr / (cr @ Yv))
            if cors:
                cor = np.median(cors, 0)
                c.rho[m] = c.rho[m] * cor
                med = med * cor
                g = np.full(3, float(med @ Yv))
                v["atlas_tone"] = [round(float(x), 3) for x in cor]
            else:
                g = med                                   # no anchor: the tone is not read (T == A on the plain skin)
        elif g is None:
            # no anchor of its own: its plain skin's mean is ours (T == A there), or the anchored views' when there are some
            g = med / (np.median(carried, 0) if carried else 1.0)
        elif an.get("level"):
            g = np.asarray(g) * float(med @ Yv) / float(np.asarray(g) @ Yv)   # white balance only
            carried.append(med / g)
        c.rho[m] = c.rho[m] / np.asarray(g)
        v["gain"] = [round(float(x), 3) for x in np.asarray(g)]
        # the light's colour across the face: log chroma of the ratio along the normal (white light on our light: none)
        lr = np.log(np.maximum(c.rho[pm], 1e-4))
        ch = lr - lr.mean(1, keepdims=True)
        Nn = np.c_[np.ones(pm.sum()), c.n[pm]]
        co, *_ = np.linalg.lstsq(Nn * c.w[pm][:, None], ch * c.w[pm][:, None], rcond=None)
        v["light_spread"] = round(float(np.sqrt((((Nn[:, 1:] - Nn[:, 1:].mean(0)) @ co[1:]) ** 2).mean())), 3)
        v["weight"] = round(1.0 / (1.0 + (v["light_spread"] / LIGHT_SPREAD) ** 2), 3)
        far = np.abs(np.log(np.maximum(c.rho[m] @ Yv, 1e-4)) - np.log(max(float(_wmedian(c.rho[pm] @ Yv, c.w[pm])), 1e-4))) > np.log(RHO_CLIP)
        ww = c.w[m]
        ww[far] = 0.0
        c.w[m] = ww * v["weight"]
        # the picture's exposure against our render under the fitted light, on the plain skin (photo_light uses it)
        v["ev"] = round(float(np.log2(max(float(_wmedian((c.rho[pm] * np.asarray(g)) @ Yv, c.w[pm] + 1e-9)), 1e-4))), 3)
    c.views = views
    try:
        from . import store as _store
        d_ = _store._dir(STAGE + name)
        if d_.exists():
            (d_ / "sr_exposure.json").write_text(json.dumps({str(v_["view"]): v_["ev"] for v_ in views}))
    except Exception:  # noqa: BLE001
        pass
    # THE LIGHTNESS ANCHOR (skinfolds). A picture does not say how light a skin is (exposure x albedo). In this order:
    #   1. the PRIOR: the model's stated tone (skin.tone: a Fitzpatrick type or its own numbers). The picture then
    #      corrects hue and saturation only; the plain skin's lightness stays within TONE_BOUND of the prior's.
    #   2. a KNOWN WHITE in the picture (shirt collar; `_white`): skin albedo = WHITE_ALBEDO x skin / white. It moves
    #      the lightness off the prior, at most TONE_BOUND_WHITE (the white's albedo and light are inferred).
    #   (the sclera stays out: lid and lash shadow, 0.45-0.9 x; a grey backdrop gives the white balance, no level)
    an["tone_prior"] = [round(float(x), 2) for x in lab(_wmedian(c.A0[plain > 0.5], c.w[plain > 0.5] + 1e-9))] if (plain > 0.5).any() else None
    an["exposure"], an["lightness"] = None, "prior"
    if wh:
        es, wts = [], []
        for v in views:
            q = wh.get(v["view"])
            m = (c.view == v["view"]) & (plain > 0.5) & (c.w > 0)
            if q is None or m.sum() < MIN_PX:
                continue
            f = next(f_ for f_ in frames if f_["view"] == v["view"])
            py = (f["P"].reshape(-1, 3)[c.pix[m]] @ Yv)
            # (the LIT skin against the white's lit part: the 75th percentile of the plain skin, as the white's own
            # upper 40 %: a face's median sits in more shade than a shirt front's bright half)
            want = q["albedo"] * float(np.percentile(py, 75)) / q["Y"]          # the plain skin's albedo luminance
            have = float(np.percentile((c.A0[m] * c.rho[m]) @ Yv, 75))
            es.append(np.log(max(want, 1e-4) / max(have, 1e-4)))
            wts.append(v["weight"] * q["px"])
            v["white"] = {"px": q["px"], "lab": q["lab"], "skin_albedo_Y": round(want, 3), "where": q["where"], "albedo": q["albedo"],
                          "declared": bool(q.get("declared"))}
        if es:
            an["exposure"] = float(np.average(es, weights=wts))
            an["lightness"] = "white"
            an["exposure_spread"] = round(float(np.std(es)), 3) if len(es) > 1 else None
    an["note"] += ("\n  LIGHTNESS: " + (
        f"a known white in view(s) {sorted(k for k in wh)} (" + "; ".join(f"view {k}: {'DECLARED' if q_.get('declared') else 'found: clothing under the face'} at "
                                                                         f"{q_['where']} px, Lab {q_['lab']}, taken as albedo {q_['albedo']}" for k, q_ in sorted(wh.items())) +
        f"; lit as the face: INFERRED) puts the plain skin "
        f"{100 * (np.exp(an['exposure']) - 1):+.0f} % from where the levelled read had it; the tone's lightness may move up to {TONE_BOUND_WHITE} L* "
        f"from the prior" if an["lightness"] == "white" else
        f"no exposure anchor in the pictures: the tone's lightness is held to the PRIOR (the model's stated skin.tone, plain skin "
        f"L* {an['tone_prior'][0] if an['tone_prior'] else '?'}) within {TONE_BOUND} L*; the pictures correct its hue and saturation only"
        + ("" if anchor == "prior" else " (a white was looked for: " + "; ".join(f"view {k}: {w_}" for k, w_ in sorted(wh_why.items())) +
           "; a backdrop is no exposure anchor: its albedo and its own light are unknown. Point at a known white with white=[{view, box, albedo}])")))
    c.T = c.A0 * c.rho
    c.dlab = lab(c.T) - lab(c.A0)
    c.J = None
    return c


SHADE_Q = (0.7, 1.35)    # the shade's colour exponents are kept within this (1 = neutral shade)
SHADE_SIGMA = 1.5        # log: how freely a region's lightness is given to SHADE the head does not cast (a deeper-set
                         # eye, the jaw's turn from the light, a light the fit got wrong) rather than to pigment (at 0.6
                         # a third of Tess's lid shade still pulled on the lid tints: 3.4 L of 15)

PRUNE = 0.25             # half chi2 units: a parameter's move worth less than this to the fit is taken back
PRIOR_TONE = 6.0         # x PRIOR for the tone's three numbers: melanin / blood / undertone trade against each other
                         # (the same colour from many triples); loose, blood ran to 0 on Tess and every layer that
                         # multiplies the tone's blood (lips, lids, flush) went inert, the lips brown from melanin alone

SHADE_SIGMA_PLAIN = 0.05  # ... on the plain zones (the lit skin the exposure is levelled on)
SHADE_SIGMA_BEARD = 0.05  # ... where a beard may be laid: its shadow IS a lightness (little colour of its own)
SHADE_MAX = 0.7          # log: no region is more than this in shade (about -20 L*)
EXPOSURE_SIGMA = 0.2     # log: the free exposure without a white (the read is already levelled on the plain skin, and the
                         # model's plain L* is held to the prior: what is left to it is small. At 0.6 it traded against shade:
                         # on the synthetic F2 head exposure went to x 0.40 with every other region "26-32 L in shade")

SHADE_LOCAL = 0.03       # log: the hold on the shaded regions' lower quartile (shade is local)
SHADE_SAY = 0.1          # log: shade from here on is named in the reply
FACE_BOUND = 3.0         # L*: the WHOLE face's mean albedo (stubble apart) may leave the prior's by this much
ATLAS_SHADE_SIGMA = 0.15  # ... when the source is the de-lit ATLAS: the light and the head's own occlusion are already out,
                          # so what a region reads darker is pigment or a form the head lacks, not a wrong light: the
                          # tints may take it (Stage 2's forms take back what is form)

ATLAS_ZONE_BOUND = (12.0, 8.0)   # ... and the zones may leave the prior further (the measurement is one albedo, all views agreed)
ZONE_BOUND = (4.0, 5.0)  # L*, a*b*: a zone's offset from the face's mean may leave the prior's by this much (pigment that
                         # no exposure anchor and no shade model vouches for); the zone layers are scaled back to it

def shade_colour(c: Context) -> np.ndarray:
    """The COLOUR OF SHADE in these pictures, measured: over the trusted skin (lips and brows apart) the slopes q of
    log(picture / ours) per channel on its luminance's. Neutral shade: 1, 1, 1. Photographs of skin: about 0.85, 1.03,
    1.18 (Tess: red falls least, blue most: bounce light off skin and scatter warm a face's shade; a painter does the
    same on purpose). A region darker than our render predicts ALONG this line is shade (or a tan: the picture cannot
    tell them apart, the prior tone does); what leaves the line (redder, yellower, greyer) is skin colour."""
    if getattr(c, "_shade_q", None) is None:
        Yv = np.array([0.2126, 0.7152, 0.0722])
        m = (c.w > 0)
        try:
            m &= (c.alb.zone("lips", 1.4) < 0.05) & (c.alb.zone("brow", 2.5) < 0.05)
        except Exception:  # noqa: BLE001
            pass
        q = np.ones(3)
        if m.sum() >= 5000:
            lr = np.log(np.maximum(c.rho[m], 1e-4))
            x = np.log(np.maximum(c.rho[m] @ Yv, 1e-4))
            x = x - _wmedian(x, c.w[m])
            ok = (x > -0.7) & (x < 0.3)
            if ok.sum() >= 5000 and float(x[ok].std()) > 0.04:
                W = np.sqrt(c.w[m][ok])
                A_ = np.c_[x[ok], np.ones(ok.sum())] * W[:, None]
                q = np.array([np.linalg.lstsq(A_, lr[ok][:, k] * W, rcond=None)[0][0] for k in range(3)])
                med = _wmedian(c.T[m], c.w[m])
                q = q / max(float((q * med * Yv).sum() / (med * Yv).sum()), 1e-3)      # (so that exp(s q) is s in luminance)
                q = np.clip(q, *SHADE_Q)
        c._shade_q = q
    return c._shade_q


def _region(c: Context, wz: np.ndarray, views: bool = True) -> dict:
    """A region's read: the picture's albedo against ours over the region's trusted pixels."""
    W = c.w * wz
    s = float(W.sum())
    if s < MIN_PX:
        return {"px": round(s, 1), "read": False}
    d = _wmedian(c.dlab, W)
    ours = lab((c.A0 * W[:, None]).sum(0) / s)
    out = {"px": round(s, 1), "read": True, "ours": [round(float(x), 1) for x in ours],
           "picture": [round(float(x), 1) for x in ours + d], "d": [round(float(x), 2) for x in d]}
    if views and len(c.views) > 1:
        out["by_view"] = {}
        for v in c.views:
            m = c.view == v["view"]
            if W[m].sum() >= MIN_PX:
                out["by_view"][v["view"]] = [round(float(x), 2) for x in _wmedian(c.dlab[m], W[m])]
    return out


def regions(c: Context) -> dict:
    """{region: weights over the pooled points}: the skin's zones, the two lips, the beard's zones."""
    if getattr(c, "_regions", None) is None:
        from . import skin as skinmod, skin_marks
        R = {z: c.alb.zone(z) for z in ZONES}
        lips, low = c.alb.zone("lips", 0.8), c.alb.zone("lip_lower", 0.8)
        for z in ZONES:
            R[z] = R[z] * (1 - lips)
        R["lip_upper"] = (lips * (1 - low)) ** 3
        R["lip_lower"] = low ** 3
        J = skinmod._joints(c.st)
        c.J = J
        if "lm_jaw_1.L" in J:
            bz = skin_marks.beard_zones(J)(c.X)
            dens = skin_marks.beard_density(J, {"trim": 0.0, "cheek_line": 0.0, "neckline": 0.0, "cheeks": 1.0, "patchy": 0.0,
                                                "density": 1.0, "seed": 0})(c.X, c.n)
            c.beard_zones = bz
            for k, u in bz.items():
                R[f"beard:{k}"] = u * dens * (1 - lips)
        c._regions = R
    return c._regions
