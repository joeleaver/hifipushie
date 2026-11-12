"""look: the lit render, the picture's lighting, the profile contour, the sheet. Part of the block-in (blockin.py has the overview)."""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from . import blockin
from . import blockin_models
from .blockin_clay import _front, brows_on, detect_view, presented_mesh
from .blockin_expression import _per_view, view_base, view_expression
from .blockin_models import _boxes

def lit_render(mesh: dict, cam: dict, img, box=None, px=None, soft: float = 8.0):
    """The model at the picture's pixels (box), lit like the photo: the light fitted on the face's skin (two passes:
    c0 + w.n, then the ambient's AO share and the direct's scale with AO and a soft cast shadow)."""
    from PIL import Image
    from . import likeness_shape as ls
    from . import likeness_measure, likeness_render
    W, H = cam["size"]
    box = box or (0.0, 0.0, float(W), float(H))
    px = px or int(max(box[2] - box[0], box[3] - box[1]))
    _, k, ps = likeness_render.render(mesh, cam, box, px=px, brows=False, passes=True)
    Hh, Ww = ps["zb"].shape
    crop = img.crop(tuple(int(round(v)) for v in box)).resize((Ww, Hh), Image.LANCZOS)
    Y = ls._lin(crop)
    P = mesh.get("_photo_P")
    side = likeness_measure.Side(np.asarray(P, float)[:, :2], None) if P is not None else None
    mask = ps["part"] == 0
    if side is not None:
        try:
            mmpx = likeness_render._mm_per_px(cam, mesh["L"][27:36])
            mask = ls.skin_mask(side, (Hh, Ww), lambda Q: (np.asarray(Q, float) - [box[0], box[1]]) * k, k / mmpx) & mask
        except Exception:  # noqa: BLE001  (a crop the skin mask can't place: the whole skin)
            pass
    elif box[2] - box[0] < 0.6 * W and box[3] - box[1] < 0.6 * H:
        # a feature's crop of a clicked profile: the light is fitted on the whole face (inside a crop of one eye the
        # fit saw lashes, brow hair and wall, and lit the clay to white), then the crop is rendered with it
        _, lt, _ = lit_render(mesh, cam, img, soft=soft)
        im, _, ps = likeness_render.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, shadow=soft, light=lt)
        return im, lt, ps
    else:
        # no detector on the picture (a clicked profile): the light is fitted inside the face's landmark hull only;
        # the whole head took in the hair over the skull and the fit lit the face to white
        from scipy.spatial import ConvexHull
        from PIL import ImageDraw
        from . import humanfit_views
        Q = (humanfit_views.project(cam, np.asarray(mesh["L"], float)[:68]) - [box[0], box[1]]) * k
        try:
            hv = Q[ConvexHull(Q).vertices]
            hm = Image.new("L", (Ww, Hh), 0)
            ImageDraw.Draw(hm).polygon([tuple(p) for p in hv], fill=1)
            mask = mask & (np.asarray(hm) > 0)
        except Exception:  # noqa: BLE001  (degenerate hull: the whole skin)
            pass
    if mask.sum() < 200:
        mask = ps["part"] == 0
    c0, w, _ = ls.fit_light(Y, ps["nrm"], mask)
    lt = (c0, w, float(np.median(Y[mask])), 1.0)
    if blockin.LIGHT == "sh":   # ambient + key + fill / bounce: the c0 + w.n light put the nose's base at black (Garrett:
        # the band under the nose 0.19-0.34 of the tip's light, his picture 0.6-0.7; SH 0.66)
        _, _, p1 = likeness_render.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True)
        m1 = mask & (p1["part"] == 0) & (np.linalg.norm(p1["nrm"], axis=-1) > 0.5)
        X = likeness_render.sh9(p1["nrm"][m1]) * p1["ao"][m1][:, None]
        use = np.ones(len(X), bool)
        a = np.zeros(9)
        for _ in range(4):
            if use.sum() < 50:
                break
            a = np.linalg.lstsq(X[use], Y[m1][use], rcond=None)[0]
            r = Y[m1] - X @ a
            use = np.abs(r) < 2.5 * r[use].std()
        if np.all(np.isfinite(a)) and use.sum() >= 50:
            lt = (c0, w, float(np.median(Y[mask])), 1.0, a)
            im, k, ps = likeness_render.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, light=lt)
            return im, lt, ps
    _, _, p2 = likeness_render.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, shadow=soft, light=lt)
    dn = p2["nrm"] @ np.asarray(w, float)
    m2 = mask & (p2["part"] == 0)
    X = np.c_[np.ones(m2.sum()), p2["ao"][m2], (np.maximum(dn, 0) * p2["lit"])[m2], np.minimum(dn, 0)[m2]]
    A, B, C = np.linalg.lstsq(X, Y[m2], rcond=None)[0][:3]
    c0n = float(A + B)
    aw = float(np.clip(B / c0n, 0.0, 1.0)) if c0n > 1e-6 else 0.0
    # an ambient floor: a painted picture's light is not one light, and the fit put its shadow side at black (Garrett's
    # 3/4 portrait: half the clay face lost); real skin in shadow keeps ~a third of its lit level
    w2 = np.asarray(w, float) * max(float(C), 0.0)
    lt2 = (c0n, w2, lt[2], aw)
    lt = lt2 if np.all(np.isfinite(lt2[1])) and np.isfinite(c0n) else lt
    im, k, ps = likeness_render.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, shadow=soft, light=lt)
    return im, lt, ps


