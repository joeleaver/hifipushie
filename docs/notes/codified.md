# Codified lessons: the ledger (2026-10-19)

Why: Joe, 2026-10-19: "any durable learning that's not codified should be, now please." Tess took a week, much of it
rediscovering rules. Every durable lesson gets ONE row here: where it lives now and how hard it is held.

Status:
- ENFORCED: code refuses / fails a test (function cited; grepped on main; re-graded after the 2026-10-19 landing).
- ENFORCED-BRANCH: the guard exists and is tested, but only on an unmerged worker branch (named). Not yet on main.
- DOC: a written rule or a code default / warning only. An agent can still get it wrong.
- CHECK-PLANNED: should be a check; the one-line spec is the job (another agent is building these; the coordinator
  reconciles this column when they land).
- TASTE: Joe's call per character; stays a judgement (the recipe says where to ask).

Totals (2026-10-19, after landing the codify checks and the export gates on main): 105 rows: CHECK-PLANNED 3, DOC 73, ENFORCED 25, TASTE 4. A row counts once, by its leading status.
New lesson = a new row the same day (check first, else a default, else a recipe / traps line). Recipe:
docs/notes/character_recipe.md. Traps (symptom -> cause): docs/notes/traps.md.
bin/ = the repo's bin/ (review, review-ab, approve, capped, slot, hooks; /mnt/data/hifipushie/bin links to it after bin/link-tools; row P14).

## Process and gates

