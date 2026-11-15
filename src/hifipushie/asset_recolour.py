"""Recolour masks for export_asset(recolour_masks=...): one neutral base and channel masks instead of a material per colour.

A kit piece whose parts take a colour per instance (a house's walls, trim, roof, doors, curtains) would otherwise need a
material slot per recolourable part (~nine draw calls a piece). With masks, the parts share one atlas and one material:

  recolour_masks = [{"R": ["siding"], "G": ["trim"], "B": ["roof", "roofdark"], "A": ["door", "shutter"]},
                    {"R": ["curtain"], "G": ["planter"], "B": ["flower"]}]

Each entry is one RGBA mask texture (<asset>_mask<k>.png, linear, 1 where the channel's parts are, else 0); a name is a
model part (spec parts) or an export part. For the masked parts the base colour is baked NEUTRAL: each texel's luminance
over its channel's default luminance, times asset.RECOLOUR_BASE_WHITE (near white), grey: the shading and painted detail
(laps, creases, grain, a darker part sharing the channel) stay as light and dark, the hue goes. A channel's default
colour is its parts' own baked colour (the median texel); every part's own colour is recorded beside it. The engine:
  albedo = basecolor * (1 - sum(m) + sum(m_c * tint_c) / RECOLOUR_BASE_WHITE)   (linear; m = the mask channels)
so tint = the default reproduces the baked colour's lightness. Unmasked parts keep their baked colour (m = 0).
All masked parts must share one atlas (that is the point: one material); the export refuses otherwise."""
from __future__ import annotations

import numpy as np

from . import asset
from .asset_raster import _dilate, _srgb

CHANNELS = "RGBA"
LUM = np.array([0.2126, 0.7152, 0.0722])  # Rec. 709 luminance of linear RGB


def resolve(masks: list | None, parts: dict, origin: dict) -> dict | None:
    """The masks as export parts: {"groups": [{channel: [export part]}], "names": [{channel: [as given]}], "atlas": index}.
    None without masks. Refuses unknown channels or parts, a part in two channels, masked parts on two atlases."""
    if not masks:
        return None
    from .spec import SpecError
    if not isinstance(masks, list) or not all(isinstance(g, dict) for g in masks):
        raise SpecError("recolour_masks: a list of masks, each {channel R/G/B/A: [part names]}")
    seen: dict = {}
    groups = []
    for k, g in enumerate(masks):
        out = {}
        for ch, names in g.items():
            c = str(ch).upper()
            if c not in CHANNELS:
                raise SpecError(f"recolour_masks[{k}]: channel {ch!r} is not one of R, G, B, A")
            names = [names] if isinstance(names, str) else list(names)
            pns = []
            for nm in names:
                hit = [pn for pn in parts if pn == nm or origin.get(pn) == nm]
                if not hit:
                    raise SpecError(f"recolour_masks[{k}].{c}: no part {nm!r} in this export (parts: "
                                    f"{sorted(set(origin.get(pn, pn) for pn in parts))})")
                for pn in hit:
                    if pn in seen and seen[pn] != (k, c):
                        raise SpecError(f"recolour_masks: part {pn!r} is in mask {seen[pn][0]} {seen[pn][1]} and "
                                        f"mask {k} {c}: one channel per part")
                    seen[pn] = (k, c)
                    if pn not in pns:
                        pns.append(pn)
            out[c] = pns
        groups.append(out)
    atl = sorted({parts[pn]["atlas"] for pn in seen})
    if len(atl) > 1:
        raise SpecError(f"recolour_masks: the masked parts are on {len(atl)} atlases; they share one material, so one "
                        "atlas: give them the same parts.<p>.atlas, or a larger texture / texel_density")
    return {"groups": groups, "names": [{str(c).upper(): ([v] if isinstance(v, str) else list(v)) for c, v in g.items()}
                                        for g in masks], "atlas": atl[0]}


def _hex(lin) -> str:
    s = np.clip(_srgb(np.asarray(lin, float)), 0, 1)
    return "#" + "".join(f"{int(round(v * 255)):02x}" for v in s)


def apply(lin: np.ndarray, rc: dict, names: list, ys, xs, part, drawn, baked, filled, log: list):
    """bake(): the neutral base over the masked parts' texels and the mask images. lin: the atlas's linear colour
    (size, size, 3); part: each drawn texel's export part index. Returns (lin, [mask images (size, size, 4)], channels)."""
    size = lin.shape[0]
    lab = np.full((size, size, 1), -1.0)
    lab[ys, xs, 0] = part
    lab = _dilate(lab, filled)[..., 0].astype(int)  # every texel: the part of its nearest drawn texel (margins too)
    lum = lin @ LUM
    out = lin.copy()
    masks = [np.zeros((size, size, 4)) for _ in rc["groups"]]
    ok = baked[ys, xs] & drawn
    w = float(asset.RECOLOUR_BASE_WHITE)
    channels = []
    for k, g in enumerate(rc["groups"]):
        for c, pns in g.items():
            idx = [names.index(pn) for pn in pns if pn in names]
            on = np.isin(lab, idx)
            sel = ok & np.isin(part, idx)
            src = lin[ys[sel], xs[sel]] if sel.any() else lin[on]
            col = np.median(src, 0) if len(src) else np.full(3, w)
            own = {}
            for pn in pns:
                s_ = ok & (part == names.index(pn))
                if s_.any():
                    own[pn] = _hex(np.median(lin[ys[s_], xs[s_]], 0))
            l0 = max(float(col @ LUM), 1e-4)
            out[on] = np.clip(w * lum[on] / l0, 0, 1)[:, None]
            masks[k][on, CHANNELS.index(c)] = 1.0
            channels.append({"mask": k, "channel": c, "parts": rc["names"][k][c], "export_parts": pns,
                             "default": _hex(col), "default_linear": [round(float(v), 4) for v in col],
                             "part_colors": own, "texels": int(sel.sum())})
            log.append(f"recolour mask{k}.{c}: {', '.join(rc['names'][k][c])}: default {_hex(col)} "
                       f"({int(sel.sum())} texels; base neutral at {w:g} x luminance / the default's)")
    return out, masks, channels


def formula() -> str:
    return (f"albedo = basecolor * (1 - sum(m) + sum(m_c * tint_c) / {asset.RECOLOUR_BASE_WHITE:g})   (linear; m_c = "
            "channel c of the mask textures, tint_c = the scheme's colour, its default = recolour.channels[].default; "
            "basecolor is neutral grey where any mask is on)")
