"""audit.py <model> [key=value ...]: WHAT THE JOINT SOLVE READS on a block-in model's pictures, nothing applied.
Per observation group (type, view): count and sigma; per measure (solve_report.rows: gnm_mm's 27, the chin set, the
macro words): prior sd -> posterior sd, read, which groups read it; the moved-without-a-read report against the
block-in's root. keys as cmp.py (cameras=free|trust|refit, anchors=, parse=, rounds=) + region=<solve_report.REGIONS key>
+ root=<model> (the start head, default the block-in's root) + save=<npz>."""
import sys, time, json
import numpy as np
from hifipushie import face_ruler as fr, blockin as bi, store, solve_report as sr

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
cams = kw.pop("cameras", "free")
region = kw.pop("region", None)
save = kw.pop("save", None)
k = 1.0 / 3.0 if cams == "trust" else 1.0
cam_sd = {kk: tuple(k * x for x in v) for kk, v in fr.PHOTO_CAM_SD6.items()}
val = lambda v: {"0": False, "1": True}.get(v, v)  # noqa: E731
rj = bi._refs(m)
root = kw.pop("root", None) or (rj.get("blockin") or {}).get("root")
args = {"lids": True, "lips": True, "parse": "auto", "adapt": True, "cmax": 3.0, **{a: val(b) for a, b in kw.items()}}
if "cmax" in kw:
    args["cmax"] = float(kw["cmax"]) or None
rounds = int(args.pop("rounds", 1))
c0 = bi.identity(store.load(m))
croot = bi.identity(store.load(root)) if root else np.zeros(170)
t = time.time()
cam0 = None if cams == "refit" else (rj.get("blockin") or {}).get("cam_done")
c = fr.compare(m, rounds=rounds, prior_off=c0 - croot, cam_sd=cam_sd, cam_first=2 if cams == "refit" else 0,
               cam_done0=cam0 if cam0 is not None else np.zeros((len(rj["views"]), 6)), **args)
dc = np.asarray(c["dc"], float)
print(f"== {m} (root {root}) {args} cameras={cams}: {time.time() - t:.0f} s; |dc| {np.linalg.norm(dc):.2f}, relax x{c['relax']:.2f}")
yaws = [abs(float(v["cam"].get("yaw", 0.0))) for v in c["views"]]
print("views:", ", ".join(f"{v['kind']} (camera yaw {y:.0f})" for v, y in zip(c["views"], yaws)))
w = np.asarray(c["post"]["w"], float)
print("observation groups (type, view): n, stated sigma mm, effective sigma mm (after adapt / relax / robust loss):")
G = {}
for i, ob in enumerate(c["obs"]):
    G.setdefault((ob["type"], ob["view"]), []).append(i)
for key, ii in sorted(G.items()):
    sg = np.array([c["obs"][i]["sig"] for i in ii])
    o = np.array([c["obs"][i]["o"] for i in ii])
    print(f"  {key[0]:9s} {key[1]:10s} n {len(ii):4d}  sigma {np.median(sg):.2f}  effective {np.median(1 / np.sqrt(w[ii])):.2f}  residual rms {np.sqrt((o ** 2).mean()):.2f}")
sup = sr.support(c["post"], c["obs"])
drc = sr.direct(c["post"], c["obs"], c["views"], c["head"])
rep = sr.report(sup, c0 + dc, croot, turned=max(yaws), drc=drc)
for reg in ([region] if region else list(sr.REGIONS)):
    print(f"\n-- {reg} (moved = since the root; * = UNREAD)")
    print(sr.table_text(rep, reg))
print("\n" + rep["text"])
if save:
    np.savez(save, names=np.array(sup["names"]), read=drc["read"], model_read=sup["read"], prior=sup["prior"], post=sup["post"],
             moved=np.array([r["moved"] for r in rep["rows"]]), by=json.dumps({n: [(f"{a[0]} {a[1]}", s) for a, s in v[:3]] for n, v in sup["by"].items()}))
