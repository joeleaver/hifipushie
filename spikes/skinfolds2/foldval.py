"""(skinfolds2: models sg_ft_* / sg_f_*; skinfolds: skinread's foldval with the folds as GEOMETRY; light=side|front|lamp; models sg_ft_* / sg_f_*)
foldval.py <head> <tag> <truth.json> <start.json> [scale=1]: the folds' validation and calibration. The head is
dressed with truth.json (a spec["skin"]) and photographed under the unknown light (val.py's); a copy starts from
start.json with those pictures as its references; ONE read (no fit) prints the checklist: per fold picture / ours /
diff / excess, present or not, extent and shift against the truth's own. Cases: truth with folds, start without
(hits, FOLD_REF = diff at amount 1); truth smooth, start smooth (false positives); truth smooth, start with folds
(ours has more); truth = start (the null)."""
import copy, json, os, pickle, sys, time
import numpy as np
from PIL import Image
from hifipushie import skin_read as sr, blockin as bi, store, resources

head, tag, truth_f, start_f = sys.argv[1:5]
kw = dict(a.split("=") for a in sys.argv[5:])
scale = float(kw.get("scale", 1))
G = os.environ["G"] + "/out"
truth, start = json.load(open(truth_f)), json.load(open(start_f))
TINT = np.array([1.0, 0.93, 0.84])
VLIGHT = {"lights": [{"dir": [0.45, -0.72, 0.5], "energy": 2.9, "color": TINT.tolist(), "angle": 25},
                     {"dir": [-0.3, -0.9, 0.1], "energy": 0.9, "color": TINT.tolist(), "angle": 40, "shadow": False, "specular": 0.0}],
          "world": {"color": (0.75 * TINT).tolist(), "strength": 0.5}, "view": "Standard", "exposure": -0.35}
tkey = os.path.basename(truth_f).replace(".json", "") + (f"_s{int(round(scale * 100))}" if scale != 1 else "")
LK = kw.get("light", "side")
if LK == "front":
    VLIGHT = {"lights": [{"dir": [0.05, -0.85, 0.5], "energy": 3.0, "color": TINT.tolist(), "angle": 30},
                         {"dir": [-0.3, -0.9, 0.1], "energy": 0.9, "color": TINT.tolist(), "angle": 40, "shadow": False, "specular": 0.0}],
              "world": {"color": (0.75 * TINT).tolist(), "strength": 0.5}, "view": "Standard", "exposure": -0.35}
    tkey += "_front"
if LK == "lamp":   # a painter's lamp from the figure's right, low: the fold is a lit / shaded step
    VLIGHT = {"lights": [{"dir": [-0.8, -0.55, 0.25], "energy": 3.2, "color": TINT.tolist(), "angle": 12},
                         {"dir": [0.3, -0.9, 0.1], "energy": 0.5, "color": TINT.tolist(), "angle": 40, "shadow": False, "specular": 0.0}],
              "world": {"color": (0.75 * TINT).tolist(), "strength": 0.4}, "view": "Standard", "exposure": -0.35}
    tkey += "_lamp"
tm, vm = f"sg_ft_{tkey}", f"sg_f_{tag}"
nv = len(bi._refs(head)["views"])
pics = [f"{G}/fval_{tkey}_{i}.png" for i in range(nv)]
if not all(os.path.exists(p) for p in pics) or os.environ.get("FRESH"):
    bi.fork(head, tm, replace=True)
    sp = store.load(tm); sp["skin"] = truth; sp["paint"] = {}
    store.save(tm, sp, "skinfolds fold validation: the truth")
    rj = bi._refs(tm)
    with resources.heavy(f"skinfolds foldval truth {tkey}", gb=6):
        sn = sr.stage(tm, log=lambda s: None)
        for i, cam in enumerate(rj["cameras"]):
            w, h = cam["size"]
            s = max(w, h)
            x0, y0 = (w - s) / 2, (h - s) / 2
            im = sr.shoot(sn, [sr.fitted_frame(cam, [x0, y0, x0 + s, y0 + s], "v")], VLIGHT, size=s)["v"]
            bg = np.zeros((s, s, 4), np.uint8)
            bg[..., :3] = np.round(255 * sr._srgb(0.5 * TINT * 2 ** -0.35)); bg[..., 3] = 255
            full = Image.alpha_composite(Image.fromarray(bg), Image.fromarray(im)).convert("RGB").crop((int(-x0), int(-y0), int(-x0) + w, int(-y0) + h))
            if scale != 1:
                full = full.resize((int(round(w * scale)), int(round(h * scale))), Image.LANCZOS)
            full.save(pics[i])
