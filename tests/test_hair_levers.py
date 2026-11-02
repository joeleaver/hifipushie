"""(round 47) Card-selecting levers report what they matched, and an ON lever that matches nothing fails loudly.
r46g's tail-only BEND_ROWS matched 0 cards for a whole round: LOD1-3's clump_cards cards carried no "cls"."""
import numpy as np
import pytest

from hifipushie import hair, hair_cards as hc


def test_lever_matched_raises_on_zero():
    hc.LEVER_MATCHES.clear()
    assert hc.lever_matched("x", 3, 10) == 3
    with pytest.raises(hc.LeverMatchedNothing):
        hc.lever_matched("x", 0, 10)
    assert hc.LEVER_MATCHES["x"] == [(3, 10), (0, 10)]
    hc.lever_matched("x", 0, 0)  # an empty population (e.g. a short cut has no tail) is not a dead filter


def test_stamp_cls_gives_far_tier_cards_their_class(monkeypatch):
    locks = [{"name": "tail0", "free": 1.0}, {"name": "head0"}, {"name": "wisp", "face": True, "hairs": 40},
             {"name": "halo", "hairs": 1}]
    P = np.c_[np.zeros(5), -np.linspace(0, 0.1, 5), np.zeros(5)]
    cards = [{"lock": n, "P": P, "kind": k} for n, k in (("tail0", "coverage"), ("head0", "coverage"),
                                                         ("wisp", "coverage"), ("halo", "fly"))]
    # the bug: unstamped cards never match a class filter
    monkeypatch.setattr(hc, "BEND_ROWS", 30.0)
    monkeypatch.setattr(hc, "BEND_CLS", ("tail",))
    assert not any(hc.bend_selected(c) for c in cards)
    hair.stamp_cls(cards, locks)
    assert [c["cls"] for c in cards] == ["tail", "head", "face", "fly"]
    assert [hc.bend_selected(c) for c in cards] == [True, False, False, False]


def test_stamp_cls_keeps_an_existing_class():
    c = {"lock": "a", "cls": "head", "kind": "baked"}
    hair.stamp_cls([c], [{"name": "a", "free": 1.0}])
    assert c["cls"] == "head"
