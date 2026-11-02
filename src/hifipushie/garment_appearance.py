"""Step 9a, APPEARANCE: a garment's material painted on its FLAT PATTERN (tooling run T14; docs/state/garment_export.md).

The export's UVs are the pattern (garment_export: every piece's flat layout packed into one square at pattern scale), so
everything a tailor knows in pattern coordinates paints there directly. Layers, in order, each with its amount:
  base       the cloth's colour (step 0's reading, sampled from the reference)
  variation  subtle value noise at a named scale (the dye's and the light's unevenness), amount ~0.03
  print      the reading's print (check / stripe) at its real repeat, turned to the piece's grain (M["grain"], deg in
             the pattern frame, 90 = along y); phase anchored at the pattern frame's origin (pieces drafted on one
             block share it, so a check meets at matched seams as the draft placed them)
  surface    the weave / grain as height (normal map) and roughness noise: DROPPED when finer than MIN_TEXELS texels
             at the texture's density (the text says so: below Nyquist it would only alias)
  stitch     dashed thread lines at offset_mm inside the pattern's seams and hems (border edges: sewn = seam, free = hem),
             a named stitch length; thread colour from the plan (default: the cloth's, a little darker)
  wear       restrained, from the story: at the body's high points (the plan's `where`: elbows, shoulders, knees, seat:
             the rig's joints) where the build touches the body, and along free edges; lighter / flatter colour, rougher
  fray       a ragged edge (alpha cut + loose threads along the grain) on the hems of the plan's pieces only
The plan (step 2's `appearance` block, or the tool's argument) carries every amount; check_plan validates it. Defaults
are restrained: wear 0 unless the story gives one, no fray unless asked. Nothing here is specific to one garment.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from . import budgets, garment_game as gg

MIN_TEXELS = 3.0  # a surface layer whose period is under this many texels is dropped (it would alias)
WEAR_MAX = 0.6  # the most a fully worn (wear 1) texel moves toward its worn colour: restraint is the default
CONTACT_M = 0.02  # a garment point within this of the body rubs on it
HIGH_POINT_M = 0.08  # falloff radius around a named high point (a joint)
EDGE_WEAR_MM = 5.0  # free edges wear within this band
# fabric families (a keyword in the reading's "fabric" / cloth name): roughness, sheen, surface layer (kind, period)
FABRICS = {
    "leather": {"rough": 0.55, "surface": ("pebble", 2.5), "creases_mm": 9.0},
    "denim": {"rough": 0.85, "surface": ("twill", 1.0)},
    "wool": {"rough": 0.92, "surface": ("twill", 1.6)},
    "linen": {"rough": 0.86, "surface": ("slub", 1.2)},
    "silk": {"rough": 0.38, "surface": ("plain", 0.3)},
    "cotton": {"rough": 0.78, "surface": ("plain", 0.5)},
    "": {"rough": 0.8, "surface": ("plain", 0.5)},
}
HIGH_POINTS = {"elbows": ("LeftForeArm", "RightForeArm"), "shoulders": ("LeftArm", "RightArm"),
               "knees": ("LeftLeg", "RightLeg"), "seat": ("Hips",), "hips": ("LeftUpLeg", "RightUpLeg")}
CLOTH_KEYS = {"wear": "0-1 (0 = new)", "why": "the story's reason (needed when wear > 0)",
              "where": f"high points worn: {sorted(HIGH_POINTS)}", "edges": "free-edge wear 0-1 (default = wear)",
              "fray": "{pieces: [...], depth_mm}: ragged hems on those pieces", "stitch": "{colour, length_mm, offset_mm, "
              "edges: seams+hems | hems | seams | none}", "variation": "{amount (default 0.03), scale_mm (default 80)}",
              "print": "{kind: check | stripe | none, line_mm}: overrides the reading's print"}
DETAIL_MATERIALS = {"metal": (1.0, 0.35), "braid": (0.9, 0.5), "plastic": (0.0, 0.4), "horn": (0.0, 0.45),
                    "wood": (0.0, 0.6), "cloth": (0.0, 0.85), "leather": (0.0, 0.55)}


class AppearanceRefused(ValueError):
    pass


def check_plan(ap, cloths, details=()) -> list[str]:
    """Faults of an `appearance` block ({cloth: {...}, "details": {name: {material, colour}}}), each naming its keys."""
    if ap is None:
        return []
    if not isinstance(ap, dict):
        return ["appearance: {<cloth>: {" + ", ".join(f"{k} ({v})" for k, v in CLOTH_KEYS.items()) + "}, details: {...}}"]
    bad = []
    for c, a in ap.items():
        if c == "details":
            for dn, x in (a or {}).items():
                if details and dn not in details:
                    bad.append(f"appearance.details.{dn}: not an inventoried detail ({', '.join(details)})")
                if not isinstance(x, dict) or x.get("material") not in DETAIL_MATERIALS:
                    bad.append(f"appearance.details.{dn}: {{material: {' | '.join(DETAIL_MATERIALS)}, colour}}")
            continue
        if cloths and c not in cloths:
            bad.append(f"appearance.{c}: not a cloth of the reading ({', '.join(cloths)})")
            continue
        if not isinstance(a, dict):
            bad.append(f"appearance.{c}: a dict")
            continue
        for k in a:
            if k not in CLOTH_KEYS:
                bad.append(f"appearance.{c}.{k}: unknown; keys: " + "; ".join(f"{k_} ({v})" for k_, v in CLOTH_KEYS.items()))
        w = a.get("wear", 0)
        if not isinstance(w, (int, float)) or not 0 <= w <= 1:
            bad.append(f"appearance.{c}.wear: 0-1")
        elif w > 0 and not str(a.get("why") or "").strip():
            bad.append(f"appearance.{c}.why: wear {w} needs the story's reason (restraint is the default)")
        for p in a.get("where") or []:
            if p not in HIGH_POINTS:
                bad.append(f"appearance.{c}.where: {p!r} not one of {sorted(HIGH_POINTS)}")
        f = a.get("fray")
        if f is not None and not (isinstance(f, dict) and isinstance(f.get("pieces"), list)):
            bad.append(f"appearance.{c}.fray: {{pieces: [...], depth_mm}}")
        st = a.get("stitch") or {}
        if st.get("edges", "seams+hems") not in ("seams+hems", "hems", "seams", "none"):
            bad.append(f"appearance.{c}.stitch.edges: seams+hems | hems | seams | none")
    return bad


def texture_size(role: str) -> int:
    """The role's clothing texture set (budgets.json textures.sets: body_and_clothing, else all)."""
    t = budgets.role(role).get("textures") or {}
    s = t.get("sets") or {}
    return int(s.get("body_and_clothing") or s.get("all") or t.get("max_map") or 1024)


