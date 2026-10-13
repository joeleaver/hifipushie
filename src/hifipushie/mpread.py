"""MediaPipe's face mesh as ABSOLUTE reads of GNM's surface (readmix, 2026-10-13; docs/notes/readmix.md).

MediaPipe's Face Landmarker (Apache 2.0) gives 478 points. Until now 68 of them were used as DIFFERENTIAL anchors (the
detector on the picture minus the detector on the model's own clay render). Here each point has a learned
CORRESPONDENCE: the GNM surface point (a triangle's three GNM vertex ids + barycentric weights) it tracks, with its bias
and scatter by the head's turn, learned on ~7,000 dressed synthetic renders with known vertex positions
(spikes/readmix/mpcorr.py -> mp_gnm.json, with provenance) and then MEASURED on photographs of scanned heads
(spikes/readmix/gmix.py: the HSRD-100 rig pictures against the scan-fitted GNM through the rig's cameras). That
real-photo table decides which FEATURES are read from which turn and at what sigma (MIX): the lip outline and seam, the
mouth corners, the nostril base / alar points, the eye contours, the nasal bridge; NOT the face oval (MediaPipe draws
a generic jaw) and not the brows.

`obs(head, view, P)` -> the solve's observations (type "mp"): per point and axis, (the detector's pixel - its learned
bias - the model's surface point through the view's camera) in mm, moving with the surface point.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np

DATA = Path(__file__).with_name("mp_gnm.json")

# MediaPipe's own point sets (canonical face mesh ids)
LIP_OUTER = (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185)
LIP_INNER = (78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191)
EYE_L = (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466)
EYE_R = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246)
BROW_L = (276, 283, 282, 295, 285, 300, 293, 334, 296, 336)
BROW_R = (46, 53, 52, 65, 55, 70, 63, 105, 66, 107)
ALAR = (129, 358, 98, 327, 64, 294, 48, 278, 219, 439, 49, 279, 102, 331, 240, 460, 235, 455, 59, 289, 75, 305, 60, 290, 99, 328, 97,
        326, 2, 94, 141, 370, 242, 462, 20, 250, 79, 309, 166, 392, 218, 438, 237, 457, 239, 459, 238, 458, 241, 461, 125, 354, 44, 274, 19)
TIP = (1, 4, 5, 45, 275, 220, 440, 51, 281, 195, 3, 248, 115, 344, 131, 360, 134, 363, 198, 420, 236, 456)
BRIDGE = (6, 197, 168, 122, 351, 196, 419, 174, 399, 188, 412, 114, 343, 245, 465, 193, 417)
COMMISSURES = (61, 291, 78, 308)
# the nose's own reads, named (the solve's reply): MediaPipe point pairs / points
NOSE_READS = {"alar width": (129, 358), "nostril base": (98, 327), "alar wings": (64, 294), "tip": (1, 4), "subnasale": (2, 94), "bridge": (6, 168)}


def feature(mp: int, set_: str = "", region: str = "") -> str:
    """The FEATURE a MediaPipe point reads (finer than GNM's regions): the mix is per feature."""
    if mp in COMMISSURES:
        return "commissures"
    if mp in LIP_OUTER:
        return "vermilion border"
    if mp in LIP_INNER:
        return "lip seam"
    if mp in EYE_L or mp in EYE_R:
        return "eye contour"
    if mp in BROW_L or mp in BROW_R:
        return "brow line"
    if set_ == "oval":
        return "face oval"
    if mp in ALAR:
        return "alar / nostril base"
    if mp in TIP:
        return "nose tip / dorsum"
    if mp in BRIDGE:
        return "nasal bridge"
    return {"lips": "lip surface", "mouth": "round the mouth", "nose": "nose other", "lids": "lids other", "eyes": "orbit",
            "brows": "brow region", "chin": "chin", "cheeks": "cheeks", "forehead": "forehead"}.get(region, region or "other")


# THE MIX: per-axis sigma in mm by feature and by how far the head is turned from the camera (None = not read there).
# From the real-photo table (docs/notes/readmix.md "## Step 2": two HSRD-100 heads, rig photographs against the scan-fitted
# GNM through the rig's cameras, the error left after the detector's own 2D similarity per view, since the solve's cameras
# are free): a feature is read where that error is under ~1.6 mm per axis, at that error.
#   READ: eye contours (0.77 front, 0.94 at 19-22 deg; 1.6 at 44: no), mouth corners, lip seam, vermilion border (1.6 / 1.75
#         against a truth whose own border slides: by eye MediaPipe's border is ON the lip's edge), the nasal bridge.
#   NOT READ: the ALAR / NOSTRIL / TIP points: 1.2-1.7 mm rms but BIASED WIDE on photographs (alar width +5.5 and +2.4 mm,
#         nostril base +4.1 / +4.6 on the two heads: MediaPipe draws a more average nose 2 mm low); the face oval (3.7-4.6:
#         a generic jaw); brows (2.4); chin, cheeks, forehead (1.9-3.3).
TURNS = (15.0, 35.0, 55.0)       # |turn| bins: < 15 front, < 35 shallow 3/4, < 55 3/4; beyond: MediaPipe is not read
MIX: dict = {"eye contour": (0.9, 1.0, None), "commissures": (1.1, 1.4, None), "lip seam": (1.4, 1.5, 1.6),
             "vermilion border": (1.5, 1.7, None), "nasal bridge": (1.5, 1.5, None)}
NEFF = 16                        # a view's MediaPipe reads count as this many independent ones: one network regresses the whole
#                                  mesh, neighbours err together (the participation ratio of its residuals' covariance on 2,400
#                                  near-frontal renders: 16 for the inner face's 864 reads, 6 for the lips' 80, 5.5 for the eyes' 64)
PX = 0.6                         # picture px: the detector's own scatter on a small face (as face_ruler.LM_PX)
BIAS = False                     # the learned bias by yaw (mp_gnm.json "bins") taken out of each read: on the real photographs it did
#                                  not help the features read here (lip seam 1.53 -> 1.68, eye contour 1.07 -> 1.07): off
ENABLED = True                   # reference_views(mp=None) takes this


@functools.lru_cache(maxsize=1)
def table() -> dict:
    """The stored correspondence: {"points": [{"mp", "tri" (3 GNM vertex ids), "w", "set", "region", "feature", "bins"}],
    "yaw_bins", "provenance"}."""
    d = json.loads(DATA.read_text())
    for p in d["points"]:
        p["feature"] = feature(int(p["mp"]), p.get("set", ""), p.get("region", ""))
    return d


def available() -> bool:
    return DATA.exists()


def cam_yaw(cam: dict) -> float:
    """The camera's place round the head in the correspondence's convention: degrees, + = the camera on the subject's
    LEFT (+X), 0 = in front."""
    from . import humanfit
    d = -humanfit._cam_rot(cam).T @ np.array([0.0, 0.0, 1.0])          # from the head toward the camera, world
    return float(np.degrees(np.arctan2(d[0], -d[1])))


def bias(pt: dict, yaw: float) -> tuple:
    """(the learned bias (x, y) mm in the picture, the bin's synthetic per-axis rms mm | None) of a point at this yaw."""
    yb = table()["yaw_bins"]
    for b0, b1 in zip(yb[:-1], yb[1:]):
        k = f"{b0}:{b1}"
        if b0 <= yaw < b1 and k in pt["bins"]:
            return np.asarray(pt["bins"][k]["bias"], float), float(pt["bins"][k]["rms"])
    return np.zeros(2), None


def sigma(feat: str, turn: float, mix: dict | None = None):
    m = (MIX if mix is None else mix).get(feat)
    if not m:
        return None
    a = abs(float(turn))
    for t, s in zip(TURNS, m):
        if a < t:
            return s
    return None


def obs(head: dict, view: dict, P, mix: dict | None = None, neff: float | None = None) -> list:
    """The view's MediaPipe reads. P: (478, 2) the detector's points on the picture (picture px)."""
    from . import face_ruler as fr
    if P is None or "gid" not in head or not available():
        return []
    cam = view["cam"]
    g2m = fr._gnm_to_model(head)
    yaw, turn = cam_yaw(cam), abs(fr.view_yaw(cam))
    out = []
    V = np.asarray(head["V"], float)
    for pt in table()["points"]:
        sg = sigma(pt["feature"], turn, mix)
        if sg is None:
            continue
        idx = [g2m.get(int(g), -1) for g in pt["tri"]]
        if min(idx) < 0:
            continue
        w = np.asarray(pt["w"], float)
        X = w @ V[idx]
        b = bias(pt, yaw)[0] if BIAS else np.zeros(2)
        Jp, mm1 = fr._proj_jac(cam, head, idx, w)
        _, q = fr._cam_points(cam, X[None])
        p = np.asarray(P[int(pt["mp"])], float)
        s_ = float(np.hypot(sg, PX * mm1))
        if view.get("style") == "photo" and not view.get("render") and pt["feature"] in ("vermilion border", "lip seam", "commissures"):
            b = b + np.array([0.0, fr.lip_bias("mp", f"mp{pt['mp']}") if abs(yaw) < 25 else 0.0])
        for ax in (0, 1):
            out.append({"type": "mp", "view": view["kind"], "name": f"mp{pt['mp']}.{'xy'[ax]}", "o": float(p[ax] - q[0, ax]) * mm1 - float(b[ax]),
                        "J": Jp[ax] * mm1, "sig": s_, "p": list(map(float, q[0])), "q": list(map(float, p)), "X": list(map(float, X)),
                        "feature": pt["feature"], "mp": int(pt["mp"]), "mm1": mm1})
    ne = float(NEFF if neff is None else neff)
    if ne and len(out) > 2 * ne:
        k_ = float(np.sqrt(len(out) / (2 * ne)))
        for ob in out:
            ob["sig"] *= k_
    return out


def nose_lines(obs_: list, resid=None) -> list:
    """The nose's own reads, said in the reply: per named read (alar width, nostril base, tip ..) the picture's value
    against the model's, in mm in the picture (a width: the distance between the pair; a point: its offset)."""
    by = {}
    for ob in obs_:
        if ob.get("type") == "mp":
            by.setdefault((ob["view"], ob["mp"]), {})[ob["name"][-1]] = ob
    out = []
    for vw in sorted({k[0] for k in by}):
        parts = []
        for nm, (a, b) in NOSE_READS.items():
            A, B = by.get((vw, a)), by.get((vw, b))
            if not A or not B or len(A) < 2 or len(B) < 2:
                continue
            pa, pb = np.array(A["x"]["p"]), np.array(B["x"]["p"])
            oa, ob_ = np.array([A["x"]["o"], A["y"]["o"]]), np.array([B["x"]["o"], B["y"]["o"]])    # mm, the learned bias taken out
            k = 0.5 * (A["x"]["mm1"] + B["x"]["mm1"])
            if nm in ("alar width", "nostril base", "alar wings"):
                u = (pb - pa) / max(np.linalg.norm(pb - pa), 1e-9)
                wm = float(np.linalg.norm(pa - pb) * k)
                parts.append(f"{nm} {wm + float((ob_ - oa) @ u):.1f} mm in the picture (model {wm:.1f})")
            else:
                d = 0.5 * (oa + ob_)
                parts.append(f"{nm} {d[0]:+.1f}, {d[1]:+.1f} mm (x right, y down) off the model's")
        if parts:
            out.append(f"NOSE READS in the {vw} picture (MediaPipe's nose points through the learned correspondence): " + "; ".join(parts))
    return out
