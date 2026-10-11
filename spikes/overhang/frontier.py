"""frontier.py <out.png>: the evidence sheet. Top row: (1) the frontier: overhang achieved (raw mesh, gnm_fold.read)
against prior cost |dc| for GNM's mean, #376 and Tess (er_s4), rest of the head held at 1 mm, with the brows free and
with the brows held at 0.3 mm; (2) what it costs elsewhere: the brow ring's drop against the overhang; (3) the lid
rows' own freedom (posterior sd of a row's height under the unit prior) against how well the rest of the head is known.
Bottom row: raw sagittal sections (pupil column) of Tess before / crisp fold / overhang, the mean with an overhang,
#376, and the designed target."""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import foldopt as fo  # noqa: E402
import lidstruct as ls  # noqa: E402
from hifipushie import gnm_fold as gf  # noqa: E402

out = sys.argv[1]
fig = plt.figure(figsize=(21, 12.5))
gs = fig.add_gridspec(2, 6, height_ratios=[1, 1.15])
heads = {"GNM mean": (np.zeros(170), 4.7, "tab:blue"), "#376": (ls.ident("gk_s376"), 3.2, "tab:green"), "Tess (er_s4)": (ls.ident("er_s4"), 4.7, "tab:red")}
ax1, ax2, ax3 = fig.add_subplot(gs[0, 0:2]), fig.add_subplot(gs[0, 2:4]), fig.add_subplot(gs[0, 4:6])
D = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5]
for hi, (lab, (c, H, col)) in enumerate(heads.items()):
    for brow, st in ((None, "-o"), (0.3, "--s")):
        R = [gf.fold(c, crease=H, overhang=d, brow=brow) for d in D]
        hg = [r["after"]["hang_mean"] for r in R]
        ax1.plot([r["dc"] for r in R], hg, st, color=col, label=f"{lab}, crease {H} mm" + (", brows held 0.3 mm" if brow else ""))
        ax2.plot(hg, [r["brow_drop"] for r in R], st, color=col, label=lab + (", brows held 0.3 mm" if brow else ""))
        print(lab, brow, " ".join(f"d{d}: hang {h:.2f} |dc| {r['dc']:.1f} brow {r['brow_drop']:.1f}" for d, h, r in zip(D, hg, R)), flush=True)
    r = gf.fold(c, crease=H)
    ax1.plot([r["dc"]], [r["after"]["hang_mean"]], "*", color=col, ms=16)
    ax1.annotate(f"crisp fold: turn {r['after']['turn_mean']:.0f} deg", (r["dc"], 0.0), textcoords="offset points", xytext=(-30, -16 - 13 * hi), fontsize=9, color=col)
ax1.axvspan(12.3, 13.7, color="0.85", zorder=0)
ax1.text(13.0, 1.45, "a typical head's |c|\n(13.0 +- 0.7)", ha="center", fontsize=9)
ax1.set_xlabel("prior cost |dc| (identity, units of GNM's sd)")
ax1.set_ylabel("overhang on the raw mesh, mm (mean over the lid's middle)")
ax1.set_title("FRONTIER: overhang against prior cost, rest of the head held at 1 mm\n(star = recipe A, the crisp fold without an overhang)", fontsize=11)
ax1.legend(fontsize=8, loc="upper left")
ax1.grid(alpha=0.3)
ax1.set_ylim(-0.33, 2.5)
ax2.set_xlabel("overhang, mm")
ax2.set_ylabel("the brow ring comes DOWN over the lid margin, mm")
ax2.set_title("WHAT IT COSTS: the overhang is hooding (the brow descends)\none unit along the cheapest overhang direction: +0.61 mm overhang, brow -2.4 mm (corr -0.95)", fontsize=11)
ax2.legend(fontsize=8)
ax2.grid(alpha=0.3)
# freedom
S = fo.setup(0)
B, ch, chR, wc = S["B"], S["ch"], S["chR"], S["wc"]
sigs = [1e9, 10, 3, 1, 0.3]
for k, col in ((3, "tab:olive"), (5, "tab:orange"), (7, "tab:purple")):
    sd = []
    for sg in sigs:
        Q, _ = fo.hold_gram(S, hold=sg, free_rings=(1, 9))
        Cv = np.linalg.inv(np.eye(len(B)) + Q)
        row = 0.5 * (np.tensordot(B[:, ch[:, k], 1], wc, 1) + np.tensordot(B[:, chR[:, k], 1], wc, 1))
        sd.append(np.sqrt(row @ Cv @ row))
    ax3.plot(range(len(sigs)), sd, "-o", color=col, label=f"ring {k}'s height")
