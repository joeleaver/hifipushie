"""fissure.py <model>...: the eye opening against the front picture, per corner (mm, + = the picture's corner lies further
OUT along the eye's own axis than the model's: the model's opening is short there) and the opening's height. LIGHT."""
import sys
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, humanfit, likeness as lk, store
for m in sys.argv[1:]:
    rj = bi._refs(m)
    vi = bi._front(rj)
    v, cam = rj["views"][vi], rj["cameras"][vi]
    P = np.asarray(bi.detect_view(Image.open(v["image"]).convert("RGB"), v), float)[:, :2]
    P = P[np.asarray(lk.MP68)]
    st = humanfit.state(bi.view_base(store.load(m)["base"], rj, vi))
    M = humanfit.project(cam, st["L"][:68])
    L = st["L"]
    mmpx = 1000.0 * float(np.linalg.norm(L[39] - L[42])) / float(np.linalg.norm(M[39] - M[42]))
    out = []
    for side, (o, i, up, lo) in (("R", (36, 39, (37, 38), (40, 41))), ("L", (45, 42, (43, 44), (46, 47)))):
        ax = (M[o] - M[i]) / np.linalg.norm(M[o] - M[i])
        dout = float((P[o] - M[o]) @ ax) * mmpx
        din = float((P[i] - M[i]) @ -ax) * mmpx
        hp = float(np.mean([np.linalg.norm(P[a] - P[b]) for a, b in zip(up, lo[::-1])])) * mmpx
        hm = float(np.mean([np.linalg.norm(M[a] - M[b]) for a, b in zip(up, lo[::-1])])) * mmpx
        out.append(f"{side}: outer corner {dout:+.1f} mm, inner corner {din:+.1f} mm, opening height picture {hp:.1f} / model {hm:.1f} mm")
    print(m, "(front view, + = the picture's corner lies further out):", "; ".join(out))
