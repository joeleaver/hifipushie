"""A solid-lock groom key written beside loose or tied hair is SAID, not silently ignored (hair_spec.unread)."""
import numpy as np

from hifipushie import hair, hair_grow, hair_spec


def test_a_read_groom_remembers_its_reads_and_a_copy_does_not():
    seen: set = set()
    g = hair_grow.Read({"volume": {"top": 0.03}, "length": 1, "tiers": {}}, seen)
    assert g["volume"]["top"] == 0.03 and g.get("flow") is None and seen == {"volume", "flow"}
    plain = {**g}
    assert type(plain) is dict and plain["length"] == 1 and "length" not in seen  # (a copy is not a read)


def _grow(monkeypatch, groom):
    """hair_grow.grow with the head work stubbed out: only which groom keys it reads matters here."""
    from hifipushie import hair_loose_grow, hair_tied
    monkeypatch.setattr(hair_grow, "fit_to_head", lambda g, sc: dict(g))  # (a copy, as the real one makes)
    monkeypatch.setattr(hair_grow, "hairline", lambda sc, g: np.zeros((4, 2)))
    monkeypatch.setattr(hair_loose_grow, "grow", lambda sc, g, line, rng, col=None: {"l0": {"tier": "loose", "n": g["loose"]}})
    monkeypatch.setattr(hair_tied, "grow", lambda sc, g, line, rng, col=None: {"t0": {"tier": "tie", "n": g["tie"]}})
    reads: set = set()
    locks = hair_grow.grow(None, {**hair.GROOM, **groom}, None, reads)
    return locks, reads


def test_beside_loose_or_tied_hair_the_solid_keys_are_not_read_and_the_answer_says_so(monkeypatch):
    written = {"loose": {"length": 0.3}, "volume": {"top": 0.05}, "length": {"top": 0.2}, "tiers": {"big": {"width": 0.06}}}
    locks, reads = _grow(monkeypatch, written)
    assert list(locks) == ["l0"] and "loose" in reads and not reads & set(hair.SOLID_KEYS)
    lines = hair_spec.unread(written, reads)
    assert [ln.split(" ")[0] for ln in lines] == ["groom.tiers", "groom.length", "groom.volume"]  # (flow was not written)
    assert all("NOT READ" in ln for ln in lines) and "use loose.length" in lines[1] and "loose.lift and loose.body" in lines[2]
    locks, reads = _grow(monkeypatch, {"tie": {"at": [180, 20]}, "tiers": {"fill": {"width": 0.03}}})
    assert list(locks) == ["t0"] and "tiers" not in reads
    assert hair_spec.unread({"tie": {}, "tiers": {}}, reads) == [
        "groom.tiers is written but was NOT READ when the locks were grown: the generated tiers are not grown beside "
        "loose or tied hair (nothing takes its place)"]


def test_a_key_the_grow_read_is_never_reported():
    assert hair_spec.unread({"volume": {}, "length": {}, "flow": {}, "tiers": {}}, {"volume", "length", "flow", "tiers"}) == []
    assert hair_spec.unread({"parting": {}, "seed": 3}, set()) == []  # (only the solid locks' keys are this check's)
    assert set(hair.SOLID_KEYS) <= set(hair.GROOM)
