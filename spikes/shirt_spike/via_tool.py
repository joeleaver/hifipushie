"""via_tool.py <tag> <json>: run the pull tool's garment_pull.style (loaded from TOOL, the tool session's file) on the
closed fit e3 and save <tag>.pkl for this spike's reads. json: {"swing": deg, "up": w, "corners": 0|1, "hug": deg}."""
import sys, json, pickle, importlib.util, os
import numpy as np
import hifipushie
spec = importlib.util.spec_from_file_location("hifipushie.garment_pull", os.environ["TOOL"]); gp = importlib.util.module_from_spec(spec); gp.__package__ = "hifipushie"; sys.modules["hifipushie.garment_pull"] = gp; spec.loader.exec_module(gp)
D = "/mnt/data/hifipushie/shirt_spike/"; tag = sys.argv[1]; A = json.loads(sys.argv[2])
d = pickle.load(open(D + "e3.pkl", "rb")); X = np.asarray(d["A"], float); M = d["mesh"]; body = (d["bodyV"], d["bodyF"])
held = gp.hold_mask(M, X, ["collar", "stand", "front.L", "front.R"], below="closure:front")
turns = [{"at": f"stand:{s}BottomEdge..{s}TopCf", "about": [f"stand:{s}BottomHinge", f"stand:{s}TopHinge"],
          "deg": A.get("swing", 30), "toward": "side", "side_from": f"stand:{s}BottomHinge"} for s in ("left", "right")]
P = {"pull": {"handles": [{"at": f"collar:{s}TopEdge", "dir": {"side": 1, "out": 0.3, "up": A.get("up", 0.0)},
                           "side_from": f"collar:{s}TopHinge"} for s in ("left", "right")]}}
ops = [{"relax": {}}]
if A.get("hug"):
    hd = {"pieces": ["stand", "collar"], "within_deg": A["hug"], "of": "back", "center": "stand"}
    if A.get("feather_to"): hd["feather_to"] = A["feather_to"]
    ops.append({"hold": hd})
ops += [{"turn": {"turns": turns}}, P, {"smooth": {"pieces": ["collar", "stand"]}}]
Xn, infos = gp.style(M, X, held, ops, body=body)
for i in infos: print(json.dumps(i, default=str)[:220])
out = dict(d); out["A"] = Xn; out["A_info"] = dict(d["A_info"], via_tool=A); pickle.dump(out, open(D + tag + ".pkl", "wb")); print("saved", tag)
