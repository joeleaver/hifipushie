"""fitM.py <src model> <out model>: faces6 STAGE M, the MACRO fit (Joe: "learn how to better approach the macros before
we do fine detail work in GNM"; the coordinator: whole-face proportions and character first, judged on their own).

The head starts from its BODY's head with GNM identity 0 (the source's local layers stripped: sliders, warp, fold,
pose, expression, lip sliders); the identity is c = B z with
  BASIS=macros  humanmacro's 37 directions (free mode, comps 0-119) + GNM's own sex direction (the semantic sampler's
                male - female class means, unit length): interpretable, later stylisable (38 dof);
  BASIS=comps   GNM comps 0..NCOARSE-1 (default 40: 98.7% of the variance): the check;
prior c ~ N(0, I) (so z's prior is B^T B). Evidence (fit5.system's terms, chosen by TERMS_M): every view's MediaPipe
face OVAL and GROSS landmarks (eye corners, brow line, nasion, nose tip / subnasale, mouth corners / midline), the
named clicks, the profile CONTOUR at PROF_SIG_M (coarse); no lips / border / contact / feature points. Plus the soft
attribute row sex_gnm = SEX_T +- SEX_SD (gates.sex_read; off with SEX_SD=0).
Body macros: env BODY = json of MakeHuman params set before the fit (age / sex / weight ...); GRID = json
{param: [values]} runs the fit per grid point and keeps the one with the lowest data chi2 + the prior's
(GRID_PRIOR = json {param: [centre, sd]}).
Reports per round |c|, z, per-term chi2 / rows; writes <out> (identity on the stripped base) + fitM.json."""
import copy
import itertools
import json
import os
import sys

import numpy as np

import fit5
import gates
from hifipushie import humanfit, humanfit_map as hm, humanmacro as hmac, store

NC = fit5.NC
BASIS = os.environ.get("BASIS", "macros")
NCOARSE = int(os.environ.get("NCOARSE", "40"))
ROUNDS = int(os.environ.get("ROUNDS_M", "4"))
SEX_T = float(os.environ.get("SEX_T", "-1.0"))
SEX_SD = float(os.environ.get("SEX_SD", "0.5"))
TERMS_M = os.environ.get("TERMS_M", "oval,gross,clicks,profile_contour").split(",")
Z_RIDGE = float(os.environ.get("Z_RIDGE", "1.0"))   # + z ~ N(0, 1/ridge) on the macro weights: the 37 directions are
# correlated, without it the solve cancels big opposite macros (face_length +10 sd with |c| 4.8): uninterpretable
EXTRA = os.environ.get("EXTRA_DIRS")
STEP_MAX = float(os.environ.get("STEP_MAX", "1.0"))   # |dc| per round after the first (0: off)
PHOTO_SIG = float(os.environ.get("PHOTO_SIG", "0"))   # > 0: the macro-scale photometric term (photom.py), log units
PHOTO_VIEWS = [int(v) for v in os.environ.get("PHOTO_VIEWS", "0,1").split(",")]
ETH = os.environ.get("ETH", "1") == "1"
ETHSTATS = os.environ.get("ETHSTATS", "/mnt/data/hifipushie/faces6/ethstats.npz")
RIDGE_OVERRIDE = {}   # npz of extra named directions (170, k) + names: the vocabulary's additions


def basis():
    if BASIS == "comps":
        B = np.zeros((NC, NCOARSE))
        B[np.arange(NCOARSE), np.arange(NCOARSE)] = 1.0
        return B, [f"head_{i:03d}" for i in range(NCOARSE)]
    cols, names = [], []
    for n in hmac.NAMES:
        u = np.zeros(NC)
        u[:hmac.K] = hmac.direction(n)
        cols.append(u)
        names.append(n)
    d = gates.CV["m_m"] - gates.CV["m_f"]
    cols.append(d / np.linalg.norm(d))
    names.append("sex_gnm_dir")
    if ETH:   # GNM's sampler's ethnicity contrasts (ethstats.npz: an orthonormal basis of the 4 groups' mean offsets,
        # gender pooled), continuous weights with the sampler's own population sd as the prior: no label asserted
        e = np.load(ETHSTATS)
        for k in range(e["dirs"].shape[1]):
            cols.append(e["dirs"][:, k])
            names.append(f"eth_dir{k}")
            RIDGE_OVERRIDE[len(cols) - 1] = 1.0 / float(e["sd"][k]) ** 2
    if EXTRA:
        z = np.load(EXTRA)
        for k, nm in enumerate(z["names"]):
            cols.append(z["dirs"][:, k])
            names.append(str(nm))
    return np.stack(cols, 1), names


