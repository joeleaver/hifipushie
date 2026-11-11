"""focus: one feature, zoomed in; note. Part of the block-in (blockin.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import blockin_models
from .blockin_clay import brows_on, detect_view, presented_mesh
from .blockin_expression import _per_view
from .blockin_look import _eye_anchor, fill, lit_render, profile_contour
from .blockin_models import _log_path
from .blockin_table import FEATURES

RAKE = np.array([-0.85, -0.35, -0.25])   # camera frame: a grazing key from the picture's upper left (forms, not tone)
RAKE = RAKE / np.linalg.norm(RAKE)


def _feature_box(feature, L2, P_ear=None):
    """A square crop (picture pixels) around the feature's projected landmarks (the ear: its projected vertices)."""
    Q = P_ear if feature == "ears" and P_ear is not None and len(P_ear) else L2[FEATURES[feature]["lm"]]
    lo, hi = Q.min(0), Q.max(0)
    c = 0.5 * (lo + hi)
    # (a profile foreshortens the eye corners' span to a few mm: the nasion-chin length doesn't, ~0.75 x the span)
    io = max(float(np.linalg.norm(L2[45] - L2[36])), 0.75 * float(np.linalg.norm(L2[27] - L2[8])))
    side = max(FEATURES[feature].get("pad", 1.5) * float(np.max(hi - lo)), 0.55 * io)
    return (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2)


