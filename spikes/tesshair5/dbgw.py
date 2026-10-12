"""dbgw.py: the ball-head test's wisps that climb (tests/test_hair_flow.py), their points as az / el / h / z."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tests"))
from test_hair_flow import _grow, _world  # noqa: E402

sc, g, line, locks = _grow({"wisps": {"amount": 0.6, "loose": 0}, "hairline": 0})
for k, lk in locks.items():
    if k.startswith("tw"):
        P = _world(sc, lk)
        if P[-1, 2] > P[0, 2] + 0.004:
            az, el, h = sc.coords(P)
            print(k, np.round(az, 0), np.round(el, 0), np.round(h * 1000, 1), np.round(P[:, 2], 3))
