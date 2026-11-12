"""The read: what the pictures say of the hair, its summary and text. Part of the hair read (hair_read.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_read
from . import store
from .hair_read import _hex, _lab_px, cam_eye, onto_scalp, region_name
from .hair_read_capture import frames
from .hair_read_measures import (
    baby_hairs, colour_split, edge_softness, hairline_pixels, hairness, lengths, outline_rays, parting,
    skin_hairness,
)

# ------------------------------------------------------------------------------------------------ the read
def _authority(fs: list, authority=None) -> int:
    if authority is not None:
        return int(authority)
    return int(min(range(len(fs)), key=lambda k: abs(((fs[k]["yaw"] + 180) % 360) - 180)))


def read(name: str, spec: dict | None = None, authority: int | None = None, log=print, fs: list | None = None,
         thresholds: dict | None = None) -> dict:
    """Measure the hair on every fitted reference view (see the module's text). authority = the view whose colour is
    the target (default: the most frontal)."""
    from scipy import ndimage as ndi
    from . import hair_head
    spec = store.load(name) if spec is None else spec
    sc = hair_head.scalp(name, spec)
    fs = frames(name, spec) if fs is None else fs
    if not fs:
        raise ValueError(f"{name}: no fitted reference views (human_refs.json cameras: block_in / face solve make them)")
    au = _authority(fs, authority)
    views = []
    for f in fs:
        mm = f["mm"]
        hn = hairness(f["image"], f["hair"], f["bg"], mm)
        o = outline_rays(f["skull"], hn["solid"], hn["a"], f["bg"], f["c"], mm)
        v = {"i": f["i"], "yaw": f["yaw"], "mm_px": round(mm, 3), "hair_rgb": _hex(hn["hair_rgb"]),
             "backdrop_rgb": _hex(hn["bg_rgb"])}
        # stand-off by region: each ray's skull edge pixel -> its grazing point on the scalp
        ks = np.nonzero(o["meets"])[0]
        if len(ks):
            th = np.radians(o["ang"][ks])
            uv = np.stack([f["c"][0] + np.sin(th) * o["skull_px"][ks], f["c"][1] - np.cos(th) * o["skull_px"][ks]], 1)
            _, _, G = onto_scalp(sc, f["cam"], uv, step=0.0015)
            az, el, _ = sc.coords(G)
            reg = region_name(az, el)
            v["standoff"] = {r: round(float(np.nanmedian(o["standoff_mm"][ks][reg == r])), 1)
                             for r in hair_read.REGIONS if (reg == r).sum() >= 3}
            v["halo"] = {r: round(float(np.nanmean(o["halo"][ks][reg == r])), 3)
                         for r in hair_read.REGIONS if (reg == r).sum() >= 3}
            v["outline_samples"] = int(len(ks))
        v["halo_all"] = round(float(np.nanmean(o["halo"])), 3) if np.isfinite(o["halo"]).any() else None
        v["rough_mm"] = round(o["rough_mm"], 2) if np.isfinite(o["rough_mm"]) else None
        v["wisps"] = o["wisps"]
        v["wisps_per_10cm"] = round(o["wisps"] / max(o["outline_cm"] / 10.0, 1e-6), 1) if o["outline_cm"] > 1 else None
        # hairline: boundary pixels onto the scalp, front-facing only
        pts, nrm = hairline_pixels(f["hair"], f["skin"], step=max(1, int(round(1.0 / mm))))
        a_sk, skc = skin_hairness(f["image"], f["skin"], hn["hair_rgb"])
        hl = []
        if len(pts) > 10:
            P, hit, _ = onto_scalp(sc, f["cam"], pts, step=0.001)
            eye, _ = cam_eye(f["cam"])
            az, el, _ = sc.coords(P)
            nn = sc.normal(az, el)
            face = ((eye - P) / np.linalg.norm(eye - P, axis=1, keepdims=True) * nn).sum(1)
            ok = hit & (face > 0.35)
            # long hair hanging over the cheeks / jaw meets skin there too: that is not the hairline. A hairline point
            # in front of the ears sits above the sideburns' bottom (~ -12 deg); round the back the nape may go low
            fa_ = np.abs(((az + 180) % 360) - 180)
            ok &= (fa_ > 110) | (el > -12.0)
            for k in np.nonzero(ok)[0]:
                hl.append((float(((az[k] + 180) % 360) - 180), float(el[k]), float(P[k, 2]), k))
            soft = {}
            fa = np.abs(np.array([h_[0] for h_ in hl])) if hl else np.zeros(0)
            idx = np.array([h_[3] for h_ in hl], int) if hl else np.zeros(0, int)
            for nm, (lo, hi) in (("front", (0, 35)), ("temples", (35, 80)), ("sides", (80, 125)), ("nape", (125, 181))):
                sel = idx[(fa >= lo) & (fa < hi)]
                if len(sel) >= 20:
                    soft[nm] = edge_softness(None, a_sk, pts[sel], nrm[sel], mm)
            v["hairline_softness_mm"] = {k: s_.get("width_mm") for k, s_ in soft.items()}
        v["hairline"] = [h_[:3] for h_ in hl]
        v["baby_hairs"] = baby_hairs(a_sk, f["hair"], f["skin"], mm)
        hl_len = len(hl) * max(1.0, 1.0) * mm / 10.0  # cm of line seen (one sample a mm)
        v["baby_per_cm"] = round(v["baby_hairs"] / max(hl_len, 1e-6), 2) if hl_len > 1 else None
        # colour: the dense hair (solid eroded 2 mm, parser sure)
        dense = ndi.binary_erosion(hn["solid"], iterations=max(1, int(round(2.0 / mm)))) & (f["hair"] > 0.8)
        v["colour"] = colour_split(f["image"], dense, mm, T=(thresholds or {}).get(f["i"]))
        # light share by region: dense pixels cast onto the hair's surface
        ys, xs = np.nonzero(dense)
        if len(xs) > 200 and v["colour"]:
            sub = slice(None, None, max(1, len(xs) // 6000))
            uv = np.stack([xs[sub], ys[sub]], 1).astype(float)
            P, hit, _ = onto_scalp(sc, f["cam"], uv, height=0.008, step=0.0015)
            az, el, _ = sc.coords(P)
            reg = region_name(az, el)
            L = _lab_px(np.asarray(f["image"], float)[ys[sub], xs[sub]])[:, 0]
            T = v["colour"]["threshold_L"]
            v["light_share_by_region"] = {r: round(float((L[hit & (reg == r)] > T).mean()), 3)
                                          for r in hair_read.REGIONS if (hit & (reg == r)).sum() >= 100}
            # (2026-10-16) the region's median L*: the whole-head colour item (sides / back too light while the front passed)
            v["L_by_region"] = {r: round(float(np.median(L[hit & (reg == r)])), 1)
                                for r in hair_read.REGIONS if (hit & (reg == r)).sum() >= 100}
        # LONG hair: how far down it reaches (the hair mask's lowest point, on the plane through the head centre facing
        # the camera: m under the centre) and how WAVY its lengths are (below the ear)
        v.update(lengths(f, sc, hn["solid"], mm))
        # parting (front-ish views only: within 50 deg of frontal)
        if abs(((f["yaw"] + 180) % 360) - 180) <= 50:
            cols = np.nonzero(hn["solid"].any(0))[0]
            top = int(np.nonzero(hn["solid"].any(1))[0].min()) if hn["solid"].any() else 0
            hlr = [pts[h_[3], 1] for h_ in hl if abs(h_[0]) < 25]
            hline = float(np.median(hlr)) if hlr else top + 60.0 / mm
            v["parting"] = parting(f["image"], hn["solid"], a_sk, mm, top, hline, f["c"])
            if v["parting"].get("x_px") is not None:
                # the part's place on the head: its pixel at the band's middle, cast onto the hair's surface
                yy = top + 0.3 * (hline - top)
                P, hit, _ = onto_scalp(sc, f["cam"], [[v["parting"]["x_px"], yy]], height=0.01)
                v["parting"]["x_m"] = round(float(P[0, 0] - sc.C[0]), 4) if hit[0] else None
        views.append(v)
    r = {"views": views, "authority": au, "authority_image": fs[au].get("image_path"), "version": hair_read.VERSION}
    r["summary"] = summarise(r)
    r["text"] = read_text(r)
    return r


def summarise(r: dict) -> dict:
    """Across views: stand-off and halo by region (median over the views that see the region's outline), hairline
    points (|az| binned, left and right together), softness, parting, colour targets (the authority view's)."""
    vs = r["views"]
    au = vs[r["authority"]]
    s = {"standoff": {}, "halo": {}}
    for k in ("standoff", "halo"):
        for reg in hair_read.REGIONS:
            x = [v[k][reg] for v in vs if reg in (v.get(k) or {}) and np.isfinite(v[k][reg])]
            if x:
                s[k][reg] = round(float(np.median(x)), 3 if k == "halo" else 1)
    hal = [v["halo_all"] for v in vs if v.get("halo_all") is not None]
    s["halo_all"] = round(float(np.median(hal)), 3) if hal else None
    rough = [v["rough_mm"] for v in vs if v.get("rough_mm") is not None]
    s["rough_mm"] = round(float(np.median(rough)), 2) if rough else None
    wp = [v["wisps_per_10cm"] for v in vs if v.get("wisps_per_10cm") is not None]
    s["wisps_per_10cm"] = round(float(np.median(wp)), 1) if wp else None
    # hairline: per 5 deg of |az| the median height (z) and elevation over every view that saw it
    allp = np.array([p for v in vs for p in v.get("hairline") or []], float).reshape(-1, 3)
    pts = []
    if len(allp):
        fa = np.abs(allp[:, 0])
        for a0 in np.arange(0, 180, 5.0):
            m = (fa >= a0) & (fa < a0 + 5)
            if m.sum() >= 6:
                pts.append([a0 + 2.5, round(float(np.median(allp[m, 2])), 4), round(float(np.median(allp[m, 1])), 1),
                            int(m.sum())])
        left, right = allp[allp[:, 0] > 5], allp[allp[:, 0] < -5]
        s["hairline_asym_mm"] = (round(1000 * float(np.median(left[np.abs(left[:, 0]) < 40, 2]) - np.median(right[np.abs(right[:, 0]) < 40, 2])), 1)
                                 if (np.abs(left[:, 0]) < 40).sum() > 5 and (np.abs(right[:, 0]) < 40).sum() > 5 else None)
    s["hairline"] = pts
    soft = {}
    for v in vs:
        for k, w in (v.get("hairline_softness_mm") or {}).items():
            if w is not None:
                soft.setdefault(k, []).append(w)
    s["hairline_softness_mm"] = {k: round(float(np.median(w)), 1) for k, w in soft.items()}
    bp = [v["baby_per_cm"] for v in vs if v.get("baby_per_cm") is not None]
    s["baby_per_cm"] = round(float(np.median(bp)), 2) if bp else None
    bm = [v["bottom_m"] for v in vs if v.get("bottom_m") is not None]
    s["bottom_m"] = round(float(max(bm)), 3) if bm else None  # (the view that sees the most of it hanging)
    wv = [v["waviness"] for v in vs if v.get("waviness") is not None]
    s["waviness"] = round(float(np.median(wv)), 3) if wv else None
    s["parting"] = au.get("parting") or next((v.get("parting") for v in vs if v.get("parting")), None)
    s["colour"] = au.get("colour") or {}
    s["colour_view"] = r["authority"]
    s["light_share_by_region"] = dict(au.get("light_share_by_region") or {})
    for v in vs:  # regions the authority view can't see (the back) from the others, marked
        for k, x in (v.get("light_share_by_region") or {}).items():
            if k not in s["light_share_by_region"]:
                s["light_share_by_region"][k] = x
                s.setdefault("light_share_from", {})[k] = v["i"]
    return s


def read_text(r: dict) -> str:
    s = r["summary"]
    L = [f"HAIR READ (v{r['version']}): {len(r['views'])} fitted views; colour authority = view {r['authority']} "
         f"(yaw {r['views'][r['authority']]['yaw']:.0f}); the others are checks"]
    L.append("stand-off over the skull, mm (rule 1), median over views: " +
             ", ".join(f"{k} {v}" for k, v in s["standoff"].items()))
    for v in r["views"]:
        L.append(f"  view {v['i']} (yaw {v['yaw']:.0f}, {v['mm_px']} mm/px): stand-off " +
                 ", ".join(f"{k} {x}" for k, x in (v.get("standoff") or {}).items())
                 + f"; halo {v.get('halo_all')}; edge roughness {v.get('rough_mm')} mm; wisps {v.get('wisps')}"
                 + (f" ({v['wisps_per_10cm']} / 10 cm)" if v.get("wisps_per_10cm") is not None else ""))
    L.append(f"halo density (rule 4; mean hairness {hair_read.HALO_BAND[0]}-{hair_read.HALO_BAND[1]} mm past the solid edge, 0 cut-out .. 1 "
             f"solid): {s['halo_all']} (by region {s['halo']}); edge roughness {s['rough_mm']} mm; wisps "
             f"{s['wisps_per_10cm']} per 10 cm of outline")
    if s["hairline"]:
        L.append("hairline (rule 6), |az| deg -> height z m / elevation deg (samples): " +
                 "; ".join(f"{a:.0f}: {z} / {e}" for a, z, e, n in s["hairline"][:8]) + (" ..." if len(s["hairline"]) > 8 else ""))
    L.append(f"hairline softness (20->80 % hair across the line, mm): {s['hairline_softness_mm']}; baby hairs "
             f"{s['baby_per_cm']} per cm; left - right height {s.get('hairline_asym_mm')} mm")
    if s.get("bottom_m") is not None:
        L.append(f"lengths: the hair reaches {s['bottom_m']} m under the head centre (the view that shows most of it; "
                 f"the jaw is ~0.11, the shoulders' top ~0.17); waviness of the lengths {s.get('waviness')} (0 straight .. 1 "
                 f"curly)")
    p = s.get("parting") or {}
    if p:
        L.append("parting (rule 5): " + ("SEEN" if p.get("seen") else "NOT SEEN (a part needs a sharp flip of strand "
                 "direction AND a scalp line)") + f": flip strength {p.get('strength')}, width {p.get('width_mm')} mm, "
                 f"scalp line {p.get('scalp')}, at {p.get('x_m')} m off the centre; the front's sweep "
                 f"{p.get('sweep')} (+ = image right)")
    c = s.get("colour") or {}
    if c:
        b = c["bands"]
        L.append(f"colour (authority view {s['colour_view']}): mean L* {b['mean']['L']} chroma {b['mean']['chroma']} hue "
                 f"{b['mean']['hue']}; shadow {b['shadow']['L']} / mid {b['mid']['L']} / highlight {b['highlight']['L']}")
        va = b.get("variation") or {}
        if va:
            L.append(f"  variation: L_sd {va.get('L_sd')}, strand_sd {va.get('strand_sd')}, ribbon_sd {va.get('ribbon_sd')}, "
                     f"mass_sd {va.get('mass_sd')}, light ribbons {va.get('ribbons')}, edge L {va.get('edge_L')} vs core "
                     f"{va.get('core_L')}")
        L.append(f"  two modes at L* {c['threshold_L']}: pigmented {c.get('dark_L')} (seen {c.get('seen')}), light / grey "
                 f"{c.get('light_L')} (grey {c.get('grey')}), light share {c['light_share']}")
        L.append(f"  light share by region: {s['light_share_by_region']}"
                 + (f" (from views {s['light_share_from']})" if s.get("light_share_from") else ""))
    for v in r["views"]:
        if v["i"] != r["authority"] and v.get("colour"):
            b = v["colour"]["bands"]["mean"]
            L.append(f"  check view {v['i']}: mean L* {b['L']} chroma {b['chroma']} hue {b['hue']}, light share "
                     f"{v['colour']['light_share']}")
    return "\n".join(L)
