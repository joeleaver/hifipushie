"""shotf.py <model> <tag>: shot.py's front render with flat=True (the stage's own mesh, no paint): saved as
$L/out/<tag>_front_big.png for eyes.py (a clay render of the SKINNED stage, to split geometry from paint)."""
import os
import sys

import shot
import sheet1
import stage

L = os.environ["L"]
name, tag = sys.argv[1], sys.argv[2]
vs, cams = sheet1.cameras(name)
fr = stage.fitted_frame(cams[0], sheet1.crop_of(vs[0]), "front")
im = stage.shoot(name, [fr], shot.light(), size=shot.BIG, hair_on=False, flat=True)["front"]
im.save(f"{L}/out/{tag}_front_big.png")
print("wrote", tag)
