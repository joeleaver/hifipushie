"""t9.py: the photo path's stability on Tess (read only): camera found and the top rows per camera prior / rounds."""
import numpy as np
from hifipushie import face_ruler as fr

head, views, notes = fr.reference_views("gd_T12")
print("kappa", head["kappa"], head["kappa_res"])
for lab, cam_sd, rounds in (("no camera freedom, 1 round", None, 1), ("no camera freedom, 3 rounds", None, 3),
                            ("2/2/5/1.2, 3 rounds", fr.CAM_SD, 3), ("photo prior, 2 rounds", fr.PHOTO_CAM_SD, 2), ("photo prior, 3 rounds", fr.PHOTO_CAM_SD, 3),
                            ("photo prior, 4 rounds", fr.PHOTO_CAM_SD, 4)):
    res = fr.read(head, views, rounds=rounds, cam_sd=cam_sd)
    n = {v["kind"]: sum(ob["view"] == v["kind"] for ob in res["obs"]) for v in views}
    print(f"== {lab}: reads {n} rms resid {res['rms']:.2f}; camera moved (mm, mm, %, deg) per view {np.round(res['cam_done'], 1).tolist()}")
    print("   " + ", ".join(f"{r['measure']} {r['gap']:+.1f}" for r in res["gaps"][:9]))
