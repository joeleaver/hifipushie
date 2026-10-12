"""bt.py <truth model> <model> ... | bt.py --set <tag>:<truth>:<start> .. --runs N,T3,.. [last call]: solved heads against a
known head, from the stored identities. SHAPE errors: after a similarity fit (errmap: the head's absolute size is the
camera's, not the pictures'): the fitted size error %, the surface rms mm (face / low = chin + jaw body + jaw angle / chin
/ jaw body / jaw angle), each measure's error with the solved head brought to the true head's size (mm; macros sd); then
|c - ct|, |c| and the largest component. --set: one row per run letter and tag (model cz_<tag>_<run>NN, the last existing
call up to `last`), then per run over the tags the mean surface errors and each measure's RMS error and bias."""
import sys
import numpy as np
from hifipushie import blockin as bi, store
import errmap

COLS = ("chin_width", "jaw_width", "gonial_width", "jaw_square", "jaw_angle", "cheekbone_width", "chin_length", "chin_forward", "under_chin", "eyes_forward", "mouth_width")


def row(m, ct):
    c = bi.identity(store.load(m))
    r = errmap.rms(c, ct)
    a, b = errmap.measures(c, r["scale"]), errmap.measures(ct)
    e = [a[k] - b[k] for k in COLS]
    return np.r_[100 * (1 / r["scale"] - 1), r["face"], r["low"], r["chin"], r["jaw body"], r["jaw angle"], e, np.linalg.norm(c - ct), np.linalg.norm(c), np.abs(c).max()]


def show(lab, v):
    return f"{lab:18s} {v[0]:+5.1f} {v[1]:5.2f} {v[2]:5.2f} {v[3]:5.2f} {v[4]:5.2f} {v[5]:5.2f} | " + " ".join(f"{x:+6.1f}" for x in v[6:-3]) + f" | {v[-3]:5.2f} {v[-2]:5.1f} {v[-1]:4.2f}"


print(f"{'model':18s} size%  face   low  chin jbody jangl | " + " ".join(f"{c[:6]:>6s}" for c in COLS) + " | |c-ct|  |c|  max")
if sys.argv[1] == "--set":
    i = sys.argv.index("--runs")
    sets = [a.split(":") for a in sys.argv[2:i]]
    runs = sys.argv[i + 1].split(",")
    last = int(sys.argv[i + 2]) if len(sys.argv) > i + 2 else 3
    acc = {}
    for tag, truth, start in sets:
        ct = bi.identity(store.load(truth))
        v = row(start, ct)
        acc.setdefault("start", []).append(v)
        print(show(f"{tag} start", v))
        for r in runs:
            m = None
            for k in range(last, 0, -1):
                if (store.HOME / f"cz_{tag}_{r}{k:02d}" / "spec.json").exists():
                    m = f"cz_{tag}_{r}{k:02d}"
                    break
            if m is None:
                continue
            v = row(m, ct)
            acc.setdefault(r, []).append(v)
            print(show(f"{tag} {r} ({m[-2:]})", v))
    print("\nper run over the heads: mean size and surface errors; RMS of each measure's error; second line: its mean (the bias)")
    for r, vs in acc.items():
        a = np.array(vs)
        v = np.r_[a[:, :6].mean(0), np.sqrt((a[:, 6:-3] ** 2).mean(0)), a[:, -3:].mean(0)]
        print(show(f"{r} (n {len(a)})", v))
        print(f"{'   bias':18s} {'':35s} | " + " ".join(f"{x:+6.1f}" for x in a[:, 6:-3].mean(0)))
else:
    ct = bi.identity(store.load(sys.argv[1]))
    for m in sys.argv[2:]:
        print(show(m[-18:], row(m, ct)))
