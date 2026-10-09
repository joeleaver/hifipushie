"""The combination on Garrett: the MAP + read head as the base, the earlier passes' STRUCTURE laid on it as residuals
(the shape controls onemesh2 tuned: planes, hollow, hood, pushes; then jawline L, chin, nose tip, brow push).
Models rs_garrett_s1 (pass 6's structure) / rs_garrett_s2 (v22's). Sheet R/rs_12_*, six views R/rs_13_*."""
import copy
import json
import os

from PIL import Image, ImageDraw

import garrett
from hifipushie import humanfit, humanfit_map, humanmacro as hm, likeness, likeness_read, store

R = os.environ.get("R")


def build():
    sp = store.load("rs_garrett_read3")
    idn = sp["base"]["head"]["identity"]
    for tag, v in (("rs_garrett_s1", 16), ("rs_garrett_s2", 22)):
        src = garrett.hist("om_garrett", v)["base"]["head"]
        b = copy.deepcopy(sp["base"])
        for k in ("shape", "pose"):
            if k in src:
                b["head"][k] = copy.deepcopy(src[k])
        b["head"]["identity"] = idn
        st = humanfit.state(b)
        it = humanfit.integrity(b, st, humanfit.state(sp["base"]))
        print(tag, humanfit.verdict(it)[:300])
        store.save(tag, {**copy.deepcopy(sp), "base": b}, f"refstudy: MAP + read identity with om_garrett v{v}'s structure controls on top")
        (store.HOME / tag / "human_refs.json").write_text((store.HOME / "rs_garrett_read3" / "human_refs.json").read_text())


MODELS = [("pass 6 (om_garrett v16)", lambda: garrett.hist("om_garrett", 16)["base"]),
          ("MAP + read (rs_garrett_read3)", lambda: store.load("rs_garrett_read3")["base"]),
          ("MAP + read + pass 6's structure", lambda: store.load("rs_garrett_s1")["base"]),
          ("MAP + read + v22's structure (jaw L, chin, nose tip)", lambda: store.load("rs_garrett_s2")["base"])]


def sheet(px=620):
    garrett.MODELS[:] = MODELS
    garrett.sheet(px)
    os.replace(f"{R}/rs_10_garrett_reference_vs_fits.png", f"{R}/rs_12_garrett_map_plus_structure.png")
    for tag, get in (("s1", MODELS[2][1]), ("s2", MODELS[3][1])):
        print(likeness_read.render_views("rs_garrett_read3", f"{R}/rs_13_garrett_six_views_{tag}.png", base=get()))


if __name__ == "__main__":
    build()
    sheet()
