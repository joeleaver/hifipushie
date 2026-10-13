"""gen.py <out dir> seed=<int> n=<samples> [size=320] [samples=16] [chunk=250] [hair=<share>] [open=<0|1>]: ONE
DRESSING of the denselm training set: a sampled person's skin on a class-mean head (one dressed head stage, synced
once: ~100 s) and n labelled renders of it, each with its OWN identity, expression, gaze, camera and light, re-posed
in Blender without a rebuild (blender_gen.py).

What is sampled (rng = seed):
  dressing (per stage)  sex, age 18-78, weight, GNM ethnicity class -> skin tone range, variation / detail / oil / sun,
                        freckles, moles, blemishes, flush, age spots, stubble (men), brows, lashes, make-up (women),
                        lips, iris colour and size, soft-tissue folds on a share
  identity (per sample) GNM's semantic sampler (z ~ N(0, I); the stage's sex and ethnicity, softened) + N(0, a^2) on
                        the 170 head components, a ~ U(0, 0.7)
  expression            35 % neutral; else 1-2 of the sampler's 20 classes (weights U(0.25, 1.1)) + latent noise
                        (open=0 leaves the classes that part the lips out: the stage has no teeth until gnmnative)
  gaze                  45 % at the camera, else yaw +-25, pitch +-15 deg
  camera                yaw: 55 % N(0, 35), else U(-100, 100); pitch N(0, 12) in +-30; roll N(0, 8); focal 30-200 mm
                        (log-uniform) with the distance that goes with it for a crop of 0.25-0.37 m; off-centre crops
  light                 a key sun (direction, softness, colour), fill, rim; a plain world or one of Blender's 8 CC0
                        studio HDRIs turned at random; exposure; view transform
Output: <out>/<i:06d>.png (RGBA, the background transparent: laid in at training time), labels.npz (xy, vis, depth
per landmark of denselm.landmarks()), meta.npz (identity, expression, gaze, cameras, the lights' json), dressing.json."""
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
OPEN_CLASSES = ("surprise", "happy", "smile_wide", "tongue_center", "funneler", "blow", "stretch_face", "snarl", "disgust")
ETH_TONE = {"white": (1.0, 3.2), "asian": (2.0, 4.2), "middle_eastern": (2.5, 4.8), "black": (4.6, 6.0)}
IRIS = {"dark": ["#3b2414", "#4a2e18", "#2e1c10", "#5a3a1e"], "light": ["#5d5a52", "#6b7f8c", "#5f7a5a", "#8a6a3a", "#4f6d86", "#7a8a8f"]}
HAIR_COL = ["#1c1512", "#2a1d14", "#413225", "#5a4330", "#7a5a3a", "#a0855a", "#8a8a88"]
HDRIS = ["city.exr", "courtyard.exr", "forest.exr", "interior.exr", "night.exr", "studio.exr", "sunrise.exr", "sunset.exr"]