def photo_lighting(name: str, template: dict, vi: int | None = None) -> dict:
    """A DRESSED render's lighting (Blender suns, the stage's `template` dict: {"lights": [key, fill], "world", ...})
    re-aimed and re-balanced to the picture's own light, as the clay sheets are (lit_render's SH fit on the face's
    skin): the key along the fitted light's first-order direction, key : fill (a frontal fill from the camera, no
    shadow) from its ambient vs directional parts (the fitted c0 + w.n: ambient c0, key |w|), the face's
    front kept as bright as the template lights it. The stage's fixed key 42 deg up put the sides of a flat-lit
    phone photo's face in shadow and the dressed head read narrower and harder than the photo and the clay. Returns a
    new dict (+ "fitted": {dir, elevation_deg, key, ambient})."""
    from PIL import Image
    from . import store
    from . import humanfit_views
    rj = blockin_models._refs(name)
    vi = _front(rj) if vi is None else vi
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    mesh = presented_mesh(view_base(store.load(name)["base"], rj, vi), rj=rj)
    mesh["_photo_P"] = detect_view(img, v)
    _, lt, _ = lit_render(mesh, cam, img)
    R = humanfit_views._cam_rot(cam)
    # the first pass's c0 + w.n fit (camera-frame normals): w = the directional part, c0 = the ambient (the SH
    # coefficients, fitted with AO multiplied in, gave no stable direction: Tess's key came out from below)
    c0, w = float(lt[0]), np.asarray(lt[1], float)
    I = float(np.linalg.norm(w))
    A = max(c0, 0.1 * I)
    d = R.T @ (w / max(I, 1e-9))                               # toward the light, world
    to_cam = R.T @ np.array([0.0, 0.0, -1.0])                 # the face's front, toward the camera
    out = copy.deepcopy(template)
    key, fill_ = out["lights"][0], (out["lights"][1] if len(out["lights"]) > 1 else None)
    k0 = np.asarray(key["dir"], float) / np.linalg.norm(key["dir"])
    e_front = float(key["energy"]) * max(float(k0 @ to_cam), 0.0) + (float(fill_["energy"]) if fill_ else 0.0)
    K = e_front / max(I * max(float(d @ to_cam), 0.0) + A, 1e-9)
    key["dir"] = [round(float(x), 4) for x in d]
    key["energy"] = round(K * I, 3)
    if fill_ is None:
        fill_ = {"energy": 0.0, "angle": 40, "shadow": False, "specular": 0.0, "color": [1, 1, 1]}
        out["lights"].append(fill_)
    fill_["dir"] = [round(float(x), 4) for x in to_cam]
    fill_["energy"] = round(K * A, 3)
    out["fitted"] = {"dir": key["dir"], "elevation_deg": round(float(np.degrees(np.arcsin(np.clip(d[2], -1, 1)))), 1),
                     "key": round(I, 4), "ambient": round(A, 4)}
    return out


