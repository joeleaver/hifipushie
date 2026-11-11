"""Hair against a reference picture: the camera fit, rays onto the head, model lines, fit metrics. Part of hair
(hair.py has the overview)."""
from __future__ import annotations

import json

import numpy as np

from . import store
from .hair import _unit
from .hair_groom import _line_at, envelope, groom_params, hairline, part_line
from .hair_head import Scalp
from .hair_spec import _catmull

# ------------------------------------------------------------------------------------------------ the reference
def _rotvec(r):
    from scipy.spatial.transform import Rotation
    return Rotation.from_rotvec(r).as_matrix()


def fit_camera(name: str, points: dict, image_size, crop, spec: dict | None = None, view: str = "matched",
               save: bool = True, focal: float | None = None) -> dict:
    """A camera matching the reference image, fitted on face landmarks: points = {lm joint name: [u, v]} in the
    reference's pixels (u right, v down), image_size = [w, h], crop = [x0, y0, x1, y1] (the square the views show).
    Pinhole, principal point at the image centre; solves pose + focal by least squares from a frontal start. Saves
    <model>/ref_camera.json: the look frame (eye, dir, up, fov, shift) for the crop, plus the reprojection error."""
    from scipy.optimize import least_squares
    spec = store.load(name) if spec is None else spec
    from .spec import expand_mirror, geometry
    J = expand_mirror({k: v for k, v in geometry(spec).items() if k != "hair"})["joints"]
    names = [n for n in points if n in J]
    X = np.array([J[n]["pos"] for n in names], float)
    uv = np.array([points[n] for n in names], float)
    W, Hh = image_size
    cx, cy = W / 2, Hh / 2
    ctr = X.mean(0)
    B = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # world -> camera for a camera in front (looking +Y)

    def project(p):
        R = _rotvec(p[:3]) @ B
        Xc = (X - ctr) @ R.T + p[3:6]
        return np.stack([p[6] * Xc[:, 0] / Xc[:, 2] + cx, p[6] * Xc[:, 1] / Xc[:, 2] + cy], 1)
    p0 = np.r_[0, 0, 0, 0, 0, 1.0, 2000.0]
    uc = uv.mean(0)
    p0[3], p0[4] = (uc[0] - cx) / p0[6] * p0[5], (uc[1] - cy) / p0[6] * p0[5]
    if focal:  # another figure in the same picture: the same lens (a free focal ran off to infinity, orthographic)
        p0[6] = float(focal)
        p0[3], p0[4] = (uc[0] - cx) / p0[6] * p0[5], (uc[1] - cy) / p0[6] * p0[5]
        r = least_squares(lambda q: (project(np.r_[q, focal]) - uv).ravel(), p0[:6],
                          x_scale=[0.1, 0.1, 0.1, 0.05, 0.05, 0.3])
        p = np.r_[r.x, focal]
    else:
        r = least_squares(lambda p: (project(p) - uv).ravel(), p0, x_scale=[0.1, 0.1, 0.1, 0.05, 0.05, 0.3, 500])
        p = r.x
    err = np.linalg.norm(project(p) - uv, axis=1)
    R = _rotvec(p[:3]) @ B
    eye = ctr - R.T @ p[3:6]  # camera centre in world
    fwd = R.T @ np.array([0.0, 0.0, 1.0])
    up = R.T @ np.array([0.0, -1.0, 0.0])
    x0, y0, x1, y1 = crop
    side = max(x1 - x0, y1 - y0)
    fov = float(np.degrees(2 * np.arctan(side / 2 / p[6])))
    # the crop's centre off the principal point: Blender's lens shift, in units of the frame's larger side
    shift = [float(((x0 + x1) / 2 - cx) / side), float(-((y0 + y1) / 2 - cy) / side)]
    cam = {"name": view, "eye": eye.tolist(), "dir": (-fwd).tolist(), "up": up.tolist(), "fov": fov,
           "shift": shift, "crop": list(crop), "image_size": list(image_size), "focal_px": float(p[6]),
           "R": R.tolist(), "t": p[3:6].tolist(), "ctr": ctr.tolist(),
           "error_px": {n: round(float(e), 1) for n, e in zip(names, err)}}
    if save:
        (store._dir(name) / "ref_camera.json").write_text(json.dumps(cam, indent=1))
    return cam


def ref_camera(name: str) -> dict | None:
    f = store._dir(name) / "ref_camera.json"
    return json.loads(f.read_text()) if f.exists() else None


def ref_views(name: str) -> list:
    """Every matched view as (view, camera, trace): the primary ("matched": ref_camera.json, ref_trace.json) then each
    of the trace's "views" (another figure in the same picture, or another picture: a turnaround's side or back),
    whose cameras live in ref_cameras.json. A view's trace inherits "image" from the main trace."""
    tr, cam = ref_trace(name), ref_camera(name)
    out = [("matched", cam, tr)] if (tr is not None and cam is not None) else []
    f = store._dir(name) / "ref_cameras.json"
    cams = json.loads(f.read_text()) if f.exists() else {}
    for v, t in ((tr or {}).get("views") or {}).items():
        if v in cams:
            out.append((v, cams[v], {"image": tr.get("image"), **t}))
    return out


