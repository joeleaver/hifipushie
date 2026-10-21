"""Shirt spike rules (2026-10-21, docs/notes/codified.md C137-C139): cheap config checks that keep the fixes in.

C139: Simon's band is sewn EDGE TO EDGE onto the fronts' placket tops and keeps its drafted ends; no worn-state fold
turns the neckline a band is sewn to. C138: a .L / .R pair of worn-state folds is declared alike. C137: the form's
collar mesh can bend the collar's roll (h <= pi r / 4)."""
import math

from hifipushie import cloth, garment_design, pattern_form as pf


def _stand_seam(tbl):
    return [s for s in tbl["seams"] if isinstance(s[0], str) and s[0].startswith("stand:") and "bottomMid" in s[0]]


def test_simon_band_is_sewn_edge_to_edge_and_keeps_its_ends():
    tbl = cloth.designs()["simon"]
    (seam,) = _stand_seam(tbl)
    band, fronts = seam
    assert band.split(":")[1].split(">")[0] == "leftBottomEdge" and band.endswith(">rightBottomEdge"), band
    assert "front.R:placketTopOut>cfNeck>neck" in fronts and "front.L:neck>cfNeck>placketTopFold1" in fronts, fronts
    assert tbl.get("band_ends") is False


def _wear_folds():
    for kind, k in garment_design.kb()["kinds"].items():
        if not isinstance(k, dict):
            continue
        for state, w in ((k.get("wear") or {}).items()):
            if isinstance(w, dict):
                for fd in w.get("folds") or []:
                    yield kind, state, fd


def test_no_worn_fold_turns_the_neckline_a_band_is_sewn_to():
    for kind, state, fd in _wear_folds():
        line = [str(p) for p in fd.get("line") or []]
        turns_neck = fd.get("flap") in ("cfNeck", "neck") or any(p.split("+")[0] in ("neck", "cfNeck") for p in line)
        assert not turns_neck, f"{kind} {state} {fd.get('name')}: a fold through the neckline the band is sewn to (C139)"


def test_mirrored_worn_folds_are_declared_alike():
    folds = {(kind, state, fd["name"]): fd for kind, state, fd in _wear_folds() if fd.get("name")}
    norm = lambda s: str(s).replace("buttonhole", "button").replace(".L", "").replace(".R", "")
    for (kind, state, nm), fd in folds.items():
        if nm.endswith(".L") and (kind, state, nm[:-2] + ".R") in folds:
            other = folds[(kind, state, nm[:-2] + ".R")]
            assert [norm(p) for p in fd.get("line") or []] == [norm(p) for p in other.get("line") or []], (nm, "C138")


def test_the_form_mesh_can_bend_the_collar_roll():
    g = cloth.expanded({"design": {"kind": "shirt", "from": "simon", "fit": "regular", "fabric": "cotton_shirting",
                                   "details": {"sleeve_placket": "slit", "collar": "shirt_collar"}}})
    rolls = [fd for fd in g.get("folds") or [] if fd.get("kind") == "roll" and fd.get("piece") in ("collar", "stand")]
    assert rolls, "the shirt collar declares its roll"
    h = {p: e["h"] for e in pf.form_refine(g) for p in ([e["piece"]] if isinstance(e["piece"], str) else e["piece"])}
    for fd in rolls:
        r = float(fd.get("radius", 0.003))
        assert h[fd["piece"]] <= math.pi * r / 4 + 1e-9, (fd["name"], h[fd["piece"]], r, "C137")
