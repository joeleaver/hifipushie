"""Checks on rendered hair: a card tier against the strand groom it was cut from, in the same view and light.

What the eye calls "corrupted" in game hair is measurable: strand silhouette left bare, a darker or greyer value,
cards whose rectangles show (stamps on the skin, plank ends on the outline), hair that an alpha test deletes.
Everything here works on images (a render with hair, the same render bald), so it judges what an engine draws, not
what the mesh was meant to be. Used by hair.check_tiers (the export report's WARNINGs) and the tests."""

from __future__ import annotations

import numpy as np

LIMITS = {
    "missing": 0.2,  # share of the strands' hair pixels a tier leaves bare (far: 0.35)
    "value": 0.12,  # |tier / strands - 1| of the hair pixels' mean HSV value
    "sat": 0.25,  # the same for saturation
    "stamps": 2,  # detached rectangular blobs (a card's own quad showing)
    "straight": 0.3,  # share of the hair outline made of straight runs (plank edges); strands themselves: ~0.1
}


def hair_mask(img, bald, tol: float = 0.06):
    """Pixels the hair changes: |render - the same view bald| over tol."""
    a, b = np.asarray(img, float) / 255, np.asarray(bald, float) / 255
    return np.abs(a[..., :3] - b[..., :3]).max(-1) > tol


def _hsv(px):
    mx, mn = px.max(-1), px.min(-1)
    return mx, np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)


def colour(img, mask) -> dict:
    px = (np.asarray(img, float) / 255)[..., :3][mask]
    if not len(px):
        return {"value": 0.0, "sat": 0.0, "black": 0.0}
    v, s = _hsv(px)
    return {"value": round(float(v.mean()), 3), "sat": round(float(s.mean()), 3),
            "black": round(float((v < 0.06).mean()), 3)}


def stamps(mask, min_px: int = 25, max_share: float = 0.03) -> dict:
    """Detached blobs of hair (not part of the main mass) and how rectangular they are: area / the area of the
    blob's own tightest rectangle (by its principal axes). A card showing as a stamp is 0.8+; a wisp of hairs 0.3."""
    from scipy import ndimage
    lab, n = ndimage.label(mask)
    if n == 0:
        return {"blobs": 0, "stamps": 0, "worst": 0.0}
    sizes = ndimage.sum(mask, lab, np.arange(1, n + 1))
    big = float(sizes.max())
    out, worst = 0, 0.0
    blobs = 0
    for i in np.nonzero((sizes >= min_px) & (sizes < max_share * mask.size) & (sizes < big))[0]:
        ys, xs = np.nonzero(lab == i + 1)
        P = np.stack([xs, ys], 1).astype(float)
        P -= P.mean(0)
        _, _, vt = np.linalg.svd(P, full_matrices=False)
        q = P @ vt.T
        ext = (np.ptp(q[:, 0]) + 1) * (np.ptp(q[:, 1]) + 1)
        rect = float(len(P) / ext)
        aspect = (np.ptp(q[:, 1]) + 1) / (np.ptp(q[:, 0]) + 1)
        blobs += 1
        if rect > 0.72 and aspect > 0.25:  # (a filled quad, not a single long hair)
            out += 1
        worst = max(worst, rect if aspect > 0.25 else 0.0)
    return {"blobs": blobs, "stamps": out, "worst": round(worst, 2)}


def straight_share(mask, run_px: float = 14.0, tol: float = 0.75) -> float:
    """Share of the hair's outline that lies on straight runs of `run_px` or more (greedy chords, each point within
    `tol` px): plank ends and cut quads. Strand hair's outline is ragged at this scale."""
    from skimage import measure
    total, straight = 0.0, 0.0
    for c in measure.find_contours(mask.astype(float), 0.5):
        if len(c) < 20:
            continue
        seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
        total += float(seg.sum())
        i, n = 0, len(c)
        step = max(1, int(run_px // 2))
        while i < n - 1:
            j = min(i + step, n - 1)
            best = i
            while j < n:
                a, b = c[i], c[j]
                ab = b - a
                L = np.linalg.norm(ab)
                if L < 1e-6:
                    break
                q = c[i:j + 1] - a
                d = np.abs(ab[0] * q[:, 1] - ab[1] * q[:, 0]) / L
                if d.max() > tol:
                    break
                best = j
                j += step
            if best > i and np.linalg.norm(c[best] - c[i]) >= run_px:
                straight += float(seg[i:best].sum())
                i = best
            else:
                i += step
    return round(straight / max(total, 1e-9), 3)


def compare(strands_img, tier_img, bald_img) -> dict:
    """One view: the tier against the strands. iou / missing of the hair masks, value and saturation ratios."""
    ms, mt = hair_mask(strands_img, bald_img), hair_mask(tier_img, bald_img)
    cs, ct = colour(strands_img, ms), colour(tier_img, mt)
    return {"iou": round(float((ms & mt).sum() / max((ms | mt).sum(), 1)), 3),
            "missing": round(float((ms & ~mt).sum() / max(ms.sum(), 1)), 3),
            "extra": round(float((mt & ~ms).sum() / max(ms.sum(), 1)), 3),
            "value": round(ct["value"] / max(cs["value"], 1e-6), 3), "sat": round(ct["sat"] / max(cs["sat"], 1e-6), 3),
            "black": ct["black"], **stamps(mt), "straight": straight_share(mt), "straight_strands": straight_share(ms)}


def mesh_verdict(clearance: dict | None) -> list:
    """WARNING lines from the card mesh's own facts (hair.card_clearance): vertices that were under the skin before
    they were moved out, wisps whose root lies on bare skin."""
    out = []
    c = clearance or {}
    if c.get("under", 0) and c.get("deepest_mm", 0) > 3.0:
        out.append(f"WARNING: {c['under']} card vertices were under the skin (deepest {c['deepest_mm']} mm; "
                   f"{', '.join(f'{k} {v}' for k, v in list(c.get('locks', {}).items())[:5])}): moved out to the clearance")
    for k, v in (c.get("detached") or {}).items():
        out.append(f"WARNING: detached wisp {k}: its cards start {-v} mm outside the hairline, on bare skin")
    return out


def verdict(views: dict, far: bool = False) -> list:
    """WARNING lines for a tier: {view: compare()} -> what fails."""
    out = []
    lim_m = 0.35 if far else LIMITS["missing"]
    worst = lambda k: max(views.values(), key=lambda v: v[k])  # noqa: E731
    m = max(v["missing"] for v in views.values())
    if m > lim_m:
        out.append(f"WARNING: leaves {m:.0%} of the strands' silhouette bare (limit {lim_m:.0%})")
    for k in ("value", "sat"):
        r = np.mean([v[k] for v in views.values()])
        if abs(r - 1) > LIMITS[k]:
            out.append(f"WARNING: hair {k} is {r:.2f} x the strands' (limit +-{LIMITS[k]:.0%})")
    st = sum(v["stamps"] for v in views.values())
    if st > LIMITS["stamps"]:
        out.append(f"WARNING: {st} detached rectangular blobs (cards showing as stamps; worst {worst('worst')['worst']})")
    s = max(v["straight"] - v["straight_strands"] for v in views.values())
    if s > LIMITS["straight"]:
        out.append(f"WARNING: {s:.0%} more of the outline is straight edges than in the strands (plank ends)")
    return out
