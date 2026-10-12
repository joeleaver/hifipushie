"""dbgs.py <model> ...: the temple / sideburn strip's gather locks (root az 45-100 on the left, below el 12): count,
and each lock's first points (az / el / h mm), width, density, fine."""
import sys

import numpy as np

from hifipushie import store

for m in sys.argv[1:]:
    L = store.load(m)["hair"]["locks"]
    S = {k: lk for k, lk in L.items() if k.startswith("tg") and 45 < lk["pts"][0][0] < 100 and lk["pts"][0][1] < 12}
    print(m, "strip locks", len(S), "of", sum(k.startswith("tg") for k in L))
    for k, lk in list(S.items())[:: max(1, len(S) // 8)]:
        P = np.asarray(lk["pts"])
        print("  ", k, "az", np.round(P[:5, 0]), "el", np.round(P[:5, 1]), "h", np.round(P[:5, 2] * 1000, 1), "w", lk["width"],
              {a: b for a, b in (lk.get("strands") or {}).items() if a in ("density", "fine", "roots", "rim")})
