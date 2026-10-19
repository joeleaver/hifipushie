# MCP audit: do the tools carry the clothing and review rules? (2026-10-19)

Why: Joe (art director): "we don't want to make it work just for this session, but anyone who uses the mcp." The rules
won today lived in briefs and notes; a model using the MCP server without them could simulate an unchecked pattern,
hand-finish a drape and judge its own contact sheet. The rule now: the tools' DEFAULTS and RESPONSES carry the rules.
Codified rows M1-M8 (codified.md); tests tests/test_mcp_rules.py; STATE docs/state/mcp_rules.md.

## The table (main at c775e8ad + this change)

| Capability | Where it is | MCP tool before | MCP tool now | Guide topic | Default matches the rule? |
|---|---|---|---|---|---|
| Pattern gate (cloth_check.pattern_gate: checklist items on the placed pattern, record per pattern + body) | main; flat-first rows (junctions truing, collar_draft, notch_flat, flat_pattern, form items INFO until form_validated) on branch garrett-muslin1 | none (Python only) | `pattern_check` (cloth) | cloth_tools "pattern_check"; cloth guide order | YES: FAIL / UNMEASURED first, "DON'T simulate" + the rows; branch rows appear when it lands (same function) |
| Sim refused without a PASS (cloth_job.require_pattern_gate) | main | `dress` started the job; the refusal surfaced later as a FAILED background job, naming a Python call | `dress` refuses up front (cloth_check.gate_status), names pattern_check; `force` no longer reads as a bypass | cloth_tools "dress" | YES |
| Alterations `true` (truing) and `match` (walk the seam) (pattern.apply) | branches pattern-form-fit, garrett-muslin1 | none (spec key "alter" by hand via dress spec) | `alter_pattern` (cloth): any pattern.apply op; true / match once the branch lands (an unknown op errors before any save) | cloth_tools "alter_pattern" | YES: drafted before save, seams walked, next = match / pattern_check |
| Truing check (cloth_check.junctions) | branches | none | read by alter_pattern (hasattr) and by pattern_check's rows once landed | cloth_tools | WIRED, inert on main |
| Virtual dress form / fit (pattern_form.assemble / on_form, FIT relax, worn_open) | branches pattern-form-fit (FIT relax, form_validated), garrett-muslin1 | none | `fit_garment` (cloth): pattern_form.on_form when importable, else the placed rest (said in the text) | cloth_tools "fit_garment" | YES: refuses before a PASS; strain p99 + pierce + next step |
| Diagnostic renders (diag_render: panels, seams, turned, backfaces, strain, layers) | main | none (look_cloth clay + strain only) | default rows in `look_cloth`, `pattern_check`, `fit_garment` (DIAG_DEFAULT) | cloth_tools; gates.md LOOK | YES: on unless diag=False |
| Flat pattern sheet (pattern_sheet.render) | main (grid / seam allowance / labels on garrett-muslin1) | `look_pattern` (via cloth_workflow) | also returned by `pattern_check` and `alter_pattern` | cloth_tools | YES |
| Pre-sim placed sheet (cloth_check.pattern_sheet, clay) | main | none | `fit_garment` clay strip | cloth_tools | YES |
| bin/judge (validated shots, measures, self-checks, blind A/B with controls) | main | none | `judge_asset` (export): shots + report (+ against); A/B stays `bin/judge ab` (text points to it) | tools_guide "judge_asset" | YES: refuses on a failed self-check |
| bin/review, reviewgate (one view per turn, no captions, no sheets, --dry) | main | none | `review_view` (core): one region / one pair by signature, input gate, bin/review or dry pair + prompt | tools_guide "review_view" | YES |
| bin/review-ab | main | none | not exposed (judge ab is the validated A/B; review_view covers single views) | - | gap, low |
| garment_game (pattern-space game mesh) | main (opt-in) | none | `game_garment` (export): every garment with a drape (+ the covers of an asked one), LODs by edge, rest + optional pose dumps, bake to GLBs | tools_guide "game_garment" | YES: refuses the bake on any LOD pierce / crack, names the fix; clean -> judge_asset + review_view (M13) |
| Tailoring principles (docs/notes/tailoring_principles.md) | branch (tailoring-principles agent) | none | guide topic "tailoring" (pointer until it lands, then the file) | guide("tailoring") | WIRED |
| Traps (docs/notes/traps.md) | main | none | guide topic "traps" | guide("traps") | YES |
| Gates (docs/notes/gates.md) | main | none | guide topic "gates" | guide("gates") | YES |
| Server instructions | main | said "made pieces built on the drape; small faults finished by hand" (WRONG since today) | the order, the gate, one view per review, "do what next: says" | INSTRUCTIONS | YES |

