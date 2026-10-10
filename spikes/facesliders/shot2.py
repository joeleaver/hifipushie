"""shot2.py <dressed model> <tag>: garrett4's shot.py through BOTH reference cameras (the concept front and the desk
painting) in one render job: $D3/out/<tag>_front_big.png, <tag>_desk_big.png (1024 px, the photos' crops)."""
import json
import os
import sys

import sheet1
import stage

from hifipushie import store
from shot import light

BIG = 1024


def main(name, tag):
    r = json.loads((store.HOME / name / "human_refs.json").read_text())
    vs, cams = r["views"], r["cameras"]
    frames = [stage.fitted_frame(cams[i], sheet1.crop_of(vs[i]), nm) for i, nm in ((0, "front"), (1, "desk"), (2, "prof")) if i < len(vs)]
    ims = stage.shoot(name, frames, light(), size=BIG, hair_on=os.environ.get("HAIR", "1") == "1",
                      engine=os.environ.get("ENGINE", "eevee"))
    for nm, im in ims.items():
        im.save(f"{os.environ['D3']}/out/{tag}_{nm}_big.png")
        print("wrote", f"{os.environ['D3']}/out/{tag}_{nm}_big.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