| # | Lesson | Codified at | Status |
|---|---|---|---|
| P1 | Every stage: DESCRIBE (checklist) -> MEASURE -> independent blind LOOK -> APPROVE | gates.md "The rule"; CLAUDE.md hard rules | DOC |
| P2 | Stages consume only approved pieces, by exact name | bin/approve (approved.json); asset.approved_head (head only) | ENFORCED for the head: asset.approved_head + the export's head / folds / stack equality refusals (tests/test_codified.py::test_export_gates_on_the_approved_head_and_fold_form, tests/test_game_ready.py::test_export_head_is_the_approved_head). CHECK-PLANNED for hair / garments / skin: export refuses any piece without an approval key |
| P3 | Clean != right; "runs end to end" is plumbing | gates.md; CLAUDE.md | DOC |
| P4 | Blind reviewer sees only ref / result pairs, no captions | bin/review, bin/review-ab (no context claims; random X/Y) | ENFORCED: bin/review, bin/review-ab; reviewgate.refuse_inputs refuses captions / context claims (exit 5; tests/test_codified.py::test_review_inputs_refuse_captions_sheets_and_claims) |
| P5 | Keep / revert by side-by-side A/B in one sitting; one-result reviews varied 2 -> 5 MAJORs | bin/review-ab docstring; gates.md "REVIEWS" | DOC. CHECK-PLANNED: audit flags a keep/revert decision that cites `review` counts instead of a review-ab key |
| P6 | A review that didn't run is not 0 MAJORs | bin/review exits 4 + writes "REVIEW FAILED" (no VERDICT line); bin/review-ab exits 4 | ENFORCED: bin/review, bin/review-ab exit 4 (now in the repo's bin/); reviewgate.majors raises ReviewNotRun (tests/test_codified.py::test_review_that_did_not_run_is_a_failure) |
| P7 | Reviewer label check: verify X/Y faults against key.json before trusting a verdict | gates.md "REVIEWS"; traps.md | CHECK-PLANNED: review-ab re-asks the reviewer to restate which tile is X for each item; mismatch -> exit 4 |
| P8 | Faces reviewed on single-feature tiles (>= ~400 px per feature), not whole-head frames | gates.md "FACES ARE REVIEWED ON FEATURE TILES"; spikes/tour/tour.py; blockin.focus | DOC. CHECK-PLANNED: review refuses a face pair whose detected face spans > 50 % of a > 1200 px image or a feature < 300 px |
| P9 | Crops not sheets for agents; sheets for Joe only; ref | best result | others | gates.md "CROPS, NOT SHEETS"; recipe "Final sheet" | DOC |
| P10 | STOP-LOSS: 2 rounds without a visible change -> change METHOD or park | gates.md "Process rules" | DOC. CHECK-PLANNED: bin/audit flags a fault id worked > 2 rounds with no before/after tile change |
| P11 | Validate a measure on a known case (ref vs itself, planted fault) before it drives a change | gates.md "MEASURE FIRST" | ENFORCED for gate measures: validated.known_answer + validated.GATE_MEASURES (tests/test_codified.py::test_gate_measures_are_validated: hair_checks x4, asset.hair_budget, budget_check, face_light_check, cloth_check.seams). Not yet self-tested: likeness rows, face_ruler / eye_ruler, skin_read crop stats, spikes' tiles.py |
| P12 | Prove a lever moves its row on the cheap path before a batch (dead levers cost rounds) | gates.md "Prove a lever"; tests/test_skin.py::test_lid_shade_survives_a_stack (one dead lever) | DOC (+1 ENFORCED instance). CHECK-PLANNED: batch scripts refuse a variant whose job.json equals its parent's (PATCH asserted, cloth.md rvpack2 lesson) |
| P13 | Scope reviews to the stage (--stage / --not); conversion stages judged vs their SOURCE | bin/review --stage; gates.md "Source-asset scope" | DOC |
| P14 | bin/ guards live outside the repo, unversioned | none | ENFORCED (versioned): review, review-ab, approve, capped, slot in the repo's bin/ (reviewgate tests); /mnt/data/hifipushie/bin -> repo symlinks pending bin/link-tools from the main checkout |
| P15 | Game assets judged at game distance (1 m / 3 m, 1080p, native px); close-up-only MAJORs don't block | gates.md "Game distance" | DOC |
| P16 | Likeness under the reference's fitted light, readability under the game rig | gates.md "LIGHT" | DOC |
| P17 | Test before asking Joe: copies, before/after sheet, numbers | memory test-before-asking; this ledger | DOC (coordinator) |
| P18 | Briefs carry rule + reason + action, not fences; agents act on Joe's rules | memory briefs-carry-rules-not-fences | DOC (coordinator) |
| P19 | Agents keep iterating past gate sheets; stop only for Joe's decisions | memory agents-keep-iterating; gates.md "Nothing goes to the coordinator until..." | DOC |
| P20 | Judge renders yourself before forwarding; agents over-rate; look before reading text | CLAUDE.md; gates.md "coordinator looks at the pairs BEFORE"; traps.md | DOC |
| P21 | Back to known good after 2 failed fixes of a shared change; new behaviour opt-in | memory back-to-known-good; recipe "Rules for every stage" | DOC |
| P22 | Coordinator judging: look-first verdict before agent numbers | memory coordinator-judging-failures | DOC (coordinator) |
| P23 | Grade every finished session: adherence / process / tooling | bin/audit, bin/audit-summary; docs/notes/audit.md; tests/test_audit.py | DOC (tool exists; running it is coordinator behaviour) |
| P24 | Describe from the reference; match it at its own camera, rules derived from the reference | gates.md DESCRIBE; memory match-reference-directly; likeness_guide | DOC |
| P25 | Handed refs: measure what they support, mark INFERRED; generated refs: shot brief from the checklist | memory reference-quality; blockin_guide "Stage 0" | DOC |
| P26 | Artists' order (silhouette -> big forms -> detail), fast looks, Blender-native first | memory artist-workflow-stages, north-star, lean-on-blender; guide.md | DOC |

## Repo, privacy, machine

