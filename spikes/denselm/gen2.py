"""gen2.py <out dir> seed=<int> n=<samples> [size=320] [samples=6] [voxel=0.002] [hair=<share>] [probe=1]: ONE
DRESSING of the STAGE-1 training set (docs/notes/fitter_whitepaper.md "## denselm stage 1"). As gen.py (one dressed
head stage per person's skin, every sample a re-pose of it in one Blender process), with what the pilot lacked:

  the head       GNM-NATIVE (base.head.attach "native": GNM's own head, eyeballs, teeth, tongue, mouth bag at GNM's own
                 size). The stage is built with the JAW HALF OPEN, so lips, teeth and tongue are separate surfaces, and
                 every sample re-poses it to its own expression, closed mouths included.
  identity       WIDE AND FLAT where the pilot answered with the average: c = class mean (sex x GNM's 4 ethnicity
                 classes) + s z, z ~ N(0, I) over the 170 head components, s ~ U(0.75, 1.0) (GNM's own prior is s = 1;
                 15 % of samples s ~ U(0.2, 0.5): near the class means); then the deviation's part in the WIDTH /
                 HEIGHT measures' subspace (jaw, gonial, chin, cheekbone, skull width; lower-face height, chin length,
                 nose length, skull top) is scaled x 1.5; 12 % of samples get one of those measures set to +-2..3 of
                 its population sd (the extremes); components clipped at +-4.5. Teeth: the 80 teeth components ~
                 N(0, 0.8^2).
  expression     ARKit-named shapes solved on GNM's basis (arkit_expr.npz) + the sampler's classes: lower face 40 %
                 neutral, 15 % smile WITH TEETH, 7 % closed smile, 13 % jaw open, 10 % speech-like, 8 % other closed
                 (frown, press, pucker ..), 7 % a sampler class; upper face 50 % neutral, 10 % eyes closed, 8 % wide,
                 10 % squint, 10 % brows down, 10 % brows up, 2 % wink.
  views          yaw 55 % U(-110, 110), 45 % N(0, 30); pitch N(0, 14) in +-35; roll N(0, 8); the camera's DISTANCE
                 log-uniform 0.3 .. 3 m (a phone selfie to a tele) with the lens that frames a 0.25-0.37 m crop there;
                 off-axis crops on half. Distance, yaw, pitch are in the labels (meta.npz).
  light          as gen.py + 15 % a HARD TOP light (a small high sun, a dark room: the dark-skin failure case).
  appearance     as gen.py, with hair on 60 % (loose hair more often and allowed over the face and jaw), heavier
                 stubble / beard shadow on 60 % of men. No glasses (not cheap: stage geometry of its own).
Landmarks: denselm.landmarks_v2() (623: the pilot's 570 skin vertices first, then GNM's iris rims, teeth, tongue).
Cheaper: the stage meshed at `voxel` (2 mm; eyes / mouth at half; teeth 0.8 mm), 6 TAA samples, one Blender start."""
import copy
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import gen as g1  # noqa: E402

WIDTH = ("jaw_width", "gonial_width", "chin_width", "cheekbone_width", "skull_width", "lower_face_height", "chin_length",
         "nose_length", "skull_top")
STAGE_JAW = 0.55            # the stage's own pose: jawOpen at this weight (lips parted, teeth and tongue their own surfaces)
_C: dict = {}


def arkit() -> dict:
    if "ak" not in _C:
        z = np.load(HERE / "arkit_expr.npz")
        _C["ak"] = {str(n): e.astype(float) for n, e in zip(z["names"], z["E"])}
    return _C["ak"]


