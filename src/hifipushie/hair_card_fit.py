"""Fitting cards and measuring a hair look: card classes, the cap under cards, clearance, the stage, reference
frames, outline and colour measures. Part of hair (hair.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import hair
from . import store
from . import hair_head
from .hair import HairError, _unit, dirs
from .hair_head import Scalp
from .hair_spec import hair_of

def card_classes(before: list, after: list, S: dict, seg, locks: dict) -> dict:
    """Where a budget's cards went: per class of lock (face-framing, hanging hair, head hair, single hairs) and card
    layer, cards and triangles cut vs kept. The export report carries it, so a tier that loses a region says so."""
    from . import hair_cards as hc

    def cls(c):
        lk = locks.get(c.get("lock")) or {}
        if lk.get("face"):
            return "face"
        if lk.get("off_head"):
            return "hanging"
        if int(lk.get("hairs") or 0) > 0 or c["kind"] == "fly":
            return "single"
        return "hanging" if float(lk.get("free", 0.0)) > 0.5 and not lk.get("lies") else "head"
    out: dict = {}
    for tag, cs in (("cut", before), ("kept", after)):
        for c in cs:
            k = f"{cls(c)}/L{int(c['layer'])}"
            d = out.setdefault(k, {"cut": [0, 0], "kept": [0, 0]})
            d[tag][0] += 1
            d[tag][1] += hc.triangles([c], S, seg)
    return dict(sorted(out.items()))


def cap_under_cards(sc: Scalp, V, cards: list, floor: float = 0.0015, bare_floor: bool | None = None):
    """Cap vertices pushed down (toward the head's centre) to CAP_UNDER under the lowest coverage card within
    CAP_REACH, never under `floor` off the scalp; where no card passes over a vertex it keeps its height."""
    from scipy.spatial import cKDTree
    V = np.asarray(V, float)
    if not cards:
        return V
    # the cards' whole surface (centre line and both edges), not their centre lines alone: at a coarse cut (24 mm
    # cards) most cap vertices had no centre line within reach, kept the groom's envelope and stood up through the
    # cards as a crest over the crown (Tess's hero at 25k)
    P = np.concatenate([np.asarray(c["P"], float) + k_ * np.asarray(c["X"], float) * np.asarray(c["hw"], float)[:, None]
                        for c in cards for k_ in (-1.0, 0.0, 1.0)])
    pa, pe, ph = sc.coords(P)
    va, ve, vh = sc.coords(V)
    tree = cKDTree(dirs(pa, pe))
    dv = dirs(va, ve)
    near = tree.query_ball_point(dv, 2 * np.sin(np.radians(hair.CAP_REACH) / 2))
    lo = np.array([ph[n].min() if n else np.inf for n in near])
    far = ~np.isfinite(lo)  # no card over it: the nearest cards within CAP_FAR set its height (the hair over it lies
    if far.any():  # no higher than the cards round it)
        dd, ii = tree.query(dv[far], k=8, distance_upper_bound=2 * np.sin(np.radians(hair.CAP_FAR) / 2))
        ok = np.isfinite(dd)
        lo[far] = np.where(ok.any(1), np.where(ok, ph[np.minimum(ii, len(ph) - 1)], np.inf).min(1), np.inf)
        if hair.CAP_TOP_EL > 0:
            top_ = far.copy()
            top_[far] = (ve[far] > hair.CAP_TOP_EL) & ok.any(1)
            if top_.any():
                hi_ = np.where(ok, ph[np.minimum(ii, len(ph) - 1)], -np.inf).max(1)
                lo[top_] = hi_[top_[far]] + hair.CAP_UNDER
    # no card over a vertex nor near it: a hole in the coverage (the part's gap, a narrowed card), so the cap lies on
    # the scalp there (CAP_BARE_FLOOR). Kept at its mass height, those vertices stood up through the hair as points
    # (b25's front-top "cat ears" where BEND_HW narrowed layer-0 cards; b26's knob at the strand part, round 18)
    h = np.where(np.isfinite(lo), np.minimum(vh, np.maximum(lo - hair.CAP_UNDER, floor)),
                 np.minimum(vh, floor) if (hair.CAP_BARE_FLOOR if bare_floor is None else bare_floor) else vh)
    # and no vertex stands over its neighbours' mean (single vertices left at the envelope were spikes)
    vt = cKDTree(dv)
    nb = vt.query_ball_point(dv, 2 * np.sin(np.radians(hair.CAP_REACH) / 2))
    h = np.minimum(h, np.array([h[n].mean() for n in nb]) + 0.001)
    return V + (h - vh)[:, None] * _unit(V - sc.C)


def cap_fill_arch(sc: Scalp, V, arch: list):
    """(round 35, hair_clumps.ARCH_FILL (b)) cap vertices under the crown arch cards raised to their height less FILL_UNDER
    (fully within CAP_REACH of an arch card's surface, eased out to nothing at FILL_REACH): the arch lies on a mass,
    not over the scalp. Only ever raised; the height is a gaussian-weighted mean of the arch surface heights near."""
    from scipy.spatial import cKDTree
    from . import hair_clumps
    V = np.asarray(V, float)
    if not arch or not hair_clumps.ARCH_FILL:
        return V
    P = np.concatenate([np.asarray(c["P"], float) + k_ * np.asarray(c["X"], float) * np.asarray(c["hw"], float)[:, None]
                        for c in arch for k_ in (-0.7, 0.0, 0.7)])
    pa, pe, ph = sc.coords(P)
    va, ve, vh = sc.coords(V)
    tree = cKDTree(dirs(pa, pe))
    dv = dirs(va, ve)
    ch = lambda deg: 2 * np.sin(np.radians(deg) / 2)
    dd, ii = tree.query(dv, k=16, distance_upper_bound=ch(hair_clumps.FILL_REACH))
    ok = np.isfinite(dd)
    if not ok.any():
        return V
    ang = np.degrees(2 * np.arcsin(np.clip(np.where(ok, dd, 0.0) / 2, 0, 1)))
    wk = np.where(ok, np.exp(-(ang / max(hair.CAP_REACH, 1e-3)) ** 2), 0.0)
    hh_ = (wk * ph[np.minimum(ii, len(ph) - 1)]).sum(1) / np.maximum(wk.sum(1), 1e-12)
    a0 = np.where(ok[:, 0], ang[:, 0], np.inf)
    f = np.clip((hair_clumps.FILL_REACH - a0) / max(hair_clumps.FILL_REACH - hair.CAP_REACH, 1e-3), 0.0, 1.0)
    w = f * f * (3 - 2 * f)
    tgt = hh_ - hair_clumps.FILL_UNDER
    h = np.where(ok[:, 0], np.maximum(vh, vh + w * (tgt - vh)), vh)
    print(f"cap fill: {int((h > vh + 1e-4).sum())} cap vertices raised under {len(arch)} arch cards "
          f"(max {1000 * float((h - vh).max()):.1f} mm)", flush=True)
    return V + (h - vh)[:, None] * _unit(V - sc.C)


def card_clearance(sc: Scalp, M: dict, locks: list, fix: float | None = None, col=None) -> dict:
    """Card vertices under the skin: how many, the deepest, and by lock (the head as the scalp's rays see it: sc).
    A card's centre line is the MEAN of its clump's strands and its width is laid flat: over a convex forehead or
    temple both cut through the head like a chord, where the strands themselves were kept off it. fix: move every
    vertex nearer than that out to it along its ray (in place). Reported as it was BEFORE the fix."""
    V = M["verts"]
    if not len(V):
        return {"verts": 0, "under": 0, "deepest_mm": 0.0, "locks": {}}
    az, el, h = sc.coords(V.astype(float))
    ok = el > sc.EL[0] + 1.0  # (below the scalp's measured range there is no surface to compare with)
    if col is not None:  # loose hair: the whole body's signed distance (neck, shoulders, back, clothes)
        h = col.at(V.astype(float))
        ok = np.ones(len(V), bool)
    under = ok & (h < 0)
    by: dict = {}
    for ci in np.unique(M["card"][under]):
        nm = locks[int(ci)] if int(ci) < len(locks) else "?"
        by[nm] = min(by.get(nm, 0.0), float(h[under & (M["card"] == ci)].min()))
    out = {"verts": int(len(V)), "under": int(under.sum()), "under_share": round(float(under.mean()), 4),
           "deepest_mm": round(float(-h[under].min() * 1000), 1) if under.any() else 0.0,
           "locks": {k: round(-v * 1000, 1) for k, v in sorted(by.items(), key=lambda kv: kv[1])[:12]}}
    if fix is not None:
        low = ok & (h < fix)
        if low.any() and col is not None:
            V[low] = col.push(V[low].astype(float), fix).astype(V.dtype)
        elif low.any():
            V[low] = sc.point(az[low], el[low], np.full(int(low.sum()), fix)).astype(V.dtype)
        out["moved"] = int(low.sum())
    return out


def _bust(spec: dict | None) -> bool:
    """Hair that leaves the head downward (groom.loose): looks and stages take in the neck and shoulders."""
    return bool(spec and ((hair_of(spec).get("groom") or {}).get("loose")))


def stage_path(name: str, bust: bool = False) -> Path:
    return store._dir(name) / ("hair_stage_bust.blend" if bust else "hair_stage.blend")


def make_stage(name: str, pad: float = 0.1, spec: dict | None = None) -> Path:
    """A small .blend for fast hair looks: the scene cropped to a box round the head (painted skin, eyes, collar),
    rebuilt when scene.blend is newer. With loose hair the box takes in the shoulders and the back."""
    from .scene import _blender, blend_path
    bp = blend_path(name)
    if not bp.exists():
        raise HairError(f"{name}: no scene.blend yet (sync the model once)")
    bust = _bust(spec)
    sp = stage_path(name, bust)
    if sp.exists() and sp.stat().st_mtime > bp.stat().st_mtime:
        return sp
    sc = hair_head.scalp(name)
    lo = (sc.C - ([0.32, 0.28, 0.7] if bust else [0.16, 0.2, 0.22])).tolist()
    hi = (sc.C + ([0.32, 0.28, 0.16] if bust else [0.16, 0.16, 0.16])).tolist()
    _blender({"mode": "hair_stage", "blend": str(bp), "out": str(sp), "box": [lo, hi]})
    return sp


def human_refs(name: str, stage: str | None = None) -> dict:
    """The model's reference pictures and their fitted cameras (human_refs.json: {"views": [{"image", "size"}],
    "cameras": [{"r", "t", "f", "size", "centre"}]}; the stage model's when the model has none)."""
    for n in (name, stage):
        f = store._dir(n) / "human_refs.json" if n else None
        if f is not None and f.exists():
            return json.loads(f.read_text())
    raise HairError(f"{name}: no human_refs.json (reference pictures with fitted cameras: block_in / face solve make it)")


def human_ref_frames(name: str, names, stage: str | None = None) -> list:
    """Render frames "ref<i>" through the i-th fitted camera of the model's reference pictures: the whole picture,
    squared (a portrait 1152 x 1536 picture sits in the middle 3/4 of the frame's width)."""
    if not names:
        return []
    from . import humanfit
    refs = human_refs(name, stage)
    out = []
    for n in names:
        i = int(str(n)[3:])
        if i >= len(refs.get("cameras") or []):
            raise HairError(f"view {n}: {name} has {len(refs.get('cameras') or [])} fitted reference cameras")
        cam = refs["cameras"][i]
        R = humanfit._cam_rot(cam)
        eye = np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float)
        fwd = R.T @ np.array([0.0, 0.0, 1.0])
        w, h = cam["size"]
        side = float(max(w, h))
        out.append({"name": str(n), "eye": eye.tolist(), "dir": (-fwd).tolist(), "up": (R.T @ np.array([0.0, -1.0, 0.0])).tolist(),
                    "fov": float(np.degrees(2 * np.arctan(side / 2 / cam["f"]))), "shift": [0.0, 0.0],
                    "center": (eye + fwd).tolist(), "near": 0.01, "scale": None, "axes": None})
    return out


def ref_square(img, size: int):
    """A reference picture (or its mask) on the square a "ref<i>" view renders: centred, padded, resized."""
    from PIL import Image
    im = Image.open(img) if not hasattr(img, "size") else img
    w, h = im.size
    side = max(w, h)
    sq = Image.new(im.mode, (side, side), 0 if im.mode in ("L", "1") else tuple([200] * len(im.getbands())))
    sq.paste(im, ((side - w) // 2, (side - h) // 2))
    return sq.resize((size, size), Image.NEAREST if im.mode in ("L", "1") else Image.LANCZOS)


def _tail_numbers(m, tx: int, ty: int, mm: float) -> dict:
    below = m[ty:]
    if not below.any():
        return {"below_px": 0, "length_mm": 0.0, "width_mm": 0.0, "back_mm": 0.0}
    cnt = below.sum(1)
    yy = np.repeat(np.arange(len(cnt)), cnt)
    wd = below[int(15 / mm):].sum(1)
    wd = wd[wd > 0]
    xs = np.nonzero(below.any(0))[0]  # (what hangs below the tie only: the head's own width is not the tail's reach)
    return {"below_px": int(below.sum()), "length_mm": round(float(np.percentile(yy, 99)) * mm, 1),
            "width_mm": round(float(np.percentile(wd, 90)) * mm, 1) if len(wd) else 0.0,
            "back_mm": round(float(max(xs.max() - tx, tx - xs.min())) * mm, 1)}


def outline_measure(ours, ref, mm_px: float, tie=None) -> dict:
    """Our hair's mask against a reference hair mask, like with like (both bool arrays on the same square of the same
    camera): {"iou", "area": ours / hers, "chamfer_mm"} and, with `tie` = the tie's pixel [x, y] on that square, what
    hangs below it for each (`hers`, `ours`: below_px, length_mm = from the tie down to the mask's lowest 1%,
    width_mm = the 90th percentile row width below tie + 15 mm, back_mm = reach sideways from the tie's column) and
    `below` = ours / hers - 1. One draw of a tail moves these about +-10 %: judge a style over 3-4 groom seeds."""
    from scipy import ndimage as ndi
    ours = ndi.binary_closing(ndi.binary_opening(np.asarray(ours, bool), iterations=1), iterations=3)
    ref = np.asarray(ref, bool)
    out = {"iou": round(float((ours & ref).sum() / max((ours | ref).sum(), 1)), 3),
           "area": round(float(ours.sum() / max(ref.sum(), 1)), 3)}
    eh, eo = ref ^ ndi.binary_erosion(ref), ours ^ ndi.binary_erosion(ours)
    if eh.any() and eo.any():
        dh, do = ndi.distance_transform_edt(~eh), ndi.distance_transform_edt(~eo)
        out["chamfer_mm"] = round(float(0.5 * (do[eh].mean() + dh[eo].mean()) * mm_px), 1)
    if tie is not None:
        tx, ty = int(round(tie[0])), int(round(tie[1]))
        out["hers"], out["ours"] = _tail_numbers(ref, tx, ty, mm_px), _tail_numbers(ours, tx, ty, mm_px)
        out["below"] = round(out["ours"]["below_px"] / max(out["hers"]["below_px"], 1) - 1.0, 3)
    return out


def _lab(img):
    a = np.asarray(img, float)[..., :3] / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    xyz = lin @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]]) / [0.9505, 1.0, 1.089]
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return 116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])


