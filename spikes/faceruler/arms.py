"""arms.py <set>...: the BLIND arms of the driving test (never shown to a driver).
Per pair: the rulers' gaps applied without looking, as `mm:` moves (each holds the other measures):
  mesh:all / top8 / top4      gnm_mm.gaps on the MESHES (gnmdrive2's ceiling)
  pic:all / top8 / top4       face_ruler on B's clay PICTURES (front, 3/4, profile) through the known cameras
  pic:top8x2                  top 8, look again (the ruler on the moved head's pictures), top 8 again
  hair:top8                   the same with no outline where hair would hide the skull
  cam:top8 / cam:all          hair + each picture taken through a camera off by 3 mm / 2 % / 1.5 deg, solved with that freedom
  fit                         (next lever) the ruler's own fitted identity change applied directly, not through 23 moves
Graded by score2 (old and new pass rule). -> $G/out/arms_<set>.json"""
import json
import os
import sys

import numpy as np

import drv
import score2
from hifipushie import face_ruler as fr, gnm_mm

G = os.environ["G"]
KINDS = ("front", "3q", "profile")
CAM_SD = (3.0, 3.0, 2.0, 1.5)
J = gnm_mm.jacobian()
NM = list(gnm_mm.NAMES)
SD = np.linalg.norm(J[:len(NM)], axis=1)


def apply(c, gap, top=None):
    """the mm: moves for these gaps ({measure: mm}; the largest `top` in sd), every other measure held."""
    g = np.array([gap[n] for n in NM])
    idx = np.argsort(-np.abs(g) / SD)[: top or len(NM)]
    b = np.zeros(len(J))
    b[idx] = g[idx]
    return c + J.T @ np.linalg.solve(J @ J.T + 1e-6 * np.eye(len(J)), b)


def pictures(cB, rng=None):
    B = fr.gnm_head(cB)
    views = []
    for k in KINDS:
        cam = fr.camera(k)
        c = dict(cam)
        if rng is not None:
            c["t"] = [rng.normal(0, CAM_SD[0] * 1e-3), rng.normal(0, CAM_SD[1] * 1e-3), c["t"][2]]
            c["f"] = c["f"] * (1 + rng.normal(0, CAM_SD[2] * 0.01))
            c["r"] = [0.0, 0.0, float(np.radians(rng.normal(0, CAM_SD[3])))]
        views.append({"img": fr.clay(B, c), "cam": cam, "kind": k, "style": "clay"})
    return views


def ruler(c, views, hair=False, cam=False):
    vs = [dict(v, hair=hair) for v in views]
    res = fr.read(fr.gnm_head(c), vs, cam_sd=CAM_SD if cam else None)
    return {r["measure"]: r["gap"] for r in res["gaps"]}, res


if __name__ == "__main__":
    for s in sys.argv[1:]:
        out = {}
        for i in range(14):
            case = f"{s}_{i:02d}"
            h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
            cA, cB = np.array(h["A"]), np.array(h["B"])
            regs = [x["region"] for x in h["changes"]]
            mesh = {r["measure"]: r["gap"] for r in gnm_mm.gaps(drv.verts(cA), drv.verts(cB))}
            views = pictures(cB)
            views_p = pictures(cB, np.random.default_rng(1000 + i))
            pic, res = ruler(cA, views)
            hair, _ = ruler(cA, views, hair=True)
            cam, _ = ruler(cA, views_p, hair=True, cam=True)
            c8 = apply(cA, pic, 8)
            pic2, _ = ruler(c8, views)
            arms = {"mesh:all": apply(cA, mesh), "mesh:top8": apply(cA, mesh, 8), "mesh:top4": apply(cA, mesh, 4),
                    "pic:all": apply(cA, pic), "pic:top8": c8, "pic:top4": apply(cA, pic, 4),
                    "pic:top8x2": apply(c8, pic2, 8), "hair:top8": apply(cA, hair, 8), "hair:all": apply(cA, hair),
                    "cam:top8": apply(cA, cam, 8), "cam:all": apply(cA, cam), "fit": cA + res["dc"]}
            g = score2.grade(cA, cB, list(arms.values()), regs)
            err = {k: float(np.sqrt(np.mean([(v[n] - mesh[n]) ** 2 for n in NM]))) for k, v in (("pic", pic), ("hair", hair), ("cam", cam))}
            out[case] = {"difficulty": h["difficulty"], "regions": regs, "ruler_rms_err": err,
                         "mesh": mesh, "pic": pic, "hair": hair, "cam": cam, **{k: x for k, x in zip(arms, g)}}
            print(case, h["difficulty"][:4], "+".join(regs).ljust(18), "ruler rms err " + " ".join(f"{k} {v:.2f}" for k, v in err.items()), flush=True)
            print("     " + " | ".join(f"{k} {x['region']:.2f}/{x['id']:.2f}/{x['outline']:.2f}{'*' if x['pass'] else ' '}{'o' if x['pass_old'] else ' '}" for k, x in zip(arms, g)), flush=True)
            json.dump(out, open(f"{G}/out/arms_{s}.json", "w"), indent=1)
        n = len(out)
        print(f"== {s} new rule: " + ", ".join(f"{k} {sum(r[k]['pass'] for r in out.values())}/{n}" for k in arms))
        print(f"== {s} old rule: " + ", ".join(f"{k} {sum(r[k]['pass_old'] for r in out.values())}/{n}" for k in arms))
