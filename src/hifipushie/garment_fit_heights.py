"""Step 0's heights (garment_fit.py), for any garment: each garment edge is read ON a part of the body, between that
part's own landmarks, so a pose that differs between the picture and the model can't move it (t s0-4: a sleeve end read
straight up landed above the A-posed model's wrist; a jacket hem read near the wrist was measured on the arm).

PARTS: torso (read straight up: it stands the same in any picture), leg and arm (read ALONG the limb: hip -> knee ->
ankle, shoulder -> elbow -> wrist; the fraction between two of the limb's landmarks on the picture, placed at the same
fraction of the model's limb between the same two). A height says `on` (default "torso"). A torso edge that maps below
the model's crotch is on a leg; one past the end of a limb is refused.
NEIGHBOURS (the landmark check, garment_fit.DRIFT): torso + leg landmarks (both stand straight), never the arm (posed);
two landmarks closer than MIN_SPAN on the model don't predict each other's span (t s0-4: armpit + chest 15 px apart
extrapolated the waist 127 mm off).
"""
from __future__ import annotations

PARTS = {"torso": ("eyes", "neck", "shoulder", "armpit", "chest", "waist", "high_hip", "hips", "seat", "crotch"),
         "leg": ("hips", "crotch", "mid_thigh", "knee", "calf", "ankle"),
         "arm": ("shoulder", "upper_arm", "elbow", "wrist")}
CHAINS = {"leg": (("thigh", "hip", "knee"), ("shin", "knee", "ankle")),
          "arm": (("arm", "shoulder", "elbow"), ("forearm", "elbow", "wrist"))}
MIN_SPAN = 60.0  # mm on the model: neighbours closer than this don't predict a span
STANDING = ("torso", "leg")  # (the parts whose landmarks the neighbour check compares: they stand the same in a picture)


def standing(lms: dict) -> dict:
    return {k: v for k, v in lms.items() if any(k in PARTS[p] for p in STANDING) and k not in PARTS["arm"][1:]}


def _pair(marks: dict, pos: dict, v) -> tuple:
    """(a, b, inner): the two landmarks a height is read between. Inside: the ones either side, unless closer than
    MIN_SPAN on the model (then the next ones out). Beyond them: the nearest and the farthest (t s0-4: a collar top
    extrapolated from the neck + shoulder, 63 mm apart, came out at the eyes)."""
    above = sorted((k for k in marks if marks[k] <= v), key=lambda k: -marks[k])
    below = sorted((k for k in marks if marks[k] > v), key=lambda k: marks[k])
    if above and below:
        for b in below:
            for a in above:
                if abs(pos[a] - pos[b]) >= MIN_SPAN:
                    return a, b, True
        return above[0], below[-1], True
    near = (above or below)[0]
    far = (above or below)[-1]
    return near, far, False


def read(hts: list, lms: dict, lfrom: dict, body, view, vi, skipped, bad: list) -> dict:
    """{name: height} for each garment edge, on its part. bad gets every fault."""
    from . import garment_fit_marks as gm
    out = {}
    for h in hts:
        on = h.get("on") or "torso"
        if on not in PARTS:
            bad.append(f"fit.heights {h['name']!r}: on {on!r}: one of {', '.join(PARTS)}")
            continue
        mine = {k: v for k, v in lms.items() if k in PARTS[on]}
        if len(mine) < 2:
            bad.append(f"fit.heights {h['name']!r} on the {on}: needs 2 of the {on}'s landmarks marked "
                       f"({', '.join(PARTS[on])}); have {', '.join(mine) or 'none'}")
            continue
        pos = {k: (body.at(k, view)["z_mm"] if on == "torso" else body.along(on, k, view)) for k in mine}
        a, b, inner = _pair(mine, pos, h["v"])
        f = (h["v"] - mine[a]) / (mine[b] - mine[a]) if mine[b] != mine[a] else 0.0
        if on == "torso":
            za, zb = body.at(a, view)["z_mm"], body.at(b, view)["z_mm"]
            zz = za + f * (zb - za)
            sa, sb = gm.sensitivity(h["v"], mine[a], mine[b], za, zb)
            try:
                crotch = body.at("crotch", view)["z_mm"]
            except Exception:  # (a body without one: tests)
                crotch = -1e9
            if zz < crotch - 10:
                bad.append(f"fit.heights {h['name']!r}: on the torso it maps {crotch - zz:.0f} mm below the model's "
                           "crotch, where there is no torso: an edge down there is on a leg (on: 'leg'), or the torso "
                           "landmarks are off")
                continue
            along, how = None, f"straight up between the model's own {a} ({za:.0f} mm) and {b} ({zb:.0f} mm)"
        else:
            s = {k: body.along(on, k, view) for k in (a, b)}
            ss = s[a] + f * (s[b] - s[a])
            total = body.limb_length(on)
            if not -10 <= ss <= total + 10:
                end = CHAINS[on][0][1] if ss < 0 else CHAINS[on][-1][2]
                bad.append(f"fit.heights {h['name']!r}: along the {on} it maps {abs(ss if ss < 0 else ss - total):.0f} mm "
                           f"past the {end}: re-mark it or the {on}'s landmarks")
                continue
            along = body.point_along(on, min(max(ss, 0.0), total))
            zz = along["z_mm"]
            sa, sb = gm.sensitivity(h["v"], mine[a], mine[b], s[a], s[b])
            how = (f"along the model's {on} between its {a} and {b} ({abs(s[b] - s[a]):.0f} mm apart along it), "
                   f"{ss:.0f} mm from the {CHAINS[on][0][1]}")
        out[h["name"]] = dict(z_mm=round(zz, 1), on=on, fraction=round(f, 3), between=[a, b], extrapolated=not inner,
                              landmarks={a: lfrom[a], b: lfrom[b]}, mm_per_10px={a: sa, b: sb},
                              **({"along": along} if along else {}),
                              source=f"{f:.3f} of the way from the {a} to the {b} on view {vi}, {how}"
                                     + (" (EXTRAPOLATED beyond them)" if not inner else "")
                                     + (f"; the {' / '.join(skipped)} not used (in a picture: the shoe's sole / the "
                                        "hair, not the body's)" if skipped else "")
                                     + (f"; {h['source']}" if h.get("source") else ""))
    return out


def section(body, height: dict, view):
    """The body's section at a garment edge's height: across its limb there, or the torso level."""
    if (height.get("along") or {}).get("bone"):
        a = height["along"]
        return body.section_on(a["bone"], a["t"], view), f"{a['bone']} at {a['t']:.2f} along it"
    return body.section_on("body", height["z_mm"], view), f"the torso at {height['z_mm']:.0f} mm"
