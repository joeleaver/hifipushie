# STATE: dress-garrett -- rewritten 2026-10-19 after "muslin 1" (branch garrett-muslin1). NO SIMS (course change).

## Current best (frozen for export) -- unchanged
- **/mnt/data/hifipushie/dress_garrett/frozen_ae/** (old pattern; Joe rejected its v8m drape: "completely unacceptable").
  Nothing approved. Target: workspace/garrett_v20/concept_v8_front_apose.png; readings refread/garrett_concept_refs_v2.json.

## Coordinator rules in force
- Joe 2026-10-19: "we need to go back to the pattern". NO sim, NO dress-form iteration until the flat pattern is right.
- Gate on what's proven (codified C29): the dress form is unvalidated, so its readings are INFO; the gate blocks on flat checks.
- One view per reviewer turn; reference beside every result; walk the seam after every change.

## The corrected pattern (one place)
- $G/muslin1/patch.py `spec()`: every cf5.py patch with its source (neckline widen 4 / back 15, trued necklines,
  collar stand 29 / fall 43 / point 15, match (collar = neckline), collar B, shirt collarStandWidth 0.090 /
  collarWidth 1.30, shirt worn open 30, length_bonus 0.15, lapel 72 / gorge_drop 0.115, sleeve truing, seam_ease).
- Run: $G/muslin1/run.sh <slot|heavy> <script> <log>. probe.py (flat stage), gate.py (gate), flat.py (sheets + Jaeger).

## Gate (flat first), records pattern_gate/d554d8b36d6a2b4967c9.json (shirt), 09497a2cc1e406f5def1.json (jacket)
- Shirt FAIL only on `pockets` UNMEASURED (no concept reading for shirt pockets). Seams, truing, flat_pattern PASS.
- Jacket FAIL on `pockets` (concept flap, op_pocket has no flap) + `vent` UNMEASURED (no reading). PASS: seams, truing,
  flat_pattern (ease by girth), collar_stand 29 (25-30), collar_fall 14 (6-15), notch flat 29.5 mm / 61.4 deg, and
  shoulder / waist / sleeve from the validated frozen_ae drape (drape_readings, same block widths).
- Form items INFO: hem sweep 423 (form FAIL), form_strain p99 36.9 % (form FAIL), worn collar items.

## Flat review vs FreeSewing Jaeger + tailor's rules ($G/muslin1/compare.md; sheets sheet_jacket/shirt/jaeger.png)
- Jacket FAILs the GATE DOES NOT MEASURE YET (checklist incomplete, gates.md): back neck width 103 (Jaeger 93, rule
  91-96); back neck rise 36.9 (Jaeger 22.7; the op's back 0.015 vs M&S ~5); waist +25.8 % = boxy (Jaeger +20.1 %),
  no front dart, suppression 56 vs 66; front edge overlap 12 (rule ~20-25); no flap pockets. MINOR: collar sewn 1:1
  (M&S eases ~10 mm), front shoulder slope = back (Jaeger 1.5 deg steeper).
- Shirt: all pass; band 36.6 (brief 38-40: -1.4); cuff -2.3 % declared (placket strips not cut as pieces).
- Rules marked M are from memory (no book checked); D = a source in cloth.md; B = the brief.

## NEXT (after the coordinator / Joe read the sheets)
1. Add the flat tailor checks as gate rows (back neck width / rise vs tape, waist suppression, front overlap), then
   re-draft: neckline back 0.015 -> ~0.005, neck width toward Jaeger's 93, a front (fish-eye) dart, overlap ~22.
2. Flap pockets (op_pocket flap), a vent reading or a sourced default, shirt pocket reading.
3. Only then a muslin sim (cloth_job, rented ZOZO; brief: sewn interfaced collar with fold rest, lapel roll rest,
   jacket open, shirt top button undone). The form KAT (two-piece sleeve lens) stays open before FORM_VALIDATED.

## Dead ends (don't retry)
- LOOSE_ROUND pressure; length-keeping truing; rigid folds about a non-edge row; changing the block to make the FORM read
  the concept; pinned "neck cloth" rows on the collar (an n8).

## History (grep only)
docs/notes/cloth.md "dress-garrett 2026-10-19 muslin 1", "form sleeves", "block proportions", "order + seam lengths".
