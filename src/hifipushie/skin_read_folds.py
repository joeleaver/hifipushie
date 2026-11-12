"""Folds: the checklist's detectors (valleys, steps, lids, fields) and `fold_read`. Part of the skin read (skin_read.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_read
from .skin_read import _srgb
from .skin_read_context import Context
from .skin_read_frames import lighting

def _valley(prof: np.ndarray, u: np.ndarray, search: float, flank: float) -> tuple:
    """(depth, position) of the darkest valley within |u| <= search against the lower of the two rims within
    `flank` of it; 0 when there is none."""
    inner = np.abs(u) <= search
    i = np.flatnonzero(inner)[np.argmin(prof[inner])]
    left = prof[(u < u[i]) & (u >= u[i] - flank)]
    right = prof[(u > u[i]) & (u <= u[i] + flank)]
    if len(left) < 2 or len(right) < 2 or abs(u[i]) > search - 1.5 * (u[1] - u[0]):
        return 0.0, float(u[i])       # (a minimum on the window's edge is the slope of something else beside the path)
    return max(float(min(left.max(), right.max()) - prof[i]), 0.0), float(u[i])


def _bil(img: np.ndarray, x, y):
    h, w = img.shape
    x = np.clip(np.asarray(x, float), 0, w - 1.001)
    y = np.clip(np.asarray(y, float), 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy


def _fold_view(f: dict, q: dict, fd: dict, ldir=None) -> dict | None:
    """One fold's path in one view: per station the valley across it in the picture, in ours, and in the picture
    over ours (the differential), or None when the view does not show the path."""
    from scipy import ndimage
    from . import humanfit_views
    Yv = np.array([0.2126, 0.7152, 0.0722])
    box = f["box"]
    k = skin_read.N / (box[2] - box[0])
    P, ac = q["P"], q["across"]
    p0 = (humanfit_views.project(f["cam"], P) - np.asarray(box[:2])) * k
    v = (humanfit_views.project(f["cam"], P + 0.001 * ac) - np.asarray(box[:2])) * k - p0       # px per mm across
    sc = np.linalg.norm(v, axis=1)
    flank = float(fd.get("flank", max(1.5 * fd["width"], 3.0)))
    U = fd["search"] + flank
    u = np.arange(-U, U + 1e-6, skin_read.FOLD_STEP)
    sx = p0[:, None, 0] + u[None, :] * v[:, None, 0]
    sy = p0[:, None, 1] + u[None, :] * v[:, None, 1]
    inb = (sx > 2) & (sx < skin_read.N - 3) & (sy > 2) & (sy < skin_read.N - 3)
    good = (f["skin"] & (f["alpha"] > 0.98)).astype(float)
    if f["parse"]:
        good = good * (f["parse"]["skin"] > 0.5) * (f["parse"]["hair"] < 0.4)
    gs = _bil(good, sx, sy) * inb
    # the station itself: on the skin the camera sees (not behind the nose), not foreshortened to nothing
    ix, iy = np.clip(np.round(p0[:, 0]).astype(int), 0, skin_read.N - 1), np.clip(np.round(p0[:, 1]).astype(int), 0, skin_read.N - 1)
    seen = (np.linalg.norm(f["X"][iy, ix] - P, axis=1) < 0.003) & (sc > 0.45 / f["mm"])
    valid = seen & (gs.mean(1) > 0.8) & (q["t"] >= float(fd.get("read_from", 0.0)))
    if valid.sum() < max(4, 0.25 * len(P)):
        return None
    sg = float(np.clip(0.3 * fd["width"] / f["mm"], 0.7, 4.0))
    lp = ndimage.gaussian_filter(np.log(np.maximum(f["P"] @ Yv, 2e-3)), sg)
    lr = ndimage.gaussian_filter(np.log(np.maximum(f["R"] @ Yv, 2e-3)), sg)
    pp, pr = _bil(lp, sx, sy), _bil(lr, sx, sy)
    # (a couple of mm along the path: a fold runs on, noise does not)
    ker = np.ones(5) / 5.0
    sm = lambda a: np.apply_along_axis(lambda c_: np.convolve(np.r_[c_[:2][::-1], c_, c_[-2:][::-1]], ker, "valid"), 0, a)  # noqa: E731
    pp, pr = sm(pp), sm(pr)
    out = {"u": u}
    for key, a in (("picture", pp), ("ours", pr)):
        dv = np.array([_valley(a[i], u, fd["search"], flank) for i in range(len(P))])
        out[key], out[key + "_u"] = dv[:, 0], dv[:, 1]
    # a "valley" deeper than any crease of skin is a feature's own edge (the mouth's corner, a nostril, lashes: the
    # model's lies a millimetre from the picture's): not a fold
    valid = valid & (out["picture"] < skin_read.FOLD_MAX) & (out["ours"] < skin_read.FOLD_MAX)
    # the step across the line (see STEP_T): windows `fw` wide starting `gap` from a centre c, plus side minus the
    # minus side, at every c within the search; the picture's over ours, signed by the light
    out["step"], out["step_u"], out["cross"] = np.zeros(len(P)), np.zeros(len(P)), np.zeros(len(P))
    if ldir is not None:
        cross = ac @ (np.asarray(ldir, float) / np.linalg.norm(ldir))
        nw = max(int(round(max(fd["width"], 2.0) / skin_read.FOLD_STEP)), 2)
        ng = max(int(round(0.25 * fd["width"] / skin_read.FOLD_STEP)), 1)
        ker = np.ones(nw) / nw
        box = lambda a: np.apply_along_axis(lambda c_: np.convolve(c_, ker, "same"), 1, a)  # noqa: E731
        off = ng + nw // 2
        D = box(pp) - box(pr)                      # the differential profile's window means
        S = np.full_like(D, np.nan)
        S[:, off:-off] = D[:, 2 * off:] - D[:, :-2 * off]
        inner = (np.abs(u) <= fd["search"]) & np.isfinite(S[0])
        sgn = -np.sign(cross)
        V = S[:, inner] * sgn[:, None]
        V = np.where(np.isfinite(V).any(1)[:, None], V, 0.0)       # (a row with no finite window: nanargmax raises)
        k = np.nanargmax(V, 1)
        # (the largest step of the light's sign within the search is positive for any noise: it counts only OVER the
        # largest step of the other sign. First version without this: on Garrett's two paintings every fold "stepped"
        # along 92-100 % of its path, the line jumping +-4 mm from station to station)
        best = np.nan_to_num(V[np.arange(len(P)), k] - np.nanmax(-V, 1), nan=0.0)   # (a station off the picture: no step)
        # ... and the picture itself must step that way there, not only its difference to ours
        Sp = np.full_like(D, np.nan)
        Bp = box(pp)
        Sp[:, off:-off] = Bp[:, 2 * off:] - Bp[:, :-2 * off]
        own = np.nan_to_num((Sp[:, inner] * sgn[:, None])[np.arange(len(P)), k], nan=0.0)
        out["step_u"] = u[inner][k]
        # (a step on the window's edge is the edge of something beside the path: on Tess both tear troughs "stepped" at
        # +5.0 mm, her lower lid's margin and lashes)
        edge = np.abs(out["step_u"]) > fd["search"] - 1.5
        out["step"] = np.where(valid & ~edge & (np.abs(cross) >= skin_read.STEP_CROSS) & (own >= 0.5 * skin_read.STEP_T), np.maximum(best, 0.0), 0.0)
        out["cross"] = np.abs(cross)
    out["valid"] = valid
    out["picture"], out["ours"] = out["picture"] * valid, out["ours"] * valid
    if valid.sum() < 2:       # (every station was a feature's edge: no read of this view, and no NaN weight)
        return None
    out["scale"] = float(np.median(sc[valid]))
    return out


def _run(mask: np.ndarray, gap: int = 3) -> tuple:
    """The longest run of True (gaps up to `gap` bridged): (i0, i1) inclusive, or None."""
    best, start, last = None, None, None
    for i, m in enumerate(mask):
        if m:
            if start is None or i - last > gap + 1:
                start = i
            last = i
            if best is None or last - start > best[1] - best[0]:
                best = (start, last)
    return best


def fold_read(c: Context) -> dict:
    """The checklist: {fold: {"readable", "why", "sides": {side: {"present", "picture", "ours", "diff" (the picture's
    valley over ours, log luminance), "excess" (ours over the picture's), "share", "extent" [t0, t1], "shift" [mm at
    N_SHIFT stations], "confidence", "views"}}}}; + "fields": the fine-line zones."""
    from . import skin as skinmod, skin_folds as sf
    J = skinmod._joints(c.st)
    part = (c.st.get("skin") or {}).get("part", "body")
    native = {f["view"]: f.get("mm_native", f["mm"]) for f in c.frames}
    out = {}
    if "lm_jaw_1.L" not in J:
        return {"folds": {}, "fields": {}, "why": "no GNM head landmarks"}
    nominal = sf.paths(c.st, part, J, None)
    ldirs = {}
    for f in c.frames:
        try:
            ldirs[f["view"]] = np.asarray(lighting(c.name, f["view"])["lights"][0]["dir"], float)
        except Exception:  # noqa: BLE001
            ldirs[f["view"]] = None
    lash = _lid_read(c, nominal)
    for name, fd in sf.FOLDS.items():
        ok_views = [f for f in c.frames if native[f["view"]] <= fd["res"]] if fd.get("read", True) else []
        row = {"readable": bool(ok_views), "sides": {}, "about": fd["about"]}
        if not fd.get("read", True):
            row["why"] = "NOT READ (" + fd["read_why"] + "): set skin.folds." + name + " by eye"
            out[name] = row
            continue
        if not ok_views:
            row["why"] = (f"cannot tell: the pictures have {min(native.values()):.2f} mm a pixel at the face, this needs "
                          f"{fd['res']} or finer (a {fd['width']} mm feature)")
            out[name] = row
            continue
        for sd in ((".L", ".R") if sf.sided(name) else ("",)):
            q = nominal[(name, sd)]
            best, acc = None, []
            for f in ok_views:
                r_ = _fold_view(f, q, fd, ldirs.get(f["view"]))
                if r_ is None:
                    continue
                vw = next(v for v in c.views if v["view"] == f["view"])["weight"]
                acc.append((f["view"], r_, vw * float(r_["valid"].sum()) * r_["scale"]))
            if not acc:
                row["sides"][sd] = {"present": None, "why": "not seen (turned away, hidden, or under hair) in any view"}
                continue
            res = {"views": [a[0] for a in acc]}
            wsum = sum(a[2] for a in acc)
            stat = {k: 0.0 for k in ("picture", "ours", "diff", "excess", "share", "step", "step_share", "cross")}
            sbest = None
            for vi, r_, w in acc:
                val = r_["valid"]
                hit = val & (r_["picture"] - r_["ours"] >= skin_read.FOLD_T) & (r_["picture"] >= skin_read.FOLD_T)
                run = _run(hit)
                # the step: where the light lies across the path
                can = val & (r_["cross"] >= skin_read.STEP_CROSS)
                shit = can & (r_["step"] >= skin_read.STEP_T)
                srun = _run(shit)
                if srun is not None:
                    # a fold's step is a LINE: its place moves smoothly from station to station (STEP_LINE mm rms about
                    # its own smoothed course), and it runs on for STEP_RUN mm
                    from scipy.ndimage import median_filter as _mf
                    seg = np.arange(srun[0], srun[1] + 1)
                    seg = seg[shit[seg]]
                    us = r_["step_u"][seg]
                    rough = float(np.sqrt(np.mean((us - _mf(us, 5, mode="nearest")) ** 2))) if len(us) >= 5 else 9.0
                    if rough > skin_read.STEP_LINE or len(seg) * sf.STATION * 1000 < skin_read.STEP_RUN:
                        srun, shit = None, np.zeros(len(val), bool)
                if can.sum() >= 4:
                    ssel = np.zeros(len(val), bool)
                    if srun:
                        ssel[srun[0]:srun[1] + 1] = True
                    suse = (ssel & can) if (ssel & can).sum() >= 4 else can
                    stat["step"] += w / wsum * float(np.nan_to_num(np.median(r_["step"][suse] / np.maximum(r_["cross"][suse], 1e-6))))
                    stat["step_share"] += w / wsum * float(shit.sum() / max(can.sum(), 1))
                    stat["cross"] += w / wsum * float(np.median(r_["cross"][can]))
                    if srun is not None and (sbest is None or w * shit.sum() > sbest[2]):
                        sbest = (vi, r_, w * shit.sum(), srun, shit)
                sel = np.zeros(len(val), bool)
                if run:
                    sel[run[0]:run[1] + 1] = True
                sel &= val
                use = sel if sel.sum() >= 4 else val
                if sel.sum() < 4:
                    # no stretch where the picture has MORE than ours: compare where the PICTURE shows its valley (the
                    # same stations round after round). Over all stations a fold the picture has along half its path
                    # read 0.03 against 0.10 of ours, laid whole: "ours has more", taken off, read PRESENT again, ...
                    prun = _run(val & (r_["picture"] >= skin_read.FOLD_T))
                    if prun is not None and prun[1] - prun[0] + 1 >= max(4, 0.3 * val.sum()):
                        psel = np.zeros(len(val), bool)
                        psel[prun[0]:prun[1] + 1] = True
                        use = psel & val
                stat["share"] += w / wsum * float(hit.sum() / max(val.sum(), 1))
                # (each alone, at its own valley: the head's own shading there is in both and cancels in the difference;
                # the valley of the RATIO image is not used: beside a fold of ours its roll and shade make false ones)
                for k in ("picture", "ours"):
                    stat[k] += w / wsum * float(np.median(r_[k][use]))
                stat["diff"] += w / wsum * float(np.median((r_["picture"] - r_["ours"])[use]))
                stat["excess"] += w / wsum * float(np.median((r_["ours"] - r_["picture"])[val]))
                wb = w * (1.0 + float(hit.sum()))          # (the view that shows the fold best places it)
                if best is None or wb > best[2]:
                    best = (vi, r_, wb, run)
            res.update({k: round(v, 4) for k, v in stat.items()})
            vi, r_, w, run = best
            res["present"] = bool(stat["share"] >= skin_read.FOLD_SHARE and stat["diff"] >= skin_read.FOLD_T + skin_read.FOLD_OWN * stat["ours"] and stat["picture"] >= skin_read.FOLD_T and run is not None)
            res["by"] = "valley" if res["present"] else None
            # (only folds that ARE steps, the ones with a roll; and STEP_MIN per unit of cross light: on a smooth young
            # head under an unknown light the mentolabial groove and both tear troughs "stepped" at 0.10-0.14, our fitted
            # light standing in for theirs; real folds at amount 1 step at 0.3-0.7. foldval case B)
            res["step_present"] = bool(sbest is not None and sf.RELIEF[name].get("roll") and stat["step_share"] >= skin_read.FOLD_SHARE
                                       and stat["step"] >= skin_read.STEP_MIN and stat["step"] * max(stat["cross"], 1e-6) >= skin_read.STEP_T)
            res["absent_in_picture"] = bool(stat["excess"] >= skin_read.FOLD_T + skin_read.FOLD_OWN * stat["picture"] and stat["ours"] >= skin_read.FOLD_T)
            t = q["t"]
            if run is not None:
                res["extent"] = [round(float(t[max(run[0] - 1, 0)]), 2), round(float(t[min(run[1] + 1, len(t) - 1)]), 2)]
                from scipy.ndimage import median_filter
                uu = median_filter(r_["picture_u"], 7, mode="nearest")
                good = r_["valid"] & (r_["picture"] - r_["ours"] >= skin_read.FOLD_T) & (r_["picture"] >= skin_read.FOLD_T)
                if good.sum() >= 3:
                    ts = np.linspace(0, 1, sf.N_SHIFT)
                    res["shift"] = [round(float(x), 2) for x in np.interp(ts, t[good], uu[good])]
                # where OURS shows the fold too, the two valleys' distance is the placement error with the light's
                # bias gone (a valley's darkest line sits off the groove, toward the wall the light misses)
                both = r_["valid"] & (r_["picture"] >= skin_read.FOLD_T) & (r_["ours"] >= skin_read.FOLD_T)
                if both.sum() >= max(4, 0.3 * r_["valid"].sum()):
                    du = median_filter(r_["picture_u"] - r_["ours_u"], 7, mode="nearest")
                    if abs(float(np.median(du[both]))) >= skin_read.FOLD_MOVE:   # (the null moves +-1 mm: less is not a difference)
                        res["move"] = [round(float(x), 2) for x in np.interp(np.linspace(0, 1, sf.N_SHIFT), t[both], du[both])]
            res["confidence"] = round(float(np.clip(stat["diff"] / (2.5 * skin_read.FOLD_T), 0, 1) * np.clip(stat["share"] / 0.5, 0, 1)), 2)
            if "shift" in res:   # a fold's line is smooth: a parabola through the stations' reads, inside the search
                ts_ = np.linspace(0, 1, len(res["shift"]))
                co = np.polyfit(ts_, res["shift"], 2)
                res["shift"] = [round(float(x), 2) for x in np.clip(np.polyval(co, ts_), -(fd["search"] - 1.0), fd["search"] - 1.0)]
            if res["step_present"] and not res["present"]:
                # a side-lit fold: no valley, a step. Placed at the step's own line (the steep wall under the roll)
                vi, r_, _, srun, shit = sbest
                res["present"], res["by"] = True, "step"
                res["views"] = sorted(set(res["views"]))
                res["extent"] = [round(float(t[max(srun[0] - 1, 0)]), 2), round(float(t[min(srun[1] + 1, len(t) - 1)]), 2)]
                if shit.sum() >= 3:
                    from scipy.ndimage import median_filter
                    uu = median_filter(r_["step_u"], 7, mode="nearest")
                    res["shift"] = [round(float(x), 2) for x in np.interp(np.linspace(0, 1, sf.N_SHIFT), t[shit], uu[shit])]
                res["confidence"] = round(float(np.clip(stat["step"] * stat["cross"] / (2.0 * skin_read.STEP_T), 0, 1) * np.clip(stat["step_share"] / 0.7, 0, 1)), 2)
            if min(native[v_] for v_ in res["views"]) > skin_read.PLACE_MM:
                for k_ in ("shift", "move", "extent"):
                    res.pop(k_, None)
                res["placed"] = "on its landmark path (the pictures are too coarse to place it)"
            if name == "lid_fold" and lash.get(sd) is not None:
                # the lash-line read PLACES the fold (the picture's own line over its own lashes); it is there when
                # either read says so, as strong as the stronger says
                lq = lash[sd]
                res["lash"] = lq["lash"]
                path_gain = (stat["step"] / skin_read.STEP_REF[name] if res.get("by") == "step" else stat["diff"] / skin_read.FOLD_REF[name]) if res["present"] else 0.0
                if lq["present"] or (res["present"] and "shift" in lq):
                    res["amount"] = round(float(np.clip(max(path_gain, lq.get("amount", 0.0)), 0, 1.5)), 3)
                    res["by"] = "lash line" + ("" if lq["present"] else f" (placed), {res.get('by')} (strength)")
                    res["present"] = True
                    res["shift"], res["extent"] = lq["shift"], lq["extent"]
                    if float(res["amount"]) >= 1.49:
                        res["placed"] = "at its strongest (the picture's fold line is darker than this control makes it)"
                    res["confidence"] = max(res["confidence"], lq["confidence"])
                    res.pop("move", None)
                    if lq["present"]:
                        res.update({k_: lq[k_] for k_ in ("picture", "ours", "diff", "excess", "share")})
                elif lq.get("works"):
                    # the lash-line read WORKS here (the picture's line, or ours, is found in 3+ columns) and says "as
                    # ours" or "ours is darker": it is the lid's read, the valley across the path is not (round 2 on
                    # Tess: her line 0.32, ours 0.30: as ours; the path's valley, 1.5 mm off her line, said "ours has
                    # more" and took half the fold off again). skinfolds2
                    res.update({k_: lq[k_] for k_ in ("picture", "ours", "diff", "excess", "share")})
                    res["present"], res["by"], res["confidence"] = False, "lash line", 0.0
                    res["absent_in_picture"] = bool(lq["excess"] >= 0.06)
                    res.pop("move", None)
            row["sides"][sd] = res
        out[name] = row
    return {"folds": out, "fields": _field_read(c, native)}


def _lid_read(c: Context, nominal: dict) -> dict:
    """{".L" | ".R": {"present", "by": "lash line", "lash": {...}, "shift", "extent", "confidence", "dark", "dark_ours"}}
    for the upper lid's fold, searched up from the PICTURE's lash line in the most frontal view fine enough
    (lidfold.read_lid; see LID_COLS); {} when no view allows it (then the path's valley read stands)."""
    from PIL import Image
    from . import lidfold, skin_folds as sf
    from . import humanfit_views
    from . import blockin_clay, blockin_models
    from .likeness_eyes import frame as eye_frame
    fd = sf.FOLDS["lid_fold"]
    rj = blockin_models._refs(c.name)
    best = None
    for f in c.frames:
        if f.get("mm_native", f["mm"]) <= fd["res"] and (best is None or abs(f["yaw"]) < abs(best["yaw"])):
            best = f
    if best is None or abs(best["yaw"]) > 25 or "R" not in best:
        return {}
    f = best
    try:
        img = Image.open(f["image"]).convert("RGB")
        P = blockin_clay.detect_view(img, rj["views"][f["view"]])
        if P is None:
            return {}
        P = np.asarray(P, float)[:, :2]
        mm = float(f.get("mm_native", f["mm"]))
        cols_p = lidfold.read_lid(img, P, mmpx=mm, fractions=skin_read.LID_COLS, reach_mm=skin_read.LID_REACH)
        # ours: the render through the same camera, the same detector points carried into its crop
        k = skin_read.N / (f["box"][2] - f["box"][0])
        # (ours at the render's full size: at the 512 crop, 0.5 mm a pixel, our own crease read 0.05-0.13 where the
        # picture's, at 0.25 mm, read 0.3: half of that was the resolution. skinfolds2)
        if "R2" in f:
            k2 = f["R2"].shape[0] / (f["box"][2] - f["box"][0])
            cols_o = lidfold.read_lid(Image.fromarray(f["R2"]), (P - np.asarray(f["box"][:2])) * k2, mmpx=f["mm"] * skin_read.N / f["R2"].shape[0],
                                      fractions=skin_read.LID_COLS, reach_mm=skin_read.LID_REACH)
        else:
            ours = Image.fromarray(np.round(255 * np.clip(_srgb(f["R"]), 0, 1)).astype(np.uint8))
            cols_o = lidfold.read_lid(ours, (P - np.asarray(f["box"][:2])) * k, mmpx=f["mm"], fractions=skin_read.LID_COLS, reach_mm=skin_read.LID_REACH)
    except Exception:  # noqa: BLE001
        return {}
    ex, ey = eye_frame(P)
    ex, ey = np.asarray(ex, float), np.asarray(ey, float)
    out = {}
    for s_, sd in ((0, ".R"), (1, ".L")):
        q = nominal.get(("lid_fold", sd))
        if q is None:
            continue
        o = P[lidfold.INNER[s_]]
        span = float((P[lidfold.OUTER[s_]] - o) @ ex)
        X = humanfit_views.project(f["cam"], q["P"]) - o
        xt, xh = X @ ex, -(X @ ey)                      # along the eye, up the face (px)
        order = np.argsort(xt * np.sign(span))
        # the lid leans back from the picture plane: a millimetre ALONG THE SKIN across the fold is this many up the
        # picture (0.4-0.6 on Tess's lids). The shift is asked in skin millimetres: the picture's are divided by it
        # (skinfolds2: laid 1:1, a fold read 1.6 mm over our path came out 0.8 over it)
        Xa = humanfit_views.project(f["cam"], q["P"] + 0.001 * q["across"]) - o
        lean = np.clip((-(Xa @ ey) - xh) * mm, 0.35, 1.0)
        # OUR lid margin through the same camera (the upper lid's landmarks): the path's height over OUR lashes
        h_own = None
        try:
            from . import skin as skinmod
            Jl = skinmod._joints(c.st)
            Mg = humanfit_views.project(f["cam"], np.array([Jl[k_ + sd] for k_ in ("lm_eye_inner", "lm_lid_upper_in", "lm_lid_upper", "lm_lid_upper_out", "lm_eye_outer")])) - o
            mt, mh = (Mg @ ex) * np.sign(span), -(Mg @ ey)
            om = np.argsort(mt)
            co_m = np.polyfit(mt[om], mh[om], 2)                    # (a lid margin is an arc)
            h_own = (xh - np.polyval(co_m, xt * np.sign(span))) * mm
        except Exception:  # noqa: BLE001
            pass
        rows = []
        for fr_, cp, co in zip(skin_read.LID_COLS, cols_p[s_], cols_o[s_]):
            tcol = fr_ * span
            lid = lidfold._interp_curve(P, lidfold.UPPER[s_], tcol, ex, ey, o)      # (down the face, px)
            h_nom = (float(np.interp(tcol * np.sign(span), (xt * np.sign(span))[order], xh[order])) + lid) * mm   # the path over the lash line
            t_path = float(np.interp(tcol * np.sign(span), (xt * np.sign(span))[order], q["t"][order]))
            rows.append({"col": fr_, "t": t_path, "tps": cp.get("tps", np.nan), "dark": cp.get("dark", 0.0), "dark_ours": co.get("dark", 0.0),
                         "tps_ours": co.get("tps", np.nan), "nominal": h_nom,
                         "lean": float(np.interp(tcol * np.sign(span), (xt * np.sign(span))[order], lean[order]))})
        good = [r_ for r_ in rows if np.isfinite(r_["tps"]) and r_["dark"] >= skin_read.LID_DARK and 1.5 <= r_["nominal"] <= 6.0]
        dark = float(np.median([r_["dark"] for r_ in rows]))
        dark_o = float(np.median([r_["dark_ours"] for r_ in rows]))
        res = {"by": "lash line", "lash": {"view": f["view"], "columns": [{k_: (round(float(v_), 2) if np.isfinite(v_) else None) for k_, v_ in r_.items()} for r_ in rows]},
               "picture": round(dark, 3), "ours": round(dark_o, 3), "diff": round(dark - dark_o, 3), "share": round(len(good) / len(rows), 2),
               "excess": round(dark_o - dark, 3), "views": [f["view"]]}
        res["present"] = bool(len(good) >= 3 and dark - dark_o >= 0.04)
        res["works"] = bool(len(good) >= 3 or sum(r_["dark_ours"] >= skin_read.LID_DARK for r_ in rows) >= 3)
        res["absent_in_picture"] = bool(dark_o - dark >= 0.08 and dark < skin_read.LID_DARK)
        res["confidence"] = round(float(np.clip(len(good) / 4.0, 0, 1) * np.clip((dark - dark_o) / 0.1, 0, 1)), 2)
        if len(good) >= 3 and h_own is not None:
            # THE LINE (skinfolds2; Joe: "that crease is still wobbly"): her fold is one smooth arc at a near-constant
            # height over her lashes. So: the picture's height over ITS lashes as a straight line in the column (2
            # numbers from the 3-5 columns: never the columns' noise), laid over OUR lash line at every station of the
            # path, in skin millimetres (/ lean), and that shift as a quadratic in t. Before: per column (picture's
            # height - the nominal path's over the PICTURE's lashes), a parabola through 5 noisy points held flat past
            # the outer columns: Tess's right eye got 2.8, 1.1, 2.6 mm along one lid.
            fr_g = np.array([r_["col"] for r_ in good])
            co_p = np.polyfit(fr_g, [r_["tps"] for r_ in good], 1, w=[max(r_["dark"], 0.05) for r_ in good])
            frs = xt / span
            use = (frs >= 0.2) & (frs <= 0.8)
            ts = q["t"][use]
            sh = (np.polyval(co_p, frs[use]) - h_own[use]) / lean[use]
            kk = np.argsort(ts)
            co = np.polyfit(ts[kk], sh[kk], 2)
            res["offset_mm"] = [round(float(np.polyval(co_p, x_)), 2) for x_ in (0.2, 0.5, 0.8)]
            ends = (float(ts.min()), float(ts.max()))
        elif len(good) >= 3:
            ts = np.array([r_["t"] for r_ in good])
            sh = np.array([(r_["tps"] - r_["nominal"]) / r_["lean"] for r_ in good])
            kk = np.argsort(ts)
            co = np.polyfit(ts[kk], sh[kk], 1 if len(good) < 4 else 2)        # a fold's line is smooth
        if len(good) >= 3:
            tn = np.linspace(0, 1, sf.N_SHIFT)
            shv = np.clip(np.polyval(co, np.clip(tn, ts.min(), ts.max())), -3, 6)
            if h_own is not None:
                # past the outer columns the constant offset ends: a crease runs into the corners with the lid, as the
                # nominal path does (the quadratic carried on gave +6 mm at the inner end: a hook)
                ramp = np.clip(np.minimum(tn / max(ends[0], 1e-3), (1 - tn) / max(1 - ends[1], 1e-3)), 0, 1)
                shv = shv * (0.25 + 0.75 * ramp * ramp * (3 - 2 * ramp))
            res["shift"] = [round(float(x), 2) for x in shv]
            res["extent"] = [0.0, 1.0]
            res["amount"] = round(float(np.clip((dark - dark_o) / skin_read.LID_REF, 0, 1.5)), 3)
            res.pop("move", None)
        out[sd] = res
    return out


def _field_read(c: Context, native: dict) -> dict:
    """Fields of fine lines (forehead, crow's feet, under the eye, round the lips): the zone's fine-line energy over
    the cheek's, in the picture and in ours."""
    from scipy import ndimage
    Yv = np.array([0.2126, 0.7152, 0.0722])
    out = {}
    cheek = c.alb.zone("cheek") > 0.5
    for name, (zone, res, _) in skin_read.FIELDS.items():
        zm = c.alb.zone(zone) > 0.5
        rows, why = [], None
        for f, v in zip(c.frames, c.views):
            if native[f["view"]] > res:
                why = f"cannot tell: {native[f['view']]:.2f} mm a pixel, fine lines need {res} or finer"
                continue
            m = c.view == f["view"]
            e = {}
            for key in ("P", "R"):
                lg = np.log(np.maximum(f[key] @ Yv, 2e-3))
                bp = ndimage.gaussian_filter(lg, skin_read.FIELD_BAND[0] / f["mm"]) - ndimage.gaussian_filter(lg, skin_read.FIELD_BAND[1] / f["mm"])
                b = bp.ravel()[c.pix[m]]
                ok = c.w[m] > 0
                if (zm[m] & ok).sum() < 300 or (cheek[m] & ok).sum() < 300:
                    e = None
                    break
                e[key] = float(np.sqrt(np.mean(b[zm[m] & ok] ** 2)) / max(np.sqrt(np.mean(b[cheek[m] & ok] ** 2)), 1e-5))
            if e:
                rows.append((v["weight"], e["P"], e["R"]))
        if not rows:
            out[name] = {"readable": False, "why": why or "the zone is not in trusted skin in any view"}
            continue
        w = np.array([r_[0] for r_ in rows])
        p, o = float(np.average([r_[1] for r_ in rows], weights=w)), float(np.average([r_[2] for r_ in rows], weights=w))
        out[name] = {"readable": True, "picture": round(p, 3), "ours": round(o, 3), "diff": round(p - o, 3)}
    return out
