import json, subprocess, sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from hifipushie import rig, sdf, store
from hifipushie.spec import compile_prims
SP = Path(__file__).parent; OUT = SP / "curve"; OUT.mkdir(exist_ok=True)
spec = store.load("troll"); prims = [p for p in compile_prims(spec) if p.part == "body"]
z = np.load(SP / "troll" / "high.npz"); HV, HF = z["verts"], z["faces"]
bones = rig.humanoid(spec)
seg = rig._segments(bones); ids = list(seg)
A = np.array([seg[i][0] for i in ids]); B = np.array([seg[i][1] for i in ids])
nm = [bones[i]["name"].split(":")[-1] for i in ids]
near = np.argmin(np.stack([rig._seg_dist(HV, A[q], B[q]) for q in range(len(ids))], 1), 1)
reg = np.array(["hands" if "Hand" in nm[q] else "head" if nm[q] in ("Head", "Neck") else "rest" for q in near])
def blender(job):
    p = OUT / "job.json"; p.write_text(json.dumps(job))
    r = subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(SP / "topo_blender.py"), "--", str(p)], capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
def tris(k):
    L, S = k["loops"], k["sizes"]; st = np.r_[0, np.cumsum(S)[:-1]]
    return np.array([(L[s], L[s + j], L[s + j + 1]) for s, n in zip(st, S) for j in range(1, n - 1)])
def err(V, T):
    u = np.linspace(0, 1, 7); U, W = np.meshgrid(u, u); m = U + W <= 1
    bc = np.c_[1 - U[m] - W[m], U[m], W[m]]
    S = np.einsum("kb,tbx->tkx", bc, V[T]).reshape(-1, 3)
    d = cKDTree(S).query(HV)[0] * 1000
    return {r: (round(float(d[reg == r].mean()), 2), round(float(np.percentile(d[reg == r], 95)), 1)) for r in ("rest", "head", "hands")}
res = []
for tri in (2500, 5000, 10000, 20000, 40000):
    for mode in ("quadriflow", "decimate"):
        out = OUT / f"{mode}_{tri}.npz"
        blender({"mode": mode, "mesh": str(SP / "troll" / "high.npz"), "faces": tri // 2, "triangles": tri, "out": str(out)})
        k = np.load(out); T = tris(k)
        e = err(k["verts"].astype(float), T)
        res.append((mode, len(T), e)); print(mode, len(T), e, flush=True)
json.dump(res, open(OUT / "curve.json", "w"))
