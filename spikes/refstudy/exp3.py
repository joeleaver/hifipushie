"""Why soft? The MAP is the posterior mean (0.25-0.4 sigma rms; a real head is ~1). Does restoring the norm sharpen
the likeness or add noise?  Variants on the detector MAP (+ read):
  scale xA     the fitted deviation times A
  evidenced    scaled only along directions the evidence pinned (posterior variance < 0.5): c + (a-1) * S c
  sample       a draw from the posterior (the MAP + noise of the posterior's own covariance)
3D error on the truth set.  run.sh exp3.py"""
import json

import numpy as np

import exp2
import fitlib
import rs
import subjects
import table as tb
from hifipushie import humanmacro as hm


def post(f):
    H = f["H"][:f["K"], :f["K"]]
    w, U = np.linalg.eigh(H)   # precision; the prior alone is 1
    return w, U


def main():
    subs = [subjects.load(n) for n in subjects.names()]
    rows = {}

    def add(name, s, c):
        sc = rs.score(rs.head(c), s["V"])
        sc["sigma"] = float(np.sqrt((c ** 2).mean()))
        rows.setdefault(name, {})[s["name"]] = sc
    for s in subs:
        for tag, kw in (("MAP", {}), ("MAP+read", {"rows": hm.prior_rows(exp2.reader(s))})):
            f = fitlib.fit(exp2.ev(s), robust=True, **kw)
            c = f["c"]
            w, U = post(f)
            add(f"{tag}", s, c)
            for a in (1.5, 2.0, 3.0):
                add(f"{tag} scale x{a}", s, a * c)
            # along the directions the evidence pinned: posterior variance 1/w < 0.5 (precision > 2)
            pin = U[:, w > 2.0]
            for a in (1.5, 2.0, 3.0):
                add(f"{tag} evidenced x{a} ({pin.shape[1]} dirs)"[:44], s, c + (a - 1) * pin @ (pin.T @ c))
            # shrinkage undone per direction: the posterior mean of a direction with precision w is the evidence's
            # estimate times (w - 1) / w; dividing gives the evidence's own (unshrunk) estimate where w > 2
            un = c + pin @ ((pin.T @ c) * (1.0 / (1 - 1 / w[w > 2.0]) - 1))
            add(f"{tag} unshrunk where pinned", s, un)
            rng = np.random.default_rng(1)
            add(f"{tag} posterior sample", s, c + U @ (rng.normal(0, 1, len(w)) / np.sqrt(w)))
    (rs.D / "out" / "table3.json").write_text(json.dumps(rows, indent=1))
    tb.show(rows)


if __name__ == "__main__":
    main()
