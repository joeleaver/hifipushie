"""readmix (2026-10-13): MediaPipe's mesh as absolute reads through the learned correspondence (mpread), the one-sided
skin | hair edge read, the known-lens distance prior, the per-picture expression prior. The model tests need the GNM
pack and the workspace block-in tn_T00 (skipped without them).
uv run python -m pytest -q tests/test_readmix.py"""
import json

import numpy as np
import pytest

from hifipushie import assets, face_ruler as fr, mpread, store

try:
    assets.pack("gnm")
    HAVE = True
except Exception:  # noqa: BLE001
    HAVE = False
REF = "tn_T00"
need_ref = pytest.mark.skipif(not HAVE or not (store.HOME / REF / "human_refs.json").exists(), reason=f"GNM pack / workspace model {REF} not present")


def test_the_stored_correspondence():
    t = mpread.table()
    pts = t["points"]
    assert t["provenance"]["samples"] > 2000 and len(pts) >= 440                 # every point but the irises
    ids = {p["mp"] for p in pts}
    assert not ids & set(range(468, 478))
    for p in pts:
        assert len(p["tri"]) == 3 and abs(sum(p["w"]) - 1) < 1e-3 and min(p["w"]) >= -1e-6
    # the features the brief names are there, and a lip point sits on GNM's lips, an alar point on its nose
    by = {p["mp"]: p for p in pts}
    assert by[61]["feature"] == by[291]["feature"] == "commissures"
    assert by[0]["feature"] == "vermilion border" and by[13]["feature"] == "lip seam"
    assert by[129]["feature"] == "alar / nostril base" and by[129]["region"] == "nose"
    assert by[33]["feature"] == "eye contour" and by[152]["feature"] == "face oval"
    # left / right: MediaPipe's 291 is the subject's LEFT mouth corner (world +X), 61 the right
    assert by[291]["x"] > 0.015 and by[61]["x"] < -0.015 and abs(by[0]["x"]) < 0.003
    # near the front the learned points are tight where it matters (synthetic scatter, per axis mm)
    for m in (61, 291, 0, 17, 13, 14, 33, 263, 133, 362):
        assert max(by[m]["bins"]["-15:15"]["sd"]) < 1.9, (m, by[m]["bins"]["-15:15"])
    assert t["neff"]["inner"]["neff"] < 40                                        # its points err together


def test_the_mix_reads_no_oval_and_nothing_past_its_turn():
    assert mpread.sigma("face oval", 0.0) is None and mpread.sigma("brow line", 0.0) is None
    assert mpread.sigma("alar / nostril base", 0.0) is None                   # biased wide on photographs: not read
    for f in ("vermilion border", "lip seam", "commissures", "eye contour"):
        assert mpread.sigma(f, 5.0) is not None and 0.3 <= mpread.sigma(f, 5.0) <= 2.0, f
        assert mpread.sigma(f, 80.0) is None
    assert mpread.sigma("vermilion border", 5.0, {"vermilion border": (9.0, None, None)}) == 9.0
    assert mpread.sigma("vermilion border", 20.0, {"vermilion border": (9.0, None, None)}) is None


@pytest.fixture(scope="module")
def tess():
    from hifipushie import blockin as bi
    spec = store.load(REF)
    return spec, fr.model_head(spec), bi._refs(REF)


@need_ref
def test_mp_obs_reads_a_known_change_and_nothing_on_the_head_itself(tess):
    spec, head, rj = tess
    cam = rj["cameras"][0]
    view = {"cam": cam, "kind": "front"}
    assert mpread.obs(head, view, None) == []
    obs0 = mpread.obs(head, view, np.zeros((478, 2)))
    assert len(obs0) > 100 and {ob["type"] for ob in obs0} == {"mp"}
    feats = {ob["feature"] for ob in obs0}
    assert "face oval" not in feats and "alar / nostril base" not in feats and {"vermilion border", "commissures", "eye contour"} <= feats
    # the detector's reading made up as the model's own surface points (+ each point's learned bias): nothing to read
    yaw = mpread.cam_yaw(cam)
    by = {p["mp"]: p for p in mpread.table()["points"]}

    def reading(h):
        P = np.zeros((478, 2))
        for ob in mpread.obs(h, view, np.zeros((478, 2))):
            if ob["name"].endswith(".x"):
                P[ob["mp"]] = np.asarray(ob["p"]) + (mpread.bias(by[ob["mp"]], yaw)[0] / ob["mm1"] if mpread.BIAS else 0.0)
        return P
    obs = mpread.obs(head, view, reading(head))
    assert max(abs(ob["o"]) for ob in obs) < 1e-6
    # a known identity change: the reading of the changed head against J dc
    r = np.random.default_rng(5).standard_normal(170)
    dc = 3.0 * r / np.linalg.norm(r)
    obs = mpread.obs(head, view, reading(head["rebuild"](head["c"] + dc)))
    o = np.array([ob["o"] for ob in obs])
    pr = np.array([ob["J"][:170] for ob in obs]) @ dc
    assert np.corrcoef(o, pr)[0, 1] > 0.9
    assert np.sqrt(np.mean((o - pr) ** 2)) < 0.45 * np.sqrt(np.mean(o ** 2))
    # the effective N: many correlated points count as NEFF reads
    s1 = min(ob["sig"] for ob in mpread.obs(head, view, reading(head), neff=0))
    s2 = min(ob["sig"] for ob in mpread.obs(head, view, reading(head), neff=10))
    assert s2 > 1.5 * s1
    # a profile is not read
    side = next((c for c in rj["cameras"] if c and abs(fr.view_yaw(c)) > 60), None)
    if side is not None:
        assert mpread.obs(head, {"cam": side, "kind": "profile"}, np.zeros((478, 2))) == []


