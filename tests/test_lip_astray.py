"""The lips' astray-texel gate (asset.bake, LIP_ASTRAY_WARN) fires on the case it was made for.

x32 (r17's retopo.SOCK_FALLOFF = 6) baked torn streaks across the closed upper lip: the lips' texels projected onto
the moved mouth sock's exact surface instead of the lip. The whole head's astray share only went 3.75 -> 4.89%, so
nothing warned. This rebuilds both cases on a GNM-native head with face shapes (the model is in the workspace, so it
SKIPS without it) and asserts that the lips' share warns with SOCK_FALLOFF 6 and not with 0.

HEAVY (two exports, ~10 min each, resources.heavy): run as a script through capped,
    CAP=20G bin/capped uv run python tests/test_lip_astray.py [model] [out dir]
Outputs are kept in <out dir>/f0, f6 (default /mnt/data/hifipushie/assembly/exp/lipgate); with KEEP=1 an existing
export is read back instead of rebuilt (the shares are re-judged against the current LIP_ASTRAY_WARN).
"""
import json
import os
import sys
from pathlib import Path

from hifipushie import asset, retopo, store


def _share(out: Path, name: str) -> tuple[float, bool]:
    """The body's lips' front share, re-measured from the export's texel dump (HP_ASTRAY_DUMP) with the current
    asset.lip_front_share, and whether the export's log warned."""
    import numpy as np
    d = json.loads((out / f"{name}.json").read_text())
    z = np.load(out / "astray_body_0.npz")
    share, n = asset.lip_front_share(z["P"], z["bad"], z["lipw"])
    assert share is not None, f"{out}: no lips' texels found"
    warned = any("lips' texels projected astray" in ln for ln in d["log"])
    return share, warned


def run(model: str = "ga_tess", root: Path = Path("/mnt/data/hifipushie/assembly/exp/lipgate")) -> dict:
    if not (store.HOME / model / "spec.json").exists():
        print(f"SKIP: no model {model} in {store.HOME}")
        return {}
    res = {}
    keep = os.environ.get("KEEP") == "1"
    old = retopo.SOCK_FALLOFF
    try:
        for f in (0, 6):
            out = root / f"f{f}"
            if not (keep and (out / f"{model}.json").exists()):
                retopo.SOCK_FALLOFF = f
                out.mkdir(parents=True, exist_ok=True)
                os.environ["HP_ASTRAY_DUMP"] = str(out)
                asset.export(model, out, role="hero", texture=2048, face_shapes=["jawOpen"], rig=False, lods=False)
            res[f] = _share(out, model)
            print(f"SOCK_FALLOFF {f}: lips' astray share {res[f][0]:.2%}, warned at export: {res[f][1]}")
    finally:
        retopo.SOCK_FALLOFF = old
    (s0, _), (s6, _) = res[0], res[6]
    assert s0 <= asset.LIP_ASTRAY_WARN, f"the clean case (SOCK_FALLOFF 0) warns: {s0:.2%} > {asset.LIP_ASTRAY_WARN:.0%}"
    assert s6 > asset.LIP_ASTRAY_WARN, f"x32's case (SOCK_FALLOFF 6) reads clean: {s6:.2%} <= {asset.LIP_ASTRAY_WARN:.0%}"
    if not keep:
        assert res[6][1] and not res[0][1], "the export log's WARNING doesn't match the shares"
    print("PASS")
    return res


if __name__ == "__main__":
    run(*(sys.argv[1:2] or ["ga_tess"]), *([Path(sys.argv[2])] if len(sys.argv) > 2 else []))
