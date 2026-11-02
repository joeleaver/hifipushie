"""The bend look of step 10 (garment_bend's poses): per pose, LARGE close-ups of the shoulder + armpit (and the elbow
for a bent elbow), the posed garment (+ the body under it) beside the posed BARE body, from the same cameras.
Looks are for shape; the numbers are in the text (C288). Rendered as the game draws it (asset.preview, EEVEE), one
Blender run per GLB under the heavy / GPU lock.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SKIN = [0.85, 0.69, 0.55]
SIZE = 640  # px per panel


def _head(rb, short):
    from .garment_bend import _bone
    return np.asarray(rb[_bone(rb, short)]["head"], float)


def cameras(rb, turns: dict, bent: bool) -> list[dict]:
    """Perspective panels at the posed left shoulder (front, back, under the arm) and, bent, the elbow."""
    from . import rig
    from .garment_bend import POSE_ARM, POSE_FOREARM, posed
    sh, el = _head(rb, POSE_ARM), _head(rb, POSE_FOREARM)
    i = [b["name"].split(":")[-1] for b in rb].index(POSE_ARM)
    J = np.full((2, 4), i)
    W = np.zeros((2, 4))
    W[:, 0] = 1
    pts = rig.pose(rb, np.stack([sh, el]), J, W, rig.drive_twist(rb, rig.resolve_turns(rb, turns)))
    sh, el = pts
    pit = sh + np.array([-0.04, 0.0, -0.09])  # the armpit: below and inside the shoulder joint
    c = 0.5 * (sh + pit)
    cams = [{"name": "shoulder front", "eye": (c + [0.05, -0.55, 0.05]).tolist(), "target": c.tolist(), "fov": 32},
            {"name": "shoulder back", "eye": (c + [0.05, 0.55, 0.05]).tolist(), "target": c.tolist(), "fov": 32},
            {"name": "armpit below", "eye": (pit + [0.30, -0.30, -0.35]).tolist(), "target": pit.tolist(), "fov": 34}]
    if bent:
        cams += [{"name": "elbow side", "eye": (el + [0.5, 0.0, 0.0]).tolist(), "target": el.tolist(), "fov": 30},
                 {"name": "elbow front", "eye": (el + [0.0, -0.5, 0.0]).tolist(), "target": el.tolist(), "fov": 30}]
    return cams


def render(meshes_posed: list[dict], body_posed: dict, cams: list[dict], out: Path, tag: str) -> Path:
    """Two rows: the garment on the body, the bare body; one column per camera. Returns the sheet."""
    from . import asset, resources
    from . import garment_glb as glbw
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with resources.heavy(f"export_garment bend look {tag}", gb=4, gpu=True):
        for k, ms in (("dressed", [body_posed] + meshes_posed), ("bare", [body_posed])):
            G = np.vstack([m["V"] for m in ms])
            glb = glbw.write(out / f"bend_{tag}_{k}.glb", k, ms, None, frame=[G.min(0).tolist(), G.max(0).tolist()])
            im = asset.preview(glb, [], size=SIZE, cameras=cams)
            p = out / f"bend_{tag}_{k}.png"
            im.save(p)
            rows.append(Image.open(p).convert("RGB"))
    w = max(r.size[0] for r in rows)
    sheet = Image.new("RGB", (w, sum(r.size[1] for r in rows) + 30), "white")
    ImageDraw.Draw(sheet).text((8, 8), f"{tag}: top = garment on the body, bottom = the bare body (same cameras)", fill="black")
    y = 30
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.size[1]
    p = out / f"bend_{tag}.png"
    sheet.save(p)
    return p


def looks(rb, meshes: list[dict], body: dict, bend: dict, out: Path, tag: str = "") -> list[Path]:
    """One sheet per pose of garment_bend.deformation's result `bend` (its posed garment from the welded outer mesh
    is not used: every mesh is posed here with its own J / W, details included)."""
    from . import garment_game as gg
    from .garment_bend import posed, poses
    shots = []
    for pn, turns in poses(rb).items():
        ms = []
        for m in meshes:
            V = posed(rb, m["V"], m["J"], m["W"], turns)
            ms.append(dict(m, V=V, N=gg.normals(V, np.asarray(m["T"]))))
        bV = posed(rb, body["V"], body["J"], body["W"], turns)
        b = dict(body, V=bV, N=gg.normals(bV, np.asarray(body["T"])), colour=SKIN)
        shots.append(render(ms, b, cameras(rb, turns, "elbow" in pn), out, f"{tag}{pn}"))
    return shots
