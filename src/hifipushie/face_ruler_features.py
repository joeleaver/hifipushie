"""A block-in model's feature reads: the iris, the lids, shading and normals on plain skin, the lips. Part of the face ruler (face_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from .face_ruler import _C, _cam_points, _clay_crop, _gnm, _proj_jac_pt, clay
from .face_ruler_outline import photo_masks

def _iris_obs(head, view, eyes_pic):
    """Iris centres: the picture's (eye_ruler.read: a circle through the limbus) against the model's (eye_ruler.model),
    moving with the model's eye centres."""
    from . import eye_ruler as er
    tru = er.model(head["spec"], view["cam"])
    out = []
    xs = [float(e[0]) for e in head["eye_X"]]
    for s_ in (0, 1):           # eye_ruler: the subject's right eye first (world x smaller: the creature's left is +X)
        j = int(np.argmin(xs)) if s_ == 0 else int(np.argmax(xs))
        Jp, mm1 = _proj_jac_pt(view["cam"], head["eye_X"][j], head["eye_B"][j])
        d = np.asarray(eyes_pic[s_]["c"], float) - np.asarray(tru[s_]["c"], float)
        for ax in (0, 1):
            out.append({"type": "iris", "view": view["kind"], "name": f"iris_{'rl'[s_]}.{'xy'[ax]}", "o": float(d[ax]) * mm1,
                        "J": Jp[ax] * mm1, "sig": 0.2, "p": list(map(float, tru[s_]["c"])), "q": list(map(float, eyes_pic[s_]["c"])),
                        "X": list(map(float, head["eye_X"][j]))})
    return out


SIG_LID = (0.2, 0.4, 0.4)   # mm: a lid margin at a column within 7 mm of the iris centre / beyond it / a canthus


def _lid_obs(head, view, rv):
    """THE LIDS IN THE SAME SOLVE (reruns, 2026-10-11): the eye ruler's read of the front picture (rv = eye_ruler.mean:
    upper / lower margin at its columns, the canthi; mm at the model in the eye's own frame, from the iris centre)
    against the model's margin ring read the same way (blockin_eyes.Reader.margins, the subject's left eye). Each
    moves with GNM's ring-0 vertices relative to the eye's centre. In the EYE's frame, so no camera column: its view
    is "eye frame". The eye step solved these alone and later steps undid them (lips 0.2 -> 1.8 mm, brows 1.8 mm)."""
    from . import blockin_eyes as be, lidrings, onemesh
    ht = onemesh.head_template(head["spec"]["base"])
    mg = be.Reader(ht).margins(ht)
    gg = _gnm()["sp"]
    T = gg["T"]
    r0 = np.asarray(lidrings.topo()["loops"][0], int)
    if "lid_mv" not in _C:
        _C["lid_mv"] = {}
    key = len(head["gid"])
    if key not in _C["lid_mv"]:
        gid = np.asarray(head["gid"], int)
        first = {}
        for i, g_ in enumerate(gid):
            if g_ >= 0 and g_ not in first:
                first[int(g_)] = i
        _C["lid_mv"][key] = np.array([first.get(int(g_), -1) for g_ in r0])
    mv = _C["lid_mv"][key]
    ok = mv >= 0
    r0, mv = r0[ok], mv[ok]
    j = int(np.argmax([float(e[0]) for e in head["eye_X"]]))        # the subject's left eye (world +X)
    E, EB = np.asarray(head["eye_X"][j], float), np.asarray(head["eye_B"][j], float)       # (3,), (170, 3)
    ejy = 0.5 * (T[r0, 1].max() + T[r0, 1].min())
    up = T[r0, 1] > ejy
    x = (np.asarray(head["V"], float)[mv, 0] - E[0]) * 1000.0
    Bx = (np.asarray(head["B"][:, mv, 0], float) - EB[:, 0:1]) * 1000.0     # (170, n) mm per unit, across
    Bz = (np.asarray(head["B"][:, mv, 2], float) - EB[:, 2:3]) * 1000.0     # up
    out = []

    def col_J(sel, u):
        xs = x[sel]
        o = np.argsort(np.abs(xs - u))[:2]
        w = 1.0 / np.maximum(np.abs(xs[o] - u), 0.05)
        w /= w.sum()
        return Bz[:, np.flatnonzero(sel)[o]] @ w
    for nm, sel, pic, mod in (("up", up, np.asarray(rv["up"], float), mg["up"]),
                              ("lo", ~up, np.asarray(rv["lo"], float) - be.LO_BIAS, mg["lo"])):
        for k, u in enumerate(be.RULER_COLS):
            if not (np.isfinite(pic[k]) and np.isfinite(mod[k])):
                continue
            out.append({"type": "lid", "view": "eye frame", "name": f"lid_{nm}_{u:+.0f}.y", "o": float(pic[k] - mod[k]),
                        "J": col_J(sel, float(u)), "sig": SIG_LID[0] if abs(u) < 7 else SIG_LID[1], "of": view.get("kind", "front")})
    io, ii = int(np.argmax(x)), int(np.argmin(x))
    if np.isfinite(rv["outer"][0]):
        out.append({"type": "lid", "view": "eye frame", "name": "canthus_out.x", "o": float(rv["outer"][0] + be.OUT_RING - mg["ring_out"][0]),
                    "J": Bx[:, io], "sig": SIG_LID[2], "of": view.get("kind", "front")})
    if np.isfinite(rv["inner"][0]):
        JL = (np.asarray(head["LB"][:, 42, 0], float) - EB[:, 0]) * 1000.0
        out.append({"type": "lid", "view": "eye frame", "name": "canthus_in.x", "o": float(rv["inner"][0] - mg["inner"][0]),
                    "J": JL, "sig": SIG_LID[2], "of": view.get("kind", "front")})
    return out


