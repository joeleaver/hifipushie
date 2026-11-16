"""The balance of a figure's masses, read off a flat reference view beside the model (look_beside's text).

A modeller checks proportion by measuring: how wide the head is against the body, where the waist falls. An
outline's difference map can't say it: two blind blockouts had a head visibly small against the body while the map
showed "a 1.8 cm strip" (p7, p8: "each mass's size as a part of the whole, view by view"). This reads the figure's
width by height (front and back: the run of clay through the centre line; side: from the foremost to the hindmost
clay) off the reference and off the model, and compares them where the REFERENCE is widest and narrowest: its own
landmarks, so nothing is named or guessed (a head, a waist and a belly on one figure; a head, a neck and a chest
on another).

    read(ref, hit, core, zs, cx, k, plane) -> {"plane", "top": {"reference", "model"},
        "landmarks": [{"kind": "widest" | "narrowest", "z", "reference", "model", "whole", "own": {"z", "w"} | None}],
        "ratios": [{"reference", "model"}]}  # each widest against the next one down
`core` is the model without its paired masses (ears, arms, legs: the ".L" / ".R" ones), `hit` with them: a limb held
out for the rig would count as body width. The reference can't be parted that way: where its limbs lie against it
they are in its width, and the text says so.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.signal import find_peaks

PROM = 0.006  # metres a widest or narrowest place has to stand out by
NEAR = 0.12  # the model's own widest / narrowest place is looked for within this part of the figure's height
MOST = (3, 2)  # at most this many widest and narrowest places


def _central(mask: np.ndarray, cx: float) -> np.ndarray:
    """Per row, the width in pixels of the run of clay through column cx (nan: none there)."""
    H, W = mask.shape
    c = int(min(max(round(cx), 0), W - 1))
    out = np.full(H, np.nan)
    for y in np.flatnonzero(mask[:, max(c - 1, 0):c + 2].any(1)):
        xs = np.flatnonzero(mask[y])
        cuts = np.flatnonzero(np.diff(xs) > 1)
        for s, e in zip(np.r_[0, cuts + 1], np.r_[cuts, len(xs) - 1]):
            if xs[s] - 1 <= c <= xs[e] + 1:
                out[y] = xs[e] - xs[s] + 1
                break
    return out


def _extent(mask: np.ndarray) -> np.ndarray:
    out = np.full(mask.shape[0], np.nan)
    for y in np.flatnonzero(mask.any(1)):
        xs = np.flatnonzero(mask[y])
        out[y] = xs[-1] - xs[0] + 1
    return out


def _smooth(w: np.ndarray, k: float) -> np.ndarray:
    """Widths in metres over the longest unbroken stretch of rows, smoothed; nan elsewhere."""
    ok = np.isfinite(w)
    out = np.full(len(w), np.nan)
    if not ok.any():
        return out
    lab, n = ndimage.label(ok)
    best = 1 + int(np.argmax(ndimage.sum(ok, lab, range(1, n + 1))))
    rows = np.flatnonzero(lab == best)
    out[rows] = ndimage.gaussian_filter1d(w[rows] * k, max(1.5, 0.012 / k), mode="nearest")
    return out


def _extrema(s: np.ndarray) -> list[tuple[int, str, float]]:
    """[(row, "widest" | "narrowest", prominence)] of a smoothed width curve."""
    rows = np.flatnonzero(np.isfinite(s))
    if len(rows) < 5:
        return []
    v = s[rows]
    out = []
    for kind, sign, most in (("widest", 1.0, MOST[0]), ("narrowest", -1.0, MOST[1])):
        idx, pr = find_peaks(sign * v, prominence=PROM)
        got = sorted(zip(pr["prominences"], idx), reverse=True)[:most]
        out += [(int(rows[i]), kind, float(p)) for p, i in got]
    if not any(kind == "widest" for _, kind, _ in out):
        out.append((int(rows[int(np.argmax(v))]), "widest", 0.0))
    return sorted(out)


def read(ref: np.ndarray, hit: np.ndarray, core: np.ndarray, zs, cx: float, k: float, plane: str) -> dict | None:
    """Module docstring. zs: the heights (m) of the first and the last pixel row; cx: the centre line's column."""
    H = ref.shape[0]
    width = (lambda m: _central(m, cx)) if plane == "front" else _extent
    z = np.linspace(float(zs[0]), float(zs[1]), H)
    sr, sm, sw = (_smooth(width(m), k) for m in (ref, core, hit))
    marks = _extrema(sr)
    if not marks or not ref.any() or not hit.any():
        return None
    own = _extrema(sm)
    span = max(int(np.isfinite(sr).sum()), 1)
    out = []
    for row, kind, _ in marks:
        near = [(abs(r - row), r) for r, kd, _ in own if kd == kind and abs(r - row) <= NEAR * span]
        mine = min(near)[1] if near else None
        out.append({"kind": kind, "z": float(z[row]), "reference": float(sr[row]),
                    "model": float(sm[row]) if np.isfinite(sm[row]) else None,
                    "whole": float(sw[row]) if np.isfinite(sw[row]) else None,
                    "own": {"z": float(z[mine]), "w": float(sm[mine])} if mine is not None else None})
    def limbs(m):  # paired masses are in the model's width there, as the reference's limbs may be in its own
        return m["model"] is None or (m["whole"] is not None and m["whole"] - m["model"] > 0.01)
    wide = [m for m in out if m["kind"] == "widest"]
    ratios = []
    for a, b in zip(wide, wide[1:]):
        if limbs(a) or limbs(b):
            continue  # (a head against a body-with-arms says nothing about the head)
        ma, mb = ((a["own"] or {}).get("w") or a["model"]), ((b["own"] or {}).get("w") or b["model"])
        ratios.append({"upper": a["z"], "lower": b["z"], "reference": a["reference"] / b["reference"],
                       "model": ma / mb if ma and mb else None})
    return {"plane": plane, "top": {"reference": float(z[np.flatnonzero(ref.any(1))[0]]),
                                    "model": float(z[np.flatnonzero(hit.any(1))[0]])},
            "landmarks": out, "ratios": ratios}


