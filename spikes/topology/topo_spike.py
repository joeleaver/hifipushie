"""Character topology spike: skin-modifier quads vs QuadriFlow vs decimation on the troll's body."""
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from hifipushie import rig, sdf, store, surface
from hifipushie.spec import compile_prims, expand_mirror, resolve_point

SP = Path(__file__).parent
BL = SP / "topo_blender.py"
NAME = sys.argv[1] if len(sys.argv) > 1 else "troll"
OUT = SP / __import__("os").environ.get("OUTDIR", NAME)
OUT.mkdir(exist_ok=True)
BEND = ("Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot", "Head")
HULL = float(__import__("os").environ.get("HULL", 0.5))  # skin radii as a fraction of the measured ones


def blender(job):
    p = OUT / f"job_{job['mode']}.json"
    p.write_text(json.dumps(job))
    r = subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(BL), "--",
                        str(p)], capture_output=True, text=True, timeout=1800)
    if r.returncode:
        raise RuntimeError(r.stdout[-3000:] + r.stderr[-3000:])
    return [l for l in r.stdout.splitlines() if l.startswith("@@")]


spec = store.load(NAME)
s = expand_mirror(spec)
prims = [p for p in compile_prims(spec) if p.part == "body"]
meta = store.build(NAME, 160)
voxel = meta["voxel"]
z = np.load(meta["mesh"])
body = z["part"] == 0
keep = np.flatnonzero(body)
remap = -np.ones(len(body), int)
remap[keep] = np.arange(len(keep))
HF = remap[z["faces"]]
HF = HF[(HF >= 0).all(1)]
HV = z["verts"][keep].astype(np.float64)
np.savez(OUT / "high.npz", verts=HV, faces=HF)
bones = rig.humanoid(spec)


def radius(p, d, reach=0.35, n=16):
    """Median distance to where rays perpendicular to d leave the body."""
    d = d / np.linalg.norm(d)
    a = np.cross(d, [0, 0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0, 0])
    a /= np.linalg.norm(a)
    b = np.cross(d, a)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    dirs = np.cos(ang)[:, None] * a + np.sin(ang)[:, None] * b
    t = np.linspace(0, reach, 176)
    f = sdf.field_at(prims, p + t[None, :, None] * dirs[:, None, :], margin=0.02)
    out = []
    for row in f:
        k = np.flatnonzero(row > 0)
        out.append(t[k[0]] if len(k) else reach)
    return float(np.median(out)) if f[0, 0] < 0 else 0.0


# ---- the graph: rig bone heads, the skull centre, ears ----
names = [b["name"].split(":")[-1] for b in bones]
P = [np.asarray(b["head"], float) for b in bones]
E = [(b["parent"], i) for i, b in enumerate(bones) if b["parent"] >= 0]
hi, ti = names.index("Head"), names.index("HeadTop_End")
E.remove((hi, ti))
P.append(resolve_point(s, "head")); names.append("skull")
E += [(hi, len(P) - 1), (len(P) - 1, ti)]
sk = len(P) - 1
for side in "LR":
    if f"ear0.{side}" in s["joints"]:
        P.append(resolve_point(s, f"ear0.{side}")); names.append(f"ear0.{side}"); E.append((sk, len(P) - 1))
        P.append(resolve_point(s, f"ear1.{side}")); names.append(f"ear1.{side}"); E.append((len(P) - 2, len(P) - 1))
SKIP = {"Neck", "LeftShoulder", "RightShoulder"}  # hub-crowding nodes: Spine2 becomes a clean cross
for i in sorted((i for i, n in enumerate(names) if n in SKIP), reverse=True):
    par = [a for a, b in E if b == i][0]
    E = [(par if a == i else a, b) for a, b in E if b != i]
E = [(a, b) for a, b in E]
P = np.array(P)
nbr = {i: [] for i in range(len(P))}
for a, b in E:
    nbr[a].append(b); nbr[b].append(a)


def node_dir(i):
    par = [a for a, b in E if b == i]
    if par:
        return P[i] - P[par[0]]
    return P[nbr[i][0]] - P[i]


R = np.array([radius(P[i], node_dir(i)) if nbr[i] else 1.0 for i in range(len(P))])
for i in range(len(P)):  # end joints on the surface: half their parent's radius
    if R[i] < 1e-3:
        R[i] = 0.5 * R[[a for a, b in E if b == i][0]]