@need_ref
def test_hair_edge_is_one_sided(tess):
    spec, head, rj = tess
    cam = rj["cameras"][0]
    _, ps = fr.clay(head, cam, passes=True)
    fig = ps["part"] >= 0
    from scipy import ndimage as ndi
    H, W = fig.shape
    yy, xx = np.mgrid[:H, :W]
    _, q = fr._cam_points(cam, np.asarray(head["L"], float)[:68])
    cx = float(q[27:36, 0].mean())
    mmpx = float(cam["t"][2] / cam["f"] * 1000.0)
    # the picture: hair down both sides. Its skin is the model's figure, WIDER by 3 mm on the picture's right (the model is too
    # narrow there), NARROWER by 4 mm on the left (hair in front of the cheek); hair beyond, on both sides
    grow = ndi.binary_dilation(fig, iterations=int(round(3.0 / mmpx)))
    shrink = ndi.binary_erosion(fig, iterations=int(round(4.0 / mmpx)))
    skin = np.where(xx > cx, grow, shrink)
    hair = ndi.binary_dilation(fig, iterations=int(round(25.0 / mmpx))) & ~skin
    view = {"cam": cam, "kind": "front", "hair_edge": {"skin": skin, "hair": hair}}
    obs = fr._hair_edge_obs(head, view, fig)
    assert len(obs) >= 10 and {ob["type"] for ob in obs} == {"hairedge"}
    assert all(ob["p"][0] > cx for ob in obs)                      # only where the skin shows OUTSIDE the model
    o = np.array([ob["o"] for ob in obs])
    assert 2.0 < np.median(o) < 4.0 and (o >= fr.HAIR_EDGE_MIN).all()
    # skin against BACKGROUND (no hair beside it) is not this read's business
    assert fr._hair_edge_obs(head, {**view, "hair_edge": {"skin": skin, "hair": np.zeros_like(hair)}}, fig) == []
    # and a profile takes none (observe)
    assert not fr._hair_edge_obs(head, {"cam": cam, "kind": "front"}, fig)


def test_known_lens(tmp_path):
    from PIL import Image
    p = tmp_path / "a.png"
    Image.new("RGB", (40, 60)).save(p)
    assert fr.lens_known({"image": str(p)}) is None
    assert fr.lens_known({"image": str(p), "lens_mm": 24}) == 24.0
    ex = Image.Exif()
    ex.get_ifd(0x8769)[41989] = 26
    Image.new("RGB", (40, 60)).save(tmp_path / "b.jpg", exif=ex)
    assert fr.lens_known({"image": str(tmp_path / "b.jpg")}) == 26.0
    assert fr.PHOTO_CAM_DIST_LENS <= 10.0 < fr.PHOTO_CAM_DIST_DENSE


def test_expression_prior_pins_a_neutral_picture():
    # two reads of one expression column: under the default prior the column takes the residual; pinned, the identity must
    K = 3
    Jm = np.zeros((1, K))
    head = {"Jm": np.zeros((23, K)), "measures": {}, "c": np.zeros(K), "expr": {"names": ["happy"]}}
    from hifipushie import gnm_mm
    head["Jm"] = np.zeros((len(gnm_mm.NAMES), K))
    head["measures"] = {n: 0.0 for n in gnm_mm.NAMES}
    obs = [{"type": "lip", "view": "front", "name": f"l{i}", "o": 1.0, "J": np.array([0.2, 0.0, 0.0, 1.0]), "sig": 0.3} for i in range(6)]
    a = fr.solve(obs, head)
    b = fr.solve(obs, head, expr_prior={"front": {"happy": (0.0, 0.01)}})
    c = fr.solve(obs, head, expr_prior={"front": {"happy": (0.9, 0.05)}})
    assert a["expr"]["front"]["happy"][0] > 0.5 and abs(b["expr"]["front"]["happy"][0]) < 0.05
    assert abs(c["expr"]["front"]["happy"][0] - 0.9) < 0.1
    assert b["dc"][0] > 3 * abs(a["dc"][0]) and abs(c["dc"][0]) < 0.6 * b["dc"][0]
