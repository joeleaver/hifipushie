"""The reference pictures as a MEASUREMENT of the skin (the `skin_from_reference` tool): what the procedural skin has
a parameter for is read off the fitted references and the parameters are set from the read. The picture is never the
albedo (likeness_texture is that test: it bakes the picture's light, brushwork and hair, and seams where no camera
looked); the result is the ordinary procedural skin, clean under any light and from any angle.

The instrument is DIFFERENTIAL. Per fitted reference view:
  P  the picture, cropped to the block-in's box
  R  OUR dressed head (the stage: bare skin + eyes) through the same camera under the picture's own fitted light
  A  our albedo at each pixel's surface point (the paint layers evaluated in Python: `albedo`)
  the picture's albedo  T = A x P / R  (the ratio image: the light, the shading, the scattering and the camera's tone
  curve cancel as far as our head and light stand in for theirs; what is left is where the skins differ).
Reads are region means of T against A, and for everything but the base tone DOUBLE differences: a region against the
face's plain skin in the same picture, so exposure and white balance cancel too. The base tone itself needs an
anchor in the picture (`anchor`): the sclera (ours through the same camera: exposure and white balance), else a
plain neutral backdrop (white balance only: the tone's lightness is kept), else nothing (tone not read).

Trust: a pixel counts where the model shows skin facing its camera (`FACE`), the picture's own parser says skin
(faceparse: no hair, cloth, backdrop), and neither picture nor render is clipped.

  capture(name)            -> the views' frames (P, R, surface points, trust), cached on disk by content
  read(name)               -> the measurements (dict + text)
  fit(name, read)          -> new spec["skin"] + the side-effect report
  apply(name, out=None)    -> read + fit + save (to `out`, or onto `name`)

Where the code is (split by responsibility, as C414): this module holds the constants and the colour spaces.
skin_read_frames: the dressed stage, `capture`, `trust`, the atlas source, our albedo. skin_read_context: the anchor,
the tone, the shade's colour, the regions. skin_read_reads: lips, freckles, brows, irises, `read`. skin_read_params:
what the fit may set. skin_read_fit: `fit`, `apply`. skin_read_folds: the fold detectors, `fold_read`.
skin_read_fold_fit: `fold_text`, `fold_fit`.
"""
from __future__ import annotations

import numpy as np

VERSION = 1
N = 512                 # px across a view's crop (the block-in's box)
FACE = (0.35, 0.7)      # cos between the skin's normal and the way to the camera: no trust .. full
CLIP = (0.02, 0.97)     # picture / render values (0..1, any channel) outside this are clipped: not read
STAGE = "_sr_"          # this reader's own dressed stages (never the look_skin / judging-sheet ones)
# the dressed render's light before it is re-aimed to the picture's own (blockin.photo_lighting): a big soft source
# above and in front, a weak frontal fill, a pale room (the judging sheets' stage light)
LIGHT = {"lights": [{"dir": [0.08, -0.74, 0.67], "energy": 3.3, "color": [1.0, 0.975, 0.95], "angle": 38,
                     "window": {"size": [1.4, 1.0], "distance": 2.2, "gain": 0.2}},
                    {"dir": [0.0, -1.0, 0.05], "energy": 0.7, "color": [1.0, 0.98, 0.97], "angle": 40, "shadow": False,
                     "specular": 0.0}],
         "world": {"color": [0.8, 0.8, 0.8], "strength": 0.45}, "view": "Standard", "exposure": 0.0}
EEVEE = {"fast_gi_resolution": "1", "fast_gi_quality": 1.0, "fast_gi_step_count": 16, "fast_gi_ray_count": 4}


def _lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(lin):
    lin = np.clip(np.asarray(lin, float), 0, None)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def lab(lin):
    """CIE Lab (D65) of LINEAR rgb."""
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = np.clip(np.asarray(lin, float), 0, None) @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _unlab(L):
    """LINEAR rgb of CIE Lab (D65): lab's inverse."""
    L = np.asarray(L, float)
    fy = (L[..., 0] + 16) / 116
    f = np.stack([fy + L[..., 1] / 500, fy, fy - L[..., 2] / 200], -1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    Mi = np.linalg.inv(np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]]))
    return xyz @ Mi.T


def _lab_scale(L, k: float):
    """Lab colours of the same surfaces k x as bright (linear)."""
    L = np.asarray(L, float)
    fy = (L[..., 0] + 16) / 116
    f = np.stack([fy + L[..., 1] / 500, fy, fy - L[..., 2] / 200], -1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * k
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)
