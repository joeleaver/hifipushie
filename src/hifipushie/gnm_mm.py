"""Millimetre moves: a measure a driver can SEE (pupils apart, the forehead ahead of the nasion, the chin forward...) moved
1 mm with every other measure held in millimetres (gnmdrive, 2026-10-10).

The macros (humanmacro) are ratios over the interocular distance, so holding them while the eyes move apart scales the
whole head (head_size! moved the neck 10 mm and the skull 8 mm per sd). Here the held quantities are the readouts in mm,
so "eyes further apart" is the eyes alone: |dc| 0.62 per mm, the face's other skin 0.35 mm rms. A block-in move
`"mm:<measure>": mm` = the least-norm change of GNM's 170 head comps doing exactly that (linear, exact).
GNM frame for the readers: x left, y up, z forward, mm."""
from __future__ import annotations

import numpy as np

_C: dict = {}


def _space():
    if "sp" not in _C:
        from . import base as basemod, humanmacro as hm
        g = basemod._gnm_data()
        names = [str(n) for n in g["identity_names"]]
        comps = [i for i, n in enumerate(names) if n.startswith("head")]
        IB = np.asarray(g["vertex_identity_basis"])[comps].astype(np.float64)
        T = np.asarray(g["template_vertex_positions"], float)
        gr = {k: np.asarray(v, float) > 0.5 for k, v in g["groups"].items()}
        WL = np.zeros((68, len(T)))
        for i, r in enumerate(g["lm68"]):
            for v, x in zip(r[0::2], r[1::2]):
                WL[i, int(v)] += float(x)
        from . import lidrings
        mir = lidrings.mirror()
        orb = {k: np.r_[ids, mir[ids]] for k, ids in lidrings.sets().items()}
        y = {k: float(T[ids, 1].mean()) for k, ids in orb.items()}
        _C["sp"] = {"T": T, "IB": IB, "gr": gr, "WL": WL, "sets": hm.space()["sets"], "orb": orb,
                    # the hollow's chord (platform -> brow ridge) at the sulcus' height, fixed on the template
                    "w_hollow": (y["brow_ridge"] - y["sulcus"]) / (y["brow_ridge"] - y["platform"]),
                    # GNM's eye is rigid: its corneal apex stands this far (mm) forward of the eye group's mean
                    "apex": float((T[gr["left_eye"], 2].max() - T[gr["left_eye"], 2].mean()) * 1000)}
    return _C["sp"]


