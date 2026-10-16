"""A layered garment's whole finish lives in the spec (2026-10-16, dress-garrett): rebuilding dg_garrett's jacket from
its spec ALONE (cache only, no sim, no run.py overrides) reproduces the frozen j17a pieces: the jacket (under.pin =
the pinned shirt, sculpt, post-construct finish), the shirt as pressed under it (under_sculpt) and its made collar +
stand (under_collar). Needs the dg_garrett model, its cached sim and the frozen files (FROZEN, default
/mnt/data/hifipushie/dress_garrett/frozen_j17b = j17a); skipped without them. The start's uncrush is the garment key
"uncrush" (the env var HP_UNCRUSH is only a fallback): this test unsets the env var, so the spec alone decides.
  HIFIPUSHIE_HOME=<workspace> uv run python tests/test_cloth_spec_durable.py
Also (always run): the uncrush key's precedence over the env var, and a design's compiled draft pattern (with its
"kind") passing cloth.validate, so store.save can check such a spec; pins (cloth.pin_file / pin_path) immutable and
checked, under.pin refusing a path.
No scratch file is read (2026-10-16 x): the spec's under.pin / sculpt / under_sculpt / finish are content-addressed pins in
workspace/dg_garrett/_pins, and the expected frozen j17b pieces are pins too (FROZEN_PINS; FROZEN=<dir> reads that dir
instead). The jacket's sim was cached while the sim key still held the design pattern's "kind" (main c2173b7c took it
out): cloth._build finds such a legacy entry under its old key, so 7aca63ae26eb8a5c holds."""
import os
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hifipushie import cloth, store  # noqa: E402

FROZEN = os.environ.get("FROZEN")
FROZEN_PINS = {"jacket": "pin:170b2da13df3f024", "shirt": "pin:38c8842a46f1af9d"}  # (frozen_j17b, 2026-10-16 01:01)


def test_pins():
    import tempfile
    old = store.HOME
    with tempfile.TemporaryDirectory() as td:
        store.HOME = Path(td)
        try:
            src = Path(td) / "a.npz"
            np.savez(src, offset=np.ones((3, 3)))
            ref = cloth.pin_file("m", src)
            assert cloth.PIN_RE.fullmatch(ref), ref
            assert cloth.pin_file("m", src) == ref  # (same content: the same pin, not rewritten)
            f = cloth.pin_path(ref, "m:garment")
            assert np.load(f)["offset"].sum() == 9
            src.write_bytes(b"other")  # (the scratch source rewritten: the pin keeps its content)
            assert np.load(cloth.pin_path(ref, "m"))["offset"].sum() == 9
            os.chmod(f, 0o644)
            f.write_bytes(b"tampered")
            try:
                cloth.pin_path(ref, "m")
                raise AssertionError("a rewritten pin must be refused")
            except cloth.ClothError as e:
                assert "no longer matches" in str(e), e
            try:
                cloth.under_pinned(str(src), "m")
                raise AssertionError("under.pin must refuse a path")
            except cloth.ClothError as e:
                assert "pin reference" in str(e), e
        finally:
            store.HOME = old
    print("ok pins: content-addressed, immutable, checked; under.pin takes pins only")


def test_uncrush_key():
    old = os.environ.pop("HP_UNCRUSH", None)
    try:
        assert cloth.uncrush_on({}) is False  # (default off: the jeans' start stays as it was)
        assert cloth.uncrush_on({"uncrush": True}) is True
        os.environ["HP_UNCRUSH"] = "1"
        assert cloth.uncrush_on({}) is True  # (the env var: a fallback only)
        assert cloth.uncrush_on({"uncrush": False}) is False  # (the key wins)
    finally:
        os.environ.pop("HP_UNCRUSH", None)
        if old is not None:
            os.environ["HP_UNCRUSH"] = old
    pat = {"from": "skirt_block"}
    try:
        cloth.validate({"cloth": {"x": {"pattern": pat, "uncrush": "yes"}}})
        raise AssertionError("uncrush must be a bool")
    except cloth.ClothError as e:
        assert "uncrush" in str(e), e
    print("ok uncrush garment key (default off, key over env)")


def test_draft_kind_validates():
    from hifipushie import garment_blocks
    assert "kind" in garment_blocks.WORDS["draft"]
    g = {"pattern": {"from": "draft", "block": "bodice", "block_options": {}, "ops": [], "kind": "coat"}}
    try:
        cloth.validate({"cloth": {"x": g}})
    except cloth.ClothError as e:
        assert "pattern keys" not in str(e), e  # (other complaints about this bare garment are not this test's)
    print("ok a compiled draft's pattern kind passes the validator")


def main():
    test_uncrush_key()
    test_draft_kind_validates()
    test_pins()
    os.environ.pop("HP_UNCRUSH", None)  # (the spec alone decides the start)
    if "dg_garrett" not in store.list_models():
        print("skip: no dg_garrett model here")
        return
    try:
        fp = {k: Path(FROZEN) / f"garrett_{k}.pkl" if FROZEN else cloth.pin_path(v, "dg_garrett") for k, v in FROZEN_PINS.items()}
    except cloth.ClothError as e:
        print(f"skip: frozen pieces not pinned here ({e})")
        return
    fj = pickle.load(open(fp["jacket"], "rb"))
    fs = pickle.load(open(fp["shirt"], "rb"))
    fj, fs = fj.get("res", fj), fs.get("res", fs)
    spec = store.load("dg_garrett")
    g = spec["cloth"]["jacket"]
    refs = [g["under"]["pin"]] + [g[k]["file"] for k in ("sculpt", "under_sculpt", "finish")]
    assert all(cloth.PIN_RE.fullmatch(r) for r in refs), f"the spec reads a scratch path: {refs}"
    assert g.get("uncrush") is True and spec["cloth"]["shirt"].get("uncrush") is True
    cloth.validate(spec)  # (the stored spec passes the checked save's cloth validation: the design's "kind")
    res = cloth.build(cloth._garment_for_sim(g), cloth.model_body("dg_garrett", spec, g), "dg_garrett:jacket",
                      log=lambda *a: None, cached_only=True)
    assert res is not None, "the jacket's sim is not cached under the spec's key (another under / start?)"
    print("key", res["key"], "sculpted", res.get("sculpted"), "finished", res.get("finished"),
          "under sculpted", res.get("under_sculpted"))
    assert res["key"] == "7aca63ae26eb8a5c", res["key"]
    assert not res.get("sculpt_stale") and not res.get("finish_stale") and not res.get("under_sculpt_stale")

    def same(a, b, what, tol=1e-6):
        a, b = np.asarray(a, float), np.asarray(b, float)
        assert a.shape == b.shape, (what, a.shape, b.shape)
        d = float(np.abs(a - b).max()) if a.size else 0.0
        print(f"  {what}: max diff {d * 1000:.4f} mm")
        assert d < tol, what

    same(res["V"], fj["V"], "jacket V")
    for p, q in zip(res["made"]["parts"], fj["made"]["parts"]):
        same(p["V"], q["V"], "jacket made " + p["name"])
    same(res["under_V"], fs["V"], "shirt as pressed (under sculpt)")
    mk = {p["name"]: p for p in fs["made"]["parts"]}
    for p in res["under_made"]["parts"]:
        same(p["V"], mk[p["name"]]["V"], "shirt made " + p["name"])
    assert sorted(res["under_made"]["hides"]) == sorted(fs["made"]["info"]["hides"])
    print("ok spec alone (no HP_UNCRUSH) reproduces the frozen j17b pieces")


if __name__ == "__main__":
    main()
