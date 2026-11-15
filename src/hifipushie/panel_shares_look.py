"""The step-2 look's panel seams (F4, t s4-28): step 2's shares drawn round the body, where Joe approves step 2.

On the reference (the view step 0 read the girth's width on): the girth's level as a thin line across the garment and
each seam the shares put on that view's side of the body as an orange tick on both sides, each visible piece named
with its share. In a corner, the girth from above (front down): the body's own ring, every seam as a spoke, every piece
named with its share, so a piece behind the side (a side body, the back) is seen too: a side body of 0.08 reads as the
sliver it is. The positions are panel_shares' `placed` (the text answer gives them in mm: pictures for shape, C288)."""
from __future__ import annotations

from .panel_shares import width_row

ORANGE, WHITE = (255, 150, 40), (240, 240, 240)
PIECE = [(255, 150, 40), (60, 230, 255), (120, 255, 140), (255, 120, 200)]  # (the inset's pieces, front to back)
SIDE_T = 0.97  # a seam this near the side is at the silhouette: drawn on the front and the back view
LEGEND = [("orange tick = a panel seam at its girth's level,", ORANGE), ("   where step 2's shares put it", ORANGE),
          ("inset = that girth from above, front down:", ORANGE), ("   each piece its own colour, seams ticked", ORANGE)]


def ticks(e: dict, read: dict, vi: int, side: str) -> list:
    """[(u, v, label)] in the picture's own px: the seams of panels entry e seen on view vi (both sides), else []."""
    wr, pl = width_row(read, e["girth"], vi), e.get("placed")
    if wr is None or not pl:
        return []
    out = []
    for sm in pl["seams"]:
        if sm["seen_from"] == side or abs(sm["t"]) >= SIDE_T:
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
            if pc["seen_from"] == side or abs(pc["mid_t"]) >= SIDE_T:
                label(d, ((wr["centre"] + abs(pc["mid_t"]) * wr["half"]) * s - 30, (wr["v"] - 80) * s),
                      f"{pc['piece']} {pc['share']:.2f}", ORANGE)
        _inset(d, e, corner, label, line)
        corner += 1
    return LEGEND if drawn else []


def _inset(d, e: dict, k: int, label, line):
    """The girth from above in the picture's lower-left corner (the k-th entry above the one before)."""
    from .garment_plan_look import FONT_LEG
    pl = e["placed"]
    R = pl["ring"]
    xm = max(abs(r[0]) for r in R) or 1.0
    ys = [r[1] for r in R]
    box = 380
    sc = 0.36 * box / xm
    cx, cy = 20 + box / 2, d.im.size[1] - 40 - box / 2 - k * (box + 20)
    ym = (max(ys) + min(ys)) / 2
    P = lambda x, y: (cx + x * sc, cy - (y - ym) * sc)  # noqa: E731  (front, -Y, down)
    d.rectangle([cx - box / 2, cy - box / 2 - 30, cx + box / 2, cy + box / 2 + 10], fill=(0, 0, 0), outline=ORANGE)
    d.text((cx - box / 2 + 8, cy - box / 2 - 26), f"{e['girth']} from above, front down", fill=ORANGE, font=FONT_LEG)
    bounds = [sm["s_mm"] for sm in pl["seams"]]
    col = lambda s_: PIECE[sum(s_ > b for b in bounds) % len(PIECE)]  # noqa: E731
    for sg in (1, -1):
        for a_, b_ in zip(R, R[1:]):
            d.line([P(sg * a_[0], a_[1]), P(sg * b_[0], b_[1])], fill=col((a_[2] + b_[2]) / 2), width=7)
        for sm in pl["seams"]:
            x, y = sm["xy"]
            d.line([P(sg * x * 0.8, ym + (y - ym) * 0.8), P(sg * x * 1.2, ym + (y - ym) * 1.2)], fill=WHITE, width=3)
    for j, pc in enumerate(pl["pieces"]):
        x, y = pc["xy"]
        u, v = P(x * 1.45, ym + (y - ym) * 1.45)
        txt = f"{pc['piece']} {pc['share']:.2f}"
        w = d.textlength(txt, font=FONT_LEG)
        d.text((min(max(u - w / 2, cx - box / 2 + 4), cx + box / 2 - w - 4), v - 9), txt, fill=PIECE[j % len(PIECE)],
               font=FONT_LEG)