def dressing(rng) -> dict:
    """A sampled person: body + skin (the stage's spec parts) and the classes its identities are drawn round."""
    male = bool(rng.random() < 0.5)
    age = float(np.clip(rng.triangular(18, 30, 78), 18, 78))
    eth = str(rng.choice(list(ETH_TONE)))
    lo, hi = ETH_TONE[eth]
    fitz = float(rng.uniform(lo, hi))
    dark = fitz > 3.4 or rng.random() < 0.45
    hair_col = str(rng.choice(HAIR_COL[:3] if dark else HAIR_COL))
    grey = float(np.clip((age - 42) / 30, 0, 1) * rng.random())
    sk = {"tone": {"fitzpatrick": round(fitz, 2), "blood": round(float(rng.uniform(0.25, 0.6)), 3),
                   "undertone": round(float(rng.uniform(-0.6, 0.7)), 3)},
          "age": round(age, 1), "sex": 1.0 if male else 0.0,
          "variation": round(float(rng.uniform(0.5, 1.3)), 2), "detail": round(float(rng.uniform(0.5, 1.3)), 2),
          "oil": round(float(rng.uniform(0.2, 0.85)), 2), "sun": round(float(rng.uniform(0.0, 0.8)), 2),
          "features": {}, "hair": {"brows": {"color": hair_col, "density": round(float(rng.uniform(0.5, 1.0)), 2),
                                             "thickness": round(float(rng.uniform(0.7, 1.4) * (1.1 if male else 0.9)), 2),
                                             "grey": round(grey, 2)},
                                   "lashes": {"amount": round(float(rng.uniform(0.4, 1.0)), 2)}},
          "eyes": {"iris": str(rng.choice(IRIS["dark"] if (fitz > 3.6 or rng.random() < 0.5) else IRIS["light"])),
                   "iris_size": round(float(rng.normal(0.0118, 0.0005)), 5), "pupil": round(float(rng.uniform(0.25, 0.5)), 2)},
          "lips": {"blood": round(float(rng.uniform(0.7, 1.4)), 2), "melanin": round(float(rng.uniform(0.7, 1.5)), 2)}}
    f = sk["features"]
    if fitz < 3.6 and rng.random() < 0.3:
        f["freckles"] = round(float(rng.uniform(0.2, 1.0)), 2)
    if rng.random() < 0.45:
        f["moles"] = round(float(rng.uniform(0.2, 0.9)), 2)
    if rng.random() < 0.25:
        f["blemishes"] = round(float(rng.uniform(0.15, 0.7)), 2)
    if rng.random() < 0.35:
        f["flush"] = round(float(rng.uniform(0.15, 0.7)), 2)
    if male and rng.random() < 0.5:
        sk["hair"]["stubble"] = {"amount": round(float(rng.uniform(0.25, 1.0)), 2), "color": hair_col, "grey": round(grey, 2)}
    if rng.random() < 0.3:
        sk["hair"]["scalp"] = {"amount": round(float(rng.uniform(0.4, 1.0)), 2), "color": hair_col,
                               "hairline": round(float(rng.uniform(0.3, 0.7)), 2)}
    if not male and rng.random() < 0.5:
        mk = {"look": str(rng.choice(["natural", "everyday", "evening"]))}
        if rng.random() < 0.6:
            mk["lipstick"] = True
        sk["makeup"] = mk
    if rng.random() < 0.3:      # the soft-tissue fold layer (geometry) on a share
        k = float(np.clip((age - 25) / 40, 0.1, 1))
        sk["folds"] = {n: round(float(rng.uniform(0.3, 1.0) * k), 2) for n in ("nasolabial", "marionette", "tear_trough", "mentolabial")
                       if rng.random() < 0.6}
    hr = None
    share = float(os.environ.get("DL_HAIR", "0.55"))
    if rng.random() < share:      # hair from the hair tools (curve locks): combed short / medium, loose (bob .. long, a fringe), cropped
        kind = str(rng.choice(["combed", "loose", "loose_fringe", "crop"], p=[0.35, 0.25, 0.25, 0.15]))
        if kind == "combed":
            v, l = float(rng.uniform(0.45, 1.2)), float(rng.uniform(0.45, 1.3))
            patch = {"volume": {k: round(x * v, 4) for k, x in (("front", 0.045), ("top", 0.036), ("crown", 0.02), ("sides", 0.012), ("back", 0.013))},
                     "length": {k: round(x * l, 4) for k, x in (("front", 0.17), ("top", 0.15), ("sides", 0.055), ("back", 0.06))},
                     "parting": {"side": str(rng.choice(["left", "right"]))}}
        elif kind == "crop":
            patch = {"loose": {"length": round(float(rng.uniform(0.012, 0.04)), 3), "messy": round(float(rng.uniform(0.1, 0.7)), 2),
                               "stiff": round(float(rng.uniform(0.5, 0.9)), 2)}}
        else:
            patch = {"loose": {"length": round(float(rng.uniform(0.06, 0.36)), 3), "messy": round(float(rng.uniform(0.0, 0.5)), 2),
                               "face": round(float(rng.uniform(0.3, 1.0)), 2), "ends": round(float(rng.uniform(-0.5, 0.8)), 2)}}
            if kind == "loose_fringe":
                patch["loose"]["fringe"] = {"length": round(float(rng.uniform(0.04, 0.09)), 3), "sweep": round(float(rng.uniform(-0.8, 0.8)), 2)}
        hr = {"kind": kind, "patch": patch, "color": hair_col if rng.random() < 0.8 else str(rng.choice(HAIR_COL)), "grey": round(grey, 2)}
        sk["hair"].pop("scalp", None)
    body = {"age": round(age, 1), "sex": round(float(np.clip((1.0 if male else 0.0) + rng.normal(0, 0.08), 0, 1)), 3),
            "weight": round(float(np.clip(rng.normal(0.45, 0.17), 0.1, 0.9)), 3)}
    return {"male": male, "eth": eth, "body": body, "skin": sk, "hair": hr}


