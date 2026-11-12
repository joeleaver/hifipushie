"""Pictures: before | after | where it moved, and the report's text. Part of humanfit (humanfit.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import humanfit
from .humanfit import _faces
from .humanfit_integrity import effects_text, verdict

def head_sheet(st0: dict, st1: dict | None = None, px: int = 420, focus=None, title: str = ""):
    """A PIL image, no Blender (a second or two): the head and neck in clay, front + three-quarter, before | after |
    where the vertices moved (blue 0 .. red 5 mm+), and with `focus` (a world point) a close-up row of it. The crop is
    the head and neck only (the body is the base's bare mesh: whole figures come dressed through `look`)."""
    from . import meshview
    from PIL import Image as PILImage
    from PIL import ImageDraw
    sts = [st0] + ([st1] if st1 is not None else [])
    cells = []
    for row, (cz, size, views) in enumerate([(None, None, ((0, 0), (50, 5)))] + ([(focus, 0.09, ((0, 0), (55, 5)))] if focus is not None else [])):
        for k, st in enumerate(sts):
            P = np.asarray(st["tpl"]["P"], float)
            F = _faces(st["tpl"])
            L = st["L"]
            hh = float(P[:, 2].max() - L[8, 2])
            c = np.array(cz, float) if cz is not None else np.array([0.0, float(L[30, 1]) + 0.08, float(L[8, 2]) + 0.42 * hh])
            sz = size or 1.3 * hh
            keep = [f for f in F if P[f, 2].min() > c[2] - 0.75 * sz]
            for az, el in views:
                cells.append(meshview.view(P, keep, c, sz, az=az, el=el, px=px, line=0,
                                           title=(title + " " if title and not cells else "") + ("before" if k == 0 and st1 is not None else "after" if k else "")))
        if st1 is not None:
            P0, P1 = np.asarray(st0["tpl"]["P"], float), np.asarray(st1["tpl"]["P"], float)
            F = _faces(st1["tpl"])
            if P0.shape == P1.shape:
                d = np.linalg.norm(P1 - P0, axis=1) * 1000
                L = st1["L"]
                hh = float(P1[:, 2].max() - L[8, 2])
                c = np.array(cz, float) if cz is not None else np.array([0.0, float(L[30, 1]) + 0.08, float(L[8, 2]) + 0.42 * hh])
                sz = size or 1.3 * hh
                keep = [f for f in F if P1[f, 2].min() > c[2] - 0.75 * sz]
                t = np.clip(np.array([d[f].mean() for f in keep]) / 5.0, 0, 1)[:, None]
                col = (1 - t) * np.array([150, 170, 215]) + t * np.array([235, 60, 40])
                for az, el in views:
                    cells.append(meshview.view(P1, keep, c, sz, az=az, el=el, px=px, line=0, colors=col,
                                               title=f"moved (blue 0 .. red 5 mm+; max {d.max():.1f} mm)" if az == views[0][0] else ""))
    cols = 2 * (len(sts) + (1 if st1 is not None else 0))
    rows = (len(cells) + cols - 1) // cols
    out = PILImage.new("RGB", (cols * px, rows * px), (236, 236, 238))
    for i, im in enumerate(cells):
        out.paste(im, ((i % cols) * px, (i // cols) * px))
    ImageDraw.Draw(out)
    return out


def report_text(rep: dict) -> str:
    """A solve / nudge / image-fit report as the tool prints it: integrity first, then what was asked and what came
    of it, then everything else that moved."""
    lines = [verdict(rep["integrity"])] + ([rep["refused"]] if rep.get("refused") else [])
    if "asked" in rep:
        for k, r in rep["asked"].items():
            lines.append(f"{k}: asked {r['asked']:g}, was {r['was']:g}, now {r['got']:g}" + ("" if r["met"] else "  NOT MET"))
        if rep.get("held_back", 1.0) < 1.0:
            lines.append(f"held back to {100 * rep['held_back']:.0f}% of the step: further, measures that were not asked for move "
                         f"more than {humanfit.COLLATERAL:g}x their tolerance. Ask for those too, release them (release=[...]), or force.")
        if rep.get("limited"):
            lines.append(f"limited by the plausible range (identity components stop at {humanfit.CLIP} sigma): the rest is a style, not an "
                         "identity (style sliders, or force=True).")
    if "landmark" in rep:
        lines.append(f"{rep['landmark']}: asked {rep['asked_mm']} mm, moved {rep['got_mm']} mm; {rep['by_sliders_mm']} mm by the identity "
                     f"sliders, {rep['by_correction_mm']} mm by a correction layer" +
                     (" (the sliders can't do this: a slider / target the model lacks)" if rep["by_correction_mm"] > 1.0 else ""))
    if "views" in rep:
        for i, v in enumerate(rep["views"]):
            lines.append(f"view {i}: {v['points']} points, reprojection {v['rms_px']} px rms = {v['rms_mm']} mm on the face; worst "
                         + ", ".join(f"{n} {mm} mm" for n, mm in v["worst"]) + f"; focal {v['focal']} px")
    p = rep["plausibility"]
    lines.append(f"plausibility: identity {p['rms_sigma']:.2f} sigma rms, largest {p['max_sigma']:.2f}")
    lines.append(effects_text(rep["side_effects"]))
    return "\n".join(lines)