| # | Lesson | Codified at | Status |
|---|---|---|---|
| R1 | Stage by path, never `git add -A` | CLAUDE.md hard rules | ENFORCED: pre-commit hook (bin/hooks/guard.py via bin/install-hooks) refuses workspace/ paths and files > 5 MB (tests/test_codified.py::test_git_guard_blocks_private_workspace_big_and_branches). scratchpad/ / out/ / png > 1 MB not covered: DOC |
| R2 | Agents never push; coordinator squashes + scrubs to main | CLAUDE.md | ENFORCED: pre-push hook refuses any ref but main and private-model prefixes in added lines / paths / messages (tests/test_codified.py::test_git_guard_blocks_private_workspace_big_and_branches) |
| R3 | Private heads: nothing in the repo (names, codes, relations, paths) | CLAUDE.md; docs/state/README.md | ENFORCED: tests/test_codified.py::test_no_private_prefix_in_tracked_files + the pre-push hook (prefixes from the environment / untracked file) |
| R4 | CLAUDE.md < 8 KB; STATE pages <= 60 lines; notes grep-only | CLAUDE.md; docs/state/README.md | ENFORCED: tests/test_codified.py::test_claude_md_under_8_kb, test_state_pages_at_most_60_lines |
| R5 | Merges can delete another thread's code | traps.md | CHECK-PLANNED: merge helper lists top-level defs / module constants present in either parent and missing after the merge; refuses until each is acknowledged |
| R6 | Heavy jobs declare real GB (resources.heavy) and run under bin/capped; light sweeps via bin/slot | resources.heavy (admits by declared peak, records measured peaks: resources._record_peak); bin/capped (systemd scope, kills at cap); CLAUDE.md | ENFORCED: resources.heavy raises without gb= / kind= (tests/test_codified.py::test_undeclared_heavy_job_is_refused), bin/capped kills at cap. CHECK-PLANNED: resources.heavy warns when the measured peak > 1.2x the declared |
| R7 | One GPU render at a time (desktop iGPU freezes); check renders sized to the detail | bin/capped gpulock; memory render-gpu-and-sizes | ENFORCED (gpulock via capped) / DOC (sizes) |
| R8 | Durable / big files on /mnt/data/hifipushie, never /tmp; downloads pinned in assets.json | CLAUDE.md; assets.py | DOC |
| R9 | Deletes: list -> summarise by folder -> look -> rm; quote globs; never sweep venvs / assets | memory cleanup-deletion-care | DOC (coordinator) |
| R10 | Document as you go: STATE / NEXT after every step, commit | CLAUDE.md | DOC |
| R11 | Agent context budget: ~100 tool calls / 250k, then hand over | CLAUDE.md; memory agent-context-budget | DOC. CHECK-PLANNED: bin/audit flags sessions past 250k context |
| R12 | Every capability reachable over MCP (tools + guide + a server test) | memory expose-features-as-mcp-tools; server._tool_with_errors | DOC |
| R13 | Bump store.BUILD_VERSION when meshing changes; incremental == cold | store.BUILD_VERSION; CLAUDE.md | ENFORCED: tests/test_codified.py::test_incremental_build_equals_cold_build, test_build_version_bumped_when_meshing_output_changes (tests/data/build_golden.json per BUILD_VERSION) |
| R14 | Tests compare statistics with tolerances, never per-pixel equality | traps.md | CHECK-PLANNED: a lint test flags `np.array_equal` / `==` on rendered images in tests/ |
| R15 | `setsid ... & echo $!` records the parent, not the job | game_ready.md "Process: nohup setsid"; traps.md | DOC |

## Head and face

