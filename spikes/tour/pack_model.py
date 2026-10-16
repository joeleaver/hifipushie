"""pack_model.py <model> <job dir> [more models...]: models as a compute-job folder (oxidegen `where: local`):
<job>/ws/<model>/ for each model (its folder minus history and scene / build caches: spec.json, human_refs.json,
skin_projection/, skin_layers/ ...), the reference pictures copied to <job>/ws/_refs/ with their paths written RELATIVE
("@refs/<file>"), and every content-store file the specs name (16-hex image ids in workspace/_images, painted clouds in
workspace/_painted: a skin stack's layer maps, a projection's albedo / detail / confidence) copied to <job>/ws/_images|
_painted. On the machine, `unpack(job)` turns "@refs/" back into absolute paths; the job runs with HIFIPUSHIE_HOME =
<job>/ws. The first model is the job's model (model.txt). Model folders are small. --stage <name> ships a built head
stage as well (pack_stage: the machine then skips its ~3 min sync)."""
import json, os, re, shutil, sys

SKIP = {"history", "scene_cache", "scene.blend", "scene.blend1", "progress.log", "build.npz", "closeup.npz"}
STORES = ("_images", "_painted")   # content-addressed stores a spec names files in by id
_ID = re.compile(r"^[0-9a-f]{16}$")


def _home():
    return os.environ.get("HIFIPUSHIE_HOME", "/home/joe/dev/hifipushie/workspace")


def _ids(x, out):
    """Every 16-hex string in a spec (keys too: some layers are keyed by id)."""
    if isinstance(x, dict):
        for k, v in x.items():
            _ids(k, out); _ids(v, out)
    elif isinstance(x, list):
        for v in x:
            _ids(v, out)
    elif isinstance(x, str) and _ID.match(x):
        out.add(x)
    return out


def store_files(spec, home=None):
    """{store/file: absolute path} of the content-store files a spec names."""
    home = home or _home(); found = {}
    for i in sorted(_ids(spec, set())):
        for st in STORES:
            d = os.path.join(home, st)
            for ext in (".png", ".npz", ".npy", ".exr", ".jpg"):
                p = os.path.join(d, i + ext)
                if os.path.isfile(p):
                    found[f"{st}/{i}{ext}"] = p
    return found


def pack(models, job, home=None):
    home = home or _home(); ws = os.path.join(job, "ws")
    os.makedirs(os.path.join(ws, "_refs"), exist_ok=True)
    named = {}
    for m in models:
        src, dst = os.path.join(home, m), os.path.join(ws, m)
        shutil.copytree(src, dst, ignore=lambda d, fs: [f for f in fs if f in SKIP or f.endswith(".blend1")],
                        dirs_exist_ok=True)
        rp = os.path.join(src, "human_refs.json")
        if os.path.isfile(rp):
            rj = json.load(open(rp))
            for v in rj.get("views", []):
                f = os.path.basename(v["image"])
                shutil.copy(v["image"], os.path.join(ws, "_refs", f))
                v["image"] = "@refs/" + f
            json.dump(rj, open(os.path.join(dst, "human_refs.json"), "w"))
        named.update(store_files(json.load(open(os.path.join(src, "spec.json"))), home))
    for rel, p in named.items():
        os.makedirs(os.path.dirname(os.path.join(ws, rel)), exist_ok=True)
        shutil.copy(p, os.path.join(ws, rel))
    open(os.path.join(job, "model.txt"), "w").write(models[0])
    kb = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(job) for f in fs) // 1024
    return {"job": job, "models": list(models), "store_files": len(named), "kb": kb}


def unpack(job):
    """On the machine: every packed model's "@refs/<file>" back to an absolute path under <job>/ws/_refs."""
    ws = os.path.join(os.path.abspath(job), "ws")
    for m in os.listdir(ws):
        p = os.path.join(ws, m, "human_refs.json")
        if not os.path.isfile(p):
            continue
        rj = json.load(open(p))
        for v in rj.get("views", []):
            v["image"] = v["image"].replace("@refs/", os.path.join(ws, "_refs") + "/")
        json.dump(rj, open(p, "w"))
    return ws


# A built head stage (spikes/garrett3/stage.py: _g3_<model>[_posed][_texN]) shipped WITH the job, so the machine skips its
# sync (remeshing + paint measuring: 170-180 s a stage on NICO-TOP, 2026-10-15): scene.blend re-saved zstd-compressed
# (162 -> ~50 MB) with its images pointed at "//../_images/<file>" (the job's ws/_images, copied there), plus the stage's
# spec / key and hair caches. stage.ensure on the machine finds key == g3_stage.key and returns at once. The key holds a
# hash of the pipeline's source files, so pack from a clean tree at the commit the job runs (remote.sh archives HEAD):
# a stale key only costs the old sync, never wrong pictures.
STAGE_FILES = ("spec.json", "g3_stage.key")
_RESAVE = r"""
import bpy, json, os, sys
out, imgs = sys.argv[sys.argv.index("--") + 1:][:2]
got = []
for im in bpy.data.images:
    if im.source != "FILE" or im.packed_file is not None or not im.filepath:
        continue
    p = bpy.path.abspath(im.filepath)
    got.append(p)
    im.filepath = "//../_images/" + os.path.basename(p)
json.dump(got, open(imgs, "w"))
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=out, compress=True, relative_remap=False, copy=True)
"""


def pack_stage(stage, job, home=None, blender=None):
    """Copy the built stage `stage` into <job>/ws/<stage> (see above). Returns {"stage", "mb"} or None when the stage
    isn't built here (the machine syncs it, as before)."""
    import subprocess, tempfile
    home = home or _home(); src, dst = os.path.join(home, stage), os.path.join(job, "ws", stage)
    if not all(os.path.isfile(os.path.join(src, f)) for f in STAGE_FILES + ("scene.blend",)):
        return None
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        if f in STAGE_FILES or (f.startswith("hair_") and f.endswith(".npz")):
            shutil.copy(os.path.join(src, f), os.path.join(dst, f))
    if blender is None:
        from hifipushie import render
        blender = render.BLENDER
    with tempfile.TemporaryDirectory() as tmp:
        scr, imgs = os.path.join(tmp, "resave.py"), os.path.join(tmp, "images.json")
        open(scr, "w").write(_RESAVE)
        subprocess.run([blender, "-b", "--factory-startup", os.path.join(src, "scene.blend"), "--python-exit-code", "1",
                        "--python", scr, "--", os.path.join(dst, "scene.blend"), imgs], check=True, capture_output=True)
        for p in json.load(open(imgs)):
            q = os.path.join(job, "ws", "_images", os.path.basename(p))
            if os.path.isfile(p) and not os.path.isfile(q):
                os.makedirs(os.path.dirname(q), exist_ok=True)
                shutil.copy(p, q)
    mb = sum(os.path.getsize(os.path.join(dst, f)) for f in os.listdir(dst)) / 2 ** 20
    return {"stage": stage, "mb": round(mb, 1)}


if __name__ == "__main__":
    # pack_model.py <model> <job dir> [more models...] [--stage <stage>]...: --stage ships a built head stage too
    a, stages = sys.argv[1:], []
    while "--stage" in a:
        i = a.index("--stage"); stages.append(a[i + 1]); del a[i:i + 2]
    r = pack([a[0]] + a[2:], a[1])
    print(r["job"], ",".join(r["models"]), r["store_files"], "store files", r["kb"], "KB")
    for s_ in stages:
        print("stage", s_, pack_stage(s_, a[1]) or "not built here: the machine syncs it")
