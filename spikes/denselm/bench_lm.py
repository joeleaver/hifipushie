"""bench_lm.py <tag> [truth models..]: the detector on the KNOWN-HEAD benchmark's pictures (chinread's cz_<x>_T,
solvereads' sx_<x>_T: dressed EEVEE renders of known heads through known cameras): each landmark's error against the
truth's own vertex through the true camera (mm at the face), per view and region; the network's sigma against its
real error; MediaPipe's 68 against the same truth. A different body / dressing / light than any training dressing,
but the same renderer: between the synthetic held-out set and real pictures. WS=main; HIFIPUSHIE_DENSELM set."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import blockin as bi, denselm, face_ruler as fr, likeness, store

tag = sys.argv[1]
models = sys.argv[2:] or [f"cz_{t}_T" for t in ("c", "d", "e", "es", "f", "g", "h", "bs", "bq", "bm", "bp")]
out = Path(f"/mnt/data/hifipushie/denselm/out/bench_{tag}")
out.mkdir(parents=True, exist_ok=True)
L = denselm.landmarks()
reg = L["region"][:L["n_skin"]]
REG = ("lids", "eyes", "brows", "nose", "lips", "mouth", "chin", "cheeks", "forehead", "ears", "scalp_neck")
acc = {}
rows = []
for m in models:
    if not (store.HOME / m / "spec.json").exists():
        continue
    rj = bi._refs(m)
    head = fr.model_head(store.load(m))
    for vi, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
        if not Path(v["image"]).exists():
            continue
        img = Image.open(v["image"]).convert("RGB")
        _, q68 = fr._cam_points(cam, np.asarray(head["L"], float)[:68])
        mmpx = likeness._mm_per_px(cam, np.asarray(head["L"], float)[27:48])
        pr = denselm.predict(img, q68)
        if "dense_v" not in head:
            fr._dense_obs(head, {"cam": cam, "kind": "front"}, pr)
        hv = head["dense_v"]
        Xc, Q = fr._cam_points(cam, head["V"][hv])
        d = (pr["xy"][:len(hv)] - Q) * mmpx
        e = np.linalg.norm(d, axis=1)
        sg = pr["sigma"][:len(hv)] * mmpx
        sure = sg < 2.0
        yaw = abs(fr.view_yaw(cam))
        kind = "front" if yaw < 15 else "3q" if yaw < 60 else "side"
        mp = likeness.detect_region(img, likeness._box({str(i): p for i, p in enumerate(q68)}, img.size))
        o68 = pr["xy"][L["lm68"]]
        e68 = np.linalg.norm(o68 - q68, axis=1) * mmpx
        m68 = None if mp is None else np.linalg.norm(np.asarray(mp, float)[likeness.MP68] - q68, axis=1) * mmpx
        a = acc.setdefault(kind, {"e": [], "sg": [], "reg": [], "d": [], "e68": [], "m68": [], "dm68": []})
        a["e"].append(e), a["sg"].append(sg), a["reg"].append(reg), a["d"].append(d), a["e68"].append(e68)
        if m68 is not None:
            a["m68"].append(m68)
            a["dm68"].append((np.asarray(mp, float)[likeness.MP68] - q68) * mmpx)
        rows.append(f"{m:10s} v{vi} {kind:5s} yaw {yaw:5.1f} {mmpx:.2f} mm/px: ours all {np.median(e):.2f} / sure ({sure.mean() * 100:.0f} %) median {np.median(e[sure]):.2f} mean {e[sure].mean():.2f} mm; "
                    f"68: ours {np.median(e68):.2f}, MediaPipe {'-' if m68 is None else f'{np.median(m68):.2f}'}; chin 7-9 y bias: ours {(o68[7:10, 1] - q68[7:10, 1]).mean() * mmpx:+.2f}, "
                    f"MediaPipe {'-' if mp is None else f'{(np.asarray(mp, float)[likeness.MP68][7:10, 1] - q68[7:10, 1]).mean() * mmpx:+.2f}'} mm")
        print(rows[-1], flush=True)
        if vi < 3 and m in models[:3]:
            bx = denselm.box_of(q68)
            k = 900 / (bx[2] - bx[0])
            im = img.crop(tuple(int(x) for x in bx)).resize((900, 900), Image.LANCZOS)
            dr = ImageDraw.Draw(im)
            for p, q, s in zip(pr["xy"][:len(hv)], Q, sg):
                a_, b_ = (p - [int(bx[0]), int(bx[1])]) * k, (q - [int(bx[0]), int(bx[1])]) * k
                c = (40, 230, 60) if s < 1 else (250, 220, 30) if s < 2 else (255, 60, 50)
                dr.line((*a_, *b_), fill=(255, 255, 255))
                dr.ellipse((a_[0] - 2, a_[1] - 2, a_[0] + 2, a_[1] + 2), fill=c)
            im.save(out / f"{m}_{vi}.png")
print("\nPER VIEW KIND (mm at the face; 'sure' = the network's own sigma under 2 mm)")
for kind, a in acc.items():
    e, sg, rg, d = np.concatenate(a["e"]), np.concatenate(a["sg"]), np.concatenate(a["reg"]), np.concatenate(a["d"])
    sure = sg < 2.0
    print(f"{kind} ({len(a['e'])} pictures): sure {sure.mean() * 100:.0f} %; error median {np.median(e[sure]):.2f} mean {e[sure].mean():.2f} p90 {np.percentile(e[sure], 90):.2f}; "
          f"calibration mean d^2 / (2 sigma^2) = {(e[sure] ** 2 / (2 * sg[sure] ** 2)).mean():.2f} (1 = honest); within 1 sigma {(e < sg)[sure].mean() * 100:.0f} % (39 expected), 2 sigma {(e < 2 * sg)[sure].mean() * 100:.0f} % (86)")
    print("   by region, median error / median sigma / share sure / mean bias x, y: " + "; ".join(
        f"{r} {np.median(e[(rg == r) & sure]):.2f} / {np.median(sg[(rg == r) & sure]):.2f} / {((rg == r) & sure).sum() / max((rg == r).sum(), 1) * 100:.0f} % / {d[(rg == r) & sure, 0].mean():+.2f}, {d[(rg == r) & sure, 1].mean():+.2f}"
        for r in REG if ((rg == r) & sure).any()))
    e68 = np.array(a["e68"])
    line = f"   the 68 standard points: ours median {np.median(e68):.2f} (jaw 0-16 {np.median(e68[:, :17]):.2f}, inner {np.median(e68[:, 17:]):.2f}, chin 7-9 {np.median(e68[:, 7:10]):.2f})"
    if a["m68"]:
        m68, dm = np.array(a["m68"]), np.array(a["dm68"])
        line += (f"; MediaPipe median {np.median(m68):.2f} (jaw {np.median(m68[:, :17]):.2f}, inner {np.median(m68[:, 17:]):.2f}, chin {np.median(m68[:, 7:10]):.2f}; "
                 f"chin bias y {dm[:, 7:10, 1].mean():+.2f} mm)")
    print(line)
(out / "rows.txt").write_text("\n".join(rows))
