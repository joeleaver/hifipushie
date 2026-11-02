"""tab1.py <tag> ..: Part 1's tables from work/<tag>/fit_*.json -> markdown on stdout."""
import json
import sys
import gt

for tag in sys.argv[1:]:
    fits = sorted((gt.WORK / tag).glob("fit_*.json"))
    J = {f.stem[4:]: json.loads(f.read_text()) for f in fits}
    order = [k for k in ("p1b3", "p0.25b3", "p1eb3", "p0.25eb3", "p1", "p1e", "p1esb3") if k in J]
    print(f"\n#### {tag}: mean / p90 mm by region (two-sided, the scan's skin)\n")
    print("| region | " + " | ".join(order) + " |")
    print("|---|" + "---|" * len(order))
    for r in gt.REGIONS:
        print(f"| {r} | " + " | ".join((f"{J[k]['table'][r]['mean']:.2f} / {J[k]['table'][r]['p90']:.2f}" if J[k]["table"].get(r) else "-") for k in order) + " |")
    print("| share of GNM face verts compared | " + " | ".join(f"{100 * J[k]['table']['face']['covered']:.0f} %" for k in order) + " |")
    print("| distance from class mean: norm (max sd) | " + " | ".join(f"{J[k]['c_off']:.1f} ({J[k]['c_max']:.1f})" for k in order) + " |")
    print("| scan scale | " + " | ".join(f"{J[k]['S']['s']:.4f}" for k in order) + " |")
    m = J[order[0]]["measures"]
    print("\nmeasures of p1b3 (mm): " + ", ".join(f"{k} {m[k]:.1f}" for k in ("jaw_width", "gonial_width", "chin_width", "cheekbone_width", "skull_width", "pupils_apart", "nose_width", "mouth_width", "chin_length", "nose_length") if k in m))
    import errmap, numpy as np
    c = np.asarray(J[order[0]]["c"])
    c0 = gt.class_mean(gt.load_scan(tag)["info"]["sex"])
    e = errmap.rms(c0, c)
    m0 = errmap.measures(c0)
    print(f"the sex's class mean laid on p1b3 by a similarity: scale {e['scale']:.3f} (the fitted head is {100 * (e['scale'] - 1):+.1f} % the class mean's size); class mean: "
          + ", ".join(f"{k} {m0[k]:.1f}" for k in ("jaw_width", "gonial_width", "chin_width", "cheekbone_width", "skull_width", "pupils_apart")))
