"""`make`: the projected skin atlas from the references, and its report. Part of the skin projection (skin_project.py has the overview)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import skin_project
from .skin_project import _srgb, _sstep, lab
from .skin_project_atlas import _blur, atlas, image, interp
from .skin_project_detail import (
    _bleed, _detail, _harmonise, _plain, _pull_push, _shine, _texture_noise, _two_band, region_masks,
)
from .skin_project_eyes import iris_profile, iris_read
from .skin_project_light import fit_light, ours_albedo, transfer
from .skin_project_sample import _picture_maps, _strands, _wisps, exclude, sample_view

def make(name: str, spec: dict | None = None, views=None, size: int = skin_project.SIZE, delight: bool = True, parse: str | None = "mediapipe",
         ears: bool = False, mirror: bool = True, tone: str = "model", key: bool = True, log=print, photos: dict | None = None,
         lights: dict | None = None) -> dict:
    """The projected skin of a model with fitted references (human_refs.json: views + cameras). Returns {"albedo"
    (H, W, 4) uint8 sRGB (alpha: the head's fade into the body), "raw" (the same blend and fill with NO de-lighting),
    "detail" (H, W) uint8 groove strength, "conf" (H, W, 3) uint8 (direct view, mirrored, ours), "source" (H, W) int8
    (the strongest view per texel, -1 mirrored, -2 ours), "box", "report": {...}, "text"}.
    views: indices (default: every view with an image and a camera). tone: "model" (the projected plain skin's median
    takes the model's own skin tone: exposure and white balance are the model's, set by skin_from_reference or by
    hand) | "picture" (the picture's colour under an assumed white light; only the lightness is the model's).
    photos: {view index: (h, w, 3) uint8} instead of the references' files (tests). lights: {view: {"sh", "key"}} to
    hold the lights (tests)."""
    import time
    from PIL import Image
    from scipy import ndimage
    from scipy.spatial import cKDTree
    from . import store
    from . import likeness_render
    from . import blockin_expression, blockin_models
    t0 = time.time()
    spec = spec or store.load(name)
    rj = blockin_models._refs(name)
    at = atlas(spec["base"], size)
    n = len(at["ii"])
    VI = [i for i in (range(len(rj["views"])) if views is None else views) if rj["views"][i].get("image") and rj["cameras"][i] is not None]
    if not VI:
        raise ValueError(f"skin_project: {name} has no fitted reference views (human_reference / block_in first)")
    meshes = blockin_expression._per_view(spec["base"], rj, VI, lambda b: likeness_render.model_mesh(b))
    plain = _plain(at)
    regs = region_masks(at)
    beard = np.zeros(n, bool)
    for k_ in skin_project.BEARD_ZONES:
        if k_ in regs:
            beard |= regs[k_]
    rep: dict = {"model": name, "views": {}, "atlas": {"size": list(at["shape"][::-1]), "mm_per_texel": round(at["mm"], 3), "box": at["box"]}}
    S: dict = {}
    tr_cache: dict = {}
    for vi in VI:
        v, cam = rj["views"][vi], rj["cameras"][vi]
        img = Image.fromarray(np.asarray(photos[vi])) if photos and vi in photos else Image.open(v["image"]).convert("RGB")
        mesh = meshes[vi]
        maps = _picture_maps(img, cam, mesh, parse)
        if "hair" in maps:
            mpp = max(cam["t"][2] / cam["f"], 1e-9)          # m per picture pixel at the head
            px = max(int(round(skin_project.HAIR_GROW / mpp)), 1)
            maps["hair_grown"] = ndimage.maximum_filter(maps["hair"], 2 * px + 1)
            maps["wisp"] = _wisps(np.asarray(img), maps["hair"], mpp, maps.get("skin"))
            maps["strand"] = _strands(np.asarray(img), maps["hair"], mpp)
        s = sample_view(at, mesh, cam, np.asarray(img), maps)
        s["_skin_map"] = maps.get("skin")
        from . import face_ruler_camera
        s["iris"] = iris_profile(img, v) if abs(face_ruler_camera.view_yaw(cam)) <= skin_project.IRIS_YAW else None
        ok, notes = exclude(at, s, mesh, cam, img, v, parse, ears)
        face = _sstep((s["facing"] - skin_project.FACE[0]) / (skin_project.FACE[1] - skin_project.FACE[0]))
        s["conf"] = (s["vis"] * face * ok * ~s["clip"]).astype(np.float32)
        s.pop("maps", None)
        S[vi] = s
        rep["views"][vi] = {"image": Path(v["image"]).name, "mm_per_px": round(s["mm"], 3), **notes,
                            "seen": round(float(s["vis"].mean()), 3), "trusted": round(float((s["conf"] > 0.5).mean()), 3)}
        log(f"skin_project: view {vi} sampled ({time.time() - t0:.0f} s): seen {s['vis'].mean():.2f} trusted {(s['conf'] > 0.5).mean():.2f} {notes}")
    # ours (the fill, and the tone)
    O = ours_albedo(at, spec, log=log)
    anyc = np.max([S[vi]["conf"] for vi in VI], 0)
    core = plain & (anyc > 0.6)
    c_tone = np.median(O[core], 0) if core.sum() > 500 else np.median(O, 0)
    rep["tone"] = {"mode": tone, "ours_plain_srgb": [round(float(x), 3) for x in _srgb(c_tone)]}
    log(f"skin_project: ours evaluated ({time.time() - t0:.0f} s)")
    # RAW: no de-lighting, each view's exposure matched on the plain skin
    def blend(cols):
        return _two_band(at, [cols[vi] for vi in VI], [S[vi]["conf"] for vi in VI])
    raw_cols = {}
    for vi in VI:
        q = plain & (S[vi]["conf"] > 0.6)
        g = float((c_tone @ skin_project.Y) / max(float(np.median(S[vi]["rgb"][q] @ skin_project.Y)), 1e-4)) if q.sum() > 200 else 1.0
        raw_cols[vi] = S[vi]["rgb"] * g
    raw, Wt, src = blend(raw_cols)
    alb_cols = raw_cols
    cav_wall = np.zeros(n, bool)      # the nostril's inner wall: neither measured nor mirrored into (set below)
    if delight:
        target = np.tile(c_tone, (n, 1))
        for rnd in range(3):
            for vi in VI:
                s = S[vi]
                fit = np.flatnonzero(plain & (s["conf"] > 0.5))
                if len(fit) < 2000:
                    fit = np.flatnonzero(s["conf"] > 0.5)
                if len(fit) > 60000:
                    fit = fit[np.random.default_rng(vi).choice(len(fit), 60000, replace=False)]
                if "T" not in s:
                    mk = id(meshes[vi])
                    if mk not in tr_cache:
                        sub = np.flatnonzero(plain & (anyc > 0.3))
                        if len(sub) > 40000:
                            sub = sub[np.random.default_rng(1).choice(len(sub), 40000, replace=False)]
                        tr = transfer(meshes[vi], s["X"], s["N"], sub)
                        tr_cache[mk] = (tr, sub)
                        log(f"skin_project: light transport of view {vi}'s head ({time.time() - t0:.0f} s)")
                    tr, sub = tr_cache[mk]
                    s.update(T=tr["T"], D=tr["D"], sub=sub, sub_vis=tr["sub_vis"], ao=tr["ao"])
                held = (lights or {}).get(vi)
                lt = fit_light(s, target, fit, key=key, key_dir=(s.get("key_dir") if rnd else None) if not held else (held.get("key") or {}).get("dir"), mesh=meshes[vi],
                               colour_w=(~beard[fit]).astype(float))
                s["light"] = lt
            cols = {}
            for vi in VI:
                s = S[vi]
                Sv = s["light"]["S"]
                if tone == "picture":   # the light taken WHITE: its shading comes out, not its colour (else the hue the fit
                    Sv = np.repeat((Sv @ skin_project.Y)[:, None], 3, 1)   # gave the light, fitted against the model's tone, is divided out again)
                sy = Sv @ skin_project.Y
                ok_ = s["conf"] > 0.5
                med = float(np.median(sy[ok_])) if ok_.any() else 1.0
                medc = np.median(Sv[ok_], 0) if ok_.any() else np.ones(3)
                cols[vi] = s["rgb"] / np.maximum(Sv, skin_project.SHADE_FLOOR * medc)        # no division by near-darkness
                # a crease the model has and the picture has elsewhere (the alar groove, a nostril's rim, the lip line):
                # dividing by the model's dip paints a bright line. Where the shading dips against its surroundings the
                # albedo may not rise above its own surroundings
                wv = (s["conf"] > 0.3).astype(float)
                dip = sy / np.maximum(_blur(at, sy, wv, skin_project.DIP_MM), 1e-6)
                cy = cols[vi] @ skin_project.Y
                cap = skin_project.DIP_OVER * _blur(at, cy, wv * (dip > skin_project.DIP[1]), skin_project.DIP_MM)
                k = np.where((dip < skin_project.DIP[1]) & (cy > cap), cap / np.maximum(cy, 1e-6), 1.0)
                k = 1 + (k - 1) * _sstep((skin_project.DIP[1] - dip) / (skin_project.DIP[1] - skin_project.DIP[0]))
                cols[vi] = cols[vi] * k[:, None]
                s["lit"] = _sstep((sy / med - 0.5 * skin_project.SHADE_FLOOR) / skin_project.SHADE_FLOOR).astype(np.float32)   # deep occlusion: the picture's dark there is ours to make
            ws = [S[vi]["conf"] * S[vi]["lit"] for vi in VI]
            if rnd == 2 and len(VI) > 1:
                _harmonise(at, cols, VI, ws, rep)
            alb, Wt, src = _two_band(at, [cols[vi] for vi in VI], ws)
            if rnd < 2:
                lo = _blur(at, np.log(np.maximum(alb, 1e-4)), (Wt > 0.2).astype(float), skin_project.LOW_MM)
                target = np.exp((1 - skin_project.MU) * np.log(c_tone) + skin_project.MU * lo)
        alb = _shine(at, alb, Wt)
        alb_cols = cols
        # a cavity's dark that the picture has BESIDE the model's cavity (a nostril, the lip line: the head's nostril
        # sits a millimetre or two from the photographed one): near the model's own cavities, on the nose and round the
        # mouth, skin much darker than its surroundings is the picture's occlusion, not pigment: left out (the fill
        # takes the skin round it; the model's own cavity makes the dark where it belongs)
        ao_all = np.min([S[vi]["ao"] for vi in VI], 0)
        cav = _blur(at, (ao_all < skin_project.CAVITY_AO).astype(float), None, skin_project.CAVITY_MM) > 0.03
        ay = np.log(np.maximum(alb @ skin_project.Y, 1e-4))
        bad = np.zeros(n, bool)
        for grp in (regs["lips"], regs["nose"] | regs["upper_lip_skin"] | regs["lower_lip_skin"]):
            wq = (grp & (Wt > 0.3)).astype(float)
            if wq.sum() < 200:
                continue
            loc = _blur(at, ay, wq, 5.0)
            bad |= grp & cav & (ay < loc + np.log(skin_project.CAVITY_DARK)) & (Wt > 0.05)
        # the nostril's INNER WALL (the model's own cavity, not its blurred surroundings): the picture's rim skin lands
        # there as "measured" and exported as white hooks inside the nostrils (assembly, r19_nos_*): unmeasured, so the
        # cavity fill takes it, light or dark
        inner = regs["nose"] & (ao_all < skin_project.CAVITY_AO) & (Wt > 0.05)
        rep["nostril_wall_left_out"] = int(inner.sum())
        cav_wall = inner | (regs["nose"] & cav)    # mirror: the whole nostril neighbourhood (its upper wall reads ao > CAVITY_AO)
        bad |= inner
        if bad.any():
            soft = np.clip(_blur(at, bad.astype(float), None, 0.5) * 2.5, 0, 1)
            Wt = Wt * (1 - soft)
            rep["cavity_dark_left_out"] = round(float(bad.sum() / max(int((Wt > 0.3).sum()), 1)), 4)
        for vi in VI:
            lt = S[vi]["light"]
            q_ = S[vi]["conf"] > 0.5
            mc = np.median(lt["S"][q_], 0) if q_.any() else np.ones(3)
            rep["views"][vi]["light_colour"] = [round(float(x), 4) for x in mc / max(float(mc @ skin_project.Y), 1e-9)]   # the light's colour IF the skin has the tone it was fitted with
            rep["views"][vi]["light"] = {"colour": rep["views"][vi]["light_colour"], "fit_rms": round(lt["rms"], 4), "fit_rms_no_key": round(lt["rms0"], 4), "key": lt["key"],
                                         "ambient_share": lt["ambient_share"], "sh": np.round(lt["sh"], 4).tolist()}
        log(f"skin_project: de-lit ({time.time() - t0:.0f} s): " + "; ".join(f"view {vi} rms {S[vi]['light']['rms']:.3f} key {S[vi]['light']['key']}" for vi in VI))
    else:
        alb = raw
    # tone: the plain skin's median
    def retone(col):
        q = plain & (Wt > 0.6)
        if q.sum() < 500:
            return col, [1.0, 1.0, 1.0]
        med = np.median(col[q], 0)
        g = c_tone / np.maximum(med, 1e-5) if tone == "model" else np.full(3, float((c_tone @ skin_project.Y) / max(med @ skin_project.Y, 1e-5)))
        return col * g, [round(float(x), 3) for x in g]
    alb, g_alb = retone(alb)
    raw, _ = retone(raw)
    rep["tone"]["gain"] = g_alb
    # FILL 1: the mirror image
    direct = np.clip(Wt, 0, 1)
    conf_m = np.zeros(n)
    outs = {}
    Xn = interp(at, at["neutral"])
    have = np.flatnonzero(direct > 0.3)
    need = np.flatnonzero(direct < 0.6)
    msrc = None
    if mirror and len(have) > 1000 and len(need):
        d, j = cKDTree(Xn[have]).query(Xn[need] * [-1.0, 1.0, 1.0], distance_upper_bound=0.0008)
        good = np.isfinite(d)
        msrc = (need[good], have[j[good]])
        conf_m[msrc[0]] = skin_project.MIRROR_CONF * direct[msrc[1]]
        # nor mirrored INTO the nostril's inner wall: the other side's rim skin lands there as light hooks (r19_nos_*,
        # tp_h3_lef2n: the pale patch at the top of the nostril was conf channel "mirrored", not direct)
        conf_m[cav_wall] = 0.0
        rep["nostril_wall_mirror_blocked"] = int((cav_wall & np.isin(np.arange(n), msrc[0])).sum())
    for kname, col in (("albedo", alb), ("raw", raw)):
        if msrc is not None:
            cm = col.copy()
            cm[msrc[0]] = col[msrc[1]]
            col2, W2, _ = _two_band(at, [col, cm], [direct, conf_m])
        else:
            col2, W2 = col, direct
        outs[kname] = (col2, W2)
    Wp = np.clip(outs["albedo"][1], 0, 1)
    # FILL 2: ours, retoned to the projected skin round it, with its fine texture
    al = _sstep((_blur(at, Wp, None, 1.5) - 0.2) / 0.5) * (Wp > 0.02)
    fin = {}
    for kname, (col, _) in outs.items():
        lc = np.log(np.maximum(col, 1e-4))
        lo_p = _blur(at, lc, (Wp > 0.4).astype(float), skin_project.LOW_MM)
        lo_o = _blur(at, np.log(np.maximum(O, 1e-4)), None, skin_project.LOW_MM)
        known = (Wp > 0.5).astype(float)
        g0 = np.median((lo_p - lo_o)[Wp > 0.5], 0) if (Wp > 0.5).sum() > 500 else np.zeros(3)
        rho = _pull_push(at, lo_p - lo_o, known, g0)
        noise, tn = _texture_noise(at, lc, plain & (Wp > 0.8))
        lo_fill = lo_o + rho
        # a small hole inside the projected skin (a nostril's rim, a lid, a wisp) takes the skin round it, not our
        # zone paint: the projected broad colour carried in, handed over to ours beyond INPAINT_MM
        inp = _pull_push(at, lc, known, np.zeros(3), reaches=skin_project.INPAINT_MM)
        from scipy import ndimage as _nd
        near = _nd.gaussian_filter(image(at, known.astype(np.float32)), skin_project.INPAINT_MM[-1] / at["mm"], truncate=3.0)[at["ii"], at["jj"]]
        kin = _sstep((near - 0.08) / 0.2)
        lo_fill = kin[:, None] * inp + (1 - kin)[:, None] * lo_fill
        fill = lo_fill + (1 - kin)[:, None] * (np.log(np.maximum(O, 1e-4)) - lo_o) + noise
        fin[kname] = np.exp(al[:, None] * lc + (1 - al)[:, None] * fill)
        if kname == "albedo":
            rep["fill"] = {"texture": tn, "ours_to_projected_gain": [round(float(x), 3) for x in np.exp(g0)]}
    # DETAIL
    trust = (direct > 0.6)
    det, dn = _detail(at, fin["albedo"], trust & plain)
    brow = np.max([interp(at, at["groups"][k]) for k in ("left_brow_region", "right_brow_region", "middle_brow_region")], 0)
    lipsm = regs["lips"]
    inner = _blur(at, (direct > 0.6).astype(float), None, 1.5)          # not at the picture's own edges (a border is no line)
    facem = np.max([m for k, m in regs.items() if k not in ("lips", "brow")], 0)
    det = det * _sstep((inner - 0.8) / 0.15) * (1 - _sstep((brow - 0.2) / 0.4)) * facem
    for Ve, _, _ in likeness_render.model_mesh(spec["base"])["eyes"]:      # not on the lids (the lid's fold and lash line are FORM, not a groove)
        c_ = Ve.mean(0)
        det = det * _sstep((np.linalg.norm(interp(at, at["V"]) - c_, axis=1) - float(np.linalg.norm(Ve - c_, axis=1).max()) - skin_project.DETAIL_LID) / 0.003)
    ao = np.min([S[vi]["ao"] for vi in VI if "ao" in S[vi]], 0) if any("ao" in S[vi] for vi in VI) else None
    if ao is not None:                                         # nor where the model has a crease of its own (alar groove, lip corner)
        det = det * _sstep((ao - 0.72) / 0.15)
    rep["detail"] = dn
    # the report: coverage, what the light did not explain
    seen_share = {"direct": round(float((direct > 0.5).mean()), 3), "mirrored": round(float(((direct <= 0.5) & (conf_m > 0.2)).mean()), 3)}
    seen_share["ours"] = round(1 - seen_share["direct"] - seen_share["mirrored"], 3)
    rep["coverage"] = seen_share
    rep["coverage_by_region"] = {k: {"direct": round(float((direct[m] > 0.5).mean()), 2), "mirrored": round(float(((direct[m] <= 0.5) & (conf_m[m] > 0.2)).mean()), 2)}
                                 for k, m in regs.items() if m.sum() > 100}
    rep["views_used"] = {int(vi): round(float(((src == i) & (direct > 0.5)).sum() / max(int((direct > 0.5).sum()), 1)), 3) for i, vi in enumerate(VI)}
    if delight:
        # what the light did not explain: the albedo's mid-band dark against its surroundings, neutral vs coloured
        lc = np.log(np.maximum(alb, 1e-4))
        mid = _blur(at, lc, (direct > 0.4).astype(float), 1.5) - _blur(at, lc, (direct > 0.4).astype(float), 12.0)
        dark = np.clip(-(mid @ skin_project.Y), 0, None)
        chroma = mid - (mid @ skin_project.Y)[:, None]
        amb = {}
        for k, m in regs.items():
            q = m & (direct > 0.6)
            if q.sum() < 300:
                continue
            d = dark[q]
            strong = d > 0.06
            amb[k] = {"dark_share": round(float(strong.mean()), 3), "mean_dark": round(float(d.mean()), 3),
                      "coloured": round(float(np.median(np.linalg.norm(chroma[q][strong], axis=1) / np.maximum(d[strong], 1e-6))) if strong.sum() > 50 else 0.0, 2)}
        rep["unexplained_dark"] = amb
        # the views' agreement after de-lighting: the same skin in two pictures
        agree = {}
        for i, a_ in enumerate(VI):
            for b_ in VI[i + 1:]:
                q = (S[a_]["conf"] * S[a_]["lit"] > 0.6) & (S[b_]["conf"] * S[b_]["lit"] > 0.6)
                if q.sum() < 500:
                    continue
                def de(ca, cb):
                    la = lab(_blur(at, ca, q.astype(float), 2.0)[q])
                    lb_ = lab(_blur(at, cb, q.astype(float), 2.0)[q])
                    la -= np.median(la, 0)
                    lb_ -= np.median(lb_, 0)
                    return float(np.sqrt(np.mean(np.sum((la - lb_) ** 2, 1))))
                agree[f"{a_}-{b_}"] = {"texels": int(q.sum()), "dE_raw": round(de(raw_cols[a_], raw_cols[b_]), 2), "dE_delit": round(de(alb_cols[a_], alb_cols[b_]), 2)}
        rep["agreement"] = agree
    # the eyes: the irises' colour and limbal ring, as albedo through the gain of the skin under the eye
    gains = []
    for vi in VI:
        q = regs["under_eye"] & (S[vi]["conf"] > 0.6)
        gains.append(np.median(alb[q] / np.maximum(S[vi]["rgb"][q], 1e-4), 0) if q.sum() > 200 else np.ones(3) * float("nan"))
    ok_v = [i for i, vi in enumerate(VI) if S[vi].get("iris") is not None and np.isfinite(gains[i]).all()]
    e0 = spec["skin"].get("eyes") if isinstance((spec.get("skin") or {}).get("eyes"), dict) else {}
    ir = iris_read([S[VI[i]]["iris"] for i in ok_v], [gains[i] for i in ok_v], e0) if ok_v else None
    rep["eyes"] = ir or {"text": "irises not read (no view within 35 deg of the front with a detection)"}
    # images
    H, W = at["shape"]
    valid = image(at, np.ones(n, bool), False)
    fade = np.clip(interp(at, at["fade"]), 0, 1)
    X0 = interp(at, at["V"])
    for Ve, _, _ in likeness_render.model_mesh(spec["base"])["eyes"]:      # the lid margins stay the live procedural skin's (wet line,
        c = Ve.mean(0)                                          # caruncle, lash roots): the image is transparent there
        r = float(np.linalg.norm(Ve - c, axis=1).max())
        fade = fade * _sstep((np.linalg.norm(X0 - c, axis=1) - r - skin_project.LID_OPEN[0]) / skin_project.LID_OPEN[1])
    def rgba(col):
        a = np.zeros((H, W, 4), np.uint8)
        a[..., :3] = _bleed(image(at, (np.clip(_srgb(col), 0, 1) * 255 + 0.5).astype(np.uint8)), valid)
        a[..., 3] = _bleed(image(at, (fade * 255).astype(np.uint8)), valid)
        return a
    conf = image(at, (np.c_[direct, np.where(direct > 0.5, 0, conf_m / skin_project.MIRROR_CONF), 1 - al] * 255).astype(np.uint8))
    srcm = np.where(direct > 0.5, np.asarray(VI)[src], np.where(conf_m > 0.2, -1, -2)).astype(np.int8)
    rep["seconds"] = round(time.time() - t0, 1)
    out = {"albedo": rgba(fin["albedo"]), "raw": rgba(fin["raw"]), "detail": image(at, (np.clip(det, 0, 1) * 255).astype(np.uint8)),
           "conf": conf, "source": image(at, srcm, -3), "box": at["box"], "report": rep, "atlas_key": at["key"],
           "lights": {vi: S[vi].get("light") and {"sh": S[vi]["light"]["sh"], "key": S[vi]["light"]["key"]} for vi in VI}}
    out["text"] = report_text(rep)
    return out


def report_text(rep: dict) -> str:
    L = [f"skin_project {rep['model']}: atlas {rep['atlas']['size'][0]} x {rep['atlas']['size'][1]}, {rep['atlas']['mm_per_texel']} mm a texel"]
    for vi, v in rep["views"].items():
        s = f"  view {vi} ({v['image']}, {v['mm_per_px']} mm a pixel): trusted on {int(100 * v['trusted'])}% of the head's texels"
        rj = v.get("rejected") or {}
        if rj:
            s += "; left out of what it sees: " + ", ".join(f"{k} {int(round(100 * x))}%" for k, x in rj.items() if x > 0.004)
        s += f"; lid margin band {v.get('lid_band_mm')} mm" + (f" (the lids' landmarks sit {v['lid_misfit_mm']} mm off the picture's)" if "lid_misfit_mm" in v else "")
        e = v.get("ear")
        if e:
            s += "; ear " + ("projected" if e.get("projected") else "NOT projected") + (f" (picture skin on {int(100 * e['inside'])}% of the model's ear, {int(100 * e['beside'])}% of the band beside it)" if "inside" in e else "")
        L.append(s)
        lt = v.get("light")
        if lt:
            L.append(f"    light: fit residual {lt['fit_rms']:.3f} of the shading (no key {lt['fit_rms_no_key']:.3f}); " +
                     (f"key from {lt['key']['dir']} colour {lt['key']['rgb']}, " if lt["key"] else "no key light found (soft light), ") + f"ambient share {lt['ambient_share']}")
    c = rep["coverage"]
    L.append(f"  coverage of the head's atlas: pictures {int(100 * c['direct'])}%, mirrored (INFERRED) {int(100 * c['mirrored'])}%, our procedural skin retoned {int(100 * c['ours'])}%")
    L.append("  by region (picture / mirrored): " + ", ".join(f"{k} {int(100 * v['direct'])}/{int(100 * v['mirrored'])}" for k, v in rep["coverage_by_region"].items()))
    t = rep["tone"]
    L.append(f"  tone ({t['mode']}): the projected plain skin x {t.get('gain')} -> our skin's {t['ours_plain_srgb']} (sRGB)")
    if rep.get("agreement"):
        L.append("  the same skin in two pictures, Lab difference of the broad colour (raw -> de-lit): " +
                 ", ".join(f"views {k}: {v['dE_raw']} -> {v['dE_delit']} ({v['texels']} texels)" for k, v in rep["agreement"].items()))
    if rep.get("unexplained_dark"):
        L.append("  AMBIGUOUS: dark the fitted light does not explain, kept in the albedo (share of the region over 6% darker than its "
                 "surroundings; coloured 0 = neutral like a shadow, higher = pigment-like):")
        L.append("    " + ", ".join(f"{k} {int(100 * v['dark_share'])}% (coloured {v['coloured']})" for k, v in rep["unexplained_dark"].items()))
    f = rep.get("fill") or {}
    if f:
        L.append(f"  fill: our skin x {f['ours_to_projected_gain']} at the border; fine texture bands {f['texture']['bands_mm']} mm with std {f['texture']['std']}")
    L.append("  eyes: " + (rep.get("eyes") or {}).get("text", "-"))
    d = rep.get("detail") or {}
    L.append(f"  detail: line strength p99 {d.get('line_p99')}, coherent share of the trusted plain skin {d.get('coherent_share')}")
    return "\n".join(L)
