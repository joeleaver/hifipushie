"""body_tape's look (garment step 3): the tape lines on the body, front / side / back, numbered, with a key."""
from __future__ import annotations

import numpy as np



# ---------------------------------------------------------------------- the look: the tape lines on the body
VIEWS = (("front", lambda P: P[:, 0], lambda P: P[:, 1]),  # (name, image x, depth: smaller is nearer the viewer)
         ("side", lambda P: P[:, 1], lambda P: -P[:, 0]),  # (from the body's left, its front to the left)
         ("back", lambda P: -P[:, 0], lambda P: -P[:, 1]))
COLOURS = [(220, 40, 40), (30, 110, 220), (20, 150, 60), (230, 120, 0), (150, 50, 190), (0, 160, 170), (210, 30, 140),
           (130, 130, 0), (110, 70, 30), (70, 70, 210), (240, 80, 120), (0, 110, 90), (170, 90, 230), (90, 160, 0),
           (0, 70, 140), (190, 150, 40)]


def _unit(v):
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def _dense(P: np.ndarray, step: float = 0.005) -> np.ndarray:
    """The polyline resampled every `step` m (its visibility is judged point by point)."""
    out = [P[:1]]
    for a, b in zip(P[:-1], P[1:]):
        k = max(int(np.linalg.norm(b - a) / step), 1)
        out.append(a + np.outer(np.arange(1, k + 1) / k, b - a))
    return np.concatenate(out)


def draw(tape, rows: list, path, h: int = 760) -> str:
    """Front / side / back: the body in clay, each row's tape line in its colour (solid where seen, thin where behind
    the body), numbered at the line in a large digit; a large legend maps each number to its row's NAME. No values
    on the image (C288: pictures are for shape, text is for numbers): every value is in run's text answer."""
    from PIL import Image, ImageDraw
    from .pattern_sheet import _font
    f_num, f_leg = _font(20), _font(20)
    V, T = tape.V, tape.T
    zmin, zmax = tape.zmin, tape.zmax
    s = (h - 40) / (zmax - zmin)
    w = int(0.62 * h)
    tiles = []
    drawn = [r for r in rows if r["name"] in tape.lines]
    for vname, fx, fd in VIEWS:
        im = Image.new("RGB", (w, h), (250, 250, 248))
        dr = ImageDraw.Draw(im)
        X = fx(V)
        cx = 0.5 * (X.min() + X.max())
        ix = lambda P: w / 2 + (fx(P) - cx) * s  # noqa: E731
        iy = lambda P: h - 20 - (P[:, 2] - zmin) * s  # noqa: E731
        px, py, D = ix(V), iy(V), fd(V)
        tri = np.stack([px[T], py[T]], axis=-1)
        nrm = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
        view = {"front": np.array([0, -1.0, 0]), "side": np.array([1.0, 0, 0]), "back": np.array([0, 1.0, 0])}[vname]
        light = _unit(view + np.array([0.3, 0, 0.5]))
        shade = np.clip(np.abs(nrm @ light), 0, 1)
        dimg = Image.new("I", (w, h), 10 ** 7)  # the nearest surface's depth (mm + 5 m), painted far to near
        dd = ImageDraw.Draw(dimg)
        Dm = D[T].mean(axis=1)
        for k in np.argsort(-Dm):
            g = int(120 + 110 * shade[k])
            pts = [tuple(p) for p in tri[k]]
            dr.polygon(pts, fill=(g, g - 4, g - 10))
            dd.polygon(pts, fill=int((Dm[k] + 5.0) * 1000))
        zb = np.asarray(dimg, dtype=np.int64)
        marks = []
        for n, r in enumerate(drawn):
            P = _dense(tape.lines[r["name"]])
            col = COLOURS[n % len(COLOURS)]
            qx, qy, qd = ix(P), iy(P), fd(P)
            i_, j_ = np.clip(qy.astype(int), 0, h - 1), np.clip(qx.astype(int), 0, w - 1)
            seen = (qd + 5.0) * 1000 <= zb[i_, j_] + 15  # (within 15 mm of the nearest surface there: seen)
            for k in range(len(P) - 1):
                both = seen[k] and seen[k + 1]
                dr.line([(qx[k], qy[k]), (qx[k + 1], qy[k + 1])], fill=col if both else tuple(int(c * 0.4 + 150) for c in col),
                        width=4 if both else 1)
            vis = np.where(seen)[0]
            if len(vis):
                k = vis[np.argmax(qx[vis])] if r["kind"] in ("girth", "freesewing") and len(P) > 8 else vis[len(vis) // 2]
                base = (qx[k] + 20, qy[k])
                cands = [(base[0] + dx, base[1] + dy) for dy, dx in ((0, 0), (0, 34), (-32, 0), (32, 0), (-32, 34),
                                                                     (32, 34), (0, 68), (-64, 0), (64, 0))]
                c0 = next((c for c in cands if all(abs(c[0] - a) > 33 or abs(c[1] - b) > 31 for a, b in marks)), base)
                marks.append(c0)
                dr.ellipse([c0[0] - 16, c0[1] - 15, c0[0] + 16, c0[1] + 15], fill=(255, 255, 255), outline=col, width=3)
                dr.text(c0, str(n + 1), fill=col, font=f_num, anchor="mm")
        dr.text((8, 6), vname, fill=(40, 40, 40), font=_font(24))
        tiles.append(im)
    per = max(1, (h - 50) // 30)  # (rows per key column; more tapes: more columns, every one named: t s3-1 lost 25-26)
    cw = 420
    lw = cw * max(1, -(-len(drawn) // per))
    leg = Image.new("RGB", (lw, h), (255, 255, 255))
    dl = ImageDraw.Draw(leg)
    dl.text((10, 8), "tapes (values: the text)", fill=(0, 0, 0), font=_font(22))
    for n, r in enumerate(drawn):
        col = COLOURS[n % len(COLOURS)]
        x0, y = cw * (n // per), 44 + 30 * (n % per)
        dl.rectangle([x0 + 10, y + 2, x0 + 34, y + 22], fill=col)
        t = f"{n + 1}  {r['name']}"
        while dl.textlength(t, font=f_leg) > cw - 50 and len(t) > 6:
            t = t[:-4] + "..."
        dl.text((x0 + 44, y), t, fill=(0, 0, 0), font=f_leg)
    out = Image.new("RGB", (3 * w + lw + 12, h), (255, 255, 255))
    for i, t in enumerate(tiles):
        out.paste(t, (i * (w + 4), 0))
    out.paste(leg, (3 * w + 12, 0))
    out.save(path)
    return str(path)


