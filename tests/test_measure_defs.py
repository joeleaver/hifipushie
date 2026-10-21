"""Known-answer tests for the tape's definitions and the per-consumer adapters (measure audit, docs/notes/measurements.md).

A synthetic mannequin whose every pinned measurement has an analytic answer: elliptic torso sections (Ramanujan's
perimeter), a round neck of known girth, a shoulder whose top slopes at a known angle, arms hung clear (A pose), two
round legs (a crotch at a known level), a round head (a known stature). tailor.measure must return each definition;
measure_defs must hand each consumer ITS definition (Simon the chord slope and the iliac-crest hips)."""
from __future__ import annotations

import math
import pathlib
import re

import numpy as np
import pytest
from skimage import measure as skm

from hifipushie import measure_defs as md, tailor

VOX = 0.005
SLOPE = 18.0  # deg: the shoulder's top
NECK_R = 0.06
Z_CROTCH, Z_SEAT_TOP, Z_WAIST_LO, Z_WAIST_HI, Z_BUST_LO, Z_BUST_HI, Z_UPPER, Z_SLAB = (
    0.80, 0.92, 1.04, 1.10, 1.22, 1.28, 1.32, 1.40)
SEAT, WAIST, BUST, UPPER = (0.18, 0.13), (0.14, 0.10), (0.17, 0.13), (0.17, 0.11)
HEAD_C, HEAD_R = 1.72, 0.10
J = {"pelvis": [0, 0, 0.98], "chest": [0, 0, 1.13], "neck": [0, 0, 1.48], "head": [0, 0, HEAD_C],
     "shoulder.L": [0.19, 0, 1.39], "elbow.L": [0.30, 0, 1.10], "wrist.L": [0.38, 0, 0.86],
     "hip.L": [0.09, 0, 0.88], "knee.L": [0.09, 0, 0.45], "ankle.L": [0.09, 0, 0.08]}


def ellipse_perimeter(a, b):
    h = ((a - b) / (a + b)) ** 2
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def torso_axes(z):
    """The torso's section semi-axes (x, y) at height z: seat, taper, waist, taper, bust, taper, upper chest."""
    knots = [(Z_CROTCH - 0.02, SEAT), (Z_SEAT_TOP, SEAT), (Z_WAIST_LO, WAIST), (Z_WAIST_HI, WAIST), (Z_BUST_LO, BUST),
             (Z_BUST_HI, BUST), (Z_UPPER, UPPER), (Z_SLAB + 0.06, UPPER)]
    zs = [k[0] for k in knots]
    return float(np.interp(z, zs, [k[1][0] for k in knots])), float(np.interp(z, zs, [k[1][1] for k in knots]))


def z_top(x):
    return 1.47 - math.tan(math.radians(SLOPE)) * (abs(x) - NECK_R)


def _capsule(P, a, b, r):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(P - (a + t[..., None] * ab), axis=-1) - r


@pytest.fixture(scope="module")
def tape():
    xs, ys, zs = np.arange(-0.46, 0.46, VOX), np.arange(-0.17, 0.17, VOX), np.arange(-0.01, 1.84, VOX)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    P = np.stack([X, Y, Z], -1)
    za = np.clip(Z, Z_CROTCH - 0.02, Z_SLAB + 0.06)
    A = np.interp(za, *zip(*[(k, v[0]) for k, v in [(Z_CROTCH - 0.02, SEAT), (Z_SEAT_TOP, SEAT), (Z_WAIST_LO, WAIST),
                                                       (Z_WAIST_HI, WAIST), (Z_BUST_LO, BUST), (Z_BUST_HI, BUST),
                                                       (Z_UPPER, UPPER), (Z_SLAB + 0.06, UPPER)]]))
    B = np.interp(za, *zip(*[(k, v[1]) for k, v in [(Z_CROTCH - 0.02, SEAT), (Z_SEAT_TOP, SEAT), (Z_WAIST_LO, WAIST),
                                                       (Z_WAIST_HI, WAIST), (Z_BUST_LO, BUST), (Z_BUST_HI, BUST),
                                                       (Z_UPPER, UPPER), (Z_SLAB + 0.06, UPPER)]]))
    torso = np.maximum((np.sqrt((X / A) ** 2 + (Y / B) ** 2) - 1) * 0.1, np.maximum(Z_CROTCH - Z, Z - (Z_SLAB + 0.02)))
    zt = 1.47 - math.tan(math.radians(SLOPE)) * (np.abs(X) - NECK_R)
    slab = np.maximum.reduce([np.abs(X) - 0.21, np.abs(Y) - 0.10, Z_SLAB - Z, Z - zt])
    neck = np.maximum(np.hypot(X, Y) - NECK_R, np.maximum(1.40 - Z, Z - HEAD_C))
    head = np.linalg.norm(P - [0, 0, HEAD_C], axis=-1) - HEAD_R
    f = np.minimum.reduce([torso, slab, neck, head])
    for s in (1, -1):
        sh, el, wr = ([s * v[0], v[1], v[2]] for v in (J["shoulder.L"], J["elbow.L"], J["wrist.L"]))
        f = np.minimum.reduce([f, _capsule(P, [s * 0.20, 0, 1.375], el, 0.04), _capsule(P, el, wr, 0.032)])
        f = np.minimum(f, np.maximum(np.hypot(X - s * 0.09, Y) - 0.075, np.maximum(-Z, Z - Z_CROTCH - 0.01)))
    V, F, _, _ = skm.marching_cubes(f, 0.0, spacing=(VOX,) * 3)
    V = V + [xs[0], ys[0], zs[0]]
    return tailor.measure(V, F[:, ::-1], {k: np.asarray(v, float) for k, v in J.items()})


