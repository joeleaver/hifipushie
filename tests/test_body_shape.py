"""New humans' head defaults (no lid stare, no sex term on eyes / cheeks) and the fit-solvable body proportions
(MakeHuman's measure modifiers: hips, waist, shoulders, chest; and the cup size)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hifipushie import humanfit, humans, makehuman  # noqa: E402


def _mh_ok():
    try:
        makehuman._target("measure-hips-circ-incr.target", "measure")
        return True
    except Exception:
        return False


def test_one_mesh_humans_rest_with_neutral_lids():
    """source="human": no opened-lid expression or lid pose by default (they made every one-mesh human stare);
    given ones are kept. Eyes and cheeks get no women's term (the same seed reads the same for both sexes)."""
    for sex in (0.0, 1.0):
        hd = humans.spec(age=35, sex=sex, seed=7, skin=False, source="human")["base"]["head"]
        assert "expression" not in hd and not {"lid_upper", "lid_lower"} & set(hd.get("pose") or {})
    f0 = humans.spec(age=35, sex=0.0, seed=7, skin=False, source="human")["base"]["head"]["features"]
    f1 = humans.spec(age=35, sex=1.0, seed=7, skin=False, source="human")["base"]["head"]["features"]
    assert f0["eyes"] == f1["eyes"] and f0["cheeks"] == f1["cheeks"]
    given = humans.spec(age=35, sex=0.0, seed=7, skin=False, source="human", head={"pose": {"lid_upper": -0.002}})
    assert given["base"]["head"]["pose"]["lid_upper"] == -0.002


def test_measure_modifiers_shape_the_body():
    if not _mh_ok():
        return
    b = {"sex": 0.0, "age": 30, "weight": 0.5}
    P0 = makehuman.body(b)["P"]
    for k in makehuman.MEASURES:
        Pm, Pp = makehuman.body({**b, k: 0.0})["P"], makehuman.body({**b, k: 1.0})["P"]
        assert np.abs(Pp - P0).max() > 0.003 and np.abs(Pm - P0).max() > 0.003, k
    assert np.array_equal(makehuman.body({**b, "hips": 0.5})["P"], P0)  # 0.5 = none


def test_hips_fit_without_weight():
    """A slim woman's hips narrowed by the solve: the hips modifier takes it, weight hardly moves."""
    if not _mh_ok():
        return
    sp = humans.spec(age=30, sex=0.0, seed=3, skin=False, source="human")
    st = humanfit.state(sp["base"])
    hb = st["measures"]["hip_breadth"]
    nb, rep = humanfit.solve(sp["base"], {"hip_breadth": "-2"}, free=("body",))
    m1 = humanfit.state(nb)["measures"]
    assert abs(m1["hip_breadth"] - (hb - 2.0)) < 0.6, (hb, m1["hip_breadth"], nb["body"])
    assert nb["body"].get("hips", 0.5) < 0.5
    assert abs(float(nb["body"].get("weight", 0.5)) - float(sp["base"]["body"].get("weight", 0.5))) < 0.05
