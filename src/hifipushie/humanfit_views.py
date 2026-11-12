"""Reference images: cameras and the face fitted together on named 2D points (project, the silhouette,
fit_outline, fit_region, fit_hood, fit_views). Part of humanfit (humanfit.py has the overview)."""
from __future__ import annotations

import copy

import numpy as np

from . import humanfit
from .humanfit import _faces, _gnm_normals, identity, plausibility, state
from .humanfit_integrity import _guarded, _newly_broken, integrity, side_effects
from .humanfit_solve import _cheek_basis, _lm_basis, _skull_basis, _with_identity

# ---- reference images: cameras and the face fitted together on named 2D points --------------------------------------
def point_index(name) -> int:
    if isinstance(name, (int, np.integer)):
        return int(name)
    if name in humanfit.LANDMARKS:
        return humanfit.LANDMARKS[name]
    if name in ("eye.L", "eye_centre.L"):
        return humanfit.EYE_L
    if name in ("eye.R", "eye_centre.R"):
        return humanfit.EYE_R
    if str(name).startswith("lm") and str(name)[2:].isdigit():
        return int(str(name)[2:])
    raise ValueError(f"humanfit: no landmark {name!r} (have {', '.join(humanfit.LANDMARKS)}, eye.L, eye.R, lm0..lm67 = the 68-point "
                     "face convention)")


def _rotvec(r):
    th = float(np.linalg.norm(r))
    if th < 1e-12:
        return np.eye(3)
    k = np.asarray(r, float) / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


def _cam_rot(cam: dict) -> np.ndarray:
    return _rotvec(np.asarray(cam["r"], float)) @ humanfit._CAM0 @ _rotvec([0, 0, np.radians(cam.get("yaw", 0.0))])


def project(cam: dict, X: np.ndarray) -> np.ndarray:
    """World points -> pixels (u right, v down) through a fitted camera {"r", "t", "f", "size", "centre", "yaw"}."""
    Xc = (np.asarray(X, float) - np.asarray(cam["centre"], float)) @ _cam_rot(cam).T + np.asarray(cam["t"], float)
    w, h = cam["size"]
    return np.stack([cam["f"] * Xc[:, 0] / Xc[:, 2] + w / 2, cam["f"] * Xc[:, 1] / Xc[:, 2] + h / 2], 1)


