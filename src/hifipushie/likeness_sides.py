"""The references and the model seen through them: photo_sides, model_sides, measure_sides. Part of likeness (likeness.py has the overview)."""
from __future__ import annotations

import json

import numpy as np

from .likeness import OVAL, checklist
from .likeness_detect import detect, detect_region
from .likeness_measure import Side, Unmeasurable, value, view_kind
from .likeness_render import _mm_per_px, model_mesh, render

# ---- the references and the model seen through them -----------------------------------------------------------------
def _refs(name: str) -> dict:
    from . import store
    p = store.HOME / name / "human_refs.json"
    if not p.exists():
        raise ValueError(f"likeness: {name} has no human_refs.json (fit its reference pictures first: human_reference)")
    return json.loads(p.read_text())


def _lm_from_points(points: dict) -> np.ndarray:
    from . import humanfit
    lm = np.full((70, 2), np.nan)
    for k, uv in points.items():
        try:
            lm[humanfit.point_index(k)] = uv
        except ValueError:
            pass
    return lm


def _box(points: dict, size) -> tuple:
    U = np.array(list(points.values()), float)
    lo, hi = U.min(0), U.max(0)
    pad = 0.5 * (hi - lo).max()
    # (below the chin: the jaw's lower border and the neck under it are checklist items)
    return (max(lo[0] - pad, 0.0), max(lo[1] - pad * 1.2, 0.0), min(hi[0] + pad, size[0]), min(hi[1] + pad * 1.1, size[1]))


def photo_sides(refs: dict) -> list:
    """Each reference picture as a Side (the detector on a crop round its face; its stored points as the fallback)."""
    from PIL import Image
    out = []
    for v, cam in zip(refs["views"], refs["cameras"]):
        img = Image.open(v["image"]).convert("RGB")
        pts = v["points"]
        if not pts:   # a detector-only view (human_reference read it, no clicks): its box from the whole picture
            Pw = detect([img])[0]
            if Pw is None:
                raise ValueError(f"{v.get('image')}: no clicked points and the detector finds no face in the picture")
            pts = {i: p for i, p in enumerate(np.asarray(Pw, float)[:468])}
        box = _box(pts, img.size)
        info = detect_region(img, box, info=True)
        P = None if info is None else info["P"]
        out.append({"view": v, "cam": cam, "kind": view_kind(cam.get("yaw", v.get("yaw", 0))), "img": img, "box": box,
                    "side": Side(P, _lm_from_points(v["points"]), "detector" if P is not None else "landmarks"),
                    "mmpx": float(cam["t"][2] / cam["f"] * 1000.0), "info": info or {}})
    return out


REFIT = ("three_quarter", "profile")  # views whose camera is refitted on the detector's points (a loose painting)
REFIT_ROUNDS = 2
INFER_TOL = 1.5     # a profile item read from a three-quarter view ("inferred"): its tolerance x this
SPECIAL = ("shape", "jaw", "contour")   # measured in compare (they need the model's render or a trace), not from points alone


def _refit(mesh, ph, cam):
    """The camera refitted for this picture: the detector's 478 on the photo against the model's surface under the same
    detector points on its render (unprojected through the render's depth), pose and focal, REFIT_ROUNDS rounds."""
    from . import likeness_shape as ls
    if ph["side"].P is None:
        return cam, None
    keep = np.setdiff1d(np.arange(468), OVAL)
    res = None
    for _ in range(REFIT_ROUNDS):
        im, k, ps = render(mesh, cam, ph["box"], passes=True)
        Pm = detect([im])[0]
        if Pm is None:
            break
        ij = np.clip(Pm[keep].astype(int), 0, [ps["zb"].shape[1] - 1, ps["zb"].shape[0] - 1])
        z = ps["zb"][ij[:, 1], ij[:, 0]]
        ok = np.isfinite(z) & (ps["part"][ij[:, 1], ij[:, 0]] == 0)
        uvm = Pm[keep][ok] / k + [ph["box"][0], ph["box"][1]]
        X = ls.unproject(cam, uvm, z[ok])
        cam, r = ls.refit_camera(cam, ph["side"].P[keep][ok], X)
        res = np.full(478, np.nan)
        res[keep[ok]] = r
    return cam, res


