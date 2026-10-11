"""lidstruct.py: identities from anywhere + the upper lid's STRUCTURE read on GNM's raw mesh by ring (library)."""
import json

import numpy as np

import lidmap as lm
from hifipushie import gnm_controls as gc


def ident(src):
    """An identity (170,) from: a model name | "mean" | json:<path>:<key> (a list in a json file, e.g. gnmdrive's
    hidden/s5_04.json:B or cases/r5_04/state.json:c) | npz:<path>:<key> | cls:<sex>:<ethnicity> (the sampler's class
    mean, z = 0; sex female | male | 0..1, ethnicity a name or all)."""
    from hifipushie import blockin as bi, store
    if src == "mean":
        return np.zeros(170)
    if src.startswith("json:"):
        _, p, k = src.split(":")
        return np.asarray(json.load(open(p))[k], float)[:170]
    if src.startswith("npz:"):
        _, p, k = src.split(":")
        return np.asarray(np.load(p)[k], float)[:170]
    if src.startswith("cls:"):
        from hifipushie import gnm_sampler as gs
        _, sex, eth = src.split(":")
        try:
            sex = float(sex)
        except ValueError:
            pass
        return gs.identity()(np.zeros(64), gs.id_label(sex, None if eth == "all" else eth))[0][:170]
    return bi.identity(store.load(src))


def structure(c, e=None, u=0.0):
    """The lid's structure at a column on GNM's RAW mesh, by ring (mm, against GNM's own 14.5 mm ball):
    margin_v     the margin's height over the ball's centre
    crease_ring  the ring where the surface turns forward most (rings 3..8), crease_h its height over the margin
    platform_s   mean stand-off of rings 2..crease (0 = lying on the ball)
    roll         the margin roll: max stand-off of rings 0..2 - the crease's
    tuck         deg: the turn of the surface at the crease ring (segment above vs segment below)
    wall         deg from the ball's surface, crease -> 2 rings up
    drape        stand-off 3 mm of skin above the crease - the crease's
    hang         mm: how far the fold's rings (crease+1..+4) come DOWN below the crease ring in a front view (overhang)
    brow         stand-off at ring 11; row = the ring spacing at the crease (the mesh's resolution there)."""
    V = gc.vertices(c, e) * 1000
    ctr, r = lm.eye_frame_raw(c)
    col = {k: (v, w) for k, v, w in lm.column(V, ctr, u)}
    ks = [k for k in range(0, 12) if k in col]
    v = np.array([col[k][0] for k in ks])
    w = np.array([col[k][1] for k in ks])
    s = np.sqrt(u * u + v * v + w * w) - r
    a = np.r_[0, np.cumsum(np.hypot(np.diff(v), np.diff(w)))]
    sl = np.degrees(np.arctan2(np.diff(s), np.diff(a)))
    turn = np.diff(sl)
    ic = max(range(3, 9), key=lambda i: turn[i - 1])
    return {"margin_v": float(v[0]), "crease_ring": ks[ic], "crease_h": float(v[ic] - v[0]), "crease_s": float(s[ic]),
            "platform_s": float(s[2:ic + 1].mean()), "roll": float(s[:3].max() - s[ic]), "tuck": float(turn[ic - 1]),
            "wall": float(np.degrees(np.arctan2(s[ic + 2] - s[ic], a[ic + 2] - a[ic]))),
            "drape": float(np.interp(a[ic] + 3.0, a, s) - s[ic]), "hang": float(max(v[ic] - v[ic + 1:ic + 5].min(), 0.0)),
            "brow": float(s[-1]), "brow_v": float(v[-1] - v[0]),
            "row": float(0.5 * (a[ic + 1] - a[ic - 1])), "s": s.round(2).tolist(), "v": v.round(2).tolist()}


KEYS = ("margin_v", "crease_ring", "crease_h", "platform_s", "roll", "tuck", "wall", "drape", "hang", "brow", "brow_v", "row")


def mean_structure(c, e=None, us=(-4.0, 0.0, 4.0)):
    q = [structure(c, e, u) for u in us]
    out = {k: float(np.mean([x[k] for x in q])) for k in KEYS}
    out["s"] = q[len(q) // 2]["s"]
    return out