def _silhouette(st: dict, cam: dict, outline: np.ndarray, skip_ears: bool = True) -> dict | None:
    """The head's silhouette through a camera matched to a reference outline: for each outline point (pixels) the
    nearest silhouette vertex of the head (edges between faces turned toward and away from the camera; GNM's own
    vertices above the stitch), its world position, how it moves per identity component (as the landmarks:
    _lm_basis) and the outline's normal there. None if nothing matched."""
    from . import base_identity
    from . import headfit, onemesh
    from scipy.spatial import cKDTree
    tpl, c = st["tpl"], st["head"]["carry"]
    P = np.asarray(tpl["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    fade = np.asarray(onemesh.asset()["g_fade"], float)
    head = (gid >= 0) & (fade[np.maximum(gid, 0)] > 0.3)
    if skip_ears:  # an ear's rim is silhouette too, and no face outline follows it
        ears = np.asarray(base_identity._gnm_data()["groups"]["ears"], float) > 0.5
        head &= ~ears[np.maximum(gid, 0)]
    T = np.array([(f[0], f[j], f[j + 1]) for f in _faces(tpl) for j in range(1, len(f) - 1)])
    T = T[head[T].all(1)]
    Rc = _cam_rot(cam)
    Xc = (P - np.asarray(cam["centre"], float)) @ Rc.T + np.asarray(cam["t"], float)
    n = np.cross(Xc[T[:, 1]] - Xc[T[:, 0]], Xc[T[:, 2]] - Xc[T[:, 0]])
    front = (n * Xc[T].mean(1)).sum(1) < 0
    edges = {}
    for t, f in zip(T, front):
        for k in range(3):
            e = (min(t[k], t[(k + 1) % 3]), max(t[k], t[(k + 1) % 3]))
            edges.setdefault(e, []).append(bool(f))
    sv = np.unique([v for e, fs in edges.items() if len(fs) == 2 and fs[0] != fs[1] for v in e])
    if not len(sv):
        return None
    uv = project(cam, P[sv])
    o = np.asarray(outline, float)
    tan = np.gradient(o, axis=0)
    nrm = np.c_[-tan[:, 1], tan[:, 0]]
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    d, j = cKDTree(uv).query(o)
    ok = d < 0.06 * max(cam["size"])
    if not ok.any():
        return None
    vs = sv[j[ok]]
    g = headfit._gnm()
    Bv = np.asarray(base_identity._gnm_data()["vertex_identity_basis"], float)[g["comps"]][:, gid[vs]]
    Bv = float(c["s"]) * (Bv - g["JB"].mean(1, keepdims=True)) @ np.asarray(c["R"], float).T
    Bv = Bv * fade[gid[vs]][None, :, None]
    return {"X": P[vs], "B": Bv, "p": o[ok], "n": nrm[ok]}


def fit_outline(base: dict, views: list, cameras: list, rounds: int = 3, symmetric: bool = True,
                structure: bool = True, force: bool = False, sigma: float | None = None) -> tuple:
    """(new base, report): the head's silhouette through each fitted camera (`cameras`, from fit_views) pulled onto
    each view's `outline` ([[u, v], ...]: the face's edge in the picture, e.g. jaw and cheeks) by a smooth warp in
    GNM's frame (base.head.warp, appended), the features held (eyes, nose, lips, brows: their landmarks stay, so an
    outline can't drag the mouth). Each silhouette vertex's 2D miss along the outline's normal becomes a 3D move in
    the camera's image plane at its depth. Identity components are left to fit_views (the points).
    A view may carry "outline_axis": "y" (only the outline's up / down misses count: a painting's camera is too loose
    for widths, its jaw angle's and cheekbone's heights still read) and "outline_weight".
    structure: width is BONE (cheekbones, jaw angles, temples, chin): targets on the soft mid-cheek count
    STRUCTURE_SOFT, and the cheek's front (GNM's cheek regions, facing forward) is held where it is, so the warp
    widens the head's sides instead of filling the cheeks (pass 2 without it: a pear-shaped, jowly face)."""
    from . import base_identity
    from . import onemesh
    from . import onemesh_head
    g = base_identity._gnm_data()
    cur = copy.deepcopy(base)
    names = [str(n) for n in g["identity_names"]]
    rep = {"rounds": []}
    for rnd in range(rounds):
        st = state(cur)
        hd = onemesh_head.head_desc(cur)
        c = st["head"]["carry"]
        Rh, s = np.asarray(c["R"], float), float(c["s"])
        idn = dict(base_identity.fit_identity(hd["fit"])) if hd.get("fit") else {}
        idn.update(hd.get("identity") or {})
        call = np.array([float(idn.get(n, 0.0)) for n in names])
        Vg = np.asarray(g["template_vertex_positions"], float) + np.tensordot(call, np.asarray(g["vertex_identity_basis"], float), 1)
        gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])]
        fade = np.asarray(onemesh.asset()["g_fade"], float)
        tgt_g, tgt_d, tgt_w, miss = [], [], [], []
        soft = np.zeros(len(Vg))
        if structure:
            soft = np.clip(np.asarray(g["groups"]["left_cheek_region"], float) + np.asarray(g["groups"]["right_cheek_region"], float), 0, 1)
        for v, cam in zip(views, cameras):
            if not v.get("outline"):
                continue
            sl = _silhouette(st, cam, np.asarray(v["outline"], float))
            if sl is None:
                continue
            uv = project(cam, sl["X"])
            r = ((uv - sl["p"]) * sl["n"]).sum(1)  # px past the outline along its normal
            Rc = _cam_rot(cam)
            Xc = (sl["X"] - np.asarray(cam["centre"], float)) @ Rc.T + np.asarray(cam["t"], float)
            m = r * Xc[:, 2] / cam["f"]  # m in the image plane at the vertex's depth
            nn = sl["n"].copy()
            if v.get("outline_axis") == "y":  # heights only: the miss along the image's vertical
                m = m * nn[:, 1]
                nn = np.c_[np.zeros(len(nn)), np.sign(nn[:, 1]) + (nn[:, 1] == 0)]
            w = nn[:, :1] * Rc[0] + nn[:, 1:] * Rc[1]  # the outline's normal as a world direction
            dW = -np.clip(m, -humanfit.OUTLINE_STEP, humanfit.OUTLINE_STEP)[:, None] * w  # (a round moves no point further: a silhouette
            # vertex matched across a gap the first round would throw the warp)
            P = np.asarray(st["tpl"]["P"], float)
            vs = np.array([int(np.argmin(np.linalg.norm(P - x, axis=1))) for x in sl["X"]])
            for k, vi in enumerate(vs):
                gi = gid[vi]
                if gi < 0 or fade[gi] < 0.3:
                    continue
                dg = (dW[k] @ Rh) / s / fade[gi]
                dg[0] /= float(c["narrow"])
                tgt_g.append(Vg[gi])
                tgt_d.append(dg)
                tgt_w.append(float(v.get("outline_weight", 1.0)) * (1.0 - (1.0 - humanfit.STRUCTURE_SOFT) * soft[gi]))
            miss.append(float(np.sqrt((m ** 2).mean()) * 1000))
        if not tgt_g:
            break
        if symmetric:  # each target also on the other side, mirrored (GNM's template is symmetric about x = 0): one
            # view's outline alone warped only its own side, a lump on one jaw
            tgt_g = tgt_g + [x * [-1, 1, 1] for x in tgt_g]
            tgt_d = tgt_d + [x * [-1, 1, 1] for x in tgt_d]
            tgt_w = tgt_w + tgt_w
        hold = []
        for row in g["lm68"][17:]:  # brows, nose, eyes, lips stay
            hold.append(sum(float(wt) * Vg[int(vi)] for vi, wt in zip(row[0::2], row[1::2])))
        # and the rest of the head where it is: skin vertices farther than two reaches from every target
        skin = np.flatnonzero(np.asarray(g["skin"], bool))
        far = skin[np.min(np.linalg.norm(Vg[skin][:, None] - np.array(tgt_g)[None], axis=2), 1) > 2 * humanfit.OUTLINE_SIGMA]
        far = far[np.linspace(0, len(far) - 1, min(len(far), 160)).astype(int)] if len(far) else far
        hold += list(Vg[far])
        hw = [humanfit.OUTLINE_HOLD] * len(hold)
        if structure:  # the cheeks' fronts stay
            front = skin[(soft[skin] > 0.5) & (_gnm_normals(Vg)[skin][:, 2] > 0.35)]
            front = front[np.linspace(0, len(front) - 1, min(len(front), 120)).astype(int)] if len(front) else front
            hold += list(Vg[front])
            hw += [humanfit.STRUCTURE_HOLD] * len(front)
            # and the lips whole (their landmarks alone held the corners while the rolls beside them were pulled:
            # widening the jaw at mouth level squeezed the lips' edges past the limit)
            lips = np.flatnonzero(((np.asarray(g["groups"]["upper_lip"], float) > 0.5)
                                   | (np.asarray(g["groups"]["lower_lip"], float) > 0.5)) & np.asarray(g["skin"], bool))
            lips = lips[np.linspace(0, len(lips) - 1, min(len(lips), 80)).astype(int)] if len(lips) else lips
            hold += list(Vg[lips])
            hw += [humanfit.STRUCTURE_HOLD] * len(lips)
            # and the mouth's corners hard (every skin vertex within 8 mm of lm 48 / 54): their edges are the shortest
            # on the face, so 0.1 mm of drift there reads as a squeeze (Garrett's v23 corner, x0.23 -> x0.20)
            lmg = np.array([sum(float(wt) * Vg[int(vi)] for vi, wt in zip(row[0::2], row[1::2])) for row in g["lm68"]])
            cn = skin[np.min(np.linalg.norm(Vg[skin][:, None] - lmg[None, [48, 54]], axis=2), 1) < 0.008]
            hold += list(Vg[cn])
            hw += [humanfit.STRUCTURE_HOLD * 4] * len(cn)
        A = np.r_[np.array(tgt_g), np.array(hold)]
        Dt = np.r_[np.array(tgt_d), np.zeros((len(hold), 3))]
        wt = np.r_[np.array(tgt_w), np.array(hw)]
        ws = (cur.get("head") or {}).get("warp")
        ws = [] if not ws else (ws if isinstance(ws, list) else [ws])
        sig = float(sigma if sigma is not None else (ws[-1]["sigma"] if ws else humanfit.OUTLINE_SIGMA))
        K = np.exp(-((A[:, None] - A[None]) ** 2).sum(-1) / (2 * sig ** 2))
        coef = np.linalg.solve((K * wt[:, None]).T @ K + 2e-2 * np.eye(len(A)), (K * wt[:, None]).T @ Dt)
        if structure:  # the ears ride their side of the head as ONE piece: the first solve's move at the ear, averaged
            # over it, is laid on every ear vertex and the warp solved again (left to the warp the ear's front went out
            # with the face's side and its back didn't: the tragus squeezed x0.21-0.24 at 75-100% of the width)
            ears = np.flatnonzero((np.asarray(g["groups"]["ears"], float) > 0.5) & np.asarray(g["skin"], bool))
            add_g, add_d = [], []
            for sg in (-1.0, 1.0):
                es = ears[np.sign(Vg[ears, 0]) == sg]
                if not len(es):
                    continue
                Ke = np.exp(-((Vg[es][:, None] - A[None]) ** 2).sum(-1) / (2 * sig ** 2))
                mv = (Ke @ coef).mean(0)
                es = es[np.linspace(0, len(es) - 1, min(len(es), 60)).astype(int)]
                add_g += list(Vg[es])
                add_d += [mv] * len(es)
            if add_g:
                ag = np.array(add_g)
                near_ear = np.min(np.linalg.norm(A[:, None] - ag[None], axis=2), 1) < humanfit.EAR_FREE
                keep = np.r_[np.ones(len(tgt_g), bool), ~near_ear[len(tgt_g):]]  # holds round the ear let go
                A = np.r_[A[keep], ag]
                Dt = np.r_[Dt[keep], np.array(add_d)]
                wt = np.r_[wt[keep], np.full(len(ag), humanfit.EAR_RIDE)]
                K = np.exp(-((A[:, None] - A[None]) ** 2).sum(-1) / (2 * sig ** 2))
                coef = np.linalg.solve((K * wt[:, None]).T @ K + 2e-2 * np.eye(len(A)), (K * wt[:, None]).T @ Dt)
        h = cur.setdefault("head", {})
        # appended to the warp of the same reach (centres added), or a warp of its own (a list of warps)
        same = [i for i, w in enumerate(ws) if abs(float(w["sigma"]) - sig) < 1e-9]
        if same:
            w0 = ws[same[-1]]
            A, coef = np.r_[np.asarray(w0["at"], float), A], np.r_[np.asarray(w0["coef"], float), coef]
            ws[same[-1]] = {"at": np.round(A, 6).tolist(), "coef": np.round(coef, 7).tolist(), "sigma": sig}
        else:
            ws = ws + [{"at": np.round(A, 6).tolist(), "coef": np.round(coef, 7).tolist(), "sigma": sig}]
        h["warp"] = ws[0] if len(ws) == 1 else ws
        rep["rounds"].append({"miss_mm": [round(x, 2) for x in miss], "targets": len(tgt_g)})
    st1 = state(cur)
    rep["integrity"] = integrity(cur, st1, state(base))
    rep["side_effects"] = side_effects(state(base), st1, set(humanfit.FACE))
    return _guarded(base, cur, rep, force)


