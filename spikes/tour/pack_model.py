"""pack_model.py <model> <job dir> [more models...]: models as a compute-job folder (oxidegen `where: local`):
<job>/ws/<model>/ for each model (its folder minus history and scene / build caches: spec.json, human_refs.json,
skin_projection/, skin_layers/ ...), the reference pictures copied to <job>/ws/_refs/ with their paths written RELATIVE
("@refs/<file>"), and every content-store file the specs name (16-hex image ids in workspace/_images, painted clouds in
workspace/_painted: a skin stack's layer maps, a projection's albedo / detail / confidence) copied to <job>/ws/_images|
_painted. On the machine, `unpack(job)` turns "@refs/" back into absolute paths; the job runs with HIFIPUSHIE_HOME =
<job>/ws. The first model is the job's model (model.txt). Model folders are small (stage caches are rebuilt there)."""
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


if __name__ == "__main__":
    r = pack([sys.argv[1]] + sys.argv[3:], sys.argv[2])
    print(r["job"], ",".join(r["models"]), r["store_files"], "store files", r["kb"], "KB")
