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