def base_spec(dr: dict) -> dict:
    from hifipushie import blockin as bi, humans
    from hifipushie.spec import empty_spec
    b = dr["body"]
    sp = {**empty_spec(), **humans.spec(age=b["age"], sex=b["sex"], weight=b["weight"], source="human", outfit_kind="none",
                                        skin=False)}
    sp["skin"] = copy.deepcopy(dr["skin"])
    hd = sp["base"]["head"]
    for k in bi.STRIP + ("lip_seal", "mouth_gap"):
        hd.pop(k, None)
    hd["lip_close"] = True
    hd["gnm_base"] = bi.default_gnm_base(b["age"])
    D = bi.data()
    en = [str(x) for x in D["eth_names"]]
    bi.set_identity(sp, np.asarray(D["eth_means"][int(dr["male"]), en.index(dr["eth"])], float))
    return sp


def identity(rng, dr) -> np.ndarray:
    from hifipushie import gnm_sampler as gs
    t = float(np.clip((1.0 if dr["male"] else 0.0) + rng.normal(0, 0.15), 0, 1))
    w = rng.dirichlet(np.full(4, 0.35))
    w = 0.6 * np.eye(4)[gs.ETH.index(dr["eth"])] + 0.4 * w
    c = gs.identity()(rng.normal(size=64), gs.id_label(t, dict(zip(gs.ETH, w))))[0][:170]
    c = c + rng.uniform(0, 0.7) * rng.normal(size=170)
    return np.clip(c, -3.5, 3.5)


def expression(rng, allow_open: bool) -> tuple:
    """(383,) GNM expression coefficients and what they are ({class: weight})."""
    from hifipushie import gnm_sampler as gs
    if rng.random() < 0.35:
        return np.zeros(383), {}
    names = [n for n in gs.EXPR if allow_open or n not in OPEN_CLASSES]
    k = 1 if rng.random() < 0.6 else 2
    pick = rng.choice(len(names), k, replace=False)
    mix = {names[i]: float(rng.uniform(0.25, 1.1)) for i in pick}
    if rng.random() < 0.12:            # eyes closed: both winks (the sampler has no blink class)
        mix = {**mix, "wink_left": float(rng.uniform(0.8, 1.1)), "wink_right": float(rng.uniform(0.8, 1.1))}
    lab = gs.ex_label(mix)
    s = max(lab.sum(), 1.0)
    e = gs.expression()(rng.normal(size=64) * 0.8, lab / s)[0] * min(s, 1.2)
    return e, mix


def rot(axis, ang):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K


