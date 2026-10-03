"""cloth_check: seam lengths, ease bands, notch alignment. Run: uv run python tests/test_cloth_check.py"""
from hifipushie import cloth, cloth_check


def _design(cap_w, notch_x):
    """A 'sleeve' rectangle sewn round a 'body' rectangle's top edge: cap_w wide vs 0.5 m of armhole."""
    g = {"pieces": {
        "body": {"rect": [0.5, 0.4], "wrap": {"to": "torso"}, "marks": {"top-notch": [0.0, 0.2]}},
        "sleeve": {"rect": [cap_w, 0.3], "wrap": {"to": "arm.L"}, "marks": {"top-notch": [notch_x, 0.15]}}},
        "seams": [["sleeve:nw>n>ne", "body:nw>n>ne"]]}
    return cloth.pieces(g, {})


def test_cap_bands():
    B = _design(0.52, 0.0)  # +4% ease
    shirt, coat = cloth_check.seams(B, "shirt")[0], cloth_check.seams(B, "overcoat")[0]
    assert shirt["kind"] == "cap_shirt" and not shirt["ok"], shirt
    assert coat["kind"] == "cap_coat" and coat["ok"], coat
    assert abs(coat["ease"] - 0.04) < 1e-6


def test_notch_mismatch():
    assert not cloth_check.seams(_design(0.52, 0.0), "overcoat")[0]["notches_off"]
    off = cloth_check.seams(_design(0.52, 0.03), "overcoat")[0]["notches_off"]  # the sleeve's top notch 3 cm forward
    assert off and off[0][2] > 20, off


if __name__ == "__main__":
    test_cap_bands()
    test_notch_mismatch()
    print("ok")
