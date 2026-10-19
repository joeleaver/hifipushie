"""shots.py <model> [stage=<model whose head stage is used>] [size=768] [samples=8] [views=v0,v1,v2,backl] [tag=]
[like=<model>] [ev=<stops>] [glb=<hair GLB> params=<json> alpha=game cutoff=0.33 only=<json tri ranges> shadow=0]: hair renders for the
hair-cards gates, ALL views in ONE Blender start (per-view light rigs: blender_scene.render's view "lights"), each with
the hair's id pass at the same frame (an exact hair mask): $TOUT/s_<model><tag>_<v>.png, id_<model><tag>_<v>.png.
- views v0, v1, v2: the reference pictures' fitted cameras under the fitted photo light (spikes/tesshair7 shots7);
  backl / backq / right / back / left / front / crown / top: the front light turned round with the camera.
- like=<model>: THAT model's cameras, moved and scaled with the head (scalp centre / median radius): the same view
  OF THE HEAD, for a groom re-seated on a different head (hair.reseat).
- g1v0 / g3backl ...: game-distance views (game_view: 1 m / 3 m, fov 59, render with size=1080 = native game pixels).
- glb=: an exported hair GLB drawn as a game draws it (blender_cards.game_material: the export's shading notes) in
  place of the model's strand groom; only= keeps triangle ranges (the report's "layers") to isolate one.
Light by design: 768 px, 8 samples by default (heavy hair renders reset the laptop's GPU, 2026-10-14); full renders
go to the offload machine (spikes/haircards/job_cards.py)."""
import copy
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

import stage
from hifipushie import hair, render, resources, scene, skin_look, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
N = int(kw.get("size", 768))
views = kw.get("views", "v0,v1,v2,backl").split(",")
OUT = os.environ["TOUT"]
TAG = kw.get("tag", "")
spec = store.load(m)
like = kw.get("like")
refs = json.loads((store.HOME / (like or m) / "human_refs.json").read_text())
if like:
    sc_a, sc_b = hair.scalp(like), hair.scalp(m, spec)
    CA, CB, KS = np.asarray(sc_a.C, float), np.asarray(sc_b.C, float), float(np.median(sc_b.R) / np.median(sc_a.R))
    print(f"like {like}: head x{KS:.3f}, centre moved {np.round((CB - CA) * 1000, 1)} mm", flush=True)


def moved(f):
    if not like:
        return f
    f = dict(f)
    for key in ("eye", "center"):
        f[key] = (CB + KS * (np.asarray(f[key], float) - CA)).tolist()
    return f


W, H = 1152, 1536
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]
J = skin_look._J(store.load(like) if like else spec)
nt = J["lm_nose_tip"]
c = np.array([0.0, nt[1] + 0.11, nt[2] - 0.03])
DIRS = {"backl": [0.62, 0.78, 0.06], "backq": [-0.6, 0.8, 0.08], "right": [-1, 0.0, 0.0], "back": [0.0, 1.0, 0.1],
        "left": [1.0, 0.0, 0.0], "front": [0.0, -1.0, 0.05], "crown": [0.25, -0.45, 1.0], "top": [0.0, -0.2, 1.0]}
_sm = kw.get("stage", m)
sn = stage.ensure(_sm) if (store.HOME / _sm / "spec.json").exists() else "_g3_" + _sm
st = json.loads((store._dir(sn) / "spec.json").read_text())
st["hair"] = spec["hair"]
GLB = kw.get("glb")
CARD = json.loads(open(kw["params"][1:]).read() if kw.get("params", "").startswith("@") else kw.get("params", "{}"))

GAME_FOV = 59.0  # gates.md game distance: 1920x1080, vertical fov ~59 deg; a square N=1080 frame = its centre columns


def game_view(v, i):
    """g<metres><view> (g1v0, g3backl): the game camera at that distance from the head centre along the view's
    direction (vN: the fitted photo camera's), vertical fov 59 deg, no lens shift: render size=1080 for native pixels."""
    dist, b = float(v[1]), v[2:]
    if b[0] == "v" and b[1:].isdigit():
        f0 = stage.fitted_frame(refs["cameras"][int(b[1:])], BOX, b)
        d, up = np.asarray(f0["dir"], float), f0["up"]
        lt = stage.photo_light(like or m, int(b[1:]))
    else:
        d, up = np.asarray(DIRS[b], float) / np.linalg.norm(DIRS[b]), [0, 0, 1]
        lt = None
    t = c if not like else CB + KS * (c - CA)
    f = render.camera_frame({"eye": (t + d * dist).tolist(), "target": t.tolist(), "fov": GAME_FOV, "up": up, "name": v}, i)
    return f, lt


frames, rigs = [], []
for i, v in enumerate(views):
    if v[0] == "g" and v[1].isdigit():
        f, lt = game_view(v, i)
        if lt is None:
            e = np.asarray(f["eye"], float) - np.asarray(f["center"], float)
            a = np.arctan2(e[0], -e[1])
            R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
            lt = copy.deepcopy(stage.FRONT_LIGHT)
            for l in lt["lights"]:
                l["dir"] = (R @ np.asarray(l["dir"], float)).tolist()
                l.pop("window", None)
        frames.append(f)
        rigs.append(lt)
        continue
    if v[0] == "v" and v[1:].isdigit():
        f = stage.fitted_frame(refs["cameras"][int(v[1:])], BOX, v)
        lt = stage.photo_light(like or m, int(v[1:]))
    else:
        d = np.asarray(DIRS[v], float) / np.linalg.norm(DIRS[v])
        f = render.camera_frame({"eye": (c + d * 1.6).tolist(), "target": c.tolist(), "fov": 17.0, "name": v}, i)
        e = np.asarray(f["eye"], float) - c
        a = np.arctan2(e[0], -e[1])
        R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        lt = copy.deepcopy(stage.FRONT_LIGHT)
        for l in lt["lights"]:
            l["dir"] = (R @ np.asarray(l["dir"], float)).tolist()
            l.pop("window", None)
    frames.append(moved(f))
    rigs.append(lt)
