"""t8.py: the block-in model adapter: observed outline offsets between two models vs the Jacobian's prediction."""
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, store

a, b = "gk_s376", "gk_s540"
sa, sb = store.load(a), store.load(b)
print({k: sa["base"]["head"].get(k) for k in ("gnm_base", "scale", "dimorphism")}, {k: sb["base"]["head"].get(k) for k in ("gnm_base", "scale", "dimorphism")})
print("same base apart from identity:", {k for k in sa["base"]["head"] if sa["base"]["head"].get(k) != sb["base"]["head"].get(k)},
      {k for k in sa["base"] if k != "head" and sa["base"].get(k) != sb["base"].get(k)})
A, B = fr.model_head(sa), fr.model_head(sb)
print("kappa", A["kappa"], "relative residual of the real vertex move", A["kappa_res"])
dc = bi.identity(sb) - bi.identity(sa)
rj = bi._refs("gd_T12")
for t in (0.25, 1.0):
    Bt = fr.model_head(sa, bi.identity(sa) + t * dc, A["kappa"])
    for v, cam in zip(rj["views"], rj["cameras"]):
        k = fr.kind_of(v.get("yaw", 0))
        view = {"img": fr.clay(Bt, cam), "cam": cam, "kind": k, "style": "dressed"}
        obs = fr.observe(A, [view])
        o = np.array([ob["o"] for ob in obs])
        p = np.array([ob["J"] for ob in obs]) @ (t * dc)
        sl = float(o @ p / (p @ p))
        print(f"t {t} {k:8s} n {len(o)} |o| rms {np.sqrt((o ** 2).mean()):.2f} pred rms {np.sqrt((p ** 2).mean()):.2f} slope {sl:.2f} resid rms {np.sqrt(((o - p) ** 2).mean()):.2f}")
# is B really A + dc? the picture of model b vs the picture of a with b's identity
for v, cam in zip(rj["views"][:1], rj["cameras"][:1]):
    m1 = np.asarray(fr.clay(B, cam).convert("L"), float)
    m2 = np.asarray(fr.clay(Bt, cam).convert("L"), float)
    print("model b vs model a + dc: mean |difference| of the clay pictures", float(np.abs(m1 - m2).mean()))
