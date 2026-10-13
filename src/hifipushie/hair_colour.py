"""The hair colour model in numpy (tesshair7): what blender_strands.material does to the look colour per strand, for
everything that is not that material: the groom export's per-point colour (blender_strands.export_groom imports this
file inside Blender: no package imports here) and the game cards' vertex colours (hair_cards.mesh).

A strand's colour = the look colour x TONE, a value multiplier from
  variation   a lock drifts +-14 % x variation; ~1.5 mm of a lock's width +-32 % x variation
  depth       under-layers darker: x (1 - 0.75 depth x shade), shade = the lock's depth in a mass with volume
  sun         x (1 + 0.5 sun x smoothstep(age / 0.28 m)): the hair's age from the scalp
  highlights  a share of ribbons x (1 + highlight_contrast), from 1-7 cm off the root
(hue / saturation shifts are the material's own and small; an engine multiplies a base colour by this tone)."""

import numpy as np

SUN_M = 0.28  # m of hair by which sun-lightening is full
TAIL_AGE = 0.15  # m of gathered hair before a tie, when a lock does not say (cards)


def _ss(x):
    x = np.clip(np.asarray(x, float), 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _k(look: dict, key: str, default: float) -> float:
    v = look.get(key, default)
    return float(np.clip(default if v is None else v, 0.0, 1.5))


def peak(look: dict) -> float:
    """The largest tone the model can give (cards store tone / peak in an 8-bit vertex colour; the atlas is lifted by
    it: hair_cards)."""
    hl = (1 + _k(look, "highlight_contrast", 0.6)) if _k(look, "highlights", 0.0) > 0 else 1.0
    return float((1 + 0.5 * _k(look, "sun", 0.2)) * hl * (1 + 0.14 * _k(look, "variation", 0.4)))


def lock_tone(look: dict, r_lock: float, shade: float = 0.0) -> float:
    """A lock's own tone: its drift (r_lock 0..1, a number per lock) and its depth in the mass."""
    return float((1 + 0.14 * _k(look, "variation", 0.4) * (2 * r_lock - 1)) * (1 - 0.75 * _k(look, "depth", 0.5) * float(np.clip(shade, 0, 1))))


def along_tone(look: dict, age, r_ribbon=None, sun_x: float = 0.0):
    """The tone along a strand / a card by its age (m from the scalp, array): sun-lightening, and, if r_ribbon (0..1,
    a number per ribbon / card) picks it, a highlight. sun_x -0.5..0.5: where the sun reaches (tips the pick)."""
    age = np.asarray(age, float)
    out = 1 + 0.5 * _k(look, "sun", 0.2) * _ss(age / SUN_M)
    hl = _k(look, "highlights", 0.0)
    if hl > 0 and r_ribbon is not None:
        pick = _ss((np.asarray(r_ribbon, float) + 0.5 * float(sun_x) - (1.0 - 0.5 * hl)) / 0.05)
        out = out * (1 + pick * _k(look, "highlight_contrast", 0.6) * _ss((age - 0.01) / 0.06))
    return out


def strand_tone(look: dict, age, r_lock, shade, r_ribbon, r_micro=None, sun_x=0.0, fly=None):
    """Per point tone of strands: age (n_points,), the rest per point too (a strand's own numbers repeated)."""
    t = along_tone(look, age, None)
    hl = _k(look, "highlights", 0.0)
    if hl > 0:
        pick = _ss((np.asarray(r_ribbon, float) + 0.5 * np.asarray(sun_x, float) - (1.0 - 0.5 * hl)) / 0.05) * (np.asarray(r_ribbon, float) > 0)
        t = t * (1 + pick * _k(look, "highlight_contrast", 0.6) * _ss((np.asarray(age, float) - 0.01) / 0.06))
    var, dep = _k(look, "variation", 0.4), _k(look, "depth", 0.5)
    t = t * (1 + 0.14 * var * np.asarray(r_lock, float)) * (1 - 0.75 * dep * np.clip(np.asarray(shade, float), 0, 1))
    if r_micro is not None:
        t = t * (1 + 0.32 * var * np.asarray(r_micro, float))
    if fly is not None:
        t = t * (1 + 0.6 * _k(look, "fly_light", 0.3) * np.asarray(fly, float))
    return t