def camera(rng, centre) -> dict:
    yaw = float(np.clip(rng.normal(0, 35), -100, 100)) if rng.random() < 0.55 else float(rng.uniform(-100, 100))
    pitch = float(np.clip(rng.normal(0, 12), -30, 30))
    roll = float(np.clip(rng.normal(0, 8), -25, 25))
    f_mm = float(np.exp(rng.uniform(np.log(30), np.log(200))))
    side = float(rng.uniform(0.25, 0.37))                       # m: the crop's side at the head
    frac = float(rng.uniform(0.15, 1.0))                        # the crop's share of a 36 mm frame's width
    dist = float(np.clip(f_mm / 36.0 * side / frac, 0.3, 8.0))
    fov = 2 * np.arctan(side / 2 / dist)
    y, p = np.radians(yaw), np.radians(pitch)
    d = np.array([np.sin(y) * np.cos(p), -np.cos(y) * np.cos(p), np.sin(p)])       # from the head toward the camera
    right = np.cross([0, 0, 1.0], d)
    right /= np.linalg.norm(right)
    up = np.cross(d, right)
    R0 = np.stack([right, up, d], 1) @ rot([0, 0, 1], np.radians(roll))             # world <- camera (looks along -Z)
    # the crop sits off the lens axis: the crop centre's ray is r in the camera, and it must run to the head
    lim = min(0.5 * (1 / frac - 1), 1.2)
    sh = rng.uniform(-lim, lim, 2) if rng.random() < 0.6 else np.zeros(2)
    t = 2 * np.tan(fov / 2)
    r = np.array([sh[0] * t, sh[1] * t, -1.0])
    r /= np.linalg.norm(r)
    ax = np.cross([0, 0, -1.0], r)
    Q = rot(ax, np.arcsin(min(np.linalg.norm(ax), 1.0))) if np.linalg.norm(ax) > 1e-9 else np.eye(3)
    R = R0 @ Q.T
    off = rng.normal(0, 0.018, 3)                                       # the head off the crop's centre
    tgt = np.asarray(centre, float) + off + np.array([0.0, 0.035 * abs(np.sin(y)), 0.0])
    return {"eye": tgt + d * dist, "R": R, "fov": float(np.degrees(fov)), "shift": sh, "yaw": yaw, "pitch": pitch, "roll": roll,
            "f_mm": f_mm, "dist": dist, "side": side, "d": d}


def kelvin(rng):
    t = rng.uniform(-1, 1)
    return [float(1.0 + 0.16 * max(t, 0) - 0.02 * max(-t, 0)), 1.0 - 0.03 * abs(t), float(1.0 - 0.22 * max(t, 0) + 0.1 * max(-t, 0))]


def lighting(rng, cam) -> str:
    d, R = cam["d"], cam["R"]
    right, up = R[:, 0], np.array([0, 0, 1.0])
    az, el = np.radians(rng.normal(0, 55)), np.radians(rng.uniform(-10, 70))
    key = np.cos(el) * (np.cos(az) * d + np.sin(az) * right) + np.sin(el) * up
    hdri = rng.random() < 0.5
    L = [{"dir": key.tolist(), "energy": float(rng.uniform(0.3, 2.5) if hdri else rng.uniform(1.5, 5.0)),
          "angle": float(np.exp(rng.uniform(np.log(2), np.log(60)))), "color": kelvin(rng)}]
    if rng.random() < 0.6:
        fill = np.cos(el * 0.3) * (np.cos(-az) * d + np.sin(-az) * right) + np.sin(el * 0.3) * up
        L.append({"dir": fill.tolist(), "energy": float(rng.uniform(0.2, 1.2)), "angle": 40.0, "color": kelvin(rng), "shadow": False,
                  "specular": 0.0})
    if rng.random() < 0.2:
        rim = -0.8 * d + rng.choice([-1, 1]) * 0.5 * right + 0.4 * up
        L.append({"dir": (rim / np.linalg.norm(rim)).tolist(), "energy": float(rng.uniform(1.0, 5.0)), "angle": 8.0, "color": kelvin(rng)})
    if hdri:
        world = {"hdri": str(rng.choice(HDRIS)), "turn": float(rng.uniform(0, 2 * np.pi)), "strength": float(rng.uniform(0.3, 1.6))}
    else:
        g = float(rng.uniform(0.25, 0.9))
        world = {"color": [float(np.clip(g + rng.normal(0, 0.05), 0, 1)) for _ in range(3)], "strength": float(rng.uniform(0.15, 0.9))}
    return json.dumps({"lights": L, "world": world, "exposure": float(np.clip(rng.normal(-0.35, 0.45), -1.6, 0.9)),
                       "view": str(rng.choice(["Khronos PBR Neutral", "AgX", "Standard"], p=[0.5, 0.35, 0.15]))})