def stripped(spec, body=None):
    sp = copy.deepcopy(spec)
    h = sp["base"]["head"]
    for k in ("sliders", "warp", "fold", "pose", "expression", "lip_seal", "mouth_gap", "seed", "spread", "features"):
        h.pop(k, None)
    h["lip_seal"] = 1   # (a closed neutral for the clay reads; contact is not evidence here)
    if body:
        sp["base"]["body"].update(body)
    return sp


def fit(spec, refs, body=None, log=print):
    sp = stripped(spec, body)
    views = [dict(v) for v in refs["views"]]
    cams = [dict(c) for c in refs["cameras"]]
    nv = len(views)
    B, names = basis()
    z = np.zeros(B.shape[1])
    a_sex = 2 * (gates.CV["m_m"] - gates.CV["m_f"]) / float((gates.CV["m_m"] - gates.CV["m_f"]) @ (gates.CV["m_m"] - gates.CV["m_f"]))
    s0 = float(a_sex @ (0.5 * (gates.CV["m_m"] + gates.CV["m_f"])))
    rviews = None
    for rnd in range(ROUNDS):
        c = B @ z
        st = humanfit.state(humanfit._with_identity(sp["base"], c))
        if rviews is None:
            rviews = hm._resolve(st, views)
        x = np.r_[c, np.zeros(fit5.NE * nv)]
        fit5.TERMS = {}
        fit5.system(st, rviews, cams, x, x, None, nv)
        H = np.zeros((NC, NC))
        b = np.zeros(NC)
        chi = {}
        for t, (Ht, bt, yy, nr) in fit5.TERMS.items():
            if t.split(":")[1] not in TERMS_M:
                continue
            H += Ht[:NC, :NC]
            b += bt[:NC]
            chi[t] = (round(float(x @ Ht @ x - 2 * bt @ x + yy), 1), int(nr))
        rid = np.full(B.shape[1], Z_RIDGE if BASIS != "comps" else 0.0)
        for j, v in RIDGE_OVERRIDE.items():
            rid[j] = v
        Hz = B.T @ H @ B + B.T @ B + np.diag(rid)
        bz = B.T @ b
        if SEX_SD > 0:
            w = 1.0 / SEX_SD
            g_ = B.T @ a_sex
            Hz += w * w * np.outer(g_, g_)
            bz += w * w * g_ * (SEX_T + s0)
        if PHOTO_SIG > 0 and rnd > 0:   # (round 0: the landmark solve from the mean; shading from round 1, damped)
            import photom
            from hifipushie import likeness
            mesh = likeness.model_mesh_from_state(st)
            if "_pv" not in locals():
                _pv = []
                for vi in PHOTO_VIEWS:
                    img = __import__("PIL.Image", fromlist=["Image"]).open(views[vi]["image"]).convert("RGB")
                    _pv.append(photom.View(views[vi], cams[vi], mesh, likeness.detect([img])[0]))
            for pv, vi in zip(_pv, PHOTO_VIEWS):
                pv.cam = cams[vi]
                pv.fit_light(mesh)
            VB = photom.vertex_basis(st)
            r0, J, keep = photom.jacobian(_pv, mesh, VB, [B[:, j] for j in range(B.shape[1])])
            w2 = 1.0 / PHOTO_SIG ** 2
            Hz += w2 * J.T @ J
            bz += w2 * J.T @ (J @ z - r0)
            chi["photometric"] = (round(float(w2 * r0 @ r0), 1), int(len(r0)))
            chi["photometric_rms"] = (round(float(np.sqrt(np.mean(r0 ** 2))), 4), 0)
            log(json.dumps({"photo_light": [[round(pv.light[0], 3), np.round(pv.light[1], 3).tolist(), round(pv.light[3], 2)] for pv in _pv]}))
        z_new = np.linalg.solve(Hz, bz)
        step = float(np.linalg.norm(B @ (z_new - z)))
        if STEP_MAX > 0 and step > STEP_MAX and rnd > 0:   # a trust region on the identity (the photometric term
            # ran away undamped: |c| 3.7 -> 11 -> 19 -> 21); round 0 from the mean is the landmark solve's own
            z_new = z + (z_new - z) * STEP_MAX / step
        z = z_new
        cz = B @ z
        dof = float(B.shape[1] - np.trace(np.linalg.solve(Hz, B.T @ B)))
        log(json.dumps({"round": rnd, "c_norm": round(float(np.linalg.norm(cz)), 2), "sex_gnm": round(gates.sex_read(cz), 2),
                        "dof": round(dof, 1), "chi2/rows (at the round's start)": chi,
                        "chi2_total": round(sum(v[0] for v in chi.values()), 1)}))
    c = B @ z
    st = humanfit.state(humanfit._with_identity(sp["base"], c))
    x = np.r_[c, np.zeros(fit5.NE * nv)]
    fit5.TERMS = {}
    fit5.system(st, rviews, cams, x, x, None, nv)
    chi = {t: (round(float(x @ v[0] @ x - 2 * v[1] @ x + v[2]), 1), int(v[3])) for t, v in fit5.TERMS.items()
           if t.split(":")[1] in TERMS_M}
    data = sum(v[0] for v in chi.values())
    prior = float(c @ c)
    log(json.dumps({"final": True, "chi2": chi, "data": round(data, 1), "prior |c|^2": round(prior, 1)}))
    return {"z": dict(zip(names, np.round(z, 3).tolist())), "c": c, "spec": humanfit_spec(sp, c), "cams": cams,
            "data": data, "prior": prior, "chi": chi, "sex_gnm": gates.sex_read(c), "c_norm": float(np.linalg.norm(c))}


