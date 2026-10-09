"""nose.py <label=base.json|model>...: the nose's checklist rows like with like (front photo + the desk painting with
lk_garrett5's traced contours): photo / model values per label."""
import json
import sys

from hifipushie import likeness, store

import os
IDS = tuple(os.environ["IDS"].split(",")) if os.environ.get("IDS") else ("alar_width", "nostril_base_width", "tip_height", "nose_length", "prof_nose_base", "prof_tip_radius",
       "prof_columella", "prof_tip_height", "prof_nose_tip", "prof_nose_gap", "prof_bridge_bow", "nasolabial_angle")
photos = likeness.photo_sides(likeness._refs("ll_garrett"))
for arg in sys.argv[1:]:
    lab, src = arg.split("=", 1)
    base = json.load(open(src)) if src.endswith(".json") else store.load(src)["base"]
    c = likeness.compare("ll_garrett", base, photos=photos, points_from="lk_garrett5")
    for r in c["rows"]:
        if r.get("id") in IDS:
            print(lab, f"{r['id']:18s} {r.get('view', ''):14s} photo {r.get('photo')!s:>8} model {r.get('model')!s:>8} tol {r.get('tol')}")
