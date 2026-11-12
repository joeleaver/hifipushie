"""Compare a groom's render with its reference read, and the colour step toward it. Part of the hair read (hair_read.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_read
from . import store
from .hair_read import _hex_lin, _lin_hex, _srgb_list
from .hair_read_capture import frames
from .hair_read_read import _authority, read

def compare(name: str, images: dict, spec: dict | None = None, authority: int | None = None) -> dict:
    """The same read on OUR renders through the fitted cameras (images {view index: square render, as hair.look's
    "ref<i>" views or hgshots' v<i>}) and on the pictures: {"ours", "picture", "text"} (the text: a table ours |
    picture per measure). Like with like: the same nets, masks and cameras on both."""
    spec = store.load(name) if spec is None else spec
    fo = frames(name, spec, images=images)
    fp = [f for f in frames(name, spec) if f["i"] in images]
    au = authority if authority is not None else _authority(fp)
    rp = read(name, spec, authority=au, fs=fp, log=lambda s: None)
    # ours split at the PICTURE's light / dark threshold: the light shares then count the same thing
    th = {v["i"]: v["colour"]["threshold_L"] for v in rp["views"] if v.get("colour")}
    ro = read(name, spec, authority=au, fs=fo, log=lambda s: None, thresholds=th)
    return {"ours": ro, "picture": rp, "text": compare_text(ro, rp)}


def compare_text(ro: dict, rp: dict) -> str:
    so, sp = ro["summary"], rp["summary"]
    L = ["HAIR COMPARE ours | picture (same nets, masks, cameras):"]
    for reg in hair_read.REGIONS:
        a, b = so["standoff"].get(reg), sp["standoff"].get(reg)
        if a is not None or b is not None:
            L.append(f"  stand-off {reg}: {a} | {b} mm" + (f"  ({a - b:+.1f})" if a is not None and b is not None else ""))
    for k, nm in (("halo_all", "halo"), ("rough_mm", "edge roughness mm"), ("wisps_per_10cm", "wisps / 10 cm"),
                  ("baby_per_cm", "baby hairs / cm")):
        L.append(f"  {nm}: {so.get(k)} | {sp.get(k)}")
    L.append(f"  hairline softness mm: {so.get('hairline_softness_mm')} | {sp.get('hairline_softness_mm')}")
    ho = {round(a): z for a, z, e, n in so.get("hairline") or []}
    hp = {round(a): z for a, z, e, n in sp.get("hairline") or []}
    common = sorted(set(ho) & set(hp))
    if common:
        L.append("  hairline height, ours - picture mm by |az|: " + ", ".join(f"{a}: {1000 * (ho[a] - hp[a]):+.0f}" for a in common))
    for v_o, v_p in zip(ro["views"], rp["views"]):
        co, cp = v_o.get("colour") or {}, v_p.get("colour") or {}
        if co and cp:
            bo, bp = co["bands"], cp["bands"]
            tag = " (AUTHORITY)" if v_p["i"] == rp["authority"] else " (check)"
            L.append(f"  view {v_p['i']}{tag} colour L*/chroma/hue mean {bo['mean']['L']}/{bo['mean']['chroma']}/{bo['mean']['hue']} | "
                     f"{bp['mean']['L']}/{bp['mean']['chroma']}/{bp['mean']['hue']}; shadow L {bo['shadow']['L']} | {bp['shadow']['L']}; "
                     f"highlight L {bo['highlight']['L']} | {bp['highlight']['L']}; light share {co['light_share']} | {cp['light_share']}")
            vo, vp = bo.get("variation") or {}, bp.get("variation") or {}
            if vo and vp:
                L.append(f"    variation L_sd {vo.get('L_sd')} | {vp.get('L_sd')}, strand_sd {vo.get('strand_sd')} | {vp.get('strand_sd')}, "
                         f"ribbon_sd {vo.get('ribbon_sd')} | {vp.get('ribbon_sd')}, edge-core L {_ec(vo)} | {_ec(vp)}")
        lo, lp = v_o.get("light_share_by_region") or {}, v_p.get("light_share_by_region") or {}
        if lo and lp:
            L.append(f"    light share by region: " + ", ".join(f"{k} {lo.get(k)} | {lp.get(k)}" for k in hair_read.REGIONS if k in lo or k in lp))
        lo, lp = v_o.get("L_by_region") or {}, v_p.get("L_by_region") or {}
        if lo and lp:
            L.append(f"    L* by region: " + ", ".join(f"{k} {lo.get(k)} | {lp.get(k)}" for k in hair_read.REGIONS if k in lo or k in lp))
    return "\n".join(L)


def colour_step(cmp: dict, look: dict, gain: float = 1.0) -> dict:
    """One colour correction from a compare (the AUTHORITY view only): each mode's colour as asked (look seen / grey)
    x (the picture's mode / our render's mode), per LINEAR channel (lightness, hue and chroma at once: what the
    renderer, the light and the mass's own shade do to a colour is taken as a fixed gain per channel). gain < 1 takes
    part of the step. Returns {"seen", "grey", "why"} (keys whose modes are missing are left out)."""
    ro, rp = cmp["ours"], cmp["picture"]
    au = rp["authority"]
    co = next((v["colour"] for v in ro["views"] if v["i"] == au), {}) or {}
    cp = next((v["colour"] for v in rp["views"] if v["i"] == au), {}) or {}
    out, why = {}, []
    # hair without grey: `seen` was set from the LIT mode, so the lit modes are compared (the start's rule)
    grey = cp.get("chroma_ratio") is None or cp["chroma_ratio"] < hair_read.GREY_CHROMA
    if not grey and look.get("seen") and co.get("mean_rgb") and cp.get("mean_rgb"):
        # NO GREY: the step in Lab, as lightness, chroma and hue SEPARATELY on the mean colour (comparing lit modes
        # failed when ours had 1 % lit pixels and the picture 30 %). Per linear channel it blew up (hair-garrett,
        # family round 2: a brown asked bluer came out PURPLE, a near-black asked greener came out GREEN): `seen`
        # derives lit with its saturation / eevee_sat, so a small hue change in seen is a big one in the strands
        from .skin_read import _unlab, lab
        Lp, Lo, Ls = (lab(_lin_hex(h)) for h in (cp["mean_rgb"], co["mean_rgb"], look["seen"]))
        Cp, Co, Cs = (float(np.hypot(x[1], x[2])) for x in (Lp, Lo, Ls))
        hp_, ho_, hs_ = (float(np.degrees(np.arctan2(x[2], x[1]))) for x in (Lp, Lo, Ls))
        L1 = float(np.clip(Ls[0] + gain * (Lp[0] - Lo[0]), 2.0, 90.0))
        C1 = float(np.clip(Cs * (Cp / max(Co, 0.5)) ** gain, 0.0, 40.0))
        dh = float(np.clip(((hp_ - ho_ + 180) % 360 - 180) * gain, -20.0, 20.0))  # (a small turn at most)
        h1 = np.radians(hs_ + dh)
        # (as sRGB FLOATS: near-grey hair's hue does not survive 8 bits: #5b504f asked +6 deg came back the same hex)
        out["seen"] = _srgb_list(_unlab(np.array([L1, C1 * np.cos(h1), C1 * np.sin(h1)])))
        why.append(f"seen (mean colour, Lab): picture L* {Lp[0]:.1f} C {Cp:.1f} h {hp_:.0f}, ours L* {Lo[0]:.1f} C {Co:.1f} h "
                   f"{ho_:.0f} (view {au}): asked {look['seen']} -> {out['seen']} (L* {Ls[0]:.1f} -> {L1:.1f}, C {Cs:.1f} -> "
                   f"{C1:.1f}, hue {dh:+.0f} deg)")
    for key in ("seen", "grey"):
        mk = key
        if key in out or not grey and key == "seen":
            continue
        if co.get(mk) and cp.get(mk) and look.get(key):
            r = _lin_hex(cp[mk]) / np.maximum(_lin_hex(co[mk]), 1e-4)
            r = np.clip(r, 0.25, 4.0) ** float(gain)
            out[key] = _hex_lin(_lin_hex(look[key]) * r)
            why.append(f"{key} ({mk} mode): asked {look[key]}, rendered {co[mk]}, picture {cp[mk]} (view {au}) -> {out[key]}")
    out["why"] = "; ".join(why)
    return out


def _ec(v):
    return round(v["edge_L"] - v["core_L"], 1) if v.get("edge_L") is not None and v.get("core_L") is not None else None