def focus(name: str, feature: str, out: str, views: list | None = None, T: int = 300, before: str | None = None) -> dict:
    """ZOOM IN: one feature per view, at native resolution: photo crop | clay crop (the photo's light, filled) | 50 %
    overlay | the local outline difference (the detector's feature contours: photo red, clay green) | clay under a
    raking light | squinted photo | squinted clay. Registered at the feature's OWN landmarks (a 2D shift), so an
    offset elsewhere doesn't hide its shape. before = another model: a second row photo | before | after | change |
    raking before | raking after. Views where the feature isn't seen (the ear in front) are left out."""
    from PIL import Image, ImageDraw, ImageFilter
    from . import humanfit, likeness, store
    if feature not in FEATURES:
        raise ValueError(f"focus: one of {', '.join(FEATURES)}")
    F = FEATURES[feature]
    rj = blockin_models._refs(name)
    VI = list(range(len(rj["views"]))) if views is None else [int(v) for v in views]
    if feature == "ears":
        VI = [vi for vi in VI if abs(float(rj["views"][vi].get("yaw", 0))) >= 20]
    if not VI:
        raise ValueError(f"focus {feature}: no view shows it (the ear needs a turned view)")
    meshes = _per_view(store.load(name)["base"], rj, VI, lambda b: presented_mesh(b, rj=rj))
    meshes_b = _per_view(store.load(before)["base"], rj, VI, lambda b: presented_mesh(b, rj=rj)) if before else None
    per = 2 if before else 1
    cols = ["photo", "clay (photo's light)", "50% overlay", "outline: photo red / clay green", "raking light",
            "squint photo", "squint clay"]
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
        L2 = humanfit.project(cam, st["L"])
        Pe = humanfit.project(cam, mesh["V"][mesh["ears"]]) if feature == "ears" and mesh.get("ears") is not None else None
        if Pe is not None:   # (the ear nearer the camera: its vertices on the picture's near side)
            ex = mesh["V"][mesh["ears"]][:, 0]
            near = ex > 0 if float(v.get("yaw", 0)) < 0 else ex < 0
            Pe = Pe[near]
        box = _feature_box(feature, L2, Pe)
        side = box[2] - box[0]
        px = 2 * T
        k = px / side
        front = abs(float(v.get("yaw", 0))) < 70
        Pd = detect_view(img, v) if front else None
        mesh["_photo_P"] = Pd
        pr = [(a, b) for a, b in F["pairs"]] if Pd is not None else []
        clicked = []   # (a turned / profile view: the view's own clicked points that belong to the feature)
        for nm, uv in (v.get("points") or {}).items():
            try:
                ix = humanfit.point_index(nm)
            except Exception:  # noqa: BLE001
                continue
            if ix in F["lm"] or (feature == "nose" and ix in (27, 30, 33)) or (feature == "mouth" and 48 <= ix < 68):
                clicked.append((ix, np.asarray(uv, float)))
        if pr:
            sh = np.mean([np.asarray(Pd[b][:2], float) - L2[a] for a, b in pr], 0)
            how = "the feature's own landmarks"
        elif clicked:
            sh = np.mean([uv - L2[ix] for ix, uv in clicked], 0)
            how = f"the feature's clicked points ({len(clicked)})"
        else:
            a_ph, a_md = _eye_anchor(v, Pd, L2)
            sh = np.zeros(2) if a_ph is None else a_ph - a_md
            how = "the eyes (no feature points on this view)"
        pbox = (box[0] + sh[0], box[1] + sh[1], box[2] + sh[0], box[3] + sh[1])
        ph = img.crop(tuple(int(round(b)) for b in pbox)).resize((px, px), Image.LANCZOS)
        cl_, _, ps = lit_render(mesh, cam, img, box=box, px=px)
        cl = brows_on(fill(cl_, ps), ps, mesh, rj, cam, box, k)
        to = lambda Q: [((q[0] - box[0]) * k, (q[1] - box[1]) * k) for q in Q]  # noqa: E731
        to_ph = lambda Q: [((q[0] - pbox[0]) * k, (q[1] - pbox[1]) * k) for q in Q]  # noqa: E731
        # (from the side the face looks to: a right-facing profile's front is on the picture's right)
        rk_dir = RAKE * [-1.0, 1.0, 1.0] if float(v.get("yaw", 0)) >= 70 else RAKE
        rake = lambda m: fill(*likeness.render(m, cam, box, px=px, brows=False, passes=True, ao=True, shadow=4.0,  # noqa: E731
                                                light=(0.3, rk_dir, 1.0, 0.0))[::2], share=0.3)
        rk = rake(mesh)
        ov = Image.blend(ph, cl, 0.5)
        ol = ph.copy().convert("L").convert("RGB")
        d = ImageDraw.Draw(ol)
        if front and F["lines"]:
            full, _, pf = lit_render(mesh, cam, img)
            Pm = detect_view(fill(full, pf), v)
            for ln in F["lines"]:
                if Pd is not None:
                    d.line(to_ph(np.asarray(Pd, float)[ln, :2]), fill=(230, 30, 30), width=2)
                if Pm is not None:   # (the clay's contour in its own crop: the photo's crop carries the registration)
                    d.line(to(np.asarray(Pm, float)[ln, :2]), fill=(30, 200, 30), width=2)
        else:
            if not front:
                try:
                    d.line(to_ph(profile_contour(v)), fill=(230, 30, 30), width=2)
                except Exception:  # noqa: BLE001
                    pass
            e = np.asarray(Image.fromarray((ps["part"] >= 0).astype(np.uint8) * 255).filter(ImageFilter.FIND_EDGES)) > 0
            e[:2], e[-2:], e[:, :2], e[:, -2:] = False, False, False, False   # (the crop's own border is no edge)
            olA = np.asarray(ol).copy()
            olA[e] = (30, 200, 30)
            ol = Image.fromarray(olA)
        sg = float(F["squint_mm"] / likeness._mm_per_px(cam, mesh["L"][27:48]) * k)
        sq = lambda im: im.convert("L").filter(ImageFilter.GaussianBlur(sg)).convert("RGB")  # noqa: E731
        y = 18 + i * per * (T + 18)
        for j, im in enumerate((ph, cl, ov, ol, rk, sq(ph), sq(cl))):
            sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, y))
        mm = likeness._mm_per_px(cam, mesh["L"][27:48])
        dr.text((4, y + T + 2), f"{feature}, view {vi} (yaw {float(v.get('yaw', 0)):g}): registered at {how}, shift "
                f"{sh[0]:+.0f}, {sh[1]:+.0f} px; crop {side * mm:.0f} mm", fill=(0, 0, 0))
        if mesh_b is not None:
            mesh_b["_photo_P"] = Pd
            cb_, _, psb = lit_render(mesh_b, cam, img, box=box, px=px)
            cb = brows_on(fill(cb_, psb), psb, mesh_b, rj, cam, box, k)
            dif = np.abs(np.asarray(cl.convert("L"), float) - np.asarray(cb.convert("L"), float))
            dif = Image.fromarray(np.clip(255 - 4 * dif, 0, 255).astype(np.uint8)).convert("RGB")
            y2 = y + T + 18
            for j, im in enumerate((ph, cb, cl, dif, rake(mesh_b), rk)):
                sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, y2))
            dr.text((4, y2 + T + 2), f"photo | BEFORE {before} | AFTER {name} | change x4 | raking before | raking after",
                    fill=(0, 0, 0))
        info.append({"view": vi, "shift_px": [round(float(sh[0]), 1), round(float(sh[1]), 1)], "registered": how})
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return {"out": str(out), "views": info}


def note(name: str, read: str, keep: bool | None = None) -> dict:
    """ZOOM OUT read of a step's result, logged on the step that made `name` (its whole-face verdict): keep / not."""
    rj = blockin_models._refs(name)
    p = _log_path(rj, name)
    lg = json.loads(p.read_text()) if p.exists() else []
    e = next((x for x in reversed(lg) if x.get("to") == name), None)
    if e is None:
        raise ValueError(f"{name}: no block-in step made it")
    e["zoom_out"] = read
    if keep is not None:
        e["kept"] = bool(keep)
    p.write_text(json.dumps(lg, indent=1))
    return e
