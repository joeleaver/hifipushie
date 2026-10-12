"""chain.py <from> <prefix> <n calls> [key=value ...]: blockin.solve_step calls in a row (no sheets), each a new model
<prefix><nn>. keys: first=refit|free|trust (the first call's cameras; default refit), cameras=free (the later calls'),
hold=auto|none, expression=view|shared|none, jaw=1 (detector jaw line 3..13 as anchors), share=1.0, truth=<model>
(score every call against a known head: |c - c_true|, the face's surface rms mm, the measures' errors).
Prints per call: reads, |dc|, |c|, largest comp, relax, the moved-without-a-read report, the expression."""
import sys, time
import numpy as np
from hifipushie import blockin as bi, gnm_mm, solve_report as sr, store

src, pre, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
kw = dict(a.split("=", 1) for a in sys.argv[4:])
first, cams = kw.pop("first", "refit"), kw.pop("cameras", "free")
hold = {"auto": "auto", "none": None}[kw.pop("hold", "none")]
expr = {"view": "view", "shared": "shared", "none": False}[kw.pop("expression", "none")]
jaw = tuple(range(3, 14)) if kw.pop("jaw", "0") == "1" else None
share = float(kw.pop("share", 1.0))
truth = kw.pop("truth", None)
i0 = int(kw.pop("i0", 1))
assert not kw, kw


def score(m):
    if not truth:
        return ""
    ct, c = bi.identity(store.load(truth)), bi.identity(store.load(m))
    sp = gnm_mm._space()
    face = sp["gr"]["hockey_mask"]
    d = np.tensordot(c - ct, sp["IB"], 1)[face] * 1000
    rw = sr.rows()
    e = rw["R"] @ (c - ct)
    worst = sorted(zip(rw["names"], e, e / rw["sd"]), key=lambda t: -abs(t[2]))[:6]
    chin = {nm: float(e[rw["names"].index(nm)]) for nm in ("pogonion_forward", "chin_forward", "chin_length", "chin_width", "jaw_width", "under_chin", "mentolabial_depth", "eyes_forward", "brow_ridge_forward", "mouth_width")}
    return (f"  TRUTH {truth}: |c - c_true| {np.linalg.norm(c - ct):.2f}; face surface rms {np.sqrt((d ** 2).sum(1).mean()):.2f} mm (p95 {np.percentile(np.linalg.norm(d, axis=1), 95):.2f}); "
            f"measures' rms error {np.sqrt(((e / rw['sd']) ** 2).mean()):.2f} sd\n    worst: " + ", ".join(f"{a} {b:+.1f} ({s_:+.1f} sd)" for a, b, s_ in worst)
            + "\n    chin etc (mm): " + ", ".join(f"{k} {v:+.1f}" for k, v in chin.items()))


print(f"== {src} -> {pre}NN x{n}: first={first} cameras={cams} hold={hold} expression={expr} jaw={bool(jaw)} share={share}")
if truth:
    print(score(src))
prev = None
for i in range(i0, i0 + n):
    out = f"{pre}{i:02d}"
    t = time.time()
    rep = bi.solve_step(src, out=out, cameras=first if i == i0 else cams, hold=hold, expression=expr, jaw_lm=jaw, share=share)
    so = rep["solve"]
    c = bi.identity(store.load(out))
    c0 = bi.identity(store.load(src))
    cos = "" if prev is None else f", cos with the last step {float((c - c0) @ prev / max(np.linalg.norm(c - c0) * np.linalg.norm(prev), 1e-9)):+.2f}"
    prev = c - c0
    print(f"-- {out} ({time.time() - t:.0f} s): reads {so['n']}; |dc| {so['dc']:.2f}{cos}; |c| {so['c']:.2f}; largest {so['max_sd']:.2f} sd; relax x{so['relax']:.3f}{' DAMPED x0.5' if so.get('damped', 1) < 1 else ''}; "
          f"table {sum(int(str(v).split('/')[0]) for v in rep['entry']['passes'].values())} / {sum(int(str(v).split('/')[1]) for v in rep['entry']['passes'].values())}")
    print(f"   views: stated {so['stated_yaw']} fitted {so['view_yaw']} kinds {so['kinds']} readers {so['readers']}; adapt {so['sig_scale']}")
    if so.get("held"):
        print("   held at the start's value:", ", ".join(so["held"]))
    for pc, d in (so.get("expression") or {}).items():
        print(f"   expression {pc}: " + ", ".join(f"{k} {v[0]:+.2f}+-{v[1]:.2f}" for k, v in d.items()))
    if so.get("report"):
        print("   " + so["report"]["text"].replace("\n", "\n   "))
    for x in so.get("notes") or []:
        if x.startswith("VIEW"):
            print("   " + x)
    s_ = score(out)
    if s_:
        print(s_)
    sys.stdout.flush()
    src = out
