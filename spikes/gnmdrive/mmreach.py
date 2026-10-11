"""mmreach.py <set>...: how far a MILLIMETRE vocabulary reaches (never shown to a driver).
For each pair: read every measure on A and B (exact), then
  all   close every gap at once (least-norm dc with J dc = rB - rA)
  top8  close only the 8 largest gaps (in population sd), the other measures held where they are: a driver with a
        perfect eye, 8 moves, no search
scored like a driver (region closed, ID closed, PASS). Reader sets: `cur` = src gnm_mm's 23; `ext` = + the candidate
measures below (EXTRA) for the phrases the manual has no clean control for."""
import json
import sys

import numpy as np

import decomp
import drv
from hifipushie import gnm_mm, gnm_controls as gcm

sp = gnm_mm._space()
Z = gcm.zones()


def extra(V):
    """candidate readers (mm) on GNM-frame vertices (m)."""
    S, gr = sp["sets"], sp["gr"]
    V = V * 1000
    L = sp["WL"] @ V
    eL, eR = V[gr["left_eye"]].mean(0), V[gr["right_eye"]].mean(0)
    ez, ey = 0.5 * (eL[2] + eR[2]), 0.5 * (eL[1] + eR[1])
    zm = lambda z: V[Z[z]].mean(0)
    wid = lambda z: 2 * np.abs(V[Z[z], 0]).mean()
    ears = V[Z["ears"]]
    return {
        "jowl_width": wid("jowls"), "jaw_angle_width": wid("jaw_angle"), "temple_width": wid("temples"),
        "cheek_width": wid("cheeks"), "parotid_width": wid("parotid"), "bridge_width": wid("bridge_walls"),
        "jaw_angle_height": zm("jaw_angle")[1] - L[8, 1],
        "cheek_forward": zm("cheeks")[2] - ez, "malar_forward": zm("malar")[2] - ez,
        "under_eye_forward": zm("tear_trough")[2] - ez, "brow_ridge_forward": zm("brows")[2] - ez,
        "glabella_forward": zm("glabella")[2] - L[27, 2],
        "dorsum_forward": zm("dorsum")[2] - 0.5 * (L[27, 2] + L[30, 2]),
        "tip_height": L[30, 1] - L[33, 1],
        "upper_red": L[51, 1] - L[62, 1], "lower_red": L[66, 1] - L[57, 1],
        "brow_arch": L[[19, 24], 1].mean() - L[[17, 21, 22, 26], 1].mean(),
        "brow_tilt": L[[17, 26], 1].mean() - L[[21, 22], 1].mean(),
        "eye_width": 0.5 * ((L[39, 0] - L[36, 0]) + (L[45, 0] - L[42, 0])),
        "eye_open": 0.5 * ((L[[37, 38], 1].mean() - L[[40, 41], 1].mean()) + (L[[43, 44], 1].mean() - L[[46, 47], 1].mean())),
        "eye_tilt": 0.5 * ((L[36, 1] - L[39, 1]) + (L[45, 1] - L[42, 1])),
        "inner_corners_apart": L[42, 0] - L[39, 0],
        "ear_out": np.ptp(ears[:, 0]), "ear_height": np.ptp(ears[:, 1]),
        "forehead_slope": V[Z["forehead"], 2][V[Z["forehead"], 1] > np.median(V[Z["forehead"], 1])].mean()
                          - V[Z["forehead"], 2][V[Z["forehead"], 1] <= np.median(V[Z["forehead"], 1])].mean(),
        "throat_forward": V[Z["neck"], 2][V[Z["neck"], 2] > np.percentile(V[Z["neck"], 2], 80)].mean() - L[8, 2],
        "mentolabial_depth": zm("mentolabial_sulcus")[2] - 0.5 * (L[57, 2] + V[S["pog"]].mean(0)[2]),
    }


MID = ("cheek_forward", "jaw_angle_height", "upper_red", "lower_red", "tip_height", "ear_out", "dorsum_forward", "eye_open",
       "forehead_slope")


