"""The six test humans, built through the MCP tool functions (put_model, skin, look_skin) as a fresh LLM would.
humans.py build <k...> | look <k> [views] | sheet"""
import json, sys, time
from pathlib import Path
from hifipushie import server, store

OUT = Path("/home/joe/dev/hifipushie/workspace/skin_renders")
EYES = {
    "iris.L": {"part": "eyes", "color": "#5a3a1e", "path": [{"at": "eye_front.L", "dir": [0, -1, 0]}], "width": 0.0105, "profile": "flat"},
    "pupil.L": {"part": "eyes", "color": "#0c0806", "path": [{"at": "eye_front.L", "dir": [0, -1, 0]}], "width": 0.0042, "profile": "flat"},
    "eye_gloss": {"part": "eyes", "roughness": 0.08, "specular": 0.7},
}


IRIS = {}


def body(age, sex, weight=0.5, muscle=0.5, height=1.7, seed=1, iris="#5a3a1e", head=None, spread=0.45):
    eyes = {}
    IRIS[seed] = iris
    return {"symmetry": True, "blend": 0.035,
            "base": {"body": {"source": "makehuman", "age": age, "weight": weight, "muscle": muscle, "height": height, "sex": sex},
                     "eyes": "eyes", "cornea": True, "look_at": [0.0, -4.0, height * 0.93],
                     "head": {"source": "gnm", "follow_body": True, "seed": seed, "spread": spread, "mouth_gap": 0.0,
                              "expression": {"left_eye_region_000": 0.6, "right_eye_region_000": 0.6}, **(head or {})}},
            "parts": {"body": {"voxel": 0.001}, "eyes": {"color": "#e8e0d6", "voxel": 0.001}},
            "joints": {}, "bones": {}, "paint": eyes,
            "blobs": {"bust_crop": {"at": [0.0, -0.05, height * 0.93], "shape": "box", "size": [0.17, 0.2, 0.21], "op": "intersect", "blend": 0.0}}}


HUMANS = {
    "child": (body(7, 0.5, 0.45, 0.4, 1.22, seed=11, head={}),
              {"tone": {"fitzpatrick": 3, "blood": 0.5}, "age": 7, "features": {"freckles": 0.25, "flush": 0.3}}),
    "teen": (body(16, 0.0, 0.42, 0.4, 1.62, seed=5, iris="#5b7a8c"),
             {"tone": {"fitzpatrick": 1.5, "blood": 0.5, "undertone": -0.3}, "age": 16, "oil": 0.8,
              "features": {"freckles": 0.9, "blemishes": 0.7, "flush": 0.2}, "hair": {"brows": {"color": "#8a6a48", "density": 0.7}}}),
    "woman": (body(32, 0.0, 0.5, 0.45, 1.68, seed=8, iris="#3a2414"),
              {"tone": {"fitzpatrick": 6, "blood": 0.45, "undertone": 0.2}, "age": 32, "oil": 0.6,
               "hair": {"brows": {"color": "#120c0a", "density": 1.0}},
               "makeup": {"foundation": {"amount": 0.6, "finish": "natural"}, "concealer": 0.5, "contour": 0.5,
                          "blush": {"amount": 0.5, "color": "#7a2a26"}, "highlight": 0.7,
                          "eyeshadow": {"color": "#8a5a1e", "finish": "shimmer", "amount": 0.9},
                          "eyeliner": {"amount": 1.0, "wing": 0.006, "width": 0.0014}, "mascara": 1.0, "brows": 0.5,
                          "lipstick": {"color": "#55101e", "finish": "satin"}}}),
    "man": (body(54, 1.0, 0.6, 0.5, 1.8, seed=3, iris="#6b7f8a", spread=0.7),
            {"tone": {"fitzpatrick": 1.3, "blood": 0.55, "undertone": -0.2}, "age": 54, "sun": 0.5,
             "features": {"moles": {"amount": 0.6, "at": [{"at": "lm_mouth_corner.L", "offset": [0.012, -0.002, 0.016]}]}, "flush": 0.35},
             "hair": {"stubble": {"amount": 0.85, "color": "#4a4038"}, "brows": {"grey": 0.3}},
             "scars": [{"kind": "cut", "age": 0.9, "path": [{"at": "lm_brow_outer.L", "offset": [-0.004, -0.008, 0.016]},
                                                              {"at": "lm_brow_outer.L", "offset": [0.002, -0.006, 0.0]},
                                                              {"at": "lm_eye_outer.L", "offset": [0.012, 0.0, -0.018]}]},
                       {"kind": "surgical", "age": 0.7, "normal": [0.5, -0.85, 0], "path": [{"at": "lm_jaw_3.R", "offset": [0.012, -0.03, 0.03]},
                                                                                        {"at": "lm_jaw_4.R", "offset": [0.012, -0.03, 0.022]}]}],
             "tattoos": [{"image": {"text": {"string": "SEMPER\nFIDELIS", "size": 0.008, "align": "center"}, "at": "neck",
                                    "offset": [0.058, -0.012, 0.0], "dir": [0.95, -0.3, 0], "size": [0.05, None], "wrap": "surface"}, "age": 18}]}),
    "elder_woman": (body(78, 0.0, 0.45, 0.3, 1.58, seed=9, iris="#6f8794"),
                    {"tone": {"fitzpatrick": 2, "blood": 0.4}, "age": 82, "sun": 0.6, "thin": 0.8,
                     "hair": {"brows": {"grey": 0.8, "density": 0.45, "thickness": 0.8}}}),
    "elder_man": (body(74, 1.0, 0.5, 0.4, 1.72, seed=17, iris="#2e1c10", spread=0.7),
                  {"tone": {"fitzpatrick": 5.3, "blood": 0.4, "undertone": 0.3}, "age": 76, "sun": 0.4,
                   "hair": {"stubble": {"amount": 0.6, "color": "#bdb8b0"}, "brows": {"grey": 0.7}}}),
}


