"""folddir.py [label=<identity source> ...]: the overhang as a DIRECTION. hang(c) = v[ka] - v[kb] (mean over the lid's
middle, both eyes) is linear in c, so "what folded heads have in common" is one gradient g per ring pair:
its size (mm per unit |c|), which components carry it, how it couples to the crease's height H = v[ka] - v[0], to the
brow's height over the margin, to the lid's stand-off (cosines of the gradients = correlations under N(0, I)), what a
unit step along it does to gnm_mm's measures, and where named heads sit along it (z)."""
import sys

import numpy as np

import foldopt as fo
import lidstruct as ls
import ohlib as oh

S = fo.setup(0)
B, ch, chR, wc = S["B"], S["ch"], S["chR"], S["wc"]


def lin(k, ax):
    return 0.5 * (np.tensordot(B[:, ch[:, k], ax], wc, 1) + np.tensordot(B[:, chR[:, k], ax], wc, 1))


def cos(a, b):
    return float(a @ b / np.linalg.norm(a) / np.linalg.norm(b))


G = {}
for ka in (3, 4, 5, 6, 7):
    R = fo.rows(S, ka, ka + 2)
    g = R["hang"]
    G[ka] = g
    o = np.argsort(-np.abs(g))[:8]
    blocks = [np.linalg.norm(g[a:b]) ** 2 / (g @ g) for a, b in ((0, 10), (10, 40), (40, 80), (80, 120), (120, 170))]
    brow = lin(12, 1) - lin(0, 1)
    marg = lin(0, 1)
    print(f"rings {ka}->{ka + 2}: template spacing {-R['hang0']:.2f} mm, |g| {np.linalg.norm(g):.3f} mm per unit |c| "
          f"(z to 0: {-R['hang0'] / np.linalg.norm(g):.1f}); share of g^2 in comps 0-10 / 10-40 / 40-80 / 80-120 / 120-170: "
          + " ".join(f"{x:.2f}" for x in blocks))
    print("    top comps:", " ".join(f"{i}:{g[i]:+.3f}" for i in o))
    print(f"    corr with: crease height H {cos(g, R['H']):+.2f} | brow height over the margin {cos(g, brow):+.2f} | margin height {cos(g, marg):+.2f} | "
          f"drape forward of the crease {cos(g, R['gap']):+.2f} | crease ring's stand-off {cos(g, R['so']):+.2f}")
    print(f"    one unit along g: hang {np.linalg.norm(g):+.2f} mm, H {R['H'] @ g / np.linalg.norm(g):+.2f}, brow {brow @ g / np.linalg.norm(g):+.2f}, "
          f"stand-off {R['so'] @ g / np.linalg.norm(g):+.2f} mm")
print("cos between the pairs' directions:", " ".join(f"{a}/{b}:{cos(G[a], G[b]):+.2f}" for a, b in ((3, 4), (4, 5), (5, 6), (6, 7), (3, 6), (4, 7))))
try:
    from hifipushie import gnm_mm
    sp = gnm_mm._space()
    g = G[5] / np.linalg.norm(G[5])
    V0 = sp["T"]
    V1 = sp["T"] + np.tensordot(g, sp["IB"], 1)
    rows = gnm_mm.gaps(V0, V1)
    rows = sorted(rows, key=lambda r: -abs(r.get("gap", 0)))[:8]
    print("one unit along the 5->7 direction moves gnm_mm's measures:", "; ".join(f"{r.get('name', r.get('measure'))} {r.get('gap', 0):+.2f}" for r in rows))
except Exception as ex:  # noqa: BLE001
    print("gnm_mm read failed:", type(ex).__name__, ex)
for a in sys.argv[1:]:
    lab, src = a.split("=", 1)
    c = ls.ident(src)
    print(f"{lab:10s} |c| {np.linalg.norm(c):5.2f} z along g:", " ".join(f"{ka}->{ka + 2}: {G[ka] @ c / np.linalg.norm(G[ka]):+.2f}" for ka in G))
