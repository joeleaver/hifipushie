"""val.py <head model> <tag> <truth.json> [scale=1] [mode=fit|null] [rounds=2]: the validation of skin_read.

A known head (the head model's shape and cameras) is dressed with KNOWN, deliberately unusual skin parameters
(truth.json = a spec["skin"]) and photographed through its reference cameras under a light the reader does not know
(another direction, a warm cast, another exposure; a grey backdrop lit by the same light). Those pictures become the
references of a copy of the head whose skin starts from DEFAULTS (mode fit) or from the truth itself (mode null), and
skin_read.apply runs on it. Reported: every parameter truth | start | fitted, and the albedo's error against the
truth's by region (Lab, the Python albedo on the same points) before and after.
scale < 1: the pictures are made smaller (a face 110 px wide: Garrett's)."""
import copy, json, os, sys, time
import numpy as np
from PIL import Image
from hifipushie import skin_read as sr, blockin as bi, store, resources, skin as skinmod

head, tag, truth_f = sys.argv[1:4]
kw = dict(a.split("=") for a in sys.argv[4:])
scale, mode, rounds = float(kw.get("scale", 1)), kw.get("mode", "fit"), int(kw.get("rounds", 2))
G = os.environ["G"] + "/out"
truth = json.load(open(truth_f))
TINT = np.array([1.0, 0.93, 0.84])                     # the unknown light's colour (all its lamps and its room)
VLIGHT = {"lights": [{"dir": [0.45, -0.72, 0.5], "energy": 2.9, "color": TINT.tolist(), "angle": 25},
                     {"dir": [-0.3, -0.9, 0.1], "energy": 0.9, "color": TINT.tolist(), "angle": 40, "shadow": False, "specular": 0.0}],
          "world": {"color": (0.75 * TINT).tolist(), "strength": 0.5}, "view": "Standard", "exposure": -0.35}

tm, vm = f"sr_vt_{tag}", f"sr_v_{tag}_{mode}"
pics = [f"{G}/val_{tag}_{i}.png" for i in range(len(bi._refs(head)["views"]))]
if not all(os.path.exists(p) for p in pics) or os.environ.get("FRESH"):
    bi.fork(head, tm, replace=True)
    sp = store.load(tm)
    sp["skin"] = truth
    sp["paint"] = {}
    store.save(tm, sp, "skinread validation: the truth")
    rj = bi._refs(tm)
    with resources.heavy(f"skinread val truth {tag}", gb=6):
        sn = sr.stage(tm)
        for i, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
            w, h = cam["size"]
            s = max(w, h)
            x0, y0 = (w - s) / 2, (h - s) / 2
            im = sr.shoot(sn, [sr.fitted_frame(cam, [x0, y0, x0 + s, y0 + s], "v")], VLIGHT, size=s)["v"]
            bg = np.zeros((s, s, 4), np.uint8)
            bg[..., :3] = np.round(255 * sr._srgb(0.5 * TINT * 2 ** -0.35))
            bg[..., 3] = 255
            full = Image.alpha_composite(Image.fromarray(bg), Image.fromarray(im)).convert("RGB")
            full = full.crop((int(-x0), int(-y0), int(-x0) + w, int(-y0) + h))
            if scale != 1:
                full = full.resize((int(round(w * scale)), int(round(h * scale))), Image.LANCZOS)
            full.save(pics[i])
            print("truth picture", pics[i], full.size)

bi.fork(head, vm, replace=True)
sp = store.load(vm)
start = copy.deepcopy(truth) if mode == "null" else {k: truth[k] for k in ("sex", "age", "part") if k in truth}
sp["skin"] = start
sp["paint"] = {}
rj = bi._refs(vm)
for i, v in enumerate(rj["views"]):
    v["image"] = pics[i]
    if scale != 1:
        v["size"] = [int(round(x * scale)) for x in v["size"]]
        v["points"] = {k: [p[0] * scale, p[1] * scale] for k, p in (v.get("points") or {}).items()}
        cam = rj["cameras"][i]
        cam["f"] *= scale
        cam["size"] = [int(round(x * scale)) for x in cam["size"]]
        if (rj.get("blockin") or {}).get("boxes"):
            rj["blockin"]["boxes"][i] = [x * scale for x in rj["blockin"]["boxes"][i]]
bi._save(vm, sp, "skinread validation: the start", rj)

t = time.time()
res = sr.apply(vm, rounds=rounds, log=lambda s: print(s) if "[measure]" not in str(s) else None)
print(res["text"])
print(f"\n{time.time() - t:.0f} s")
fit = res["skin"]

# every parameter: truth | start | fitted
P = [p for g in ("tone", "zones", "eyes", "lips") for p in sr.GROUPS[g]]
print(f"\n{'parameter':26s} {'truth':>8s} {'start':>8s} {'fitted':>8s}   recovered share of (truth - start)")
rows = []
for p in P:
    a, b, c = sr._get(truth, p), sr._get(start, p), sr._get(fit, p)
    sh = (c - b) / (a - b) if abs(a - b) > 1e-6 else float("nan")
    rows.append((p, a, b, c, sh))
    print(f"{p:26s} {a:8.3f} {b:8.3f} {c:8.3f}   {sh:6.2f}")
for k in ("stubble", "brows"):
    print(f"hair.{k}: truth {json.dumps((truth.get('hair') or {}).get(k))}\n    fitted {json.dumps((fit.get('hair') or {}).get(k))}")
print("freckles: truth", (truth.get("features") or {}).get("freckles"), "fitted", (fit.get("features") or {}).get("freckles"))
print("eyes: truth", truth.get("eyes"), "fitted", fit.get("eyes"))

# the albedo against the truth's, by region (the same points, the Python albedo)
c = sr.context(vm, render=False) if False else None
frames = sr.capture(vm, render=False)
X = np.concatenate([f["X"][sr.trust(f) > 0.5] for f in frames]); n = np.concatenate([f["n"][sr.trust(f) > 0.5] for f in frames])
alb = sr.Albedo(sr.stage_spec(store.load(vm)), X, n)
At, As, Af = alb(truth), alb(start), alb(fit)
print(f"\n{'region':16s} albedo error vs truth, Lab:  start                 fitted")
tot = [[], []]
for z in sr.ZONES + ("lips",):
    w = alb.zone(z, 0.8 if z == "lips" else 1.0)
    if w.sum() < 50:
        continue
    L = lambda A: sr.lab((A * w[:, None]).sum(0) / w.sum())
    e0, e1 = L(As) - L(At), L(Af) - L(At)
    tot[0].append(e0); tot[1].append(e1)
    print(f"{z:16s} {str(e0.round(1)):24s} {str(e1.round(1))}")
print("rms over regions:  start", np.sqrt((np.array(tot[0]) ** 2).mean(0)).round(2), " fitted", np.sqrt((np.array(tot[1]) ** 2).mean(0)).round(2))
json.dump({"truth": truth, "start": start, "fit": fit, "rows": rows}, open(f"{G}/val_{tag}_{mode}.json", "w"), indent=1, default=str)
