import numpy as np
from hifipushie import face_ruler as fr, blockin as bi, store
m = "tk_T06"; spec = store.load(m); rj = bi._refs(m)
A = fr.model_head(spec); c0 = bi.identity(spec)
c0l, w = 0.35, np.array([0.40, -0.20, -0.25]); L = (c0l, w, 1.6 * (c0l + float(np.linalg.norm(w))))
def run(dct):
    Bh = fr.model_head(spec, c0 + dct, A["kappa"]); res = []
    for v, cam in zip(rj["views"], rj["cameras"]):
        vw = {"img": fr.clay(Bh, cam, light=L), "cam": cam, "kind": fr.kind_of(v.get("yaw", 0)), "style": "clay"}
        obs = fr._shade_obs(A, vw)
        o = np.array([ob["o"] for ob in obs]); J = np.array([ob["J"] for ob in obs])
        N = np.array([[ob["nu"][k] for k in sorted(ob["nu"])] for ob in obs])
        proj = lambda x: x - N @ np.linalg.lstsq(N, x, rcond=None)[0]      # the nuisance field taken out
        pred = J @ dct
        res.append((vw["kind"], len(o), float(proj(o).std()), float(proj(pred).std()),
                    float(np.corrcoef(proj(o), proj(pred))[0, 1]) if proj(pred).std() > 1e-9 else float("nan")))
    return res
for name, d in (("null", np.zeros(170)), ("cheek_fullness +1.5", 1.5 * bi.direction("cheek_fullness")), ("sculpt:cheeks +2", 2.0 * bi.direction("sculpt:cheeks")),
                ("cheek_fullness -1.5", -1.5 * bi.direction("cheek_fullness"))):
    print(name, [(k, n, f"obs sd {a:.3f}", f"predicted sd {b:.3f}", f"corr {c:+.2f}") for k, n, a, b, c in run(d)])
