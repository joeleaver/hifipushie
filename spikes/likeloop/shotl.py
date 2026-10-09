"""shotl.py <model> <tag> <layer>...: each paint layer's mask rendered through the photo's camera
($L/out/<tag>_<layer>_front_big.png), for eyes.py crops (which layer sits where on the lids)."""
import os
import sys

import shot
import sheet1
import stage

L = os.environ["L"]
name, tag = sys.argv[1], sys.argv[2]
vs, cams = sheet1.cameras(name)
fr = stage.fitted_frame(cams[0], sheet1.crop_of(vs[0]), "front")
for lay in sys.argv[3:]:
    im = stage.shoot(name, [fr], shot.light(), size=shot.BIG, hair_on=False, layer=lay)["front"]
    im.save(f"{L}/out/{tag}_{lay}_front_big.png")
    print("wrote", tag, lay)
