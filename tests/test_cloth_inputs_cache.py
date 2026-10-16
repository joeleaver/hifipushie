"""The sim cache is also addressed by a job's actual inputs (2026-10-16, dress-tess): cloth_job.input_hash over job.json
(the "out" path aside) + in.npz's arrays. A sim key that misses but whose inputs hash to a cached sim uses that sim,
under ITS key (so garments over it and its sculpt / finish files keep theirs). The incident: dt_tess's jeans re-keyed
when a lanyard was added elsewhere on the model (the worn shoes were keyed by store.build's whole-model key), with
byte-identical inputs, and the sweater and coat over them re-keyed through `under`.
  uv run python tests/test_cloth_inputs_cache.py
Always run: the hash's invariants and the index (two keys, identical inputs, one sim). With the dt_tess model and its
cached jeans sim (skipped without): the jeans found, and again under an altered body key, with no sim run."""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hifipushie import cloth, cloth_job, store  # noqa: E402


def _job():
    cfg = {"fabric": {"kb": "denim", "name": "denim", "mass": 0.5, "tension": 40, "compression": 40, "shear": 30,
                      "bending": 2.0, "thickness": 0.001}, "frames": 48, "state": "worn", "name": "m:g",
           "made": np.array([1, 2]), "trace": []}
    arrays = {"X": np.random.default_rng(1).random((20, 3)), "F": np.arange(30).reshape(10, 3), "pins": np.zeros(0, np.int64)}
    return cfg, arrays


def test_input_hash_invariants():
    cfg, arrays = _job()
    h = cloth_job.input_hash(cloth_job.job_config(cfg, ["a", "b"]), arrays)
    with tempfile.TemporaryDirectory() as td:
        jd = cloth_job.write(Path(td) / "job_k1" / "sim", cfg, arrays, ["a", "b"])
        assert cloth_job.job_input_hash(jd) == h  # the written folder hashes as the in-memory job
        jd2 = cloth_job.write(Path(td) / "job_k2" / "sim", cfg, arrays, ["a", "b"])
        assert json.loads((jd2 / "job.json").read_text())["out"] != json.loads((jd / "job.json").read_text())["out"]
        assert cloth_job.job_input_hash(jd2) == h  # the out path never counts
    a2 = dict(arrays, X=arrays["X"] + 1e-9)
    assert cloth_job.input_hash(cloth_job.job_config(cfg, ["a", "b"]), a2) != h
    assert cloth_job.input_hash(cloth_job.job_config(dict(cfg, frames=49), ["a", "b"]), arrays) != h
    assert cloth_job.input_hash(cloth_job.job_config(cfg, ["b", "a"]), arrays) != h


def test_two_keys_one_sim():
    """A sim cached under key k1 (its job folder kept) is found for key k2 with identical inputs: by the backfilled
    index, then by the index entry alone; another input misses."""
    old = store.HOME
    with tempfile.TemporaryDirectory() as td:
        store.HOME = Path(td)
        try:
            cfg, arrays = _job()
            cloth_job.write(cloth._cache_dir() / "job_k1" / "sim", cfg, arrays, ["a"])
            np.savez(cloth._cache_dir() / "k1.npz", V=np.zeros((20, 3)))
            h = cloth_job.input_hash(cloth_job.job_config(cfg, ["a"]), arrays)
            assert cloth.cached_by_inputs(h) == "k1"  # (indexed from the kept folder on the miss)
            assert (cloth._cache_dir() / "job_k1" / "sim" / "inputs_hash").read_text() == h
            import shutil
            shutil.rmtree(cloth._cache_dir() / "job_k1")  # (folders go unless HIFIPUSHIE_CLOTH_KEEP: the index holds)
            assert cloth.cached_by_inputs(h) == "k1"
            cloth.note_inputs(h, "k9")  # (a later note never moves an entry)
            assert cloth.cached_by_inputs(h) == "k1"
            h2 = cloth_job.input_hash(cloth_job.job_config(dict(cfg, frames=10), ["a"]), arrays)
            assert cloth.cached_by_inputs(h2) is None
            (cloth._cache_dir() / "k1.npz").unlink()
            assert cloth.cached_by_inputs(h) is None  # (the sim itself gone: a miss)
        finally:
            store.HOME = old


def test_dt_tess_jeans_by_inputs():
    """The real incident, pre-placement cache off: the jeans found (3e42fc7c870b3383 or whatever key holds their
    inputs), and found again under another body key (same inputs, another sim key): no sim is run."""
    if not (store.HOME / "dt_tess" / "spec.json").exists():
        print("skip: no dt_tess model"); return
    os.environ["HIFIPUSHIE_CLOTH_PRE"] = "0"
    real = cloth._blender_job

    def no_sim(*a, **k):
        raise AssertionError("a sim was started")
    cloth._blender_job = no_sim
    try:
        spec = store.load("dt_tess")
        g = spec["cloth"]["jeans"]
        src = cloth.model_body("dt_tess", spec, g, simulate=False)
        res = cloth.build(cloth._garment_for_sim(g), src, "dt_tess:jeans", log=lambda *_: None, cached_only=True)
        if res is None:
            print("skip: dt_tess jeans not cached"); return
        res2 = cloth.build(cloth._garment_for_sim(g), dict(src, key=str(src.get("key")) + ":moved"), "dt_tess:jeans",
                           log=lambda *_: None, cached_only=True)
        assert res2 is not None and res2["key"] == res["key"], (res["key"], res2 and res2["key"])
        assert np.array_equal(res2["V_sim"], res["V_sim"])
        print("dt_tess jeans", res["key"])
    finally:
        cloth._blender_job = real
        os.environ.pop("HIFIPUSHIE_CLOTH_PRE", None)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
            print("ok", n)
