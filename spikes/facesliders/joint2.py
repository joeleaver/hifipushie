"""joint2.py <start model> <out model> [sex=+1] [nores]: the joint face solve over the WHOLE-MODEL controls (step 3 of Joe's
redesign: "every hand-made slider should control the model as a whole").

  variables  GNM's 120 head components (the identity: every free macro and every coupled slider is a direction in
             it; their values are READ OUT of the result, faceatlas) + the residual local morphs (RES: detail the
             identity can't express), each with an L2 cost SLIDER_W per unit toward 0;
  prior      the identity WITHIN the head's sex (faceatlas.within_sex: mean sex * delta / 2, covariance I - dd^T/4,
             the ANSUR II sex axis), Mahalanobis, + a wall past CAP sigma;
  evidence   every view's calibrated detector points / clicks through its own camera (refitted each step: joint.py);
  checklist  the likeness items ITEMS (eye opening, canthal tilt, brow-eye gap, lip heights), each as photo - clay
             render (both through the detector: likeness.compare once per round, so the detector's bias on either
             cancels) over the item's tolerance x IMPORTANCE, linearised through the same item read on the model's
             predicted MediaPipe points (humanfit_map's calibrated table): its gradient in every variable.
  no embedding term: face-ID cosine (SFace and ArcFace w600k_r50, the strongest open one we have) moved -0.16..+0.11
             across the clay / painting gap on every pair likeloop tried: it can't steer, so it is read after, not
             solved for.

Prints per view rms (sigmas), per item photo / model before -> after, the prior cost, the identity vs residual share
(the same solve without residuals), the coupled sliders and macros read out of the identity, every residual slider,
and flags any residual past BIG (a place the identity can't reach). Writes <out model> (spec + refs + report json)."""
import copy
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

import joint as J0
from hifipushie import base as basemod
from hifipushie import faceatlas, headfit, humanfit, humanfit_map as hm, likeness, onemesh, store

WS = Path("/home/joe/dev/hifipushie/workspace")
CAP = 2.5
SLIDER_W = 1.0
ROUNDS = 3
INNER = 5
BIG = 0.5           # a residual slider past this (its own units ~ 1 population spread) is flagged
RES = ("brow_lateral", "eye_hood", "eye_hood_lateral", "eye_platform", "eye_sulcus", "eye_bag", "eye_tear_trough",
       "lip_tubercle", "mouth_corner", "lip_lower_width", "tip_definition", "nose_dorsum_hump")
# the ageing ops that are local morphs too (no attribute of GNM's: not coupled), solved as residuals where the
# evidence sees them (the outline: cheek hollow, lean, cheek flat, prejowl); one-sided (their negative is no youth)
AGE = ("cheek_hollow", "face_lean", "age_cheek_flat", "age_prejowl")
ITEMS = ("eye_opening", "canthal_tilt", "brow_eye", "upper_lip", "lower_lip")
# READ ONLY (reported, not solved): the proportion items read the detector's face OVAL / chin on the photo and on the
# clay render; on Garrett's front they came out 11-15% larger on the photo at the same camera (width_temple 154 vs
# 133 mm, face height 142 vs 127) while the snapped contour fits at 1.6 mm and the desk view agrees on face height:
# the detector puts the oval differently on clay and on a photo (hair, ears, collar), so they would steer by the bias.
# The face's outline and proportions come from the outline term instead.
READ_ONLY = ("face_height", "face_index", "lower_third", "width_temple", "width_cheekbone", "width_jaw", "width_chin", "jaw_taper")
IMPORTANCE = {"eye_opening": 1.5, "canthal_tilt": 1.5, "brow_eye": 1.0, "upper_lip": 1.0, "lower_lip": 1.0,
              "face_height": 1.5, "face_index": 1.5, "lower_third": 1.0, "width_temple": 1.0, "width_cheekbone": 1.5,
              "width_jaw": 1.5, "width_chin": 1.0, "jaw_taper": 1.0}
