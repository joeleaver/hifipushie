"""c1_tool.py <tag> [base]: the spike's c1 recipe as garment_pull ops on <base> (default e5), saved as <tag>.pkl."""
import sys, json, pickle
import numpy as np
from hifipushie import garment_pull as gp
D = "/mnt/data/hifipushie/shirt_spike/"; tag = sys.argv[1]; base = sys.argv[2] if len(sys.argv) > 2 else "e5"
d = pickle.load(open(D + base + ".pkl", "rb")); X = np.asarray(d["A"], float); M = d["mesh"]; body = (d["bodyV"], d["bodyF"])
held = gp.hold_mask(M, X, ["collar", "stand", "front.L", "front.R"], below="closure:front")
OPS = json.load(open("/home/joe/dev/hifipushie/.claude/worktrees/modest-napier-7b031c/src/hifipushie/garment_kb.json"))["kinds"]["shirt"]["wear"]["no_tie"].get("style") if len(sys.argv) > 3 else None
ops = OPS or [
    {"relax": {}},
    {"hold": {"pieces": ["stand", "collar"], "within_deg": 70, "feather_to": 130, "feather_pieces": ["stand"], "of": "back", "center": "stand"}},
    {"turn": {"turns": [{"at": f"stand:{s}BottomEdge..{s}TopCf", "about": [f"stand:{s}BottomHinge", f"stand:{s}TopHinge"],
                         "deg": 65, "toward": "side", "side_from": f"stand:{s}BottomHinge"} for s in ("left", "right")], "steps": 8}},
    {"push": {"pieces": ["front.L", "front.R"]}},
    {"pull": {"handles": [{"at": f"collar:{s}TopEdge", "dir": {"side": 1, "out": 0.3}, "side_from": f"collar:{s}TopHinge"} for s in ("left", "right")], "max_move": 0.045}},
    {"smooth": {"border": "collar:leftTopEdge..topMid..rightTopEdge", "spline": 10, "release": ["collar"], "tol": 0.02, "rounds": 40}},
    {"smooth": {"pieces": ["collar", "stand", "front.L", "front.R"], "rounds": 30}},
    {"push": {"pieces": ["front.L", "front.R"]}},
    {"smooth": {"pieces": ["collar"], "near": ["collar:leftTopEdge", "collar:rightTopEdge"], "radius": 0.04, "rounds": 40}},
]
Xn, infos = gp.style(M, X, held, ops, body=body)
for i in infos: print(json.dumps(i, default=str)[:200])
out = dict(d); out["A"] = Xn; pickle.dump(out, open(D + tag + ".pkl", "wb")); print("saved", tag)
