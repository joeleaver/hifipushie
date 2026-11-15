"""The step-2 look's panel seams (F4, t s4-28): step 2's shares drawn round the body, where Joe approves step 2.

On the reference (the view step 0 read the girth's width on): the girth's level as a thin line across the garment and
each seam the shares put on that view's side of the body as an orange tick on both sides, each visible piece named
with its share. In a corner, the girth from above (front down): the body's own ring, every seam as a spoke, every piece
named with its share, so a piece behind the side (a side body, the back) is seen too: a side body of 0.08 reads as the
sliver it is. The positions are panel_shares' `placed` (the text answer gives them in mm: pictures for shape, C288)."""
from __future__ import annotations

from .panel_shares import width_row

ORANGE, WHITE = (255, 150, 40), (240, 240, 240)
LEGEND = [("orange tick = a panel seam at its girth's level,", ORANGE), ("   where step 2's shares put it", ORANGE),
          ("orange inset = that girth from above, front", ORANGE), ("   down: every seam a spoke, pieces named", ORANGE)]


def ticks(e: dict, read: dict, vi: int, side: str) -> list:
    """[(u, v, label)] in the picture's own px: the seams of panels entry e seen on view vi (both sides), else []."""
    wr, pl = width_row(read, e["girth"], vi), e.get("placed")
    if wr is None or not pl:
        return []
    out = []
    for sm in pl["seams"]:
        if sm["seen_from"] == side:
            out += [(wr["centre"] + k * abs(sm["t"]) * wr["half"], wr["v"], " / ".join(sm["between"])) for k in (-1, 1)]
    return out


def draw(d, s: float, vi: int, plan: dict, read: dict, label, line) -> list:
    """Draw every panels entry on view vi (scale s); returns the legend lines (none when nothing is drawn)."""
    side = (read.get("views") or [{}])[vi].get("view")
    drawn, corner = False, 0
    for e in plan.get("panels") or []:
        pl, wr = e.get("placed"), width_row(read, e["girth"], vi)
        if not pl or wr is None:
            continue
        drawn = True
        line(d, [((wr["centre"] - wr["half"]) * s, wr["v"] * s), ((wr["centre"] + wr["half"]) * s, wr["v"] * s)],
             WHITE, 1, (6, 6))
        for u, v, _ in ticks(e, read, vi, side):
            d.line([(u * s, (v - 45) * s), (u * s, (v + 45) * s)], fill=ORANGE, width=5)
        for pc in pl["pieces"]:
            if pc["seen_from"] == side:
                label(d, ((wr["centre"] + abs(pc["mid_t"]) * wr["half"]) * s - 30, (wr["v"] - 80) * s),
                      f"{pc['piece']} {pc['share']:.2f}", ORANGE)
        _inset(d, e, corner, label, line)
        corner += 1
    return LEGEND if drawn else []


def _inset(d, e: dict, k: int, label, line):
    """The girth from above in the picture's lower-left corner (the k-th entry above the one before)."""
    pl = e["placed"]
    R = pl["ring"]
    xm = max(abs(x) for x, _ in R) or 1.0
    ys = [y for _, y in R]
    box = 300
    sc = 0.36 * box / xm
    cx, cy = 20 + box / 2, d.im.size[1] - 40 - box / 2 - k * (box + 20)
    ym = (max(ys) + min(ys)) / 2
    P = lambda x, y: (cx + x * sc, cy - (y - ym) * sc)  # noqa: E731  (front, -Y, down)
    d.rectangle([cx - box / 2, cy - box / 2 - 30, cx + box / 2, cy + box / 2 + 10], fill=(0, 0, 0), outline=ORANGE)
    d.text((cx - box / 2 + 8, cy - box / 2 - 26), f"{e['girth']} from above, front down", fill=ORANGE)
    for sg in (1, -1):
        line(d, [P(sg * x, y) for x, y in R], WHITE, 2, None)
        for sm in pl["seams"]:
            x, y = sm["xy"]
            d.line([P(0, ym), P(sg * x * 1.25, ym + (y - ym) * 1.25)], fill=ORANGE, width=3)
    for pc in pl["pieces"]:
        x, y = pc["xy"]
        u, v = P(x * 1.45, ym + (y - ym) * 1.45)
        txt = f"{pc['piece']} {pc['share']:.2f}"
        d.text((min(u, cx + box / 2 - 8 * len(txt)), v - 7), txt, fill=ORANGE)