FREE_AGE = os.environ.get("FREE_AGE", "0") == "1"
FREE_W = 0.1
OUT_SIG = 2.0       # mm per outline point (the front's snapped contour, the traced lines)
DESK_W = float(os.environ.get("DESK_W", "1.0"))   # weight (residual units) of every non-front view: Garrett's desk
TRACE_LINES = tuple(os.environ.get("TRACE_LINES", "cheek.R,cheek.L,jaw.R,jaw.L,chin,profile").split(","))
TRACES = os.environ.get("TRACES")                 # painting is a stylised secondary (0.5); the model whose traces


def view_w(v):
    return 1.0 if abs(float(v.get("yaw", 0.0))) < 20 else DESK_W


def outlines(views):
    """Per view the face outline (px) or None: the front's snapped contour, a turned view's traced jaw / profile."""
    import outl
    out = []
    for v in views:
        if abs(float(v.get("yaw", 0.0))) < 20 and not TRACES:   # (the edge snap: superseded by traces)
            fo = outl.front_outline(v)
            out.append([fo] if fo is not None else [])
        else:   # (each traced line on its own: joined, the gap between them became an outline)
            out.append(outl.traced(TRACES, v["image"], TRACE_LINES) if TRACES else [])
    return out


def outline_rows(st, cam, o, names):
    """humanfit._silhouette matched to the outline + the residual sliders' basis at those vertices."""
    from scipy.spatial import cKDTree
    sl = humanfit._silhouette(st, cam, o)
    if sl is None:
        return None
    P = np.asarray(st["tpl"]["P"], float)
    vs = cKDTree(P).query(sl["X"])[1]
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])][vs]
    fade = np.asarray(onemesh.asset()["g_fade"], float)[gid]
    rows = [("v", np.array([g, g, g]), np.array([f, 0.0, 0.0])) for g, f in zip(gid, fade)]
    sl["SB"] = J0.slider_basis(st, rows, names) if names else np.zeros((0, len(vs), 3))
    return sl


def _need():
    s = {168, 152, 13, 14}
    for iid in ITEMS:
        s |= {int(i) for i in likeness.points_of(likeness._item(iid)["measure"])}
    return np.array(sorted(s))


NEED = None