def readers(V: np.ndarray) -> dict:
    """The measures (mm) on GNM-frame vertices V (m)."""
    sp = _space()
    S, gr = sp["sets"], sp["gr"]
    V = V * 1000
    L = sp["WL"] @ V
    eL, eR = V[gr["left_eye"]].mean(0), V[gr["right_eye"]].mean(0)
    pog = V[S["pog"]].mean(0)
    cr = V[S["cranium"]]
    fh = V[S["forehead"]].mean(0)
    O = {k: V[ids].mean(0) for k, ids in sp["orb"].items()}     # both sides' mean (x cancels)
    ez, ey, nz = 0.5 * (eL[2] + eR[2]), 0.5 * (eL[1] + eR[1]), L[27, 2]
    wh = sp["w_hollow"]
    return {
        "pupils_apart": abs(eL[0] - eR[0]),
        "eyes_forward": 0.5 * (eL[2] + eR[2]) - L[27, 2],
        "eyes_height": 0.5 * (eL[1] + eR[1]) - L[33, 1],
        "brows_over_eyes": L[[19, 24], 1].mean() - 0.5 * (eL[1] + eR[1]),
        "forehead_forward": fh[2] - L[27, 2],
        "tip_forward": L[30, 2] - L[33, 2],
        # (orbit, 2026-10-11: against the NASION, was against the eyes: the muzzle's chain hung from the eye, so
        # mm:eyes_forward carried nose base, lips and chin forward with the eye and, in the face's own frame, pushed
        # the nasion and forehead back instead: on a fitted head the profile line left the picture's bridge)
        "subnasale_forward": L[33, 2] - nz,
        "upper_lip_forward": L[51, 2] - L[33, 2],
        "lower_lip_forward": L[57, 2] - L[51, 2],
        "chin_forward": pog[2] - L[57, 2],
        "philtrum_length": L[33, 1] - L[51, 1],
        "chin_length": L[57, 1] - L[8, 1],
        "nose_length": L[27, 1] - L[33, 1],
        "cheekbone_width": np.ptp(V[S["zyg"], 0]),
        "jaw_width": L[12, 0] - L[4, 0],
        "chin_width": L[10, 0] - L[6, 0],
        "mouth_width": L[54, 0] - L[48, 0],
        "nose_width": L[35, 0] - L[31, 0],
        "skull_width": np.ptp(cr[:, 0]),
        "skull_top": cr[:, 1].max() - L[27, 1],
        "skull_back": L[27, 2] - cr[:, 2].min(),
        "neck_width": np.ptp(V[S["neck"], 0]),
        "under_chin": L[8, 1] - V[S["under_chin"], 1].mean(),
        # the ORBIT (orbit, 2026-10-11): the rims round the eye, each against the nasion like the eye itself, so that
        # mm:eyes_forward is the EYE UNIT alone (ball, lids, lining) inside rims that stay
        "brow_ridge_forward": O["brow_ridge"][2] - nz,
        "side_rim_forward": O["side_rim"][2] - nz,
        "under_eye_forward": O["under_eye"][2] - nz,
        "brow_hollow": wh * O["platform"][2] + (1 - wh) * O["brow_ridge"][2] - O["sulcus"][2],
        # held, never moved: where the face sits in the head's frame (else a move may slide the face: the measures
        # above are all relative, and a slid face reads as a shifted profile against the picture)
        "_face_x": L[:, 0].mean(), "_face_y": L[:, 1].mean(), "_face_z": L[:, 2].mean(),
        # held, never moved: the lids stay ON the ball (a least-norm "eye forward" may otherwise push the ball through
        # them: our eyeball is seated on the lid landmarks), the opening and corners keep their place round the pupil,
        # and the profile line between the measured points (glabella, dorsum) stays on the picture's
        "_lid_up_z": O["margin_up"][2] - ez, "_lid_lo_z": O["margin_lo"][2] - ez, "_platform_z": O["platform"][2] - ez,
        "_canthi_z": L[[36, 39, 42, 45], 2].mean() - ez,
        "_lid_up_y": O["margin_up"][1] - ey, "_lid_lo_y": O["margin_lo"][1] - ey,
        "_canthus_in_x": 0.5 * ((L[42, 0] - eL[0]) - (L[39, 0] - eR[0])),
        "_canthus_out_x": 0.5 * ((L[45, 0] - eL[0]) - (L[36, 0] - eR[0])),
        "_glabella_z": V[gr["middle_brow_region"], 2].mean() - nz, "_dorsum_z": L[28:30, 2].mean() - nz,
    }


NAMES = ("pupils_apart", "eyes_forward", "eyes_height", "brows_over_eyes", "forehead_forward", "tip_forward",
         "subnasale_forward", "upper_lip_forward", "lower_lip_forward", "chin_forward", "philtrum_length",
         "chin_length", "nose_length", "cheekbone_width", "jaw_width", "chin_width", "mouth_width", "nose_width",
         "skull_width", "skull_top", "skull_back", "neck_width", "under_chin",
         "brow_ridge_forward", "side_rim_forward", "under_eye_forward", "brow_hollow")
ORBIT = ("eyes_forward", "brows_over_eyes", "brow_ridge_forward", "side_rim_forward", "under_eye_forward", "brow_hollow")
HELD = NAMES + ("_face_x", "_face_y", "_face_z", "_lid_up_z", "_lid_lo_z", "_platform_z", "_canthi_z", "_lid_up_y",
                "_lid_lo_y", "_canthus_in_x", "_canthus_out_x", "_glabella_z", "_dorsum_z")


