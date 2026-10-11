"""sheet3.py <out name> <label=case>,<label=case>...: ONE pair per sheet, side by side, 3 rows (front / profile /
profile trace: red = target outline, green = this head): START A | each arm's result | TARGET B. Captions (kept moves,
region / ID closed, pass) go in the title. (<= 3 rows: tall stacked sheets are mis-seen.)"""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import drv
import gnmc

R = Path(os.environ.get("R", "/home/joe/dev/hifipushie/workspace/human_renders"))
PX = 300


def main(name, arms):
    sc = json.loads((drv.G / "out" / "scores.json").read_text())
    arms = [a.split("=") for a in arms]
    h = json.loads((drv.HIDDEN / f"{arms[0][1]}.json").read_text())
    cA, cB = np.array(h["A"]), np.array(h["B"])
    regs = "+".join(x["region"] for x in h["changes"])
    heads, cap = [("START A", cA)], []
    for lab, case in arms:
        st = json.loads((drv.CASES / case / "state.json").read_text())
        r = sc.get(f"{case}:state")
        heads.append((lab, np.array(st["c"])))
        mv = "; ".join(", ".join(f"{k} {float(v):+g}" for k, v in m["moves"].items()) for m in st["moves"]) or "(none)"
        cap.append(f"{lab} ({case}): " + (f"region closed {r['region_closed_mean']:.2f}, ID closed {r['id_closed']:.2f}, "
                                          f"{'PASS' if r['pass'] else 'no pass'}; " if r else "") + mv)
    heads.append(("TARGET B", cB))
    _, tf = drv.view_imgs(cB, cB, "head", px=PX, views=["profile"], fg=True)
    rows = [[], [], []]
    for lab, c in heads:
        ims, fg = drv.view_imgs(c, cB, "head", px=PX, views=["front", "profile"], fg=True)
        rows[0].append(ims[0])
        rows[1].append(ims[1])
        rows[2].append(drv.trace(ims[1], fg[1], tf[0]))
    import textwrap
    from PIL import ImageDraw
    G = gnmc.grid(rows, cols_labels=[l for l, _ in heads], rows_labels=["front", "profile", "profile trace\nred = target\ngreen = this"],
                  lw=110)
    lines = [f"{name}: pair {arms[0][1][3:]} {h['difficulty']} ({regs})"]
    for c in cap:
        lines += textwrap.wrap(c, 200, subsequent_indent="    ")
    S = Image.new("RGB", (G.size[0], G.size[1] + 15 * len(lines) + 8), (250, 250, 248))
    d = ImageDraw.Draw(S)
    for i, l in enumerate(lines):
        d.text((6, 4 + 15 * i), l, fill=(25, 25, 25), font=gnmc.FONT)
    S.paste(G, (0, 15 * len(lines) + 8))
    S.save(R / f"{name}.png")
    print(R / f"{name}.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].split(","))