def _hood_amount(base: dict) -> float:
    h = ((base.get("head") or {}).get("shape") or {}).get("hood") or 0.0
    return float(h["amount"] if isinstance(h, dict) else h)


def _with_hood(base: dict, a: float) -> dict:
    b = copy.deepcopy(base)
    sh = b.setdefault("head", {}).setdefault("shape", {})
    if isinstance(sh.get("hood"), dict):
        sh["hood"]["amount"] = round(float(a), 6)
    elif a > 0:
        sh["hood"] = round(float(a), 6)
    else:
        sh.pop("hood", None)
    return b


def fit_region(base: dict, cameras: list, targets: list, group, feather: int = 8, hold=None, force: bool = False,
               name: str | None = None) -> tuple:
    """(new base, report): GNM identity components applied inside ONE region (base.head.regions: a feathered group,
    e.g. "nose_region"), fitted so given SURFACE points land where a picture has them. targets = [{"view": i, "tpl":
    [vertex index x 3], "bary": [w x 3], "uv": [x, y]}]: a point on the template mesh (a triangle's corners and
    barycentric weights, as a render's id pass gives it) and where it should project through cameras[view]. Points are
    linear in the components (GNM vertex basis x region weight, placed by the head's scale / rotation / narrowing),
    so the step is one ridge least squares; `hold` = 68-landmark indices kept where they are (default: everything
    outside the nose and the brows' inner ends). A region of the same `name` (default the group) is replaced
    (re-fitted on top of its own components). Refused if it breaks the mesh (unless force)."""
    from . import base_identity
    from . import onemesh
    g = base_identity._gnm_data()
    names = [str(n) for n in g["identity_names"]][:humanfit.REGION_K]
    VB = np.asarray(g["vertex_identity_basis"], float)[:humanfit.REGION_K]
    st0 = state(base)
    c = st0["head"]["carry"]
    Rh, s, nar = np.asarray(c["R"], float), float(c["s"]), float(c["narrow"])
    gid_all = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st0["tpl"]["fid"])]
    fade = np.asarray(onemesh.asset()["g_fade"], float)
    rw = base_identity.region_weight(group, int(feather))
    rname = name or (group if isinstance(group, str) else "+".join(group))
    regs = list((base.get("head") or {}).get("regions") or [])
    old = next((r for r in regs if r.get("name") == rname), None)
    c0 = np.array([float((old or {}).get("identity", {}).get(n, 0.0)) for n in names])

    def basis_at(gids, w):  # (K, 3) world move per component of a surface point
        B = np.zeros((len(names), 3))
        for gi, wi in zip(gids, w):
            if gi < 0:
                continue
            d = VB[:, gi, :] * rw[gi] * fade[gi]
            d = d * [nar, 1.0, 1.0]
            B += wi * s * d @ Rh.T
        return B

    def cam_jac(cam, X):  # 2 x 3 numerical
        e = 1e-5
        u0 = project(cam, X[None])[0]
        return np.stack([(project(cam, (X + e * np.eye(3)[k])[None])[0] - u0) / e for k in range(3)], 1), u0

    rows, rhs, miss = [], [], []
    P = np.asarray(st0["tpl"]["P"], float)
    for t in targets:
        cam = cameras[int(t["view"])]
        idx, w = np.asarray(t["tpl"], int), np.asarray(t["bary"], float)
        X = (w[:, None] * P[idx]).sum(0)
        Jc, u0 = cam_jac(cam, X)
        B = basis_at(gid_all[idx], w)
        Xc = (X - np.asarray(cam["centre"])) @ _cam_rot(cam).T + np.asarray(cam["t"])
        k = Xc[2] / cam["f"] * 1000  # mm per px there
        A = (B @ Jc.T) * k  # (K, 2) mm per component
        r = (np.asarray(t["uv"], float) - u0) * k
        miss.append(float(np.linalg.norm(r)))
        rows += list(A.T)
        rhs += list(r)
    hold = list(hold) if hold is not None else [i for i in range(17, 68) if not (27 <= i <= 35)]
    L0 = st0["L"]
    for i in hold:  # the landmark's own vertices: a world move per component, held at zero (x, y, z)
        row = g["lm68"][i]
        B = basis_at(np.asarray(row[0::2], int), np.asarray(row[1::2], float))
        for a in range(3):
            rows.append(B[:, a] * 1000 * humanfit.REGION_HOLD)
            rhs.append(0.0)
    for kk in range(len(names)):
        e = np.zeros(len(names))
        e[kk] = humanfit.REGION_RIDGE * 10
        rows.append(e)
        rhs.append(-humanfit.REGION_RIDGE * 10 * c0[kk] * 0.0)
    dc = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)[0]
    clip = humanfit.CLIP_FORCE if force else humanfit.CLIP
    # the step is cut back until the mesh holds (the share reached is reported): a nose turned up in full folded its
    # nostrils' insides
    for share in ((1.0,) if force else (1.0, 0.75, 0.55, 0.4, 0.28, 0.2)):
        cn = np.clip(c0 + share * dc, -clip, clip)
        cur = copy.deepcopy(base)
        h = cur.setdefault("head", {})
        entry = {"name": rname, "group": group, "feather": int(feather),
                 "identity": {n: round(float(v), 4) for n, v in zip(names, cn) if abs(v) > 1e-4}}
        h["regions"] = [r for r in regs if r.get("name") != rname] + [entry]
        st1 = state(cur)
        it = integrity(cur, st1, st0)
        if it["ok"] or not _newly_broken(base, it):
            break
    rep = {"region": rname, "points": len(targets), "miss_mm_before": round(float(np.sqrt(np.mean(np.square(miss)))), 2),
           "share": share, "components_used": int((np.abs(cn) > 1e-4).sum()), "largest_sigma": round(float(np.abs(cn).max()), 2),
           "plausibility": plausibility(cur), "side_effects": side_effects(st0, st1, set(humanfit.FACE)), "integrity": it}
    # what the step reached (linear prediction at the points)
    A_t = np.array(rows[:2 * len(targets)])
    rr = np.array(rhs[:2 * len(targets)]) - A_t @ (cn - c0)
    rep["miss_mm_after"] = round(float(np.sqrt(np.mean(rr.reshape(-1, 2) ** 2) * 2)), 2)
    return _guarded(base, cur, rep, force)


