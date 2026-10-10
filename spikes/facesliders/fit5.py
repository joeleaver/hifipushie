"""fit5.py <model> <out model>: faces5, the ONE MAP the way GNM is meant to be driven (docs/notes/gnm_audit.md section 8):
identity (all 170 head comps, N(0, I)) shared by every view + per-picture expression (both eyes' comp k as one variable,
k < NEYE, and lower face comps < NLOW; N(0, I)), Gauss-Newton with the head rebuilt each round.

Evidence:
  points   every view's MediaPipe 478 through the calibrated table (humanfit_map), with the noise model changed:
           INFLATE (default 1: the audit; humanfit_map's 2.0 halved all the information) and CUT (default none: the
           alar / jaw points stay at their honest sigma);
  border   the vermilion border along its length (lipborder.read on the front photo, both borders, ~50 samples within
           the corners) against the model's border loops (GNM's upper_lip / lower_lip groups' outer edges,
           lipborder_model), point-to-curve along the traced curve's normal, BORDER_SIG mm.
Unknowns not in the evidence come back as the mean (MAP); reported: |c|, the identity's effective degrees of freedom
trace(I - C_post) (the audit: ours pinned ~19), the posterior cost, per-view points rms, the border misses.
The model's local lip sliders are dropped (LIP_SLIDERS): GNM alone draws the lips. Writes <out model> (identity only:
the per-picture expressions go to fit5.json, the model's neutral is its identity) and $F/out/fit5_<out>.png."""
import copy
import json
import os
import sys
from pathlib import Path

import numpy as np

from hifipushie import headfit

headfit.N = 170
import joint as J0  # noqa: E402
import joint2 as J2  # noqa: E402
import outl  # noqa: E402
import lipborder as LB  # noqa: E402
import lipborder_model as LBM  # noqa: E402
from hifipushie import base as basemod, humanfit, humanfit_map as hm, likeness, onemesh, store  # noqa: E402

hm.INFLATE = float(os.environ.get("INFLATE", "1.0"))
hm.CUT = float(os.environ.get("CUT", "99"))
F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces5"))
WS = store.HOME
NEYE = int(os.environ.get("NEYE", "20"))
NLOW = int(os.environ.get("NLOW", "20"))
ROUNDS = int(os.environ.get("ROUNDS", "3"))
INNER = int(os.environ.get("INNER", "4"))
BORDER_SIG = float(os.environ.get("BORDER_SIG", "0.4"))   # mm
USE_BORDER = os.environ.get("BORDER", "1") == "1"
# per-picture expression prior sd: GNM's own prior is N(0, I) over expressive scans; a reference read as NEUTRAL gets a
# tighter one (design section 4: the detector's blendshapes set each picture's scale). With 1.0 the front picture's
# expression took the border evidence (|e| 2.2) and the identity, which ships, kept none of it.
EXPR_SD = float(os.environ.get("EXPR_SD", "0.3"))
PROF_SIG = float(os.environ.get("PROF_SIG", "0.7"))   # mm: a true profile's skin edge against a plain background
USE_PROFILE = os.environ.get("PROFILE", "1") == "1"
PROF_REJECT = float(os.environ.get("PROF_REJECT", "3.0"))
LIP_SLIDERS = ("lip_tubercle", "mouth_corner", "lip_lower_width", "mh_lowerlip_width", "mh_lowerlip_middle",
               "mh_lowerlip_volume", "mh_lowerlip_ext", "mh_mouth_angles", "lip_upper_height", "lip_lower_height",
               "lip_upper_roll", "lip_lower_roll", "lip_bow")
g = basemod._gnm_data()
EN = [str(x) for x in g["expression_names"]]
_EB = np.asarray(g["expression_basis"], float)
EXPR = ([(f"left_eye_region_{k:03d}", f"right_eye_region_{k:03d}") for k in range(NEYE)]
        + [(f"lower_face_region_{k:03d}",) for k in range(NLOW)])
EB = np.stack([sum(_EB[EN.index(x)] for x in t) for t in EXPR])
NE = len(EXPR)
NC = 170