def jacobian() -> np.ndarray:
    """(n readers, 170): mm per head comp (exact: the readers are linear in V up to the ptp / abs, linearised at GNM's
    template)."""
    if "J" not in _C:
        sp = _space()
        r0 = readers(sp["T"])
        J = np.zeros((len(HELD), 170))
        for k in range(170):
            r = readers(sp["T"] + sp["IB"][k] * 1e-3)
            J[:, k] = [(r[n] - r0[n]) / 1e-3 for n in HELD]
        _C["J"] = J
    return _C["J"]


def direction(name: str) -> np.ndarray:
    """`mm:<reader>`: the least-norm dc moving the reader +1 mm with every other reader held at 0 (170,)."""
    m = name[3:] if name.startswith("mm:") else name
    if m not in NAMES:
        raise ValueError(f"mm: one of {', '.join(NAMES)}")
    J = jacobian()
    i = NAMES.index(m)
    b = np.zeros(len(HELD))
    b[i] = 1.0
    return J.T @ np.linalg.solve(J @ J.T + 1e-6 * np.eye(len(J)), b)


# What each measure LOOKS like (an artist's phrase for + ; the view to read it in). The driving test (gnmdrive2): closing
# the 8 largest of these gaps passes 30 / 42 synthetic pairs (all 23: 40 / 42), against 19 / 42 for drivers picking
# macros / pc: moves from the phrase manual and 27 / 42 for the oracle's 10 best moves from that vocabulary.
SEE = {
    "pupils_apart": ("front", "the eyes are set further apart (irises doubled side by side in an overlay)"),
    "eyes_forward": ("profile", "the EYE UNIT (ball, lids, socket lining) stands further forward in its orbit: less "
                                "deep-set against the bridge, brow, cheek and side rim, which all stay"),
    "eyes_height": ("front", "the eyes sit higher above the nose base (a longer mid-face between eyes and nostrils)"),
    "brows_over_eyes": ("front", "the brows sit higher over the eyes (more lid space)"),
    "forehead_forward": ("profile", "the forehead stands further forward of the nasion (upright, full; - = sloping)"),
    "tip_forward": ("profile", "the nose tip projects further from the nose base (subnasale)"),
    "subnasale_forward": ("profile", "the nose base (and with it lips and chin: the whole muzzle) stands further "
                                     "forward of the nasion"),
    "upper_lip_forward": ("profile", "the upper lip (and the lower lip and chin under it) stands further forward of "
                                     "the nose base"),
    "lower_lip_forward": ("profile", "the lower lip (and the chin under it) stands further forward of the upper lip"),
    "chin_forward": ("profile", "the chin's front (pogonion) stands further forward of the lower lip"),
    "philtrum_length": ("front", "the upper lip is longer: the mouth sits lower under the nose"),
    "chin_length": ("front", "the chin is taller: its bottom sits lower under the lower lip"),
    "nose_length": ("front", "the nose is longer: its base sits lower under the nasion"),
    "cheekbone_width": ("front", "the face is wider at the cheekbones"),
    "jaw_width": ("front", "the jaw is wider at mouth level (jaw line, landmarks 4-12)"),
    "chin_width": ("front", "the chin is broader"),
    "mouth_width": ("front", "the mouth is wider corner to corner (total)"),
    "nose_width": ("front", "the nose is wider at the wings (total)"),
    "skull_width": ("front", "the skull is wider above the ears"),
    "skull_top": ("front", "the vault is taller: the crown sits higher over the nasion"),
    "skull_back": ("profile", "the back of the skull sits further back (a longer head)"),
    "neck_width": ("front", "the neck is thicker"),
    "under_chin": ("profile", "the line under the chin hangs lower below the chin's bottom (full, double chin; - = a "
                              "clean jaw-to-neck angle)"),
    "brow_ridge_forward": ("profile", "the brow ridge over the pupil (supraorbital rim) stands further forward: more "
                                      "overhang over the eye"),
    "side_rim_forward": ("profile", "the orbit's side rim (beside the outer corner) sits further forward: less of the "
                                    "eyeball shows from the side"),
    "under_eye_forward": ("profile", "the cheek's top under the eye (infraorbital rim) stands further forward (the "
                                     "cheek ahead of the cornea)"),
    "brow_hollow": ("3q", "the skin between brow and lid is more sunken behind the line from the lid to the brow ridge "
                          "(a hollow under the brow; - = full, flat)"),
}


