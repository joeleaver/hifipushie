"""Judge a wrapped mesh: MODEL=<model> wrap_eval.py wrapped.npz out_dir [label]
Error (field -> mesh, mm) by region (rest / head / hands / ears), joint rings (elbows, knees, ankles; shoulders and
hips slid down the limb to their first closed cut), turned faces, and a posed render sheet (rest + test pose)."""
import json
import sys
from pathlib import Path

import numpy as np

import topo_eval as E
import topo_loops as TL
from hifipushie import sdf


ear_prims = [p for p in E.prims if "ear" in p.name and "face" not in p.name]
if ear_prims:
    d_ear = sdf.field_at(ear_prims, E.HV, clip=False)
    E.REGION = np.where(d_ear < 0.004, "ears", E.REGION)


def planes():
    """The anatomy's loop planes (hinge creases; limb roots through cap top and pits, slid down the limb to their
    first closed cut: shoulder 0.6 r, hip 0.4 r), both sides."""
    from hifipushie import anatomy, kits
    out = []
    for p in anatomy.loop_planes(kits.expand(E.spec)):
        lab, pt, n, r = p["label"], np.asarray(p["point"]), np.asarray(p["normal"]), p["r"]
        if p["joint"] in {x["joint"] for x in anatomy.limb_roots(kits.expand(E.spec))}:
            pt = pt + (0.4 if lab.startswith("hip") else 0.6) * r * n
        r = TL.limb_radius(pt, n)
        out.append((lab, pt, n, r))
        m = np.array([-1.0, 1, 1])
        out.append((lab.replace(".L", ".R"), pt * m, n * m, r))
    return out


def turned(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12
    g = sdf.gradient(E.prims, V[T].mean(1), 1e-4)
    g /= np.linalg.norm(g, axis=1, keepdims=True) + 1e-12
    c = V[T].mean(1)
    on = np.abs(sdf.field_at(E.prims, c, margin=0.01)) < 0.0015  # interiors kept off the surface don't count
    bad = ((fn * g).sum(1) < 0.0) & on
    reg = E.REGION[E.cKDTree(E.HV).query(c[bad])[1]] if bad.any() else np.array([])
    return bad, {r: int((reg == r).sum()) for r in np.unique(reg)}


def evaluate(path, out_dir, label="wrap", render=True):
    z = np.load(path)
    V, L, S = z["verts"].astype(float), z["loops"], z["sizes"]
    T = E.tris(V, L, S)
    errs = E.errors(V, T)
    if "ears" in E.REGION:
        u = np.linspace(0, 1, 7)
        U, W = np.meshgrid(u, u)
        m = U + W <= 1
        bc = np.c_[1 - U[m] - W[m], U[m], W[m]]
        Sm = np.einsum("kb,tbx->tkx", bc, V[T]).reshape(-1, 3)
        d = E.cKDTree(Sm).query(E.HV[E.REGION == "ears"])[0] * 1000
        errs["ears"] = (round(float(d.mean()), 2), round(float(np.percentile(d, 95)), 1))
    rc = TL.ring_check(V, L, S, planes())
    bad, where = turned(V, T)
    faces = {int(k): int(c) for k, c in zip(*np.unique(S, return_counts=True))}
    res = {"verts": len(V), "faces": faces, "tris": len(T), "errors_mm": errs,
           "rings": f"{sum(v['ring'] for v in rc.values())}/{len(rc)}", "turned_tris": int(bad.sum()), "turned_by_region": where}
    print(json.dumps(res))
    print(TL.fmt(rc))
    if render:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ims = E.posed_row(label, V, L, S, out_dir, rings=[v["path"] for v in rc.values() if v["ring"]])
        E.sheet([(f"{label}: {errs['all']}", ims)], out_dir / f"{label}_sheet.png")
        print(out_dir / f"{label}_sheet.png")
    return res, rc


def closeups(path, out_png, center, scale, dirs=(("front", [0, -1, 0]), ("side", [1, 0, 0]), ("3q", [0.7, -1, 0.2]),
                                                    ("back", [0.5, 1, 0.3])), size=700, wire=True):
    """Rest-pose close-ups of a mesh (wire over clay), side by side."""
    from PIL import Image
    out_png = Path(out_png)
    if str(path) == "model":  # the model's own body mesh
        path = out_png.with_name("model_body.npz")
        np.savez(path, verts=E.HV, loops=E.HF.ravel(), sizes=np.full(len(E.HF), 3))
        wire = False
    job = {}
    import os
    if os.environ.get("RINGS"):  # closed polylines to draw (an (n, k, 3) .npy)
        job["rings"] = [r.tolist() for f in os.environ["RINGS"].split(",") for r in np.load(f)]
        job["ring_width"] = 0.0006
    if wire:  # turned faces flagged in red
        z = np.load(path)
        V = z["verts"].astype(float)
        T = E.tris(V, z["loops"], z["sizes"])
        bad, _ = turned(V, T)
        if os.environ.get("ERR"):  # instead: the model's surface the mesh misses by more than ERR mm, in red
            u = np.linspace(0, 1, 7)
            U, Wb = np.meshgrid(u, u)
            m = U + Wb <= 1
            bc = np.c_[1 - U[m] - Wb[m], U[m], Wb[m]]
            d = E.cKDTree(np.einsum("kb,tbx->tkx", bc, V[T]).reshape(-1, 3)).query(E.HV)[0] * 1000
            far = (d[E.HF] > float(os.environ["ERR"])).all(1)
            V, T, bad = E.HV, E.HF, far
        if bad.any():
            np.savez(out_png.with_name("hl.npz"), verts=V, loops=T[bad].ravel(), sizes=np.full(int(bad.sum()), 3))
            job["hl_mesh"] = str(out_png.with_name("hl.npz"))
    vs =[{"dir": d, "up": [0, 0, 1], "center": list(map(float, center)), "scale": scale, "wire": wire,
           "out": str(out_png.with_name(f"{out_png.stem}_{n}.png"))} for n, d in dirs]
    E.blender({"mode": "render", "mesh": str(path), "views": vs, "size": size, **job}, out_png.parent)
    im = Image.new("RGB", (size * len(vs), size))
    for k, v in enumerate(vs):
        im.paste(Image.open(v["out"]).convert("RGB"), (k * size, 0))
    im.save(out_png)
    return out_png


if __name__ == "__main__":
    if sys.argv[1] == "closeup":  # closeup mesh.npz out.png joint scale [dx dy dz]
        from hifipushie.spec import expand_mirror, resolve_point
        c = resolve_point(expand_mirror(E.spec), sys.argv[4]) + np.array([float(x) for x in sys.argv[6:9]] or [0, 0, 0])
        print(closeups(sys.argv[2], sys.argv[3], c, float(sys.argv[5])))
    else:
        evaluate(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "wrap")
