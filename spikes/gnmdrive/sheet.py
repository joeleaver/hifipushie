"""sheet.py <out name> <case>[:<state file>] ... : gd2 sheets: per case rows START (A) | DRIVER's result | ORACLE
(least-cost vocabulary moves) | TARGET (B), front / 3/4 / profile + a profile tracing of the result vs the target;
captions: the driver's kept moves and the scores. -> $R/<out name>.png"""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import drv
import gnmc
from hifipushie import blockin as bi

R = Path(os.environ.get("R", "/home/joe/dev/hifipushie/workspace/human_renders"))
PX = 230


def wrap(t, n=44):
    out, line = [], ""
    for w in t.split():
        if len(line) + len(w) + 1 > n:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    return out + [line]


def main(name, specs):
    rows, labels = [], []
    for spec in specs:
        case, _, stf = spec.partition(":")
        h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
        st = json.loads(Path(stf).read_text()) if stf else json.loads((drv.CASES / case / "state.json").read_text())
        orc = json.loads((drv.HIDDEN / f"{case}_oracle.json").read_text())
        cA, cB, c = np.array(h["A"]), np.array(h["B"]), np.array(st["c"])
        cO = cA.copy()
        for k, v in orc["moves"].items():
            cO = cO + v * bi.direction(k)
        sc = None
        p = drv.G / "out" / "scores.json"
        if p.exists():
            sc = json.loads(p.read_text()).get(f"{case}:{Path(stf).stem if stf else 'state'}")
        regs = "+".join(x["region"] for x in h["changes"])
        mv = "; ".join(", ".join(f"{k} {v:+g}" for k, v in m["moves"].items()) for m in st["moves"]) or "(none)"
        for lab, cc in (("START A", cA), ("DRIVER", c), ("ORACLE", cO), ("TARGET B", cB)):
            ims = drv.view_imgs(cc, cB, "head", px=PX)
            if lab == "DRIVER":
                im, fg = drv.view_imgs(cc, cB, "head", px=PX, views=["profile"], fg=True)
                _, tf = drv.view_imgs(cB, cB, "head", px=PX, views=["profile"], fg=True)
                ims.append(drv.trace(im[0], fg[0], tf[0]))
            else:
                ims.append(Image.new("RGB", (PX, PX), (250, 250, 248)))
            rows.append(ims)
            txt = f"{case} {h['difficulty']} ({regs})\n{lab}"
            if lab == "DRIVER":
                txt += "\n" + "\n".join(wrap(mv, 24)[:7])
                if sc:
                    txt += f"\nface err {sc['face_err'][0]:.1f}->{sc['face_err'][1]:.1f} mm\nID {sc['id'][0]:.3f}->{sc['id'][1]:.3f}"
            if lab == "ORACLE":
                txt += f"\n{len(orc['moves'])} moves\nerr {orc['err0']:.1f}->{orc['err_after'][-1]:.1f} mm"
            labels.append(txt)
    S = gnmc.grid(rows, cols_labels=["front", "3/4", "profile", "profile: red = target, green = driver"],
                  rows_labels=labels, title=name, lw=190)
    R.mkdir(exist_ok=True)
    S.save(R / f"{name}.png")
    print(R / f"{name}.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
