"""Three small models that consume images as paint (the `image` paint generator, images.py):

  img_painting  a framed landscape on a plaster wall (the picture's colours + impasto relief from its luma)
  img_book      an open book: two bowed pages of set text (text rendered to an image, laid on a curved surface)
  img_disc      a disc golf disc with a hot-stamped logo (PNG alpha, metallic foil on a dome)

    uv run python examples/images/make_images.py      # the two images (already committed)
    uv run python examples/image_decals_src.py        # saves the three models into the workspace

The specs name images by "file"; saving copies each into workspace/_images/ and names it by "id".
examples/framed_painting.json is img_painting's spec as written here (by file).
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from hifipushie import store  # noqa: E402

LANDSCAPE = str(HERE / "images" / "landscape.jpg")
LOGO = str(HERE / "images" / "logo.png")


def painting() -> dict:
    W, H = 0.62, 0.465  # the canvas (4:3, as the picture)
    pic = {"file": LANDSCAPE, "at": "canvas", "dir": "front", "size": [W, None]}
    return {
        "symmetry": False, "blend": 0.002,
        "story": {"summary": "a small oil landscape in a gilt frame on a plastered wall, a few years old"},
        "joints": {"c": {"pos": [0, 0, 1.4], "r": 0.01}},
        "parts": {"wall": {"color": "#d9d2c3", "roughness": 0.9}, "frame": {"color": "#a8863f", "roughness": 0.4,
                                                                           "metallic": 0.6},
                  "canvas": {"color": "#ece6d6", "roughness": 0.7}},
        "blobs": {
            "wall": {"shape": "box", "at": [0, 0.06, 1.4], "size": [0.7, 0.03, 0.55], "part": "wall", "blend": 0},
            "frame": {"shape": "box", "at": [0, -0.004, 1.4], "size": [W / 2 + 0.06, 0.025, H / 2 + 0.06],
                      "round": 0.008, "part": "frame", "blend": 0},
            "frame_lip": {"shape": "box", "at": [0, -0.03, 1.4], "size": [W / 2 + 0.035, 0.01, H / 2 + 0.035],
                          "round": 0.006, "part": "frame", "blend": 0.006},
            "opening": {"shape": "box", "at": [0, -0.03, 1.4], "size": [W / 2 - 0.004, 0.03, H / 2 - 0.004],
                        "op": "subtract", "targets": ["frame", "frame_lip"], "blend": 0.004},
            "canvas": {"shape": "box", "at": [0, 0.0, 1.4], "size": [W / 2 + 0.01, 0.012, H / 2 + 0.01],
                       "round": 0.002, "part": "canvas", "blend": 0},
        },
        "paint": {
            "plaster": {"part": "wall", "color": "#c9c0ae", "opacity": 0.5,
                        "noise": {"scale": 0.08, "range": [0.4, 0.75], "warp": 0.8}},
            "gilt_wear": {"part": "frame", "color": "#5a4320", "roughness": 0.7, "metallic": 0.1,
                          "mask": [{"cavity": "concave", "radius": [0.02, 0.004]},
                                   {"noise": {"scale": 0.01, "range": [0.3, 0.7]}, "blend": "multiply"}]},
            "picture": {"part": "canvas", "color": "image", "roughness": 0.45, "image": pic},
            "impasto": {"part": "canvas", "height": 0.00025, "image": {**pic, "channel": "luma"}},
            "brushwork": {"part": "canvas", "height": 0.0001,
                          "mask": [{"image": {**pic, "channel": "coverage"}},
                                   {"noise": {"scale": 0.004, "range": [0.35, 0.75],
                                              "stretch": {"dir": [1, 0, 0.2], "factor": 4}}}]},
        },
    }


TEXT_L = """On Making Things Look Used

Nothing made by hand is uniform. A board cut from a log keeps the curve of the grain; a stone set in a wall leans a little toward its neighbour; a cup that has been washed a thousand times is paler where the hand holds it.

When a model reads as new and false, the fault is rarely the shape. It is the evenness: every edge equally sharp, every surface equally clean, every copy of a thing identical to the last.

So begin with a story. Who used this, and for how long? Where did the rain come from, and what did it touch first? Answer those, and the wear has somewhere to go.

The same holds for paint. A colour laid evenly over a whole part is a colour nobody chose. Let it pool in the hollows, fade where the sun reaches, and break where the edges are knocked."""

TEXT_R = """II. Restraint

The opposite failure is easier to fall into. Grime in every crease, rust on every bolt, chips along every edge: the model ages forty years in an afternoon and stops being believable for the other reason.

