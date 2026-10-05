"""Numbers for "does this skin read real": the same measurements on a render and on a photograph (skin.py's looks
report them; the diagnosis that started the skin work compared them, see skin_guide.md).

All work on patches of skin (boxes holding only skin: no brows, lips, hair or background), in CIE Lab from sRGB:
- `bands`: contrast per octave of feature size (mm), for lightness L and for the colour axes a (green-red) and
  b (blue-yellow). a and b hardly see the lighting, so they read the ALBEDO's variation: mottling, freckles, veins,
  redness. L holds albedo + shading + highlights.
- `zones`: mean colour per named zone and its difference from the forehead (the face's colour zones).
- `highlight`: how much of a patch is highlight, how big its blobs are and how broken up it is (a smooth plastic
  highlight is one blob with no fine structure; pores and an uneven oily film break it into speckle).
- `micro`: fine-scale lightness contrast (<= 0.7 mm features) where the surface is lit: the pores and skin lines
  that micro-normal detail gives.
- `shadow_colour`: how the skin's chroma and hue move from its lit to its shadowed pixels (subsurface light turns
  shadows and their edges redder and more saturated; without it they only get darker).
"""
from __future__ import annotations

import numpy as np

OCTAVES = (0.35, 0.7, 1.4, 2.8, 5.6, 11.2, 22.4)  # mm: feature sizes (the band's centre wavelength / 2)


def lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (uint8 or 0..1) -> CIE Lab (D65), (..., 3)."""
    c = np.asarray(rgb, np.float64)
    if c.max() > 1.5:
        c = c / 255.0
    c = c[..., :3]
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _crop(img, box):
    a = np.asarray(img)
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    return a[max(y0, 0):y1, max(x0, 0):x1]


def bands(patch: np.ndarray, mm_per_px: float, octaves=OCTAVES) -> dict:
    """{"L" | "a" | "b": [rms per octave]} of a skin patch (sRGB): each octave is a difference of Gaussians holding
    features about that size (mm). None where the patch is too small or the pixels too coarse for the octave."""
    from scipy.ndimage import gaussian_filter
    q = lab(patch)
    out = {}
    for k, name in enumerate("Lab"):
        ch = q[..., k]
        row = []
        for s in octaves:
            sig = 0.5 * s / mm_per_px  # px: a feature of size s is a blob of sigma ~ s/2
            if sig < 0.6 or 6 * sig > min(ch.shape):
                row.append(None)
                continue
            d = gaussian_filter(ch, sig * 0.7, mode="reflect") - gaussian_filter(ch, sig * 1.4, mode="reflect")
            m = int(2 * sig)
            d = d[m:-m or None, m:-m or None] if d.shape[0] > 4 * m + 4 and d.shape[1] > 4 * m + 4 else d
            row.append(round(float(np.sqrt(np.mean(d * d))), 3))
        out[name] = row
    return out


def zones(img, boxes: dict) -> dict:
    """Mean Lab + HSV hue/saturation per zone box, and each zone's a/b/L offset from "forehead" when there is one."""
    import colorsys
    out = {}
    for name, box in boxes.items():
        p = _crop(img, box)
        if p.size == 0:
            continue
        m = lab(p).reshape(-1, 3).mean(0)
        r, g, b = (np.asarray(p, float).reshape(-1, p.shape[-1])[:, :3].mean(0) / 255.0)
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        out[name] = {"L": round(float(m[0]), 1), "a": round(float(m[1]), 1), "b": round(float(m[2]), 1),
                     "hue": round(h * 360, 1), "sat": round(s, 3), "val": round(v, 3)}
    if "forehead" in out:
        f = out["forehead"]
        for name, z in out.items():
            if name != "forehead":
                z["d"] = {k: round(z[k] - f[k], 1) for k in "Lab"}
    return out


def highlight(patch: np.ndarray, mm_per_px: float) -> dict:
    """The specular highlight in a patch: `share` of the patch more than `lift` L over its smooth (4 mm) lightness
    ... no: over the patch's median; `blob_mm` the area-weighted mean blob width; `breakup` = fine (<= 0.7 mm)
    lightness contrast inside the highlight over that outside (1 = the highlight is as smooth as the rest: plastic);
    `fine_L` the fine contrast inside it."""
    from scipy import ndimage
    L = lab(patch)[..., 0]
    med = np.median(L)
    hi = L > med + max(6.0, 1.5 * np.std(L))
    sig = max(0.35 / mm_per_px, 0.6)
    fine = L - ndimage.gaussian_filter(L, sig * 1.4)
    out = {"share": round(float(hi.mean()), 4)}
    if hi.sum() < 12:
        return {**out, "blob_mm": 0.0, "breakup": None, "fine_L": None, "peak_L": round(float(L.max() - med), 1)}
    lab_, n = ndimage.label(hi)
    sizes = ndimage.sum(hi, lab_, range(1, n + 1))
    w = np.sqrt(sizes) * mm_per_px
    inside = float(np.sqrt(np.mean(fine[hi] ** 2)))
    outside = float(np.sqrt(np.mean(fine[~hi] ** 2)))
    return {**out, "blob_mm": round(float((w * sizes).sum() / sizes.sum()), 2), "blobs": int(n),
            "breakup": round(inside / max(outside, 1e-6), 2), "fine_L": round(inside, 3),
            "peak_L": round(float(np.percentile(L, 99.5) - med), 1)}


