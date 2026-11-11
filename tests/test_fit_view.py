"""fit_view.py: fitting a model's numbers to pictures from a fitted (perspective) camera, a part's own outline seen
in front of the rest, and the press rule (a part sinks in only where it joins on)."""
import numpy as np

from hifipushie import fit as F
from hifipushie import fit_view as FV
from hifipushie import sdf
from hifipushie.spec import compile_prims

CAM = {"az": -25.0, "el": 8.0, "roll": 0.0, "f_px": 1400.0, "aim": [0.0, 0.0, 0.5], "dist": 2.0, "size": [400, 400]}
BOX = (150, 50, 330, 230)


def _spec(ear_at, tip_at=None):
    blobs = {"head": {"shape": "ellipsoid", "at": [0, 0, 0.5], "size": [0.12, 0.11, 0.11]},
             "ear": {"shape": "ellipsoid", "at": list(ear_at), "size": [0.05, 0.025, 0.03], "blend": 0.006}}
    if tip_at:
        blobs["tip"] = {"shape": "ellipsoid", "at": list(tip_at), "size": [0.02, 0.02, 0.02], "blend": 0.006}
    return {"symmetry": False, "blend": 0.01, "joints": {}, "bones": {}, "blobs": blobs}


def _mask(s, elements=None):
    """The picture a target would trace: the whole silhouette, or the elements' seen pixels."""
    v = FV.View("m", CAM, np.zeros((400, 400), bool), BOX, None)
    g = sdf.evaluate(compile_prims(s), 128)
    gf = None
    if elements:
        fp = FV._sel(elements)(s)
        gf = sdf.evaluate(fp, 128, box=(np.min([p.lo for p in fp], 0) - .01, np.max([p.hi for p in fp], 0) + .01))
    x0, y0, x1, y1 = BOX
    ys, xs = np.mgrid[y0:y1, x0:x1]
    fa, _, ff, _ = FV._march(v, np.stack([xs.ravel(), ys.ravel()], 1).astype(float), g, FV._depths(g, v), gf)
    m = np.zeros((400, 400), bool)
    m[y0:y1, x0:x1] = ((ff if elements else fa) < 0).reshape(ys.shape)
    return m


def test_recovers_a_moved_part_from_a_three_quarter_camera():
    true, start = _spec((0.09, 0.0, 0.62)), _spec((0.07, 0.01, 0.60))
    tg = [{"label": "whole", "camera": CAM, "mask": _mask(true), "box": BOX},
          {"label": "ear", "camera": CAM, "mask": _mask(true, ["ear"]), "box": BOX, "elements": ["ear"]}]
    res = FV.fit(start, tg, groups=("offset",), only=["ear"], iterations=8)
    at = np.array(res.spec["blobs"]["ear"]["at"])
    assert np.abs(at - [0.09, 0.0, 0.62]).max() < 0.004, (at, res.log)
    assert res.after["ear"] > 0.95 > res.before["ear"], res.log
    assert res.spec["blobs"]["head"] == start["blobs"]["head"]  # only the named element moves


def test_part_outline_sees_what_the_whole_silhouette_cannot():
    """Sinking the ear into the head hardly changes the whole silhouette from this camera; its seen outline does."""
    up, sunk = _spec((0.09, 0.0, 0.62)), _spec((0.075, -0.02, 0.585))
    whole = [_mask(s) for s in (up, sunk)]
    ear = [_mask(s, ["ear"]) for s in (up, sunk)]
    iou = lambda a, b: (a & b).sum() / (a | b).sum()  # noqa: E731
    assert iou(ear[0], ear[1]) < iou(whole[0], whole[1]) - 0.2, (iou(ear[0], ear[1]), iou(whole[0], whole[1]))


def test_press_lifts_a_buried_piece_and_keeps_the_join():
    s = _spec((0.09, 0.0, 0.62), tip_at=(0.06, -0.06, 0.55))
    press = {"elements": ["ear", "tip"], "mm": 3, "join": [0.09, 0.0, 0.6]}
    st = FV.evaluate(F.freeze(s), None, [], 128, press)
    assert st.buried_mm > 25, st.buried_mm  # the tip is buried ~32 mm, away from the join
    res = FV.fit(s, [{"label": "whole", "camera": CAM, "mask": _mask(s), "box": BOX}], groups=("offset",),
                 only=["tip"], press=press, iterations=10)
    assert res.after["buried_mm"] < 1.5, res.log
    # a piece buried AT the join is the join: not lifted
    deep_root = _spec((0.09, 0.0, 0.58))
    assert FV.evaluate(F.freeze(deep_root), None, [], 128, {"elements": ["ear"], "mm": 3,
                                                           "join": [0.09, 0.0, 0.58]}).buried_mm == 0.0
