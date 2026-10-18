"""eyeview.py <glb> <out.png>: each eye's baked albedo seen from the front (orthographic, dense barycentric samples per
eye face, nearest-front wins), the right eye mirrored beside the left so the two can be compared texel for texel."""
import sys, numpy as np
from PIL import Image
import mouthhits as mh
g, _, _ = mh.load(sys.argv[1])
uv, tex = mh.uv_of("eyes"); tex = np.asarray(tex, float)[..., :3]; tex = tex * (255 if tex.max() <= 1.0 else 1)
m = g["meshes"]["eyes"]; V, F = np.asarray(m["V"], float), np.asarray(m["F"], int)
UVF = uv[F]
rng = np.random.default_rng(0); k = 300
b = rng.random((k, 2)); b[b.sum(1) > 1] = 1 - b[b.sum(1) > 1]; B = np.c_[1 - b.sum(1), b]
P = np.einsum("kj,fjd->fkd", B, V[F]).reshape(-1, 3); U = np.einsum("kj,fjd->fkd", B, UVF).reshape(-1, 2)
H, W = tex.shape[:2]
C = tex[np.clip(((1 - U[:, 1]) * H).astype(int), 0, H - 1), np.clip((U[:, 0] * W).astype(int), 0, W - 1)]
res = 0.0001; half = 0.014; out = []
for side in (1, -1):
    s = (P[:, 0] * side) > 0; Q, Cq = P[s], C[s]
    c = np.array([np.median(Q[:, 0]), 0, np.median(Q[:, 2])])
    x = ((Q[:, 0] - c[0]) * side + half) / res; z = (half - (Q[:, 2] - c[2])) / res
    n = int(2 * half / res); img = np.zeros((n, n, 3)); depth = np.full((n, n), 9.0)
    xi, zi = x.astype(int), z.astype(int); ok = (xi >= 0) & (xi < n) & (zi >= 0) & (zi < n)
    order = np.argsort(-Q[ok, 1])  # far first, nearest (most -y) last wins
    img[zi[ok][order], xi[ok][order]] = Cq[ok][order]
    out.append(img); print("side", side, "eye centre", c.round(4), "samples", ok.sum())
L, R = out  # R is mirrored (lateral on the same side as L's)
Image.fromarray(np.hstack([L, np.full((L.shape[0], 8, 3), 255), R]).astype(np.uint8)).resize((1128, 560)).save(sys.argv[2])
