"""truthbias.py <truth model> ..: at the TRUE head (the scan-fitted identity through the rig's true cameras, front view; the
groundtruth / readmix HSRD sets), MediaPipe on the PHOTOGRAPH against MediaPipe's learned correspondence on the true
surface (mp_gnm.json: where the detector lands on OUR dressed renders of that surface; bias off). Mouth width, lip
heights, fissure lengths, openings, inter- / outer canthal distances, mm in the picture (photo minus ours: + = the photo
reads it bigger). A non-zero mean = our drawing of the SAME shape reads differently from a real face of it.
-> out/truthbias.json + a table."""
import json
import sys

import numpy as np

from hifipushie import face_ruler as fr

OUT = "/mnt/data/hifipushie/mouthbias/out"
IDS = (61, 291, 0, 13, 14, 17, 33, 133, 263, 362, 159, 145, 386, 374)
NAMES = ("mouth_w", "upper", "lower", "fiss_R", "fiss_L", "open_R", "open_L", "intercanth", "outer_canth")


def meas(P, mm):
    d = lambda a, b: float(np.linalg.norm(P[a] - P[b])) * mm  # noqa: E731
    y = lambda a, b: float(P[b][1] - P[a][1]) * mm  # noqa: E731
    return {"mouth_w": d(61, 291), "upper": y(0, 13), "lower": y(14, 17), "fiss_R": d(33, 133), "fiss_L": d(263, 362),
            "open_R": y(159, 145), "open_L": y(386, 374), "intercanth": d(133, 362), "outer_canth": d(33, 263)}


rows = {}
for name in sys.argv[1:]:
    head, views, notes = fr.reference_views(name, lips=False, lids=False, mp=True, hair_edge=False, alar=False)
    v = next(v for v in views if v["kind"] == "front")
    obs = v["extra"](head, v)
    ph, md, mm = {}, {}, []
    for ob in obs:
        if ob.get("type") == "mp" and ob["mp"] in IDS and ob["name"].endswith(".x"):
            ph[ob["mp"]] = np.asarray(ob["q"], float)
            md[ob["mp"]] = np.asarray(ob["p"], float)
            mm.append(ob["mm1"])
    if not all(i in ph for i in IDS):
        print(name, "missing", [i for i in IDS if i not in ph])
        continue
    m = float(np.median(mm))
    a, b = meas(ph, m), meas(md, m)
    rows[name] = {k: a[k] - b[k] for k in NAMES}
    rows[name]["_photo"] = a
    print(name, " ".join(f"{k} {rows[name][k]:+.2f}" for k in NAMES), flush=True)
json.dump(rows, open(f"{OUT}/truthbias.json", "w"), indent=1)
print("\n| measure | photo - ours at the truth, mean (sd) mm | n |")
for k in NAMES:
    x = np.array([r[k] for r in rows.values()])
    print(f"| {k} | {x.mean():+.2f} ({x.std():.2f}) | {len(x)} |")
