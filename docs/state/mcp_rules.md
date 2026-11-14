# STATE: the front door -- what an agent meets: find_tool, guides, next lines, refusals (2026-11-12)

An agent sees only tool names, descriptions, find_tool answers, guide topics, each tool's "next:" line and refusals.
This page is that surface for every domain (it began as "mcp-rules", the clothing and review rules of 2026-10-19; the
tools it listed then were deleted in the legacy cuts, C409 / C411). History: docs/notes/mcp_audit.md "## History".

## Current best (on main)
- 102 tools, 14 native (core); the rest through call_tool. find_tool("") lists them by domain (2.7k characters).
- find_tool (find_route.py, C400 + C436): a job's domain comes from its subject words; a domain's steps lead in order;
  a tool FOR the job beats one that mentions it; "make / build / model / sculpt / create a <thing>" that no domain names
  leads with put_model and the playbook; KEYWORDS hold plain words a tool's name and purpose lack.
  Measured: 34 of 35 on the first list; on 49 jobs worded afresh 33 found before C436, 47 of 51 after (FRESH in
  tests/test_find_jobs.py; its four misses carry their reasons). FRESH is a regression list now: measure next on new words.
- next lines: heads, clothes and skin from their route modules; creatures and props from next_steps.after_save /
  after_model_look (put_model, edit_model, look). Terrain, plants, clutter, hair export: none yet.
- Refusals that name the fix: unknown blob shape (spec.BLOB_SHAPES), unknown key on a joint / bone / blob
  (spec_keys), kits, materials, paint, walls, plan keys.
- A dressed character: export_asset takes a chain garment's step-10 file (docs/state/dressed_export.md, C434).

## Open, by what it costs an agent (from the area re-review: /mnt/data/hifipushie/review_20261112/<area>.md)
1. DONE (C437): block_in_start called as its own example shows now works (a picture's size is read from the file, a
   missing sex is refused before the detector runs, the profile refusal names its points). Still open there: a profile
   needs clicked points, and nothing fits a profile's camera from its outline.
2. Dead ends: approvals (a garment's step 9 and 7a, a head before skin) have no tool; terrain's designer questions
   (eight texts forbid answering, none says what to do alone); stage "hang_rows_failed" has no answer (tools_cloth.py).
3. review_view, the only independent look, is worded for clothes (DETAIL_WORDS, the look_chain refusal, the "hang"
   checklist: tools_model.py:528-564). Garment trials call it: change with the garment thread.
4. No pose while modelling (store ops: set, delete, rename, move, scale_r): "turn the head" has no tool.
5. DONE for joints, bones, blobs and the elements inside prefabs (C442, C449: spec_keys.py; C442 wrongly refused
   "hollow" and "chips" on a bone, fixed) and for hair's solid-lock keys beside loose / tied hair (C449: groom_hair
   WARNS about each written key the grow did not read; a refusal would have stopped 301 current models).
   Terrain (C456): the report WARNS about a key no terrain code names (terrain.unnamed_keys); a real key in the
   wrong section is NOT caught (no list per section: 19 sections across 67 modules).
6. DONE (C443): the one-picture route is a row of the playbook's "Which path" table; feature_tiles answers with one
   review_view call per region. Not run end to end by a blind agent yet.
7. DONE (C458): likeness_guide.md hands a block-in head to face_ruler and block_in_step (fit_likeness refuses it);
   the finder leads a feature job on a block-in head with the hand step. Whether fit_likeness stays: the legacy thread.
8. DONE (C460): guide(topic="example") returns a whole fox and a whole chair, held to examples/ by a test. Still
   open: kit_reference is 49k characters with no section argument.
9. DONE (C461): guide(topic="traps") and "gates" are short packaged topics for an agent (guide_traps.md, guide_gates.md);
   the developer notes stay in docs/notes. "tailoring" still serves a repo note (the garment thread's).
10. DONE (C445): terrain views, plant looks and clutter looks run Blender inside resources.heavy(..., gpu=True);
    tests/test_gpu_lock.py holds it. The terrain view's 6 GB is a guess, not a measured peak.
11. README.md's tool table has 12 rows.

## Decisions in force
- The domain is read from subject words, never from a word match; nothing is read off scores (C400).
- A keyword is added only for a measured miss, and kept specific: it makes its tool "for the job".
- Next lines are built from the result or the spec's state, never fixed boilerplate.
- An unknown blob shape is refused at compile (none in 6,211 saved specs on 2026-11-12); an unknown key on a joint,
  bone or blob before the spec is saved (none in 21,751 saved specs and histories, same day).

## Commands
- `bin/slot uv run pytest tests/test_find_jobs.py tests/test_front_door.py tests/test_skill_file.py`
- A fresh measure: write 40-50 jobs in your own words with the tools you expect, count top-three hits with
  tests/test_find_jobs.py's `ranked`, fix by rule or keyword, then add them to FRESH.

NEXT: item 11, then dressed_export.md fault 4. Joe's or the coordinator's: items 2, 3, 4. A
tool-description change runs tests/test_toolsets.py with -m "" (a slow-tier rule the suite skips); a new constant
goes in its family's base module (tests/test_constants_address.py).
