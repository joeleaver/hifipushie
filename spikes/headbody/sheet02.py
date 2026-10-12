"""sheet02.py <glb> <tag> [out png]: the neck's seam on an exported two-mesh GLB: rest | head turned 45 | neck bent,
views front / side / back; rows shaded (the GLB as an engine draws it, Cycles) / raking (clay, the GLB's OWN normals
skinned per mesh, never welded across the seam) / wire (head grey, body blue, the seam ring red).
Prints the seam's numbers per pose: gap between the two meshes' ring vertices, normal difference, weight difference."""
import os, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "onemesh"))
import wire
from hifipushie import asset, render, resources, rig as rigmod, rig_audit, store

glb, tag = Path(sys.argv[1]), sys.argv[2]
out = sys.argv[3] if len(sys.argv) > 3 else f"/mnt/data/hifipushie/headbody/out/seam_{tag}.png"
FAST = os.environ.get("FAST")
g = rig_audit.read_glb(glb)
bones, M = g["bones"], g["meshes"]
names = [b["name"] for b in bones]
print("meshes:", {k: (len(m["V"]), len(m["F"]), len(m.get("targets") or {})) for k, m in M.items()})
hk = next(k for k in M if k.endswith("head"))
bk = next(k for k in M if k.endswith("body"))
H, Bd = M[hk], M[bk]
# the seam: vertices of the two meshes at one place
d, j = cKDTree(Bd["V"]).query(H["V"])
hi = np.flatnonzero(d < 1e-6)
bi = j[hi]
print(f"seam: {len(hi)} head vertices coincide with body vertices at rest ({len(np.unique(np.round(H['V'][hi], 6), axis=0))} places)")


def dense(m, rows):
    W = np.zeros((len(rows), len(bones)))
    for c in range(m["J"].shape[1]):
        np.add.at(W, (np.arange(len(rows)), m["J"][rows, c]), m["W"][rows, c])
    return W


print(f"  rest: normals differ by at most {np.degrees(np.arccos(np.clip((H['N'][hi] * Bd['N'][bi]).sum(1), -1, 1))).max():.3f} deg (nearest pair; uv-split copies excluded below), "
      f"weights by {np.abs(dense(H, hi) - dense(Bd, bi)).max():.2e}")


def mats(turns):
    n = len(bones)
    T = np.tile(np.eye(4), (n, 1, 1))
    for i, b in enumerate(bones):
        L = np.eye(4)
        if b["name"] in turns:
            ax, deg = turns[b["name"]]
            ax = np.asarray(ax, float) / np.linalg.norm(ax)
            t = np.radians(deg)
            K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
            R = np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K
            h = np.asarray(b["head"], float)
            L[:3, :3], L[:3, 3] = R, h - R @ h
        T[i] = (T[b["parent"]] if b["parent"] >= 0 else np.eye(4)) @ L
    return T


def skin(m, T):
    V4 = np.c_[m["V"], np.ones(len(m["V"]))]
    P, N = np.zeros((len(V4), 3)), np.zeros((len(V4), 3))
    for c in range(m["J"].shape[1]):
        Tc = T[m["J"][:, c]]
        P += m["W"][:, c:c + 1] * np.einsum("nij,nj->ni", Tc, V4)[:, :3]
        N += m["W"][:, c:c + 1] * np.einsum("nij,nj->ni", Tc[:, :3, :3], m["N"])
    return P, N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)


P_ = rigmod.PREFIX
up = [0.0, 0.0, 1.0]
POSES = [("REST", {}), ("HEAD TURNED 45", {P_ + "Neck": (up, 15.0), P_ + "Head": (up, 30.0)}),
         ("NECK BENT 35", {P_ + "Neck": ([1.0, 0, 0], -20.0), P_ + "Head": ([1.0, 0, 0], -15.0)})]
