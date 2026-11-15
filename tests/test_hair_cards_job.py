"""The cards job, run: a grown groom on a ball head through hair_job.job at a tier, with the constants as they are.

Until 2026-11-15 no test ran it. For four days (from the split of hair_clumps) every strand groom that is not cut by
clumps raised UnboundLocalError at the tiers main / npc / far: the crown arch row read `hair_clumps.ARCH` in a block
that had imported the module only as `_hk` (C477). Needs Blender for the strands: the slow tier.
`uv run pytest -m "" tests/test_hair_cards_job.py`."""
import contextlib
import io
import shutil

import numpy as np
import pytest

from hifipushie import hair, hair_groom, hair_grow, hair_head, hair_job, hair_loose, render
from test_hair_loose import _ball_head

LOOSE = {"loose": {"length": 0.3, "spacing": 0.03}, "parting": {"side": "left"}, "seed": 2}
TIED = {"tie": {"at": [176, 25], "escape": 0}, "parting": {"side": "centre"}, "seed": 2}

needs_blender = pytest.mark.skipif(shutil.which(render.BLENDER) is None, reason="needs Blender (the strands)")


def cards_at(groom: dict, tier, monkeypatch=None, **constants) -> tuple:
    """(the job's cards entry, its mesh arrays, what it printed) for a groom grown on the ball head."""
    spec = {"hair": {"style": "cards", "groom": groom}}
    sc, col = _ball_head()
    spec["hair"]["locks"] = hair_grow.grow(sc, hair_groom.groom_params(spec), col)
    key = hair_head._geometry_key(spec)
    hair._SCALPS[key] = sc
    hair_loose._COLL[key] = col
    for name, value in constants.items():
        monkeypatch.setattr(hair, name, value)
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        out = hair_job.job("cards_job_ball", spec=spec, budget=tier)
    return out["cards"], dict(np.load(out["cards"]["mesh"], allow_pickle=False)), said.getvalue()


@needs_blender
@pytest.mark.parametrize("tier", ["main", "npc", "far"])
def test_a_loose_groom_exports_at_every_tier_below_hero(tier):
    """The tiers under hero are cut by lock, not by clumps, and get the crown arch row by default (hair.ARCH_TIERS)."""
    assert float(hair.ARCH_TIERS.get(tier, 0.0)) > 0, "the default this test is about"
    c, mesh, said = cards_at(LOOSE, tier)
    assert c["cards"] > 0 and c["triangles"] > 0 and not c["short"]
    assert len(mesh["verts"]) > 0 and len(mesh["tris"]) > 0
    assert "hair cards: crown arch" in said and f"at tier {tier!r}" in said, said[-400:]


@needs_blender
def test_a_tied_groom_exports_below_hero():
    c, mesh, said = cards_at(TIED, "npc")
    assert c["cards"] > 0 and len(mesh["verts"]) > 0


@needs_blender
def test_the_part_cover_row_at_a_coarser_tier(monkeypatch):
    """hair.COVER_TIERS is off by default; switched on, the cover row is cut at that tier (the second block that read
    the module by a name it had not imported)."""
    c, mesh, said = cards_at(LOOSE, "main", monkeypatch, COVER_TIERS={"main": 1.0})
    assert c["cards"] > 0
    assert "hair cards: part cover" in said, said[-400:]