SCALP = {"child": {"amount": 0.9, "color": "#2a1a10"}, "teen": {"amount": 0.8, "color": "#9a7a50", "hairline": 0.6},
         "woman": {"amount": 1.0, "color": "#0c0808", "hairline": 0.6}, "man": {"amount": 0.7, "color": "#4a4038", "hairline": 0.3},
         "elder_woman": {"amount": 0.6, "color": "#b8b4ae", "hairline": 0.45}, "elder_man": {"amount": 0.5, "color": "#c0bcb6", "hairline": 0.2}}
for _k, (_spec, _sk) in HUMANS.items():
    _sk.setdefault("hair", {})["scalp"] = SCALP[_k]
    _sk["sex"] = _spec["base"]["body"]["sex"]
    _sk["eyes"] = {"iris": IRIS[_spec["base"]["head"]["seed"]]}


def name(k):
    return f"skin_h_{k}"


if __name__ == "__main__":
    cmd, keys = sys.argv[1], sys.argv[2].split(",")
    OUT.mkdir(exist_ok=True)
    for k in keys:
        t = time.time()
        if cmd == "build":
            spec, sk = HUMANS[k]
            print(server.put_model(name(k), spec, note="skin test human"))
            print(server.skin(name(k), sk, replace=True))
        elif cmd == "skin":
            s = store.load(name(k))
            if any(x in (s.get("paint") or {}) for x in ("iris.L", "pupil.L", "eye_gloss")):
                print(server.edit_model(name(k), [{"op": "delete", "kind": "paint", "name": x} for x in ("iris.L", "pupil.L", "eye_gloss")
                                                  if x in s["paint"]]).splitlines()[0])
            print(server.skin(name(k), HUMANS[k][1], replace=True))
        if cmd in ("build", "skin", "look"):
            views = sys.argv[3].split(",") if len(sys.argv) > 3 else ["bust", "three_quarter", "cheek", "eye", "mouth", "forehead"]
            try:
                r = server.look_skin(name(k), views=views, size=int(sys.argv[4]) if len(sys.argv) > 4 else 512, save=str(OUT / f"sk_2w_{k}.png"))
                print(r[-1])
            except Exception as e:
                print("Error", k, repr(e)[:300])
        print(k, "done in", round(time.time() - t), "s", flush=True)