def dressing(rng) -> dict:
    os.environ["DL_HAIR"] = "0"
    dr = g1.dressing(rng)
    male, sk = dr["male"], dr["skin"]
    sk["hair"].pop("scalp", None)
    hair_col = sk["hair"]["brows"]["color"]
    grey = float(sk["hair"]["brows"].get("grey", 0.0))
    if male and rng.random() < 0.6:        # stubble to a beard's shadow
        sk["hair"]["stubble"] = {"amount": round(float(rng.uniform(0.4, 1.4)), 2), "color": hair_col, "grey": round(grey, 2),
                                 "size": round(float(rng.uniform(1.0, 2.2)), 2), "shadow": round(float(rng.uniform(0.6, 1.5)), 2)}
    else:
        sk["hair"].pop("stubble", None)
    sk.pop("folds", None)                    # (a native head carries nothing of ours on its surface; the stage is re-posed)
    share = float(os.environ.get("DL_HAIR2", "0.6"))
    hr = None
    if rng.random() < share:
        kind = str(rng.choice(["combed", "loose", "loose_fringe", "crop"], p=[0.27, 0.36, 0.22, 0.15]))
        if kind == "combed":
            v, l = float(rng.uniform(0.45, 1.2)), float(rng.uniform(0.45, 1.3))
            patch = {"volume": {k: round(x * v, 4) for k, x in (("front", 0.045), ("top", 0.036), ("crown", 0.02), ("sides", 0.012), ("back", 0.013))},
                     "length": {k: round(x * l, 4) for k, x in (("front", 0.17), ("top", 0.15), ("sides", 0.055), ("back", 0.06))},
                     "parting": {"side": str(rng.choice(["left", "right"]))}}
        elif kind == "crop":
            patch = {"loose": {"length": round(float(rng.uniform(0.012, 0.04)), 3), "messy": round(float(rng.uniform(0.1, 0.7)), 2),
                               "stiff": round(float(rng.uniform(0.5, 0.9)), 2)}}
        else:      # loose: a bob .. long; `face` low = it hangs over the cheeks and the jaw
            patch = {"loose": {"length": round(float(rng.uniform(0.08, 0.4)), 3), "messy": round(float(rng.uniform(0.0, 0.5)), 2),
                               "face": round(float(rng.uniform(0.0, 1.0)), 2), "ends": round(float(rng.uniform(-0.5, 0.8)), 2)}}
            if kind == "loose_fringe":
                patch["loose"]["fringe"] = {"length": round(float(rng.uniform(0.04, 0.09)), 3), "sweep": round(float(rng.uniform(-0.8, 0.8)), 2)}
        hr = {"kind": kind, "patch": patch, "color": hair_col if rng.random() < 0.8 else str(rng.choice(g1.HAIR_COL)), "grey": round(grey, 2)}
    elif rng.random() < 0.4:
        sk["hair"]["scalp"] = {"amount": round(float(rng.uniform(0.4, 1.0)), 2), "color": hair_col, "hairline": round(float(rng.uniform(0.3, 0.7)), 2)}
    dr["hair"] = hr
    dr["eyes_id"] = [round(float(x), 3) for x in np.clip(rng.normal(0, 1, 2), -2, 2)]      # GNM's limbus size, cornea prominence
    return dr


def base_spec(dr: dict, voxel: float) -> dict:
    from hifipushie import blockin as bi, humans
    from hifipushie.spec import empty_spec
    b = dr["body"]
    sp = {**empty_spec(), **humans.spec(age=b["age"], sex=b["sex"], weight=b["weight"], source="human", outfit_kind="none", skin=False)}
    sp["skin"] = copy.deepcopy(dr["skin"])
    sp["skin"]["wrinkles"] = {"amount": 0.0}
    hd = sp["base"]["head"]
    for k in bi.STRIP + ("lip_seal", "mouth_gap", "eye_radius", "interior", "scale"):
        hd.pop(k, None)
    hd.update({"attach": "native", "gnm_base": 1.0, "dimorphism": 0.0, "eyes": 1.0, "lip_close": True})
    D = bi.data()
    en = [str(x) for x in D["eth_names"]]
    bi.set_identity(sp, np.asarray(D["eth_means"][int(dr["male"]), en.index(dr["eth"])], float))
    hd["identity"].update({"eyes_000": dr["eyes_id"][0], "eyes_001": dr["eyes_id"][1]})
    hd["expression"] = {k: round(STAGE_JAW * float(v), 5) for k, v in zip(_enames(), arkit()["jawOpen"]) if abs(v) > 1e-6}
    sp["parts"] = {**(sp.get("parts") or {}), "teeth": {"voxel": max(0.0008, voxel * 0.4), "color": [0.93, 0.9, 0.8], "roughness": 0.25}, "tongue": {"voxel": max(0.0015, voxel * 0.75)}}
    return sp


def _enames() -> list:
    if "en" not in _C:
        from hifipushie import base as basemod
        _C["en"] = [str(x) for x in basemod._gnm_data()["expression_names"]]
        _C["in"] = [str(x) for x in basemod._gnm_data()["identity_names"]]
    return _C["en"]