def fit_hood(base: dict, views: list, cameras: list, force: bool = False) -> tuple:
    """(new base, report): hooded upper lids (base.head.shape.hood) fitted on the upper lids' points (37, 38, 43, 44)
    through each fitted camera (`cameras`, from fit_views): a picture's upper lid line is where the fold hangs over
    the lid, which the identity components can't reach without squeezing the lids. One number, solved linearly
    (the hood moves those landmarks in proportion), clamped to [0, HOOD_MAX] and halved until integrity holds."""
    st0 = state(base)
    a0 = _hood_amount(base)
    step = 0.002 if a0 + 0.002 <= humanfit.HOOD_MAX else -0.002
    st1 = state(_with_hood(base, a0 + step))
    J, r = [], []
    for v, cam in zip(views, cameras):
        for j in humanfit.HOOD_LIDS:
            p = v["points"].get(f"lm{j}")
            if p is None:
                continue
            u0, u1 = project(cam, st0["L"][j:j + 1])[0], project(cam, st1["L"][j:j + 1])[0]
            J.append((u1 - u0) / step)
            r.append(np.asarray(p, float) - u0)
    rep = {"amount_before": round(a0 * 1000, 2), "points": len(r)}
    if not r:
        rep.update(amount=rep["amount_before"], note="no upper-lid points in the views")
        return base, rep
    J, r = np.array(J).ravel(), np.array(r).ravel()
    da = float(J @ r / max(J @ J, 1e-12))
    a = float(np.clip(a0 + da, 0.0, humanfit.HOOD_MAX))
    rep["asked_mm"] = round((a0 + da) * 1000, 2)
    rep["rms_px_before"] = round(float(np.sqrt((r ** 2).mean())), 2)
    while True:
        cur = _with_hood(base, a)
        st = state(cur)
        it = integrity(cur, st, st0)
        if it["ok"] or abs(a - a0) < 1e-4:
            break
        a = a0 + 0.5 * (a - a0)
    rr = r - J * (a - a0)
    rep.update(amount=round(a * 1000, 2), rms_px_after=round(float(np.sqrt((rr ** 2).mean())), 2), integrity=it,
               side_effects=side_effects(st0, st, {"eye_height"}))
    if a0 + da > humanfit.HOOD_MAX:
        rep["note"] = f"the picture asks {1000 * (a0 + da):.1f} mm of hood, the most is {1000 * humanfit.HOOD_MAX:.1f}"
    elif a0 + da < 0:
        rep["note"] = "the picture's upper lids are HIGHER than the hood-free face's: open the eyes (pose lid_upper) instead"
    return _guarded(base, cur, rep, force)


