"""The garment reading checklist (cloth_checklist.json) and cloth_reference's camera, readings and measures, on
synthetic bodies and garments. No sim, no Blender.
uv run python tests/test_cloth_reference.py"""
import json

import numpy as np

from hifipushie import cloth_reference as cr, garment_design


class FakeBody:
    """A standing figure's landmarks without a mesh build: Body.at / Body.J / V / T as cloth.Body has them."""

    def __init__(self):
        self.J = {"neck": np.array([0, -0.01, 1.55]), "elbow.L": np.array([0.30, 0, 1.21]),
                  "wrist.L": np.array([0.43, -0.02, 0.98]), "knee.L": np.array([0.14, -0.03, 0.54]),
                  "knee.R": np.array([-0.14, -0.03, 0.54]), "ankle.L": np.array([0.16, -0.01, 0.07]),
                  "ankle.R": np.array([-0.16, -0.01, 0.07]), "lm_chin": np.array([0, -0.09, 1.62])}
        self.at = {"shoulder.L": np.array([0.22, 0, 1.48]), "cf_neck": np.array([0, -0.11, 1.55]), "armpit_z": 1.36,
                   "chest_z": 1.34, "waist_z": 1.13, "hips_z": 0.97, "seat_z": 0.92, "crotch_z": 0.88}
        # a box torso: front face at y = -0.12 (the chest's front)
        z = np.linspace(0.0, 1.84, 40)
        self.V = np.array([[x, y, zz] for zz in z for x in (-0.15, 0.15) for y in (-0.12, 0.10)], float)
        self.T = np.array([[0, 1, 2]])


def _tube(cx, cy, r, z0, z1, n=24, m=30):
    """A vertical tube (a sleeve, a leg, a torso): vertices and triangles."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    zs = np.linspace(z0, z1, m)
    V = np.array([[cx + r * np.cos(t), cy + r * np.sin(t), z] for z in zs for t in a])
    F = []
    for i in range(m - 1):
        for j in range(n):
            p, q = i * n + j, i * n + (j + 1) % n
            F += [[p, q, p + n], [q, q + n, p + n]]
    return V, np.array(F)


def _ctx(results, spec=None):
    return cr.Ctx("test", spec or {"cloth": {}}, results, body=FakeBody())


def test_checklist_is_complete_and_resolvable():
    ck = cr.checklist()
    kb = garment_design.kb()
    need = {"id", "stage", "kinds", "what", "view", "type", "measure", "tolerance", "sets"}
    ids = set()
    for it in ck["items"]:
        assert need <= set(it), (it["id"], need - set(it))
        assert it["id"] not in ids
        ids.add(it["id"])
        assert it["stage"] in (1, 2, 3, 4, 5) and str(it["stage"]) in ck["stages"]
        assert it["kinds"] == ["*"] or all(k in kb["kinds"] for k in it["kinds"]), it["id"]
        if it.get("detail"):
            assert it["detail"] in kb["details"], it["id"]
        if it["type"] == "length":
            assert it.get("anchor") or it.get("target_mm") or len(it.get("points", [])) == 2, it["id"]
        m = it["measure"]
        assert m.startswith("missing") or m in cr.MEASURES, (it["id"], m)
        for nm in (it.get("region") or {}).get("around", []) + (it.get("anchor") or []):
            assert nm.split(".")[0] in ("head_top", "chin", "neck_base", "shoulder", "armpit", "chest", "waist", "hip",
                                        "seat", "crotch", "knee", "ankle", "floor", "elbow", "wrist"), (it["id"], nm)
    # big to small: every kind's list starts with silhouette / lengths
    assert cr.items_for("jacket")[0]["stage"] == 1 and cr.items_for("jacket")[-1]["stage"] == 5


def test_every_hand_correction_is_an_item():
    """The corrections the user made by hand on Garrett's suit (2026-10) must each be a checklist item."""
    ids = {it["id"] for it in cr.checklist()["items"]}
    for want in ("buttons_done", "front_state", "placket", "collar_show", "collar_hug", "collar_state", "belt",
                 "knee_width", "leg_opening", "sleeve_end", "cuff_show", "front_hang"):
        assert want in ids, want


def test_camera_recovers_a_similarity_and_round_trips():
    L = cr.landmarks(FakeBody())
    s, th, t = 860.0, np.radians(3.0), np.array([620.0, -1720.0])
    Rm = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    pts = {}
    for k in ("head_top", "chin", "knee.L", "knee.R", "ankle.L", "floor", "wrist.L"):
        x, z = L[k][0], L[k][2]
        y = s * Rm @ np.array([x, z]) + t
        pts[k] = [y[0], -y[1]]
    cam = cr.fit_camera(pts, L, (1248, 1824))
    assert abs(cam["s"] - s) < 1e-6 * s and max(cam["residual_px"].values()) < 1e-6
    uv = cr.project(cam, L["knee.L"])
    xz = cr.unproject(cam, uv)[0]
    assert np.allclose(xz, [L["knee.L"][0], L["knee.L"][2]], atol=1e-9)