def project_ref(cam: dict, P):
    """World points -> reference image pixels (u, v) through the matched camera."""
    R, t, ctr = np.array(cam["R"]), np.array(cam["t"]), np.array(cam["ctr"])
    W, Hh = cam["image_size"]
    Xc = (np.asarray(P, float) - ctr) @ R.T + t
    return np.stack([cam["focal_px"] * Xc[..., 0] / Xc[..., 2] + W / 2,
                     cam["focal_px"] * Xc[..., 1] / Xc[..., 2] + Hh / 2], -1)


def ray_onto(sc: Scalp, g: dict, cam: dict, uv, onto: str = "volume"):
    """Reference pixels -> points on the head (the scalp, or the groom's volume): each pixel's camera ray, first
    crossing of the surface (sampled from the camera out)."""
    R, t, ctr = np.array(cam["R"]), np.array(cam["t"]), np.array(cam["ctr"])
    W, Hh = cam["image_size"]
    eye = ctr - R.T @ t
    uv = np.atleast_2d(np.asarray(uv, float))
    dc = np.stack([(uv[:, 0] - W / 2) / cam["focal_px"], (uv[:, 1] - Hh / 2) / cam["focal_px"],
                   np.ones(len(uv))], 1)
    D = _unit(dc @ R)  # world directions
    line = hairline(sc, g)
    dist = np.linalg.norm(sc.C - eye)
    ts = np.linspace(dist - 0.2, dist + 0.05, 500)
    out = []
    for d in D:
        P = eye + ts[:, None] * d
        a, e, hh = sc.coords(P)
        if onto == "volume":
            Hv, _ = envelope(sc, g, line, a, e)
            hh = hh - Hv
        k = int(np.argmax(hh < 0)) if np.any(hh < 0) else int(np.argmin(hh))  # a miss: its closest approach
        out.append(P[k])
    return np.array(out)


def ref_trace(name: str) -> dict | None:
    """The reference traced by hand (<model>/ref_trace.json, reference pixels): "part" (polyline from its start),
    "hairline" (polyline across the forehead), "hair" (closed polygon of the visible hair), "clumps" ([{"name",
    "line": root -> tip, "width": px}])."""
    f = store._dir(name) / "ref_trace.json"
    return json.loads(f.read_text()) if f.exists() else None


def _to_crop(cam: dict, uv, W: int):
    x0, y0, x1, y1 = cam["crop"]
    uv = np.asarray(uv, float)
    return (uv - [x0, y0]) * (W / max(x1 - x0, y1 - y0))


def _poly_dist(P, Q):
    """Mean and max distance from each point of P to the polyline Q (px)."""
    P, Q = np.asarray(P, float), np.asarray(Q, float)
    A, B = Q[:-1], Q[1:]
    AB = B - A
    t = np.clip(((P[:, None] - A) * AB).sum(-1) / np.maximum((AB * AB).sum(-1), 1e-9), 0, 1)
    d = np.linalg.norm(P[:, None] - (A + t[..., None] * AB), axis=-1).min(1)
    return d


def _dense(Q, step=2.0):
    Q = np.asarray(Q, float)
    c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    t = np.arange(0, c[-1] + 1e-9, step)
    return np.stack([np.interp(t, c, Q[:, k]) for k in range(2)], 1)


def model_lines(name: str, sc: Scalp, cam: dict, spec: dict) -> dict:
    """The groom's own lines in reference pixels, through the matched camera: the hairline (the part of it facing the
    camera), the parting (drawn clumps' roots on the part side: their start points), each drawn clump's spine."""
    g = groom_params(spec)
    line = hairline(sc, g)
    az = np.arange(-70.0, 71.0, 1.0)
    P = sc.point(az, _line_at(line, az), 0.0)
    out = {"hairline": project_ref(cam, P).tolist()}
    locks = (spec.get("hair") or {}).get("locks") or {}
    cl = {}
    for n, lk in locks.items():
        if lk.get("tier") not in ("drawn", "hand") or n.endswith("_under"):
            continue
        p = np.asarray(lk["pts"], float)
        Q = sc.point(p[:, 0], p[:, 1], p[:, 2])
        if lk.get("tier") == "hand":  # locks added by hand anywhere: only those the camera sees (a back lock's spine
            # projected across the face, and the clump match could pick it)
            if float(np.mean(_unit(Q - sc.C) @ _unit(np.asarray(cam["eye"]) - sc.C))) < 0.2:
                continue
        cl[n] = project_ref(cam, _catmull(Q, 24)).tolist()
    out["clumps"] = cl
    q = part_line(sc, g)
    if q is not None:
        H, _ = envelope(sc, g, line, q[:, 0], q[:, 1])
        out["part"] = project_ref(cam, sc.point(q[:, 0], q[:, 1], H)).tolist()
    return out