def proxy_rows(st, k):
    """The model's predicted MediaPipe points NEED in view class k: world X (n, 3), identity basis XB (K, n, 3), rows."""
    g = headfit._gnm()
    gd = basemod._gnm_data()
    tpl, c = st["tpl"], st["head"]["carry"]
    R, s = np.asarray(c["R"], float), float(c["s"])
    P = np.asarray(tpl["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    of = np.full(len(gd["template_vertex_positions"]), -1)
    of[gid[gid >= 0]] = np.flatnonzero(gid >= 0)
    IB = np.asarray(gd["vertex_identity_basis"])
    jm = g["JB"].mean(1)
    tab = hm.table()
    vid, w = tab["vid"][k][NEED], tab["w"][k][NEED]
    off = ~(of[vid] >= 0).all(1)          # (a point whose table vertices are off the one mesh's head: unread)
    vid = np.where(off[:, None], vid[~off][0][None, :], vid)
    X = (P[of[vid]] * w[..., None]).sum(1)
    X[off] = np.nan
    B = (IB[g["comps"]][:, vid].astype(float) * w[None, ..., None]).sum(2)
    B[:, off] = 0.0
    if off.any():
        print("proxy: off the head", NEED[off].tolist())
    return X, s * (B - jm[:, None, :]) @ R.T, [("v", vid[i], w[i]) for i in range(len(NEED))]


def pmeasure(uv, iid, mmpx):
    P = np.full((478, 2), np.nan)
    P[NEED] = uv
    if not np.isfinite(P[152]).all():     # (the chin point off the head: the frame's fallback, as likeness does)
        P[152] = 0.5 * (P[13] + P[14])
    return likeness.value(likeness.Side(P, None, "detector"), likeness._item(iid)["measure"], mmpx)


def proj_jac(cam, X):
    Rc = humanfit._cam_rot(cam)
    Xc = (X - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
    z = Xc[:, 2]
    J = np.zeros((len(X), 2, 3))
    J[:, 0, 0] = J[:, 1, 1] = cam["f"] / z
    J[:, 0, 2] = -cam["f"] * Xc[:, 0] / z ** 2
    J[:, 1, 2] = -cam["f"] * Xc[:, 1] / z ** 2
    return J @ Rc, z


def item_targets(refname, b, views):
    """{(item, view): photo - model} from likeness.compare (photo and clay render both through the detector), the
    skipped ones with why, and the compare's rows of ITEMS."""
    cmp = likeness.compare(refname, b)
    tg, why, rows = {}, [], {}
    for r in cmp["rows"]:
        if r["id"] not in ITEMS + READ_ONLY or r["vi"] == "-":
            continue
        rows[(r["id"], r["vi"])] = (r.get("photo"), r.get("model"))
        if r["id"] in READ_ONLY:
            continue
        if r.get("expression"):
            why.append(f"{r['id']} view {r['vi']}: {r['expression']} on the picture (the item is pose, not identity)")
        elif r["score"] < 0 or not isinstance(r.get("photo"), float) or not isinstance(r.get("model"), float):
            why.append(f"{r['id']} view {r['vi']}: {r.get('why') or 'unmeasured'}")
        else:
            tg[(r["id"], r["vi"])] = (r["photo"] - r["model"], float(r["tol"]))
    return tg, why, rows


def solve(base, views, names, refname, mu, Sinv, log=print, items=True):
    st0 = humanfit.state(base)
    views = hm._resolve(st0, views)
    c0 = humanfit.identity(base)
    K = len(c0)
    s0 = np.array([float(np.mean((base["head"].get("sliders") or {}).get(n, 0.0))) for n in names])
    S = len(names)
    c, s = c0.copy(), s0.copy()
    cams = [v.get("_cam") for v in views]
    cur = base
    info = {"skipped": [], "rows0": None, "outline_mm": []}
    OL = outlines(views)
    one = np.array([n in AGE for n in names], bool)
    # FREE_AGE (a man of ~50: leanness and hollow cheeks are soft tissue and age, which GNM has no variable for):
    # those residuals nearly free, so the identity doesn't strain for them
    sw = np.array([FREE_W if (FREE_AGE and n in ("face_lean", "cheek_hollow")) else SLIDER_W for n in names])
    for it in range(ROUNDS):
        st = humanfit.state(cur)
        evs = J0.evidence(st, views)
        SBs = [J0.slider_basis(st, e["rows"], names) if S else np.zeros((0, len(e["X"]), 3)) for e in evs]
        tg = {}
        if items:
            tg, why, rows = item_targets(refname, cur, views)
            if it == 0:
                info["skipped"], info["rows0"] = why, rows
                for w in why:
                    log("  skipped: " + w)
            log(f"round {it} item targets (photo - model): " + ", ".join(f"{k[0]}@{k[1]} {v[0]:+.2f}" for k, v in tg.items()))
        prox = {}
        for vi in {k[1] for k in tg}:
            X, XB, rows_ = proxy_rows(st, hm.view_class(float(views[vi].get("yaw", 0.0))))
            prox[vi] = (X, XB, J0.slider_basis(st, rows_, names) if S else np.zeros((0, len(X), 3)))
        sls = [(vi, sl) for vi, ol in enumerate(OL) for sl in (outline_rows(st, cams[vi], o, names) for o in ol) if sl is not None]
        m0 = {}
        c_lin, s_lin = c.copy(), s.copy()
        for inner in range(INNER):
            n_ = K + S
            H = np.zeros((n_, n_))
            b = np.zeros(n_)
            H[:K, :K] += Sinv
            b[:K] += Sinv @ mu
            over = np.clip(np.abs(c) - CAP, 0, None)
            wall = np.where(over > 0, 25.0, 0.0)
            H[:K, :K] += np.diag(wall)
            b[:K] += wall * np.clip(c, -CAP, CAP)
            H[K:, K:] += np.diag(sw)
            for vi, (v, e, SB) in enumerate(zip(views, evs, SBs)):
                X = e["X"] + np.tensordot(c - c_lin, e["XB"], 1) + np.tensordot(s - s_lin, SB, 1)
                if cams[vi] is None:
                    raise SystemExit("joint2 needs the start model's cameras (human_refs.json 'cameras')")
                cam = cams[vi]
                mm0 = cam["t"][2] / cam["f"] * 1000
                cam = cams[vi] = hm._fit_cam(cam, X, e["uv"], mm0 / e["sig"])
                J, z = proj_jac(cam, X)
                wt = (z / cam["f"] * 1000) / e["sig"] * view_w(v)
                r = (e["uv"] - humanfit.project(cam, X)) * wt[:, None]
                a = np.linalg.norm(r, axis=1)
                hw = np.where(a > 2.5, np.sqrt(2.5 / np.maximum(a, 1e-9)), 1.0)
                Ac = (np.einsum("nij,knj->nik", J, e["XB"]) * (wt * hw)[:, None, None]).reshape(-1, K)
                As = (np.einsum("nij,knj->nik", J, SB) * (wt * hw)[:, None, None]).reshape(-1, S) if S else np.zeros((Ac.shape[0], 0))
                A = np.c_[Ac, As]
                y = A @ np.r_[c, s] + (r * hw[:, None]).ravel()
                H += A.T @ A
                b += A.T @ y
            # the checklist items: photo - model (rendered), linearised through the item on the predicted points
            for (iid, vi), (delta, tol) in tg.items():
                PX, PXB, PSB = prox[vi]
                X = PX + np.tensordot(c - c_lin, PXB, 1) + np.tensordot(s - s_lin, PSB, 1)
                cam = cams[vi]
                uv = humanfit.project(cam, X)
                Jp, z = proj_jac(cam, X)
                mmpx = float(np.median(z)) / cam["f"] * 1000
                m = pmeasure(uv, iid, mmpx)
                if not np.isfinite(m):
                    continue
                if (iid, vi) not in m0:
                    m0[(iid, vi)] = m
                g = np.zeros_like(uv)
                rel = set(likeness.points_of(likeness._item(iid)["measure"])) | {168, 152, 13, 14}
                for i in [j for j in range(len(uv)) if int(NEED[j]) in rel]:
                    for d in range(2):
                        u2 = uv.copy()
                        u2[i, d] += 0.25
                        m2 = pmeasure(u2, iid, mmpx)
                        g[i, d] = (m2 - m) / 0.25 if np.isfinite(m2) else 0.0
                gx = np.nan_to_num(np.einsum("nd,ndj->nj", g, np.nan_to_num(Jp)))                       # d m / d X per point
                Gc = np.einsum("nj,knj->k", gx, PXB)
                Gs = np.einsum("nj,knj->k", gx, PSB) if S else np.zeros(0)
                w_ = IMPORTANCE[iid] / tol * view_w(views[vi])
                arow = w_ * np.r_[Gc, Gs]
                yv = arow @ np.r_[c, s] + w_ * (m0[(iid, vi)] + delta - m)
                H += np.outer(arow, arow)
                b += arow * yv
            # the outlines: each matched silhouette vertex's miss along the outline's normal (mm / OUT_SIG)
            for vi, sl in sls:
                X = sl["X"] + np.tensordot(c - c_lin, sl["B"], 1) + np.tensordot(s - s_lin, sl["SB"], 1)
                cam = cams[vi]
                Jp, z = proj_jac(cam, X)
                wt = (z / cam["f"] * 1000) / OUT_SIG * view_w(views[vi])
                r = ((humanfit.project(cam, X) - sl["p"]) * sl["n"]).sum(1) * wt
                hw = np.where(np.abs(r) > 2.5, np.sqrt(2.5 / np.maximum(np.abs(r), 1e-9)), 1.0)
                nJ = np.einsum("nd,ndj->nj", sl["n"], Jp)
                A = np.c_[np.einsum("nj,knj->nk", nJ, sl["B"]), np.einsum("nj,knj->nk", nJ, sl["SB"]) if S else np.zeros((len(X), 0))]
                A = A * (wt * hw)[:, None]
                y = A @ np.r_[c, s] - r * hw
                H += A.T @ A
                b += A.T @ y
                if inner == INNER - 1:
                    info["outline_mm"].append((it, vi, float(np.sqrt(np.mean((r / wt * z / cam["f"] * 1000) ** 2)))))
            x = np.linalg.solve(H, b)
            c, s = x[:K], np.clip(x[K:], -1.5, 1.5)
            s[one] = np.clip(s[one], 0.0, 1.5)
        cur = J0.with_x(base, c, s, names)
        log(f"round {it} outline rms mm: " + ", ".join(f"v{vi} {m:.2f}" for i_, vi, m in info["outline_mm"] if i_ == it))
        d = c - mu
        log(f"round {it}: max |c| {np.abs(c).max():.2f}, prior (within sex) {float(d @ Sinv @ d):.1f}, "
            f"residuals {dict((n, round(float(v), 2)) for n, v in zip(names, s) if abs(v) > 0.01)}")
    return cur, views, cams, (c0, s0), (c, s), info


def readouts(c, mu):
    """The identity read as the whole-model controls: every coupled slider (+1 = +1 population sd of its attribute,
    from the within-sex mean) and the macros / attributes past 0.5 sd."""
    t = faceatlas.table()
    z = {}
    for a in t["names"]:
        i = t["index"][str(a)]
        if t["r2"][i] > 0.9 and t["sd"][i] > 0:
            z[str(a)] = float(t["B"][i] @ (c - mu) / t["sd"][i])
    coupled = {k: round(z[a], 2) for k, a in faceatlas.COUPLED.items() if a in z}
    return coupled, z


if __name__ == "__main__":
    name, out = sys.argv[1], sys.argv[2]
    sex = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] not in ("nores",) else 1.0
    names = [] if "nores" in sys.argv else list(RES) + list(AGE)
    NEED = _need()
    sp = store.load(name)
    base = sp["base"]
    refs = json.loads((WS / name / "human_refs.json").read_text())
    views = [dict(v) for v in refs["views"]]
    for v, cam in zip(views, refs.get("cameras") or []):
        v["_cam"] = cam
    d_sex = np.asarray(faceatlas.table()["delta_sex"], float)
    mu = sex * d_sex / 2
    Sinv = np.linalg.inv(faceatlas.within_sex())
    # the output model (refs copied so likeness.compare finds the pictures and the traces)
    d = WS / out
    d.mkdir(exist_ok=True)
    shutil.copy(WS / name / "human_refs.json", d / "human_refs.json")
    for f in ("likeness_points.json",):
        if (WS / name / f).exists():
            shutil.copy(WS / name / f, d / f)
    st0 = humanfit.state(base)
    nb, rviews, cams, (c0, s0), (c1, s1), info = solve(base, views, names, name, mu, Sinv)
    st1 = humanfit.state(nb)
    rms0 = J0.view_rms(st0, rviews, cams)
    rms1 = J0.view_rms(st1, rviews, cams)
    _, _, rows1 = item_targets(name, nb, rviews)
    rep = {"start": name, "out": out, "sex": sex, "views": [], "items": [], "skipped": info["skipped"]}
    print("\nview      points rms (sigmas)  before -> after")
    for v, a, b_ in zip(rviews, rms0, rms1):
        print(f"  yaw {float(v.get('yaw', 0)):5.0f}   {a:6.2f} -> {b_:6.2f}  {'WORSE' if b_ > a + 0.05 else ''}")
        rep["views"].append({"yaw": float(v.get("yaw", 0)), "before": a, "after": b_})
    print("checklist items (photo | model before -> after):")
    for k in sorted(info["rows0"] or {}):
        p, m0_ = info["rows0"][k]
        m1 = rows1.get(k, (None, None))[1]
        f = lambda x: f"{x:6.2f}" if isinstance(x, float) else str(x)[:30]  # noqa: E731
        print(f"  {k[0]:13s} view {k[1]}  {f(p)} | {f(m0_)} -> {f(m1)}")
        rep["items"].append({"id": k[0], "view": k[1], "photo": p, "before": m0_, "after": m1})
    for w in info["skipped"]:
        print("  skipped:", w)
    dd0, dd1 = c0 - mu, c1 - mu
    rep["prior"] = {"before": float(dd0 @ Sinv @ dd0), "after": float(dd1 @ Sinv @ dd1),
                    "max_c_before": float(np.abs(c0).max()), "max_c_after": float(np.abs(c1).max())}
    print(f"prior (within-sex Mahalanobis) {rep['prior']['before']:.1f} -> {rep['prior']['after']:.1f}; "
          f"max |c| {np.abs(c0).max():.2f} -> {np.abs(c1).max():.2f}")
    coupled, z = readouts(c1, mu)
    rep["coupled"] = coupled
    rep["attributes_z"] = {k: round(v, 2) for k, v in z.items()}
    print("coupled sliders read out of the identity (sd from the within-sex mean):", coupled)
    print("other attributes past 0.5 sd:", {k: round(v, 2) for k, v in sorted(z.items(), key=lambda t: -abs(t[1]))
                                             if abs(v) > 0.5 and k not in faceatlas.COUPLED.values()})
    rep["residuals"] = {n: round(float(v), 3) for n, v in zip(names, s1)}
    rep["fixed_sliders"] = {k: v for k, v in (nb["head"].get("sliders") or {}).items() if k not in names}
    print("residual sliders:", rep["residuals"])
    print("fixed sliders (ageing, not solved):", rep["fixed_sliders"])
    rep["big"] = [n for n, v in zip(names, s1) if abs(v) > BIG]
    for n in rep["big"]:
        print(f"BIG RESIDUAL {n} {rep['residuals'][n]:+.2f}: a place the identity can't reach")
    if names:
        nb_id, _, cams_id, _, (c_id, _), _ = solve(base, views, [], name, mu, Sinv, log=lambda *a: None)
        rms_id = J0.view_rms(humanfit.state(nb_id), rviews, cams_id)
        tot0, totid, tot1 = (float(np.sum(np.square(r))) for r in (rms0, rms_id, rms1))
        rep["identity_only_rms"] = rms_id
        if tot0 > tot1:
            rep["share"] = {"identity": (tot0 - totid) / (tot0 - tot1), "residual": (totid - tot1) / (tot0 - tot1)}
            print(f"identity only: {[round(x, 2) for x in rms_id]}; share of the improvement: identity "
                  f"{100 * rep['share']['identity']:.0f}%, residual sliders {100 * rep['share']['residual']:.0f}%")
    rep["gates"] = {"no_view_worse": all(b_ <= a + 0.05 for a, b_ in zip(rms0, rms1)), "cap": bool(np.abs(c1).max() <= CAP + 0.05)}
    print("gates", rep["gates"])
    spec = json.loads((WS / name / "spec.json").read_text())
    spec = spec.get("spec", spec)
    spec["base"] = nb
    (d / "spec.json").write_text(json.dumps(spec, indent=1))
    refs2 = dict(refs)
    refs2["cameras"] = cams
    (d / "human_refs.json").write_text(json.dumps(refs2, indent=1, default=float))
    (d / "joint_report.json").write_text(json.dumps(rep, indent=1, default=float))
    print("wrote", d)