def fill(im, ps, share: float = None):
    """DISPLAY only (the fitted light stays as fitted for anything measured): the shadow side lifted to a fill of
    FILL x the lit skin's median, a soft knee (v' = sqrt(v^2 + f^2)): a painted picture's light put half of Garrett's
    3/4 clay at black, which no one can judge."""
    from PIL import Image
    a = np.asarray(im.convert("RGB"), float)
    on = ps["part"] >= 0
    if not on.any():
        return im.convert("RGB")
    f = (blockin.FILL if share is None else share) * float(np.percentile(a[ps["part"] == 0].mean(-1), 75)) if (ps["part"] == 0).any() else 0.0
    b = a.copy()
    b[on] = np.sqrt(a[on] ** 2 + f ** 2)
    return Image.fromarray(np.clip(b, 0, 255).astype(np.uint8))


def profile_contour(view: dict, step: int = 3) -> np.ndarray:
    """A true profile's front contour where the skin meets a plain background (the photo's own pixels), from just above
    the nasion to under the chin; hair / lashes crossing are skipped, the throat cut off. A right-facing picture (yaw > 0)
    is read mirrored and its contour mirrored back."""
    from PIL import Image
    a = np.asarray(Image.open(view["image"]).convert("RGB"), float)
    pts = dict(view.get("points") or {})
    right = float(view.get("yaw", 0)) > 0
    if right:   # (the scan below runs from the image's left: mirror the picture and the clicked points)
        a = a[:, ::-1]
        pts = {k: [a.shape[1] - 1 - float(p[0]), float(p[1])] for k, p in pts.items()}
    eo = pts.get("eye_outer.L", pts.get("eye_outer.R"))
    yb, yc = float(pts["nose_bridge"][1]), float(pts["chin"][1])
    y0, y1 = int(yb - 0.12 * (yc - yb)), int(yc + 0.22 * (yc - yb))
    # the background per row (a profile in front of a wall above and a sofa below has two): a band just in front of the most forward clicked point (a wall's light falls off across
    # the picture: its far edge is another colour), else the row's far end
    xs = [float(p[0]) for p in pts.values()]
    b1 = int(min(xs) - 0.02 * a.shape[1]) if xs else 15
    b0 = max(0, b1 - int(0.04 * a.shape[1]))
    bg = np.median(a[:, b0:max(b1, b0 + 15)], 1)[:, None, :]
    lum = a.mean(-1)
    # differs from the row's background in colour OR in hue alone: a warm wall can be as bright and as red as skin
    # (a tan wall behind a fair face: |rgb| differs by ~35, the chromaticity (rgb / sum) by ~0.07, the wall's own ~0.005)
    from scipy.ndimage import uniform_filter
    ch = uniform_filter(a / np.maximum(a.sum(-1, keepdims=True), 1.0), (5, 5, 1))   # (sensor noise in the hue)
    chb = bg / np.maximum(bg.sum(-1, keepdims=True), 1.0)
    fg = ((np.abs(a - bg).sum(-1) > 40) | (np.abs(ch - chb).sum(-1) > 0.05)) & (lum > 0.55 * np.median(lum[int(yb):int(yc), :]))
    # and skin-like: a textured background (a leather sofa's highlights) differs from its row's left end too; skin is
    # told by its warmth ((r - b) / sum) against a patch of cheek in front of the ear (between nose base and eye)
    if "nose_base" in pts and eo is not None:
        cx, cy = (np.asarray(pts["nose_base"], float) + 2.0 * np.asarray(eo, float)) / 3.0
        r_ = max(4, int(0.04 * (yc - yb)))
        patch = a[int(cy) - r_:int(cy) + r_, int(cx) - r_:int(cx) + r_].reshape(-1, 3)
        if len(patch):
            warm = (a[..., 0] - a[..., 2]) / np.maximum(a.sum(-1), 1.0)
            pw = (patch[:, 0] - patch[:, 2]) / np.maximum(patch.sum(-1), 1.0)
            fg &= (warm > 0.4 * float(np.median(pw))) & (lum > 0.4 * float(np.median(patch.mean(-1))))
    out = []
    for y in range(max(y0, 0), min(y1, a.shape[0]), step):
        run = np.convolve(fg[y].astype(float), np.ones(6), "valid") >= 6
        if not run.any():
            continue
        x = float(np.argmax(run))
        if out and y > yc and x - out[-1][0] > 12.0 * step / 6:
            break
        out.append([x, float(y)])
    out = np.array(out)
    if len(out) >= 5:   # (single rows where lashes / a shadowed fold break the run: a 5-row median)
        from scipy.ndimage import median_filter
        out[:, 0] = median_filter(out[:, 0], 5, mode="nearest")
    if right and len(out):
        out[:, 0] = a.shape[1] - 1 - out[:, 0]
    return out


