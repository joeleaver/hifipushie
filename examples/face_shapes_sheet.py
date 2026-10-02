"""Face-shapes contact sheet: every ARKit shape of an exported character at weight 1.0 (front + 3/4 close-ups of the
face, rendered from the GLB as an engine loads it), the neutral, and a few viseme-like combinations.

  uv run python examples/face_shapes_sheet.py [model] [out_dir]      (defaults: goblin_talk, workspace/face_shapes)

Imports examples/<model>.json if the model isn't in the workspace, exports it with face_shapes=True (rig + FBX) unless
<out_dir>/<model>/<model>.glb exists, checks the GLB's morph targets (faceshapes.read_glb), then writes
<out_dir>/<model>_shapes.png (and a smaller .jpg)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from hifipushie import asset, faceshapes, store

ROOT = Path(__file__).resolve().parents[1]


def main(model: str = "goblin_talk", out: str = "workspace/face_shapes"):
    out_dir = Path(out)
    glb = out_dir / model / f"{model}.glb"
    try:
        spec = store.load(model)
    except Exception:
        spec = json.loads((ROOT / "examples" / f"{model}.json").read_text())
        store.save(model, spec, "face shapes sheet")
        spec = store.load(model)
    if not glb.exists():
        info = asset.export(model, glb.parent, triangles=15000, texture=1024, rig=True, fbx=True, face_shapes=True)
        print("\n".join(info["log"]))
    got = faceshapes.read_glb(glb)
    for mesh, g in got.items():
        moving = [n for n, t in zip(g["names"], g["targets"]) if np.abs(t["POSITION"]).max() > 0]
        print(f"{mesh}: {g['count']} vertices, {len(g['names'])} targets, {len(moving)} move it")
    face = faceshapes.Face(spec)
    target = face.M + face.up * 0.35 * face.R - face.out * 0.2 * face.R
    dist = 5.0 * face.R
    q = (face.out + face.side) / np.sqrt(2)  # three quarter from the creature's left
    cams = [{"eye": (target + face.out * dist).tolist(), "target": target.tolist(), "fov": 30, "name": "front"},
            {"eye": (target + q * dist).tolist(), "target": target.tolist(), "fov": 30, "name": "3/4 left"}]
    poses = [("neutral", {})] + [(n, {n: 1.0}) for n in faceshapes.ALL] + list(faceshapes.COMBOS.items())
    sheets = asset.preview(glb, [], size=300, samples=16, cameras=cams, poses=[p for _, p in poses])
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        small = ImageFont.truetype("DejaVuSans.ttf", 14)
    except OSError:
        font = small = ImageFont.load_default()
    cols = 5
    tw, th = sheets[0].size
    pad = 30
    rows = -(-len(poses) // cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + pad)), (24, 25, 28))
    d = ImageDraw.Draw(sheet)
    for i, ((name, pose), im) in enumerate(zip(poses, sheets)):
        x, y = (i % cols) * tw, (i // cols) * (th + pad)
        sheet.paste(im, (x, y + pad))
        d.text((x + 8, y + 3), name, fill=(240, 220, 160) if pose and len(pose) > 1 or not pose else (235, 235, 235),
               font=font)
        if len(pose) > 1:
            d.text((x + 8 + d.textlength(name, font=font) + 10, y + 8),
                   " + ".join(f"{k} {v:g}" for k, v in pose.items()), fill=(170, 170, 170), font=small)
    png = out_dir / f"{model}_shapes.png"
    sheet.save(png)
    sheet.convert("RGB").resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS).save(png.with_suffix(".jpg"),
                                                                                           quality=88)
    print(png)


if __name__ == "__main__":
    main(*sys.argv[1:])