SPACING = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
nodes, radii, edges, owner = list(P), list(R), [], list(range(len(P)))
for a, b in E:
    L = np.linalg.norm(P[b] - P[a])
    rm = 0.5 * (R[a] + R[b])
    n = max(1, int(np.ceil(L / (SPACING * rm))))
    ts = list(np.linspace(0, 1, n + 1)[1:-1])
    for j, end in ((a, 0.0), (b, 1.0)):  # a ring either side of a bending joint
        if names[j] in BEND or names[j].startswith(("Left", "Right")) and names[j].split("Left")[-1].split("Right")[-1] in BEND:
            ts.append(abs(end - 0.45 * R[j] / L))
    ts = sorted(t for t in ts if 0.05 < t < 0.95)
    ts = [t for k, t in enumerate(ts) if k == 0 or t - ts[k - 1] > 0.12]
    prev = a
    for t in ts:
        q = P[a] + t * (P[b] - P[a])
        nodes.append(q)
        r = radius(q, P[b] - P[a])
        radii.append(r if r > 1e-3 else R[a] + t * (R[b] - R[a]))
        owner.append(a)
        edges.append((prev, len(nodes) - 1))
        prev = len(nodes) - 1
    edges.append((prev, b))
nodes, radii = np.array(nodes), np.array(radii)
used = sorted({i for e in edges for i in e})
ix = -np.ones(len(nodes), int); ix[used] = np.arange(len(used))
nodes, radii, edges = nodes[used], radii[used], [(int(ix[a]), int(ix[b])) for a, b in edges]
print(f"graph: {len(P)} joints, {len(nodes)} nodes, {len(edges)} edges")


def tris_of(loops, sizes):
    """Polygons -> triangles (quads split along the shorter diagonal) and the unique polygon edges."""
    st = np.r_[0, np.cumsum(sizes)[:-1]]
    T, ed = [], set()
    for s0, n in zip(st, sizes):
        f = loops[s0:s0 + n]
        for k in range(n):
            e = (f[k], f[(k + 1) % n])
            ed.add((min(e), max(e)))
        T += [(f[0], f[k], f[k + 1]) for k in range(1, n - 1)]
    return np.array(T), np.array(sorted(ed))


def fix_quads(V, loops, sizes):
    st = np.r_[0, np.cumsum(sizes)[:-1]]
    T = []
    for s0, n in zip(st, sizes):
        f = loops[s0:s0 + n]
        if n == 4 and np.linalg.norm(V[f[0]] - V[f[2]]) > np.linalg.norm(V[f[1]] - V[f[3]]):
            T += [(f[1], f[2], f[3]), (f[1], f[3], f[0])]
        else:
            T += [(f[0], f[k], f[k + 1]) for k in range(1, n - 1)]
    return np.array(T)


def vnormals(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], fn)
    return N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)


def shoot(V, N, reach=0.16, steps=161):
    """Each vertex to the field's zero crossing along its normal nearest to it, then Newton."""
    t = np.linspace(-reach, reach, steps)
    f = sdf.field_at(prims, V[:, None, :] + t[None, :, None] * N[:, None, :], margin=reach)
    out = V.copy()
    sgn = np.signbit(f)
    cross = sgn[:, 1:] != sgn[:, :-1]
    mid = 0.5 * (t[1:] + t[:-1])
    cost = np.where(cross, np.abs(mid)[None, :], np.inf)
    k = cost.argmin(1)
    ok = np.isfinite(cost[np.arange(len(V)), k])
    f0, f1 = f[np.arange(len(V)), k], f[np.arange(len(V)), k + 1]
    tt = t[k] + (t[k + 1] - t[k]) * f0 / np.where(f0 - f1 == 0, 1, f0 - f1)
    out[ok] += tt[ok, None] * N[ok]
    x, _ = surface.newton(prims, out, voxel * 0.125, voxel, iterations=8)
    return x, ok


def relax(V, T, ed, rounds=12, lam=0.5):
    n = len(V)
    for _ in range(rounds):
        acc = np.zeros_like(V)
        deg = np.zeros(n)
        np.add.at(acc, ed[:, 0], V[ed[:, 1]]); np.add.at(acc, ed[:, 1], V[ed[:, 0]])
        np.add.at(deg, ed[:, 0], 1); np.add.at(deg, ed[:, 1], 1)
        N = vnormals(V, T)
        dv = acc / np.maximum(deg, 1)[:, None] - V
        dv -= (dv * N).sum(1, keepdims=True) * N
        V, _ = surface.newton(prims, V + lam * dv, voxel * 0.125, voxel, iterations=6)
    return V


def errors(V, T):
    """mesh -> field (|f| at vertices, face centres, edge midpoints) and field -> mesh (high verts to a dense
    sampling of the triangles), in mm."""
    pts = np.r_[V, V[T].mean(1), 0.5 * (V[T[:, 0]] + V[T[:, 1]])]
    a = np.abs(sdf.field_at(prims, pts, margin=0.05)) * 1000
    u = np.linspace(0, 1, 7)
    U, W = np.meshgrid(u, u)
    m = U + W <= 1
    bc = np.c_[1 - U[m] - W[m], U[m], W[m]]
    S = np.einsum("kb,tbx->tkx", bc, V[T]).reshape(-1, 3)
    d, _ = cKDTree(S).query(HV)
    b = d * 1000
    return {"out_mean": a.mean(), "out_p95": np.percentile(a, 95), "out_max": a.max(),
            "in_mean": b.mean(), "in_p95": np.percentile(b, 95), "in_max": b.max()}


