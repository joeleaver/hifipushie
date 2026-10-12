"""fitdbg.py <head> <tag> <truth.json>: ONE read + fit from the default start against val.py's truth pictures, frames
cached (the solver's own behaviour, without the render loop). Prints truth | start | fitted."""
import copy, json, os, pickle, sys, time
import numpy as np
from hifipushie import skin_read as sr, blockin as bi, store

head, tag, truth_f = sys.argv[1:4]
G = os.environ["G"] + "/out"
truth = json.load(open(truth_f))
vm = f"sr_v_{tag}_dbg"
fp = f"{G}/frames_{vm}.pkl"
start = {k: truth[k] for k in ("sex", "age", "part") if k in truth}
if not os.path.exists(fp) or os.environ.get("FRESH"):
    bi.fork(head, vm, replace=True)
    sp = store.load(vm); sp["skin"] = start; sp["paint"] = {}
    rj = bi._refs(vm)
    for i, v in enumerate(rj["views"]):
        v["image"] = f"{G}/val_{tag}_{i}.png"
    bi._save(vm, sp, "skinread fit debug", rj)
    frames = sr.capture(vm, log=lambda s: None)
    pickle.dump(frames, open(fp, "wb"))
frames = pickle.load(open(fp, "rb"))
t = time.time()
r = sr.read(vm, frames=frames, log=lambda s: None)
print(r["text"]); print("read", round(time.time() - t), "s")
f = sr.fit(r)
print(f["text"])
fit = f["skin"]
P = [p for g in ("tone", "zones", "eyes", "lips") for p in sr.GROUPS[g]]
print(f"\n{'parameter':26s} {'truth':>8s} {'start':>8s} {'fitted':>8s}")
for p in P:
    print(f"{p:26s} {sr._get(truth, p):8.3f} {sr._get(start, p):8.3f} {sr._get(fit, p):8.3f}")
print("stubble truth", (truth.get("hair") or {}).get("stubble"), "\n   fitted", (fit.get("hair") or {}).get("stubble"))
print("brows", (fit.get("hair") or {}).get("brows"), "freckles", (fit.get("features") or {}).get("freckles"), "eyes", fit.get("eyes"))
c = r["ctx"]
At, As, Af = c.alb(truth), c.alb(start), c.alb(fit)
tot = [[], []]
for z in sr.ZONES + ("lips",):
    w = c.alb.zone(z, 0.8 if z == "lips" else 1.0) * (c.w > 0)
    if w.sum() < 50:
        continue
    L = lambda A: sr.lab((A * w[:, None]).sum(0) / w.sum())
    e0, e1 = L(As) - L(At), L(Af) - L(At)
    tot[0].append(e0); tot[1].append(e1)
    rr = r["regions"].get(z, {})
    print(f"{z:16s} {str(e0.round(1)):24s} {str(e1.round(1)):24s} truth-start {str((-e0).round(1)):22s} READ d {rr.get('d')}")
print("albedo error vs truth, rms over regions: start", np.sqrt((np.array(tot[0]) ** 2).mean(0)).round(2), " fitted", np.sqrt((np.array(tot[1]) ** 2).mean(0)).round(2))
