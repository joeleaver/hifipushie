"""Offload packs: a job folder packed on the laptop must be what the runner reads, checked with the archive's code.

dt-b01 (2026-10-16): rvpack folders (r_<name>/job.json + data.npz, cloth.render's own job) were submitted with
job_clothrender.py (sheets.pkl) and failed on NICO-TOP after the queue. remote.sh now runs `<runner> --check <dir>`
before a submit; these tests pin that both cloth runners accept their own pack and refuse the other's, and that the
committed runner (git archive HEAD, what NICO-TOP gets) agrees."""
import json
import os
import pickle
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OFF = ROOT / "spikes/offload"


def _check(runner, job, cwd=None):
    r = subprocess.run([sys.executable, str(runner), "--check", str(job)], capture_output=True, text=True, cwd=cwd,
                       env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))
    return r.returncode, r.stdout + r.stderr


def _pack_render(job: Path, name="t"):
    """A job folder exactly as cloth.render writes its job (its Blender call captured), maps made folder-local."""
    from hifipushie import cloth
    d = job / f"r_{name}"
    d.mkdir(parents=True)
    tex = job / "tex.png"
    tex.write_bytes(b"\x89PNG\r\n")
    seen = {}

    def fake_run(cmd, **k):
        jp = Path(cmd[-1])
        j = json.loads(jp.read_text())
        (d / "data.npz").write_bytes((jp.parent / j["data"]).read_bytes())
        j["data"] = "data.npz"
        for o in j["objects"]:
            for mk, v in (o.get("maps") or {}).items():
                (d / Path(v).name).write_bytes(Path(v).read_bytes())
                o["maps"][mk] = Path(v).name
        (d / "job.json").write_text(json.dumps(j))
        seen["ok"] = True
        return subprocess.CompletedProcess(cmd, 0, "", "")

    V = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1.0]])
    real = cloth.subprocess.run
    cloth.subprocess.run = fake_run
    try:
        cloth.render([{"name": "g_coat", "V": V, "F": np.array([[0, 1, 2]]), "color": "#ffffff",
                       "uv": np.zeros((3, 2)), "maps": {"basecolor": str(tex)}}], str(job / "tmp" / "look"),
                     views=["front", {"name": "game1m", "dir": [0, -1, 0], "dist": 1.0, "fov": 59}], textured=True)
    finally:
        cloth.subprocess.run = real
    assert seen
    return d


def test_clothjobs_pack_checks():
    with tempfile.TemporaryDirectory() as t:
        job = Path(t) / "j1"
        _pack_render(job)
        rc, out = _check(OFF / "job_clothjobs.py", job)
        assert rc == 0 and out.strip() == "ok", out
        rc, out = _check(OFF / "job_clothrender.py", job)  # the dt-b01 mistake: refused, with the right runner named
        assert rc == 1 and "job_clothjobs.py" in out, out
        (job / "r_t" / "data.npz").unlink()
        rc, out = _check(OFF / "job_clothjobs.py", job)
        assert rc == 1 and "missing" in out, out


def test_clothrender_pack_checks():
    with tempfile.TemporaryDirectory() as t:
        job = Path(t) / "j1"
        job.mkdir()
        (job / "m.png").write_bytes(b"x")
        S = [{"out": "a.png", "objs": [{"name": "g", "maps": {"basecolor": "m.png"}}], "views": ["front"],
              "resolution": 64, "box": None, "aspect": 1.0, "textured": True}]
        pickle.dump(S, open(job / "sheets.pkl", "wb"))
        assert _check(OFF / "job_clothrender.py", job)[0] == 0
        rc, out = _check(OFF / "job_clothjobs.py", job)
        assert rc == 1 and "job_clothrender" in out, out
        # a pickle naming a class the archive's code doesn't have
        (job / "sheets.pkl").write_bytes(b"\x80\x04\x8c\x05nomod\x94\x8c\x03Cls\x94\x93\x94.")
        rc, out = _check(OFF / "job_clothrender.py", job)
        assert rc == 1 and "does not unpickle" in out, out


def test_archived_runner_checks_the_pack():
    """The runner NICO-TOP gets is git archive HEAD's: its --check must accept a pack made by this code."""
    with tempfile.TemporaryDirectory() as t:
        a = Path(t) / "a.tar"
        subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "-o", str(a), "HEAD", "spikes/offload"],
                       check=True)
        tarfile.open(a).extractall(Path(t) / "repo", filter="data")
        runner = Path(t) / "repo/spikes/offload/job_clothjobs.py"
        job = Path(t) / "j1"
        _pack_render(job)
        if '"--check"' not in runner.read_text():
            raise AssertionError("HEAD's job_clothjobs.py has no --check: commit the runner before submitting")
        rc, out = _check(runner, job)
        assert rc == 0, out


if __name__ == "__main__":
    for f in (test_clothjobs_pack_checks, test_clothrender_pack_checks, test_archived_runner_checks_the_pack):
        f()
        print("ok", f.__name__)