def stage(name: str, sp: dict, voxel: float, with_hair: bool, log=print) -> tuple:
    """The dressed head stage of a base spec at a COARSE mesh (voxel; eyes / mouth boxes at half). -> (stage model, its spec)."""
    from hifipushie import scene, skin_look, store
    st = skin_look.stage_spec(sp, "head")
    for k, p in st["parts"].items():
        if k in ("teeth", "tongue"):
            continue
        if "voxel" in p:
            p["voxel"] = max(float(p["voxel"]), voxel)
        for r in p.get("refine") or []:
            r["voxel"] = max(float(r["voxel"]), voxel / 2)
    for k in ("teeth", "tongue"):
        if k in (sp.get("parts") or {}):
            st["parts"][k] = dict(sp["parts"][k])
    if with_hair and sp.get("hair"):
        st["hair"] = copy.deepcopy(sp["hair"])
        st["parts"]["hair"] = copy.deepcopy((sp.get("parts") or {}).get("hair") or {})
    sn = "_dl2_" + name
    d = store._dir(sn)
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(st))
    t = time.time()
    r = scene.sync(sn, resolution=256)
    log(f"step: stage {sn} synced in {time.time() - t:.0f} s ({r['seconds']})")
    return sn, st


def identity(rng, dr) -> tuple:
    """(170,) head components, (80,) teeth components, what was done."""
    from hifipushie import blockin as bi, gnm_sampler as gs, solve_report as sr
    if "W" not in _C:
        rw = sr.rows()
        Rw = np.array([rw["R"][rw["names"].index(n)] for n in WIDTH])
        _C["W"] = (Rw, Rw.T @ np.linalg.solve(Rw @ Rw.T, Rw), np.array([rw["sd"][rw["names"].index(n)] for n in WIDTH]))
    Rw, Pw, sdw = _C["W"]
    D = bi.data()
    en = [str(x) for x in D["eth_names"]]
    male = dr["male"] if rng.random() < 0.95 else not dr["male"]
    eth = dr["eth"] if rng.random() < 0.6 else str(rng.choice(en))
    m = np.asarray(D["eth_means"][int(male), en.index(eth)], float)
    near = rng.random() < 0.15
    s = float(rng.uniform(0.2, 0.5) if near else rng.uniform(0.75, 1.0))
    d = s * rng.normal(size=170)
    d = d + 0.5 * (Pw @ d)
    what = "near" if near else "wide"
    if rng.random() < 0.12:
        k = int(rng.integers(len(WIDTH)))
        tgt = float(rng.choice([-1, 1]) * rng.uniform(2.0, 3.0) * sdw[k])
        d = d + Rw[k] * (tgt - Rw[k] @ d) / (Rw[k] @ Rw[k])
        what = f"extreme {WIDTH[k]} {tgt:+.1f}"
    return np.clip(m + d, -4.5, 4.5), np.clip(rng.normal(0, 0.8, 80), -2.5, 2.5), what