def colour_variation(img, mask, mm_px: float) -> dict:
    """How much the hair's colour VARIES inside `mask` (the flat-brown check: the same call on our render and on the
    picture, same mask, same camera). Scales in mm on the head (`mm_px`):
      L_sd / L_p10 / L_p90   the spread of lightness over the whole mask (light, form and colour together)
      strand_sd              L* against its own 1.5 mm neighbourhood: strand-to-strand contrast
      ribbon_sd              the 1.5 mm average against the 9 mm one: clump / ribbon contrast (highlight ribbons, locks)
      mass_sd                the 9 mm average against the 40 mm one: broad light and dark masses (form, roots / lengths)
      ribbons {"share", "contrast"}  the share of the mask that is a LIGHT ribbon (ribbon band > + 1 sd of the
                             picture-independent 4 L*) and those ribbons' mean lift in L*
      chroma_sd, hue_sd      the spread of chroma, and of hue (deg, over pixels with chroma > 4)
    Blurs are normalised by the mask (no bleeding in from skin or backdrop)."""
    from scipy import ndimage as ndi
    m = np.asarray(mask, bool)
    if m.sum() < 200:
        return {}
    L, A, B = _lab(img)
    w = m.astype(float)

    def blur(x, mm):
        sg = max(mm / max(mm_px, 1e-6), 0.5)
        return ndi.gaussian_filter(x * w, sg) / np.maximum(ndi.gaussian_filter(w, sg), 1e-3)
    b1, b2, b3 = blur(L, 1.5), blur(L, 9.0), blur(L, 40.0)
    rb = (b1 - b2)[m]
    C = np.hypot(A, B)[m]
    Hh = np.degrees(np.arctan2(B, A))[m]
    lite = rb > 4.0
    return {"L_sd": round(float(L[m].std()), 2), "L_p10": round(float(np.percentile(L[m], 10)), 1),
            "L_p90": round(float(np.percentile(L[m], 90)), 1), "strand_sd": round(float((L - b1)[m].std()), 2),
            "ribbon_sd": round(float(rb.std()), 2), "mass_sd": round(float((b2 - b3)[m].std()), 2),
            "ribbons": {"share": round(float(lite.mean()), 3), "contrast": round(float(rb[lite].mean()), 1) if lite.any() else 0.0},
            "chroma_sd": round(float(C.std()), 2), "hue_sd": round(float(Hh[C > 4].std()), 1) if (C > 4).sum() > 50 else 0.0,
            # EDGE vs CORE: thin hair at the outline (within 3 mm of the mask's edge) against the mass more than 8 mm in:
            # light through thin hair (transmission) lightens and warms the edge; an opaque stand-in shader does not
            **_edge_core(L, A, B, m, mm_px)}


