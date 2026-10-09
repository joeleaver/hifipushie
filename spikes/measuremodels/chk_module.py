import time
import numpy as np
import dense, mm, rs
from hifipushie import humannormals as hn
iid = "S2_squarejaw_tq"
it = mm.item(iid)
g = rs.gnm()
c = np.zeros(rs.K_FIT)
A, y = dense.rows("david", mm.pred("david", iid), c, it["cam"], "tq", use=("n",), infl=4.0)
t0 = time.time()
pr = mm.pred("david", iid)["normal"] * hn.calibration()["flip"]
A2, y2, info = hn.rows(pr, rs.head(c), g["IB"][:rs.K_FIT].astype(float), c, it["cam"], 1)
print("module rows", A2.shape, "study rows", A.shape, "seconds", round(time.time() - t0, 1), info)
if A.shape == A2.shape:
    print("max |dA|", np.abs(A - A2).max(), "of", np.abs(A).max(), " max |dy|", np.abs(y - y2).max(), "of", np.abs(y).max())
print(hn.available())
if hn.available() is None:
    t0 = time.time()
    p = hn.predict(mm.SET / f"{iid}.png")
    print("local DAViD seconds", round(time.time() - t0, 1), p["normal"].shape)
    d = (p["normal"] * pr).sum(-1)
    print("local vs GPU-box prediction: mean cos", float(d[p["mask"] > 0.5].mean()))
