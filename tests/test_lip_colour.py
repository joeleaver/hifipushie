"""skin.lips reaches the whole vermilion on a one-mesh head (the likeloop "lip colour stuck" bug: the upper lip's layer
was drawn border -> contact ring, which seen from the front lies above the lip's own lower front, so ~2/3 of the upper
vermilion kept the face's pale layers whatever skin.lips said)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hifipushie import assets, base, humanfit, humans, onemesh, paint, skin  # noqa: E402


def _ok():
    try:
        assets.path("gnm", base.GNM)
        return True
    except Exception:
        return False


def test_lip_layers_cover_the_vermilion():
    if not _ok():
        return
    sp = humans.spec(age=45, sex=1.0, seed=4, source="human")
    if not sp.get("skin"):
        sp["skin"] = {"age": 45, "sex": 1.0}
    st = humanfit.state(sp["base"])
    P = np.asarray(st["tpl"]["P"], float)
    Q = np.asarray(st["tpl"]["L"]).reshape(-1, 4)
    n = np.zeros_like(P)
    for a, b, c in ((0, 1, 3), (1, 2, 0), (2, 3, 1), (3, 0, 2)):
        np.add.at(n, Q[:, a], np.cross(P[Q[:, b]] - P[Q[:, a]], P[Q[:, c]] - P[Q[:, a]]))
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
    EJ = paint._expanded(sp)["joints"]
    assert sum(k.startswith("verm_") for k in EJ) == 4 * base.VERM_N  # the vermilion's own edges as joints
    g = base._gnm_data()
    gid = np.maximum(np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])], 0)
    ext = np.asarray(g["groups"]["skin_exterior"]) > 0.5
    lys = skin.layers(sp)
    for grp in ("upper_lip", "lower_lip"):
        sel = (np.asarray(g["groups"][grp]) > 0.5)[gid] & ext[gid] & (-n[:, 1] > 0.3)  # front-facing vermilion
        cover = np.zeros(len(P))
        for lname in ("skin:lips_upper", "skin:lips_lower"):
            o = lys[lname]["mask"][0]
            stack = skin.zone(sp, o["zone"]["name"], grow=o["zone"].get("grow", 1.0))
            cover = np.maximum(cover, paint._outline_mask(sp, lname, stack[0]["outline"], P, n))
        # (the border's own vertices lie on the outline: 0.5 there by construction)
        assert (cover[sel] > 0.45).mean() > 0.85, (grp, float((cover[sel] > 0.45).mean()))
    # and the colour follows skin.lips
    hi = skin.layers({**sp, "skin": {**sp["skin"], "lips": {"blood": 3.0}}})["skin:lips_upper"]["color"]
    assert hi[1] < lys["skin:lips_upper"]["color"][1] - 0.05  # redder (less green)