sd = []
R57 = fo.rows(S, 5, 7)
for sg in sigs:
    Q, _ = fo.hold_gram(S, hold=sg, free_rings=(1, 9))
    Cv = np.linalg.inv(np.eye(len(B)) + Q)
    sd.append(np.sqrt(R57["hang"] @ Cv @ R57["hang"]))
ax3.plot(range(len(sigs)), sd, "-s", color="black", lw=2, label="ring 7 against ring 5 (what an overhang reverses)")
ax3.axhline(-R57["hang0"], color="red", ls=":")
ax3.text(0.05, -R57["hang0"] * 1.08, f"needed for ANY overhang: {-R57['hang0']:.2f} mm (template spacing)", color="red", fontsize=9)
ax3.set_yscale("log")
ax3.set_xticks(range(len(sigs)))
ax3.set_xticklabels(["margins only", "10 mm", "3 mm", "1 mm", "0.3 mm"])
ax3.set_xlabel("how well the rest of the head is known (every skin vertex outside upper-lid rings 1-9)")
ax3.set_ylabel("sd left under GNM's unit prior, mm")
ax3.set_title("THE LID'S OWN FREEDOM once the head around it is fixed\n(at 1 mm: 0.03 mm sd against 1.64 needed = 54 sd)", fontsize=11)
ax3.legend(fontsize=8)
ax3.grid(alpha=0.3, which="both")
# sections
import lidmap as lm  # noqa: E402
import sect  # noqa: E402
G = __import__("os").environ["G"] + "/out/"
items = [("Tess before (er_s4)", "er_s4"), ("Tess, recipe A: crisp fold (oh_TD)", "oh_TD"), ("Tess, recipe B: overhang (oh_TG)", "oh_TG"),
         ("GNM mean, recipe B (oh_MB)", "oh_MB"), ("GNM sample #376 as is", "gk_s376"), ("DESIGNED fold (the target)", "npzV:" + G + "fTD_target.npz")]
chs = gf.chains(10.0)
jm = len(chs) // 2
for i, (lab, src) in enumerate(items):
    a = fig.add_subplot(gs[1, i])
    c, e = sect.load(src)
    V = e if (e is not None and np.ndim(e) == 2) else gf.vertices(c)
    ctr, r = lm.eye_frame_raw(c)
    q = gf.read(V)
    for j, col in ((2, "tab:green"), (jm, "black"), (len(chs) - 3, "tab:blue")):
        P = V[chs[j]] - ctr
        rr = np.sqrt(max(r * r - P[0, 0] ** 2, 1e-6))
        th = np.linspace(-0.1, 1.2, 60)
        a.plot(rr * np.cos(th), rr * np.sin(th), color=col, lw=0.6, alpha=0.35)
        a.plot(P[:, 2], P[:, 1], "-o", color=col, ms=3.5, lw=1.3, label=f"column u {P[0, 0]:+.0f} mm")
        a.plot(P[0, 2], P[0, 1], "o", color="red", ms=6)
    a.set_aspect("equal")
    a.set_xlim(8, 24)
    a.set_ylim(-1, 19)
    a.grid(alpha=0.3)
    a.set_title(f"{lab}\noverhang {q['hang_mean']:.2f} mm, turn {q['turn_mean']:.0f} deg, crease {q['h_mean']:.1f} mm up\nbrow ring {q['brow_h']:.1f} mm over the margin", fontsize=9)
    a.set_xlabel("forward, mm")
    if i == 0:
        a.set_ylabel("RAW GNM MESH, sagittal sections: height over the eyeball's centre, mm\n(dots = GNM's rings; red = lid margin; arcs = GNM's eyeball)")
        a.legend(fontsize=7, loc="lower right")
fig.tight_layout()
fig.savefig(out, dpi=100)
print("wrote", out)