def fit_views(base: dict, views: list, free=("identity",), force: bool = False, rounds: int = 3, focal: float | None = None,
              hold_cheeks: bool = True) -> tuple:
    """(new base, report). views: [{"points": {landmark: [u, v]}, "size": [w, h], "yaw": deg (a hint: 0 front, 45
    three-quarter from its left, 90 its left side)}]: one camera per view (pose + focal; all views share the face) and,
    with "identity" free, the identity components, solved together on the reprojection error, ridged toward the
    current face. A single frontal view says nothing about depth: profile measures stay as they were."""
    from scipy.optimize import least_squares
    st0 = state(base)
    L0 = st0["L"]
    c0 = identity(base)
    use_id = "identity" in free
    clip = humanfit.CLIP_FORCE if force else humanfit.CLIP
    ctr = L0[:68].mean(0)
    obs = []
    for v in views:
        ids = [point_index(k) for k in v["points"]]
        obs.append((np.array(ids), np.array([v["points"][k] for k in v["points"]], float)))
    cams = []
    for v, (ids, uv) in zip(views, obs):
        w, h = v["size"]
        f0 = float(focal or v.get("focal") or 2.2 * max(w, h))
        z0 = f0 * np.ptp(L0[ids], axis=0).max() / max(np.ptp(uv, axis=0).max(), 1.0)
        uc = uv.mean(0)
        cams.append({"r": [0.0, 0.0, 0.0], "t": [(uc[0] - w / 2) / f0 * z0, (uc[1] - h / 2) / f0 * z0, z0], "f": f0,
                     "size": [w, h], "centre": ctr.tolist(), "yaw": float(v.get("yaw", 0.0))})
    cur, c = copy.deepcopy(base), c0.copy()
    outl = [np.asarray(v["outline"], float) if v.get("outline") else None for v in views]
    if any(o is not None for o in outl):
        rounds = max(rounds, 4)  # (the silhouette is found again each round)
    for it in range(rounds if use_id else 1):
        st = state(cur) if it else st0
        L, B = st["L"], (_lm_basis(st) if use_id else None)
        S = _skull_basis(st) if use_id else None
        C = _cheek_basis(st) if (use_id and hold_cheeks) else None
        nc = len(c) if use_id else 0
        # outlines (view["outline"]: [[u, v], ...] along the face's edge in the picture, e.g. the jaw and cheeks): each
        # point pulled onto the model's silhouette through that view's camera, along the outline's own normal (the
        # silhouette vertex nearest it, found again each round; they move with the identity like the landmarks)
        sil = [_silhouette(st, cam, o) if (o is not None and use_id) else None for cam, o in zip(cams, outl)]

        def unpack(x):
            out = []
            for k, cam in enumerate(cams):
                p = x[7 * k:7 * k + 7]
                out.append({**cam, "r": p[:3], "t": p[3:6], "f": float(focal) if focal else p[6]})
            return out, x[7 * len(cams):]

        def resid(x):
            cs, dc = unpack(x)
            Lc = L + (np.tensordot(dc, B, axes=(0, 0)) if use_id else 0.0)
            r = [(project(cam, Lc[ids]) - uv).ravel() / max(cam["size"]) * 400.0 for cam, (ids, uv) in zip(cs, obs)]
            for cam, sl in zip(cs, sil):
                if sl is not None:
                    X = sl["X"] + np.tensordot(dc, sl["B"], axes=(0, 0))
                    d = ((project(cam, X) - sl["p"]) * sl["n"]).sum(1)
                    r.append(humanfit.OUTLINE_W * d / max(cam["size"]) * 400.0)
            if use_id:
                r.append(humanfit.RIDGE * 1.5 * dc)
                r.append(0.4 * humanfit.RIDGE * (c + dc - c0))
                r.append(humanfit.HOLD_SKULL * 1000.0 * (np.tensordot(c + dc - c0, S, axes=(0, 0))).ravel())  # the skull stays
                if C is not None:  # and the cheeks' fronts (no landmark sees them)
                    r.append(humanfit.HOLD_CHEEK * 1000.0 * (np.tensordot(c + dc - c0, C, axes=(0, 0))).ravel())
            return np.concatenate(r)
        x0 = np.concatenate([np.r_[cam["r"], cam["t"], cam["f"]] for cam in cams] + [np.zeros(nc)])
        sol = least_squares(resid, x0, x_scale=np.r_[np.tile([0.1, 0.1, 0.1, 0.05, 0.05, 0.3, 500.0], len(cams)), np.ones(nc)])
        cs, dc = unpack(sol.x)
        cams = [{**cam, "r": [float(v) for v in cam["r"]], "t": [float(v) for v in cam["t"]], "f": float(cam["f"])} for cam in cs]
        if use_id:
            c = np.clip(c + dc, -max(clip, np.abs(c0).max()), max(clip, np.abs(c0).max()))
            cur = _with_identity(cur, c)
    st1 = state(cur)
    per = []
    for cam, (ids, uv), v in zip(cams, obs, views):
        e = np.linalg.norm(project(cam, st1["L"][ids]) - uv, axis=1)
        Xc = (st1["L"][ids] - ctr) @ _cam_rot(cam).T + cam["t"]
        mm = e * Xc[:, 2] / cam["f"] * 1000
        names = list(v["points"])
        worst = np.argsort(-mm)[:3]
        per.append({"points": len(ids), "rms_px": round(float(np.sqrt((e ** 2).mean())), 2), "rms_mm": round(float(np.sqrt((mm ** 2).mean())), 2),
                    "worst": [(str(names[i]), round(float(mm[i]), 1)) for i in worst], "focal": round(cam["f"], 1)})
    rep = {"views": per, "cameras": cams, "plausibility": plausibility(cur), "side_effects": side_effects(st0, st1, set(humanfit.FACE)),
           "integrity": integrity(cur, st1, st0)}
    return _guarded(base, cur, rep, force)
