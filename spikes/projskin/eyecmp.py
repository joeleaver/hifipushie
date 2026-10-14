"""eyecmp.py <dir with face_v0.png + face_v0_ref.png> [more dirs]: the upper-lid fold READ the same way on our render and
on the picture (lidfold.read_lid on the same frame: visible platform tps mm, fold-line darkness 0..1, per column inner /
middle / outer, both eyes). The crease's depth as it READS, ours against the photo's. LIGHT."""
import json, sys
import numpy as np
from PIL import Image
from hifipushie import lidfold, likeness

res = {}
for d in sys.argv[1:]:
    row = {}
    for nm, f in (("photo", "face_v0_ref.png"), ("ours", "face_v0.png")):
        import os
        if not os.path.exists(f"{d}/{f}") and os.path.exists(f"{d}/{f[:-4]}_cy.png"):
            f = f[:-4] + "_cy.png"          # (a Cycles render)
        img = Image.open(f"{d}/{f}").convert("RGB")
        P = likeness.detect([img])[0]
        if P is None:
            row[nm] = None
            continue
        rd = lidfold.read_lid(img, P)
        # the ORBIT's darkness (what the baked occlusion adds): mean luminance in a ring 3-9 mm round each eye's opening
        # (lids, socket, under-eye; the opening itself out) against the cheek under it, 1 - ring / cheek
        A = np.asarray(img, float) @ [0.2126, 0.7152, 0.0722]
        Pp = np.asarray(P, float)[:, :2]
        from scipy import ndimage
        from PIL import ImageDraw
        orb = []
        for ids_ in ((33, 160, 158, 133, 153, 144), (263, 387, 385, 362, 380, 373)):
            e = Pp[list(ids_)]
            w_ = float(np.linalg.norm(e[0] - e[3]))
            mmpx = 30.0 / max(w_, 1e-6)              # (an eye ~30 mm corner to corner at this scale, roughly)
            mk = Image.new("L", img.size, 0); ImageDraw.Draw(mk).polygon([tuple(q) for q in e], fill=255)
            M = np.asarray(mk) > 0
            dist = ndimage.distance_transform_edt(~M) * mmpx
            ring = (dist > 3) & (dist < 9)
            cen = e.mean(0)
            yy, xx = np.mgrid[:A.shape[0], :A.shape[1]]
            cheek = (np.abs(xx - cen[0]) < 0.25 * w_) & (yy > cen[1] + 14 / mmpx) & (yy < cen[1] + 20 / mmpx)
            orb.append(round(float(1 - A[ring].mean() / max(A[cheek].mean(), 1e-6)), 3) if ring.any() and cheek.any() else None)
        row[nm] = [[{"tps": None if not np.isfinite(c.get("tps", np.nan)) else round(float(c["tps"]), 2), "dark": round(float(c.get("dark", 0.0)), 3)} for c in eye] for eye in rd]
        row[nm + "_orbit"] = orb
    res[d] = row
    for nm in ("photo", "ours"):
        if row[nm]:
            print(f"{d.split('/')[-2]}/{d.split('/')[-1]} {nm:5s}", "  ".join("eye%d tps %s dark %s" % (i, [c["tps"] for c in e], [c["dark"] for c in e]) for i, e in enumerate(row[nm])), " orbit", row[nm + "_orbit"])
json.dump(res, open(sys.argv[1] + "/eyecmp.json", "w"), indent=1)