def humanfit_spec(sp, c):
    out = copy.deepcopy(sp)
    out["base"] = humanfit._with_identity(sp["base"], c)
    return out


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    spec = store.load(src)
    refs = json.loads((store.HOME / src / "human_refs.json").read_text())
    body = json.loads(os.environ["BODY"]) if os.environ.get("BODY") else None
    grid = json.loads(os.environ["GRID"]) if os.environ.get("GRID") else None
    gprior = json.loads(os.environ.get("GRID_PRIOR", "{}"))
    runs = []
    if grid:
        keys = list(grid)
        for vals in itertools.product(*[grid[k] for k in keys]):
            bd = {**(body or {}), **dict(zip(keys, vals))}
            print("GRID", json.dumps(bd), flush=True)
            r = fit(spec, refs, bd)
            pen = sum(((bd[k] - c_) / s_) ** 2 for k, (c_, s_) in gprior.items() if k in bd)
            r["body"], r["score"] = bd, r["data"] + r["prior"] + pen
            print("SCORE", json.dumps({"body": bd, "data": round(r["data"], 1), "prior": round(r["prior"], 1),
                                       "body_prior": round(pen, 2), "score": round(r["score"], 1)}), flush=True)
            runs.append(r)
        best = min(runs, key=lambda r: r["score"])
    else:
        best = fit(spec, refs, body)
        best["body"] = body
    d = store.HOME / dst
    d.mkdir(exist_ok=True)
    (d / "spec.json").write_text(json.dumps(best["spec"], indent=1))
    r2 = dict(refs)
    r2["cameras"] = best["cams"]
    (d / "human_refs.json").write_text(json.dumps(r2, indent=1, default=float))
    rep = {k: best[k] for k in ("z", "data", "prior", "chi", "sex_gnm", "c_norm", "body")}
    rd = hmac.read(best["c"][:hmac.K])
    rep["macros_read"] = {k: round(v, 2) for k, v in sorted(rd.items(), key=lambda kv: -abs(kv[1]))}
    print("READ", json.dumps(dict(list(rep["macros_read"].items())[:14])))
    if os.path.exists(ETHSTATS):
        e = np.load(ETHSTATS)
        p = e["dirs"].T @ (best["c"] - e["mu"])
        Q = e["dirs"].T @ (e["eth"] - e["mu"]).T          # (3, 4)
        A = np.r_[Q, 10 * np.ones((1, 4))]
        w = np.linalg.lstsq(A, np.r_[p, 10.0], rcond=None)[0]
        rep["ethnicity_mix"] = {str(n): round(float(x), 2) for n, x in zip(e["names"], w)}
        rep["ethnicity_coords_sd"] = (p / e["sd"]).round(2).tolist()
        print("ETH", json.dumps({"mix (barycentric over the sampler's group means)": rep["ethnicity_mix"],
                                 "coords in pop sd": rep["ethnicity_coords_sd"]}))
    rep.update(basis=BASIS, terms=TERMS_M, sex=[SEX_T, SEX_SD], grid=[{"body": r["body"], "score": r["score"]} for r in runs])
    (d / "fitM.json").write_text(json.dumps(rep, indent=1, default=float))
    print("BEST", json.dumps({"body": best["body"], "c_norm": round(best["c_norm"], 2), "sex_gnm": round(best["sex_gnm"], 2),
                              "z_top": sorted(best["z"].items(), key=lambda kv: -abs(kv[1]))[:10]}))
    print("wrote", d)
