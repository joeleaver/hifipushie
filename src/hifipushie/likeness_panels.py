"""Focus panels: photo | model at the same crop and camera, the focus sheet, report. Part of likeness (likeness.py has the overview)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import likeness
from .likeness_compare import compare
from .likeness_measure import Side, Unmeasurable, _item, _width_ends, _width_lines
from .likeness_notes import _fmt, table_text

def _draw_feature(d, Q, idx, col, r=3):
    for i in idx:
        x, y = Q[i]
        d.ellipse((x - r, y - r, x + r, y + r), outline=col, width=2)


def _region_pts(side: Side, idx):
    out = {}
    for i in idx:
        try:
            out[i] = side.pt(i)
        except Unmeasurable:
            pass
    return out


def panel(cmp: dict, row: dict, px: int = likeness.PANEL_PX):
    """One focus panel for a row: [photo | model], both cropped round the feature in the reference picture's pixels;
    the photo's points red, the model's blue on both halves (the gap between them is the miss)."""
    from PIL import Image, ImageDraw
    vi = row["vi"] if row["vi"] != "-" else 0
    ph, md = cmp["photos"][vi], cmp["models"][vi]
    m = _item(row["id"])["measure"]
    widths = _width_lines(m)
    idx = [i for i in row["points"] if i not in likeness.OVAL] if widths else row["points"]
    pp, mp_ = _region_pts(ph["side"], idx), _region_pts(md["side"], idx)
    segs = []
    for lv in widths:
        for sd, col in ((ph["side"], likeness.PHOTO_COL), (md["side"], likeness.MODEL_COL)):
            try:
                segs.append((_width_ends(sd, lv), col))
            except Unmeasurable:
                pass
    b0 = ph["box"]
    k = md["k"]
    circles, polys = [], []   # (centre px, r px, colour), (points, colour) in picture pixels
    if row.get("kind") == "shape":
        pp, mp_ = {}, {}
        for reg, ref, rr, rf in row.get("regions") or []:
            circles += [(reg / k + b0[:2], rr / k, (255, 220, 60)), (ref / k + b0[:2], rf / k, (120, 230, 120))]
    if row.get("kind") == "contour":
        for pts_, col in zip(row.get("marks") or [], (likeness.PHOTO_COL, likeness.MODEL_COL)):
            for g in pts_:
                circles.append((np.asarray(g), 2.0 / max(md["mmpx"], 1e-6), col))
    if row.get("kind") in ("jaw", "contour"):
        pp, mp_ = {}, {}
        for Q, Qm, gp, gm in row.get("traces") or []:
            polys.append((Q, likeness.PHOTO_COL))
            if Qm is not None:
                polys.append((Qm, likeness.MODEL_COL))
            for g, col in ((gp, likeness.PHOTO_COL), (gm, likeness.MODEL_COL)):
                if g is not None:
                    circles.append((np.asarray(g), 4.0 / max(md["mmpx"], 1e-6), col))
        from . import likeness_shape as ls
        tr = ls.load_points(cmp.get("points_from") or cmp.get("name", "")).get(ph["view"]["image"], {}) if row.get("kind") == "jaw" else {}
        for nm_, uv in tr.get("points", {}).items():
            circles.append((np.asarray(uv, float), 2.5 / max(md["mmpx"], 1e-6), (255, 140, 255)))
        for nm_, ln in tr.get("lines", {}).items():
            if not nm_.startswith("jaw"):
                polys.append((np.asarray(ln, float), (255, 140, 255)))
    allp = list(pp.values()) + list(mp_.values()) + [p for s, _ in segs for p in s]
    allp += [c_ + d_ for c_, r_, _ in circles for d_ in ([r_, r_], [-r_, -r_])] + [q for Q, _ in polys for q in np.asarray(Q)]
    allp = np.array(allp) if allp else np.array([[(ph["box"][0] + ph["box"][2]) / 2, (ph["box"][1] + ph["box"][3]) / 2]])
    lo, hi = allp.min(0), allp.max(0)
    side = max((hi - lo).max() * 1.4, 30.0 / max(md["mmpx"], 1e-6))   # at least 30 mm across
    side = min(side, b0[2] - b0[0], b0[3] - b0[1])
    c = (lo + hi) / 2
    c = np.clip(c, [b0[0] + side / 2, b0[1] + side / 2], [b0[2] - side / 2, b0[3] - side / 2])   # inside the render
    box = (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2)
    s = px / side

    def crop(img, origin, scale):
        return img.crop(tuple(int(round(v)) for v in ((box[0] - origin[0]) * scale, (box[1] - origin[1]) * scale,
                                                       (box[2] - origin[0]) * scale, (box[3] - origin[1]) * scale))).resize((px, px), Image.LANCZOS)
    a = crop(ph["img"], (0, 0), 1.0)
    lit = row.get("kind") in ("shape", "jaw", "judge", "contour") and md.get("img_lit") is not None
    b = crop(md["img_lit"] if lit else md["img"], (b0[0], b0[1]), k)
    for im in (a, b):
        d = ImageDraw.Draw(im)
        for cc, rr, col in circles:
            q = (cc - box[:2]) * s
            d.ellipse((q[0] - rr * s, q[1] - rr * s, q[0] + rr * s, q[1] + rr * s), outline=col, width=2)
        for Q, col in polys:
            d.line([tuple((q - box[:2]) * s) for q in np.asarray(Q, float)], fill=col, width=2)
        for (p, q), col in segs:
            d.line([tuple((p - box[:2]) * s), tuple((q - box[:2]) * s)], fill=col, width=2)
        _draw_feature(d, {i: (p - box[:2]) * s for i, p in pp.items()}, pp, likeness.PHOTO_COL)
        _draw_feature(d, {i: (p - box[:2]) * s for i, p in mp_.items()}, mp_, likeness.MODEL_COL, r=2)
    out = Image.new("RGB", (2 * px + 6, px + 34), (24, 24, 28))
    out.paste(a, (0, 34))
    out.paste(b, (px + 6, 34))
    d = ImageDraw.Draw(out)
    miss = f"{row['miss']:+.{3 if row['unit'] == '' else 1}f}{row['unit']} (tol {row['tol']:g})" if row["score"] >= 0 else "judge"
    tag = (" INFERRED" if row.get("inferred") else "") + (" | model lit like the photo" if lit else "")
    d.text((4, 2), f"{row['name'][:46]} [{row['view']}{tag}]", fill=(240, 240, 240))
    extra = f"  3D {row['model3d']:.1f} mm" if isinstance(row.get("model3d"), float) else ""
    if row.get("kind") == "shape":
        txt = f"shading contrast photo {_fmt(row['photo'], 'x')}% vs model 0  (yellow region - green ref){extra}"
    else:
        txt = f"photo {_fmt(row['photo'], row['unit'])} | model {_fmt(row['model'], row['unit'])}  miss {miss}{extra}"
    d.text((4, 17), txt, fill=(255, 210, 120))
    return out


def focus_sheet(cmp: dict, out: str, top: int = 8, judge: bool = True, cols: int = 2, rows: list | None = None) -> str:
    """The top misses' panels (and, with judge, the judge-by-eye items) on one sheet; or the given rows."""
    from PIL import Image, ImageDraw
    if rows is not None:
        rows = [r for r in rows if r["vi"] != "-"][:top]
        judge = False
    else:
        rows = [r for r in cmp["rows"] if r["score"] > 1.0][:top]
    if judge:
        seen = set()
        for r in cmp["rows"]:
            if r["score"] < 0 and r["vi"] != "-" and r["id"] not in seen and r["points"]:
                seen.add(r["id"])
                rows.append(r)
    tiles = [panel(cmp, r) for r in rows]
    if not tiles:
        tiles = [Image.new("RGB", (2 * likeness.PANEL_PX + 6, likeness.PANEL_PX + 34), (24, 24, 28))]
    w, h = tiles[0].size
    n = len(tiles)
    sheet = Image.new("RGB", (cols * w + (cols - 1) * 8, ((n + cols - 1) // cols) * (h + 8) + 22), (14, 14, 16))
    ImageDraw.Draw(sheet).text((6, 4), "photo (left) | model (right), same camera and crop; red = photo's points, "
                                        "blue = model's", fill=(230, 230, 230))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * (w + 8), 22 + (i // cols) * (h + 8)))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def report(name: str, base: dict | None = None, top: int = 8, save: str | None = None) -> tuple:
    """(table text, focus sheet path): every checklist item measured on the references and on the model."""
    from . import store
    cmp = compare(name, base)
    out = save or str(store.HOME / "human_renders" / f"lk_{name}_focus.png")
    focus_sheet(cmp, out, top=top)
    # stage 0, the character read: its diff (reference vs the model's blind reads) and what the read implies lead the
    # report, above the millimetres
    from . import likeness_read as lr
    lead = []
    try:   # the six-view sheet: what a person judges too (reference cameras + the views no reference shows)
        views = str(Path(out).with_name(Path(out).stem.replace("_focus", "") + "_views.png"))
        lr.render_views(name, views, base=base)
        lead.append(f"six-view sheet (judge this first, and last): {views}")
    except Exception as e:  # noqa: BLE001
        lead.append(f"(six-view sheet not rendered: {e})")
    reads = lr.load(name)["reads"]
    if reads.get("reference"):
        for tag in reads:
            if tag != "reference":
                lead.append(lr.diff(name, tag))
        pr = lr.apply_prior(cmp, reads["reference"])
        if pr:
            lead.append("the read as a prior:\n" + "\n".join(pr))
    else:
        lead.append("no character read stored (character_read): the report is millimetres only")
    return "\n\n".join(lead + [table_text(cmp)]), out, cmp
