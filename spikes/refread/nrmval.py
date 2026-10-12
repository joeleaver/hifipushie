"""nrmval.py <clay|dressed> [model=tk_T06] [diff=0|1]: the LEARNED-NORMAL read validated as shval.py validated the
shading read. Head A = the model; the "picture" = a render of head B = A + a known identity change through the
model's own cameras; ONLY the normal observations go into the solve (GNM's prior). Reported: how well the solved change
reproduces the true change of the cheek surface along its normal (correlation, size), and the NULL case (B = A).
clay: face_ruler.clay under a frontal light (the estimator sees grey clay). dressed: EEVEE shots of scratch models
nv_<case> (skin, eyes, brows, the photo's light; bald), as the judging sheet's, cached in out/nv_*.png.
diff=1: the observation is estimate(picture) - estimate(A's own picture of the same kind) (the estimator's bias out).
PASS = null near zero AND every known change back with corr >= 0.7 and about the right size."""
import os, sys
import numpy as np
from PIL import Image
from hifipushie import face_ruler as fr, facenormals as fnm, blockin as bi, store

mode = sys.argv[1]
m = sys.argv[2] if len(sys.argv) > 2 else "tk_T06"
diff = len(sys.argv) > 3 and sys.argv[3] in ("1", "diff=1")
OUT = "/mnt/data/hifipushie/refread/out"
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
sm = fr._normal_model(A)
ck = cheek[gid[sm["idx"]]]
Bn = np.einsum("kvc,vc->kv", np.asarray(A["B"][:, sm["idx"]], float), sm["N"]) * 1000.0     # mm along the normal per unit
rng = np.random.default_rng(3)
r = rng.standard_normal(170); r *= 2.0 / np.linalg.norm(r)
CASES = {"null": np.zeros(170), "cf_p": 1.5 * bi.direction("cheek_fullness"), "cf_m": -1.5 * bi.direction("cheek_fullness"),
         "sc_cheeks": 2.0 * bi.direction("sculpt:cheeks"), "sc_malar": 2.0 * bi.direction("sculpt:malar"), "rand2": r}
SAY = {"null": "null", "cf_p": "cheek_fullness +1.5", "cf_m": "cheek_fullness -1.5", "sc_cheeks": "sculpt:cheeks +2 mm",
       "sc_malar": "sculpt:malar +2 mm", "rand2": "random |dc| 2"}


def dressed(name, vi, cam, ib):
    f = f"{OUT}/nv_{name}_{vi}.png"
    if name == m and os.path.exists(f"/mnt/data/hifipushie/reruns/out/d_{m}_{vi}.png"):
        f = f"/mnt/data/hifipushie/reruns/out/d_{m}_{vi}.png"
    if not os.path.exists(f):
        sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3"]
        import stage
        from hifipushie import resources
        with resources.heavy(f"refread validation shot {name} {vi}", gb=6):
            im = stage.shoot(name, [stage.fitted_frame(cam, [float(x) for x in ib], f"v{vi}")], stage.photo_light(name, vi), size=1040,
                             hair_on=False)[f"v{vi}"]
        bg = Image.new("RGB", im.size, (200, 200, 200))
        bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
        bg.save(f)
    return Image.open(f).convert("RGB")


def views_of(name, head):
    out = []
    for vi, (v, cam, box) in enumerate(zip(rj["views"], rj["cameras"], rj["blockin"]["boxes"])):
        kind = fr.kind_of(v.get("yaw", 0))
        if mode == "clay":
            img = fr.clay(head, cam, light=(0.45, np.array([0.10, -0.15, -0.40]), 1.6 * (0.45 + 0.44)))
            out.append({"img": img, "cam": cam, "kind": kind, "style": "clay"})
        else:
            ib = [int(round(x)) for x in box]
            img = dressed(name, vi, cam, ib)
            out.append({"img": img, "cam": cam, "kind": kind, "style": "photo", "hair": False, "scale": img.size[0] / float(ib[2] - ib[0]),
                        "origin": (ib[0], ib[1])})
    return out


ref = None
if diff:
    ref = []
    for vw in views_of(m, A):
        fr._normal_obs(A, vw)
        ref.append(vw["_nrm"])
for cn, dct in CASES.items():
    name = m
    if cn != "null" and mode == "dressed":
        name = f"nv_{cn}"
        if not (store.HOME / "nv_A" / "spec.json").exists():
            bi.fork(m, "nv_A")                       # (steps log into the fork, never into the model's own block-in)
        if not (store.HOME / name / "spec.json").exists():
            bi.step("nv_A", {}, out=name, seen="refread validation", why=SAY[cn], _identity=c0 + dct)
    Bh = fr.model_head(spec, c0 + dct, A["kappa"])
    vs = views_of(name, Bh)
    obs = [ob for i, vw in enumerate(vs) for ob in fr._normal_obs(A, vw, None if ref is None else ref[i])]
    if not obs:
        print(cn, "NO OBS"); continue
    out = fr.solve(obs, A, tau=1.0)
    o = np.array([ob["o"] for ob in obs])
    pred = np.array([ob["J"] for ob in obs]) @ dct
    de, dt = out["dc"] @ Bn, dct @ Bn
    rms = lambda x: float(np.sqrt(np.mean(x[ck] ** 2)))
    cor = float(np.corrcoef(de[ck], dt[ck])[0, 1]) if rms(dt) > 1e-6 else float("nan")
    oc = float(np.corrcoef(o, pred)[0, 1]) if np.abs(pred).max() > 1e-9 else float("nan")
    print(f"{mode}{' diff' if diff else ''} {SAY[cn]:20s} obs {len(obs)} | cheek surface along the normal: true {rms(dt):.2f} mm rms, read {rms(de):.2f}, "
          f"corr {cor:+.2f}, miss {rms(de - dt):.2f} | |dc| true {np.linalg.norm(dct):.2f} read {np.linalg.norm(out['dc']):.2f}, cos {float(out['dc'] @ dct / max(np.linalg.norm(out['dc']) * np.linalg.norm(dct), 1e-9)):+.2f} | "
          f"obs: sd {np.degrees(o.std()):.1f} deg, predicted signal sd {np.degrees(pred.std()):.1f} deg, corr(obs, predicted) {oc:+.2f} | fit rms {out['rms']:.2f} sig", flush=True)
