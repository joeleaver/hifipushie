"""widthval.py <model.pt> <data root> <dressing dirs..>: WHERE DOES THE WIDTH BIAS COME FROM? On held-out synthetic
near-frontal samples (|yaw| < 20, clean crops) the lower face's width as the network places it against the truth
(x scale of the cheek + chin landmarks about the face's mid-line, in the crop), regressed on what could cause it: the
head's own jaw width (GNM mm from the mean: a NEGATIVE slope = it answers with the average jaw), the camera's distance
(log m: perspective misread), the sex of the dressing, hair, the hard top light. Torch venv (no hifipushie): the jaw
measure's row over the 170 components is passed in a json made by widthval_rows.py."""
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
import train as T  # noqa: E402

model, root, dirs = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]
rows = json.loads((Path(__file__).parent / "width_rows.json").read_text())
Ld = json.loads((root / "landmarks.json").read_text())
L = {"mirror": np.array(Ld["mirror"]), "lm68": np.array(Ld["lm68"]), "region": np.array(Ld["region"]), "n": Ld["n"]}
tmp = Path("/mnt/data/hifipushie/denselm/out/widthval_root")
tmp.mkdir(exist_ok=True)
for d in dirs:
    if not (tmp / d).exists():
        (tmp / d).symlink_to(root / d)
(tmp / "landmarks.json").write_text((root / "landmarks.json").read_text())
pk = Path("/mnt/data/hifipushie/denselm/out/widthval_pack")
pk.mkdir(exist_ok=True)
P = T.pack(tmp, pk)
meta = [dict(np.load(root / d / "meta.npz", allow_pickle=False)) for d in sorted(dirs)]
dress = [json.loads((root / d / "dressing.json").read_text()) for d in sorted(dirs)]
ident = np.concatenate([m["identity"] for m in meta])
light = np.concatenate([np.array(["hard_top" in str(x) for x in m["light"]]) for m in meta])
male = np.concatenate([np.full(len(m["identity"]), float(dr["male"])) for m, dr in zip(meta, dress)])
hair = np.concatenate([np.full(len(m["identity"]), float(bool(dr.get("hair")))) for m, dr in zip(meta, dress)])
sel = np.where(np.abs(P["yaw"]) < 20)[0]
ds = T.Data(P, sel, L, False)
net = torch.jit.load(model).eval()
torch.set_num_threads(6)
reg = L["region"]
low = np.isin(reg, ("cheeks", "chin"))
inner = np.isin(reg, ("eyes", "lids", "nose", "lips", "mouth"))
out = []
for k in range(len(sel)):
    x, t, vis, mmpx, i = ds[k]
    with torch.no_grad():
        o = net(torch.from_numpy((x * T.STD[:, None, None] + T.MEAN[:, None, None])[None]))[0].numpy()
    p, tt = o[:-1, :2], t[:-1]
    x0 = tt[inner, 0].mean()
    a, b = tt[low, 0] - x0, p[low, 0] - x0
    ai, bi = tt[inner, 0] - x0, p[inner, 0] - x0
    out.append((float(a @ b / (a @ a)), float(ai @ bi / (ai @ ai)), float(np.exp(o[-1, 0] * T.DIST_UNIT)), int(i)))
out = np.array(out)
i = out[:, 3].astype(int)
jw = (ident[i] - np.array(rows["mean"])) @ np.array(rows["jaw_width"])
y = (out[:, 0] - 1) * 100
A = np.stack([np.ones(len(i)), jw / 10.0, np.log(P["dist"][i]), male[i], hair[i], light[i].astype(float)], 1)
co, *_ = np.linalg.lstsq(A, y, rcond=None)
print(f"{len(i)} near-frontal held-out samples: lower-face width as placed, % of the true: mean {y.mean():+.2f}, sd {y.std():.2f}; the inner face's: {((out[:, 1] - 1) * 100).mean():+.2f}")
print("regression of the width error (pct) on: constant %+.2f; jaw width +10 mm %+.2f; log distance (x e) %+.2f; male %+.2f; hair %+.2f; hard top light %+.2f" % tuple(co))
for lo, hi in ((-99, -6), (-6, -2), (-2, 2), (2, 6), (6, 99)):
    m = (jw >= lo) & (jw < hi)
    if m.sum() > 5:
        print(f"   true jaw width {lo:+d}..{hi:+d} mm from GNM's mean (n {m.sum()}): width error {y[m].mean():+.2f} % = {y[m].mean() / 100 * 130:+.2f} mm on a 130 mm jaw")
for lo, hi in ((0.2, 0.5), (0.5, 1.0), (1.0, 3.1)):
    m = (P["dist"][i] >= lo) & (P["dist"][i] < hi)
    if m.sum() > 5:
        dr_ = out[m, 2] / P["dist"][i][m]
        print(f"   camera {lo}-{hi} m (n {m.sum()}): width error {y[m].mean():+.2f} %; distance output / true: median {np.median(dr_):.2f} (p10 {np.percentile(dr_, 10):.2f}, p90 {np.percentile(dr_, 90):.2f})")
ld = np.log(out[:, 2]) - np.log(P["dist"][i])
print(f"distance output: log-slope against the truth {np.polyfit(np.log(P['dist'][i]), np.log(out[:, 2]), 1)[0]:.2f} (1 = right), median |error| {np.median(np.abs(np.expm1(ld))) * 100:.0f} %")
