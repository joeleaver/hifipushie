"""Garments read from reference art, and simulated garments checked against that reading (guide(topic=
"cloth_reference"); the list is cloth_checklist.json).

Two uses of one checklist, as with the face's likeness list:
- `read(model, garments, views, answers)`: the FORM an LLM fills from the pictures (one row per checklist item of the
  garments' kinds, big to small, with the crop that shows it), then, from the answers, the design-sheet patch per
  garment and the TARGET TABLE (each item's reading with its tolerance and confidence; "not visible" allowed).
  Numbers come from marked image points: an orthographic camera is fitted to the model's own body landmarks
  (`fit_camera`), lengths are read ANCHORED (the fraction t along two body landmarks: the jacket's hem at t of the
  way waist -> knee) and carried onto our body, widths in metres through the camera's scale.
- `check(model, garments, refs, results)`: our cached sims (never simulated here) measured item by item (`MEASURES`),
  each miss in tolerances, ranked (stage weight x miss), with focus panels: the reference crop | our garments drawn
  through the SAME camera (`render_front`), the item's points marked.

A result may be a full cloth.build result or a light one {"V", "F", "piece", "names"} (an npz a scratch run saved):
measures that need more (folds, button marks) say "not measured in this result".
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------- body landmarks


# ---------------------------------------------------------------- the camera (orthographic, front)


# ---------------------------------------------------------------- reading a reference


def _kb():
    from . import garment_design
    return garment_design.kb()


def _sample_colour(image: str, pts: list, r: int = 7) -> list:
    from PIL import Image
    a = np.asarray(Image.open(image).convert("RGB"), float)
    px = []
    for u, v in pts:
        u, v = int(round(u)), int(round(v))
        px.append(a[max(v - r, 0):v + r + 1, max(u - r, 0):u + r + 1].reshape(-1, 3))
    return [int(round(c)) for c in np.median(np.concatenate(px), 0)]


# ---------------------------------------------------------------- our side: measures on a simulated garment


def _fabric_entry(name):
    fb = _kb()["fabrics"]
    if isinstance(name, dict):  # {preset, overrides}
        name = name.get("preset")
    if name in fb:
        return fb[name]
    for k, v in fb.items():
        if isinstance(v, dict) and v.get("preset") == name:
            return v
    return None


# ---------------------------------------------------------------- checking


# ---------------------------------------------------------------- pictures


# ---------------------------------------------------------------- the reference brief (what pictures to ask for)

