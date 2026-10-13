"""tab.py <regex over chain tags> [call index | last] [md]: the chains' records (out/<tag>.json) as one table: the
last call's shape errors and each view's camera error; md = markdown rows."""
import glob, json, os, re, sys
import numpy as np
S = "/mnt/data/hifipushie/solvecams/out"
pat = re.compile(sys.argv[1])
which = sys.argv[2] if len(sys.argv) > 2 else "last"
md = "md" in sys.argv
rows = []
for f in sorted(glob.glob(f"{S}/sc_*.json")):
    tag = os.path.basename(f)[:-5]
    if not pat.fullmatch(tag):
        continue
    r = json.load(open(f))
    c = r["calls"][-1 if which == "last" else int(which)]
    c0 = r["calls"][0]
    cams = " | ".join(f"{e['yaw']:+5.1f} {e['pitch']:+5.1f} {e['scale']:+5.1f}" for e in c["cams"].values())
    cams0 = " | ".join(f"{e['yaw']:+5.1f} {e['pitch']:+5.1f}" for e in c0["cams"].values())
    m = c["meas"]
    rows.append((tag, len(r["calls"]) - 1, c))
    sep = " | " if md else "  "
    print(("| " if md else "") + sep.join([f"{tag:16s}", f"{len(r['calls']) - 1}", f"start {cams0}", f"end {cams}", f"face {c['face']:.2f} low {c['low']:.2f} chin {c['chin']:.2f} jawb {c['jaw body']:.2f} jawa {c['jaw angle']:.2f}",
                                            f"jaw_w {m['jaw_width']:+5.1f} gon {m['gonial_width']:+5.1f} chin_w {m['chin_width']:+5.1f} cheekb {m['cheekbone_width']:+5.1f}",
                                            f"size {c['size']:+.1f}", f"relax x{c.get('relax', 1):.2f}", f"|dc| {c.get('dc', 0):.2f}", f"|c-ct| {c['dct']:.1f}"]) + (" |" if md else ""))
if rows:
    A = np.array([[c["face"], c["low"], c["chin"], c["jaw body"], c["jaw angle"], abs(c["meas"]["jaw_width"]), abs(c["meas"]["gonial_width"]), abs(c["meas"]["chin_width"]), abs(c["meas"]["cheekbone_width"]), c.get("relax", 1)] for _, _, c in rows])
    print(f"MEAN over {len(rows)}: face {A[:, 0].mean():.2f} low {A[:, 1].mean():.2f} chin {A[:, 2].mean():.2f} jawb {A[:, 3].mean():.2f} jawa {A[:, 4].mean():.2f} | mean |err| jaw_w {A[:, 5].mean():.1f} gon {A[:, 6].mean():.1f} chin_w {A[:, 7].mean():.1f} cheekb {A[:, 8].mean():.1f} | relax x{A[:, 9].mean():.2f}")
