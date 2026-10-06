"""lineup.py <tmp dir> [labels,...]: the 14 dressed people of the humans line-up, each built TWICE through the `human`
tool (source "makehuman" = the GNM head grafted at build time; "human" = one mesh), side by side: bodies at true
relative height, faces (front + three-quarter), necks, and both measured against the references.
Sheets: workspace/human_renders/om_10_lineup_bodies.png, om_10_lineup_faces.png, om_10_lineup_necks.png,
om_10_lineup_measures.txt. Every figure is clothed. COMPOSE=1 re-lays the sheets from the panels already rendered."""
import importlib.util
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import anthro, humans, server, store
from hifipushie.spec import expand_mirror

OUT = Path("/home/joe/dev/hifipushie/workspace/human_renders")
_sp = importlib.util.spec_from_file_location("hl", Path(__file__).parents[1] / "humans" / "lineup.py")
PEOPLE = [("baby girl 1", 1, 0.0, 21), ("baby boy 1", 1, 1.0, 4), ("toddler girl 3", 3, 0.0, 9), ("toddler boy 3", 3, 1.0, 14),
          ("girl 7", 7, 0.0, 12), ("boy 7", 7, 1.0, 6), ("girl 11", 11, 0.0, 17), ("boy 11", 11, 1.0, 2),
          ("teen girl 16", 16, 0.0, 5), ("teen boy 16", 16, 1.0, 23), ("woman 30", 30, 0.0, 8), ("man 30", 30, 1.0, 3),
          ("woman 75", 75, 0.0, 9), ("man 75", 75, 1.0, 17)]
SOURCES = (("makehuman", "graft"), ("human", "one mesh"))


def figure(im, pad=6):
    a = np.asarray(im.convert("RGB"), float)
    bg = a[60, 80]
    isbg = np.abs(a - bg).sum(-1) < 10
    cols = np.flatnonzero(isbg.mean(0) > 0.3)
    rows = np.flatnonzero(isbg.mean(1) > 0.3)
    x0, x1, y0, y1 = cols[0] + 2, cols[-1] - 2, rows[0] + 2, rows[-1] - 2
    fg = ~isbg[y0:y1, x0:x1] & (np.abs(a[y0:y1, x0:x1] - bg).sum(-1) > 24)
    ys, xs = np.flatnonzero(fg.any(1)), np.flatnonzero(fg.any(0))
    return im.crop((x0 + max(xs[0] - pad, 0), y0 + max(ys[0] - pad, 0), x0 + min(xs[-1] + pad, x1 - x0), y0 + min(ys[-1] + pad, y1 - y0))), tuple(int(v) for v in bg)


