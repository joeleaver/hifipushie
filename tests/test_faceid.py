"""faceid: cosine / five-point mapping always; with the asset pack and a face photo in the workspace, a lightly altered
copy scores as the same face and another person does not. Run: uv run python tests/test_faceid.py"""
import numpy as np

from hifipushie import faceid, store


def test_cosine_and_lm5():
    a = np.array([1.0, 0.0, 1.0])
    assert abs(faceid.cosine(a, a) - 1) < 1e-9 and abs(faceid.cosine(a, -a) + 1) < 1e-9
    P = np.zeros((478, 2))
    P[468], P[473], P[1], P[61], P[291] = (10, 20), (50, 20), (30, 40), (15, 60), (45, 60)
    assert faceid.lm5_from_mediapipe(P) == [[10, 20], [50, 20], [30, 40], [15, 60], [45, 60]]


def test_same_face_scores_high():
    from PIL import Image, ImageFilter
    d = store.HOME / "skin_refs"
    a, b = d / "ref_01_light_man_stubble.jpg", d / "ref_03_dark_man.jpg"
    if not (faceid.available() and a.exists() and b.exists()):
        print("skip: no faceid pack / skin_refs photos")
        return
    im = Image.open(a).convert("RGB")
    im = im.resize((1000, int(1000 * im.size[1] / im.size[0])))
    other = Image.open(b).convert("RGB")
    s_same, s_other = faceid.scores(im, [im.filter(ImageFilter.GaussianBlur(2)), other])
    for m in faceid.MODELS:
        assert s_same[m] > 0.8, (m, s_same)
        assert s_other[m] < 0.3, (m, s_other)


if __name__ == "__main__":
    test_cosine_and_lm5()
    test_same_face_scores_high()
    print("ok")
