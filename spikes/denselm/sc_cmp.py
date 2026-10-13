"""sc_cmp.py <tag a> <tag b>: two region tables (sc_table.py's out/sc_<tag>.json) side by side: rms per axis (mm) per
view kind x region, a -> b; honesty; the cameras the landmarks imply; the widths; lips / nose against MediaPipe."""
import json
import sys

import numpy as np

A, B = (json.load(open(f"/mnt/data/hifipushie/denselm/out/sc_{t}.json")) for t in sys.argv[1:3])
ta, tb = sys.argv[1:3]
REG = ("lids", "eyes", "brows", "nose", "nose_base", "philtrum", "lips", "lip_border_upper", "lip_border_lower", "lip_seam", "mouth", "chin",
       "cheeks", "forehead", "ears", "scalp_neck", "eyeball")
kinds = sorted({k.rsplit("|", 1)[0] for k in list(A["regions"]) + list(B["regions"])})
print(f"rms per axis mm (honesty): {ta} -> {tb}")
for kc in kinds:
    cells = []
    for r in REG:
        a, b = A["regions"].get(f"{kc}|{r}"), B["regions"].get(f"{kc}|{r}")
        if a or b:
            f = lambda x: "-" if x is None else f"{x['rms_axis']:.2f} ({x['honesty']:.1f})"
            cells.append(f"{r} {f(a)} -> {f(b)}")
    print(f"| {kc} | " + "; ".join(cells) + " |")
for name, T in ((ta, A), (tb, B)):
    print(f"\n{name}: cameras implied on the true head")
    for kind in ("front", "3q", "side72", "side90"):
        cs = [c for c in T["cameras"] if c["kind"] == kind]
        if not cs:
            continue
        f = lambda k: np.array([c[k] for c in cs], float)
        dh = [(c["dist_head_m"] / c["dist_true_m"] - 1) * 100 for c in cs if c.get("dist_head_m")]
        print(f"   {kind:7s}: yaw {f('yaw_err').mean():+.2f} (rms {np.sqrt((f('yaw_err') ** 2).mean()):.2f}); pitch {f('pitch_err').mean():+.2f} (rms {np.sqrt((f('pitch_err') ** 2).mean()):.2f}); "
              f"distance from the landmarks {np.median(f('dist_err_pct')):+.0f} % (median |.| {np.median(np.abs(f('dist_err_pct'))):.0f})"
              + (f"; distance OUTPUT {np.median(dh):+.0f} % (median |.| {np.median(np.abs(dh)):.0f}, worst {max(np.abs(dh)):.0f})" if dh else ""))
    for sub, hs in (("male a b e", "abe"), ("female c d g", "cdg")):
        cs = [c for c in T["cameras"] if c["kind"] == "front" and c["head"] in hs]
        if cs:
            print(f"      front pitch, {sub}: {np.mean([c['pitch_err'] for c in cs]):+.2f}")
    w = T["width"]
    by = {}
    for r in w:
        by.setdefault(r["head"], []).append(r)
    print("   lower-face width error mm / chin x scale per head: " + "; ".join(f"{h} {np.mean([r['lower_face_width_mm'] for r in rs]):+.1f} / {np.mean([r['chin'] for r in rs]):.3f}" for h, rs in by.items())
          + f"; MEAN |width error| {np.mean([abs(np.mean([r['lower_face_width_mm'] for r in rs])) for rs in by.values()]):.2f}, mean {np.mean([r['lower_face_width_mm'] for r in w]):+.2f}")
    for kind in ("front", "3q"):
        rs = [r for r in T.get("h2h", []) if r["kind"] == kind]
        if rs:
            f = lambda k: np.mean([r[k] for r in rs if k in r]) if any(k in r for r in rs) else float("nan")
            print(f"   {kind}: lips outer {f('lips_outer_ours'):.2f} (MediaPipe {f('lips_outer_mp'):.2f}); inner {f('lips_inner_ours'):.2f} ({f('lips_inner_mp'):.2f}); nose base {f('nose_base_ours'):.2f} ({f('nose_base_mp'):.2f})"
                  + (f"; mouth width bias {f('mouth_width_ours'):+.2f} ({f('mouth_width_mp'):+.2f}); alar width {f('alar_width_ours'):+.2f} ({f('alar_width_mp'):+.2f}); dense nose-base width {f('alar_width_dense'):+.2f}" if kind == "front" else ""))