def text(r: dict) -> list[str]:
    across = ("width across the middle of the figure" if r["plane"] == "front" else "depth from its foremost to its hindmost clay")
    lines = [f"  proportions: {across}, by height, where the REFERENCE is widest and narrowest (the model's without its "
             "paired masses: ears, arms, legs; the reference's limbs count where they lie against it):",
             f"    top of the figure: reference z {r['top']['reference']:.3f}, model {r['top']['model']:.3f}"]
    for m in r["landmarks"]:
        mod = "no clay there" if m["model"] is None else f"{m['model'] * 100:.1f} cm"
        if m["whole"] is not None and m["model"] is not None and m["whole"] - m["model"] > 0.01:
            mod += f" ({m['whole'] * 100:.1f} with its paired masses)"
        mine = (f"; the model's own {m['kind']} place near there: {m['own']['w'] * 100:.1f} cm at z {m['own']['z']:.3f}"
                if m["own"] else "")
        lines.append(f"    {m['kind']} at z {m['z']:.3f}: reference {m['reference'] * 100:.1f} cm, model {mod}{mine}")
    for q in r["ratios"]:
        lines.append(f"    the widest place at z {q['upper']:.3f} against the one at z {q['lower']:.3f}: {q['reference']:.2f} "
                     "in the reference, " + (f"{q['model']:.2f} in the model" if q["model"] else "not there in the model")
                     + (" (the model's upper mass is small against its lower)" if q["model"] and q["model"] < q["reference"] - 0.04
                        else " (the model's upper mass is big against its lower)" if q["model"] and q["model"] > q["reference"] + 0.04
                        else ""))
    return lines