def fabric(cloth_name: str, c: dict) -> dict:
    key = f"{c.get('fabric', '')} {cloth_name}".lower()
    for k, v in FABRICS.items():
        if k and k in key:
            return {"family": k, **v}
    return {"family": "", **FABRICS[""]}


def print_of(c: dict, a: dict) -> dict | None:
    """{kind, repeat_m, line_m, colour} from the reading's print (a's override), or None."""
    p = dict(c.get("print") or {})
    p.update(a.get("print") or {})
    kind = str(p.get("kind") or "").lower()
    k = next((x for x, ws in (("check", ("check", "plaid", "gingham", "windowpane", "tartan")), ("stripe", ("stripe",)))
              if any(w in kind for w in ws)), None)
    if k is None or not p.get("repeat_mm"):
        return None
    rep = float(p["repeat_mm"]) / 1000
    col = (p.get("colours") or [[0, 0, 0]])[0]
    return {"kind": k, "repeat_m": rep, "line_m": float(p.get("line_mm") or rep * 1000 * 0.08) / 1000,
            "colour": np.asarray(col, float) / (255 if max(col) > 1 else 1)}


# ---- layout: the atlas from the PATTERN (drape) pieces, shared with the export's game mesh -----------------------
def layout(drape: dict) -> dict:
    """{"side": m, "place": {piece: (lo, pos)}}: garment_game.atlas on each pattern piece's box (only its bounds count)."""
    uv, pc = drape["uv"], drape["piece"]
    names = [n for i, n in enumerate(drape["names"]) if (pc == i).any()]
    boxes = [{"uv": np.array([uv[pc == drape["names"].index(n)].min(0), uv[pc == drape["names"].index(n)].max(0)])}
             for n in names]
    uvs, side = gg.atlas(boxes)
    return {"side": side, "place": {n: (b["uv"][0], u[0] * side) for n, b, u in zip(names, boxes, uvs)}}