def fit_metrics(name: str, sc: Scalp, cam: dict, spec: dict, hair_mask=None, tr: dict | None = None,
                owners=None) -> dict:
    """The groom against the traced reference in the matched view (reference pixels, and mm at the head's depth):
    part start (px) and direction (deg) error, hairline mean/max distance, hair silhouette IoU + mean boundary
    distance (from the matched id pass), the outline per head region (`outline_regions`), the hair's top over the
    brows, each traced clump's direction error against the nearest drawn clump."""
    from . import hair_trace
    tr = ref_trace(name) if tr is None else tr
    if tr is None:
        return {}
    ml = model_lines(name, sc, cam, spec)
    mm = 1000 * np.linalg.norm(np.asarray(cam["eye"]) - sc.C) / cam["focal_px"]  # mm per reference pixel
    out = {"mm_per_px": round(float(mm), 2)}

    def ang(v):
        return np.degrees(np.arctan2(v[1], v[0]))
    if tr.get("part") and ml.get("part"):
        a, b = np.asarray(tr["part"], float), np.asarray(ml["part"], float)
        da = (ang(a[min(3, len(a) - 1)] - a[0]) - ang(b[min(3, len(b) - 1)] - b[0]) + 180) % 360 - 180
        out["part_start_px"] = round(float(np.linalg.norm(a[0] - b[0])), 1)
        out["part_dir_deg"] = round(float(abs(da)), 1)
    if tr.get("hairline"):
        d = _poly_dist(_dense(tr["hairline"]), ml["hairline"])
        out["hairline_px"] = [round(float(d.mean()), 1), round(float(d.max()), 1)]
    if tr.get("hair") and hair_mask is not None:
        from PIL import Image, ImageDraw
        from scipy.ndimage import distance_transform_edt, binary_erosion
        x0, y0, x1, y1 = cam["crop"]
        Wm = hair_mask.shape[0]
        im = Image.new("L", (Wm, Wm), 0)
        ImageDraw.Draw(im).polygon([tuple(p) for p in _to_crop(cam, tr["hair"], Wm)], fill=255)
        R = np.asarray(im) > 0
        M = hair_mask.copy()
        if tr.get("clip_y") is not None:  # under it: ear, sideburn, beard (not traced)
            cy = int(round((tr["clip_y"] - y0) * Wm / max(x1 - x0, y1 - y0)))
            R[cy:], M[cy:] = False, False
        out["iou"] = round(float((R & M).sum() / max((R | M).sum(), 1)), 3)
        bR, bM = R & ~binary_erosion(R), M & ~binary_erosion(M)
        s = (max(x1 - x0, y1 - y0)) / Wm  # reference px per mask px
        if bR.any() and bM.any():
            d1 = distance_transform_edt(~bM)[bR]
            d2 = distance_transform_edt(~bR)[bM]
            out["outline_px"] = [round(float(np.r_[d1, d2].mean() * s), 1), round(float(max(d1.max(), d2.max()) * s), 1)]
        fe = hair_trace.front_edge(cam, tr, hair_mask, mm, owners=owners)
        if fe:
            out["front_edge"] = fe
        reg, brow = hair_trace.outline_regions(sc, cam, spec, R, M, tr, s * mm)
        out["regions"] = reg
        if brow:
            out["over_brow_mm"] = brow
    if tr.get("clumps") and ml["clumps"]:
        errs = {}
        for c in tr["clumps"]:
            L = np.asarray(c["line"], float)
            # the model's clump nearest along the traced one (mean distance of its points to each spine)
            best = min(ml["clumps"].items(), key=lambda kv: _poly_dist(_dense(L, 4), kv[1]).mean())
            Q = np.asarray(best[1], float)
            dl = _dense(L, 4)
            # direction where they overlap: the traced one's overall heading vs the model spine's over the same span
            k = [int(np.argmin(np.linalg.norm(Q - p, axis=1))) for p in (dl[0], dl[-1])]
            v2 = Q[max(k)] - Q[min(k)] if max(k) > min(k) else Q[-1] - Q[0]
            if np.dot(v2, L[-1] - L[0]) < 0:
                v2 = -v2
            da = (ang(L[-1] - L[0]) - ang(v2) + 180) % 360 - 180
            errs[c.get("name", str(len(errs)))] = [best[0], round(float(abs(da)), 1),
                                                   round(float(_poly_dist(dl, Q).mean()), 1)]
        out["clumps"] = errs
        out["clump_dir_deg_mean"] = round(float(np.mean([v[1] for v in errs.values()])), 1)
    return out


EDGE_SMOOTH = 0.008  # m: the hairline edge's own sweep is the edge with tips/notches narrower than ~this taken out
EDGE_REACH = 0.03  # m: how far either side of the traced hairline the rendered edge is looked for