## Next-step lines (next_steps.py), from the result

- pattern_check FAIL: "next: the pattern gate is FAIL: DON'T simulate (dress refuses). fix these rows on the flat
  pattern first (alter_pattern / design_garment): seams ... unmeasured (no reading = no pass): rise, ... then
  pattern_check(...) again". PASS: "next: fit_garment(...): assemble it on the form (no sim) and judge clay + diag
  beside the reference, one view at a time (review_view)".
- fit_garment: strain p99 > 6 % -> "fix on the pattern ... where the strain map is red"; pierce > 0 -> "draft this
  garment over the under one"; clean -> "judge the clay AND the diag views beside the reference, ONE view per
  review_view call"; always "a sim is optional and only a wrinkle source; never close or hand-finish after it".
- dress refused: "<g>: NOT simulated: no pattern-gate record ... next: pattern_check(...), fix its FAIL / UNMEASURED
  rows, fit_garment, judge".
- look on a character / look_cloth: no reference -> "set one ... a look with nothing to compare to proves nothing";
  else "judge this ... BESIDE its reference before forwarding it, then an independent review_view per region".
- game_garment: any LOD with an under layer crossing its cover (pierce_faces) or a crack -> "NOT baked, no GLB
  written", per LOD + pair + count, fix = finer edge at that LOD / gap_rings=2 / draft it further under (never by
  hand); clean, not baked -> "bake=True"; baked -> judge_asset each GLB then one crop per review_view; no poses ->
  "rest pose only".
- review_view: FAIL -> fix every independent MAJOR grouped by cause; no verdict -> "this is not 0 MAJORs".

## Wired when the branches landed (2026-10-19 integration)

- One dress-form switch: the gate, `fit_garment` and next_steps read `cloth_check.form_validated()` (the manual
  override FORM_VALIDATED or `pattern_form.form_validated()`: flag + a record whose rows all pass); nothing else
  reads FORM_VALIDATED or pattern_form's flag (tests/test_mcp_rules.py::test_one_form_switch_for_gate_and_tools).
- `fit_garment` always assembles with `pattern_form.on_form`; its under garment is on_form's "form_under" ("A"
  pressed vertices, "mesh"), named by the garment key "over" (on_form has no "name" field).
- `alter_pattern`'s truing line reads `cloth_check.junctions` as the gate's truing row does (corners = garment key
  truing_corners; fields at / seam / turn_deg / ok).
- `pattern_check`'s diag views show the pattern as the gate read it (on_form's "A", not the placed start).
- Guide topic "tailoring" = docs/notes/tailoring_principles.md (landed).

## History

- 2026-10-19 mcp-rules: audit, five tools (pattern_check, fit_garment, alter_pattern, review_view, judge_asset), diag
  default on look_cloth, dress refusal up front, instructions + cloth guide order rewritten, traps / gates / tailoring
  topics, next_steps.py, tests/test_mcp_rules.py (8 light + 1 render under capped: skirt on a MakeHuman base, renders
  checked by eye: panels / seams / strain read, placed rest only on main).
- 2026-10-19 game_garment (export): garment_game behind a tool (from_result for cached / frozen drapes, covers_of from
  the "over" chain, build_lods outer garments first, write, bake under resources.heavy; covered_cull takes a rest body
  when no poses). Gate: pierce_faces per LOD and under / cover pair + missing boundary edges; any -> nothing written,
  fix named. Codified M13; tests: synthetic shirt / jacket sheets (crossing at the cover's free edge: 14 / 6 faces at
  30 / 60 mm; clean: 0, low meshes written). Real check on ag_garrett2: refuses (0 / 2 / 11 / 17 faces, 3 cracks).
