"""tiles.py: the sg_* sheets' tiles in two steps, so a BEFORE model can be rendered by the code that made it.
  tiles.py jobs <a1 model> <after model> <jobs.json>   every tile's frame + lighting (this worktree's code): the reference
        views under their fitted light AT THE PICTURE'S EXPOSURE (skin_read.photo_light: the EV the AFTER model's last
        read measured; the same light and EV for every model: like with like), eye / eye / mouth crops of the front view
        under that light and a raking light, the front view and three unseen angles under a NEUTRAL light.
  tiles.py shoot <model> <jobs.json> <tag>             renders them to $G/out/t_<tag>_<key>.png (skipped when there). Uses
        only skin_read.stage / shoot: runs under main's src too (run_main.sh) for the sf_* BEFORE models."""
import copy, json, os, sys
import numpy as np
from PIL import Image

G = os.environ["G"] + "/out"
RAKE = {"lights": [{"dir": [0.96, -0.25, 0.12], "energy": 4.0, "color": [1.0, 0.98, 0.96], "angle": 6}],
        "world": {"color": [0.5, 0.5, 0.52], "strength": 0.12}, "view": "Standard", "exposure": 0.0}
NEUTRAL = {"lights": [{"dir": [0.08, -0.74, 0.67], "energy": 3.3, "color": [1.0, 1.0, 1.0], "angle": 38},
                      {"dir": [0.0, -1.0, 0.05], "energy": 0.7, "color": [1.0, 1.0, 1.0], "angle": 40, "shadow": False, "specular": 0.0}],
           "world": {"color": [0.8, 0.8, 0.8], "strength": 0.45}, "view": "Standard", "exposure": -0.25}
T = 560


def jobs(a1, after, path):
    from hifipushie import skin_read as sr, blockin as bi, humanfit, store
    import stage as g3stage
    rj = bi._refs(a1)
    boxes = sr.boxes(a1)
    front = bi._front(rj)
    out = {"front": front, "views": len(rj["cameras"]), "tiles": {}, "ev": {}}
    pl = {}
    for vi in range(len(rj["cameras"])):
        lt = sr.photo_light(after, vi)
        out["ev"][vi] = [lt["exposure"], bool(lt["measured"])]
        pl[vi] = {k: v for k, v in lt.items() if k not in ("fitted", "measured")}
        out["tiles"][f"v{vi}"] = [sr.fitted_frame(rj["cameras"][vi], boxes[vi], "v"), pl[vi]]
    cam = rj["cameras"][front]
    L = humanfit.state(store.load(a1)["base"])["L"]
    P = humanfit.project(cam, L)
    sq = lambda cx, cy, side: [cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2]  # noqa: E731
    eye_w = float(np.linalg.norm(P[45] - P[36]))
    crops = {"eyeR": sq(*(P[36:42].mean(0) + [0, 0.05 * eye_w]), 0.62 * eye_w), "eyeL": sq(*(P[42:48].mean(0) + [0, 0.05 * eye_w]), 0.62 * eye_w),
             "mouth": sq(*(0.5 * (P[33] + P[8]) - [0, 0.12 * eye_w]), 1.0 * eye_w)}
    out["crops"] = crops
    for k, cb in crops.items():
        fr = sr.fitted_frame(cam, cb, "v")
        out["tiles"][k] = [fr, pl[front]]
        rk = copy.deepcopy(RAKE)
        if k == "eyeR":        # (the raking light from the eye's own side)
            rk["lights"][0]["dir"][0] *= -1
        out["tiles"][k + "_rk"] = [fr, rk]
    out["tiles"]["n_front"] = [sr.fitted_frame(cam, boxes[front], "v"), NEUTRAL]
    for fr in g3stage.view_frames(store.load(a1), ("three_quarter_other", "profile_right", "low_angle")):
        out["tiles"]["n_" + fr["name"]] = [fr, NEUTRAL]
    json.dump(out, open(path, "w"), default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o))
    print(path, "EV per view", out["ev"])


def shoot(model, path, tag):
    from hifipushie import skin_read as sr, resources, store
    J = json.load(open(path))
    todo = {k: v for k, v in J["tiles"].items() if not os.path.exists(f"{G}/t_{tag}_{k}.png")}
    if not todo:
        return
    with resources.heavy(f"skinfolds2 tiles {model}", gb=6):
        sn = sr.stage(model, store.load(model), log=lambda s: None)
        for k, (fr, lt) in todo.items():
            a = sr.shoot(sn, [{**fr, "name": "v"}], lt, size=2 * T, samples=32)["v"]
            im = Image.fromarray(a)
            im = Image.alpha_composite(Image.new("RGBA", im.size, (205, 205, 205, 255)), im).convert("RGB").resize((T, T), Image.LANCZOS)
            im.save(f"{G}/t_{tag}_{k}.png")
    print(model, tag, len(todo), "tiles")


if __name__ == "__main__":
    if sys.argv[1] == "jobs":
        jobs(*sys.argv[2:5])
    else:
        shoot(*sys.argv[2:5])
