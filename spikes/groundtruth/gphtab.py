"""gphtab.py <tag> <label>=<chain prefix> ..: ONE table over chains of one scan for the nose / lips / distance question:
per chain the recovered camera distances (f / 45 / 90, % off the truth), the surface distance to the scan (face,
nose, lips, jaw line; gscore, made when missing), the signed nose and lip measures and jaw_width (solved - Part 1 fit)."""
import json
import sys
import numpy as np
import gt, gscore, noselip

tag = sys.argv[1]
chains = dict(a.split("=") for a in sys.argv[2:])
scan = None
ct, cm = noselip.ident("fit:p1b3", tag), noselip.ident("mean", tag)
rows = []
KEYS = ("nose_base_width", "alar_width", "tip_width", "tip_radius_h", "nose_projection", "mouth_width", "upper_vermilion_mid", "lower_vermilion_mid")
print("| chain | calls | distance f / 45 / 90 % (start -> end) | face / nose / lips / jaw line mm to the scan | " + " | ".join(KEYS) + " | jaw_width |")
print("|---|---|---|---|" + "---|" * (len(KEYS) + 1))
for lab, pre in chains.items():
    f = gt.OUT / "chains" / f"{pre}.json"
    if not f.exists():
        print(f"| {lab} | (not run) |")
        continue
    r = json.loads(f.read_text())
    c0, c = r["calls"][0], r["calls"][-1]
    sf = gt.OUT / "scores" / f"{tag}__{c['model']}.json"
    if sf.exists():
        s = json.loads(sf.read_text())
    else:
        scan = scan or gt.load_scan(tag)
        s = gscore.score(tag, c["model"], scan)
    t = s["table"]
    m = noselip.compare(ct, cm, {"x": np.asarray(s["c"])})["models"]["x"]
    d0 = " / ".join(f"{e['dist']:+.0f}" for e in c0["cams"].values())
    d1 = " / ".join(f"{e['dist']:+.0f}" for e in c["cams"].values())
    print(f"| {lab} | {len(r['calls']) - 1} | {d0} -> {d1} | {t['face']['mean']:.2f} / {t['nose']['mean']:.2f} / {t['lips']['mean']:.2f} / {t['jaw line']['mean']:.2f} | "
          + " | ".join(f"{m[k]:+.1f}" for k in KEYS) + f" | {c['meas']['jaw_width']:+.1f} |")
m0 = noselip.compare(ct, cm, {})["mean_err"]
print(f"| (the class mean, the start) | 0 | | | " + " | ".join(f"{m0[k]:+.1f}" for k in KEYS) + " | |")
