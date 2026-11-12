"""block_in_start called the way its own example shows (the area re-review, 2026-11-12; C436).

The tool's example and check_references' next line give views as {"image", "yaw", "lens_mm"}: the camera fit read
v["size"] and ended in a bare KeyError after the detector had run; a start without `sex` filled in 0.5 and built the
male class mean without a word."""
from pathlib import Path

import pytest
from PIL import Image

from hifipushie import blockin_models, humanfit_map


def _picture(tmp_path, name="front.png", size=(64, 48)) -> str:
    p = tmp_path / name
    Image.new("RGB", size, (128, 128, 128)).save(p)
    return str(p)


def test_a_views_size_is_read_from_its_picture(tmp_path):
    img = _picture(tmp_path)
    views = [{"image": img, "yaw": 0}, {"image": img, "yaw": 45, "size": [640, 480]}, {"yaw": 90, "points": {"chin": [1, 2]}}]
    out = blockin_models.with_sizes(views)
    assert out[0]["size"] == [64, 48] and out[0]["yaw"] == 0   # (w, h, as humanfit_map unpacks it)
    assert out[1]["size"] == [640, 480]                          # a given size stands
    assert "size" not in out[2] and "size" not in views[0]       # no picture: left alone; the caller's list untouched


class _Reached(Exception):
    pass


def test_the_sex_is_asked_for_before_anything_runs(tmp_path, monkeypatch):
    def reached(views):
        raise _Reached(views)
    monkeypatch.setattr(blockin_models, "with_anchor_points", reached)
    views = [{"image": _picture(tmp_path), "yaw": 0}]
    with pytest.raises(ValueError, match="say the sex"):
        blockin_models.start("no_such_model_for_this_test", views)
    with pytest.raises(ValueError, match="say the sex"):
        blockin_models.start("no_such_model_for_this_test", views, body={"weight": 0.5})
    # said either way, the start goes on, and the views reach the detector step WITH their sizes
    for kw in ({"sex": "female"}, {"sex": 0.0}, {"body": {"sex": "male"}}):
        with pytest.raises(_Reached) as e:
            blockin_models.start("no_such_model_for_this_test", views, **kw)
        assert e.value.args[0][0]["size"] == [64, 48], kw


def test_the_profile_refusal_names_the_points_to_click():
    src = Path(humanfit_map.__file__).read_text()
    assert '", ".join(CLICK_SIGMAS["profile"])' in src and "at least nose_bridge, nose_tip, nose_base and chin" in src
    assert {"nose_bridge", "nose_tip", "nose_base", "chin"} <= set(humanfit_map.CLICK_SIGMAS["profile"])
