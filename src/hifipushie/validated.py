"""Known-answer self-tests for the measures that drive gates (docs/notes/gates.md "MEASURE FIRST, AND VALIDATE THE
MEASURE", 2026-10-19): before a measure drives a change it must reproduce a known-good case (the reference against
itself) and find a planted fault. Wasted rounds came from unvalidated measures: uvs read upside down, AgX vs PBR
Neutral compared, a half-sided preview, a photo mask dropping highlights.

A measure carries its self-test with the decorator:

    def _selftest_foo():            # raises AssertionError when the measure is wrong
        assert foo(same, same) == 0 and foo(ref, planted_fault) > 0.4

    @validated.known_answer(_selftest_foo)
    def foo(a, b): ...

GATE_MEASURES lists every measure a gate (an export WARNING / refusal, a checklist row) reads; tests/test_codified.py
fails when one of them has no self-test or its self-test fails. A new gate measure goes on the list WITH its test.
"""
from __future__ import annotations

import importlib
from typing import Callable

SELFTESTS: dict[str, Callable[[], None]] = {}

# module.function of every measure a gate reads (see the module docstring)
GATE_MEASURES = (
    "hifipushie.hair_checks.compare",          # hair.check_tiers: missing / value / sat / stamps / straight WARNINGs
    "hifipushie.hair_checks.colour",
    "hifipushie.hair_checks.stamps",
    "hifipushie.hair_checks.straight_share",
    "hifipushie.asset.hair_budget",            # the export's hair-card budget refusal
    "hifipushie.asset.budget_check",           # the export's per-part budget lines
    "hifipushie.asset.face_light_check",       # the export's shipped-vs-approved lid / forehead WARNINGs
    "hifipushie.cloth_check.seams",            # the pattern checklist's seam ease / notch rows
    "hifipushie.pattern_form.placement_error",  # the dress form's neck point on the body's HPS (pattern stage)
    "hifipushie.cloth_check.neckline_standoff_mm",  # the pattern gate's neckline row (cloth_check.pattern_gate)
    "hifipushie.garment_game.pierce_faces",    # game garment: under-layer faces crossing the cover, per LOD + pose
    "hifipushie.pattern_form.gorge_lie",       # the form gate's gorge_lie row (collar end on the lapel, fit round 17)
)


def known_answer(test: Callable[[], None]):
    """Attach a known-answer self-test to a measure (registered as module.qualname)."""
    def deco(fn):
        SELFTESTS[f"{fn.__module__}.{fn.__qualname__}"] = test
        fn.selftest = test
        return fn
    return deco


def _resolve(name: str):
    mod, _, attr = name.rpartition(".")
    return getattr(importlib.import_module(mod), attr)


def missing() -> list[str]:
    """Gate measures without a self-test."""
    out = []
    for n in GATE_MEASURES:
        fn = _resolve(n)
        if getattr(fn, "selftest", None) is None:
            out.append(n)
    return out


def run(names=GATE_MEASURES) -> dict[str, str]:
    """{measure: "ok" | the failure} for each named measure's self-test."""
    res = {}
    for n in names:
        t = getattr(_resolve(n), "selftest", None)
        if t is None:
            res[n] = "NO SELF-TEST"
            continue
        try:
            t()
            res[n] = "ok"
        except Exception as e:  # noqa: BLE001 (a report, not control flow)
            res[n] = f"FAIL {type(e).__name__}: {e}"
    return res
