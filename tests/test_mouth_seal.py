"""A sealed mouth (base.head.lip_seal) with a mouth interior (base.head.interior: teeth, tongue) shows nothing of the
inside from the front: the slit and the bag (subtracts) are held behind the fused lips when sealed, and the meshed lips have no hole
at the scene's voxel (a front z-buffer over the lips: no cell whose front-most surface sinks 3 mm past its row's)."""
import json
import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spikes", "facesliders"))

from hifipushie import assets, base, humans, spec as specmod, store  # noqa: E402

NAME = "_test_mouth_seal"


def _ok():
    try:
        assets.path("gnm", base.GNM)
        return True
    except Exception:
        return False


def _model():
    sp = humans.spec(age=45, sex=1.0, seed=None, skin=False, source="human")
    sp["base"]["head"]["lip_seal"] = 1.0
    sp["base"]["head"]["interior"] = {"teeth": {"show": 0.0035}, "tongue": True, "slit": 0.0003}
    d = store.HOME / NAME
    d.mkdir(exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp))
    return sp


def test_sealed_interior_held_behind_the_lips():
    """The slit's front end sits behind the lips' front (it started in front of them)."""
    if not _ok():
        return
    _model()
    blobs = specmod.expand_mirror(store.load(NAME)).get("blobs") or {}
    slit = [v for k, v in blobs.items() if k.endswith("_mouth_slit")]
    assert slit and max(np.atleast_1d(slit[0]["values"]["n1"])) <= -base.SEALED_BACK + 1e-9, slit
    assert [k for k in blobs if "teeth" in k], list(blobs)


def test_sealed_mouth_has_no_hole_from_the_front():
    if not _ok():
        return
    _model()
    try:
        import sealmesh
        holes, n = sealmesh.holes(NAME, 1.3)
        assert holes == 0, (holes, n)
    finally:
        shutil.rmtree(store.HOME / NAME, ignore_errors=True)
