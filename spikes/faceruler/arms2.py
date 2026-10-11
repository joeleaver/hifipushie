"""arms2.py <set>...: the blind arms with a FITTED camera, as on a photo (never shown to a driver).
  fitcam   each picture of B is taken through the true camera, but the ruler is given the camera that best lays the
           MODEL's (A's) landmarks on B's picture landmarks (a shift / scale / roll per view, least squares, 0.5 mm of
           landmark noise): what humanfit's camera fit does with a model that is not yet the person. The fit hides
           whatever a similarity can absorb. The ruler leaves CAM_SD of freedom per view and refines the cameras.
  cam      each picture through a camera off by a random 3 mm / 2 % / 1.5 deg (arms.py's, now with camera refinement)
  :top8 / :all as arms.py; :sig = the gaps beyond 2 x their shown error only (at most 8).
Hair: no outline where hair would be. -> $G/out/arms2_<set>.json"""
import json
import os
import sys

import numpy as np
from scipy.optimize import least_squares

import arms
import drv
import score2
from hifipushie import face_ruler as fr, gnm_mm

G = os.environ["G"]
NM = list(gnm_mm.NAMES)
LM = {"front": list(range(68)), "3q": list(range(68)), "profile": [8, 27, 28, 29, 30, 33, 51, 57, 62, 66, 45, 54]}


def cam_of(cam, p):
    c = dict(cam)
    c["t"] = [p[0] * 1e-3, p[1] * 1e-3, cam["t"][2]]
    c["f"] = cam["f"] * (1 + p[2] * 0.01)
    c["r"] = [0.0, 0.0, float(np.radians(p[3]))]
    return c


def fitted_views(cA, cB, rng):
    A, B = fr.gnm_head(cA), fr.gnm_head(cB)
    views, dev = [], []
    for k in arms.KINDS:
        cam = fr.camera(k)
        mmpx = cam["t"][2] / cam["f"] * 1000
        PB = fr._cam_points(cam, B["L"][LM[k]])[1] + rng.normal(0, 0.5 / mmpx, (len(LM[k]), 2))
        # the camera c' with project(c', A's landmarks) ~ B's picture landmarks; the picture is B through the TRUE camera
        r = least_squares(lambda p: (fr._cam_points(cam_of(cam, p), A["L"][LM[k]])[1] - PB).ravel(), np.zeros(4))
        dev.append(r.x.tolist())
        views.append({"img": fr.clay(B, cam), "cam": cam_of(cam, r.x), "kind": k, "style": "clay", "hair": True})
    return views, dev


def sig(c, res, top=8):
    rows = [r for r in res["gaps"] if abs(r["gap"]) > 2 * r["err"]][:top]
    gap = {n: 0.0 for n in NM}
    for r in rows:
        gap[r["measure"]] = r["gap"]
    return arms.apply(c, gap), len(rows)


if __name__ == "__main__":
    for s in sys.argv[1:]:
        out = {}
        for i in range(14):
            case = f"{s}_{i:02d}"
            h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
            cA, cB = np.array(h["A"]), np.array(h["B"])
            regs = [x["region"] for x in h["changes"]]
            mesh = {r["measure"]: r["gap"] for r in gnm_mm.gaps(drv.verts(cA), drv.verts(cB))}
            fv, dev = fitted_views(cA, cB, np.random.default_rng(2000 + i))
            rf = fr.read(fr.gnm_head(cA), fv, cam_sd=fr.CAM_SD, rounds=4)
            g_f = {r["measure"]: r["gap"] for r in rf["gaps"]}
            g_c = g_f
            cs, ns = sig(cA, rf)
            ne = 0
            c8 = arms.apply(cA, g_f, 8)
            fv2, _ = fitted_views(c8, cB, np.random.default_rng(3000 + i))      # look again: the camera re-fitted too
            r2 = fr.read(fr.gnm_head(c8), fv2, cam_sd=fr.CAM_SD, rounds=4)
            A = {"fitcam:all": arms.apply(cA, g_f), "fitcam:top8": c8, "fitcam:sig": cs,
                 "fitcam:top8x2": arms.apply(c8, {r["measure"]: r["gap"] for r in r2["gaps"]}, 8)}
            g = score2.grade(cA, cB, list(A.values()), regs)
            out[case] = {"difficulty": h["difficulty"], "regions": regs, "mesh": mesh, "fitcam": g_f, "cam": g_c,
                         "fitcam_err": {r["measure"]: r["err"] for r in rf["gaps"]}, "dev": dev, "cam_found": rf["cam_done"],
                         "n_sig": [ns, ne], **{k: x for k, x in zip(A, g)}}
            e = lambda q: float(np.sqrt(np.mean([(q[n] - mesh[n]) ** 2 for n in NM])))  # noqa: E731
            print(case, h["difficulty"][:4], "+".join(regs).ljust(18), f"ruler rms err fitcam {e(g_f):.2f} cam {e(g_c):.2f}; fitted camera off by "
                  + " / ".join(f"{np.abs(np.array(dev)[:, j]).mean():.1f}" for j in range(4)) + " (mm, mm, %, deg)", flush=True)
            print("     " + " | ".join(f"{k} {x['region']:.2f}/{x['id']:.2f}{'*' if x['pass'] else ' '}" for k, x in zip(A, g)), flush=True)
            json.dump(out, open(f"{G}/out/arms2_{s}.json", "w"), indent=1)
        print(f"== {s} new rule: " + ", ".join(f"{k} {sum(r[k]['pass'] for r in out.values())}/{len(out)}" for k in A))