def expression(rng) -> tuple:
    """(383,) GNM expression coefficients, {what: weight}."""
    from hifipushie import gnm_sampler as gs
    A = arkit()
    e, mix = np.zeros(383), {}

    def add(name, w):
        nonlocal e
        if name in A and abs(w) > 1e-6:
            e = e + w * A[name]
            mix[name] = round(float(w), 3)

    def both(stem, w, asym=0.15):
        add(stem + "Left", w * (1 + rng.uniform(-asym, asym)))
        add(stem + "Right", w * (1 + rng.uniform(-asym, asym)))
    u = rng.random()
    if u < 0.40:
        pass
    elif u < 0.55:                              # smile with teeth
        both("mouthSmile", rng.uniform(0.5, 1.0))
        both("mouthUpperUp", rng.uniform(0.2, 0.8))
        both("mouthLowerDown", rng.uniform(0.0, 0.5))
        add("jawOpen", rng.uniform(0.0, 0.25))
    elif u < 0.62:                              # closed smile
        both("mouthSmile", rng.uniform(0.3, 0.8))
    elif u < 0.75:                              # jaw open
        add("jawOpen", rng.uniform(0.25, 1.0))
        if rng.random() < 0.4:
            add("mouthFunnel", rng.uniform(0.1, 0.5))
        if rng.random() < 0.4:
            both("mouthLowerDown", rng.uniform(0.1, 0.6))
        if rng.random() < 0.3:
            both("mouthUpperUp", rng.uniform(0.1, 0.6))
    elif u < 0.85:                              # speech-like
        add("jawOpen", rng.uniform(0.05, 0.35))
        for n in rng.choice(["mouthFunnel", "mouthPucker", "mouthStretch", "mouthUpperUp", "mouthLowerDown", "mouthLeft", "mouthRight",
                             "jawLeft", "jawRight", "jawForward"], int(rng.integers(1, 3)), replace=False):
            w = rng.uniform(0.2, 0.7)
            (both(str(n), w) if str(n) + "Left" in A else add(str(n), w))
    elif u < 0.93:                              # other closed mouths
        for n in rng.choice(["mouthFrown", "mouthPress", "mouthPucker", "mouthRollLower", "mouthRollUpper", "mouthShrugLower",
                             "mouthShrugUpper", "mouthDimple", "mouthLeft", "mouthRight"], int(rng.integers(1, 3)), replace=False):
            w = rng.uniform(0.3, 0.9)
            (both(str(n), w) if str(n) + "Left" in A else add(str(n), w))
    else:                                       # one of the sampler's whole-face classes
        c = str(rng.choice(gs.EXPR))
        w = float(rng.uniform(0.3, 1.0))
        e = e + gs.expression()(rng.normal(size=64) * 0.8, gs.ex_label(c))[0] * w
        mix["class:" + c] = round(w, 3)
    u = rng.random()
    if u < 0.50:
        pass
    elif u < 0.60:
        both("eyeBlink", rng.uniform(0.85, 1.05), 0.05)
    elif u < 0.62:
        add("eyeBlink" + str(rng.choice(["Left", "Right"])), rng.uniform(0.8, 1.0))
    elif u < 0.70:
        both("eyeWide", rng.uniform(0.4, 1.0))
        if rng.random() < 0.5:
            add("browInnerUp", rng.uniform(0.2, 0.8))
    elif u < 0.80:
        both("eyeSquint", rng.uniform(0.4, 1.0))
    elif u < 0.90:
        both("browDown", rng.uniform(0.4, 1.0))
        if rng.random() < 0.4:
            both("eyeSquint", rng.uniform(0.2, 0.6))
    else:
        add("browInnerUp", rng.uniform(0.3, 1.0))
        if rng.random() < 0.6:
            both("browOuterUp", rng.uniform(0.2, 0.9))
    return e, mix


def camera(rng, centre) -> dict:
    yaw = float(rng.uniform(-110, 110)) if rng.random() < 0.55 else float(np.clip(rng.normal(0, 30), -110, 110))
    pitch = float(np.clip(rng.normal(0, 14), -35, 35))
    roll = float(np.clip(rng.normal(0, 8), -25, 25))
    dist = float(np.exp(rng.uniform(np.log(0.3), np.log(3.0))))
    side = float(rng.uniform(0.25, 0.37))
    fov = 2 * np.arctan(side / 2 / dist)
    y, p = np.radians(yaw), np.radians(pitch)
    d = np.array([np.sin(y) * np.cos(p), -np.cos(y) * np.cos(p), np.sin(p)])
    right = np.cross([0, 0, 1.0], d)
    right /= np.linalg.norm(right)
    up = np.cross(d, right)
    R0 = np.stack([right, up, d], 1) @ g1.rot([0, 0, 1], np.radians(roll))
    sh = rng.uniform(-0.8, 0.8, 2) if rng.random() < 0.5 else np.zeros(2)
    t = 2 * np.tan(fov / 2)
    r = np.array([sh[0] * t, sh[1] * t, -1.0])
    r /= np.linalg.norm(r)
    ax = np.cross([0, 0, -1.0], r)
    Q = g1.rot(ax, np.arcsin(min(np.linalg.norm(ax), 1.0))) if np.linalg.norm(ax) > 1e-9 else np.eye(3)
    off = rng.normal(0, 0.018, 3)
    tgt = np.asarray(centre, float) + off + np.array([0.0, 0.04 * min(abs(np.sin(y)), 1.0), 0.0])
    return {"eye": tgt + d * dist, "R": R0 @ Q.T, "fov": float(np.degrees(fov)), "shift": sh, "yaw": yaw, "pitch": pitch, "roll": roll,
            "f_mm": float(36.0 * dist / side * 0.3), "dist": dist, "side": side, "d": d}


