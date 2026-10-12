"""lmval.py <model>...: the detector's JAW-LINE points as DIFFERENTIAL anchors (face_ruler._anchor_obs with
view["jaw_lm"] = lm 3..13), validated as jval.py: picture = the model's own dressed shot (front / 3/4), reader's model =
the same head (NULL: truth 0) or the head with a known change (reads must equal J (-change)). Per group of landmarks:
chin (7, 8, 9: already in the solve), jaw near the chin (5, 6, 10, 11), jaw angle (3, 4, 12, 13)."""
import os, sys
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, face_ruler as fr, store, gnm_mm, likeness

SHOTS = os.environ.get("SHOTS", "/mnt/data/hifipushie/reruns/out:/mnt/data/hifipushie/garrettgood/out").split(":")
GR = {"chin 7-9": (7, 8, 9), "jaw 5,6,10,11": (5, 6, 10, 11), "angle 3,4,12,13": (3, 4, 12, 13)}
ALL = tuple(range(3, 14))
rng = np.random.default_rng(3)
rnd = rng.normal(0, 1, 170)
rnd *= 3.0 / np.linalg.norm(rnd)
CH = {"chin_width+5": 5 * gnm_mm.direction("chin_width"), "chin_length+4": 4 * gnm_mm.direction("chin_length"),
      "jaw_width+6": 6 * gnm_mm.direction("jaw_width"), "under_chin+4": 4 * gnm_mm.direction("under_chin"), "random3": rnd}
tot = {}
for m in sys.argv[1:]:
    spec, rj = store.load(m), bi._refs(m)
    head = fr.model_head(spec)
    for vi, (v, cam, box) in enumerate(zip(rj["views"], rj["cameras"], rj["blockin"]["boxes"])):
        f = next((f"{d}/d_{m}_{vi}.png" for d in SHOTS if os.path.exists(f"{d}/d_{m}_{vi}.png")), None)
        kind = fr.kind_of(v.get("yaw", 0))
        if f is None or kind == "profile":
            continue
        shot = Image.open(f).convert("RGB")
        ib = [int(round(x)) for x in box]
        sc = shot.size[0] / float(ib[2] - ib[0])
        Ps = likeness.detect([shot])[0]
        if Ps is None:
            print(m, kind, "no face on the dressed shot")
            continue
        det = {"P": np.asarray(Ps, float)[:, :2] / sc + [ib[0], ib[1]], "box": tuple(float(x) for x in ib)}
        view = {"cam": cam, "kind": kind, "jaw_lm": ALL}
        pts = {"lm30": [0, 0]}
        for nm, dlt in {"null": None, **CH}.items():
            h2 = head if dlt is None else head["rebuild"](head["c"] + dlt)
            ob = [o for o in fr._anchor_obs(h2, view, pts, det) if o["type"] == "landmark" and o.get("diff")]
            for g, ids in GR.items():
                sel = [o for o in ob if int(o["name"][2:].split(".")[0]) in ids]
                if not sel:
                    continue
                o = np.array([x["o"] for x in sel])
                pr = np.zeros(len(o)) if dlt is None else np.array([x["J"] @ (-dlt) for x in sel])
                tot.setdefault((kind, g, nm), []).append(np.c_[o, pr])
    print(m, "done", flush=True)
print("ALL MODELS (mm):")
for (kind, g, nm), L in sorted(tot.items()):
    A = np.concatenate(L)
    o, pr = A[:, 0], A[:, 1]
    if nm == "null":
        print(f"  {kind:6s} {g:16s} NULL           n {len(o):4d}  bias {o.mean():+5.2f}  rms {np.sqrt((o ** 2).mean()):5.2f}")
    else:
        print(f"  {kind:6s} {g:16s} {nm:14s} n {len(o):4d}  predicted rms {np.sqrt((pr ** 2).mean()):.2f}  slope {float(o @ pr / max(pr @ pr, 1e-12)):+.2f}  "
              f"corr {np.corrcoef(o, pr)[0, 1]:+.2f}  residual rms {np.sqrt(((o - pr) ** 2).mean()):.2f}")