def atlas_uv(lay: dict, name: str, uv: np.ndarray) -> np.ndarray:
    lo, pos = lay["place"][name]
    return (np.asarray(uv, float) - lo + pos) / lay["side"]


# ---- noise ------------------------------------------------------------------------------------------------------
def vnoise(x, y, scale, seed=0, octaves=2):
    """Smooth value noise in [-1, 1] at a scale (same units as x, y)."""
    out, amp, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        s = scale / 2 ** o
        gx, gy = x / s, y / s
        ix, iy = np.floor(gx), np.floor(gy)
        fx, fy = gx - ix, gy - iy
        fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)

        def h(i, j):
            v = np.sin(i * 127.1 + j * 311.7 + (seed + o) * 74.7) * 43758.5453
            return (v - np.floor(v)) * 2 - 1
        a = h(ix, iy) * (1 - fx) + h(ix + 1, iy) * fx
        b = h(ix, iy + 1) * (1 - fx) + h(ix + 1, iy + 1) * fx
        out = out + amp * (a * (1 - fy) + b * fy)
        tot += amp
        amp *= 0.5
    return out / tot


def lines(t, period, width, texel):
    """Antialiased coverage of lines every `period` (width wide) along coordinate t."""
    d = np.abs(((t / period + 0.5) % 1.0) - 0.5) * period
    return np.clip((width / 2 - d) / texel + 0.5, 0, 1)


# ---- the pattern's edges ----------------------------------------------------------------------------------------
def edge_samples(drape: dict, step: float = 0.0005) -> dict:
    """Per piece: points along its border loops every `step` m (pattern coords), their arc length and seam flag."""
    F, pc, uv = drape["F"], drape["piece"], drape["uv"]
    sewn = np.zeros(len(uv), bool)
    sewn[np.asarray(drape["sew"]).reshape(-1)] = True
    out = {}
    for i, n in enumerate(drape["names"]):
        Fi = F[pc[F[:, 0]] == i]
        if not len(Fi):
            continue
        E = np.sort(np.vstack([Fi[:, [0, 1]], Fi[:, [1, 2]], Fi[:, [2, 0]]]), 1)
        u, cnt = np.unique(E, axis=0, return_counts=True)
        B = u[cnt == 1]
        nb = {}
        for a, b in B:
            nb.setdefault(a, []).append(b); nb.setdefault(b, []).append(a)
        seen, P, S, K = set(), [], [], []
        for start in list(nb):
            if start in seen:
                continue
            loop, prev, cur = [start], None, start
            seen.add(start)
            while True:
                nxt = [x for x in nb[cur] if x != prev and (x not in seen or (x == start and len(loop) > 2))]
                if not nxt or nxt[0] == start:
                    break
                prev, cur = cur, nxt[0]
                seen.add(cur); loop.append(cur)
            loop.append(loop[0])
            s0 = 0.0
            for a, b in zip(loop[:-1], loop[1:]):
                pa, pb = uv[a], uv[b]
                L = float(np.linalg.norm(pb - pa))
                k = max(1, int(np.ceil(L / step)))
                t = (np.arange(k) + 0.5) / k
                P.append(pa + (pb - pa) * t[:, None]); S.append(s0 + L * t); K.append(np.full(k, sewn[a] and sewn[b]))
                s0 += L
        out[n] = {"P": np.vstack(P), "s": np.concatenate(S), "seam": np.concatenate(K)}
    return out


