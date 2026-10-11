"""The GNM driving manual (gnm_driving_guide.md, parsed by gnm_manual): every control it names is a real block-in move,
and the phrases the driving test taught it land on the right control."""
import pytest

from hifipushie import gnm_controls as gcm, gnm_manual as gm

pytestmark = pytest.mark.skipif(not gcm.DATA.exists(), reason="gnm_controls.npz not built")


def test_entries_parse_and_name_real_moves():
    from hifipushie import blockin as bi
    es = gm.entries()
    assert len(es) >= 40
    seen = set()
    for e in es:
        assert e["see"] and e["use"] and e["section"]
        for m in e["moves"]:
            for part in m.replace(" + ", ",").split(","):
                p = part.strip().split(" ")[0]
                if p and p not in seen:
                    seen.add(p)
                    bi.direction(p)    # raises on an unknown move
    assert {"pc:upper_lip_region0", "head_size", "pc:nose_region0", "under_chin!"} <= seen
    assert len(gm.alike()) >= 6


@pytest.mark.parametrize("phrase,control", [
    ("the mouth stands forward in profile", "pc:upper_lip_region0"),
    ("muzzle forward", "pc:upper_lip_region0"),
    ("pupils further apart", "mm:pupils_apart"),
    ("double chin", "under_chin!"),
    ("the whole nose stands further out", "pc:nose_region0"),
    ("eyes bulge, prominent", "eye_depth"),
    ("upper lip longer, mouth lower under the nose", "philtrum!"),
    ("ears stick out", "ear_out!"),
    ("eyes and brows sit lower over the nose", "nose_length!"),
    ("a halo: our outline a rim outside all round", "head_size"),
])
def test_phrases_find_their_control(phrase, control):
    r = gm.suggest(phrase, top=1)
    assert r["entries"] and control in r["entries"][0]["moves"], (phrase, r["entries"][:1])


def test_mm_moves_move_their_measure_alone():
    """mm:<measure> moves that measure 1 mm and holds the others (in mm) and the face's place."""
    import numpy as np
    from hifipushie import blockin as bi, gnm_mm
    sp = gnm_mm._space()
    r0 = gnm_mm.readers(sp["T"])
    for n in ("pupils_apart", "chin_forward", "forehead_forward", "philtrum_length", "tip_forward"):
        d = bi.direction("mm:" + n)
        r = gnm_mm.readers(sp["T"] + np.tensordot(d * 2.0, sp["IB"], 1))
        assert abs((r[n] - r0[n]) - 2.0) < 0.15, n
        others = [abs(r[k] - r0[k]) for k in gnm_mm.HELD if k != n]
        assert max(others) < 0.3, (n, max(others))
        assert np.linalg.norm(d) < 1.5, n


def test_step_reply_carries_the_manual():
    """block_in_step's report text has the manual's entries for its `seen` (no model needed: step_text on a report)."""
    from hifipushie import blockin as bi
    rep = {"entry": {"to": "x", "round": 1, "from": "w", "c_norm": 1.0, "read": {}, "coupled": [], "passes": {},
                     "camera_moves": []},
           "c0": 1.0, "big": [], "delta": [], "before": {}, "manual": gm.suggest("the muzzle stands forward", top=1)}
    assert "pc:upper_lip_region0" in bi.step_text(rep)
