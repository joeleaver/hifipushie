"""oval.py <mode> <model>...: the ORBIT reads validated on DRESSED pictures of known heads (faceruler's dshots: EEVEE
stage, bald, through gd_T12's three fitted cameras; $D = their directory).
  limbus   the limbus reader alone: per picture of B, the read shift from A's limbus (A = the previous model) against
           the true shift (B's own limbus through the same camera); mm, across / up, per view and eye
  ruler    the whole ruler, model A, pictures of B (hair masked, as a photo is read): the orbit measures' gaps against
           the truth (gnm_mm on the two identities, the uniform-size part taken out as dval.py does), for
             known      the true cameras, no camera freedom
             free       the true cameras, shift / scale / roll / yaw / pitch free (PHOTO_CAM_SD6)
             off        each camera turned by a random yaw (profile 6, 3/4 4, front 2 deg sd), pitch 2, shifted 1.5 mm,
                        scaled 2.5 %, then left free: a FITTED camera
           each with the views: all three | front + profile | front + 3/4
-> $G/out/oval_<mode>.json + tables."""
import json
import os
import sys

import numpy as np
from PIL import Image

from hifipushie import blockin as bi, eye_ruler as er, face_ruler as fr, gnm_mm, humanfit, likeness, store

G = os.environ["G"] + "/out"
D = os.environ.get("D", "/mnt/data/hifipushie/faceruler/out")
REFS = os.environ.get("REFS", "gd_T12")
BOX = json.load(open(f"{D}/d_box.json"))["box"]
mode, names = sys.argv[1], sys.argv[2:]
rj = bi._refs(REFS)
kinds = [fr.kind_of(v.get("yaw", 0)) for v in rj["views"]]
specs = {n: store.load(n) for n in names}
heads = {n: fr.model_head(specs[n]) for n in names}
sp = gnm_mm._space()
Vg = {n: sp["T"] + np.tensordot(bi.identity(specs[n]), sp["IB"], 1) for n in names}
rng = np.random.default_rng(11)


def pic(b, k):
    return Image.open(f"{D}/d_{b}_{k}.png").convert("RGB")


if mode == "limbus":
    rows = []
    IRIS = {}
    for i, a in enumerate(names):
        for b in (names[(i + 1) % len(names)], a):
            for k, cam in zip(kinds, rj["cameras"]):
                if k == "front":
                    continue
                img = pic(b, k)
                lum = fr._lum(img)
                from scipy import ndimage as ndi
                valid = ndi.binary_erosion(fr.foreground(img), iterations=3)
                if b not in IRIS:
                    fimg = pic(b, "front")
                    Pd = np.asarray(likeness.detect([fimg])[0], float)[:, :2] + BOX[:2]
                    fcam = rj["cameras"][kinds.index("front")]
                    IRIS[b] = float(np.mean([e["iris"] for e in er.read(fimg, Pd, likeness._mm_per_px(fcam, humanfit.state(specs[b]["base"])["L"][27:48]), scale=1.0, origin=BOX[:2])]))
                    print(b, "iris read on the front picture", round(IRIS[b], 2), "mm; model's", round(2000 * fr.limbus_model(heads[b])[0]["r"], 2))
                la, lb = fr.limbus_model(heads[a], IRIS[b]), fr.limbus_model(heads[b], IRIS[b])
                part = likeness.render(heads[a]["mesh"], cam, tuple(BOX), px=int(BOX[2] - BOX[0]), brows=False, passes=True)[2]["part"]
                eye_c = np.asarray(cam["centre"], float) - humanfit._cam_rot(cam).T @ np.asarray(cam["t"], float)
                dist = [np.linalg.norm(q["X"] - eye_c) for q in la]
                for j in (0, 1):
                    rd = fr.limbus_read(lum, cam, la[j], BOX[:2], 1.0, far=dist[j] > min(dist) + 1e-6, valid=valid, part=part)
                    if rd is None:
                        continue
                    tru = (fr._cam_points(cam, lb[j]["X"][None])[1][0] - fr._cam_points(cam, la[j]["X"][None])[1][0])
                    rows.append({"a": a, "b": b, "view": k, "eye": "rl"[j], "far": bool(dist[j] > min(dist) + 1e-6), "read": (rd["d"] * rd["mmpx"]).tolist(),
                                 "truth": (tru * rd["mmpx"]).tolist(), "score": rd["score"], "sharp": rd["sharp"], "open": rd["open"],
                                 "fwd_err": float((rd["d"] - tru) @ rd["fwd"] * rd["mmpx"])})
                    r = rows[-1]
                    print(f"{a} <- {b} {k} {r['eye']} {'far ' if r['far'] else 'near'} open {r['open']:.2f}: read {r['read'][0]:+.2f} {r['read'][1]:+.2f} truth "
                          f"{r['truth'][0]:+.2f} {r['truth'][1]:+.2f} | err {r['read'][0] - r['truth'][0]:+.2f} {r['read'][1] - r['truth'][1]:+.2f} score {r['score']:.3f} sharp {r['sharp']:.3f}", flush=True)
    json.dump(rows, open(f"{G}/oval_limbus.json", "w"))
    for k in ("3q", "profile"):
        for far in (False, True):
            for same in (True, False):
                e = np.array([np.subtract(r["read"], r["truth"]) for r in rows if r["view"] == k and r["far"] == far and (r["a"] == r["b"]) == same
                              and r["score"] >= fr.LIMBUS_MIN and r["sharp"] > 0])
                n0 = sum(r["view"] == k and r["far"] == far and (r["a"] == r["b"]) == same for r in rows)
                if len(e):
                    fe = np.array([r["fwd_err"] for r in rows if r["view"] == k and r["far"] == far and (r["a"] == r["b"]) == same
                                   and r["score"] >= fr.LIMBUS_MIN and r["sharp"] > 0])
                    print(f"{k:8s} {'far ' if far else 'near'} eye, {'own picture' if same else 'other head '}: {len(e)}/{n0} kept; across bias {e[:, 0].mean():+.2f} sd {e[:, 0].std():.2f} "
                          f"(|max| {np.abs(e[:, 0]).max():.2f}); up bias {e[:, 1].mean():+.2f} sd {e[:, 1].std():.2f}; along the picture's FORWARD {fe.mean():+.2f} sd {fe.std():.2f}")
    sys.exit()

