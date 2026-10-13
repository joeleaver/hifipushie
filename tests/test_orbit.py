"""The orbit (eye depth) as measured, driveable quantities; the limbus in turned views; the camera's yaw; the whole-lid
solve and the eyeball guard (orbit, 2026-10-11).  uv run python -m pytest -q tests/test_orbit.py"""
import numpy as np
import pytest

from hifipushie import assets, store

try:
    assets.pack("gnm")
    HAVE = True
except Exception:  # noqa: BLE001
    HAVE = False
pytestmark = pytest.mark.skipif(not HAVE, reason="GNM asset pack not installed")
REF = "fs_ge3"
need_ref = pytest.mark.skipif(not (store.HOME / REF / "human_refs.json").exists(), reason=f"workspace model {REF} not present")


def test_rings_and_orbit_sets():
    from hifipushie import lidrings
    t = lidrings.topo()
    assert len(t["loops"][0]) == 41 and all(k in t["loops"] for k in range(-3, 15))
    m = lidrings.mirror()
    ids = np.concatenate([t["loops"][k] for k in range(0, 15)])
    assert (m[m[ids]] == ids).all() and not set(m[ids]) & set(ids)      # the right eye's rings: the left's, mirrored
    s = lidrings.sets()
    assert all(len(v) >= 4 for v in s.values()), {k: len(v) for k, v in s.items()}
    assert not set(s["brow_ridge"]) & set(s["sulcus"])


def test_orbit_moves_move_their_measure_alone():
    """Every orbit move: its measure 1 mm, the 26 others, the lid's seat on the ball, the opening, the corners and the
    profile line held."""
    from hifipushie import gnm_mm
    sp = gnm_mm._space()
    r0 = gnm_mm.readers(sp["T"])
    assert set(gnm_mm.ORBIT) <= set(gnm_mm.NAMES) and len(gnm_mm.NAMES) == 27
    for n in gnm_mm.ORBIT:
        d = gnm_mm.direction("mm:" + n)
        r = gnm_mm.readers(sp["T"] + np.tensordot(d * 2.0, sp["IB"], 1))
        assert abs((r[n] - r0[n]) - 2.0) < 0.1, n
        assert max(abs(r[k] - r0[k]) for k in gnm_mm.HELD if k != n) < 0.1, n
        assert np.linalg.norm(d) < 2.0, (n, np.linalg.norm(d))


def test_eyes_forward_is_the_eye_unit_not_the_nasion():
    """mm:eyes_forward: the ball AND its lids come forward together inside rims, bridge and muzzle that stay (the old
    move pushed nasion + forehead back a third of it and carried the whole mid-face with the eye)."""
    from hifipushie import gnm_mm
    sp = gnm_mm._space()
    gr, S, L = sp["gr"], sp["sets"], sp["WL"]
    D = np.tensordot(gnm_mm.direction("mm:eyes_forward"), sp["IB"], 1) * 1000.0       # mm per mm
    ref = D[S["cranium"], 2].mean()
    z = lambda ids: float(D[ids, 2].mean() - ref)                                      # noqa: E731
    eye = 0.5 * (z(gr["left_eye"]) + z(gr["right_eye"]))
    assert 0.9 < eye < 1.1
    o = sp["orb"]
    for k in ("margin_up", "margin_lo", "platform"):
        assert abs(z(o[k]) - eye) < 0.05, k                  # the lids ride on the ball
    for k in ("brow_ridge", "side_rim", "under_eye"):
        assert abs(z(o[k])) < 0.1, k                         # the rims stay
    Lz = L @ D[:, 2] - ref
    assert np.abs(Lz[[27, 28, 29, 30, 33, 51, 57]]).max() < 0.1          # nasion, dorsum, tip, nose base, lips
    assert abs(z(S["forehead"])) < 0.1 and abs(z(S["pog"])) < 0.1
    mid = gr["skin_exterior"] & gr["hockey_mask"] & (np.abs(sp["T"][:, 0]) < 0.004)
    assert np.sqrt(np.mean((D[mid, 2] - ref) ** 2)) < 0.15              # the profile line a side picture fixed


