# STATE: the front door -- what an agent meets: find_tool, guides, next lines, refusals (2026-11-12)

An agent sees only tool names, descriptions, find_tool answers, guide topics, each tool's "next:" line and refusals.
This page is that surface for every domain (it began as "mcp-rules", the clothing and review rules of 2026-10-19; the
tools it listed then were deleted in the legacy cuts, C409 / C411). History: docs/notes/mcp_audit.md "## History".

## Current best (on main)
- 102 tools, 14 native (core); the rest through call_tool. find_tool("") lists them by domain (2.7k characters).
- find_tool (find_route.py, C400 + C435): a job's domain comes from its subject words; a domain's steps lead in order;
  a tool FOR the job beats one that mentions it; "make / build / model / sculpt / create a <thing>" that no domain names
  leads with put_model and the playbook; KEYWORDS hold plain words a tool's name and purpose lack.
  Measured: 34 of 35 on the first list; on 49 jobs worded afresh 33 found before C435, 47 of 51 after (FRESH in
  tests/test_find_jobs.py; its four misses carry their reasons). FRESH is a regression list now: measure next on new words.
- next lines: heads, clothes and skin from their route modules; creatures and props from next_steps.after_save /
  after_model_look (put_model, edit_model, look). Terrain, plants, clutter, hair export: none yet.
- Refusals that name the fix: unknown blob shape (spec.BLOB_SHAPES), kits, materials, paint, walls, plan keys.
- A dressed character: export_asset takes a chain garment's step-10 file (docs/state/dressed_export.md, C434).

## Open, by what it costs an agent (from the area re-review: /mnt/data/hifipushie/review_20261112/<area>.md)
1. block_in_start cannot be called as its own example shows: no `size` in the example, read unguarded
   (humanfit_map.py:95, :282); sex left out silently gives the male mean (blockin_models.py:113). Read, not run.
2. Dead ends: approvals (a garment's step 9 and 7a, a head before skin) have no tool; terrain's designer questions
   (eight texts forbid answering, none says what to do alone); stage "hang_rows_failed" has no answer (tools_cloth.py).
3. review_view, the only independent look, is worded for clothes (DETAIL_WORDS, the look_chain refusal, the "hang"
   checklist: tools_model.py:528-564). Garment trials call it: change with the garment thread.
4. No pose while modelling (store ops: set, delete, rename, move, scale_r): "turn the head" has no tool.
5. Joints, bones and blobs accept any key (paint, walls, style refuse unknown ones); terrain ignores unknown keys
   outside rivers; hair ignores solid-lock keys once loose or tie is set.
6. The one-picture route (fit_concept_camera, look_matched, feature_tiles) is in no guide*.md; feature_tiles answers
   with a shell command on a machine path where an agent has review_view (matched.py:329).
7. Old head route still handed over: likeness_guide.md:94-121 teaches fit_likeness, which refuses block-in models.
8. No worked example a tool returns (kit_reference is 49k characters; examples/fox.json is 2.3k and unnamed).
9. guide(topic="traps") and "gates" serve developer notes from docs/notes (Garrett's collars, the machine).
10. No environment render takes the GPU lock (terrain_views.py:353, veg_look.py:296, clutter_kit.py:48).
11. README.md's tool table has 12 rows.

## Decisions in force
- The domain is read from subject words, never from a word match; nothing is read off scores (C400).
- A keyword is added only for a measured miss, and kept specific: it makes its tool "for the job".
- Next lines are built from the result or the spec's state, never fixed boilerplate.
- An unknown blob shape is refused at compile (none in 6,211 saved specs on 2026-11-12).

## Commands
- `bin/slot uv run pytest tests/test_find_jobs.py tests/test_front_door.py tests/test_skill_file.py`
- A fresh measure: write 40-50 jobs in your own words with the tools you expect, count top-three hits with
  tests/test_find_jobs.py's `ranked`, fix by rule or keyword, then add them to FRESH.

NEXT: item 1 (run block_in_start as documented on a public head; fill size, refuse a missing sex), then items 5 and 6.