def main():
    tmp = Path(sys.argv[1])
    tmp.mkdir(parents=True, exist_ok=True)
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    compose = bool(os.environ.get("COMPOSE"))
    got, rows = {}, []
    for label, age, sex, seed in PEOPLE:
        if only and label not in only:
            continue
        for src, tag in SOURCES:
            name = f"om_{'new' if src == 'human' else 'old'}_" + label.replace(" ", "_")
            f = {k: tmp / f"{name}_{k}.png" for k in ("body", "face", "neck")}
            t = time.time()
            try:
                if not compose and not all(p.exists() for p in f.values()):
                    print(server.human(name, age=age, sex=sex, seed=seed, skin=False, source=src).splitlines()[0][:200], flush=True)
                sp = store.load(name)
                J = expand_mirror(sp)["joints"]
                m = humans.measures(sp)
                rows.append((f"{label} / {tag}", age, sex, m))
                nz, ch = J["lm_nose_tip"]["pos"], J["lm_chin"]["pos"]
                hh = m["head_height"]
                if not compose:
                    if not f["body"].exists():
                        server.look(name, views=["front", "side"], size=720, resolution=360, save=str(f["body"]))
                    if not f["face"].exists():
                        server.look(name, views=["front", "three_quarter"], size=420, focus=[0, nz[1] + 0.03, nz[2] + 0.04 * hh],
                                    zoom=m["stature"] / (1.45 * hh), resolution=300, save=str(f["face"]))
                    if not f["neck"].exists():
                        server.look(name, views=["three_quarter", "side"], size=420, focus=[0, ch[1] + 0.05, ch[2] - 0.2 * hh],
                                    zoom=m["stature"] / (1.1 * hh), resolution=300, save=str(f["neck"]))
                got[(label, src)] = (m["stature"], {k: Image.open(p) for k, p in f.items()})
            except Exception as e:  # noqa: BLE001
                print(f"{label} / {tag}: FAILED {e!r}"[:700], flush=True)
            print(f"  {label} / {tag}: {time.time() - t:.0f} s", flush=True)
    txt = anthro.table(rows) + "\n\nours | reference (ratio); cm. graft = base.body.source makehuman + a GNM head grafted at build time; " \
        "one mesh = base.body.source human. References: WHO medians (stature), Snyder 1977 means scaled to it (the rest)."
    (OUT / "om_10_lineup_measures.txt").write_text(txt)
    print(txt)
    people = [p for p in PEOPLE if all((p[0], s) in got for s, _ in SOURCES)]
    if not people:
        return
    # bodies: per person graft | one mesh (front + side each), true relative height
    K = 300
    gap = 10
    per_row = (len(people) + 1) // 2 if len(people) > 4 else len(people)
    blocks = []
    for label, *_ in people:
        parts, bg = [], None
        for src, tag in SOURCES:
            H, ims = got[(label, src)]
            im = ims["body"]
            w = im.width // 2
            for k in (0, 1):
                fr, bg = figure(im.crop((k * w, 0, (k + 1) * w, min(im.height, w + 40))))
                s = K * H / fr.height if k == 0 else None
                parts.append((fr, H, tag if k == 0 else ""))
        sc = [K * got[(label, src)][0] / parts[2 * i][0].height for i, (src, _) in enumerate(SOURCES)]
        parts = [(q.resize((max(int(q.width * sc[i // 2]), 1), max(int(q.height * sc[i // 2]), 1)), Image.LANCZOS), H, t) for i, (q, H, t) in enumerate(parts)]
        blocks.append((label, parts, bg))
    rowsf = [blocks[i:i + per_row] for i in range(0, len(blocks), per_row)]
    W = max(sum(q.width + gap for b in rf for q, _, _ in b[1]) + gap * (len(rf) + 1) for rf in rowsf)
    hrow = [max(q.height for b in rf for q, _, _ in b[1]) + 60 for rf in rowsf]
    sheet = Image.new("RGB", (W, sum(hrow)), blocks[0][2])
    d = ImageDraw.Draw(sheet)
    y0 = 0
    for rf, hr in zip(rowsf, hrow):
        base_y = y0 + hr - 34
        for mark in np.arange(0.25, 2.0, 0.25):
            y = base_y - int(K * mark)
            if y > y0 + 16:
                d.line([(0, y), (W, y)], fill=(112, 116, 125), width=1)
                d.text((2, y - 11), f"{mark:.2f} m", fill=(70, 72, 80))
        d.line([(0, base_y), (W, base_y)], fill=(90, 93, 100), width=1)
        x = gap
        for label, parts, _ in rf:
            d.text((x + 2, base_y + 18), label, fill=(255, 255, 160))
            for q, H, t in parts:
                sheet.paste(q, (x, base_y - q.height + 6))
                if t:
                    d.text((x + 2, base_y + 4), f"{t} {H * 100:.0f} cm", fill=(235, 235, 235))
                x += q.width + gap
            x += gap
        y0 += hr
    sheet.save(OUT / "om_10_lineup_bodies.png")
    for key, fname, title in (("face", "om_10_lineup_faces.png", "faces"), ("neck", "om_10_lineup_necks.png", "necks: three-quarter, side")):
        cell = 300
        per = 4 if len(people) > 4 else len(people)
        nrow = (len(people) + per - 1) // per
        out = Image.new("RGB", (per * 4 * cell, nrow * (cell + 24)), (30, 32, 36))
        dd = ImageDraw.Draw(out)
        for i, (label, *_) in enumerate(people):
            x, y = (i % per) * 4 * cell, (i // per) * (cell + 24)
            for j, (src, tag) in enumerate(SOURCES):
                im = got[(label, src)][1][key]
                w = im.width // 2
                for k in (0, 1):
                    c = im.crop((k * w + 38, 22, (k + 1) * w - 6, w - 6)).resize((cell - 2, cell - 2), Image.LANCZOS)
                    out.paste(c, (x + (2 * j + k) * cell, y + 22))
                dd.text((x + 2 * j * cell + 6, y + 5), f"{label}: {tag}", fill=(255, 255, 160))
        out.save(OUT / fname)
    print("sheets in", OUT)


if __name__ == "__main__":
    main()