def test_orbit_as_seen_is_the_measures_combined():
    from hifipushie import gnm_mm
    sp = gnm_mm._space()
    c = np.random.default_rng(2).normal(size=170) * 0.7
    Va, Vb = sp["T"], sp["T"] + np.tensordot(c, sp["IB"], 1)
    ra, rb, oa, ob = gnm_mm.readers(Va), gnm_mm.readers(Vb), gnm_mm.orbit(Va), gnm_mm.orbit(Vb)
    for row, comb in gnm_mm.ORBIT_SEEN.items():
        assert abs((ob[row] - oa[row]) - sum(w * (rb[k] - ra[k]) for k, w in comb.items())) < 1e-6, row
    assert 5 < oa["apex_behind_nasion"] < 12 and 10 < oa["apex_ahead_of_side_rim"] < 22


def _views(c, kinds, **kw):
    from hifipushie import face_ruler as fr
    B = fr.gnm_head(c)
    return [{"img": fr.clay(B, fr.camera(k)), "cam": fr.camera(k), "kind": k, "style": "clay", **kw} for k in kinds]


def test_limbus_read_in_turned_views():
    """The limbus of a known head read in a 3/4 and a profile clay picture: the read shift = the true shift."""
    from hifipushie import face_ruler as fr, gnm_mm
    cA = 0.5 * np.random.default_rng(4).normal(size=170)
    cB = cA + 3.0 * gnm_mm.direction("mm:eyes_forward") + 2.0 * gnm_mm.direction("mm:pupils_apart")
    A, B = fr.gnm_head(cA), fr.gnm_head(cB)
    n = 0
    for k in ("3q", "profile"):
        cam = fr.camera(k)
        lum = fr._lum(fr.clay(B, cam))
        la, lb = fr.limbus_model(A), fr.limbus_model(B)
        for j in (0, 1):
            rd = fr.limbus_read(lum, cam, la[j])
            if rd is None or (k == "profile" and rd["open"] < 0.0):
                continue
            tru = fr._cam_points(cam, lb[j]["X"][None])[1][0] - fr._cam_points(cam, la[j]["X"][None])[1][0]
            if rd["sharp"] <= 0 or rd["score"] < fr.LIMBUS_MIN:
                continue
            err = (rd["d"] - tru) * rd["mmpx"]
            if k == "3q" and rd["open"] > 0.75:
                assert abs(err[0]) < 0.6, (k, j, err)
                n += 1
    assert n >= 1


def test_ruler_reads_eye_depth_and_orbit_rows():
    """Front + 3/4 + profile clay of a head whose eye unit sits 3 mm further forward: the ruler reads it (camera
    known), the orbit rows come with errors, and a front picture alone does not read it."""
    from hifipushie import face_ruler as fr, gnm_mm
    cA = 0.5 * np.random.default_rng(4).normal(size=170)
    cB = cA + 3.0 * gnm_mm.direction("mm:eyes_forward") - 2.0 * gnm_mm.direction("mm:brow_ridge_forward")
    res = fr.read(fr.gnm_head(cA), _views(cB, ("front", "3q", "profile")))
    got = {r["measure"]: r for r in res["gaps"]}
    assert abs(got["eyes_forward"]["gap"] - 3.0) < 1.0, got["eyes_forward"]
    orb = {r["row"]: r for r in res["orbit"]}
    assert set(orb) == set(gnm_mm.ORBIT_SEEN)
    assert abs(orb["apex_behind_nasion"]["gap"] + got["eyes_forward"]["gap"]) < 1e-6
    assert orb["apex_behind_nasion"]["gap"] < -1.5 and orb["apex_behind_nasion"]["err"] > 0
    assert "ORBIT" in fr.orbit_text(res["orbit"])
    one = fr.read(fr.gnm_head(cA), _views(cB, ("front",), hair=True))
    o1 = {r["row"]: r for r in one["orbit"]}
    assert o1["apex_behind_nasion"]["err"] > 2 * orb["apex_behind_nasion"]["err"]      # depth is not in a front view


def test_camera_yaw_is_a_freedom_with_its_error():
    """A profile camera turned 4 deg: with yaw left free the solve gives the turn back (sign and about the size) and the
    eye depth's error is larger than with the camera known."""
    from hifipushie import face_ruler as fr, gnm_mm
    cA = 0.5 * np.random.default_rng(4).normal(size=170)
    cB = cA + 3.0 * gnm_mm.direction("mm:eyes_forward")
    views = _views(cB, ("front", "3q", "profile"))
    known = fr.read(fr.gnm_head(cA), [dict(v) for v in views])
    views[2]["cam"] = fr.cam_moved(views[2]["cam"], yaw=4.0)
    assert abs(fr.cam_moved(fr.camera("front"), yaw=3.0)["yaw"] - 3.0) < 1e-9
    sd6 = {"front": (0.5, 0.5, 0.5, 0.3, 1.0, 1.0), "3q": (0.5, 0.5, 0.5, 0.3, 1.0, 1.0), "profile": (0.5, 0.5, 0.5, 0.3, 6.0, 1.0)}
    free = fr.read(fr.gnm_head(cA), views, rounds=4, cam_sd=sd6)
    assert len(free["cam_done"][2]) == 6
    assert -7.0 < free["cam_done"][2][4] < -1.5, free["cam_done"][2]          # turned back
    e0 = {r["measure"]: r["err"] for r in known["gaps"]}["eyes_forward"]
    e1 = {r["measure"]: r["err"] for r in free["gaps"]}["eyes_forward"]
    assert e1 > e0
    g = {r["measure"]: r["gap"] for r in free["gaps"]}["eyes_forward"]
    assert abs(g - 3.0) < 2.0, g


