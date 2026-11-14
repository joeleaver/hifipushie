"""D2 step 1 (measurement only): the pattern's own girths against the body's. Each girth: the flat pieces cut by the
level line (across the grain, seam lines: the pattern carries no allowance, sewn edges share their points), the inside
lengths summed (darts and gaps between pieces out; a front's part past its centre line (x < 0: the buttons sit on x 0)
out; .L x 2) vs the body's tape loop + 2 pi GAP (the cloth GAP off the body all round). Edges (neck, armhole) by arc
length along the outline between named points.

  uv run python spikes/d2_girths.py <loaded.pkl> <n2j run dir> [out.json]"""
import json
import pickle
import sys

import numpy as np

from hifipushie.chain_core import GAP

src, run = sys.argv[1:3]
d = pickle.load(open(src, "rb"))
M = d["pat"].M
cnet = pickle.load(open(run + "/cnet.pkl", "rb"))["cnet"]
P = M["points"]
uv = np.asarray(M["uv"], float)
T = M["starts"]["tapes"]


def tape_len(n):
    Q = np.asarray(T[n]["pts"], float)
    if T[n]["kind"] == "loop":
        Q = np.r_[Q, Q[:1]]
    return float(np.linalg.norm(np.diff(Q, axis=0), axis=1).sum())


def poly(nm):
    return cnet.uv[np.asarray(cnet.loop(nm))]


def width_at(nm, y, xmin=-np.inf):
    """Inside length of the piece's outline on the line at height y (even-odd), x >= xmin only."""
    U = poly(nm)
    A, B = U, np.roll(U, -1, axis=0)
    k = (A[:, 1] > y) != (B[:, 1] > y)  # (half-open: a vertex on the line counts once)
    t = (y - A[k, 1]) / (B[k, 1] - A[k, 1])
    xs = np.sort(A[k, 0] + t * (B[k, 0] - A[k, 0]))
    w = 0.0
    for a, b in zip(xs[0::2], xs[1::2]):
        a, b = max(a, xmin), max(b, xmin)
        w += b - a
    return w, len(xs)


def arc(nm, a, b):
    """Outline arc length between named points a and b of piece nm (the shorter way)."""
    lp = list(cnet.loop(nm))
    U = cnet.uv[lp]
    ia = int(np.argmin(np.linalg.norm(U - uv[P[f"{nm}:{a}"]], axis=1)))
    ib = int(np.argmin(np.linalg.norm(U - uv[P[f"{nm}:{b}"]], axis=1)))
    seg = np.linalg.norm(np.diff(np.r_[U, U[:1]], axis=0), axis=1)
    i, j = sorted((ia, ib))
    s = seg[i:j].sum()
    return float(min(s, seg.sum() - s))


y = lambda k: float(uv[P[k], 1])
body_pieces = ["front.L", "side.L", "back.L"]
levels = {"chest": y("back.L:cbChest"), "waist": y("back.L:cbWaist"), "hips": y("back.L:cbHips"),
          "seat (hem)": y("back.L:cbHem") + 0.004}
tape_of = {"chest": "chest", "waist": "waist", "hips": "hips", "seat (hem)": "seat"}
rows = []
plan = {}
try:
    import os
    j = json.load(open(os.environ.get("D2_PLAN", "/mnt/data/hifipushie/d2/ws/garrett/garments/jacket.json")))
    plan = j["steps"]["0"]["output"]["fit"]
except Exception:
    pass
for lv, yy in levels.items():
    per = {}
    for nm in body_pieces:
        w, nx = width_at(nm, yy, 0.0 if nm.startswith("front") else -np.inf)
        per[nm] = round(w * 1e3, 1)
    g = 2 * sum(per.values()) / 1e3
    b = tape_len(tape_of[lv])
    pl = plan.get(lv.split()[0], {}).get("garment_girth_mm")
    rows.append({"girth": lv, "level_y_mm": round(yy * 1e3), "pattern_mm": round(g * 1e3), "half_by_piece_mm": per,
                 "body_mm": round(b * 1e3), "body_plus_gap_mm": round((b + 2 * np.pi * GAP) * 1e3),
                 "spare_mm": round((g - b - 2 * np.pi * GAP) * 1e3), "planned_mm": pl})
# sleeve: two pieces, own frames; levels from their named points
sl = {"biceps": ("tsLeftEdge", "usLeftEdge"), "elbow": ("tsElbowLeft", "usElbowLeft"),
      "wrist": ("tsWristLeft", "usWristLeft")}
for lv, (a, b_) in sl.items():
    wt, _ = width_at("sleeve_top.L", y(f"sleeve_top.L:{a}"))
    wu, _ = width_at("sleeve_under.L", y(f"sleeve_under.L:{b_}"))
    g = wt + wu
    b = tape_len(lv)
    rows.append({"girth": lv, "pattern_mm": round(g * 1e3), "half_by_piece_mm": {"top": round(wt * 1e3, 1),
                 "under": round(wu * 1e3, 1)}, "body_mm": round(b * 1e3),
                 "body_plus_gap_mm": round((b + 2 * np.pi * GAP) * 1e3), "spare_mm": round((g - b - 2 * np.pi * GAP) * 1e3)})
