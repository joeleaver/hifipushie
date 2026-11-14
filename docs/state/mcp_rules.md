# STATE: the front door -- what an agent meets: find_tool, guides, next lines, refusals (2026-11-14)

An agent sees only tool names, descriptions, find_tool answers, guide topics, each tool's "next:" line and refusals.
This page is that surface for every domain (it began as "mcp-rules", the clothing and review rules of 2026-10-19; the
tools it listed then were deleted in the legacy cuts, C409 / C411). History: docs/notes/mcp_audit.md "## History".

## Current best (on main)
- 107 tools in 14 domains, 14 native (core); the rest through call_tool. find_tool("") lists them by domain; the
  README's table is the same registry (tests/test_readme.py).
- find_tool (find_route.py, C400 + C436): a job's domain comes from its subject words; a domain's steps lead in order;
  a tool FOR the job beats one that mentions it; "make / build / model / sculpt / create a <thing>" that no domain names
  leads with put_model and the playbook; KEYWORDS hold plain words a tool's name and purpose lack. Pins: a person + a
  picture -> block_in_start; a feature of a block-in head -> block_in_step, face_ruler (C458); the dressed character's
  export -> export_asset (C464). FRESH in tests/test_find_jobs.py is the regression list: measure next on new words.
- Guides an agent is sent to are packaged and written for it: the playbook, "example" (a whole fox, a whole chair:
  C460), "traps" and "gates" (C461), the one-picture route (C443), the likeness guide's route (C458).
- next lines: heads, clothes and skin from their route modules; creatures and props from next_steps.after_save /
  after_model_look (put_model, edit_model, look). Terrain, plants, clutter, hair export: none yet.
- A key that does nothing is said: joints, bones, blobs and prefab elements REFUSE an unknown key (spec_keys: C442,
  C449); groom_hair WARNS about a solid-lock key the grow did not read (C449); the terrain report WARNS about a key no
  terrain code names (C456). Also refused by name: blob shapes, kits, materials, paint, walls, plan keys.
- Terrain views, plant looks and clutter looks wait in the GPU queue (C445). A dressed character: export_asset takes a
  chain garment's step-10 file and its LOD files (docs/state/dressed_export.md).

## Open, by what it costs an agent (from the area re-review: /mnt/data/hifipushie/review_20261112/<area>.md)
1. Dead ends (Joe's): approvals (a garment's step 9 and 7a, a head before skin) have no tool; terrain's designer
   questions (eight texts forbid answering, none says what to do alone); stage "hang_rows_failed" has no answer.
2. review_view, the only independent look, is worded for clothes (DETAIL_WORDS, the look_chain refusal, the "hang"
   checklist: tools_model.py). Garment trials call it: change with the garment thread.
3. No pose while modelling (store ops: set, delete, rename, move, scale_r): "turn the head" has no tool.
4. block_in_start (C437 fixed its own example): a profile needs clicked points; nothing fits a profile's camera.
5. Keys: a real key written in the wrong terrain section passes (no list per section: 19 sections, 67 modules); the
   terrain view's 6 GB in the GPU queue is a guess, not a measured peak.
6. kit_reference is 49k characters with no section argument; "tailoring" still serves a repo note (garment thread).
7. Not run end to end by a blind agent: the one-picture route; the example topic as a start. Whether fit_likeness
   stays at all is the legacy thread's.

## Decisions in force
- The domain is read from subject words, never from a word match; nothing is read off scores (C400).
- A keyword or a pin is added only for a measured miss, and kept specific; a feature word as a keyword was tried and
  taken out ("paint the lips red" came back to the head: C458).
- Next lines are built from the result or the spec's state, never fixed boilerplate.
- A key list is read off the code, not off the saved specs (C449). Where no list can hold (hair's modes, terrain's
  sections), what was read is recorded, or the source is asked whether it names the key at all (C456).
- Saved models decide refusal or warning: measured first (301 hair models; 218 terrains; 21,751 specs).

## Commands
- `bin/slot uv run pytest tests/test_find_jobs.py tests/test_front_door.py tests/test_skill_file.py`
- A fresh measure: write 40-50 jobs in your own words with the tools you expect, count top-three hits with
  tests/test_find_jobs.py's `ranked`, fix by rule or pin, then add them to FRESH.
- Rules that bit: a tool-description change runs tests/test_toolsets.py with -m "" (slow tier); a constant goes in
  its family's base module (tests/test_constants_address.py); a new tool goes in the README's row.

NEXT: the re-review's list is done except items 1-3 (Joe's, the garment thread's, the coordinator's). The next
useful measure is a blind agent making a creature from one picture through the front door as it now stands.
