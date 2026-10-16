"""body_check: ANSUR II percentiles and the girth regression (skips without the ANSUR II CSVs)."""
import numpy as np
import pytest

from hifipushie import body_check as bc

pytestmark = pytest.mark.skipif(not (bc.ANSUR_DIR / "ANSUR_II_FEMALE_Public.csv").exists(), reason="no ANSUR II data")


def test_percentiles_flags():
    t = bc.table(0)
    med = {k: float(np.median(t[c])) for k, c in bc.MAP.items()}
    pc = bc.percentiles(med, 0)
    assert all(40 < v["pct"] < 60 and not v["flag"] for v in pc.values())
    low = dict(med, calf=276.0)  # (dt_tess before the fix: under the smallest ANSUR II woman, 282)
    pc = bc.percentiles(low, 0)
    assert pc["calf"]["flag"] == "under p1" and pc["calf"]["pct"] == 0.0
    assert bc.percentiles(dict(med, calf=600.0), 0)["calf"]["flag"] == "over p99"


def test_predict_recovers_medians():
    t = bc.table(0)
    known = {k: float(np.mean(t[bc.MAP[k]])) for k in ("height", "seat", "upperLeg")}
    r = bc.predict(known, ["calf"], 0)["calf"]
    assert abs(r["mm"] - float(np.mean(t["calfcircumference"]))) < 1.0  # (OLS passes through the means)
    assert 10 < r["resid_sd"] < 30 and 0.4 < r["r2"] < 0.9


def test_sex_of():
    assert bc.sex_of({"base": {"body": {"sex": 0.0}}}) == 0
    assert bc.sex_of({"base": {"template": "male_stylized"}}) == 1
    assert bc.sex_of({"base": {}}) is None


def test_ages_filter():
    t = bc.table(0)
    m = bc.ages(0, 18, 30)
    assert 1000 < m.sum() < len(m)
    med = float(np.median(t["calfcircumference"][m]))
    assert 45 < bc.percentile_of(med, "calfcircumference", 0, (18, 30)) < 55


def _mh(sex):
    try:
        from hifipushie import cloth
        return cloth.body_mesh(params={"sex": float(sex), "age": 25})
    except Exception as e:  # (no MakeHuman pack)
        pytest.skip(f"no MakeHuman body: {e}")


def test_landmark_girths_on_makehuman_default_woman():
    """Calibration (2026-10-15): MakeHuman's default young woman (macros at 0.5). Readings then, mm: tailor -> ANSUR
    landmark: waist 683 -> 719 (omphalion), thigh 516 -> 556 (square to the thigh at the crotch), seat 946 -> 905
    (buttock protrusion level), chest 845 -> 838 (bust point), biceps 285 -> 299 (x FLEX); BMI 19.2 (48 kg)."""
    b = _mh(0)
    mm = bc.girths(b["V"], b["F"], b["J"], sex=0)
    H = float(np.ptp(np.asarray(b["V"])[:, 2]))
    z0 = float(np.asarray(b["V"])[:, 2].min())
    assert abs((mm["waist_z"] - z0) / H - bc.ratio("waistheightomphalion", 0)) < 1e-3
    assert mm["waist"] > mm["tailor_waist"] + 15  # the omphalion sits under the natural waist
    assert mm["upperLeg"] > 1.05 * mm["tailor_upperLeg"]  # the level tape 5 cm down read ~7% low
    assert mm["seat_z"] > z0 + 0.48 * H  # (the largest level section had slid down onto the thigh tops)
    assert abs(mm["biceps"] - bc.FLEX * mm["tailor_biceps"]) < 0.2
    pc = bc.percentiles(mm, 0, (18, 30))
    assert all(3 < pc[k]["pct"] < 60 for k in ("waist", "seat", "upperLeg", "calf", "biceps", "chest")), pc
    w = bc.bmi(b["V"], b["F"])
    assert 17 < w["bmi"] < 22


def test_shoulder_items_read_against_ansur():
    """biacromial breadth and shoulder length (coordinator 2026-10-15): ANSUR II women's medians read near p50, and a
    313 mm breadth (Tess as saved) reads under p5."""
    t = bc.table(0)
    med = {k: float(np.median(t[bc.MAP[k]])) for k in ("biacromial", "shoulderLength")}
    pc = bc.percentiles(med, 0)
    assert all(40 < pc[k]["pct"] < 60 for k in med), pc
    assert bc.percentiles({"biacromial": 313.0}, 0)["biacromial"]["pct"] < 5
    print("ok shoulders", {k: round(v) for k, v in med.items()})


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