| # | Lesson | Codified at | Status |
|---|---|---|---|
| H1 | Artist block-in is the default for heads from pictures | blockin_guide.md; server guide topic block_in | DOC |
| H2 | One joint solve over all views + prior, not sequential local slider tweaks | blockin.block_in_solve; blockin_solve.md | DOC (the tool is the default path) |
| H3 | Solve gives the base; the agent finishes with hand steps (block_in_step, mm:, sculpt:) | blockin_guide "The loop" 3-6 | DOC |
| H4 | Never start from a previous fit; start from the class mean on a GNM-native head | blockin_guide loop 1; block_in_start | DOC |
| H5 | Judge likeness on the judging sheet (refs projected as skin + blend) | spikes/reruns/jsheet.py; gates.md "Head shape" | DOC |
| H6 | Perceptual identity metrics (ID embedding between our renders), not mm / variance | memory perceptual-identity-metrics; faceid (tests/test_faceid.py) | DOC |
| H7 | Use what GNM ships (eyeball, teeth, mouth, tongue) | blockin_guide loop 1 ("GNM's own base, eyeball, mouth") | DOC |
| H8 | One coherent face model; new controls are dimensions of it | memory coherent-face-model; gnm_controls.py | DOC |
| H9 | Fits protect model integrity: sliders are solver outputs, side-effect report, whole-figure views | memory fits-must-protect-model-integrity; block_in_solve reply (MOVED WITH NO READ lists) | DOC |
| H10 | Parametric source before hand edits (MakeHuman / GNM params) | memory prefer-parametric-over-hand-edits; guide.md 4d | DOC |
| H11 | Downstream threads never reshape an approved head (Garrett drift via lid_fold / eye bags) | asset.approved_head + head-equality check in asset.export | ENFORCED: asset.approved_head + head-equality refusal in the export (see P2). CHECK-PLANNED: skin variants' base.head must equal the approved head's except skin keys (the skin thread's variant maker) |
| H12 | Folds <= 1 mm relief are skin; more is head form | asset.FOLD_FORM_MAX_MM = 1.0 (clamp + WARNING; export raises unless the model carries the clamped value) | ENFORCED: asset.fold_form_gate / FOLD_FORM_MAX_MM; the export raises unless the model carries the clamped value (tests/test_codified.py::test_export_gates_on_the_approved_head_and_fold_form, tests/test_game_ready.py::test_skin_folds_over_a_millimetre_are_head_form) |
| H13 | Realistic body build by measurement (ANSUR II percentiles, no outlier) before drafting | body_check.percentiles (src/hifipushie/body_check.py, tests/test_body_check.py) | DOC (tool on main; not a gate). CHECK-PLANNED: cloth draft warns when the body has a girth < p1 or > p99 |
| H14 | Tess's build: p20-35 ANSUR II women 18-30 | memory tess-body-build | TASTE (per character; Joe confirms on a sheet) |
| H15 | Texture carries identity: folds / textures / eye-mouth detail are the lever once shape is close | memory texture-carries-identity; recipe "Skin" | DOC |

## Skin

| # | Lesson | Codified at | Status |
|---|---|---|---|
| S1 | Skin stage owns textures only; shape forms go into the head before projection | skin_guide.md "From pictures" ("Shape first"); H11 / H12 | DOC (+H12 ENFORCED) |
| S2 | Lever order inside a stack: an opaque layer after a lever kills it | tests/test_skin.py::test_lid_shade_survives_a_stack; skin.md r7 order.py | ENFORCED (lid_shade only) / DOC (others) |
| S3 | Colour compared under PBR Neutral (asset.GAME_LIGHT / blender_game default view), never AgX | blender_game.py job view default "Khronos PBR Neutral" | ENFORCED: asset.same_view / game_light_view (scene.look and asset.preview refuse the game rig under another view), face_light_check requires views= and raises MixedViewTransform (tests/test_codified.py::test_mixed_view_transforms_are_refused). Renders don't record their view in the PNG: a script comparing files must pass the views |
| S4 | One lever per step (lips: melanin at strength >= 1; brows: thickness / opacity / soft one at a time) | docs/state/skin.md "Dead ends / rules" | DOC |
| S5 | Tone lightness is not observable from photos without an exposure anchor | skin.md "## skinread"; skin_read | DOC |
| S6 | Judge skin at the face resolution the export meshes, then in the exported GLB | docs/state/skin.md decisions; skin_guide "Judge in EEVEE" | DOC |
| S7 | Lashes thickness >= .12 mm (0.09 vanishes at 512 px eye crops) | skin.md:1861 | DOC. CHECK-PLANNED: skin validate warns under .12 |
| S8 | On a stacked head skin.tone is the body; undertone edits move the neck only | skin.md:1766 | DOC |
| S9 | Age texture beyond the approved head (wrinkles) | docs/state/garrett_export.md | TASTE (Joe / coordinator) |
| S10 | Iris colour where photo and approved head disagree | docs/state/skin.md | TASTE |

## Hair

| # | Lesson | Codified at | Status |
|---|---|---|---|
| A1 | Describe the hairstyle first (15-rule checklist) and seat it on the APPROVED head | hair_guide.md / hair_checklist.md; hair.py reseat (seat_locks); gates.md "Hair" | DOC |
| A2 | Judge hair in EEVEE only (Cycles columns add nothing) | memory hair-judge-in-eevee; skin_guide "never in Cycles" | DOC |
| A3 | Cards are judged against the groom (source); the groom against the photo | gates.md "Source-asset scope" | DOC |
| A4 | Short hair: baked cap + shells + hairline / sideburn row cards, not cut-per-clump cards | hair_short.md; hair.SHORT_TIERS; hair_cards "hairline_row"; shells: hair.export.style "shells" | DOC (shells code is on branch hair-heads2 only, not main) |
| A5 | Long hair: crown arch + fill under it | hair_clumps.ARCH = 4, ARCH_FILL = 1, hair.ARCH_TIERS | DOC (defaults) |
| A6 | LOD0 hair tier from the role when hair.export.tier is unset (the "helmet" trap) | asset.hair_tier_default + ROLE_HAIR_TIER (WARNING when neither) | DOC (default; warns). |
| A7 | Back faces exported as own triangles + single-sided material (engines flip normals) | hair.BACK_FACES = 1; tests/test_hair_back_faces.py | ENFORCED |
| A8 | Hair budget unit | hair.py cards fit (`bf_`: DRAWN incl. back faces fit to the budget); docs/state/tess_hair.md, garrett_hair.md | ENFORCED: decided 2026-10-19, the role default counts CARD faces, drawn <= range max: hair.BUDGET_UNIT "card_faces" (cards fit to card faces, and the tier's drawn max via hair.card_allowance), asset.hair_budget / budget_check FAIL -> export raises (tests/test_codified.py::test_hair_budget_refuses_drawn_over_max_and_counts_card_faces). STATE pages to follow |
| A9 | Outline rule: the part shows only where the groom's outline dips | docs/state/tess_hair.md decisions | DOC |
| A10 | Hair constants are module constants, not spec keys: exports must set them through one script | docs/state/garrett_export.md ("export only through sh4t.py"); HP_FS_SET env | DOC. CHECK-PLANNED: the export writes every non-default hair module constant into its report; the A/B'd build's constants must match |
| A11 | `hair_clumps.FILL` is the BAKE's packing share (0.82), not the arch fill (ARCH_FILL) | hair_clumps.py comment at ARCH_FILL | DOC. Found today: Tess RC rc2n's HP_FS_SET and hair-cards r45a's hk.FILL=1 set FILL = 1.0 (packing share), not the arch fill. CHECK-PLANNED: HP_FS_SET warns on FILL; rename it BAKE_FILL |
| A12 | Measures must measure the visible fault (laygeo proxy angle lied: 20 deg vs 56 rendered) | hair.md:3197 LESSONS | DOC |

## Clothes

| # | Lesson | Codified at | Status |
|---|---|---|---|
| C1 | Construction before solver: faults are pattern / construction, never solver tuning | cloth_guide / cloth_construction.md; cloth.md "Where each lesson lives" (stage checks) | ENFORCED (stage 2-5 checks per that table; spot-checked) / DOC (rest) |
| C2 | Pattern passes its checklist before any sim | cloth_job.preflight before every paid submit (the START's geometry: raises SimNotSubmitted); the pattern itself: C11 | ENFORCED (start geometry) |
| C11 | Validate the pattern before simulating: a PASS pattern-gate record for this exact pattern + body before any sim (Joe 2026-10-19); UNMEASURED items block; params changing a default carry a "source" (warned) | cloth_check.pattern_gate (record /mnt/data/hifipushie/pattern_gate/<key>.json, LOOK sheet with sheet=True), cloth_job.require_pattern_gate in cloth._blender_job / cloth_job.run_zozo / run_external; override HIFIPUSHIE_SIM_WITHOUT_PATTERN_GATE=<reason> (logged); cloth_check.option_sources; tests/test_pattern_gate.py (test_submit_refused_without_record, test_submit_allowed_with_pass_record, test_submit_refused_when_pattern_changed, test_override_logged, test_unmeasured_items_reported_and_blocking, test_neckline_standoff_known_answer, test_option_sources_warn_only) | ENFORCED |
| C3 | Fine start strain-limited (< 1.6x) or refused before the GPU | cloth.fine_start_check | ENFORCED |
| C4 | Sim for the big read only (~3 draft + 2 final); made pieces built on the drape; faults finished by hand | gates.md "Garments"; cloth.md made pieces; cloth "construct" key, cloth sculpt finish | DOC |
| C5 | Cloth sims rented (ZOZO via oxidegen), $5/day, NICO-TOP fallback; other rented compute needs Joe | memory cloth-rented-default, cloth-solver-zozo | DOC |
| C6 | Freeze approved garments (cloth.freeze); exports consume the frozen pickles | cloth.freeze | DOC |
| C7 | A sculpt file's name is its identity (cache): write anew, never rewrite under the same name | docs/state/dress_tess.md dead ends | DOC. CHECK-PLANNED: cache key includes the sculpt file's content hash |
| C8 | Spike gate passes before sheets | cloth.spikes / cloth.despike | DOC (gate run is a session script). CHECK-PLANNED: cloth.freeze refuses a result with spikes > 0 |
| C9 | Never change code under an in-flight multi-round stage script | cloth.md:4473 | DOC |
| C10 | Clothing is generic, staged like a pattern maker | memory clothing-artist-workflow; cloth guides | DOC |

## Expressions, export, rig

| # | Lesson | Codified at | Status |
|---|---|---|---|
| E1 | Expressions are mixes of expression parameters only; never sculpt per-character deltas | recipe "Expressions"; faceshapes.SHAPE_SCULPT (HP_SHAPE_SCULPT) still accepted | ENFORCED: faceshapes.refuse_sculpt (HP_SHAPE_SCULPT, face_fits.sculpt, sculpted deltas) unless HIFIPUSHIE_ALLOW_SHAPE_SCULPT=1 (WARNING) (tests/test_codified.py::test_sculpted_expression_deltas_are_refused) |
| E2 | Tess smile = mix A2 (mouthSmile .8, cheekSquint 1, eyeSquint .5, mouthDimple .6, mouthPress .2, mouthUpperUp .108); its limits accepted | /mnt/data/hifipushie/happy/NOTES.md (NOT in the repo); recipe | ENFORCED (in the repo): faceshapes.EXPRESSION_PRESETS["smile_tess"] = mix A2, faceshapes.expression() (tests/test_codified.py::test_expression_presets_are_arkit_mixes); its limits accepted |
| E3 | Per-character fit env (HP_SMILE_FIT / HP_JAW_FIT / HP_SHAPE_SCULPT) leaks into the next character's export | faceshapes.env_fits (WARNING) ; spec base.head.face_fits (FIT_KEYS) | DOC. CHECK-PLANNED: export refuses env fits whose source model != the exported head |
| E4 | Export takes the approved head geometry + skin textures only | asset.approved_head | ENFORCED: asset.approved_head (P2) |
| E5 | Engine-agnostic: GLB re-imported into Blender EEVEE like a game; no Godot | gates.md "Engine"; memory engine-agnostic-eevee (supersedes godot-without-focus) | DOC |
| E6 | Budget for a mainstream GPU, not the laptop iGPU | budgets.json (role defaults / ranges); memory target-mainstream-gpu | DOC |
| E7 | RC changes only by blind A/B against the approved stage reference | docs/state/tess_export.md, garrett_export.md | DOC |
| E8 | Exports declare 24 GB to resources.heavy (OOM sharing the slice) | docs/state/garrett_export.md | ENFORCED: asset.export_gb >= resources.EXPORT_HUMAN_GB (24) for base / skin / hair specs (tests/test_codified.py::test_human_export_declares_24_gb) |
| E9 | trimesh GLB texcoords are already v-up: never `1 - uv` | docs/state/tess_export.md GOTCHA; asset.rasterize docstring (row 0 = top) | DOC. CHECK-PLANNED: a helper uv_to_pixel in asset with a test on a known GLB; probes must use it |
| E10 | Proxies render the batch's exact pose (fastproxy smile was a different pose) | game_ready.md r47 "WHY THE PROXY LIED" | DOC. CHECK-PLANNED: proxy and batch read pose weights from one shots file and print its hash; mismatch refuses |
| E11 | Rig: Mixamo-compatible, modelling bones never exported as rig bones | rig.humanoid; memory rig-standards; guide_rigging.md | DOC |
| E12 | Retargets corrected for rest pose (A vs T) | blender_game.py rest-pose correction | DOC (code path) |

## Style and other domains (durable, not on the character path)

| # | Lesson | Codified at | Status |
|---|---|---|---|
| X1 | "Stylized" is ambiguous: ask for a style reference per model; a style is a coherent rule set | memory stylized-means-feature-animation; guide_style.md | TASTE |
| X2 | Weathering from a story, restrained magnitudes | guide_story.md; realism.py | DOC / TASTE (amount) |
| X3 | General tools, not domain-specific features | memory general-tools-not-domain-specific | DOC (coordinator) |
| X4 | Terrain: narrative vocabulary above heightmap ops; detail by scale (tiling for <= 0.5 m) | terrain_guide.md; memory terrain-direction, terrain-detail-by-scale | DOC |
| X5 | Experimental: build small, test on a real model, pivot | memory experimental-approach | DOC (coordinator) |

## Memory files not given a row (why)

- threads-handover-2026-10-07, faces-handover-2026-10-11: dated status snapshots; their method parts are rows H1-H5.
- hifipushie-project, default-human-path: project description / direction (CLAUDE.md, guide.md "Which path").
- overboard-for-todos, tooling-lessons-as-cards, consumers-file-cards, thread-roster, grade-agents-process-tooling,
  agent-job-slots, parallel-agents-memory-cap, machine-memory-limits, godot-without-focus: coordinator behaviour or
  folded into R6 / R7 / P23 / E5.
- fitter-whitepaper-idea, open-source-fitter-licensing: parked ideas / Joe's open policy, not a character rule.
- voice-reference-clip-guidance: another project's doc.
- the private-likeness memory: private; its only repo rule is R3.
- codify-durable-learning: this ledger.
