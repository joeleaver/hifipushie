"""Macros MEASURED on a front picture (the reference-modelling study's item C, behind a flag): humanmacro's macros
regressed from what one picture gives without knowing the camera: the detector's 478 points (aligned on the irises,
in interocular units) and, when the head stands against a PLAIN backdrop, the outline's widths at the levels of the
cheeks and jaw (0.6 and 0.75 of the way from the eye line to the chin: lower, a collar is the edge; higher, ears and
hair). The regression (`human_measured.npz`) was calibrated on 1200 RENDERS of sampled heads (random pose, lens,
light, clay or tinted skin, a third with an expression): its sigmas are cross-validated on those renders and
stretched by SIGMA (the truth set's error was ~1.5 x the cv rms). On a photograph (stubble, hair, real light) it is
NOT validated: "renders only". The shading features of the study (which give the depth macros: bridge, brow ridge,
eye depth) are left out on purpose: they know only our render's shader.

  measure(image, P478, backdrop=False) -> {macro: (sigmas, +-)} for the macros a picture can measure (cv rms < CUT)
  backdrop_mask(image) -> the head against a plain backdrop (colour distance from the top corners)
`humanfit_map.fit(..., measure=True)` gives these to the MAP as evidence under a said read (the read wins where both
speak); MCP: human_reference(..., measure=True).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

MODEL = Path(__file__).with_name("human_measured.npz")
LEVELS = np.linspace(-0.9, 1.5, 17)     # outline levels the training set holds: 0 = the eye line, 1 = the chin (point 152)
LOW = (0.6, 0.75)                        # the levels a photo shows
IRIS, CHIN = (468, 473), 152
CUT = 0.7      # cv rms (population sigmas; 1 = knows nothing) past which a macro is not measured
SIGMA = 1.5    # the truth set's error over the cv rms
_M = {}


def model() -> dict:
    if not _M:
        z = np.load(MODEL, allow_pickle=False)
        _M.update({k: z[k] for k in z.files})
        _M["names"] = [str(n) for n in z["names"]]
    return _M


def features(P, mask=None) -> dict:
    """{"pts": (956,) the points aligned on the irises / interocular, "sil": the mask's half widths (left, right of
    the mid-line) at LOW + the eye line -> chin distance, all / interocular} (sil None without a mask)."""
    P = np.asarray(P, float)[:, :2]
    e0, e1 = P[IRIS[0]], P[IRIS[1]]
    io = float(np.linalg.norm(e1 - e0))
    mid = 0.5 * (e0 + e1)
    ax = (e1 - e0) / io
    if ax[0] < 0:
        ax = -ax
    up = np.array([-ax[1], ax[0]])
    if (P[CHIN] - mid) @ up < 0:
        up = -up                         # points DOWN the face
    Q = np.c_[(P - mid) @ ax, (P - mid) @ up] / io
    hgt = float(Q[CHIN, 1])
    sil = None
    if mask is not None:
        m = np.asarray(mask, bool)
        h, w = m.shape
        sil = []
        for lv in LOW:
            c = mid + up * (lv * hgt * io)
            t = np.arange(-2.2 * io, 2.2 * io)
            xy = c[None] + t[:, None] * ax[None]
            u, v = np.round(xy[:, 0]).astype(int), np.round(xy[:, 1]).astype(int)
            ok = (u >= 0) & (u < w) & (v >= 0) & (v < h)
            on = np.zeros(len(t), bool)
            on[ok] = m[v[ok], u[ok]]
            sil += [-t[on].min() / io, t[on].max() / io] if on.any() else [0.0, 0.0]
        sil = np.array(sil + [hgt])
    return {"pts": Q.ravel(), "sil": sil}


def backdrop_mask(image, tol: float = 28.0):
    """The head (and whatever else is not backdrop) in a picture with a PLAIN backdrop: colour distance from the
    backdrop (the top corners' median), opened, holes filled, the largest piece."""
    from scipy import ndimage
    c = np.asarray(image, float)[..., :3]
    k = max(min(c.shape[0], c.shape[1]) // 30, 4)
    bg = np.median(np.r_[c[:k, :k].reshape(-1, 3), c[:k, -k:].reshape(-1, 3)], 0)
    m = np.linalg.norm(c - bg, axis=2) > tol
    m = ndimage.binary_fill_holes(ndimage.binary_opening(m, iterations=2))
    lab, n = ndimage.label(m)
    if n > 1:
        m = lab == (1 + int(np.argmax(ndimage.sum(m, lab, range(1, n + 1)))))
    return m


def plain_backdrop(image, tol: float = 14.0) -> bool:
    """Is the picture's backdrop plain? (its top corners and upper side strips are one colour)"""
    c = np.asarray(image, float)[..., :3]
    h, w = c.shape[:2]
    k = max(min(h, w) // 30, 4)
    S = np.r_[c[:k, :k].reshape(-1, 3), c[:k, -k:].reshape(-1, 3), c[:h // 3, :k].reshape(-1, 3), c[:h // 3, -k:].reshape(-1, 3)]
    return bool(np.percentile(np.linalg.norm(S - np.median(S, 0), axis=1), 90) < tol)


def _predict(tag: str, F: dict) -> tuple:
    M = model()
    X = []
    for k in ("pts", "sil") if tag == "outline" else ("pts",):
        X.append(((F[k] - M[f"{tag}_{k}_mu"]) / M[f"{tag}_{k}_sd"]) @ M[f"{tag}_{k}_B"])
    X = np.r_[np.hstack(X), 1.0]
    return X @ M[f"{tag}_W"], M[f"{tag}_rms"]


def measure(image, P, backdrop: bool | None = None) -> dict:
    """{"macros": {name: (z, sigma)}, "used": "points" | "points + outline", "note"}: the macros this picture
    measures (cv rms < CUT), sigma = SIGMA x the cv rms. backdrop: True = the head stands against a plain backdrop
    (the outline's low levels are used), None = decided from the picture's corners."""
    if backdrop is None:
        backdrop = plain_backdrop(image)
    F = features(P, backdrop_mask(image) if backdrop else None)
    tag = "outline" if backdrop and F["sil"] is not None and F["sil"][:4].min() > 0.2 else "points"
    z, rms = _predict(tag, F)
    names = model()["names"]
    out = {n: (round(float(z[i]), 2), round(float(max(rms[i], 0.25) * SIGMA), 2)) for i, n in enumerate(names) if rms[i] < CUT}
    return {"macros": out, "used": "points + outline (cheek and jaw levels)" if tag == "outline" else "points",
            "note": "measured macros: calibrated on RENDERS of sampled heads only (not validated on photographs)"}
