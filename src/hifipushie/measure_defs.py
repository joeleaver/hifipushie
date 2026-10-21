"""Measurement definitions at the draft boundary: every measurement a draft consumes, in the CONSUMER's definition.

The tape (tailor.measure) measures each quantity once, by its own stated definition (its docstring; ANSUR II / ISO
8559-1 where it cites them). A draft (a FreeSewing design, one of our blocks, the jacket rules) reads a measurement by
ITS author's definition. Where the two differ, an ADAPTER here converts the tape's value into the consumer's; the
draft never reads a measurement that has no declared definition for it (`for_consumer` raises DefinitionError).
The reference table, with sources and Garrett's / Tess's values: docs/notes/measurements.md.

Why (measure audit 2026-10-20, M1): two of the costliest garment faults in 34 rounds were definition mismatches at
this boundary: shoulderSlope (the tape's line fit 10.9 deg vs the hps -> shoulder point chord every draft places its
shoulder point with, 22.5: C61, C117) and the neck point / neck split (C113); FreeSewing's "hips" is the top of the
hip bone (iliac crest), ours was the hip joint's level, 106-125 mm lower (M2).

  CONSUMERS   {consumer: {measurement: (status, adapter or None, their definition + source)}}
              status: "match" | "adapter" (differs; converted here) | "ambiguous" (their source doesn't pin it; ours
              is a stated reading of it).
  consumer_of(g)          the consumer a garment's pattern is drafted by ("freesewing:simon", "block:bodice", ...)
  for_consumer(c, mm, at, holds)  (mm in c's definitions, info): adapters applied, held ones reported
  holds_for(g, kind_kb)   measurements a garment (or its kind, garment_kb kinds.<kind>.definition_holds) keeps on the
              tape's legacy value until it is refitted: {measurement: reason}. A hold is a known, declared mismatch.
  gate_row(c, mm, holds)  the pattern gate's row "measure_definitions": FAIL when the consumer has no declared
              definitions, INFO "HELD" when a mismatch is held, PASS otherwise.
"""
from __future__ import annotations

FS = "FreeSewing 4.10.2"
FSDOC = "freesewing.org/docs/measurements/"
BRIAN = f"{FS} brian/src/base.mjs"


class DefinitionError(ValueError):
    pass


# ---------------------------------------------------------------- adapters: (mm, at) -> {measurement: value}
def _chord(mm: dict, at: dict) -> dict:
    """shoulderSlope as every draft here uses it: the angle of the hps -> shoulder point chord. Brian places the
    shoulder point on the beam from the hps at -shoulderSlope to x = shoulderToShoulder / 2 (base.mjs, points.shoulder);
    our bodice block does the same (sy = (sx - nw) tan slope). The tape's default mm value is a line fit over the top of
    the shoulder (tailor.SHOULDER_SLOPE "line"); the chord is at["shoulder_slope_chord"]."""
    v = at.get("shoulder_slope_chord")
    return {} if v is None else {"shoulderSlope": float(v)}


def _iliac_crest(mm: dict, at: dict) -> dict:
    """FreeSewing's hips: round the body at the top of the hip bones (the iliac crest), and waistToHips from the waist
    down to it. The tape's hips is at the hip joint + 2 cm (its own definition; the seat's window hangs off it); the
    crest's girth and level are the tape's highHip / waistToHighHip (ANSUR II iliocristale height, located from the
    crotch: tailor.ILIAC_CREST_OVER_CROTCH)."""
    out = {}
    if "highHip" in mm:
        out["hips"] = float(mm["highHip"])
    if "waistToHighHip" in mm:
        out["waistToHips"] = float(mm["waistToHighHip"])
    return out


ADAPTERS = {"chord": _chord, "iliac_crest": _iliac_crest}