def _eye_anchor(view, Pd, Lm):
    """Registration: the photo's and the model's eye corners + nasion (a profile: nasion + outer eye corner)."""
    if abs(float(view.get("yaw", 0))) < 70:
        if Pd is not None:
            a_ph = np.asarray(Pd, float)[[33, 133, 263, 362, 168], :2].mean(0)
        else:
            pts = view.get("points") or {}
            got = [pts[k] for k in ("lm36", "lm39", "lm42", "lm45", "lm27") if k in pts]
            if not got:
                return None, None
            a_ph = np.mean(got, 0)
        return np.asarray(a_ph, float), Lm[[36, 39, 42, 45, 27]].mean(0)
    pts = view["points"]
    if "eye_outer.L" in pts:   # (the side the picture shows: her left = lm45, her right = lm36)
        return np.mean([pts["nose_bridge"], pts["eye_outer.L"]], 0), Lm[[27, 45]].mean(0)
    return np.mean([pts["nose_bridge"], pts["eye_outer.R"]], 0), Lm[[27, 36]].mean(0)


def look(name: str, out: str, views: list | None = None, T: int = 330, before: str | None = None) -> dict:
    """The block-in sheet: per view photo | clay under the photo's fitted light (hair cap, the person's brows, a
    presentable eye) | 50 % overlay | outline difference (photo red, clay green) | squinted photo | squinted clay,
    registered at the EYES + nasion (a 2D shift: a tracing over the photo, never on the outline it should judge).
    before = another model (a step's source): per view a second row photo | before | after | the change (|after -
    before| x4) | squint before | squint after: a half-sd step is hard to see side by side with the photo alone.
    Returns {"out", "views": [{"view", "shift_px"}]}."""
    from PIL import Image, ImageDraw, ImageFilter
    from . import likeness, store
    from . import humanfit_views
    from . import likeness_render
    rj = blockin_models._refs(name)
    base = store.load(name)["base"]
    VI = list(range(len(rj["views"]))) if views is None else [int(v) for v in views]
    meshes = _per_view(base, rj, VI, lambda b: presented_mesh(b, rj=rj))   # (each picture's expression, if fitted)
    boxes = (rj.get("blockin") or {}).get("boxes") or _boxes(base, rj)
    cols = ["photo", f"{name} (photo's light)", "50% overlay", "outline: photo red / clay green", "squint photo", "squint clay"]
    meshes_b = _per_view(store.load(before)["base"], rj, VI, lambda b: presented_mesh(b, rj=rj)) if before else None
    per = 2 if before else 1
    sheet = Image.new("RGB", (T * len(cols), (T + 18) * len(VI) * per + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(cols):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    info = []
    for i, vi in enumerate(VI):
        v, cam = rj["views"][vi], rj["cameras"][vi]
        mesh, mesh_b = meshes[vi], (meshes_b[vi] if meshes_b else None)
        st = mesh["state"]
        img = Image.open(v["image"]).convert("RGB")
        box = tuple(boxes[vi])
        side = box[2] - box[0]
        px = 2 * T
        k = px / side
        front = abs(float(v.get("yaw", 0))) < 70
        Pd = detect_view(img, v) if front else None
        mesh["_photo_P"] = Pd
        Lm = humanfit_views.project(cam, st["L"])
        a_ph, a_md = _eye_anchor(v, Pd, Lm)
        sh = np.zeros(2) if a_ph is None else a_ph - a_md
        pbox = (box[0] + sh[0], box[1] + sh[1], box[2] + sh[0], box[3] + sh[1])
        ph = img.crop(tuple(int(round(b)) for b in pbox)).resize((px, px), Image.LANCZOS)
        cl, _, ps = lit_render(mesh, cam, img, box=box, px=px)
        cl = brows_on(fill(cl, ps), ps, mesh, rj, cam, box, k)
        to = lambda Q: [((q[0] - box[0]) * k, (q[1] - box[1]) * k) for q in Q]  # noqa: E731
        to_ph = lambda Q: [((q[0] - pbox[0]) * k, (q[1] - pbox[1]) * k) for q in Q]  # noqa: E731
        ov = Image.blend(ph, cl, 0.5)
        ol = ph.copy().convert("L").convert("RGB")
        d = ImageDraw.Draw(ol)
        if front:
            if Pd is not None:
                Pp = np.asarray(Pd, float)[likeness.OVAL, :2]
                d.line(to_ph(np.r_[Pp, Pp[:1]]), fill=(230, 30, 30), width=3)
            full, _, pf = lit_render(mesh, cam, img)
            Pm_ = detect_view(fill(full, pf), v)
            if Pm_ is not None:
                Pm = np.asarray(Pm_, float)[likeness.OVAL, :2]
                d.line(to(np.r_[Pm, Pm[:1]]), fill=(30, 200, 30), width=3)
        else:
            try:
                d.line(to_ph(profile_contour(v)), fill=(230, 30, 30), width=3)
            except Exception:  # noqa: BLE001  (a profile without a plain background: the clay's edge alone)
                pass
            e = np.asarray(Image.fromarray((ps["part"] >= 0).astype(np.uint8) * 255).filter(ImageFilter.FIND_EDGES)) > 0
            e[:2], e[-2:], e[:, :2], e[:, -2:] = False, False, False, False   # (the crop's own border is no edge)
            olA = np.asarray(ol).copy()
            olA[e] = (30, 200, 30)
            ol = Image.fromarray(olA)
        sg = float(blockin.SQUINT_MM / likeness_render._mm_per_px(cam, mesh["L"][27:48]) * k)
        sq = lambda im: im.convert("L").filter(ImageFilter.GaussianBlur(sg)).convert("RGB")  # noqa: E731
        y = 18 + i * per * (T + 18)
        for j, im in enumerate((ph, cl, ov, ol, sq(ph), sq(cl))):
            sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, y))
        xn = len(view_expression(rj, vi))
        dr.text((4, y + T + 2), f"view {vi} (yaw {float(v.get('yaw', 0)):g}): {Path(v['image']).name}; registered at "
                f"the eyes, shift {sh[0]:+.0f}, {sh[1]:+.0f} px" + (f"; clay with the picture's expression ({xn} comps)"
                                                                    if xn else ""), fill=(0, 0, 0))
        if mesh_b is not None:
            mesh_b["_photo_P"] = Pd
            cb_, _, psb = lit_render(mesh_b, cam, img, box=box, px=px)
            cb = brows_on(fill(cb_, psb), psb, mesh_b, rj, cam, box, k)
            dif = np.abs(np.asarray(cl.convert("L"), float) - np.asarray(cb.convert("L"), float))
            dif = Image.fromarray(np.clip(255 - 4 * dif, 0, 255).astype(np.uint8)).convert("RGB")
            y2 = y + T + 18
            for j, im in enumerate((ph, cb, cl, dif, sq(cb), sq(cl))):
                sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, y2))
            dr.text((4, y2 + T + 2), f"view {vi}: photo | BEFORE {before} | AFTER {name} | the change (|after - before| x4, "
                    "dark = moved) | squint before | squint after", fill=(0, 0, 0))
        info.append({"view": vi, "shift_px": [round(float(sh[0]), 1), round(float(sh[1]), 1)]})
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return {"out": str(out), "views": info}
