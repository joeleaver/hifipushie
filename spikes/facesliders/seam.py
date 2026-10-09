"""seam.py <model> [seal]: the sealed mouth's FIELD along the seam: at 15 places across the mouth, from 3 mm in front of
the contact to 6 mm behind it (0.25 mm steps), the built field (base.surface's IMLS): a pocket = the field going
positive (outside) again behind the lips' front, a slit = no negative stretch at all. Prints per place the depths
(mm from the contact) where the field is outside, and a summary."""
import copy
import sys

import numpy as np

DEPTH = 6.0  # mm behind the contact (the lips' depth: past ~10 mm a corner reaches the mouth's cavity)

from hifipushie import base, onemesh, store
from hifipushie.spec import expand_mirror


def check(sp, log=print, old=False):
    e = expand_mirror(sp)
    tpl = onemesh.template(sp["base"])
    S = tpl.get("seal_field")
    if old:  # the field as it was before base._sealed_field
        tpl["seal_field"] = None
        base._CACHE.clear()
    sf = base.surface(e, sp["base"])
    if old:
        tpl["seal_field"] = S
    if not S:
        log("no seal_field (not sealed)")
        return None
    P = np.asarray(sf["quads"][0], float)
    U, L = P[np.asarray(S["up"])], P[np.asarray(S["lo"])]
    U, L = U[np.argsort(U[:, 0])], L[np.argsort(L[:, 0])]
    x0, x1 = max(U[0, 0], L[0, 0]), min(U[-1, 0], L[-1, 0])
    xs = np.linspace(x0, x1, 17)[1:-1]
    bad = 0
    for x in xs:
        c = np.array([x, 0.5 * (np.interp(x, U[:, 0], U[:, 1]) + np.interp(x, L[:, 0], L[:, 1])),
                      0.5 * (np.interp(x, U[:, 0], U[:, 2]) + np.interp(x, L[:, 0], L[:, 2]))])
        d = np.arange(-3.0, DEPTH + 0.01, 0.25)  # mm, + = back into the head (+y)
        pts = c[None] + np.c_[np.zeros_like(d), d * 0.001, np.zeros_like(d)]
        f = base._sd_body(pts, sf)
        inside = f < 0
        first = int(np.argmax(inside)) if inside.any() else None
        holes = [] if first is None else [float(v) for v in d[first:][~inside[first:]]]
        if first is None or holes:
            bad += 1
            log(f"x {1000 * x:6.1f} mm: front at {d[first] if first is not None else None} mm, outside again at {holes[:6]}")
    log(f"{bad} of {len(xs)} places with a slit or a pocket behind the seam")
    return bad


if __name__ == "__main__":
    sp = store.load(sys.argv[1])
    sp["base"]["head"].pop("mouth_gap", None)
    sp["base"]["head"].pop("interior", None)
    if len(sys.argv) > 2:
        sp["base"]["head"]["lip_seal"] = float(sys.argv[2])
    check(sp, old=len(sys.argv) > 3)
