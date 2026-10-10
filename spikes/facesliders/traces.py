"""traces.py: the face contours traced by eye (facesliders, 2026-10-09; gridimg.py crops at 4-10 px grids, full-picture
pixels) into likeness_points.json of fs_traces_g (Garrett: + lk_garrett5's desk profile) and fs_traces_t (Tess).
Only segments with a visible edge: the face against background, dark hair behind it, or the ear (a shadowed line
in front of it); segments where hair crosses the face or skin meets skin without an edge are stored with an "x_"
prefix (uncertain: never used). Names: .R / .L = the subject's right / left (picture left / right on a front)."""
from hifipushie import likeness_shape as ls

GF = "/home/joe/dev/hifipushie/workspace/garrett_v20/concept_v8_front_apose.png"
TF = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/tess_head_front.png"
TQ = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/tess_head_three_quarter_left.png"
BY = "facesliders, by eye on a 4-10 px grid, 2026-10-09"

garrett_front = {
    # the cheeks against the ears (a shadowed line), from the ear's top to the lobe
    "cheek.R": [[558, 268], [558.5, 276], [559, 284], [559.5, 292], [560, 299]],
    "cheek.L": [[680.4, 252], [680.7, 262], [680.5, 272], [680.4, 280], [680.1, 289]],
    # the jaw's underside and the chin over the neck's shadow (a strong dark edge under the stubble)
    "chin": [[574, 329], [583, 340], [592, 345], [602, 349], [612, 351], [620, 351.5], [630, 350.5], [640, 347],
             [649, 342], [657, 335], [663, 328], [668, 323]],
    # uncertain: temples under the hair; below the lobes the outer edge is the NECK, not the jaw; the ramus
    "x_jaw.R": [[568, 309], [574, 320]],
}
tess_front = {
    # the jaw against the background (lobe to the angle; below it the neck)
    "jaw.R": [[309, 821], [314, 840], [320.6, 858], [328, 877], [336.8, 895], [345, 910], [352.9, 922], [361, 936], [366, 944]],
    # against dark hair behind: the left cheek above the ear; the jaw below the lobe
    "cheek.L": [[754, 605], [755, 630], [755.5, 655], [756, 680]],
    "jaw.L": [[749.5, 793], [742.6, 830], [732.4, 867], [724, 894.7], [719.6, 922], [717, 940]],
    # uncertain: the chin's underside is a soft shading line over the neck (skin on skin)
    "x_chin": [[399.7, 949.3], [429.4, 964.2], [459, 974], [488.8, 979], [518.5, 980.7], [548, 977.4], [574.6, 970.8],
               [601, 959.2], [627.4, 946], [653.8, 932.8], [680, 919.6]],
}
tess_tq = {
    # the far side's silhouette against the background: cheek below the eye, the lips, chin, the jaw's underside
    "profile": [[272, 626], [270, 656], [270, 686.5], [272, 717], [276, 740], [286, 759], [300, 770], [302, 790],
                [302, 804], [300, 816], [304, 839], [306, 869], [310, 899.5], [315.6, 922], [329, 937.5], [355.5, 945],
                [385, 946], [414, 943]],
}

TP = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/tess_head_profile_left.png"
tess_profile = {
    # the forehead's skin against the background where it shows between the hair strands (5 px grid), down to the
    # brow hairs; above y 466 a strand crosses (uncertain), y 518-545 the brow's hairs stand out past the skin
    "forehead": [[203, 466], [201, 474], [199.5, 482], [198.4, 490], [197.4, 498], [196.6, 506], [196, 514]],
    "x_forehead_hair": [[215, 446], [210, 456]],
}

if __name__ == "__main__":
    import json
    import shutil
    from hifipushie import store
    for m in ("fs_traces_g", "fs_traces_t"):
        (store.HOME / m).mkdir(exist_ok=True)
    shutil.copy(store.HOME / "lk_garrett5" / "likeness_points.json", store.HOME / "fs_traces_g" / "likeness_points.json")
    # the desk painting's traced jaw.R matched no silhouette of the head (15 mm, it dragged the jaw): uncertain
    dk = "/home/joe/dev/hifipushie/workspace/garrett_v20/concept_v6_portrait_at_desk.png"
    jr = ls.load_points("fs_traces_g")[dk]["lines"]["jaw.R"]
    ls.set_points("fs_traces_g", dk, lines={"jaw.R": None, "x_jaw.R": jr})
    ls.set_points("fs_traces_g", GF, lines=garrett_front, by=BY)
    ls.set_points("fs_traces_t", TF, lines=tess_front, by=BY)
    ls.set_points("fs_traces_t", TQ, lines=tess_tq, by=BY)
    ls.set_points("fs_traces_t", TP, lines=tess_profile, by=BY)
    for m in ("fs_traces_g", "fs_traces_t"):
        print(m, {k: list(v["lines"]) for k, v in ls.load_points(m).items()})
    for nm, img, L in (("gf", GF, garrett_front), ("tf", TF, tess_front), ("tq", TQ, tess_tq)):
        json.dump(L, open(f"/mnt/data/hifipushie/facesliders/out/tr_{nm}.json", "w"))
