"""joint.py <model> <out_model> [--sliders a,b,..]: the JOINT face solve (spike; Joe: "the more we tweak one thing, the
uglier everything gets"). One least-squares problem over every view at once:

  evidence  every view's points through its own camera (humanfit_map's calibrated detector points and the clicked
            points, each at its own sigma in mm; the cameras refitted each round), front, 3/4 and profile together;
  prior     GNM's identity components in population sigmas (Mahalanobis: the population's own covariation of jaw with
            brow, eye depth with cheek), 1 per sigma toward the mean, plus a wall past CAP sigma;
  sliders   the face sliders as RESIDUAL controls on top (faceslide: morph targets, analytic in the same points), each
            with an L2 cost of SLIDER_W per unit toward 0: they only explain what the identity space can't.

Gauss-Newton on [identity, sliders] with the cameras alternated, ROUNDS rebuilds of the head (the one mesh is near
linear in both). Writes <out_model> (spec + refs) and prints per view: points rms (mm) before / after, the prior's
cost and max |sigma|, the sliders before / after. Gates (printed): no view worse, max |component| <= CAP."""
import copy
import json
import shutil
import sys
from pathlib import Path

import numpy as np

from hifipushie import faceslide, gnmloops, humanfit, humanfit_map as hm, onemesh, store
from hifipushie import base as basemod

WS = Path("/home/joe/dev/hifipushie/workspace")
CAP = 2.5           # sigma: no identity component past this
SLIDER_W = 1.0      # cost per slider unit (1 unit ~ the population's spread: as costly as one identity sigma)
ROUNDS = 3
INNER = 5
DEFAULT_SLIDERS = ("canthal_tilt", "brow_lateral", "brow_ridge", "eye_hood", "eye_hood_lateral", "eye_platform",
                   "eye_sulcus", "eye_bag", "eye_setback", "malar_rise", "lip_upper_height", "lip_lower_height",
                   "lip_upper_roll", "lip_lower_roll", "lip_bow", "lip_tubercle", "mouth_corner", "lip_lower_width",
                   "nose_radix_width", "nose_dorsum_width", "nose_tip_width", "nose_dorsum_hump", "nostril_show")


def slider_basis(st, ev_rows, names):
    """(S, n, 3) world move per slider unit of each evidence row (rows: ("v", vid (3,), w (3,)) a GNM surface point,
    ("L", i) one of the 68 landmarks, ("E", j) an eye centre)."""
    g = basemod._gnm_data()
    c = st["head"]["carry"]
    R, s = np.asarray(c["R"], float), float(c["s"])
    F = faceslide.fields()
    out = np.zeros((len(names), len(ev_rows), 3))
    for k, nm in enumerate(names):
        dR, dL = F[nm]
        d = (dR + dL)[:gnmloops.N_RAW]  # (both sides at one value)
        dw = s * d @ R.T
        for i, row in enumerate(ev_rows):
            if row[0] == "v":
                out[k, i] = (dw[row[1]] * row[2][:, None]).sum(0)
            elif row[0] == "L":
                r = g["lm68"][row[1]]
                out[k, i] = sum(float(w) * dw[int(v)] for v, w in zip(r[0::2], r[1::2]))
            else:
                jd = faceslide.joint_delta({nm: 1.0})
                if jd is not None:
                    out[k, i] = s * jd[2 + row[1]] @ R.T
    return out


def evidence(st, views):
    """humanfit_map._evidence + each row's identity on GNM's surface (for the sliders' basis)."""
    evs = hm._evidence(st, views)
    tab = hm.table()
    gd = basemod._gnm_data()
    tpl = st["tpl"]
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    of = np.full(len(gd["template_vertex_positions"]), -1)
    of[gid[gid >= 0]] = np.flatnonzero(gid >= 0)
    for v, e in zip(views, evs):
        rows = []
        det = hm.detector_points(v) if v.get("detector", True) else None
        k = int(v["_class"]) if "_class" in v else hm.view_class(float(v.get("yaw", 0.0)))
        if det is not None and np.isfinite(tab["sd"][k]).any():
            ok = (tab["sd"][k] < hm.CUT) & (of[tab["vid"][k]] >= 0).all(1)
            rows += [("v", tab["vid"][k][i], tab["w"][k][i]) for i in np.flatnonzero(ok)]
        named = {kk: p for kk, p in (v.get("points") or {}).items()}
        lm68 = {kk: p for kk, p in named.items() if str(kk).startswith("lm") and str(kk)[2:].isdigit()}
        clicks = {kk: p for kk, p in named.items() if kk not in lm68}
        if det is None and lm68:
            clicks = {**lm68, **clicks}
        for n in clicks:
            i = humanfit.point_index(n)
            rows.append(("L", i) if i < 68 else ("E", i - 68))
        assert len(rows) == len(e["X"]), (len(rows), len(e["X"]))
        e["rows"] = rows
    return evs