def test_anchored_reading_carries_onto_our_body():
    """A hem read at t along waist -> knee in a picture lands at the same fraction on our body: the miss is in mm on
    OUR body, whatever the picture's scale."""
    body = FakeBody()
    c = _ctx({})
    L = c.L
    it = next(i for i in cr.checklist()["items"] if i["id"] == "body_length")
    view = {"points": {"waist": [600, 700], "knee.L": [700, 1300], "hem_cf": [640, 940]}}
    ref = cr.reading(it, {"points": {"hem_cf": [640, 940]}}, [view])
    assert abs(ref["t"] - 0.4) < 1e-6
    hit = L["waist"] + 0.4 * (L["knee.L"] - L["waist"])
    row = cr.compare(it, ref, {"point": hit}, c)
    assert abs(row["miss"]) < 1e-6
    lower = hit + np.array([0.05, 0, -0.03])  # 3 cm lower (and aside): a body level is read in height only
    row = cr.compare(it, ref, {"point": lower}, c)
    assert abs(row["miss"] - 30.0) < 1e-6 and row["severity"] > 1


def test_widths_and_hems_on_a_synthetic_suit():
    """Widths are front-view extents at the item's height; a jacket hem, a sleeve end and a trouser leg read where
    they were built."""
    Vj, Fj = _tube(0.0, 0.0, 0.2, 0.75, 1.45)
    Vs, Fs = _tube(0.37, -0.01, 0.06, 1.0, 1.3)
    V = np.r_[Vj, Vs]
    F = np.r_[Fj, Fs + len(Vj)]
    piece = np.r_[np.zeros(len(Vj), int), np.ones(len(Vs), int)]
    jacket = {"V": V, "F": F, "piece": piece, "names": ["front.L", "sleeve.L"]}
    Vt, Ft = _tube(0.14, -0.03, 0.08, 0.08, 0.9)
    trousers = {"V": Vt, "F": Ft, "piece": np.zeros(len(Vt), int), "names": ["front.L"]}
    c = _ctx({"jacket": jacket, "trousers": trousers})
    assert abs(cr.m_chest_width(c, "jacket")["width_m"] - 0.4) < 0.01  # the sleeve isn't the chest
    assert abs(cr.m_hem_cf(c, "jacket")["point"][2] - 0.75) < 1e-9
    assert abs(cr.m_knee_width(c, "trousers")["width_m"] - 0.16) < 0.01
    hem = cr.m_trouser_hem(c, "trousers")["point"]
    assert abs(hem[2] - 0.08) < 1e-9 and hem[1] < c.L["ankle.L"][1]
    # the hem 8 cm forward of the chest's front reads as a tent
    assert abs(cr.m_front_hang(c, "jacket")["mm"] - (-0.12 + 0.2) * 1000) < 2


def test_crinkle_flat_vs_folded():
    V, F = _tube(0, 0, 0.2, 0, 1, n=64, m=20)
    flat_ish = cr.crinkle_deg(V, F)
    rng = np.random.default_rng(0)
    rough = cr.crinkle_deg(V + rng.normal(0, 0.006, V.shape), F)
    assert flat_ish < 4 < rough


def test_choices_counts_and_rules():
    c = _ctx({})
    items = {i["id"]: i for i in cr.checklist()["items"]}
    row = cr.compare(items["collar"], {"value": "notched_lapel", "visible": True}, {"value": "shawl"}, c)
    assert row["severity"] == cr.CHOICE_MISS and row["miss"] == 1
    row = cr.compare(items["buttons_done"], {"value": 0, "visible": True, "confidence": "high"}, {"value": 2}, c)
    assert row["severity"] > 1
    # not visible in the picture, but a tailoring rule judges it (a tent)
    row = cr.compare(items["front_hang"], {"visible": False}, {"mm": 60.0}, c)
    assert row["source"] == "rule" and row["miss"] == 50.0 and row["severity"] > 1
    try:
        cr.reading(items["collar"], {"value": "a nice collar"}, [{}])
    except ValueError:
        pass
    else:
        raise AssertionError("a choice outside the KB accepted")
    assert cr.reading(items["vent"], "not visible", [{}])["visible"] is False


