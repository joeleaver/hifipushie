"""Shared evaluation for the topology spike: region errors, posed wire renders, sizing field, QuadriFlow binary."""
import json
import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from hifipushie import rig, sdf, store, surface
from hifipushie.spec import compile_prims

SP = Path(__file__).parent
QF = SP / "QuadriFlow" / "build" / "quadriflow"
NAME = os.environ.get("MODEL", "troll")
spec = store.load(NAME)
prims = [p for p in compile_prims(spec) if p.part == "body"]
meta = store.build(NAME, 160)
voxel = meta["voxel"]
z = np.load(meta["mesh"])
keep = np.flatnonzero(z["part"] == 0)
remap = -np.ones(len(z["part"]), int)
remap[keep] = np.arange(len(keep))
HF = remap[z["faces"]]
HF = HF[(HF >= 0).all(1)]
HV = z["verts"][keep].astype(np.float64)
HN = z["normals"][keep].astype(np.float64)
bones = rig.humanoid(spec)
seg = rig._segments(bones)
ids = list(seg)
A = np.array([seg[i][0] for i in ids])
B = np.array([seg[i][1] for i in ids])
segnames = [bones[i]["name"].split(":")[-1] for i in ids]
D = np.stack([rig._seg_dist(HV, A[q], B[q]) for q in range(len(ids))], 1)
near = D.argmin(1)
REGION = np.array(["hands" if "Hand" in segnames[q] else "head" if segnames[q] in ("Head", "Neck") else "rest"
                   for q in near])


def blender(job, out_dir):
    p = Path(out_dir) / f"job_{job['mode']}.json"
    p.write_text(json.dumps(job))
    r = subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python",
                        str(SP / "topo_blender.py"), "--", str(p)], capture_output=True, text=True, timeout=1800)
    if r.returncode:
        raise RuntimeError(r.stdout[-3000:] + r.stderr[-3000:])


def edges_of(F):
    e = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    return np.unique(e, axis=0)


def smooth(x, F, rounds):
    e = edges_of(F)
    n = len(x)
    deg = np.bincount(e.ravel(), minlength=n).astype(float)
    for _ in range(rounds):
        acc = np.zeros_like(x)
        np.add.at(acc, e[:, 0], x[e[:, 1]])
        np.add.at(acc, e[:, 1], x[e[:, 0]])
        x = 0.5 * x + 0.5 * acc / np.maximum(deg, 1)
    return x


def vertex_area(V, F):
    a = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    out = np.zeros(len(V))
    for k in range(3):
        np.add.at(out, F[:, k], a / 3)
    return out


BEND = ("LeftArm", "RightArm", "LeftForeArm", "RightForeArm", "LeftHand", "RightHand", "LeftUpLeg", "RightUpLeg",
        "LeftLeg", "RightLeg", "LeftFoot", "RightFoot", "Neck", "Head")


def kmax(rounds=4):
    """Largest principal curvature per vertex: the fastest turn of the field normal along an incident edge,
    averaged a little over the mesh (saddles on a face register, unlike mean curvature)."""
    e = edges_of(HF)
    k = np.linalg.norm(HN[e[:, 0]] - HN[e[:, 1]], axis=1) / np.linalg.norm(HV[e[:, 0]] - HV[e[:, 1]], axis=1)
    out = np.zeros(len(HV))
    np.maximum.at(out, e[:, 0], k)
    np.maximum.at(out, e[:, 1], k)
    return smooth(out, HF, rounds)


def sizing(k=0.3, joint=0.35, lo=0.25, hi=1.6, curv_rounds=4):
    """Relative edge length per high vertex: curvature-limited (edge <= k / |mean curvature|: a cylinder of
    radius r gets ~pi/k... segments around), shortened near bending joints (extra loops), normalised so the face
    count stays at the target."""
    H = kmax(curv_rounds)
    area = vertex_area(HV, HF)
    e0 = np.sqrt(area.sum() / 5000)  # a reference; normalisation removes it
    s = np.clip(k / np.maximum(H, 1e-6) / e0, 0, 1e9)
    heads = {b["name"].split(":")[-1]: np.asarray(b["head"]) for b in bones}
    for n in BEND:
        if n in heads:
            d = np.linalg.norm(HV - heads[n], axis=1)
            r = float(np.percentile(d, 0.5)) + 0.02  # about the limb's radius there
            s *= 1 - joint * np.exp(-(d / (1.2 * r)) ** 2)
    s = smooth(s, HF, 10)
    s = np.clip(s / np.median(s), lo, hi)
    c = np.sqrt((area / s ** 2).sum() / area.sum())
    return s * c


def write_obj(path, V, F):
    with open(path, "w") as f:
        f.write("".join(f"v {x:.6f} {y:.6f} {z:.6f}\n" for x, y, z in V))
        f.write("".join(f"f {a + 1} {b + 1} {c + 1}\n" for a, b, c in F))


def read_obj(path):
    V, L, S = [], [], []
    for line in open(path):
        t = line.split()
        if not t:
            continue
        if t[0] == "v":
            V.append([float(x) for x in t[1:4]])
        elif t[0] == "f":
            f = [int(x.split("/")[0]) - 1 for x in t[1:]]
            L += f
            S.append(len(f))
    return np.array(V), np.array(L), np.array(S)


