"""The measures (absolute, against another run, against the photos), their self-check, and the report. Part of the judge (judge.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import judge
from .judge_crops import _flat, photo_crops

# ------------------------------------------------------------------ measures
def _lab(im):
    from skimage.color import rgb2lab
    a = np.asarray(im.convert("RGBA"), np.float32) / 255.0
    return rgb2lab(a[..., :3]), a[..., 3]


def _blur(x, s, m=None):
    from scipy.ndimage import gaussian_filter
    if m is None:
        return gaussian_filter(x, s)
    return gaussian_filter(x * m, s) / np.maximum(gaussian_filter(m, s), 1e-6)


def _bandpass(L, m, w):
    return _blur(L, 0.012 * w, m) - _blur(L, 0.05 * w, m)


def _edges(L):
    from scipy.ndimage import sobel
    g = _blur(L, 1.0)
    return np.hypot(sobel(g, 0), sobel(g, 1))


def measures(im, mask=None) -> dict:
    """L* p10 / p50 / p90, chroma p50, blotch (std of the mid-scale band-pass of L*: blotches / speckle 1-5 % of the
    crop) inside the subject (alpha > 0.5)."""
    lab, a = _lab(im)
    m = (a > 0.5) if mask is None else mask
    if m.sum() < 50:
        return {"coverage": float(m.mean())}
    L = lab[..., 0]
    C = np.hypot(lab[..., 1], lab[..., 2])
    w = max(L.shape)
    core = _erode(m, int(0.05 * w))
    bp = _bandpass(L, m.astype(float), w)
    return {"L10": float(np.percentile(L[m], 10)), "L50": float(np.percentile(L[m], 50)),
            "L90": float(np.percentile(L[m], 90)), "C50": float(np.percentile(C[m], 50)),
            "blotch": float(bp[core].std()) if core.sum() > 50 else float(bp[m].std()), "coverage": float(m.mean())}


def _erode(m, r):
    from scipy.ndimage import binary_erosion
    return binary_erosion(m, iterations=max(1, r)) if r > 0 else m


def compare(x, ref) -> dict:
    """x against ref (PIL images; resized to ref's size): each measure's delta (x - ref), edge difference (mean |edges
    x - edges ref| / mean edges ref, inside both subjects), outline (1 - IoU of the alphas, when both have one)
    and the worst spot (the crop cell where the band-passed L* differs most: [x, y] in ref pixels)."""
    from PIL import Image
    if x.size != ref.size:
        x = x.resize(ref.size, Image.LANCZOS)
    lx, ax = _lab(x)
    lr, ar = _lab(ref)
    has_a = (ax < 0.99).any() and (ar < 0.99).any()
    mx, mr = (ax > 0.5), (ar > 0.5)
    both = mx & mr if has_a else np.ones_like(mr)
    mx_ = mr_ = both
    a, b = measures(x, mx_), measures(ref, mr_)
    out = {k: a[k] - b[k] for k in ("L10", "L50", "L90", "C50", "blotch") if k in a and k in b}
    Ex, Er = _edges(lx[..., 0]), _edges(lr[..., 0])
    # inside both subjects, off their borders (the silhouette is the outline measure's; border pixels carry the
    # background / premultiplication, not the surface)
    u = _erode(mx & mr, 3) if has_a else np.ones_like(mr)
    if u.sum() < 50:
        u = (mx | mr) if has_a else np.ones_like(mr)
    out["edge"] = float(np.abs(Ex - Er)[u].mean() / max(Er[u].mean(), 1e-6))
    # signed: + = x's edges harder / more contrasty than the reference's (a decal, a rim), - = softer (smudged)
    out["sharp"] = float(np.percentile(Ex[u], 99) / max(np.percentile(Er[u], 99), 1e-6) - 1.0)  # (p99: the strongest 1 %, a lip outline)
    if has_a:
        out["outline"] = float(1 - (mx & mr).sum() / max((mx | mr).sum(), 1))
    w = max(lr.shape[:2])
    d = np.abs(_bandpass(lx[..., 0], both.astype(float), w) - _bandpass(lr[..., 0], both.astype(float), w))
    d = _blur(d * both, 0.02 * w)
    e = max(2, int(0.04 * w))  # (the blur's border is not a finding)
    d[:e], d[-e:], d[:, :e], d[:, -e:] = 0, 0, 0, 0
    j, i = np.unravel_index(np.argmax(d), d.shape)
    out["spot"] = float(d[j, i])   # the largest local mid-scale L* difference (L*): a blotch / sticker / rim
    out["worst"] = [int(i), int(j)]
    out["ref"] = {k: b[k] for k in ("L10", "L50", "L90", "C50", "blotch") if k in b}
    return out


def plant_blot(im, frac=0.06, dL=-25.0, at=None):
    """A dark blot (gaussian, dL in L*, radius frac x the crop) painted on a copy: the planted fault."""
    from PIL import Image
    from skimage.color import lab2rgb
    lab, a = _lab(im)
    H, W = a.shape
    if at is None:
        ys, xs = np.nonzero(_erode(a > 0.5, int(0.12 * max(H, W))) if (a < 0.99).any() else np.ones_like(a, bool))
        if len(xs) == 0:
            ys, xs = np.nonzero(a > 0.5)
        k = len(xs) // 2
        at = (int(xs[k]), int(ys[k]))
    yy, xx = np.mgrid[0:H, 0:W]
    r = frac * max(H, W)
    g = np.exp(-((xx - at[0]) ** 2 + (yy - at[1]) ** 2) / (2 * (r / 2) ** 2))
    lab = lab.copy()
    lab[..., 0] = np.clip(lab[..., 0] + dL * g, 0, 100)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rgb = np.clip(lab2rgb(lab), 0, 1)
    out = np.dstack([rgb, a])
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA"), at


def self_check_measures(ref) -> list:
    """The measure-side self-checks on one reference crop: [(name, ok, detail)]."""
    res = []
    z = compare(ref, ref)
    worst = max(abs(v) for k, v in z.items() if k not in ("worst", "ref"))
    res.append(("ref_vs_itself", worst < 1e-6, f"max |delta| {worst:.2e}"))
    bl, at = plant_blot(ref)
    c = compare(bl, ref)
    w = max(ref.size)
    dist = float(np.hypot(c["worst"][0] - at[0], c["worst"][1] - at[1]))
    ok = c["spot"] > 1.0 and dist < 0.08 * w and c["L50"] <= 0.0
    res.append(("planted_blot", bool(ok), f"spot {c['spot']:.2f}, blotch {c['blotch']:+.2f}, L50 {c['L50']:+.2f}, "
                f"found {dist:.0f} px from it"))
    return res


def report(run: Path, ref_run: Path | None = None, head: str | None = None, only: list | None = None) -> dict:
    """Measures of a run's crops: absolute, vs another run (same crop names, identical render state required), and
    vs the photo crops (face features of the photo-lit shots only). Refuses (raises) when a self-check fails."""
    from PIL import Image
    run = Path(run)
    me = json.loads((run / "crops.json").read_text())
    checks = json.loads((run / "checks.json").read_text()) if (run / "checks.json").exists() else []
    bad = [c for c in checks if not c[1]]
    if bad:
        raise RuntimeError(f"judge: refusing to report on {run}: render self-checks failed: {bad}")
    rows, mchecks = {}, []
    refc = json.loads((Path(ref_run) / "crops.json").read_text()) if ref_run else {}
    pho = photo_crops(head, run) if head else {}
    for k, v in sorted(me.items()):
        if "file" not in v or (only and not any(o in k for o in only)):
            continue
        im = Image.open(v["file"])
        row = {"abs": measures(im)}
        if k in refc and "file" in refc[k]:
            if refc[k]["state"] != v["state"]:
                raise RuntimeError(f"judge: {k}: render state differs from the reference run's ({v['state']} vs "
                                   f"{refc[k]['state']}): view transform / lights not the same; refusing")
            r = Image.open(refc[k]["file"])
            mchecks.append((k, self_check_measures(r)))
            row["vs_ref"] = compare(im, r)
        pk = f"{v.get('view')}__{v.get('feature')}"
        if "-photo-" in k and pk in pho:
            r = Image.open(pho[pk]["file"]).convert("RGBA")
            mchecks.append((k + " (photo)", self_check_measures(r)))
            row["vs_photo"] = compare(_flat(im, _photo_bg(r)).convert("RGBA"), r)
        rows[k] = row
    fails = [(k, c) for k, cs in mchecks for c in cs if not c[1]]
    out = {"run": str(run), "ref": str(ref_run) if ref_run else None, "head": head, "render_checks": checks,
           "measure_checks": mchecks, "rows": rows}
    (run / ("report.json" if not ref_run else f"report_vs_{Path(ref_run).name}.json")).write_text(json.dumps(out, indent=1, default=float))
    if fails:
        raise RuntimeError(f"judge: refusing to report: measure self-checks failed: {fails[:5]}")
    return out


def _photo_bg(r):
    a = np.asarray(r.convert("RGB"), np.float32) / 255.0
    return tuple(np.median(a.reshape(-1, 3), 0))


def format_report(rep: dict) -> str:
    lines = ["SELF-CHECKS:"] + [f"  {'ok  ' if c[1] else 'FAIL'} {c[0]}: {c[2]}" for c in rep["render_checks"]]
    mc = [c for _, cs in rep["measure_checks"] for c in cs]
    if mc:
        n_ok = sum(c[1] for c in mc)
        lines.append(f"  {'ok  ' if n_ok == len(mc) else 'FAIL'} measures: ref_vs_itself + planted_blot on "
                     f"{len(rep['measure_checks'])} reference crops ({n_ok}/{len(mc)} passed)")
    for col in ("vs_ref", "vs_photo"):
        rs = {k: r[col] for k, r in rep["rows"].items() if col in r}
        if not rs:
            continue
        lines.append(f"\n{col.upper()} (x - ref; edge / outline: 0 = same):")
        lines.append(f"  {'crop':38s} " + " ".join(f"{c:>7s}" for c in judge.ROW_KEYS) + "   worst@")
        for k, r in rs.items():
            lines.append(f"  {k:38s} " + " ".join(f"{r[c]:+7.2f}" if c in r else f"{'':>7s}" for c in judge.ROW_KEYS)
                         + f"   {r['worst']}")
    if not any("vs_ref" in r or "vs_photo" in r for r in rep["rows"].values()):
        lines.append(f"\nABSOLUTE:")
        for k, r in rep["rows"].items():
            a = r["abs"]
            lines.append(f"  {k:38s} " + " ".join(f"{c} {a[c]:6.1f}" for c in ("L10", "L50", "L90", "C50", "blotch") if c in a))
    return "\n".join(lines)
