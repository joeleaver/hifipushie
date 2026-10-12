"""cmp.py <model> [key=value ...]: the joint solve's READ of a block-in model WITHOUT applying it (what block_in_solve
would do): reads by type, the step's size, |c| after it, the largest component, per-type residual before the solve.
keys: anchors=differential|absolute|none, parse=0|1|auto, normals=0|1, cameras=free|trust, lids=1, lips=1, rounds=3."""
import sys, time
import numpy as np
from hifipushie import face_ruler as fr, blockin as bi, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
cams = kw.pop("cameras", "free")
save = kw.pop("save", None)
k = 1.0 / 3.0 if cams == "trust" else 1.0
cam_sd = {kk: tuple(k * x for x in v) for kk, v in fr.PHOTO_CAM_SD6.items()}


def val(v):
    return {"0": False, "1": True}.get(v, v)


args = {"lids": True, "lips": True, "parse": "auto", "adapt": True, "cmax": 3.0, **{a: val(b) for a, b in kw.items()}}
if "cmax" in kw:
    args["cmax"] = float(kw["cmax"]) or None
rounds = int(args.pop("rounds", 3))
c0 = bi.identity(store.load(m))
root = (bi._refs(m).get("blockin") or {}).get("root")
off = c0 - bi.identity(store.load(root)) if root else None
t = time.time()
cam0 = None if cams == "refit" else (bi._refs(m).get("blockin") or {}).get("cam_done")
c = fr.compare(m, rounds=rounds, prior_off=off, cam_sd=cam_sd, cam_first=2 if cams == "refit" else 0,
               cam_done0=cam0 if cam0 is not None else np.zeros((len(bi._refs(m)["views"]), 6)), **args)
dc = np.asarray(c["dc"], float)
print(f"{m} {args} cameras={cams}: {time.time() - t:.0f} s")
print("reads", c["n"])
print(f"|dc| {np.linalg.norm(dc):.2f}  |c| {np.linalg.norm(c0):.2f} -> {np.linalg.norm(c0 + dc):.2f}  largest comp {np.abs(c0 + dc).max():.2f} sd "
      f"(#{int(np.abs(c0 + dc).argmax())}); comps past 2.5 sd: {int((np.abs(c0 + dc) > 2.5).sum())}")
print("LAST round's residuals (o, mm; the picture - the solved head before its last step), by type and view:")
for typ in sorted({ob["type"] for ob in c["obs"]}):
    for vw in sorted({ob["view"] for ob in c["obs"] if ob["type"] == typ}):
        o = np.array([ob["o"] for ob in c["obs"] if ob["type"] == typ and ob["view"] == vw])
        sg = np.array([ob["sig"] for ob in c["obs"] if ob["type"] == typ and ob["view"] == vw])
        print(f"  {typ:9s} {vw:10s} n {len(o):4d}  mean {o.mean():+6.2f}  rms {np.sqrt((o ** 2).mean()):5.2f}  sig {sg.mean():.2f}")
print("relax", c["relax"], "sigma scales", {k_: round(v_, 2) for k_, v_ in c["sig_scale"].items() if v_ > 1.2})
print("cameras moved:", np.round(np.asarray(c["cam_done"], float), 2).tolist())
print("\n".join(c["notes"]))
if save:
    np.save(save, c0 + dc)
