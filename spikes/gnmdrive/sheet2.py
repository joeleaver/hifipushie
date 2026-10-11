"""sheet2.py <out name> <case without manual>,<same pair with manual> ...: gd2 before / after sheets: per pair the rows
START A | driver WITHOUT the manual | driver WITH the manual | TARGET B, front / 3/4 / profile + a profile tracing of
each driver's result against the target (red = target); captions: kept moves, region / ID closure, pass."""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import drv
import gnmc

R = Path(os.environ.get("R", "/home/joe/dev/hifipushie/workspace/human_renders"))
PX = 230


def wrap(t, n=26):
    out, line = [], ""
    for w in t.split():
        if len(line) + len(w) + 1 > n:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    return out + [line]


def main(name, pairs_):
    sc = json.loads((drv.G / "out" / "scores.json").read_text())
    rows, labels = [], []
    for p in pairs_:
        c0, c1 = p.split(",")
        h = json.loads((drv.HIDDEN / f"{c0}.json").read_text())
        cA, cB = np.array(h["A"]), np.array(h["B"])
        regs = "+".join(x["region"] for x in h["changes"])
        _, tf = drv.view_imgs(cB, cB, "head", px=PX, views=["profile"], fg=True)
        heads = [("START A", cA, None)]
        for lab, case in (("NO MANUAL", c0), ("WITH MANUAL", c1)):
            st = json.loads((drv.CASES / case / "state.json").read_text())
            heads.append((lab, np.array(st["c"]), (st, sc.get(f"{case}:state"))))
        heads.append(("TARGET B", cB, None))
        for lab, c, info in heads:
            ims = drv.view_imgs(c, cB, "head", px=PX)
            if info:
                im, fg = drv.view_imgs(c, cB, "head", px=PX, views=["profile"], fg=True)
                ims.append(drv.trace(im[0], fg[0], tf[0]))
            else:
                ims.append(Image.new("RGB", (PX, PX), (250, 250, 248)))
            rows.append(ims)
            txt = f"{c0[3:]} {h['difficulty']} ({regs})\n{lab}"
            if info:
                st, r = info
                mv = "; ".join(", ".join(f"{k} {v:+g}" for k, v in m["moves"].items()) for m in st["moves"]) or "(none)"
                txt += "\n" + "\n".join(wrap(mv)[:8])
                if r:
                    txt += (f"\nregion closed {r['region_closed_mean']:.2f}\nID {r['id'][0]:.3f}->{r['id'][1]:.3f}"
                            + ("\nPASS" if r["pass"] else "\nno pass"))
            labels.append(txt)
    S = gnmc.grid(rows, cols_labels=["front", "3/4", "profile", "profile trace: red = target, green = result"],
                  rows_labels=labels, title=name, lw=200)
    S.save(R / f"{name}.png")
    print(R / f"{name}.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