bi.fork(head, vm, replace=True)
sp = store.load(vm); sp["skin"] = start; sp["paint"] = {}
rj = bi._refs(vm)
for i, v in enumerate(rj["views"]):
    v["image"] = pics[i]
    if scale != 1:
        v["size"] = [int(round(x * scale)) for x in v["size"]]
        v["points"] = {k: [p[0] * scale, p[1] * scale] for k, p in (v.get("points") or {}).items()}
        cam = rj["cameras"][i]; cam["f"] *= scale; cam["size"] = [int(round(x * scale)) for x in cam["size"]]
        if (rj.get("blockin") or {}).get("boxes"):
            rj["blockin"]["boxes"][i] = [x * scale for x in rj["blockin"]["boxes"][i]]
bi._save(vm, sp, "skinfolds fold validation: the start", rj)
t = time.time()
frames = sr.capture(vm, log=lambda s: None)
c = sr.context(vm, frames=frames, log=lambda s: None)
fr = sr.fold_read(c)
print(f"== {tag}: truth {os.path.basename(truth_f)} folds {json.dumps(truth.get('folds'))} wrinkles {json.dumps(truth.get('wrinkles'))}")
print(f"   start {os.path.basename(start_f)} folds {json.dumps(start.get('folds'))} wrinkles {json.dumps(start.get('wrinkles'))}; {time.time() - t:.0f} s")
print(sr.fold_text(fr))
json.dump(fr, open(f"{G}/fval_{tag}.json", "w"), indent=1, default=str)
if kw.get("fit"):
    sk = copy.deepcopy(start)
    for ch in sr.fold_fit(sk, fr, True):
        print("  FIT", ch)
if kw.get("apply"):
    # THE ROUND TRIP: read -> skin.folds (geometry) -> render -> read again, then both heads side by side
    from hifipushie import skin_folds as sf
    res = sr.apply(vm, groups=("folds",), rounds=int(kw["apply"]), brow_shape=False, log=lambda s: None)
    got = sf.options((res["skin"] or {}).get("folds"))
    want = sf.options(truth.get("folds"))
    print(f"== ROUND TRIP ({kw['apply']} rounds, {time.time() - t:.0f} s): fold side | truth amount | recovered amount | recovered shift (median mm) vs truth")
    hits = miss = false = 0
    errs = []
    for name in sf.FOLDS:
        for sd in ((".L", ".R") if sf.sided(name) else ("",)):
            a_t = want[name]["amount"] * want[name]["sides"][sd]["amount"] if name in want else 0.0
            a_g = got[name]["amount"] * got[name]["sides"][sd]["amount"] if name in got else 0.0
            sh_t = float(np.median(want[name]["sides"][sd]["shift"])) if name in want and want[name]["sides"][sd]["shift"] else 0.0
            sh_g = float(np.median(got[name]["sides"][sd]["shift"])) if name in got and got[name]["sides"][sd]["shift"] else 0.0
            tagv = "HIT" if a_t > 0.3 and a_g > 0.3 else "MISS" if a_t > 0.3 else "FALSE" if a_g > 0.3 else "ok (absent)"
            hits += tagv == "HIT"; miss += tagv == "MISS"; false += tagv == "FALSE"
            if tagv == "HIT":
                errs.append(a_g - a_t)
            print(f"   {name + sd:15s} {a_t:5.2f} {a_g:5.2f}   shift {sh_g:+.1f} (truth {sh_t:+.1f})   {tagv}")
    print(f"   hits {hits}, misses {miss}, false {false}; strength error on hits: mean {np.mean(errs) if errs else 0:+.2f}, rms {np.sqrt(np.mean(np.square(errs))) if errs else 0:.2f}")
    print(res["reads"][-1][res["reads"][-1].find("  FOLDS"):][:6000])
    import shots
    cells = {}
    for label, m in (("TRUTH", tm), ("READ BACK", vm)):
        got_ = shots.shoot_all(m, store.load(m), ["eyes", "mouth", "q3"], ["photo", "rake"], size=512, log=lambda s: None)
        for (ln, vn), a in got_.items():
            cells[(f"{label} | {ln}", vn)] = a
    p = shots.sheet(cells, [f"{a} | {b}" for b in ("photo", "rake") for a in ("TRUTH", "READ BACK")], ["eyes", "mouth", "q3"],
                    f"fold validation {tag}: known folds (geometry) -> pictures -> read -> displacement -> render", f"{G}/fval_{tag}_roundtrip.png", 512)
    print(p)