# ---------------------------------------------------------------- the consumers' definitions
M, A, AMB = "match", "adapter", "ambiguous"
_BRIAN = {
    "biceps": (M, None, f"round the fullest part of the upper arm ({FSDOC}biceps)"),
    "chest": (M, None, f"round the fullest part of the chest, horizontal ({FSDOC}chest)"),
    "highBust": (M, None, f"round the chest just under the arms, above the bust; may tilt ({FSDOC}highbust); read only "
                          "with option draftForHighBust (plugin-bust), off in every table"),
    "hpsToBust": (AMB, None, f"HPS straight down to the bust line ({FSDOC}hpstobust): surface or vertical not stated"),
    "hpsToWaistBack": (A, None, f"HPS straight down the back to the waist ({FSDOC}hpstowaistback); cloth.length_level "
                                "re-bases it on the nape (napeToWaistBack + 0.05 neck) so the length is not the hps's"),
    "neck": (AMB, None, f"round the neck where a shirt collar sits ({FSDOC}neck): height not pinned"),
    "shoulderToShoulder": (M, None, f"shoulder tip to shoulder tip across the back ({FSDOC}shouldertoshoulder); NB "
                                    f"{BRIAN} then uses half of it as a HORIZONTAL half width"),
    "shoulderSlope": (A, "chord", f"degrees ({FSDOC}shoulderslope: the shoulder line's drop, points not named); "
                                  f"{BRIAN} points.shoulder: the beam from the HPS at -shoulderSlope = the hps -> "
                                  "shoulder point chord"),
    "waistToArmpit": (M, None, f"waist up the side to the armpit ({FSDOC}waisttoarmpit)"),
    "waistToHips": (A, "iliac_crest", f"waist down to the top of the hip bone, at the side ({FSDOC}waisttohips)"),
}
_LOWER = {
    "waist": (AMB, None, f"round the narrowest part, below the ribs, horizontal ({FSDOC}waist); ours is skeletal "
                         "(70 % pelvis -> chest joint): Garrett 15 mm, Tess 50 mm under the narrowest section"),
    "hips": (A, "iliac_crest", f"round the body at the top of the hip bones ({FSDOC}hips); not the seat"),
}
_SLEEVE = {
    "shoulderToWrist": (AMB, None, f"shoulder tip down the slightly bent arm to the wrist, over it ({FSDOC}"
                                   "shouldertowrist); ours: shoulder point -> elbow -> wrist joint centres"),
    "wrist": (M, None, f"round the wrist where it joins the hand ({FSDOC}wrist)"),
}
_SEAT = {
    "seat": (M, None, f"round the fullest part of the seat, horizontal ({FSDOC}seat)"),
    "waistToSeat": (M, None, f"vertical, waist to the seat line at the side ({FSDOC}waisttoseat)"),
    "waistToFloor": (M, None, f"vertical, waist to the floor ({FSDOC}waisttofloor)"),
}
OURS = "our own consumer: the tape's definition is the rule's (tailor.measure docstring)"


def _own(*names, status=M, note=OURS):
    return {n: (status, None, note) for n in names}


_BLOCK_UPPER = dict(
    {k: v for k, v in _BRIAN.items()},
    **{k: v for k, v in _LOWER.items()},
    **_own("napeToWaistBack", "hpsToArmpitBack", "hpsToSeatFront", "hpsToSeatBack", "neckBase", "napeBaseToWaistBack",
           "neckBaseFrontDrop", "hpsToWaistBackRaw", "bustSpan"),
)
_BLOCK_UPPER["neck"] = (AMB, None, _BRIAN["neck"][2] + "; a garment worn over another reads it round the under "
                                   "garment's collar (cloth.over_measures)")
_BLOCK_UPPER["highBust"] = (M, None, "bust dart = (chest - highBust) / 2 when > 8 mm (pattern_blocks.bodice), "
                                     + _BRIAN["highBust"][2].split(";")[0])

CONSUMERS: dict[str, dict] = {
    "freesewing:simon": dict(_BRIAN, **_LOWER, **_SLEEVE),
    "freesewing:jaeger": dict(_BRIAN, **_LOWER, **_SLEEVE),
    "freesewing:carlton": dict(_BRIAN, **_LOWER, **_SLEEVE, **_SEAT),
    "block:bodice": _BLOCK_UPPER,
    "block:knit": _BLOCK_UPPER,
    "rules:jacket": dict(_own("chest", "waist", "hpsToWaistBack", "waistToArmpit", "plumbGirth"),
                         neck=_BLOCK_UPPER["neck"], hips=_LOWER["hips"], waistToHips=_BRIAN["waistToHips"]),
    "block:sleeve": dict(_own("biceps", "shoulderToElbow"), **_SLEEVE),
    # the trouser and skirt blocks read hips only as the pair (hips, waistToHips) to interpolate a dropped waist
    # (pattern_blocks.dropped_waist): any level works while the pair is the same level's
    "block:trouser": _own("waist", "seat", "hips", "waistToHips", "waistToSeat", "waistToUpperLeg", "waistToKnee",
                          "waistToFloor", "knee", "calf", "heel", "ankle"),
    "block:skirt": _own("waist", "hips", "seat", "waistToHips", "waistToSeat", "waistToKnee"),
    "cloth:shared": _own("neckHeight", "chestDepth", "waistDepth", "neck", "waistToArmpit", "waist", "seat", "hips"),
}


