"""solvecams benchmark: shared pieces. Known GNM-NATIVE heads (block_in_start's default spec from a views list, a class
mean + a random GNM draw + mm moves) shot DRESSED (EEVEE, stage.shoot) through KNOWN cameras. Models: sc_<h>_T (truth,
all views, true cameras), sc_<h>_<set>T (truth, the set's three views), sc_<h>_<set>00 (block_in_start on the set's
pictures: class mean, cameras refit). Pictures /mnt/data/hifipushie/solvecams/synth/sc_<h>_<view>.png."""
import json
import numpy as np
from scipy.spatial.transform import Rotation
from hifipushie import blockin as bi, face_ruler as fr, humanfit, store

S = "/mnt/data/hifipushie/solvecams"
HEADS = {"a": ("male", 11, 0.6, ""), "b": ("male", 12, 0.6, "chin_width:-6,jaw_width:-6"),
         "c": ("female", 13, 0.6, "chin_width:5,jaw_width:6"), "d": ("female", 14, 0.6, ""),
         # the widened set (Part 2): e = another dressing (dark skin, age 60) under a hard TOP light; g = tess_n1's body,
         # skin and strand HAIR (tied back; over the scalp's outline and the ears' tops) with a random identity
         "e": ("male", 17, 0.6, "jaw_width:4", {"skin": {"tone": {"fitzpatrick": 5}, "age": 60.0}, "light": "top"}),
         "g": ("female", 16, 0.6, "", {"from": "tess_n1", "hair": True})}
# view name: (nominal yaw, nominal pitch, lens mm (35 mm equivalent))
VIEWS = {"f": (0, 0, 85), "q23": (23, 0, 85), "q45": (45, 0, 85), "s72": (72, 0, 85), "s90": (90, 0, 85),
         "fu": (0, 8, 85), "fd": (0, -8, 85), "fn": (0, 0, 40), "ff": (0, 0, 200)}
SETS = {"A": ("f", "q45", "s90"), "B": ("f", "q23", "s72"), "P": ("fu", "q45", "s90"), "M": ("fd", "q45", "s90"),
        "N": ("fn", "q45", "s90"), "F": ("ff", "q45", "s90")}
SIZE = (1152, 1536)
PXM = 3500.0        # picture px per metre at the head


def refs(name):
    return json.loads((store.HOME / name / "human_refs.json").read_text())


def write_refs(name, rj):
    (store.HOME / name / "human_refs.json").write_text(json.dumps(rj))


def true_cams(tag):
    rj = refs(f"sc_{tag}_T")
    return {v["name"]: c for v, c in zip(rj["views"], rj["cameras"])}


def landmarks(name):
    return np.asarray(humanfit.state(store.load(name)["base"])["L"], float)[:68]


def cam_err(cam, true, L):
    """A camera against the true one, the head fixed in the world: the relative rotation in the camera's frame as
    (pitch, yaw, roll) degrees (rotation vector about the picture's x / y / z), the head's turn from the camera
    (view_yaw) minus the true one, the picture scale f / z (%), the distance z (%), the focal length (%), and where
    the true head's landmark centre falls (mm at the head, x / y)."""
    R1, R0 = humanfit._cam_rot(cam), humanfit._cam_rot(true)
    rv = np.degrees(Rotation.from_matrix(R1 @ R0.T).as_rotvec())
    c1 = (L.mean(0) - np.asarray(cam["centre"])) @ R1.T + np.asarray(cam["t"])
    c0 = (L.mean(0) - np.asarray(true["centre"])) @ R0.T + np.asarray(true["t"])
    p1, p0 = humanfit.project(cam, L.mean(0)[None])[0], humanfit.project(true, L.mean(0)[None])[0]
    mm = c0[2] / true["f"] * 1000
    return {"pitch": float(rv[0]), "yaw": float(rv[1]), "roll": float(rv[2]),
            "turn": float(abs(fr.view_yaw(cam)) - abs(fr.view_yaw(true))), "view_yaw": float(abs(fr.view_yaw(cam))),
            "scale": float(100 * ((cam["f"] / c1[2]) / (true["f"] / c0[2]) - 1)), "dist": float(100 * (c1[2] / c0[2] - 1)),
            "focal": float(100 * (cam["f"] / true["f"] - 1)), "dx": float((p1 - p0)[0] * mm), "dy": float((p1 - p0)[1] * mm)}


def cam_text(e):
    return (f"yaw {e['yaw']:+5.1f} pitch {e['pitch']:+5.1f} roll {e['roll']:+5.1f} deg | scale {e['scale']:+5.1f} % dist {e['dist']:+6.1f} % "
            f"focal {e['focal']:+6.1f} % | centre {e['dx']:+5.1f} {e['dy']:+5.1f} mm")
