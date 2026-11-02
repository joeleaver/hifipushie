"""gsum.py <tag> <label>=<chain prefix> ..: Part 2's tables for one scan from the chain records (out/chains) and the
scan scores (gscore; made here when missing): the solved heads' last call against the SCAN (regions), against the Part
1 direct fit (errmap; the solvecams acceptance measures), the cameras against the TRUE ones, nose and lips signed.
Markdown on stdout; out/sum_<tag>.json."""
import json
import sys
import numpy as np
import gt, gscore, noselip

tag = sys.argv[1]
chains = dict(a.split("=") for a in sys.argv[2:])
scan = gt.load_scan(tag)
recs = {}
for lab, pre in chains.items():
    f = gt.OUT / "chains" / f"{pre}.json"
    if f.exists():
        recs[lab] = json.loads(f.read_text())
last = {lab: r["calls"][-1] for lab, r in recs.items()}


def sc(what):
    f = gt.OUT / "scores" / f"{tag}__{what.replace(':', '_')}.json"
    return json.loads(f.read_text()) if f.exists() else gscore.score(tag, what, scan)


S = {"class mean": sc("mean"), "ceiling (Part 1)": sc("fit:p1b3")}
for lab, c in last.items():
    S[lab] = sc(c["model"])
labs = list(S)
print(f"\n#### {tag}: against the SCAN's surface, mean / p90 mm (each head laid on the scan by its own best pose and scale)\n")
print("| region | " + " | ".join(labs) + " |")
print("|---|" + "---|" * len(labs))
for r in gt.REGIONS:
    print(f"| {r} | " + " | ".join((f"{S[l]['table'][r]['mean']:.2f} / {S[l]['table'][r]['p90']:.2f}" if S[l]["table"].get(r) else "-") for l in labs) + " |")
print("| scan scale to fit (1 = the head has the real size) | " + " | ".join(f"{S[l]['scan_scale']:.3f}" for l in labs) + " |")
print(f"\n#### {tag}: against the Part 1 direct fit (GNM vertex to vertex after a similarity: errmap), and the acceptance measures (solved - fit, mm)\n")
print("| chain | calls | face rms | lower face rms | size % | jaw_width | gonial_width | chin_width | cheekbone_width | distance from the fit (identity norm) |")
print("|---|---|---|---|---|---|---|---|---|---|")
c0 = next(iter(recs.values()))["calls"][0] if recs else None
if c0:
    print(f"| start (class mean) | 0 | {c0['face']:.2f} | {c0['low']:.2f} | {c0['size']:+.1f} | {c0['meas']['jaw_width']:+.1f} | {c0['meas']['gonial_width']:+.1f} | {c0['meas']['chin_width']:+.1f} | {c0['meas']['cheekbone_width']:+.1f} | {c0['dct']:.1f} |")
for lab, c in last.items():
    n = len(recs[lab]["calls"]) - 1
    best = min(recs[lab]["calls"][1:], key=lambda x: x["face"]) if n else c
    print(f"| {lab} | {n} | {c['face']:.2f} (best call {best['face']:.2f}) | {c['low']:.2f} | {c['size']:+.1f} | {c['meas']['jaw_width']:+.1f} | {c['meas']['gonial_width']:+.1f} | {c['meas']['chin_width']:+.1f} | {c['meas']['cheekbone_width']:+.1f} | {c['dct']:.1f} |"
          + (f" REFUSED at call {recs[lab]['error']['call']}" if recs[lab].get("error") else ""))
print(f"\n#### {tag}: recovered cameras against the true ones (last call): yaw / pitch / roll deg, distance %, picture scale %\n")
print("| chain | " + " | ".join(next(iter(last.values()))["cams"]) + " |" if last else "")
print("|---|" + "---|" * (len(next(iter(last.values()))["cams"]) if last else 0))
for lab, c in last.items():
    print(f"| {lab} | " + " | ".join(f"{e['yaw']:+.1f} / {e['pitch']:+.1f} / {e['roll']:+.1f}, dist {e['dist']:+.0f} %, scale {e['scale']:+.1f} %" for e in c["cams"].values()) + " |")
if c0:
    print("| start (as given to the solve of the first chain) | " + " | ".join(f"{e['yaw']:+.1f} / {e['pitch']:+.1f} / {e['roll']:+.1f}, dist {e['dist']:+.0f} %, scale {e['scale']:+.1f} %" for e in c0["cams"].values()) + " |")
ct, cm = noselip.ident("fit:p1b3", tag), noselip.ident("mean", tag)
cmp = noselip.compare(ct, cm, {lab: np.asarray(S[lab]["c"]) for lab in last})
print(noselip.text(cmp, f"\n#### {tag}: nose and lips, signed (solved - Part 1 fit, mm; the solved head scaled onto the fit)\n"))
(gt.OUT / f"sum_{tag}.json").write_text(json.dumps({"scores": {l: {"table": S[l]["table"], "scan_scale": S[l]["scan_scale"], "vs_fit": S[l]["vs_fit"], "meas": S[l]["meas"]} for l in labs},
                                                    "last": last, "noselip": cmp}))