def test_girths_are_the_sections_they_are_defined_on(tape):
    mm = tape["mm"]
    assert abs(mm["neck"] - 2000 * math.pi * NECK_R) < 0.015 * mm["neck"]  # square to the neck, 2 cm up it
    assert abs(mm["chest"] - 1000 * ellipse_perimeter(*BUST)) < 8  # the fullest 2-12 cm under the armpit
    zw = J["pelvis"][2] + 0.7 * (J["chest"][2] - J["pelvis"][2])  # skeletal waist
    assert abs(tape["at"]["waist_z"] - zw) < 1e-6 and abs(mm["waist"] - 1000 * ellipse_perimeter(*torso_axes(zw))) < 8
    assert abs(mm["hips"] - 1000 * ellipse_perimeter(*SEAT)) < 8  # hip joint + 2 cm: in the seat's band here


def test_high_bust_is_the_armpit_level_not_the_chest(tape):
    """FreeSewing highBust: round the chest just under the arms, above the bust (it was = chest: no bust dart ever)."""
    mm = tape["mm"]
    assert abs(mm["highBustUnder"] - 1000 * ellipse_perimeter(*UPPER)) < 8
    assert mm["chest"] - mm["highBustUnder"] > 40
    assert mm["highBust"] == mm["chest"]  # (the tape's legacy key)
    for c in ("block:bodice", "freesewing:simon"):
        assert md.for_consumer(c, mm, tape["at"])[0]["highBust"] == mm["highBustUnder"]


def test_iliac_crest_level_and_girth(tape):
    """highHip at crotch + ILIAC_CREST_OVER_CROTCH x stature (ANSUR II iliocristale), waistToHighHip down to it."""
    mm, at = tape["mm"], tape["at"]
    stature = HEAD_C + HEAD_R - 0.0
    assert abs(mm["height"] / 1000 - stature) < 0.01
    zc = at["crotch_z"]
    assert abs(zc - Z_CROTCH) < 0.01
    zi = zc + tailor.ILIAC_CREST_OVER_CROTCH * mm["height"] / 1000
    assert abs(at["high_hip_z"] - zi) < 0.002
    assert abs(mm["waistToHighHip"] - 1000 * (at["waist_z"] - zi)) < 1.0
    assert abs(mm["highHip"] - 1000 * ellipse_perimeter(*torso_axes(zi))) < 8


def test_shoulder_line_and_chord(tape):
    """The tape's line fit is the top's own slope; the chord is hps -> shoulder point (what Brian's beam reads)."""
    at = tape["at"]
    assert abs(at["shoulder_slope_line"] - SLOPE) < 1.5
    hps, sp = np.asarray(at["hps.L"]), np.asarray(at["shoulder.L"])
    assert abs(hps[0] - NECK_R) < 0.004  # the neck loop's widest point (HP_HPS "widest")
    chord = math.degrees(math.atan2(hps[2] - sp[2], sp[0] - hps[0]))
    assert abs(at["shoulder_slope_chord"] - chord) < 1e-6
    # the shoulder point near the shoulder's end (x 0.19-0.23), its height on the top: the analytic chord there
    assert 0.185 < sp[0] < 0.235 and abs(sp[2] - z_top(sp[0])) < 0.01
    assert at["shoulder_slope_chord"] > at["shoulder_slope_line"] + 5  # the two definitions are not interchangeable


def test_each_consumer_receives_its_definition(tape):
    mm, at = tape["mm"], tape["at"]
    for c in ("freesewing:simon", "freesewing:jaeger", "freesewing:carlton", "block:bodice", "block:knit"):
        m2, info = md.for_consumer(c, mm, at)
        assert m2["shoulderSlope"] == pytest.approx(at["shoulder_slope_chord"]), c
        assert m2["hips"] == pytest.approx(mm["highHip"]) and m2["waistToHips"] == pytest.approx(mm["waistToHighHip"]), c
        assert set(info["definitions"]) >= {"shoulderSlope", "hips", "waistToHips", "highBust"}
    # the trouser block reads (hips, waistToHips) only as a pair: the tape's own, unchanged
    m2, info = md.for_consumer("block:trouser", mm, at)
    assert m2["hips"] == mm["hips"] and not info
    # a declared hold keeps the legacy value and is reported
    m2, info = md.for_consumer("freesewing:simon", mm, at, {"hips": "refit pending", "waistToHips": "refit pending"})
    assert m2["hips"] == mm["hips"] and set(info["held"]) == {"hips", "waistToHips"}
    assert m2["shoulderSlope"] == pytest.approx(at["shoulder_slope_chord"])
    with pytest.raises(md.DefinitionError, match="declare"):
        md.for_consumer("freesewing:teagan", mm, at)


