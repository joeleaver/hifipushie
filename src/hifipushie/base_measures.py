"""The head a spec gets and what is measured on it: head_of, posed and plane measures, eye size and opening,
landmark and vermilion joints. Part of base (base.py has the overview)."""
from __future__ import annotations

import json

import numpy as np

from . import base
from . import base as base_mod
from . import retopo
from .base import source, template_joints
from .base_gnm_head import gnm_head
from .base_identity import _gnm_data
from .base_imls import _unit

def head_of(s: dict, base: dict):
    """The grafted head (gnm_head) for a base with "head": {"source": "gnm", ...}, placed on the template's eye
    midpoint (the head joint's ride) and the neck -> head direction; None without one. Cached."""
    if (base.get("body") or {}).get("source") == "human":  # one human mesh: the head is part of the body's mesh
        from . import onemesh_head
        return onemesh_head.head(s, base)
    head = base.get("head")
    if not head:
        return None
    if head.get("source", "gnm") != "gnm":
        raise ValueError('base head: {"source": "gnm", ...} (the only head source so far)')
    from . import headfit
    if headfit.applies(base):  # the body's age / sex / weight shape the head too (headfit.py)
        head = headfit.follow(base, head)
    tpl = source(base)
    tj = template_joints(base)
    J = s["joints"]
    eb = np.array((tpl["face"].get("eyeball") or {}).get("centre") or tpl["face"]["landmarks"]["eye.L"]) * [0, 1, 1]
    mid = np.array(J["head"]["pos"], float) + eb - np.array(tj["head"]["pos"])
    up = np.array(J["head"]["pos"], float) - np.array(J["neck"]["pos"], float)
    up0 = np.array(tj["head"]["pos"]) - np.array(tj["neck"]["pos"])
    up = retopo._rot_between(_unit(up0), _unit(up)) @ np.array([0, 0, 1.0])
    st = base.get("style") or {}
    if st:  # the stylisation layer, reusable across characters: bigger eyes, a bigger head, simpler planes
        head = {**head, "eyes": float(head.get("eyes", 1.0)) * float(st.get("eyes", 1.0)),
                "scale": float(head.get("scale", 1.4)) * float(st.get("head", 1.0)),
                "simplify": float(head.get("simplify", 0.0)) + float(st.get("simplify", 0.0)),
                **({"shape": {**st["shape"], **(head.get("shape") or {})}} if st.get("shape") else {}),
                **({"simplify_keep": st["simplify_keep"]} if "simplify_keep" in st and "simplify_keep" not in head
                   else {})}
    key = ("head", json.dumps([head, mid.round(5).tolist(), up.round(5).tolist()], sort_keys=True))
    if key not in base_mod._CACHE:
        base_mod._CACHE[key] = gnm_head(head, mid, up)
        if headfit.applies(base):
            base_mod._CACHE[key]["room"] = True
            base_mod._CACHE[key]["own_neck"] = bool(head.get("own_neck"))
    return base_mod._CACHE[key]


def posed_measures(head: dict) -> dict:
    """FIT_KEYS measured on the built head (pose, eyes and scale applied), in interocular units, world Z up."""
    lm = np.asarray(head["lm68"])
    e0, e1 = head["eyes"]
    io = abs(e0[0] - e1[0])
    ey = 0.5 * (e0[2] + e1[2])
    z = lm[:, 2]
    x = lm[:, 0]
    vals = [x[16] - x[0], x[12] - x[4], x[10] - x[6], ey - z[8], ey - z[57], ey - z[33], x[35] - x[31],
            x[54] - x[48], ey - 0.5 * (z[62] + z[66])]
    return {k: round(float(abs(v) / io), 3) for k, v in zip(base.FIT_KEYS, vals)}


def plane_measures(head: dict) -> dict:
    """How designed the head's planes are, on the built head mesh (world, Z up, facing -Y):
    corner_radius_*_mm: the tightest turn (mm) of the horizontal section between the front (straight ahead) and the
    side (straight out), 30-80 deg round from the front about the jaw contour's centre, at brow / cheekbone / mouth
    height, both sides averaged (a real head ~42-50 mm; a stylised front/side corner ~30); muzzle_mm: how far the
    upper lip stands in front of the cheeks beside the nose wings (GNM ~12 mm: a muzzle)."""
    from scipy.ndimage import gaussian_filter1d
    V, lm = head["verts"], np.asarray(head["lm68"])
    e0, e1 = head["eyes"]
    io = abs(e0[0] - e1[0])
    xc, yc = 0.5 * (lm[0][0] + lm[16][0]), 0.5 * (lm[0][1] + lm[16][1]) + 0.01

    def corner(z0):
        P = V[np.abs(V[:, 2] - z0) < 0.0015][:, :2] - [xc, yc]
        th = np.degrees(np.arctan2(np.abs(P[:, 0]), -P[:, 1]))
        r = np.linalg.norm(P, axis=1)
        out = []
        for side in (1, -1):
            s = np.sign(P[:, 0]) == side
            bins = np.arange(0, 100, 2.0)
            R = np.array([r[s & (th >= b) & (th < b + 2)].max() if (s & (th >= b) & (th < b + 2)).any() else np.nan
                          for b in bins])
            ok = ~np.isnan(R)
            R = gaussian_filter1d(np.interp(bins, bins[ok], R[ok]), 1.5)
            t = np.radians(bins + 1)
            dr = np.gradient(R, t)
            ddr = np.gradient(dr, t)
            k = np.abs(R ** 2 + 2 * dr ** 2 - R * ddr) / (R ** 2 + dr ** 2) ** 1.5
            out.append(1000 / k[(bins >= 30) & (bins <= 80)].max())
        return round(float(np.mean(out)), 1)
    mx = 0.5 * (e0[0] + e1[0])
    lip = V[(np.abs(V[:, 0] - mx) < 0.004) & (np.abs(V[:, 2] - lm[51][2]) < 0.003), 1].min()
    ck = [V[(np.abs(V[:, 0] - mx - s * 0.032) < 0.003) & (np.abs(V[:, 2] - lm[33][2]) < 0.003), 1].min()
          for s in (-1, 1)]
    return {"corner_radius_brow_mm": corner(lm[24][2]),
            "corner_radius_cheekbone_mm": corner(0.5 * (e0[2] + e1[2]) - 0.35 * io),
            "corner_radius_mouth_mm": corner(lm[48][2]), "muzzle_mm": round(1000 * float(np.mean(ck) - lip), 1)}


