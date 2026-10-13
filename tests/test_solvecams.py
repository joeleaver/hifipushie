"""solvecams (2026-10-12): the joint solve's cameras and read weights; what the benchmark found on the way.
Needs the gnm / makehuman packs (skipped without them).
uv run python -m pytest -q tests/test_solvecams.py"""
import copy

import numpy as np
import pytest

from hifipushie import assets, base as basemod, blockin as bi, humans
from hifipushie.spec import empty_spec


def _have():
    try:
        assets.path("gnm", "gnm/shape/data/versions/v3_0/gnm_head.npz")
        from hifipushie import makehuman
        makehuman.body({"age": 25, "sex": 0.5})
        return True
    except Exception as err:  # the packs aren't in the repo
        print("skipped:", str(err)[:80])
        return False


need = pytest.mark.skipif(not _have(), reason="gnm / makehuman packs not present")


@need
def test_template_joints_follow_the_head():
    """The one mesh's injected joints are the HEAD's too: a second identity (or a native attach) of the same body in
    the same process must get its own head / landmark joints, whatever was evaluated first."""
    sp = {**empty_spec(), **humans.spec(age=35, sex=1.0, source="human")}
    a = copy.deepcopy(sp["base"])
    a["head"]["attach"] = "native"
    b = copy.deepcopy(a)
    sp_b = {"base": b}
    bi.set_identity(sp_b, bi.identity({"base": a}) + 0.8 * np.random.default_rng(3).standard_normal(170))
    c = copy.deepcopy(a)
    c["head"].pop("attach")
    basemod._CACHE.clear()
    ja = basemod.template_joints(a)
    jb = basemod.template_joints(b)
    jc = basemod.template_joints(c)
    assert ja != jb
    assert ja["head"]["pos"] != jc["head"]["pos"]
    basemod._CACHE.clear()              # the other order gives the same joints
    assert basemod.template_joints(c) == jc and basemod.template_joints(b) == jb and basemod.template_joints(a) == ja


def test_camera_distance_is_a_freedom_that_keeps_the_picture_scale():
    """cam_moved(dist=): the camera further away with the lens to match: the head's centre stays where it is in the
    picture and as large; points nearer / further than the centre move (perspective). _cam_columns has its column."""
    from hifipushie import face_ruler as fr, humanfit
    cam = {"r": [0.02, 0.0, 0.01], "t": [0.01, -0.02, 0.8], "f": 2700.0, "size": [1152, 1536], "centre": [0.0, -0.13, 1.58], "yaw": -40.0}
    far = fr.cam_moved(cam, dist=30.0)
    assert abs(far["t"][2] / cam["t"][2] - np.exp(0.3)) < 1e-9 and abs(far["f"] / cam["f"] - np.exp(0.3)) < 1e-9
    X = np.array([cam["centre"], [0.07, -0.05, 1.5], [0.0, -0.2, 1.6]])
    a, b = humanfit.project(cam, X), humanfit.project(far, X)
    assert np.allclose(a[0], b[0], atol=1e-6)                 # the centre: unmoved
    assert np.abs(a[1:] - b[1:]).max() > 2.0                  # depth off the centre: perspective changes
    obs = [{"type": "landmark", "view": "3q", "name": f"lm{i}.{ax}", "o": 0.0, "J": np.zeros(170), "sig": 1.0, "p": list(map(float, a[i])), "X": list(map(float, X[i]))}
           for i in range(3) for ax in "xy"]
    C, pri = fr._cam_columns(obs, [{"kind": "3q", "cam": cam}], fr.PHOTO_CAM_SD7)
    assert C.shape == (6, 7) and len(pri) == 7 and np.abs(C[:2, 6]).max() < 1e-6 and np.abs(C[2:, 6]).max() > 0.01
    assert fr.PHOTO_CAM_SD7["front"][5] >= 5.0                # the front camera's pitch is free under a prior (not +-2 with a clip)


def test_dense_reads_are_no_surer_than_their_measured_error():
    from hifipushie import face_ruler as fr
    assert "ears" not in fr.DENSE_REGIONS and "scalp_neck" not in fr.DENSE_REGIONS
    assert fr.DENSE_REGION_SIG["profile"]["lids"] > 4 * fr.DENSE_REGION_SIG["front"]["lids"]     # a true profile's lids: 4 mm against 0.7
    assert fr.DENSE is False
