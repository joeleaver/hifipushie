"""QuadriFlow with our sizing field vs plain QuadriFlow vs decimation, at one budget: errors + posed renders."""
import sys
import time
from pathlib import Path

import numpy as np

import topo_eval as E

TRI = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
OUT = E.SP / f"qfa_{TRI}"
OUT.mkdir(exist_ok=True)
np.savez(OUT / "high.npz", verts=E.HV, faces=E.HF)

t = time.time()
size = E.sizing(k=0.5, curv_rounds=6)
print(f"sizing {time.time() - t:.1f}s: range {size.min():.2f}..{size.max():.2f}, "
      + ", ".join(f"{r} median {np.median(size[E.REGION == r]):.2f}" for r in ("rest", "head", "hands")))
meshes = {}
t = time.time()
m = E.quadriflow(OUT, TRI // 2, size)
m = E.quadriflow(OUT, int(TRI // 2 * TRI / len(E.tris(*m))), size)  # one calibration step to the budget
meshes["qf sized"] = m
print(f"qf sized {time.time() - t:.1f}s")
t = time.time()
m = E.quadriflow(OUT, TRI // 2, None, adaptive=False)
meshes["qf plain"] = E.quadriflow(OUT, int(TRI // 2 * TRI / len(E.tris(*m))), None, adaptive=False)
print(f"qf plain {time.time() - t:.1f}s")
E.blender({"mode": "decimate", "mesh": str(OUT / "high.npz"), "triangles": TRI, "out": str(OUT / "dec.npz")}, OUT)
k = np.load(OUT / "dec.npz")
meshes["decimate"] = (k["verts"].astype(float), k["loops"], k["sizes"])
rows = []
for name, (V, L, S) in meshes.items():
    T = E.tris(V, L, S)
    e = E.errors(V, T)
    label = (f"{name}: {len(T)} tris, {(S == 4).sum()} quads; field->mesh mean/p95 mm: all {e['all'][0]}/{e['all'][1]} "
             f"(max {e['all'][2]}), rest {e['rest'][0]}/{e['rest'][1]}, head {e['head'][0]}/{e['head'][1]}, "
             f"hands {e['hands'][0]}/{e['hands'][1]}")
    print(label, flush=True)
    rows.append((label, E.posed_row(name.replace(" ", "_"), V, L, S, OUT)))
E.sheet(rows, OUT / "compare.png")
