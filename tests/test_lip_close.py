"""base.head.lip_close (gnmdetail2): GNM's own lower-face expression closes the rest mouth corner to corner (in place of
the seal's membrane), and the one mesh then gives the field the closed seam (the crossed inner rolls left out, the
first row drawn in: onemesh.CLOSED_SEAL_V), so a closed mouth reads as one line, not a wall with a pale band."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hifipushie import assets, base, blockin_lips as bl, humans, onemesh  # noqa: E402


def _ok():
    try:
        assets.path("gnm", base.GNM)
        return True
    except Exception:
        return False


def _base(**hd):
    sp = humans.spec(age=30, sex=0.0, seed=None, skin=False, source="human")
    h = sp["base"]["head"]
    h.pop("lip_seal", None)
    h.update(hd)
    return sp["base"]


def test_lip_close_closes_gnm_neutral():
    if not _ok():
        return
    open_ = bl.contact_gaps(onemesh.head_template(_base()), None, 1.0)
    shut = bl.contact_gaps(onemesh.head_template(_base(lip_close=True)), None, 1.0)
    assert open_.max() > 1.0, open_            # GNM's neutral is parted
    assert shut.max() < 0.6 and shut.min() > -0.6, shut


def test_closed_mouth_field_gets_the_seam():
    if not _ok():
        return
    tpl = onemesh.template(_base(lip_close=True))
    sf = tpl.get("seal_field")
    assert sf is not None and list(sf.get("v") or []) == list(onemesh.CLOSED_SEAL_V), sf and sf.get("v")
    assert len(sf["drop"]) > 0 and len(sf["outer"]) >= 1
    assert onemesh.template(_base()).get("seal_field") is None   # a parted mouth: none
