"""crease_diag.py <model> [slider values...]: where does the supratarsal crease go? A sagittal slice through the
left eye's middle (x = eye.L x + dx) of (a) the warped quads, (b) the Catmull-Clark'd base, (c) the IMLS field's
zero set, for eye_crease_depth = each value. Prints the profile's forward-most y per height over the eye and the
crease's depth (local dip under the chord of its neighbours 2.5 mm up / down)."""
import copy
import json
import sys

import numpy as np

from hifipushie import base as basemod, sdf, skin_look, store
from hifipushie.spec import compile_prims, expand_mirror

name = sys.argv[1]
vals = [float(v) for v in sys.argv[2:]] or [0.0, 0.8, 2.0]
SM = float(__import__("os").environ.get("SMOOTH", "1"))
spec = store.load(name)


def slice_mesh(V, F, x0, ez, ey):
    """forward-most y of the mesh's cut at x = x0, per z bin (0.1 mm) over the eye."""
    T = np.array([(f[0], f[j], f[j + 1]) for f in F for j in range(1, len(f) - 1)])
    s = V[T][..., 0] - x0
    keep = (s.min(1) < 0) & (s.max(1) > 0)
    T = T[keep]
    P = V[T]
    s = P[..., 0] - x0
    pts = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        m = (s[:, a] * s[:, b]) < 0
        t = s[m, a] / (s[m, a] - s[m, b])
        pts.append(P[m, a] + t[:, None] * (P[m, b] - P[m, a]))
    Q = np.concatenate(pts)
    Q = Q[(Q[:, 1] < ey) & (Q[:, 1] > ey - 0.04) & (Q[:, 2] > ez - 0.01) & (Q[:, 2] < ez + 0.03)]
    # sort along the polyline by z: front-most per bin
    zs = np.arange(ez - 0.005, ez + 0.025, 0.0001)
    out = np.full(len(zs), np.nan)
    for i, z in enumerate(zs):
        m = np.abs(Q[:, 2] - z) < 0.0004
        if m.any():
            # interpolate y at z from the two nearest by z
            q = Q[m]
            out[i] = np.interp(z, *zip(*sorted(zip(q[:, 2], q[:, 1])))) if len(q) > 1 else q[0, 1]
    return zs, out


def slice_field(prim, x0, ez, ey):
    zs = np.arange(ez - 0.005, ez + 0.025, 0.0001)
    ys = np.arange(ey - 0.035, ey - 0.002, 0.00005)
    Y, Z = np.meshgrid(ys, zs)
    P = np.c_[np.full(Y.size, x0), Y.ravel(), Z.ravel()]
    f = sdf.field_at([prim], P).reshape(Y.shape)
    out = np.full(len(zs), np.nan)
    for i in range(len(zs)):
        r = f[i]
        k = np.flatnonzero((r[:-1] > 0) & (r[1:] <= 0))
        if len(k):
            k = k[0]
            out[i] = ys[k] + (ys[k + 1] - ys[k]) * r[k] / (r[k] - r[k + 1])
    return zs, out


def dip(zs, y, ez):
    """the crease: over the margin, the largest backward dip of y under the chord of +-2.5 mm (mm)."""
    d = 25
    best = (0.0, None)
    for i in range(d, len(zs) - d):
        if not (np.isfinite(y[i - d]) and np.isfinite(y[i + d]) and np.isfinite(y[i])):
            continue
        chord = 0.5 * (y[i - d] + y[i + d])
        b = (y[i] - chord) * 1000  # + = behind the chord (y is depth: larger y = further back)
        if zs[i] > ez + 0.004 and b > best[0]:
            best = (b, (zs[i] - ez) * 1000)
    return best


st0 = skin_look.stage_spec(spec, "head")
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(st0)["joints"].items() if "pos" in v}
ex, ey, ez = J["eye.L"]
res = {}
for v in vals:
    st = copy.deepcopy(st0)
    st["base"]["head"].setdefault("sliders", {})["eye_crease_depth"] = v
    if SM != 1:
        st["base"]["smooth"] = SM
    prims = compile_prims(st)
    bp = [p for p in prims if p.kind == "base"][0]
    surf = basemod.surface(expand_mirror(st), st["base"])
    W, Fq = surf["quads"]
    for dx in (0.0,):
        x0 = ex + dx
        zq, yq = slice_mesh(np.asarray(W), Fq, x0, ez, ey)
        zs, ys = slice_mesh(surf["verts"], surf["faces"], x0, ez, ey)
        zf, yf = slice_field(bp, x0, ez, ey)
        res[v] = (zq, yq, ys, yf)
        print(f"crease_depth {v}: dip (mm behind chord, at mm over eye centre): quads {dip(zq, yq, ez)}, "
              f"subdiv {dip(zs, ys, ez)}, field {dip(zf, yf, ez)}")
        hq = surf["h"]
        near = np.linalg.norm(surf["verts"] - J["eye.L"], axis=1) < 0.02
        print(f"   kernel h near the eye: median {np.median(hq[near]) * 1000:.2f} mm, max {hq[near].max() * 1000:.2f}")
v0 = vals[0]
for v in vals[1:]:
    zq, yq, ys, yf = res[v]
    _, yq0, ys0, yf0 = res[v0]
    print(f"difference {v} - {v0} along z (mm over eye centre): quads / subdiv / field (mm, + = back)")
    for i in range(0, len(zq), 10):
        print(f"  {(zq[i] - ez) * 1000:5.1f}  {(yq[i] - yq0[i]) * 1000:+.3f}  {(ys[i] - ys0[i]) * 1000:+.3f}  {(yf[i] - yf0[i]) * 1000:+.3f}")
np.savez(f"/mnt/data/hifipushie/eyedetail/out/crease_{name}.npz", **{f"v{k}": np.array(r) for k, r in res.items()})