def spec_with(spec, c):
    sp = copy.deepcopy(spec)
    b = humanfit._with_identity(sp["base"], c)
    b["head"]["sliders"] = {k: v for k, v in (b["head"].get("sliders") or {}).items() if k not in LIP_SLIDERS}
    if os.environ.get("NOSEAL"):
        b["head"].pop("lip_seal", None)
    sp["base"] = b
    return sp


def _carry(st):
    c = st["head"]["carry"]
    return np.asarray(c["R"], float), float(c["s"])


def expr_rows(st, rows):
    R, s = _carry(st)
    out = np.zeros((NE, len(rows), 3))
    for i, row in enumerate(rows):
        if row[0] == "v":
            out[:, i] = s * (EB[:, row[1]] * row[2][None, :, None]).sum(1) @ R.T
        elif row[0] == "L":
            r = g["lm68"][row[1]]
            out[:, i] = s * sum(float(w) * EB[:, int(v)] for v, w in zip(r[0::2], r[1::2])) @ R.T
    return out


def border_model(st):
    """{"up"/"lo": (X world (n, 3), XB identity (170, n, 3), XE expression (NE, n, 3))} for the border loops."""
    tpl = st["tpl"]
    P = np.asarray(tpl["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    of = np.full(len(g["template_vertex_positions"]), -1)
    of[gid[gid >= 0]] = np.flatnonzero(gid >= 0)
    R, s = _carry(st)
    hg = headfit._gnm()
    jm = hg["JB"].mean(1)
    IB = np.asarray(g["vertex_identity_basis"], float)[hg["comps"]]
    out = {}
    for k, loop in (("up", LBM.UP_LOOP), ("lo", LBM.LO_LOOP)):
        ok = of[loop] >= 0
        v = loop[ok]
        X = P[of[v]]
        XB = s * (IB[:, v] - jm[:, None, :]) @ R.T
        XE = s * EB[:, v] @ R.T
        out[k] = (X, XB, XE)
    return out


def silhouette_env(st, cam, o):
    """The model's profile silhouette read the SAME way as the photo's (outl.profile_auto: per row the first skin pixel
    from the side the face looks to), on our own render (likeness.render passes) through the view's camera; each
    silhouette pixel unprojected through its depth to the nearest head vertex. Returns envelope()'s dict. (The envelope
    match, farthest-out vertex in a band, fails in concavities: at the stomion and the mentolabial sulcus it picked
    the lips' vertices, 7-25 mm off, and those rows were rejected: the lips' depth went unseen.)"""
    from scipy.spatial import cKDTree
    from hifipushie import likeness, likeness_shape as lsh
    tpl = st["tpl"]
    P = np.asarray(tpl["P"], float)
    mesh = likeness.model_mesh_from_state(st)
    x0, x1 = o[:, 0].min() - 120, o[:, 0].max() + 60
    y0, y1 = o[:, 1].min() - 10, o[:, 1].max() + 10
    side = max(x1 - x0, y1 - y0)
    im, k, ps = likeness.render(mesh, cam, (x0, y0, x0 + side, y0 + side), px=int(side), brows=False, passes=True)
    part, zb = ps["part"], ps["zb"]
    if os.environ.get("SILDBG"):
        im.save(os.environ["SILDBG"])
    face_left = np.median(o[:, 0]) < cam["size"][0] / 2
    gid_all = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    tree = cKDTree(P)
    vs, keep, pts = [], [], []
    for i, (x, y) in enumerate(o):
        row = int(round((y - y0) * k))
        if not (0 <= row < part.shape[0]):
            continue
        sk = np.flatnonzero(part[row] == 0)
        if len(sk) == 0:
            continue
        j = sk[0] if face_left else sk[-1]
        xm = x0 + (j + 0.5) / k
        Xw = lsh.unproject(cam, np.array([[xm, y]]), np.array([zb[row, j]]))
        vs.append(int(tree.query(Xw)[1][0]))
        keep.append(i)
    if not vs:
        return None
    vs, keep = np.array(vs), np.array(keep)
    hg = headfit._gnm()
    c = st["head"]["carry"]
    gid = gid_all[vs]
    fade = np.asarray(onemesh.asset()["g_fade"], float)[np.maximum(gid, 0)] * (gid >= 0)
    Bv = np.asarray(g["vertex_identity_basis"], float)[hg["comps"]][:, np.maximum(gid, 0)]
    Bv = float(c["s"]) * (Bv - hg["JB"].mean(1, keepdims=True)) @ np.asarray(c["R"], float).T * fade[None, :, None]
    n_ = np.tile([[-1.0, 0.0]] if face_left else [[1.0, 0.0]], (len(vs), 1))
    return {"X": P[vs], "B": Bv, "p": o[keep], "n": n_, "vs": vs, "keep": keep}


SIL = os.environ.get("SIL", "render")   # render (silhouette_env) | envelope (joint2.envelope)


def _env(st, cam, o):
    return silhouette_env(st, cam, o) if SIL == "render" else J2.envelope(st, cam, o)


def fit_cam_pose(cam, X, uv, wt):
    """hm._fit_cam with the focal length held (pose only): the profile's camera, fitted to 8 clicks + the contour, let
    its focal drift to 1022 px at 0.34 m (from 2600 at 0.8: the lens / distance trade-off is unconstrained in a
    profile), and the near camera put the body's faces behind it (the clay render went solid)."""
    from scipy.optimize import least_squares

    def res(p):
        c = {**cam, "r": p[:3], "t": p[3:6]}
        return ((humanfit.project(c, X) - uv) * wt[:, None]).ravel()
    sol = least_squares(res, np.r_[cam["r"], cam["t"]], x_scale=[0.1, 0.1, 0.1, 0.05, 0.05, 0.3], loss="soft_l1",
                        f_scale=3.0)
    return {**cam, "r": [float(v) for v in sol.x[:3]], "t": [float(v) for v in sol.x[3:6]]}


CONTACT_PAIRS = ((13, 14), (82, 87), (312, 317), (81, 178), (311, 402))   # MediaPipe inner lips, upper / lower
CONTACT_SIG = float(os.environ.get("CONTACT_SIG", "0.3"))   # mm
USE_CONTACT = os.environ.get("CONTACT", "1") == "1"
# CONTACT_BY "identity" (default): the NEUTRAL's lips touch (GNM's identity is each person's relaxed neutral, closed for a
# closed-mouth person), so the shipped head keeps lip_seal (nothing left for it to pull: no pinching) and stays valid
# for face shapes (GnmFace needs a mouth that can open: mouth_gap 0 is refused). "expression": each picture's lower-face
# expression closes them (tl10: lips full and closed in the renders, but the identity stays parted 5.6 mm, and the
# shipped neutral then needs mouth_gap 0, which face_shapes rejects)
CONTACT_BY = os.environ.get("CONTACT_BY", "identity")


def _contact_pairs():
    """GNM's own lip contact ring (faceslide._lip_rings, the ring the seal closes), split by the upper_lip / lower_lip
    groups; each upper vertex paired with the lower vertex nearest in x on the template (the corners' 10% left out)."""
    from hifipushie import faceslide
    R = faceslide._lip_rings()
    C = R["rings"][R["contact"]]
    T = np.asarray(g["template_vertex_positions"], float)
    U, Lw = C[R["upper"][C]], C[~R["upper"][C]]
    x0, x1 = T[C, 0].min(), T[C, 0].max()
    U = U[(T[U, 0] > x0 + 0.1 * (x1 - x0)) & (T[U, 0] < x1 - 0.1 * (x1 - x0))]
    L = Lw[np.argmin(np.abs(T[Lw, 0][None, :] - T[U, 0][:, None]), 1)]
    return U, L


CU, CL = None, None


def contact_rows(st):
    """(upper, lower) contact-ring points on the built head: X (n, 3), XB (170, n, 3), XE (NE, n, 3). A closed-mouth
    picture asks each pair to touch (its lower-face expression closes the lips, GNM's way; faceslide's seal is off in
    the fit). (MediaPipe's inner-lip points, the first try, already 'touched' at 0.4 mm on a visibly parted mouth: the
    detector table puts both on the visible lip line.)"""
    global CU, CL
    if CU is None:
        CU, CL = _contact_pairs()
    tpl = st["tpl"]
    P = np.asarray(tpl["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    of = np.full(len(g["template_vertex_positions"]), -1)
    of[gid[gid >= 0]] = np.flatnonzero(gid >= 0)
    R, s = _carry(st)
    hg = headfit._gnm()
    jm = hg["JB"].mean(1)
    IB = np.asarray(g["vertex_identity_basis"], float)[hg["comps"]]
    out = []
    for vid in (CU, CL):
        out.append((P[of[vid]], s * (IB[:, vid] - jm[:, None, :]) @ R.T, s * EB[:, vid] @ R.T))
    return out


def proj_jac(cam, X):
    Rc = humanfit._cam_rot(cam)
    Xc = (X - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
    z = Xc[:, 2]
    J = np.zeros((len(X), 2, 3))
    J[:, 0, 0] = J[:, 1, 1] = cam["f"] / z
    J[:, 0, 2] = -cam["f"] * Xc[:, 0] / z ** 2
    J[:, 1, 2] = -cam["f"] * Xc[:, 1] / z ** 2
    return J @ Rc, z


def curve_rows(px, poly):
    """per point: (nearest point on the polyline, its unit normal)."""
    a, b = poly[:-1], poly[1:]
    ab = b - a
    tan = ab / np.maximum(np.linalg.norm(ab, axis=1, keepdims=True), 1e-9)
    nrm = np.c_[-tan[:, 1], tan[:, 0]]
    Q, Nn = [], []
    for p in px:
        t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab ** 2).sum(1), 1e-9), 0, 1)
        q = a + t[:, None] * ab
        j = int(np.argmin(np.linalg.norm(p - q, axis=1)))
        Q.append(q[j])
        Nn.append(nrm[j])
    return np.array(Q), np.array(Nn)


def system(st, views, cams, x, x_lin, border, nview):
    """Normal equations at x (linearised at x_lin's built state). x = [c (170), e_view0 (NE), e_view1, ...]."""
    n = NC + NE * nview
    H, b = np.zeros((n, n)), np.zeros(n)
    rep = {"rms": [], "border": {}}
    evs = J0.evidence(st, views)
    dc = x[:NC] - x_lin[:NC]
    for vi, (v, e) in enumerate(zip(views, evs)):
        ev = x[NC + NE * vi: NC + NE * (vi + 1)]
        XE = expr_rows(st, e["rows"])
        X = e["X"] + np.tensordot(dc, e["XB"], 1) + np.tensordot(ev, XE, 1)
        cam = cams[vi]
        mm0 = cam["t"][2] / cam["f"] * 1000
        prof = USE_PROFILE and abs(float(v.get("yaw", 0.0))) > 70
        cam = cams[vi] = (fit_cam_pose if prof else hm._fit_cam)(cam, X, e["uv"], mm0 / e["sig"])
        if prof:   # the camera fitted to the clicks AND the contour (the clicks alone left it ~3 mm off the skin edge)
            if "_prof" not in v:
                v["_prof"] = outl.profile_auto(v, step=3)
            for rej in (15.0, 6.0, PROF_REJECT):   # (coarse to fine: a clicks-only camera starts several mm off)
                env = _env(st, cam, v["_prof"])
                if env is None:
                    break
                gidv = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])][env["vs"]]
                fade = np.asarray(onemesh.asset()["g_fade"], float)[np.maximum(gidv, 0)] * (gidv >= 0)
                Rr, ss = _carry(st)
                XEp = ss * EB[:, np.maximum(gidv, 0)] @ Rr.T * fade[None, :, None]
                Xp = env["X"] + np.tensordot(dc, env["B"], 1) + np.tensordot(ev, XEp, 1)
                rp0 = ((humanfit.project(cam, Xp) - env["p"]) * env["n"]).sum(1) * mm0
                ok = np.abs(rp0) < rej
                cam = cams[vi] = fit_cam_pose(cam, np.r_[X, Xp[ok]], np.r_[e["uv"], env["p"][ok]],
                                             np.r_[mm0 / e["sig"], np.full(ok.sum(), mm0 / PROF_SIG)])
        J, z = proj_jac(cam, X)
        wt = (z / cam["f"] * 1000) / e["sig"]
        r = (e["uv"] - humanfit.project(cam, X)) * wt[:, None]
        a = np.linalg.norm(r, axis=1)
        hw = np.where(a > 2.5, np.sqrt(2.5 / np.maximum(a, 1e-9)), 1.0)
        A = np.zeros((len(X) * 2, n))
        A[:, :NC] = (np.einsum("nij,knj->nik", J, e["XB"]) * (wt * hw)[:, None, None]).reshape(-1, NC)
        A[:, NC + NE * vi: NC + NE * (vi + 1)] = (np.einsum("nij,knj->nik", J, XE) * (wt * hw)[:, None, None]).reshape(-1, NE)
        y = A @ x + (r * hw[:, None]).ravel()
        H += A.T @ A
        b += A.T @ y
        rep["rms"].append(float(np.sqrt(np.mean(a ** 2))))
        if prof:
            env = _env(st, cam, v["_prof"])
            if env is not None:
                tplP = np.asarray(st["tpl"]["P"], float)
                gidv = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])][env["vs"]]
                fade = np.asarray(onemesh.asset()["g_fade"], float)[np.maximum(gidv, 0)] * (gidv >= 0)
                Rr, ss = _carry(st)
                XEp = ss * EB[:, np.maximum(gidv, 0)] @ Rr.T * fade[None, :, None]
                Xp = env["X"] + np.tensordot(dc, env["B"], 1) + np.tensordot(ev, XEp, 1)
                Jp, zp = proj_jac(cam, Xp)
                mmpx = zp / cam["f"] * 1000
                rp = ((humanfit.project(cam, Xp) - env["p"]) * env["n"]).sum(1) * mmpx / PROF_SIG
                ap = np.abs(rp)
                # matches more than PROF_REJECT mm off are dropped (lashes crossing the contour at the eye, envelope
                # picks on the brow / under the chin: 9.6 mm rms at the start with them in)
                hwp = np.where(ap > 2.5, np.sqrt(2.5 / np.maximum(ap, 1e-9)), 1.0) * (ap * PROF_SIG < PROF_REJECT)
                Ap = np.zeros((len(Xp), n))
                Ap[:, :NC] = np.einsum("ni,nij,knj->nk", env["n"], Jp, env["B"]) * (mmpx * hwp / PROF_SIG)[:, None]
                Ap[:, NC + NE * vi: NC + NE * (vi + 1)] = np.einsum("ni,nij,knj->nk", env["n"], Jp, XEp) * (mmpx * hwp / PROF_SIG)[:, None]
                yp = Ap @ x - rp * hwp
                H += Ap.T @ Ap
                b += Ap.T @ yp
                kept = ap * PROF_SIG < PROF_REJECT
                rep["profile_mm"] = float(np.sqrt(np.mean((rp[kept] * PROF_SIG) ** 2))) if kept.any() else None
                rep["profile_kept"] = f"{int(kept.sum())}/{len(kept)}"
        if USE_CONTACT and abs(float(v.get("yaw", 0.0))) < 70:   # a closed mouth in this picture
            (Xu, XBu, XEu), (Xl, XBl, XEl) = contact_rows(st)
            D = (Xu - Xl) + np.tensordot(dc, XBu - XBl, 1) + np.tensordot(ev, XEu - XEl, 1)   # (n, 3) m
            wv = np.ones_like(D)
            wv[:, 0] = 0.0                       # (x: the pairs are matched in x)
            wv[:, 2] = np.where(D[:, 2] > 0, 1.0, 0.0)   # world z up: upper above lower = open; touching / pressed: free
            rc = (D * wv * 1000 / CONTACT_SIG).ravel()
            Ac = np.zeros((len(rc), n))
            Ac[:, :NC] = ((XBu - XBl) * wv[None] * 1000 / CONTACT_SIG).transpose(1, 2, 0).reshape(-1, NC)
            if CONTACT_BY == "expression":
                Ac[:, NC + NE * vi: NC + NE * (vi + 1)] = ((XEu - XEl) * wv[None] * 1000 / CONTACT_SIG).transpose(1, 2, 0).reshape(-1, NE)
            else:   # the neutral's own contact: the picture's expression is not in it
                D = (Xu - Xl) + np.tensordot(dc, XBu - XBl, 1)
                wv[:, 2] = np.where(D[:, 2] > 0, 1.0, 0.0)
                rc = (D * wv * 1000 / CONTACT_SIG).ravel()
                Ac[:, :NC] = ((XBu - XBl) * wv[None] * 1000 / CONTACT_SIG).transpose(1, 2, 0).reshape(-1, NC)
            yc = Ac @ x - rc
            H += Ac.T @ Ac
            b += Ac.T @ yc
            rep.setdefault("contact_mm", []).append(float(np.sqrt(np.mean(np.sum((D * wv) ** 2, 1)))) * 1000)
        if abs(float(v.get("yaw", 0.0))) < 20 and border is not None:
            bm = border_model(st)
            for k, poly in (("up", border["upper"][border["keep"]]), ("lo", border["lower"][border["keep"]])):
                Xb, XBb, XEb = bm[k]
                Xb = Xb + np.tensordot(dc, XBb, 1) + np.tensordot(ev, XEb, 1)
                px = humanfit.project(cam, Xb)
                # only model samples within the traced span (the corners are the detector's)
                lo_x, hi_x = poly[:, 0].min(), poly[:, 0].max()
                inn = (px[:, 0] > lo_x) & (px[:, 0] < hi_x)
                Q, Nn = curve_rows(px[inn], poly)
                Jb, zb = proj_jac(cam, Xb[inn])
                mmpx = zb / cam["f"] * 1000
                rr = ((px[inn] - Q) * Nn).sum(1) * mmpx / BORDER_SIG       # + along the curve's normal
                Ab = np.zeros((inn.sum(), n))
                Ab[:, :NC] = np.einsum("ni,nij,knj->nk", Nn, Jb, XBb[:, inn]) * (mmpx / BORDER_SIG)[:, None]
                Ab[:, NC + NE * vi: NC + NE * (vi + 1)] = np.einsum("ni,nij,knj->nk", Nn, Jb, XEb[:, inn]) * (mmpx / BORDER_SIG)[:, None]
                yb = Ab @ x - rr
                H += Ab.T @ Ab
                b += Ab.T @ yb
                rep["border"][k] = (rr * BORDER_SIG).round(2).tolist()
    return H, b, rep


