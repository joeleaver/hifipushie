"""lineup.py [clay|skin] [labels,...]: whole dressed humans by age and sex at true relative height, a face row, and
their measured proportions against the references (anthro.py). Built through the tool functions (server.human, look).
Sheets go to workspace/skin_renders/sk_4x_*. Every figure is clothed."""
import os, sys, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import server, humans, store, anthro
from hifipushie.spec import expand_mirror

OUT = Path("/home/joe/dev/hifipushie/workspace/skin_renders")
TMP = Path("/tmp/claude-1000/-home-joe-dev-hifipushie/1d5c679b-4c56-495b-8635-72e86a3b3567/scratchpad/humans4/lineup")
TMP.mkdir(parents=True, exist_ok=True)
PEOPLE = [("baby girl 1", 1, 0.0, 21, 2.5), ("baby boy 1", 1, 1.0, 4, 4), ("toddler girl 3", 3, 0.0, 9, 3), ("toddler boy 3", 3, 1.0, 14, 5),
          ("girl 7", 7, 0.0, 12, 2), ("boy 7", 7, 1.0, 6, 4.5), ("girl 11", 11, 0.0, 17, 5), ("boy 11", 11, 1.0, 2, 3),
          ("teen girl 16", 16, 0.0, 5, 1.5), ("teen boy 16", 16, 1.0, 23, 3.5), ("woman 30", 30, 0.0, 8, 6), ("man 30", 30, 1.0, 3, 2.5),
          ("woman 75", 75, 0.0, 9, 2), ("man 75", 75, 1.0, 17, 5)]
BG = np.array([128, 132, 141])


def figure(im, pad=6):
    """The figure cut out of a look panel: the panel's own picture area (inside the rulers), then what isn't
    background there."""
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
    mode = sys.argv[1] if len(sys.argv) > 1 else "clay"
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    rows, cells, faces = [], [], []
    for label, age, sex, seed, tone in PEOPLE:
        if only and label not in only:
            continue
        name = "hum4_" + label.replace(" ", "_")
        t = time.time()
        try:
            f1 = TMP / f"{name}_{mode}_body.png"
            f2 = TMP / f"{name}_{mode}_face.png"
            fresh = not (os.environ.get("COMPOSE") and f1.exists() and f2.exists())
            if fresh:
                print(server.human(name, age=age, sex=sex, seed=seed, tone=tone, skin=mode == "skin").splitlines()[0], flush=True)
            sp = store.load(name)
            J = expand_mirror(sp)["joints"]
            m = humans.measures(sp)
            rows.append((label, age, sex, m))
            nz = J["lm_nose_tip"]["pos"]
            hh = m["head_height"]
            kw = {"paint": mode == "skin"}
            if fresh:
                server.look(name, views=["front", "side"], size=720, resolution=360, save=str(f1), **kw)
                server.look(name, views=["front", "three_quarter"], size=420, focus=[0, nz[1] + 0.03, nz[2] + 0.04 * hh],
                            zoom=m["stature"] / (1.45 * hh), resolution=300, save=str(f2), **kw)
            cells.append((label, m["stature"], Image.open(f1)))
            faces.append((label, Image.open(f2)))
        except Exception as e:  # noqa: BLE001
            print(f"{label}: FAILED {e!r}"[:600], flush=True)
        print(f"  {label}: {time.time() - t:.0f} s", flush=True)
    tag = "sk_40_ages_lineup" if mode == "clay" else "sk_41_ages_lineup_skin"
    bust = "\n".join(f"{lb:16s} bust {m['bust_projection'] * 1000:5.1f} mm ahead of the breast bone, girth {m['bust_circ'] * 100:.1f} cm"
                     for lb, _, _, m in rows if "bust_projection" in m)
    txt = anthro.table(rows) + "\n\n" + bust + "\n\nours | reference (ratio); cm. References: WHO medians (stature), Snyder 1977 means scaled to it (the rest); " \
        "head height under 2.75 y estimated from WHO head circumference. biacromial = between the shoulder JOINTS here (inside the bone points)."
    (OUT / f"{tag}_measures.txt").write_text(txt)
    print(txt)
    if not cells:
        return
    K = 330  # px per metre
    figs = []
    for label, H, im in cells:
        w = im.width // 2
        parts = []
        for k in (0, 1):  # front, side
            fr, bg = figure(im.crop((k * w, 0, (k + 1) * w, min(im.height, w + 40))))
            parts.append(fr)
        s = K * H / parts[0].height
        parts = [q.resize((max(int(q.width * s), 1), max(int(q.height * s), 1)), Image.LANCZOS) for q in parts]
        figs.append((label, H, parts, bg))
    per_row = (len(figs) + 1) // 2 if len(figs) > 8 else len(figs)
    rowsf = [figs[i:i + per_row] for i in range(0, len(figs), per_row)]
    gap = 14
    W = max(sum(q.width + gap for f in rf for q in f[2]) + gap for rf in rowsf)
    hrow = [max(q.height for f in rf for q in f[2]) + 50 for rf in rowsf]
    sheet = Image.new("RGB", (W, sum(hrow)), figs[0][3])
    d = ImageDraw.Draw(sheet)
    y0 = 0
    for rf, hr in zip(rowsf, hrow):
        base_y = y0 + hr - 22
        for mark in np.arange(0.25, 2.0, 0.25):  # height lines
            y = base_y - int(K * mark)
            if y > y0 + 16:
                d.line([(0, y), (W, y)], fill=(112, 116, 125), width=1)
                d.text((2, y - 11), f"{mark:.2f} m", fill=(70, 72, 80))
        d.line([(0, base_y), (W, base_y)], fill=(90, 93, 100), width=1)
        x = gap
        for label, H, parts, _ in rf:
            d.text((x + 2, base_y + 4), f"{label}   {H * 100:.0f} cm", fill=(255, 255, 160))
            for q in parts:
                sheet.paste(q, (x, base_y - q.height + 6))
                x += q.width + gap
        y0 += hr
    per = (len(faces) + 1) // 2 if len(faces) > 8 else len(faces)
    fw = W // (2 * per)  # front + three-quarter per person
    frow = Image.new("RGB", (W, ((len(faces) + per - 1) // per) * (fw + 22)), (30, 32, 36))
    for i, (label, im) in enumerate(faces):
        w = im.width // 2
        x, y = (i % per) * 2 * fw, (i // per) * (fw + 22)
        for k in (0, 1):
            c = im.crop((k * w + 38, 22, (k + 1) * w - 6, w - 6)).resize((fw - 2, fw - 2), Image.LANCZOS)
            frow.paste(c, (x + k * fw, y + 20))
        ImageDraw.Draw(frow).text((x + 6, y + 4), label, fill=(255, 255, 160))
    out = Image.new("RGB", (W, sheet.height + frow.height), (30, 32, 36))
    out.paste(sheet, (0, 0))
    out.paste(frow, (0, sheet.height))
    out.save(OUT / f"{tag}.png")
    print(OUT / f"{tag}.png", out.size)


if __name__ == "__main__":
    main()