def test_gate_row_states_holds_and_refuses_undeclared(tape):
    mm = tape["mm"]
    assert md.gate_row("freesewing:simon", mm)["status"] == "PASS"
    r = md.gate_row("block:bodice", mm, {"shoulderSlope": "jacket r26"})
    assert r["status"] == "INFO" and "HELD" in r["why"] and "shoulderSlope" in r["held"]
    assert md.gate_row("freesewing:teagan", mm)["status"] == "FAIL"


def test_simon_draft_gets_the_chord_through_the_garment_path():
    """cloth.slope_measures (draft_measures' boundary) on a Simon garment: the chord, and the shirt kind's hips hold."""
    from hifipushie import cloth

    class B:
        m = {"mm": {}, "at": {"shoulder_slope_line": 10.92, "shoulder_slope_chord": 22.51}}
    tape_mm = {"shoulderSlope": 10.92, "hips": 942.8, "waistToHips": 151.7, "highHip": 805.0, "waistToHighHip": 23.4}
    mm, info = cloth.slope_measures(dict(tape_mm), B(), {"pattern": {"from": "simon"}})
    assert mm["shoulderSlope"] == pytest.approx(22.51) and info["consumer"] == "freesewing:simon"
    # a Simon garment is the shirt kind, which holds hips (Garrett's shirt in flight): unchanged until refitted
    assert mm["hips"] == 942.8 and set(info["held"]) == {"hips", "waistToHips"}  # (no highBust in this tape)
    # the shirt kind (Garrett's shirt in flight) holds hips: unchanged until refitted
    kkb = cloth._kb()["kinds"]["shirt"]
    assert set(md.holds_for({}, kkb)) >= {"hips", "waistToHips"}
    assert "shoulderSlope" in md.holds_for({}, cloth._kb()["kinds"]["jacket"])


def _fs_reads(design):
    from hifipushie import assets
    try:
        P = assets.pack("freesewing") / "node_modules" / "@freesewing"
    except Exception:
        pytest.skip("no FreeSewing pack")
    chain = {"simon": ["brian"], "jaeger": ["bent", "brian"], "carlton": ["bent", "brian"]}[design]
    reads = set()
    for d in [design] + chain:
        for f in (P / d / "src").rglob("*.mjs"):
            reads |= set(re.findall(r"measurements\??\.([a-zA-Z]+)", f.read_text()))
    return reads


@pytest.mark.parametrize("design", ["simon", "jaeger", "carlton"])
def test_every_freesewing_read_is_declared(design):
    """The draft refuses a measurement with no declared definition: every measurements.<x> the design's source reads
    (with the designs it extends) has a row for that consumer."""
    assert md.check_reads(f"freesewing:{design}", _fs_reads(design)) == []


def test_every_block_read_is_declared():
    src = (pathlib.Path(tailor.__file__).with_name("pattern_blocks.py")).read_text()
    fns = {"bodice": ("def bodice", "def _cap"), "trouser": ("def leg_cut", "\ndef ", )}
    body = src[src.index("def bodice"):src.index("def _cap")] + src[src.index("def front_balance"):src.index("def bodice")]
    reads = set(re.findall(r'(?:mm\(|m\[|m\.get\()"([a-zA-Z]+)"', body))
    assert md.check_reads("block:bodice", reads) == []
    tr = src[src.index("def leg_cut"):]
    tr = tr[:tr.index("\ndef trouser")] + src[src.index("def trouser"):].split("\ndef ", 1)[0]
    assert md.check_reads("block:trouser", set(re.findall(r'(?:mm\(|m\[|m\.get\()"([a-zA-Z]+)"', tr))) == []


@pytest.mark.xfail(strict=True, reason="AMBIGUOUS, not adapted (measure audit): FreeSewing's waist is the narrowest "
                   "section below the ribs; the tape's is skeletal (70 % pelvis -> chest joint, so a belly doesn't move "
                   "it): Garrett's narrowest is 15 mm above ours (783.8 vs 788.8), Tess's 50 mm (649.6 vs 686.6). Moving "
                   "the waist moves every hps -> waist length: a coordinator / Joe call")
def test_freesewing_waist_is_the_narrowest_section(tape):
    m2, _ = md.for_consumer("freesewing:simon", tape["mm"], tape["at"])
    assert md.CONSUMERS["freesewing:simon"]["waist"][0] == md.M