def ala_width(head: dict) -> float:
    """The nose's width across the outer alar wings over the interocular (eye centres), on the built head mesh: the
    nose region's most lateral points in a band from the nostril base (lm31/35) to 1 cm above it. What reads as the
    nose's width in a picture; GNM's lm31-35 (fit key nose_width) sit at the nostril base, inside the wings."""
    g = _gnm_data()
    skin = g["skin"]
    V = np.asarray(head["verts"])
    ns = int(skin.sum())
    lm = np.asarray(head["lm68"])
    e0, e1 = head["eyes"]
    io = abs(e0[0] - e1[0])
    s = io / 0.063  # the band in the head's own scale
    za = 0.5 * (lm[31][2] + lm[35][2])
    nose = np.flatnonzero(g["groups"]["nose_region"][skin] > 0.5)
    if head.get("skin_index") is not None:  # zipped lips dropped vertices (_zip_lips)
        nose = head["skin_index"][nose]
        nose = nose[nose >= 0]
    z = V[nose, 2]
    iv = nose[(z > za - 0.002 * s) & (z < za + 0.010 * s)]
    return float((V[iv, 0].max() - V[iv, 0].min()) / io)


def eye_size(head: dict) -> dict:
    """The eye opening's size from its lid landmarks seen from the front, over the interocular (eye centres): width
    corner to corner (lm 36-39 / 42-45), height upper lid margin to lower (37-41, 38-40 / 43-47, 44-46), both eyes'
    mean. Landmarks, so a reference photo measures the same way (corners and lid margins traced; eye_opening's
    eyeball-in-front-of-skin width leaves the corners out)."""
    lm = np.asarray(head["lm68"], float)
    e0, e1 = (np.asarray(e, float) for e in head["eyes"])
    fwd = _unit(np.asarray(head["forward"], float))
    P = lm - np.outer(lm @ fwd, fwd)  # onto the front plane
    io = float(np.linalg.norm((e0 - e1) - ((e0 - e1) @ fwd) * fwd))
    w = np.mean([np.linalg.norm(P[36] - P[39]), np.linalg.norm(P[42] - P[45])])
    h = np.mean([np.linalg.norm(P[a] - P[b]) for a, b in ((37, 41), (38, 40), (43, 47), (44, 46))])
    return {"eye_w_over_io": round(float(w / io), 3), "eye_h_over_io": round(float(h / io), 3)}


def eye_opening(head: dict, cell: float = 0.0005) -> list:
    """Each eye's opening as seen from the front: where the eyeball stands in front of the skin (the skin runs on into
    the socket behind the lids, so the opening has no edge loop to measure). Per eye {"w", "h", "top", "bottom"} in
    mm: the width, the height at the eye centre's column and how far its top and bottom lie from the centre (the
    iris is centred there: top/bottom against the iris radius say how much of it the lids cover)."""
    from scipy import ndimage
    W, r = head["verts"], head["eye_r"]
    fwd = _unit(np.asarray(head["forward"], float))
    up = np.array([0.0, 0.0, 1.0])
    side = _unit(np.cross(up, fwd))
    up = np.cross(fwd, side)
    out = []
    for c in head["eyes"]:
        d = W - c
        u, v, depth = d @ side, d @ up, d @ fwd  # depth: toward the viewer
        m = (np.abs(u) < 0.035) & (np.abs(v) < 0.03) & (depth > -0.005)
        iu, iv = np.floor(u[m] / cell).astype(int), np.floor(v[m] / cell).astype(int)
        n = int(r / cell) + 1
        front = np.full((2 * n + 3, 2 * n + 3), -9.0)
        ok = (np.abs(iu) <= n) & (np.abs(iv) <= n)
        np.maximum.at(front, (iu[ok] + n + 1, iv[ok] + n + 1), depth[m][ok])
        front = ndimage.maximum_filter(front, size=3)[1:-1, 1:-1]  # vertex gaps: a cell sees its neighbours' skin
        g = (np.arange(-n, n + 1) + 0.5) * cell
        q = r * r - g[:, None] ** 2 - g[None, :] ** 2
        ball = np.where(q > 0, np.sqrt(np.maximum(q, 0)), -np.inf)
        lab, _ = ndimage.label((ball > front) & (q > 0))
        if lab[n, n] == 0:
            out.append(None)
            continue
        xs, zs = np.nonzero(lab == lab[n, n])
        col = zs[np.abs(xs - n) <= 2]
        out.append({"w": round(float((xs.max() - xs.min() + 1) * cell * 1000), 1),
                    "h": round(float((col.max() - col.min() + 1) * cell * 1000), 1),
                    "top": round(float((col.max() - n + 1) * cell * 1000), 1),
                    "bottom": round(float((n - col.min()) * cell * 1000), 1)})
    return out


