"""The atlas layout: the skyline packer, density, `layout`, a card's coordinates. Part of hair clumps (hair_clumps.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_clumps

def _skyline(sizes, W: int, H: int):
    """Bottom-left skyline packing (few boxes: the shared tiles): short islands stack under the tall ones' shelf."""
    from numpy.lib.stride_tricks import sliding_window_view
    sky = np.zeros(W, int)
    pos = [None] * len(sizes)
    for i in np.argsort([-h for _, h in sizes], kind="stable"):
        w, h = sizes[i]
        w_ = w + hair_clumps.PAD
        if w > W:
            return None
        top = sliding_window_view(np.r_[sky, np.zeros(hair_clumps.PAD, int)], w_).max(1)[:W - w + 1]
        x = int(np.argmin(top))
        if top[x] + h > H:
            return None
        pos[i] = (x, int(top[x]))
        sky[x:x + w_] = top[x] + h + hair_clumps.PAD
    return pos


def _pack(sizes, W: int, H: int):
    """Shelf packing of (w, h) boxes into W x H, tallest first: [(x, y)] or None if they don't fit."""
    if len(sizes) <= 64:
        return _skyline(sizes, W, H)
    order = np.argsort([-h for _, h in sizes], kind="stable")
    pos = [None] * len(sizes)
    x = y = shelf = 0
    for i in order:
        w, h = sizes[i]
        if x + w > W:
            x, y, shelf = 0, y + shelf + hair_clumps.PAD, 0
        if y + h > H or w > W:
            return None
        pos[i] = (x, y)
        x += w + hair_clumps.PAD
        shelf = max(shelf, h)
    return pos


def _density(c: dict) -> float:
    """Texel density of a card's island relative to the rest: coverage cards lie under two layers (Epic's tutorial:
    the coverage layer repeats few textures, the budget goes to the visible layers)."""
    return hair_clumps.DENSITY.get(c.get("cls"), {}).get(int(c["layer"]), 1.0)


def layout(cards: list, W: int, H: int, aniso: float | None = None) -> tuple[list, float]:
    """Each baked card's island (x, y, w, h) px in a W x H block, at the finest texel that fits (per card x its
    _density)."""
    ANISO_ = hair_clumps.ANISO if aniso is None else float(aniso)
    dens = [_density(c) for c in cards]
    area = sum(float(c["s"][-1]) * 2 * float(np.max(c["hw"])) * d * d for c, d in zip(cards, dens))
    ra = np.sqrt(area / (ANISO_ * hair_clumps.FILL * W * H))  # m across a texel
    for _ in range(60):
        sizes = [(int(np.clip(np.ceil(2 * float(np.max(c["hw"])) * d / ra), 4, W)),
                  int(np.clip(np.ceil(float(c["s"][-1]) * d / (ANISO_ * ra)), 8, H))) for c, d in zip(cards, dens)]
        pos = _pack(sizes, W, H)
        if pos is not None:
            return [(p[0], p[1], s[0], s[1]) for p, s in zip(pos, sizes)], float(ra)
        ra *= 1.04
    raise ValueError("hair bake: the islands do not fit the block")


def _card_coords(c: dict, q: np.ndarray, smooth: bool = False):
    """Points q (k, 3) in a card's own frame: (across m, along m from the card's start, depth m over its plane)."""
    P = np.asarray(c.get("P_fit", c["P"]), float)  # (the arch row's picture: its strands, not the raised line)
    from scipy.spatial import cKDTree
    i = cKDTree(P).query(q)[1]
    d = q - P[i]
    ax, al, dp = (d * c["X"][i]).sum(-1), c["s"][i] + (d * c["T"][i]).sum(-1), (d * c["N"][i]).sum(-1)
    if smooth and len(q) > 4:  # one strand's points in order: its coordinates jump where its nearest station switches
        # (off-centre points at a bend; ~40% of the tail's strands had one, drawn as stair steps across the flow)
        from scipy.ndimage import gaussian_filter1d, median_filter
        ax, al = (gaussian_filter1d(median_filter(v, 5, mode="nearest"), 1.0, mode="nearest") for v in (ax, al))
    return ax, al, dp