def consumer_of(g: dict) -> str | None:
    """The draft that consumes a garment's measurements: "freesewing:<design>" or "block:<block>" (None: not drafted
    from the tape)."""
    from . import cloth
    p = (cloth.expanded(g).get("pattern") or {}) if g else {}
    fr = p.get("from")
    if fr == "draft":
        return f"block:{p.get('block', 'bodice')}"
    if fr and f"freesewing:{fr}" in CONSUMERS:
        return f"freesewing:{fr}"
    return None


def holds_for(g: dict, kind_kb: dict | None = None) -> dict:
    """{measurement: reason} kept on the tape's legacy value (a declared mismatch, until the garment is refitted on
    its consumer's definition): the garment's "definition_holds" over its kind's. The C117 garment key
    shoulder_slope "line" is a hold of shoulderSlope."""
    h = dict((kind_kb or {}).get("definition_holds") or {})
    for src_, d_ in (("kind", kind_kb or {}), ("garment", g or {})):
        if src_ == "garment":
            h.update(d_.get("definition_holds") or {})
        if d_.get("shoulder_slope") == "line":
            h["shoulderSlope"] = f"{src_} key shoulder_slope 'line'"
        elif d_.get("shoulder_slope") == "chord":
            h.pop("shoulderSlope", None)
    return h


def slope_definition(g: dict, kind_kb: dict | None = None) -> str:
    """"chord" when the garment's draft receives the chord shoulder slope, else "line" (the tape's default)."""
    c = consumer_of(g)
    ad = CONSUMERS.get(c or "", {}).get("shoulderSlope", (None, None, ""))[1]
    if c is None:
        return (g or {}).get("shoulder_slope") or (kind_kb or {}).get("shoulder_slope") or "line"
    return "line" if ad != "chord" or "shoulderSlope" in holds_for(g, kind_kb) else "chord"


def for_consumer(consumer: str | None, mm: dict, at: dict | None = None, holds: dict | None = None) -> tuple[dict, dict]:
    """The tape `mm` in `consumer`'s definitions. (mm, info): info["definitions"] {measurement: [adapter, tape value,
    consumer value]}, info["held"] {measurement: reason}."""
    if consumer is None:
        return mm, {}
    if consumer not in CONSUMERS:
        raise DefinitionError(f"no measurement definitions declared for consumer {consumer!r} (measure_defs.CONSUMERS: "
                              f"{', '.join(CONSUMERS)}); declare what it reads, by its source, before drafting from it")
    at, holds = at or {}, holds or {}
    out, info, held = dict(mm), {}, {}
    for k, (st, ad, _) in CONSUMERS[consumer].items():
        if ad is None or k not in mm:
            continue
        if k in holds:
            held[k] = holds[k]
            continue
        new = ADAPTERS[ad](mm, at).get(k)
        if new is not None and abs(float(new) - float(mm[k])) > 1e-9:
            info[k] = [ad, round(float(mm[k]), 2), round(float(new), 2)]
            out[k] = float(new)
    return out, dict(({"definitions": info} if info else {}), **({"held": held} if held else {}))


def check_reads(consumer: str, reads) -> list:
    """The measurements in `reads` with no declared definition for `consumer` (the draft refuses them)."""
    have = CONSUMERS.get(consumer, {})
    return sorted(k for k in reads if k not in have)


def gate_row(consumer: str | None, mm: dict, holds: dict | None = None) -> dict:
    """Pattern gate row "measure_definitions": every consumed measurement has a matching definition."""
    row = {"id": "measure_definitions", "stage": 1, "measure": "measure_defs.gate_row", "consumer": consumer}
    if consumer is None:
        return dict(row, status="INFO", why="not drafted from the tape")
    if consumer not in CONSUMERS:
        return dict(row, status="FAIL", why=f"no definitions declared for {consumer}")
    held = {k: v for k, v in (holds or {}).items() if k in CONSUMERS[consumer] and CONSUMERS[consumer][k][1]}
    amb = sorted(k for k, (st, _, _) in CONSUMERS[consumer].items() if st == AMB and k in mm)
    if held:  # (INFO, not FAIL: a hold is declared; it never blocks a garment in flight, and never reads as a pass)
        return dict(row, status="INFO", held=held, ambiguous=amb,
                    why="HELD: declared definition mismatches kept on the tape's legacy value until refitted: "
                        + ", ".join(held))
    return dict(row, status="PASS", ambiguous=amb)