def lighting(rng, cam) -> str:
    if rng.random() >= 0.15:
        return g1.lighting(rng, cam)
    d, right, up = cam["d"], cam["R"][:, 0], np.array([0, 0, 1.0])       # HARD TOP light: a small high sun, a dark room
    az, el = np.radians(rng.normal(0, 40)), np.radians(rng.uniform(60, 88))
    key = np.cos(el) * (np.cos(az) * d + np.sin(az) * right) + np.sin(el) * up
    L = [{"dir": key.tolist(), "energy": float(rng.uniform(3.0, 6.5)), "angle": float(rng.uniform(1.0, 5.0)), "color": g1.kelvin(rng)}]
    if rng.random() < 0.4:
        L.append({"dir": (0.9 * d + 0.1 * up).tolist(), "energy": float(rng.uniform(0.05, 0.3)), "angle": 40.0, "shadow": False, "specular": 0.0})
    g = float(rng.uniform(0.2, 0.7))
    return json.dumps({"lights": L, "world": {"color": [g, g, g], "strength": float(rng.uniform(0.04, 0.3))},
                       "exposure": float(np.clip(rng.normal(-0.3, 0.45), -1.5, 0.8)),
                       "view": str(rng.choice(["Khronos PBR Neutral", "AgX", "Standard"], p=[0.5, 0.35, 0.15])), "hard_top": True})


def _state(args):
    base, c, teeth, e = args
    from hifipushie import humanfit
    b = copy.deepcopy(base)
    idn = {f"head_{i:03d}": round(float(x), 5) for i, x in enumerate(c)}
    idn.update({k: v for k, v in (base["head"].get("identity") or {}).items() if k.startswith("eyes_")})
    idn.update({f"teeth_{i:03d}": round(float(x), 4) for i, x in enumerate(teeth)})
    b["head"]["identity"] = idn
    b["head"]["expression"] = {n: round(float(x), 5) for n, x in zip(_enames(), e) if abs(x) >= 1e-4}
    st = humanfit.state(b)
    h = st["head"]
    return (np.asarray(st["tpl"]["P"], np.float32), np.asarray(h["gnm_world"], np.float32), np.asarray(st["L"], np.float32),
            np.asarray(h["eyes"], np.float32)[:, :3] if np.ndim(h["eyes"]) == 2 else np.array([np.asarray(q, float)[:3] for q in h["eyes"]], np.float32))


