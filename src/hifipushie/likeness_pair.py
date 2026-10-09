"""The matched pair: the reference picture's face crop and the model rendered through that picture's FITTED camera at
the same crop and scale, side by side, a 50/50 overlay and a flicker GIF, with the face-recognition score
(faceid.py) and a few checklist items read by the same detector on both. One question per look: "does this head
look like the photo?"

`matched(name, base)` -> dict (photo crop, render lit by the photo's fitted light, sides, items, face-ID scores);
`sheet(m, out, gif=)` draws it. The model is drawn by likeness.render (clay, numba): seconds, no Blender.
"""
from __future__ import annotations

import numpy as np

ITEMS = ("canthal_tilt", "eye_opening", "eye_width", "brow_eye", "brow_tilt", "face_index", "width_cheekbone",
         "width_jaw", "jaw_taper", "alar_width", "nose_length", "mouth_width", "mouth_corner_tilt", "lower_third")


def _crop(img, box, size):
    from PIL import Image
    return img.transform(size, Image.EXTENT, tuple(float(v) for v in box), Image.BICUBIC)


def matched(name: str, base: dict | None = None, view: int = 0, items=ITEMS, face_id: bool = True,
            mesh: dict | None = None) -> dict:
    """The photo (view `view` of <name>/human_refs.json) and the model `base` (default: <name>'s spec base) through
    that picture's fitted camera (not refitted: the camera is the photo's, so a difference is the head's)."""
    from . import likeness, store
    if base is None:
        base = store.load(name)["base"]
    refs = likeness._refs(name)
    ph = likeness.photo_sides(refs)[view]
    md = likeness.model_sides(base, [ph], mesh=mesh, refit=False)[0]
    ren = md.get("img_lit") or md["img"]
    photo = _crop(ph["img"], ph["box"], ren.size)
    rows = {}
    for iid in items:
        try:
            it = likeness._item(iid)
        except (KeyError, StopIteration, IndexError):
            continue
        r = []
        for side, mmpx in ((ph["side"], ph["mmpx"]), (md["side"], md["mmpx"])):
            try:
                r.append(round(likeness.value(side, it["measure"], mmpx), 2))
            except Exception:  # noqa: BLE001  (unmeasurable on this side)
                r.append(None)
        rows[iid] = {"photo": r[0], "model": r[1], "tol": it.get("tol"), "unit": it.get("unit")}
    out = {"name": name, "photo": photo, "render": ren, "clay": md["img"], "ph": ph, "md": md, "items": rows,
           "box": ph["box"], "k": md["k"]}
    if face_id:
        out["face_id"] = face_id_scores(out)
    return out


def _lm5(side, box, k):
    from . import faceid
    if side.P is None:
        return None
    return faceid.lm5_from_mediapipe((np.asarray(side.P) - [box[0], box[1]]) * k)


def face_id_scores(m: dict) -> dict:
    """Cosine similarity photo crop vs render, by each embedding; the faces aligned on the SAME detector's five
    points on both (MediaPipe, which finds faces on clay; YuNet's own detection as a cross-check if it finds both)."""
    from . import faceid
    if not faceid.available():
        return {}
    box, k = m["box"], m["k"]
    a = _lm5(m["ph"]["side"], box, k)
    b = _lm5(m["md"]["side"], box, k)
    res = {}
    if a is not None and b is not None:
        res.update(faceid.similarity(m["photo"], m["render"], a, b))
    yn = faceid.similarity(m["photo"], m["render"])
    res.update({f"{kk}_yunet": v for kk, v in yn.items()})
    return res


def _label(im, text, xy=(8, 6), size=22):
    from PIL import ImageDraw, ImageFont
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        f = ImageFont.load_default()
    for dx, dy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
        d.text((xy[0] + dx, xy[1] + dy), text, fill=(0, 0, 0), font=f)
    d.text(xy, text, fill=(255, 255, 255), font=f)


def _canthi(im, side, box, k, col):
    """The canthal lines (inner -> outer corner, both eyes) drawn on a copy."""
    from PIL import ImageDraw
    if side.P is None:
        return im
    im = im.copy()
    d = ImageDraw.Draw(im)
    P = (np.asarray(side.P) - [box[0], box[1]]) * k
    for a, b in ((133, 33), (362, 263)):
        u = P[b] - P[a]
        d.line([tuple(P[a] - 0.4 * u), tuple(P[b] + 0.4 * u)], fill=col, width=2)
    return im


def sheet(m: dict, out: str, gif: str | None = None, title: str = "", crop: str = "face", px: int = 520) -> str:
    """photo | render | 50/50 (+ the same row with the canthal lines), item table underneath. crop "face": eyebrows
    to chin; "head": the whole box."""
    from PIL import Image, ImageDraw
    P, R = m["photo"], m["render"]
    if crop == "face" and m["ph"]["side"].P is not None:
        Q = (np.asarray(m["ph"]["side"].P) - [m["box"][0], m["box"][1]]) * m["k"]
        lo, hi = Q.min(0), Q.max(0)
        c, s = (lo + hi) / 2, (hi - lo).max() * 0.62
        cb = (int(c[0] - s), int(c[1] - s), int(c[0] + s), int(c[1] + s))
    else:
        cb = (0, 0, P.size[0], P.size[1])
    sub = lambda im: im.crop(cb).resize((px, px), Image.LANCZOS)  # noqa: E731
    box, k = m["box"], m["k"]
    Pc, Rc = _canthi(P, m["ph"]["side"], box, k, (255, 60, 60)), _canthi(R, m["md"]["side"], box, k, (60, 120, 255))
    tiles = [sub(P), sub(R), Image.blend(sub(P), sub(R), 0.5),
             sub(Pc), sub(Rc), Image.blend(sub(Pc), sub(Rc), 0.5)]
    for t, lab in zip(tiles, ("photo", "model", "50/50", "photo canthi", "model canthi", "overlay")):
        _label(t, lab)
    rows = [f"{iid:18s} photo {r['photo']!s:>7}  model {r['model']!s:>7}  {r['unit'] or ''}" +
            ("" if None in (r["photo"], r["model"]) or not r["tol"] else
             f"  d {r['model'] - r['photo']:+.2f} ({(r['model'] - r['photo']) / r['tol']:+.1f} tol)")
            for iid, r in m["items"].items()]
    fid = m.get("face_id") or {}
    head = f"{title}   face-ID " + "  ".join(f"{kk} {v}" for kk, v in fid.items() if v is not None)
    th = 30 + 20 * len(rows)
    S = Image.new("RGB", (3 * px, 2 * px + th + 34), (24, 24, 24))
    for i, t in enumerate(tiles):
        S.paste(t, ((i % 3) * px, 34 + (i // 3) * px))
    d = ImageDraw.Draw(S)
    _label(S, head, (8, 6), 20)
    for j, r in enumerate(rows):
        d.text((10, 34 + 2 * px + 8 + 20 * j), r, fill=(230, 230, 230))
    S.save(out)
    if gif:
        a, b = sub(P), sub(R)
        a.save(gif, save_all=True, append_images=[b], duration=600, loop=0)
    return out