def _edge_core(L, A, B, m, mm_px):
    from scipy import ndimage as ndi
    d = ndi.distance_transform_edt(m) * mm_px
    e, c = m & (d <= 3.0), m & (d > 8.0)
    if e.sum() < 30 or c.sum() < 30:
        return {}
    ch = np.hypot(A, B)
    return {"edge_L": round(float(L[e].mean()), 1), "core_L": round(float(L[c].mean()), 1),
            "edge_chroma": round(float(ch[e].mean()), 1), "core_chroma": round(float(ch[c].mean()), 1)}


def colour_bands(img, mask, mm_px: float | None = None) -> dict:
    """The colour of `img` (RGB image or array, sRGB) inside `mask`, as CIE L*, chroma, hue (deg): the mean and the
    shadow / mid / highlight thirds by lightness. For matching a hair look to a picture: the same call on the render
    (mask = our hair AND hers, eroded: dense hair only) and on the picture, per engine (EEVEE reads look.eevee_gain /
    eevee_sat, Cycles look.cycles_fit / cycles_width / cycles_sat). With `mm_px` (mm on the head a pixel) also
    "variation": colour_variation (strand / ribbon / mass contrast, the share and lift of light ribbons)."""
    a = np.asarray(img, float)[..., :3] / 255.0
    m = np.asarray(mask, bool)
    if m.sum() < 30:
        return {}
    if mm_px:
        return {**colour_bands(img, mask), "variation": colour_variation(img, mask, float(mm_px))}
    c = a[m]
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]]) / [0.9505, 1.0, 1.089]
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    L, A, B = 116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])
    q1, q2 = np.percentile(L, [33.3, 66.7])

    def band(k):
        return {"L": round(float(L[k].mean()), 1), "chroma": round(float(np.hypot(A[k], B[k]).mean()), 1),
                "hue": round(float(np.degrees(np.arctan2(B[k].mean(), A[k].mean())) % 360), 1)}
    return {"mean": band(np.ones(len(L), bool)), "shadow": band(L <= q1), "mid": band((L > q1) & (L <= q2)),
            "highlight": band(L > q2)}


