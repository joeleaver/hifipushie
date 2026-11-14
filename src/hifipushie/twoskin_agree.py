"""The side skin made to agree with the front and back skins (twoskin_build, hold "rows").

The skins are two or three pictures' accounts of one solid, and the solid is what all of them leave (twoskin.py).
The accounts differ: at the corner of a head the front picture's and the side picture's surfaces lie up to 2 cm
apart, and over a forehead or the front of a face, which the side picture sees edge-on, the side skin as read
lies well INSIDE the surface the front picture shows squarely, and cuts it away. So one of them has to rule each
place, and the handing over must not show.

  the front (back) picture rules   a LAYER under its own skin (fully for LAYER[0] of depth, fading out by
                                   LAYER[1]), where it is to be believed: where its picture shows the surface,
                                   and the more the deeper inside its outline (fully from BAND inside)
  the side skin yields             there it is never narrower than the front or back skin's surface is wide at
                                   that depth: it is lifted to that, and CLEAR beyond
  the side picture rules           everything else: the rim of the face, the sides, and whatever lies deeper than
                                   the layers

The lifting is done to the side skin as a height map, so it stays one surface: nothing can overhang. Tried and
worse (slices and maps in the Baynard notes, sections 22 to 24):
- the same rule made in space (the side skin standing away at points inside the layer): the layer reached out to
  the outline as a thin shell, a lip like the edge of a mask where the side skin took over below it;
- no layer, the side skin yielding only along its own outline: it cut the forehead and pinched the eyes;
- the front and back skins lifted to the side skin's account as well: the side skin has a muzzle as wide as the
  cheeks behind it (its rows are set by their widest point), and the rim of the face was pulled forward to the
  muzzle's depth as a fin; bending both towards each other gave the same fin, wider.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

CLEAR = 0.012             # m: where a front or back skin rules, the side skin stands this far clear of its surface (two
#                           surfaces that touch all along take turns being the solid's, point by point: a rough skin)
EASE = 0.003              # m: what the others say is eased over this much (how wide a nearly flat face is at a depth
#                           changes by centimetres with a millimetre of depth)
BAND = 0.02               # m: a front or back skin is believed fully from this far inside its outline and what its picture shows
LAYER = (0.008, 0.025)    # m under a front or back skin: its picture rules fully down to the first, not at all from the second
FAR = 0.06                # m: what "not at all" is worth: a place that far inside the side skin is no concern of the others


def _ramp(x, a, b):
    s = np.clip((x - a) / (b - a), 0.0, 1.0)
    return s * s * (3 - 2 * s)


def widths(Tf, Tb, agreed, wf, wb, fr: dict, s_shape, sfr: dict) -> np.ndarray:
    """How wide the front and back skins' surfaces are at each depth and height, as far as their pictures rule
    there: on the side grid, metres from the middle (0 where they have nothing to say). Tf, Tb: heights towards
    the front and the back viewer on the front grid; agreed: the outline both pictures show; wf, wb: how much
    each is believed (0..1). fr / sfr: each grid's place, {"u0", "z0", "px", "za", "U", "F"} (pixel (c, r) is
    centred at u0 + (c + 0.5) px along U and z0 - (r + 0.5) px za up)."""
    a, b = float(np.asarray(fr["U"]) @ np.asarray(sfr["F"])), float(np.asarray(fr["F"]) @ np.asarray(sfr["U"]))
    if abs(abs(a) - 1) > 1e-6 or abs(abs(b) - 1) > 1e-6:
        raise ValueError("the two grids are not views at right angles")
    H, W = Tf.shape
    Hs, Ws = s_shape
    wide = np.abs(fr["u0"] + (np.arange(W) + 0.5) * fr["px"])     # how far each front column is from the middle
    t_s = (b * (sfr["u0"] + (np.arange(Ws) + 0.5) * sfr["px"]))[:, None]   # the side's columns as depths towards the front
    zs = sfr["z0"] - (np.arange(Hs) + 0.5) * sfr["px"] * sfr["za"]
    f_of = np.round((fr["z0"] - zs) / (fr["px"] * fr["za"]) - 0.5).astype(int)      # side row -> front row
    x = np.zeros((Hs, Ws))
    for r in np.flatnonzero((f_of >= 0) & (f_of < H)):
        sel = agreed[f_of[r]]
        if not sel.any():
            continue
        hh = wide[sel][None, :]
        for T, w, sign in ((Tf[f_of[r], sel], wf[f_of[r], sel], 1.0), (Tb[f_of[r], sel], wb[f_of[r], sel], -1.0)):
            under = T[None, :] - sign * t_s                       # how deep under this skin
            val = hh + CLEAR - FAR * (1 - w[None, :]) - FAR * _ramp(under, *LAYER)
            x[r] = np.maximum(x[r], np.where(under >= 0, val, 0.0).max(1))
    return x


def agree(Tf, Tb, agreed, dFf, dFb, fr: dict, S, s_own, sfr: dict):
    """(the side skin, what was done, the maps to look at). dFf, dFb: metres inside the agreed outline and what
    the front / the back picture shows. S: the side skin's height on the side grid; s_own: the side outline
    there. The rest as widths()."""
    wf, wb = (_ramp(np.clip(d, 0, None), 0.0, BAND) for d in (dFf, dFb))
    says = widths(Tf, Tb, agreed, wf, wb, fr, S.shape, sfr)
    says = ndimage.maximum_filter(ndimage.gaussian_filter(says, EASE / sfr["px"]), size=3)
    new = np.maximum(S, says)
    ch = (new - S)[s_own]
    about = {"lifted_mm": [round(float(np.percentile(ch, q)) * 1e3, 1) for q in (50, 90, 99)],
             "yields": round(float((s_own & (new > S + 1e-4)).sum() / max(s_own.sum(), 1)), 2)}
    return new, about, {"was": S, "says": says, "share": (new <= S + 1e-4).astype(float), "own": s_own, "now": new}
