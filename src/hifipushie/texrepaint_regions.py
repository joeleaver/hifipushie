"""Texture repaint: REGIONS and MATERIALS. The generated texture and the concept views are each read as "which
material is this" (nearest named colour, lightness half-weighted so baked shading doesn't flip a cream texel to grey),
the votes are smoothed ON THE SURFACE (texrepaint_surface.Grid: across UV seams, never across empty UV space), and
the concept outvotes the texture where a view sees the texel squarely. Where they disagree in a cluster bigger than a
speck, that's a CONTRADICTION: reported with where it is (front / back / left / right, height), its area and which way
round (texture has X where the art shows Y), and fixed by the concept. Texels no view sees keep the texture's reading
(said so in the report: "decided plausibly, unseen in the art").

materials: [{"name": "clay_cream", "colour": [r, g, b]}, ...]: the painter's list, colours sampled from the concept
(texrepaint_palette proposes them). Optional per material: "rough" (0-1), "kind" (clay | gloss | horn | metal | wood |
paint | flat: the detail it gets), "paint" ([r,g,b]: the base colour to paint, else measured from the concept),
"keep_texture": true (its texels keep the generated colour, e.g. the eyes' painted detail), "zones": [[z0, z1], ...]
(height fractions, 0 = lowest point: the material exists only there, e.g. pupils [[0.7, 1]], hooves [[0, 0.1]]: a
painter knows dark shading under the body is not a pupil)."""
from __future__ import annotations

import numpy as np

from .texrepaint_concept import lab
from .texrepaint_surface import Grid, Texels


def allowed(pos: np.ndarray, materials: list[dict], lo: float, hi: float) -> np.ndarray:
    """(n, K) where each material may be (its height zones)"""
    f = (pos[:, 2] - lo) / max(hi - lo, 1e-9); out = np.ones((len(pos), len(materials)), bool)
    for k, m in enumerate(materials):
        if m.get("zones"):
            out[:, k] = np.any([(f >= a) & (f <= b) for a, b in m["zones"]], 0)
    return out


def classify(rgb: np.ndarray, materials: list[dict], l_weight: float = 0.5, ok=None):
    """nearest material per colour (Lab, lightness down-weighted) among the allowed ones (ok (n, K)); also the
    margin (2nd - 1st distance)"""
    C = lab(np.array([m["colour"] for m in materials], np.float32)) * [l_weight, 1, 1]
    L = lab(rgb.astype(np.float32)) * [l_weight, 1, 1]
    d = np.linalg.norm(L[:, None, :] - C[None], axis=-1)
    if ok is not None:
        d = np.where(ok, d, 1e9)
    o = np.argsort(d, 1)
    return o[:, 0], np.take_along_axis(d, o[:, 1:2], 1)[:, 0] - np.take_along_axis(d, o[:, :1], 1)[:, 0]


def texel_area(surf, tx: Texels) -> np.ndarray:
    """world area each texel covers (m^2): triangle 3D area / its UV area / texels per UV unit"""
    P = surf.P[tx.tri]; U = surf.UV[tx.tri]
    a3 = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
    d1, d2 = U[:, 1] - U[:, 0], U[:, 2] - U[:, 0]
    a2 = 0.5 * np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0])
    return (a3 / np.maximum(a2, 1e-12) / tx.res ** 2).astype(np.float32)


def where(p, centre, size) -> str:
    """a painter's words for a place on the model"""
    rel = (p - centre) / np.maximum(size, 1e-6)
    side = "back" if rel[1] > 0.15 else "front" if rel[1] < -0.15 else ""
    lr = "its left (+x)" if rel[0] > 0.12 else "its right (-x)" if rel[0] < -0.12 else "centre"
    h = rel[2] + 0.5
    band = "head/top" if h > 0.75 else "upper body" if h > 0.5 else "lower body" if h > 0.25 else "legs/feet"
    return f"{band}, {side + ' ' if side else ''}{lr}".strip()


