# STATE: pattern gate (validate the pattern before simulating)

STATE / NEXT (2026-10-19): gate built and enforced on branch worktree-agent-aadbbb5b964e9f24f (not on main yet).
NEXT: coordinator lands it; agents with sims in flight set HIFIPUSHIE_SIM_WITHOUT_PATTERN_GATE="<reason>" until
their garment has a record; save a cloth_reference reading per garment (read(..., save=)) so the placed items measure.

## What it is
- `cloth_check.pattern_gate(model, garment, refs=, waive=, sheet=)`: drafts + places the pattern (cloth.build
  place_only, no sim), measures the garment kind's cloth_checklist.json items, writes
  /mnt/data/hifipushie/pattern_gate/<gate_key>.json (pattern hash + body hash, checklist_version, rows, warnings,
  waived, overrides, sheet).
- Row statuses: PASS / FAIL (numbers) | UNMEASURED (blocks) | SIM (judged after the sim; not blocking) | INFO.
- Verdict: PASS, PASS_WAIVED (every blocking row waived by name with a reason), else FAIL.
- `cloth_job.require_pattern_gate(job_dir)`: reads job_dir/pattern_gate.json (keys written by cloth._blender_job;
  not part of input_hash: caches keep their keys) and refuses (SimNotSubmitted) without a PASS record.
- Enforced at: cloth._blender_job (local Blender), cloth_job.run_zozo (local and rented, before the preflight),
  cloth_job.run_external (paid remote, "file"). Free remotes (have.sh, nobox.sh) and garments with no pattern exempt.
- Override: HIFIPUSHIE_SIM_WITHOUT_PATTERN_GATE="<reason>" -> record "overrides", job_dir/pattern_gate_override.log,
  <gate dir>/overrides.jsonl.
- Sources: `cloth_check.option_sources(g)` WARNs on pattern ops / block_options / construct collar_options,
  lapel_options, hug that change defaults without "source". "source" keys are inert (pattern_draft.apply,
  cloth_made.options, the sim key drop them).
- LOOK: `sheet=True` -> cloth_check.pattern_sheet: clay placed rest on the body, front / three / side / back, ~1 m box,
  concept first (garment design.concept or concept=). Needs bin/capped (takes resources.heavy gpu). Not run yet.

## Measured today
- seams (cloth_check.seams: ease bands + notches) on the full draft (held-out collar included).
- placed rest (fine mesh X0) through cloth_reference measures: hem_cf_z, hem_cb_z, sleeve_end_t, trouser_hem_z,
  shoulder/chest/waist/seat/knee widths, hem_sweep, leg_opening, sleeve_opening, waistband_z, lapel_width,
  top_button_z, detail choices, has_belt, over, fabric, colour: only with a reference reading (or a target_mm rule).
- neckline_standoff_mm (validated known answer) as INFO: 7.3 mm median on ga_suit shirt.
## UNMEASURED today
- every "missing:" item: gorge_height, wear_age, and collar-redraft's new collar / neckline items (picked up live).
- every placed item without a saved reading: no garment has one yet (ga_suit shirt: 13 rows).
- SIM (not blocking): silhouette, front_hang, drape, folds, closures state / counts, placket, tucked, crease, tells.

## Results
- ga_suit shirt (201 s, scratch gate dir): FAIL: seams 2 of 15 off band, 13 UNMEASURED (no reading). jacket needs
  the shirt dressed (layered garments gate on their under garment).

## Commands
- tests: /mnt/data/hifipushie/bin/slot uv run pytest -q tests/test_pattern_gate.py tests/test_codified.py
- gate: CAP=10G /mnt/data/hifipushie/bin/capped uv run python -c "from hifipushie import cloth_check as cc;
  cc.pattern_gate('<model>', '<garment>', refs='<reading.json>', sheet=True)"

## History
docs/notes/pattern_gate.md (grep).
