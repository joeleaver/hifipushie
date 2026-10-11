"""yawq.py <model>: what turns the PROFILE camera? face_ruler on front + profile with (a) everything, (b) the limbus
left out, (c) the limbus in and the yaw NOT free (sd 0.3 deg), (d) yaw free at sd 12: the camera's yaw taken, the eye
depth read, the limbus residual. If (b) turns the camera like (a), the outline / landmarks see the yaw themselves; if
only (a) does, the turn is just the cheapest way to explain the limbus and eye depth vs yaw is NOT separated."""
import sys

import numpy as np

from hifipushie import face_ruler as fr

name = sys.argv[1]
head, views, notes = fr.reference_views(name)
views = [v for v in views if v["kind"] in ("front", "profile")]


def run(lab, limbus=True, yaw_sd=6.0, drop=()):
    vs = [dict(v, limbus=limbus) for v in views]
    sd = {k: tuple(v) for k, v in fr.PHOTO_CAM_SD6.items()}
    sd["profile"] = sd["profile"][:4] + (yaw_sd, sd["profile"][5])
    res = fr.read(head, vs, rounds=4, cam_sd=sd)
    g = {r["measure"]: r for r in res["gaps"]}
    pi = [i for i, v in enumerate(res["views"]) if v["kind"] == "profile"][0]
    lim = [round(ob["o"], 2) for ob in res["obs"] if ob["type"] == "limbus" and ob["name"].endswith(".x")]
    n = {t: sum(ob["type"] == t and ob["view"] == "profile" for ob in res["obs"]) for t in ("outline", "landmark", "limbus")}
    print(f"{lab:44s} profile yaw {res['cam_done'][pi][4]:+5.1f} +-{res['cam_post'][pi][4]:.1f} deg | eyes_forward {g['eyes_forward']['gap']:+5.1f} "
          f"(posterior x1.5: {np.sqrt(max(g['eyes_forward']['err'] ** 2 - fr.ERR['eyes_forward'] ** 2, 0)):.1f}) | limbus left {lim} | profile reads {n} | rms {res['rms']:.2f}", flush=True)
    return res


run("(a) limbus in, yaw free (sd 6)")
run("(b) NO limbus, yaw free (sd 6)", limbus=False)
run("(c) limbus in, yaw held (sd 0.3)", yaw_sd=0.3)
run("(d) limbus in, yaw free (sd 12)", yaw_sd=12.0)
run("(e) NO limbus, yaw free (sd 12)", limbus=False, yaw_sd=12.0)