def fuse(tx: Texels, tex_rgb, con_rgb, con_w, materials, sigma: float, voxel: float, trust=None,
         authority: float = 3.0, min_area: float = 4e-5, area=None):
    """the region reading: per texel probabilities (n, K) after the surface blur, plus the contradictions list.
    trust: per-texel weight of the generated texture (bake coverage, 0 where invented / no ray hit)."""
    K = len(materials); n = len(tx.idx)
    ok = allowed(tx.pos, materials, tx.pos[:, 2].min(), tx.pos[:, 2].max())
    tl, _ = classify(tex_rgb, materials, ok=ok)
    seen = con_w > 0.05
    cl = np.full(n, -1); cl[seen], _ = classify(con_rgb[seen], materials, ok=ok[seen])
    trust = np.ones(n, np.float32) if trust is None else trust.astype(np.float32)
    g = Grid(tx.pos, voxel)
    Pt = np.zeros((n, K), np.float32); Pc = np.zeros((n, K), np.float32); Pf = np.zeros((n, K), np.float32)
    wt_tot = None; wc_tot = None
    for k in range(K):
        a = (tl == k).astype(np.float32); b = (cl == k).astype(np.float32)
        Pt[:, k], wt_tot = g.smooth(a, sigma, trust + 1e-3)
        Pc[:, k], wc_tot = g.smooth(b, sigma, con_w * seen + 1e-6)
        Pf[:, k], _ = g.smooth(a * trust + authority * b * con_w, sigma, trust + authority * con_w + 1e-4)
    for P in (Pt, Pc, Pf):
        P /= np.maximum(P.sum(1, keepdims=True), 1e-6)
    keep_tex = np.array([bool(m.get("keep_texture")) for m in materials])
    # contradictions: where the concept sees squarely AND both readings are confident AND they differ
    conf_seen = g.smooth(con_w, sigma)[0] > 0.25
    t_arg, c_arg = Pt.argmax(1), Pc.argmax(1)
    dis = conf_seen & (Pt.max(1) > 0.6) & (Pc.max(1) > 0.6) & (t_arg != c_arg) & ~keep_tex[t_arg] & ~keep_tex[c_arg]
    area = np.full(n, 1e-6, np.float32) if area is None else area
    lo, hi = tx.pos.min(0), tx.pos.max(0); ctr, size = (lo + hi) / 2, hi - lo
    found = []
    clusters = []
    for a in range(K):   # one kind of disagreement at a time (texture a where the art shows b)
        for b in range(K):
            sel = dis & (t_arg == a) & (c_arg == b)
            if sel.sum() < 20:
                continue
            lab_, nlab = g.components(sel)
            clusters += [lab_ == j for j in range(1, nlab + 1)]
    for m in clusters:
        A = float(area[m].sum())
        if A < min_area:
            continue
        tm = np.bincount(t_arg[m], minlength=K).argmax(); cm = np.bincount(c_arg[m], minlength=K).argmax()
        p = tx.pos[m].mean(0)
        found.append({"where": where(p, ctr, size), "at": [round(float(x), 3) for x in p],
                      "area_cm2": round(A * 1e4, 1), "texture_has": materials[tm]["name"],
                      "concept_shows": materials[cm]["name"], "fixed": f"painted {materials[cm]['name']} (concept)",
                      "texels": int(m.sum())})
    found.sort(key=lambda f: -f["area_cm2"])
    unseen = ~(g.smooth(con_w, sigma)[0] > 0.05)
    return {"P": Pf, "Pt": Pt, "Pc": Pc, "tex_label": tl, "con_label": cl, "contradictions": found,
            "unseen": unseen, "disagree": dis, "grid": g}


def summary(tx: Texels, R: dict, materials, area) -> dict:
    lab_ = R["P"].argmax(1); A = area.sum()
    out = {}
    for k, m in enumerate(materials):
        s = lab_ == k
        out[m["name"]] = {"share": round(float(area[s].sum() / A), 3),
                          "unseen_by_art": round(float(area[s & R["unseen"]].sum() / max(area[s].sum(), 1e-12)), 2)}
    return {"materials": out, "unseen_share": round(float(area[R["unseen"]].sum() / A), 3),
            "contradictions": len(R["contradictions"])}