def test_belt_hidden_by_an_untucked_shirt():
    """A belt chosen on the trousers reads as visible only when nothing hangs over the waistband at the centre front."""
    Vt, Ft = _tube(0.0, 0.0, 0.17, 0.6, 1.02)
    names = ["front.L", "waistband"]
    piece = (Vt[:, 2] > 0.99).astype(int)
    trousers = {"V": Vt, "F": Ft, "piece": piece, "names": names}
    Vs, Fs = _tube(0.0, 0.0, 0.19, 0.85, 1.45)
    shirt = {"V": Vs, "F": Fs, "piece": np.zeros(len(Vs), int), "names": ["front.L"]}
    spec = {"cloth": {"trousers": {"design": {"kind": "suit_trousers", "fit": "tailored"}}, "shirt": {}}}
    c = _ctx({"trousers": trousers, "shirt": shirt}, spec)
    r = cr.m_has_belt(c, "trousers")
    assert r["value"] is False and "shirt" in r["note"]
    spec["cloth"]["trousers"]["over"] = "shirt"  # tucked
    c = _ctx({"trousers": trousers, "shirt": shirt}, spec)
    assert cr.m_has_belt(c, "trousers")["value"] is True
    assert cr.m_tucked(c, "shirt")["value"] is True


def test_sheet_patch_from_readings():
    items = {i["id"]: i for i in cr.checklist()["items"]}
    tg = {"collar": {"visible": True, "value": "notched_lapel", "_item": items["collar"]},
          "front_state": {"visible": True, "value": "open", "_item": items["front_state"]},
          "placket": {"visible": True, "value": "box", "_item": items["placket"]},
          "colour": {"visible": True, "value": [58, 56, 54], "_item": items["colour"]}}
    p = cr._sheet_patch("jacket", "jacket", tg)
    assert p["design"]["details"]["collar"] == "notched_lapel" and p["color"] == "#3a3836"
    assert p["closures"] == [{"name": "front", "state": "open", "finish": {"over": "box"}}]
    json.dumps(p)


def test_reference_brief_covers_the_checklist():
    """Every item of the outfit's kinds is served by at least one shot; the wear state comes from a reading."""
    garments = {"jacket": "jacket", "shirt": "shirt", "trousers": "suit_trousers"}
    refs = {"targets": {"jacket": {"front_state": {"visible": True, "value": "open"},
                                   "button_count": {"visible": True, "value": 2},
                                   "buttons_done": {"visible": True, "value": 0}},
                        "shirt": {"tucked": {"visible": True, "value": True},
                                  "collar_state": {"visible": True, "value": "open"}},
                        "trousers": {"belt": {"visible": True, "value": True}}}}
    b = cr.reference_brief(garments, refs=refs)
    served = {i for s in b["shots"] for i in s["purpose"]}
    for kind in garments.values():
        for it in cr.items_for(kind):
            assert it["id"] in served, it["id"]
    ids = [s["id"] for s in b["shots"]]
    for want in ("front", "side", "back", "three", "collar", "closure", "cuff", "raking"):
        assert want in ids, want
    p = b["common"]["prompt"]
    assert "all 2 front buttons undone" in p and "tucked into the trousers" in p and "belt" in p and "A-pose" in p
    assert all(b["common"]["prompt"] in s["prompt"] for s in b["shots"])  # same figure, same clothes, every shot
    assert next(s for s in b["shots"] if s["id"] == "raking")["light"] == "raking"


def test_check_references_says_why():
    garments = {"jacket": "jacket"}
    front = {"yaw": 0, "framing": "full", "light": "even", "perspective": "ortho-ish", "posed": "a-pose", "size": [1200, 1800]}
    painting = {"yaw": -40, "framing": "bust", "light": "warm", "perspective": "perspective", "posed": "other"}
    r = cr.check_references([front, painting], garments)
    uns = {u["id"]: u for u in r["unsupported"]}
    assert "collar_show" in uns and "back" in uns["collar_show"]["shot"]
    assert "fold_character" in uns and "raking" in uns["fold_character"]["why"]
    assert "body_length" not in uns
    # the painting alone gives no numbers
    r = cr.check_references([painting], garments)
    uns = {u["id"]: u for u in r["unsupported"]}
    assert "body_length" in uns and "camera" in uns["body_length"]["why"] or "needs" in uns["body_length"]["why"]
    # a full set: front, side, back, 3/4, close-ups and a raking pass support everything
    full = [dict(front, yaw=y) for y in (0, 90, 180, 45)] + [
        {"yaw": 0, "framing": f"close:{r_}", "light": "even"} for r_ in ("neck_base", "chest", "wrist", "hip", "floor")] + [
        {"yaw": 180, "framing": "close:crotch", "light": "even"}, dict(front, light="raking")]
    assert not cr.check_references(full, garments)["unsupported"]


def test_guide_topic():
    from hifipushie import server
    assert "points-of-measure" in server.guide("cloth_reference") or "POM" in server.guide("cloth_reference")


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