def measure_ref(name: str, view: str, mask=None, tie=None, colour: bool = True, stage: str | None = None) -> dict:
    """After look(views=[.., view]) with view = "ref<i>": the CURRENT hair against that reference picture:
    `outline` (outline_measure against `mask`, a hair mask image in the picture's own pixels, white = hair; `tie` =
    the tie's pixel in the picture) and `colour` (colour_bands of our render and of the picture over the dense hair
    both have). Needs the look just made (look.ids / look.images)."""
    from . import hair_look
    from PIL import Image
    from scipy import ndimage as ndi
    ids, imgs = getattr(hair_look.look, "ids", {}), getattr(hair_look.look, "images", {})
    if view not in ids:
        raise HairError(f"measure: look the model through {view!r} first (look_hair(views=[..., {view!r}]))")
    ours = ids[view]
    n = ours.shape[0]
    refs = human_refs(name, stage)
    i = int(view[3:])
    cam = refs["cameras"][i]
    w, h = cam["size"]
    side = float(max(w, h))
    mm = float(cam["t"][2]) / float(cam["f"]) * 1000.0 * side / n
    out = {"view": view, "mm_per_px": round(mm, 3)}
    mref = None
    if mask:
        mref = np.asarray(ref_square(Image.open(mask).convert("L"), n)) > 127
        t_ = None if tie is None else [(tie[0] + (side - w) / 2) * n / side, (tie[1] + (side - h) / 2) * n / side]
        out["outline"] = outline_measure(ours, mref, mm, t_)
    pic = ((refs.get("views") or [{}] * (i + 1))[i] or {}).get("image")
    if colour and pic and Path(pic).exists() and view in imgs:
        both = ours & mref if mref is not None else ours
        dense = ndi.binary_erosion(both, iterations=max(1, n // 160))
        out["colour"] = {"ours": colour_bands(imgs[view].resize((n, n)), dense, mm),
                         "picture": colour_bands(ref_square(Image.open(pic).convert("RGB"), n), dense, mm)}
    return out


def reference_image(name: str, reference: str | None = None):
    """(path, crop or None) of the image the hair is judged against: `reference` if given, else the traced
    reference's image (ref_trace.json "image", cropped to the matched camera's crop), else none."""
    from . import hair_reference
    if reference:
        p = Path(reference).expanduser()
        return (p, None) if p.exists() else (None, None)
    tr = hair_reference.ref_trace(name) or {}
    cam = hair_reference.ref_camera(name) or {}
    p = tr.get("image") or cam.get("reference")
    if p and Path(p).exists():
        return Path(p), cam.get("crop") or tr.get("crop")
    return None, None


def cameras(sc: Scalp, views, dist: float = 0.62, fov: float = 30.0) -> list:
    out = []
    target = sc.C + np.array([0.0, 0.0, 0.0])
    for v in views:
        az, el, *dd = hair.VIEWS[v]
        tg = target - np.array([0.0, 0.0, dd[1] if len(dd) > 1 else 0.0])
        eye = tg + dirs(az, el) * (dd[0] if dd else dist)  # close-ups: the material at work
        out.append({"name": v, "eye": eye.tolist(), "target": tg.tolist(), "fov": fov})
    return out
