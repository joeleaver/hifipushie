"""cchain.py <from> <prefix> <n calls> [key=value ...]: blockin.solve_step calls in a row (solvereads' chain.py + any
other solve_step keyword as key=value, + the jaw / chin region's surface error). keys: first=refit|free|trust (the first
call's cameras; default refit), cameras=free (the later calls'), truth=<model> (score every call against a known head:
|c - c_true|, the face's surface rms mm, the jaw / chin region's, the measures' errors), i0=<first index>; anything else
goes to solve_step (anchors=none, chin=..., hold=auto ...)."""
import sys, time
import numpy as np
from hifipushie import blockin as bi, gnm_mm, solve_report as sr, store

src, pre, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
kw = dict(a.split("=", 1) for a in sys.argv[4:])
first, cams = kw.pop("first", "refit"), kw.pop("cameras", "free")
truth = kw.pop("truth", None)
i0 = int(kw.pop("i0", 1))


def val(v):
    if v in ("0", "1"):
        return v == "1"
    if v in ("none", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return v


extra = {a: (b if a in ("anchors", "parse") else val(b)) for a, b in kw.items() if not a.startswith("chin.")}
chin = {a[5:]: (b if a == "chin.chin_lm" else val(b)) for a, b in kw.items() if a.startswith("chin.")}
if chin:
    extra["chin"] = chin
SHOW = ("pogonion_forward", "chin_forward", "chin_length", "chin_width", "jaw_width", "under_chin", "mentolabial_depth", "eyes_forward",
        "brow_ridge_forward", "mouth_width", "gonial_width", "jaw_square", "jaw_angle", "cheekbone_width")


def low_face():
    """GNM vertices of the jaw / chin region: the face's exterior skin below the lower lip's border."""
    sp = gnm_mm._space()
    T = sp["T"] * 1000
    L = sp["WL"] @ T
    return sp["gr"]["hockey_mask"] & sp["gr"]["skin_exterior"] & (T[:, 1] < L[57, 1])


def score(m):
    if not truth:
        return ""
    ct, c = bi.identity(store.load(truth)), bi.identity(store.load(m))
    sp = gnm_mm._space()
    face = sp["gr"]["hockey_mask"]
    D = np.tensordot(c - ct, sp["IB"], 1) * 1000
    d = D[face]
    jc = float(np.sqrt((D[low_face()] ** 2).sum(1).mean()))
    rw = sr.rows()
    e = rw["R"] @ (c - ct)
    worst = sorted(zip(rw["names"], e, e / rw["sd"]), key=lambda t: -abs(t[2]))[:6]
    chin = {nm: float(e[rw["names"].index(nm)]) for nm in SHOW}
    return (f"  TRUTH {truth}: |c - c_true| {np.linalg.norm(c - ct):.2f}; face surface rms {np.sqrt((d ** 2).sum(1).mean()):.2f} mm; jaw / chin rms {jc:.2f} mm; "
            f"measures' rms error {np.sqrt(((e / rw['sd']) ** 2).mean()):.2f} sd\n    worst: " + ", ".join(f"{a} {b:+.1f} ({s_:+.1f} sd)" for a, b, s_ in worst)
            + "\n    chin etc (mm): " + ", ".join(f"{k} {v:+.1f}" for k, v in chin.items()))


print(f"== {src} -> {pre}NN x{n}: first={first} cameras={cams} {extra}")
if truth:
    print(score(src))
prev = None
for i in range(i0, i0 + n):
    out = f"{pre}{i:02d}"
    t = time.time()
    rep = bi.solve_step(src, out=out, cameras=first if i == i0 else cams, **extra)
    so = rep["solve"]
    c = bi.identity(store.load(out))
    c0 = bi.identity(store.load(src))
    cos = "" if prev is None else f", cos with the last step {float((c - c0) @ prev / max(np.linalg.norm(c - c0) * np.linalg.norm(prev), 1e-9)):+.2f}"
    prev = c - c0
    rw = sr.rows()
    mm = rw["R"] @ c
    print(f"-- {out} ({time.time() - t:.0f} s): reads {so['n']}; |dc| {so['dc']:.2f}{cos}; |c| {so['c']:.2f}; largest {so['max_sd']:.2f} sd; relax x{so['relax']:.3f}{' DAMPED x0.5' if so.get('damped', 1) < 1 else ''}; "
          f"table {sum(int(str(v).split('/')[0]) for v in rep['entry']['passes'].values())} / {sum(int(str(v).split('/')[1]) for v in rep['entry']['passes'].values())}")
    print(f"   views: stated {so['stated_yaw']} fitted {so['view_yaw']} kinds {so['kinds']} readers {so['readers']}; adapt {so['sig_scale']}")
    print("   identity (GNM mm / sd, from GNM's mean): " + ", ".join(f"{k} {mm[rw['names'].index(k)]:+.1f}" for k in ("chin_width", "jaw_width", "gonial_width", "jaw_square", "jaw_angle", "chin_length", "chin_forward")))
    if so.get("held"):
        print("   held at the start's value:", ", ".join(so["held"]))
    if so.get("chin"):
        print("   chin / jaw term:", so["chin"])
    if so.get("report"):
        print("   " + so["report"]["text"].replace("\n", "\n   "))
    for x in so.get("notes") or []:
        if x.startswith("VIEW") or x.startswith("CHIN"):
            print("   " + x)
    s_ = score(out)
    if s_:
        print(s_)
    sys.stdout.flush()
    src = out
