"""Cloth pre-placement cache (2026-10-16): a finished build is also stored under a key of its inputs before placement
(cloth.pre_key), so a garment whose sim is cached loads without being placed again; within one garments() / cached()
call builds and body meshes are memoised. _build is stubbed here (a real placement takes minutes; the real-model check
is in docs/notes/cloth.md). Run: uv run python tests/test_cloth_precache.py"""
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["HIFIPUSHIE_HOME"] = tempfile.mkdtemp(prefix="hp_precache_")

from hifipushie import cloth, store  # noqa: E402

store.HOME = Path(os.environ["HIFIPUSHIE_HOME"])
CALLS = []


def fake_build(g, body_src, name="garment", **kw):
    CALLS.append(name)
    key = "k" + str(abs(hash((g["n"], float(np.sum(body_src["V"])))))  % 10 ** 8)
    if kw.get("cached_only") and not (cloth._cache_dir() / f"{key}.npz").exists():
        cloth._MEMO.miss = key  # (as _build does)
        return None
    np.savez(cloth._cache_dir() / f"{key}.npz", V=np.zeros(1))
    rng = np.random.default_rng(len(CALLS))
    return {"key": key, "V": body_src["V"] + g["n"], "noise": rng.random(3), "mesh": {"F": np.arange(6).reshape(2, 3)}}


def body(z=0.0):
    return {"V": np.array([[0, 0, z], [1, 0, 0], [0, 1, 0.]]), "F": [[0, 1, 2]], "J": {"hip": np.zeros(3)}, "key": "b"}


cloth._build = fake_build


def test_pre_cache_skips_build():
    CALLS.clear()
    a = cloth.build({"n": 1}, body(), "a")
    b = cloth.build({"n": 1}, body(), "a")
    assert CALLS == ["a"], CALLS  # the second came from pre_<key>.pkl
    assert np.array_equal(a["V"], b["V"]) and np.array_equal(a["noise"], b["noise"]) and a["key"] == b["key"]
    assert a["pre_key"] == cloth.pre_key({"n": 1}, body())


def test_pre_cache_keys_and_invalidation():
    CALLS.clear()
    cloth.build({"n": 2}, body(), "a")
    cloth.build({"n": 3}, body(), "b")       # another garment
    cloth.build({"n": 2}, body(0.5), "c")    # another body
    assert CALLS == ["a", "b", "c"], CALLS
    r = cloth.build({"n": 2}, body(), "d")
    (cloth._cache_dir() / f"{r['key']}.npz").unlink()  # the sim result gone: the pre entry is not used
    assert cloth.build({"n": 2}, body(), "e", cached_only=True) is None
    assert CALLS == ["a", "b", "c", "e"], CALLS
    os.environ["HIFIPUSHIE_CLOTH_PRE"] = "0"
    try:
        cloth.build({"n": 3}, body(), "f")
    finally:
        os.environ.pop("HIFIPUSHIE_CLOTH_PRE")
    assert CALLS[-1] == "f"


def test_under_pre_key_chains():
    u1 = {"key": "u", "name": "jeans", "V": np.zeros((3, 3)), "F": np.zeros((1, 3), int), "res": {"pre_key": "p1"}}
    u2 = dict(u1, res={"pre_key": "p2"})  # same sim, other clean-up: another result over it
    assert cloth.pre_key({"n": 1}, dict(body(), under=u1)) != cloth.pre_key({"n": 1}, dict(body(), under=u2))


def test_unsimulated_not_placed_again():
    CALLS.clear()
    g = {"n": 42}
    assert cloth.build(g, body(), "a", cached_only=True) is None
    assert cloth.build(g, body(), "b", cached_only=True) is None  # the .miss record: no placement
    assert CALLS == ["a"], CALLS
    r = cloth.build(g, body(), "c")  # simulated now (dress): its npz exists, the miss no longer applies
    assert np.array_equal(cloth.build(g, body(), "d", cached_only=True)["V"], r["V"])
    assert CALLS == ["a", "c"], CALLS


def test_memo_scope():
    CALLS.clear()
    for f in cloth._cache_dir().glob("pre_*.pkl"):
        f.unlink()
    with cloth._memo_scope():
        os.environ["HIFIPUSHIE_CLOTH_PRE"] = "1"
        a = cloth.build({"n": 9}, body(), "a")
        for f in cloth._cache_dir().glob("pre_*.pkl"):
            f.unlink()
        b = cloth.build({"n": 9}, body(), "b")  # memoised in the scope, not read from disk
        b["V"][:] = -1  # a caller's edit doesn't reach the memo
        c = cloth.build({"n": 9}, body(), "c")
    assert CALLS == ["a"], CALLS
    assert np.array_equal(a["V"], c["V"]) and not np.array_equal(b["V"], c["V"])
    assert cloth._MEMO.builds is None


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
