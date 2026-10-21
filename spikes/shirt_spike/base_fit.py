"""Shirt spike step 0: the existing no-sim fitter (pattern_form.on_form) on the plain average male (workspace wf_simon:
MakeHuman 35 y, 1.78 m, weight / muscle 0.5) with its Simon shirt, closed. Baseline before changing anything.
Args: tag. Writes <tag>.pkl (the fit) and <tag>_{front,side,...}.png (clay) + diag."""
import sys, time, pickle, json
import numpy as np
from pathlib import Path
from hifipushie import store, pattern_form as pf, cloth, resources, diag_render as dr
OUT = Path("/mnt/data/hifipushie/shirt_spike"); TAG = sys.argv[1] if len(sys.argv) > 1 else "s0"
spec = store.load("wf_simon")
_ov0 = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
if _ov0.get("simon_seam"):  # the band sewn EDGE TO EDGE (its extensions onto the fronts' placket tops), in memory
    _d0 = cloth.designs
    def _designs():
        D = _d0(); S = D["simon"]["seams"]
        for i, sm in enumerate(S):
            if isinstance(sm[0], str) and sm[0].startswith("stand:leftBottomCf"):
                S[i] = ["stand:leftBottomEdge>leftBottomCf>bottomMid>rightBottomCf>rightBottomEdge", _ov0["simon_seam"]]
        return D
    cloth.designs = _designs
_ov = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
if _ov.get("kb_folds") or "roll_angle" in _ov:  # override the KB's no_tie open-neck fold lines in memory: {"open neck.L": [..line..], ...}
    from hifipushie import garment_design as gd
    _k = gd.kb()
    if _ov.get("kb_folds") == "none":
        _k["kinds"]["shirt"]["wear"]["no_tie"]["folds"] = []
    for fd in _k["kinds"]["shirt"]["wear"]["no_tie"]["folds"]:
        if "roll_angle" in _ov: fd["angle"] = _ov["roll_angle"]
        if isinstance(_ov["kb_folds"], dict) and fd["name"] in _ov["kb_folds"]: fd["line"] = _ov["kb_folds"][fd["name"]]
    print("kb folds", [(f["name"], f["line"]) for f in _k["kinds"]["shirt"]["wear"]["no_tie"]["folds"]])
if "OPEN_SPREAD" in _ov: pf.OPEN_SPREAD = _ov["OPEN_SPREAD"]; print("pattern_form.OPEN_SPREAD =", pf.OPEN_SPREAD)
OV = dict(_ov); OV.pop("OPEN_SPREAD", None); OV.pop("kb_folds", None); OV.pop("roll_angle", None); OV.pop("simon_seam", None); OV.pop("band_ends", None); ROLL = OV.pop("collar_roll", None)
if OV.get("from_garrett"):  # copy Garrett's worn-open construction keys (closures, worn_open, neck_split, folds)
    gg = store.load("sh_garrett")["cloth"]["shirt"]
    for k in OV.pop("from_garrett"): spec["cloth"]["shirt"][k] = gg[k]
spec["cloth"]["shirt"].update(OV)
g = cloth.expanded(spec["cloth"]["shirt"])
if OV.pop("band_ends", None) is False or _ov0.get("band_ends") is False:
    g["pattern"]["band_ends"] = False; print("band_ends off (Simon's own band ends)")
OV.pop("simon_seam", None)
if ROLL:  # override the design's collar roll fold keys (angle, strength, radius, line offset)
    for fd in g.get("folds") or []:
        if fd.get("name") == "collar roll":
            if "offset" in ROLL: fd["line"] = dict(fd["line"], offset=ROLL["offset"])
            fd.update({k: v for k, v in ROLL.items() if k != "offset"}); print("collar roll", fd)
if "worn_open" not in OV and "worn_open" not in spec["cloth"]["shirt"]: g.pop("worn_open", None)
print("garment keys", sorted(g))
t0 = time.time()
with resources.heavy(f"shirt spike {TAG}", gb=6.0):
    res = pf.on_form("wf_simon", "shirt", spec, g=g)
print(f"fit {time.time()-t0:.0f}s; A_info keys {list(res.get('A_info', {}))[:20]}")
X, M, body = np.asarray(res["A"], float), res["mesh"], res["body"]
pickle.dump({"A": X, "mesh": M, "A_info": res.get("A_info"), "bodyV": np.asarray(body.V), "bodyF": np.asarray(body.T if hasattr(body, "T") else body.F),
             "at": {k: np.asarray(v).tolist() for k, v in body.at.items() if np.asarray(v).size <= 6}}, open(OUT / f"{TAG}.pkl", "wb"))
st = dr.face_strain(X, M["F"], M["uv"]); print("face strain p50 / p99 %", np.round(np.percentile(np.abs(st), [50, 99]) * 100, 1))
BF = np.asarray(body.T if hasattr(body, "T") else body.F)
hps = np.asarray(body.at["hps.L"], float).reshape(-1)[-3:]
objs = [{"name": "body", "V": np.asarray(body.V, float), "F": BF, "color": "#c4bcb4"},
        {"name": "shirt", "V": X, "F": np.asarray(M["F"]), "color": "#c9ccd2", "thickness": 0.0004, "offset": 0.0}]
VIEWS = [{"name": "front", "dir": [0, -1, 0]}, {"name": "q", "dir": [-0.6, -0.8, 0.0]}, {"name": "side", "dir": [-1, 0, 0]}]
box = [[-0.32, -0.25, hps[2] - 0.62], [0.32, 0.25, hps[2] + 0.12]]
with resources.heavy(f"shirt spike {TAG} render", gb=4.0, gpu=True):
    p1 = cloth.render(objs, str(OUT / f"{TAG}_clay"), views=VIEWS, resolution=640, box=box)
    p2 = cloth.render([objs[0], {"name": "shirt", "V": X, "F": np.asarray(M["F"]), "mesh": M, "layer": 0, "color": "#c9ccd2"}],
                      str(OUT / f"{TAG}_diag"), views=VIEWS, resolution=640, box=box, diag=["panels", "seams", "turned"])
print(p1, p2, f"total {time.time()-t0:.0f}s")