VAR = tuple(os.environ.get("VAR", "known,free,off").split(","))
SUB = {"all": ("front", "3q", "profile"), "f+p": ("front", "profile"), "f+3q": ("front", "3q")}
SKIP = set(os.environ.get("SKIP", "").split(","))
TAG = os.environ.get("TAG", "")
PAIRS = [int(x) for x in os.environ["PAIRS"].split(",")] if os.environ.get("PAIRS") else None
OFF_SD = {"front": (1.5, 1.5, 2.5, 0.8, 2.0, 2.0), "3q": (1.5, 1.5, 2.5, 0.8, 4.0, 2.0), "profile": (1.5, 1.5, 2.5, 0.8, 6.0, 2.0)}
rows = []
for i, a in enumerate(names):
    b = names[(i + 1) % len(names)]
    offs_i = {k: rng.normal(size=6) * OFF_SD[k] for k in kinds}       # (drawn for every pair: the same in every process)
    if PAIRS is not None and i not in PAIRS:
        continue
    truth = {r["measure"]: r["gap"] for r in gnm_mm.gaps(Vg[a], Vg[b])}
    row = {"a": a, "b": b, "truth": truth}
    offs = offs_i
    row["offs"] = {k: v.tolist() for k, v in offs.items()}
    for var in VAR:
        for sub, use in SUB.items():
            if f"{var}/{sub}" in SKIP:
                continue
            views = []
            for k, cam in zip(kinds, rj["cameras"]):
                if k not in use:
                    continue
                cam2 = fr.cam_moved(cam, *offs[k]) if var == "off" else cam
                img = pic(b, k)
                v = {"img": img, "cam": cam2, "kind": k, "style": "dressed", "origin": BOX[:2], "scale": 1.0, "hair": True}
                v["mask"], v["trust"] = fr.photo_masks(img, cam2, heads[a], origin=BOX[:2])
                if k == "front":
                    try:
                        P = np.asarray(likeness.detect([img])[0], float)[:, :2] + BOX[:2]
                        mm = likeness._mm_per_px(cam2, humanfit.state(specs[a]["base"])["L"][27:48])
                        eyes = er.read(img, P, mm, scale=1.0, origin=BOX[:2])
                        v["extra"] = lambda h, vw, eyes=eyes: fr._iris_obs(h, vw, eyes)
                        iris_b = float(np.mean([e["iris"] for e in eyes]))
                    except Exception as e:  # noqa: BLE001
                        print("  no iris read:", b, e)
                views.append(v)
            for v in views:
                v["iris_mm"] = iris_b
            res = fr.read(heads[a], views, rounds=4 if var != "known" else 3, cam_sd=None if var == "known" else fr.PHOTO_CAM_SD6)
            key = f"{var}/{sub}"
            row[key] = {r["measure"]: [r["gap"], r["err"]] for r in res["gaps"]}
            row[key + "_orbit"] = {r["row"]: [r["gap"], r["err"]] for r in res["orbit"]}
            row[key + "_cam"] = [res.get("cam_done"), res.get("cam_post")]
            row[key + "_n"] = {t: sum(ob["type"] == t for ob in res["obs"]) for t in ("outline", "iris", "limbus")}
            print(a, "<-", b, key, row[key + "_n"], " ".join(f"{m} {row[key][m][0]:+.1f}+-{row[key][m][1]:.1f} ({truth[m]:+.1f})" for m in gnm_mm.ORBIT), flush=True)
    rows.append(row)
    json.dump(rows, open(f"{G}/oval_ruler{TAG}.json", "w"))