def orbit(V: np.ndarray) -> dict:
    """The orbit as an artist reads it off a side view (mm, GNM-frame vertices V in m), each a difference of the
    measures: how far the corneal apex sits BEHIND the nasion, how far the brow ridge overhangs the apex, how far the
    apex stands ahead of the orbit's side rim (what an exophthalmometer reads, here on skin) and of the cheek under the
    eye, the brow's height over the pupil, the hollow under the brow."""
    r, ap = readers(V), _space()["apex"]
    a = r["eyes_forward"] + ap                      # the apex forward of the nasion (negative: behind it)
    return {"apex_behind_nasion": -a, "brow_over_apex": r["brow_ridge_forward"] - a,
            "apex_ahead_of_side_rim": a - r["side_rim_forward"], "apex_ahead_of_cheek": a - r["under_eye_forward"],
            "brows_over_eyes": r["brows_over_eyes"], "brow_hollow": r["brow_hollow"]}


# orbit()'s rows as combinations of the measures (a ruler's table: each row's gap and error from the measures')
ORBIT_SEEN = {"apex_behind_nasion": {"eyes_forward": -1.0},
              "brow_over_apex": {"brow_ridge_forward": 1.0, "eyes_forward": -1.0},
              "apex_ahead_of_side_rim": {"eyes_forward": 1.0, "side_rim_forward": -1.0},
              "apex_ahead_of_cheek": {"eyes_forward": 1.0, "under_eye_forward": -1.0},
              "brows_over_eyes": {"brows_over_eyes": 1.0}, "brow_hollow": {"brow_hollow": 1.0}}
# the forward measures are a CHAIN (each is taken against the one above it), so a link carries everything below it
CHAIN = ("subnasale_forward", "upper_lip_forward", "lower_lip_forward", "chin_forward")


def sd() -> dict:
    """Each measure's population sd in mm (GNM's identity prior: comps ~ N(0, 1))."""
    J = jacobian()
    return {n: float(np.linalg.norm(J[i])) for i, n in enumerate(NAMES)}


def gaps(Va: np.ndarray, Vb: np.ndarray, bias: np.ndarray | None = None) -> list[dict]:
    """The RULER: every measure on head a (current) and head b (target), GNM-frame vertices (m): b - a in mm and in
    population sd, largest (in sd) first. `bias` (len NAMES, mm) is added to b's readings (a photo reader's error)."""
    ra, rb, s = readers(Va), readers(Vb), sd()
    out = []
    for i, n in enumerate(NAMES):
        g = float(rb[n] - ra[n]) + (0.0 if bias is None else float(bias[i]))
        out.append({"measure": n, "current": float(ra[n]), "gap": g, "sd": g / s[n], "view": SEE[n][0], "see": SEE[n][1]})
    out.sort(key=lambda r: -abs(r["sd"]))
    return out


def gaps_text(rows: list[dict], top: int = 0, floor: float = 0.0) -> str:
    """The ruler as text: one line per measure, the move that closes it."""
    out = ["measure            target - current     move that closes it          what + looks like"]
    for r in rows[: top or None]:
        if abs(r["gap"]) < floor:
            continue
        mv = '"mm:%s": %+.1f' % (r["measure"], r["gap"])
        out.append(f"{r['measure']:18s} {r['gap']:+6.1f} mm ({r['sd']:+.1f} sd)   {mv:28s} [{r['view']}] {r['see']}")
    return "\n".join(out)
