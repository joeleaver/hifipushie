"""dval.py <model>...: the ruler's BLOCK-IN path validated on pictures of known heads through real fitted cameras
(env REFS's three cameras): model A (a block-in model), pictures of model B, truth = gnm_mm gaps of their GNM identities.
Variants: clay (B's clay through the camera), dressed (dshots.py's EEVEE pictures, bald), dressed+hair (no outline
where hair would be), dressed+hair+cam (and the camera's shift / scale / roll left free, as compare() does on a photo).
Irises on the dressed front picture: eye_ruler.read. -> $G/out/dval.json + the table."""
import json
import os
import sys

import numpy as np
from PIL import Image

from hifipushie import blockin as bi, eye_ruler as er, face_ruler as fr, gnm_mm, humanfit, likeness, store

G = os.environ["G"] + "/out"
REFS = os.environ.get("REFS", "gd_T12")
BOX = json.load(open(f"{G}/d_box.json"))["box"]
names = sys.argv[1:]
rj = bi._refs(REFS)
kinds = [fr.kind_of(v.get("yaw", 0)) for v in rj["views"]]
VAR = ("clay+cam", "dressed+cam", "dressed+hair+cam")
specs = {n: store.load(n) for n in names}
heads = {n: fr.model_head(specs[n]) for n in names}
sp = gnm_mm._space()
Vg = {n: sp["T"] + np.tensordot(bi.identity(specs[n]), sp["IB"], 1) for n in names}
rows = []
for i, a in enumerate(names):
    for b in (names[(i + 1) % len(names)],):
        truth = {r["measure"]: r["gap"] for r in gnm_mm.gaps(Vg[a], Vg[b])}
        row = {"a": a, "b": b, "truth": truth}
        for var in VAR:
            views = []
            for k, cam in zip(kinds, rj["cameras"]):
                if var == "clay+cam":
                    v = {"img": fr.clay(heads[b], cam), "cam": cam, "kind": k, "style": "dressed"}
                else:
                    img = Image.open(f"{G}/d_{b}_{k}.png").convert("RGB")
                    v = {"img": img, "cam": cam, "kind": k, "style": "dressed", "origin": BOX[:2], "scale": 1.0,
                         "hair": "hair" in var}
                    v["mask"], v["trust"] = fr.photo_masks(img, cam, heads[a], origin=BOX[:2])   # as a photo is read
                    if k == "front":
                        try:
                            P = np.asarray(likeness.detect([img])[0], float)[:, :2] + BOX[:2]
                            mm = likeness._mm_per_px(cam, humanfit.state(specs[a]["base"])["L"][27:48])
                            eyes = er.read(img, P, mm, scale=1.0, origin=BOX[:2])
                            v["extra"] = lambda h, vw, eyes=eyes: fr._iris_obs(h, vw, eyes)
                        except Exception as e:  # noqa: BLE001
                            print("  no iris read:", b, e)
                views.append(v)
            res = fr.read(heads[a], views, rounds=4 if "cam" in var else 3, cam_sd=fr.CAM_SD if "cam" in var else None)
            row[var] = {r["measure"]: [r["gap"], r["err"]] for r in res["gaps"]}
            row[var + "_n"] = len(res["obs"])
        rows.append(row)
        print(a, "<-", b, " ".join(f"{v}: n {row[v + '_n']} rms err {np.sqrt(np.mean([(row[v][m][0] - truth[m]) ** 2 for m in gnm_mm.NAMES])):.2f}" for v in VAR),
              f"| truth rms {np.sqrt(np.mean([truth[m] ** 2 for m in gnm_mm.NAMES])):.2f}", flush=True)
        json.dump(rows, open(f"{G}/dval.json", "w"))
sd = gnm_mm.sd()
# The one mesh sets the head's SIZE from the body, so a model's pictures do not show its identity's size: compare the
# gaps with the uniform-size part taken out of both (g - alpha m, m = the measures' own values, alpha by least squares)
m0 = np.array([heads[names[0]]["measures"][m] for m in gnm_mm.NAMES])
w = 1.0 / np.array([sd[m] for m in gnm_mm.NAMES]) ** 2


def shape(g):
    g = np.asarray(g, float)
    return g - (g * m0 * w).sum() / (m0 * m0 * w).sum() * m0


for r in rows:
    r["truth_s"] = dict(zip(gnm_mm.NAMES, shape([r["truth"][m] for m in gnm_mm.NAMES])))
    for v in VAR:
        r[v + "_s"] = dict(zip(gnm_mm.NAMES, shape([r[v][m][0] for m in gnm_mm.NAMES])))
print(f"\n{len(rows)} pairs: size-free gaps, reader - truth (mm): bias / sd, pop sd / rms error")
print(f"{'measure':18s} pop sd | " + " | ".join(f"{v:^18s}" for v in VAR))
for m in gnm_mm.NAMES:
    line = f"{m:18s} {sd[m]:5.1f} truth rms {np.sqrt(np.mean([r['truth_s'][m] ** 2 for r in rows])):4.1f} | "
    for v in VAR:
        e = np.array([r[v + "_s"][m] - r["truth_s"][m] for r in rows])
        line += f"{e.mean():+5.2f} {e.std():5.2f} {sd[m] / np.sqrt((e ** 2).mean()):4.1f}x | "
    print(line)
