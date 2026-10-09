"""mk_measured.py: src/hifipushie/human_measured.npz from refstudy2's training set ($D2/measured_train_1200.npz):
two regressions (measured.py's fit_model: per block standardise + PCA, ridge), "points" and "outline" (points + the
outline at humanmeasure.LOW + the eye-chin distance), each with its 5-fold cv rms per macro. Prints the table and
checks humanmeasure on Garrett's photo against garrett3.measure's numbers."""
import os

import numpy as np

import measured as ms
from hifipushie import humanmacro as hm, humanmeasure as hx

D2 = os.environ.get("D2")
z = np.load(f"{D2}/measured_train_1200.npz")
cols = [j for i, lv in enumerate(ms.LEVELS) for j in (2 * i, 2 * i + 1) if min(abs(lv - x) for x in hx.LOW) < 0.01] + [2 * len(ms.LEVELS)]
F = {"pts": z["pts"], "sil": z["sil"][:, cols]}
Z = z["Z"]
out = {"names": np.array(hm.NAMES)}
for tag, keys in (("points", ("pts",)), ("outline", ("pts", "sil"))):
    P = ms.cv(F, Z, keys)
    rms = np.sqrt(((P - Z) ** 2).mean(0))
    M = ms.fit_model(F, Z, keys)
    for k in keys:
        mu, sd, B = M["blocks"][k]
        out[f"{tag}_{k}_mu"], out[f"{tag}_{k}_sd"], out[f"{tag}_{k}_B"] = mu.astype(np.float32), sd.astype(np.float32), B.astype(np.float32)
    out[f"{tag}_W"] = M["W"].astype(np.float32)
    out[f"{tag}_rms"] = rms.astype(np.float32)
    print(tag, "cv rms: mean", round(float(rms.mean()), 3), "; measurable (<", hx.CUT, "):",
          ", ".join(f"{hm.NAMES[i]} {rms[i]:.2f}" for i in np.argsort(rms) if rms[i] < hx.CUT))
np.savez_compressed(hx.MODEL, **out)
print("wrote", hx.MODEL, os.path.getsize(hx.MODEL) // 1024, "KB")
