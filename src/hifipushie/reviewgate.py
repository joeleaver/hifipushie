"""Input and output gates for the blind reviews (/mnt/data/hifipushie/bin/review, bin/review-ab; docs/notes/gates.md LOOK).

The reviewer must see ONLY reference | result crops and neutral region names: no captions, numbers or claims. And a
review that did not run (usage limit, auth, timeout: no VERDICT line, bin/review exit 4) is a FAILURE, never "0 MAJORs"
(skin r8, 2026-10-18: four heads read as 0 MAJORs because the reviewer never ran).

    refuse_inputs(images, names, context)   # raises InputRefused: captioned / sheet-sized images, claims in text
    result(review_md) -> {"ran", "verdict", "major", "minor"}
    majors(review_md) -> int                 # raises ReviewNotRun on a review that did not run

Only numpy / scipy / PIL: bin/review runs under the system python3.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

MAX_SIDE = 3000      # px: a crop bigger than this is a sheet
MAX_ASPECT = 3.2     # a crop this many times wider than tall (or taller than wide) is a strip of panels
# A number with a unit, or a word that claims a result: neither belongs in a region name or the --context line.
CLAIM = re.compile(r"\d+(\.\d+)?\s*(mm|cm|px|%|l\*|db|deg|°)|\b(fixed|improved|better|worse|closer|matches|"
                   r"correct(ed)?|approved|best|pass(es|ed)?|fail(s|ed)?|v\d+\w*|r\d+\w*)\b", re.I)


class InputRefused(ValueError):
    pass


class ReviewNotRun(RuntimeError):
    pass


def caption_band(img) -> str | None:
    """'top' / 'bottom' when an edge band of the image is a caption: a near-uniform strip holding many small
    high-contrast marks (glyphs). A render's own plain background has no glyphs; a hair edge entering the strip is one
    big component, not many small ones."""
    from scipy import ndimage
    a = np.asarray(img.convert("RGB"), np.int16)
    h = a.shape[0]
    bh = int(min(60, max(8, 0.15 * h)))
    for side, band in (("top", a[:bh]), ("bottom", a[h - bh:])):
        q = (band // 8).reshape(-1, 3)
        vals, counts = np.unique(q, axis=0, return_counts=True)
        mode = vals[counts.argmax()] * 8 + 4
        d = np.abs(band - mode).max(-1)
        if (d <= 14).mean() < 0.8:
            continue
        lab, n = ndimage.label(d > 70, structure=np.ones((3, 3)))
        if n < 6:
            continue
        sl = ndimage.find_objects(lab)
        area = ndimage.sum(np.ones_like(lab), lab, np.arange(1, n + 1))
        g = sorted(((s[1].start + s[1].stop) / 2, (s[0].start + s[0].stop) / 2, s[0].stop - s[0].start)
                   for s, ar in zip(sl, area)
                   if 3 <= ar <= 400 and 4 <= (s[0].stop - s[0].start) <= 24 and (s[1].stop - s[1].start) <= 24)
        if _text_line(g):
            return side
    return None


def _text_line(g: list, need: int = 6, dy: float = 4.0) -> bool:
    """A run of `need` glyphs (x, y, height) on one line: centres within dy, heights alike (x0.6-1.6 of the first), each
    within ~2 glyph heights of the last: a line of text, not scattered marks."""
    for x0, y0, h0 in g:
        row = [x for x, y, h in g if abs(y - y0) <= dy and x >= x0 and 0.6 * h0 <= h <= 1.6 * h0]
        run, last = 1, x0
        for x in row[1:]:
            if x - last > 2.2 * h0:
                break
            run, last = run + 1, x
        if run >= need:
            return True
    return False


def grid_gutters(img, min_frac: float = 0.15) -> str | None:
    """Gutters of a multi-view grid: a full-length row or column of one flat colour inside the image (not within
    min_frac of an edge), as a contact sheet's tile borders leave, of a value unlike the image's own background (the
    border's commonest value) and with picture on both sides. A single view on a flat background has background
    columns, but those match the border, so they don't count."""
    import numpy as np
    a = np.asarray(img.convert("L"), dtype=np.int16)
    h, w = a.shape
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    counts = np.bincount(border.clip(0, 255))
    bg = int(counts.argmax()) if counts.max() > 0.3 * border.size else -100  # no flat background: any gutter counts
    for axis, n, name in ((0, w, "column"), (1, h, "row")):
        lines_min, lines_max = a.min(axis=axis), a.max(axis=axis)
        flat = (lines_max - lines_min <= 2) & (np.abs(lines_min - bg) > 10)
        busy = lines_max - lines_min > 40
        lo, hi = int(n * min_frac), int(n * (1 - min_frac))
        for i in np.flatnonzero(flat[lo:hi]) + lo:
            if busy[:i].sum() > 0.1 * n and busy[i + 1:].sum() > 0.1 * n:
                return f"a flat gutter {name} at {i} of {n} px"
    return None


def refuse_inputs(images=(), names=(), context: str = "") -> None:
    """Raise InputRefused when a review input breaks the blind-review rules (all faults listed at once)."""
    from PIL import Image
    faults = []
    for p in images:
        im = Image.open(p)
        w, h = im.size
        if max(w, h) > MAX_SIDE or max(w / h, h / w) > MAX_ASPECT:
            faults.append(f"{p}: {w}x{h} is a sheet, not a crop (crop each region; max side {MAX_SIDE}, aspect {MAX_ASPECT})")
        g = grid_gutters(im)
        if g:
            faults.append(f"{p}: {g} (a contact sheet: the reviewer sees ONE view per turn, Joe 2026-10-19)")
        band = caption_band(im)
        if band:
            faults.append(f"{p}: a caption in its {band} band (the reviewer sees no captions: crop it off)")
    for t in [*names, context]:
        m = CLAIM.search(t or "")
        if m:
            faults.append(f"{t!r}: {m.group(0)!r} is a number or a claim (names and --context are neutral words only)")
    if faults:
        raise InputRefused("review input refused:\n  " + "\n  ".join(faults))


def result(review_md) -> dict:
    """What a review.md says: ran (a VERDICT line and no REVIEW FAILED mark), the verdict, MAJOR / MINOR counts
    (OTHER STAGES excluded)."""
    text = Path(review_md).read_text(errors="replace")
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    ran = bool(lines) and not text.lstrip().startswith("REVIEW FAILED") and "VERDICT:" in lines[-1]
    verdict = re.search(r"VERDICT:\s*(\w+)", lines[-1]).group(1) if ran else None
    major = minor = 0
    other = False
    for ln in lines:
        if ln.lstrip("# ").upper().startswith("OTHER STAGES") or (ln.startswith("#") and "OTHER" in ln.upper()):
            other = True
        if other:
            continue
        major += len(re.findall(r"\bMAJOR\b", ln))
        minor += len(re.findall(r"\bMINOR\b", ln))
    return {"ran": ran, "verdict": verdict, "major": major if ran else None, "minor": minor if ran else None}


def majors(review_md) -> int:
    """MAJOR count of a review that ran; ReviewNotRun otherwise (never 0 for a review that didn't happen)."""
    r = result(review_md)
    if not r["ran"]:
        raise ReviewNotRun(f"{review_md}: the review did not run (REVIEW FAILED / no VERDICT line): not 0 MAJORs")
    return r["major"]