def view_rms(st, views, cams):
    out = []
    ctr = st["L"][:68].mean(0)
    for cam, e in zip(cams, hm._evidence(st, views)):
        d = np.linalg.norm(humanfit.project(cam, e["X"]) - e["uv"], axis=1)
        mm = d * ((e["X"] - ctr) @ humanfit._cam_rot(cam).T + cam["t"])[:, 2] / cam["f"] * 1000
        out.append(float(np.sqrt(np.mean((mm / e["sig"]) ** 2))))  # (in sigmas: the solve's own units)
    return out


def with_x(base, c, s, names):
    b = humanfit._with_identity(copy.deepcopy(base), c)
    sl = dict(b["head"].get("sliders") or {})
    sl.update({n: round(float(v), 4) for n, v in zip(names, s)})
    b["head"]["sliders"] = sl
    return b


def solve(base, views, names, log=print):
    st0 = humanfit.state(base)
    views = hm._resolve(st0, views)
    c0 = humanfit.identity(base)
    K = len(c0)
    s0 = np.array([float(np.mean((base["head"].get("sliders") or {}).get(n, 0.0))) for n in names])
    S = len(names)
    c, s = c0.copy(), s0.copy()
    cams = [None] * len(views)
    cur = base
    for it in range(ROUNDS):
        st = humanfit.state(cur)
        evs = evidence(st, views)
        SBs = [slider_basis(st, e["rows"], names) if S else np.zeros((0, len(e["X"]), 3)) for e in evs]
        c_lin, s_lin = c.copy(), s.copy()
        for _ in range(INNER):
            n_ = K + S
            H = np.zeros((n_, n_))
            b = np.zeros(n_)
            # the identity's prior (toward the population's mean) and the wall past CAP
            H[:K, :K] += np.eye(K)
            over = np.clip(np.abs(c) - CAP, 0, None)
            wall = np.where(over > 0, 25.0, 0.0)
            H[:K, :K] += np.diag(wall)
            b[:K] += wall * np.clip(c, -CAP, CAP)
            # the sliders' L2 cost toward 0
            H[K:, K:] += np.eye(S) * SLIDER_W
            for vi, (v, e, SB) in enumerate(zip(views, evs, SBs)):
                X = e["X"] + np.tensordot(c - c_lin, e["XB"], 1) + np.tensordot(s - s_lin, SB, 1)
                if cams[vi] is None:
                    cams[vi] = v.get("_cam") or None
                if cams[vi] is None:
                    w_, h_ = v["size"]
                    f0 = hm.LENS[0] / 36.0 * w_
                    z0 = f0 * np.ptp(X, axis=0).max() / max(np.ptp(e["uv"], axis=0).max(), 1.0)
                    uc = e["uv"].mean(0)
                    cams[vi] = {"r": [0.0, 0.0, 0.0], "t": [(uc[0] - w_ / 2) / f0 * z0, (uc[1] - h_ / 2) / f0 * z0, z0],
                                "f": f0, "size": [w_, h_], "centre": st0["L"][:68].mean(0).tolist(), "yaw": float(v.get("yaw", 0.0))}
                cam = cams[vi]
                mm0 = cam["t"][2] / cam["f"] * 1000
                cam = cams[vi] = hm._fit_cam(cam, X, e["uv"], mm0 / e["sig"])
                Rc = humanfit._cam_rot(cam)
                Xc = (X - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
                z = Xc[:, 2]
                J = np.zeros((len(X), 2, 3))
                J[:, 0, 0] = J[:, 1, 1] = cam["f"] / z
                J[:, 0, 2] = -cam["f"] * Xc[:, 0] / z ** 2
                J[:, 1, 2] = -cam["f"] * Xc[:, 1] / z ** 2
                J = J @ Rc
                wt = (z / cam["f"] * 1000) / e["sig"]
                r = (e["uv"] - humanfit.project(cam, X)) * wt[:, None]
                a = np.linalg.norm(r, axis=1)
                hw = np.where(a > 2.5, np.sqrt(2.5 / np.maximum(a, 1e-9)), 1.0)
                Ac = (np.einsum("nij,knj->nik", J, e["XB"]) * (wt * hw)[:, None, None]).reshape(-1, K)
                As = (np.einsum("nij,knj->nik", J, SB) * (wt * hw)[:, None, None]).reshape(-1, S) if S else np.zeros((Ac.shape[0], 0))
                A = np.c_[Ac, As]
                y = A @ np.r_[c, s] + (r * hw[:, None]).ravel()
                H += A.T @ A
                b += A.T @ y
            x = np.linalg.solve(H, b)
            c, s = x[:K], np.clip(x[K:], -1.5, 1.5)
        cur = with_x(base, c, s, names)
        log(f"round {it}: max |c| {np.abs(c).max():.2f}, prior {float(c @ c):.1f}, sliders {np.round(s, 2).tolist()}")
    return cur, views, cams, (c0, s0), (c, s)


if __name__ == "__main__":
    name, out = sys.argv[1], sys.argv[2]
    names = list(DEFAULT_SLIDERS)
    if "--sliders" in sys.argv:
        names = sys.argv[sys.argv.index("--sliders") + 1].split(",")
    sp = store.load(name)
    base = sp["base"]
    refs = json.loads((WS / name / "human_refs.json").read_text())
    views = [dict(v) for v in refs["views"]]
    for v, cam in zip(views, refs.get("cameras") or []):
        v["_cam"] = cam
    st0 = humanfit.state(base)
    nb, rviews, cams, (c0, s0), (c1, s1) = solve(base, views, names)
    st1 = humanfit.state(nb)
    rms0 = view_rms(st0, rviews, cams)
    rms1 = view_rms(st1, rviews, cams)
    print("\nview      points rms (sigmas)  before -> after")
    for v, a, b_ in zip(rviews, rms0, rms1):
        print(f"  yaw {float(v.get('yaw', 0)):5.0f}   {a:6.2f} -> {b_:6.2f}  {'WORSE' if b_ > a + 0.05 else ''}")
    print(f"prior (sum c^2) {float(c0 @ c0):.1f} -> {float(c1 @ c1):.1f}; max |c| {np.abs(c0).max():.2f} -> {np.abs(c1).max():.2f}")
    print("sliders (before -> after; |after| = what the identity couldn't explain):")
    for n, a, b_ in sorted(zip(names, s0, s1), key=lambda t: -abs(t[2])):
        if abs(a) > 0.01 or abs(b_) > 0.01:
            print(f"  {n:20s} {a:+.2f} -> {b_:+.2f}")
    # how much the identity (the population's coupled directions) explains, and how much is left to the sliders:
    # the same solve with no residual sliders
    nb_id, _, cams_id, _, (c_id, _) = solve(base, views, [], log=lambda *a: None)
    rms_id = view_rms(humanfit.state(nb_id), rviews, cams_id)
    print("identity only (no sliders):", [round(x, 2) for x in rms_id], f"prior {float(c_id @ c_id):.1f}")
    tot0, totid, tot1 = (float(np.sum(np.square(r))) for r in (rms0, rms_id, rms1))
    if tot0 > tot1:
        print(f"share of the improvement (sum of squared view rms): identity {100 * (tot0 - totid) / (tot0 - tot1):.0f}%, "
              f"residual sliders {100 * (totid - tot1) / (tot0 - tot1):.0f}%")
    gates = {"no_view_worse": all(b_ <= a + 0.05 for a, b_ in zip(rms0, rms1)), "cap": bool(np.abs(c1).max() <= CAP + 0.05)}
    print("gates", gates)
    d = WS / out
    d.mkdir(exist_ok=True)
    spec = json.loads((WS / name / "spec.json").read_text())
    spec = spec.get("spec", spec)
    spec["base"] = nb
    (d / "spec.json").write_text(json.dumps(spec, indent=1))
    refs2 = dict(refs)
    refs2["cameras"] = cams
    (d / "human_refs.json").write_text(json.dumps(refs2, indent=1, default=float))
    print("wrote", d)
    # the whole-face identity term, as a check (face-ID cosine, photo vs clay through each view's camera; likeloop
    # found it can't see geometry across the render / photo gap: read it, don't steer by it)
    from hifipushie import likeness_pair as lp
    for i in range(len(views)):
        try:
            a = lp.matched(name, base, view=i)["face_id"]
            b_ = lp.matched(out, nb, view=i)["face_id"]
            print(f"face-id view {i}: before {a} after {b_}")
        except Exception as e:  # noqa: BLE001
            print(f"face-id view {i}: {e}")