# ---- the bake -----------------------------------------------------------------------------------------------------
def high_point_wear(drape: dict, body_V, rb: list[dict], where: list) -> np.ndarray:
    """Per drape vertex 0-1: touching the body (CONTACT_M) near the named high points (the rig's joints)."""
    V = drape["V"]
    if not where or body_V is None or not len(body_V):
        return np.zeros(len(V))
    d = cKDTree(np.asarray(body_V, float)).query(V)[0]
    contact = np.clip(1 - d / CONTACT_M, 0, 1)
    heads = [np.asarray(b["head"], float) for b in rb for p in where for j in HIGH_POINTS[p]
             if b["name"].split(":")[-1] == j]
    if not heads:
        return np.zeros(len(V))
    r = cKDTree(np.array(heads)).query(V)[0]
    return contact * np.exp(-(r / HIGH_POINT_M) ** 2)


def bake(drape: dict, cloth_of: dict, cloths: dict, plan: dict, grain: dict, size: int, wear_v=None) -> dict:
    """The textures: {"base" RGBA uint8, "rough" uint8, "normal" RGB uint8, "layers": [...], "texel_mm"}.
    cloth_of: piece -> cloth name; cloths: step 0's cloth readings; plan: the appearance block; grain: piece -> deg;
    wear_v: {cloth: per-drape-vertex high-point wear} (high_point_wear)."""
    from PIL import Image, ImageDraw
    from scipy.interpolate import griddata
    from scipy.ndimage import distance_transform_edt
    lay = layout(drape)
    side, texel = lay["side"], lay["side"] / size
    uv, pc, F = drape["uv"], drape["piece"], drape["F"]
    names = drape["names"]
    A = np.zeros_like(uv)
    for i, n in enumerate(names):
        m = pc == i
        if m.any():
            A[m] = atlas_uv(lay, n, uv[m])
    # piece id per texel (row 0 = top = glTF v 0 = atlas v 1)
    idim = Image.new("I", (size, size), 0)
    dr = ImageDraw.Draw(idim)
    px = np.c_[A[:, 0] * size, (1 - A[:, 1]) * size]
    for f in F:
        dr.polygon([tuple(px[j]) for j in f], fill=int(pc[f[0]]) + 1)
    pid = np.asarray(idim, np.int64) - 1
    rows, cols = np.nonzero(pid >= 0)
    au, av = (cols + 0.5) / size, 1 - (rows + 0.5) / size
    tp = pid[rows, cols]
    # pattern coords per texel (the inverse of the atlas: per piece a translation at pattern scale)
    P = np.zeros((len(tp), 2))
    for i, n in enumerate(names):
        m = tp == i
        if m.any() and n in lay["place"]:
            lo, pos = lay["place"][n]
            P[m] = np.c_[au[m], av[m]] * side - pos + lo
    base = np.zeros((len(tp), 3)); alpha = np.ones(len(tp)); rough = np.zeros(len(tp)); H = np.zeros(len(tp))
    edges = edge_samples(drape)
    # per-vertex high-point wear -> texels (low frequency: interpolated over the atlas, nearest outside the hull)
    wear_t = np.zeros(len(tp))
    if wear_v:
        wv = np.zeros(len(uv))
        for c, w in wear_v.items():
            for i, n in enumerate(names):
                if cloth_of.get(n) == c:
                    wv[pc == i] = w[pc == i]
        if wv.max() > 0:
            q = np.c_[au, av]
            wear_t = griddata(A, wv, q, method="linear")
            bad = ~np.isfinite(wear_t)
            if bad.any():
                wear_t[bad] = griddata(A, wv, q[bad], method="nearest")
    layers = {}
    for i, n in enumerate(names):
        m = np.nonzero(tp == i)[0]
        if not len(m):
            continue
        cname = cloth_of.get(n)
        c, a = cloths.get(cname) or {}, (plan.get(cname) or {})
        fab = fabric(cname or "", c)
        x, y = P[m, 0], P[m, 1]
        g = np.radians(float(grain.get(n, 90.0)))
        along = x * np.cos(g) + y * np.sin(g)  # along the grain (warp)
        across = -x * np.sin(g) + y * np.cos(g)
        col = np.tile(np.asarray(c.get("colour") or [200, 200, 200], float) / 255, (len(m), 1))
        L = layers.setdefault(cname, {"cloth": cname, "fabric": fab["family"], "colour": c.get("colour"), "pieces": []})
        L["pieces"].append(n)
        var = a.get("variation") or {}
        va, vs = float(var.get("amount", 0.03)), float(var.get("scale_mm", 80)) / 1000
        col *= (1 + va * vnoise(x, y, vs, seed=i))[:, None]
        L["variation"] = {"amount": va, "scale_mm": vs * 1000}
        pr = print_of(c, a)
        if pr:
            w = lines(along, pr["repeat_m"], pr["line_m"], texel)
            if pr["kind"] == "check":
                w = np.maximum(w, lines(across, pr["repeat_m"], pr["line_m"], texel))
            col = col * (1 - w[:, None]) + pr["colour"] * w[:, None]
            L["print"] = {"kind": pr["kind"], "repeat_mm": pr["repeat_m"] * 1000, "line_mm": round(pr["line_m"] * 1000, 2),
                          "repeat_px": round(pr["repeat_m"] / texel, 1)}
        kind, per = fab["surface"]
        per_m = per / 1000
        if per_m / texel >= MIN_TEXELS:
            if kind == "twill":
                h = np.sin(2 * np.pi * (along + across) / per_m)
            elif kind == "slub":
                h = 0.5 * np.sin(2 * np.pi * across / per_m) + vnoise(along, across * 30, 0.04, seed=7 + i)
            elif kind == "pebble":
                h = vnoise(x, y, per_m, seed=11 + i)
            else:
                h = np.sin(2 * np.pi * along / per_m) * np.sin(2 * np.pi * across / per_m)
            H[m] += 0.3 * h
            L["surface"] = {"kind": kind, "period_mm": per, "period_px": round(per_m / texel, 1)}
        else:
            L["surface"] = {"kind": kind, "period_mm": per, "dropped": f"{per_m / texel:.1f} px < {MIN_TEXELS} px"}
        if fab.get("creases_mm"):
            H[m] += 0.5 * np.abs(vnoise(x, y, fab["creases_mm"] / 1000, seed=23 + i, octaves=3))
        rough[m] = fab["rough"] + 0.03 * vnoise(x, y, 0.01, seed=31 + i)
        # the edges: distance to the nearest border sample, its arc length, seam or hem
        e = edges.get(n)
        st = a.get("stitch") or {}
        we = float(a.get("wear", 0.0))
        ew = float(a.get("edges", we))
        if e is not None:
            d, k = cKDTree(e["P"]).query(P[m])
            s, seam = e["s"][k], e["seam"][k]
            which = st.get("edges", "seams+hems")
            on = {"seams+hems": np.ones(len(m), bool), "hems": ~seam, "seams": seam, "none": np.zeros(len(m), bool)}[which]
            off, sl = float(st.get("offset_mm", 3.0)) / 1000, float(st.get("length_mm", 2.5)) / 1000
            tw = max(0.0004, texel * 0.9)
            line = np.clip((tw / 2 - np.abs(d - off)) / texel + 0.5, 0, 1) * ((s % sl) < sl * 0.7) * on
            tc = st.get("colour")
            tcol = (np.asarray(tc, float) / (255 if max(tc) > 1 else 1)) if tc else col * 0.82
            col = col * (1 - line[:, None]) + tcol * line[:, None]
            H[m] += 0.8 * line - 0.4 * np.clip(1 - d / 0.0012, 0, 1) * seam
            rough[m] = rough[m] * (1 - line) + 0.7 * line
            L["stitch"] = {"edges": which, "offset_mm": off * 1000, "length_mm": sl * 1000,
                           "colour": tc or "cloth x0.82"}
            edge_w = ew * np.clip(1 - d / (EDGE_WEAR_MM / 1000), 0, 1) * (~seam) * (0.6 + 0.4 * vnoise(x, y, 0.006, 41 + i))
            fr = a.get("fray") or {}
            if n in (fr.get("pieces") or []):
                depth = float(fr.get("depth_mm", 12)) / 1000
                rag = depth * (0.45 + 0.55 * (0.5 + 0.5 * vnoise(s, s * 0, 0.012, 53 + i, octaves=3)))
                threads = (np.sin(2 * np.pi * across / 0.0018) > 0.2)
                cut = (~seam) & ((d < rag * 0.55) | ((d < rag) & ~threads))
                alpha[m] = np.where(cut, 0.0, 1.0)
                edge_w = np.maximum(edge_w, (~seam) * np.clip(1 - d / (rag * 1.6), 0, 1) * 0.8)
                L["fray"] = {"pieces": fr["pieces"], "depth_mm": depth * 1000}
        else:
            edge_w = np.zeros(len(m))
        wt = np.clip(np.maximum(edge_w, we * wear_t[m] * (0.6 + 0.4 * vnoise(x, y, 0.015, 61 + i))), 0, 1)
        worn = np.clip(col.mean(1, keepdims=True) * 0.35 + col * 0.65, 0, 1) * 1.15
        t = (WEAR_MAX * wt)[:, None]
        col = col * (1 - t) + np.clip(worn, 0, 1) * t
        rough[m] += 0.08 * wt
        L["wear"] = {"amount": we, "edges": ew, "where": a.get("where") or [], "why": a.get("why", ""),
                     "worn_texels_pct": round(100 * float((wt > 0.05).mean()), 2)}
        base[m] = np.clip(col, 0, 1)
    out_rgba = np.zeros((size, size, 4)); out_r = np.full((size, size), 0.8); out_h = np.zeros((size, size))
    out_rgba[rows, cols, :3] = base; out_rgba[rows, cols, 3] = alpha; out_r[rows, cols] = rough; out_h[rows, cols] = H
    # pad outside the pieces (mips / bilinear never pull the background in)
    idx = distance_transform_edt(pid < 0, return_distances=False, return_indices=True)
    out_rgba[..., :3] = out_rgba[idx[0], idx[1], :3]
    out_r, out_h = out_r[idx[0], idx[1]], out_h[idx[0], idx[1]]
    out_rgba[..., 3] = np.where(pid >= 0, out_rgba[..., 3], 0.0)
    gy, gx = np.gradient(out_h)
    k = 0.6
    N = np.dstack([-gx * k, gy * k, np.ones_like(gx)])
    N /= np.linalg.norm(N, axis=2, keepdims=True)
    return {"base": (out_rgba * 255 + 0.5).astype(np.uint8), "rough": (np.clip(out_r, 0, 1) * 255 + 0.5).astype(np.uint8),
            "normal": ((N * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8), "pid": pid, "layers": list(layers.values()),
            "texel_mm": texel * 1000, "side_m": side, "size": size, "alpha_cut": bool((alpha < 1).any())}


def detail_material(dn: str, plan: dict, colour) -> dict:
    x = (plan.get("details") or {}).get(dn) or {}
    kind = x.get("material", "plastic")
    met, ro = DETAIL_MATERIALS[kind]
    return {"material": kind, "metallic": met, "roughness": ro, "colour": x.get("colour") or colour}
