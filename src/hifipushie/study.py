"""Studying one part of the reference before modelling it: the same part cut from every reference picture, large, and
an order of reading that gets its 3D form right.

Why: where one part of a form hides another in a view (an ear's folded lobe in front of its root, seen from the side),
Claude reads the outline as one broad shape. Blind modellers and fresh reviewers alike, given the same pictures and
asked plainly or part by part, read a pig ear's root as long front to back; it is the ear's edge seen on. One reader
made to work in this order (each view alone, naming what hides what; each sub-form's size on each axis read only from
a view where nothing is in front of it; then checking the 3D shape against every outline; words last) read it
right (trials review3, 2026-11-16). The order is general: it says nothing about ears.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from . import matched, refread

SIDE_PX = 560  # each crop is drawn this big on its long side

ORDER = """Read {what} as a sculptor would, BEFORE you model it. Write each step out (in your log) before the next;
describe {what} as a whole only at step 5.

1. Each picture on its own. Trace {what}'s outline in pieces (top, front edge, back edge, where it meets the
   body...). For each piece: which surface is it, and does another part sit IN FRONT of it in this picture, hiding
   what is behind? Name every place where one part overlaps another or the body.
2. Sub-forms. Split it into the parts you would block separately (where it joins, what stands, what bends or
   folds...). Name each.
3. Three axes, each from its best picture. Each sub-form's size side to side (x), front to back (y), up and down (z).
   For each, say which picture you read it from and why nothing is in front of it there. Where the only picture
   showing an axis has another part in front, write "hidden in <picture>" and say what the OTHER pictures show of it
   (an edge seen on, a shadow line, a thickness at a silhouette). Never read an axis from a picture where it is
   hidden.
4. Check. Would the shape you gave each sub-form in step 3 make, in each picture, the outline you traced in step 1?
   Where not, correct step 3.
5. Only now: {what} in words a modeller can block from: where it grows from, which way it stands and faces, how
   thick, what its top does and which way."""


def _views(name: str) -> list[tuple[str, dict, str]]:
    """(view, camera, image path) for every reference picture with a camera: the flat views and the painting."""
    from . import beside, beside_painting
    out = []
    for v in beside.flat_views(name):
        out.append((v, matched.load_camera(name, v), refread.view_record(name, v)["image"]))
    label = beside_painting.camera_label(name)
    if label:
        cam = matched.load_camera(name, label)
        out.append(("painting", cam, cam["image"]))
    return out


def _words(view: str) -> str:
    return {"front": "the front view: its left (+x) is on the picture's right",
            "back": "the back view: its left (+x) is on the picture's left",
            "side": "the side view: it faces the picture's left (forward, -y, is left)",
            "side_r": "the other side view: it faces the picture's right",
            "painting": "the concept painting, from its own angle"}.get(view, view)


def crops(name: str, at, size: float) -> list[tuple[str, Image.Image, list[int]]]:
    """(caption, picture, box in the source image's pixels) for the box `at` +- `size` metres, in every reference
    picture where it falls inside the picture."""
    c = np.asarray(at, float)
    corners = c + size * np.array([[i, j, k] for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)], float)
    out = []
    for view, cam, path in _views(name):
        im = Image.open(path).convert("RGBA")
        W, H = im.size
        xy, _ = matched.project(corners, cam, size=(W, H))
        x0, y0 = np.floor(xy.min(0)).astype(int)
        x1, y1 = np.ceil(xy.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        cut = im.crop((x0, y0, x1, y1))
        bg = Image.new("RGBA", cut.size, (226, 226, 222, 255))
        bg.alpha_composite(cut)
        s = SIDE_PX / max(cut.size)
        pic = bg.convert("RGB").resize((max(1, round(cut.size[0] * s)), max(1, round(cut.size[1] * s))), Image.LANCZOS)
        cap = f"{_words(view)}; {2 * size * 100:.0f} cm across"
        band = Image.new("RGB", (pic.width, 26), (255, 255, 255))
        ImageDraw.Draw(band).text((6, 6), cap, fill=(0, 0, 0), font=refread._font(14))
        sheet = Image.new("RGB", (pic.width, pic.height + 26), (255, 255, 255))
        sheet.paste(band, (0, 0))
        sheet.paste(pic, (0, 26))
        out.append((cap, sheet, [int(x0), int(y0), int(x1), int(y1)]))
    return out


def order(what: str) -> str:
    return ORDER.format(what=what)


STEPS = 5
MIN_STEP_CHARS = 40  # a step is a few words at least: "1. ok" is not a reading


def _record_path(name: str):
    from . import store
    return store._dir(name) / "studies.json"


def readings(name: str) -> list[dict]:
    import json
    p = _record_path(name)
    return json.loads(p.read_text()) if p.exists() else []


def save_reading(name: str, what: str, at, size: float, reading: str) -> dict:
    """Keep a written reading of a part (study_part's five steps), checked to have its five steps."""
    import json
    import re
    text = str(reading or "")
    marks = [m.start() for k in range(1, STEPS + 1) for m in [re.search(rf"(?m)^\s*{k}[.):]", text)] if m]
    if len(marks) < STEPS or marks != sorted(marks):
        raise ValueError(f"reading: write the {STEPS} steps out, each starting on its own line with its number (\"1.\" to "
                         f"\"{STEPS}.\"), in order: each picture alone and what hides what; the sub-forms; each sub-form's "
                         "size on each axis and the picture you read it from; the check; the part in words")
    parts = [text[a:b] for a, b in zip(marks, marks[1:] + [len(text)])]
    short = [i + 1 for i, s in enumerate(parts) if len(s.strip()) < MIN_STEP_CHARS]
    if short:
        raise ValueError(f"reading: step {short[0]} says almost nothing; write what you see in it")
    rec = {"what": what, "at": [float(c) for c in at], "size": float(size), "reading": text}
    old = [r for r in readings(name) if not (r["what"] == what or np.linalg.norm(np.subtract(r["at"], rec["at"])) < 1e-6)]
    _record_path(name).parent.mkdir(parents=True, exist_ok=True)
    _record_path(name).write_text(json.dumps(old + [rec], indent=1))
    return rec


def reading_near(name: str, point) -> dict | None:
    """The written reading whose box holds `point` (either side: a ".L" part read on the right counts), or None."""
    for r in readings(name):
        c, s = np.asarray(r["at"], float), 1.5 * float(r["size"])
        for q in (np.asarray(point, float), np.asarray(point, float) * [-1, 1, 1]):
            if np.all(np.abs(q - c) <= s):
                return r
    return None