def main(src, dst):
    from PIL import Image
    spec = store.load(src)
    refs = json.loads((WS / src / "human_refs.json").read_text())
    views = [dict(v) for v in refs["views"]]
    cams = [dict(cm) for cm in refs["cameras"]]
    if os.environ.get("VIEWS"):   # a subset of the references (the consistency test: front + 3/4 vs profile)
        sel = [int(i) for i in os.environ["VIEWS"].split(",")]
        views, cams = [views[i] for i in sel], [cams[i] for i in sel]
    nv = len(views)
    border = None
    if USE_BORDER:
        fr = [v for v in views if abs(float(v.get("yaw", 0.0))) < 20]
        img = Image.open((fr[0] if fr else refs["views"][0])["image"]).convert("RGB")
        border = LB.read(img, likeness.detect([img])[0])
    c0 = humanfit.identity(spec["base"])
    x = np.r_[c0, np.zeros(NE * nv)]
    n = len(x)
    Pinv = np.diag(np.r_[np.ones(NC), np.full(NE * nv, 1.0 / EXPR_SD ** 2)])
    rviews = None
    log = []
    for rnd in range(ROUNDS):
        st = humanfit.state(spec_with(spec, x[:NC])["base"])
        if rviews is None:
            rviews = hm._resolve(st, views)
        x_lin = x.copy()
        for it in range(INNER):
            H, b, rep = system(st, rviews, cams, x, x_lin, border, nv)
            if rnd == 0 and it == 0:
                rep0 = rep
                print("start:", json.dumps({"rms": np.round(rep["rms"], 2).tolist(), "profile_mm": rep.get("profile_mm"), "kept": rep.get("profile_kept"),
                                            "border_rms": {k: float(np.sqrt(np.mean(np.square(v)))) for k, v in rep["border"].items()}}), flush=True)
            x = np.linalg.solve(H + Pinv, b)
        post = np.linalg.inv(H + Pinv)
        dof = float(NC - np.trace(post[:NC, :NC]))
        log.append({"round": rnd, "rms": rep["rms"], "profile_mm": rep.get("profile_mm"), "kept": rep.get("profile_kept"), "c_norm": float(np.linalg.norm(x[:NC])), "dof": dof,
                    "border_rms": {k: float(np.sqrt(np.mean(np.square(v)))) for k, v in rep["border"].items()},
                    "expr_norm": [float(np.linalg.norm(x[NC + NE * i: NC + NE * (i + 1)])) for i in range(nv)]})
        print(f"round {rnd}: {json.dumps(log[-1])}", flush=True)
    st = humanfit.state(spec_with(spec, x[:NC])["base"])
    H, b, rep = system(st, rviews, cams, x, x, border, nv)
    out = {"src": src, "inflate": hm.INFLATE, "cut": hm.CUT, "border_sig": BORDER_SIG, "start": rep0, "final": rep,
           "c_norm_start": float(np.linalg.norm(c0)), "c_norm": float(np.linalg.norm(x[:NC])),
           "max_c": float(np.abs(x[:NC]).max()), "dc_norm": float(np.linalg.norm(x[:NC] - c0)),
           "expr": {f"view{i}": dict(zip(["+".join(t) for t in EXPR], x[NC + NE * i: NC + NE * (i + 1)].round(3).tolist()))
                    for i in range(nv)}, "log": log}
    d = WS / dst
    d.mkdir(exist_ok=True)
    noseal = os.environ.pop("NOSEAL", None)
    shipped = spec_with(spec, x[:NC])
    if noseal and USE_CONTACT and CONTACT_BY == "expression":
        # the shipped neutral closes its mouth with the fit's OWN closing: the front (else first closed-mouth)
        # picture's lower-face expression as base.head.expression. (faces5 shipped mouth_gap 0 instead: base's solver
        # closes only the midline pair 62 / 66 and left tl10's raw mouth parted 3.5 mm, which the implicit surface
        # fused into one thick lip: the "too full, bow lost" overshoot, f6_04)
        shipped["base"]["head"].pop("lip_seal", None)
        shipped["base"]["head"].pop("mouth_gap", None)
        vi0 = next((i for i, v in enumerate(views) if abs(float(v.get("yaw", 0.0))) < 20),
                   next(i for i, v in enumerate(views) if abs(float(v.get("yaw", 0.0))) < 70))
        ev0 = x[NC + NE * vi0: NC + NE * (vi0 + 1)]
        shipped["base"]["head"]["expression"] = {**(shipped["base"]["head"].get("expression") or {}),
                                                 **{t[0]: float(e) for t, e in zip(EXPR, ev0) if t[0].startswith("lower_face")}}
    (d / "spec.json").write_text(json.dumps(shipped, indent=1))
    r2 = dict(refs)
    r2["cameras"] = cams
    if os.environ.get("VIEWS"):
        r2["views"] = [refs["views"][i] for i in sel]
    (d / "human_refs.json").write_text(json.dumps(r2, indent=1, default=float))
    (d / "fit5.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: out[k] for k in ("c_norm_start", "c_norm", "max_c", "dc_norm")}), "final rms", np.round(rep["rms"], 2).tolist(),
          "border", {k: float(np.sqrt(np.mean(np.square(v)))) for k, v in rep["border"].items()})
    print("wrote", d)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
