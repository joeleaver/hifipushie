"""gphone.py: the PHONE-DISTANCE test on the Lee Perry-Smith scan: the textured scan drawn through a 24 mm-equivalent
camera at 0.30 m and 0.40 m (1728 x 2304: strong perspective, the nose enlarged) and, for contrast, from 1.75 m through
the lens that frames the head the same (191 mm, 1152 x 1536); front / 45 / 90 each (the benchmark's jitter). Models
(needs gmk.py lps first: the truth gt_lps_T): gt_ph<d>_AT (truth, true cameras) and gt_ph<d>_A00 = block_in_start on
the pictures WITH each picture's true lens_mm told (as EXIF would)."""
import copy
import json
import numpy as np
from PIL import Image
import gt, rast
from gmk import CL, PICS
from hifipushie import blockin as bi, face_ruler as fr, humanfit, store

tag = "lps"
scan = gt.load_scan(tag)
fj = json.loads((gt.WORK / tag / "fit_p1b3.json").read_text())
S = (fj["S"]["s"], np.asarray(fj["S"]["R"]), np.asarray(fj["S"]["t"]))
Mj = json.loads((gt.WORK / tag / "model_world.json").read_text())["M"]
SM = gt.compose((Mj["s"], np.asarray(Mj["R"]), np.asarray(Mj["t"])), S)
sp = store.load("gt_lps_T")
L = np.asarray(humanfit.state(sp["base"])["L"], float)[:68]
ctr = L.mean(0)
Vm = gt.apply(SM, scan["V"])
tex = np.asarray(Image.open(gt.ROOT / scan["info"]["texture"]).convert("RGB"))
for name, dist, lens, (w, h) in (("ph30", 0.30, 24.0, (1728, 2304)), ("ph40", 0.40, 24.0, (1728, 2304)), ("ph175", 1.75, 191.4, (1152, 1536))):
    rng = np.random.default_rng(777 + int(dist * 100))
    cams, views = [], []
    for vn, yaw in (("f", 0), ("q45", 45), ("s90", 90)):
        j = rng.uniform(-1, 1, 5)
        f = lens / 36.0 * w
        z = dist                                    # the camera's distance to the head's CENTRE (between eyes and mouth, mid-depth of the landmarks)
        cam = {"r": [0.0, 0.0, float(np.radians(1.5 * j[2]))], "t": [float(0.004 * j[3] - 0.03 * np.sin(np.radians(yaw))), float(0.004 * j[4] - 0.012), float(z)],
               "f": float(f), "size": [w, h], "centre": ctr.tolist(), "yaw": float(-(yaw + 2 * j[0]))}
        cam = fr.cam_moved(cam, pitch=2 * j[1])
        cam["r"] = [float(x) for x in cam["r"]]
        fn = PICS / f"{name}_{vn}.png"
        vis = rast.visibility(Vm, scan["F"], cam, ss=2)
        rast.shade(vis, Vm, scan["F"], rast.texture_lookup(vis, scan["FUV"], tex), gamma=True, bg=(128, 130, 134),
                   lights=(((-0.50, -0.45, -0.74), 1.35), ((0.80, -0.10, -0.59), 0.55)), ambient=0.30).save(fn)
        pts = {}
        if yaw >= 70:
            P = humanfit.project(cam, L[list(CL.values())]) + 2.0 * rng.standard_normal((len(CL), 2))
            pts = {kk: [round(float(p[0]), 1), round(float(p[1]), 1)] for kk, p in zip(CL, P)}
        views.append({"image": str(fn), "size": [w, h], "yaw": (yaw if yaw < 70 else -yaw), "points": pts, "name": vn, "lens_mm": lens})
        cams.append(cam)
        print(f"{name} {vn}: turn {abs(fr.view_yaw(cam)):.1f} dist {z:.2f} m lens {lens:.0f} mm; {f / z:.0f} px / m")
    views = bi.with_anchor_points(views)
    print("  detector points:", [sum(1 for k in v["points"] if k.startswith("lm")) for v in views])
    ST = f"gt_{name}_AT"
    store._dir(ST).mkdir(parents=True, exist_ok=True)
    (store.HOME / ST / "spec.json").write_text(json.dumps(sp))
    (store.HOME / ST / "human_refs.json").write_text(json.dumps({"views": views, "cameras": cams, "blockin": {"root": ST, "attach": "native", "placement": list(bi._placement(sp["base"]))}}))
    e = bi.start(f"gt_{name}_A00", [copy.deepcopy(v) for v in views], sex="male", age=35, cameras="refit", replace=True)
    print(f"  start gt_{name}_A00: {e['start']['cameras']}")
