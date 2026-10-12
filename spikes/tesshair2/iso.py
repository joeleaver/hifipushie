"""iso.py <model> <tag>=<variant> ... [views=backq,right,backl,topback] [size=640]: ISOLATE a groom's faults by
switching pieces off one at a time. Each variant is the model's hair changed IN MEMORY (nothing saved) and rendered on
one shared dressed stage (the stage of $STAGE_MODEL, default th_T04: every th_* model has tess_a1's head).
Variants (joined with +):
  base            the groom as it is
  only:<pat,pat>  only these locks (fnmatch on lock names: tg0_* = gather row 0, tt* = the tail, tf* = frame pieces)
  drop:<pat,pat>  without these locks
  S.<dial>:<v>    hair.strands.<dial> = v (e.g. S.under:0 = no scalp layer, S.roots:0, S.under_length:0.02)
  L.<pat>.<key>:<v>   every lock matching pat: lock[key] = v (L.tg*.width:0.03)
  LS.<pat>.<dial>:<v> every lock matching pat: lock.strands[dial] = v
Tiles $TOUT/iso_<model>_<tag>_<view>.png and one sheet $TOUT/iso_<model>_<tags>.png (a row per variant)."""
import copy, json, os, sys, tempfile
from fnmatch import fnmatch
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import stage
from hifipushie import hair, render, resources, scene, skin_look, store

VIEWS = {"backl": [0.62, 0.78, 0.06], "backq": [-0.6, 0.8, 0.08], "right": [-1, 0.0, 0.0], "back": [0.0, 1.0, 0.1],
         "topback": [-0.15, 0.6, 0.8], "front": [0.0, -1.0, 0.05], "left": [1.0, 0.0, 0.0], "top": [0.0, -0.15, 1.0],
         "frontq": [0.6, -0.8, 0.05], "frontr": [-0.6, -0.8, 0.05]}


def num(v):
    try:
        return json.loads(v)
    except Exception:
        return v


def variant(spec, v):
    sp = copy.deepcopy(spec)
    h = sp["hair"]
    for op in v.split("+"):
        if op == "base":
            continue
        k, _, val = op.partition(":")
        if k == "only":
            h["locks"] = {n: l for n, l in h["locks"].items() if any(fnmatch(n, p) for p in val.split(","))}
        elif k == "drop":
            h["locks"] = {n: l for n, l in h["locks"].items() if not any(fnmatch(n, p) for p in val.split(","))}
        elif k.startswith("S."):
            h.setdefault("strands", {})[k[2:]] = num(val)
        elif k.startswith("LS."):
            pat, dial = k[3:].rsplit(".", 1)
            for n, l in h["locks"].items():
                if fnmatch(n, pat):
                    l.setdefault("strands", {})[dial] = num(val)
        elif k.startswith("L."):
            pat, key = k[2:].rsplit(".", 1)
            for n, l in h["locks"].items():
                if fnmatch(n, pat):
                    l[key] = num(val)
        else:
            raise SystemExit(f"unknown variant op {op}")
    return sp


def frames_for(spec, names, dist=1.6, fov=17.0, dz=-0.03):
    J = skin_look._J(spec)
    nt = J["lm_nose_tip"]
    c = np.array([0.0, nt[1] + 0.11, nt[2] + dz])
    out = []
    for i, n in enumerate(names):
        d = np.asarray(VIEWS[n], float)
        d /= np.linalg.norm(d)
        out.append(render.camera_frame({"eye": (c + d * dist).tolist(), "target": c.tolist(), "fov": fov, "name": n}, i))
    return out, c


def turned_light(f, c):
    """The front picture's light turned round the head with the camera."""
    e = np.asarray(f["eye"], float) - c
    a = np.arctan2(e[0], -e[1])
    R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    lt = copy.deepcopy(stage.FRONT_LIGHT)
    for l in lt["lights"]:
        l["dir"] = (R @ np.asarray(l["dir"], float)).tolist()
        l.pop("window", None)
    return lt


def shoot_spec(sn, st_hair_spec, frames, lighting, size=640, engine="eevee", samples=24, extra=None):
    """Frames of stage `sn` wearing the hair of an in-memory spec. {frame name: RGB image}."""
    st = json.loads((store._dir(sn) / "spec.json").read_text())
    st["hair"] = st_hair_spec["hair"]
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        fr = [{**f, "out": str(Path(tmp) / f"{f['name']}.png")} for f in frames]
        job = {"blend": str(scene.blend_path(sn)), "views": fr, "size": size, "samples": samples, "hide": [], "flat": False,
               "transparent": True, "lighting": {**lighting, "target": fr[0]["center"]}, "eevee": stage.STAGE_EEVEE,
               "mode": "hair_look", "hair": hair.job(sn, st), "clay_views": [], "id_views": [], "look_engine": engine}
        job.update(extra or {})
        scene._blender(job, 3600)
        for f in fr:
            im = Image.open(f["out"])
            if im.mode == "RGBA":
                bg = Image.new("RGBA", im.size, (219, 219, 219, 255))
                im = Image.alpha_composite(bg, im)
            out[f["name"]] = im.convert("RGB").copy()
    return out


if __name__ == "__main__":
    m = sys.argv[1]
    KEYS = ("views", "size", "fov", "dz")
    args = [a for a in sys.argv[2:] if "=" in a]
    kw = dict(a.split("=", 1) for a in args if a.split("=", 1)[0] in KEYS)
    vs = [a.split("=", 1) for a in args if a.split("=", 1)[0] not in KEYS]
    views = kw.get("views", "backq,right,backl,topback").split(",")
    N = int(kw.get("size", 640))
    OUT = os.environ["TOUT"]
    spec = store.load(m)
    sn = stage.ensure(os.environ.get("STAGE_MODEL", "th_T04"))
    frames, c = frames_for(spec, views, fov=float(kw.get("fov", 17.0)), dz=float(kw.get("dz", -0.03)))
    sh = Image.new("RGB", (N * len(views), (N + 18) * len(vs)), "white")
    d = ImageDraw.Draw(sh)
    with resources.heavy(f"tesshair2 iso {m}", gb=6):
        for r, (tag, v) in enumerate(vs):
            sp = variant(spec, v)
            for j, f in enumerate(frames):
                im = shoot_spec(sn, sp, [f], turned_light(f, c), size=N)[f["name"]]
                im.save(f"{OUT}/iso_{m}_{tag}_{f['name']}.png")
                sh.paste(im, (j * N, r * (N + 18) + 18))
            d.text((6, r * (N + 18) + 3), f"{tag} = {v}", fill=(0, 0, 0))
            print("done", tag, flush=True)
    p = f"{OUT}/iso_{m}_{'_'.join(t for t, _ in vs)}.png"
    sh.save(p)
    print(p)
