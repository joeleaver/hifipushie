"""Wrapped image decals (the `image` paint generator's "wrap", images.py):

  wrap_mug      a mug with a label wrapping 300 degrees round it (cylinder wrap, seam behind the handle)
  wrap_bottle   a bottle: a body label (cylinder) and a band on the tapered shoulder (cylinder wrap along the
                shoulder's bone: arc length at the surface's own radius, so the band isn't stretched where it narrows)
  wrap_sticker  a ball with a sticker (surface wrap: geodesic coordinates from its centre), a curved car-door-like
                panel with another, and a globe-style band round a second ball (sphere wrap, span in degrees)

    uv run python examples/images/make_images.py      # label.png, neck.png, sticker.png (committed)
    uv run python examples/image_wraps_src.py         # saves the three models into the workspace
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from hifipushie import store  # noqa: E402

LABEL = str(HERE / "images" / "label.png")
NECK = str(HERE / "images" / "neck.png")
STICKER = str(HERE / "images" / "sticker.png")
LANDSCAPE = str(HERE / "images" / "landscape.jpg")


def mug() -> dict:
    R, H = 0.042, 0.1
    return {
        "symmetry": False, "blend": 0.003,
        "story": {"summary": "a cola-branded diner mug, the label printed round it"},
        "joints": {"base": {"pos": [0, 0, 0], "r": 0.01}, "h0": {"pos": [0, R + 0.004, 0.078], "r": 0.008},
                   "h1": {"pos": [0, R + 0.03, 0.072], "r": 0.008}, "h2": {"pos": [0, R + 0.036, 0.036], "r": 0.008},
                   "h3": {"pos": [0, R + 0.004, 0.024], "r": 0.008}},
        "parts": {"mug": {"color": "#f3efe6", "roughness": 0.25}},
        "bones": {"handle_a": {"a": "h0", "b": "h1", "r_a": 0.007, "r_b": 0.007, "part": "mug", "group": "handle"},
                  "handle_b": {"a": "h1", "b": "h2", "r_a": 0.007, "r_b": 0.007, "part": "mug", "group": "handle"},
                  "handle_c": {"a": "h2", "b": "h3", "r_a": 0.007, "r_b": 0.007, "part": "mug", "group": "handle"}},
        "blobs": {"body": {"shape": "cylinder", "at": [0, 0, H / 2], "size": [R, R, H / 2], "round": 0.005,
                           "hollow": 0.0045, "part": "mug", "blend": 0.0},
                  "mouth": {"shape": "box", "at": [0, 0, H], "size": [0.06, 0.06, 0.01], "op": "subtract",
                            "targets": ["body"], "blend": 0.002}},
        "paint": {"label": {"part": "mug", "color": "image", "roughness": 0.35,
                            "image": {"file": LABEL, "wrap": "cylinder", "at": "body", "span": 300,
                                      "size": [None, 0.066], "depth": 0.01}}},
    }


def bottle() -> dict:
    return {
        "symmetry": False, "blend": 0.004,
        "story": {"summary": "a brown glass bottle with a paper body label and a gold neck band"},
        "joints": {"s0": {"pos": [0, 0, 0.17], "r": 0.034}, "s1": {"pos": [0, 0, 0.235], "r": 0.013},
                   "n1": {"pos": [0, 0, 0.29], "r": 0.013}},
        "parts": {"bottle": {"color": "#4a2a12", "roughness": 0.15}},
        "bones": {"shoulder": {"a": "s0", "b": "s1", "r_a": 0.034, "r_b": 0.0135, "part": "bottle"},
                  "neck": {"a": "s1", "b": "n1", "r_a": 0.0135, "r_b": 0.0125, "part": "bottle"}},
        "blobs": {"body": {"shape": "cylinder", "at": [0, 0, 0.09], "size": [0.034, 0.034, 0.09], "round": 0.006,
                           "part": "bottle", "blend": 0.0},
                  "lip": {"shape": "cylinder", "at": [0, 0, 0.29], "size": [0.0155, 0.0155, 0.005], "round": 0.003,
                          "part": "bottle"}},
        "paint": {
            "body_label": {"part": "bottle", "color": "image", "roughness": 0.6,
                           "image": {"file": LABEL, "wrap": "cylinder", "at": [0, 0, 0.085], "axis": [0, 0, 1],
                                     "span": 200, "depth": 0.01}},
            "neck_band": {"part": "bottle", "color": "image", "roughness": 0.4, "metallic": 0.5,
                          "image": {"file": NECK, "wrap": "cylinder", "axis": "shoulder", "at": [0, 0, 0.205],
                                    "size": [0.07, None], "depth": 0.012}},
        },
    }


def sticker() -> dict:
    return {
        "symmetry": False, "blend": 0.004,
        "story": {"summary": "a ball, a car door panel and a globe, each with a printed decal"},
        "joints": {"ball": {"pos": [0, 0, 0.11], "r": 0.01}, "globe": {"pos": [0.62, 0, 0.11], "r": 0.01}},
        "parts": {"ball": {"color": "#d8452b", "roughness": 0.4}, "door": {"color": "#9fb4c4", "roughness": 0.25,
                                                                          "metallic": 0.6},
                  "globe": {"color": "#e8e2d0", "roughness": 0.5}},
        "blobs": {"ball": {"shape": "ellipsoid", "at": "ball", "size": [0.11, 0.11, 0.11], "part": "ball"},
                  "door": {"shape": "ellipsoid", "at": [0.3, 0.6, 0.25], "size": [0.3, 0.62, 0.25], "part": "door"},
                  "door_cut": {"shape": "box", "at": [0.3, 0.85, 0.25], "size": [0.4, 0.62, 0.3], "op": "subtract",
                               "targets": ["door"], "blend": 0.0},
                  "globe": {"shape": "ellipsoid", "at": "globe", "size": [0.11, 0.11, 0.11], "part": "globe"}},
        "paint": {
            "ball_sticker": {"part": "ball", "color": "image", "roughness": 0.3,
                             "image": {"file": STICKER, "wrap": "surface", "at": [0.03, -0.2, 0.15],
                                       "size": [0.12, 0.12]}},
            "door_sticker": {"part": "door", "color": "image", "roughness": 0.3,
                             "image": {"file": STICKER, "wrap": "surface", "at": [0.36, -0.2, 0.3],
                                       "size": [0.2, 0.2]}},
            "globe_map": {"part": "globe", "color": "image", "roughness": 0.5,
                          "image": {"file": LANDSCAPE, "wrap": "sphere", "at": "globe", "span": [360, 120],
                                    "depth": 0.02}},
        },
    }


if __name__ == "__main__":
    models = {"wrap_mug": mug(), "wrap_bottle": bottle(), "wrap_sticker": sticker()}
    for name, spec in models.items():
        if len(sys.argv) > 1 and name not in sys.argv[1:]:
            continue
        (store.HOME / name).mkdir(parents=True, exist_ok=True)
        v = store.save(name, spec, "image wraps example")
        print(name, "saved, version", v)