def _landmark_joints(head: dict) -> dict:
    lm = head["lm68"]
    out = {}
    for name, i in base.LANDMARKS.items():
        p = lm[i]
        out[name] = {"pos": [round(float(x), 4) for x in p], "r": 0.005}
    for name in ("lm_lid_upper.L", "lm_lid_lower.L"):
        i, j = (43, 44) if "upper" in name else (46, 47)
        out[name] = {"pos": [round(float(x), 4) for x in 0.5 * (lm[i] + lm[j])], "r": 0.004}
    # the lid margins' own points (the lash lines run corner -> these -> corner: skin_zones.zone lash_upper / lash_lower)
    for name, i in (("lm_lid_upper_in.L", 43), ("lm_lid_upper_out.L", 44), ("lm_lid_lower_in.L", 47),
                    ("lm_lid_lower_out.L", 46)):
        out[name] = {"pos": [round(float(x), 4) for x in lm[i]], "r": 0.003}
    out["lm_lip_seam"] = {"pos": [round(float(x), 4) for x in 0.5 * (lm[62] + lm[66])], "r": 0.003}  # between the lips
    out.update(_vermilion_joints(head))
    return out


def _vermilion_edges() -> dict:
    """GNM's lips' outline edges (its raw ids, right corner -> left, VERM_N each): the upper / lower vermilion's outer
    border (the upper_lip / lower_lip groups' edge against the skin: the 68 landmarks 48-59 lie on it, but seven
    chords cut the Cupid's bow and the corners off) and the inner edges (the contact ring's upper / lower halves)."""
    if "verm_edges" in base._CACHE:
        return base._CACHE["verm_edges"]
    from . import faceslide_mouth
    g = _gnm_data()
    X = np.asarray(g["template_vertex_positions"], float)
    ext = np.asarray(g["groups"]["skin_exterior"]) > 0.5
    Q = np.asarray(g["quads"])
    e = np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]]
    out = {}
    for key, grp in (("u", "upper_lip"), ("l", "lower_lip")):
        m = (np.asarray(g["groups"][grp]) > 0.5) & ext
        edge = np.unique(e[m[e[:, 0]] & ~m[e[:, 1]] & ext[e[:, 1]] & np.asarray(g["skin"], bool)[e[:, 1]], 0])
        out[key] = edge[np.argsort(X[edge, 0])]
    R = faceslide_mouth._lip_rings()
    C = R["rings"][R["contact"]]
    x = X[C, 0]
    a, b = X[C[np.argmin(x)]], X[C[np.argmax(x)]]
    side = R["upper"][C]  # (GNM's own upper_lip / lower_lip groups)
    out["iu"], out["il"] = C[side][np.argsort(X[C[side], 0])], C[~side][np.argsort(X[C[~side], 0])]
    # VERM_N samples of each by index along x (the edges are single-valued enough in x for an outline)
    base._CACHE["verm_edges"] = {k: v[np.round(np.linspace(0, len(v) - 1, base.VERM_N)).astype(int)] for k, v in out.items()}
    return base._CACHE["verm_edges"]


def _vermilion_joints(head: dict) -> dict:
    """Joints verm_<u|l|iu|il><i> on the lips' outline edges (_vermilion_edges), at this head's vertices: what the skin's
    lip zones are drawn through on a GNM head (skin.OUTLINES_DENSE). {} when the head's vertices aren't GNM's skin."""
    g = _gnm_data()
    skin_ids = np.flatnonzero(g["skin"])
    W = np.asarray(head.get("verts", []), float)
    if head.get("skin_index") is not None or len(W) != len(skin_ids):
        return {}  # (zipped lips renumber the skin: the 68-landmark outlines then)
    row = np.full(len(g["skin"]), -1)
    row[skin_ids] = np.arange(len(skin_ids))
    out = {}
    for k, ids in _vermilion_edges().items():
        r = row[ids]
        if (r < 0).any():
            return {}
        for i, p in enumerate(W[r]):
            out[f"verm_{k}{i:02d}"] = {"pos": [round(float(x), 5) for x in p], "r": 0.001}
    return out
