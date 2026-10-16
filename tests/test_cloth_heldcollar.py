"""A collar held out of the sim (construct {"collar": true, "sim_collar": false}, dress-tess c14 / c15: the simulated
collar crossed the fronts): the sim's draft has no collar (`cloth_made.hold_out`) and construct reads the collar's sewn
edge off the FULL draft's mesh, mapped onto the simulated mesh by pattern place (`held_chain`). The test: on a drafted
coat, the held-out chain lands on the same garment-side places (piece + pattern uv) as the sewn chain of the full mesh.
Run: uv run python tests/test_cloth_heldcollar.py"""
import numpy as np

from hifipushie import cloth, cloth_made as cm

MM = {"neck": 340.0, "shoulderSlope": 22.0, "shoulderToShoulder": 400.0, "chest": 860.0, "waist": 720.0, "hips": 900.0,
      "seat": 940.0, "biceps": 290.0, "wrist": 150.0, "shoulderToElbow": 310.0, "shoulderToWrist": 570.0,
      "hpsToWaistBack": 400.0, "hpsToBust": 260.0, "highBust": 840.0, "waistToArmpit": 200.0, "waistToHips": 180.0,
      "waistToSeat": 200.0, "waistToFloor": 1000.0, "waistToKnee": 560.0, "head": 550.0, "waistToUpperLeg": 240.0,
      "inseam": 760.0, "hpsToArmpitBack": 190.0}

G = {"design": {"kind": "coat", "block": "bodice", "fit": "regular", "fabric": "cotton_twill",
                "block_options": {"fitted": False, "chest_ease": 0.22, "hips_ease": 0.25, "length": 0.9},
                "ops": [{"op": "lapel", "break_y": 0.25, "stand": 0.02, "width": 0.075, "gorge": "straight", "gorge_drop": 0.08,
                         "notch": 0.03}, {"op": "collar", "type": "tailored", "stop": 0.0, "stand_height": 0.024, "fall": 0.038},
                        {"op": "unfold"}],
                "details": {"collar": "notched_lapel", "front_closure": "button_stand"}},
     "construct": {"collar": True, "sim_collar": False}}


def _lift(M):
    """pattern places as 3D points, one plane per piece (so P compares pattern places)"""
    uv = np.asarray(M["uv"], float)
    return np.c_[uv, np.asarray(M["piece"], float)]


def test_held_out_collar_chain_matches_the_sewn_chain():
    Bf = cloth.pieces(G, MM)
    assert "collar" in Bf["pieces"]
    Bs = cm.hold_out(Bf, ("collar",))
    assert "collar" not in Bs["pieces"] and Bs["held_out"] == ["collar"]
    assert not any("collar" in str(s) for s in Bs["seams"] + Bs["stitches"]), "a seam still names the collar"
    h = 0.01
    Mf, Ms = cloth.mesh(Bf, h), cloth.mesh(Bs, h)
    assert "collar" not in Ms["names"]
    ref = cm.seam_chain(_lift(Mf), Mf, ("collar",))
    ch = cm.held_chain(_lift(Ms), Ms, Mf)
    # the same collar-side order and edge
    assert len(ch["idx"]) >= 0.9 * len(ref["idx"]), (len(ch["idx"]), len(ref["idx"]))
    assert np.isin(ch["made_idx"], ref["made_idx"]).all()
    # garment-side places: same piece, the same pattern place up to the two meshes' seam sampling
    namesf, names = list(Mf["names"]), list(Ms["names"])
    pf = [namesf[i] for i in np.asarray(Mf["piece"])[ref["idx"]]]
    k = {int(m): i for i, m in enumerate(ref["made_idx"])}
    for j, m in enumerate(ch["made_idx"]):
        i = k[int(m)]
        assert names[int(Ms["piece"][ch["idx"][j]])] == pf[i]
    # (without the collar the neckline is sampled on its own: a station may land one edge along, under h)
    assert ch["map_mm"] < h * 1000, ch["map_mm"]
    # the chain runs in order along the neck (no back-tracking: consecutive stations close in pattern space)
    print("ok", {"stations": len(ch["idx"]), "sewn": len(ref["idx"]), "map_mm": ch["map_mm"]})


def test_options_default_keeps_the_simulated_collar():
    assert cm.options({"construct": {"collar": True}})["sim_collar"] is True


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
