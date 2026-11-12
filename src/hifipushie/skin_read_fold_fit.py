"""Folds: `fold_text` and `fold_fit`. Part of the skin read (skin_read.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_read

def fold_text(fr: dict) -> str:
    L = ["  FOLDS and LINES the shape model does not make (a valley across each feature's landmark path; log luminance; "
         "diff = the picture's over ours):"]
    for name, row in fr["folds"].items():
        if not row["readable"]:
            L.append(f"    {name:13s} {row['why']}")
            continue
        for sd, s in row["sides"].items():
            tag = f"{name}{sd}"
            if s.get("present") is None:
                L.append(f"    {tag:13s} {s['why']}")
                continue
            verdict = (f"PRESENT ({s.get('by') or 'valley'}), ours lacks it") if s["present"] else ("ours has more than the picture" if s["absent_in_picture"] else
                                                                       ("as ours" if s["picture"] >= skin_read.FOLD_T else "absent"))
            L.append(f"    {tag:13s} {verdict:36s} picture {s['picture']:.3f} ours {s['ours']:.3f} diff {s['diff']:.3f} excess {s['excess']:.3f}"
                     + (f" step {s['step']:.3f}/cross-light along {int(100 * s['step_share'])} %" if s.get("step") else "") +
                     f" along {int(100 * s['share'])} %" + (f", extent {s.get('extent')}, shift mm {s.get('shift')}" if s["present"] else "") +
                     f"; confidence {s['confidence']} (views {s['views']})" +
                     ("\n" + " " * 18 + "lash line (mm over the picture's lashes; nominal = our path): " + "; ".join(
                         f"col {q['col']}: line {q['tps']} dark {q['dark']} (ours {q['dark_ours']}), nominal {q['nominal']}" for q in s["lash"]["columns"])
                      if s.get("lash") else ""))
    for name, row in fr["fields"].items():
        L.append(f"    {name + ' lines':13s} " + (f"fine-line energy over the cheek's: picture {row['picture']}, ours {row['ours']} (diff {row['diff']:+.3f}; REPORTED ONLY: follows the light)"
                                                   if row["readable"] else row["why"]))
    return "\n".join(L)


def fold_fit(sk: dict, fr: dict, first: bool, lid_prior: bool = False) -> list:
    """skin["folds"] and the fine-line amounts of skin["wrinkles"] set from a fold read (in place). Returns changes."""
    from . import skin_folds as sf
    changes, stuck = [], []
    folds = dict(sk.get("folds") or {})
    cur = sf.options(folds)
    for name, row in fr["folds"].items():
        if not row["readable"]:
            if name == "lid_fold" and name not in cur and lid_prior:
                from . import skin_params
                pp = skin_params.params({"skin": sk})
                masc = float(pp.get("masc", 0.0)) if sk.get("sex") is not None else 0.5
                show = skin_read.LID_PRIOR["show"][0] + (skin_read.LID_PRIOR["show"][1] - skin_read.LID_PRIOR["show"][0]) * masc
                sh = round(show - skin_read.LID_PRIOR["nominal"], 2)
                entry = {"amount": skin_read.LID_PRIOR["amount"], "roll": round(1.0 + 1.2 * skin_params._age_curve(pp["age"], 35, 75), 2),
                         "L": {"shift": [sh] * 3}, "R": {"shift": [sh] * 3}}
                hood = round(0.9 * skin_params._age_curve(pp["age"], 40, 75), 2)
                if hood >= 0.05:
                    entry["hood"] = hood
                folds[name] = entry
                changes.append((f"folds.{name}", "none", entry, f"INFERRED, NOT READ ({row.get('why', 'cannot tell')}): every lid has a fold and the shape "
                                f"model's is soft; laid from norms (platform show {show:.1f} mm over the lashes, hooding by age {pp['age']:.0f}). "
                                "Check it against the person; set skin.folds.lid_fold yourself or to 0"))
            continue
        old = cur.get(name)
        new_sides, amounts = {}, {}
        for sd, s in row["sides"].items():
            os_ = (old["sides"][sd] if old else {"amount": 0.0, "shift": [], "extent": [0.0, 1.0]})
            a0 = (old["amount"] * os_["amount"]) if old else 0.0
            if s.get("present") is None:
                amounts[sd], new_sides[sd] = a0, os_
                continue
            leg = skin_read.LEGACY.get(name)
            a_leg = skin_read.LEGACY_SHARE * float((sk.get("wrinkles") or {}).get(leg, 0.0)) if (leg and old is None and s["present"]) else 0.0
            a1 = a0
            if s["present"] and s["confidence"] >= skin_read.FOLD_CONF:
                gain = (s["amount"] if "amount" in s else min(s["step"] / skin_read.STEP_REF[name], max(skin_read.STEP_MAX - a0, 0.0)) if s.get("by") == "step"
                        else s["diff"] / skin_read.FOLD_REF[name])
                a1 = float(np.clip(a0 + a_leg + gain, 0, 1.5))
                if a0 > 0.2 and s.get("by") == "valley" and s["ours"] < 0.5 * a0 * skin_read.FOLD_REF[name]:
                    # ours is laid and does not read under this light: more paint will not make it a form (a flat
                    # frontal light hides painted relief; the picture's fold is geometry + occlusion)
                    a1 = a0
                    stuck.append(f"{name}{sd}")
            elif s["absent_in_picture"] and a0 > 0:
                if s["picture"] >= skin_read.FOLD_T and s.get("by") != "lash line":
                    # the picture has it, ours has more: toward the picture's share of ours, at most halved a round
                    a1 = float(a0 * np.clip(s["picture"] / max(s["ours"], 1e-6), 0.5, 1.0))
                else:
                    a1 = float(np.clip(a0 - s["excess"] / (skin_read.LID_REF if s.get("by") == "lash line" else skin_read.FOLD_REF[name]), 0, 1.5))
            amounts[sd] = a1
            shift = os_["shift"]
            if s.get("move") and a0 > 0.2:        # ours has it: move it by the two valleys' distance
                base = np.interp(np.linspace(0, 1, len(s["move"])), np.linspace(0, 1, len(shift)), shift) if shift else np.zeros(len(s["move"]))
                shift = [round(float(x), 2) for x in base + np.asarray(s["move"])]
            elif s["present"] and "shift" in s:
                shift = s["shift"]
            ext = s["extent"] if (s["present"] and "extent" in s and s["extent"][1] - s["extent"][0] > 0.2) else os_["extent"]
            me = sf.FOLDS[name].get("min_extent")
            if me and ext[1] - ext[0] < me:    # (a soft fold laid along a third of its path is a nick: a scar, not a fold)
                mid = float(np.clip(0.5 * (ext[0] + ext[1]), me / 2, 1 - me / 2))
                ext = [round(mid - me / 2, 2), round(mid + me / 2, 2)]
            new_sides[sd] = {"shift": shift, "extent": ext}
        # a fold both sides of every face have (the lid's crease): read on one side only, the other takes it over
        # (hair, a shadow or the pose hid it there): INFERRED, and said so
        mirrored = None
        if name in skin_read.BILATERAL and len(amounts) == 2:
            (sa, sb) = list(amounts)
            for one, other in ((sa, sb), (sb, sa)):
                so, sn = row["sides"][one], row["sides"][other]
                if so.get("present") and so["confidence"] >= skin_read.FOLD_CONF and not sn.get("present") and amounts[other] < 0.5 * amounts[one]:
                    amounts[other] = amounts[one]
                    new_sides[other] = {"shift": list(new_sides[one]["shift"]), "extent": list(new_sides[one]["extent"])}
                    mirrored = (one, other)
        # SYMMETRY AS THE PRIOR (skinfolds2): one side read with confidence, the other NOT READABLE (not seen, or pictures
        # too coarse to place a fold: there "not found" is no evidence of absence): the unread side takes the read
        # side's amount whole, INFERRED and said. (On pictures fine enough to place a fold a side that reads absent
        # stays absent: foldval's one-sided marionette.) Before: Garrett's left bag came out at 0.16 beside 0.44.
        if name in skin_read.SYMMETRIC and len(amounts) == 2 and mirrored is None:
            (sa, sb) = list(amounts)
            for one, other in ((sa, sb), (sb, sa)):
                so, sn = row["sides"][one], row["sides"][other]
                poor = sn.get("present") is None or "placed" in sn
                if (so.get("present") and so["confidence"] >= skin_read.FOLD_CONF and not sn.get("present") and poor and amounts[other] < 0.8 * amounts[one]) or \
                        (poor and "placed" in so and not so.get("present") and not sn.get("present") and amounts[one] > 0.2 and amounts[other] < 0.8 * amounts[one]
                         and (cur.get(name) or {}).get("sides", {}).get(one, {}).get("amount", 0) > 0):
                    amounts[other] = amounts[one]
                    new_sides[other] = {"shift": list(new_sides[other]["shift"]), "extent": list(new_sides[one]["extent"])}
                    mirrored = (one, other, "symmetry")
                    break
        if name in skin_read.SYMMETRIC and len(amounts) == 2 and mirrored is None:
            (sa, sb) = list(amounts)
            for one, other in ((sa, sb), (sb, sa)):
                so, sn = row["sides"][one], row["sides"][other]
                if (so.get("present") and so["confidence"] >= skin_read.FOLD_CONF and not sn.get("present") and sn.get("present") is not None
                        and sn["picture"] >= skin_read.FOLD_T and sn["picture"] > sn["ours"] and amounts[other] < 0.4 * amounts[one]):
                    amounts[other] = amounts[one] * float(np.clip(sn["picture"] / max(so["picture"], 1e-6), 0.3, 1.0))
                    new_sides[other] = {"shift": list(new_sides[other]["shift"]), "extent": list(new_sides[other]["extent"])}
                    mirrored = (one, other)
        top = max(amounts.values()) if amounts else 0.0
        a_old = old["amount"] if old else 0.0
        if top < 0.08:
            if old:
                folds.pop(name, None)
                changes.append((f"folds.{name}", round(a_old, 2), "off", "the pictures do not show it"))
            continue
        moved = any(row["sides"][sd].get("move") for sd in row["sides"])
        if old is not None and abs(top - a_old) < 0.06 and not moved and all(not row["sides"][sd].get("present") for sd in row["sides"]):
            continue
        entry = {"amount": round(top, 3)}
        for sd, q in new_sides.items():
            e = {**({"amount": round(amounts[sd] / top, 3)} if abs(amounts[sd] / top - 1) > 0.05 else {}),
                 **({"shift": q["shift"]} if q["shift"] else {}), **({"extent": q["extent"]} if list(q["extent"]) != [0.0, 1.0] else {})}
            if sd:
                if e:
                    entry[sd[1:]] = e
            else:
                entry.update(e)
        if old:
            for kk in ("width", "roll", "depth", "hood"):
                if kk in (sk["folds"].get(name) if isinstance(sk["folds"].get(name), dict) else {}):
                    entry[kk] = sk["folds"][name][kk]
        folds[name] = entry
        why = "; ".join(f"{name}{sd}: valley {s['picture']:.3f} (ours {s['ours']:.3f}) along {int(100 * s['share'])} %, confidence {s['confidence']}"
                        for sd, s in row["sides"].items() if s.get("present") is not None)
        if mirrored:
            why += (f"; {name}{mirrored[1]} was not read: it takes {name}{mirrored[0]}'s (INFERRED: both sides have this fold)" if name in skin_read.BILATERAL else
                    f"; {name}{mirrored[1]} CANNOT BE READ in these pictures (not seen, or too coarse to place a fold): it takes {name}{mirrored[0]}'s amount "
                    f"(INFERRED from the other side: these folds come in pairs; set skin.folds.{name}.{mirrored[1][1:]}.amount if the person is not symmetric)"
                    if len(mirrored) == 3 else
                    f"; {name}{mirrored[1]} shows a valley along too little of its path to count: it takes {name}{mirrored[0]}'s amount x its own "
                    f"valley's share (INFERRED: these folds come in pairs)")
        changes.append((f"folds.{name}", round(a_old, 2) if old else "none", entry, why))
        leg = skin_read.LEGACY.get(name)
        if leg and old is None and float((sk.get("wrinkles") or {}).get(leg, 1.0)) != 0.0:
            sk.setdefault("wrinkles", {})[leg] = 0.0
            changes.append((f"wrinkles.{leg}", "by age / as set", 0.0, f"replaced by the measured folds.{name}"))
    if folds:
        sk["folds"] = folds
    else:
        sk.pop("folds", None)
    if stuck:
        changes.append(("folds (NOT raised)", "", "", ", ".join(stuck) + ": laid, yet our render shows less than a third of what that "
                        "amount should read under the picture's light. Painted relief does not carry it: the picture's fold is "
                        "geometry (sculpt / block-in), not more paint"))
    from . import skin_params
    p = skin_params.params({"skin": sk})
    for name, row in fr["fields"].items():
        # FIELD_FIT is off: the validation's null (the same lines in picture and ours, another light) read +0.47 where
        # lines against none read +0.65: fine-line energy follows the light as much as the lines. Reported, not fitted.
        if not skin_read.FIELD_FIT or not row["readable"] or abs(row["diff"]) < skin_read.FIELD_T:
            continue
        age = p["age"]
        dflt = {"forehead": skin_params._age_curve(age, 26, 72), "crows_feet": skin_params._age_curve(age, 28, 70),
                "under_eye": skin_params._age_curve(age, 30, 75), "lip_lines": skin_params._age_curve(age, 48, 85)}[name]
        a0 = float((sk.get("wrinkles") or {}).get(name, dflt))
        a1 = round(float(np.clip(a0 + row["diff"] / skin_read.FIELDS[name][2], 0, 2.0)), 3)
        if abs(a1 - a0) > 0.08:
            sk.setdefault("wrinkles", {})[name] = a1
            changes.append((f"wrinkles.{name}", round(a0, 3), a1, f"fine-line energy over the cheek's: picture {row['picture']}, ours {row['ours']}"))
    return changes
