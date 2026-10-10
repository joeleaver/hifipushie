"""newdirs.py: faces6, the block-in's VOCABULARY GAPS as data-backed coupled directions (coordinator / Joe's standing
rule: "where the model can't reach a feature, extend the model with a data-backed direction with its couplings").
Readers (humanmacro.measures, GNM heads, world frame): gonial_height, orbital_rim, lower_orbit, radix_width (new) +
every existing macro. Sampled over N heads from GNM's prior (comps 0-119, seed 0 like the atlas), each attribute's
linear model (80 / 20 split: held-out R2), sd, and its COUPLED direction: the conditional mean per +1 sd,
dc = S a (a' S a)^-1 sd, S = the identity covariance WITHIN sex on GNM's OWN sex axis (the semantic sampler's
class-mean difference d: S = I - d d' / 4, capped like faceatlas.within_sex). Reports R2, sd, the strongest
couplings (population correlations) and what +1 sd of the coupled direction does to the other macros (in their sd).
Writes $F/newdirs.npz {names, dirs (170, k), sd, r2} for artist.py step ("nd:<name>")."""
import json
import os

import numpy as np

from hifipushie import faceatlas, humanmacro as hm

F = os.environ.get("F", "/mnt/data/hifipushie/faces6")
N = int(os.environ.get("N", "2000"))
NEW = ["gonial_height", "orbital_rim", "lower_orbit", "radix_width"]

if __name__ == "__main__":
    K = hm.K
    rng = np.random.default_rng(0)
    C = rng.normal(0, 1, (N, K))
    sp = hm.space()
    V0, ext = sp["V0"], sp["ext"]
    L0 = sp["W"] @ V0
    band = np.flatnonzero(ext & (np.abs(V0[:, 2] - L0[28, 2]) < 0.002) & (np.abs(V0[:, 0]) < 0.016)
                          & (-V0[:, 1] > (-V0[ext, 1]).max() - 0.05))

    def radix_width(V):
        """the bridge's width between the eyes at the radix (landmark 28's height): the soft-weighted spread of the
        surface within 3 mm of the bridge's front, over the interocular distance (not a humanmacro macro: R2 0.90)."""
        L = sp["W"] @ V
        B_ = V[band]
        w_ = 1.0 / (1.0 + np.exp(-((-B_[:, 1]) - (-L[28, 1] - 0.003)) / 0.0006))
        return 2.0 * float(np.sqrt((w_ * (B_[:, 0] - L[28, 0]) ** 2).sum() / max(w_.sum(), 1e-9))) / (L[68, 0] - L[69, 0])

    names = hm.NAMES + ["radix_width"]
    A = np.array([[*[(m := hm.measures(V))[k] for k in hm.NAMES], radix_width(V)] for V in (hm.head(c) for c in C)])
    tr = np.arange(N) < int(0.8 * N)
    X = np.c_[np.ones(N), C]
    cv = np.load(f"{F}/cvae_stats.npz")
    d = (cv["m_m"] - cv["m_f"])[:K]
    S = np.eye(K) - np.outer(d, d) / 4 * min(1.0, faceatlas.SEX_SHARE * 4 / float(d @ d))
    corr = np.corrcoef(A.T)
    Bfull, sdv = [], A.std(0)
    for j in range(len(names)):
        beta = np.linalg.lstsq(X[tr], A[tr, j], rcond=None)[0]
        Bfull.append(beta[1:])
    Bfull = np.array(Bfull)
    out_dirs, out = [], {}
    for nm in NEW:
        j = names.index(nm)
        beta = np.linalg.lstsq(X[tr], A[tr, j], rcond=None)[0]
        r2 = 1 - np.mean((A[~tr, j] - X[~tr] @ beta) ** 2) / np.var(A[~tr, j])
        a = beta[1:]
        dc = S @ a / float(a @ S @ a) * sdv[j]
        eff = (Bfull @ dc) / np.maximum(sdv, 1e-12)
        top_c = sorted([(names[i], round(float(corr[j, i]), 2)) for i in range(len(names)) if i != j], key=lambda t: -abs(t[1]))[:5]
        top_e = sorted([(names[i], round(float(eff[i]), 2)) for i in range(len(names)) if i != j], key=lambda t: -abs(t[1]))[:5]
        out[nm] = {"r2": round(float(r2), 3), "sd": round(float(sdv[j]), 4), "unit": hm.MACROS[nm][0] if nm in hm.MACROS else "io", "|dc| per sd": round(float(np.linalg.norm(dc)), 2),
                   "correlated with": top_c, "+1 sd coupled moves (sd)": top_e}
        print(nm, json.dumps(out[nm]), flush=True)
        D = np.zeros(170)
        D[:K] = dc
        out_dirs.append(D)
    # held variants: the attribute moved by +1 sd with named neighbours held (the population's coupling is what an
    # artist sometimes wants to break: her defined orbital RIM without the heavy brow / deep-set eyes it comes with)
    HOLDS = {"orbital_rim": ["brow_ridge", "eye_depth"], "gonial_height": ["face_length", "chin_height"]}
    for nm, hold in HOLDS.items():
        rows = [names.index(nm)] + [names.index(h) for h in hold]
        Bs = Bfull[rows]
        da = np.r_[sdv[rows[0]], np.zeros(len(hold))]
        dc = S @ Bs.T @ np.linalg.solve(Bs @ S @ Bs.T, da)
        eff = (Bfull @ dc) / np.maximum(sdv, 1e-12)
        key = f"{nm}|hold_" + "_".join(hold)
        top_e = sorted([(names[i], round(float(eff[i]), 2)) for i in range(len(names)) if i != rows[0]], key=lambda t: -abs(t[1]))[:5]
        out[key] = {"r2": out[nm]["r2"], "sd": out[nm]["sd"], "unit": out[nm]["unit"], "|dc| per sd": round(float(np.linalg.norm(dc)), 2),
                    "+1 sd moves (sd)": top_e}
        print(key, json.dumps(out[key]), flush=True)
        D = np.zeros(170)
        D[:K] = dc
        out_dirs.append(D)
        NEW = NEW + [key]
    t = faceatlas.table()
    for k in ("gonion_height", "radix_width", "eye_setback", "malar_rise", "lid_aperture", "ramus_angle"):
        if k in t["index"]:
            i = t["index"][k]
            print(f"(faceatlas, existing) {k}: R2 {float(t['r2'][i]):.3f}, sd {float(t['sd'][i]):.4f}")
    np.savez(f"{F}/newdirs.npz", names=np.array(NEW), dirs=np.stack(out_dirs, 1), sd=np.array([out[n]["sd"] for n in NEW]),
             r2=np.array([out[n]["r2"] for n in NEW]))
    json.dump(out, open(f"{F}/out/newdirs.json", "w"), indent=1)