def micro(patch: np.ndarray, mm_per_px: float) -> float | None:
    """Fine lightness contrast (features <= 0.7 mm) as a share of the local lightness, over the patch's lit half."""
    from scipy.ndimage import gaussian_filter
    L = lab(patch)[..., 0]
    sig = 0.35 / mm_per_px
    if sig < 0.6:
        return None
    smooth = gaussian_filter(L, sig * 1.4)
    lit = smooth >= np.median(smooth)
    return round(float(np.sqrt(np.mean(((L - smooth)[lit]) ** 2)) / max(float(smooth[lit].mean()), 1e-6)), 5)


def shadow_colour(pixels: np.ndarray) -> dict:
    """Skin pixels (n, 3 sRGB; lit and shadowed skin together): chroma/lightness and hue angle of the brightest and
    the darkest quarter, and the mid-tones' excess redness over the straight line between them (the red terminator)."""
    q = lab(np.asarray(pixels).reshape(-1, 1, np.asarray(pixels).shape[-1])).reshape(-1, 3)
    L = q[:, 0]
    lo, mid_lo, mid_hi, hi = np.percentile(L, [25, 40, 60, 75])
    def stat(sel):
        m = q[sel].mean(0)
        return m, float(np.hypot(m[1], m[2]) / max(m[0], 1e-6)), float(np.degrees(np.arctan2(m[2], m[1])))
    (ml, cl, hl), (md, cd, hd), (mm, cm, hm) = stat(L >= hi), stat(L <= lo), stat((L > mid_lo) & (L < mid_hi))
    t = (mm[0] - md[0]) / max(ml[0] - md[0], 1e-6)
    return {"L_lit": round(float(ml[0]), 1), "L_shadow": round(float(md[0]), 1),
            "chroma_over_L_lit": round(cl, 3), "chroma_over_L_shadow": round(cd, 3),
            "chroma_ratio_shadow_over_lit": round(cd / max(cl, 1e-6), 2),
            "hue_lit": round(hl, 1), "hue_shadow": round(hd, 1), "hue_shift_to_red": round(hl - hd, 1),
            "mid_red_excess": round(float(mm[1] - (md[1] + t * (ml[1] - md[1]))), 2)}


def patch_report(img, boxes: dict, mm_per_px: float) -> dict:
    """Everything above for one image: boxes {zone: [x0, y0, x1, y1]} of skin."""
    a = np.asarray(img.convert("RGB") if hasattr(img, "convert") else img)
    per = {}
    for name, box in boxes.items():
        p = _crop(a, box)
        if min(p.shape[:2]) < 24:
            continue
        per[name] = {"bands": bands(p, mm_per_px), "highlight": highlight(p, mm_per_px), "micro": micro(p, mm_per_px)}
    px = np.concatenate([_crop(a, b).reshape(-1, 3) for b in boxes.values() if _crop(a, b).size])
    def avg(key):
        rows = [v["bands"][key] for v in per.values()]
        out = []
        for k in range(len(OCTAVES)):
            vals = [r[k] for r in rows if r[k] is not None]
            out.append(round(float(np.mean(vals)), 3) if vals else None)
        return out
    mic = [v["micro"] for v in per.values() if v["micro"] is not None]
    return {"mm_per_px": round(mm_per_px, 4), "octaves_mm": list(OCTAVES),
            "bands": {k: avg(k) for k in "Lab"} if per else {}, "zones": zones(a, boxes),
            "highlight": {n: v["highlight"] for n, v in per.items()},
            "micro": round(float(np.mean(mic)), 5) if mic else None, "shadow": shadow_colour(px), "per_box": per}


def table(rows: dict) -> str:
    """{label: patch_report} as aligned text: band contrasts per octave, zone offsets, highlight, micro, shadow."""
    out = ["feature size mm      " + "".join(f"{o:>7}" for o in OCTAVES)]
    for ch, what in (("L", "lightness"), ("a", "red-green"), ("b", "yellow-blue")):
        for label, r in rows.items():
            v = (r.get("bands") or {}).get(ch) or [None] * len(OCTAVES)
            out.append(f"{what[:9]:<9} {label[:10]:<10} " + "".join(f"{x:>7.2f}" if x is not None else "      -" for x in v))
    out.append("zones (a, b offset from the forehead; + a = redder, + b = yellower):")
    for label, r in rows.items():
        z = r.get("zones") or {}
        bits = [f"{n} a{v['d']['a']:+.1f} b{v['d']['b']:+.1f} L{v['d']['L']:+.1f}" for n, v in z.items() if "d" in v]
        f = z.get("forehead")
        out.append(f"  {label[:14]:<14} " + (f"forehead L{f['L']} a{f['a']} b{f['b']} sat {f['sat']}; " if f else "") + "; ".join(bits))
    out.append("highlight (share of patch, blob width mm, breakup: fine contrast inside / outside), micro, shadow colour:")
    for label, r in rows.items():
        hs = [h for h in (r.get("highlight") or {}).values() if h.get("breakup") is not None]
        h = max(hs, key=lambda x: x["share"]) if hs else None
        s = r.get("shadow") or {}
        out.append(f"  {label[:14]:<14} " + (f"share {h['share']:.3f} blob {h['blob_mm']} mm x{h['blobs']} breakup {h['breakup']} "
                                             f"fine {h['fine_L']}" if h else "no highlight") +
                   f" | micro {r.get('micro')} | shadow chroma x{s.get('chroma_ratio_shadow_over_lit')} "
                   f"hue {s.get('hue_shift_to_red')} deg redder, mid-tone red +{s.get('mid_red_excess')}")
    return "\n".join(out)
