"""who.py <model> [truth=<model>] [cameras=refit|free] [key=value ..]: WHO PUSHES the chin / jaw in one joint solve
(nothing applied). The solve is linear-Gaussian per round: dc = Ai (Jx' w o + prior), so each measure's move splits
exactly into what each group of reads (type, view) contributes. With truth=: each read's error against the known head
(o - J (c_true - c), the cameras' part fitted out per view) per group, and the part of every measure's move that comes
from those ERRORS (the bias the reads put into the measure)."""
import sys, time
import numpy as np
from hifipushie import face_ruler as fr, blockin as bi, store, solve_report as sr

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
truth = kw.pop("truth", None)
cams = kw.pop("cameras", "refit")
rootkw = kw.pop("root", None)
names = kw.pop("measures", "chin_width,jaw_width,gonial_width,jaw_square,jaw_angle,cheekbone_width,neck_width,chin_length,under_chin").split(",")
val = lambda v: {"0": False, "1": True}.get(v, v)  # noqa: E731
chin = {a[5:]: (b if a == "chin.chin_lm" else (float(b) if b.replace(".", "", 1).isdigit() and "." in b else val(b))) for a, b in kw.items() if a.startswith("chin.")}
args = {"lids": True, "lips": True, "parse": "auto", "adapt": True, "cmax": 3.0, **{a: val(b) for a, b in kw.items() if not a.startswith("chin.")}, "chin": chin}
rj = bi._refs(m)
b0 = rj.get("blockin") or {}
root = rootkw or b0.get("root")
c0 = bi.identity(store.load(m))
croot = bi.identity(store.load(root)) if root else c0
cam_sd = {kk: tuple(v) for kk, v in fr.PHOTO_CAM_SD6.items()}
t = time.time()
cam0 = None if cams == "refit" else b0.get("cam_done")
c = fr.compare(m, rounds=1, prior_off=c0 - croot, cam_sd=cam_sd, cam_first=2 if cams == "refit" else 0,
               cam_done0=cam0 if cam0 is not None else np.zeros((len(rj["views"]), 6)), kinds=b0.get("kinds"), readers=b0.get("readers"), **args)
post, obs = c["post"], c["obs"]
Jx, w, pri, n1 = post["Jx"], post["w"], post["pri"], post["n1"]
o = np.array([ob["o"] for ob in obs])
A = (Jx * w[:, None]).T @ Jx + np.diag(1.0 / pri ** 2)
Ai = np.linalg.inv(A)
rw = sr.rows()
R = np.array([rw["R"][rw["names"].index(n)] for n in names])          # (m, 170)
P = R @ Ai[:n1]                                                       # measure per unit of (Jx' w o)
G = {}
for i, ob in enumerate(obs):
    G.setdefault((ob["type"], ob["view"]), []).append(i)
dc = np.asarray(c["dc"], float)
print(f"== {m}: {time.time() - t:.0f} s; reads {len(obs)}; |dc| {np.linalg.norm(dc):.2f}; relax x{c['relax']:.2f}; readers {c['readers']}")
print("the step's move of each measure (mm, macros in sd): " + ", ".join(f"{n} {v:+.2f}" for n, v in zip(names, R @ dc)))
print(f"{'group':22s} {'n':>4s} {'eff sig':>7s} | " + " ".join(f"{n[:11]:>11s}" for n in names))
tot = np.zeros(len(names))
for key, ii in sorted(G.items()):
    g = P @ (Jx[ii].T @ (w[ii] * o[ii]))
    tot += g
    print(f"{key[0] + ' ' + key[1]:22s} {len(ii):4d} {np.median(1 / np.sqrt(w[ii])):7.2f} | " + " ".join(f"{v:+11.2f}" for v in g))
print(f"{'sum of reads':22s} {'':4s} {'':7s} | " + " ".join(f"{v:+11.2f}" for v in tot))
if truth:
    ct = bi.identity(store.load(truth))
    d = ct - c0
    print(f"\nTRUTH {truth}: the true gap of each measure: " + ", ".join(f"{n} {v:+.2f}" for n, v in zip(names, R @ d)))
    e = o - Jx[:, :n1] @ d
    # the cameras' part of the error: fitted per the solve's own camera columns (weighted, their prior)
    C = Jx[:, n1:]
    if C.shape[1]:
        Ac = (C * w[:, None]).T @ C + np.diag(1.0 / pri[n1:] ** 2)
        thc = np.linalg.solve(Ac, C.T @ (w * e))
        e = e - C @ thc
    print("each group's ERROR against the truth (mm; cameras fitted out) and what those errors put into each measure:")
    print(f"{'group':22s} {'n':>4s} {'bias':>6s} {'rms':>6s} | " + " ".join(f"{n[:11]:>11s}" for n in names))
    tot = np.zeros(len(names))
    for key, ii in sorted(G.items()):
        g = P @ (Jx[ii].T @ (w[ii] * e[ii]))
        tot += g
        print(f"{key[0] + ' ' + key[1]:22s} {len(ii):4d} {e[ii].mean():+6.2f} {np.sqrt((e[ii] ** 2).mean()):6.2f} | " + " ".join(f"{v:+11.2f}" for v in g))
    print(f"{'sum (the reads bias)':22s} {'':4s} {'':6s} {'':6s} | " + " ".join(f"{v:+11.2f}" for v in tot))
    # what a PERFECT set of the same reads would give (o = J d): the prior's shrink / leak alone
    th = Ai @ (Jx.T @ (w * (Jx[:, :n1] @ d)) + np.r_[-(c0 - croot), np.zeros(len(pri) - n1)] / pri ** 2 * 0)
    print(f"{'perfect reads':22s} {'':4s} {'':6s} {'':6s} | " + " ".join(f"{v:+11.2f}" for v in R @ th[:n1]) + "   (move with error-free reads of the same kind, same weights; prior centred here)")
    np.savez(f"/mnt/data/hifipushie/chinread/out/who_{m}.npz", e=e, o=o, w=w, typ=np.array([ob["type"] for ob in obs]), view=np.array([ob["view"] for ob in obs]),
             p=np.array([ob.get("p", [np.nan, np.nan]) for ob in obs], float), X=np.array([ob.get("X", [np.nan] * 3) for ob in obs], float),
             names=np.array([ob.get("name", "") for ob in obs]), push=np.array([(P[:, :] @ (Jx[i] * w[i] * e[i])) for i in range(len(obs))]), mnames=np.array(names))
