"""a1copy.py <gg best> [rounds]: gg_a1copy = garrett_a1's spec (read only, IDENTITY UNTOUCHED) under the GOOD references:
the views and the block-in boxes of <gg best>, its cameras as the start, then the cameras ONLY laid on garrett_a1's
head (face_ruler's cameras-first rounds: the head held, tau 0.02, twice the camera freedom a round; outlines from the
parser as block_in_solve reads them, differential anchors, lids and lips read but unable to move the head). Prints each
camera's move and the outline / anchor residuals before and after, for both heads."""
import copy, json, sys
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, store

best, rounds = sys.argv[1], 4
SRC, OUT = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("garrett_a1", "gg_a1copy")   # any head through the same pictures
sp = copy.deepcopy(store.load(SRC))
for k in ("hair", "cloth"):
    sp.pop(k, None)
rj = copy.deepcopy(bi._refs(best))
rj["blockin"] = {"root": OUT, "boxes": rj["blockin"]["boxes"]}
rj.pop("expressions", None)
c0 = bi.identity(sp).copy()
bi._save(OUT, sp, f"{SRC}'s spec under the good references (cameras of {best}); identity untouched", rj)


def resid(name):
    head, views, _ = fr.reference_views(name, True, lids=True, lips=True, anchors="differential", parse="auto")
    for v in views:
        if v.get("extra"):
            v["extra_obs"] = v["extra"](head, v)
    obs = fr.observe(head, views)
    out = {}
    for o in obs:
        out.setdefault((o["type"], o["view"]), []).append(o["o"])
    return head, views, {k: (len(v), float(np.sqrt(np.mean(np.square(v)))), float(np.mean(v))) for k, v in out.items()}


def show(tag, r):
    print(tag + ": " + "; ".join(f"{t} {v} n {n} rms {a:.2f} mm (mean {b:+.2f})" for (t, v), (n, a, b) in sorted(r.items())))


_, _, r = resid(best); show(f"{best} (its own cameras)", r)
head, views, r = resid(OUT); show(f"{OUT} BEFORE the camera refit ({best}'s cameras)", r)
sd = fr.PHOTO_CAM_SD6
loose = {kk: tuple(fr.CAM_LOOSE * x for x in sd[kk]) for kk in sd}
tot = np.zeros((len(views), 6))
for _ in range(rounds):
    for v in views:
        if v.get("extra"):
            v["extra_obs"] = v["extra"](head, v)
    obs = fr.observe(head, views)
    o_ = fr.solve(obs, head, views=views, tau=0.02, cam_sd=loose)
    th = np.asarray(o_["cam"], float).reshape(len(views), 6)
    lim = 2.5 * np.array([loose[v["kind"]] for v in views], float)
    th = np.clip(th, -lim, lim)
    for v, t_ in zip(views, th):
        v["cam"] = fr.cam_moved(v["cam"], *t_)
    tot += th
    print("round: cameras moved (shift mm, shift mm, scale %, roll, yaw, pitch deg):", np.round(th, 2).tolist(), "|dc| of the held head", round(float(np.linalg.norm(o_["dc"])), 3))
print("cameras' whole move from", best, ":", np.round(tot, 2).tolist())
for i, v in enumerate(views):
    rj["cameras"][i] = {**rj["cameras"][i], **{k: (np.asarray(x).tolist() if hasattr(x, "tolist") else x) for k, x in v["cam"].items()}}
bi._save(OUT, sp, f"cameras refit on {SRC}'s head (head held)", rj)
assert np.allclose(bi.identity(store.load(OUT)), c0), "identity moved"
_, _, r = resid(OUT); show(f"{OUT} AFTER the camera refit", r)
print("identity untouched: |c|", round(float(np.linalg.norm(c0)), 2))
