"""`decompose`: the de-lit atlas split into the stack's layers, with its error and multiplier. Part of the skin's layer stack (skin_layers.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_layers
from . import skin_project as sp
from . import skin_project_atlas, skin_project_detail
from .skin_layers import _atlas_of, axes, ica_check, venous_axis
from .skin_layers_lips import _lip_mask, lips_from_indications
from .skin_layers_shade import _fill_soft

def decompose(name: str, spec: dict | None = None, log=print, lips: str = "texels") -> dict:
    """The stack of a model with a de-lit atlas: {"base" (3,) linear (the lightest skin: every map is >= 0 over it),
    "layers": {name: {"amount": {axis: (n,) map}, "od": (n, 3) its optical density, "meas"/"mirror" shares}},
    "freckles": (n,) density map 0..1, "provenance" (n,) uint8 (255 measured, 170 mirrored, 85 inferred), "recomposed"
    (n, 3) linear, "residual": {...by region and band}, "ica", "axes", "at", "text"}."""
    from scipy.spatial import cKDTree
    from . import store
    from . import skin_params
    spec = spec or store.load(name)
    at, alb, cf, pj = _atlas_of(spec)
    n = len(alb)
    tone = skin_params.params(spec)["tone"]
    V = axes(tone)
    Vi = np.linalg.inv(V)                                     # amounts = D @ Vi
    meas = cf > 0.6
    regs = skin_project_detail.region_masks(at)
    plain = skin_project_detail._plain(at) & meas
    c_tone = np.median(alb[plain], 0)
    D = -np.log(np.maximum(alb, 1e-4) / c_tone)
    A = D @ Vi                                                # (n, 3): m, h, d
    wm = meas.astype(float)
    zero = np.array([np.percentile(skin_project_atlas._blur(at, A[:, k], wm, 4.0)[plain], skin_layers.LOW_PCT) for k in range(3)])
    A = A - zero                                              # over the lightest skin
    base = c_tone * np.exp(-(zero @ V))
    # an albedo over 1 cannot be laid: the stored base (sRGB) clipped its red channel at 1 and every colour over it lost
    # red (a test head's forms-first stack read grey: base [1.0, 0.93, 0.91], the photo's cheek r/g 1.42, ours 1.27). The
    # whole stack darkened instead (the lightness is the model's guess anyway: tone "picture" keeps only the hue)
    if float(base.max()) > skin_layers.BASE_MAX:
        base = base * (skin_layers.BASE_MAX / float(base.max()))
    ica = ica_check(D[plain][:: max(int(plain.sum() // 60000), 1)], V)
    sup = {"all": np.ones(n)}
    for k, names in skin_layers.SUPPORT.items():
        sup[k] = np.clip(skin_project_atlas._blur(at, np.max([regs[r] for r in names if r in regs], 0).astype(float), None, 1.5), 0, 1)
    # THE LIPS' SUPPORT IS WIDE AND SOFT (GNM's lips + LIP_REACH, fading over LIP_FADE): inside it the lips layer takes
    # everything the broad layers left at its own 0.8 mm, so the vermilion border's PROFILE is the atlas' own (soft on
    # the lower lip and at the corners, sharpest at the cupid's bow), not a mask's edge. (First version: a thresholded
    # vermilion mask multiplied the layer and cut the broad layers out: one hard colour line all round. Joe: "the lip
    # color lines are a little hard".) `vermilion` (the colour edge) is kept for the report only.
    vermilion = _lip_mask(at, regs, A[:, 1], meas)
    sup["lips"] = sp._sstep(skin_project_atlas._blur(at, regs["lips"].astype(float), None, skin_layers.LIP_REACH) / skin_layers.LIP_FADE)
    lips_core = np.clip(skin_project_atlas._blur(at, regs["lips"].astype(float), None, 0.4) * 2.0, 0, 1)
    # the mirror image of every unmeasured texel
    Xn = skin_project_atlas.interp(at, at["neutral"])
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
    for lname, axs, sname, mm in skin_layers.LAYERS:
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
            S = S * (1 - skin_layers.ORBIT_SHADE_CUT * sup["orbit"])   # laid as paint too it doubled into a dark ring round the eye
        amt = {}
        od = np.zeros((n, 3))
        for a in axs:
            k = ax[a]
            Sa = S
            if lname == "lips" and a == "d":   # the neutral darkness only ON the lips: round them it is the shadow of a form
                Sa = np.clip(skin_project_atlas._blur(at, regs["lips"].astype(float), None, 0.4) * 2.0, 0, 1)   # (the lower lip's): a dark ring
            w = known.astype(float) * (Sa > 0.05)
            if hole is not None:
                w = w * ~hole
            v = np.clip(skin_project_atlas._blur(at, R[:, k], w, mm), 0, None) * Sa
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
                    kb = skin_project_atlas._blur(at, known.astype(float), None, 2.0)
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
            ul, ll = skin_project_atlas.interp(at, g_["upper_lip"]), skin_project_atlas.interp(at, g_["lower_lip"])
            seam = np.clip(skin_project_atlas._blur(at, (ul > 0.5).astype(float), None, 1.0) * skin_project_atlas._blur(at, (ll > 0.5).astype(float), None, 1.0) * 8.0, 0, 1)
            body = regs["lips"] & meas & (seam < 0.2)
            if body.sum() > 200:
                od = np.zeros((n, 3))
                for a in axs:
                    cap = float(np.percentile(amt[a][body], 60))
                    amt[a] = np.minimum(amt[a], cap)
                    # (the lips' blood half venous, half arterial: all venous read mauve-grey to a blind review, all
                    # arterial read orange)
                    vax = venous_axis(tone) * (float(np.linalg.norm(V[1])) / max(float(np.linalg.norm(venous_axis(tone))), 1e-9))
                    od += amt[a][:, None] * ((skin_layers.LIPS_VENOUS * vax + (1 - skin_layers.LIPS_VENOUS) * V[1]) if a == "h" else V[ax[a]])
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
    Xs = skin_project_atlas.interp(at, at["V"])
    dmm = cKDTree(pts).query(Xs)[0] * 1000.0
    seam = np.exp(-0.5 * (dmm / max(skin_layers.PARTING_MM * 1.5, 1e-6)) ** 2) * (regs["lips"] | (dmm < 1.0))
    band = regs["lips"] & meas & (seam > 0.6)
    body = regs["lips"] & meas & (seam < 0.15)
    dpart = float(np.clip(np.median((A[:, 2] + A[:, 0] * 0.3)[band]) - np.median((A[:, 2] + A[:, 0] * 0.3)[body]), 0.35, skin_layers.PARTING_MAX)) if band.sum() > 50 and body.sum() > 200 else 0.4
    out_l["parting"] = {"amount": {"d": dpart * seam}, "od": (dpart * seam)[:, None] * V[2], "support": "lips", "mm": skin_layers.PARTING_MM}
    if lips == "indications":   # the lips layer replaced by the picture's outline + mid-lip colour
        li = lips_from_indications(name, spec, at, base, log=log)
        if li is not None:
            out_l["lips"] = {"amount": {"m": li["mask"]}, "od": li["od"], "support": "lips", "mm": skin_layers.EDGE_MM, "indications": li}
    # surfaces no picture saw that sit in occlusion (nostril interior, the inner lip at the seam, the lid's tuck): dark
    # and warm by their own ambient occlusion (INFERRED), on the shade (neutral) and redness (haemoglobin) layers
    from . import likeness_render
    ao = np.clip(skin_project_atlas.interp(at, likeness_render.ambient_occlusion(likeness_render.model_mesh(spec["base"]))), 0, 1)
    cav = np.where(~meas, np.clip((skin_layers.CAVITY[0] - ao) / skin_layers.CAVITY[1], 0, 1), 0.0)
    # only inside an unmeasured REGION (a nostril, the seam's inner faces), never along a sliver of unmeasured texels (a
    # UV seam or a thin gap between views on open skin drew a thin dark scratch on a jaw)
    reg_um = np.clip((skin_project_atlas._blur(at, (~meas).astype(float), None, 1.0) - 0.6) / 0.3, 0, 1)
    cav = cav * reg_um
    if skin_layers.CAVITY_SPREAD:
        sp_ = np.clip(skin_project_atlas._blur(at, cav, None, skin_layers.CAVITY_SPREAD[0]) * skin_layers.CAVITY_SPREAD[1], 0, 1) * reg_um * np.clip((skin_layers.CAVITY_SPREAD[2] - ao) / skin_layers.CAVITY_SPREAD[3], 0, 1)
        cav = np.maximum(cav, sp_)
    # never on the lids: the skin tucked under a fold is occluded at rest but a blink shows it (a dark patch on a closed
    # lid); only surfaces that stay hidden (nostril interiors, the lip seam) take the dark-warm term
    X_ = skin_project_atlas.interp(at, at["V"])
    for Ve, _, _ in likeness_render.model_mesh(spec["base"])["eyes"]:
        c_ = Ve.mean(0)
        cav = cav * sp._sstep((np.linalg.norm(X_ - c_, axis=1) - float(np.linalg.norm(Ve - c_, axis=1).max()) - 0.008) / 0.004)
    cav = skin_project_atlas._blur(at, cav, None, 1.0)      # (0.3 mm: a hard-edged pale crescent where it stopped, under the outer corner)
    if cav.any():
        out_l["shade"]["amount"]["d"] = out_l["shade"]["amount"]["d"] + skin_layers.CAVITY[2] * cav
        out_l["shade"]["od"] = out_l["shade"]["od"] + (skin_layers.CAVITY[2] * cav)[:, None] * V[2]
        out_l["redness"]["amount"]["h"] = out_l["redness"]["amount"]["h"] + skin_layers.CAVITY[3] * cav
        out_l["redness"]["od"] = out_l["redness"]["od"] + (skin_layers.CAVITY[3] * cav)[:, None] * V[1]
    # freckles: the fine melanin band's positive part as a density (the generator draws the dots)
    fb = skin_project_atlas._blur(at, A[:, 0], wm, skin_layers.FRECKLE_BAND[0]) - skin_project_atlas._blur(at, A[:, 0], wm, skin_layers.FRECKLE_BAND[1])
    # freckles are DARK spots on lighter skin: the band's dark excess over its light excess (symmetric noise, a soft or
    # compressed photo's grain, cancels: the positive part alone gave smooth phone photos 5-6 % "freckled" skin)
    fpos = np.clip(fb, 0, None) * skin_project_detail._plain(at)
    fneg = np.clip(-fb, 0, None) * skin_project_detail._plain(at)
    fden = np.clip(skin_project_atlas._blur(at, fpos, wm, 3.0) - skin_project_atlas._blur(at, fneg, wm, 3.0), 0, None)
    ref = float(np.percentile(fden[plain], 99)) if plain.any() else 0.0
    fr = np.clip(fden / skin_layers.FRECKLE_REF, 0, 1)                    # ABSOLUTE: an even skin has no freckle map (its own p99 as 1 made noise a map)
    if (msrc >= 0).any():
        fr[msrc >= 0] = fr[msrc[msrc >= 0]]
    fr = np.where(known, fr, float(np.median(fr[plain])) if plain.any() else 0.0)
    # BLEMISHES: small red spots (papules, marks) = the fine HAEMOGLOBIN band's dark excess over its light excess (as the
    # freckles' melanin), a density for our blemish generator (the dots are ours; where and how many is the picture's)
    hb_ = skin_project_atlas._blur(at, A[:, 1], wm, skin_layers.BLEMISH_BAND[0]) - skin_project_atlas._blur(at, A[:, 1], wm, skin_layers.BLEMISH_BAND[1])
    bden = np.clip(skin_project_atlas._blur(at, np.clip(hb_, 0, None) * skin_project_detail._plain(at), wm, 3.0) - skin_project_atlas._blur(at, np.clip(-hb_, 0, None) * skin_project_detail._plain(at), wm, 3.0), 0, None)
    bref = float(np.percentile(bden[plain], 99)) if plain.any() else 0.0
    bl = np.clip(bden / skin_layers.BLEMISH_REF, 0, 1)
    if (msrc >= 0).any():
        bl[msrc >= 0] = bl[msrc[msrc >= 0]]
    bl = np.where(known, bl, 0.0)
    rec = base * np.exp(-np.sum([l["od"] for l in out_l.values()], 0))
    res = _error(at, rec, alb, meas, regs)
    # FINE TEXTURE STRENGTH (no photo pixels): how much fine-band (< 1.2 mm) contrast the atlas has that the maps do
    # not carry, as a smooth map (4 mm): it sets the strength of OUR fine generator there (the stack alone read porcelain)
    la_, lr_ = np.log(np.maximum(alb, 1e-4)) @ skin_layers.Y, np.log(np.maximum(rec, 1e-4)) @ skin_layers.Y
    fa, frc = la_ - skin_project_atlas._blur(at, la_, wm, 1.2), lr_ - skin_project_atlas._blur(at, lr_, wm, 1.2)
    need = np.sqrt(np.clip(skin_project_atlas._blur(at, fa ** 2, wm, 4.0) - skin_project_atlas._blur(at, frc ** 2, wm, 4.0), 0, None))
    # (never near a feature edge: there the "fine band the maps miss" is the edge's own contrast (the vermilion border, a
    # nostril, a lid margin), and the fine generator laid its stipple as a grey band all along the upper lip: Tess's
    # "moustache", found by switching layers off one at a time)
    edge = np.clip(skin_project_atlas._blur(at, (regs["lips"] | regs["orbit"]).astype(float), None, 5.0) * 6.0, 0, 1)   # (3 mm: a faint band above the lip in the 3/4 view)
    # (a FLOOR on plain skin: a picture at 0.2-0.3 mm a pixel resolves little under 1.2 mm, so the measured band is a
    # lower bound; at the measure alone every head under the stack read smoother than its photograph)
    fine = np.clip(np.maximum(need / skin_layers.FINE_FULL, skin_layers.FINE_FLOOR * skin_project_detail._plain(at)), 0, 0.8) * (1 - np.clip(sup["lips"] + sup["brow"], 0, 1)) * (1 - edge)
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
    L.append(f"    freckles     density map: p99 of the fine melanin band {ref:.4f} ({skin_layers.FRECKLE_REF} = 1 on the map); share of plain skin over 0.5: {float((fr[plain] > 0.5).mean()):.2f}")
    L.append(f"    blemishes    density map: p99 of the fine haemoglobin band {bref:.4f} ({skin_layers.BLEMISH_REF} = 1 on the map); share of plain skin over 0.5: {float((bl[plain] > 0.5).mean()):.3f}")
    L.append("  RECOMPOSED against the atlas (measured texels): broad colour dE / mid band (1.2-6 mm) rms log luminance / what the stack leaves of the fine band:")
    L += [f"    {k:16s} dE {r['dE']:5.2f}  dL {r['dL']:+5.1f}   mid {r['mid']:.3f} of {r['mid_atlas']:.3f}   fine kept x {r['fine']:.2f}" for k, r in res.items()]
    # the vermilion border's WIDTH per segment (10-90 % of the haemoglobin step, measured across the border in the
    # atlas): what the lips layer now carries at 0.3 mm (Joe: at 0.8 mm the border went from a cut-out line to blurry)
    try:
        hs = skin_project_atlas._blur(at, A[:, 1], wm, 0.25)
        lipc = X0 = skin_project_atlas.interp(at, at["V"])
        lc = X0[regs["lips"] & meas].mean(0)
        inner, ring = regs["lips"] & meas, (skin_project_atlas._blur(at, regs["lips"].astype(float), None, 1.5) > 0.03) & ~regs["lips"] & meas
        hi_, lo_ = float(np.percentile(hs[inner], 60)), float(np.percentile(hs[ring], 40))
        img = skin_project_atlas.image(at, hs.astype(np.float32))
        gy, gx = np.gradient(img)
        gm = np.hypot(gx, gy)[at["ii"], at["jj"]] / at["mm"]          # per mm
        edge = (np.abs(hs - 0.5 * (hi_ + lo_)) < 0.15 * (hi_ - lo_)) & (skin_project_atlas._blur(at, regs["lips"].astype(float), None, 1.0) > 0.02) & meas
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
    L.append("  fine texture the maps do not carry (rms log luminance under 1.2 mm, by zone; " + f"{skin_layers.FINE_FULL} = our fine generator at full strength): " +
             ", ".join(f"{k} {v:.3f}" for k, v in fine_by.items()))
    return {"base": base, "layers": out_l, "freckles": fr, "blemishes": bl, "blemish_p99": bref, "fine": fine, "fine_by": fine_by, "provenance": prov, "recomposed": rec, "residual": res, "ica": ica, "axes": V,
            "at": at, "atlas": alb, "meas": meas, "support": sup, "zero": zero, "vermilion": vermilion, "text": "\n".join(L)}


def _error(at, rec, alb, meas, regs) -> dict:
    w = meas.astype(float)
    la, lr = np.log(np.maximum(alb, 1e-4)), np.log(np.maximum(rec, 1e-4))
    A_low, R_low = np.exp(skin_project_atlas._blur(at, la, w, 6.0)), np.exp(skin_project_atlas._blur(at, lr, w, 6.0))
    a_mid = skin_project_atlas._blur(at, la @ skin_layers.Y, w, 1.2) - skin_project_atlas._blur(at, la @ skin_layers.Y, w, 6.0)
    r_mid = skin_project_atlas._blur(at, lr @ skin_layers.Y, w, 1.2) - skin_project_atlas._blur(at, lr @ skin_layers.Y, w, 6.0)
    a_fine, r_fine = la @ skin_layers.Y - skin_project_atlas._blur(at, la @ skin_layers.Y, w, 1.2), lr @ skin_layers.Y - skin_project_atlas._blur(at, lr @ skin_layers.Y, w, 1.2)
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
    return np.clip(1 - (1 - c) / skin_layers.P0, 0.0, 1.0)
