"""acc.py <version letter> [heads]: the acceptance table of a suite (mkv.py): per head and start the jaw's width error, the
gonial width's, face / lower face rms, the front camera's pitch error and distance error at the end; per head the SPREAD
of the jaw's width over the starts; the class mean's own errors."""
import json, os, sys
import numpy as np
S = "/mnt/data/hifipushie/solvecams/out"
v = sys.argv[1]; heads = sys.argv[2] if len(sys.argv) > 2 else "abcd"
ST = ("fit", "tru", "pu", "pd", "dh", "dx", "fitt", "put")
LAB = {"fit": "fitted", "tru": "true", "pu": "pitch +8", "pd": "pitch -8", "dh": "dist x0.5", "dx": "dist x2", "fitt": "fitted, trust", "put": "pitch +8, trust"}
print("| head | class mean: face / low / jaw / gonial | " + " | ".join(LAB[s] for s in ST) + " | jaw spread (free starts) | worst face / low |")
print("|---|---|" + "---|" * (len(ST) + 2))
allf, alll, sp = [], [], []
for h in heads:
    cells, jw, worst = [], [], [0, 0]
    c0 = None
    for s in ST:
        f = f"{S}/sc_{h}_Av{v}{s}.json"
        if not os.path.exists(f):
            cells.append("-"); continue
        r = json.load(open(f)); c = r["calls"][-1]
        if s == "fit":
            c0 = r["calls"][0]
        e = list(c["cams"].values())[0]
        cells.append(f"{c['meas']['jaw_width']:+.1f} / {c['meas']['gonial_width']:+.1f}; {c['face']:.2f} / {c['low']:.2f}; p {e['pitch']:+.1f} d {e['dist']:+.0f}%")
        if not s.endswith("t"):
            jw.append(c["meas"]["jaw_width"])
        worst = [max(worst[0], c["face"]), max(worst[1], c["low"])]
        allf.append(c["face"]); alll.append(c["low"])
    sp.append(max(jw) - min(jw) if jw else float("nan"))
    cm = f"{c0['face']:.2f} / {c0['low']:.2f} / {c0['meas']['jaw_width']:+.1f} / {c0['meas']['gonial_width']:+.1f}" if c0 else "-"
    print(f"| {h} | {cm} | " + " | ".join(cells) + f" | {sp[-1]:.1f} | {worst[0]:.2f} / {worst[1]:.2f} |")
print(f"cells: jaw_width / gonial_width error mm; face / lower face rms mm; the front camera's pitch error deg and distance error at the end")
print(f"MEAN over all chains: face {np.mean(allf):.2f}, lower face {np.mean(alll):.2f}; jaw spread mean {np.nanmean(sp):.1f}, worst {np.nanmax(sp):.1f} mm")
