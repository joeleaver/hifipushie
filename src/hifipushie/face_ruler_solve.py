"""observe, solve and read: the observations of a head against its views, the camera's columns, the most likely
identity change and the 23 gaps read off it. Part of the face ruler (face_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from .face_ruler import ERR, ERR_POST, TAU, _cam_points, _clay_crop, clay, gnm_head
from .face_ruler_blockin import EXPR_SD, EXPR_TYPES
from .face_ruler_camera import ADAPT_MIN, CAM_LOOSE, CAM_STEP
from .face_ruler_features import NU_SD
from .face_ruler_jaw import CLOTH_EDGE, RAMP, _cloth_obs, _jaw_obs, _ramp_obs
from .face_ruler_orbit import _limbus_obs, orbit_rows
from .face_ruler_outline import _colour_obs, _hair_edge_obs, _outline_obs, foreground, hair_vertices

def observe(head: dict, views: list, outline: bool = True, colour: bool = True) -> list:
    """Every observation of the pictures against the model: [{"type", "view", "o" mm, "J" (K,) mm per comp, "sig"}].
    A view with "hair": True drops the outline where hair would hide the skull (hair_vertices)."""
    obs = []
    for view in views:
        cam = view["cam"]
        im_m, ps = clay(head, cam, passes=True) if "scale" not in view else _clay_crop(head, view)
        if outline:
            mp, cv = view.get("mask"), view.get("outline")
            if mp is None and cv is None and view.get("style", "clay") != "photo":
                mp = foreground(view["img"])
            if cv is not None:      # image px of the picture's own outline (a photo's skin edge), as (x, y) points
                cv = (np.asarray(cv, float) - np.asarray(view.get("origin", (0.0, 0.0)), float)) * float(view.get("scale", 1.0))
            oo = [] if (mp is None and cv is None) else _outline_obs(
                head, view, ps["part"] >= 0, None if mp is None else np.asarray(mp, bool), view.get("trust"), cv)
            if view.get("hair"):
                hv = hair_vertices(head)
                oo = [ob for ob in oo if not hv[ob["v"]]]
            if view.get("face_only") and "face" in head:      # a photo: the neck and shoulders are a pose, not the head
                keep = head["face"] | head["ears"] if (view.get("ears") and "ears" in head) else head["face"]
                oo = [ob for ob in oo if keep[ob["v"]]]
            if view.get("outline_sig"):
                for ob in oo:
                    ob["sig"] = float(view["outline_sig"])
            obs += oo
            if view.get("hair_edge") and view["kind"] != "profile":
                he = _hair_edge_obs(head, view, ps["part"] >= 0)
                if view.get("hair"):
                    hv = hair_vertices(head)
                    he = [ob for ob in he if not hv[ob["v"]]]
                obs += he
        if colour and view.get("style", "clay") == "clay" and view.get("colour", True):
            obs += _colour_obs(head, view, im_m, view["img"])
        if view["kind"] != "front" and view.get("limbus", True) and ("eye_X" in head or head.get("kind") == "gnm"):
            view["_part"] = ps["part"]
            if "_valid" not in view:
                from scipy import ndimage as ndi
                fg = view["mask"] if view.get("mask") is not None else foreground(view["img"])
                view["_valid"] = ndi.binary_erosion(np.asarray(fg, bool), iterations=3)
            obs += _limbus_obs(head, view)
        if view.get("jaw") and view["kind"] != "profile" and "gid" in head:
            obs += _jaw_obs(head, view, ps)
        if (view.get("chin") or {}).get("ramp", RAMP) and view["kind"] != "profile" and "gid" in head and view.get("style") == "photo":
            obs += _ramp_obs(head, view)
        if (view.get("chin") or {}).get("cloth", CLOTH_EDGE) and view["kind"] != "profile" and "gid" in head and view.get("style") == "photo":
            obs += _cloth_obs(head, view, ps)
        obs += list(view.get("extra_obs") or [])
    return obs


def cam_moved(cam: dict, dx=0.0, dy=0.0, sc=0.0, roll=0.0, yaw=0.0, pitch=0.0, dist=0.0, lens: bool = False) -> dict:
    """A fitted camera moved by the ruler's camera freedoms: mm of shift (x, y), % of scale, degrees of roll, of YAW
    (the head turned about the vertical through the camera's centre point) and of PITCH (nodded about the picture's
    horizontal), and DISTANCE (dist: log units x 100, ~ % further away, the lens lengthened to match: the picture's
    scale at the head's centre stays, its PERSPECTIVE changes; solvecams)."""
    from . import humanfit
    c = dict(cam)
    if lens:      # A KNOWN LENS (readmix): the focal length is the picture's own (EXIF / lens_mm) and stays; the picture's SCALE
        #           is then the camera's DISTANCE (d = f x size / pixels) and the free distance / lens trade does not exist
        c["t"] = [c["t"][0] + dx * 1e-3, c["t"][1] + dy * 1e-3, c["t"][2] / (1 + 0.01 * sc)]
    else:
        kd = float(np.exp(0.01 * dist)) if dist else 1.0
        c["t"] = [c["t"][0] + dx * 1e-3, c["t"][1] + dy * 1e-3, c["t"][2] * kd]
        c["f"] = c["f"] * (1 + 0.01 * sc) * kd
    r = list(c.get("r", [0.0, 0.0, 0.0]))
    c["r"] = [r[0], r[1], r[2] + float(np.radians(roll))]
    if yaw:
        c["yaw"] = float(c.get("yaw", 0.0)) + float(yaw)
    if pitch:
        from scipy.spatial.transform import Rotation
        c["r"] = (Rotation.from_rotvec([float(np.radians(pitch)), 0.0, 0.0]) * Rotation.from_matrix(humanfit._rotvec(np.asarray(c["r"], float)))).as_rotvec().tolist()
    return c


def _all_types(obs, weights) -> dict:
    return {t: (weights or {}).get(t, 1.0) for t in {ob["type"] for ob in obs}}


def cam_sd_of(cam_sd, kind):
    """cam_sd per view kind: a tuple (every view the same) or {"front": .., "3q": .., "profile": ..}."""
    return tuple(cam_sd[kind]) if isinstance(cam_sd, dict) else tuple(cam_sd)


def _cam_columns(obs, views, cam_sd):
    """Nuisance columns for a camera that was FITTED (its shift, scale, roll, and with 6 numbers its yaw and pitch, are
    not known exactly): per view the observation's change per mm of shift (x, y), per 1 % of scale, per degree of roll
    / yaw / pitch. Yaw matters for depth off the midline: in a profile 1 degree moves the eye (30 mm from the midline)
    0.5 mm along the picture while the profile line itself stays."""
    cols, pri = [], []
    for view in views:
        k = view["kind"]
        sc = float(view.get("scale", 1.0))
        c = (np.asarray(view["cam"]["size"], float) / 2 - np.asarray(view.get("origin", (0.0, 0.0)), float)) * sc
        mm = float(view["cam"]["t"][2]) / view["cam"]["f"] * 1000.0 / sc
        sds = cam_sd_of(cam_sd, k)
        iv = [i for i, ob in enumerate(obs) if ob["view"] == k and "X" in ob]
        rot = {}
        if len(sds) > 4 and iv:       # the rotations: finite differences of each observation's own 3D point
            X = np.array([obs[i]["X"] for i in iv], float)
            p0 = _cam_points(view["cam"], X)[1]
            for j, key in ((4, "yaw"), (5, "pitch"), (6, "dist"))[:len(sds) - 4]:
                d = (_cam_points(cam_moved(view["cam"], **{key: 0.5}, lens=bool(view.get("lens_known"))), X)[1] - p0) / 0.5 * sc * mm     # mm per degree / per % of distance
                rot[j] = dict(zip(iv, d))
            if view.get("lens_known"):      # a known lens: 1 % of scale = the camera 1 % nearer (its perspective with it), per read
                d = (_cam_points(cam_moved(view["cam"], sc=0.5, lens=True), X)[1] - p0) / 0.5 * sc * mm
                rot[2] = dict(zip(iv, d))
        for j, (nm, sd) in enumerate(zip(("dx", "dy", "scale", "roll", "yaw", "pitch", "dist"), sds)):
            col = np.zeros(len(obs))
            for i, ob in enumerate(obs):
                if ob["view"] != k:
                    continue
                if j >= 4 or (j == 2 and i in rot.get(2, ())):
                    if i not in rot.get(j, ()):
                        continue
                    d = rot[j][i]
                    col[i] = d @ np.asarray(ob["n"]) if "n" in ob else (d[0] if ob["name"].endswith(".x") else d[1])
                    continue
                p = (np.asarray(ob["p"], float) - c) * mm                # mm from the picture's centre
                d = {0: np.array([1.0, 0.0]), 1: np.array([0.0, 1.0]), 2: 0.01 * p,
                     3: np.radians(1.0) * np.array([-p[1], p[0]])}[j]
                if "n" in ob:
                    col[i] = d @ np.asarray(ob["n"])
                else:
                    col[i] = d[0] if ob["name"].endswith(".x") else d[1]
            cols.append(col)
            pri.append(sd)
    return np.array(cols).T, np.array(pri)


def solve(obs: list, head: dict, tau: float = TAU, span: bool = False, cam_sd=None, views=None, huber: float = 2.5,
          weights: dict | None = None, done=None, cam_done=None, prior_off=None, adapt: bool = False,
          cmax: float | None = None, relax0: float = 1.0, expr_mode: str = "view", expr_sd: float | None = None,
          expr_prior: dict | None = None) -> dict:
    """The gaps of the 23 measures from the observations. Default: the most likely identity change dc (prior N(0,
    tau^2) per comp) and the measures read off it, with posterior sd. span=True: least squares over the 23 `mm:` moves
    alone. cam_sd = (shift mm, shift mm, scale %, roll deg): the camera was fitted, so much of each is unknown."""
    from . import gnm_mm
    names = list(gnm_mm.NAMES)
    Jm = head["Jm"]
    o = np.array([ob["o"] for ob in obs])
    K = Jm.shape[1]
    kx = max(len(ob["J"]) for ob in obs)
    Jall = np.zeros((len(obs), kx))
    for i, ob in enumerate(obs):                # (a hold row has the identity's columns only)
        Jall[i, :len(ob["J"])] = ob["J"]
    J, Xc_ = Jall[:, :K], Jall[:, K:]          # identity | the EXPRESSION each read's own picture shows (model_head expr)
    sig = np.array([ob["sig"] * (weights or {}).get(ob["type"], 1.0) for ob in obs])
    firm = np.array([ob["type"] == "hold" for ob in obs])
    if span:
        D = np.array([gnm_mm.direction(n) for n in names]).T          # (170, 23)
        Jx, pri = J @ D, np.array([10.0 * s for s in gnm_mm.sd().values()])
    else:
        Jx, pri = J, np.full(K, tau)
    nc = 0
    if cam_sd is not None:
        C, cp = _cam_columns(obs, views, cam_sd)
        Jx, pri, nc = np.c_[Jx, C], np.r_[pri, cp], C.shape[1]
        if cam_done is not None:       # the cameras were already moved this much: the prior is on the whole of it
            cam_m0 = -np.asarray(cam_done, float).ravel()
    m0 = np.zeros(len(pri))
    if nc and cam_done is not None:
        m0[-nc:] = cam_m0
    if done is not None and not span:      # a later round: the prior is on the WHOLE change (done + this step)
        m0[:K] = -np.asarray(done, float)
    if prior_off is not None and not span:  # the model already stands this far from the prior's centre (its start
        m0[:K] -= np.asarray(prior_off, float)   # class's mean): the prior is on the WHOLE identity, across calls
    nn = 0                                 # NUISANCE columns an observation brings itself ({"nu": {name: value}}:
    keys = sorted({k for ob in obs for k in (ob.get("nu") or {})})   # a shading read's albedo / exposure field per view)
    if keys:
        Cn = np.array([[(ob.get("nu") or {}).get(k, 0.0) for k in keys] for ob in obs], float)
        Jx, pri, m0, nn = np.c_[Jx, Cn], np.r_[pri, np.full(len(keys), NU_SD)], np.r_[m0, np.zeros(len(keys))], len(keys)
    xcols = []                             # EXPRESSION as a nuisance: per picture ("view") or one for the set ("shared"),
    if Xc_.shape[1] and not span:          # a strong prior at neutral; never applied to the head, so each round's estimate
        pics = sorted({ob.get("of", ob["view"]) for ob in obs if ob["type"] in EXPR_TYPES}) if expr_mode == "view" else ["all"]
        xn = (head.get("expr") or {}).get("names") or [f"x{j}" for j in range(Xc_.shape[1])]     # is of the whole expression
        cols = []
        for pc in pics:
            m_ = np.array([(expr_mode != "view" or ob.get("of", ob["view"]) == pc) and ob["type"] in EXPR_TYPES for ob in obs], float)
            for j in range(Xc_.shape[1]):
                cols.append(Xc_[:, j] * m_)
                xcols.append((pc, xn[j]))
        Cx = np.array(cols).T
        # (readmix) expr_prior {picture: {class: (mean, sd)}}: each picture's expression under its OWN prior (the detector's
        # blendshape scores, calibrated: expression_evidence) instead of N(0, EXPR_SD) for all: a neutral picture's is pinned
        xm = np.array([((expr_prior or {}).get(pc) or {}).get(nm, (0.0, EXPR_SD if expr_sd is None else float(expr_sd)))[0] for pc, nm in xcols])
        xs = np.array([((expr_prior or {}).get(pc) or {}).get(nm, (0.0, EXPR_SD if expr_sd is None else float(expr_sd)))[1] for pc, nm in xcols])
        Jx, pri, m0 = np.c_[Jx, Cx], np.r_[pri, xs], np.r_[m0, xm]
        nn += len(xcols)
    if cmax and not span:
        # NOTHING FORCED, as a BOUND (solvecams, 2026-10-13): no identity component may end past cmax sd. Until now a
        # component past it turned EVERY read's sigma up until none was (x1.2 .. x18, carried from call to call): on a
        # known head with its TRUE cameras one component at 3.11 instead of 3.00 (pushed there by the size hold and the
        # neck prior's rows, which the factor never touched) cost x15.3 and the head ended worse than it started. Now
        # the components that would pass the bound are HELD AT it and the rest solved again (an active set: the most
        # likely head inside the box); no read is down-weighted, nothing is carried. out["bound"] names them.
        c_at = np.asarray(head["c"], float)   # (the head as it stands in this round)
        kb = dict(tau=tau, cam_sd=cam_sd, views=views, huber=huber, weights=weights, done=done, cam_done=cam_done,
                  prior_off=prior_off, adapt=adapt, expr_mode=expr_mode, expr_sd=expr_sd, expr_prior=expr_prior)
        rows_b, held_b = [], {}
        t_ = solve(obs, head, **kb)
        for _ in range(8):
            c_new = c_at + t_["dc"]
            bad = [int(i) for i in np.where(np.abs(c_new) > cmax + 1e-6)[0] if int(i) not in held_b]
            if not bad:
                break
            for i in bad:
                held_b[i] = float(np.sign(c_new[i]) * cmax)
                e = np.zeros(K)
                e[i] = 1.0
                rows_b.append({"type": "hold", "view": "prior", "name": f"bound_c{i}", "o": float(held_b[i] - c_at[i]), "J": e, "sig": 1e-3})
            t_ = solve(list(obs) + rows_b, head, **kb)
        t_["relax"] = 1.0
        t_["bound"] = sorted(held_b)
        t_["bound_rows"] = rows_b
        return t_
    w = 1.0 / sig ** 2
    sig0, grp, scale = sig.copy(), {}, {}
    if adapt:
        for i, ob in enumerate(obs):
            if ob["type"] != "hold":
                grp.setdefault((ob["type"], ob["view"]), []).append(i)
    for it in range(6 if adapt else 3):
        A = (Jx * w[:, None]).T @ Jx + np.diag(1.0 / pri ** 2)
        Ai = np.linalg.inv(A)
        th = Ai @ (Jx.T @ (w * o) + m0 / pri ** 2)
        if adapt and it in (2, 3, 4):     # a group the model cannot explain to its sigma is NOISIER than assumed (a
            for key, ii in grp.items():   # painting's outline, a detector on brush strokes): its sigma = its own scatter
                if len(ii) >= ADAPT_MIN:
                    s_ = 1.4826 * float(np.median(np.abs((o - Jx @ th)[ii])))
                    scale[key] = max(1.0, s_ / float(np.median(sig0[ii])))
                    sig[ii] = sig0[ii] * scale[key]
        r = (o - Jx @ th) / sig
        w = 1.0 / sig ** 2 * np.where(firm, 1.0, np.minimum(1.0, huber / np.maximum(np.abs(r), 1e-9)))
    n1 = len(th) - nc - nn
    if span:
        g, cov = th[:n1], Ai[:n1, :n1]
        dc = D @ g
    else:
        dc = th[:n1]
        g, cov = Jm @ dc, Jm @ Ai[:n1, :n1] @ Jm.T
        if done is not None:          # the gap of the WHOLE change (earlier rounds + this one)
            g = Jm @ (np.asarray(done, float) + dc)
    err = np.sqrt(np.maximum(np.diag(cov), 0))
    err = np.hypot(ERR_POST * err, [ERR[n] for n in names])
    sd = gnm_mm.sd()
    rows = []
    for i, n in enumerate(names):
        prior = np.sqrt(2.0) * tau * sd[n] if not span else np.inf
        rows.append({"measure": n, "current": head["measures"][n], "gap": float(g[i]), "sd": float(g[i] / sd[n]),
                     "err": float(err[i]), "read": float(max(0.0, 1 - (err[i] / (tau * sd[n])) ** 2)) if not span else 1.0,
                     "view": gnm_mm.SEE[n][0], "see": gnm_mm.SEE[n][1]})
    rows.sort(key=lambda r: -abs(r["sd"]))
    full = ERR_POST ** 2 * cov + np.diag([ERR[n] ** 2 for n in names])
    return {"dc": dc, "gaps": rows, "n": len(obs), "rms": float(np.sqrt(np.mean(r ** 2))), "sig_scale": scale, "relax": 1.0,
            "resid": ((o - Jx @ th) / sig0).tolist(),      # what is left of each read after the solve, in its own sigmas
            "cam": th[n1:n1 + nc].tolist() if nc else None, "cov": full, "names": names,
            "cam_post": np.sqrt(np.maximum(np.diag(Ai)[n1:n1 + nc], 0)).tolist() if nc else None,
            # the linear-Gaussian system as solved (solve_report: what each measure's posterior owes to which reads)
            "post": {"Jx": Jx, "w": w, "pri": pri, "n1": n1, "tau": tau, "span": span},
            "expr": {pc: {} for pc, _ in xcols} and _expr_out(xcols, th[len(th) - len(xcols):], np.sqrt(np.maximum(np.diag(Ai)[len(th) - len(xcols):], 0)))}


def _expr_out(xcols, val, sd) -> dict:
    out = {}
    for (pc, nm), v, s_ in zip(xcols, val, sd):
        out.setdefault(pc, {})[nm] = (float(v), float(s_))
    return out


def read(head: dict, views: list, rounds: int = 3, **kw) -> dict:
    """The ruler: the pictures against the model, `rounds` Gauss-Newton rounds (the outline's maker and normal are
    re-taken on the moved head: one round is off by the step's curvature when the gap is large). Gaps are the measures
    of the fitted head minus the model's."""
    from . import gnm_mm
    if kw.get("span"):
        rounds = 1
    make = head.get("rebuild") or (lambda c: gnm_head(c))
    done = np.zeros(len(head["c"]) if "c" in head else head["B"].shape[0])
    cur = head
    relax0 = float(kw.pop("relax0", 1.0))      # the down-weighting the block-in already stands at (cmax)
    hold = kw.pop("hold", None)                # None | "auto" (every measure no read looks at) | [measure names]
    held0 = list(kw.pop("held0", None) or [])  # measures held in the block-in's earlier calls: they stay held
    tie = kw.pop("tie", None)                  # None | {"names", "given", "sig"}: solve_report.tie_rows every round
    poff = kw.get("prior_off")
    held = []
    views = [dict(v) for v in views]
    free = kw.get("cam_sd") is not None
    ncam = len(cam_sd_of(kw["cam_sd"], views[0]["kind"])) if free else 4
    cam_done = np.zeros((len(views), ncam))
    cam0 = kw.pop("cam_done0", None)     # the cameras' move in EARLIER calls (per view): the prior is on the whole of it
    cam_first = int(kw.pop("cam_first", 0))
    cam_reset = bool(kw.pop("cam_reset", True))     # "refit": the cameras-first rounds' result is the NEW start (cameras of another head)
    if not free:
        cam_first = 0
    prior_cam = cam0 is not None and free and not (cam_first and cam_reset)
    if prior_cam:
        a0 = np.zeros_like(cam_done)
        c0_ = np.atleast_2d(np.asarray(cam0, float))
        a0[:min(len(a0), len(c0_)), :min(ncam, c0_.shape[1])] = c0_[:len(a0), :ncam]
        cam_done = a0
    cam_start0 = cam_done.copy()         # (the call's whole camera step counts its cameras-first rounds too, unless they are a new start)
    for _ in range(cam_first):
        # CAMERAS FIRST (solvecams: on EVERY call now): the head held (tau tiny), the cameras laid on its outline and
        # anchors under their prior, before identity may move: a wrong front pitch is otherwise paid in jaw width (1.4 mm
        # a degree). cam_reset ("refit"): each camera CAM_LOOSE x its freedom and the result is the new start. DISTANCE
        # is HELD in these rounds, with the dense read too: on a held head a shape misfit is explained as perspective
        # (measured, cameras only on the class mean with dense: a wide-jawed head's front camera goes to -54 % from
        # any start, a head near the mean's to +22 %): distance is solved WITH identity or not at all
        for v in views:
            if v.get("extra"):
                v["extra_obs"] = v["extra"](cur, v)
        obs = observe(cur, views)
        if not obs:
            break
        k_ = CAM_LOOSE if cam_reset else 1.0
        loose = {kk: tuple((k_ * x if j < 6 else 1e-3) for j, x in enumerate(cam_sd_of(kw["cam_sd"], kk))) for kk in ("front", "3q", "profile")}
        o_ = solve(obs, cur, views=views, **{**kw, "tau": 0.02, "cam_sd": loose, "cmax": None,
                                             "cam_done": None if (cam_reset or not prior_cam) else cam_done})
        th = np.asarray(o_["cam"], float).reshape(len(views), ncam)
        lim = (2.0 if cam_reset else 1.0) * np.asarray(CAM_STEP[:ncam], float)      # a round's STEP is limited (the columns are a linearisation); the whole move is not
        th = np.clip(th, -lim, lim)
        for v, t_ in zip(views, th):
            v["cam"] = cam_moved(v["cam"], *t_, lens=bool(v.get("lens_known")))
        if cam_reset:
            cam0 = None              # refitted cameras are the new start
        else:
            cam_done = cam_done + th
            prior_cam = True
    cam_start = cam_done.copy() if (cam_reset or not cam_first) else cam_start0
    relax = 1.0
    for k in range(rounds):
        for v in views:              # per-view extra observations follow the moved head and camera
            if v.get("extra"):
                v["extra_obs"] = v["extra"](cur, v)
        obs = observe(cur, views)
        if not obs:
            raise ValueError("face_ruler: nothing could be read (no outline, no feature) in these pictures")
        skw = dict(done=done if k else None, cam_done=cam_done if (free and (k or prior_cam)) else None, relax0=max(relax0, relax), **kw)
        skw.pop("cam_reset", None)
        out = solve(obs, cur, views=views, **skw)
        if hold and "gid" in cur and not kw.get("span"):
            # HOLD what no read looks at (solve_report.direct) at the START head's value: the prior's correlations may
            # not carry an unread measure along with the read ones (garrett_a1's eye depth: 7.8 mm from nothing)
            from . import solve_report as sr
            whole = done + (np.asarray(poff, float) if poff is not None else 0.0)
            if hold == "auto":      # STICKY: a measure whose read hovers at the threshold was held in one round and let
                drc = sr.direct(out["post"], obs, views, cur, groups=False)       # go in the next, and drifted
                now = [h["name"][5:] for h in sr.hold_rows(drc["read"], done=whole)]
                held0 = held0 + [n for n in now if n not in held0]
                hrows = sr.hold_rows(None, done=whole, names=held0)
            else:
                hrows = sr.hold_rows(None, done=whole, names=list(hold))
            held = [h["name"][5:] for h in hrows]
            if hrows:
                obs = obs + hrows
                out = solve(obs, cur, views=views, **skw)
        if tie and "gid" in cur and not kw.get("span"):
            # TIE what no picture reads to its expectation given what they do read (solve_report.tie_rows; chinread)
            from . import solve_report as sr
            whole = done + (np.asarray(poff, float) if poff is not None else 0.0)
            tk = {k_: v_ for k_, v_ in tie.items() if k_ not in ("size", "size_target", "neck", "neck_sig")}
            obs = obs + (sr.tie_rows(done=whole, **tk) if tk.get("names") else []) + ([sr.size_row(done=whole, target=float(tie.get("size_target") or 0.0))] if tie.get("size") else [])
            if tie.get("neck"):      # THE NECK's girth at its anthropometric target (solve_report.neck_row; nothing reads it)
                obs = obs + [sr.neck_row(np.asarray(head["c"], float) + done, float(tie["neck"]), float(tie.get("neck_sig") or sr.NECK_SIG))]
            out = solve(obs, cur, views=views, **skw)
        relax = float(out.get("relax", 1.0))
        obs = obs + list(out.get("bound_rows") or [])
        done = done + out["dc"]
        if free:                     # the fitted cameras are refined too: the next round reads through the moved ones
            th = np.asarray(out["cam"], float).reshape(len(views), ncam)
            # (solvecams, 2026-10-13) NO CLIP on the whole move: it was clipped at 2.5 sd of the start (a "trust" front
            # camera 8 deg off in pitch could be corrected by 1.67: 1.4 mm of jaw width per degree left in). The prior
            # (cam_sd, on the whole move since the block-in's start) is what holds a camera now; only a round's STEP is
            # limited, the columns being a linearisation
            lim = np.asarray(CAM_STEP[:ncam], float)
            th = np.clip(th, -lim, lim)
            cam_done += th
            for v, t_ in zip(views, th):
                v["cam"] = cam_moved(v["cam"], *t_, lens=bool(v.get("lens_known")))
        if k + 1 < rounds:
            cur = make(head["c"] + done)
    out["cam_done"], out["views"] = cam_done.tolist(), views
    out["cam_step"], out["relax"], out["held"] = (cam_done - cam_start).tolist(), relax, held
    if free and out.get("cam_post") is not None:
        out["cam_post"] = np.asarray(out["cam_post"], float).reshape(len(views), ncam).tolist()
    if rounds > 1 and head.get("kind") == "gnm":
        fin = gnm_head(head["c"] + done)
        sd = gnm_mm.sd()
        for r in out["gaps"]:
            r["gap"] = fin["measures"][r["measure"]] - head["measures"][r["measure"]]
            r["current"], r["sd"] = head["measures"][r["measure"]], r["gap"] / sd[r["measure"]]
        out["gaps"].sort(key=lambda r: -abs(r["sd"]))
    for r in out["gaps"]:
        r["current"] = head["measures"][r["measure"]]
    out["dc"], out["obs"] = done, obs
    out["orbit"] = orbit_rows(out, head)
    return out
