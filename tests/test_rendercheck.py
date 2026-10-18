"""render.missing_texture_fraction / magenta_tiles: a render set with Blender's missing-texture magenta must fail before
review (garrett_g10, 2026-10-16: 7 of 9 lit tiles magenta, job exit 0, no error in the log)."""
import os, subprocess, sys, tempfile
import numpy as np
from PIL import Image
from hifipushie import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _img(rgb, n=64):
    return Image.fromarray(np.full((n, n, 3), rgb, np.uint8))


def test_magenta_fraction():
    assert render.missing_texture_fraction(_img((255, 0, 255))) == 1.0
    assert render.missing_texture_fraction(_img((190, 40, 170))) == 1.0      # lit / tone-mapped magenta
    for skin in ((224, 172, 150), (120, 70, 60), (200, 110, 120), (150, 60, 90), (60, 50, 140), (240, 240, 240), (5, 0, 5)):
        assert render.missing_texture_fraction(_img(skin)) == 0.0, skin   # skin, lips, a deep lip, blue, white, black


def test_magenta_tiles_fail_the_set():
    with tempfile.TemporaryDirectory() as d:
        a = np.full((64, 64, 3), (220, 170, 150), np.uint8)
        Image.fromarray(a).save(f"{d}/face_v0.png")
        a[:40] = (255, 0, 255)                                               # 62 % magenta
        Image.fromarray(a).save(f"{d}/mouth_v0.png")
        Image.fromarray(np.full((64, 64, 3), (255, 0, 255), np.uint8)).save(f"{d}/mouth_v0_ref.png")   # refs skipped
        assert list(render.magenta_tiles([f"{d}/face_v0.png", f"{d}/mouth_v0.png", f"{d}/mouth_v0_ref.png"])) == [f"{d}/mouth_v0.png"]
        cli = [sys.executable, os.path.join(ROOT, "spikes/projskin/rendercheck.py"), d]
        r = subprocess.run(cli, capture_output=True, text=True)
        assert r.returncode == 1 and os.path.exists(f"{d}/ERROR"), r.stdout + r.stderr
        os.remove(f"{d}/mouth_v0.png")
        r = subprocess.run(cli, capture_output=True, text=True)
        assert r.returncode == 0 and not os.path.exists(f"{d}/ERROR"), r.stdout + r.stderr


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