def main():
    out = Path(sys.argv[1])
    kw = dict(a.split("=", 1) for a in sys.argv[2:])
    seed, n = int(kw.get("seed", 0)), int(kw.get("n", 8))
    size, spp, voxel = int(kw.get("size", 320)), int(kw.get("samples", 6)), float(kw.get("voxel", 0.002))
    if kw.get("hair") is not None:
        os.environ["DL_HAIR2"] = kw["hair"]
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    from hifipushie import base as basemod, denselm, humanfit, likeness, onemesh, render, resources, scene, store
    t0 = time.time()
    dr = dressing(rng)
    sp = base_spec(dr, voxel)
    name = kw.get("name", f"d2_s{seed:05d}")
    d = store._dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp))
    (out / "dressing.json").write_text(json.dumps(dr, indent=1))
    if dr.get("hair"):
        from hifipushie import hair
        try:
            hair.groom(name, replace=True, note="denselm", patch=dr["hair"]["patch"])
        except Exception as e_:  # noqa: BLE001
            print(f"step: groom {dr['hair']['kind']} failed ({str(e_)[:200]}): the default groom", flush=True)
            hair.groom(name, replace=True, note="denselm")
        sp = store.load(name)
        sp["hair"]["look"] = {**(sp["hair"].get("look") or {}), **hair.seen_look(dr["hair"]["color"])}
        (d / "spec.json").write_text(json.dumps(sp))
    with resources.heavy(f"denselm stage {name}", gb=8):
        sn, st_spec = stage(name, sp, voxel, bool(dr.get("hair")), log=lambda s: print(s, flush=True))
    hair_job = None
    if dr.get("hair"):
        from hifipushie import hair
        hair_job = out / "hair_job.json"
        hair_job.write_text(json.dumps(hair.job(sn, st_spec)))
    t_stage = time.time() - t0
    print(f"step: stage {sn} in {t_stage:.0f} s", flush=True)
    st0 = humanfit.state(sp["base"])
    tpl, h0 = st0["tpl"], st0["head"]
    P0 = np.asarray(tpl["P"], float)
    W0 = np.asarray(h0["gnm_world"], float)
    g = basemod._gnm_data()
    gr = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    Fq = likeness.model_mesh_from_state(st0)["F"]
    skin_v = (gid < 0) | gr["skin"][np.maximum(gid, 0)]
    F_skin = Fq[skin_v[Fq].all(1)]
    Q = np.asarray(g["quads"], int)
    piece = gr["upper_teeth_and_gums"] | gr["lower_teeth_and_gums"] | gr["tongue"]
    pid = np.where(piece)[0]
    loc = np.full(len(W0), -1)
    loc[pid] = len(P0) + np.arange(len(pid))

    def tris(mask):
        q = Q[mask[Q].all(1)]
        return loc[np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]]]
    F_teeth = tris(gr["upper_teeth_and_gums"] | gr["lower_teeth_and_gums"])
    F_tongue = tris(gr["tongue"])
    ALL0 = np.concatenate([P0, W0[pid]])
    LMS = denselm.landmarks_v2()
    lid = LMS["gnm_all"]
    # the model's vertex of each GNM vertex (skin: the one mesh's own; a check that both evaluations agree)
    at = np.full(int(gid.max()) + 1, -1)
    at[gid[gid >= 0]] = np.where(gid >= 0)[0]
    chk = float(np.abs(P0[at[LMS["gnm"]]] - W0[LMS["gnm"]]).max())
    print(f"step: skin landmarks: the one mesh against GNM's own evaluation: max {chk * 1000:.2f} mm", flush=True)
    eye0 = np.array([np.asarray(q, float)[:3] for q in h0["eyes"]])
    axes0 = np.asarray((h0.get("eye_gnm") or {}).get("axes", [[0, -1, 0], [0, -1, 0]]), float)
    eyeside = [int(np.argmin(np.linalg.norm(eye0 - W0[LMS["gnm_all"][ids_]].mean(0), axis=1))) for ids_ in (LMS["left_eye"], LMS["right_eye"])]
    probe = kw.get("probe", "0") == "1"
    ids, teeth, what = [], [], []
    for _ in range(n):
        c, tt, w = identity(rng, dr)
        ids.append(c), teeth.append(tt), what.append(w)
    ex = [expression(rng) for _ in range(n)]
    if probe:      # the expression families on the stage's own head, front and 3/4, one light
        from hifipushie import blockin as bi
        A = arkit()
        fam = [{}, {"jawOpen": 1.0}, {"jawOpen": 0.4}, {"mouthSmileLeft": 0.9, "mouthSmileRight": 0.9, "mouthUpperUpLeft": 0.6, "mouthUpperUpRight": 0.6},
               {"mouthSmileLeft": 0.7, "mouthSmileRight": 0.7}, {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0}, {"eyeWideLeft": 1.0, "eyeWideRight": 1.0},
               {"eyeSquintLeft": 1.0, "eyeSquintRight": 1.0}, {"browDownLeft": 1.0, "browDownRight": 1.0}, {"mouthFunnel": 0.8, "jawOpen": 0.3},
               {"mouthPucker": 0.9}, {"mouthFrownLeft": 0.9, "mouthFrownRight": 0.9}]
        n = len(fam) * 2
        ids = [bi.identity(sp)] * n
        teeth = [np.zeros(80)] * n
        ex = [(sum((w * A[k] for k, w in f.items()), np.zeros(383)), f) for f in fam for _ in (0, 1)]
        what = ["probe"] * n
    E = np.array([e for e, _ in ex])
    # THE POSE OF EVERY SAMPLE, LINEAR (0.01 s; humanfit.state takes 2 s a head on a native head: the body's neck is
    # re-fitted to every identity): GNM's own bases at the stage's placement. Checked against the exact build
    # (scratch fast.py): the face 0.13-0.24 mm rms, teeth 0.1 mm, eyeballs 0.00 after a rigid move (the exact build
    # also re-seats the head on the neck by a few mm: a rigid move of the whole head, which a picture cannot show).
    # The neck: the head's move fades to 0 over the rings above the stitch (the asset's g_fade), the body stands.
    t1 = time.time()
    names_i = [str(x) for x in g["identity_names"]]
    IB = np.asarray(g["vertex_identity_basis"], np.float32)
    EB = np.asarray(g["expression_basis"], np.float32)
    JB = np.asarray(g["joint_identity_basis"], np.float64)[:, 2:4]
    Tg = np.asarray(g["template_vertex_positions"], float)
    idn0, ex0 = sp["base"]["head"]["identity"], sp["base"]["head"].get("expression") or {}
    c0 = np.array([float(idn0.get(nm, 0.0)) for nm in names_i])
    e0 = np.array([float(ex0.get(nm, 0.0)) for nm in _enames()])
    world = lambda X: np.stack([X[..., 0], -X[..., 2], X[..., 1]], -1)      # GNM frame -> world (face_ruler._world)
    G0 = world(Tg + np.tensordot(c0, IB, 1) + np.tensordot(e0, EB, 1))
    fv = LMS["gnm"][np.isin(LMS["region"][:LMS["n_skin"]], ["lids", "eyes", "nose", "lips", "mouth", "chin", "cheeks", "brows", "forehead"])]
    ca, cb = G0[fv].mean(0), W0[fv].mean(0)
    U, S_, Vt = np.linalg.svd((G0[fv] - ca).T @ (W0[fv] - cb))
    dd_ = np.sign(np.linalg.det(U @ Vt))
    Rp = (U @ np.diag([1, 1, dd_]) @ Vt).T
    sc = float((S_ * [1, 1, dd_]).sum() / ((G0[fv] - ca) ** 2).sum())
    fade = np.asarray(onemesh.asset()["g_fade"], float)
    hv = np.where(gid >= 0)[0]
    WL = np.zeros((68, len(Tg)))
    for li, r_ in enumerate(np.asarray(g["lm68"], float)):
        WL[li, r_[0::2].astype(int)] = r_[1::2]
    Jw0 = world(np.asarray(g["template_joint_positions"], float)[2:4] + np.tensordot(c0, JB, 1))
    jord = [int(np.argmin(np.linalg.norm(eye0 - (cb + sc * (j_ - ca) @ Rp.T), axis=1))) for j_ in Jw0]
    tix = [names_i.index(f"teeth_{k:03d}") for k in range(80)]
    res = []
    for i in range(n):
        cf = c0.copy()
        cf[:170] = ids[i]
        cf[tix] = teeth[i]
        Wn = W0 + sc * world(np.tensordot((cf - c0).astype(np.float32), IB, 1) + np.tensordot((E[i] - e0).astype(np.float32), EB, 1)) @ Rp.T
        P = P0.copy()
        P[hv] += fade[gid[hv]][:, None] * (Wn[gid[hv]] - W0[gid[hv]])
        eye = eye0.copy()
        dJ = sc * world(np.tensordot(cf - c0, JB, 1)) @ Rp.T
        for j_, k_ in enumerate(jord):
            eye[k_] = eye0[k_] + dJ[j_]
        res.append((P, Wn, WL @ Wn, eye))
    t_state = time.time() - t1
    print(f"step: {n} heads posed in {t_state:.1f} s (GNM's bases, linear)", flush=True)
    meta = {k: [] for k in ("cam_eye", "cam_R", "fov", "shift", "yaw", "pitch", "roll", "f_mm", "dist", "side", "gaze", "light", "eye")}
    Ds, LMw = [], []
    for i in range(n):
        P, Wn, L, eye = (np.asarray(a, float) for a in res[i])
        cam = camera(rng, L[[36, 45, 48, 54]].mean(0))
        if probe:
            tg = L[[36, 45, 48, 54]].mean(0)
            yw = np.radians(-35.0 if i % 2 else 0.0)
            dd = np.array([np.sin(yw), -np.cos(yw), 0.0])
            rr = np.cross([0, 0, 1.0], dd)
            cam = {**cam, "eye": tg + dd * 1.2, "R": np.stack([rr, [0, 0, 1.0], dd], 1), "fov": float(np.degrees(2 * np.arctan(0.13 / 1.2))),
                   "shift": np.zeros(2), "d": dd, "dist": 1.2, "yaw": float(np.degrees(yw)), "pitch": 0.0}
        look_cam = rng.random() < 0.45 or probe
        gy, gp = np.radians(np.clip(rng.normal(0, 12), -28, 28)), np.radians(np.clip(rng.normal(0, 8), -18, 18))
        G = []
        lm = Wn[lid].copy()
        lm[:LMS["n_skin"]] = P[at[LMS["gnm"]]]       # skin: the one mesh's own vertex (what is rendered and what the solve reads)
        for k in (0, 1):
            a0 = axes0[k] / np.linalg.norm(axes0[k])
            if look_cam:
                a1 = cam["eye"] - eye[k]
                a1 /= np.linalg.norm(a1)
                ang = np.degrees(np.arccos(np.clip(a0 @ a1, -1, 1)))
                if ang > 32:
                    a1 = a0 + (a1 - a0) * (32 / ang)
                    a1 /= np.linalg.norm(a1)
            else:
                a1 = g1.rot([0, 0, 1], gy) @ g1.rot([1, 0, 0], gp) @ a0
            ax = np.cross(a0, a1)
            s_ = np.linalg.norm(ax)
            G.append(g1.rot(ax, np.arctan2(s_, a0 @ a1)) if s_ > 1e-9 else np.eye(3))
        for ids_, k in ((LMS["left_eye"], eyeside[0]), (LMS["right_eye"], eyeside[1])):
            lm[ids_] = eye[k] + (lm[ids_] - eye[k]) @ G[k].T
        LMw.append(lm)
        Ds.append((np.concatenate([P, Wn[pid]]) - ALL0).astype(np.float16))
        for k_, v in (("cam_eye", cam["eye"]), ("cam_R", cam["R"]), ("fov", cam["fov"]), ("shift", cam["shift"]), ("yaw", cam["yaw"]),
                      ("pitch", cam["pitch"]), ("roll", cam["roll"]), ("f_mm", cam["f_mm"]), ("dist", cam["dist"]), ("side", cam["side"]),
                      ("gaze", np.array(G)), ("light", g1.PROBE_LIGHT if probe else lighting(rng, cam)), ("eye", eye)):
            meta[k_].append(v)
    e0, e1 = LMS["eye"]
    tol = np.full(LMS["n"], 0.0012)
    tol[e0:e1] = 0.0045           # the iris lies behind GNM's clear cornea (2.9 mm of chamber)
    t2 = time.time()
    jp = out / "job.npz"
    np.savez(jp, P0=ALL0.astype(np.float32), F=F_skin.astype(np.int32), F_teeth=F_teeth.astype(np.int32), F_tongue=F_tongue.astype(np.int32),
             D=np.array(Ds), eye0=eye0, eye=np.array(meta["eye"]), gaze=np.array(meta["gaze"]), cam_eye=np.array(meta["cam_eye"]),
             cam_R=np.array(meta["cam_R"]), fov=np.array(meta["fov"]), shift=np.array(meta["shift"]), LM=np.array(LMw, np.float32),
             light=np.array(meta["light"]), size=size, samples=spp, first=0, tol=tol,
             eevee=json.dumps(json.loads(kw.get("eevee") or os.environ.get("DL_EEVEE", "{}"))))
    cmd = [render.BLENDER, "-b", str(scene.blend_path(sn)), "--python-exit-code", "1", "--python", str(HERE / "blender_gen.py"),
           "--", str(jp), str(out / "part")] + ([str(hair_job)] if hair_job else [])
    with resources.heavy(f"denselm render {name}", gb=6, gpu=os.environ.get("DL_GPU_CLAIM", "0") == "1"):
        r = resources.run(cmd, capture_output=True, text=True, timeout=14400)
    for line in r.stdout.splitlines():
        if line.startswith("@@"):
            print("step:", line[2:], flush=True)
    if r.returncode:
        raise RuntimeError(f"blender failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    jp.unlink()
    t_render = time.time() - t2
    lab = dict(np.load(out / "part" / "labels.npz"))
    for f in sorted((out / "part").glob("*.png")):
        f.rename(out / f.name)
    (out / "part" / "labels.npz").unlink()
    (out / "part").rmdir()
    np.savez_compressed(out / "labels.npz", **lab, landmark_version=LMS["version"], size=size)
    np.savez_compressed(out / "meta.npz", identity=np.array(ids, np.float32), teeth=np.array(teeth, np.float32), expression=E.astype(np.float32),
                        expr_mix=np.array([json.dumps(m) for _, m in ex]), identity_kind=np.array(what),
                        **{k: np.array(v) for k, v in meta.items()}, LM=np.array(LMw, np.float32))
    tm = {"stage_s": round(t_stage, 1), "pose_s": round(t_state, 1), "render_s": round(t_render, 1), "n": n,
          "per_sample_s": round((time.time() - t0) / n, 3), "blender_pose_render_labels_s": lab["sec"].mean(0).round(3).tolist(),
          "host": os.uname().nodename, "size": size, "samples": spp, "voxel": voxel}
    (out / "timing.json").write_text(json.dumps(tm))
    print("step: done", json.dumps(tm), flush=True)


if __name__ == "__main__":
    main()