def model_sides(base: dict, photos: list, mesh=None, cameras=None, refit: bool = True) -> list:
    """The model through each reference's camera (refitted for REFIT views): the clay render, the detector on it, its
    own landmarks projected, its passes (depth, normals), the light fitted to the photo on its normals and the
    residual shading, and a render lit like the photo for the panels. mesh may be a list (one per
    photo)."""
    from . import humanfit
    from . import likeness_shape as ls
    meshes = mesh if isinstance(mesh, list) else None   # (one per photo: each picture's own expression, blockin)
    mesh = None if meshes else (mesh or model_mesh(base))
    out = []
    for i, ph in enumerate(photos):
        mesh = meshes[i] if meshes else mesh
        cam, box = (cameras[i] if cameras else ph["cam"]), ph["box"]
        cres = None
        if refit and ph["kind"] in REFIT and not cameras:
            cam, cres = _refit(mesh, ph, cam)
        im, k, ps = render(mesh, cam, box, passes=True)
        P = detect([im])[0]
        P = None if P is None else P / k + [box[0], box[1]]
        mmpx = _mm_per_px(cam, mesh["L"])
        md = {"img": im, "k": k, "cam": cam, "passes": ps, "cam_res": cres, "mmpx": mmpx, "mesh": mesh,
              "side": Side(P, humanfit.project(cam, mesh["L"]), "detector" if P is not None else "landmarks")}
        md["shade"] = _shade(ph, md)
        if md["shade"]:
            md["img_lit"] = render(mesh, cam, box, light=(md["shade"]["c0"], md["shade"]["w"], md["shade"]["med"]))[0]
        out.append(md)
    return out


SHADE_LIGHT = "sh"   # the shading rows' light: "sh" (fit_light_sh) | "linear" (fit_light: c0 + w.n), as before 2026-10-10


def _shade(ph, md) -> dict | None:
    """The photo's light fitted on the model's normals over the face's skin, and the residual (photo / model lit so - 1)."""
    from PIL import Image
    from . import likeness_shape as ls
    if ph["side"].P is None:
        return None
    k, box, ps = md["k"], ph["box"], md["passes"]
    H, W = ps["zb"].shape
    crop = ph["img"].crop(tuple(int(round(v)) for v in box)).resize((W, H), Image.LANCZOS)
    Y = ls._lin(crop)
    to_px = lambda P: (np.asarray(P, float) - [box[0], box[1]]) * k  # noqa: E731
    ppm = k / md["mmpx"]
    mask = ls.skin_mask(ph["side"], (H, W), to_px, ppm) & (ps["part"] == 0)
    if mask.sum() < 500:
        return None
    c0, w, rms = ls.fit_light(Y, ps["nrm"], mask)
    if SHADE_LIGHT == "sh":   # (blockin2) the shading rows' residual under ambient + key + fill / bounce: the linear
        # light predicted the nose's underside (and every down-facing plane) near black, so those rows read the light
        a_sh, _ = ls.fit_light_sh(Y, ps["nrm"], mask)
        R = ls.residual_sh(Y, ps["nrm"], a_sh, mask, 1.5 * ppm)
    else:
        R = ls.residual(Y, ps["nrm"], c0, w, mask, 1.5 * ppm)
    ex, ey = ph["side"].frame()
    hard = float(np.linalg.norm(w) / max(c0 + np.linalg.norm(w), 1e-6))
    return {"c0": c0, "w": w, "rms": rms, "R": R, "med": float(np.median(Y[mask])), "mask": mask, "to_px": to_px, "ppm": ppm, "ex": ex, "ey": ey,
            "hard": hard, "fit_share": float(rms / max(np.nanmean(Y[mask]), 1e-6))}


def _allowed(it: dict, vk: str, kinds: list) -> tuple:
    """(measured in this view, inferred): a profile item falls back to a three-quarter view when there's no profile."""
    if vk in it["views"]:
        return True, False
    if "profile" in it["views"] and vk == "three_quarter" and "profile" not in kinds:
        return True, True
    return False, False


def measure_sides(sides: list, kinds: list, mmpxs: list) -> dict:
    """{item id: {view index: value | "unmeasurable: why"}}; "-" when no picture has a view the item needs. Shape and
    jaw items are left to compare (`SPECIAL`)."""
    out = {}
    for it in checklist():
        if it["measure"]["kind"] in SPECIAL:
            continue
        row = {}
        for vi, (s, vk, mp) in enumerate(zip(sides, kinds, mmpxs)):
            ok, _ = _allowed(it, vk, kinds)
            if not ok:
                continue
            try:
                row[vi] = value(s, it["measure"], mp)
            except Unmeasurable as e:
                row[vi] = f"unmeasurable: {e}"
        if not row:
            row["-"] = "unmeasurable: " + " or ".join(it["views"]) + " view needed"
        out[it["id"]] = row
    return out


def _near_sign(side: Side) -> list:
    """Sides to read in a picture: both in a front view, only the nearer (wider eye) in a turned one: [-1] = the
    subject's right, [1] its left."""
    try:
        wr = np.linalg.norm(side.pt(33) - side.pt(133))
        wl = np.linalg.norm(side.pt(263) - side.pt(362))
    except Unmeasurable:
        return [-1, 1]
    if max(wr, wl) / max(min(wr, wl), 1e-6) < 1.25:
        return [-1, 1]
    return [-1] if wr > wl else [1]
