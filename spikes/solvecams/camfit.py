"""camfit.py <truth> <model> .. [n=6] [dense=1] [only=dense] [dist=40]: CAMERAS ONLY: the head HELD as the model has it,
its cameras solved for n rounds under today's free prior (face_ruler.PHOTO_CAM_SD7; with dense the distance wide), each
round's reads re-taken; the cameras' errors against the truth's at the start and the end. What a read can do for the
cameras before identity moves (dense: pitch, distance)."""
import sys
import numpy as np
from hifipushie import face_ruler as fr, store
import common as C

args = [a for a in sys.argv[1:] if "=" not in a]
kw = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
n, dense, only = int(kw.get("n", 6)), kw.get("dense", "0") == "1", kw.get("only")
truth = args[0]
rt = C.refs(truth); Lt = C.landmarks(truth)
for name in args[1:]:
    rj = C.refs(name)
    head, views, notes = fr.reference_views(name, lids=True, lips=True, parse="auto", dense=dense)
    sd = {k: tuple(v[:6]) + (float(kw.get("dist", fr.PHOTO_CAM_DIST_DENSE if dense else v[6])),) for k, v in fr.PHOTO_CAM_SD7.items()}
    done = np.zeros((len(views), 7))
    e0 = [C.cam_err(v["cam"], tc, Lt) for v, tc in zip(views, rt["cameras"])]
    for r in range(n):
        for v in views:
            v["extra_obs"] = v["extra"](head, v)
        obs = fr.observe(head, views)
        if only:
            obs = [ob for ob in obs if ob["type"] in only.split("+")]
        o_ = fr.solve(obs, head, views=views, tau=0.02, cam_sd=sd, cam_done=done if r else None, adapt=True)
        th = np.clip(np.asarray(o_["cam"], float).reshape(len(views), 7), -np.asarray(fr.CAM_STEP), np.asarray(fr.CAM_STEP))
        done += th
        for v, t_ in zip(views, th):
            v["cam"] = fr.cam_moved(v["cam"], *t_)
    e1 = [C.cam_err(v["cam"], tc, Lt) for v, tc in zip(views, rt["cameras"])]
    print(f"== {name} (dense {dense}, only {only}): cameras only, {n} rounds; reads {len(obs)}")
    for v, a, b in zip(views, e0, e1):
        print(f"   {v['kind']:8s} yaw {a['yaw']:+5.1f} -> {b['yaw']:+5.1f}  pitch {a['pitch']:+5.1f} -> {b['pitch']:+5.1f}  dist {a['dist']:+5.0f} -> {b['dist']:+5.0f} %  scale {a['scale']:+4.1f} -> {b['scale']:+4.1f} %  centre {np.hypot(b['dx'], b['dy']):.1f} mm", flush=True)
