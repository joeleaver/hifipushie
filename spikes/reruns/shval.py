"""shval.py [model=tk_T06]: the SHADING read validated on clay pairs. Head A = the model; the "picture" = clay of head
B = A + a known identity change, under a known light, through the model's own three cameras. Only the shading
observations go into the solve (GNM's prior). Reported: how well the solved change reproduces the true change of the
surface along its normal over the cheek regions (correlation, size ratio), and a NULL case (B = A)."""
import sys, copy
import numpy as np
from hifipushie import face_ruler as fr, blockin as bi, store

m = sys.argv[1] if len(sys.argv) > 1 else "tk_T06"
spec = store.load(m)
rj = bi._refs(m)
A = fr.model_head(spec)
c0 = bi.identity(spec)
gr = fr._gnm()["gr"]
gid = np.asarray(A["gid"], int)
cheek = np.zeros(len(gr["skin"]), bool)
for k in ("left_cheek_region", "right_cheek_region", "left_zygomatic_region", "right_zygomatic_region",
          "left_infraorbital_region", "right_infraorbital_region", "left_parotid_region", "right_parotid_region"):
    cheek |= gr[k]
sm = fr._shade_model(A)
ck = cheek[gid[sm["idx"]]]
Bn = np.einsum("kvc,vc->kv", np.asarray(A["B"][:, sm["idx"]], float), sm["N"]) * 1000.0     # mm along the normal per unit
LIGHTS = {"frontal": (0.45, np.array([0.10, -0.15, -0.40])), "side": (0.35, np.array([0.40, -0.20, -0.25]))}
rng = np.random.default_rng(3)
r = rng.standard_normal(170); r *= 2.0 / np.linalg.norm(r)
CASES = {"null": np.zeros(170), "cheek_fullness +1.5": 1.5 * bi.direction("cheek_fullness"),
         "cheek_fullness -1.5": -1.5 * bi.direction("cheek_fullness"), "sculpt:cheeks +2 mm": 2.0 * bi.direction("sculpt:cheeks"),
         "sculpt:malar +2 mm": 2.0 * bi.direction("sculpt:malar"), "random |dc| 2": r}
for ln, (c0l, w) in LIGHTS.items():
    for cn, dct in CASES.items():
        Bh = fr.model_head(spec, c0 + dct, A["kappa"])
        views = []
        for v, cam in zip(rj["views"], rj["cameras"]):
            img = fr.clay(Bh, cam, light=(c0l, w, 1.6 * (c0l + float(np.linalg.norm(w)))))
            views.append({"img": img, "cam": cam, "kind": fr.kind_of(v.get("yaw", 0)), "style": "clay"})
        obs = [ob for vw in views for ob in fr._shade_obs(A, vw)]
        if not obs:
            print(ln, cn, "NO OBS"); continue
        out = fr.solve(obs, A, tau=1.0)
        de, dt = out["dc"] @ Bn, dct @ Bn
        rms = lambda x: float(np.sqrt(np.mean(x[ck] ** 2)))
        cor = float(np.corrcoef(de[ck], dt[ck])[0, 1]) if rms(dt) > 1e-6 else float("nan")
        lights = [vw.get("_shade_light") for vw in views]
        print(f"{ln:8s} {cn:22s} obs {len(obs)} | cheek surface along the normal: true {rms(dt):.2f} mm rms, read {rms(de):.2f}, "
              f"corr {cor:+.2f}, miss {rms(de - dt):.2f} | |dc| true {np.linalg.norm(dct):.2f} read {np.linalg.norm(out['dc']):.2f} | "
              f"fit rms {out['rms']:.2f} sig | light c0 {lights[0][0]:.2f} w {np.round(lights[0][1], 2).tolist()}")