if kw.get("shadow", "").startswith("game"):  # shadow=game[:<texel mm>[:<filter>]]: a game's shadow map (blender_scene
    g_ = kw["shadow"].split(":")  # light keys shadow_res / shadow_filter), on every view's suns
    for lt_ in rigs:
        for l in lt_["lights"]:
            l["shadow_res"] = float(g_[1]) / 1000 if len(g_) > 1 else 0.004
            l["shadow_filter"] = float(g_[2]) if len(g_) > 2 else 2.0
# (one rig shape for every view: the first view's, with a window on its key; views re-aim / re-weight its suns)
base = copy.deepcopy(next((r for r in rigs if any(l.get("window") for l in r["lights"])), rigs[0]))
if float(kw.get("ev", 0)):  # ev=<stops>: added to the exposure (Garrett's hair sheets: ev 1.0, hair-garrett successor 18)
    base["exposure"] = float(base.get("exposure", 0.0)) + float(kw["ev"])

with resources.heavy(f"haircards shots {m}{TAG}", gb=8), tempfile.TemporaryDirectory() as tmp:
    vf, idf = [], []
    for v, f, lt in zip(views, frames, rigs):
        vf.append({**f, "name": v, "out": str(Path(tmp) / f"{v}.png"), "lights": lt["lights"]})
        if kw.get("shadow", "").startswith("game") and kw.get("shadowlod", "1") == "1" and v[0] == "g" and v[1].isdigit():
            vf[-1]["card_shadow"] = float(v[1]) < 3  # the shading notes' hair shadow LOD: cards cast at 1 m, not at 3 m+
        idf.append({**f, "name": v + "_id", "out": str(Path(tmp) / f"{v}_id.png")})
    job = {"blend": str(scene.blend_path(sn)), "views": vf, "size": N, "samples": int(kw.get("samples", 8)), "hide": [],
           "flat": kw.get("flat") == "1", "transparent": True, "lighting": {**base, "target": frames[0]["center"]},
           # rays=<n> (default 4, round 20): EEVEE's shadow rays per sample, for groom AND cards. At 1 (the old default) any
           # shadowed skin read as grain (0.65 vs 0.29 unshadowed); 4 stands in for an engine's filtered soft shadow
           "eevee": {**stage.STAGE_EEVEE, "shadow_ray_count": int(kw.get("rays", 4))},
           "mode": "hair_look", "clay_views": [], "id_views": idf, "look_engine": "eevee"}
    if GLB:
        job.update(mode="hair_glb_look", glb=GLB, alpha=kw.get("alpha", "game"), card_params=CARD,
                   aux=str(Path(GLB).parent / "hair_aux.png"), cutoff=float(kw.get("cutoff", 0.33)))
        if kw.get("only"):
            job["only_tris"] = json.loads(kw["only"])
        if kw.get("shadow") == "0":  # shadow=0: the cards cast no shadow (test pass)
            job["card_shadow"] = False
        if kw.get("dbg"):  # dbg=<json>: blender_scene._glb_debug's isolation switches (offset, hide_hair, probe)
            job.update(json.loads(kw["dbg"]))
        if kw.get("proxy") == "0":  # proxy=0: no shadow proxy (the cards cast their own shadow, as before round 19)
            job["shadow_proxy"] = False
    else:
        job["hair"] = hair.job(sn, st)
        if kw.get("gshadow"):  # gshadow=opaque: the strand groom's own shadow made opaque (no transparent shadow), the
            job["groom_shadow"] = kw["gshadow"]  # strands cast explicitly (round 20: the source frames' groom cast ~none)
        if kw.get("gproxy"):  # gproxy=<obj>: the groom's shadow caster (gproxy.py: the cards' shadow-proxy recipe on the
            job["groom_proxy"] = kw["gproxy"]  # strands), shadow-only; the strands cast none (round 22, "gSc")
    t0 = time.time()
    out = scene._blender(job, 3600)
    for ln in str(out).splitlines():
        if ln.startswith("@@probe"):
            print(ln, flush=True)
    fr = [float(ln.split()[1]) for ln in str(out).splitlines() if ln.startswith("@@frame")]
    print(f"{m}{TAG}: {len(views)} views in {time.time() - t0:.0f} s wall; frames {fr} s", flush=True)
    json.dump({v: {k: f[k] for k in ("eye", "center", "fov", "dir", "up")} for v, f in zip(views, frames)},
              open(f"{OUT}/frames_{m}{TAG}.json", "w"))
    for v, f, lt in zip(views, vf, rigs):
        im = Image.open(f["out"])
        if im.mode == "RGBA":
            bg = Image.new("RGBA", im.size, tuple(int(255 * min(1.0, x)) for x in lt.get("backdrop", [0.86, 0.86, 0.86])) + (255,))
            im = Image.alpha_composite(bg, im)
        im.convert("RGB").save(f"{OUT}/s_{m}{TAG}_{v}.png")
    for v, f in zip(views, idf):
        Image.open(f["out"]).convert("RGB").save(f"{OUT}/id_{m}{TAG}_{v}.png")
print("done", m, flush=True)
