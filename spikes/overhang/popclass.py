"""popclass.py [n=400]: does the sampling population make folds rare? ohlib.read (overhang, turn, crease height) over
identities drawn from: N(0, I) on the 170 comps; N(0, 1.3 I); GNM's semantic sampler per class (z ~ N(0, I), sex x
ethnicity) and uniform blends; and the sampler's expression prototypes dialled on the mean and on #376 (lead 5: does
any data-backed expression form the fold?)."""
import sys

import numpy as np

import ohlib as oh
from hifipushie import gnm_sampler as gs

n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
rng = np.random.default_rng(11)
ch = oh.chains(7.0)


def stats(C, lab, E=None):
    hg, tr, hh, hx = [], [], [], []
    for i, c in enumerate(C):
        q = oh.read(oh.verts(c[:170], None if E is None else E[i]), ch)
        hg.append(q["hang_mean"])
        hx.append(q["hang_max"])
        tr.append(q["turn_mean"])
        hh.append(q["h_mean"])
    hg, tr, hh, hx = map(np.array, (hg, tr, hh, hx))
    tall = hh >= 4.0
    print(f"{lab:28s} n {len(C):4d} |c| {np.mean(np.linalg.norm(C[:, :170], axis=1)):5.1f} | overhang > 0.1 mm (mean over columns): {(hg > 0.1).mean() * 100:5.2f} %, any column: {(hx > 0.1).mean() * 100:5.2f} %, max {hx.max():.2f} mm "
          f"| turn p50 {np.median(tr):4.0f} p90 {np.percentile(tr, 90):4.0f} max {tr.max():4.0f} | crease >= 4 mm up: {tall.mean() * 100:4.0f} %, there turn p90 {np.percentile(tr[tall], 90) if tall.any() else 0:4.0f} max {tr[tall].max() if tall.any() else 0:4.0f}")
    return hg, tr, hh


stats(rng.standard_normal((n * 3, 170)), "N(0, I)")
stats(1.3 * rng.standard_normal((n, 170)), "N(0, 1.3^2 I)")
D = gs.identity()
for sex in gs.GENDER:
    for eth in gs.ETH:
        C = D(rng.standard_normal((n, 64)), gs.id_label(sex, eth))
        stats(C, f"sampler {sex} {eth}")
stats(D(rng.standard_normal((n, 64)), gs.id_label(0.5, None)), "sampler blend (all classes)")
stats(D(1.5 * rng.standard_normal((n, 64)), gs.id_label("male", "white")), "sampler male white, z x 1.5")
print("\nexpression prototypes (z = 0) x amount, on the mean / on #376 (identity fixed): hang mean, turn, crease height")
import lidstruct as ls  # noqa: E402
heads = {"mean": np.zeros(170), "s376": ls.ident("gk_s376")}
for cls in gs.EXPR:
    e = gs.prototype(cls)
    out = []
    for hn, c in heads.items():
        for a in (1.0, 2.0):
            q = oh.read(oh.verts(c, a * e), ch)
            out.append(f"{hn} x{a:g}: {q['hang_mean']:.2f} / {q['turn_mean']:.0f} / {q['h_mean']:.1f}")
    print(f"  {cls:14s} |e_eye| {np.linalg.norm(e[:100]):4.1f} | " + " | ".join(out))
