"""uvover.py <glb>: meshes sharing each base-colour texture, and UV overlap (texels covered by 2+ meshes, or by
both the +x and -x halves of one mesh, or by 2+ triangles of one mesh) on a 1024 grid."""
import sys, numpy as np
from PIL import Image, ImageDraw
import mouthhits as mh
g, _, _ = mh.load(sys.argv[1]); doc = mh.doc
by = {}
for me in doc["meshes"]:
    p = me["primitives"][0]; mat = doc["materials"][p.get("material", 0)]
    t = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture", {}).get("index")
    by.setdefault((t, mat.get("name")), []).append(me["name"])
for k, v in by.items(): print("texture", k, "meshes", v)
N = 1024
def mask(name, sel=None):
    uv, _ = mh.uv_of(name); F = np.asarray(g["meshes"][name]["F"]); V = np.asarray(g["meshes"][name]["V"])
    if sel is not None: F = F[sel(V[F].mean(1))]
    cnt = np.zeros((N, N), np.int32)
    for f in F:
        im = Image.new("L", (N, N)); ImageDraw.Draw(im).polygon([(uv[i, 0] * N, uv[i, 1] * N) for i in f], fill=1)
        cnt += np.asarray(im, np.int32)
    return cnt
eyes = ["shoes", "socks", "soles", "teeth", "tongue"]
L = mask("eyes", lambda c: c[:, 0] > 0); R = mask("eyes", lambda c: c[:, 0] < 0)
print("eyes +x texels", (L > 0).sum(), "-x", (R > 0).sum(), "shared L&R", ((L > 0) & (R > 0)).sum(),
      "self-overlap +x", (L > 1).sum(), "-x", (R > 1).sum())
for n in eyes:
    if n == "eyes": continue
    M = mask(n); print(f"  {n}: texels {(M>0).sum()}, overlap with eyes +x {((M>0)&(L>0)).sum()} -x {((M>0)&(R>0)).sum()}")