def quadriflow(out_dir, faces, size=None, lam=10, adaptive=True):
    out_dir = Path(out_dir)
    src = out_dir / "high.obj"
    if not src.exists():
        write_obj(src, HV, HF)
    env = dict(os.environ)
    if size is not None:
        np.savetxt(out_dir / "sizing.txt", size, fmt="%.5f")
        env["QF_SIZING"] = str(out_dir / "sizing.txt")
        env["QF_LAMBDA"] = str(lam)
    out = out_dir / f"qf_{faces}.obj"
    args = [str(QF), "-i", str(src), "-o", str(out), "-f", str(faces), "-seed", "0"] + (["-adaptive"] if adaptive else [])
    r = subprocess.run(args, env=env, capture_output=True, text=True, timeout=1800)
    if r.returncode or not out.exists():
        raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
    return read_obj(out)


def tris(V, L, S):
    st = np.r_[0, np.cumsum(S)[:-1]]
    T = []
    for s0, n in zip(st, S):
        f = L[s0:s0 + n]
        if n == 4 and np.linalg.norm(V[f[0]] - V[f[2]]) > np.linalg.norm(V[f[1]] - V[f[3]]):
            T += [(f[1], f[2], f[3]), (f[1], f[3], f[0])]
        else:
            T += [(f[0], f[j], f[j + 1]) for j in range(1, n - 1)]
    return np.array(T)


def errors(V, T):
    """Field -> mesh distance (high vertices to a dense sampling of the triangles) per region, mm: mean, p95;
    and mesh -> field |f| mean."""
    u = np.linspace(0, 1, 7)
    U, W = np.meshgrid(u, u)
    m = U + W <= 1
    bc = np.c_[1 - U[m] - W[m], U[m], W[m]]
    S = np.einsum("kb,tbx->tkx", bc, V[T]).reshape(-1, 3)
    d = cKDTree(S).query(HV)[0] * 1000
    out = {r: (round(float(d[REGION == r].mean()), 2), round(float(np.percentile(d[REGION == r], 95)), 1))
           for r in ("rest", "head", "hands")}
    out["all"] = (round(float(d.mean()), 2), round(float(np.percentile(d, 95)), 1), round(float(d.max()), 1))
    return out


turns = rig.test_pose(bones)
_heads = np.array([b["head"] for b in bones])
_Jh = np.arange(len(bones))[:, None]
_PH = rig.pose(bones, _heads, _Jh, np.ones_like(_Jh, float), turns)
AT = {b["name"].split(":")[-1]: _PH[i] for i, b in enumerate(bones)}
VIEWS = [("front", [0, -1, 0], None, 1.15, False), ("front wire", [0, -1, 0], None, 1.15, True),
         ("R shoulder", [0, -1, 0], "RightArm", 0.32, True), ("L elbow", [1, 0, 0], "LeftForeArm", 0.26, True),
         ("R knee", [-1, 0, 0], "RightLeg", 0.3, True), ("face", [0.3, -1, 0.1], "Head", 0.3, True),
         ("L hand", [0.2, -1, 0.2], "LeftHand", 0.2, True)]


def posed_row(name, V, L, S, out_dir, size=480, rings=()):
    """Skin with the rig weights, pose with the test pose, render the views; returns the images."""
    out_dir = Path(out_dir)
    T = tris(V, L, S)
    J, W = rig.rig_weights(spec, bones, V, T)
    PV = rig.pose(bones, V, J, W, turns)
    np.savez(out_dir / f"{name}_posed.npz", verts=PV, loops=L, sizes=S)
    c = 0.5 * (PV.min(0) + PV.max(0))
    vs = []
    for vn, d, focus, scale, wire in VIEWS:
        foc = c if focus is None else AT[focus]
        if vn == "face":
            foc = AT["Head"] + np.array([0, -0.05, 0.06])
        vs.append({"dir": d, "up": [0, 0, 1], "center": np.asarray(foc).tolist(), "scale": scale, "wire": wire,
                   "out": str(out_dir / f"{name}_{vn.replace(' ', '_')}.png")})
    blender({"mode": "render", "mesh": str(out_dir / f"{name}_posed.npz"), "views": vs, "size": size,
             "rings": [PV[r].tolist() for r in rings]}, out_dir)
    return [Image.open(v["out"]).convert("RGB") for v in vs]


def sheet(rows, path, size=480):
    lh = 26
    im = Image.new("RGB", (size * len(VIEWS), (size + lh) * len(rows) + lh), (30, 31, 35))
    d = ImageDraw.Draw(im)
    for j, v in enumerate(VIEWS):
        d.text((j * size + 8, 6), v[0], fill=(230, 230, 230))
    for i, (label, ims) in enumerate(rows):
        d.text((8, lh + i * (size + lh) + 6), label, fill=(230, 230, 230))
        for j, x in enumerate(ims):
            im.paste(x, (j * size, 2 * lh + i * (size + lh)))
    im.save(path)