VIEWS = [("front", 0, 0), ("side", 90, 0), ("back", 180, 0)]
neck = np.asarray(bones[names.index(P_ + "Neck")]["head"], float)
headj = np.asarray(bones[names.index(P_ + "Head")]["head"], float)
c = 0.5 * (neck + headj) + [0, 0, 0.01]
SIZE, T_ = 0.30, 430
F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)  # noqa: E731
rows_n = ["wire", "raking"] + ([] if FAST else ["shaded"])
sheet = Image.new("RGB", (len(POSES) * len(VIEWS) * T_ + 150, len(rows_n) * T_ + 120), (250, 250, 250))
dr = ImageDraw.Draw(sheet)
spec_name = tag
rak = str(render.raking_matcap(store.HOME / "raking_matcap.png"))
with resources.heavy(f"headbody seam sheet {tag}", gb=8):
    for pi, (pname, turns) in enumerate(POSES):
        T = mats(turns)
        Ph, Nh = skin(H, T)
        Pb, Nb = skin(Bd, T)
        gap = np.linalg.norm(Ph[hi] - Pb[bi], axis=1).max()
        # normals: every head corner copy against every body copy at the same place
        key = np.round(H["V"][hi] * 1e5).astype(np.int64)
        worst = 0.0
        for a_, b_ in zip(hi, bi):
            worst = max(worst, float(np.degrees(np.arccos(np.clip(Nh[a_] @ Nb[b_], -1, 1)))))
        print(f"  {pname}: largest gap between the two meshes at the seam {gap * 1e6:.2f} um; largest normal difference {worst:.3f} deg")
        dr.text((150 + pi * len(VIEWS) * T_ + 10, 8), f"{pname}", font=F(34), fill=(20, 20, 20))
        dr.text((150 + pi * len(VIEWS) * T_ + 10, 52), f"seam gap {gap * 1e3:.4f} mm   normal step {worst:.2f} deg", font=F(22), fill=(20, 110, 40) if gap < 1e-5 and worst < 0.5 else (170, 30, 30))
        V = np.r_[Pb, Ph]
        Fc = np.r_[Bd["F"], H["F"] + len(Pb)]
        N = np.r_[Nb, Nh]
        cp = c if not turns else (skin({"V": c[None], "N": np.array([[0, 0, 1.0]]), "J": np.array([[names.index(P_ + "Neck")]]), "W": np.ones((1, 1))}, T)[0][0])
        ring = set((hi + len(Pb)).tolist())
        hedges = [(int(f[k]), int(f[(k + 1) % 3])) for f in Fc[len(Bd["F"]):] for k in range(3) if int(f[k]) in ring and int(f[(k + 1) % 3]) in ring]
        col = [(170, 190, 215)] * len(Bd["F"]) + [(205, 200, 192)] * len(H["F"])
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "posed.npz"
            np.savez(f, verts=V.astype(np.float32), faces=Fc, normals=N.astype(np.float32))
            frames = [dict(fr, scale=SIZE) for fr in render.view_frames(V, [v for v, _, _ in VIEWS], focus=cp, zoom=1.0)]
            for fr in frames:
                fr["scale"] = SIZE
            rimgs = render.render_views(f, frames, T_, rak)
        simgs = None
        if not FAST:
            one = {"turns": {k: [*(float(x) for x in v[0]), float(v[1])] for k, v in turns.items()}}
            try:
                sh = asset.preview(glb, [], size=T_, samples=32, poses=[one],
                                   cameras=[{"eye": (cp + 1.6 * np.array([np.sin(np.radians(az)), -np.cos(np.radians(az)), 0.05])).tolist(),
                                             "target": cp.tolist(), "fov": 11.0, "name": v} for v, az, _ in VIEWS])[0]
                simgs = sh
            except Exception as e:
                print("no shaded row:", str(e)[:300])
        for vi, (v, az, el) in enumerate(VIEWS):
            x = 150 + (pi * len(VIEWS) + vi) * T_
            sheet.paste(wire.view(V, [list(t) for t in Fc], cp, SIZE, az=az, el=el, px=T_, colors=col, hi_edges=hedges, edge=(70, 70, 76)), (x, 100))
            sheet.paste(rimgs[vi].convert("RGB").resize((T_, T_)), (x, 100 + T_))
            dr.text((x + 8, 100 + 4), v, font=F(20), fill=(20, 20, 20))
        if simgs is not None:
            im = simgs.convert("RGB")
            w = len(POSES) and len(VIEWS) * T_
            im = im.resize((w, int(w * im.height / im.width)))
            sheet.paste(im.crop((0, 0, w, T_)), (150 + pi * len(VIEWS) * T_, 100 + 2 * T_))
for ri, rn in enumerate(rows_n):
    dr.text((10, 100 + ri * T_ + T_ // 2 - 20), rn.upper(), font=F(28), fill=(20, 20, 20))
sheet.save(out)
print("saved", out)