def test_whole_lid_solve_on_gnm():
    """blockin_lid.solve from GNM's template (a wedge: no platform, a 14 deg turn) toward donor s376: the platform comes
    onto the ball and the turn sharpens, the margins and the mm measures stay; `clear` lifts the designed platform."""
    from hifipushie import blockin_lid as bl
    c0 = np.zeros(170)
    s = bl.solve(c0, bl.donor("s376"))
    a, b = bl.mean_structure(c0), bl.mean_structure(s["c"])
    assert b["platform_s"] < a["platform_s"] - 0.5 and b["tuck"] > a["tuck"] + 4, (a, b)
    assert s["margins"] < 0.2 and s["mm"] < 0.6 and s["miss"] < s["miss0"] and s["dc"] < 12, s
    s2 = bl.solve(c0, bl.donor("s376"), clear=0.6)
    assert bl.mean_structure(s2["c"])["platform_s"] > b["platform_s"] + 0.2
    with pytest.raises(ValueError):
        bl.donor("no_such_donor_model")


@need_ref
def test_eyeball_guard_reads_the_shipped_head():
    """ball_clearance on a shipped head. With OUR ball (base.head.eye_radius: seated by a search) the six lid landmarks
    clear it by the seat's 0.8 mm; without the key the head has GNM's OWN ball at GNM's centre (the default since
    gnmnative, 2026-10-12: no seat), which GNM's lid margins touch (0 +- 0.5 mm); the lid's skin by a number per ring;
    a ball pushed forward 1.5 mm comes through (less clearance)."""
    import copy
    from hifipushie import blockin_lid as bl, onemesh
    b0 = store.load(REF)["base"]
    b1 = copy.deepcopy(b0)
    b1["head"]["eye_radius"] = 0.012
    ours = bl.ball_clearance(onemesh.head_template(b1))
    assert abs(ours["landmarks"] - 0.8) < 0.15, ours
    b0["head"].pop("eye_radius", None)
    ht = onemesh.head_template(b0)
    b = bl.ball_clearance(ht)
    assert abs(b["landmarks"]) < 0.5 and set(b["rings"]) == set(range(1, 8)), b
    ht2 = copy.copy(ht)
    ht2["eyes"] = [np.asarray(c, float) + 0.0015 * np.asarray(ht["forward"], float) for c in ht["eyes"]]
    assert bl.ball_clearance(ht2)["min"] < b["min"] - 0.5


def test_eye_step_report_recommends_no_paint():
    """Decision 2026-10-11: nothing recommends a painted fold line, crease make-up or liner; the step is identity only
    by default and says when the orbit is unread."""
    import inspect
    from hifipushie import blockin_eyes as be, eye_ruler as er
    assert inspect.signature(be.solve).parameters["ne"].default == 0
    assert inspect.signature(be.eye_step).parameters["expression"].default is False
    e = {"evidence": {"up": 0.6, "lo": 0.9, "tps": 4.0, "dark": 0.2}, "read0": {"up": 0.7, "lo": 0.9, "show": 3.0, "lsoft": 0.5, "hsoft": 4.0},
         "read": {"up": 0.6, "lo": 0.9, "show": 3.5, "lsoft": 0.6, "hsoft": 4.2}, "dc": 3.0, "e": 0.0, "crease": None, "identity_only": True,
         "orbit": {"state": "unread", "text": "ORBIT: UNREAD: ..."}, "lid": None}
    txt = be.text(e)
    assert "identity only" in txt and "ORBIT: UNREAD" in txt
    for bad in ("eyeshadow", "skin.eyes.crease", "eyeliner"):
        assert bad not in txt, bad
        assert bad not in inspect.getsource(er.compare), bad