results = {}
meshes = {}
t0 = time.time()
blender({"mode": "skin", "nodes": nodes.tolist(), "edges": edges, "radii": (HULL * radii).tolist(), "root": 0,
         "subsurf": int(sys.argv[3]) if len(sys.argv) > 3 else 2, "out": str(OUT / "skin_raw.npz")})
k = np.load(OUT / "skin_raw.npz")
V, L, S = k["verts"].astype(np.float64), k["loops"], k["sizes"]
T0, ED = tris_of(L, S)
V, ok = shoot(V, vnormals(V, T0))
print(f"skin: {len(V)} verts, {len(S)} faces ({np.bincount(S)[3:]}), {(~ok).sum()} missed the surface")
V = relax(V, T0, ED)
meshes["skin"] = (V, L, S)
print(f"skin built {time.time() - t0:.1f}s")
TRI = len(fix_quads(V, L, S))

t0 = time.time()
blender({"mode": "quadriflow", "mesh": str(OUT / "high.npz"), "faces": TRI // 2, "out": str(OUT / "qf.npz")})
k = np.load(OUT / "qf.npz")
meshes["quadriflow"] = (k["verts"].astype(np.float64), k["loops"], k["sizes"])
print(f"quadriflow {time.time() - t0:.1f}s")
t0 = time.time()
blender({"mode": "decimate", "mesh": str(OUT / "high.npz"), "triangles": TRI, "out": str(OUT / "dec.npz")})
k = np.load(OUT / "dec.npz")
meshes["decimate"] = (k["verts"].astype(np.float64), k["loops"], k["sizes"])
print(f"decimate {time.time() - t0:.1f}s")

turns = rig.test_pose(bones)
heads = np.array([b["head"] for b in bones])
Jh = np.arange(len(bones))[:, None]
PH = rig.pose(bones, heads, Jh, np.ones_like(Jh, float), turns)
at = {b["name"].split(":")[-1]: PH[i] for i, b in enumerate(bones)}
views = [("front", [0, -1, 0], None, 1.15, False), ("front wire", [0, -1, 0], None, 1.15, True),
         ("R shoulder", [0, -1, 0], "RightArm", 0.32, True), ("L elbow", [1, 0, 0], "LeftForeArm", 0.26, True),
         ("R knee", [-1, 0, 0], "RightLeg", 0.3, True), ("L hip", [1, 0, 0], "LeftUpLeg", 0.34, True)]
rows = []
for name, (V, L, S) in meshes.items():
    T = fix_quads(V, L, S)
    results[name] = {"triangles": len(T), "quads": int((S == 4).sum()), "polys": len(S), **errors(V, T)}
    J, W = rig.rig_weights(spec, bones, V, T)
    PV = rig.pose(bones, V, J, W, turns)
    np.savez(OUT / f"{name}_posed.npz", verts=PV, loops=L, sizes=S)
    np.savez(OUT / f"{name}_rest.npz", verts=V, loops=L, sizes=S)
    c = 0.5 * (PV.min(0) + PV.max(0))
    vs = []
    for vn, d, focus, scale, wire in views:
        vs.append({"dir": d, "up": [0, 0, 1], "center": (c if focus is None else at[focus]).tolist(),
                   "scale": scale, "wire": wire, "out": str(OUT / f"{name}_{vn.replace(' ', '_')}.png")})
    blender({"mode": "render", "mesh": str(OUT / f"{name}_posed.npz"), "views": vs, "size": 560})
    rows.append((name, [Image.open(v["out"]).convert("RGB") for v in vs]))
    print(name, {k: round(v, 2) if isinstance(v, float) else v for k, v in results[name].items()})

cw, lh = 560, 26
sheet = Image.new("RGB", (cw * len(views), (cw + lh) * len(rows) + lh), (30, 31, 35))
d = ImageDraw.Draw(sheet)
for j, v in enumerate(views):
    d.text((j * cw + 8, 6), v[0], fill=(230, 230, 230))
for i, (name, ims) in enumerate(rows):
    r = results[name]
    d.text((8, lh + i * (cw + lh) + 6), f"{name}: {r['triangles']} tris, {r['quads']} quads; mesh->field mean "
           f"{r['out_mean']:.1f} p95 {r['out_p95']:.1f} mm; field->mesh mean {r['in_mean']:.1f} p95 {r['in_p95']:.1f} "
           f"max {r['in_max']:.1f} mm", fill=(230, 230, 230))
    for j, im in enumerate(ims):
        sheet.paste(im, (j * cw, 2 * lh + i * (cw + lh)))
sheet.save(OUT / "compare.png")
json.dump(results, open(OUT / "results.json", "w"), indent=1, default=float)
