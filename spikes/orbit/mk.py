"""mk.py <src> <dst ob_*> [mm:<measure>=<mm> ...] [yaw:<view index>=<deg> ...] [table]: a SCRATCH copy of a block-in
model with mm: moves added to its identity (and a reference camera turned: the ruler's solved yaw). Reports the cost
and what else moved: |dc|, the 27 measures, the shipped head's skin (mm, by region), our eyeball and the lid's
clearance over it, the eye ruler's margin rows on the mesh, and with `table` the block-in target table's changes."""
import copy
import json
import shutil
import sys

import numpy as np

from hifipushie import blockin as bi, blockin_eyes as be, blockin_lid as bl, face_ruler as fr, gnm_mm, onemesh, store

src, dst = sys.argv[1:3]
assert dst.startswith("ob_"), "scratch models are ob_*"
moves = {a.split("=")[0]: float(a.split("=")[1]) for a in sys.argv[3:] if a.startswith("mm:")}
yaws = {int(a.split("=")[0][4:]): float(a.split("=")[1]) for a in sys.argv[3:] if a.startswith("yaw:")}
sp = copy.deepcopy(store.load(src))
c0 = bi.identity(sp)
dc = sum((v * gnm_mm.direction(k) for k, v in moves.items()), np.zeros(170))
c1 = c0 + dc
bi.set_identity(sp, c1)
sp.pop("hair", None)
d = store._dir(dst)
d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp))
rj = json.loads((store._dir(src) / "human_refs.json").read_text())
if "mm:eyes_forward" in moves:      # as block_in_step: the cameras follow the face (the head hangs on its eyes)
    dd = bi.eye_follow(store.load(src)["base"], sp["base"])
    for cam in rj["cameras"]:
        cam["centre"] = (np.asarray(cam["centre"], float) + dd).tolist()
    print(f"cameras follow the face: {1000 * dd.round(5)} mm")
for vi, deg in yaws.items():
    rj["cameras"][vi] = fr.cam_moved(rj["cameras"][vi], yaw=deg)
(d / "human_refs.json").write_text(json.dumps(rj, indent=1))
print(f"{dst} = {src} + {moves}" + (f", cameras turned {yaws}" if yaws else ""))
print(f"  |dc| {np.linalg.norm(dc):.2f} (|c| {np.linalg.norm(c0):.2f} -> {np.linalg.norm(c1):.2f})")
g = gnm_mm._space()
r0, r1 = gnm_mm.readers(g["T"] + np.tensordot(c0, g["IB"], 1)), gnm_mm.readers(g["T"] + np.tensordot(c1, g["IB"], 1))
print("  measures moved: " + ", ".join(f"{n} {r1[n] - r0[n]:+.2f}" for n in gnm_mm.HELD if abs(r1[n] - r0[n]) > 0.05))
o0, o1 = gnm_mm.orbit(g["T"] + np.tensordot(c0, g["IB"], 1)), gnm_mm.orbit(g["T"] + np.tensordot(c1, g["IB"], 1))
print("  orbit as seen (GNM mm): " + ", ".join(f"{k} {o0[k]:.1f} -> {o1[k]:.1f}" for k in o0))
b0 = store.load(src)["base"]
h0, h1 = onemesh.head_template(b0), onemesh.head_template(sp["base"])
V0, V1 = np.asarray(h0["verts"], float), np.asarray(h1["verts"], float)
ring, up = bl._skin_rings()
n = len(ring)
dd_ = bi.eye_follow(b0, sp["base"])
D = np.linalg.norm(V1[:n] - V0[:n] - dd_, axis=1) * 1000          # (against the face: the cameras' frame)
print(f"  the face (landmarks off the eyes) moved {1000 * dd_.round(5)} mm in the shipped head: taken out below")
from hifipushie import base as basemod  # noqa: E402
gr = basemod._gnm_data()["groups"]
sk = np.flatnonzero(np.asarray(basemod._gnm_data()["skin"]))
face = np.asarray(gr["hockey_mask"])[sk] > 0.5
print(f"  shipped head, skin move (mm): lid rings 0-7 rms {np.sqrt((D[ring <= 7] ** 2).mean()):.2f}; orbit rings 8-14 {np.sqrt((D[(ring > 7) & (ring < 99)] ** 2).mean()):.2f}; "
      f"the face beyond {np.sqrt((D[face & (ring == 99)] ** 2).mean()):.2f} (max {D[face & (ring == 99)].max():.2f}); the rest of the head "
      f"{np.sqrt((D[~face] ** 2).mean()):.2f} (max {D[~face].max():.2f})")
for nm in ("nose_region", "upper_lip_region", "lower_lip_region", "chin_region", "forehead_region", "left_cheek_region", "left_zygomatic_region", "ears"):
    m = np.asarray(gr[nm])[sk] > 0.5
    print(f"     {nm:22s} rms {np.sqrt((D[m] ** 2).mean()):.2f} max {D[m].max():.2f}")
e0, e1 = np.asarray(h0["eyes"], float), np.asarray(h1["eyes"], float)
f = np.asarray(h0["forward"], float)
print(f"  our eyeballs moved against the face {1000 * np.linalg.norm(e1 - e0 - dd_, axis=1).round(5)} mm, along the face's forward {1000 * ((e1 - e0 - dd_) @ f).round(5)}")
print(f"  lid over our eyeball: least stand-off {bl.ball_clearance(h0)['min']:.2f} -> {bl.ball_clearance(h1)['min']:.2f} mm")
m0, m1 = be.Reader(h0).margins(h0), be.Reader(h1).margins(h1)
print(f"  eye ruler rows on the mesh: upper margin moved max {np.nanmax(np.abs(m1['up'] - m0['up'])):.2f} mm, lower {np.nanmax(np.abs(m1['lo'] - m0['lo'])):.2f}, "
      f"inner canthus {np.abs(m1['inner'] - m0['inner']).max():.2f}, ring's outer end {np.abs(m1['ring_out'] - m0['ring_out']).max():.2f}")
s0, s1 = bl.mean_structure(c0), bl.mean_structure(c1)
print("  lid structure (raw): " + ", ".join(f"{k} {s0[k]:.2f} -> {s1[k]:.2f}" for k in s0))
if "table" in sys.argv:
    t0, t1 = bi.table(src), bi.table(dst)
    print("  block-in table passes:", bi.passes(t0), "->", bi.passes(t1))
    for x in bi.table_delta(t0, t1):
        print("    " + x)