PROBE_LIGHT = json.dumps({"lights": [{"dir": [0.3, -0.7, 0.6], "energy": 3.2, "angle": 30.0}, {"dir": [-0.5, -0.8, 0.1], "energy": 0.6,
                          "angle": 40.0, "shadow": False, "specular": 0.0}], "world": {"color": [0.8, 0.8, 0.8], "strength": 0.45},
                          "exposure": -0.5, "view": "Khronos PBR Neutral"})


def _state(args):
    base, c, e_names, e = args
    from hifipushie import blockin as bi, humanfit
    sp = {"base": copy.deepcopy(base)}
    bi.set_identity(sp, c)
    sp["base"]["head"]["expression"] = {n: round(float(x), 5) for n, x in zip(e_names, e) if abs(x) >= 1e-4}
    st = humanfit.state(sp["base"])
    return np.asarray(st["tpl"]["P"], np.float32), np.asarray(st["L"], np.float32)


def main():
    out = Path(sys.argv[1])
    kw = dict(a.split("=", 1) for a in sys.argv[2:])
    seed, n = int(kw.get("seed", 0)), int(kw.get("n", 8))
    size, spp, chunk = int(kw.get("size", 320)), int(kw.get("samples", 16)), int(kw.get("chunk", 250))
    allow_open = kw.get("open", "0") == "1"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    if kw.get("hair") is not None:
        os.environ["DL_HAIR"] = kw["hair"]
    import stage
    from hifipushie import base as basemod, denselm, humanfit, render, resources, scene, skin, store
    t0 = time.time()
    dr = dressing(rng)
    if kw.get("dressing"):
        dr = json.loads(Path(kw["dressing"]).read_text())
    sp = base_spec(dr)
    name = kw.get("name", f"dl_s{seed:05d}")
    d = store._dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp))
    (out / "dressing.json").write_text(json.dumps(dr, indent=1))
    hair_job = None
    if dr.get("hair"):
        from hifipushie import hair
        try:
            hair.groom(name, replace=True, note="denselm", patch=dr["hair"]["patch"])
        except Exception as e_:  # noqa: BLE001  (a sampled groom the tools refuse: the default one)
            print(f"step: groom {dr['hair']['kind']} failed ({str(e_)[:200]}): the default groom", flush=True)
            hair.groom(name, replace=True, note="denselm")
        sp = store.load(name)
        sp["hair"]["look"] = {**(sp["hair"].get("look") or {}), **hair.seen_look(dr["hair"]["color"]), "grey_amount": dr["hair"].get("grey", 0.0)}
        sp["hair"]["look"].pop("grey_amount")
        (d / "spec.json").write_text(json.dumps(sp))
    with resources.heavy(f"denselm stage {name}", gb=8):
        sn = stage.ensure(name, with_hair=bool(dr.get("hair")))
    if dr.get("hair"):
        from hifipushie import hair
        st_ = json.loads((store._dir(sn) / "spec.json").read_text())
        hair_job = out / "hair_job.json"
        hair_job.write_text(json.dumps(hair.job(sn, st_)))
    t_stage = time.time() - t0
    print(f"step: stage {sn} in {t_stage:.0f} s", flush=True)
    st0 = humanfit.state(sp["base"])
    tpl = st0["tpl"]
    P0 = np.asarray(tpl["P"], float)
    from hifipushie import likeness, onemesh
    Fq = likeness.model_mesh_from_state(st0)["F"]
    g = basemod._gnm_data()
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    skin_v = (gid < 0) | (np.asarray(g["groups"]["skin_exterior"]) > 0.5)[np.maximum(gid, 0)]
    F = Fq[skin_v[Fq].all(1)]
    LMS = denselm.landmarks()
    lv = denselm.model_vertices(tpl["fid"])
    e_names = [str(x) for x in g["expression_names"]]
    eye0 = np.asarray(st0["L"], float)[68:70]
    eye_r = float(st0["head"].get("eye_r", 0.012))
    iris_r = float(skin.params(sp)["eyes"].get("iris_size", 0.0118)) / 2
    fwd0 = np.asarray(sp["base"].get("look_at", [0, -4, eye0[0, 2]]), float)
    centre0 = np.asarray(st0["L"], float)[[36, 45, 48, 54]].mean(0)
    ids = np.array([identity(rng, dr) for _ in range(n)])
    ex = [expression(rng, allow_open) for _ in range(n)]
    probe = kw.get("probe", "0") == "1"       # every expression class at full weight on the stage's own head, from the front
    if probe:
        from hifipushie import blockin as bi, gnm_sampler as gs
        n = len(gs.EXPR) + 1
        ids = np.repeat(bi.identity(sp)[None], n, 0)
        ex = [(np.zeros(383), {})] + [(gs.prototype(c), {c: 1.0}) for c in gs.EXPR]
    E = np.array([e for e, _ in ex])
    procs = int(os.environ.get("DL_PROCS", "4"))
    t1 = time.time()
    jobs = [(sp["base"], ids[i], e_names, E[i]) for i in range(n)]
    if procs > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(procs) as pool:
            res = pool.map(_state, jobs, chunksize=8)
    else:
        res = [_state(j) for j in jobs]
    t_state = time.time() - t1
    print(f"step: {n} heads posed in {t_state:.0f} s ({procs} procs)", flush=True)
    meta = {k: [] for k in ("cam_eye", "cam_R", "fov", "shift", "yaw", "pitch", "roll", "f_mm", "dist", "side", "gaze", "light", "eye")}
    Ds, LMw = [], []
    for i in range(n):
        P, L = res[i]
        P, L = P.astype(float), L.astype(float)
        eye = L[68:70]
        cam = camera(rng, L[[36, 45, 48, 54]].mean(0))
        if probe:
            tg = L[[36, 45, 48, 54]].mean(0)
            yw = np.radians(-30.0 if i % 2 else 0.0)
            dd = np.array([np.sin(yw), -np.cos(yw), 0.0])
            rr = np.cross([0, 0, 1.0], dd)
            cam = {**cam, "eye": tg + dd * 1.2, "R": np.stack([rr, [0, 0, 1.0], dd], 1), "fov": float(np.degrees(2 * np.arctan(0.13 / 1.2))),
                   "shift": np.zeros(2), "d": dd}
        G, pts = [], []
        look_cam = rng.random() < 0.45 or probe
        gy, gp = np.radians(np.clip(rng.normal(0, 12), -25, 25)), np.radians(np.clip(rng.normal(0, 7), -15, 15))
        for k in (0, 1):
            a0 = fwd0 - eye0[k]
            a0 /= np.linalg.norm(a0)
            if look_cam:
                a1 = cam["eye"] - eye[k]
                a1 /= np.linalg.norm(a1)
                ang = np.degrees(np.arccos(np.clip(a0 @ a1, -1, 1)))
                if ang > 32:            # not past what an eye turns: as far as it goes
                    a1 = a0 + (a1 - a0) * (32 / ang)
                    a1 /= np.linalg.norm(a1)
            else:
                a1 = rot([0, 0, 1], gy) @ rot([1, 0, 0], gp) @ a0
            ax = np.cross(a0, a1)
            s_ = np.linalg.norm(ax)
            Gk = rot(ax, np.arctan2(s_, a0 @ a1)) if s_ > 1e-9 else np.eye(3)
            G.append(Gk)
            pts.append(denselm.limbus_points(eye[k], a1, eye_r, iris_r))
        LMw.append(np.concatenate([P[lv]] + pts))
        Ds.append((P - P0).astype(np.float16))
        for k_, v in (("cam_eye", cam["eye"]), ("cam_R", cam["R"]), ("fov", cam["fov"]), ("shift", cam["shift"]), ("yaw", cam["yaw"]),
                      ("pitch", cam["pitch"]), ("roll", cam["roll"]), ("f_mm", cam["f_mm"]), ("dist", cam["dist"]), ("side", cam["side"]),
                      ("gaze", np.array(G)), ("light", PROBE_LIGHT if probe else lighting(rng, cam)), ("eye", eye)):
            meta[k_].append(v)
    tol = np.r_[np.full(LMS["n_skin"], 0.0012), np.full(LMS["n"] - LMS["n_skin"], 0.0035)]
    t2 = time.time()
    sec = []
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        jp = out / f"job_{a:06d}.npz"
        np.savez(jp, P0=P0.astype(np.float32), F=F.astype(np.int32), D=np.array(Ds[a:b]), eye0=eye0, eye=np.array(meta["eye"][a:b]),
                 gaze=np.array(meta["gaze"][a:b]), cam_eye=np.array(meta["cam_eye"][a:b]), cam_R=np.array(meta["cam_R"][a:b]),
                 fov=np.array(meta["fov"][a:b]), shift=np.array(meta["shift"][a:b]), LM=np.array(LMw[a:b], np.float32),
                 light=np.array(meta["light"][a:b]), size=size, samples=spp, first=a, tol=tol,
                 eevee=json.dumps(json.loads(kw.get("eevee") or os.environ.get("DL_EEVEE", "{}"))))
        cmd = [render.BLENDER, "-b", str(scene.blend_path(sn)), "--python-exit-code", "1", "--python", str(HERE / "blender_gen.py"),
               "--", str(jp), str(out / f"part_{a:06d}")] + ([str(hair_job)] if hair_job else [])
        # (no exclusive GPU claim by default: an EEVEE render, as every stage shot of the other agents; DL_GPU_CLAIM=1 for it)
        with resources.heavy(f"denselm render {name} {a}", gb=6, gpu=os.environ.get("DL_GPU_CLAIM", "0") == "1"):
            r = resources.run(cmd, capture_output=True, text=True, timeout=7200)
        for line in r.stdout.splitlines():
            if line.startswith("@@"):
                print("step:", line[2:], flush=True)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
        jp.unlink()
    t_render = time.time() - t2
    parts = [np.load(out / f"part_{a:06d}" / "labels.npz") for a in range(0, n, chunk)]
    for a in range(0, n, chunk):
        for f in sorted((out / f"part_{a:06d}").glob("*.png")):
            f.rename(out / f.name)
        (out / f"part_{a:06d}" / "labels.npz").unlink()
        (out / f"part_{a:06d}").rmdir()
    lab = {k: np.concatenate([p[k] for p in parts]) for k in ("xy", "vis", "depth", "sec")}
    np.savez_compressed(out / "labels.npz", **lab, landmark_version=LMS["version"], size=size)
    np.savez_compressed(out / "meta.npz", identity=ids.astype(np.float32), expression=E.astype(np.float32),
                        expr_mix=np.array([json.dumps(m) for _, m in ex]),
                        **{k: np.array(v) for k, v in meta.items()}, LM=np.array(LMw, np.float32))
    tm = {"stage_s": round(t_stage, 1), "pose_s": round(t_state, 1), "render_s": round(t_render, 1), "n": n,
          "per_sample_s": round((time.time() - t0) / n, 3), "blender_pose_render_labels_s": lab["sec"].mean(0).round(3).tolist(),
          "host": os.uname().nodename, "size": size, "samples": spp}
    (out / "timing.json").write_text(json.dumps(tm))
    print("step: done", json.dumps(tm), flush=True)


if __name__ == "__main__":
    main()