Look at a real kitchen table. Most of it is simply a table. The wear gathers at the near edge, under the elbows, around the one chair that everyone prefers.

A good rule: decide where the hands go, put the wear there, and leave the rest alone. Then step back, and take half of it away.

What is left will look as if it happened, rather than as if it were applied: which is the whole of the trick, and the hardest part of it."""


def book() -> dict:
    # each side of the open book: a block cut from a big cylinder lying along Y (the spine), so its top is bowed
    R, pw, ph, top = 0.35, 0.145, 0.21, 0.035
    text = {"font": "serif", "size": 0.0042, "align": "justify", "margin": 0.012, "line": 1.38, "color": "#1d1b19"}
    blobs = {"cover": {"shape": "box", "at": [0, 0, 0.004], "size": [0.162, 0.115, 0.004], "round": 0.002,
                       "part": "cover", "blend": 0}}
    paint = {"leather": {"part": "cover", "color": "#4a2a1e", "roughness": 0.65,
                         "noise": {"scale": 0.01, "range": [0.3, 0.8]}, "opacity": 0.4}}
    for side, sx, txt in (("left", -1, TEXT_L), ("right", 1, TEXT_R)):
        cx = sx * (pw / 2 + 0.004)
        blobs[f"block_{side}"] = {"shape": "cylinder", "at": [cx, 0, top - R], "size": [R, R, ph / 2 + 0.01],
                                  "rot": [90, 0, 0], "part": "paper", "blend": 0}
        blobs[f"trim_{side}"] = {"shape": "box", "at": [cx, 0, top / 2 + 0.004], "size": [pw / 2, ph / 2, top / 2],
                                 "op": "intersect", "targets": [f"block_{side}"], "blend": 0.005}
        paint[f"text_{side}"] = {"part": "paper", "color": "image",
                                 "image": {"text": {**text, "string": txt}, "at": [cx, 0, top + 0.002],
                                           "dir": [0, 0, 1], "up": [0, 1, 0], "size": [pw, ph]}}
    paint["page_edges"] = {"part": "paper", "color": "#cfc6ae", "facing": [0, 0, 1], "range": [0.6, 0.1]}
    return {"symmetry": False, "blend": 0.002,
            "story": {"summary": "an open book lying on a desk"},
            "joints": {"c": {"pos": [0, 0, 0.02], "r": 0.01}},
            "parts": {"cover": {"color": "#5a3324"}, "paper": {"color": "#f1ead8", "roughness": 0.85,
                                                               "specular": 0.3}},
            "blobs": blobs, "paint": paint}


def disc() -> dict:
    return {"symmetry": False, "blend": 0.004,
            "story": {"summary": "a new putter, the stamp still bright"},
            "joints": {"c": {"pos": [0, 0, 0.0], "r": 0.01}},
            "parts": {"disc": {"color": "#e9edf2", "roughness": 0.35}},
            "blobs": {"dome": {"shape": "ellipsoid", "at": [0, 0, 0.0], "size": [0.105, 0.105, 0.022], "part": "disc"},
                      "rim": {"shape": "cylinder", "at": [0, 0, -0.004], "size": [0.106, 0.106, 0.008], "round": 0.007,
                              "part": "disc", "blend": 0.008},
                      "flat": {"shape": "box", "at": [0, 0, -0.04], "size": [0.2, 0.2, 0.028], "op": "subtract",
                               "targets": ["dome", "rim"], "blend": 0.003}},
            "paint": {"stamp": {"part": "disc", "color": "image", "metallic": 0.85, "roughness": 0.25,
                                "image": {"file": LOGO, "at": [0, 0, 0.022], "dir": [0, 0, 1], "size": [0.13, 0.13]}}}}


if __name__ == "__main__":
    models = {"img_painting": painting(), "img_book": book(), "img_disc": disc()}
    for name, spec in models.items():
        if len(sys.argv) > 1 and name not in sys.argv[1:]:
            continue
        (store.HOME / name).mkdir(parents=True, exist_ok=True)
        v = store.save(name, spec, "image decals example")
        print(name, "saved, version", v)
    p = painting()
    rel = lambda s: s.replace(str(HERE.parent) + "/", "")  # noqa: E731
    for k in ("picture", "impasto"):
        p["paint"][k]["image"]["file"] = rel(p["paint"][k]["image"]["file"])
    p["paint"]["brushwork"]["mask"][0]["image"]["file"] = rel(p["paint"]["brushwork"]["mask"][0]["image"]["file"])
    (HERE / "framed_painting.json").write_text(json.dumps(p, indent=1))
