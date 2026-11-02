# Heads from pictures (block-in route through the MCP) — STATE 2026-11-02

Branch face-route (worktree .claude/worktrees/face-route). Audit: /mnt/data/hifipushie/readiness/faces.md.

## What the tools hold now (commits 5ffab5a2, 8c65dd50)
- find_tool: a person word plus a picture word, with no other domain named, pins block_in_start
  (head_route.pin_block_in). "pose an expression on a finished head" ranks set_expression first.
- `human` defaults to source="human" (one mesh). block_in_start has no `attach` / `gnm_base` over the MCP;
  lid_read(match="pose") is refused.
- fit_human, nudge_human, fit_likeness and human_reference(fit=True) refuse a block-in model and name block_in_step
  with `mm:`. human_reference(fit=False) keeps the chain's record (rj["blockin"]).
- block_in_step refuses a head with no block_in_solve (hand_first=True overrides) and refuses a posed model.
  A move over 1 sd warns; an `mm:` move is read against its measure's own sd (blockin.over_sd).
- set_expression(name, mix | preset): a NEW model (<name>_<preset>) whose base.head.expression is the mix added to the
  head's own; base.head.posed records where it came from. Presets: smile (reviewed earlier as smile_tess), open_mouth,
  frown, surprise, blink (not reviewed). cheekPuff and eyeLook are refused.
- GnmFace.shape_coeffs: shapes built as vertex offsets (jawOpen, smile, cheekSquint) are projected on GNM's expression
  basis. This was the known failure test_jaw_open_moves_gnms_own_pieces_and_opens_the_bag (removed from
  known_failures.txt).
- Every human / likeness reply ends in `next:` (head_route.with_next, hooked in server._tool_with_errors). The skin
  tools are left to the skin thread.
- block_in_look(judge=True): the judging sheet, per view photo | 50 % blend | pictures projected as skin | clay, drawn
  with the software render (blockin_judge.py). It replaces spikes/reruns/jsheet.py (Blender stage), which can now be
  deleted.
- Guides: human_guide, guide 4d, human_tools, human_shape, blockin_guide, blockin_solve, blockin_tools,
  blockin_features, tools_guide. Ledger rows C270-C274 (numbers chosen to avoid colliding with parallel agents).

## Verified
- tests/test_head_route.py, test_find_tool, test_toolsets, test_codified and test_mcp_rules: 42 passed.
- The jaw test and test_face_shapes_on_gnms_own_mouth pass.
- Over the MCP, on the Tess pictures (non-private), with the views' stored points:
  - block_in_start ran (766 s at load 90) and its reply ends in next:.
  - block_in_step was refused (no solve) and fit_human was refused (block-in model).

## Not verified
- The full area run (test_gnm_native, test_face_shapes, test_blockin, test_nativedefault with -m "") finished, but its
  log was not read: /mnt/data/hifipushie/scratch_faceroute/t2.log.
- The judge sheet render, the expression renders and the hand_first step on a posed model were still running at
  handover: /mnt/data/hifipushie/scratch_faceroute/e2e3.log, images j_fr_t1.png and l_<preset>.png in that folder.
  No picture was looked at.
- block_in_solve over the MCP timed out at 2700 s under load.

## Open (audit blockers left)
- 2 (hand-pass instruments), 8 (profiles: a profile view without clicked points is refused at start; this blocked the
  first route run), 9 (vocabulary gaps), 10 (guide leaks). No blind trial yet.
- texture_from_reference was not renamed; it now warns that photo pixels never ship.

NEXT: read t2.log and e2e3.log. Look at j_fr_t1.png and l_*.png beside the Tess pictures and fix what reads wrong.
Then delete spikes/reruns/jsheet.py and run one blind MCP-only agent on a non-private picture set (front, 3/4, and a
profile with points).