# neck: the garment's neckline (back neck hps -> cb, front neck hps -> collar corner) vs the collar's neck edge and the
# body's neckline path (shoulder to shoulder round the front) / neck loop
gn = 2 * (arc("back.L", "hps", "cbNeck") + arc("front.L", "neck", "collarCorner"))
cn = 2 * arc("collar", "hpsL", "cbN") + 2 * arc("collar", "hpsL", "ccL")
un = 2 * arc("undercollar", "hpsL", "cbN") + 2 * arc("undercollar", "hpsL", "ccL")
rows.append({"girth": "neckline", "pattern_mm": round(gn * 1e3), "collar_neck_edge_mm": round(cn * 1e3),
             "undercollar_neck_edge_mm": round(un * 1e3), "body_mm": round(tape_len("neck") * 1e3),
             "body_neckline_path_mm": round(tape_len("neckline") * 1e3),
             "body_plus_gap_mm": round((tape_len("neck") + 2 * np.pi * GAP) * 1e3),
             "spare_mm": round((gn - tape_len("neck") - 2 * np.pi * GAP) * 1e3)})
ah = arc("front.L", "shoulder", "fsArmhole") + arc("side.L", "fsArmhole", "bsArmholeHollow") + \
    arc("back.L", "bsArmholeHollow", "shoulder")
cap = arc("sleeve_top.L", "tsLeftEdge", "tsRightEdge") + arc("sleeve_under.L", "usLeftEdge", "usRightEdge")
ba = tape_len("armhole_front") + tape_len("armhole_back")
rows.append({"girth": "armhole", "pattern_mm": round(ah * 1e3), "sleeve_cap_mm": round(cap * 1e3),
             "cap_ease_mm": round((cap - ah) * 1e3), "body_mm": round(ba * 1e3),
             "body_plus_gap_mm": round((ba + 2 * np.pi * GAP) * 1e3), "spare_mm": round((ah - ba - 2 * np.pi * GAP) * 1e3)})
for r in rows:
    print(json.dumps(r))
# the torso girths again at the BODY's tape heights (the flat's y follows height from the waist: the pieces' grain is
# vertical and their levels shared), and a profile every 20 mm
zc = lambda n: float(np.asarray(T[n]["pts"], float)[:, 2].mean())
yw = y("back.L:cbWaist")
girth = lambda yy: 2 * sum(width_at(nm, yy, 0.0 if nm.startswith("front") else -np.inf)[0] for nm in body_pieces)
for lv in ("chest", "waist", "hips", "seat"):
    yy = yw + zc(lv) - zc("waist")
    g, b = girth(yy), tape_len(lv)
    rows.append({"girth": lv + " at body height", "level_y_mm": round(yy * 1e3), "pattern_mm": round(g * 1e3),
                 "body_plus_gap_mm": round((b + 2 * np.pi * GAP) * 1e3), "spare_mm": round((g - b - 2 * np.pi * GAP) * 1e3)})
    print(json.dumps(rows[-1]))
prof = [(round(yy * 1e3), round(girth(yy) * 1e3)) for yy in np.arange(-0.28, -0.725, -0.02)]
print("profile (y mm, pattern girth mm):", prof)
Qn = np.asarray(T["neck"]["pts"], float)
i, j = sorted(np.argsort(Qn[:, 0])[[0, -1]])
seg = np.linalg.norm(np.diff(np.r_[Qn, Qn[:1]], axis=0), axis=1)
s1 = seg[i:j].sum()
bn = s1 if Qn[i:j + 1, 1].mean() > Qn[:, 1].mean() else seg.sum() - s1
rows.append({"girth": "back neck (side to side round the back)", "pattern_mm": round(2e3 * arc("back.L", "hps", "cbNeck")),
             "undercollar_mm": round(2e3 * arc("undercollar", "hpsL", "cbN")), "body_mm": round(bn * 1e3),
             "body_plus_gap_mm": round((bn + np.pi * GAP) * 1e3)})
print(json.dumps(rows[-1]))
# the sleeve at the body's own distances from the shoulder point (the shoulderToWrist path's start; the sleeve's top at
# flat y 0 sits there), and its profile every 20 mm
sp = np.asarray(T["shoulderToWrist"]["pts"], float)
ax = (sp[-1] - sp[0]) / np.linalg.norm(sp[-1] - sp[0])
sw = lambda yy: width_at("sleeve_top.L", yy)[0] + width_at("sleeve_under.L", yy)[0]
for lv in ("biceps", "elbow", "wrist"):
    dd = float((np.asarray(T[lv]["pts"], float).mean(0) - sp[0]) @ ax)
    g, b = sw(-dd), tape_len(lv)
    rows.append({"girth": lv + " at body distance", "from_shoulder_mm": round(dd * 1e3), "pattern_mm": round(g * 1e3),
                 "body_mm": round(b * 1e3), "body_plus_gap_mm": round((b + 2 * np.pi * GAP) * 1e3),
                 "spare_mm": round((g - b - 2 * np.pi * GAP) * 1e3)})
    print(json.dumps(rows[-1]))
sprof = [(round(yy * 1e3), round(sw(yy) * 1e3)) for yy in np.arange(-0.10, -0.56, -0.03)]
print("sleeve profile (y mm, girth mm):", sprof)
if len(sys.argv) > 3:
    json.dump({"rows": rows, "profile": prof, "sleeve_profile": sprof}, open(sys.argv[3], "w"), indent=1)
