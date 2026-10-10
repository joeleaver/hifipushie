"""mtable.py <model>...: faces6, stage M's ACCEPTANCE TABLE (Joe: "Head and jaw shape, eye placement, nose size and
shape, mouth size and placement"): the checklist items of the five macro groups, read by likeness.compare on the photo
and on each model through its own fitted cameras (photo | model, per view), with each item's tolerance; a row
passes at |model - photo| <= tol. Prints a table per group and a pass count per model; writes $F/out/mtable.json."""
import json
import os
import sys

from hifipushie import likeness, store

GROUPS = {
    "1 head shape": ["face_height", "face_index", "upper_third", "middle_third", "width_temple", "width_cheekbone",
                     "forehead_slope", "prof_forehead_slope"],
    "2 jaw and chin": ["width_jaw", "width_chin", "jaw_taper", "jaw_gonial", "jaw_angle_height", "chin_height",
                       "chin_shape", "chin_projection", "prof_chin"],
    "3 eye placement": ["pupil_distance", "intercanthal", "eye_width", "brow_eye"],
    "4 nose": ["nose_length", "alar_width", "width_nose_base", "nose_projection", "prof_nose_length", "prof_bridge_bow",
               "tip_height", "nasolabial_angle"],
    "5 mouth": ["mouth_width", "mouth_line", "philtrum", "lower_third", "mouth_over_alar"],
}
F = os.environ.get("F", "/mnt/data/hifipushie/faces6")


def table(m):
    rows = likeness.compare(m, store.load(m)["base"])["rows"]
    by = {(r["id"], r["vi"]): r for r in rows}
    out = {}
    for g, ids in GROUPS.items():
        out[g] = []
        for i in ids:
            for (rid, vi), r in sorted(by.items(), key=lambda kv: str(kv[0][1])):
                if rid != i or r.get("photo") is None or r.get("model") is None:
                    continue
                if not isinstance(r["photo"], (int, float)) or not isinstance(r["model"], (int, float)):
                    continue
                tol = r.get("tol") or 0
                d = float(r["model"]) - float(r["photo"])
                out[g].append({"id": i, "view": r.get("view", vi), "unit": r.get("unit"), "photo": round(float(r["photo"]), 3),
                               "model": round(float(r["model"]), 3), "diff": round(d, 3), "tol": round(float(tol), 3),
                               "ok": bool(tol and abs(d) <= tol)})
    return out


if __name__ == "__main__":
    allt = {}
    for m in sys.argv[1:]:
        allt[m] = table(m)
    ms = sys.argv[1:]
    for g in GROUPS:
        print(f"\n== {g}")
        keys = []
        for m in ms:
            for r in allt[m][g]:
                if (r["id"], r["view"]) not in keys:
                    keys.append((r["id"], r["view"]))
        print(f"{'item':22s} {'view':13s} {'photo':>8s} " + " ".join(f"{m[-12:]:>14s}" for m in ms) + "   tol")
        for k in keys:
            line, ph, tol = [], None, None
            for m in ms:
                r = next((r for r in allt[m][g] if (r["id"], r["view"]) == k), None)
                if r is None:
                    line.append(f"{'-':>14s}")
                    continue
                ph, tol = r["photo"], r["tol"]
                line.append(f"{r['model']:>9.3f} {'ok' if r['ok'] else 'MISS':>4s}")
            print(f"{k[0]:22s} {str(k[1]):13s} {ph if ph is not None else '-':>8} " + " ".join(line) + f"   {tol}")
    print("\npasses:", {m: {g: f"{sum(r['ok'] for r in allt[m][g])}/{len(allt[m][g])}" for g in GROUPS} for m in ms})
    json.dump(allt, open(f"{F}/out/mtable.json", "w"), indent=1)
