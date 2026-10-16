"""Per-view lighting in ONE Blender (2026-10-16): a render job's views may each carry their own "lighting"
(blender_scene._light_rig rebuilds the rig between frames), so a job of several photo-lit views pays the scene load,
groom build and shader compile once instead of per view. Run: uv run python tests/test_view_lighting.py"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hifipushie import scene  # noqa: E402

L1 = {"lights": [{"dir": [-0.6, -0.6, 0.5], "energy": 4.0, "color": [1.0, 0.6, 0.4], "angle": 5}],
      "world": {"color": [0.2, 0.3, 0.6], "strength": 0.3}, "view": "Standard", "exposure": 0.0}
L2 = {"lights": [{"dir": [0.7, -0.3, 0.6], "energy": 2.5, "color": [0.5, 0.7, 1.0], "angle": 20},
                 {"dir": [0.0, -1.0, 0.1], "energy": 0.4, "angle": 40, "shadow": False}],
      "world": {"color": [0.9, 0.85, 0.7], "strength": 0.8}, "view": "Khronos PBR Neutral", "exposure": -0.5}


def _cube(path):
    v = np.array([[x, y, z] for x in (-.3, .3) for y in (-.3, .3) for z in (-.3, .3)], np.float32)
    f = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                  [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], np.int32)
    np.savez(path, verts=v, faces=f, colors=np.full((8, 4), 0.8, np.float32))


def _view(tmp, name, d):
    return {"dir": d, "up": [0, 0, 1], "center": [0, 0, 0], "scale": 1.6, "out": str(Path(tmp) / f"{name}.png")}


def test_blender_per_view_lighting():
    """Two views in one job, each under its own rig == each view alone under that rig as the job's lighting (Cycles
    on the CPU, tiny: no GPU)."""
    with tempfile.TemporaryDirectory() as tmp:
        _cube(Path(tmp) / "cube.npz")
        base = {"mode": "render", "blend": str(Path(tmp) / "none.blend"), "caps": str(Path(tmp) / "cube.npz"),
                "engine": "cycles", "samples": 4, "denoise": False, "size": 24, "threads": 2}
        a, b = _view(tmp, "a", [-0.5, -1, 0.4]), _view(tmp, "b", [0.6, -1, 0.3])
        scene._blender({**base, "lighting": L1, "views": [{**a, "lighting": L1}, {**b, "lighting": L2}]})
        one = [np.asarray(Image.open(v["out"]), float) for v in (a, b)]
        a2, b2 = _view(tmp, "a2", a["dir"]), _view(tmp, "b2", b["dir"])
        scene._blender({**base, "lighting": L1, "views": [a2]})
        scene._blender({**base, "lighting": L2, "views": [b2]})
        sep = [np.asarray(Image.open(v["out"]), float) for v in (a2, b2)]
        for x, y in zip(one, sep):
            assert np.abs(x - y).mean() < 0.5, np.abs(x - y).mean()
        # (and the rigs really differ: B under L1 would be another picture)
        b3 = _view(tmp, "b3", b["dir"])
        scene._blender({**base, "lighting": L1, "views": [b3]})
        assert np.abs(np.asarray(Image.open(b3["out"]), float) - sep[1]).mean() > 5


def test_view_without_lighting_returns_to_the_jobs():
    """In a job where some views carry a rig, a view without one is lit by the job's lighting (not the last view's)."""
    with tempfile.TemporaryDirectory() as tmp:
        _cube(Path(tmp) / "cube.npz")
        base = {"mode": "render", "blend": str(Path(tmp) / "none.blend"), "caps": str(Path(tmp) / "cube.npz"),
                "engine": "cycles", "samples": 4, "denoise": False, "size": 24, "threads": 2}
        a, b = _view(tmp, "a", [-0.5, -1, 0.4]), _view(tmp, "b", [-0.5, -1, 0.4])
        scene._blender({**base, "lighting": L1, "views": [{**a, "lighting": L2}, b]})
        c = _view(tmp, "c", a["dir"])
        scene._blender({**base, "lighting": L1, "views": [c]})
        x, y = (np.asarray(Image.open(v["out"]), float) for v in (b, c))
        assert np.abs(x - y).mean() < 0.5, np.abs(x - y).mean()


def test_stage_shoot_job():
    """spikes/garrett3/stage.shoot builds ONE job for frames with their own lights: each frame's windows aimed at the
    first frame sharing its light (as when each light was its own call), flat frames carry none."""
    sys.path.insert(0, str(ROOT / "spikes/garrett3"))
    import stage
    from hifipushie import store
    jobs = []

    def fake(job, timeout=900, progress=None):
        jobs.append(json.loads(json.dumps(job)))
        for v in job["views"]:
            Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(v["out"])
        return "@@phase open 1.0\n@@frame 0.5\n"

    with tempfile.TemporaryDirectory() as tmp:
        old = stage.ensure, scene._blender, store.HOME
        try:
            store.HOME = Path(tmp)
            (Path(tmp) / "_st").mkdir()
            (Path(tmp) / "_st" / "spec.json").write_text("{}")
            stage.ensure = lambda *a, **k: "_st"
            scene._blender = fake
            la, lb = {"lights": [{"dir": [0, -1, 0]}]}, {"lights": [{"dir": [1, 0, 0]}]}
            fr = [{"name": n, "center": c, "dir": [0, 1, 0], "up": [0, 0, 1], "lighting": lt}
                  for n, c, lt in (("a", [0, 0, 1], la), ("b", [0, 0, 2], la), ("c", [0, 0, 3], lb))]
            out = stage.shoot("m", fr, la, size=8, hair_on=False)
            assert sorted(out) == ["a", "b", "c"] and len(jobs) == 1
            vs = jobs[0]["views"]
            assert [v["lighting"]["target"] for v in vs] == [[0, 0, 1], [0, 0, 1], [0, 0, 3]]
            assert vs[2]["lighting"]["lights"] == lb["lights"] and jobs[0]["lighting"]["target"] == [0, 0, 1]
            stage.shoot("m", fr, None, size=8, hair_on=False, flat=True)
            assert all("lighting" not in v for v in jobs[1]["views"])
        finally:
            stage.ensure, scene._blender, store.HOME = old


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
