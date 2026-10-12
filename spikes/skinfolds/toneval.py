"""toneval.py <head> <tag> <truth fitzpatrick> <ev> [prior=<fitzpatrick>] [white=1]: the lightness anchor's validation.
A known head dressed with a KNOWN tone (Fitzpatrick f with its own hue: blood 0.6, undertone +0.35) is photographed
through its reference cameras under a light the reader does not know (warm, another direction) at exposure `ev`, on a
grey backdrop. A copy starts from the PRIOR tone (the same Fitzpatrick type by default, default hue: what a person
would state; prior= another type: a wrong statement) and skin_read.apply(groups tone + zones) runs.
Reported: the base tone's Lab (skin.tone_rgb) truth | prior | fitted, and the bound.
white=1 paints a white collar (albedo 0.8 under the same light) under the chin: the exposure anchor."""
import copy, json, os, sys, time
import numpy as np
from PIL import Image
from hifipushie import skin_read as sr, blockin as bi, store, resources, skin as skinmod

head, tag, f_true, ev = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
kw = dict(a.split("=") for a in sys.argv[5:])
f_prior = float(kw.get("prior", f_true))
white = bool(int(kw.get("white", 0)))
G = os.environ["G"] + "/out"
TINT = np.array([1.0, 0.93, 0.84])
VLIGHT = {"lights": [{"dir": [0.45, -0.72, 0.5], "energy": 2.9, "color": TINT.tolist(), "angle": 25},
                     {"dir": [-0.3, -0.9, 0.1], "energy": 0.9, "color": TINT.tolist(), "angle": 40, "shadow": False, "specular": 0.0}],
          "world": {"color": (0.75 * TINT).tolist(), "strength": 0.5}, "view": "Standard", "exposure": ev}
truth = {"sex": 0, "age": 25, "tone": {"fitzpatrick": f_true, "blood": 0.6, "undertone": 0.35}, "wrinkles": {"amount": 0}}
start = {"sex": 0, "age": 25, "tone": {"fitzpatrick": f_prior}, "wrinkles": {"amount": 0}}
key = f"{tag}_f{f_true:g}_ev{ev:+.1f}".replace(".", "p") + ("_w" if white else "")
tm, vm = f"sf_tt_{key}", f"sf_tv_{key}_p{f_prior:g}".replace(".", "p")
nv = len(bi._refs(head)["views"])
pics = [f"{G}/tone_{key}_{i}.png" for i in range(nv)]
if not all(os.path.exists(p) for p in pics) or os.environ.get("FRESH"):
    bi.fork(head, tm, replace=True)
    sp = store.load(tm); sp["skin"] = truth; sp["paint"] = {}
    store.save(tm, sp, "skinfolds tone validation: the truth")
    rj = bi._refs(tm)
    with resources.heavy(f"skinfolds toneval truth {key}", gb=6):
        sn = sr.stage(tm, log=lambda s: None)
        for i, cam in enumerate(rj["cameras"]):
            w, h = cam["size"]
            s = max(w, h)
            x0, y0 = (w - s) / 2, (h - s) / 2
            im = sr.shoot(sn, [sr.fitted_frame(cam, [x0, y0, x0 + s, y0 + s], "v")], VLIGHT, size=s)["v"]
            bg = np.zeros((s, s, 4), np.uint8)
            lit = TINT * 2 ** ev                      # what a white card facing the key would read (about 1 x the light)
            bg[..., :3] = np.round(255 * sr._srgb(np.clip(0.5 * lit, 0, 1))); bg[..., 3] = 255
            full = Image.alpha_composite(Image.fromarray(bg), Image.fromarray(im)).convert("RGB")
            if white:   # a white collar: a band under the chin, behind the figure's alpha (albedo 0.8, lit as the face's front)
                a = np.asarray(Image.fromarray(im).split()[3], float) / 255
                ys = np.nonzero(a.any(1))[0]
                # the face's front irradiance: the brightest decile of the head's luminance / its albedo luminance
                rgb = sr._lin(np.asarray(Image.fromarray(im).convert("RGB"), float) / 255)
                Yh = (rgb @ [0.2126, 0.7152, 0.0722])[a > 0.98]
                alb = sr._lin(np.asarray(skinmod.tone_rgb(truth["tone"]), float)) @ [0.2126, 0.7152, 0.0722]
                E = float(np.percentile(Yh, 60)) / alb
                col = np.round(255 * sr._srgb(np.clip(0.8 * E * TINT / (TINT @ [0.2126, 0.7152, 0.0722]), 0, 0.999))).astype(np.uint8)
                arr = np.asarray(full).copy()
                y0c = int(ys.max() - 0.16 * (ys.max() - ys.min()))
                band = np.zeros(a.shape, bool); band[y0c:, int(0.25 * s):int(0.75 * s)] = True
                arr[band & (a < 0.02)] = col
                # and over the shoulders' skin under the chin line: a shirt
                arr[band & (np.arange(s)[:, None] > ys.max() - 0.07 * (ys.max() - ys.min()))] = col
                full = Image.fromarray(arr)
            full = full.crop((int(-x0), int(-y0), int(-x0) + w, int(-y0) + h))
            full.save(pics[i])
bi.fork(head, vm, replace=True)
sp = store.load(vm); sp["skin"] = copy.deepcopy(start); sp["paint"] = {}
rj = bi._refs(vm)
for i, v in enumerate(rj["views"]):
    v["image"] = pics[i]
bi._save(vm, sp, "skinfolds tone validation: the start", rj)
t = time.time()
res = sr.apply(vm, groups=("tone", "zones"), rounds=int(kw.get("rounds", 1)), brow_shape=False, log=lambda s: None)
fit = res["skin"]
L = lambda tn: sr.lab(sr._lin(np.asarray(skinmod.tone_rgb(tn), float)))  # noqa: E731
lt, ls, lf = L(truth["tone"]), L(start["tone"]), L(fit.get("tone") or start["tone"])
f0 = res["fits"][0]
print(f"== {key} prior F{f_prior:g}: anchor {f0['tone']['anchor']}, exposure x {f0['exposure']}, plain L {f0['tone']['prior_L']} -> {f0['tone']['fitted_L']} "
      f"(bound {f0['tone']['bound']}) {f0['tone']['note'] or ''}; {time.time() - t:.0f} s")
print(f"   base tone Lab  truth {lt.round(1).tolist()}  prior {ls.round(1).tolist()}  fitted {lf.round(1).tolist()}")
print(f"   error to truth: prior dL {ls[0] - lt[0]:+.1f} da {ls[1] - lt[1]:+.1f} db {ls[2] - lt[2]:+.1f}  ->  fitted dL {lf[0] - lt[0]:+.1f} da {lf[1] - lt[1]:+.1f} db {lf[2] - lt[2]:+.1f};"
      f"  drift from the prior {lf[0] - ls[0]:+.1f} L")
print("   fitted tone", json.dumps(fit.get("tone")), "| anchor note:", [ln for ln in res["reads"][0].split("\n") if "LIGHTNESS" in ln][:1])
json.dump({"key": key, "prior": f_prior, "truth": lt.tolist(), "start": ls.tolist(), "fitted": lf.tolist(), "fit": f0["tone"], "tone": fit.get("tone")},
          open(f"{G}/tone_{key}_p{f_prior:g}.json", "w"))