def jac(fn, names):
    r0 = fn(sp["T"])
    J = np.zeros((len(names), 170))
    for k in range(170):
        r = fn(sp["T"] + sp["IB"][k] * 1e-3)
        J[:, k] = [(r[n] - r0[n]) / 1e-3 for n in names]
    return J


def setup(kind):
    if kind == "mid":
        fn = lambda V: {**gnm_mm.readers(V), **{k: v for k, v in extra(V).items() if k in MID}}
        names = list(gnm_mm.HELD) + list(MID)
        return fn, names, jac(fn, names)
    if kind == "cur":
        fn, names = gnm_mm.readers, list(gnm_mm.HELD)
    else:
        fn = lambda V: {**gnm_mm.readers(V), **extra(V)}
        names = list(gnm_mm.HELD) + list(extra(sp["T"]))
    return fn, names, jac(fn, names)


def solve(J, b):
    return J.T @ np.linalg.solve(J @ J.T + 1e-6 * np.eye(len(J)), b)


if __name__ == "__main__":
    K = {k: setup(k) for k in ("cur", "mid")}
    fn, names, J = K["mid"]
    sd = np.linalg.norm(J, axis=1)
    cost = [np.linalg.norm(solve(J, np.eye(len(names))[i])) for i in range(len(names))]
    print("ext readers: sd mm, |dc| per mm:", " ".join(f"{n} {s:.1f}/{c:.2f}" for n, s, c in zip(names, sd, cost)))
    tot = {}
    for s in sys.argv[1:]:
        for i in range(14):
            case = f"{s}_{i:02d}"
            p = drv.HIDDEN / f"{case}.json"
            if not p.exists():
                continue
            h = json.loads(p.read_text())
            cA, cB = np.array(h["A"]), np.array(h["B"])
            regs = [x["region"] for x in h["changes"]]
            VA, VB = sp["T"] + np.tensordot(cA, sp["IB"], 1), sp["T"] + np.tensordot(cB, sp["IB"], 1)
            cs, lab, tops = [], [], None
            for kind, (fn, names, J) in K.items():
                rA, rB = fn(VA), fn(VB)
                gap = np.array([rB[n] - rA[n] for n in names])
                cs.append(cA + solve(J, gap))
                lab.append(kind + ":all")
                sdk = np.linalg.norm(J, axis=1)
                free = [j for j, n in enumerate(names) if not n.startswith("_")]
                top = sorted(free, key=lambda j: -abs(gap[j]) / sdk[j])[:8]
                b = np.zeros(len(names))
                b[top] = gap[top]
                cs.append(cA + solve(J, b))
                lab.append(kind + ":top8")
                # top4, and top8 read with a 1 mm (sd) ruler error on every gap (photo readers drift 1-1.5 mm)
                b = np.zeros(len(names))
                b[top[:4]] = gap[top[:4]]
                cs.append(cA + solve(J, b))
                lab.append(kind + ":top4")
                rng = np.random.default_rng(i)
                gn = gap + rng.normal(0, 1.0, len(gap))
                topn = sorted(free, key=lambda j: -abs(gn[j]) / sdk[j])[:8]
                b = np.zeros(len(names))
                b[topn] = gn[topn]
                cs.append(cA + solve(J, b))
                lab.append(kind + ":top8n")
                if kind == "mid":
                    tops = [f"{names[j]} {gap[j]:+.1f}" for j in top]
            g = decomp.grade(cA, cB, cs, regs)
            for l, x in zip(lab, g):
                tot.setdefault(l, []).append(x["pass"])
            print(case, h["difficulty"][:4], "+".join(regs).ljust(18),
                  " | ".join(f"{l} {x['region']:.2f}/{x['id']:.2f}{'*' if x['pass'] else ' '}" for l, x in zip(lab, g)), flush=True)
            print("      top8:", ", ".join(tops))
    print({k: f"{sum(v)}/{len(v)}" for k, v in tot.items()})