NU_SD = 2.0                 # prior sd of an observation's own nuisance columns (log units: wide)


SIG_SHADE = 0.05            # log luminance: one shading sample (validated on clay pairs: spikes/reruns/shval.py)


SHADE_N = 350               # shading samples per view


SHADE_REGIONS = ("forehead_region", "left_temple_region", "right_temple_region", "left_zygomatic_region",
                 "right_zygomatic_region", "left_parotid_region", "right_parotid_region", "left_infraorbital_region",
                 "right_infraorbital_region", "left_cheek_region", "right_cheek_region", "chin_region")


def _vnormals(V, F):
    n = np.zeros_like(V)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for k in range(3):
        np.add.at(n, F[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _shade_model(head) -> dict:
    """Per head: the model vertices of the plain-skin regions (SHADE_REGIONS: no brows, lids, nose, lips: albedo
    edges and cast shadows), their world normals and the normals' change per identity comp (finite differences of
    the head's own faces): {"idx", "N" (n, 3), "dN" (170, n, 3)}."""
    if "_shade" in head:
        return head["_shade"]
    gr = _gnm()["gr"]
    sel = np.zeros(len(next(iter(gr.values()))), bool)
    for k in SHADE_REGIONS:
        sel |= gr[k]
    gid = np.asarray(head["gid"], int)
    V, F = np.asarray(head["V"], float), np.asarray(head["F"], int)
    used = np.zeros(len(V), bool)
    used[F.ravel()] = True
    idx = np.flatnonzero((gid >= 0) & sel[np.maximum(gid, 0)] & used)
    N0 = _vnormals(V, F)
    c = V[idx].mean(0)
    if ((V[idx] - c) * N0[idx]).sum() < 0:      # outward
        N0 = -N0
        sgn = -1.0
    else:
        sgn = 1.0
    eps = 0.5
    dN = np.zeros((head["B"].shape[0], len(idx), 3))
    for k in range(head["B"].shape[0]):
        dN[k] = (sgn * _vnormals(V + eps * np.asarray(head["B"][k], float), F)[idx] - N0[idx]) / eps
    head["_shade"] = {"idx": idx, "N": N0[idx], "dN": dN}
    return head["_shade"]


def _shade_obs(head, view):
    """SHADING (reruns, 2026-10-11; Joe on tk_03: "the puffiness of her cheeks is really weird"): what no outline sees,
    the surface INSIDE the silhouette. On the plain-skin regions (cheeks, zygoma, parotid, under the eye, chin,
    forehead, temples) the picture's luminance is albedo x (c0 + w . n): the light (c0, w) is fitted on the model's
    own normals at the sampled vertices (robust), and each sample's log luminance minus the log of the model's
    predicted shading is the observation: it moves with the vertex's NORMAL, d = (w . dn / dc) / (c0 + w . n). The
    albedo, exposure and their slow drift across the face are the observation's own nuisance columns (a quadratic in
    the picture's coordinates per view). Samples: visible (the clay pass's depth), turned at least 25 deg off
    grazing, on the picture's skin (view["trust"]) and not in the darkest shading (cast shadows)."""
    from scipy import ndimage as ndi
    from . import humanfit
    sm = _shade_model(head)
    cam = view["cam"]
    kind = view["kind"]
    sc, org = float(view.get("scale", 1.0)), np.asarray(view.get("origin", (0.0, 0.0)), float)
    if "_Ylog" not in view:
        a = (np.asarray(view["img"].convert("RGB"), float) / 255.0) ** 2.2
        Y = a @ np.array([0.2126, 0.7152, 0.0722])
        mmpx = float(cam["t"][2]) / cam["f"] * 1000.0 / sc
        view["_Ylog"] = ndi.gaussian_filter(Y, 1.5 / mmpx)       # 1.5 mm: pores, freckles, noise
    Y = view["_Ylog"]
    H, W = Y.shape
    Rc = humanfit._cam_rot(cam)
    X = np.asarray(head["V"], float)[sm["idx"]]
    Xc, px = _cam_points(cam, X)
    px = (px - org) * sc
    nc_ = sm["N"] @ Rc.T
    facing = -nc_[:, 2]                                          # the camera looks along +z
    _, ps = clay(head, cam, passes=True)
    zb = ps["zb"]
    kz = zb.shape[0] / float(cam["size"][1])
    qx = np.clip((px / sc + org)[:, 0] * kz, 0, zb.shape[1] - 1).astype(int)
    qy = np.clip((px / sc + org)[:, 1] * kz, 0, zb.shape[0] - 1).astype(int)
    vis = np.abs(zb[qy, qx] - Xc[:, 2]) < 0.004
    ix, iy = np.round(px[:, 0]).astype(int), np.round(px[:, 1]).astype(int)
    ok = vis & (facing > 0.42) & (ix >= 2) & (ix < W - 2) & (iy >= 2) & (iy < H - 2)
    if "hair" in head:
        ok &= ~np.asarray(head["hair"], bool)[sm["idx"]]        # the hairline / a clay picture's hair cap
    if view.get("trust") is None and view.get("style") == "photo":
        view["trust"] = photo_masks(view["img"], cam, head, origin=org, scale=sc)[1]
    if view.get("trust") is not None:
        tr = ndi.binary_erosion(view["trust"], iterations=max(int(2.0 / (float(cam["t"][2]) / cam["f"] * 1000.0 / sc)), 1))
        ok &= tr[np.clip(iy, 0, H - 1), np.clip(ix, 0, W - 1)]
    if ok.sum() < 60:
        return []
    k = np.flatnonzero(ok)
    y = Y[iy[k], ix[k]]
    n = nc_[k]
    A = np.c_[np.ones(len(k)), n]
    use = y > 0.02
    sol = np.zeros(4)
    for _ in range(5):
        if use.sum() < 40:
            return []
        sol = np.linalg.lstsq(A[use], y[use], rcond=None)[0]
        r = y - A @ sol
        use = (np.abs(r) < 2.5 * r[use].std()) & (y > 0.02)
    S = A @ sol
    good = (S > 0.35 * np.median(S[use])) & (y > 0.25 * np.median(y[use]))     # not the shadow side's floor
    k, y, S, n = k[good], y[good], S[good], n[good]
    if len(k) < 40:
        return []
    if len(k) > SHADE_N:
        pick = np.round(np.linspace(0, len(k) - 1, SHADE_N)).astype(int)
        k, y, S, n = k[pick], y[pick], S[pick], n[pick]
    wv = sol[1:]
    dNc = np.einsum("knc,dc->knd", sm["dN"][:, k], Rc)                # (170, n, 3) camera frame
    J = (dNc @ wv) / S[None, :]                                       # (170, n)
    u = (px[k] - px[k].mean(0)) / max(float(np.ptp(px[k][:, 0])), float(np.ptp(px[k][:, 1])), 1.0)
    o = np.log(y) - np.log(S)
    out = []
    for i in range(len(k)):
        nu = {f"sh_{kind}_1": 1.0, f"sh_{kind}_x": u[i, 0], f"sh_{kind}_y": u[i, 1], f"sh_{kind}_xx": u[i, 0] ** 2,
              f"sh_{kind}_xy": u[i, 0] * u[i, 1], f"sh_{kind}_yy": u[i, 1] ** 2}
        out.append({"type": "shade", "view": "shade:" + kind, "name": f"shade_{kind}_{i}", "o": float(o[i]), "J": J[:, i],
                    "sig": SIG_SHADE, "nu": nu, "px": list(map(float, px[k[i]])),
                    "vid": int(sm["idx"][k[i]])})
    view["_shade_light"] = (float(sol[0]), [float(x) for x in sol[1:]], int(len(k)))
    return out


SIG_NORMAL = 0.10           # radians: one learned-normal sample's tangent component (spikes/refread/nrmval.py)


NORMAL_N = 400              # normal samples per view


NORMAL_REGIONS = SHADE_REGIONS + ("nose_region",)


def _normal_model(head, regions=NORMAL_REGIONS) -> dict:
    """as _shade_model for any set of GNM regions (cached on the head)."""
    key = "_nm_" + ",".join(regions)
    if key in head:
        return head[key]
    old = head.pop("_shade", None)
    global SHADE_REGIONS
    keep = SHADE_REGIONS
    try:
        SHADE_REGIONS = tuple(regions)
        head[key] = _shade_model(head)
    finally:
        SHADE_REGIONS = keep
        head.pop("_shade", None)
        if old is not None:
            head["_shade"] = old
    return head[key]


def _normals_of_model(head, view) -> dict:
    """The estimator's normals on the MODEL's own clay picture on the view's pixel grid (the differential reference of
    _normal_obs: the same estimator on picture and render, as the anchors)."""
    from . import facenormals as fnm
    cam = view["cam"]
    sc, org = float(view.get("scale", 1.0)), np.asarray(view.get("origin", (0.0, 0.0)), float)
    im = _clay_crop(head, view)[0] if "scale" in view else clay(head, cam)
    if im.size != view["img"].size:
        im = im.resize(view["img"].size)
    PL = (_cam_points(cam, np.asarray(head["L"], float)[:68])[1] - org) * sc
    return fnm.estimate(im, fnm.head_box(PL, im.size))


def _normal_obs(head, view, differential=None):
    """LEARNED SURFACE NORMALS as the interior observation (refread, 2026-10-11): at sampled visible skin vertices
    (NORMAL_REGIONS) the picture's normal from a monocular estimator (facenormals: camera frame) against the model's
    own: the two tangent components of the difference (radians), each moving with the vertex's normal (dn / dc from
    _shade_model, as the shading read). Nuisance per view: a small global ROTATION of the estimator's normals (3) and
    its RELIEF gain (1: estimators flatten or exaggerate the turn away from the camera). differential = the
    estimator's normals on a picture of the MODEL itself through the same camera ({"n", "box"}, facenormals.estimate):
    then the observation is estimate(picture) - estimate(model's picture), the estimator's own bias taken out."""
    from . import facenormals as fnm, humanfit
    sm = _normal_model(head)
    cam, kind = view["cam"], view["kind"]
    sc, org = float(view.get("scale", 1.0)), np.asarray(view.get("origin", (0.0, 0.0)), float)
    img = view["img"]
    Wd, Hd = img.size
    Rc = humanfit._cam_rot(cam)
    X = np.asarray(head["V"], float)[sm["idx"]]
    Xc, pc = _cam_points(cam, X)
    px = (pc - org) * sc
    nc_ = sm["N"] @ Rc.T
    _, ps = _clay_crop(head, view) if "scale" in view else clay(head, cam, passes=True)
    zb = ps["zb"]
    kz = zb.shape[0] / float(Hd)
    qx = np.clip(px[:, 0] * kz, 0, zb.shape[1] - 1).astype(int)
    qy = np.clip(px[:, 1] * kz, 0, zb.shape[0] - 1).astype(int)
    ok = (np.abs(zb[qy, qx] - Xc[:, 2]) < 0.004) & (-nc_[:, 2] > 0.35)
    ok &= (px[:, 0] >= 2) & (px[:, 0] < Wd - 2) & (px[:, 1] >= 2) & (px[:, 1] < Hd - 2)
    if "hair" in head and view.get("hair", True):
        ok &= ~np.asarray(head["hair"], bool)[sm["idx"]]
    if view.get("trust") is not None:
        from scipy import ndimage as ndi
        mmpx = float(cam["t"][2]) / cam["f"] * 1000.0 / sc
        tr = ndi.binary_erosion(np.asarray(view["trust"], bool), iterations=max(int(2.0 / mmpx), 1))
        ok &= tr[np.clip(px[:, 1].astype(int), 0, Hd - 1), np.clip(px[:, 0].astype(int), 0, Wd - 1)]
    if ok.sum() < 60:
        return []
    if "_nrm" not in view:
        PL = (_cam_points(cam, np.asarray(head["L"], float)[:68])[1] - org) * sc
        view["_nrm"] = fnm.estimate(img, fnm.head_box(PL, img.size))
    k = np.flatnonzero(ok)
    ne = fnm.at(view["_nrm"], px[k])
    ref = nc_[k]
    if differential is not None:
        ref = fnm.at(differential, px[k])
    g = np.isfinite(ne).all(1) & np.isfinite(ref).all(1)
    k, ne, ref = k[g], ne[g], ref[g]
    if len(k) > NORMAL_N:
        pick = np.round(np.linspace(0, len(k) - 1, NORMAL_N)).astype(int)
        k, ne, ref = k[pick], ne[pick], ref[pick]
    n = nc_[k]
    t1 = np.cross(n, [0.0, 1.0, 0.0])
    t1 /= np.maximum(np.linalg.norm(t1, axis=1, keepdims=True), 1e-9)
    t2 = np.cross(n, t1)
    dNc = np.einsum("knc,dc->knd", sm["dN"][:, k], Rc)                # (170, n, 3) camera frame
    zc = np.array([0.0, 0.0, -1.0])
    out = []
    for i in range(len(k)):
        for a, t in (("u", t1[i]), ("v", t2[i])):
            rot = np.cross(n[i], t)
            nu = {f"nr_{kind}_x": rot[0], f"nr_{kind}_y": rot[1], f"nr_{kind}_z": rot[2], f"nr_{kind}_gain": float(zc @ t)}
            out.append({"type": "normal", "view": "normal:" + kind, "name": f"normal_{kind}_{i}.{a}", "o": float((ne[i] - ref[i]) @ t),
                        "J": dNc[:, i] @ t, "sig": SIG_NORMAL, "nu": nu, "px": list(map(float, px[k[i]])),
                        "vid": int(sm["idx"][k[i]])})
    return out


SIG_LIP = 0.3               # mm: a vermilion border vertex against the picture's traced border


# (readmix, 2026-10-14) THE LIPS' READS ON A PHOTOGRAPH ARE NOT THE MODEL'S BORDER ROWS: at the TRUE head (seven HSRD training
# subjects, the scan-fitted identity through the rig's cameras) the photograph's colour edge lies 0.5-2.4 mm ABOVE GNM's
# upper border row and 0.4-4.0 mm BELOW its lower one (most at the middle), and MediaPipe's border points and the
# differential anchors (picture minus our render) agree: our render's lips look thinner to every reader than the same
# lips photographed. Uncorrected, the solve makes lips 3-8 mm too tall. Each read's mean vertical offset (per border
# position / point) is taken out of a PHOTO's lip reads (lip_photo_bias.json; spikes/readmix/lipbias.py); per-person
# scatter remains (sd 0.5-2.5 mm). The colour edge itself belongs to the PAINT, placed from the picture.
LIP_PHOTO_BIAS = False      # OFF (2026-10-14, the coordinator's decision): on three held-out HSRD heads it took the lip heights' error


#                             4.4 -> 1.8 mm against the fit's vertices, but the scan's SURFACE did not confirm it (lips 1.06 / 0.69 /
#                             1.60 -> 1.03 / 0.80 / 1.76 mm; one chin 1.29 -> 2.00): an option, docs/notes/readmix.md "## TALL LIPS"
def lip_bias(kind: str, key: str) -> float:
    """The calibrated vertical offset (mm, + = the photo's point lies lower) of a lip read at the true head; 0 if none."""
    if not LIP_PHOTO_BIAS:
        return 0.0
    if "lipcal" not in _C:
        import json as _json
        from pathlib import Path as _P
        f = _P(__file__).with_name("lip_photo_bias.json")
        _C["lipcal"] = _json.loads(f.read_text())["cal"] if f.exists() else {}
    v = (_C["lipcal"].get(kind) or {}).get(key)
    return float(v[0]) if v else 0.0


def _gnm_to_model(head) -> dict:
    """GNM vertex id -> a model vertex of head["V"] (the first that carries it)."""
    key = ("g2m", len(head["gid"]))
    if key not in _C:
        first = {}
        for i, g_ in enumerate(np.asarray(head["gid"], int)):
            if g_ >= 0 and g_ not in first:
                first[int(g_)] = i
        _C[key] = first
    return _C[key]


def _lip_obs(head, view, ev):
    """THE LIP BORDERS IN THE SAME SOLVE: the front picture's traced vermilion borders (blockin_lips.photo_evidence:
    upper / lower polylines, px) against the model's border loops (GNM's lip-group vertices next to skin) through the
    view's camera: per border vertex its distance to the picture's border (mm, along the line to the nearest point),
    moving with the vertex. Every other border vertex; past the traced part's ends there is no evidence."""
    from . import blockin_lips as bl
    from . import base_identity
    sk = np.flatnonzero(np.asarray(base_identity._gnm_data()["skin"]))
    g2m = _gnm_to_model(head)
    cam = view["cam"]
    s_ = float(view.get("scale", 1.0))
    o_ = np.asarray(view.get("origin", (0.0, 0.0)), float)
    out = []
    for nm, rows in zip(("upper", "lower"), bl.border_loops()):
        mv = np.array([g2m.get(int(sk[r]), -1) for r in np.asarray(rows)[::2]])
        mv = mv[mv >= 0]
        if not len(mv):
            continue
        X = np.asarray(head["V"], float)[mv]
        px = _cam_points(cam, X)[1]
        d, q, ins = bl._poly_dist(px, (np.asarray(ev[nm], float) - o_) / 1.0)
        _, qc = _cam_points(cam, np.asarray(head["L"], float)[[48, 54]])
        c0_, ex_ = qc.mean(0), (qc[1] - qc[0]) / max(np.linalg.norm(qc[1] - qc[0]), 1e-9)
        half_ = 0.5 * np.linalg.norm(qc[1] - qc[0])
        photo = view.get("style") == "photo" and not view.get("render")
        for i in np.flatnonzero(ins):
            Jp, mm1 = _proj_jac_pt(cam, X[i], head["B"][:, mv[i]])
            if d[i] < 1e-6:
                n = np.array([0.0, 1.0 if nm == "lower" else -1.0])
            else:
                n = (q[i] - px[i]) / d[i]
            ub = int(np.clip(round((float((px[i] - c0_) @ ex_) / max(half_, 1e-9) + 1) * 5), 0, 10))
            b_ = lip_bias("lip", f"{nm}:{ub}") if photo else 0.0
            out.append({"type": "lip", "view": view["kind"], "name": f"lip_{nm}_{i}", "o": float(d[i]) * mm1 / s_ - b_ * float(n[1]), "n": n.tolist(),
                        "J": (n @ Jp) * mm1, "sig": SIG_LIP, "p": list(map(float, px[i])), "q": list(map(float, q[i])),
                        "X": list(map(float, X[i]))})
    return out
